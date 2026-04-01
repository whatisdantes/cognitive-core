"""
tests/test_vision_encoder.py — TDD тесты для VisionEncoder (J.3).

Все ML-зависимости мокируются — тесты проходят без CLIP/Pillow.
VisionEncoder: CLIP 512d (без проекции, Strategy A).
"""
from __future__ import annotations

import contextlib
import struct
import zlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from brain.encoders.vision_encoder import PRIMARY_DIM, VisionEncoder
from brain.core.contracts import Modality


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def encoder():
    return VisionEncoder()


@pytest.fixture
def tmp_png(tmp_path):
    """Минимальный валидный PNG (1x1 белый пиксель)."""

    def _chunk(name: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(name + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = _chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
    iend = _chunk(b"IEND", b"")
    p = tmp_path / "test.png"
    p.write_bytes(sig + ihdr + idat + iend)
    return str(p)


def _mock_clip_vector(dim: int = 512) -> np.ndarray:
    """Создать нормализованный случайный вектор для мока CLIP."""
    rng = np.random.default_rng(42)
    v = rng.random(dim).astype(np.float32)
    return v / np.linalg.norm(v)


# ─── PRIMARY_DIM константа ───────────────────────────────────────────────────


def test_primary_dim_is_512():
    assert PRIMARY_DIM == 512


# ─── Fallback: PIL недоступен ────────────────────────────────────────────────


def test_encode_no_pil_returns_zeros(tmp_png):
    with (
        patch("brain.encoders.vision_encoder._PIL_AVAILABLE", False),
        patch("brain.encoders.vision_encoder._CLIP_AVAILABLE", False),
    ):
        enc = VisionEncoder()
        result = enc.encode(tmp_png)
    assert result.modality == Modality.IMAGE
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] == "failed"


def test_encode_no_clip_returns_zeros(tmp_png):
    mock_img = MagicMock()
    with (
        patch("brain.encoders.vision_encoder._PIL_AVAILABLE", True),
        patch("brain.encoders.vision_encoder._CLIP_AVAILABLE", False),
        patch("brain.encoders.vision_encoder._open_image", return_value=mock_img),
    ):
        enc = VisionEncoder()
        result = enc.encode(tmp_png)
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] == "degraded"


# ─── Happy path: CLIP доступен ───────────────────────────────────────────────


@contextlib.contextmanager
def _clip_context(mock_img: Any, clip_vec: np.ndarray):
    """Контекстный менеджер: все патчи для CLIP happy-path."""
    mock_model = MagicMock()
    mock_preprocess = MagicMock()
    with (
        patch("brain.encoders.vision_encoder._PIL_AVAILABLE", True),
        patch("brain.encoders.vision_encoder._CLIP_AVAILABLE", True),
        patch("brain.encoders.vision_encoder._open_image", return_value=mock_img),
        patch(
            "brain.encoders.vision_encoder._load_clip_model",
            return_value=(mock_model, mock_preprocess),
        ),
        patch("brain.encoders.vision_encoder._encode_image_clip", return_value=clip_vec),
    ):
        yield


def test_encode_clip_returns_512d_vector(tmp_png):
    mock_img = MagicMock()
    clip_vec = _mock_clip_vector(512)
    with _clip_context(mock_img, clip_vec):
        enc = VisionEncoder()
        result = enc.encode(tmp_png)
    assert result.modality == Modality.IMAGE
    assert len(result.vector) == PRIMARY_DIM
    assert result.metadata["encoder_status"] == "ok"


def test_encode_clip_vector_is_l2_normalized(tmp_png):
    mock_img = MagicMock()
    clip_vec = _mock_clip_vector(512)
    with _clip_context(mock_img, clip_vec):
        enc = VisionEncoder()
        result = enc.encode(tmp_png)
    vec = np.array(result.vector)
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-5


def test_encode_clip_vector_dim_matches_primary_dim(tmp_png):
    mock_img = MagicMock()
    clip_vec = _mock_clip_vector(512)
    with _clip_context(mock_img, clip_vec):
        enc = VisionEncoder()
        result = enc.encode(tmp_png)
    assert result.vector_dim == PRIMARY_DIM


# ─── EncodedPercept контракт ─────────────────────────────────────────────────


def test_encode_returns_encoded_percept_with_required_fields(tmp_png):
    mock_img = MagicMock()
    clip_vec = _mock_clip_vector(512)
    mock_model = MagicMock()
    mock_preprocess = MagicMock()
    with (
        patch("brain.encoders.vision_encoder._PIL_AVAILABLE", True),
        patch("brain.encoders.vision_encoder._CLIP_AVAILABLE", True),
        patch("brain.encoders.vision_encoder._open_image", return_value=mock_img),
        patch(
            "brain.encoders.vision_encoder._load_clip_model",
            return_value=(mock_model, mock_preprocess),
        ),
        patch("brain.encoders.vision_encoder._encode_image_clip", return_value=clip_vec),
    ):
        enc = VisionEncoder()
        result = enc.encode(
            tmp_png,
            source="test_source",
            trace_id="t1",
            session_id="s1",
            cycle_id="c1",
        )
    assert result.modality == Modality.IMAGE
    assert result.source == "test_source"
    assert result.trace_id == "t1"
    assert result.session_id == "s1"
    assert result.cycle_id == "c1"
    assert "encoder_status" in result.metadata
    assert "encoding_time_ms" in result.metadata


def test_encode_file_not_found_returns_zeros(encoder):
    result = encoder.encode("/nonexistent/image.png")
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] in ("failed", "degraded")


def test_encode_empty_path_returns_zeros(encoder):
    result = encoder.encode("")
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)


# ─── Crash fallback ──────────────────────────────────────────────────────────


def test_encode_clip_crash_returns_zeros(tmp_png):
    mock_img = MagicMock()
    mock_model = MagicMock()
    mock_preprocess = MagicMock()
    with (
        patch("brain.encoders.vision_encoder._PIL_AVAILABLE", True),
        patch("brain.encoders.vision_encoder._CLIP_AVAILABLE", True),
        patch("brain.encoders.vision_encoder._open_image", return_value=mock_img),
        patch(
            "brain.encoders.vision_encoder._load_clip_model",
            return_value=(mock_model, mock_preprocess),
        ),
        patch(
            "brain.encoders.vision_encoder._encode_image_clip",
            side_effect=RuntimeError("CLIP crash"),
        ),
    ):
        enc = VisionEncoder()
        result = enc.encode(tmp_png)
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] in ("failed", "degraded")


def test_encode_pil_crash_returns_zeros(tmp_png):
    with (
        patch("brain.encoders.vision_encoder._PIL_AVAILABLE", True),
        patch(
            "brain.encoders.vision_encoder._open_image",
            side_effect=Exception("PIL crash"),
        ),
    ):
        enc = VisionEncoder()
        result = enc.encode(tmp_png)
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)


# ─── status() ────────────────────────────────────────────────────────────────


def test_status_returns_dict_with_required_keys(encoder):
    s = encoder.status()
    assert isinstance(s, dict)
    assert "pil_available" in s
    assert "clip_available" in s
    assert "vector_dim" in s
    assert s["vector_dim"] == PRIMARY_DIM


# ─── vector_dim property ─────────────────────────────────────────────────────


def test_vector_dim_property_equals_primary_dim(encoder):
    assert encoder.vector_dim == PRIMARY_DIM
