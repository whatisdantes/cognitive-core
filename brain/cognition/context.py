"""
brain/cognition/context.py

Центральные структуры данных когнитивного ядра.

Содержит:
  - CognitiveContext     — состояние текущего цикла мышления
  - GoalTypeLimits       — stop conditions для типа цели
  - PolicyConstraints    — ограничения поведения
  - CognitiveOutcome     — коды завершения reasoning loop
  - EvidencePack         — структурированный объект доказательства
  - ReasoningState       — изменяемое состояние reasoning loop
  - GOAL_TYPE_LIMITS     — стартовые значения для 4 типов целей
  - NORMAL_OUTCOMES      — нормальные завершения (не ошибки)
  - FAILURE_OUTCOMES     — ошибки и сбои

Все dataclass наследуют ContractMixin для единообразной сериализации.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from brain.core.contracts import ContractMixin

# ---------------------------------------------------------------------------
# CognitiveOutcome — коды завершения reasoning loop
# ---------------------------------------------------------------------------

class CognitiveOutcome(str, Enum):
    """
    Коды завершения reasoning loop.
    Используются в check_stop_conditions(), replan() и логах.

    Разделены на нормальные завершения и ошибки/сбои.
    """
    # --- Нормальные завершения (не ошибки) ---
    STOP_CONDITION_MET      = "stop_condition_met"
    GOAL_COMPLETED          = "goal_completed"
    STEP_LIMIT_REACHED      = "step_limit_reached"

    # --- Ошибки и сбои ---
    RETRIEVAL_FAILED        = "retrieval_failed"
    NO_HYPOTHESIS_GENERATED = "no_hypothesis_generated"
    INSUFFICIENT_CONFIDENCE = "insufficient_confidence"
    RESOURCE_BLOCKED        = "resource_blocked"


# Обратная совместимость (псевдоним):
CognitiveFailure = CognitiveOutcome


# ---------------------------------------------------------------------------
# UncertaintyTrend — тренд неопределённости в reasoning loop
# ---------------------------------------------------------------------------

class UncertaintyTrend(str, Enum):
    """
    Тренд неопределённости (confidence) в reasoning loop.

    Используется UncertaintyMonitor для определения динамики:
      RISING  — confidence растёт (хорошо)
      FALLING — confidence падает (плохо, возможна эскалация)
      STABLE  — confidence стабильна (delta < threshold)
      UNKNOWN — недостаточно данных (< 2 точки)
    """
    RISING  = "rising"
    FALLING = "falling"
    STABLE  = "stable"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# ReplanStrategy — стратегии перепланирования
# ---------------------------------------------------------------------------

class ReplanStrategy(str, Enum):
    """
    Стратегии перепланирования после сбоя в reasoning loop.

    RETRY:          повторить тот же план (MVP baseline)
    NARROW_SCOPE:   сузить фокус (убрать explore шаги)
    BROADEN_SCOPE:  расширить запрос (добавить retrieve шаг)
    DECOMPOSE:      разбить на подцели (depth limit = 1)
    ESCALATE:       отказ, передать выше (return None)
    """
    RETRY          = "retry"
    NARROW_SCOPE   = "narrow_scope"
    BROADEN_SCOPE  = "broaden_scope"
    DECOMPOSE      = "decompose"
    ESCALATE       = "escalate"

# Helper-наборы для быстрой проверки:
NORMAL_OUTCOMES = frozenset({
    CognitiveOutcome.STOP_CONDITION_MET,
    CognitiveOutcome.GOAL_COMPLETED,
    CognitiveOutcome.STEP_LIMIT_REACHED,
})

FAILURE_OUTCOMES = frozenset({
    CognitiveOutcome.RETRIEVAL_FAILED,
    CognitiveOutcome.NO_HYPOTHESIS_GENERATED,
    CognitiveOutcome.INSUFFICIENT_CONFIDENCE,
    CognitiveOutcome.RESOURCE_BLOCKED,
})


# ---------------------------------------------------------------------------
# GoalTypeLimits — stop conditions для конкретного типа цели
# ---------------------------------------------------------------------------

@dataclass
class GoalTypeLimits(ContractMixin):
    """
    Stop conditions для конкретного типа цели.

    Все значения стартовые — подлежат эмпирической калибровке.
    """
    step_limit: int = 3
    time_limit_ms: float = 200.0
    confidence_threshold: float = 0.75
    stability_window: int = 2


# Стартовые значения для 4 типов целей:
GOAL_TYPE_LIMITS: Dict[str, GoalTypeLimits] = {
    "answer_question": GoalTypeLimits(
        step_limit=3,
        time_limit_ms=200.0,
        confidence_threshold=0.75,
        stability_window=2,
    ),
    "verify_claim": GoalTypeLimits(
        step_limit=7,
        time_limit_ms=500.0,
        confidence_threshold=0.80,
        stability_window=2,
    ),
    "explore_topic": GoalTypeLimits(
        step_limit=10,
        time_limit_ms=800.0,
        confidence_threshold=0.70,
        stability_window=3,
    ),
    "learn_fact": GoalTypeLimits(
        step_limit=3,
        time_limit_ms=150.0,
        confidence_threshold=0.70,
        stability_window=1,
    ),
}


# ---------------------------------------------------------------------------
# PolicyConstraints — ограничения поведения для текущего цикла
# ---------------------------------------------------------------------------

@dataclass
class PolicyConstraints(ContractMixin):
    """
    Ограничения поведения для текущего цикла.

    min_confidence: минимальная уверенность для прямого ответа.
    max_retries:    максимум повторов replan().
    goal_limits:    stop conditions для текущего типа цели.
    """
    min_confidence: float = 0.4
    max_retries: int = 2
    goal_limits: GoalTypeLimits = field(
        default_factory=lambda: GoalTypeLimits()
    )

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация с вложенным GoalTypeLimits."""
        d = {
            "min_confidence": self.min_confidence,
            "max_retries": self.max_retries,
            "goal_limits": self.goal_limits.to_dict(),
        }
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PolicyConstraints":
        """Десериализация с вложенным GoalTypeLimits."""
        goal_limits_data = data.get("goal_limits")
        goal_limits = (
            GoalTypeLimits.from_dict(goal_limits_data)
            if isinstance(goal_limits_data, dict)
            else GoalTypeLimits()
        )
        return cls(
            min_confidence=data.get("min_confidence", 0.4),
            max_retries=data.get("max_retries", 2),
            goal_limits=goal_limits,
        )


# ---------------------------------------------------------------------------
# EvidencePack — структурированный объект доказательства
# ---------------------------------------------------------------------------

@dataclass
class EvidencePack(ContractMixin):
    """
    Структурированный объект доказательства для reasoning.

    Reasoning работает не с "голыми фактами", а с объектами доказательства.
    Это укрепляет retrieval, hypothesis generation, trace и contradiction analysis.
    """
    evidence_id: str = ""
    content: str = ""
    memory_type: str = ""           # "working" | "semantic" | "episodic"
    concept_refs: List[str] = field(default_factory=list)
    source_refs: List[str] = field(default_factory=list)
    confidence: float = 0.0
    trust: float = 0.5
    timestamp: Optional[str] = None
    modality: str = "text"
    contradiction_flags: List[str] = field(default_factory=list)
    relevance_score: float = 0.0
    freshness_score: float = 1.0
    retrieval_stage: int = 1
    supports_hypotheses: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ReasoningState — изменяемое состояние reasoning loop
# ---------------------------------------------------------------------------

@dataclass
class ReasoningState(ContractMixin):
    """
    Изменяемое состояние reasoning loop.
    Обновляется на каждой итерации.
    """
    retrieved_evidence: List[EvidencePack] = field(default_factory=list)
    active_hypotheses: List[Any] = field(default_factory=list)
    contradiction_flags: List[str] = field(default_factory=list)
    current_confidence: float = 0.0
    iteration: int = 0
    top_hypothesis_id: Optional[str] = None
    best_score: float = 0.0
    prev_best_score: float = 0.0


# ---------------------------------------------------------------------------
# CognitiveContext — состояние текущего цикла мышления
# ---------------------------------------------------------------------------

@dataclass
class CognitiveContext(ContractMixin):
    """
    Состояние текущего цикла мышления.
    Передаётся всем компонентам когнитивного ядра.

    active_goal и goal_chain типизированы как Any, чтобы избежать
    циклического импорта с goal_manager.py (Goal определён там).
    """
    session_id: str = ""
    cycle_id: str = ""
    trace_id: str = ""
    active_goal: Optional[Any] = None
    goal_chain: List[Any] = field(default_factory=list)
