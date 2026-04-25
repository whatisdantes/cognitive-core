from brain.core.contracts import Claim, ClaimStatus, EvidenceKind
from brain.memory.claim_store import ClaimStore
from brain.memory.storage import MemoryDatabase


def _store(tmp_path):
    db = MemoryDatabase(str(tmp_path / "memory.db"))
    return db, ClaimStore(db)


def test_create_is_idempotent_by_concept_text_source(tmp_path):
    db, store = _store(tmp_path)
    try:
        claim = Claim(
            concept="Python",
            claim_text="Python это язык программирования",
            source_ref="book#p1",
            source_group_id="book",
            status=ClaimStatus.ACTIVE,
        )
        first = store.create(claim)
        second = store.create(claim)

        assert first.claim_id == second.claim_id
        assert store.count() == 1
        assert first.concept == "python"
        assert first.claim_family_key
        assert first.stance_key
    finally:
        db.close()


def test_claim_contract_roundtrip_restores_enums_and_span():
    claim = Claim(
        claim_id="c1",
        concept="python",
        claim_text="Python это язык",
        source_ref="book#p1",
        source_group_id="book",
        evidence_span=(3, 12),
        evidence_kind=EvidenceKind.VERSIONED,
        status=ClaimStatus.ACTIVE,
    )

    restored = Claim.from_dict(claim.to_dict())

    assert restored.status == ClaimStatus.ACTIVE
    assert restored.evidence_kind == EvidenceKind.VERSIONED
    assert restored.evidence_span == (3, 12)


def test_active_and_answerable_claims_are_distinct(tmp_path):
    db, store = _store(tmp_path)
    try:
        active = store.create(
            Claim(
                concept="память",
                claim_text="память хранит опыт",
                source_ref="a",
                source_group_id="a",
                status=ClaimStatus.ACTIVE,
            )
        )
        disputed = store.create(
            Claim(
                concept="память",
                claim_text="память не хранит опыт",
                source_ref="b",
                source_group_id="b",
                status=ClaimStatus.DISPUTED,
            )
        )

        assert [c.claim_id for c in store.active_claims("память")] == [active.claim_id]
        assert {c.claim_id for c in store.answerable_claims("память")} == {
            active.claim_id,
            disputed.claim_id,
        }
    finally:
        db.close()


def test_conflict_pair_lifecycle_and_resolution(tmp_path):
    db, store = _store(tmp_path)
    try:
        a = store.create(
            Claim(
                concept="рабочая память",
                claim_text="рабочая память содержит 7 элементов",
                source_ref="a",
                source_group_id="a",
                status=ClaimStatus.ACTIVE,
            )
        )
        b = store.create(
            Claim(
                concept="рабочая память",
                claim_text="рабочая память содержит 4 элемента",
                source_ref="b",
                source_group_id="b",
                status=ClaimStatus.ACTIVE,
            )
        )

        store.mark_conflict_candidate(a.claim_id, b.claim_id)
        assert len(store.get_conflict_candidates()) == 1

        store.mark_disputed(a.claim_id, b.claim_id)
        pair = store.get_disputed_pairs()[0]
        assert pair.a.status == ClaimStatus.DISPUTED
        assert pair.b.status == ClaimStatus.DISPUTED

        store.resolve(a.claim_id, b.claim_id, "majority")
        assert store.get(a.claim_id).status == ClaimStatus.ACTIVE
        assert store.get(b.claim_id).status == ClaimStatus.SUPERSEDED
        assert store.get_disputed_pairs() == []
    finally:
        db.close()


def test_resolve_rejects_circular_supersedes(tmp_path):
    db, store = _store(tmp_path)
    try:
        a = store.create(
            Claim(
                concept="x",
                claim_text="x это a",
                source_ref="a",
                source_group_id="a",
                status=ClaimStatus.ACTIVE,
            )
        )
        b = store.create(
            Claim(
                concept="x",
                claim_text="x это b",
                source_ref="b",
                source_group_id="b",
                status=ClaimStatus.ACTIVE,
            )
        )

        store.mark_disputed(a.claim_id, b.claim_id)
        store.resolve(b.claim_id, a.claim_id, "trust")

        try:
            store.resolve(a.claim_id, b.claim_id, "trust")
        except ValueError as exc:
            assert "circular supersedes" in str(exc)
        else:
            raise AssertionError("expected circular supersedes rejection")
    finally:
        db.close()


def test_search_ignores_question_words_in_query(tmp_path):
    db, store = _store(tmp_path)
    try:
        linux = store.create(
            Claim(
                concept="linux",
                claim_text="Linux обычно используют в серверной и инженерной среде",
                source_ref="a",
                source_group_id="a",
                status=ClaimStatus.ACTIVE,
            )
        )
        store.create(
            Claim(
                concept="помнишь",
                claim_text="это шумный хвост от формулировки вопроса",
                source_ref="b",
                source_group_id="b",
                status=ClaimStatus.ACTIVE,
            )
        )

        results = store.search("Что ты помнишь про Linux?", top_n=5)
        assert results
        assert results[0].claim_id == linux.claim_id
        assert all(claim.concept != "помнишь" for claim in results)
    finally:
        db.close()


def test_search_prefers_informative_claim_over_toc_noise(tmp_path):
    db, store = _store(tmp_path)
    try:
        noisy = store.create(
            Claim(
                concept="linux",
                claim_text="starts on page 27",
                source_ref="toc",
                source_group_id="toc",
                status=ClaimStatus.ACTIVE,
                confidence=0.9,
            )
        )
        informative = store.create(
            Claim(
                concept="linux",
                claim_text="Linux обычно выступает основной системой для специалистов по безопасности",
                source_ref="book",
                source_group_id="book",
                status=ClaimStatus.ACTIVE,
                confidence=0.6,
            )
        )

        results = store.search("Linux", top_n=5)
        assert results
        assert results[0].claim_id == informative.claim_id
        assert any(claim.claim_id == noisy.claim_id for claim in results)
    finally:
        db.close()
