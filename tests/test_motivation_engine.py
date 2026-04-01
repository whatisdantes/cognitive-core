"""
tests/test_motivation_engine.py

Тесты для brain/motivation/motivation_engine.py (Stage M.2).

Покрывает:
  - MotivationState dataclass
  - MotivationEngine начальное состояние
  - EMA обновление epistemic_score (α=0.1)
  - cycle_count инкремент
  - Decay ×0.95 каждые 100 циклов
  - is_frustrated при низком epistemic_score
  - preferred_goal_types обновление
  - Side effects: GoalManager.push при epistemic_score > 0.7
  - Side effects: ReplayEngine.mark_as_high_value при prediction_error > 0.2
  - NullObject pattern (goal_manager=None, replay_engine=None)
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from brain.motivation.motivation_engine import (
    ALPHA,
    DECAY_EVERY,
    DECAY_FACTOR,
    FRUSTRATION_THRESHOLD,
    CURIOSITY_TRIGGER_THRESHOLD,
    MotivationEngine,
    MotivationState,
)
from brain.motivation.reward_engine import RewardSignal, RewardType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signal(
    reward_type: RewardType = RewardType.ACCURACY,
    value: float = 1.0,
    cycle_id: str = "c1",
) -> RewardSignal:
    return RewardSignal(type=reward_type, value=value, source="test", cycle_id=cycle_id)


# ---------------------------------------------------------------------------
# MotivationState — dataclass
# ---------------------------------------------------------------------------

class TestMotivationState:
    """Проверяем поля MotivationState."""

    def test_default_values(self):
        state = MotivationState()
        assert state.epistemic_score == pytest.approx(0.0)
        assert state.preferred_goal_types == {}
        assert state.is_frustrated is False
        assert state.cycle_count == 0

    def test_custom_values(self):
        state = MotivationState(
            epistemic_score=0.5,
            preferred_goal_types={"explore": 0.8},
            is_frustrated=True,
            cycle_count=42,
        )
        assert state.epistemic_score == pytest.approx(0.5)
        assert state.preferred_goal_types == {"explore": 0.8}
        assert state.is_frustrated is True
        assert state.cycle_count == 42


# ---------------------------------------------------------------------------
# MotivationEngine — начальное состояние
# ---------------------------------------------------------------------------

class TestMotivationEngineInit:
    """Проверяем начальное состояние MotivationEngine."""

    def test_initial_state_zero(self):
        engine = MotivationEngine()
        state = engine.state
        assert state.epistemic_score == pytest.approx(0.0)
        assert state.cycle_count == 0
        assert state.is_frustrated is False

    def test_no_goal_manager_by_default(self):
        engine = MotivationEngine()
        assert engine._goal_manager is None

    def test_no_replay_engine_by_default(self):
        engine = MotivationEngine()
        assert engine._replay_engine is None

    def test_accepts_goal_manager(self):
        gm = MagicMock()
        engine = MotivationEngine(goal_manager=gm)
        assert engine._goal_manager is gm

    def test_accepts_replay_engine(self):
        re = MagicMock()
        engine = MotivationEngine(replay_engine=re)
        assert engine._replay_engine is re


# ---------------------------------------------------------------------------
# EMA обновление
# ---------------------------------------------------------------------------

class TestEMAUpdate:
    """Проверяем EMA обновление epistemic_score."""

    def test_ema_single_update(self):
        """После одного обновления: score = α * value + (1-α) * 0."""
        engine = MotivationEngine()
        sig = _signal(value=1.0)
        state = engine.update(sig)
        expected = ALPHA * 1.0 + (1 - ALPHA) * 0.0
        assert state.epistemic_score == pytest.approx(expected)

    def test_ema_two_updates(self):
        """После двух обновлений: EMA накапливается."""
        engine = MotivationEngine()
        engine.update(_signal(value=1.0))
        state = engine.update(_signal(value=0.0))
        # После 1-го: score1 = 0.1 * 1.0 = 0.1
        # После 2-го: score2 = 0.1 * 0.0 + 0.9 * 0.1 = 0.09
        assert state.epistemic_score == pytest.approx(0.09, abs=1e-9)

    def test_ema_negative_signal(self):
        """Отрицательный сигнал (PENALTY) снижает epistemic_score."""
        engine = MotivationEngine()
        # Сначала поднимаем score
        for _ in range(10):
            engine.update(_signal(value=1.0))
        score_before = engine.state.epistemic_score
        # Теперь штраф
        state = engine.update(_signal(reward_type=RewardType.PENALTY, value=-0.5))
        assert state.epistemic_score < score_before

    def test_ema_alpha_constant(self):
        """ALPHA = 0.1 по спецификации."""
        assert ALPHA == pytest.approx(0.1)

    def test_update_returns_state(self):
        """update() возвращает MotivationState."""
        engine = MotivationEngine()
        result = engine.update(_signal())
        assert isinstance(result, MotivationState)


# ---------------------------------------------------------------------------
# cycle_count
# ---------------------------------------------------------------------------

class TestCycleCount:
    """Проверяем инкремент cycle_count."""

    def test_cycle_count_increments(self):
        engine = MotivationEngine()
        for i in range(5):
            state = engine.update(_signal())
        assert state.cycle_count == 5

    def test_cycle_count_starts_at_zero(self):
        engine = MotivationEngine()
        assert engine.state.cycle_count == 0


# ---------------------------------------------------------------------------
# Decay
# ---------------------------------------------------------------------------

class TestDecay:
    """Проверяем decay ×0.95 каждые 100 циклов."""

    def test_decay_factor_constant(self):
        assert DECAY_FACTOR == pytest.approx(0.95)

    def test_decay_every_constant(self):
        assert DECAY_EVERY == 100

    def test_decay_applied_at_cycle_100(self):
        """На 100-м цикле применяется decay."""
        engine = MotivationEngine()
        # Накапливаем score
        for _ in range(99):
            engine.update(_signal(value=1.0))
        score_before_decay = engine.state.epistemic_score

        # 100-й цикл — должен применить decay
        state = engine.update(_signal(value=1.0))

        # После EMA обновления применяется decay:
        # score_after_ema = ALPHA * 1.0 + (1-ALPHA) * score_before_decay
        # score_final = score_after_ema * DECAY_FACTOR
        score_after_ema = ALPHA * 1.0 + (1 - ALPHA) * score_before_decay
        expected = score_after_ema * DECAY_FACTOR
        assert state.epistemic_score == pytest.approx(expected, rel=1e-6)

    def test_no_decay_before_100_cycles(self):
        """До 100-го цикла decay не применяется."""
        engine = MotivationEngine()
        for _ in range(50):
            engine.update(_signal(value=1.0))
        # Проверяем, что score соответствует чистому EMA без decay
        # (просто убеждаемся, что score > 0 и не обнулён)
        assert engine.state.epistemic_score > 0.0


# ---------------------------------------------------------------------------
# is_frustrated
# ---------------------------------------------------------------------------

class TestFrustration:
    """Проверяем флаг is_frustrated."""

    def test_frustration_threshold_constant(self):
        assert FRUSTRATION_THRESHOLD == pytest.approx(0.2)

    def test_not_frustrated_initially(self):
        engine = MotivationEngine()
        assert engine.state.is_frustrated is False

    def test_frustrated_when_score_low(self):
        """is_frustrated=True когда epistemic_score < FRUSTRATION_THRESHOLD."""
        engine = MotivationEngine()
        # Один сигнал с value=0.0 → score = 0.0 < 0.2
        state = engine.update(_signal(value=0.0))
        assert state.is_frustrated is True

    def test_not_frustrated_when_score_high(self):
        """is_frustrated=False когда epistemic_score >= FRUSTRATION_THRESHOLD."""
        engine = MotivationEngine()
        # Много положительных сигналов
        for _ in range(20):
            engine.update(_signal(value=1.0))
        state = engine.state
        assert state.is_frustrated is False

    def test_frustration_recovers(self):
        """После серии штрафов и затем положительных сигналов — восстановление."""
        engine = MotivationEngine()
        # Штрафы
        for _ in range(5):
            engine.update(_signal(reward_type=RewardType.PENALTY, value=-0.5))
        assert engine.state.is_frustrated is True
        # Восстановление
        for _ in range(50):
            engine.update(_signal(value=1.0))
        assert engine.state.is_frustrated is False


# ---------------------------------------------------------------------------
# preferred_goal_types
# ---------------------------------------------------------------------------

class TestPreferredGoalTypes:
    """Проверяем обновление preferred_goal_types."""

    def test_epistemic_signal_updates_explore(self):
        """EPISTEMIC сигнал обновляет 'explore_unknown_concept' в preferred_goal_types."""
        engine = MotivationEngine()
        sig = _signal(reward_type=RewardType.EPISTEMIC, value=0.8)
        state = engine.update(sig)
        assert "explore_unknown_concept" in state.preferred_goal_types
        assert state.preferred_goal_types["explore_unknown_concept"] > 0.0

    def test_accuracy_signal_updates_answer(self):
        """ACCURACY сигнал обновляет 'answer_question' в preferred_goal_types."""
        engine = MotivationEngine()
        sig = _signal(reward_type=RewardType.ACCURACY, value=1.0)
        state = engine.update(sig)
        assert "answer_question" in state.preferred_goal_types

    def test_preferred_types_ema_accumulation(self):
        """preferred_goal_types накапливается через EMA."""
        engine = MotivationEngine()
        engine.update(_signal(reward_type=RewardType.EPISTEMIC, value=0.8))
        score1 = engine.state.preferred_goal_types.get("explore_unknown_concept", 0.0)
        engine.update(_signal(reward_type=RewardType.EPISTEMIC, value=0.8))
        score2 = engine.state.preferred_goal_types.get("explore_unknown_concept", 0.0)
        assert score2 > score1


# ---------------------------------------------------------------------------
# Side effects — GoalManager
# ---------------------------------------------------------------------------

class TestGoalManagerSideEffect:
    """Проверяем добавление цели при высоком epistemic_score."""

    def test_explore_goal_added_when_high_epistemic(self):
        """GoalManager.push вызывается когда epistemic_score > CURIOSITY_TRIGGER_THRESHOLD."""
        gm = MagicMock()
        engine = MotivationEngine(goal_manager=gm)
        # Накапливаем высокий score
        for _ in range(30):
            engine.update(_signal(value=1.0))
        # Проверяем, что push был вызван хотя бы раз
        assert gm.push.called

    def test_no_explore_goal_when_low_epistemic(self):
        """GoalManager.push НЕ вызывается при низком epistemic_score."""
        gm = MagicMock()
        engine = MotivationEngine(goal_manager=gm)
        # Один сигнал с низким value
        engine.update(_signal(value=0.0))
        gm.push.assert_not_called()

    def test_no_error_without_goal_manager(self):
        """Нет ошибки если goal_manager=None."""
        engine = MotivationEngine(goal_manager=None)
        for _ in range(30):
            engine.update(_signal(value=1.0))  # не должно бросать исключение

    def test_curiosity_trigger_threshold_constant(self):
        assert CURIOSITY_TRIGGER_THRESHOLD == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Side effects — ReplayEngine
# ---------------------------------------------------------------------------

class TestReplayEngineSideEffect:
    """Проверяем вызов mark_as_high_value при большой prediction_error."""

    def test_replay_triggered_on_high_prediction_error(self):
        """mark_as_high_value вызывается когда prediction_error > 0.2."""
        re = MagicMock()
        engine = MotivationEngine(replay_engine=re)
        # prediction_error = actual - expected = 1.0 - 0.5 = 0.5 > 0.2
        engine.update(_signal(value=1.0), episode_id="ep_001", expected_value=0.5)
        re.mark_as_high_value.assert_called_once_with("ep_001")

    def test_no_replay_when_small_error(self):
        """mark_as_high_value НЕ вызывается при малой prediction_error."""
        re = MagicMock()
        engine = MotivationEngine(replay_engine=re)
        # prediction_error = 1.0 - 0.9 = 0.1 < 0.2
        engine.update(_signal(value=1.0), episode_id="ep_001", expected_value=0.9)
        re.mark_as_high_value.assert_not_called()

    def test_no_replay_without_episode_id(self):
        """mark_as_high_value НЕ вызывается без episode_id."""
        re = MagicMock()
        engine = MotivationEngine(replay_engine=re)
        engine.update(_signal(value=1.0), expected_value=0.5)
        re.mark_as_high_value.assert_not_called()

    def test_no_error_without_replay_engine(self):
        """Нет ошибки если replay_engine=None."""
        engine = MotivationEngine(replay_engine=None)
        engine.update(_signal(value=1.0), episode_id="ep_001", expected_value=0.5)
