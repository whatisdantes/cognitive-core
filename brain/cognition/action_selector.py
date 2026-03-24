"""
brain/cognition/action_selector.py

Селектор действий когнитивного ядра.

Содержит:
  - ActionType      — типы действий (5 штук MVP)
  - ActionDecision  — решение о действии
  - ActionSelector  — выбор действия на основе ReasoningTrace

Аналог: премоторная кора — выбор моторной программы на основе
результатов рассуждения.

MVP: 5 типов действий. LEARN — explicit memory action (≠ Learning Loop).
SEARCH_MEMORY убран (это внутренний шаг reasoning, не действие).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from brain.core.contracts import ContractMixin
from .context import (
    CognitiveOutcome,
    FAILURE_OUTCOMES,
    PolicyConstraints,
)
from .reasoner import ReasoningTrace

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ActionType — типы действий
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    """
    Типы действий когнитивного ядра.

    RESPOND_DIRECT:    прямой ответ (высокая уверенность)
    RESPOND_HEDGED:    ответ с оговоркой (средняя уверенность)
    ASK_CLARIFICATION: запросить уточнение у пользователя
    REFUSE:            отказ (нет данных / опасно / вне компетенции)
    LEARN:             сохранить факт в память (explicit memory action)

    LEARN ≠ Learning Loop (Stage I). LEARN — это осознанное действие
    "запомни факт", Learning Loop — автоматическое обучение из опыта.
    """
    RESPOND_DIRECT    = "respond_direct"
    RESPOND_HEDGED    = "respond_hedged"
    ASK_CLARIFICATION = "ask_clarification"
    REFUSE            = "refuse"
    LEARN             = "learn"


# ---------------------------------------------------------------------------
# ActionDecision — решение о действии
# ---------------------------------------------------------------------------

@dataclass
class ActionDecision(ContractMixin):
    """
    Решение о действии.

    action:       тип действия (ActionType)
    statement:    текст ответа / действия
    confidence:   уверенность в решении [0..1]
    reasoning:    краткое обоснование выбора
    hypothesis_id: ID гипотезы, на которой основано решение
    metadata:     дополнительные данные
    """
    action: str = ActionType.REFUSE.value
    statement: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    hypothesis_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def action_type(self) -> ActionType:
        """Получить ActionType из строки."""
        try:
            return ActionType(self.action)
        except ValueError:
            return ActionType.REFUSE


# ---------------------------------------------------------------------------
# ActionSelector — выбор действия
# ---------------------------------------------------------------------------

class ActionSelector:
    """
    Выбор действия на основе ReasoningTrace и PolicyConstraints.

    Логика выбора (приоритет сверху вниз):
      1. goal_type == "learn_fact" → LEARN
      2. outcome ∈ FAILURE_OUTCOMES → REFUSE или ASK_CLARIFICATION
      3. confidence ≥ min_confidence → RESPOND_DIRECT
      4. confidence ≥ min_confidence * 0.6 → RESPOND_HEDGED
      5. hypothesis_count > 0 → ASK_CLARIFICATION
      6. fallback → REFUSE

    Использование:
        selector = ActionSelector()
        decision = selector.select(
            trace=reasoning_trace,
            goal_type="answer_question",
            policy=PolicyConstraints(),
            resources={},
        )
    """

    def select(
        self,
        trace: ReasoningTrace,
        goal_type: str = "answer_question",
        policy: Optional[PolicyConstraints] = None,
        resources: Optional[Dict[str, Any]] = None,
    ) -> ActionDecision:
        """
        Выбрать действие на основе результатов reasoning.

        Возвращает ActionDecision.
        """
        if policy is None:
            policy = PolicyConstraints()

        # --- 1. LEARN: если цель — запомнить факт ---
        if goal_type == "learn_fact":
            return self._decide_learn(trace)

        # --- 2. Failure outcomes → REFUSE / ASK_CLARIFICATION ---
        outcome = self._parse_outcome(trace.outcome)
        if outcome in FAILURE_OUTCOMES:
            return self._decide_on_failure(trace, outcome)

        # --- 3-6. Выбор по confidence ---
        return self._decide_by_confidence(trace, policy)

    # ------------------------------------------------------------------
    # Приватные методы — стратегии выбора
    # ------------------------------------------------------------------

    def _decide_learn(self, trace: ReasoningTrace) -> ActionDecision:
        """Решение LEARN для goal_type=learn_fact."""
        statement = trace.best_statement or trace.query
        return ActionDecision(
            action=ActionType.LEARN.value,
            statement=f"Сохраняю факт: {statement}",
            confidence=max(trace.final_confidence, 0.5),
            reasoning="Цель — запомнить факт (goal_type=learn_fact)",
            hypothesis_id=trace.best_hypothesis_id,
            metadata={"goal_type": "learn_fact"},
        )

    def _decide_on_failure(
        self,
        trace: ReasoningTrace,
        outcome: CognitiveOutcome,
    ) -> ActionDecision:
        """Решение при failure outcome."""

        # Если есть хоть какие-то гипотезы — запросить уточнение
        if trace.hypothesis_count > 0 and trace.final_confidence > 0.1:
            return ActionDecision(
                action=ActionType.ASK_CLARIFICATION.value,
                statement=(
                    "Не удалось найти точный ответ. "
                    "Можете уточнить вопрос?"
                ),
                confidence=trace.final_confidence,
                reasoning=f"Failure outcome ({outcome.value}), "
                          f"но есть {trace.hypothesis_count} гипотез",
                hypothesis_id=trace.best_hypothesis_id,
                metadata={
                    "outcome": outcome.value,
                    "stop_reason": trace.stop_reason,
                },
            )

        # Полный отказ
        return ActionDecision(
            action=ActionType.REFUSE.value,
            statement="Не удалось найти ответ на ваш вопрос.",
            confidence=0.0,
            reasoning=f"Failure outcome: {outcome.value}. "
                      f"Причина: {trace.stop_reason}",
            hypothesis_id="",
            metadata={
                "outcome": outcome.value,
                "stop_reason": trace.stop_reason,
            },
        )

    def _decide_by_confidence(
        self,
        trace: ReasoningTrace,
        policy: PolicyConstraints,
    ) -> ActionDecision:
        """Выбор действия по уровню confidence."""
        conf = trace.final_confidence
        min_conf = policy.min_confidence
        hedged_threshold = min_conf * 0.6

        # Высокая уверенность → прямой ответ
        if conf >= min_conf:
            return ActionDecision(
                action=ActionType.RESPOND_DIRECT.value,
                statement=trace.best_statement,
                confidence=conf,
                reasoning=(
                    f"Confidence {conf:.3f} ≥ threshold {min_conf:.3f}"
                ),
                hypothesis_id=trace.best_hypothesis_id,
                metadata={"threshold": min_conf},
            )

        # Средняя уверенность → ответ с оговоркой
        if conf >= hedged_threshold:
            hedged_statement = trace.best_statement
            if hedged_statement and not hedged_statement.startswith("Возможно"):
                hedged_statement = f"Возможно, {hedged_statement[0].lower()}{hedged_statement[1:]}"

            return ActionDecision(
                action=ActionType.RESPOND_HEDGED.value,
                statement=hedged_statement or "Возможно, ответ связан с данной темой.",
                confidence=conf,
                reasoning=(
                    f"Confidence {conf:.3f} ≥ hedged threshold "
                    f"{hedged_threshold:.3f} but < {min_conf:.3f}"
                ),
                hypothesis_id=trace.best_hypothesis_id,
                metadata={
                    "threshold": min_conf,
                    "hedged_threshold": hedged_threshold,
                },
            )

        # Есть гипотезы, но низкая уверенность → уточнение
        if trace.hypothesis_count > 0:
            return ActionDecision(
                action=ActionType.ASK_CLARIFICATION.value,
                statement="Мне нужно больше информации. Можете уточнить вопрос?",
                confidence=conf,
                reasoning=(
                    f"Confidence {conf:.3f} < hedged threshold "
                    f"{hedged_threshold:.3f}, есть {trace.hypothesis_count} гипотез"
                ),
                hypothesis_id=trace.best_hypothesis_id,
                metadata={"hypothesis_count": trace.hypothesis_count},
            )

        # Fallback → отказ
        return ActionDecision(
            action=ActionType.REFUSE.value,
            statement="У меня недостаточно данных для ответа.",
            confidence=0.0,
            reasoning="Нет гипотез и низкая уверенность",
            hypothesis_id="",
            metadata={},
        )

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_outcome(outcome_str: str) -> Optional[CognitiveOutcome]:
        """Парсинг строки outcome в CognitiveOutcome."""
        if not outcome_str:
            return None
        try:
            return CognitiveOutcome(outcome_str)
        except ValueError:
            return None
