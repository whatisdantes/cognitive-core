"""Fast-path тесты ConflictGuard (U-B.1)."""

from brain.core.contracts import Claim, ClaimStatus
from brain.memory import ClaimStore, ConflictGuard, MemoryDatabase


def _guard(tmp_path):
    db = MemoryDatabase(str(tmp_path / "memory.db"))
    store = ClaimStore(db)
    guard = ConflictGuard(store)
    return db, store, guard


def _claim(
    store: ClaimStore,
    text: str,
    source: str,
    *,
    concept: str = "система",
    confidence: float = 1.0,
) -> Claim:
    return store.create(
        Claim(
            concept=concept,
            claim_text=text,
            source_ref=source,
            source_group_id=source.split("#", 1)[0],
            confidence=confidence,
            status=ClaimStatus.ACTIVE,
        )
    )


def test_fast_path_negation_creates_candidate_not_disputed(tmp_path):
    db, store, guard = _guard(tmp_path)
    try:
        old = _claim(store, "система работает", "src-a#p1")
        new = _claim(store, "система не работает", "src-b#p1")

        result = guard.check_new_claim(new)

        assert result.action == "candidate"
        assert len(store.get_conflict_candidates()) == 1
        assert store.get_disputed_pairs() == []
        assert store.get(old.claim_id).status == ClaimStatus.POSSIBLY_CONFLICTING
        assert store.get(new.claim_id).status == ClaimStatus.POSSIBLY_CONFLICTING
    finally:
        db.close()


def test_fast_path_numeric_divergence_creates_candidate(tmp_path):
    db, store, guard = _guard(tmp_path)
    try:
        old = _claim(
            store,
            "рабочая память содержит 7 элементов",
            "src-a#p1",
            concept="рабочая память",
        )
        new = _claim(
            store,
            "рабочая память содержит 4 элемента",
            "src-b#p1",
            concept="рабочая память",
        )

        result = guard.check_new_claim(new)

        assert result.action == "candidate"
        pair = store.get_conflict_candidates()[0]
        assert {pair.a.claim_id, pair.b.claim_id} == {old.claim_id, new.claim_id}
    finally:
        db.close()


def test_fast_path_checks_only_top_k_candidates(tmp_path):
    db, store, guard = _guard(tmp_path)
    try:
        _claim(store, "система полезна для анализа", "src-a#p1", confidence=1.0)
        _claim(store, "система ускоряет поиск", "src-b#p1", confidence=0.9)
        _claim(store, "система поддерживает обучение", "src-c#p1", confidence=0.8)
        _claim(store, "система работает", "src-d#p1", confidence=0.1)
        new = _claim(store, "система не работает", "src-e#p1", confidence=0.5)

        result = guard.check_new_claim(new)

        assert result.action == "clean"
        assert store.get_conflict_candidates() == []
        assert store.get(new.claim_id).status == ClaimStatus.ACTIVE
    finally:
        db.close()


def test_fast_path_allows_intra_source_candidate(tmp_path):
    db, store, guard = _guard(tmp_path)
    try:
        old = _claim(store, "система работает", "book#p1")
        new = _claim(store, "система не работает", "book#p2")

        result = guard.check_new_claim(new)

        assert result.action == "candidate"
        pair = store.get_conflict_candidates()[0]
        assert pair.a.source_group_id == pair.b.source_group_id == "book"
        assert {pair.a.claim_id, pair.b.claim_id} == {old.claim_id, new.claim_id}
    finally:
        db.close()
