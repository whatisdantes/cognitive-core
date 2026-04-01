"""
tests/test_vision_ingestor.py — TDD тесты для VisionIngestor (J.1).

Все ML-зависимости мокируются — тесты проходят без Pillow/pytesseract.
"""
from __future__ import annotations

import struct
import wave
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brain.perception.vision_ingestor import VISION_EXTENSIONS, VisionIngestor


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def ingestor():
    return VisionIngestor()


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


@pytest.fixture
def tmp_jpg(tmp_path):
    """Минимальный JPEG-файл."""
    data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    p = tmp_path / "test.jpg"
    p.write_bytes(data)
    return str(p)


def _mock_image(width: int = 100, height: int = 200, fmt: str = "PNG") -> MagicMock:
    img = MagicMock()
    img.size = (width, height)
    img.format = fmt
    return img


# ─── VISION_EXTENSIONS ───────────────────────────────────────────────────────


def test_vision_extensions_contains_jpg():
    assert ".jpg" in VISION_EXTENSIONS


def test_vision_extensions_contains_jpeg():
    assert ".jpeg" in VISION_EXTENSIONS


def test_vision_extensions_contains_png():
    assert ".png" in VISION_EXTENSIONS


def test_vision_extensions_contains_gif():
    assert ".gif" in VISION_EXTENSIONS


def test_vision_extensions_contains_bmp():
    assert ".bmp" in VISION_EXTENSIONS


def test_vision_extensions_contains_webp():
    assert ".webp" in VISION_EXTENSIONS


def test_vision_extensions_contains_tiff():
    assert ".tiff" in VISION_EXTENSIONS


# ─── Валидация файла ─────────────────────────────────────────────────────────


def test_ingest_file_not_found_returns_empty(ingestor):
    result = ingestor.ingest("/nonexistent/path/image.png")
    assert result == []


def test_ingest_unsupported_extension_returns_empty(ingestor, tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("hello")
    result = ingestor.ingest(str(f))
    assert result == []


def test_ingest_empty_path_returns_empty(ingestor):
    result = ingestor.ingest("")
    assert result == []


# ─── Fallback: PIL недоступен ────────────────────────────────────────────────


def test_ingest_no_pil_returns_empty(tmp_png):
    with patch("brain.perception.vision_ingestor._PIL_AVAILABLE", False):
        ingestor = VisionIngestor()
        result = ingestor.ingest(tmp_png)
    assert result == []


# ─── Fallback: PIL есть, OCR нет ─────────────────────────────────────────────


def test_ingest_pil_no_ocr_returns_event_with_empty_content(tmp_png):
    mock_img = _mock_image(100, 200, "PNG")
    with (
        patch("brain.perception.vision_ingestor._PIL_AVAILABLE", True),
        patch("brain.perception.vision_ingestor._TESSERACT_AVAILABLE", False),
        patch("brain.perception.vision_ingestor._open_image", return_value=mock_img),
    ):
        ingestor = VisionIngestor()
        result = ingestor.ingest(tmp_png)
    assert len(result) == 1
    event = result[0]
    assert event.modality == "image"
    assert event.content == ""
    assert event.metadata["ocr_available"] is False
    assert event.metadata["pil_available"] is True
    assert event.metadata["width"] == 100
    assert event.metadata["height"] == 200


def test_ingest_pil_no_ocr_quality_is_lower(tmp_png):
    mock_img = _mock_image()
    with (
        patch("brain.perception.vision_ingestor._PIL_AVAILABLE", True),
        patch("brain.perception.vision_ingestor._TESSERACT_AVAILABLE", False),
        patch("brain.perception.vision_ingestor._open_image", return_value=mock_img),
    ):
        ingestor = VisionIngestor()
        result = ingestor.ingest(tmp_png)
    assert result[0].quality < 1.0


# ─── Happy path: PIL + pytesseract ───────────────────────────────────────────


def test_ingest_full_ocr_returns_event_with_text(tmp_png):
    mock_img = _mock_image(640, 480, "PNG")
    with (
        patch("brain.perception.vision_ingestor._PIL_AVAILABLE", True),
        patch("brain.perception.vision_ingestor._TESSERACT_AVAILABLE", True),
        patch("brain.perception.vision_ingestor._open_image", return_value=mock_img),
        patch("brain.perception.vision_ingestor._ocr_image", return_value="Hello World"),
    ):
        ingestor = VisionIngestor()
        result = ingestor.ingest(tmp_png)
    assert len(result) == 1
    event = result[0]
    assert event.modality == "image"
    assert event.content == "Hello World"
    assert event.metadata["ocr_available"] is True
    assert event.quality == 1.0


def test_ingest_ocr_empty_text_quality_lower(tmp_png):
    mock_img = _mock_image()
    with (
        patch("brain.perception.vision_ingestor._PIL_AVAILABLE", True),
        patch("brain.perception.vision_ingestor._TESSERACT_AVAILABLE", True),
        patch("brain.perception.vision_ingestor._open_image", return_value=mock_img),
        patch("brain.perception.vision_ingestor._ocr_image", return_value=""),
    ):
        ingestor = VisionIngestor()
        result = ingestor.ingest(tmp_png)
    assert len(result) == 1
    assert result[0].quality < 1.0


# ─── PerceptEvent контракт ───────────────────────────────────────────────────


def test_ingest_event_has_all_required_metadata_fields(tmp_png):
    mock_img = _mock_image(320, 240, "PNG")
    with (
        patch("brain.perception.vision_ingestor._PIL_AVAILABLE", True),
        patch("brain.perception.vision_ingestor._TESSERACT_AVAILABLE", False),
        patch("brain.perception.vision_ingestor._open_image", return_value=mock_img),
    ):
        ingestor = VisionIngestor()
        result = ingestor.ingest(tmp_png, session_id="s1", trace_id="t1")
    event = result[0]
    assert event.modality == "image"
    assert event.source == tmp_png
    assert "width" in event.metadata
    assert "height" in event.metadata
    assert "format" in event.metadata
    assert "pil_available" in event.metadata
    assert "ocr_available" in event.metadata
    assert "file_size_kb" in event.metadata
    assert event.session_id == "s1"
    assert event.trace_id == "t1"


# ─── status() ────────────────────────────────────────────────────────────────


def test_status_returns_dict_with_required_keys(ingestor):
    s = ingestor.status()
    assert isinstance(s, dict)
    assert "pil_available" in s
    assert "tesseract_available" in s
    assert "supported_extensions" in s


# ─── Все поддерживаемые форматы ──────────────────────────────────────────────


@pytest.mark.parametrize("ext", [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".gif"])
def test_ingest_accepts_all_supported_extensions(tmp_path, ext):
    f = tmp_path / f"img{ext}"
    f.write_bytes(b"\x00" * 100)
    mock_img = _mock_image(10, 10, ext.lstrip(".").upper())
    with (
        patch("brain.perception.vision_ingestor._PIL_AVAILABLE", True),
        patch("brain.perception.vision_ingestor._TESSERACT_AVAILABLE", False),
        patch("brain.perception.vision_ingestor._open_image", return_value=mock_img),
    ):
        ingestor = VisionIngestor()
        result = ingestor.ingest(str(f))
    assert len(result) == 1


# ─── Crash fallbacks ─────────────────────────────────────────────────────────


def test_ingest_ocr_crash_returns_event_with_empty_content(tmp_png):
    mock_img = _mock_image()
    with (
        patch("brain.perception.vision_ingestor._PIL_AVAILABLE", True),
        patch("brain.perception.vision_ingestor._TESSERACT_AVAILABLE", True),
        patch("brain.perception.vision_ingestor._open_image", return_value=mock_img),
        patch(
            "brain.perception.vision_ingestor._ocr_image",
            side_effect=RuntimeError("OCR failed"),
        ),
    ):
        ingestor = VisionIngestor()
        result = ingestor.ingest(tmp_png)
    assert len(result) == 1
    assert result[0].content == ""


def test_ingest_pil_crash_returns_empty(tmp_png):
    with (
        patch("brain.perception.vision_ingestor._PIL_AVAILABLE", True),
        patch(
            "brain.perception.vision_ingestor._open_image",
            side_effect=Exception("PIL crash"),
        ),
    ):
        ingestor = VisionIngestor()
        result = ingestor.ingest(tmp_png)
    assert result == []
