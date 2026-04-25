from brain.core.contracts import ClaimStatus
from brain.logging import BrainLogger
from brain.memory import MemoryManager


def test_memory_manager_stores_claims_and_derives_semantic_description(tmp_path):
    mm = MemoryManager(data_dir=str(tmp_path), auto_consolidate=False)
    try:
        mm.store_fact("Python", "язык программирования", source_ref="book#p1")
        mm.store_fact("Python", "используется для автоматизации", source_ref="book#p2")

        assert mm.claim_store is not None
        claims = mm.claim_store.active_claims("python")
        assert len(claims) == 2
        assert all(c.status == ClaimStatus.ACTIVE for c in claims)

        node = mm.semantic.get_fact("python")
        assert node is not None
        assert "язык программирования" in node.description
        assert "используется для автоматизации" in node.description
    finally:
        mm.stop(save=False)


def test_disputed_claims_do_not_leak_into_semantic_description(tmp_path):
    mm = MemoryManager(data_dir=str(tmp_path), auto_consolidate=False)
    try:
        mm.store_fact(
            "Рабочая память",
            "рабочая память содержит 7 элементов",
            source_ref="source-a#p1",
        )
        mm.store_fact(
            "Рабочая память",
            "рабочая память содержит 4 элемента",
            source_ref="source-b#p1",
        )

        assert mm.conflict_guard is not None
        mm.conflict_guard.reconcile_candidates(current_tick=1)

        node = mm.semantic.get_fact("рабочая память")
        assert node is not None
        assert "7 элементов" not in node.description
        assert "4 элемента" not in node.description

        result = mm.retrieve("рабочая память", memory_types=["claims"])
        assert len(result.answerable_claims) == 2
        assert {claim.status for claim in result.answerable_claims} == {
            ClaimStatus.DISPUTED,
        }
    finally:
        mm.stop(save=False)


def test_claim_created_event_has_non_empty_session_id(tmp_path):
    blog = BrainLogger(log_dir=str(tmp_path / "logs"), min_level="DEBUG")
    mm = MemoryManager(
        data_dir=str(tmp_path / "memory"),
        auto_consolidate=False,
        brain_logger=blog,
    )
    try:
        mm.store_fact("Python", "язык программирования", source_ref="book#p1")
        blog.flush()
        text = (tmp_path / "logs" / "memory.jsonl").read_text(encoding="utf-8")
        assert '"event": "claim_created"' in text
        assert '"session_id": "memory_direct"' in text
    finally:
        mm.stop(save=False)
        blog.close()
