"""
brain/core/text_utils.py — Канонические текстовые утилиты.

Phase C: Critical DRY — единственный источник истины для:
  - detect_language(text)      — определение языка по соотношению кириллицы/латиницы
  - parse_fact_pattern(text)   — структурный парсинг факта из текста ("X это Y")

Эти функции ранее дублировались в:
  - brain/perception/metadata_extractor.py
  - brain/encoders/text_encoder.py
  - brain/output/dialogue_responder.py
  - brain/output/response_validator.py
  - brain/memory/consolidation_engine.py
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# ─── Константы ───────────────────────────────────────────────────────────────

_CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")
_LATIN_RE = re.compile(r"[a-zA-Z]")


# ─── detect_language ─────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """
    Определить язык текста по соотношению кириллических и латинских символов.

    Пороги:
      > 60% кириллицы → 'ru'
      > 60% латиницы  → 'en'
      > 10 букв, но ни одна группа не доминирует → 'mixed'
      нет букв или текст пустой → 'unknown'

    Args:
        text: входной текст

    Returns:
        'ru' | 'en' | 'mixed' | 'unknown'
    """
    if not text or not text.strip():
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
    if lat_ratio > 0.6:
        return "en"
    if total_letters > 10:
        return "mixed"
    return "unknown"


# ─── parse_fact_pattern ──────────────────────────────────────────────────────

def parse_fact_pattern(text: str) -> Optional[Tuple[str, str]]:
    """
    Извлечь структурированный факт из текста.

    Ищет паттерны:
      - "X это Y"
      - "X — Y"
      - "X - Y"
      - "X: Y"
      - "X is Y"
      - "X are Y"
      - "X means Y"

    Ограничения:
      - concept: 2–50 символов
      - description: >= 5 символов
      - text: 5–500 символов

    Функция отвечает только за структурный парсинг, без побочных эффектов
    и без нормализации сверх необходимого минимума.

    Args:
        text: входной текст

    Returns:
        (concept, description) или None если паттерн не найден
    """
    text = text.strip()
    if len(text) < 5 or len(text) > 500:
        return None

    # Паттерны на русском (порядок важен: " это " до " — ")
    for sep in [" это ", " — ", " - ", ": "]:
        if sep in text:
            parts = text.split(sep, 1)
            if len(parts) == 2:
                concept = parts[0].strip()
                description = parts[1].strip()
                if 2 <= len(concept) <= 50 and len(description) >= 5:
                    return concept, description

    # Паттерны на английском
    for sep in [" is ", " are ", " means "]:
        if sep in text.lower():
            idx = text.lower().find(sep)
            concept = text[:idx].strip()
            description = text[idx + len(sep):].strip()
            if 2 <= len(concept) <= 50 and len(description) >= 5:
                return concept, description

    return None
