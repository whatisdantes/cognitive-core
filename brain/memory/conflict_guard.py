"""ConflictGuard — lifecycle claim-конфликтов."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from brain.bridges.llm_bridge import LLMProvider, LLMRequest
from brain.bridges.llm_budget import LLMRateLimiter
from brain.core.contracts import Claim, ClaimStatus, ConflictPair, EvidenceKind
from brain.core.text_utils import normalize_claim_text
from brain.logging import _NULL_LOGGER, BrainLogger

from .claim_store import ClaimStore
from .source_memory import SourceMemory

logger = logging.getLogger(__name__)

_NEGATION_MARKERS = frozenset(
    {
        "не",
        "нет",
        "никогда",
        "без",
        "not",
        "no",
        "never",
        "without",
    }
)
_NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


@dataclass
class ConflictGuardConfig:
    """Настройки ConflictGuard."""
    top_k: int = 3
    trust_gap: float = 0.3
    conflict_ttl_ticks: int = 50
    timeout_confidence_decay: float = 0.9
    timeout_confidence_floor: float = 0.20


@dataclass
class ConflictGuardResult:
    """Результат одного lifecycle шага."""
    action: str
    claim_ids: List[str] = field(default_factory=list)
    pair_count: int = 0
    event: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConflictGuard:
    """
    Управляет fast/slow lifecycle claim-конфликтов.

    LLM может дать только advisory-классификацию (`claim_llm_advice`).
    Статусы claims/pairs меняются только deterministic-правилами.
    """

    def __init__(
        self,
        claim_store: ClaimStore,
        source_memory: Optional[SourceMemory] = None,
        goal_manager: Optional[Any] = None,
        brain_logger: Optional[BrainLogger] = None,
        llm_provider: Optional[LLMProvider] = None,
        llm_rate_limiter: Optional[LLMRateLimiter] = None,
        config: Optional[ConflictGuardConfig] = None,
    ) -> None:
        self._claims = claim_store
        self._sources = source_memory
        self._goal_manager = goal_manager
        self._blog: BrainLogger = brain_logger or _NULL_LOGGER  # type: ignore[assignment]
        self._llm_provider = llm_provider
        self._llm_rate_limiter = llm_rate_limiter
        self._config = config or ConflictGuardConfig()
        self._verification_goals: Dict[str, str] = {}

    def check_new_claim(
        self,
        claim: Claim,
        *,
        session_id: str = "",
        trace_id: str = "",
    ) -> ConflictGuardResult:
        """Fast-path: найти cheap contradiction candidates для нового claim-а."""
        candidates = self._top_candidates(claim)
        suspicious: List[Claim] = []
        for other in candidates:
            if self._cheap_conflict(claim, other):
                suspicious.append(other)

        if not suspicious:
            self._claims.set_status(claim.claim_id, ClaimStatus.ACTIVE)
            active = self._claims.get(claim.claim_id) or claim
            self._log(
                "claim_created",
                session_id=session_id,
                trace_id=trace_id,
                state={
                    "claim_id": active.claim_id,
                    "concept": active.concept,
                    "status": ClaimStatus.ACTIVE.value,
                    "source_group_id": active.source_group_id,
                },
            )
            return ConflictGuardResult(
                action="clean",
                claim_ids=[claim.claim_id],
                event="claim_created",
            )

        self._claims.set_status(
            claim.claim_id,
            ClaimStatus.POSSIBLY_CONFLICTING,
            reason="fast_path_suspicious",
        )
        for other in suspicious:
            if other.status == ClaimStatus.ACTIVE:
                self._claims.set_status(
                    other.claim_id,
                    ClaimStatus.POSSIBLY_CONFLICTING,
                    reason="fast_path_suspicious",
                )
            self._claims.mark_conflict_candidate(claim.claim_id, other.claim_id)
            self._log(
                "claim_conflict_candidate",
                session_id=session_id,
                trace_id=trace_id,
                state={
                    "claim_id_a": claim.claim_id,
                    "claim_id_b": other.claim_id,
                    "concept": claim.concept,
                    "source_group_ids": [claim.source_group_id, other.source_group_id],
                },
            )

        return ConflictGuardResult(
            action="candidate",
            claim_ids=[claim.claim_id, *(c.claim_id for c in suspicious)],
            pair_count=len(suspicious),
            event="claim_conflict_candidate",
        )

    def reconcile_candidates(
        self,
        *,
        limit: int = 5,
        current_tick: int = 0,
        session_id: str = "",
        trace_id: str = "",
    ) -> List[ConflictGuardResult]:
        """Slow-path: подтвердить или отклонить candidate pairs."""
        results: List[ConflictGuardResult] = []
        for pair in self._claims.get_conflict_candidates(limit=limit):
            self._record_llm_advice(pair, session_id=session_id, trace_id=trace_id)
            if self._cheap_conflict(pair.a, pair.b):
                self._mark_disputed(pair, current_tick=current_tick)
                self._log_pair("claim_disputed", pair, session_id, trace_id)
                results.append(
                    ConflictGuardResult(
                        action="disputed",
                        claim_ids=[pair.a.claim_id, pair.b.claim_id],
                        pair_count=1,
                        event="claim_disputed",
                    )
                )
            else:
                self._claims.dismiss_conflict(
                    pair.a.claim_id,
                    pair.b.claim_id,
                    resolution="false_positive",
                )
                self._claims.restore_if_no_open_conflicts(pair.a.claim_id)
                self._claims.restore_if_no_open_conflicts(pair.b.claim_id)
                self._log_pair("claim_conflict_dismissed", pair, session_id, trace_id)
                results.append(
                    ConflictGuardResult(
                        action="dismissed",
                        claim_ids=[pair.a.claim_id, pair.b.claim_id],
                        pair_count=1,
                        event="claim_conflict_dismissed",
                    )
                )
        return results

    def resolve_disputed(
        self,
        *,
        limit: int = 10,
        current_tick: int = 0,
        session_id: str = "",
        trace_id: str = "",
    ) -> List[ConflictGuardResult]:
        """Применить deterministic resolution к disputed pairs."""
        results: List[ConflictGuardResult] = []
        for pair in self._claims.get_disputed_pairs(limit=limit):
            result = self._resolve_pair(
                pair,
                current_tick=current_tick,
                session_id=session_id,
                trace_id=trace_id,
            )
            results.append(result)
        return results

    def handle_timeouts(
        self,
        *,
        current_tick: int,
        limit: int = 10,
        session_id: str = "",
        trace_id: str = "",
    ) -> List[ConflictGuardResult]:
        """Обработать TTL для unresolved disputed pairs без retract/resolve."""
        results: List[ConflictGuardResult] = []
        for pair in self._claims.get_disputed_pairs(limit=limit):
            disputed_tick = self._pair_disputed_tick(pair)
            if disputed_tick is None:
                continue
            if current_tick - disputed_tick < self._config.conflict_ttl_ticks:
                continue

            before = {
                pair.a.claim_id: pair.a.confidence,
                pair.b.claim_id: pair.b.confidence,
            }
            for claim in (pair.a, pair.b):
                decayed = max(
                    self._config.timeout_confidence_floor,
                    claim.confidence * self._config.timeout_confidence_decay,
                )
                self._claims.set_confidence(
                    claim.claim_id,
                    decayed,
                    reason="claim_resolution_timed_out",
                )
                self._claims.update_metadata(
                    claim.claim_id,
                    {"last_timeout_tick": current_tick},
                )

            goal_id = self._create_verification_goal(pair, reason="timeout")
            updated_a = self._claims.get(pair.a.claim_id)
            updated_b = self._claims.get(pair.b.claim_id)
            after = {
                pair.a.claim_id: updated_a.confidence if updated_a is not None else None,
                pair.b.claim_id: updated_b.confidence if updated_b is not None else None,
            }
            self._log(
                "claim_resolution_timed_out",
                session_id=session_id,
                trace_id=trace_id,
                state={
                    "claim_id_a": pair.a.claim_id,
                    "claim_id_b": pair.b.claim_id,
                    "before_confidence": before,
                    "after_confidence": after,
                    "verification_goal_id": goal_id,
                },
            )
            results.append(
                ConflictGuardResult(
                    action="timed_out",
                    claim_ids=[pair.a.claim_id, pair.b.claim_id],
                    pair_count=1,
                    event="claim_resolution_timed_out",
                    metadata={
                        "before_confidence": before,
                        "after_confidence": after,
                        "verification_goal_id": goal_id,
                    },
                )
            )
        return results

    def reconcile_disputed(
        self,
        *,
        limit: int = 5,
        current_tick: int = 0,
        session_id: str = "",
        trace_id: str = "",
    ) -> List[ConflictGuardResult]:
        """Единый recurring handler: candidates → disputed → resolution → TTL."""
        results = self.reconcile_candidates(
            limit=limit,
            current_tick=current_tick,
            session_id=session_id,
            trace_id=trace_id,
        )
        results.extend(
            self.resolve_disputed(
                limit=limit,
                current_tick=current_tick,
                session_id=session_id,
                trace_id=trace_id,
            )
        )
        results.extend(
            self.handle_timeouts(
                current_tick=current_tick,
                limit=limit,
                session_id=session_id,
                trace_id=trace_id,
            )
        )
        return results

    def _top_candidates(self, claim: Claim) -> List[Claim]:
        statuses = [
            ClaimStatus.ACTIVE,
            ClaimStatus.POSSIBLY_CONFLICTING,
            ClaimStatus.DISPUTED,
        ]
        candidates = [
            other
            for other in self._claims.find_by_concept(claim.concept, statuses=statuses)
            if other.claim_id != claim.claim_id
        ]
        candidates.sort(key=lambda c: (-c.confidence, -c.created_ts, c.claim_id))
        return candidates[: self._config.top_k]

    def _cheap_conflict(self, a: Claim, b: Claim) -> bool:
        if a.concept != b.concept:
            return False
        if self._numeric_divergence(a, b):
            return True
        return self._negation_conflict(a.claim_text, b.claim_text)

    @staticmethod
    def _numeric_divergence(a: Claim, b: Claim) -> bool:
        nums_a: List[str] = _NUMBER_RE.findall(normalize_claim_text(a.claim_text))
        nums_b: List[str] = _NUMBER_RE.findall(normalize_claim_text(b.claim_text))
        if not nums_a or not nums_b:
            return False
        return nums_a[0].replace(",", ".") != nums_b[0].replace(",", ".")

    @staticmethod
    def _negation_conflict(text_a: str, text_b: str) -> bool:
        tokens_a = normalize_claim_text(text_a).split()
        tokens_b = normalize_claim_text(text_b).split()
        neg_a = any(token in _NEGATION_MARKERS for token in tokens_a)
        neg_b = any(token in _NEGATION_MARKERS for token in tokens_b)
        if neg_a == neg_b:
            return False
        clean_a = {token for token in tokens_a if token not in _NEGATION_MARKERS}
        clean_b = {token for token in tokens_b if token not in _NEGATION_MARKERS}
        if not clean_a or not clean_b:
            return False
        overlap = len(clean_a & clean_b) / max(1, min(len(clean_a), len(clean_b)))
        return overlap >= 0.6

    def _record_llm_advice(
        self,
        pair: ConflictPair,
        *,
        session_id: str,
        trace_id: str,
    ) -> None:
        if self._llm_provider is None or not self._llm_provider.is_available():
            return
        if self._llm_rate_limiter is not None and not self._llm_rate_limiter.allow("conflict_advice"):
            return
        request = LLMRequest(
            prompt=(
                "Классифицируй пару claims одним словом: not_a_conflict, "
                "negation, numeric или paraphrase.\n"
                f"A: {pair.a.claim_text}\nB: {pair.b.claim_text}"
            ),
            max_tokens=20,
            temperature=0.0,
            metadata={"purpose": "conflict_advice"},
        )
        try:
            response = self._llm_provider.complete(request)
        except Exception as exc:
            logger.debug("[ConflictGuard] LLM advice failed: %s", exc)
            return
        if self._llm_rate_limiter is not None:
            self._llm_rate_limiter.record("conflict_advice")
        self._log(
            "claim_llm_advice",
            session_id=session_id,
            trace_id=trace_id,
            state={
                "claim_id_a": pair.a.claim_id,
                "claim_id_b": pair.b.claim_id,
                "advice": response.text.strip()[:80],
                "provider": response.provider,
            },
        )

    def _mark_disputed(self, pair: ConflictPair, *, current_tick: int) -> None:
        self._claims.mark_disputed(pair.a.claim_id, pair.b.claim_id)
        metadata = {"disputed_tick": current_tick} if current_tick > 0 else {}
        if metadata:
            self._claims.update_metadata(pair.a.claim_id, metadata)
            self._claims.update_metadata(pair.b.claim_id, metadata)

    def _resolve_pair(
        self,
        pair: ConflictPair,
        *,
        current_tick: int,
        session_id: str,
        trace_id: str,
    ) -> ConflictGuardResult:
        trusted = self._resolve_by_trust(pair, session_id, trace_id)
        if trusted is not None:
            return trusted
        majority = self._resolve_by_majority(pair, session_id, trace_id)
        if majority is not None:
            return majority
        recency = self._resolve_by_recency(pair, session_id, trace_id)
        if recency is not None:
            return recency

        goal_id = self._create_verification_goal(pair, reason="hypothesis")
        self._log(
            "claim_verification_goal_created",
            session_id=session_id,
            trace_id=trace_id,
            state={
                "claim_id_a": pair.a.claim_id,
                "claim_id_b": pair.b.claim_id,
                "verification_goal_id": goal_id,
                "current_tick": current_tick,
            },
        )
        return ConflictGuardResult(
            action="verification_goal",
            claim_ids=[pair.a.claim_id, pair.b.claim_id],
            pair_count=1,
            event="claim_verification_goal_created",
            metadata={"verification_goal_id": goal_id},
        )

    def _resolve_by_trust(
        self,
        pair: ConflictPair,
        session_id: str,
        trace_id: str,
    ) -> Optional[ConflictGuardResult]:
        if self._sources is None:
            return None
        trust_a = self._sources.get_trust(pair.a.source_group_id)
        trust_b = self._sources.get_trust(pair.b.source_group_id)
        gap = abs(trust_a - trust_b)
        if gap < self._config.trust_gap:
            return None
        winner, loser = (pair.a, pair.b) if trust_a > trust_b else (pair.b, pair.a)
        self._claims.resolve(winner.claim_id, loser.claim_id, "trust")
        self._log_resolution(
            "claim_resolved_by_trust",
            winner,
            loser,
            session_id,
            trace_id,
            {"trust_a": trust_a, "trust_b": trust_b},
        )
        return ConflictGuardResult(
            action="resolved_by_trust",
            claim_ids=[winner.claim_id, loser.claim_id],
            pair_count=1,
            event="claim_resolved_by_trust",
        )

    def _resolve_by_majority(
        self,
        pair: ConflictPair,
        session_id: str,
        trace_id: str,
    ) -> Optional[ConflictGuardResult]:
        statuses = [
            ClaimStatus.ACTIVE,
            ClaimStatus.POSSIBLY_CONFLICTING,
            ClaimStatus.DISPUTED,
        ]
        claims = self._claims.find_by_family(pair.a.concept, pair.a.claim_family_key, statuses)
        by_stance: Dict[str, Dict[str, Claim]] = {}
        for claim in claims:
            if not claim.source_group_id:
                continue
            by_stance.setdefault(claim.stance_key, {})
            existing = by_stance[claim.stance_key].get(claim.source_group_id)
            if existing is None or claim.confidence > existing.confidence:
                by_stance[claim.stance_key][claim.source_group_id] = claim

        stance_a = pair.a.stance_key
        stance_b = pair.b.stance_key
        count_a = len(by_stance.get(stance_a, {}))
        count_b = len(by_stance.get(stance_b, {}))
        winner_stance: Optional[str] = None
        if count_a >= 2 and count_b <= 1:
            winner_stance = stance_a
        elif count_b >= 2 and count_a <= 1:
            winner_stance = stance_b
        if winner_stance is None:
            return None

        winner = pair.a if pair.a.stance_key == winner_stance else pair.b
        loser = pair.b if winner.claim_id == pair.a.claim_id else pair.a
        self._claims.resolve(winner.claim_id, loser.claim_id, "majority")
        self._log_resolution(
            "claim_resolved_by_majority",
            winner,
            loser,
            session_id,
            trace_id,
            {"stance_counts": {stance_a: count_a, stance_b: count_b}},
        )
        return ConflictGuardResult(
            action="resolved_by_majority",
            claim_ids=[winner.claim_id, loser.claim_id],
            pair_count=1,
            event="claim_resolved_by_majority",
        )

    def _resolve_by_recency(
        self,
        pair: ConflictPair,
        session_id: str,
        trace_id: str,
    ) -> Optional[ConflictGuardResult]:
        if pair.a.evidence_kind != EvidenceKind.VERSIONED:
            return None
        if pair.b.evidence_kind != EvidenceKind.VERSIONED:
            return None
        winner, loser = (
            (pair.a, pair.b)
            if pair.a.created_ts >= pair.b.created_ts
            else (pair.b, pair.a)
        )
        self._claims.resolve(winner.claim_id, loser.claim_id, "recency")
        self._log_resolution(
            "claim_resolved_by_recency",
            winner,
            loser,
            session_id,
            trace_id,
            {"winner_created_ts": winner.created_ts, "loser_created_ts": loser.created_ts},
        )
        return ConflictGuardResult(
            action="resolved_by_recency",
            claim_ids=[winner.claim_id, loser.claim_id],
            pair_count=1,
            event="claim_resolved_by_recency",
        )

    def _pair_disputed_tick(self, pair: ConflictPair) -> Optional[int]:
        ticks: List[int] = []
        for claim in (pair.a, pair.b):
            raw_tick = claim.metadata.get("disputed_tick")
            if raw_tick is None:
                continue
            try:
                ticks.append(int(raw_tick))
            except (TypeError, ValueError):
                continue
        if not ticks:
            return None
        return min(ticks)

    def _create_verification_goal(self, pair: ConflictPair, *, reason: str) -> str:
        pair_key = "::".join(sorted([pair.a.claim_id, pair.b.claim_id]))
        if pair_key in self._verification_goals:
            return self._verification_goals[pair_key]
        if self._goal_manager is None:
            goal_id = f"verification:{pair_key}"
            self._verification_goals[pair_key] = goal_id
            return goal_id
        from brain.cognition.goal_manager import Goal

        goal = Goal(
            goal_type="verify_claim",
            description=(
                f"Проверить конфликт claims для '{pair.a.concept}': "
                f"'{pair.a.claim_text}' vs '{pair.b.claim_text}'"
            ),
            priority=0.8,
            context={
                "claim_id_a": pair.a.claim_id,
                "claim_id_b": pair.b.claim_id,
                "reason": reason,
            },
        )
        self._goal_manager.push(goal)
        self._verification_goals[pair_key] = goal.goal_id
        return goal.goal_id

    def _log_pair(
        self,
        event: str,
        pair: ConflictPair,
        session_id: str,
        trace_id: str,
    ) -> None:
        self._log(
            event,
            session_id=session_id,
            trace_id=trace_id,
            state={
                "claim_id_a": pair.a.claim_id,
                "claim_id_b": pair.b.claim_id,
                "concept": pair.a.concept,
            },
        )

    def _log_resolution(
        self,
        event: str,
        winner: Claim,
        loser: Claim,
        session_id: str,
        trace_id: str,
        extra: Dict[str, Any],
    ) -> None:
        state = {
            "winner_id": winner.claim_id,
            "loser_id": loser.claim_id,
            "concept": winner.concept,
        }
        state.update(extra)
        self._log(event, session_id=session_id, trace_id=trace_id, state=state)

    def _log(
        self,
        event: str,
        *,
        session_id: str,
        trace_id: str,
        state: Dict[str, Any],
    ) -> None:
        self._blog.info(
            "memory",
            event,
            session_id=session_id or "memory_direct",
            trace_id=trace_id,
            state=state,
        )
