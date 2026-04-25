from __future__ import annotations

from pathlib import Path

from brain.cognition.retrieval_adapter import KeywordRetrievalBackend
from brain.core.contracts import Claim, ClaimRef, ClaimStatus, CognitiveResult, TraceChain
from brain.memory.memory_manager import MemoryManager
from brain.output.dialogue_responder import OutputPipeline


class FakeSourceMemory:
    def __init__(self, trust_by_group: dict[str, float]):
        self.trust_by_group = trust_by_group
        self.calls: list[str] = []

    def get_trust(self, source_group_id: str) -> float:
        self.calls.append(source_group_id)
        return self.trust_by_group[source_group_id]


def _result_with_claims(claims: list[ClaimRef], response: str = "Обычный ответ.") -> CognitiveResult:
    return CognitiveResult(
        action="respond_direct",
        response=response,
        confidence=0.84,
        trace=TraceChain(trace_id="trace_dispute"),
        goal="Что известно о рабочей памяти?",
        trace_id="trace_dispute",
        session_id="sess_dispute",
        cycle_id="cycle_dispute",
        memory_refs=claims,
        metadata={"language": "ru", "goal_type": "answer_question"},
    )


def test_disputed_claims_render_hedged_text_with_source_group_trust() -> None:
    source_memory = FakeSourceMemory({"source-a": 0.91, "source-b": 0.42})
    claims = [
        ClaimRef(
            claim_id="claim_a",
            concept="рабочая память",
            claim_text="Рабочая память хранит данные около 20 секунд.",
            source_ref="source-a#p1",
            source_group_id="source-a",
            confidence=0.82,
            status=ClaimStatus.DISPUTED,
            conflict_refs=["claim_b"],
        ),
        ClaimRef(
            claim_id="claim_b",
            concept="рабочая память",
            claim_text="Рабочая память хранит данные несколько минут.",
            source_ref="source-b#p7",
            source_group_id="source-b",
            confidence=0.77,
            status=ClaimStatus.DISPUTED,
            conflict_refs=["claim_a"],
        ),
    ]

    output = OutputPipeline(source_memory=source_memory).process(
        _result_with_claims(claims, response="Этого текста не должно быть в ответе.")
    )

    assert "неразрешённый конфликт" in output.text
    assert "Рабочая память хранит данные около 20 секунд." in output.text
    assert "Рабочая память хранит данные несколько минут." in output.text
    assert "source_ref=source-a#p1" in output.text
    assert "source_ref=source-b#p7" in output.text
    assert "trust=0.91" in output.text
    assert "trust=0.42" in output.text
    assert "Этого текста не должно быть" not in output.text
    assert source_memory.calls == ["source-a", "source-b"]
    assert output.metadata["decision"]["reason"] == "dispute"
    assert "respond_hedged_due_to_dispute" in output.metadata["validation_reasons"]


def test_non_disputed_claims_keep_ordinary_response() -> None:
    claims = [
        ClaimRef(
            claim_id="claim_active",
            concept="рабочая память",
            claim_text="Рабочая память удерживает текущий контекст.",
            source_ref="source-a#p1",
            source_group_id="source-a",
            confidence=0.86,
            status=ClaimStatus.ACTIVE,
            trust=0.9,
        ),
    ]

    output = OutputPipeline().process(_result_with_claims(claims, response="Обычный ответ."))

    assert output.text == "Обычный ответ."
    assert "неразрешённый конфликт" not in output.text
    assert output.metadata.get("decision", {}).get("reason") != "dispute"


def test_claim_aware_retrieval_exposes_disputed_claim_refs(tmp_path: Path) -> None:
    memory = MemoryManager(
        data_dir=str(tmp_path),
        storage_backend="sqlite",
        auto_consolidate=False,
    )
    try:
        rec_a = memory.source.register("source-a")
        rec_b = memory.source.register("source-b")
        rec_a.trust_score = 0.88
        rec_b.trust_score = 0.61

        claim_a = memory.claim_store.create(  # type: ignore[union-attr]
            Claim(
                concept="рабочая память",
                claim_text="Рабочая память длится 20 секунд.",
                source_ref="source-a#p1",
                source_group_id="source-a",
                confidence=0.8,
                status=ClaimStatus.ACTIVE,
            )
        )
        claim_b = memory.claim_store.create(  # type: ignore[union-attr]
            Claim(
                concept="рабочая память",
                claim_text="Рабочая память длится несколько минут.",
                source_ref="source-b#p2",
                source_group_id="source-b",
                confidence=0.7,
                status=ClaimStatus.ACTIVE,
            )
        )
        memory.claim_store.mark_disputed(claim_a.claim_id, claim_b.claim_id)  # type: ignore[union-attr]

        result = memory.retrieve("рабочая память", top_n=5)
        assert {claim.claim_id for claim in result.answerable_claims} == {
            claim_a.claim_id,
            claim_b.claim_id,
        }
        assert result.active_claims == []

        evidence = KeywordRetrievalBackend(memory).search("рабочая память", top_n=5)
        claim_evidence = [ev for ev in evidence if ev.memory_type == "claim"]

        assert len(claim_evidence) == 2
        assert {ev.metadata["claim_status"] for ev in claim_evidence} == {"disputed"}
        assert {ev.metadata["source_group_id"] for ev in claim_evidence} == {"source-a", "source-b"}
        assert {round(ev.trust, 2) for ev in claim_evidence} == {0.88, 0.61}
        assert all(ev.metadata["claim_ref"]["conflict_refs"] for ev in claim_evidence)
    finally:
        memory.stop(save=False)


def test_legacy_semantic_fallback_still_returns_evidence(tmp_path: Path) -> None:
    memory = MemoryManager(
        data_dir=str(tmp_path),
        storage_backend="json",
        auto_consolidate=False,
    )
    try:
        memory.store_fact(
            concept="нейрон",
            description="клетка нервной системы",
            source_ref="legacy-source",
        )

        evidence = KeywordRetrievalBackend(memory).search("нейрон", top_n=5)

        assert any(ev.memory_type == "semantic" for ev in evidence)
        assert not any(ev.memory_type == "claim" for ev in evidence)
    finally:
        memory.stop(save=False)
