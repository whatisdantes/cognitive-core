"""
brain/fusion/confidence_calibrator.py — Калибровка confidence кросс-модального слияния.

Формула:
  confidence = base_quality × modality_agreement × source_trust × recency_factor

Компоненты:
  base_quality       — взвешенное среднее quality перцептов (text×1.0, audio×0.9, image×0.85)
  modality_agreement — среднее cosine similarity всех пар в shared space
  source_trust       — среднее trust_score из source_trust dict (default 0.7)
  recency_factor     — 1.0 (статический, расширяется в Stage M)

Нет новых pip-зависимостей — только numpy.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False

from brain.core.contracts import EncodedPercept, Modality

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Веса модальностей для base_quality
# ---------------------------------------------------------------------------

MODALITY_WEIGHTS: Dict[Modality, float] = {
    Modality.TEXT: 1.0,
    Modality.AUDIO: 0.9,
    Modality.IMAGE: 0.85,
    Modality.VIDEO: 0.85,
    Modality.FUSED: 1.0,
}


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
    import math
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-10 or nb < 1e-10:
        return 0.0
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# ConfidenceCalibrator
# ---------------------------------------------------------------------------

class ConfidenceCalibrator:
    """
    Калибрует итоговый confidence кросс-модального слияния.

    Использование:
        cc = ConfidenceCalibrator()
        conf = cc.calibrate(percepts, projected_vectors)
        conf = cc.calibrate(percepts, projected_vectors, source_trust={"src1": 0.9})
    """

    def __init__(self, default_source_trust: float = 0.7) -> None:
        self._default_trust = default_source_trust

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calibrate(
        self,
        percepts: List[EncodedPercept],
        projected: List[List[float]],
        source_trust: Optional[Dict[str, float]] = None,
    ) -> float:
        """
        Вычислить итоговый confidence.

        Args:
            percepts:     список EncodedPercept
            projected:    список 512d векторов (соответствует percepts по индексу)
            source_trust: dict {percept_id → trust_score} (опционально)

        Returns:
            float в диапазоне [0.0, 1.0]. 0.0 если percepts пуст.
        """
        if not percepts:
            return 0.0

        bq = self.base_quality(percepts)
        ma = self.modality_agreement(projected)
        st = self._source_trust_score(percepts, source_trust)
        recency = 1.0  # статический, расширяется в Stage M

        result = bq * ma * st * recency
        return round(max(0.0, min(1.0, result)), 6)

    def modality_agreement(self, projected: List[List[float]]) -> float:
        """
        Среднее cosine similarity всех пар в shared space.

        Returns:
            1.0 если 0 или 1 вектор (нет пар для сравнения).
            Среднее попарных cosine similarities иначе.
        """
        if len(projected) <= 1:
            return 1.0

        total = 0.0
        count = 0
        for i in range(len(projected)):
            for j in range(i + 1, len(projected)):
                total += _cosine_sim(projected[i], projected[j])
                count += 1

        return round(total / count, 6) if count > 0 else 1.0

    def base_quality(self, percepts: List[EncodedPercept]) -> float:
        """
        Взвешенное среднее quality по модальностям.

        Веса: text=1.0, audio=0.9, image=0.85, video=0.85, fused=1.0.
        Returns 0.0 если percepts пуст.
        """
        if not percepts:
            return 0.0

        total_weighted = 0.0
        total_weight = 0.0
        for p in percepts:
            w = MODALITY_WEIGHTS.get(p.modality, 1.0)
            total_weighted += p.quality * w
            total_weight += w

        if total_weight < 1e-10:
            return 0.0
        return round(total_weighted / total_weight, 6)

    def status(self) -> Dict[str, Any]:
        """Статус калибратора."""
        return {
            "default_source_trust": self._default_trust,
            "modality_weights": {m.value: w for m, w in MODALITY_WEIGHTS.items()},
        }

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _source_trust_score(
        self,
        percepts: List[EncodedPercept],
        source_trust: Optional[Dict[str, float]],
    ) -> float:
        """Среднее trust_score для всех перцептов."""
        if not percepts:
            return self._default_trust

        scores: List[float] = []
        for p in percepts:
            if source_trust and p.percept_id in source_trust:
                scores.append(source_trust[p.percept_id])
            else:
                scores.append(self._default_trust)

        return sum(scores) / len(scores) if scores else self._default_trust
