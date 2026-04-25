# tests/test_confidence_calibrator.py
"""Тесты для brain/fusion/confidence_calibrator.py (K.3)."""
from __future__ import annotations

import math

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
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    assert ConfidenceCalibrator is not None


# ---------------------------------------------------------------------------
# calibrate() — edge cases
# ---------------------------------------------------------------------------

def test_calibrate_empty_returns_zero():
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    assert ConfidenceCalibrator().calibrate([], []) == 0.0


def test_calibrate_single_text_in_range():
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    v = _unit(512)
    ps = [_p("p1", Modality.TEXT, v, 0.9)]
    result = ConfidenceCalibrator().calibrate(ps, [v])
    assert 0.0 < result <= 1.0


def test_calibrate_result_in_range():
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    v = _unit(512)
    ps = [_p("p1", Modality.TEXT, v, 0.8), _p("p2", Modality.IMAGE, v, 0.7)]
    result = ConfidenceCalibrator().calibrate(ps, [v, v])
    assert 0.0 <= result <= 1.0


def test_calibrate_high_trust_gt_low_trust():
    """Высокий source_trust → выше confidence."""
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    v = _unit(512)
    ps = [_p("p1", Modality.TEXT, v, 0.9)]
    r_high = ConfidenceCalibrator().calibrate(ps, [v], source_trust={"p1": 1.0})
    r_low = ConfidenceCalibrator().calibrate(ps, [v], source_trust={"p1": 0.1})
    assert r_high > r_low


def test_calibrate_identical_vectors_higher_than_orthogonal():
    """Идентичные векторы (agreement=1.0) → выше confidence, чем ортогональные."""
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    v = _unit(512)
    v1 = [1.0] + [0.0] * 511
    v2 = [0.0, 1.0] + [0.0] * 510
    ps_same = [_p("p1", Modality.TEXT, v, 0.8), _p("p2", Modality.IMAGE, v, 0.8)]
    ps_orth = [_p("p1", Modality.TEXT, v1, 0.8), _p("p2", Modality.IMAGE, v2, 0.8)]
    r_same = ConfidenceCalibrator().calibrate(ps_same, [v, v])
    r_orth = ConfidenceCalibrator().calibrate(ps_orth, [v1, v2])
    assert r_same > r_orth


# ---------------------------------------------------------------------------
# modality_agreement()
# ---------------------------------------------------------------------------

def test_modality_agreement_single():
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    v = _unit(512)
    assert ConfidenceCalibrator().modality_agreement([v]) == 1.0


def test_modality_agreement_empty():
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    assert ConfidenceCalibrator().modality_agreement([]) == 1.0


def test_modality_agreement_identical():
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    v = _unit(512)
    result = ConfidenceCalibrator().modality_agreement([v, v])
    assert abs(result - 1.0) < 1e-5


def test_modality_agreement_orthogonal():
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    v1 = [1.0] + [0.0] * 511
    v2 = [0.0, 1.0] + [0.0] * 510
    result = ConfidenceCalibrator().modality_agreement([v1, v2])
    assert abs(result) < 1e-5


# ---------------------------------------------------------------------------
# base_quality()
# ---------------------------------------------------------------------------

def test_base_quality_empty():
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    assert ConfidenceCalibrator().base_quality([]) == 0.0


def test_base_quality_text_weight_gt_audio():
    """text weight=1.0 > audio weight=0.9 → text quality выше при равном quality."""
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    v = _unit(512)
    ps_text = [_p("p1", Modality.TEXT, v, 1.0)]
    ps_audio = [_p("p1", Modality.AUDIO, v, 1.0)]
    q_text = ConfidenceCalibrator().base_quality(ps_text)
    q_audio = ConfidenceCalibrator().base_quality(ps_audio)
    assert q_text >= q_audio


def test_base_quality_image_weight_lt_text():
    """image weight=0.85 < text weight=1.0."""
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    v = _unit(512)
    ps_text = [_p("p1", Modality.TEXT, v, 1.0)]
    ps_image = [_p("p1", Modality.IMAGE, v, 1.0)]
    assert ConfidenceCalibrator().base_quality(ps_text) >= ConfidenceCalibrator().base_quality(ps_image)


# ---------------------------------------------------------------------------
# default_source_trust
# ---------------------------------------------------------------------------

def test_default_source_trust_affects_result():
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    v = _unit(512)
    ps = [_p("p1", Modality.TEXT, v, 0.9)]
    r_high = ConfidenceCalibrator(default_source_trust=1.0).calibrate(ps, [v])
    r_low = ConfidenceCalibrator(default_source_trust=0.1).calibrate(ps, [v])
    assert r_high > r_low


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------

def test_status():
    from brain.fusion.confidence_calibrator import ConfidenceCalibrator
    s = ConfidenceCalibrator().status()
    assert "default_source_trust" in s
