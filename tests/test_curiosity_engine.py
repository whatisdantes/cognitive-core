"""
tests/test_curiosity_engine.py

Тесты для brain/motivation/curiosity_engine.py (Stage M.3).

Покрывает:
  - CuriosityEngine.score() — формула 1/max(coverage, 0.01)
  - CuriosityEngine.knowledge_coverage() — подсчёт связей в SemanticMemory
  - Автономный режим: score > 0.8 → GoalManager.push()
  - NullObject pattern (gap_detector=None, goal_manager=None)
  - Граничные случаи: неизвестный концепт, концепт с множеством связей
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brain.motivation.curiosity_engine import (
    CURIOSITY_THRESHOLD,
    CuriosityEngine,
)

# ---------------------------------------------------------------------------
# Helpers — mock SemanticMemory
# ---------------------------------------------------------------------------

def _make_semantic(related_count: int = 0, has_node: bool = True) -> MagicMock:
    """
    Создать mock SemanticMemory.

    Args:
        related_count: количество связанных концептов (get_related возвращает список)
        has_node:      True если get_fact возвращает узел, False если None
    """
    sm = MagicMock()
    sm.get_related.return_value = [MagicMock()] * related_count
    if has_node:
        node = MagicMock()
        node.confidence = 0.9
        sm.get_fact.return_value = node
    else:
        sm.get_fact.return_value = None
    return sm


# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

class TestConstants:
    def test_curiosity_threshold(self):
        assert pytest.approx(0.8) == CURIOSITY_THRESHOLD


# ---------------------------------------------------------------------------
# knowledge_coverage()
# ---------------------------------------------------------------------------

class TestKnowledgeCoverage:
    """Проверяем вычисление knowledge_coverage."""

    def test_unknown_concept_coverage_zero(self):
        """Неизвестный концепт → coverage = 0."""
        sm = _make_semantic(related_count=0, has_node=False)
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.knowledge_coverage("unknown_concept") == pytest.approx(0.0)

    def test_known_concept_no_relations(self):
        """Известный концепт без связей → coverage = 0."""
        sm = _make_semantic(related_count=0, has_node=True)
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.knowledge_coverage("neuron") == pytest.approx(0.0)

    def test_known_concept_with_relations(self):
        """Известный концепт с N связями → coverage = N."""
        sm = _make_semantic(related_count=5, has_node=True)
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.knowledge_coverage("neuron") == pytest.approx(5.0)

    def test_coverage_uses_get_related(self):
        """knowledge_coverage вызывает get_related с top_n=20."""
        sm = _make_semantic(related_count=3)
        engine = CuriosityEngine(semantic_memory=sm)
        engine.knowledge_coverage("test_concept")
        sm.get_related.assert_called_once_with("test_concept", top_n=20)

    def test_coverage_handles_exception(self):
        """При ошибке get_related → coverage = 0 (не бросает исключение)."""
        sm = MagicMock()
        sm.get_related.side_effect = RuntimeError("db error")
        sm.get_fact.return_value = None
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.knowledge_coverage("broken") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# score()
# ---------------------------------------------------------------------------

class TestScore:
    """Проверяем вычисление curiosity score."""

    def test_unknown_concept_max_curiosity(self):
        """Неизвестный концепт → score = 1.0 (максимум)."""
        sm = _make_semantic(related_count=0, has_node=False)
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.score("unknown") == pytest.approx(1.0)

    def test_known_no_relations_max_curiosity(self):
        """Известный концепт без связей → score = 1.0."""
        sm = _make_semantic(related_count=0, has_node=True)
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.score("neuron") == pytest.approx(1.0)

    def test_two_relations_score(self):
        """2 связи → coverage=2 → score = min(1.0, 1/2) = 0.5."""
        sm = _make_semantic(related_count=2, has_node=True)
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.score("neuron") == pytest.approx(0.5)

    def test_five_relations_score(self):
        """5 связей → coverage=5 → score = min(1.0, 1/5) = 0.2."""
        sm = _make_semantic(related_count=5, has_node=True)
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.score("neuron") == pytest.approx(0.2)

    def test_ten_relations_score(self):
        """10 связей → coverage=10 → score = min(1.0, 1/10) = 0.1."""
        sm = _make_semantic(related_count=10, has_node=True)
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.score("neuron") == pytest.approx(0.1)

    def test_score_capped_at_one(self):
        """score никогда не превышает 1.0."""
        sm = _make_semantic(related_count=0, has_node=False)
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.score("anything") <= 1.0

    def test_score_always_positive(self):
        """score всегда > 0."""
        sm = _make_semantic(related_count=100, has_node=True)
        engine = CuriosityEngine(semantic_memory=sm)
        assert engine.score("well_known") > 0.0

    def test_score_returns_float(self):
        """score возвращает float."""
        sm = _make_semantic(related_count=3)
        engine = CuriosityEngine(semantic_memory=sm)
        result = engine.score("concept")
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# Автономный режим — GoalManager
# ---------------------------------------------------------------------------

class TestAutonomousMode:
    """Проверяем добавление цели при высоком curiosity score."""

    def test_goal_added_when_high_curiosity(self):
        """score > 0.8 → GoalManager.push вызывается."""
        sm = _make_semantic(related_count=0, has_node=False)  # score = 1.0 > 0.8
        gm = MagicMock()
        engine = CuriosityEngine(semantic_memory=sm, goal_manager=gm)
        engine.score("unknown_concept")
        assert gm.push.called

    def test_goal_not_added_when_low_curiosity(self):
        """score < 0.8 → GoalManager.push НЕ вызывается."""
        sm = _make_semantic(related_count=5, has_node=True)  # score = 0.2 < 0.8
        gm = MagicMock()
        engine = CuriosityEngine(semantic_memory=sm, goal_manager=gm)
        engine.score("well_known_concept")
        gm.push.assert_not_called()

    def test_no_error_without_goal_manager(self):
        """Нет ошибки если goal_manager=None."""
        sm = _make_semantic(related_count=0, has_node=False)
        engine = CuriosityEngine(semantic_memory=sm, goal_manager=None)
        engine.score("unknown")  # не должно бросать исключение

    def test_goal_description_contains_concept(self):
        """Добавленная цель содержит название концепта."""
        sm = _make_semantic(related_count=0, has_node=False)
        gm = MagicMock()
        engine = CuriosityEngine(semantic_memory=sm, goal_manager=gm)
        engine.score("нейрон")
        # Проверяем, что push был вызван с Goal, содержащим "нейрон"
        call_args = gm.push.call_args
        goal = call_args[0][0]
        assert "нейрон" in goal.description or "нейрон" in getattr(goal, "goal_type", "")

    def test_no_error_without_gap_detector(self):
        """Нет ошибки если gap_detector=None."""
        sm = _make_semantic(related_count=2)
        engine = CuriosityEngine(semantic_memory=sm, gap_detector=None)
        result = engine.score("concept")
        assert isinstance(result, float)
