"""MaterialIngestor — reusable ingestion contract для материалов."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from brain.bridges.llm_bridge import LLMProvider, LLMRequest
from brain.bridges.llm_budget import LLMRateLimiter
from brain.core.contracts import Claim, ClaimStatus, EvidenceKind, Task
from brain.core.hash_utils import sha256_file, sha256_text
from brain.core.text_utils import (
    build_claim_grouping_keys,
    normalize_concept,
    parse_fact_pattern,
)
from brain.logging import _NULL_LOGGER, BrainLogger
from brain.memory.claim_store import ClaimStore
from brain.memory.material_registry import MaterialRegistry
from brain.memory.memory_manager import MemoryManager

from .input_router import InputRouter, InputType

logger = logging.getLogger(__name__)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass
class MaterialIngestResult:
    """Итог ingestion одного материала."""
    material_sha256: str
    path: str
    status: str
    chunks_total: int = 0
    chunks_processed: int = 0
    claim_count: int = 0
    skipped_duplicate: bool = False
    errors: List[str] = field(default_factory=list)


class MaterialIngestor:
    """
    Повторно используемый pipeline ingestion материалов.

    Persistent idempotence живёт в `MaterialRegistry`; in-memory dedup
    `InputRouter` обходится через `force=True`.
    """

    def __init__(
        self,
        memory: MemoryManager,
        input_router: Optional[InputRouter] = None,
        llm_provider: Optional[LLMProvider] = None,
        llm_rate_limiter: Optional[LLMRateLimiter] = None,
        brain_logger: Optional[BrainLogger] = None,
        max_chunk_retries: int = 3,
    ) -> None:
        if memory.material_registry is None or memory.claim_store is None:
            raise ValueError("MaterialIngestor requires sqlite MemoryManager")
        self._memory = memory
        self._registry: MaterialRegistry = memory.material_registry
        self._claims: ClaimStore = memory.claim_store
        self._router = input_router or InputRouter(brain_logger=brain_logger)
        self._llm_provider = llm_provider
        self._llm_rate_limiter = llm_rate_limiter
        self._blog: BrainLogger = brain_logger or _NULL_LOGGER  # type: ignore[assignment]
        self._max_chunk_retries = max_chunk_retries

    def ingest_path(
        self,
        path: str,
        session_id: str = "",
        trace_id: str = "",
    ) -> MaterialIngestResult:
        """Ingest одного файла с persistent chunk idempotence."""
        file_path = Path(path)
        if not file_path.exists() or not file_path.is_file():
            return MaterialIngestResult(
                material_sha256="",
                path=str(file_path),
                status="failed",
                errors=["file_not_found"],
            )

        material_sha = sha256_file(str(file_path), truncate=64)
        stat = file_path.stat()
        existing = self._registry.get_material(material_sha)
        if existing is not None and existing.ingest_status == "done":
            self._blog.info(
                "perception",
                "material_skipped_duplicate",
                session_id=session_id or "material_ingest",
                trace_id=trace_id,
                state={
                    "material_sha256": material_sha,
                    "path": str(file_path),
                    "chunk_count": existing.chunk_count,
                    "claim_count": existing.claim_count,
                },
            )
            return MaterialIngestResult(
                material_sha256=material_sha,
                path=str(file_path),
                status="skipped_duplicate",
                chunks_total=existing.chunk_count,
                claim_count=existing.claim_count,
                skipped_duplicate=True,
            )

        self._registry.upsert_material(
            sha256=material_sha,
            path=str(file_path),
            size=stat.st_size,
            mtime=stat.st_mtime,
            ingest_status="in_progress",
        )
        if existing is not None and existing.ingest_status != "done":
            self._blog.info(
                "perception",
                "material_resumed",
                session_id=session_id or "material_ingest",
                trace_id=trace_id,
                state={
                    "material_sha256": material_sha,
                    "path": str(file_path),
                    "previous_status": existing.ingest_status,
                },
            )

        events = self._router.route(
            str(file_path),
            session_id=session_id,
            trace_id=trace_id,
            force=True,
            input_type=InputType.FILE,
        )
        if not events:
            self._registry.set_material_status(
                material_sha,
                "failed",
                error_message="no_events",
            )
            return MaterialIngestResult(
                material_sha256=material_sha,
                path=str(file_path),
                status="failed",
                errors=["no_events"],
            )

        content_by_index: Dict[int, str] = {}
        for index, event in enumerate(events):
            content = str(event.content or "")
            chunk_hash = sha256_text(content, truncate=64)
            source_ref = f"material:{material_sha}#chunk_{index}"
            chunk = self._registry.add_chunk(
                material_sha,
                index,
                chunk_hash,
                source_ref,
                status="pending",
            )
            content_by_index[chunk.chunk_index] = content

        processed = 0
        claim_count = 0
        errors: List[str] = []
        retryable = self._registry.pending_or_retryable_chunks(
            material_sha,
            max_chunk_retries=self._max_chunk_retries,
        )
        for chunk in retryable:
            content = content_by_index.get(chunk.chunk_index, "")
            if not content:
                continue
            try:
                count = self._process_chunk(
                    material_sha=material_sha,
                    path=str(file_path),
                    chunk_index=chunk.chunk_index,
                    chunk_hash=chunk.chunk_hash,
                    source_ref=chunk.source_ref,
                    content=content,
                    session_id=session_id,
                    trace_id=trace_id,
                )
                self._registry.set_chunk_status(
                    material_sha,
                    chunk.chunk_index,
                    "done",
                    claim_count=count,
                    error_message=None,
                )
                processed += 1
                claim_count += count
            except Exception as exc:
                message = str(exc)
                errors.append(message)
                self._registry.set_chunk_status(
                    material_sha,
                    chunk.chunk_index,
                    "failed",
                    error_message=message,
                    increment_retry=True,
                )

        final_status = self._finalize_material(material_sha)
        material = self._registry.get_material(material_sha)
        total_claims = material.claim_count if material is not None else claim_count
        if final_status == "done":
            self._blog.info(
                "perception",
                "material_ingested",
                session_id=session_id or "material_ingest",
                trace_id=trace_id,
                state={
                    "material_sha256": material_sha,
                    "path": str(file_path),
                    "chunk_count": len(self._registry.chunks_for_material(material_sha)),
                    "claim_count": total_claims,
                },
            )
        return MaterialIngestResult(
            material_sha256=material_sha,
            path=str(file_path),
            status=final_status,
            chunks_total=len(self._registry.chunks_for_material(material_sha)),
            chunks_processed=processed,
            claim_count=total_claims,
            errors=errors,
        )

    def resume_incomplete(self, session_id: str = "") -> List[MaterialIngestResult]:
        """Resume всех incomplete материалов из registry."""
        results: List[MaterialIngestResult] = []
        for material in self._registry.list_incomplete_materials():
            results.append(self.ingest_path(material.path, session_id=session_id))
        return results

    def scan_directory(
        self,
        directory: str,
        session_id: str = "",
        patterns: Optional[Iterable[str]] = None,
    ) -> List[MaterialIngestResult]:
        """Startup scan директории материалов через тот же ingest_path()."""
        base = Path(directory)
        if not base.exists() or not base.is_dir():
            return []
        glob_patterns = list(patterns or ("*.txt", "*.md", "*.pdf", "*.json", "*.csv"))
        paths: List[Path] = []
        for pattern in glob_patterns:
            paths.extend(base.rglob(pattern))
        return [self.ingest_path(str(path), session_id=session_id) for path in sorted(paths)]

    def handle_ingest_file_task(self, task: Task) -> Dict[str, Any]:
        """Scheduler handler для watcher-задач `ingest_file`."""
        path = str(task.payload.get("path", ""))
        result = self.ingest_path(
            path,
            session_id=task.session_id or task.payload.get("session_id", ""),
            trace_id=task.trace_id,
        )
        return asdict(result)

    def _process_chunk(
        self,
        *,
        material_sha: str,
        path: str,
        chunk_index: int,
        chunk_hash: str,
        source_ref: str,
        content: str,
        session_id: str,
        trace_id: str,
    ) -> int:
        regex_claims = self._extract_regex_claims(content)
        claim_count = 0
        for concept, description, span in regex_claims:
            self._store_claim(
                concept=concept,
                description=description,
                confidence=0.60,
                extraction_method="regex",
                material_sha=material_sha,
                source_ref=source_ref,
                chunk_hash=chunk_hash,
                path=path,
                evidence_span=span,
                session_id=session_id,
                trace_id=trace_id,
            )
            claim_count += 1

        llm_claims = self._extract_llm_claims(content, material_sha, chunk_index)
        for concept, description, llm_model in llm_claims:
            self._store_claim(
                concept=concept,
                description=description,
                confidence=0.75,
                extraction_method="llm",
                material_sha=material_sha,
                source_ref=source_ref,
                chunk_hash=chunk_hash,
                path=path,
                evidence_span=None,
                session_id=session_id,
                trace_id=trace_id,
                llm_model=llm_model,
            )
            claim_count += 1
        return claim_count

    def _extract_regex_claims(self, text: str) -> List[Tuple[str, str, Tuple[int, int]]]:
        """Извлечь claims через deterministic regex/path без LLM."""
        claims: List[Tuple[str, str, Tuple[int, int]]] = []
        seen: set[tuple[str, str]] = set()
        for part in _SENTENCE_SPLIT_RE.split(text):
            candidate = part.strip()
            if not candidate:
                continue
            parsed = parse_fact_pattern(candidate)
            if parsed is None:
                continue
            concept, description = parsed
            key = (normalize_concept(concept), description.strip())
            if key in seen:
                continue
            seen.add(key)
            offset = text.find(candidate)
            if offset < 0:
                offset = 0
            claims.append((concept, description, (offset, len(candidate))))
        return claims

    def _extract_llm_claims(
        self,
        text: str,
        material_sha: str,
        chunk_index: int,
    ) -> List[Tuple[str, str, str]]:
        """Опциональное LLM extraction с общим budget."""
        if self._llm_provider is None or not self._llm_provider.is_available():
            return []
        if self._llm_rate_limiter is not None:
            if not self._llm_rate_limiter.allow("ingest_extract"):
                return []
        request = LLMRequest(
            prompt=(
                "Извлеки факты из текста. Верни по одному факту на строку "
                "в формате 'concept: description'.\n\n"
                f"{text[:3000]}"
            ),
            max_tokens=512,
            temperature=0.0,
            metadata={
                "purpose": "ingest_extract",
                "material_sha256": material_sha,
                "chunk_index": chunk_index,
            },
        )
        try:
            response = self._llm_provider.complete(request)
        except Exception as exc:
            if self._llm_rate_limiter is not None:
                self._llm_rate_limiter.record("ingest_extract")
            logger.warning("[MaterialIngestor] LLM extraction failed: %s", exc)
            self._blog.warn(
                "perception",
                "material_llm_extract_failed",
                state={
                    "material_sha256": material_sha,
                    "chunk_index": chunk_index,
                    "error": str(exc),
                },
            )
            return []
        if self._llm_rate_limiter is not None:
            self._llm_rate_limiter.record("ingest_extract")
        claims: List[Tuple[str, str, str]] = []
        seen: set[tuple[str, str]] = set()
        for line in response.text.splitlines():
            parsed = parse_fact_pattern(line.strip())
            if parsed is not None:
                concept, description = parsed
                key = (normalize_concept(concept), description.strip())
                if key in seen:
                    continue
                seen.add(key)
                claims.append((concept, description, response.model))
        return claims

    def _store_claim(
        self,
        *,
        concept: str,
        description: str,
        confidence: float,
        extraction_method: str,
        material_sha: str,
        source_ref: str,
        chunk_hash: str,
        path: str,
        evidence_span: Optional[Tuple[int, int]],
        session_id: str,
        trace_id: str,
        llm_model: str = "",
    ) -> Claim:
        concept_norm = normalize_concept(concept)
        family_key, stance_key = build_claim_grouping_keys(concept_norm, description)
        metadata = {
            "source": "material_ingestor",
            "extraction_method": extraction_method,
            "chunk_hash": chunk_hash,
            "material_path": path,
        }
        if llm_model:
            metadata["llm_model"] = llm_model
        claim = self._claims.create(
            Claim(
                concept=concept_norm,
                claim_text=description[:500],
                claim_family_key=family_key,
                stance_key=stance_key,
                source_ref=source_ref,
                material_sha256=material_sha,
                source_group_id=material_sha,
                evidence_span=evidence_span,
                evidence_kind=EvidenceKind.TIMELESS,
                confidence=confidence,
                status=ClaimStatus.ACTIVE,
                metadata=metadata,
            )
        )
        if self._memory.conflict_guard is not None:
            self._memory.conflict_guard.check_new_claim(
                claim,
                session_id=session_id or "material_ingest",
                trace_id=trace_id,
            )
        return claim

    def _finalize_material(self, material_sha: str) -> str:
        chunks = self._registry.chunks_for_material(material_sha)
        done_count = sum(1 for chunk in chunks if chunk.status == "done")
        claim_count = sum(chunk.claim_count for chunk in chunks if chunk.status == "done")
        retryable = self._registry.pending_or_retryable_chunks(
            material_sha,
            max_chunk_retries=self._max_chunk_retries,
        )
        failed = [chunk for chunk in chunks if chunk.status == "failed"]
        if done_count == len(chunks) and chunks:
            self._registry.set_material_status(
                material_sha,
                "done",
                chunk_count=len(chunks),
                claim_count=claim_count,
                error_message=None,
            )
            return "done"
        if failed and not retryable:
            self._registry.set_material_status(
                material_sha,
                "failed",
                chunk_count=len(chunks),
                claim_count=claim_count,
                error_message="non_retryable_failed_chunks",
            )
            return "failed"
        self._registry.set_material_status(
            material_sha,
            "in_progress",
            chunk_count=len(chunks),
            claim_count=claim_count,
            error_message=None,
        )
        return "in_progress"
