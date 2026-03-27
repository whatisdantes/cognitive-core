"""
tests/test_cognition.py

Unit-тесты когнитивного ядра (Stage F).
Все зависимости замокированы — тесты быстрые и детерминированные.

~130 тестов, 14 классов.
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from brain.cognition.action_selector import ActionDecision, ActionSelector, ActionType
from brain.cognition.cognitive_core import CognitiveCore
from brain.cognition.context import (
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
)
from brain.cognition.goal_manager import Goal, GoalManager, GoalStatus
from brain.cognition.hypothesis_engine import Hypothesis, HypothesisEngine
from brain.cognition.planner import ExecutionPlan, Planner, PlanStep
from brain.cognition.reasoner import Reasoner, ReasoningStep, ReasoningTrace

# ===================================================================
# Helpers
# ===================================================================

def _make_evidence(
    evidence_id="ev_1",
    content="нейрон — клетка нервной системы",
    confidence=0.8,
    relevance=0.9,
    memory_type="semantic",
    concept_refs=None,
    contradiction_flags=None,
):
    return EvidencePack(
        evidence_id=evidence_id,
        content=content,
        memory_type=memory_type,
        confidence=confidence,
        relevance_score=relevance,
        concept_refs=concept_refs or [],
        contradiction_flags=contradiction_flags or [],
    )


def _make_mock_memory(search_results=None):
    mm = MagicMock()
    if search_results is None:
        search_results = [
            MagicMock(content="нейрон — клетка нервной системы",
                      score=0.85, memory_type="semantic", memory_id="mem_1"),
            MagicMock(content="синапс — место контакта нейронов",
                      score=0.70, memory_type="semantic", memory_id="mem_2"),
        ]
    mm.search.return_value = search_results
    mm.store.return_value = None
    return mm


def _make_trace(
    outcome="goal_completed",
    confidence=0.8,
    best_statement="нейрон — клетка",
    best_hypothesis_id="hyp_1",
    hypothesis_count=2,
    evidence_refs=None,
):
    return ReasoningTrace(
        query="что такое нейрон?",
        outcome=outcome,
        final_confidence=confidence,
        best_statement=best_statement,
        best_hypothesis_id=best_hypothesis_id,
        hypothesis_count=hypothesis_count,
        evidence_refs=evidence_refs or ["ev_1"],
        total_iterations=2,
        total_duration_ms=5.0,
    )


# ===================================================================
# TestCognitiveContext (~10 tests)
# ===================================================================

class TestCognitiveContext:

    def test_default_creation(self):
        ctx = CognitiveContext()
        assert ctx.session_id == ""
        assert ctx.cycle_id == ""
        assert ctx.trace_id == ""
        assert ctx.active_goal is None
        assert ctx.goal_chain == []

    def test_creation_with_values(self):
        ctx = CognitiveContext(session_id="s1", cycle_id="c1", trace_id="t1")
        assert ctx.session_id == "s1"
        assert ctx.cycle_id == "c1"
        assert ctx.trace_id == "t1"

    def test_to_dict(self):
        ctx = CognitiveContext(session_id="s1", cycle_id="c1")
        d = ctx.to_dict()
        assert isinstance(d, dict)
        assert d["session_id"] == "s1"

    def test_from_dict(self):
        d = {"session_id": "s2", "cycle_id": "c2", "trace_id": "t2"}
        ctx = CognitiveContext.from_dict(d)
        assert ctx.session_id == "s2"

    def test_from_dict_unknown_keys_ignored(self):
        d = {"session_id": "s1", "unknown_field": 42}
        ctx = CognitiveContext.from_dict(d)
        assert ctx.session_id == "s1"

    def test_active_goal_assignment(self):
        ctx = CognitiveContext()
        goal = Goal(description="test")
        ctx.active_goal = goal
        assert ctx.active_goal is goal

    def test_goal_chain_mutable(self):
        ctx = CognitiveContext()
        ctx.goal_chain.append(Goal(description="g1"))
        ctx.goal_chain.append(Goal(description="g2"))
        assert len(ctx.goal_chain) == 2

    def test_roundtrip_serialization(self):
        ctx = CognitiveContext(session_id="s1", cycle_id="c1", trace_id="t1")
        d = ctx.to_dict()
        ctx2 = CognitiveContext.from_dict(d)
        assert ctx2.session_id == ctx.session_id

    def test_evidence_pack_default(self):
        ep = EvidencePack()
        assert ep.evidence_id == ""
        assert ep.confidence == 0.0
        assert ep.contradiction_flags == []

    def test_reasoning_state_default(self):
        rs = ReasoningState()
        assert rs.iteration == 0
        assert rs.current_confidence == 0.0
        assert rs.retrieved_evidence == []


# ===================================================================
# TestCognitiveOutcome (~8 tests)
# ===================================================================

class TestCognitiveOutcome:

    def test_all_values_exist(self):
        assert len(CognitiveOutcome) == 7

    def test_normal_outcomes_set(self):
        assert CognitiveOutcome.GOAL_COMPLETED in NORMAL_OUTCOMES
        assert CognitiveOutcome.STEP_LIMIT_REACHED in NORMAL_OUTCOMES
        assert CognitiveOutcome.STOP_CONDITION_MET in NORMAL_OUTCOMES
        assert len(NORMAL_OUTCOMES) == 3

    def test_failure_outcomes_set(self):
        assert CognitiveOutcome.RETRIEVAL_FAILED in FAILURE_OUTCOMES
        assert CognitiveOutcome.NO_HYPOTHESIS_GENERATED in FAILURE_OUTCOMES
        assert CognitiveOutcome.INSUFFICIENT_CONFIDENCE in FAILURE_OUTCOMES
        assert CognitiveOutcome.RESOURCE_BLOCKED in FAILURE_OUTCOMES
        assert len(FAILURE_OUTCOMES) == 4

    def test_no_overlap(self):
        assert NORMAL_OUTCOMES & FAILURE_OUTCOMES == frozenset()

    def test_all_covered(self):
        all_outcomes = NORMAL_OUTCOMES | FAILURE_OUTCOMES
        assert all_outcomes == frozenset(CognitiveOutcome)

    def test_cognitive_failure_alias(self):
        assert CognitiveFailure is CognitiveOutcome

    def test_string_value(self):
        assert CognitiveOutcome.GOAL_COMPLETED.value == "goal_completed"

    def test_from_string(self):
        o = CognitiveOutcome("goal_completed")
        assert o == CognitiveOutcome.GOAL_COMPLETED


# ===================================================================
# TestGoalTypeLimits (~7 tests)
# ===================================================================

class TestGoalTypeLimits:

    def test_default_values(self):
        g = GoalTypeLimits()
        assert g.step_limit == 3
        assert g.time_limit_ms == 200.0
        assert g.confidence_threshold == 0.75
        assert g.stability_window == 2

    def test_custom_values(self):
        g = GoalTypeLimits(step_limit=10, confidence_threshold=0.9)
        assert g.step_limit == 10

    def test_goal_type_limits_dict_has_4_types(self):
        assert len(GOAL_TYPE_LIMITS) == 4
        for k in ("answer_question", "verify_claim", "explore_topic", "learn_fact"):
            assert k in GOAL_TYPE_LIMITS

    def test_answer_question_limits(self):
        lim = GOAL_TYPE_LIMITS["answer_question"]
        assert lim.step_limit == 3
        assert lim.confidence_threshold == 0.75

    def test_to_dict_from_dict(self):
        g = GoalTypeLimits(step_limit=5, confidence_threshold=0.8)
        d = g.to_dict()
        g2 = GoalTypeLimits.from_dict(d)
        assert g2.step_limit == 5

    def test_policy_constraints_default(self):
        p = PolicyConstraints()
        assert p.min_confidence == 0.4
        assert p.max_retries == 2
        assert isinstance(p.goal_limits, GoalTypeLimits)

    def test_policy_constraints_roundtrip(self):
        p = PolicyConstraints(min_confidence=0.6, max_retries=3)
        d = p.to_dict()
        p2 = PolicyConstraints.from_dict(d)
        assert p2.min_confidence == 0.6
        assert p2.max_retries == 3


# ===================================================================
# TestGoal (~8 tests)
# ===================================================================

class TestGoal:

    def test_default_creation(self):
        g = Goal(description="test goal")
        assert g.description == "test goal"
        assert g.goal_type == "answer_question"
        assert g.status == GoalStatus.PENDING
        assert g.goal_id.startswith("goal_")

    def test_auto_id_generation(self):
        g1 = Goal(description="a")
        g2 = Goal(description="b")
        assert g1.goal_id != g2.goal_id

    def test_is_terminal_false(self):
        assert not Goal(description="t").is_terminal

    def test_is_terminal_done(self):
        assert Goal(description="t", status=GoalStatus.DONE).is_terminal

    def test_is_terminal_failed(self):
        assert Goal(description="t", status=GoalStatus.FAILED).is_terminal

    def test_is_terminal_cancelled(self):
        assert Goal(description="t", status=GoalStatus.CANCELLED).is_terminal

    def test_limits_property(self):
        g = Goal(description="t", goal_type="answer_question")
        assert g.limits.step_limit == 3

    def test_to_dict_from_dict(self):
        g = Goal(goal_id="g1", description="t", goal_type="learn_fact", priority=0.8)
        d = g.to_dict()
        assert d["status"] == "pending"
        g2 = Goal.from_dict(d)
        assert g2.goal_id == "g1"
        assert g2.status == GoalStatus.PENDING


# ===================================================================
# TestGoalManager (~22 tests)
# ===================================================================

class TestGoalManager:

    def test_creation(self):
        gm = GoalManager()
        assert gm.total_count == 0
        assert gm.active_count == 0

    def test_push_single(self):
        gm = GoalManager()
        gm.push(Goal(description="t"))
        assert gm.total_count == 1
        assert gm.active_count == 1

    def test_push_sets_active(self):
        gm = GoalManager()
        g = Goal(description="t")
        gm.push(g)
        assert g.status == GoalStatus.ACTIVE

    def test_push_duplicate_ignored(self):
        gm = GoalManager()
        g = Goal(goal_id="g1", description="t")
        gm.push(g)
        gm.push(g)
        assert gm.total_count == 1

    def test_peek_returns_highest_priority(self):
        gm = GoalManager()
        g1 = Goal(description="low", priority=0.3)
        g2 = Goal(description="high", priority=0.9)
        gm.push(g1)
        gm.push(g2)
        assert gm.peek().goal_id == g2.goal_id

    def test_peek_empty(self):
        assert GoalManager().peek() is None

    def test_complete(self):
        gm = GoalManager()
        g = Goal(description="t")
        gm.push(g)
        gm.complete(g.goal_id)
        assert g.status == GoalStatus.DONE
        assert gm.active_count == 0

    def test_complete_nonexistent(self):
        GoalManager().complete("nonexistent")

    def test_complete_terminal_noop(self):
        gm = GoalManager()
        g = Goal(description="t", status=GoalStatus.DONE)
        gm._goal_tree[g.goal_id] = g
        gm.complete(g.goal_id)
        assert g.status == GoalStatus.DONE

    def test_fail(self):
        gm = GoalManager()
        g = Goal(description="t")
        gm.push(g)
        gm.fail(g.goal_id, "timeout")
        assert g.status == GoalStatus.FAILED
        assert g.failure_reason == "timeout"

    def test_cancel(self):
        gm = GoalManager()
        g = Goal(description="t")
        gm.push(g)
        gm.cancel(g.goal_id)
        assert g.status == GoalStatus.CANCELLED

    def test_interrupt(self):
        gm = GoalManager()
        g1 = Goal(description="normal", priority=0.5)
        gm.push(g1)
        g2 = Goal(description="urgent", priority=0.9)
        gm.interrupt(g2)
        assert g1.status == GoalStatus.INTERRUPTED
        assert gm.peek().goal_id == g2.goal_id
        assert gm.interrupted_count == 1

    def test_resume_interrupted(self):
        gm = GoalManager()
        g1 = Goal(description="normal", priority=0.5)
        gm.push(g1)
        g2 = Goal(description="urgent", priority=0.9)
        gm.interrupt(g2)
        gm.complete(g2.goal_id)
        resumed = gm.resume_interrupted()
        assert resumed is not None
        assert resumed.goal_id == g1.goal_id
        assert resumed.status == GoalStatus.ACTIVE

    def test_resume_empty(self):
        assert GoalManager().resume_interrupted() is None

    def test_get_goal(self):
        gm = GoalManager()
        g = Goal(description="t")
        gm.push(g)
        assert gm.get_goal(g.goal_id) is g

    def test_get_goal_nonexistent(self):
        assert GoalManager().get_goal("x") is None

    def test_get_active_chain_single(self):
        gm = GoalManager()
        g = Goal(description="t")
        gm.push(g)
        chain = gm.get_active_chain()
        assert len(chain) == 1

    def test_get_active_chain_parent_child(self):
        gm = GoalManager()
        parent = Goal(goal_id="p1", description="parent", priority=0.3)
        gm.push(parent)
        child = Goal(goal_id="c1", description="child", parent_goal_id="p1", priority=0.8)
        gm.push(child)
        chain = gm.get_active_chain()
        assert len(chain) == 2
        assert chain[0].goal_id == "p1"
        assert chain[1].goal_id == "c1"

    def test_get_active_chain_empty(self):
        assert GoalManager().get_active_chain() == []

    def test_status_dict(self):
        gm = GoalManager()
        g = Goal(description="t")
        gm.push(g)
        s = gm.status()
        assert s["total_goals"] == 1
        assert s["current_goal"] == g.goal_id

    def test_clear(self):
        gm = GoalManager()
        gm.push(Goal(description="a"))
        gm.push(Goal(description="b"))
        gm.clear()
        assert gm.total_count == 0

    def test_repr(self):
        assert "GoalManager" in repr(GoalManager())


# ===================================================================
# TestPlanStep (~8 tests)
# ===================================================================

class TestPlanStep:

    def test_plan_step_default(self):
        ps = PlanStep(step_type="retrieve", description="test")
        assert ps.step_type == "retrieve"
        assert not ps.completed
        assert ps.step_id.startswith("step_")

    def test_plan_step_to_dict(self):
        d = PlanStep(step_type="retrieve", description="t").to_dict()
        assert d["step_type"] == "retrieve"

    def test_execution_plan_creation(self):
        plan = ExecutionPlan(goal_id="g1", steps=[
            PlanStep(step_type="retrieve"),
            PlanStep(step_type="hypothesize"),
        ])
        assert plan.total_steps == 2
        assert plan.completed_steps == 0

    def test_execution_plan_current_step(self):
        plan = ExecutionPlan(steps=[
            PlanStep(step_type="retrieve"),
            PlanStep(step_type="hypothesize"),
        ])
        assert plan.current_step.step_type == "retrieve"

    def test_execution_plan_mark_done(self):
        s1 = PlanStep(step_type="retrieve")
        plan = ExecutionPlan(steps=[s1])
        assert plan.mark_step_done(s1.step_id, result="ok")
        assert s1.completed and s1.result == "ok"

    def test_execution_plan_is_complete(self):
        s1 = PlanStep(step_type="retrieve")
        plan = ExecutionPlan(steps=[s1])
        assert not plan.is_complete
        plan.mark_step_done(s1.step_id)
        assert plan.is_complete

    def test_execution_plan_to_dict_from_dict(self):
        plan = ExecutionPlan(goal_id="g1", steps=[PlanStep(step_type="retrieve")])
        plan2 = ExecutionPlan.from_dict(plan.to_dict())
        assert plan2.goal_id == "g1" and plan2.total_steps == 1

    def test_mark_done_nonexistent(self):
        plan = ExecutionPlan(steps=[PlanStep(step_type="retrieve")])
        assert not plan.mark_step_done("nonexistent")


# ===================================================================
# TestPlanner (~22 tests)
# ===================================================================

class TestPlanner:

    def test_decompose_answer_question(self):
        plan = Planner().decompose(Goal(description="q?", goal_type="answer_question"))
        assert plan.total_steps == 5
        assert plan.steps[0].step_type == "retrieve"
        assert plan.steps[-1].step_type == "act"

    def test_decompose_learn_fact(self):
        plan = Planner().decompose(Goal(description="запомни", goal_type="learn_fact"))
        assert plan.total_steps == 3
        assert plan.steps[1].step_type == "store"

    def test_decompose_verify_claim(self):
        plan = Planner().decompose(Goal(description="правда?", goal_type="verify_claim"))
        assert plan.total_steps == 5

    def test_decompose_explore_topic(self):
        plan = Planner().decompose(Goal(description="мозг", goal_type="explore_topic"))
        assert plan.total_steps == 5

    def test_decompose_unknown_type_uses_default(self):
        plan = Planner().decompose(Goal(description="t", goal_type="unknown_type"))
        assert plan.total_steps == 5

    def test_decompose_sets_goal_id(self):
        plan = Planner().decompose(Goal(goal_id="g1", description="t"))
        assert plan.goal_id == "g1"

    def test_decompose_unique_step_ids(self):
        plan = Planner().decompose(Goal(description="t"))
        ids = [s.step_id for s in plan.steps]
        assert len(ids) == len(set(ids))

    def test_check_stop_step_limit(self):
        r = Planner().check_stop_conditions(
            ReasoningState(iteration=5), GoalTypeLimits(step_limit=3))
        assert r == CognitiveOutcome.STEP_LIMIT_REACHED

    def test_check_stop_goal_completed(self):
        r = Planner().check_stop_conditions(
            ReasoningState(iteration=3, current_confidence=0.85, prev_best_score=0.84),
            GoalTypeLimits(step_limit=10, confidence_threshold=0.75, stability_window=2))
        assert r == CognitiveOutcome.GOAL_COMPLETED

    def test_check_stop_resource_blocked_cpu(self):
        r = Planner().check_stop_conditions(
            ReasoningState(iteration=1), GoalTypeLimits(step_limit=10),
            {"cpu_percent": 98, "memory_percent": 50})
        assert r == CognitiveOutcome.RESOURCE_BLOCKED

    def test_check_stop_none_when_ok(self):
        r = Planner().check_stop_conditions(
            ReasoningState(iteration=1, current_confidence=0.3),
            GoalTypeLimits(step_limit=10, confidence_threshold=0.75))
        assert r is None

    def test_check_stop_confidence_not_stable(self):
        r = Planner().check_stop_conditions(
            ReasoningState(iteration=3, current_confidence=0.85, prev_best_score=0.5),
            GoalTypeLimits(step_limit=10, confidence_threshold=0.75, stability_window=2))
        assert r is None

    def test_replan_first_retry(self):
        plan = Planner().replan(
            PlanStep(step_type="retrieve"),
            Goal(description="t", goal_type="answer_question"),
            CognitiveOutcome.RETRIEVAL_FAILED, 0, 2)
        assert plan is not None and plan.is_retry and plan.retry_count == 1

    def test_replan_max_retries_exceeded(self):
        plan = Planner().replan(
            PlanStep(step_type="retrieve"),
            Goal(description="t"),
            CognitiveOutcome.RETRIEVAL_FAILED, 2, 2)
        assert plan is None

    def test_replan_second_retry(self):
        plan = Planner().replan(
            PlanStep(step_type="retrieve"),
            Goal(description="t", goal_type="answer_question"),
            CognitiveOutcome.RETRIEVAL_FAILED, 1, 2)
        assert plan is not None and plan.retry_count == 2

    def test_check_stop_memory_blocked(self):
        r = Planner().check_stop_conditions(
            ReasoningState(iteration=1), GoalTypeLimits(step_limit=10),
            {"cpu_percent": 50, "memory_percent": 96})
        assert r == CognitiveOutcome.RESOURCE_BLOCKED

    def test_check_stop_empty_resources(self):
        r = Planner().check_stop_conditions(
            ReasoningState(iteration=1), GoalTypeLimits(step_limit=10), {})
        assert r is None

    def test_check_stop_no_resources(self):
        r = Planner().check_stop_conditions(
            ReasoningState(iteration=1), GoalTypeLimits(step_limit=10), None)
        assert r is None

    def test_decompose_plan_has_id(self):
        plan = Planner().decompose(Goal(description="t"))
        assert plan.plan_id.startswith("plan_")

    def test_decompose_steps_have_descriptions(self):
        plan = Planner().decompose(Goal(description="t", goal_type="answer_question"))
        for step in plan.steps:
            assert step.description != ""

    def test_check_stop_at_stability_window_boundary(self):
        r = Planner().check_stop_conditions(
            ReasoningState(iteration=2, current_confidence=0.85, prev_best_score=0.84),
            GoalTypeLimits(step_limit=10, confidence_threshold=0.75, stability_window=2))
        assert r == CognitiveOutcome.GOAL_COMPLETED


# ===================================================================
# TestHypothesis (~6 tests)
# ===================================================================

class TestHypothesis:

    def test_default_creation(self):
        h = Hypothesis(statement="test")
        assert h.statement == "test"
        assert h.strategy == "associative"
        assert h.hypothesis_id.startswith("hyp_")

    def test_final_score_calculated(self):
        h = Hypothesis(support_score=0.8, risk_score=0.2)
        assert abs(h.final_score - 0.6) < 1e-6

    def test_to_dict(self):
        d = Hypothesis(statement="t", support_score=0.5).to_dict()
        assert d["statement"] == "t" and d["support_score"] == 0.5

    def test_from_dict(self):
        h = Hypothesis.from_dict({"statement": "t", "strategy": "deductive"})
        assert h.strategy == "deductive"

    def test_evidence_ids_list(self):
        assert len(Hypothesis(evidence_ids=["e1", "e2"]).evidence_ids) == 2

    def test_negative_final_score(self):
        assert Hypothesis(support_score=0.1, risk_score=0.5).final_score < 0


# ===================================================================
# TestHypothesisEngine (~20 tests)
# ===================================================================

class TestHypothesisEngine:

    def test_creation(self):
        assert HypothesisEngine().max_hypotheses == 3

    def test_custom_max(self):
        assert HypothesisEngine(max_hypotheses=5).max_hypotheses == 5

    def test_generate_empty_query(self):
        assert HypothesisEngine().generate("", [_make_evidence()]) == []

    def test_generate_empty_evidence(self):
        assert HypothesisEngine().generate("test", []) == []

    def test_generate_single_evidence(self):
        engine = HypothesisEngine()
        ev = _make_evidence()
        result = engine.generate("что такое нейрон?", [ev])
        assert len(result) >= 1
        assert result[0].strategy == "associative"

    def test_generate_max_hypotheses_limit(self):
        engine = HypothesisEngine(max_hypotheses=2)
        evs = [_make_evidence(f"ev_{i}", f"факт {i}") for i in range(5)]
        result = engine.generate("query", evs)
        assert len(result) <= 2

    def test_generate_deductive_needs_2_evidence(self):
        engine = HypothesisEngine()
        ev1 = _make_evidence("ev_1", "факт 1", concept_refs=["нейрон"])
        ev2 = _make_evidence("ev_2", "факт 2", concept_refs=["нейрон"])
        result = engine.generate("нейрон", [ev1, ev2])
        deductive = [h for h in result if h.strategy == "deductive"]
        assert len(deductive) >= 1

    def test_generate_no_deductive_with_1_evidence(self):
        engine = HypothesisEngine()
        ev = _make_evidence("ev_1", "факт", concept_refs=["нейрон"])
        result = engine.generate("нейрон", [ev])
        deductive = [h for h in result if h.strategy == "deductive"]
        assert len(deductive) == 0

    def test_generate_deterministic_order(self):
        engine = HypothesisEngine()
        evs = [
            _make_evidence("ev_1", "факт A", relevance=0.9),
            _make_evidence("ev_2", "факт B", relevance=0.7),
        ]
        r1 = engine.generate("query", evs)
        r2 = engine.generate("query", evs)
        assert [h.statement for h in r1] == [h.statement for h in r2]

    def test_generate_empty_content_skipped(self):
        engine = HypothesisEngine()
        ev = _make_evidence("ev_1", "   ")
        result = engine.generate("query", [ev])
        assert len(result) == 0

    def test_score_single_hypothesis(self):
        engine = HypothesisEngine()
        ev = _make_evidence("ev_1", "факт", confidence=0.8, relevance=0.9)
        h = Hypothesis(statement="test", evidence_ids=["ev_1"])
        score = engine.score(h, [ev])
        assert score > 0
        assert h.confidence > 0

    def test_score_with_contradictions(self):
        engine = HypothesisEngine()
        ev = _make_evidence("ev_1", "факт", contradiction_flags=["c1", "c2"])
        h = Hypothesis(statement="test", evidence_ids=["ev_1"])
        engine.score(h, [ev])
        assert h.risk_score > 0

    def test_score_no_evidence_match(self):
        engine = HypothesisEngine()
        h = Hypothesis(statement="test", evidence_ids=["ev_999"])
        score = engine.score(h, [_make_evidence("ev_1")])
        assert score == 0.0
        assert h.confidence == 0.0

    def test_score_all(self):
        engine = HypothesisEngine()
        ev = _make_evidence("ev_1")
        h1 = Hypothesis(statement="h1", evidence_ids=["ev_1"])
        h2 = Hypothesis(statement="h2", evidence_ids=["ev_1"])
        result = engine.score_all([h1, h2], [ev])
        assert len(result) == 2

    def test_rank_by_score(self):
        engine = HypothesisEngine()
        h1 = Hypothesis(statement="low", support_score=0.3)
        h2 = Hypothesis(statement="high", support_score=0.9)
        ranked = engine.rank([h1, h2])
        assert ranked[0].statement == "high"

    def test_rank_stable_sort(self):
        engine = HypothesisEngine()
        h1 = Hypothesis(hypothesis_id="hyp_a", statement="a", final_score=0.5)
        h2 = Hypothesis(hypothesis_id="hyp_b", statement="b", final_score=0.5)
        ranked = engine.rank([h1, h2])
        assert ranked[0].hypothesis_id == "hyp_a"

    def test_rank_empty(self):
        assert HypothesisEngine().rank([]) == []

    def test_generate_deductive_statement_contains_concept(self):
        engine = HypothesisEngine()
        ev1 = _make_evidence("ev_1", "факт 1", concept_refs=["мозг"])
        ev2 = _make_evidence("ev_2", "факт 2", concept_refs=["мозг"])
        result = engine.generate("мозг", [ev1, ev2])
        deductive = [h for h in result if h.strategy == "deductive"]
        if deductive:
            assert "мозг" in deductive[0].statement.lower()

    def test_score_confidence_bounded(self):
        engine = HypothesisEngine()
        ev = _make_evidence("ev_1", "факт", confidence=1.0, relevance=1.0)
        h = Hypothesis(statement="t", evidence_ids=["ev_1"])
        engine.score(h, [ev])
        assert 0.0 <= h.confidence <= 1.0

    def test_make_id_deterministic(self):
        id1 = HypothesisEngine._make_id("assoc", "ev_1")
        id2 = HypothesisEngine._make_id("assoc", "ev_1")
        assert id1 == id2

    def test_make_id_different_seeds(self):
        id1 = HypothesisEngine._make_id("assoc", "ev_1")
        id2 = HypothesisEngine._make_id("assoc", "ev_2")
        assert id1 != id2


# ===================================================================
# TestReasoningTrace (~6 tests)
# ===================================================================

class TestReasoningTrace:

    def test_default_creation(self):
        t = ReasoningTrace()
        assert t.trace_id.startswith("trace_")
        assert t.steps == []
        assert t.outcome == ""

    def test_add_step(self):
        t = ReasoningTrace()
        t.add_step(ReasoningStep(step_type="retrieve"))
        assert t.step_count == 1

    def test_to_dict(self):
        t = ReasoningTrace(query="test", outcome="goal_completed")
        d = t.to_dict()
        assert d["query"] == "test"
        assert d["outcome"] == "goal_completed"

    def test_from_dict(self):
        t = ReasoningTrace.from_dict({"query": "q", "outcome": "retrieval_failed"})
        assert t.query == "q"

    def test_step_count(self):
        t = ReasoningTrace()
        t.add_step(ReasoningStep(step_type="retrieve"))
        t.add_step(ReasoningStep(step_type="hypothesize"))
        assert t.step_count == 2

    def test_reasoning_step_default(self):
        rs = ReasoningStep(step_type="retrieve")
        assert rs.step_id.startswith("rstep_")
        assert rs.duration_ms == 0.0


# ===================================================================
# TestReasoner (~20 tests)
# ===================================================================

class TestReasoner:

    def test_creation(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        assert r is not None

    def test_reason_returns_trace(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="что такое нейрон?", goal_type="answer_question")
        trace = r.reason("что такое нейрон?", goal)
        assert isinstance(trace, ReasoningTrace)
        assert trace.outcome != ""

    def test_reason_has_steps(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        assert trace.step_count >= 1

    def test_reason_retrieval_failed_empty_memory(self):
        mm = _make_mock_memory(search_results=[])
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        assert trace.outcome == CognitiveOutcome.RETRIEVAL_FAILED.value

    def test_reason_has_duration(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        assert trace.total_duration_ms > 0

    def test_reason_has_iterations(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        assert trace.total_iterations >= 1

    def test_reason_with_policy(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        policy = PolicyConstraints(min_confidence=0.1)
        trace = r.reason("q?", goal, policy=policy)
        assert isinstance(trace, ReasoningTrace)

    def test_reason_with_resources(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal, resources={"cpu_percent": 50})
        assert isinstance(trace, ReasoningTrace)

    def test_reason_resource_blocked(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal, resources={"cpu_percent": 99, "memory_percent": 99})
        assert trace.outcome == CognitiveOutcome.RESOURCE_BLOCKED.value

    def test_reason_step_limit_reached(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        # learn_fact has step_limit=3
        goal = Goal(description="q?", goal_type="learn_fact")
        trace = r.reason("q?", goal)
        assert trace.total_iterations >= 1

    def test_reason_evidence_refs_populated(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        # If hypotheses were generated, evidence_refs should be populated
        if trace.hypothesis_count > 0:
            assert len(trace.evidence_refs) >= 1

    def test_reason_best_hypothesis_set(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        if trace.hypothesis_count > 0:
            assert trace.best_hypothesis_id != ""

    def test_reason_memory_search_called(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        r.reason("q?", goal)
        mm.search.assert_called()

    def test_reason_memory_exception_handled(self):
        mm = MagicMock()
        mm.search.side_effect = RuntimeError("DB error")
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        assert trace.outcome == CognitiveOutcome.RETRIEVAL_FAILED.value

    def test_reason_dict_search_results(self):
        mm = MagicMock()
        mm.search.return_value = [
            {"content": "факт 1", "score": 0.8, "memory_type": "semantic", "memory_id": "m1"},
        ]
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        assert trace.step_count >= 1

    def test_reason_string_search_results(self):
        mm = MagicMock()
        mm.search.return_value = ["простой текст"]
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        assert trace.step_count >= 1

    def test_reason_custom_hypothesis_engine(self):
        mm = _make_mock_memory()
        he = HypothesisEngine(max_hypotheses=1)
        r = Reasoner(memory_manager=mm, hypothesis_engine=he)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        assert isinstance(trace, ReasoningTrace)

    def test_reason_custom_planner(self):
        mm = _make_mock_memory()
        p = Planner()
        r = Reasoner(memory_manager=mm, planner=p)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        assert isinstance(trace, ReasoningTrace)

    def test_outcome_to_reason_all_outcomes(self):
        state = ReasoningState(iteration=3, current_confidence=0.5)
        for outcome in CognitiveOutcome:
            reason = Reasoner._outcome_to_reason(outcome, state)
            assert isinstance(reason, str) and len(reason) > 0

    def test_reason_trace_steps_have_types(self):
        mm = _make_mock_memory()
        r = Reasoner(memory_manager=mm)
        goal = Goal(description="q?", goal_type="answer_question")
        trace = r.reason("q?", goal)
        for step in trace.steps:
            assert step.step_type in ("retrieve", "hypothesize", "score", "select")


# ===================================================================
# TestActionType (~4 tests)
# ===================================================================

class TestActionType:

    def test_all_5_types(self):
        assert len(ActionType) == 5

    def test_values(self):
        expected = {"respond_direct", "respond_hedged", "ask_clarification", "refuse", "learn"}
        assert {a.value for a in ActionType} == expected

    def test_learn_exists(self):
        assert ActionType.LEARN.value == "learn"

    def test_action_decision_default(self):
        ad = ActionDecision()
        assert ad.action == ActionType.REFUSE.value
        assert ad.confidence == 0.0


# ===================================================================
# TestActionSelector (~16 tests)
# ===================================================================

class TestActionSelector:

    def test_creation(self):
        assert ActionSelector() is not None

    def test_select_learn_fact(self):
        sel = ActionSelector()
        trace = _make_trace()
        decision = sel.select(trace, goal_type="learn_fact")
        assert decision.action == ActionType.LEARN.value

    def test_select_respond_direct_high_confidence(self):
        sel = ActionSelector()
        trace = _make_trace(confidence=0.8, outcome="goal_completed")
        decision = sel.select(trace, goal_type="answer_question",
                              policy=PolicyConstraints(min_confidence=0.4))
        assert decision.action == ActionType.RESPOND_DIRECT.value

    def test_select_respond_hedged_medium_confidence(self):
        sel = ActionSelector()
        trace = _make_trace(confidence=0.3, outcome="goal_completed")
        policy = PolicyConstraints(min_confidence=0.4)
        decision = sel.select(trace, goal_type="answer_question", policy=policy)
        assert decision.action == ActionType.RESPOND_HEDGED.value

    def test_select_ask_clarification_low_confidence(self):
        sel = ActionSelector()
        trace = _make_trace(confidence=0.1, outcome="goal_completed", hypothesis_count=2)
        policy = PolicyConstraints(min_confidence=0.5)
        decision = sel.select(trace, goal_type="answer_question", policy=policy)
        assert decision.action == ActionType.ASK_CLARIFICATION.value

    def test_select_refuse_no_hypotheses(self):
        sel = ActionSelector()
        trace = _make_trace(confidence=0.0, outcome="goal_completed",
                            hypothesis_count=0, best_statement="", best_hypothesis_id="")
        policy = PolicyConstraints(min_confidence=0.5)
        decision = sel.select(trace, goal_type="answer_question", policy=policy)
        assert decision.action == ActionType.REFUSE.value

    def test_select_refuse_on_retrieval_failed(self):
        sel = ActionSelector()
        trace = _make_trace(outcome="retrieval_failed", confidence=0.0,
                            hypothesis_count=0, best_hypothesis_id="")
        decision = sel.select(trace, goal_type="answer_question")
        assert decision.action == ActionType.REFUSE.value

    def test_select_ask_on_failure_with_hypotheses(self):
        sel = ActionSelector()
        trace = _make_trace(outcome="no_hypothesis_generated", confidence=0.3,
                            hypothesis_count=2)
        decision = sel.select(trace, goal_type="answer_question")
        assert decision.action == ActionType.ASK_CLARIFICATION.value

    def test_select_learn_has_statement(self):
        sel = ActionSelector()
        trace = _make_trace()
        decision = sel.select(trace, goal_type="learn_fact")
        assert "Сохраняю" in decision.statement or "факт" in decision.statement.lower()

    def test_select_hedged_has_prefix(self):
        sel = ActionSelector()
        trace = _make_trace(confidence=0.3, outcome="goal_completed",
                            best_statement="нейрон — клетка")
        policy = PolicyConstraints(min_confidence=0.4)
        decision = sel.select(trace, goal_type="answer_question", policy=policy)
        if decision.action == ActionType.RESPOND_HEDGED.value:
            assert "озможно" in decision.statement

    def test_select_direct_uses_best_statement(self):
        sel = ActionSelector()
        trace = _make_trace(confidence=0.9, outcome="goal_completed",
                            best_statement="нейрон — клетка нервной системы")
        decision = sel.select(trace, goal_type="answer_question",
                              policy=PolicyConstraints(min_confidence=0.4))
        assert decision.statement == "нейрон — клетка нервной системы"

    def test_select_decision_has_reasoning(self):
        sel = ActionSelector()
        trace = _make_trace()
        decision = sel.select(trace, goal_type="answer_question")
        assert decision.reasoning != ""

    def test_select_decision_has_hypothesis_id(self):
        sel = ActionSelector()
        trace = _make_trace(confidence=0.9, outcome="goal_completed")
        decision = sel.select(trace, goal_type="answer_question",
                              policy=PolicyConstraints(min_confidence=0.4))
        assert decision.hypothesis_id == "hyp_1"

    def test_action_decision_action_type_property(self):
        ad = ActionDecision(action="learn")
        assert ad.action_type == ActionType.LEARN

    def test_action_decision_invalid_action_type(self):
        ad = ActionDecision(action="invalid_action")
        assert ad.action_type == ActionType.REFUSE

    def test_select_default_policy(self):
        sel = ActionSelector()
        trace = _make_trace(confidence=0.8, outcome="goal_completed")
        decision = sel.select(trace, goal_type="answer_question")
        assert decision.action in {a.value for a in ActionType}


# ===================================================================
# TestCognitiveCore (~12 tests)
# ===================================================================

class TestCognitiveCore:

    def test_creation(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        assert core is not None
        assert core.cycle_count == 0

    def test_run_returns_cognitive_result(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        from brain.core.contracts import CognitiveResult
        result = core.run("что такое нейрон?")
        assert isinstance(result, CognitiveResult)

    def test_run_has_action(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        result = core.run("что такое нейрон?")
        assert result.action in {a.value for a in ActionType}

    def test_run_has_response(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        result = core.run("что такое нейрон?")
        assert isinstance(result.response, str)

    def test_run_has_trace(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        from brain.core.contracts import TraceChain
        result = core.run("что такое нейрон?")
        assert isinstance(result.trace, TraceChain)
        assert len(result.trace.steps) >= 1

    def test_run_increments_cycle(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        core.run("q1?")
        core.run("q2?")
        assert core.cycle_count == 2

    def test_run_learn_fact(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        result = core.run("запомни: нейрон — клетка нервной системы")
        assert result.action == ActionType.LEARN.value

    def test_run_learn_calls_store(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        core.run("запомни: нейрон — клетка нервной системы")
        mm.store.assert_called()

    def test_run_empty_memory(self):
        mm = _make_mock_memory(search_results=[])
        core = CognitiveCore(memory_manager=mm)
        result = core.run("что такое нейрон?")
        assert result.action in (ActionType.REFUSE.value, ActionType.ASK_CLARIFICATION.value)

    def test_run_with_encoded_percept(self):
        from brain.core.contracts import EncodedPercept, Modality
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        ep = EncodedPercept(
            percept_id="p1", modality=Modality.TEXT,
            metadata={"keywords": ["нейрон", "клетка"]},
        )
        result = core.run("что такое нейрон?", encoded_percept=ep)
        assert isinstance(result.response, str)

    def test_run_with_event_bus(self):
        mm = _make_mock_memory()
        eb = MagicMock()
        core = CognitiveCore(memory_manager=mm, event_bus=eb)
        core.run("что такое нейрон?")
        eb.publish.assert_called()

    def test_run_with_resource_monitor(self):
        mm = _make_mock_memory()
        rm = MagicMock()
        rm.snapshot.return_value = {"cpu_percent": 30, "memory_percent": 40}
        core = CognitiveCore(memory_manager=mm, resource_monitor=rm)
        result = core.run("что такое нейрон?")
        assert isinstance(result.response, str)

    def test_status(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        s = core.status()
        assert "cycle_count" in s
        assert "goal_manager" in s

    def test_goal_manager_property(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        assert isinstance(core.goal_manager, GoalManager)

    def test_detect_goal_type_question(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        assert core._detect_goal_type("что такое нейрон?") == "answer_question"

    def test_detect_goal_type_learn(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        assert core._detect_goal_type("запомни: факт") == "learn_fact"

    def test_detect_goal_type_verify(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        assert core._detect_goal_type("правда ли что земля круглая?") == "verify_claim"

    def test_strip_learn_markers(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        assert core._strip_learn_markers("запомни: нейрон — клетка") == "нейрон — клетка"

    def test_strip_learn_markers_no_marker(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        assert core._strip_learn_markers("просто текст") == "просто текст"

    def test_run_metadata_has_goal_type(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        result = core.run("что такое нейрон?")
        assert "goal_type" in result.metadata

    def test_run_metadata_has_outcome(self):
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm)
        result = core.run("что такое нейрон?")
        assert "outcome" in result.metadata


# ===================================================================
# TestAutoEncode (B.1) (~8 tests)
# ===================================================================

class TestAutoEncode:
    """Тесты для auto-encode в CognitiveCore.run() (B.1)."""

    def test_auto_encode_called_when_no_percept(self):
        """Если encoded_percept=None и encoder есть — encoder.encode() вызывается."""
        mm = _make_mock_memory()
        encoder = MagicMock()
        from brain.core.contracts import EncodedPercept, Modality
        encoder.encode.return_value = EncodedPercept(
            percept_id="auto_1", modality=Modality.TEXT,
            vector=[0.1] * 10, text="что такое нейрон?",
            metadata={"keywords": ["нейрон"], "encoder_status": "ok"},
        )
        core = CognitiveCore(memory_manager=mm, text_encoder=encoder)
        core.run("что такое нейрон?")
        encoder.encode.assert_called_once_with("что такое нейрон?")

    def test_auto_encode_skipped_when_percept_provided(self):
        """Если encoded_percept передан — encoder.encode() НЕ вызывается."""
        mm = _make_mock_memory()
        encoder = MagicMock()
        from brain.core.contracts import EncodedPercept, Modality
        ep = EncodedPercept(
            percept_id="manual_1", modality=Modality.TEXT,
            metadata={"keywords": ["нейрон"]},
        )
        core = CognitiveCore(memory_manager=mm, text_encoder=encoder)
        core.run("что такое нейрон?", encoded_percept=ep)
        encoder.encode.assert_not_called()

    def test_auto_encode_skipped_when_no_encoder(self):
        """Если encoder=None — работает без ошибок (как раньше)."""
        mm = _make_mock_memory()
        core = CognitiveCore(memory_manager=mm, text_encoder=None)
        result = core.run("что такое нейрон?")
        assert result.action in {a.value for a in ActionType}

    def test_auto_encode_failure_graceful(self):
        """Если encoder.encode() бросает исключение — run() не падает."""
        mm = _make_mock_memory()
        encoder = MagicMock()
        encoder.encode.side_effect = RuntimeError("encoder crashed")
        core = CognitiveCore(memory_manager=mm, text_encoder=encoder)
        result = core.run("что такое нейрон?")
        assert result.action in {a.value for a in ActionType}

    def test_auto_encode_enriches_retrieval_query(self):
        """Auto-encoded percept с keywords обогащает retrieval query."""
        mm = _make_mock_memory()
        encoder = MagicMock()
        from brain.core.contracts import EncodedPercept, Modality
        encoder.encode.return_value = EncodedPercept(
            percept_id="auto_2", modality=Modality.TEXT,
            vector=[0.1] * 10, text="нейрон",
            metadata={"keywords": ["нейрон", "клетка", "мозг"], "encoder_status": "ok"},
        )
        core = CognitiveCore(memory_manager=mm, text_encoder=encoder)
        core.run("нейрон")
        # Проверяем что search был вызван с обогащённым запросом
        call_args = mm.search.call_args
        if call_args:
            search_query = call_args[0][0] if call_args[0] else call_args[1].get("query", "")
            # Запрос должен содержать keywords
            assert "нейрон" in search_query

    def test_auto_encode_result_has_percept_in_goal(self):
        """Auto-encode устанавливает has_percept=True в goal context."""
        mm = _make_mock_memory()
        encoder = MagicMock()
        from brain.core.contracts import EncodedPercept, Modality
        encoder.encode.return_value = EncodedPercept(
            percept_id="auto_3", modality=Modality.TEXT,
            vector=[0.1] * 10, text="тест",
            metadata={"keywords": [], "encoder_status": "ok"},
        )
        core = CognitiveCore(memory_manager=mm, text_encoder=encoder)
        core.run("тест")
        # Проверяем что goal был создан с has_percept=True
        gm = core.goal_manager
        # Последняя цель должна иметь has_percept=True
        goals = list(gm._goal_tree.values())
        assert len(goals) >= 1
        last_goal = goals[-1]
        assert last_goal.context.get("has_percept") is True

    def test_auto_encode_learn_fact_with_encoder(self):
        """Auto-encode работает и для learn_fact запросов."""
        mm = _make_mock_memory()
        encoder = MagicMock()
        from brain.core.contracts import EncodedPercept, Modality
        encoder.encode.return_value = EncodedPercept(
            percept_id="auto_4", modality=Modality.TEXT,
            vector=[0.1] * 10, text="запомни: нейрон — клетка",
            metadata={"keywords": ["нейрон", "клетка"], "encoder_status": "ok"},
        )
        core = CognitiveCore(memory_manager=mm, text_encoder=encoder)
        result = core.run("запомни: нейрон — клетка")
        assert result.action == ActionType.LEARN.value
        encoder.encode.assert_called_once()

    def test_auto_encode_with_zero_vector_handled(self):
        """Auto-encode с нулевым вектором не ломает pipeline."""
        mm = _make_mock_memory()
        encoder = MagicMock()
        from brain.core.contracts import EncodedPercept, Modality
        encoder.encode.return_value = EncodedPercept(
            percept_id="auto_5", modality=Modality.TEXT,
            vector=[0.0] * 10, text="тест",
            metadata={"keywords": [], "encoder_status": "failed"},
        )
        core = CognitiveCore(memory_manager=mm, text_encoder=encoder)
        result = core.run("тест")
        assert result.action in {a.value for a in ActionType}


# ===================================================================
# TestImports (~4 tests)
# ===================================================================

class TestImports:

    def test_import_from_package(self):
        from brain.cognition import CognitiveCore
        assert CognitiveCore is not None

    def test_import_all_public(self):
        from brain.cognition import __all__
        assert "CognitiveCore" in __all__
        assert "GoalManager" in __all__
        assert "Reasoner" in __all__
        assert "ActionSelector" in __all__

    def test_import_context_types(self):
        from brain.cognition import (
            CognitiveContext,
        )
        assert CognitiveContext is not None

    def test_import_constants(self):
        from brain.cognition import FAILURE_OUTCOMES, GOAL_TYPE_LIMITS, NORMAL_OUTCOMES
        assert len(GOAL_TYPE_LIMITS) == 4
        assert len(NORMAL_OUTCOMES) == 3
        assert len(FAILURE_OUTCOMES) == 4
