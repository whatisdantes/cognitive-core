"""
brain/fusion/cross_modal_contradiction_detector.py — Детектор кросс-модальных противоречий.

Два типа противоречий:
  MODAL_MISMATCH       — cosine similarity < 0.20 между разными модальностями
  CONFIDENCE_CONFLICT  — |quality_a - quality_b| > 0.50 между разными модальностями

Severity:
  HIGH   — sim < 0.05  (почти ортогональные)
  MEDIUM — sim < 0.20  (низкая схожесть)
  LOW    — CONFIDENCE_CONFLICT без MODAL_MISMATCH

Только кросс-модальные пары (разные modality) проверяются.
Нет новых pip-зависимостей — только numpy.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False

from brain.core.contracts import EncodedPercept, Modality

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Пороги
# ---------------------------------------------------------------------------

_MISMATCH_THRESHOLD = 0.20   # sim < этого → MODAL_MISMATCH
_CONFLICT_THRESHOLD = 0.50   # |q_a - q_b| > этого → CONFIDENCE_CONFLICT
_SEVERITY_HIGH = 0.05        # sim < этого → HIGH severity


# ---------------------------------------------------------------------------
# CrossModalContradiction
# ---------------------------------------------------------------------------

@dataclass
class CrossModalContradiction:
    """Описание одного кросс-модального противоречия."""

    contradiction_id: str
    percept_a_id: str
    percept_b_id: str
    modality_a: Modality
    modality_b: Modality
    similarity: float
    contradiction_type: str   # "MODAL_MISMATCH" | "CONFIDENCE_CONFLICT"
    severity: str             # "LOW" | "MEDIUM" | "HIGH"
    description: str


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


def _severity(sim: float) -> str:
    """Severity по cosine similarity."""
    if sim < _SEVERITY_HIGH:
        return "HIGH"
    return "MEDIUM"


# ---------------------------------------------------------------------------
# CrossModalContradictionDetector
# ---------------------------------------------------------------------------

class CrossModalContradictionDetector:
    """
    Детектирует кросс-модальные противоречия между перцептами.

    Использование:
        detector = CrossModalContradictionDetector()
        contradictions = detector.detect(percepts, projected_vectors)
    """

    def __init__(
        self,
        mismatch_threshold: float = _MISMATCH_THRESHOLD,
        conflict_threshold: float = _CONFLICT_THRESHOLD,
    ) -> None:
        self._mismatch_threshold = mismatch_threshold
        self._conflict_threshold = conflict_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        percepts: List[EncodedPercept],
        projected: List[List[float]],
    ) -> List[CrossModalContradiction]:
        """
        Обнаружить кросс-модальные противоречия.

        Args:
            percepts:  список EncodedPercept
            projected: список 512d векторов (соответствует percepts по индексу)

        Returns:
            Список CrossModalContradiction. Пустой если нет противоречий.
        """
        if len(percepts) < 2:
            return []

        contradictions: List[CrossModalContradiction] = []

        for i in range(len(percepts)):
            for j in range(i + 1, len(percepts)):
                pa = percepts[i]
                pb = percepts[j]

                # Только кросс-модальные пары
                if pa.modality == pb.modality:
                    continue

                va = projected[i] if i < len(projected) else []
                vb = projected[j] if j < len(projected) else []
                sim = _cosine_sim(va, vb)

                # Проверка MODAL_MISMATCH
                if sim < self._mismatch_threshold:
                    cid = f"contra_{uuid.uuid4().hex[:8]}"
                    contradictions.append(CrossModalContradiction(
                        contradiction_id=cid,
                        percept_a_id=pa.percept_id,
                        percept_b_id=pb.percept_id,
                        modality_a=pa.modality,
                        modality_b=pb.modality,
                        similarity=round(sim, 6),
                        contradiction_type="MODAL_MISMATCH",
                        severity=_severity(sim),
                        description=(
                            f"Cross-modal similarity {sim:.3f} < "
                            f"{self._mismatch_threshold} between "
                            f"{pa.modality.value} and {pb.modality.value}"
                        ),
                    ))
                    continue  # не добавляем CONFIDENCE_CONFLICT поверх MODAL_MISMATCH

                # Проверка CONFIDENCE_CONFLICT
                quality_diff = abs(pa.quality - pb.quality)
                if quality_diff > self._conflict_threshold:
                    cid = f"contra_{uuid.uuid4().hex[:8]}"
                    contradictions.append(CrossModalContradiction(
                        contradiction_id=cid,
                        percept_a_id=pa.percept_id,
                        percept_b_id=pb.percept_id,
                        modality_a=pa.modality,
                        modality_b=pb.modality,
                        similarity=round(sim, 6),
                        contradiction_type="CONFIDENCE_CONFLICT",
                        severity="LOW",
                        description=(
                            f"Quality difference {quality_diff:.3f} > "
                            f"{self._conflict_threshold} between "
                            f"{pa.modality.value}(q={pa.quality}) and "
                            f"{pb.modality.value}(q={pb.quality})"
                        ),
                    ))

        return contradictions

    def status(self) -> Dict[str, Any]:
        """Статус детектора."""
        return {
            "mismatch_threshold": self._mismatch_threshold,
            "conflict_threshold": self._conflict_threshold,
        }
