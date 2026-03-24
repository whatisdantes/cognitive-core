"""
cognition — Когнитивное ядро (аналог префронтальной коры).

Реализованные модули (Stage F MVP):
    context.py              — CognitiveContext, CognitiveOutcome, EvidencePack, ReasoningState
    goal_manager.py         — Goal, GoalStatus, GoalManager
    planner.py              — PlanStep, ExecutionPlan, Planner
    hypothesis_engine.py    — Hypothesis, HypothesisEngine
    reasoner.py             — ReasoningStep, ReasoningTrace, Reasoner
    action_selector.py      — ActionType, ActionDecision, ActionSelector
    cognitive_core.py       — CognitiveCore (orchestrator)

Запланированные модули (Stage F.2+):
    contradiction_resolver.py — разрешение противоречий между фактами
    uncertainty_monitor.py  — оценка и управление неопределённостью
    self_reflector.py       — периодический анализ качества мышления
    skill_refiner.py        — тонкая коррекция паттернов (аналог Мозжечка)
"""

from .context import (
    CognitiveContext,
    CognitiveOutcome,
    CognitiveFailure,
    EvidencePack,
    GoalTypeLimits,
    PolicyConstraints,
    ReasoningState,
    GOAL_TYPE_LIMITS,
    NORMAL_OUTCOMES,
    FAILURE_OUTCOMES,
)
from .goal_manager import (
    Goal,
    GoalStatus,
    GoalManager,
)
from .planner import (
    PlanStep,
    ExecutionPlan,
    Planner,
)
from .hypothesis_engine import (
    Hypothesis,
    HypothesisEngine,
)
from .reasoner import (
    ReasoningStep,
    ReasoningTrace,
    Reasoner,
)
from .action_selector import (
    ActionType,
    ActionDecision,
    ActionSelector,
)
from .cognitive_core import CognitiveCore

__all__ = [
    # context
    "CognitiveContext",
    "CognitiveOutcome",
    "CognitiveFailure",
    "EvidencePack",
    "GoalTypeLimits",
    "PolicyConstraints",
    "ReasoningState",
    "GOAL_TYPE_LIMITS",
    "NORMAL_OUTCOMES",
    "FAILURE_OUTCOMES",
    # goal_manager
    "Goal",
    "GoalStatus",
    "GoalManager",
    # planner
    "PlanStep",
    "ExecutionPlan",
    "Planner",
    # hypothesis_engine
    "Hypothesis",
    "HypothesisEngine",
    # reasoner
    "ReasoningStep",
    "ReasoningTrace",
    "Reasoner",
    # action_selector
    "ActionType",
    "ActionDecision",
    "ActionSelector",
    # cognitive_core
    "CognitiveCore",
]
