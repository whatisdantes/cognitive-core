"""
brain/motivation/motivation_engine.py — Движок мотивации (Stage M.2).

Биологический аналог: прилежащее ядро (nucleus accumbens) + орбитофронтальная кора.

Компоненты:
  - MotivationState — текущее состояние мотивации
  - MotivationEngine — EMA-аккумулятор сигналов вознаграждения

Алгоритм (BRAIN.md §15.2):
  epistemic_score = α * signal.value + (1−α) * epistemic_score   (α=0.1)
  decay ×0.95 каждые 100 циклов
  is_frustrated = epistemic_score < 0.2

Side effects (NullObject pattern — None = no-op):
  epistemic_score > 0.7  → GoalManager.push("explore_unknown_concept")
  prediction_error > 0.2 → ReplayEngine.mark_as_high_value(episode_id)

Маппинг RewardType → goal_type для preferred_goal_types:
  EPISTEMIC  → "explore_unknown_concept"
  ACCURACY   → "answer_question"
  COHERENCE  → "verify_claim"
  COMPLETION → "plan"
  EFFICIENCY → "answer_question"
  PENALTY    → "answer_question"  (default)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from brain.motivation.reward_engine import RewardSignal, RewardType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

ALPHA: float = 0.1                    # EMA коэффициент
DECAY_FACTOR: float = 0.95            # Коэффициент затухания
DECAY_EVERY: int = 100                # Затухание каждые N циклов
FRUSTRATION_THRESHOLD: float = 0.2   # Порог фрустрации
CURIOSITY_TRIGGER_THRESHOLD: float = 0.7  # Порог добавления цели "explore"
PREDICTION_ERROR_THRESHOLD: float = 0.2  # Порог для mark_as_high_value

# Маппинг RewardType → goal_type
_REWARD_TO_GOAL_TYPE: Dict[RewardType, str] = {
    RewardType.EPISTEMIC:  "explore_unknown_concept",
    RewardType.ACCURACY:   "answer_question",
    RewardType.COHERENCE:  "verify_claim",
    RewardType.COMPLETION: "plan",
    RewardType.EFFICIENCY: "answer_question",
    RewardType.PENALTY:    "answer_question",
}


# ---------------------------------------------------------------------------
# MotivationState
# ---------------------------------------------------------------------------

@dataclass
class MotivationState:
    """
    Текущее состояние мотивационной системы.

    Поля:
        epistemic_score      — EMA-аккумулятор вознаграждений [−1, 1]
        preferred_goal_types — EMA по типам целей {goal_type: score}
        is_frustrated        — True если epistemic_score < FRUSTRATION_THRESHOLD
        cycle_count          — количество обработанных сигналов
    """
    epistemic_score: float = 0.0
    preferred_goal_types: Dict[str, float] = field(default_factory=dict)
    is_frustrated: bool = False
    cycle_count: int = 0


# ---------------------------------------------------------------------------
# MotivationEngine
# ---------------------------------------------------------------------------

class MotivationEngine:
    """
    Движок мотивации — аккумулирует сигналы вознаграждения через EMA.

    Биологический аналог: прилежащее ядро (nucleus accumbens).

    Параметры:
        goal_manager   — GoalManager для добавления целей (NullObject: None)
        replay_engine  — ReplayEngine для mark_as_high_value (NullObject: None)

    Публичный API:
        update(signal, episode_id=None, expected_value=None) → MotivationState
        state  → текущий MotivationState (property)
    """

    def __init__(
        self,
        goal_manager: Optional[Any] = None,
        replay_engine: Optional[Any] = None,
    ) -> None:
        self._state = MotivationState()
        self._goal_manager = goal_manager
        self._replay_engine = replay_engine

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    @property
    def state(self) -> MotivationState:
        """Текущее состояние мотивации (read-only snapshot)."""
        return self._state

    def update(
        self,
        signal: RewardSignal,
        episode_id: Optional[str] = None,
        expected_value: Optional[float] = None,
    ) -> MotivationState:
        """
        Обновить состояние мотивации по сигналу вознаграждения.

        Алгоритм:
          1. EMA: epistemic_score = α * signal.value + (1−α) * epistemic_score
          2. EMA: preferred_goal_types[goal_type] обновляется аналогично
          3. cycle_count += 1
          4. Decay ×0.95 каждые DECAY_EVERY циклов
          5. is_frustrated = epistemic_score < FRUSTRATION_THRESHOLD
          6. Side effects: GoalManager / ReplayEngine

        Args:
            signal:         RewardSignal от RewardEngine
            episode_id:     ID эпизода для mark_as_high_value (опционально)
            expected_value: ожидаемое вознаграждение для prediction_error (опционально)

        Returns:
            Обновлённый MotivationState
        """
        # 1. EMA epistemic_score
        self._state.epistemic_score = (
            ALPHA * signal.value + (1 - ALPHA) * self._state.epistemic_score
        )

        # 2. EMA preferred_goal_types
        goal_type = _REWARD_TO_GOAL_TYPE.get(signal.type, "answer_question")
        old_pref = self._state.preferred_goal_types.get(goal_type, 0.0)
        self._state.preferred_goal_types[goal_type] = (
            ALPHA * signal.value + (1 - ALPHA) * old_pref
        )

        # 3. cycle_count
        self._state.cycle_count += 1

        # 4. Decay каждые DECAY_EVERY циклов
        if self._state.cycle_count % DECAY_EVERY == 0:
            self._apply_decay()

        # 5. Frustration
        self._state.is_frustrated = (
            self._state.epistemic_score < FRUSTRATION_THRESHOLD
        )

        # 6. Side effects
        self._maybe_add_explore_goal()
        self._maybe_mark_high_value(signal, episode_id, expected_value)

        logger.debug(
            "[MotivationEngine] cycle=%d score=%.4f frustrated=%s",
            self._state.cycle_count,
            self._state.epistemic_score,
            self._state.is_frustrated,
        )

        return self._state

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _apply_decay(self) -> None:
        """Применить decay ×DECAY_FACTOR к epistemic_score и preferred_goal_types."""
        self._state.epistemic_score *= DECAY_FACTOR
        for key in self._state.preferred_goal_types:
            self._state.preferred_goal_types[key] *= DECAY_FACTOR
        logger.debug(
            "[MotivationEngine] decay applied at cycle=%d, score=%.4f",
            self._state.cycle_count,
            self._state.epistemic_score,
        )

    def _maybe_add_explore_goal(self) -> None:
        """
        Добавить цель "explore_unknown_concept" если epistemic_score > CURIOSITY_TRIGGER_THRESHOLD.

        No-op если goal_manager=None.
        """
        if self._goal_manager is None:
            return
        if self._state.epistemic_score > CURIOSITY_TRIGGER_THRESHOLD:
            try:
                from brain.cognition.goal_manager import Goal
                goal = Goal(
                    goal_type="explore_unknown_concept",
                    description="Автономное исследование: высокий epistemic_score",
                    priority=0.6,
                )
                self._goal_manager.push(goal)
                logger.info(
                    "[MotivationEngine] explore goal added (score=%.4f)",
                    self._state.epistemic_score,
                )
            except Exception as exc:
                logger.warning("[MotivationEngine] _maybe_add_explore_goal error: %s", exc)

    def _maybe_mark_high_value(
        self,
        signal: RewardSignal,
        episode_id: Optional[str],
        expected_value: Optional[float],
    ) -> None:
        """
        Вызвать ReplayEngine.mark_as_high_value если prediction_error > 0.2.

        No-op если replay_engine=None или episode_id=None или expected_value=None.
        """
        if self._replay_engine is None or episode_id is None or expected_value is None:
            return
        prediction_error = signal.value - expected_value
        if prediction_error > PREDICTION_ERROR_THRESHOLD:
            try:
                self._replay_engine.mark_as_high_value(episode_id)
                logger.info(
                    "[MotivationEngine] mark_as_high_value: episode=%s error=%.4f",
                    episode_id,
                    prediction_error,
                )
            except Exception as exc:
                logger.warning("[MotivationEngine] _maybe_mark_high_value error: %s", exc)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"MotivationEngine("
            f"score={self._state.epistemic_score:.4f} | "
            f"cycles={self._state.cycle_count} | "
            f"frustrated={self._state.is_frustrated})"
        )
