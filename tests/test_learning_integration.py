"""
tests/test_learning_integration.py

Интеграционные тесты подсистемы обучения (Этап J).

Проверяет:
  - OnlineLearner вызывается после каждого когнитивного цикла
  - OnlineLearner пропускает обновление при confidence < 0.3
  - KnowledgeGapDetector обнаруживает MISSING пробел (total == 0)
  - KnowledgeGapDetector обнаруживает WEAK пробел (confidence < threshold)
  - KnowledgeGapDetector не создаёт пробел при высоком confidence
  - ReplayEngine.run_replay_session() вызывается в handle_consolidate_memory
  - Backward compatibility: CognitiveCore без конкретного MemoryManager
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brain.cognition.cognitive_core import CognitiveCore
from brain.core.contracts import CognitiveResult
from brain.learning import (
    GapSeverity,
    GapType,
    KnowledgeGapDetector,
    OnlineLearner,
    OnlineLearningUpdate,
    ReplayEngine,
    ReplaySession,
    ReplayStrategy,
)
from brain.memory.memory_manager import MemoryManager

# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture
def mm(tmp_path):
    """MemoryManager с временной директорией."""
    m = MemoryManager(data_dir=str(tmp_path))
    m.start()
    yield m
    m.stop(save=False)


# ---------------------------------------------------------------------------
# Тест 1: OnlineLearner вызывается после когнитивного цикла
# ---------------------------------------------------------------------------

def test_online_learner_called_after_cycle(mm: MemoryManager) -> None:
    """OnlineLearner.update() должен вызываться ровно один раз после core.run()."""
    core = CognitiveCore(memory_manager=mm)
    assert core._online_learner is not None, (
        "OnlineLearner должен быть создан при конкретном MemoryManager"
    )

    update_calls: list[CognitiveResult] = []
    original_update = core._pipeline._online_learner.update

    def tracking_update(result: CognitiveResult) -> OnlineLearningUpdate:
        update_calls.append(result)
        return original_update(result)

    core._pipeline._online_learner.update = tracking_update  # type: ignore[method-assign]

    core.run("Что такое нейрон?")

    assert len(update_calls) == 1, "update() должен быть вызван ровно один раз"
    assert hasattr(update_calls[0], "confidence")
    assert hasattr(update_calls[0], "action")


# ---------------------------------------------------------------------------
# Тест 2: OnlineLearner пропускает при confidence < 0.3
# ---------------------------------------------------------------------------

def test_online_learner_skips_low_confidence(mm: MemoryManager) -> None:
    """OnlineLearner.update() должен возвращать пустой update при confidence < 0.3."""
    learner = OnlineLearner(memory=mm)

    # CognitiveResult с низким confidence (ниже порога 0.3)
    low_conf_result = MagicMock()
    low_conf_result.confidence = 0.1
    low_conf_result.action = "answer"
    low_conf_result.cycle_id = "test_cycle_low_001"
    low_conf_result.memory_refs = []
    low_conf_result.source_refs = []
    low_conf_result.goal = "тест"

    update = learner.update(low_conf_result)

    # При confidence < 0.3 — no-op: нет подтверждений, опровержений, ассоциаций
    assert update.facts_confirmed == [], "Не должно быть подтверждённых фактов"
    assert update.facts_denied == [], "Не должно быть опровергнутых фактов"
    assert update.associations_updated == [], "Не должно быть обновлённых ассоциаций"


# ---------------------------------------------------------------------------
# Тест 3: KnowledgeGapDetector — MISSING пробел (total == 0)
# ---------------------------------------------------------------------------

def test_gap_detector_missing_gap(mm: MemoryManager) -> None:
    """KnowledgeGapDetector должен создавать MISSING/HIGH пробел при total == 0."""
    detector = KnowledgeGapDetector(memory=mm)

    # MemorySearchResult без результатов
    mock_result = MagicMock()
    mock_result.total = 0
    mock_result.best_semantic.return_value = None

    gap = detector.analyze(query="квантовый компьютер", search_result=mock_result)

    assert gap is not None, "Должен быть создан пробел при total == 0"
    assert gap.gap_type == GapType.MISSING
    assert gap.severity == GapSeverity.HIGH
    assert "квантовый компьютер" in gap.concept


# ---------------------------------------------------------------------------
# Тест 4: KnowledgeGapDetector — WEAK пробел (confidence < threshold)
# ---------------------------------------------------------------------------

def test_gap_detector_weak_gap(mm: MemoryManager) -> None:
    """KnowledgeGapDetector должен создавать WEAK/MEDIUM пробел при confidence < weak_threshold."""
    detector = KnowledgeGapDetector(memory=mm, weak_threshold=0.5)

    # Мок top-1 результата с низким confidence
    mock_best = MagicMock()
    mock_best.confidence = 0.2
    mock_best.age_days.return_value = 1.0  # свежий — не OUTDATED

    mock_result = MagicMock()
    mock_result.total = 1
    mock_result.best_semantic.return_value = mock_best

    gap = detector.analyze(query="нейропластичность", search_result=mock_result)

    assert gap is not None, "Должен быть создан пробел при confidence < weak_threshold"
    assert gap.gap_type == GapType.WEAK
    assert gap.severity == GapSeverity.MEDIUM
    assert gap.metadata.get("confidence") == 0.2


# ---------------------------------------------------------------------------
# Тест 5: KnowledgeGapDetector — нет пробела (высокий confidence, свежий)
# ---------------------------------------------------------------------------

def test_gap_detector_no_gap(mm: MemoryManager) -> None:
    """KnowledgeGapDetector не должен создавать пробел при высоком confidence и свежем факте."""
    detector = KnowledgeGapDetector(memory=mm, weak_threshold=0.5, outdated_days=30.0)

    # Мок top-1 результата с высоким confidence и свежей датой
    mock_best = MagicMock()
    mock_best.confidence = 0.9
    mock_best.age_days.return_value = 1.0  # свежий (1 день < 30 дней)

    mock_result = MagicMock()
    mock_result.total = 2
    mock_result.best_semantic.return_value = mock_best

    gap = detector.analyze(query="нейрон", search_result=mock_result)

    assert gap is None, "При высоком confidence и свежем факте пробела быть не должно"


# ---------------------------------------------------------------------------
# Тест 6: ReplayEngine вызывается в handle_consolidate_memory
# ---------------------------------------------------------------------------

def test_replay_engine_in_autonomous(tmp_path) -> None:
    """ReplayEngine.run_replay_session() должен вызываться в handle_consolidate_memory."""
    from brain.cli import run_autonomous

    replay_calls: list[dict] = []

    def mock_run_replay(
        self: ReplayEngine,
        strategy: ReplayStrategy = ReplayStrategy.IMPORTANCE_BASED,
        batch_size: int | None = None,
        force: bool = False,
    ) -> ReplaySession:
        replay_calls.append({"force": force, "strategy": strategy})
        return ReplaySession(
            session_id="test_session_001",
            strategy=strategy,
            episodes_replayed=0,
            reinforced=0,
            stale_removed=0,
            duration_ms=1.0,
        )

    with patch.object(ReplayEngine, "run_replay_session", mock_run_replay):
        # 5 cognitive_cycle (NORMAL) + 1 consolidate_memory (LOW) = 6 задач
        result = run_autonomous(
            data_dir=str(tmp_path),
            ticks=6,
        )

    assert result == 0, "run_autonomous должен вернуть 0 при успехе"
    assert len(replay_calls) >= 1, "ReplayEngine.run_replay_session() должен быть вызван"
    # force=False — CPU-aware режим (не принудительный запуск)
    assert all(not call["force"] for call in replay_calls), (
        "run_replay_session должен вызываться с force=False"
    )


# ---------------------------------------------------------------------------
# Тест 7: Backward compatibility — CognitiveCore без конкретного MemoryManager
# ---------------------------------------------------------------------------

def test_learning_backward_compat() -> None:
    """CognitiveCore должен работать без Learning subsystem при Protocol-only memory."""
    # Mock MemoryManagerProtocol (не конкретный MemoryManager)
    mock_mm = MagicMock()
    mock_mm.retrieve = MagicMock(return_value=MagicMock(
        results=[],
        total=0,
        best_semantic=MagicMock(return_value=None),
    ))
    mock_mm.store = MagicMock()

    core = CognitiveCore(memory_manager=mock_mm)

    # Learning subsystem НЕ должен быть активирован для Protocol-only memory
    assert core._gap_detector is None, (
        "gap_detector должен быть None для Protocol-only memory"
    )
    assert core._online_learner is None, (
        "online_learner должен быть None для Protocol-only memory"
    )

    # run() должен работать без ошибок
    result = core.run("Что такое нейрон?")
    assert result is not None
    assert hasattr(result, "action")
    assert hasattr(result, "confidence")

    # status() должен отражать отсутствие learning subsystem
    status = core.status()
    assert status["has_gap_detector"] is False
    assert status["has_online_learner"] is False
