"""
brain/cognition/policy_layer.py

Слой политик поведения — фильтр и модификатор кандидатов действий.

Этап H: Attention & Resource Control.

PolicyLayer применяется в step_select_action() пайплайна между
scoring (Reasoner) и выбором действия (ActionSelector):
  1. apply_filters()   — убирает недопустимые действия по ресурсам и уверенности
  2. apply_modifiers() — корректирует веса кандидатов по контексту

Фильтры:
  F0: жёсткий блок GATHER_EVIDENCE/EXPLORE при resource_blocked
      (outcome == RESOURCE_BLOCKED или ring2_allowed == False)
  F1: убрать RESPOND_DIRECT при confidence < min_confidence
  F2: убрать GATHER_EVIDENCE при soft_blocked (умеренная нагрузка CPU)

Модификаторы:
  M1: штраф -0.15 для GATHER_EVIDENCE/EXPLORE при soft_blocked
  M2: буст +0.20 для ASK_CLARIFICATION при наличии contradiction_flags
  M3: буст +0.15 для RESPOND_HEDGED при 0.5 ≤ confidence ≤ 0.7

Использование:
    layer = PolicyLayer()
    filtered = layer.apply_filters(candidates, state, resources, constraints)
    scores   = layer.apply_modifiers(scores, state, resources)
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from brain.core.contracts import ResourceState

from .action_selector import ActionType
from .context import CognitiveOutcome, PolicyConstraints, ReasoningState

logger = logging.getLogger(__name__)


class PolicyLayer:
    """
    Слой политик поведения.

    Применяется в step_select_action() пайплайна:
      1. apply_filters()   — убирает недопустимые кандидаты
      2. apply_modifiers() — корректирует веса

    Не имеет состояния — все методы stateless.
    Может быть переопределён в подклассах для кастомных политик.
    """

    # Действия, заблокированные при жёстком ресурсном блоке
    # LEARN — единственное тяжёлое действие (запись в память/диск)
    RESOURCE_BLOCKED_ACTIONS: frozenset = frozenset({
        ActionType.LEARN,
    })

    # Штраф за дорогие действия при soft_blocked
    SOFT_BLOCK_PENALTY: float = 0.15

    # Буст ASK_CLARIFICATION при противоречиях
    CONTRADICTION_BOOST: float = 0.20

    # Буст RESPOND_HEDGED при умеренной уверенности
    HEDGED_BOOST: float = 0.15
    HEDGED_CONFIDENCE_LOW: float = 0.5
    HEDGED_CONFIDENCE_HIGH: float = 0.7

    def apply_filters(
        self,
        candidates: List[ActionType],
        state: ReasoningState,
        resources: ResourceState,
        constraints: PolicyConstraints,
        outcome: Optional[CognitiveOutcome] = None,
    ) -> List[ActionType]:
        """
        Отфильтровать недопустимые кандидаты действий.

        Args:
            candidates:  список кандидатов ActionType
            state:       текущее состояние reasoning loop
            resources:   состояние ресурсов (CPU/RAM/flags)
            constraints: ограничения политики (min_confidence и др.)
            outcome:     исход reasoning loop (опционально)

        Returns:
            Отфильтрованный список кандидатов (порядок сохранён).
        """
        # Определяем жёсткий ресурсный блок
        resource_blocked = (
            outcome == CognitiveOutcome.RESOURCE_BLOCKED
            or not resources.ring2_allowed
        )

        filtered: List[ActionType] = []
        removed: List[str] = []

        for action in candidates:
            # F0: жёсткий блок при перегрузке ресурсов
            if resource_blocked and action in self.RESOURCE_BLOCKED_ACTIONS:
                removed.append(f"F0:{action.value}")
                continue

            # F1: не отвечать напрямую при низкой уверенности
            if (
                action == ActionType.RESPOND_DIRECT
                and state.best_score < constraints.min_confidence
            ):
                removed.append(f"F1:{action.value}")
                continue

            # F2: мягкий блок LEARN при умеренной нагрузке CPU
            if action == ActionType.LEARN and resources.soft_blocked:
                removed.append(f"F2:{action.value}")
                continue

            filtered.append(action)

        if removed:
            logger.debug(
                "[PolicyLayer] apply_filters: removed=%s remaining=%d",
                removed,
                len(filtered),
            )

        return filtered

    def apply_modifiers(
        self,
        scores: Dict[ActionType, float],
        state: ReasoningState,
        resources: ResourceState,
    ) -> Dict[ActionType, float]:
        """
        Скорректировать веса кандидатов по контексту.

        Args:
            scores:    словарь {ActionType: score}
            state:     текущее состояние reasoning loop
            resources: состояние ресурсов

        Returns:
            Новый словарь с откорректированными весами (оригинал не мутируется).
        """
        modified = dict(scores)

        # M1: штраф за дорогие действия при умеренной нагрузке CPU
        if resources.soft_blocked:
            for action in self.RESOURCE_BLOCKED_ACTIONS:
                if action in modified:
                    modified[action] = max(0.0, modified[action] - self.SOFT_BLOCK_PENALTY)
                    logger.debug(
                        "[PolicyLayer] M1: %s -= %.2f (soft_blocked)",
                        action.value,
                        self.SOFT_BLOCK_PENALTY,
                    )

        # M2: буст ASK_CLARIFICATION при наличии противоречий
        if state.contradiction_flags:
            if ActionType.ASK_CLARIFICATION in modified:
                modified[ActionType.ASK_CLARIFICATION] = min(
                    1.0,
                    modified[ActionType.ASK_CLARIFICATION] + self.CONTRADICTION_BOOST,
                )
                logger.debug(
                    "[PolicyLayer] M2: ASK_CLARIFICATION += %.2f (contradictions=%d)",
                    self.CONTRADICTION_BOOST,
                    len(state.contradiction_flags),
                )

        # M3: буст RESPOND_HEDGED при умеренной уверенности
        if self.HEDGED_CONFIDENCE_LOW <= state.best_score <= self.HEDGED_CONFIDENCE_HIGH:
            if ActionType.RESPOND_HEDGED in modified:
                modified[ActionType.RESPOND_HEDGED] = min(
                    1.0,
                    modified[ActionType.RESPOND_HEDGED] + self.HEDGED_BOOST,
                )
                logger.debug(
                    "[PolicyLayer] M3: RESPOND_HEDGED += %.2f (confidence=%.3f)",
                    self.HEDGED_BOOST,
                    state.best_score,
                )

        return modified
