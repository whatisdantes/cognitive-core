"""
tests/test_audio_ingestor.py — TDD тесты для AudioIngestor (J.2).

Все ML-зависимости мокируются — тесты проходят без Whisper.
"""
from __future__ import annotations

import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brain.perception.audio_ingestor import AUDIO_EXTENSIONS, AudioIngestor


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def ingestor():
    return AudioIngestor()


@pytest.fixture
def tmp_wav(tmp_path):
    """Минимальный валидный WAV-файл (0.1 сек, 16kHz, mono)."""
    p = tmp_path / "test.wav"
    n_frames = 1600  # 0.1 сек при 16kHz
    with wave.open(str(p), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * n_frames)
    return str(p)


@pytest.fixture
def tmp_mp3(tmp_path):
    """Фиктивный MP3-файл (не валидный, но с правильным расширением)."""
    p = tmp_path / "test.mp3"
    p.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 100)
    return str(p)


# ─── AUDIO_EXTENSIONS ────────────────────────────────────────────────────────


def test_audio_extensions_contains_wav():
    assert ".wav" in AUDIO_EXTENSIONS


def test_audio_extensions_contains_mp3():
    assert ".mp3" in AUDIO_EXTENSIONS


def test_audio_extensions_contains_flac():
    assert ".flac" in AUDIO_EXTENSIONS


def test_audio_extensions_contains_ogg():
    assert ".ogg" in AUDIO_EXTENSIONS


def test_audio_extensions_contains_aac():
    assert ".aac" in AUDIO_EXTENSIONS


def test_audio_extensions_contains_m4a():
    assert ".m4a" in AUDIO_EXTENSIONS


# ─── Валидация файла ─────────────────────────────────────────────────────────


def test_ingest_file_not_found_returns_empty(ingestor):
    result = ingestor.ingest("/nonexistent/audio.wav")
    assert result == []


def test_ingest_unsupported_extension_returns_empty(ingestor, tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("hello")
    result = ingestor.ingest(str(f))
    assert result == []


def test_ingest_empty_path_returns_empty(ingestor):
    result = ingestor.ingest("")
    assert result == []


# ─── Fallback: Whisper недоступен, WAV файл ──────────────────────────────────


def test_ingest_no_whisper_wav_returns_event_with_empty_content(tmp_wav):
    with patch("brain.perception.audio_ingestor._WHISPER_AVAILABLE", False):
        ingestor = AudioIngestor()
        result = ingestor.ingest(tmp_wav)
    assert len(result) == 1
    event = result[0]
    assert event.modality == "audio"
    assert event.content == ""
    assert event.metadata["whisper_available"] is False
    assert event.metadata["duration_s"] is not None  # WAV → wave stdlib
    assert event.metadata["duration_s"] > 0


def test_ingest_no_whisper_wav_quality_lower(tmp_wav):
    with patch("brain.perception.audio_ingestor._WHISPER_AVAILABLE", False):
        ingestor = AudioIngestor()
        result = ingestor.ingest(tmp_wav)
    assert result[0].quality < 1.0


# ─── Fallback: Whisper недоступен, non-WAV файл ──────────────────────────────


def test_ingest_no_whisper_mp3_duration_is_none(tmp_mp3):
    with patch("brain.perception.audio_ingestor._WHISPER_AVAILABLE", False):
        ingestor = AudioIngestor()
        result = ingestor.ingest(tmp_mp3)
    assert len(result) == 1
    event = result[0]
    assert event.modality == "audio"
    assert event.content == ""
    assert event.metadata["duration_s"] is None
    assert event.metadata["duration_available"] is False


# ─── Happy path: Whisper доступен ────────────────────────────────────────────


def test_ingest_whisper_returns_transcript(tmp_wav):
    mock_result = {"text": "Привет мир", "language": "ru"}
    with (
        patch("brain.perception.audio_ingestor._WHISPER_AVAILABLE", True),
        patch("brain.perception.audio_ingestor._transcribe_audio", return_value=mock_result),
    ):
        ingestor = AudioIngestor()
        result = ingestor.ingest(tmp_wav)
    assert len(result) == 1
    event = result[0]
    assert event.modality == "audio"
    assert event.content == "Привет мир"
    assert event.language == "ru"
    assert event.metadata["whisper_available"] is True
    assert event.quality == 1.0


def test_ingest_whisper_empty_transcript_quality_lower(tmp_wav):
    mock_result = {"text": "", "language": "unknown"}
    with (
        patch("brain.perception.audio_ingestor._WHISPER_AVAILABLE", True),
        patch("brain.perception.audio_ingestor._transcribe_audio", return_value=mock_result),
    ):
        ingestor = AudioIngestor()
        result = ingestor.ingest(tmp_wav)
    assert result[0].quality < 1.0


# ─── PerceptEvent контракт ───────────────────────────────────────────────────


def test_ingest_event_has_all_required_metadata_fields(tmp_wav):
    with patch("brain.perception.audio_ingestor._WHISPER_AVAILABLE", False):
        ingestor = AudioIngestor()
        result = ingestor.ingest(tmp_wav, session_id="s1", trace_id="t1")
    event = result[0]
    assert event.modality == "audio"
    assert event.source == tmp_wav
    assert "whisper_available" in event.metadata
    assert "duration_s" in event.metadata
    assert "sample_rate" in event.metadata
    assert "file_size_kb" in event.metadata
    assert "duration_available" in event.metadata
    assert event.session_id == "s1"
    assert event.trace_id == "t1"


def test_ingest_wav_metadata_has_sample_rate(tmp_wav):
    with patch("brain.perception.audio_ingestor._WHISPER_AVAILABLE", False):
        ingestor = AudioIngestor()
        result = ingestor.ingest(tmp_wav)
    assert result[0].metadata["sample_rate"] == 16000


# ─── status() ────────────────────────────────────────────────────────────────


def test_status_returns_dict_with_required_keys(ingestor):
    s = ingestor.status()
    assert isinstance(s, dict)
    assert "whisper_available" in s
    assert "supported_extensions" in s


# ─── Crash fallbacks ─────────────────────────────────────────────────────────


def test_ingest_whisper_crash_returns_event_with_empty_content(tmp_wav):
    with (
        patch("brain.perception.audio_ingestor._WHISPER_AVAILABLE", True),
        patch(
            "brain.perception.audio_ingestor._transcribe_audio",
            side_effect=RuntimeError("Whisper crash"),
        ),
    ):
        ingestor = AudioIngestor()
        result = ingestor.ingest(tmp_wav)
    assert len(result) == 1
    assert result[0].content == ""


# ─── Все поддерживаемые форматы ──────────────────────────────────────────────


@pytest.mark.parametrize("ext", [".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a"])
def test_ingest_accepts_all_supported_extensions(tmp_path, ext):
    f = tmp_path / f"audio{ext}"
    f.write_bytes(b"\x00" * 100)
    with patch("brain.perception.audio_ingestor._WHISPER_AVAILABLE", False):
        ingestor = AudioIngestor()
        result = ingestor.ingest(str(f))
    # Должен вернуть событие (не []) — файл существует и расширение поддерживается
    assert len(result) == 1
    assert result[0].modality == "audio"
