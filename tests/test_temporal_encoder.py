"""
tests/test_temporal_encoder.py — TDD тесты для TemporalEncoder (J.5).

Все ML-зависимости мокируются — тесты проходят без cv2/CLIP.
TemporalEncoder: видео → 512d вектор (mean-pool CLIP frame embeddings).
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from brain.core.contracts import Modality
from brain.encoders.temporal_encoder import PRIMARY_DIM, TemporalEncoder

# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def encoder():
    return TemporalEncoder()


@pytest.fixture
def tmp_mp4(tmp_path):
    """Фиктивный MP4-файл (не валидный, но с правильным расширением)."""
    p = tmp_path / "test.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftyp" + b"\x00" * 100)
    return str(p)


def _mock_frame_vector(dim: int = 512) -> np.ndarray:
    """Создать нормализованный случайный вектор для мока."""
    rng = np.random.default_rng(13)
    v = rng.random(dim).astype(np.float32)
    return v / np.linalg.norm(v)


# ─── PRIMARY_DIM константа ───────────────────────────────────────────────────


def test_primary_dim_is_512():
    assert PRIMARY_DIM == 512


# ─── Fallback: cv2 недоступен ────────────────────────────────────────────────


def test_encode_no_cv2_returns_zeros(tmp_mp4):
    with (
        patch("brain.encoders.temporal_encoder._CV2_AVAILABLE", False),
        patch("brain.encoders.temporal_encoder._CLIP_AVAILABLE", False),
    ):
        enc = TemporalEncoder()
        result = enc.encode(tmp_mp4)
    assert result.modality == Modality.VIDEO
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] == "failed"


def test_encode_no_clip_returns_zeros(tmp_mp4):
    mock_frames = [MagicMock(), MagicMock()]
    with (
        patch("brain.encoders.temporal_encoder._CV2_AVAILABLE", True),
        patch("brain.encoders.temporal_encoder._CLIP_AVAILABLE", False),
        patch(
            "brain.encoders.temporal_encoder._extract_frames",
            return_value=mock_frames,
        ),
    ):
        enc = TemporalEncoder()
        result = enc.encode(tmp_mp4)
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] == "degraded"


# ─── Happy path: cv2 + CLIP доступны ─────────────────────────────────────────


@contextlib.contextmanager
def _temporal_context(frame_vec: np.ndarray, n_frames: int = 2):
    """Контекстный менеджер: все патчи для TemporalEncoder happy-path."""
    mock_frames = [MagicMock() for _ in range(n_frames)]
    mock_model = MagicMock()
    mock_preprocess = MagicMock()
    with (
        patch("brain.encoders.temporal_encoder._CV2_AVAILABLE", True),
        patch("brain.encoders.temporal_encoder._CLIP_AVAILABLE", True),
        patch(
            "brain.encoders.temporal_encoder._extract_frames",
            return_value=mock_frames,
        ),
        patch(
            "brain.encoders.temporal_encoder._load_clip_model",
            return_value=(mock_model, mock_preprocess),
        ),
        patch(
            "brain.encoders.temporal_encoder._encode_frame_clip",
            return_value=frame_vec,
        ),
    ):
        yield


def test_encode_returns_512d_vector(tmp_mp4):
    frame_vec = _mock_frame_vector(512)
    with _temporal_context(frame_vec):
        enc = TemporalEncoder()
        result = enc.encode(tmp_mp4)
    assert result.modality == Modality.VIDEO
    assert len(result.vector) == PRIMARY_DIM
    assert result.metadata["encoder_status"] == "ok"


def test_encode_vector_is_l2_normalized(tmp_mp4):
    frame_vec = _mock_frame_vector(512)
    with _temporal_context(frame_vec):
        enc = TemporalEncoder()
        result = enc.encode(tmp_mp4)
    vec = np.array(result.vector)
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-5


def test_encode_vector_dim_matches_primary_dim(tmp_mp4):
    frame_vec = _mock_frame_vector(512)
    with _temporal_context(frame_vec):
        enc = TemporalEncoder()
        result = enc.encode(tmp_mp4)
    assert result.vector_dim == PRIMARY_DIM


def test_encode_mean_pools_multiple_frames(tmp_mp4):
    """Mean-pool: результат должен быть нормализованным средним по кадрам."""
    frame_vec = _mock_frame_vector(512)
    with _temporal_context(frame_vec, n_frames=4):
        enc = TemporalEncoder()
        result = enc.encode(tmp_mp4)
    # Mean-pool нормализованных одинаковых векторов = тот же вектор
    expected = frame_vec / np.linalg.norm(frame_vec)
    actual = np.array(result.vector)
    assert np.allclose(actual, expected, atol=1e-5)


# ─── EncodedPercept контракт ─────────────────────────────────────────────────


def test_encode_returns_encoded_percept_with_required_fields(tmp_mp4):
    frame_vec = _mock_frame_vector(512)
    with _temporal_context(frame_vec):
        enc = TemporalEncoder()
        result = enc.encode(
            tmp_mp4,
            source="test_source",
            trace_id="t1",
            session_id="s1",
            cycle_id="c1",
        )
    assert result.modality == Modality.VIDEO
    assert result.source == "test_source"
    assert result.trace_id == "t1"
    assert result.session_id == "s1"
    assert result.cycle_id == "c1"
    assert "encoder_status" in result.metadata
    assert "encoding_time_ms" in result.metadata
    assert "frames_extracted" in result.metadata


def test_encode_file_not_found_returns_zeros(encoder):
    result = encoder.encode("/nonexistent/video.mp4")
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] in ("failed", "degraded")


def test_encode_empty_path_returns_zeros(encoder):
    result = encoder.encode("")
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)


# ─── No frames extracted ─────────────────────────────────────────────────────


def test_encode_no_frames_returns_zeros(tmp_mp4):
    with (
        patch("brain.encoders.temporal_encoder._CV2_AVAILABLE", True),
        patch("brain.encoders.temporal_encoder._CLIP_AVAILABLE", True),
        patch(
            "brain.encoders.temporal_encoder._extract_frames",
            return_value=[],
        ),
    ):
        enc = TemporalEncoder()
        result = enc.encode(tmp_mp4)
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] in ("failed", "degraded")
    assert result.metadata["frames_extracted"] == 0


# ─── Crash fallback ──────────────────────────────────────────────────────────


def test_encode_clip_crash_returns_zeros(tmp_mp4):
    mock_frames = [MagicMock()]
    mock_model = MagicMock()
    mock_preprocess = MagicMock()
    with (
        patch("brain.encoders.temporal_encoder._CV2_AVAILABLE", True),
        patch("brain.encoders.temporal_encoder._CLIP_AVAILABLE", True),
        patch(
            "brain.encoders.temporal_encoder._extract_frames",
            return_value=mock_frames,
        ),
        patch(
            "brain.encoders.temporal_encoder._load_clip_model",
            return_value=(mock_model, mock_preprocess),
        ),
        patch(
            "brain.encoders.temporal_encoder._encode_frame_clip",
            side_effect=RuntimeError("CLIP crash"),
        ),
    ):
        enc = TemporalEncoder()
        result = enc.encode(tmp_mp4)
    assert len(result.vector) == PRIMARY_DIM
    assert all(v == 0.0 for v in result.vector)


# ─── status() ────────────────────────────────────────────────────────────────


def test_status_returns_dict_with_required_keys(encoder):
    s = encoder.status()
    assert isinstance(s, dict)
    assert "cv2_available" in s
    assert "clip_available" in s
    assert "vector_dim" in s
    assert s["vector_dim"] == PRIMARY_DIM


# ─── vector_dim property ─────────────────────────────────────────────────────


def test_vector_dim_property_equals_primary_dim(encoder):
    assert encoder.vector_dim == PRIMARY_DIM
