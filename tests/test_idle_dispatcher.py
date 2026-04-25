"""Тесты IdleDispatcher (U-A.2/U-D)."""

from types import SimpleNamespace

from brain.bridges.llm_budget import LLMRateLimitConfig, LLMRateLimiter
from brain.core import EventBus, Scheduler, SchedulerConfig, Task, TaskPriority
from brain.core.contracts import Claim, ClaimStatus, ConflictPair
from brain.motivation.idle_dispatcher import (
    IdleCandidate,
    IdleDispatcher,
    IdleDispatcherConfig,
)


class FakeBrainLogger:
    def __init__(self):
        self.events = []

    def info(self, module, event, **kwargs):
        self.events.append((module, event, kwargs))


class FakeCuriosity:
    def __init__(self, scores):
        self.scores = scores

    def score(self, concept):
        return self.scores.get(concept, 0.0)


class FakeClaimStore:
    def __init__(self, pairs):
        self.pairs = pairs

    def get_disputed_pairs(self, limit=10):
        return self.pairs[:limit]

    def count(self, status=None):
        if status == ClaimStatus.DISPUTED:
            return len(self.pairs) * 2
        return len(self.pairs) * 2


class FakeSemantic:
    def __init__(self, nodes):
        self.nodes = nodes

    def get_most_important(self, top_n=5):
        return self.nodes[:top_n]


class FakeGapDetector:
    def __init__(self, gaps):
        self.gaps = gaps

    def get_gaps(self, resolved=False):
        return self.gaps


def _pair(concept="рабочая память"):
    a = Claim(
        claim_id="claim_a",
        concept=concept,
        claim_text="A",
        source_group_id="src_a",
        confidence=0.7,
        status=ClaimStatus.DISPUTED,
    )
    b = Claim(
        claim_id="claim_b",
        concept=concept,
        claim_text="B",
        source_group_id="src_b",
        confidence=0.6,
        status=ClaimStatus.DISPUTED,
    )
    return ConflictPair(a=a, b=b, detected_ts=1.0)


def test_idle_dispatcher_enqueues_best_candidate_when_scheduler_allows():
    scheduler = Scheduler(
        EventBus(),
        SchedulerConfig(tick_normal_ms=1, max_low_queue_backlog=8, session_id="idle"),
    )
    dispatcher = IdleDispatcher(scheduler)

    result = dispatcher.dispatch(
        [
            IdleCandidate(task_type="reflect", score=0.2),
            IdleCandidate(task_type="verify_claim", score=0.9),
        ]
    )

    assert result.enqueued
    assert result.task_type == "verify_claim"
    assert scheduler.queue_size() == 1
    assert scheduler.low_backlog_size() == 1


def test_idle_dispatcher_skips_when_high_or_normal_pending():
    scheduler = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1))
    scheduler.enqueue(Task(task_id="user", task_type="question"), TaskPriority.HIGH)
    dispatcher = IdleDispatcher(scheduler)

    result = dispatcher.dispatch([IdleCandidate(task_type="reflect", score=1.0)])

    assert not result.enqueued
    assert result.reason == "scheduler_backlog_guard"
    assert scheduler.queue_size() == 1


def test_idle_dispatcher_skips_when_low_backlog_is_full():
    scheduler = Scheduler(
        EventBus(),
        SchedulerConfig(tick_normal_ms=1, max_low_queue_backlog=1),
    )
    scheduler.enqueue(Task(task_id="low", task_type="maintenance"), TaskPriority.LOW)
    dispatcher = IdleDispatcher(scheduler)

    result = dispatcher.dispatch([IdleCandidate(task_type="reflect", score=1.0)])

    assert not result.enqueued
    assert result.reason == "scheduler_backlog_guard"
    assert scheduler.low_backlog_size() == 1


def test_idle_dispatcher_skips_llm_dependent_work_when_budget_exhausted():
    limiter = LLMRateLimiter(LLMRateLimitConfig(llm_calls_per_hour=1))
    limiter.record("ingestion")
    scheduler = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1))
    dispatcher = IdleDispatcher(scheduler, llm_rate_limiter=limiter)

    result = dispatcher.dispatch(
        [IdleCandidate(task_type="llm_reflect", score=1.0, requires_llm=True)]
    )

    assert not result.enqueued
    assert result.reason == "idle_no_candidates"
    assert scheduler.queue_size() == 0


def test_idle_dispatcher_can_choose_non_llm_candidate_when_llm_budget_exhausted():
    limiter = LLMRateLimiter(LLMRateLimitConfig(llm_calls_per_hour=1))
    limiter.record("conflict_advice")
    scheduler = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1))
    dispatcher = IdleDispatcher(scheduler, llm_rate_limiter=limiter)

    result = dispatcher.dispatch(
        [
            IdleCandidate(task_type="llm_reflect", score=1.0, requires_llm=True),
            IdleCandidate(task_type="regex_gap_fill", score=0.2, requires_llm=False),
        ]
    )

    assert result.enqueued
    assert result.task_type == "regex_gap_fill"


def test_idle_dispatcher_collects_and_ranks_sources_deterministically():
    scheduler = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1))
    memory = SimpleNamespace(
        semantic=FakeSemantic(
            [
                SimpleNamespace(
                    concept="нейрон",
                    importance=0.9,
                    confidence=0.8,
                )
            ]
        ),
        claim_store=FakeClaimStore([_pair()]),
    )
    gap_detector = FakeGapDetector(
        [
            SimpleNamespace(
                gap_id="gap_1",
                concept="синапс",
                severity=SimpleNamespace(value="high"),
                gap_type=SimpleNamespace(value="missing"),
            )
        ]
    )
    motivation = SimpleNamespace(
        state=SimpleNamespace(
            preferred_goal_types={"verify_claim": 0.2, "explore_unknown_concept": 0.1},
            is_frustrated=False,
        )
    )
    dispatcher_a = IdleDispatcher(
        scheduler,
        memory=memory,
        gap_detector=gap_detector,
        curiosity_engine=FakeCuriosity({"рабочая память": 0.3, "синапс": 0.5}),
        motivation_engine=motivation,
        config=IdleDispatcherConfig(max_idle_tasks_per_tick=3),
    )
    dispatcher_b = IdleDispatcher(
        Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1)),
        memory=memory,
        gap_detector=gap_detector,
        curiosity_engine=FakeCuriosity({"рабочая память": 0.3, "синапс": 0.5}),
        motivation_engine=motivation,
        config=IdleDispatcherConfig(max_idle_tasks_per_tick=3),
    )

    ranked_a = dispatcher_a.rank_candidates(dispatcher_a.collect_candidates(), current_tick=1)
    ranked_b = dispatcher_b.rank_candidates(dispatcher_b.collect_candidates(), current_tick=1)

    assert [item.task_type for item in ranked_a] == [item.task_type for item in ranked_b]
    assert [item.concept for item in ranked_a] == [item.concept for item in ranked_b]
    assert ranked_a[0].task_type == "reconcile_dispute"
    assert ranked_a[1].task_type == "gap_fill"
    assert ranked_a[2].task_type == "self_reflect"


def test_dispatch_tick_logs_idle_no_candidates():
    scheduler = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1))
    blog = FakeBrainLogger()
    dispatcher = IdleDispatcher(scheduler, brain_logger=blog)

    result = dispatcher.dispatch_tick(current_tick=1)

    assert not result.enqueued
    assert result.reason == "idle_no_candidates"
    assert ("motivation", "idle_no_candidates") in [
        (module, event) for module, event, _ in blog.events
    ]


def test_cooldown_blocks_same_concept_for_configured_ticks():
    scheduler = Scheduler(
        EventBus(),
        SchedulerConfig(tick_normal_ms=1, max_low_queue_backlog=8),
    )
    dispatcher = IdleDispatcher(
        scheduler,
        config=IdleDispatcherConfig(cooldown_per_concept_ticks=15),
    )
    candidate = IdleCandidate(task_type="gap_fill", concept="синапс", score=1.0)

    first = dispatcher.dispatch([candidate], current_tick=1)
    second = dispatcher.dispatch([candidate], current_tick=2)
    after_cooldown = dispatcher.dispatch([candidate], current_tick=16)

    assert first.enqueued
    assert not second.enqueued
    assert second.reason == "idle_no_candidates"
    assert after_cooldown.enqueued
    assert scheduler.low_backlog_size() == 2


def test_disputed_claim_priority_beats_reflect_candidate():
    scheduler = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1))
    memory = SimpleNamespace(claim_store=FakeClaimStore([_pair()]))
    dispatcher = IdleDispatcher(
        scheduler,
        memory=memory,
        config=IdleDispatcherConfig(dispute_priority_bonus=1.0),
    )

    ranked = dispatcher.rank_candidates(
        [
            IdleCandidate(
                task_type="self_reflect",
                concept="нейрон",
                goal_type="self_reflection",
                score=0.8,
            ),
            IdleCandidate(
                task_type="reconcile_dispute",
                concept="рабочая память",
                goal_type="verify_claim",
                score=0.0,
            ),
        ],
        current_tick=1,
    )

    assert ranked[0].task_type == "reconcile_dispute"


def test_frustration_prioritizes_reconcile_then_gap_and_disables_reflect():
    scheduler = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1))
    motivation = SimpleNamespace(
        state=SimpleNamespace(preferred_goal_types={}, is_frustrated=True)
    )
    dispatcher = IdleDispatcher(scheduler, motivation_engine=motivation)

    ranked = dispatcher.rank_candidates(
        [
            IdleCandidate(task_type="self_reflect", concept="нейрон", score=10.0),
            IdleCandidate(task_type="gap_fill", concept="синапс", score=0.2),
            IdleCandidate(
                task_type="reconcile_dispute",
                concept="рабочая память",
                score=0.1,
            ),
        ],
        current_tick=1,
    )

    assert [item.task_type for item in ranked] == ["reconcile_dispute", "gap_fill"]


def test_dispatcher_low_backlog_guard_prevents_queue_inflation():
    scheduler = Scheduler(
        EventBus(),
        SchedulerConfig(tick_normal_ms=1, max_low_queue_backlog=99),
    )
    scheduler.enqueue(Task(task_id="low", task_type="maintenance"), TaskPriority.LOW)
    dispatcher = IdleDispatcher(
        scheduler,
        config=IdleDispatcherConfig(max_low_queue_backlog=1),
    )

    result = dispatcher.dispatch([IdleCandidate(task_type="self_reflect", score=1.0)])

    assert not result.enqueued
    assert result.reason == "scheduler_backlog_guard"
    assert scheduler.low_backlog_size() == 1
