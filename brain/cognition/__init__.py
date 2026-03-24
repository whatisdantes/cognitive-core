"""
cognition — Когнитивное ядро (аналог префронтальной коры).

Реализованные модули (Stage F + F+):
    context.py                — CognitiveContext, CognitiveOutcome, EvidencePack,
                                ReasoningState, UncertaintyTrend, ReplanStrategy
    goal_manager.py           — Goal, GoalStatus, GoalManager
    planner.py                — PlanStep, ExecutionPlan, Planner (5 replan strategies)
    hypothesis_engine.py      — Hypothesis, HypothesisEngine (4 strategies + budget)
    reasoner.py               — ReasoningStep, ReasoningTrace, Reasoner
    action_selector.py        — ActionType, ActionDecision, ActionSelector
    cognitive_core.py         — CognitiveCore (orchestrator)
    retrieval_adapter.py      — RetrievalAdapter, RetrievalBackend, KeywordRetrievalBackend
    contradiction_detector.py — Contradiction, ContradictionDetector
    uncertainty_monitor.py    — UncertaintySnapshot, UncertaintyMonitor

Запланированные модули (Stage H+):
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
    UncertaintyTrend,
    ReplanStrategy,
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
from .retrieval_adapter import (
    RetrievalAdapter,
    KeywordRetrievalBackend,
)
from .contradiction_detector import (
    Contradiction,
    ContradictionDetector,
)
from .uncertainty_monitor import (
    UncertaintySnapshot,
    UncertaintyMonitor,
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
    "UncertaintyTrend",
    "ReplanStrategy",
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
    # retrieval_adapter (F+)
    "RetrievalAdapter",
    "KeywordRetrievalBackend",
    # contradiction_detector (F+)
    "Contradiction",
    "ContradictionDetector",
    # uncertainty_monitor (F+)
    "UncertaintySnapshot",
    "UncertaintyMonitor",
    # cognitive_core
    "CognitiveCore",
]
