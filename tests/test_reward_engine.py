"""
tests/test_reward_engine.py

Тесты для brain/motivation/reward_engine.py (Stage M.1).

Покрывает:
  - RewardType enum и значения вознаграждений
  - RewardSignal dataclass
  - RewardEngine.compute() — маппинг action → RewardType
  - RewardEngine.prediction_error()
  - RewardEngine.sliding_mean()
  - История (deque maxlen=100)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from brain.motivation.reward_engine import (
    REWARD_VALUES,
    RewardEngine,
    RewardSignal,
    RewardType,
)
from brain.core.contracts import CognitiveResult, TraceChain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    action: str = "answer",
    confidence: float = 0.7,
    cycle_id: str = "cycle_001",
    metadata: dict | None = None,
) -> CognitiveResult:
    """Создать минимальный CognitiveResult для тестов."""
    return CognitiveResult(
        action=action,
        response="test response",
        confidence=confidence,
        trace=TraceChain(trace_id="t1", session_id="s1", cycle_id=cycle_id),
        cycle_id=cycle_id,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# RewardType — значения
# ---------------------------------------------------------------------------

class TestRewardTypeValues:
    """Проверяем, что все типы вознаграждений имеют правильные значения."""

    def test_epistemic_value(self):
        assert REWARD_VALUES[RewardType.EPISTEMIC] == pytest.approx(0.8)

    def test_accuracy_value(self):
        assert REWARD_VALUES[RewardType.ACCURACY] == pytest.approx(1.0)

    def test_coherence_value(self):
        assert REWARD_VALUES[RewardType.COHERENCE] == pytest.approx(0.6)

    def test_completion_value(self):
        assert REWARD_VALUES[RewardType.COMPLETION] == pytest.approx(0.7)

    def test_efficiency_value(self):
        assert REWARD_VALUES[RewardType.EFFICIENCY] == pytest.approx(0.3)

    def test_penalty_value(self):
        assert REWARD_VALUES[RewardType.PENALTY] == pytest.approx(-0.5)

    def test_all_six_types_exist(self):
        types = {rt for rt in RewardType}
        assert len(types) == 6


# ---------------------------------------------------------------------------
# RewardSignal — dataclass
# ---------------------------------------------------------------------------

class TestRewardSignal:
    """Проверяем поля RewardSignal."""

    def test_fields_present(self):
        sig = RewardSignal(
            type=RewardType.ACCURACY,
            value=1.0,
            source="answer",
            cycle_id="cycle_42",
        )
        assert sig.type == RewardType.ACCURACY
        assert sig.value == pytest.approx(1.0)
        assert sig.source == "answer"
        assert sig.cycle_id == "cycle_42"

    def test_timestamp_auto_set(self):
        before = time.time()
        sig = RewardSignal(type=RewardType.EPISTEMIC, value=0.8, source="learn", cycle_id="c1")
        after = time.time()
        assert before <= sig.timestamp <= after

    def test_type_is_enum(self):
        sig = RewardSignal(type=RewardType.PENALTY, value=-0.5, source="refuse", cycle_id="c1")
        assert isinstance(sig.type, RewardType)


# ---------------------------------------------------------------------------
# RewardEngine.compute() — маппинг action → RewardType
# ---------------------------------------------------------------------------

class TestRewardEngineCompute:
    """Проверяем маппинг action → RewardType в compute()."""

    def setup_method(self):
        self.engine = RewardEngine()

    def test_learn_action_gives_epistemic(self):
        result = _make_result(action="learn")
        sig = self.engine.compute(result)
        assert sig.type == RewardType.EPISTEMIC
        assert sig.value == pytest.approx(0.8)

    def test_store_action_gives_epistemic(self):
        result = _make_result(action="store")
        sig = self.engine.compute(result)
        assert sig.type == RewardType.EPISTEMIC

    def test_answer_action_gives_accuracy(self):
        result = _make_result(action="answer")
        sig = self.engine.compute(result)
        assert sig.type == RewardType.ACCURACY
        assert sig.value == pytest.approx(1.0)

    def test_respond_action_gives_accuracy(self):
        result = _make_result(action="respond")
        sig = self.engine.compute(result)
        assert sig.type == RewardType.ACCURACY

    def test_resolve_action_gives_coherence(self):
        result = _make_result(action="resolve")
        sig = self.engine.compute(result)
        assert sig.type == RewardType.COHERENCE
        assert sig.value == pytest.approx(0.6)

    def test_clarify_action_gives_coherence(self):
        result = _make_result(action="clarify")
        sig = self.engine.compute(result)
        assert sig.type == RewardType.COHERENCE

    def test_complete_action_gives_completion(self):
        result = _make_result(action="complete")
        sig = self.engine.compute(result)
        assert sig.type == RewardType.COMPLETION
        assert sig.value == pytest.approx(0.7)

    def test_refuse_action_gives_penalty(self):
        result = _make_result(action="refuse")
        sig = self.engine.compute(result)
        assert sig.type == RewardType.PENALTY
        assert sig.value == pytest.approx(-0.5)

    def test_efficiency_high_confidence_fast(self):
        """Высокая уверенность + быстрый ответ → EFFICIENCY."""
        result = _make_result(
            action="answer",
            confidence=0.95,
            metadata={"elapsed_ms": 50},
        )
        sig = self.engine.compute(result)
        assert sig.type == RewardType.EFFICIENCY
        assert sig.value == pytest.approx(0.3)

    def test_no_efficiency_slow_response(self):
        """Высокая уверенность, но медленный ответ → не EFFICIENCY."""
        result = _make_result(
            action="answer",
            confidence=0.95,
            metadata={"elapsed_ms": 500},
        )
        sig = self.engine.compute(result)
        assert sig.type != RewardType.EFFICIENCY

    def test_signal_source_matches_action(self):
        result = _make_result(action="learn", cycle_id="cycle_99")
        sig = self.engine.compute(result)
        assert sig.source == "learn"
        assert sig.cycle_id == "cycle_99"

    def test_signal_added_to_history(self):
        result = _make_result(action="answer")
        self.engine.compute(result)
        assert len(self.engine._history) == 1


# ---------------------------------------------------------------------------
# RewardEngine.prediction_error()
# ---------------------------------------------------------------------------

class TestPredictionError:
    """Проверяем вычисление ошибки предсказания."""

    def setup_method(self):
        self.engine = RewardEngine()

    def test_positive_error(self):
        """actual > expected → положительная ошибка."""
        err = self.engine.prediction_error(actual=1.0, expected=0.7)
        assert err == pytest.approx(0.3)

    def test_negative_error(self):
        """actual < expected → отрицательная ошибка."""
        err = self.engine.prediction_error(actual=0.3, expected=0.7)
        assert err == pytest.approx(-0.4)

    def test_zero_error(self):
        """actual == expected → нулевая ошибка."""
        err = self.engine.prediction_error(actual=0.5, expected=0.5)
        assert err == pytest.approx(0.0)

    def test_penalty_error(self):
        """Штраф: actual=-0.5, expected=0.5 → error=-1.0."""
        err = self.engine.prediction_error(actual=-0.5, expected=0.5)
        assert err == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# RewardEngine.sliding_mean()
# ---------------------------------------------------------------------------

class TestSlidingMean:
    """Проверяем скользящее среднее по истории."""

    def setup_method(self):
        self.engine = RewardEngine()

    def test_empty_history_returns_zero(self):
        assert self.engine.sliding_mean() == pytest.approx(0.0)

    def test_single_signal(self):
        result = _make_result(action="answer")
        self.engine.compute(result)
        assert self.engine.sliding_mean() == pytest.approx(1.0)

    def test_multiple_signals_mean(self):
        """Среднее по нескольким сигналам."""
        self.engine.compute(_make_result(action="answer"))    # +1.0
        self.engine.compute(_make_result(action="learn"))     # +0.8
        self.engine.compute(_make_result(action="complete"))  # +0.7
        expected_mean = (1.0 + 0.8 + 0.7) / 3
        assert self.engine.sliding_mean() == pytest.approx(expected_mean, abs=1e-6)

    def test_history_maxlen_100(self):
        """История ограничена 100 сигналами."""
        for _ in range(150):
            self.engine.compute(_make_result(action="answer"))
        assert len(self.engine._history) == 100

    def test_custom_history_size(self):
        """Можно задать кастомный размер истории."""
        engine = RewardEngine(history_size=5)
        for _ in range(10):
            engine.compute(_make_result(action="answer"))
        assert len(engine._history) == 5
