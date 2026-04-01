"""
perception — Слой восприятия (аналог Таламуса).

Реализовано (Этап D — Text-Only Perception):
    text_ingestor.py      — парсинг txt/md/pdf/docx/json/csv → PerceptEvent
    metadata_extractor.py — извлечение source/timestamp/quality/language
    input_router.py       — маршрутизация входящих данных

Реализовано (Этап J — Multimodal Expansion):
    vision_ingestor.py  — загрузка изображений + OCR → PerceptEvent (PIL + pytesseract)
    audio_ingestor.py   — ASR + временные метки → PerceptEvent (Whisper)
"""

from brain.perception.input_router import InputRouter, InputType
from brain.perception.metadata_extractor import MetadataExtractor
from brain.perception.text_ingestor import TextIngestor
from brain.perception.validators import MAX_FILE_SIZE_MB, check_file_size, validate_file_path
from brain.perception.vision_ingestor import VisionIngestor
from brain.perception.audio_ingestor import AudioIngestor

__all__ = [
    "MetadataExtractor",
    "TextIngestor",
    "InputRouter",
    "InputType",
    "validate_file_path",
    "check_file_size",
    "MAX_FILE_SIZE_MB",
    "VisionIngestor",
    "AudioIngestor",
]
