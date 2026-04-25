# tests/test_shared_space_projector.py
"""Тесты для brain/fusion/shared_space_projector.py (K.1)."""
from __future__ import annotations

import math
import os
import tempfile

from brain.core.contracts import EncodedPercept, Modality


def _percept(modality: Modality, dim: int, value: float = 0.5, pid: str = "p1") -> EncodedPercept:
    return EncodedPercept(
        percept_id=pid, modality=modality,
        vector=[value] * dim, text="test", quality=0.8, vector_dim=dim,
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def test_import():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    assert SharedSpaceProjector is not None


# ---------------------------------------------------------------------------
# Инициализация
# ---------------------------------------------------------------------------

def test_default_target_dim():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    assert SharedSpaceProjector().TARGET_DIM == 512


def test_custom_target_dim():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    assert SharedSpaceProjector(target_dim=256).TARGET_DIM == 256


def test_seed_reproducibility():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    v = [0.5] * 768
    r1 = SharedSpaceProjector(seed=42).project(v, Modality.TEXT)
    r2 = SharedSpaceProjector(seed=42).project(v, Modality.TEXT)
    assert r1 == r2


# ---------------------------------------------------------------------------
# project() — размерность
# ---------------------------------------------------------------------------

def test_project_text_dim():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    assert len(SharedSpaceProjector(seed=0).project([0.1] * 768, Modality.TEXT)) == 512


def test_project_audio_dim():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    assert len(SharedSpaceProjector(seed=0).project([0.1] * 768, Modality.AUDIO)) == 512


def test_project_image_dim():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    assert len(SharedSpaceProjector(seed=0).project([0.1] * 512, Modality.IMAGE)) == 512


# ---------------------------------------------------------------------------
# project() — L2-нормализация
# ---------------------------------------------------------------------------

def test_project_text_l2_norm():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    r = SharedSpaceProjector(seed=0).project([0.3] * 768, Modality.TEXT)
    assert abs(math.sqrt(sum(x * x for x in r)) - 1.0) < 1e-5


def test_project_image_l2_norm():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    r = SharedSpaceProjector(seed=0).project([0.3] * 512, Modality.IMAGE)
    assert abs(math.sqrt(sum(x * x for x in r)) - 1.0) < 1e-5


def test_project_audio_l2_norm():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    r = SharedSpaceProjector(seed=0).project([0.3] * 768, Modality.AUDIO)
    assert abs(math.sqrt(sum(x * x for x in r)) - 1.0) < 1e-5


# ---------------------------------------------------------------------------
# project() — edge cases
# ---------------------------------------------------------------------------

def test_project_empty_returns_zeros():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    assert SharedSpaceProjector(seed=0).project([], Modality.TEXT) == [0.0] * 512


def test_project_all_zeros_returns_zeros():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    assert SharedSpaceProjector(seed=0).project([0.0] * 768, Modality.TEXT) == [0.0] * 512


# ---------------------------------------------------------------------------
# project_percept() и project_all()
# ---------------------------------------------------------------------------

def test_project_percept_text():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    p = _percept(Modality.TEXT, 768)
    assert len(SharedSpaceProjector(seed=0).project_percept(p)) == 512


def test_project_all_three_modalities():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    ssp = SharedSpaceProjector(seed=0)
    ps = [
        _percept(Modality.TEXT, 768, pid="p1"),
        _percept(Modality.IMAGE, 512, pid="p2"),
        _percept(Modality.AUDIO, 768, pid="p3"),
    ]
    rs = ssp.project_all(ps)
    assert len(rs) == 3
    for r in rs:
        assert len(r) == 512


def test_project_all_empty():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    assert SharedSpaceProjector(seed=0).project_all([]) == []


# ---------------------------------------------------------------------------
# save() / load()
# ---------------------------------------------------------------------------

def test_save_load_roundtrip():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    ssp1 = SharedSpaceProjector(seed=7)
    v = [0.4] * 768
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "proj.json")
        ssp1.save(path)
        ssp2 = SharedSpaceProjector(seed=99)
        ssp2.load(path)
        assert ssp1.project(v, Modality.TEXT) == ssp2.project(v, Modality.TEXT)


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------

def test_status_keys():
    from brain.fusion.shared_space_projector import SharedSpaceProjector
    s = SharedSpaceProjector().status()
    assert s["target_dim"] == 512
    assert "text_input_dim" in s
    assert "audio_input_dim" in s
