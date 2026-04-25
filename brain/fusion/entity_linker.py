"""
brain/fusion/entity_linker.py — Связывание сущностей между модальностями.

Находит пары EncodedPercept с высоким cosine similarity в shared space
и группирует их в EntityCluster через union-find.

Пороги:
  sim > 0.90  → STRONG LINK
  sim > 0.75  → LINK
  sim > 0.60  → WEAK LINK
  sim ≤ 0.60  → NO LINK (не создаётся)

Проверяются только пары с РАЗНЫМИ модальностями.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False

from brain.core.contracts import EncodedPercept

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CrossModalLink:
    """Связь между двумя перцептами разных модальностей."""
    source_id: str
    target_id: str
    similarity: float
    link_type: str          # "STRONG" | "LINK" | "WEAK"
    source_modality: str
    target_modality: str


@dataclass
class EntityCluster:
    """Кластер связанных перцептов (одна сущность в разных модальностях)."""
    cluster_id: str
    centroid: List[float]       # 512d, среднее по members
    member_ids: List[str]       # percept_id's
    modalities: List[str]       # уникальные модальности
    confidence: float           # среднее quality members
    created_at: str             # ISO timestamp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cosine_sim(a: List[float], b: List[float]) -> float:
    """Cosine similarity между двумя векторами."""
    if not a or not b:
        return 0.0
    if _NUMPY_AVAILABLE:
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        na = float(np.linalg.norm(va))
        nb = float(np.linalg.norm(vb))
        if na < 1e-10 or nb < 1e-10:
            return 0.0
        return float(np.dot(va, vb) / (na * nb))
    # Fallback: pure Python
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-10 or nb < 1e-10:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# EntityLinker
# ---------------------------------------------------------------------------

class EntityLinker:
    """
    Связывает сущности между модальностями через cosine similarity в shared space.

    Использование:
        linker = EntityLinker()
        links = linker.link(percepts, projected_vectors)
        clusters = linker.cluster(percepts, projected_vectors)
    """

    STRONG_THRESHOLD: float = 0.90
    LINK_THRESHOLD: float = 0.75
    WEAK_THRESHOLD: float = 0.60

    def __init__(
        self,
        link_threshold: float = 0.75,
        strong_threshold: float = 0.90,
        weak_threshold: float = 0.60,
    ) -> None:
        self._link_threshold = link_threshold
        self._strong_threshold = strong_threshold
        self._weak_threshold = weak_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def link(
        self,
        percepts: List[EncodedPercept],
        projected: List[List[float]],
    ) -> List[CrossModalLink]:
        """
        Найти все пары с sim > weak_threshold и разными модальностями.

        Args:
            percepts:  список EncodedPercept
            projected: список 512d векторов (соответствует percepts по индексу)

        Returns:
            Список CrossModalLink (только пары с разными модальностями)
        """
        if len(percepts) < 2:
            return []

        links: List[CrossModalLink] = []
        for i in range(len(percepts)):
            for j in range(i + 1, len(percepts)):
                p_a, p_b = percepts[i], percepts[j]

                # Только разные модальности
                if p_a.modality == p_b.modality:
                    continue

                sim = _cosine_sim(projected[i], projected[j])
                if sim <= self._weak_threshold:
                    continue

                if sim > self._strong_threshold:
                    link_type = "STRONG"
                elif sim > self._link_threshold:
                    link_type = "LINK"
                else:
                    link_type = "WEAK"

                links.append(CrossModalLink(
                    source_id=p_a.percept_id,
                    target_id=p_b.percept_id,
                    similarity=round(sim, 6),
                    link_type=link_type,
                    source_modality=p_a.modality.value,
                    target_modality=p_b.modality.value,
                ))
        return links

    def cluster(
        self,
        percepts: List[EncodedPercept],
        projected: List[List[float]],
    ) -> List[EntityCluster]:
        """
        Сгруппировать связанные перцепты в кластеры (union-find).

        Объединяет пары с sim > link_threshold (любые модальности).
        Centroid = mean(projected_vectors) для всех members.
        Confidence = mean(quality) для всех members.
        """
        if not percepts:
            return []

        n = len(percepts)
        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            parent[find(x)] = find(y)

        # Объединяем пары с sim > link_threshold
        for i in range(n):
            for j in range(i + 1, n):
                if _cosine_sim(projected[i], projected[j]) > self._link_threshold:
                    union(i, j)

        # Собираем группы
        groups: Dict[int, List[int]] = {}
        for i in range(n):
            groups.setdefault(find(i), []).append(i)

        now = datetime.now(timezone.utc).isoformat()
        clusters: List[EntityCluster] = []

        for indices in groups.values():
            member_ids = [percepts[i].percept_id for i in indices]
            modalities = list({percepts[i].modality.value for i in indices})
            qualities = [percepts[i].quality for i in indices]
            confidence = sum(qualities) / len(qualities) if qualities else 0.0

            # Centroid = mean of projected vectors
            if _NUMPY_AVAILABLE:
                vecs = np.array([projected[i] for i in indices], dtype=np.float32)
                centroid = vecs.mean(axis=0).tolist()
            else:
                dim = len(projected[indices[0]])
                centroid = [
                    sum(projected[i][d] for i in indices) / len(indices)
                    for d in range(dim)
                ]

            clusters.append(EntityCluster(
                cluster_id=uuid.uuid4().hex[:12],
                centroid=centroid,
                member_ids=member_ids,
                modalities=modalities,
                confidence=round(confidence, 4),
                created_at=now,
            ))

        return clusters

    def status(self) -> Dict[str, Any]:
        """Статус линкера."""
        return {
            "link_threshold": self._link_threshold,
            "strong_threshold": self._strong_threshold,
            "weak_threshold": self._weak_threshold,
        }
