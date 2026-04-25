"""ClaimStore — SQLite-хранилище claim-based memory."""

from __future__ import annotations

import json
import time
import uuid
from typing import List, Optional

from brain.core.contracts import Claim, ClaimStatus, ConflictPair, ConflictStatus, EvidenceKind
from brain.core.text_utils import (
    build_claim_grouping_keys,
    estimate_text_signal,
    normalize_concept,
    search_terms,
)

from .storage import MemoryDatabase


class ClaimStore:
    """CRUD и lifecycle-операции для claims и claim_conflicts."""

    def __init__(self, db: MemoryDatabase):
        self._db = db

    def create(self, claim: Claim) -> Claim:
        """Создать claim идемпотентно по `(concept, claim_text, source_ref)`."""
        now = time.time()
        concept = normalize_concept(claim.concept)
        family_key = claim.claim_family_key
        stance_key = claim.stance_key
        if not family_key or not stance_key:
            family_key, stance_key = build_claim_grouping_keys(concept, claim.claim_text)
        claim_id = claim.claim_id or uuid.uuid4().hex[:16]
        source_group_id = claim.source_group_id or claim.material_sha256 or claim.source_ref or "unknown"
        created_ts = claim.created_ts or now
        updated_ts = claim.updated_ts or now

        with self._db._lock:  # noqa: SLF001 - хранилища памяти используют общий DB lock
            existing = self._db._conn.execute(  # noqa: SLF001
                """
                SELECT claim_id FROM claims
                WHERE concept = ? AND claim_text = ? AND source_ref = ?
                """,
                (concept, claim.claim_text, claim.source_ref),
            ).fetchone()
            if existing:
                found = self.get(str(existing["claim_id"]))
                if found is None:
                    raise RuntimeError("ClaimStore invariant broken: existing claim not found")
                return found

            offset = length = None
            if claim.evidence_span is not None:
                offset, length = claim.evidence_span

            self._db._conn.execute(  # noqa: SLF001
                """
                INSERT INTO claims (
                    claim_id, concept, claim_text, claim_family_key, stance_key,
                    source_ref, material_sha256, source_group_id,
                    evidence_span_offset, evidence_span_length, evidence_kind,
                    confidence, status, supersedes, superseded_by,
                    created_ts, updated_ts, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    concept,
                    claim.claim_text[:500],
                    family_key,
                    stance_key,
                    claim.source_ref,
                    claim.material_sha256,
                    source_group_id,
                    offset,
                    length,
                    claim.evidence_kind.value,
                    float(claim.confidence),
                    claim.status.value,
                    claim.supersedes,
                    claim.superseded_by,
                    created_ts,
                    updated_ts,
                    json.dumps(claim.metadata, ensure_ascii=False),
                ),
            )

        created = self.get(claim_id)
        if created is None:
            raise RuntimeError("ClaimStore invariant broken: inserted claim not found")
        return created

    def get(self, claim_id: str) -> Optional[Claim]:
        with self._db._lock:  # noqa: SLF001
            row = self._db._conn.execute(  # noqa: SLF001
                "SELECT * FROM claims WHERE claim_id = ?",
                (claim_id,),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_claim(row)

    def find_by_concept(
        self,
        concept: str,
        status: Optional[ClaimStatus] = None,
        statuses: Optional[List[ClaimStatus]] = None,
    ) -> List[Claim]:
        concept = normalize_concept(concept)
        with self._db._lock:  # noqa: SLF001
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                # placeholders строятся только из длины enum-списка statuses.
                query = (
                    "SELECT * FROM claims "  # nosec B608
                    f"WHERE concept = ? AND status IN ({placeholders}) "
                    "ORDER BY confidence DESC"
                )
                rows = self._db._conn.execute(  # noqa: SLF001
                    query,
                    (concept, *(s.value for s in statuses)),
                ).fetchall()
            elif status is not None:
                rows = self._db._conn.execute(  # noqa: SLF001
                    "SELECT * FROM claims WHERE concept = ? AND status = ? ORDER BY confidence DESC",
                    (concept, status.value),
                ).fetchall()
            else:
                rows = self._db._conn.execute(  # noqa: SLF001
                    "SELECT * FROM claims WHERE concept = ? ORDER BY confidence DESC",
                    (concept,),
                ).fetchall()
        return [self._row_to_claim(row) for row in rows]

    def active_claims(self, concept: str) -> List[Claim]:
        return self.find_by_concept(concept, status=ClaimStatus.ACTIVE)

    def answerable_claims(self, concept: str) -> List[Claim]:
        return self.find_by_concept(
            concept,
            statuses=[ClaimStatus.ACTIVE, ClaimStatus.DISPUTED],
        )

    def search(
        self,
        query: str,
        statuses: Optional[List[ClaimStatus]] = None,
        top_n: int = 5,
    ) -> List[Claim]:
        """Найти answerable claims по простому token-overlap поверх concept и claim_text."""
        query_terms = search_terms(query, drop_stopwords=True)
        if not query_terms:
            return []

        statuses = statuses or [ClaimStatus.ACTIVE, ClaimStatus.DISPUTED]
        status_values = {status.value for status in statuses}
        with self._db._lock:  # noqa: SLF001
            rows = self._db._conn.execute(  # noqa: SLF001
                """
                SELECT * FROM claims
                ORDER BY confidence DESC, created_ts DESC
                """,
            ).fetchall()

        scored: List[tuple[float, float, float, Claim]] = []
        for row in rows:
            claim = self._row_to_claim(row)
            if claim.status.value not in status_values:
                continue
            concept_terms = search_terms(claim.concept)
            text_terms = search_terms(claim.claim_text)
            haystack_terms = concept_terms | text_terms
            if not haystack_terms:
                continue
            overlap = query_terms & haystack_terms
            if not overlap:
                continue
            overlap_score = len(overlap) / len(query_terms)
            concept_overlap = len(query_terms & concept_terms) / len(query_terms)
            quality = estimate_text_signal(f"{claim.concept}: {claim.claim_text}")
            combined = overlap_score * quality * (1.0 + 0.75 * concept_overlap)
            scored.append((combined, concept_overlap, quality, claim))

        scored.sort(
            key=lambda item: (
                -item[0],
                -item[1],
                -item[2],
                -item[3].confidence,
                -item[3].created_ts,
                item[3].claim_id,
            )
        )
        return [claim for _, _, _, claim in scored[:top_n]]

    def get_conflict_candidates(self, limit: int = 10) -> List[ConflictPair]:
        return self._get_pairs(ConflictStatus.CANDIDATE, limit)

    def get_disputed_pairs(self, limit: int = 10) -> List[ConflictPair]:
        return self._get_pairs(ConflictStatus.DISPUTED, limit)

    def get_unverified(self, limit: int = 50) -> List[Claim]:
        with self._db._lock:  # noqa: SLF001
            rows = self._db._conn.execute(  # noqa: SLF001
                "SELECT * FROM claims WHERE status = ? ORDER BY created_ts ASC LIMIT ?",
                (ClaimStatus.UNVERIFIED.value, limit),
            ).fetchall()
        return [self._row_to_claim(row) for row in rows]

    def set_status(self, claim_id: str, status: ClaimStatus, reason: str = "") -> None:
        claim = self.get(claim_id)
        metadata = claim.metadata if claim else {}
        if reason:
            metadata["status_reason"] = reason
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                UPDATE claims
                SET status = ?, updated_ts = ?, metadata_json = ?
                WHERE claim_id = ?
                """,
                (
                    status.value,
                    time.time(),
                    json.dumps(metadata, ensure_ascii=False),
                    claim_id,
                ),
            )

    def update_metadata(self, claim_id: str, updates: dict) -> None:  # type: ignore[type-arg]
        """Обновить metadata claim-а без изменения lifecycle status."""
        claim = self.get(claim_id)
        if claim is None:
            return
        metadata = dict(claim.metadata)
        metadata.update(updates)
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                UPDATE claims
                SET metadata_json = ?, updated_ts = ?
                WHERE claim_id = ?
                """,
                (json.dumps(metadata, ensure_ascii=False), time.time(), claim_id),
            )

    def set_confidence(self, claim_id: str, confidence: float, reason: str = "") -> None:
        """Установить confidence claim-а с optional причиной в metadata."""
        claim = self.get(claim_id)
        if claim is None:
            return
        metadata = dict(claim.metadata)
        if reason:
            metadata["confidence_reason"] = reason
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                UPDATE claims
                SET confidence = ?, metadata_json = ?, updated_ts = ?
                WHERE claim_id = ?
                """,
                (
                    max(0.0, min(1.0, float(confidence))),
                    json.dumps(metadata, ensure_ascii=False),
                    time.time(),
                    claim_id,
                ),
            )

    def mark_conflict_candidate(self, claim_a_id: str, claim_b_id: str) -> None:
        a_id, b_id = self._ordered_pair(claim_a_id, claim_b_id)
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                INSERT OR IGNORE INTO claim_conflicts
                    (claim_id_a, claim_id_b, detected_ts, status)
                VALUES (?, ?, ?, ?)
                """,
                (a_id, b_id, time.time(), ConflictStatus.CANDIDATE.value),
            )

    def dismiss_conflict(
        self,
        claim_a_id: str,
        claim_b_id: str,
        resolution: str = "false_positive",
    ) -> None:
        """Закрыть pair как dismissed без supersedes-связей."""
        a_id, b_id = self._ordered_pair(claim_a_id, claim_b_id)
        now = time.time()
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                UPDATE claim_conflicts
                SET status = ?, resolution = ?, resolved_ts = ?
                WHERE claim_id_a = ? AND claim_id_b = ?
                """,
                (ConflictStatus.DISMISSED.value, resolution, now, a_id, b_id),
            )

    def mark_disputed(self, claim_a_id: str, claim_b_id: str) -> None:
        a_id, b_id = self._ordered_pair(claim_a_id, claim_b_id)
        now = time.time()
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                INSERT INTO claim_conflicts (claim_id_a, claim_id_b, detected_ts, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(claim_id_a, claim_id_b) DO UPDATE SET
                    status = excluded.status,
                    resolution = NULL,
                    resolved_ts = NULL
                """,
                (a_id, b_id, now, ConflictStatus.DISPUTED.value),
            )
            self._db._conn.execute(  # noqa: SLF001
                "UPDATE claims SET status = ?, updated_ts = ? WHERE claim_id IN (?, ?)",
                (ClaimStatus.DISPUTED.value, now, a_id, b_id),
            )

    def resolve(self, winner_id: str, loser_id: str, resolution: str) -> None:
        if winner_id == loser_id:
            raise ValueError("winner_id and loser_id must differ")
        loser = self.get(loser_id)
        if loser is not None and loser.superseded_by == winner_id:
            return
        if self._would_create_supersedes_cycle(winner_id, loser_id):
            raise ValueError("resolve would create circular supersedes")
        a_id, b_id = self._ordered_pair(winner_id, loser_id)
        now = time.time()
        with self._db._lock:  # noqa: SLF001
            self._db._conn.execute(  # noqa: SLF001
                """
                UPDATE claims
                SET status = ?, superseded_by = ?, updated_ts = ?
                WHERE claim_id = ?
                """,
                (ClaimStatus.SUPERSEDED.value, winner_id, now, loser_id),
            )
            self._db._conn.execute(  # noqa: SLF001
                "UPDATE claims SET status = ?, updated_ts = ? WHERE claim_id = ?",
                (ClaimStatus.ACTIVE.value, now, winner_id),
            )
            self._db._conn.execute(  # noqa: SLF001
                """
                UPDATE claim_conflicts
                SET status = ?, resolution = ?, resolved_ts = ?
                WHERE claim_id_a = ? AND claim_id_b = ?
                """,
                (ConflictStatus.RESOLVED.value, resolution, now, a_id, b_id),
            )

    def retract(self, claim_id: str, reason: str) -> None:
        self.set_status(claim_id, ClaimStatus.RETRACTED, reason=reason)

    def open_conflict_count(self, claim_id: str) -> int:
        """Количество candidate/disputed pairs, где участвует claim."""
        with self._db._lock:  # noqa: SLF001
            row = self._db._conn.execute(  # noqa: SLF001
                """
                SELECT COUNT(*) AS cnt FROM claim_conflicts
                WHERE (claim_id_a = ? OR claim_id_b = ?)
                  AND status IN (?, ?)
                """,
                (
                    claim_id,
                    claim_id,
                    ConflictStatus.CANDIDATE.value,
                    ConflictStatus.DISPUTED.value,
                ),
            ).fetchone()
            return int(row["cnt"])

    def restore_if_no_open_conflicts(self, claim_id: str) -> None:
        """Вернуть claim в ACTIVE, если больше нет открытых конфликтов."""
        claim = self.get(claim_id)
        if claim is None:
            return
        if claim.status not in (ClaimStatus.POSSIBLY_CONFLICTING, ClaimStatus.DISPUTED):
            return
        if self.open_conflict_count(claim_id) == 0:
            self.set_status(claim_id, ClaimStatus.ACTIVE, reason="no_open_conflicts")

    def find_by_family(
        self,
        concept: str,
        claim_family_key: str,
        statuses: Optional[List[ClaimStatus]] = None,
    ) -> List[Claim]:
        """Найти claims одного concept/family для majority resolution."""
        concept = normalize_concept(concept)
        with self._db._lock:  # noqa: SLF001
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                # placeholders строятся только из длины enum-списка statuses.
                query = (
                    "SELECT * FROM claims "  # nosec B608
                    "WHERE concept = ? AND claim_family_key = ? "
                    f"AND status IN ({placeholders}) "
                    "ORDER BY confidence DESC, created_ts DESC"
                )
                rows = self._db._conn.execute(  # noqa: SLF001
                    query,
                    (concept, claim_family_key, *(s.value for s in statuses)),
                ).fetchall()
            else:
                rows = self._db._conn.execute(  # noqa: SLF001
                    """
                    SELECT * FROM claims
                    WHERE concept = ? AND claim_family_key = ?
                    ORDER BY confidence DESC, created_ts DESC
                    """,
                    (concept, claim_family_key),
                ).fetchall()
        return [self._row_to_claim(row) for row in rows]

    def count(self, status: Optional[ClaimStatus] = None) -> int:
        with self._db._lock:  # noqa: SLF001
            if status is None:
                row = self._db._conn.execute("SELECT COUNT(*) AS cnt FROM claims").fetchone()  # noqa: SLF001
            else:
                row = self._db._conn.execute(  # noqa: SLF001
                    "SELECT COUNT(*) AS cnt FROM claims WHERE status = ?",
                    (status.value,),
                ).fetchone()
            return int(row["cnt"])

    def _get_pairs(self, status: ConflictStatus, limit: int) -> List[ConflictPair]:
        with self._db._lock:  # noqa: SLF001
            rows = self._db._conn.execute(  # noqa: SLF001
                """
                SELECT * FROM claim_conflicts
                WHERE status = ?
                ORDER BY detected_ts ASC
                LIMIT ?
                """,
                (status.value, limit),
            ).fetchall()
        pairs: List[ConflictPair] = []
        for row in rows:
            a = self.get(str(row["claim_id_a"]))
            b = self.get(str(row["claim_id_b"]))
            if a is not None and b is not None:
                pairs.append(
                    ConflictPair(
                        a=a,
                        b=b,
                        detected_ts=float(row["detected_ts"]),
                        status=ConflictStatus(row["status"]),
                        resolution=row["resolution"],
                        resolved_ts=row["resolved_ts"],
                    )
                )
        return pairs

    def _row_to_claim(self, row) -> Claim:
        evidence_span = None
        if row["evidence_span_offset"] is not None and row["evidence_span_length"] is not None:
            evidence_span = (int(row["evidence_span_offset"]), int(row["evidence_span_length"]))
        metadata = json.loads(row["metadata_json"] or "{}")
        conflict_refs = self._conflict_refs(str(row["claim_id"]))
        return Claim(
            claim_id=str(row["claim_id"]),
            concept=str(row["concept"]),
            claim_text=str(row["claim_text"]),
            claim_family_key=str(row["claim_family_key"]),
            stance_key=str(row["stance_key"]),
            source_ref=str(row["source_ref"]),
            material_sha256=row["material_sha256"],
            source_group_id=str(row["source_group_id"]),
            evidence_span=evidence_span,
            evidence_kind=EvidenceKind(row["evidence_kind"]),
            confidence=float(row["confidence"]),
            status=ClaimStatus(row["status"]),
            supersedes=row["supersedes"],
            superseded_by=row["superseded_by"],
            conflict_refs=conflict_refs,
            created_ts=float(row["created_ts"]),
            updated_ts=float(row["updated_ts"]),
            metadata=metadata,
        )

    def _conflict_refs(self, claim_id: str) -> List[str]:
        rows = self._db._conn.execute(  # noqa: SLF001
            """
            SELECT claim_id_a, claim_id_b FROM claim_conflicts
            WHERE claim_id_a = ? OR claim_id_b = ?
            """,
            (claim_id, claim_id),
        ).fetchall()
        refs: List[str] = []
        for row in rows:
            other = row["claim_id_b"] if row["claim_id_a"] == claim_id else row["claim_id_a"]
            refs.append(str(other))
        return refs

    @staticmethod
    def _ordered_pair(a: str, b: str) -> tuple[str, str]:
        if a == b:
            raise ValueError("claim conflict pair requires two distinct claim IDs")
        return (a, b) if a < b else (b, a)

    def _would_create_supersedes_cycle(self, winner_id: str, loser_id: str) -> bool:
        current_id: Optional[str] = winner_id
        seen: set[str] = set()
        while current_id:
            if current_id == loser_id:
                return True
            if current_id in seen:
                return True
            seen.add(current_id)
            current = self.get(current_id)
            current_id = current.superseded_by if current is not None else None
        return False
