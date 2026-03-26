"""
brain/perception/validators.py

Валидация файловых путей и размеров для Perception Layer.

Защита от:
  - Path traversal (../../../etc/passwd)
  - Null bytes в пути (\x00)
  - Symlink escape (ссылка за пределы allowed dirs)
  - Слишком большие файлы (> MAX_FILE_SIZE_MB)

Использование:
    from brain.perception.validators import validate_file_path, check_file_size

    safe, reason = validate_file_path("/some/path/file.txt")
    ok, size_mb = check_file_size("/some/path/file.txt")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

_logger = logging.getLogger(__name__)

# ─── Константы ───────────────────────────────────────────────────────────────

MAX_FILE_SIZE_MB: float = 50.0
"""Максимальный размер файла в мегабайтах (по умолчанию)."""

# Опасные компоненты пути
_TRAVERSAL_PATTERNS = ("..", "..\\", "../")

# Null byte
_NULL_BYTE = "\x00"


# ─── Публичный API ───────────────────────────────────────────────────────────

def validate_file_path(
    file_path: str,
    allowed_dirs: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """
    Проверить безопасность файлового пути.

    Проверки:
      1. Null bytes в пути → reject
      2. Path traversal (.. компоненты) → reject
      3. Symlink escape (resolved path за пределами allowed_dirs) → reject
      4. Абсолютные пути к системным директориям → reject

    Args:
        file_path:    путь к файлу (строка)
        allowed_dirs: список разрешённых корневых директорий (опционально).
                      Если None — проверяется только traversal и null bytes.

    Returns:
        (safe: bool, reason: str) — True если путь безопасен, иначе причина отказа.
    """
    if not file_path:
        return False, "empty_path"

    # 1. Null bytes
    if _NULL_BYTE in file_path:
        _logger.warning("validators: null byte в пути: %r", file_path)
        return False, "null_byte_in_path"

    # 2. Path traversal — проверяем компоненты пути
    # Нормализуем путь для анализа
    normalized = os.path.normpath(file_path)

    # Проверяем каждый компонент пути на ".."
    parts = Path(normalized).parts
    if ".." in parts:
        _logger.warning("validators: path traversal обнаружен: %s", file_path)
        return False, "path_traversal"

    # Дополнительно: проверяем исходную строку на паттерны traversal
    # (до нормализации, чтобы поймать обфускацию)
    for pattern in _TRAVERSAL_PATTERNS:
        if pattern in file_path:
            _logger.warning(
                "validators: path traversal pattern '%s' в пути: %s",
                pattern, file_path,
            )
            return False, "path_traversal"

    # 3. Symlink escape — resolve и проверить что внутри allowed_dirs
    if allowed_dirs is not None:
        try:
            resolved = Path(file_path).resolve()
        except (OSError, ValueError) as e:
            _logger.warning("validators: не удалось resolve путь %s: %s", file_path, e)
            return False, f"resolve_error: {e}"

        resolved_str = str(resolved)
        in_allowed = False
        for allowed in allowed_dirs:
            try:
                allowed_resolved = str(Path(allowed).resolve())
            except (OSError, ValueError):
                continue
            if resolved_str.startswith(allowed_resolved):
                in_allowed = True
                break

        if not in_allowed:
            _logger.warning(
                "validators: путь %s (resolved: %s) за пределами allowed_dirs",
                file_path, resolved_str,
            )
            return False, "outside_allowed_dirs"

    # 4. Системные директории (базовая защита для Windows и Unix)
    _dangerous_prefixes = _get_dangerous_prefixes()
    normalized_lower = normalized.lower().replace("\\", "/")
    for prefix in _dangerous_prefixes:
        if normalized_lower.startswith(prefix):
            _logger.warning(
                "validators: путь к системной директории: %s",
                file_path,
            )
            return False, "system_directory"

    return True, ""


def check_file_size(
    file_path: str,
    max_mb: float = MAX_FILE_SIZE_MB,
) -> Tuple[bool, float]:
    """
    Проверить размер файла.

    Args:
        file_path: путь к файлу
        max_mb:    максимальный размер в мегабайтах (default: MAX_FILE_SIZE_MB)

    Returns:
        (ok: bool, size_mb: float) — True если размер допустим.
        Если файл не существует, возвращает (False, 0.0).
    """
    try:
        size_bytes = os.path.getsize(file_path)
    except OSError as e:
        _logger.warning("validators: не удалось получить размер файла %s: %s", file_path, e)
        return False, 0.0

    size_mb = size_bytes / (1024 * 1024)

    if size_mb > max_mb:
        _logger.warning(
            "validators: файл слишком большой: %s (%.1f MB > %.1f MB)",
            file_path, size_mb, max_mb,
        )
        return False, round(size_mb, 2)

    return True, round(size_mb, 2)


# ─── Вспомогательные ─────────────────────────────────────────────────────────

def _get_dangerous_prefixes() -> List[str]:
    """
    Список опасных системных префиксов (нормализованных, lowercase, forward slash).
    """
    prefixes = [
        "/etc/",
        "/proc/",
        "/sys/",
        "/dev/",
        "/boot/",
        "/root/",
        "/var/log/",
    ]
    # Windows
    if os.name == "nt":
        prefixes.extend([
            "c:/windows/",
            "c:/windows/system32/",
            "c:/program files/",
            "c:/program files (x86)/",
        ])
    return prefixes
