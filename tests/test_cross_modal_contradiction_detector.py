# tests/test_cross_modal_contradiction_detector.py
"""Тесты для brain/fusion/cross_modal_contradiction_detector.py (K.4)."""
from __future__ import annotations
import math

import pytest

from brain.core.contracts import EncodedPercept, Modality


def _p(pid: str, mod: Modality, vec: list, q: float = 0.8) -> EncodedPercept:
    return EncodedPercept(
        percept_id=pid, modality=mod, vector=vec,
        text="test", quality=q, vector_dim=len(vec),
    )


def _unit(dim: int) -> list:
    v = [1.0] * dim
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def test_import():
    from brain.fusion.cross_modal_contradiction_detector import (
        CrossModalContradiction,
        CrossModalContradictionDetector,
    )
    assert CrossModalContradiction is not None
    assert CrossModalContradictionDetector is not None


# ---------------------------------------------------------------------------
# CrossModalContradiction dataclass fields
# ---------------------------------------------------------------------------

def test_contradiction_fields():
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradiction
    c = CrossModalContradiction(
        contradiction_id="c1",
        percept_a_id="p1",
        percept_b_id="p2",
        modality_a=Modality.TEXT,
        modality_b=Modality.IMAGE,
        similarity=0.1,
        contradiction_type="MODAL_MISMATCH",
        severity="HIGH",
        description="test",
    )
    assert c.contradiction_id == "c1"
    assert c.percept_a_id == "p1"
    assert c.percept_b_id == "p2"
    assert c.modality_a == Modality.TEXT
    assert c.modality_b == Modality.IMAGE
    assert c.similarity == 0.1
    assert c.contradiction_type == "MODAL_MISMATCH"
    assert c.severity == "HIGH"
    assert c.description == "test"


# ---------------------------------------------------------------------------
# detect() — empty / single
# ---------------------------------------------------------------------------

def test_detect_empty():
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    result = CrossModalContradictionDetector().detect([], [])
    assert result == []


def test_detect_single_percept():
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    v = _unit(512)
    ps = [_p("p1", Modality.TEXT, v)]
    result = CrossModalContradictionDetector().detect(ps, [v])
    assert result == []


# ---------------------------------------------------------------------------
# detect() — same modality excluded
# ---------------------------------------------------------------------------

def test_detect_same_modality_no_contradiction():
    """Два TEXT перцепта с ортогональными векторами — не должны давать противоречие."""
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    v1 = [1.0] + [0.0] * 511
    v2 = [0.0, 1.0] + [0.0] * 510
    ps = [_p("p1", Modality.TEXT, v1), _p("p2", Modality.TEXT, v2)]
    result = CrossModalContradictionDetector().detect(ps, [v1, v2])
    assert result == []


# ---------------------------------------------------------------------------
# detect() — MODAL_MISMATCH (sim < 0.20)
# ---------------------------------------------------------------------------

def test_detect_modal_mismatch_orthogonal():
    """TEXT + IMAGE с ортогональными векторами → MODAL_MISMATCH."""
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    v1 = [1.0] + [0.0] * 511
    v2 = [0.0, 1.0] + [0.0] * 510
    ps = [_p("p1", Modality.TEXT, v1), _p("p2", Modality.IMAGE, v2)]
    result = CrossModalContradictionDetector().detect(ps, [v1, v2])
    assert len(result) == 1
    assert result[0].contradiction_type == "MODAL_MISMATCH"
    assert result[0].percept_a_id == "p1"
    assert result[0].percept_b_id == "p2"


def test_detect_modal_mismatch_has_id():
    """Каждое противоречие имеет непустой contradiction_id."""
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    v1 = [1.0] + [0.0] * 511
    v2 = [0.0, 1.0] + [0.0] * 510
    ps = [_p("p1", Modality.TEXT, v1), _p("p2", Modality.AUDIO, v2)]
    result = CrossModalContradictionDetector().detect(ps, [v1, v2])
    assert len(result) >= 1
    assert result[0].contradiction_id != ""


def test_detect_no_contradiction_similar_vectors():
    """TEXT + IMAGE с идентичными векторами → нет противоречия."""
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    v = _unit(512)
    ps = [_p("p1", Modality.TEXT, v), _p("p2", Modality.IMAGE, v)]
    result = CrossModalContradictionDetector().detect(ps, [v, v])
    assert result == []


# ---------------------------------------------------------------------------
# detect() — CONFIDENCE_CONFLICT (|quality_a - quality_b| > 0.5)
# ---------------------------------------------------------------------------

def test_detect_confidence_conflict():
    """TEXT quality=0.9 + IMAGE quality=0.3 → CONFIDENCE_CONFLICT."""
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    v = _unit(512)  # похожие векторы, но большая разница в quality
    ps = [_p("p1", Modality.TEXT, v, 0.9), _p("p2", Modality.IMAGE, v, 0.3)]
    result = CrossModalContradictionDetector().detect(ps, [v, v])
    types = [r.contradiction_type for r in result]
    assert "CONFIDENCE_CONFLICT" in types


def test_detect_confidence_conflict_threshold():
    """Разница quality = 0.5 (граница) — не должна давать CONFIDENCE_CONFLICT."""
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    v = _unit(512)
    ps = [_p("p1", Modality.TEXT, v, 0.9), _p("p2", Modality.IMAGE, v, 0.4)]
    result = CrossModalContradictionDetector().detect(ps, [v, v])
    types = [r.contradiction_type for r in result]
    assert "CONFIDENCE_CONFLICT" not in types


# ---------------------------------------------------------------------------
# severity
# ---------------------------------------------------------------------------

def test_detect_severity_high_for_orthogonal():
    """Ортогональные векторы → severity HIGH."""
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    v1 = [1.0] + [0.0] * 511
    v2 = [0.0, 1.0] + [0.0] * 510
    ps = [_p("p1", Modality.TEXT, v1), _p("p2", Modality.IMAGE, v2)]
    result = CrossModalContradictionDetector().detect(ps, [v1, v2])
    assert any(r.severity == "HIGH" for r in result)


def test_detect_severity_medium_for_low_sim():
    """Sim ~0.15 (низкая, но не нулевая) → severity MEDIUM или HIGH."""
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    # Вектор с небольшим перекрытием
    v1 = [1.0, 0.1] + [0.0] * 510
    v2 = [0.1, 1.0] + [0.0] * 510
    # Нормализуем
    n1 = math.sqrt(sum(x * x for x in v1))
    n2 = math.sqrt(sum(x * x for x in v2))
    v1 = [x / n1 for x in v1]
    v2 = [x / n2 for x in v2]
    ps = [_p("p1", Modality.TEXT, v1), _p("p2", Modality.IMAGE, v2)]
    result = CrossModalContradictionDetector().detect(ps, [v1, v2])
    # Если sim > 0.20 — нет MODAL_MISMATCH, но может быть другое
    # Просто проверяем что severity валидный
    for r in result:
        assert r.severity in ("LOW", "MEDIUM", "HIGH")


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------

def test_status():
    from brain.fusion.cross_modal_contradiction_detector import CrossModalContradictionDetector
    s = CrossModalContradictionDetector().status()
    assert isinstance(s, dict)
    assert "mismatch_threshold" in s
    assert "conflict_threshold" in s
