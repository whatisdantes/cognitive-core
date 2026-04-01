"""
brain/motivation/curiosity_engine.py — Движок любопытства (Stage M.3).

Биологический аналог: гиппокамп + дофаминовая система новизны.

Принцип (BRAIN.md §15.3):
  Чем меньше мозг знает о концепте X → тем выше curiosity_score(X).

Формула:
  knowledge_coverage(X) = len(semantic_memory.get_related(X, top_n=20))
  curiosity(X) = min(1.0, 1.0 / max(coverage, 0.01))

Интерпретация:
  coverage = 0  → curiosity = 1.0  (полностью неизвестно)
  coverage = 1  → curiosity = 1.0  (почти неизвестно)
  coverage = 2  → curiosity = 0.5
  coverage = 5  → curiosity = 0.2
  coverage = 10 → curiosity = 0.1

Автономный режим:
  curiosity > CURIOSITY_THRESHOLD (0.8) → GoalManager.push("explore_unknown_concept")

NullObject pattern:
  gap_detector=None, goal_manager=None → no-op (не бросает исключений)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

CURIOSITY_THRESHOLD: float = 0.8   # Порог для автономного добавления цели
_GET_RELATED_TOP_N: int = 20       # Количество связей для подсчёта coverage


# ---------------------------------------------------------------------------
# CuriosityEngine
# ---------------------------------------------------------------------------

class CuriosityEngine:
    """
    Движок любопытства — оценивает интерес к концепту по покрытию знаний.

    Биологический аналог: гиппокамп + дофаминовая система новизны.

    Параметры:
        semantic_memory — SemanticMemory для подсчёта связей концепта
        gap_detector    — KnowledgeGapDetector (NullObject: None)
        goal_manager    — GoalManager для автономного добавления целей (NullObject: None)

    Публичный API:
        score(concept)              → float  [0.0, 1.0]
        knowledge_coverage(concept) → float  (количество прямых связей)
    """

    def __init__(
        self,
        semantic_memory: Any,
        gap_detector: Optional[Any] = None,
        goal_manager: Optional[Any] = None,
    ) -> None:
        self._semantic = semantic_memory
        self._gap_detector = gap_detector
        self._goal_manager = goal_manager

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def score(self, concept: str) -> float:
        """
        Вычислить curiosity score для концепта.

        Формула:
            coverage = knowledge_coverage(concept)
            curiosity = min(1.0, 1.0 / max(coverage, 0.01))

        Автономный режим:
            curiosity > CURIOSITY_THRESHOLD → GoalManager.push(explore goal)

        Args:
            concept: название концепта для оценки

        Returns:
            float в диапазоне (0.0, 1.0]
        """
        coverage = self.knowledge_coverage(concept)
        curiosity = min(1.0, 1.0 / max(coverage, 0.01))

        logger.debug(
            "[CuriosityEngine] concept='%s' coverage=%.2f curiosity=%.4f",
            concept, coverage, curiosity,
        )

        # Автономный режим: добавить цель если curiosity высокий
        if curiosity > CURIOSITY_THRESHOLD:
            self._maybe_add_explore_goal(concept, curiosity)

        return curiosity

    def knowledge_coverage(self, concept: str) -> float:
        """
        Вычислить покрытие знаний для концепта.

        Покрытие = количество прямых связей в семантической памяти.
        Если концепт неизвестен или ошибка → 0.0.

        Args:
            concept: название концепта

        Returns:
            float — количество прямых связей (0.0 если неизвестен)
        """
        try:
            related = self._semantic.get_related(concept, top_n=_GET_RELATED_TOP_N)
            return float(len(related))
        except Exception as exc:
            logger.debug(
                "[CuriosityEngine] knowledge_coverage error for '%s': %s", concept, exc
            )
            return 0.0

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _maybe_add_explore_goal(self, concept: str, curiosity: float) -> None:
        """
        Добавить цель "explore_unknown_concept" в GoalManager.

        No-op если goal_manager=None.

        Args:
            concept:   концепт с высоким curiosity
            curiosity: значение curiosity score
        """
        if self._goal_manager is None:
            return
        try:
            from brain.cognition.goal_manager import Goal
            goal = Goal(
                goal_type="explore_unknown_concept",
                description=f"Любопытство: исследовать '{concept}' (score={curiosity:.3f})",
                priority=0.7,
            )
            self._goal_manager.push(goal)
            logger.info(
                "[CuriosityEngine] explore goal added: concept='%s' curiosity=%.4f",
                concept, curiosity,
            )
        except Exception as exc:
            logger.warning("[CuriosityEngine] _maybe_add_explore_goal error: %s", exc)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        has_gm = self._goal_manager is not None
        has_gd = self._gap_detector is not None
        return (
            f"CuriosityEngine("
            f"threshold={CURIOSITY_THRESHOLD} | "
            f"goal_manager={has_gm} | "
            f"gap_detector={has_gd})"
        )
