"""
tests/test_encoder_router.py — TDD тесты для EncoderRouter (J.6).

EncoderRouter маршрутизирует PerceptEvent → правильный энкодер по modality.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from brain.encoders.encoder_router import EncoderRouter
from brain.core.contracts import EncodedPercept, Modality


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_percept(modality: str, content: str = "test", file_path: str = "") -> MagicMock:
    """Создать мок PerceptEvent."""
    p = MagicMock()
    p.modality = modality
    p.content = content
    p.file_path = file_path
    p.source = "test_source"
    p.trace_id = "t1"
    p.session_id = "s1"
    p.cycle_id = "c1"
    return p


def _make_encoded(modality: Modality, dim: int = 768) -> EncodedPercept:
    """Создать мок EncodedPercept."""
    rng = np.random.default_rng(42)
    vec = rng.random(dim).tolist()
    ep = MagicMock(spec=EncodedPercept)
    ep.modality = modality
    ep.vector = vec
    ep.vector_dim = dim
    return ep


# ─── Инициализация ───────────────────────────────────────────────────────────


def test_router_creates_with_defaults():
    router = EncoderRouter()
    assert router is not None


def test_router_accepts_custom_encoders():
    mock_text = MagicMock()
    mock_vision = MagicMock()
    mock_audio = MagicMock()
    mock_temporal = MagicMock()
    router = EncoderRouter(
        text_encoder=mock_text,
        vision_encoder=mock_vision,
        audio_encoder=mock_audio,
        temporal_encoder=mock_temporal,
    )
    assert router is not None


# ─── Маршрутизация по modality ────────────────────────────────────────────────


def test_route_text_percept_to_text_encoder():
    mock_text_enc = MagicMock()
    mock_text_enc.encode.return_value = _make_encoded(Modality.TEXT, 768)
    router = EncoderRouter(text_encoder=mock_text_enc)

    percept = _make_percept("text", content="hello world")
    result = router.route(percept)

    mock_text_enc.encode.assert_called_once()
    assert result.modality == Modality.TEXT


def test_route_image_percept_to_vision_encoder():
    mock_vision_enc = MagicMock()
    mock_vision_enc.encode.return_value = _make_encoded(Modality.IMAGE, 512)
    router = EncoderRouter(vision_encoder=mock_vision_enc)

    percept = _make_percept("image", file_path="/tmp/img.jpg")
    result = router.route(percept)

    mock_vision_enc.encode.assert_called_once()
    assert result.modality == Modality.IMAGE


def test_route_audio_percept_to_audio_encoder():
    mock_audio_enc = MagicMock()
    mock_audio_enc.encode.return_value = _make_encoded(Modality.AUDIO, 768)
    router = EncoderRouter(audio_encoder=mock_audio_enc)

    percept = _make_percept("audio", file_path="/tmp/audio.wav")
    result = router.route(percept)

    mock_audio_enc.encode.assert_called_once()
    assert result.modality == Modality.AUDIO


def test_route_video_percept_to_temporal_encoder():
    mock_temporal_enc = MagicMock()
    mock_temporal_enc.encode.return_value = _make_encoded(Modality.VIDEO, 512)
    router = EncoderRouter(temporal_encoder=mock_temporal_enc)

    percept = _make_percept("video", file_path="/tmp/video.mp4")
    result = router.route(percept)

    mock_temporal_enc.encode.assert_called_once()
    assert result.modality == Modality.VIDEO


# ─── Fallback: энкодер не задан ──────────────────────────────────────────────


def test_route_image_no_vision_encoder_returns_zeros():
    router = EncoderRouter(vision_encoder=None)
    percept = _make_percept("image", file_path="/tmp/img.jpg")
    result = router.route(percept)
    assert result.modality == Modality.IMAGE
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata.get("encoder_status") in ("failed", "degraded", "unavailable")


def test_route_audio_no_audio_encoder_returns_zeros():
    router = EncoderRouter(audio_encoder=None)
    percept = _make_percept("audio", file_path="/tmp/audio.wav")
    result = router.route(percept)
    assert result.modality == Modality.AUDIO
    assert all(v == 0.0 for v in result.vector)


def test_route_video_no_temporal_encoder_returns_zeros():
    router = EncoderRouter(temporal_encoder=None)
    percept = _make_percept("video", file_path="/tmp/video.mp4")
    result = router.route(percept)
    assert result.modality == Modality.VIDEO
    assert all(v == 0.0 for v in result.vector)


# ─── Неизвестная модальность ─────────────────────────────────────────────────


def test_route_unknown_modality_returns_zeros():
    router = EncoderRouter()
    percept = _make_percept("unknown_modality")
    result = router.route(percept)
    assert isinstance(result, EncodedPercept)
    assert all(v == 0.0 for v in result.vector)
    assert result.metadata.get("encoder_status") in ("failed", "unavailable")


# ─── route_all ───────────────────────────────────────────────────────────────


def test_route_all_returns_list_of_encoded_percepts():
    mock_text_enc = MagicMock()
    mock_text_enc.encode.return_value = _make_encoded(Modality.TEXT, 768)
    router = EncoderRouter(text_encoder=mock_text_enc)

    percepts = [
        _make_percept("text", content="hello"),
        _make_percept("text", content="world"),
    ]
    results = router.route_all(percepts)
    assert len(results) == 2
    assert all(r.modality == Modality.TEXT for r in results)


def test_route_all_empty_list_returns_empty():
    router = EncoderRouter()
    results = router.route_all([])
    assert results == []


# ─── status() ────────────────────────────────────────────────────────────────


def test_status_returns_dict_with_required_keys():
    router = EncoderRouter()
    s = router.status()
    assert isinstance(s, dict)
    assert "text_encoder" in s
    assert "vision_encoder" in s
    assert "audio_encoder" in s
    assert "temporal_encoder" in s


def test_status_shows_none_for_missing_encoders():
    router = EncoderRouter(vision_encoder=None, audio_encoder=None)
    s = router.status()
    assert s["vision_encoder"] is None
    assert s["audio_encoder"] is None
