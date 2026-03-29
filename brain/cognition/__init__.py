"""
cognition — Когнитивное ядро (аналог префронтальной коры).

Реализованные модули (Stage F + F+ + P3):
    context.py                — CognitiveContext, CognitiveOutcome, EvidencePack,
                                ReasoningState, UncertaintyTrend, ReplanStrategy
    goal_manager.py           — Goal, GoalStatus, GoalManager
    planner.py                — PlanStep, ExecutionPlan, Planner (5 replan strategies)
    hypothesis_engine.py      — Hypothesis, HypothesisEngine (4 strategies + budget)
    reasoner.py               — ReasoningStep, ReasoningTrace, Reasoner
    action_selector.py        — ActionType, ActionDecision, ActionSelector
    cognitive_core.py         — CognitiveCore (orchestrator)
    pipeline.py               — CognitivePipeline, CognitivePipelineContext (P3-10)
    retrieval_adapter.py      — RetrievalAdapter, RetrievalBackend, KeywordRetrievalBackend,
                                BM25Scorer (BM25 reranking)
    contradiction_detector.py — Contradiction, ContradictionDetector
    uncertainty_monitor.py    — UncertaintySnapshot, UncertaintyMonitor

Запланированные модули (Stage H+):
    self_reflector.py       — периодический анализ качества мышления
    skill_refiner.py        — тонкая коррекция паттернов (аналог Мозжечка)
"""

from .action_selector import (
    ActionDecision,
    ActionSelector,
    ActionType,
)
from .cognitive_core import CognitiveCore
from .context import (
    FAILURE_OUTCOMES,
    GOAL_TYPE_LIMITS,
    NORMAL_OUTCOMES,
    CognitiveContext,
    CognitiveFailure,
    CognitiveOutcome,
    EvidencePack,
    GoalTypeLimits,
    PolicyConstraints,
    ReasoningState,
    ReplanStrategy,
    UncertaintyTrend,
)
from .contradiction_detector import (
    Contradiction,
    ContradictionDetector,
)
from .goal_manager import (
    Goal,
    GoalManager,
    GoalStatus,
)
from .hypothesis_engine import (
    Hypothesis,
    HypothesisEngine,
)
from .pipeline import CognitivePipeline, CognitivePipelineContext
from .planner import (
    ExecutionPlan,
    Planner,
    PlanStep,
)
from .policy_layer import PolicyLayer
from .reasoner import (
    Reasoner,
    ReasoningStep,
    ReasoningTrace,
)
from .retrieval_adapter import (
    BM25Scorer,
    HybridRetrievalBackend,
    KeywordRetrievalBackend,
    RetrievalAdapter,
    VectorRetrievalBackend,
)
from .salience_engine import SalienceEngine, SalienceScore
from .uncertainty_monitor import (
    UncertaintyMonitor,
    UncertaintySnapshot,
)

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
    "BM25Scorer",
    "RetrievalAdapter",
    "KeywordRetrievalBackend",
    "VectorRetrievalBackend",
    "HybridRetrievalBackend",
    # contradiction_detector (F+)
    "Contradiction",
    "ContradictionDetector",
    # uncertainty_monitor (F+)
    "UncertaintySnapshot",
    "UncertaintyMonitor",
    # cognitive_core
    "CognitiveCore",
    # pipeline (P3-10)
    "CognitivePipeline",
    "CognitivePipelineContext",
    # salience_engine (Этап H)
    "SalienceScore",
    "SalienceEngine",
    # policy_layer (Этап H)
    "PolicyLayer",
]
