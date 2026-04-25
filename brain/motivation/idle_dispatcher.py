"""IdleDispatcher — постановка фоновой работы с учётом мотивации и cooldown."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, List, Optional

from brain.bridges.llm_budget import LLMRateLimiter
from brain.core.contracts import ClaimStatus, Task
from brain.core.scheduler import Scheduler, TaskPriority
from brain.logging import _NULL_LOGGER, BrainLogger

logger = logging.getLogger(__name__)


@dataclass
class IdleDispatcherConfig:
    """Настройки idle-диспетчера."""
    max_idle_tasks_per_tick: int = 3
    cooldown_per_concept_ticks: int = 15
    max_low_queue_backlog: int = 8
    semantic_top_n: int = 5
    gap_top_n: int = 5
    disputed_pair_limit: int = 10
    dispute_priority_bonus: float = 1.0


@dataclass
class IdleCandidate:
    """Кандидат фоновой idle-задачи."""
    task_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.LOW
    score: float = 0.0
    requires_llm: bool = False
    concept: str = ""
    goal_type: str = ""
    cooldown_key: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IdleDispatchResult:
    """Результат попытки поставить idle-задачи."""
    enqueued: bool
    reason: str = ""
    task_id: str = ""
    task_type: str = ""
    task_ids: List[str] = field(default_factory=list)
    task_types: List[str] = field(default_factory=list)
    enqueued_count: int = 0


class IdleDispatcher:
    """
    Диспетчер фоновой работы.

    U-D контракт:
      - собирает candidates из gaps, важных semantic concepts и disputed pairs;
      - ранжирует через curiosity и motivation preferences;
      - защищает LOW backlog и cooldown per concept;
      - при frustration отдаёт приоритет reconcile → gap и отключает reflect.
    """

    def __init__(
        self,
        scheduler: Scheduler,
        llm_rate_limiter: Optional[LLMRateLimiter] = None,
        *,
        memory: Optional[Any] = None,
        gap_detector: Optional[Any] = None,
        curiosity_engine: Optional[Any] = None,
        motivation_engine: Optional[Any] = None,
        config: Optional[IdleDispatcherConfig] = None,
        brain_logger: Optional[BrainLogger] = None,
    ) -> None:
        self._scheduler = scheduler
        self._llm_rate_limiter = llm_rate_limiter
        self._memory = memory
        self._gap_detector = gap_detector
        self._curiosity = curiosity_engine
        self._motivation = motivation_engine
        self._config = config or IdleDispatcherConfig()
        self._blog: BrainLogger = brain_logger or _NULL_LOGGER  # type: ignore[assignment]
        self._counter = 0
        self._tick = 0
        self._cooldowns: Dict[str, int] = {}

    def collect_candidates(self) -> List[IdleCandidate]:
        """Собрать idle-candidates из подключённых источников."""
        candidates: List[IdleCandidate] = []
        candidates.extend(self._gap_candidates())
        candidates.extend(self._semantic_candidates())
        candidates.extend(self._dispute_candidates())
        return candidates

    def dispatch_tick(self, current_tick: Optional[int] = None) -> IdleDispatchResult:
        """Собрать candidates и поставить до `max_idle_tasks_per_tick` LOW задач."""
        if current_tick is None:
            self._tick += 1
            current_tick = self._tick
        else:
            self._tick = current_tick
        return self.dispatch(
            self.collect_candidates(),
            current_tick=current_tick,
            max_tasks=self._config.max_idle_tasks_per_tick,
        )

    def dispatch(
        self,
        candidates: Iterable[IdleCandidate],
        *,
        current_tick: Optional[int] = None,
        max_tasks: int = 1,
    ) -> IdleDispatchResult:
        """Выбрать лучшие candidates и поставить их в очередь."""
        if current_tick is None:
            current_tick = self._tick
        if max_tasks <= 0:
            return IdleDispatchResult(enqueued=False, reason="idle_no_candidates")
        if not self._can_enqueue_idle_work():
            logger.debug("[IdleDispatcher] idle enqueue skipped by scheduler guard")
            return IdleDispatchResult(enqueued=False, reason="scheduler_backlog_guard")

        candidate_list = list(candidates)
        ranked = self.rank_candidates(candidate_list, current_tick=current_tick)
        task_ids: List[str] = []
        task_types: List[str] = []
        first_task_id = ""
        first_task_type = ""

        while ranked and len(task_ids) < max_tasks and self._can_enqueue_idle_work():
            candidate = ranked.pop(0)
            enqueued_task_id = self._enqueue_candidate(candidate, current_tick)
            if not enqueued_task_id:
                break

            if not first_task_id:
                first_task_id = enqueued_task_id
                first_task_type = candidate.task_type
            task_ids.append(enqueued_task_id)
            task_types.append(candidate.task_type)
            self._mark_cooldown(candidate, current_tick)
            ranked = [
                item
                for item in ranked
                if self._candidate_identity(item) != self._candidate_identity(candidate)
                and self._cooldown_allows(item, current_tick)
            ]

        if not task_ids:
            self._log_no_candidates(current_tick=current_tick, candidate_count=len(candidate_list))
            return IdleDispatchResult(enqueued=False, reason="idle_no_candidates")

        return IdleDispatchResult(
            enqueued=True,
            task_id=first_task_id,
            task_type=first_task_type,
            task_ids=task_ids,
            task_types=task_types,
            enqueued_count=len(task_ids),
        )

    def rank_candidates(
        self,
        candidates: Iterable[IdleCandidate],
        *,
        current_tick: Optional[int] = None,
    ) -> List[IdleCandidate]:
        """Отфильтровать и отсортировать candidates детерминированно."""
        if current_tick is None:
            current_tick = self._tick

        ranked: List[IdleCandidate] = []
        for candidate in self._filter_budget(candidates):
            if not self._cooldown_allows(candidate, current_tick):
                continue
            if not self._motivation_allows(candidate):
                continue
            ranked.append(replace(candidate, score=self._score(candidate)))

        ranked.sort(
            key=lambda item: (
                -item.score,
                int(item.priority),
                item.task_type,
                item.concept,
                self._payload_sort_key(item.payload),
            )
        )
        return ranked

    def _filter_budget(self, candidates: Iterable[IdleCandidate]) -> List[IdleCandidate]:
        """Отфильтровать LLM-dependent candidates при исчерпанном бюджете."""
        result: List[IdleCandidate] = []
        for candidate in candidates:
            if candidate.requires_llm and self._llm_rate_limiter is not None:
                if not self._llm_rate_limiter.allow("idle"):
                    continue
            result.append(candidate)
        return result

    def _gap_candidates(self) -> List[IdleCandidate]:
        if self._gap_detector is None or not hasattr(self._gap_detector, "get_gaps"):
            return []
        try:
            gaps = self._gap_detector.get_gaps(resolved=False)
        except TypeError:
            gaps = self._gap_detector.get_gaps()
        except Exception as exc:
            logger.debug("[IdleDispatcher] gap collection failed: %s", exc)
            return []

        candidates: List[IdleCandidate] = []
        for gap in list(gaps)[: self._config.gap_top_n]:
            severity = getattr(gap, "severity", "")
            severity_value = getattr(severity, "value", str(severity))
            concept = str(getattr(gap, "concept", "") or "")
            base_score = {"high": 0.9, "medium": 0.6, "low": 0.3}.get(severity_value, 0.4)
            candidates.append(
                IdleCandidate(
                    task_type="gap_fill",
                    concept=concept,
                    goal_type="explore_unknown_concept",
                    score=base_score,
                    payload={
                        "concept": concept,
                        "gap_id": getattr(gap, "gap_id", ""),
                        "gap_type": getattr(getattr(gap, "gap_type", ""), "value", ""),
                        "severity": severity_value,
                    },
                    metadata={"source": "knowledge_gap_detector"},
                )
            )
        return candidates

    def _semantic_candidates(self) -> List[IdleCandidate]:
        semantic = getattr(self._memory, "semantic", None)
        if semantic is None or not hasattr(semantic, "get_most_important"):
            return []
        try:
            nodes = semantic.get_most_important(top_n=self._config.semantic_top_n)
        except Exception as exc:
            logger.debug("[IdleDispatcher] semantic collection failed: %s", exc)
            return []

        candidates: List[IdleCandidate] = []
        for node in nodes:
            concept = str(getattr(node, "concept", "") or "")
            importance = float(getattr(node, "importance", 0.5) or 0.5)
            confidence = float(getattr(node, "confidence", 0.5) or 0.5)
            candidates.append(
                IdleCandidate(
                    task_type="self_reflect",
                    concept=concept,
                    goal_type="self_reflection",
                    score=importance * confidence,
                    payload={
                        "concept": concept,
                        "semantic_confidence": confidence,
                        "semantic_importance": importance,
                    },
                    metadata={"source": "semantic_memory"},
                )
            )
        return candidates

    def _dispute_candidates(self) -> List[IdleCandidate]:
        claim_store = getattr(self._memory, "claim_store", None)
        if claim_store is None or not hasattr(claim_store, "get_disputed_pairs"):
            return []
        try:
            pairs = claim_store.get_disputed_pairs(limit=self._config.disputed_pair_limit)
        except Exception as exc:
            logger.debug("[IdleDispatcher] disputed collection failed: %s", exc)
            return []

        candidates: List[IdleCandidate] = []
        for pair in pairs:
            a = getattr(pair, "a", None)
            b = getattr(pair, "b", None)
            concept = str(getattr(a, "concept", "") or getattr(b, "concept", "") or "")
            confidence = max(
                float(getattr(a, "confidence", 0.0) or 0.0),
                float(getattr(b, "confidence", 0.0) or 0.0),
            )
            candidates.append(
                IdleCandidate(
                    task_type="reconcile_dispute",
                    concept=concept,
                    goal_type="verify_claim",
                    score=confidence,
                    payload={
                        "concept": concept,
                        "claim_ids": [
                            getattr(a, "claim_id", ""),
                            getattr(b, "claim_id", ""),
                        ],
                        "source_group_ids": [
                            getattr(a, "source_group_id", ""),
                            getattr(b, "source_group_id", ""),
                        ],
                    },
                    metadata={"source": "claim_store"},
                )
            )
        return candidates

    def _score(self, candidate: IdleCandidate) -> float:
        score = float(candidate.score)
        if candidate.concept and self._curiosity is not None:
            try:
                score += float(self._curiosity.score(candidate.concept))
            except Exception as exc:
                logger.debug("[IdleDispatcher] curiosity score failed: %s", exc)

        state = getattr(self._motivation, "state", None)
        preferences = getattr(state, "preferred_goal_types", {}) or {}
        if candidate.goal_type:
            score += float(preferences.get(candidate.goal_type, 0.0))

        if candidate.task_type == "reconcile_dispute" and self._disputed_count() > 0:
            score += self._config.dispute_priority_bonus

        if getattr(state, "is_frustrated", False):
            if candidate.task_type == "reconcile_dispute":
                score += 2.0
            elif candidate.task_type == "gap_fill":
                score += 1.0

        return round(score, 6)

    def _motivation_allows(self, candidate: IdleCandidate) -> bool:
        state = getattr(self._motivation, "state", None)
        if not getattr(state, "is_frustrated", False):
            return True
        return candidate.task_type != "self_reflect"

    def _can_enqueue_idle_work(self) -> bool:
        return (
            self._scheduler.can_enqueue_idle_work()
            and self._scheduler.low_backlog_size() < self._config.max_low_queue_backlog
        )

    def _enqueue_candidate(self, candidate: IdleCandidate, current_tick: int) -> str:
        self._counter += 1
        task_id = f"idle_{candidate.task_type}_{self._counter:06d}"
        payload = dict(candidate.payload)
        payload.setdefault("concept", candidate.concept)
        payload["idle"] = True
        payload["requires_llm"] = candidate.requires_llm
        payload["idle_score"] = candidate.score
        payload["idle_tick"] = current_tick
        if candidate.goal_type:
            payload["goal_type"] = candidate.goal_type
        if candidate.metadata:
            payload["idle_metadata"] = dict(candidate.metadata)

        task = Task(
            task_id=task_id,
            task_type=candidate.task_type,
            payload=payload,
            trace_id=task_id,
        )
        if not self._scheduler.enqueue_idle(task, candidate.priority):
            return ""
        return task_id

    def _cooldown_allows(self, candidate: IdleCandidate, current_tick: int) -> bool:
        key = self._cooldown_key(candidate)
        if not key:
            return True
        last_tick = self._cooldowns.get(key)
        if last_tick is None:
            return True
        return current_tick - last_tick >= self._config.cooldown_per_concept_ticks

    def _mark_cooldown(self, candidate: IdleCandidate, current_tick: int) -> None:
        key = self._cooldown_key(candidate)
        if key:
            self._cooldowns[key] = current_tick

    @staticmethod
    def _cooldown_key(candidate: IdleCandidate) -> str:
        return candidate.cooldown_key or candidate.concept

    @staticmethod
    def _candidate_identity(candidate: IdleCandidate) -> tuple[str, str, str]:
        return (
            candidate.task_type,
            candidate.concept,
            IdleDispatcher._payload_sort_key(candidate.payload),
        )

    @staticmethod
    def _payload_sort_key(payload: Dict[str, Any]) -> str:
        return repr(sorted(payload.items()))

    def _disputed_count(self) -> int:
        claim_store = getattr(self._memory, "claim_store", None)
        if claim_store is None or not hasattr(claim_store, "count"):
            return 0
        try:
            return int(claim_store.count(status=ClaimStatus.DISPUTED))
        except Exception:
            return 0

    def _log_no_candidates(self, *, current_tick: int, candidate_count: int) -> None:
        logger.debug("[IdleDispatcher] idle_no_candidates")
        self._blog.info(
            "motivation",
            "idle_no_candidates",
            state={
                "tick": current_tick,
                "candidate_count": candidate_count,
                "low_backlog_size": self._scheduler.low_backlog_size(),
            },
        )
