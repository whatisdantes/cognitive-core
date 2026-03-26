"""
perception — Слой восприятия (аналог Таламуса).

Реализовано (Этап D — Text-Only Perception):
    text_ingestor.py      — парсинг txt/md/pdf/docx/json/csv → PerceptEvent
    metadata_extractor.py — извлечение source/timestamp/quality/language
    input_router.py       — маршрутизация входящих данных (text-only MVP)

Запланировано (Этапы J+):
    vision_ingestor.py  — загрузка изображений + OCR → PerceptEvent
    audio_ingestor.py   — ASR + временные метки → PerceptEvent
"""

from brain.perception.metadata_extractor import MetadataExtractor
from brain.perception.text_ingestor import TextIngestor
from brain.perception.input_router import InputRouter
from brain.perception.validators import validate_file_path, check_file_size, MAX_FILE_SIZE_MB

__all__ = [
    "MetadataExtractor",
    "TextIngestor",
    "InputRouter",
    "validate_file_path",
    "check_file_size",
    "MAX_FILE_SIZE_MB",
]
