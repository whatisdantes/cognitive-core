"""
conftest.py — общая конфигурация pytest для cognitive-core.

Обеспечивает:
  - корректный sys.path (brain пакет доступен без PYTHONPATH хака)
  - общие fixtures для тестов
"""

import sys
import os
from pathlib import Path

# ── Гарантируем что корень проекта в sys.path ────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Fixtures ──────────────────────────────────────────────────────────────────

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Временная директория для JSON-файлов памяти."""
    data_dir = tmp_path / "memory"
    data_dir.mkdir()
    return str(data_dir)


@pytest.fixture
def sample_text_short():
    """Короткий русский текст для тестов perception."""
    return "Нейрон — это клетка нервной системы, передающая электрические сигналы."


@pytest.fixture
def sample_text_long():
    """Длинный русский текст (несколько абзацев) для тестов chunking."""
    paragraphs = [
        "Мозг человека содержит около 86 миллиардов нейронов. "
        "Каждый нейрон может образовывать тысячи синаптических связей с другими нейронами.",
        "Синапс — это место контакта между двумя нейронами. "
        "Через синапсы передаются электрические и химические сигналы.",
        "Гиппокамп играет ключевую роль в формировании новых воспоминаний. "
        "Повреждение гиппокампа приводит к антероградной амнезии.",
        "Префронтальная кора отвечает за планирование, принятие решений и контроль поведения. "
        "Она созревает последней — примерно к 25 годам.",
    ]
    return "\n\n".join(paragraphs)
