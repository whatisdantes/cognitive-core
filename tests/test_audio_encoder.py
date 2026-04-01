"""
tests/test_audio_encoder.py — TDD тесты для AudioEncoder (J.4).

Все ML-зависимости мокируются — тесты проходят без Whisper/torch.
AudioEncoder: Whisper → dynamic output_dim (совпадает с text_encoder.vector_dim).
"""
from __future__ import annotations

import contextlib
import wave
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from brain.encoders.audio_encoder import AudioEncoder
from brain.core.contracts import Modality


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def encoder():
    return AudioEncoder()


@pytest.fixture
def tmp_wav(tmp_path):
    """Минимальный валидный WAV-файл (0.1 сек, 16kHz, mono)."""
    p = tmp_path / "test.wav"
    n_frames = 1600
    with wave.open(str(p), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * n_frames)
    return str(p)


def _mock_audio_vector(dim: int = 768) -> np.ndarray:
    """Создать нормализованный случайный вектор для мока."""
    rng = np.random.default_rng(7)
    v = rng.random(dim).astype(np.float32)
    return v / np.linalg.norm(v)


# ─── output_dim ──────────────────────────────────────────────────────────────


def test_default_output_dim_is_768():
    enc = AudioEncoder()
    assert enc.vector_dim == 768


def test_custom_output_dim():
    enc = AudioEncoder(output_dim=300)
    assert enc.vector_dim == 300


# ─── Fallback: Whisper недоступен ────────────────────────────────────────────


def test_encode_no_whisper_returns_zeros(tmp_wav):
    with patch("brain.encoders.audio_encoder._WHISPER_AVAILABLE", False):
        enc = AudioEncoder()
        result = enc.encode(tmp_wav)
    assert result.modality == Modality.AUDIO
    assert len(result.vector) == 768
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] == "degraded"


def test_encode_no_whisper_vector_dim_matches_output_dim(tmp_wav):
    with patch("brain.encoders.audio_encoder._WHISPER_AVAILABLE", False):
        enc = AudioEncoder(output_dim=300)
        result = enc.encode(tmp_wav)
    assert len(result.vector) == 300
    assert result.vector_dim == 300


# ─── Happy path: Whisper доступен ────────────────────────────────────────────


@contextlib.contextmanager
def _whisper_context(audio_vec: np.ndarray):
    """Контекстный менеджер: все патчи для Whisper happy-path."""
    mock_model = MagicMock()
    mock_preprocess = MagicMock()
    with (
        patch("brain.encoders.audio_encoder._WHISPER_AVAILABLE", True),
        patch(
            "brain.encoders.audio_encoder._load_whisper_model",
            return_value=mock_model,
        ),
        patch(
            "brain.encoders.audio_encoder._encode_audio_whisper",
            return_value=audio_vec,
        ),
    ):
        yield


def test_encode_whisper_returns_vector(tmp_wav):
    audio_vec = _mock_audio_vector(768)
    with _whisper_context(audio_vec):
        enc = AudioEncoder()
        result = enc.encode(tmp_wav)
    assert result.modality == Modality.AUDIO
    assert len(result.vector) == 768
    assert result.metadata["encoder_status"] == "ok"


def test_encode_whisper_vector_is_l2_normalized(tmp_wav):
    audio_vec = _mock_audio_vector(768)
    with _whisper_context(audio_vec):
        enc = AudioEncoder()
        result = enc.encode(tmp_wav)
    vec = np.array(result.vector)
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-5


def test_encode_whisper_vector_dim_matches_output_dim(tmp_wav):
    audio_vec = _mock_audio_vector(768)
    with _whisper_context(audio_vec):
        enc = AudioEncoder()
        result = enc.encode(tmp_wav)
    assert result.vector_dim == 768


# ─── EncodedPercept контракт ─────────────────────────────────────────────────


def test_encode_returns_encoded_percept_with_required_fields(tmp_wav):
    audio_vec = _mock_audio_vector(768)
    with _whisper_context(audio_vec):
        enc = AudioEncoder()
        result = enc.encode(
            tmp_wav,
            source="test_source",
            trace_id="t1",
            session_id="s1",
            cycle_id="c1",
        )
    assert result.modality == Modality.AUDIO
    assert result.source == "test_source"
    assert result.trace_id == "t1"
    assert result.session_id == "s1"
    assert result.cycle_id == "c1"
    assert "encoder_status" in result.metadata
    assert "encoding_time_ms" in result.metadata
    assert "whisper_available" in result.metadata


def test_encode_file_not_found_returns_zeros(encoder):
    result = encoder.encode("/nonexistent/audio.wav")
    assert len(result.vector) == encoder.vector_dim
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] in ("failed", "degraded")


def test_encode_empty_path_returns_zeros(encoder):
    result = encoder.encode("")
    assert len(result.vector) == encoder.vector_dim
    assert all(v == 0.0 for v in result.vector)


# ─── Crash fallback ──────────────────────────────────────────────────────────


def test_encode_whisper_crash_returns_zeros(tmp_wav):
    mock_model = MagicMock()
    with (
        patch("brain.encoders.audio_encoder._WHISPER_AVAILABLE", True),
        patch(
            "brain.encoders.audio_encoder._load_whisper_model",
            return_value=mock_model,
        ),
        patch(
            "brain.encoders.audio_encoder._encode_audio_whisper",
            side_effect=RuntimeError("Whisper crash"),
        ),
    ):
        enc = AudioEncoder()
        result = enc.encode(tmp_wav)
    assert len(result.vector) == 768
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata["encoder_status"] in ("failed", "degraded")


# ─── status() ────────────────────────────────────────────────────────────────


def test_status_returns_dict_with_required_keys(encoder):
    s = encoder.status()
    assert isinstance(s, dict)
    assert "whisper_available" in s
    assert "vector_dim" in s
    assert s["vector_dim"] == 768


# ─── vector_dim property ─────────────────────────────────────────────────────


def test_vector_dim_property_equals_output_dim(encoder):
    assert encoder.vector_dim == 768
