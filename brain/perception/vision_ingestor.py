"""
brain/perception/vision_ingestor.py — Ingestor для изображений (J.1).

Поддерживаемые форматы: .jpg, .jpeg, .png, .gif, .bmp, .webp, .tiff

Fallback-цепочка:
  PIL + pytesseract → OCR-текст, quality=1.0
  PIL only          → content="", quality=0.6, ocr_available=False
  no PIL            → [] (пустой список)

Использование:
    ingestor = VisionIngestor()
    events = ingestor.ingest("photo.jpg", session_id="s1")
    # events[0].modality == "image"
    # events[0].content  == "OCR text or empty"
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List

from brain.core.events import EventFactory, PerceptEvent

logger = logging.getLogger(__name__)

# ─── Опциональные зависимости ────────────────────────────────────────────────

try:
    from PIL import Image as _PILImage  # type: ignore[import-untyped]
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.debug("Pillow не установлен — VisionIngestor работает в degraded режиме")

try:
    import pytesseract as _pytesseract  # type: ignore[import-untyped]
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False
    logger.debug("pytesseract не установлен — OCR недоступен")

# ─── Константы ───────────────────────────────────────────────────────────────

VISION_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff",
})

_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


# ─── Вспомогательные функции (мокируемые в тестах) ───────────────────────────

def _open_image(path: str) -> Any:
    """Открыть изображение через PIL. Мокируется в тестах."""
    return _PILImage.open(path)


def _ocr_image(image: Any) -> str:
    """Выполнить OCR через pytesseract. Мокируется в тестах."""
    return str(_pytesseract.image_to_string(image)).strip()


# ─── VisionIngestor ──────────────────────────────────────────────────────────

class VisionIngestor:
    """
    Читает файлы изображений и преобразует в PerceptEvent(modality="image").

    Параметры:
        max_file_size: максимальный размер файла в байтах (default: 50 MB)
    """

    def __init__(self, max_file_size: int = _MAX_FILE_SIZE_BYTES) -> None:
        self._max_file_size = max_file_size

    def ingest(
        self,
        file_path: str,
        session_id: str = "",
        trace_id: str = "",
    ) -> List[PerceptEvent]:
        """
        Прочитать файл изображения → List[PerceptEvent].

        Возвращает [] при:
          - пустом пути
          - несуществующем файле
          - неподдерживаемом расширении
          - PIL недоступен
          - ошибке открытия файла
        """
        if not file_path:
            return []

        path = Path(file_path)

        # Проверка расширения
        if path.suffix.lower() not in VISION_EXTENSIONS:
            logger.debug("VisionIngestor: неподдерживаемое расширение '%s'", path.suffix)
            return []

        # Проверка существования файла
        if not path.exists():
            logger.warning("VisionIngestor: файл не найден '%s'", file_path)
            return []

        # PIL недоступен → degraded
        if not _PIL_AVAILABLE:
            logger.warning("VisionIngestor: Pillow недоступен, пропускаем '%s'", file_path)
            return []

        # Открытие изображения
        try:
            image = _open_image(file_path)
        except Exception as exc:
            logger.warning("VisionIngestor: ошибка открытия '%s': %s", file_path, exc)
            return []

        # Метаданные изображения
        width, height = image.size
        fmt = image.format or path.suffix.lstrip(".").upper()
        file_size_kb = round(path.stat().st_size / 1024, 2)

        # OCR
        content = ""
        ocr_available = _TESSERACT_AVAILABLE
        if _TESSERACT_AVAILABLE:
            try:
                content = _ocr_image(image)
            except Exception as exc:
                logger.warning("VisionIngestor: OCR ошибка для '%s': %s", file_path, exc)
                content = ""
                ocr_available = False

        # Качество: 1.0 если OCR дал текст, 0.6 если нет OCR/текста
        if ocr_available and content:
            quality = 1.0
        else:
            quality = 0.6

        event = EventFactory.percept(
            source=file_path,
            content=content,
            modality="image",
            quality=quality,
            language="unknown",
            session_id=session_id,
            # metadata kwargs:
            width=width,
            height=height,
            format=fmt,
            pil_available=_PIL_AVAILABLE,
            ocr_available=ocr_available,
            file_size_kb=file_size_kb,
        )
        if trace_id:
            event.trace_id = trace_id

        return [event]

    def status(self) -> dict:  # type: ignore[type-arg]
        """Статус ingestor'а."""
        return {
            "pil_available": _PIL_AVAILABLE,
            "tesseract_available": _TESSERACT_AVAILABLE,
            "supported_extensions": sorted(VISION_EXTENSIONS),
            "max_file_size_mb": self._max_file_size // (1024 * 1024),
        }

    def __repr__(self) -> str:
        return (
            f"VisionIngestor("
            f"pil={_PIL_AVAILABLE}, "
            f"ocr={_TESSERACT_AVAILABLE})"
        )
