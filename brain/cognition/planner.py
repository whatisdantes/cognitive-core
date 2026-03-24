"""
brain/cognition/planner.py

Планировщик когнитивного ядра.

Содержит:
  - PlanStep       — один шаг плана
  - ExecutionPlan  — план выполнения цели
  - Planner        — декомпозиция целей на шаги + stop conditions + replan

Аналог: дорсолатеральная префронтальная кора — декомпозиция и планирование.

4 шаблона декомпозиции (answer_question, learn_fact, verify_claim,
explore_topic). 5 стратегий replan: RETRY, NARROW_SCOPE, BROADEN_SCOPE,
DECOMPOSE, ESCALATE. Защита от циклов: max_total_replans=3,
used_strategies set, DECOMPOSE depth=1.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from brain.core.contracts import ContractMixin
from .context import (
    CognitiveOutcome,
    GoalTypeLimits,
    ReasoningState,
    ReplanStrategy,
)
from .goal_manager import Goal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PlanStep — один шаг плана
# ---------------------------------------------------------------------------

@dataclass
class PlanStep(ContractMixin):
    """
    Один шаг плана выполнения цели.

    step_type определяет, что делать:
      "retrieve"   — извлечь факты из памяти
      "hypothesize"— сгенерировать гипотезы
      "score"      — оценить гипотезы
      "select"     — выбрать лучшую гипотезу
      "act"        — выбрать действие (respond/learn/ask/refuse)
      "store"      — сохранить факт в память
    """
    step_id: str = ""
    step_type: str = ""
    description: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    completed: bool = False
    result: Optional[Any] = None

    def __post_init__(self):
        if not self.step_id:
            self.step_id = f"step_{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# ExecutionPlan — план выполнения цели
# ---------------------------------------------------------------------------

@dataclass
class ExecutionPlan(ContractMixin):
    """
    План выполнения цели.

    steps:        упорядоченный список шагов
    goal_id:      ID цели, для которой создан план
    plan_id:      уникальный ID плана
    is_retry:     True если план создан через replan()
    retry_count:  номер повтора (0 = первый план)
    """
    plan_id: str = ""
    goal_id: str = ""
    steps: List[PlanStep] = field(default_factory=list)
    is_retry: bool = False
    retry_count: int = 0

    def __post_init__(self):
        if not self.plan_id:
            self.plan_id = f"plan_{uuid.uuid4().hex[:8]}"

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.completed)

    @property
    def current_step(self) -> Optional[PlanStep]:
        """Первый незавершённый шаг."""
        for s in self.steps:
            if not s.completed:
                return s
        return None

    @property
    def is_complete(self) -> bool:
        return all(s.completed for s in self.steps)

    def mark_step_done(self, step_id: str, result: Any = None) -> bool:
        """Пометить шаг как завершённый. Возвращает True если найден."""
        for s in self.steps:
            if s.step_id == step_id:
                s.completed = True
                s.result = result
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal_id": self.goal_id,
            "steps": [s.to_dict() for s in self.steps],
            "is_retry": self.is_retry,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionPlan":
        steps = [
            PlanStep.from_dict(s) if isinstance(s, dict) else s
            for s in data.get("steps", [])
        ]
        return cls(
            plan_id=data.get("plan_id", ""),
            goal_id=data.get("goal_id", ""),
            steps=steps,
            is_retry=data.get("is_retry", False),
            retry_count=data.get("retry_count", 0),
        )


# ---------------------------------------------------------------------------
# Planner — декомпозиция целей на шаги
# ---------------------------------------------------------------------------

class Planner:
    """
    Декомпозиция целей на шаги + stop conditions + replan.

    MVP: 4 шаблона декомпозиции. replan() = retry only.

    Использование:
        planner = Planner()
        plan = planner.decompose(goal)
        outcome = planner.check_stop_conditions(state, limits, resources)
        retry_plan = planner.replan(failed_step, context, failure)
    """

    # ------------------------------------------------------------------
    # Шаблоны декомпозиции
    # ------------------------------------------------------------------

    # Каждый шаблон — список (step_type, description)
    _TEMPLATES: Dict[str, List[tuple]] = {
        "answer_question": [
            ("retrieve", "Извлечь релевантные факты из памяти"),
            ("hypothesize", "Сгенерировать гипотезы ответа"),
            ("score", "Оценить гипотезы по доказательствам"),
            ("select", "Выбрать лучшую гипотезу"),
            ("act", "Выбрать действие и сформировать ответ"),
        ],
        "learn_fact": [
            ("retrieve", "Проверить, есть ли факт в памяти"),
            ("store", "Сохранить факт в семантическую память"),
            ("act", "Подтвердить сохранение"),
        ],
        "verify_claim": [
            ("retrieve", "Извлечь факты, связанные с утверждением"),
            ("hypothesize", "Сгенерировать гипотезы: подтверждение / опровержение"),
            ("score", "Оценить гипотезы по доказательствам"),
            ("select", "Выбрать лучшую гипотезу"),
            ("act", "Сформировать вердикт"),
        ],
        "explore_topic": [
            ("retrieve", "Извлечь всё, что известно по теме"),
            ("hypothesize", "Сгенерировать гипотезы о связях и аспектах"),
            ("score", "Оценить гипотезы"),
            ("select", "Выбрать наиболее информативные"),
            ("act", "Сформировать обзор"),
        ],
    }

    # Fallback шаблон для неизвестных типов целей
    _DEFAULT_TEMPLATE: List[tuple] = [
        ("retrieve", "Извлечь релевантные факты"),
        ("hypothesize", "Сгенерировать гипотезы"),
        ("score", "Оценить гипотезы"),
        ("select", "Выбрать лучшую"),
        ("act", "Выбрать действие"),
    ]

    # ------------------------------------------------------------------
    # Декомпозиция
    # ------------------------------------------------------------------

    def decompose(self, goal: Goal) -> ExecutionPlan:
        """
        Декомпозировать цель на шаги по шаблону.

        Если goal_type не найден в шаблонах — используется default.
        """
        template = self._TEMPLATES.get(goal.goal_type, self._DEFAULT_TEMPLATE)

        steps = [
            PlanStep(
                step_type=step_type,
                description=description,
            )
            for step_type, description in template
        ]

        plan = ExecutionPlan(
            goal_id=goal.goal_id,
            steps=steps,
        )

        logger.debug(
            "[Planner] decompose goal_id=%s type=%s → %d steps",
            goal.goal_id, goal.goal_type, len(steps),
        )
        return plan

    # ------------------------------------------------------------------
    # Stop conditions
    # ------------------------------------------------------------------

    def check_stop_conditions(
        self,
        state: ReasoningState,
        limits: GoalTypeLimits,
        resources: Optional[Dict[str, Any]] = None,
    ) -> Optional[CognitiveOutcome]:
        """
        Проверить stop conditions для текущего состояния reasoning loop.

        Возвращает CognitiveOutcome если нужно остановиться, иначе None.

        Порядок проверок:
          1. resource_blocked — ресурсы исчерпаны
          2. step_limit_reached — превышен лимит итераций
          3. goal_completed — confidence ≥ threshold + стабильность
        """
        # 1. Ресурсы
        if resources:
            cpu = resources.get("cpu_percent", 0)
            mem = resources.get("memory_percent", 0)
            if cpu > 95 or mem > 95:
                logger.warning(
                    "[Planner] resource_blocked: cpu=%.1f%% mem=%.1f%%",
                    cpu, mem,
                )
                return CognitiveOutcome.RESOURCE_BLOCKED

        # 2. Лимит итераций
        if state.iteration >= limits.step_limit:
            logger.info(
                "[Planner] step_limit_reached: iteration=%d limit=%d",
                state.iteration, limits.step_limit,
            )
            return CognitiveOutcome.STEP_LIMIT_REACHED

        # 3. Confidence + стабильность
        if state.current_confidence >= limits.confidence_threshold:
            # Проверяем стабильность: разница с предыдущим лучшим результатом
            delta = abs(state.current_confidence - state.prev_best_score)
            if delta < 0.05 and state.iteration >= limits.stability_window:
                logger.info(
                    "[Planner] goal_completed: confidence=%.3f threshold=%.3f",
                    state.current_confidence, limits.confidence_threshold,
                )
                return CognitiveOutcome.GOAL_COMPLETED

        return None

    # ------------------------------------------------------------------
    # Strategy selection
    # ------------------------------------------------------------------

    # Mapping: failure → preferred strategy
    _FAILURE_STRATEGY_MAP: Dict[CognitiveOutcome, ReplanStrategy] = {
        CognitiveOutcome.RETRIEVAL_FAILED: ReplanStrategy.BROADEN_SCOPE,
        CognitiveOutcome.NO_HYPOTHESIS_GENERATED: ReplanStrategy.DECOMPOSE,
        CognitiveOutcome.INSUFFICIENT_CONFIDENCE: ReplanStrategy.NARROW_SCOPE,
        CognitiveOutcome.RESOURCE_BLOCKED: ReplanStrategy.ESCALATE,
    }

    def _select_strategy(
        self,
        failure: CognitiveOutcome,
        used_strategies: Set[ReplanStrategy],
    ) -> Optional[ReplanStrategy]:
        """
        Выбрать стратегию перепланирования на основе типа сбоя.

        Порядок:
          1. Preferred strategy для данного failure
          2. RETRY как fallback
          3. Skip already used strategies
          4. None если все стратегии исчерпаны

        Args:
            failure:          тип сбоя
            used_strategies:  уже использованные стратегии

        Returns:
            ReplanStrategy или None (все исчерпаны)
        """
        # Preferred strategy
        preferred = self._FAILURE_STRATEGY_MAP.get(failure, ReplanStrategy.RETRY)

        if preferred not in used_strategies:
            return preferred

        # Fallback: RETRY
        if ReplanStrategy.RETRY not in used_strategies:
            return ReplanStrategy.RETRY

        # Try remaining strategies in order
        for strategy in ReplanStrategy:
            if strategy == ReplanStrategy.ESCALATE:
                continue  # ESCALATE = give up, not a real retry
            if strategy not in used_strategies:
                return strategy

        return None

    # ------------------------------------------------------------------
    # Replan (5 strategies + cycle protection)
    # ------------------------------------------------------------------

    def replan(
        self,
        failed_step: PlanStep,
        goal: Goal,
        failure: CognitiveOutcome,
        current_retry: int = 0,
        max_retries: int = 2,
        max_total_replans: int = 3,
        used_strategies: Optional[Set[ReplanStrategy]] = None,
        decompose_depth: int = 0,
    ) -> Optional[ExecutionPlan]:
        """
        Попытка перепланирования после сбоя.

        5 стратегий:
          RETRY:         повторить тот же план
          NARROW_SCOPE:  убрать explore шаги
          BROADEN_SCOPE: добавить дополнительный retrieve
          DECOMPOSE:     разбить на 2 подплана (depth limit=1)
          ESCALATE:      return None (отказ)

        Защита от циклов:
          - max_total_replans=3 (глобальный ceiling)
          - used_strategies: запрет повтора стратегии
          - DECOMPOSE depth limit=1

        Args:
            failed_step:       шаг, на котором произошёл сбой
            goal:              цель
            failure:           тип сбоя
            current_retry:     текущий номер повтора
            max_retries:       максимум повторов (legacy, respected)
            max_total_replans: глобальный лимит перепланирований
            used_strategies:   уже использованные стратегии
            decompose_depth:   текущая глубина DECOMPOSE

        Returns:
            Новый ExecutionPlan или None (отказ)
        """
        if used_strategies is None:
            used_strategies = set()

        # Global ceiling
        if current_retry >= max_total_replans:
            logger.info(
                "[Planner] replan: max_total_replans reached (%d/%d) for goal %s",
                current_retry, max_total_replans, goal.goal_id,
            )
            return None

        # Legacy max_retries check
        if current_retry >= max_retries:
            logger.info(
                "[Planner] replan: max_retries reached (%d/%d) for goal %s",
                current_retry, max_retries, goal.goal_id,
            )
            return None

        # Select strategy
        strategy = self._select_strategy(failure, used_strategies)
        if strategy is None or strategy == ReplanStrategy.ESCALATE:
            logger.info(
                "[Planner] replan: escalate/no strategy for goal %s (failure=%s)",
                goal.goal_id, failure.value,
            )
            return None

        # Mark strategy as used
        used_strategies.add(strategy)

        logger.info(
            "[Planner] replan: strategy=%s retry=%d/%d for goal %s (failure=%s)",
            strategy.value, current_retry + 1, max_total_replans,
            goal.goal_id, failure.value,
        )

        # Execute strategy
        plan: Optional[ExecutionPlan] = None

        if strategy == ReplanStrategy.RETRY:
            plan = self._replan_retry(goal, current_retry)

        elif strategy == ReplanStrategy.NARROW_SCOPE:
            plan = self._replan_narrow_scope(goal, current_retry)

        elif strategy == ReplanStrategy.BROADEN_SCOPE:
            plan = self._replan_broaden_scope(goal, current_retry)

        elif strategy == ReplanStrategy.DECOMPOSE:
            if decompose_depth >= 1:
                logger.info(
                    "[Planner] replan: DECOMPOSE depth limit reached (depth=%d)",
                    decompose_depth,
                )
                return None
            plan = self._replan_decompose(goal, current_retry)

        if plan is not None:
            plan.is_retry = True
            plan.retry_count = current_retry + 1

        return plan

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    def _replan_retry(self, goal: Goal, current_retry: int) -> ExecutionPlan:
        """RETRY: повторить тот же план (новые step_id)."""
        return self.decompose(goal)

    def _replan_narrow_scope(self, goal: Goal, current_retry: int) -> ExecutionPlan:
        """NARROW_SCOPE: убрать explore-подобные шаги, оставить core."""
        plan = self.decompose(goal)

        # Убираем шаги, которые не являются core reasoning
        # Core: retrieve, hypothesize, score, select, act, store
        # Remove: explore-like steps (в текущих шаблонах их нет,
        # но если goal_type=explore_topic — сокращаем до 3 шагов)
        if goal.goal_type == "explore_topic" and len(plan.steps) > 3:
            # Оставляем: retrieve, select, act
            core_types = {"retrieve", "select", "act"}
            plan.steps = [s for s in plan.steps if s.step_type in core_types]
            if not plan.steps:
                plan.steps = [PlanStep(step_type="act", description="Сформировать ответ")]

        return plan

    def _replan_broaden_scope(self, goal: Goal, current_retry: int) -> ExecutionPlan:
        """BROADEN_SCOPE: добавить дополнительный retrieve шаг в начало."""
        plan = self.decompose(goal)

        # Добавляем дополнительный retrieve в начало
        extra_retrieve = PlanStep(
            step_type="retrieve",
            description="Расширенный поиск: дополнительные источники",
            params={"broadened": True},
        )
        plan.steps.insert(0, extra_retrieve)

        return plan

    def _replan_decompose(self, goal: Goal, current_retry: int) -> ExecutionPlan:
        """
        DECOMPOSE: разбить на 2 подплана (retrieve+hypothesize, score+select+act).
        Depth limit=1 (проверяется в replan()).
        """
        # Подплан 1: retrieve + hypothesize
        sub_steps_1 = [
            PlanStep(step_type="retrieve", description="Подплан 1: извлечь факты"),
            PlanStep(step_type="hypothesize", description="Подплан 1: сгенерировать гипотезы"),
        ]

        # Подплан 2: score + select + act
        sub_steps_2 = [
            PlanStep(step_type="score", description="Подплан 2: оценить гипотезы"),
            PlanStep(step_type="select", description="Подплан 2: выбрать лучшую"),
            PlanStep(step_type="act", description="Подплан 2: сформировать ответ"),
        ]

        # Объединяем в один план
        plan = ExecutionPlan(
            goal_id=goal.goal_id,
            steps=sub_steps_1 + sub_steps_2,
        )

        return plan
