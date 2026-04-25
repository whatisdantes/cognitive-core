from pathlib import Path

from brain.bridges.llm_bridge import LLMRequest, LLMResponse
from brain.bridges.llm_budget import LLMRateLimitConfig, LLMRateLimiter
from brain.core.events import EventFactory
from brain.logging import BrainLogger
from brain.memory import MemoryManager
from brain.perception.input_router import InputType
from brain.perception.material_ingestor import MaterialIngestor


class RecordingProvider:
    def __init__(self, text: str, *, model: str = "mock-ingest") -> None:
        self.text = text
        self.model = model
        self.calls = 0

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text=self.text,
            model=self.model,
            provider="recording",
            tokens_used=len(request.prompt.split()),
        )

    def is_available(self) -> bool:
        return True

    @property
    def provider_name(self) -> str:
        return "recording"


class FailingProvider(RecordingProvider):
    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        raise RuntimeError("llm boom")


class RecordingRouter:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def route(
        self,
        source,
        session_id="",
        trace_id="",
        force=False,
        input_type=InputType.AUTO,
    ):
        self.calls.append(
            {
                "source": source,
                "session_id": session_id,
                "trace_id": trace_id,
                "force": force,
                "input_type": input_type,
            }
        )
        return list(self.events)


class CrashAfterClaimIngestor(MaterialIngestor):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.crashed = False

    def _process_chunk(self, **kwargs) -> int:
        count = super()._process_chunk(**kwargs)
        if not self.crashed:
            self.crashed = True
            raise RuntimeError("boom_after_claim")
        return count


def _memory(tmp_path: Path) -> MemoryManager:
    data_dir = tmp_path / "memory"
    data_dir.mkdir(exist_ok=True)
    return MemoryManager(
        data_dir=str(data_dir),
        auto_consolidate=False,
        storage_backend="sqlite",
    )


def test_ingest_path_regex_only_is_idempotent(tmp_path):
    material = tmp_path / "materials" / "facts.md"
    material.parent.mkdir()
    material.write_text(
        "Python: язык программирования общего назначения.\n"
        "Нейрон: клетка нервной системы.",
        encoding="utf-8",
    )
    memory = _memory(tmp_path)
    try:
        ingestor = MaterialIngestor(memory)

        first = ingestor.ingest_path(str(material), session_id="test-session")
        assert first.status == "done"
        assert first.claim_count == 2
        assert memory.claim_store.count() == 2
        chunks = memory.material_registry.chunks_for_material(first.material_sha256)
        assert chunks
        assert all(chunk.status == "done" for chunk in chunks)

        second = ingestor.ingest_path(str(material), session_id="test-session")
        assert second.status == "skipped_duplicate"
        assert second.skipped_duplicate is True
        assert memory.claim_store.count() == 2

        claim = memory.claim_store.find_by_concept("python")[0]
        assert claim.confidence == 0.60
        assert claim.source_group_id == first.material_sha256
        assert claim.metadata["extraction_method"] == "regex"
        assert claim.metadata["chunk_hash"]
    finally:
        memory.stop(save=False)


def test_ingested_material_is_idempotent_after_memory_restart(tmp_path):
    material = tmp_path / "materials" / "restart.md"
    material.parent.mkdir()
    material.write_text("Мозжечок: структура мозга для координации.", encoding="utf-8")

    memory = _memory(tmp_path)
    try:
        first = MaterialIngestor(memory).ingest_path(str(material), session_id="test-session")
        assert first.status == "done"
        assert first.claim_count == 1
        assert memory.claim_store.count() == 1
    finally:
        memory.stop(save=False)

    restarted = _memory(tmp_path)
    try:
        second = MaterialIngestor(restarted).ingest_path(str(material), session_id="test-session")
        assert second.status == "skipped_duplicate"
        assert second.skipped_duplicate is True
        assert restarted.claim_store.count() == 1
    finally:
        restarted.stop(save=False)


def test_ingest_path_forces_router_dedup_bypass(tmp_path):
    material = tmp_path / "materials" / "force.md"
    material.parent.mkdir()
    material.write_text("Кора: внешний слой мозга.", encoding="utf-8")
    router = RecordingRouter([
        EventFactory.percept(
            source=str(material),
            content="Кора: внешний слой мозга.",
            modality="text",
            quality=1.0,
        )
    ])
    memory = _memory(tmp_path)
    try:
        result = MaterialIngestor(memory, input_router=router).ingest_path(
            str(material),
            session_id="test-session",
            trace_id="trace-force",
        )

        assert result.status == "done"
        assert router.calls == [
            {
                "source": str(material),
                "session_id": "test-session",
                "trace_id": "trace-force",
                "force": True,
                "input_type": InputType.FILE,
            }
        ]
    finally:
        memory.stop(save=False)


def test_ingest_path_allows_double_dot_filename(tmp_path):
    material = tmp_path / "materials" / "book..md"
    material.parent.mkdir()
    material.write_text("Гиппокамп: структура мозга для памяти.", encoding="utf-8")
    memory = _memory(tmp_path)
    try:
        result = MaterialIngestor(memory).ingest_path(str(material), session_id="test-session")

        assert result.status == "done"
        assert result.claim_count == 1
        assert memory.claim_store.count() == 1
    finally:
        memory.stop(save=False)


def test_duplicate_chunk_hash_is_processed_once(tmp_path):
    material = tmp_path / "materials" / "duplicate_chunks.md"
    material.parent.mkdir()
    material.write_text("Гиппокамп: структура мозга для памяти.", encoding="utf-8")
    duplicate_content = "Гиппокамп: структура мозга для памяти."
    router = RecordingRouter([
        EventFactory.percept(
            source=str(material),
            content=duplicate_content,
            modality="text",
            quality=1.0,
        ),
        EventFactory.percept(
            source=str(material),
            content=duplicate_content,
            modality="text",
            quality=1.0,
        ),
    ])
    memory = _memory(tmp_path)
    try:
        result = MaterialIngestor(memory, input_router=router).ingest_path(
            str(material),
            session_id="test-session",
        )
        chunks = memory.material_registry.chunks_for_material(result.material_sha256)

        assert result.status == "done"
        assert result.chunks_total == 1
        assert result.claim_count == 1
        assert len(chunks) == 1
        assert chunks[0].claim_count == 1
        assert memory.claim_store.count() == 1
    finally:
        memory.stop(save=False)


def test_resume_failed_chunk_retries_without_duplicate_claims(tmp_path):
    material = tmp_path / "materials" / "resume.md"
    material.parent.mkdir()
    material.write_text("Гиппокамп: структура мозга для памяти.", encoding="utf-8")
    memory = _memory(tmp_path)
    try:
        crashing = CrashAfterClaimIngestor(memory)
        failed = crashing.ingest_path(str(material), session_id="test-session")
        assert failed.status == "in_progress"
        assert failed.errors == ["boom_after_claim"]
        assert memory.claim_store.count() == 1

        resumed = MaterialIngestor(memory).resume_incomplete(session_id="test-session")
        assert len(resumed) == 1
        assert resumed[0].status == "done"
        assert resumed[0].claim_count == 1
        assert memory.claim_store.count() == 1
        chunks = memory.material_registry.chunks_for_material(resumed[0].material_sha256)
        assert all(chunk.status == "done" for chunk in chunks)
    finally:
        memory.stop(save=False)


def test_llm_extraction_respects_budget_and_regex_still_runs(tmp_path):
    material = tmp_path / "materials" / "budget.md"
    material.parent.mkdir()
    material.write_text("Рефлекс: автоматическая реакция организма.", encoding="utf-8")
    memory = _memory(tmp_path)
    provider = RecordingProvider("LLMConcept: extracted from model")
    limiter = LLMRateLimiter(LLMRateLimitConfig(llm_calls_per_hour=0))
    try:
        result = MaterialIngestor(
            memory,
            llm_provider=provider,
            llm_rate_limiter=limiter,
        ).ingest_path(str(material), session_id="test-session")

        assert result.status == "done"
        assert provider.calls == 0
        assert memory.claim_store.count() == 1
        claim = memory.claim_store.find_by_concept("рефлекс")[0]
        assert claim.metadata["extraction_method"] == "regex"
    finally:
        memory.stop(save=False)


def test_llm_extraction_records_model_metadata(tmp_path):
    material = tmp_path / "materials" / "llm.md"
    material.parent.mkdir()
    material.write_text("Кора: внешний слой мозга.", encoding="utf-8")
    memory = _memory(tmp_path)
    provider = RecordingProvider("LLMFact: extracted from model", model="mock-v2")
    limiter = LLMRateLimiter(LLMRateLimitConfig(llm_calls_per_hour=3))
    try:
        result = MaterialIngestor(
            memory,
            llm_provider=provider,
            llm_rate_limiter=limiter,
        ).ingest_path(str(material), session_id="test-session")

        assert result.status == "done"
        assert provider.calls == 1
        assert limiter.usage_by_purpose()["ingest_extract"] == 1
        llm_claim = memory.claim_store.find_by_concept("llmfact")[0]
        assert llm_claim.confidence == 0.75
        assert llm_claim.metadata["extraction_method"] == "llm"
        assert llm_claim.metadata["llm_model"] == "mock-v2"
        assert llm_claim.source_group_id == result.material_sha256
    finally:
        memory.stop(save=False)


def test_llm_failure_warns_and_finishes_regex_chunk(tmp_path):
    material = tmp_path / "materials" / "failure.md"
    material.parent.mkdir()
    material.write_text("Синапс: контакт между нейронами.", encoding="utf-8")
    memory = _memory(tmp_path)
    blog = BrainLogger(log_dir=str(tmp_path / "logs"))
    provider = FailingProvider("")
    try:
        result = MaterialIngestor(
            memory,
            llm_provider=provider,
            brain_logger=blog,
        ).ingest_path(str(material), session_id="test-session")

        assert result.status == "done"
        assert provider.calls == 1
        assert memory.claim_store.count() == 1
        perception_log = tmp_path / "logs" / "perception.jsonl"
        assert "material_llm_extract_failed" in perception_log.read_text(encoding="utf-8")
    finally:
        blog.close()
        memory.stop(save=False)


def test_llm_failure_consumes_budget_and_limits_followup_chunks(tmp_path):
    material = tmp_path / "materials" / "limited_failure.md"
    material.parent.mkdir()
    material.write_text("stub", encoding="utf-8")
    router = RecordingRouter([
        EventFactory.percept(
            source=str(material),
            content="Axon: long neuron projection.",
            modality="text",
            quality=1.0,
        ),
        EventFactory.percept(
            source=str(material),
            content="Dendrite: branching neuron projection.",
            modality="text",
            quality=1.0,
        ),
    ])
    provider = FailingProvider("")
    limiter = LLMRateLimiter(LLMRateLimitConfig(llm_calls_per_hour=1))
    memory = _memory(tmp_path)
    try:
        result = MaterialIngestor(
            memory,
            input_router=router,
            llm_provider=provider,
            llm_rate_limiter=limiter,
        ).ingest_path(str(material), session_id="test-session")

        assert result.status == "done"
        assert provider.calls == 1
        assert limiter.remaining() == 0
        assert limiter.usage_by_purpose()["ingest_extract"] == 1
        assert memory.claim_store.count() == 2
    finally:
        memory.stop(save=False)


def test_scan_directory_uses_ingest_path_contract(tmp_path):
    materials = tmp_path / "materials"
    materials.mkdir()
    (materials / "a.md").write_text("Аксон: длинный отросток нейрона.", encoding="utf-8")
    (materials / "b.txt").write_text("Дендрит: ветвистый отросток нейрона.", encoding="utf-8")
    memory = _memory(tmp_path)
    try:
        results = MaterialIngestor(memory).scan_directory(str(materials), session_id="test-session")

        assert [Path(result.path).name for result in results] == ["a.md", "b.txt"]
        assert all(result.status == "done" for result in results)
        assert memory.claim_store.count() == 2
    finally:
        memory.stop(save=False)


def test_scan_directory_includes_pdf_by_default(tmp_path):
    materials = tmp_path / "materials"
    materials.mkdir()
    material = materials / "manual.pdf"
    material.write_bytes(b"%PDF-1.4\n")
    router = RecordingRouter([
        EventFactory.percept(
            source=str(material),
            content="PdfFact: extracted from pdf.",
            modality="text",
            quality=1.0,
        )
    ])
    memory = _memory(tmp_path)
    try:
        results = MaterialIngestor(memory, input_router=router).scan_directory(
            str(materials),
            session_id="test-session",
        )

        assert [Path(result.path).name for result in results] == ["manual.pdf"]
        assert results[0].status == "done"
        assert router.calls[0]["source"] == str(material)
        assert router.calls[0]["input_type"] == InputType.FILE
        assert memory.claim_store.find_by_concept("pdffact")
    finally:
        memory.stop(save=False)
