"""Slow-path и resolution тесты ConflictGuard (U-B.2-U-B.4)."""

from brain.bridges.llm_bridge import MockProvider
from brain.bridges.llm_budget import LLMRateLimitConfig, LLMRateLimiter
from brain.cognition.goal_manager import GoalManager
from brain.core.contracts import Claim, ClaimStatus, ConflictStatus, EvidenceKind
from brain.logging import BrainLogger
from brain.memory import ClaimStore, ConflictGuard, MemoryDatabase, SourceMemory


def _store(tmp_path):
    db = MemoryDatabase(str(tmp_path / "memory.db"))
    store = ClaimStore(db)
    source = SourceMemory(
        data_path=str(tmp_path / "sources.json"),
        storage_backend="sqlite",
        db=db,
    )
    return db, store, source


def _claim(
    store: ClaimStore,
    text: str,
    source_group: str,
    *,
    concept: str = "система",
    confidence: float = 1.0,
    status: ClaimStatus = ClaimStatus.ACTIVE,
    evidence_kind: EvidenceKind = EvidenceKind.TIMELESS,
    created_ts: float = 0.0,
    source_ref: str = "",
) -> Claim:
    return store.create(
        Claim(
            concept=concept,
            claim_text=text,
            source_ref=source_ref or f"{source_group}#p1",
            source_group_id=source_group,
            confidence=confidence,
            status=status,
            evidence_kind=evidence_kind,
            created_ts=created_ts,
        )
    )


def test_false_positive_candidate_is_dismissed(tmp_path):
    db, store, source = _store(tmp_path)
    try:
        a = _claim(store, "система полезна", "a")
        b = _claim(store, "система документирована", "b")
        store.mark_conflict_candidate(a.claim_id, b.claim_id)
        guard = ConflictGuard(store, source_memory=source)

        result = guard.reconcile_candidates(limit=5)[0]

        assert result.action == "dismissed"
        assert store.get_conflict_candidates() == []
        assert store.get(a.claim_id).status == ClaimStatus.ACTIVE
        assert store.get(b.claim_id).status == ClaimStatus.ACTIVE
    finally:
        db.close()


def test_llm_advice_is_logged_without_status_side_effects(tmp_path):
    db, store, source = _store(tmp_path)
    blog = BrainLogger(log_dir=str(tmp_path / "logs"), min_level="DEBUG")
    try:
        a = _claim(store, "система полезна", "a")
        b = _claim(store, "система документирована", "b")
        store.mark_conflict_candidate(a.claim_id, b.claim_id)
        guard = ConflictGuard(
            store,
            source_memory=source,
            brain_logger=blog,
            llm_provider=MockProvider("numeric"),
            llm_rate_limiter=LLMRateLimiter(LLMRateLimitConfig(llm_calls_per_hour=10)),
        )

        result = guard.reconcile_candidates(limit=5)[0]
        blog.flush()
        text = (tmp_path / "logs" / "memory.jsonl").read_text(encoding="utf-8")

        assert '"event": "claim_llm_advice"' in text
        assert result.action == "dismissed"
        assert store.get(a.claim_id).status == ClaimStatus.ACTIVE
        assert store.get(b.claim_id).status == ClaimStatus.ACTIVE
    finally:
        blog.close()
        db.close()


def test_conflict_advice_skips_when_budget_exhausted(tmp_path):
    db, store, source = _store(tmp_path)
    blog = BrainLogger(log_dir=str(tmp_path / "logs"), min_level="DEBUG")
    try:
        a = _claim(store, "система полезна", "a")
        b = _claim(store, "система документирована", "b")
        store.mark_conflict_candidate(a.claim_id, b.claim_id)
        guard = ConflictGuard(
            store,
            source_memory=source,
            brain_logger=blog,
            llm_provider=MockProvider("numeric"),
            llm_rate_limiter=LLMRateLimiter(LLMRateLimitConfig(llm_calls_per_hour=0)),
        )

        guard.reconcile_candidates(limit=5)
        blog.flush()
        text = (tmp_path / "logs" / "memory.jsonl").read_text(encoding="utf-8")

        assert '"event": "claim_llm_advice"' not in text
    finally:
        blog.close()
        db.close()


def test_trust_resolution_picks_more_trusted_source(tmp_path):
    db, store, source = _store(tmp_path)
    try:
        source.register("trusted").trust_score = 0.95
        source.register("weak").trust_score = 0.40
        a = _claim(store, "система работает", "trusted")
        b = _claim(store, "система не работает", "weak")
        store.mark_disputed(a.claim_id, b.claim_id)
        guard = ConflictGuard(store, source_memory=source)

        result = guard.resolve_disputed()[0]

        assert result.action == "resolved_by_trust"
        assert store.get(a.claim_id).status == ClaimStatus.ACTIVE
        assert store.get(b.claim_id).status == ClaimStatus.SUPERSEDED
    finally:
        db.close()


def test_majority_uses_unique_source_group_ids(tmp_path):
    db, store, _source = _store(tmp_path)
    try:
        a = _claim(
            store,
            "рабочая память содержит 7 элементов",
            "material-a",
            concept="рабочая память",
        )
        _claim(
            store,
            "рабочая память содержит 7 элементов",
            "material-a",
            concept="рабочая память",
            source_ref="material-a#p2",
        )
        b = _claim(
            store,
            "рабочая память содержит 4 элемента",
            "material-b",
            concept="рабочая память",
        )
        store.mark_disputed(a.claim_id, b.claim_id)
        guard = ConflictGuard(store, source_memory=None, goal_manager=GoalManager())

        first = guard.resolve_disputed()[0]
        same_source_claims = [
            claim
            for claim in store.find_by_family(a.concept, a.claim_family_key)
            if claim.source_group_id == "material-a"
        ]
        assert len(same_source_claims) == 2
        assert first.action == "verification_goal"
        assert store.get_disputed_pairs()[0].status == ConflictStatus.DISPUTED

        _claim(
            store,
            "рабочая память содержит 7 элементов",
            "material-c",
            concept="рабочая память",
        )
        second = guard.resolve_disputed()[0]

        assert second.action == "resolved_by_majority"
        assert store.get(a.claim_id).status == ClaimStatus.ACTIVE
        assert store.get(b.claim_id).status == ClaimStatus.SUPERSEDED
    finally:
        db.close()


def test_versioned_conflict_resolves_by_recency(tmp_path):
    db, store, _source = _store(tmp_path)
    try:
        old = _claim(
            store,
            "api версия 1",
            "doc-old",
            concept="api",
            evidence_kind=EvidenceKind.VERSIONED,
            created_ts=10.0,
        )
        new = _claim(
            store,
            "api версия 2",
            "doc-new",
            concept="api",
            evidence_kind=EvidenceKind.VERSIONED,
            created_ts=20.0,
        )
        store.mark_disputed(old.claim_id, new.claim_id)
        guard = ConflictGuard(store, source_memory=None)

        result = guard.resolve_disputed()[0]

        assert result.action == "resolved_by_recency"
        assert store.get(new.claim_id).status == ClaimStatus.ACTIVE
        assert store.get(old.claim_id).status == ClaimStatus.SUPERSEDED
    finally:
        db.close()


def test_timeless_conflict_does_not_resolve_by_recency(tmp_path):
    db, store, _source = _store(tmp_path)
    try:
        old = _claim(store, "api версия 1", "doc-old", concept="api", created_ts=10.0)
        new = _claim(store, "api версия 2", "doc-new", concept="api", created_ts=20.0)
        store.mark_disputed(old.claim_id, new.claim_id)
        guard = ConflictGuard(store, source_memory=None, goal_manager=GoalManager())

        result = guard.resolve_disputed()[0]

        assert result.action == "verification_goal"
        assert store.get(old.claim_id).status == ClaimStatus.DISPUTED
        assert store.get(new.claim_id).status == ClaimStatus.DISPUTED
    finally:
        db.close()


def test_ttl_timeout_keeps_dispute_and_decays_confidence(tmp_path):
    db, store, _source = _store(tmp_path)
    try:
        a = _claim(store, "система работает", "a", confidence=0.8)
        b = _claim(store, "система не работает", "b", confidence=0.7)
        store.mark_conflict_candidate(a.claim_id, b.claim_id)
        guard = ConflictGuard(store, source_memory=None, goal_manager=GoalManager())
        guard.reconcile_candidates(current_tick=10)

        result = guard.handle_timeouts(current_tick=60)[0]

        assert result.action == "timed_out"
        pair = store.get_disputed_pairs()[0]
        assert pair.status == ConflictStatus.DISPUTED
        assert pair.resolution is None
        assert store.get(a.claim_id).status == ClaimStatus.DISPUTED
        assert store.get(b.claim_id).status == ClaimStatus.DISPUTED
        assert round(store.get(a.claim_id).confidence, 2) == 0.72
        assert round(store.get(b.claim_id).confidence, 2) == 0.63
    finally:
        db.close()
