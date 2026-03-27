"""
brain/core/hash_utils.py — Канонические хеш-утилиты.

Phase C: Critical DRY — единственный источник истины для:
  - sha256_text(text, truncate)  — SHA256 хеш строки
  - sha256_file(path, truncate)  — SHA256 хеш файла

Эти функции ранее дублировались в:
  - brain/encoders/text_encoder.py      (_sha256 — полный hex)
  - brain/perception/input_router.py    (_sha256 — truncate=16, _sha256_file)
"""

from __future__ import annotations

import hashlib
from typing import Optional


def sha256_text(text: str, truncate: Optional[int] = None) -> str:
    """
    SHA256 хеш текстовой строки.

    Args:
        text:     входной текст (кодируется в UTF-8)
        truncate: если задано — обрезать hex-digest до N символов.
                  None → полный hex (64 символа).

    Returns:
        hex-digest строка (полная или обрезанная)
    """
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    if truncate is not None and truncate > 0:
        return digest[:truncate]
    return digest


def sha256_file(path: str, truncate: int = 16) -> str:
    """
    SHA256 хеш файла (читает блоками по 64KB).

    При ошибке чтения (OSError) — fallback на хеш от пути файла.
    Это сохраняет семантику дедупликации: даже если файл недоступен,
    один и тот же путь всегда даёт один и тот же хеш.

    Args:
        path:     путь к файлу
        truncate: обрезать hex-digest до N символов (default: 16)

    Returns:
        hex-digest строка (обрезанная до truncate символов)
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        digest = h.hexdigest()
    except OSError:
        # Fallback: хеш от пути (сохраняем стабильность дедупликации)
        digest = hashlib.sha256(path.encode("utf-8", errors="replace")).hexdigest()

    if truncate > 0:
        return digest[:truncate]
    return digest
