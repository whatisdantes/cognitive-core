"""
brain/cognition/planner.py

Планировщик когнитивного ядра.

Содержит:
  - PlanStep       — один шаг плана
  - ExecutionPlan  — план выполнения цели
  - Planner        — декомпозиция целей на шаги + stop conditions + replan

Аналог: дорсолатеральная префронтальная кора — декомпозиция и планирование.

MVP: 4 шаблона декомпозиции (answer_question, learn_fact, verify_claim,
explore_topic). replan() = retry only (без умного replanning).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from brain.core.contracts import ContractMixin
from .context import (
    CognitiveOutcome,
    GoalTypeLimits,
    ReasoningState,
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
    # Replan (MVP: retry only)
    # ------------------------------------------------------------------

    def replan(
        self,
        failed_step: PlanStep,
        goal: Goal,
        failure: CognitiveOutcome,
        current_retry: int = 0,
        max_retries: int = 2,
    ) -> Optional[ExecutionPlan]:
        """
        Попытка перепланирования после сбоя.

        MVP: единственная стратегия — retry (повторить тот же план).
        Если current_retry >= max_retries → None (отказ).

        Возвращает новый ExecutionPlan или None.
        """
        if current_retry >= max_retries:
            logger.info(
                "[Planner] replan: max retries reached (%d/%d) for goal %s",
                current_retry, max_retries, goal.goal_id,
            )
            return None

        logger.info(
            "[Planner] replan: retry %d/%d for goal %s (failure=%s)",
            current_retry + 1, max_retries, goal.goal_id, failure.value,
        )

        # Создаём новый план (тот же шаблон, новые step_id)
        plan = self.decompose(goal)
        plan.is_retry = True
        plan.retry_count = current_retry + 1
        return plan
