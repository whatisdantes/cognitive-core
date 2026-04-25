"""MaterialRegistry — persistent idempotence для ingestion материалов."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from .storage import MemoryDatabase


@dataclass
class MaterialRecord:
    sha256: str
    path: str
    size: int
    mtime: float
    ingest_status: str = "pending"
    chunk_count: int = 0
    claim_count: int = 0
    last_ingested_at: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class MaterialChunkRecord:
    material_sha256: str
    chunk_index: int
    chunk_hash: str
    source_ref: str
    status: str = "pending"
    claim_count: int = 0
    retry_count: int = 0
    processed_ts: Optional[float] = None
    error_message: Optional[str] = None


class MaterialRegistry:
    """SQLite wrapper для materials_registry и material_chunks."""

    def __init__(self, db: MemoryDatabase):
        self._db = db

    def upsert_material(
        self,
        sha256: str,
        path: str,
        size: int,
        mtime: float,
        ingest_status: str = "in_progress",
    ) -> MaterialRecord:
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                INSERT INTO materials_registry
                    (sha256, path, size, mtime, ingest_status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sha256) DO UPDATE SET
                    path = excluded.path,
                    size = excluded.size,
                    mtime = excluded.mtime
                """,
                (sha256, path, size, mtime, ingest_status),
            )
        record = self.get_material(sha256)
        if record is None:
            raise RuntimeError("MaterialRegistry invariant broken: material not found")
        return record

    def get_material(self, sha256: str) -> Optional[MaterialRecord]:
        with self._db._lock:  # noqa: SLF001
            row = self._db._conn.execute(  # noqa: SLF001
                "SELECT * FROM materials_registry WHERE sha256 = ?",
                (sha256,),
            ).fetchone()
        return self._row_to_material(row) if row else None

    def set_material_status(
        self,
        sha256: str,
        status: str,
        *,
        chunk_count: Optional[int] = None,
        claim_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        now = time.time() if status == "done" else None
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                UPDATE materials_registry
                SET ingest_status = ?,
                    chunk_count = COALESCE(?, chunk_count),
                    claim_count = COALESCE(?, claim_count),
                    last_ingested_at = COALESCE(?, last_ingested_at),
                    error_message = ?
                WHERE sha256 = ?
                """,
                (status, chunk_count, claim_count, now, error_message, sha256),
            )

    def add_chunk(
        self,
        material_sha256: str,
        chunk_index: int,
        chunk_hash: str,
        source_ref: str,
        status: str = "pending",
    ) -> MaterialChunkRecord:
        existing_by_hash = self.get_chunk_by_hash(material_sha256, chunk_hash)
        if existing_by_hash is not None:
            return existing_by_hash
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                INSERT OR IGNORE INTO material_chunks
                    (material_sha256, chunk_index, chunk_hash, source_ref, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (material_sha256, chunk_index, chunk_hash, source_ref, status),
            )
        record = self.get_chunk(material_sha256, chunk_index)
        if record is None:
            raise RuntimeError("MaterialRegistry invariant broken: chunk not found")
        return record

    def get_chunk(self, material_sha256: str, chunk_index: int) -> Optional[MaterialChunkRecord]:
        with self._db._lock:  # noqa: SLF001
            row = self._db._conn.execute(  # noqa: SLF001
                """
                SELECT * FROM material_chunks
                WHERE material_sha256 = ? AND chunk_index = ?
                """,
                (material_sha256, chunk_index),
            ).fetchone()
        return self._row_to_chunk(row) if row else None

    def list_incomplete_materials(self) -> List[MaterialRecord]:
        """Вернуть материалы, которые можно resume-ить."""
        with self._db._lock:  # noqa: SLF001
            rows = self._db._conn.execute(  # noqa: SLF001
                """
                SELECT * FROM materials_registry
                WHERE ingest_status IN ('pending', 'in_progress', 'failed')
                ORDER BY mtime ASC, path ASC
                """
            ).fetchall()
        return [self._row_to_material(row) for row in rows]

    def chunks_for_material(self, material_sha256: str) -> List[MaterialChunkRecord]:
        """Вернуть все chunks материала в порядке chunk_index."""
        with self._db._lock:  # noqa: SLF001
            rows = self._db._conn.execute(  # noqa: SLF001
                """
                SELECT * FROM material_chunks
                WHERE material_sha256 = ?
                ORDER BY chunk_index ASC
                """,
                (material_sha256,),
            ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def get_chunk_by_hash(self, material_sha256: str, chunk_hash: str) -> Optional[MaterialChunkRecord]:
        with self._db._lock:  # noqa: SLF001
            row = self._db._conn.execute(  # noqa: SLF001
                """
                SELECT * FROM material_chunks
                WHERE material_sha256 = ? AND chunk_hash = ?
                """,
                (material_sha256, chunk_hash),
            ).fetchone()
        return self._row_to_chunk(row) if row else None

    def pending_or_retryable_chunks(
        self,
        material_sha256: str,
        *,
        max_chunk_retries: int = 3,
    ) -> List[MaterialChunkRecord]:
        with self._db._lock:  # noqa: SLF001
            rows = self._db._conn.execute(  # noqa: SLF001
                """
                SELECT * FROM material_chunks
                WHERE material_sha256 = ?
                  AND (status = 'pending' OR (status = 'failed' AND retry_count < ?))
                ORDER BY chunk_index ASC
                """,
                (material_sha256, max_chunk_retries),
            ).fetchall()
        return [self._row_to_chunk(row) for row in rows]

    def set_chunk_status(
        self,
        material_sha256: str,
        chunk_index: int,
        status: str,
        *,
        claim_count: Optional[int] = None,
        error_message: Optional[str] = None,
        increment_retry: bool = False,
    ) -> None:
        processed_ts = time.time() if status == "done" else None
        retry_delta = 1 if increment_retry else 0
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                UPDATE material_chunks
                SET status = ?,
                    claim_count = COALESCE(?, claim_count),
                    retry_count = retry_count + ?,
                    processed_ts = COALESCE(?, processed_ts),
                    error_message = ?
                WHERE material_sha256 = ? AND chunk_index = ?
                """,
                (
                    status,
                    claim_count,
                    retry_delta,
                    processed_ts,
                    error_message,
                    material_sha256,
                    chunk_index,
                ),
            )

    @staticmethod
    def _row_to_material(row) -> MaterialRecord:
        return MaterialRecord(
            sha256=str(row["sha256"]),
            path=str(row["path"]),
            size=int(row["size"]),
            mtime=float(row["mtime"]),
            ingest_status=str(row["ingest_status"]),
            chunk_count=int(row["chunk_count"]),
            claim_count=int(row["claim_count"]),
            last_ingested_at=row["last_ingested_at"],
            error_message=row["error_message"],
        )

    @staticmethod
    def _row_to_chunk(row) -> MaterialChunkRecord:
        return MaterialChunkRecord(
            material_sha256=str(row["material_sha256"]),
            chunk_index=int(row["chunk_index"]),
            chunk_hash=str(row["chunk_hash"]),
            source_ref=str(row["source_ref"]),
            status=str(row["status"]),
            claim_count=int(row["claim_count"]),
            retry_count=int(row["retry_count"]),
            processed_ts=row["processed_ts"],
            error_message=row["error_message"],
        )
