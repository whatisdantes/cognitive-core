"""
metadata_extractor.py — Извлечение метаданных из текстового контента.

Работает поверх всех ingestor'ов и добавляет к каждому фрагменту:
  - source, ts, quality, language, file_size_kb, encoding, page, chunk_id

Quality scoring (MVP, эвристики из спецификации):
  - длина текста > 50 символов       → +0.3
  - нет битых символов               → +0.3
  - язык определён                   → +0.2
  - структура есть (абзацы/строки)   → +0.2

Пороги (MVP):
  quality >= 0.7  → нормальный вход
  0.4 <= q < 0.7  → WARNING (обработать с пометкой)
  quality < 0.4   → WARNING + low-priority
  Hard reject     → только пустой/нечитаемый контент

Язык определяется эвристически по доле кириллических символов:
  > 60% кириллицы → 'ru'
  > 60% латиницы  → 'en'
  смешанный       → 'mixed'
  нет букв        → 'unknown'
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_logger = logging.getLogger(__name__)

# ─── Константы ───────────────────────────────────────────────────────────────

# Символы, которые считаются "битыми" (replacement character и управляющие)
_BROKEN_CHARS_RE = re.compile(r'[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

# Минимальная длина текста для нормального качества
_MIN_TEXT_LEN = 50

# Порог кириллицы для определения языка
_CYRILLIC_RE = re.compile(r'[а-яёА-ЯЁ]')
_LATIN_RE = re.compile(r'[a-zA-Z]')


# ─── MetadataExtractor ───────────────────────────────────────────────────────

class MetadataExtractor:
    """
    Извлекает и вычисляет метаданные для текстового фрагмента.

    Использование:
        extractor = MetadataExtractor()
        meta = extractor.extract(
            text="Нейрон — это клетка нервной системы...",
            source="docs/нейрон.pdf",
            file_path="docs/нейрон.pdf",
            page=1,
            chunk_id=0,
        )
        # meta["quality"] → 0.8
        # meta["language"] → "ru"
    """

    def extract(
        self,
        text: str,
        source: str,
        file_path: Optional[str] = None,
        page: Optional[int] = None,
        chunk_id: int = 0,
        encoding: str = "utf-8",
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Вычислить метаданные для текстового фрагмента.

        Args:
            text:       текст фрагмента
            source:     строка-идентификатор источника (путь, URL, "user_input")
            file_path:  реальный путь к файлу (для file_size_kb)
            page:       номер страницы (для PDF)
            chunk_id:   порядковый номер чанка в документе
            encoding:   кодировка файла
            extra:      дополнительные поля (будут добавлены в metadata)

        Returns:
            dict с полями: source, ts, quality, language, file_size_kb,
                           encoding, page, chunk_id, warnings, ...
        """
        language = self.detect_language(text)
        quality, warnings = self.compute_quality(text, language)

        meta: Dict[str, Any] = {
            "source": source,
            "ts": datetime.now(timezone.utc).isoformat(),
            "quality": round(quality, 3),
            "language": language,
            "encoding": encoding,
            "chunk_id": chunk_id,
            "text_len": len(text),
            "warnings": warnings,
        }

        if page is not None:
            meta["page"] = page

        if file_path:
            try:
                meta["file_size_kb"] = round(os.path.getsize(file_path) / 1024, 2)
            except OSError:
                meta["file_size_kb"] = 0.0

        if extra:
            meta.update(extra)

        # Логируем предупреждения
        if warnings:
            _logger.warning(
                "MetadataExtractor: source='%s' chunk=%d quality=%.2f warnings=%s",
                source, chunk_id, quality, warnings,
            )

        return meta

    # ─── Определение языка ───────────────────────────────────────────────────

    @staticmethod
    def detect_language(text: str) -> str:
        """
        Определить язык текста по доле кириллических и латинских символов.

        Returns:
            'ru' | 'en' | 'mixed' | 'unknown'
        """
        if not text:
            return "unknown"

        cyrillic = len(_CYRILLIC_RE.findall(text))
        latin = len(_LATIN_RE.findall(text))
        total_letters = cyrillic + latin

        if total_letters == 0:
            return "unknown"

        cyr_ratio = cyrillic / total_letters
        lat_ratio = latin / total_letters

        if cyr_ratio > 0.6:
            return "ru"
        elif lat_ratio > 0.6:
            return "en"
        elif total_letters > 10:
            return "mixed"
        else:
            return "unknown"

    # ─── Оценка качества ─────────────────────────────────────────────────────

    @staticmethod
    def compute_quality(text: str, language: Optional[str] = None) -> tuple[float, list[str]]:
        """
        Вычислить quality score по эвристикам из спецификации.

        Компоненты:
          +0.3  длина > 50 символов
          +0.3  нет битых символов
          +0.2  язык определён (не 'unknown')
          +0.2  структура есть (есть переносы строк или несколько предложений)

        Returns:
            (quality: float 0.0–1.0, warnings: List[str])
        """
        warnings: list[str] = []
        score = 0.0

        if not text or not text.strip():
            return 0.0, ["empty_text"]

        stripped = text.strip()

        # +0.3: длина
        if len(stripped) >= _MIN_TEXT_LEN:
            score += 0.3
        else:
            warnings.append(f"short_text(len={len(stripped)})")

        # +0.3: нет битых символов
        broken = _BROKEN_CHARS_RE.findall(stripped)
        if not broken:
            score += 0.3
        else:
            warnings.append(f"broken_chars(count={len(broken)})")

        # +0.2: язык определён
        if language is None:
            language = MetadataExtractor.detect_language(stripped)
        if language != "unknown":
            score += 0.2
        else:
            warnings.append("language_unknown")

        # +0.2: структура (есть переносы строк или несколько предложений)
        has_newlines = "\n" in stripped
        sentence_count = len(re.findall(r'[.!?]+', stripped))
        if has_newlines or sentence_count >= 2:
            score += 0.2
        else:
            warnings.append("weak_structure")

        return round(min(score, 1.0), 3), warnings

    # ─── Классификация качества ──────────────────────────────────────────────

    @staticmethod
    def quality_label(quality: float) -> str:
        """
        Вернуть метку качества по числовому значению.

        Returns:
            'normal' | 'warning' | 'low_priority'
        """
        if quality >= 0.7:
            return "normal"
        elif quality >= 0.4:
            return "warning"
        else:
            return "low_priority"

    @staticmethod
    def should_reject(text: str) -> tuple[bool, str]:
        """
        Проверить, нужно ли жёстко отклонить контент (hard reject).

        Hard reject только для:
          - пустой текст
          - текст не извлёкся (None)
          - слишком мало осмысленного текста (< 10 символов после strip)

        Returns:
            (reject: bool, reason: str)
        """
        if text is None:
            return True, "text_is_none"
        if not text or not text.strip():
            return True, "empty_text"
        if len(text.strip()) < 10:
            return True, f"too_short(len={len(text.strip())})"
        return False, ""
