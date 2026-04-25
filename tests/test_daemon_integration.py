from __future__ import annotations

import gc
import threading
import tracemalloc
from pathlib import Path

from brain.bridges import LLMRateLimiter
from brain.cli import run_daemon
from brain.core.contracts import (
    Claim,
    ClaimRef,
    ClaimStatus,
    CognitiveResult,
    DaemonConfig,
    TraceChain,
)
from brain.core.scheduler import Scheduler
from brain.logging import BrainLogger
from brain.memory import ClaimStore, ConflictGuard, MaterialRegistry, MemoryManager
from brain.motivation import IdleDispatcher
from brain.output.dialogue_responder import OutputPipeline
from brain.perception import MaterialIngestor

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "conflicts"


def test_public_autonomy_names_are_exported() -> None:
    assert ClaimStatus.__name__ == "ClaimStatus"
    assert ClaimStore.__name__ == "ClaimStore"
    assert MaterialRegistry.__name__ == "MaterialRegistry"
    assert MaterialIngestor.__name__ == "MaterialIngestor"
    assert ConflictGuard.__name__ == "ConflictGuard"
    assert IdleDispatcher.__name__ == "IdleDispatcher"
    assert LLMRateLimiter.__name__ == "LLMRateLimiter"


def test_daemon_long_running_smoke_has_bounded_resources(tmp_path, monkeypatch) -> None:
    """Smoke-прогон daemon loop без очевидного роста памяти и висящих потоков."""
    monkeypatch.setattr(
        Scheduler,
        "get_tick_interval",
        lambda self, resource_state=None: 0.0,
    )
    before_threads = {
        thread.ident
        for thread in threading.enumerate()
        if thread.ident is not None
    }

    tracemalloc.start()
    try:
        exit_code = run_daemon(
            str(tmp_path / "daemon-memory"),
            log_dir=str(tmp_path / "logs"),
            log_level="ERROR",
            config=DaemonConfig(
                reconcile_every_ticks=2,
                replay_every_ticks=7,
                consolidate_every_ticks=11,
                self_reflect_every_ticks=3,
                llm_calls_per_hour=0,
            ),
            max_ticks=120,
        )
        gc.collect()
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    leaked_threads = [
        thread.name
        for thread in threading.enumerate()
        if thread.ident not in before_threads and thread.is_alive()
    ]

    assert exit_code == 0
    assert "ResourceMonitor" not in leaked_threads
    assert current_bytes < 25 * 1024 * 1024
    assert peak_bytes < 80 * 1024 * 1024


def _memory(tmp_path: Path, blog: BrainLogger) -> MemoryManager:
    data_dir = tmp_path / "memory"
    data_dir.mkdir()
    return MemoryManager(
        data_dir=str(data_dir),
        auto_consolidate=False,
        storage_backend="sqlite",
        brain_logger=blog,
    )


def _ingest(memory: MemoryManager, paths: list[Path], blog: BrainLogger) -> None:
    ingestor = MaterialIngestor(memory, brain_logger=blog)
    for path in paths:
        result = ingestor.ingest_path(str(path), session_id="daemon-test")
        assert result.status == "done"
        assert result.claim_count >= 1


def _claim_refs(claims: list[Claim]) -> list[ClaimRef]:
    return [ClaimRef.from_claim(claim) for claim in claims]


def _result(response: str, claims: list[ClaimRef], goal: str) -> CognitiveResult:
    return CognitiveResult(
        action="respond_direct",
        response=response,
        confidence=0.86,
        trace=TraceChain(trace_id="trace_daemon_integration"),
        goal=goal,
        trace_id="trace_daemon_integration",
        session_id="daemon-test",
        cycle_id="cycle-daemon-test",
        memory_refs=claims,
        metadata={"language": "ru", "goal_type": "answer_question"},
    )


def test_conflict_fixtures_resolve_by_majority_and_output_winner(tmp_path):
    blog = BrainLogger(log_dir=str(tmp_path / "logs"), min_level="DEBUG")
    memory = _memory(tmp_path, blog)
    paths = [
        FIXTURES / "high_trust" / "topology.md",
        FIXTURES / "mid_trust_a" / "cognitive_basics.md",
        FIXTURES / "mid_trust_b" / "neuro_update.md",
        FIXTURES / "low_trust" / "blog_post.md",
    ]
    try:
        _ingest(memory, paths, blog)
        store = memory.claim_store
        assert store is not None

        claims = store.find_by_concept("рабочая память")
        assert len(claims) == 3
        by_name = {
            Path(claim.metadata["material_path"]).name: claim
            for claim in claims
        }
        a_first = by_name["topology.md"]
        a_second = by_name["cognitive_basics.md"]
        b_claim = by_name["neuro_update.md"]

        assert a_first.claim_family_key == a_second.claim_family_key == b_claim.claim_family_key
        assert a_first.stance_key == a_second.stance_key
        assert b_claim.stance_key != a_first.stance_key
        assert len({claim.source_group_id for claim in claims}) == 3
        assert store.get_conflict_candidates()

        results = []
        for tick in range(1, 21):
            results.extend(
                memory.conflict_guard.reconcile_disputed(  # type: ignore[union-attr]
                    current_tick=tick,
                    session_id="daemon-test",
                    trace_id=f"daemon-tick-{tick}",
                )
            )
            if any(result.event == "claim_resolved_by_majority" for result in results):
                break

        blog.flush()
        memory_log = (tmp_path / "logs" / "memory.jsonl").read_text(encoding="utf-8")

        assert any(result.event == "claim_disputed" for result in results)
        assert any(result.event == "claim_resolved_by_majority" for result in results)
        assert '"event": "claim_conflict_candidate"' in memory_log
        assert '"event": "claim_disputed"' in memory_log
        assert '"event": "claim_resolved_by_majority"' in memory_log

        assert store.get(b_claim.claim_id).status == ClaimStatus.SUPERSEDED
        active_claims = store.active_claims("рабочая память")
        assert {claim.stance_key for claim in active_claims} == {a_first.stance_key}

        winner_text = active_claims[0].claim_text
        output = OutputPipeline(source_memory=memory.source).process(
            _result(
                response=winner_text,
                claims=_claim_refs(active_claims),
                goal="Что известно о рабочей памяти?",
            )
        )

        assert "7" in output.text
        assert "4±1" not in output.text
        assert output.metadata.get("decision", {}).get("reason") != "dispute"
    finally:
        blog.close()
        memory.stop(save=False)


def test_unresolved_conflict_times_out_and_output_mentions_both_sources(tmp_path):
    blog = BrainLogger(log_dir=str(tmp_path / "logs"), min_level="DEBUG")
    memory = _memory(tmp_path, blog)
    paths = [
        FIXTURES / "unresolved" / "source_a.md",
        FIXTURES / "unresolved" / "source_b.md",
    ]
    try:
        _ingest(memory, paths, blog)
        store = memory.claim_store
        assert store is not None

        first = memory.conflict_guard.reconcile_disputed(  # type: ignore[union-attr]
            current_tick=1,
            session_id="daemon-test",
            trace_id="daemon-tick-1",
        )
        assert any(result.event == "claim_disputed" for result in first)
        assert any(result.action == "verification_goal" for result in first)

        second = memory.conflict_guard.reconcile_disputed(  # type: ignore[union-attr]
            current_tick=60,
            session_id="daemon-test",
            trace_id="daemon-tick-60",
        )
        blog.flush()
        memory_log = (tmp_path / "logs" / "memory.jsonl").read_text(encoding="utf-8")

        assert any(result.event == "claim_resolution_timed_out" for result in second)
        assert '"event": "claim_resolution_timed_out"' in memory_log

        disputed = store.find_by_concept(
            "тестовая система",
            statuses=[ClaimStatus.DISPUTED],
        )
        assert len(disputed) == 2
        assert not store.find_by_concept(
            "тестовая система",
            statuses=[ClaimStatus.RETRACTED, ClaimStatus.SUPERSEDED],
        )

        output = OutputPipeline(source_memory=memory.source).process(
            _result(
                response="Эта строка не должна попасть в hedged response.",
                claims=_claim_refs(disputed),
                goal="Что известно о тестовой системе?",
            )
        )

        assert output.metadata["decision"]["reason"] == "dispute"
        assert "работает стабильно" in output.text
        assert "не работает стабильно" in output.text
        assert disputed[0].source_ref in output.text
        assert disputed[1].source_ref in output.text
    finally:
        blog.close()
        memory.stop(save=False)
