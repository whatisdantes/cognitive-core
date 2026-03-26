"""
test_perception_hardening.py — Тесты B.2: Perception Hardening.

Тестирует:
  1. validators.py — validate_file_path, check_file_size
  2. Интеграция в InputRouter — path traversal, file size
  3. Интеграция в TextIngestor — path traversal, file size

Запуск:
    pytest tests/test_perception_hardening.py -v
"""

from __future__ import annotations

import os
import textwrap

import pytest

from brain.perception.validators import (
    MAX_FILE_SIZE_MB,
    check_file_size,
    validate_file_path,
)
from brain.perception.input_router import InputRouter
from brain.perception.text_ingestor import TextIngestor


# ═══════════════════════════════════════════════════════════════════════════════
# 1. validate_file_path — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidateFilePath:
    """Тесты для validate_file_path()."""

    # --- Нормальные пути ---

    def test_normal_relative_path(self):
        safe, reason = validate_file_path("docs/readme.txt")
        assert safe is True
        assert reason == ""

    def test_normal_absolute_path(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        safe, reason = validate_file_path(str(f))
        assert safe is True

    def test_normal_path_with_dots_in_name(self):
        safe, reason = validate_file_path("docs/file.v2.0.txt")
        assert safe is True

    # --- Null bytes ---

    def test_null_byte_rejects(self):
        safe, reason = validate_file_path("docs/file\x00.txt")
        assert safe is False
        assert reason == "null_byte_in_path"

    def test_null_byte_in_middle(self):
        safe, reason = validate_file_path("docs\x00/secret.txt")
        assert safe is False
        assert reason == "null_byte_in_path"

    # --- Path traversal ---

    def test_traversal_dotdot_unix(self):
        safe, reason = validate_file_path("../../../etc/passwd")
        assert safe is False
        assert reason == "path_traversal"

    def test_traversal_dotdot_windows(self):
        safe, reason = validate_file_path("..\\..\\..\\windows\\system32\\config")
        assert safe is False
        assert reason == "path_traversal"

    def test_traversal_mixed(self):
        safe, reason = validate_file_path("docs/../../secret.txt")
        assert safe is False
        assert reason == "path_traversal"

    def test_traversal_encoded_dotdot(self):
        # Прямой ".." в пути
        safe, reason = validate_file_path("docs/../../../etc/shadow")
        assert safe is False
        assert reason == "path_traversal"

    # --- Empty path ---

    def test_empty_path(self):
        safe, reason = validate_file_path("")
        assert safe is False
        assert reason == "empty_path"

    # --- allowed_dirs ---

    def test_allowed_dirs_inside(self, tmp_path):
        f = tmp_path / "safe" / "file.txt"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("data")
        safe, reason = validate_file_path(str(f), allowed_dirs=[str(tmp_path)])
        assert safe is True

    def test_allowed_dirs_outside(self, tmp_path):
        # Создаём файл вне allowed_dirs
        other = tmp_path / "other"
        other.mkdir(exist_ok=True)
        f = other / "file.txt"
        f.write_text("data")

        allowed = tmp_path / "safe"
        allowed.mkdir(exist_ok=True)

        safe, reason = validate_file_path(str(f), allowed_dirs=[str(allowed)])
        assert safe is False
        assert reason == "outside_allowed_dirs"

    # --- System directories ---

    def test_system_dir_etc(self):
        safe, reason = validate_file_path("/etc/passwd")
        assert safe is False
        assert reason == "system_directory"

    def test_system_dir_proc(self):
        safe, reason = validate_file_path("/proc/self/environ")
        assert safe is False
        assert reason == "system_directory"

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_system_dir_windows(self):
        safe, reason = validate_file_path("C:\\Windows\\System32\\config\\SAM")
        assert safe is False
        assert reason == "system_directory"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. check_file_size — unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckFileSize:
    """Тесты для check_file_size()."""

    def test_small_file_ok(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_text("hello world")
        ok, size_mb = check_file_size(str(f))
        assert ok is True
        assert size_mb >= 0.0

    def test_large_file_rejected(self, tmp_path):
        f = tmp_path / "large.txt"
        # Создаём файл > 50 MB (пишем 51 MB нулей)
        with open(f, "wb") as fh:
            fh.seek(51 * 1024 * 1024)
            fh.write(b"\0")
        ok, size_mb = check_file_size(str(f))
        assert ok is False
        assert size_mb > 50.0

    def test_custom_max_mb(self, tmp_path):
        f = tmp_path / "medium.txt"
        # 2 MB файл
        with open(f, "wb") as fh:
            fh.write(b"x" * (2 * 1024 * 1024))
        ok, size_mb = check_file_size(str(f), max_mb=1.0)
        assert ok is False
        assert size_mb > 1.0

    def test_nonexistent_file(self):
        ok, size_mb = check_file_size("/nonexistent/file.txt")
        assert ok is False
        assert size_mb == 0.0

    def test_exact_limit(self, tmp_path):
        f = tmp_path / "exact.txt"
        # Файл ровно 1 MB
        with open(f, "wb") as fh:
            fh.write(b"x" * (1024 * 1024))
        ok, size_mb = check_file_size(str(f), max_mb=1.0)
        assert ok is True  # ровно на границе — допустимо

    def test_default_max_is_50mb(self):
        assert MAX_FILE_SIZE_MB == 50.0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. InputRouter integration — hardening
# ═══════════════════════════════════════════════════════════════════════════════

class TestInputRouterHardening:
    """Тесты интеграции validators в InputRouter."""

    def test_route_file_path_traversal_rejected(self):
        router = InputRouter(dedup=False)
        events = router.route_file("../../../etc/passwd")
        assert events == []
        stats = router.stats()
        assert stats["hard_rejected"] >= 1

    def test_route_file_null_byte_rejected(self):
        router = InputRouter(dedup=False)
        events = router.route_file("docs/file\x00.txt")
        assert events == []
        stats = router.stats()
        assert stats["hard_rejected"] >= 1

    def test_route_file_large_file_rejected(self, tmp_path):
        """Файл > 50 MB отклоняется."""
        large = tmp_path / "huge.txt"
        with open(large, "wb") as f:
            f.seek(51 * 1024 * 1024)
            f.write(b"\0")
        router = InputRouter(dedup=False)
        events = router.route_file(str(large))
        assert events == []
        stats = router.stats()
        assert stats["hard_rejected"] >= 1

    def test_route_file_normal_file_passes(self, tmp_path):
        """Нормальный файл проходит валидацию."""
        normal = tmp_path / "normal.txt"
        content = textwrap.dedent("""
            Нейрон — это основная клетка нервной системы.
            Нейроны передают электрические и химические сигналы.

            Существует несколько типов нейронов: сенсорные, моторные и вставочные.
            Каждый нейрон состоит из тела клетки, аксона и дендритов.
        """).strip()
        normal.write_text(content, encoding="utf-8")
        router = InputRouter(dedup=False)
        events = router.route_file(str(normal))
        assert len(events) > 0

    def test_route_file_system_dir_rejected(self):
        router = InputRouter(dedup=False)
        events = router.route_file("/etc/shadow")
        assert events == []


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TextIngestor integration — hardening
# ═══════════════════════════════════════════════════════════════════════════════

class TestTextIngestorHardening:
    """Тесты интеграции validators в TextIngestor."""

    def test_ingest_path_traversal_rejected(self):
        ingestor = TextIngestor()
        events = ingestor.ingest("../../../etc/passwd")
        assert events == []

    def test_ingest_null_byte_rejected(self):
        ingestor = TextIngestor()
        events = ingestor.ingest("docs/file\x00.txt")
        assert events == []

    def test_ingest_large_file_rejected(self, tmp_path):
        large = tmp_path / "huge.txt"
        with open(large, "wb") as f:
            f.seek(51 * 1024 * 1024)
            f.write(b"\0")
        ingestor = TextIngestor()
        events = ingestor.ingest(str(large))
        assert events == []

    def test_ingest_normal_file_passes(self, tmp_path):
        normal = tmp_path / "normal.txt"
        content = textwrap.dedent("""
            Нейрон — это основная клетка нервной системы.
            Нейроны передают электрические и химические сигналы.

            Существует несколько типов нейронов: сенсорные, моторные и вставочные.
            Каждый нейрон состоит из тела клетки, аксона и дендритов.
        """).strip()
        normal.write_text(content, encoding="utf-8")
        ingestor = TextIngestor()
        events = ingestor.ingest(str(normal))
        assert len(events) > 0

    def test_ingest_text_not_affected(self):
        """ingest_text() не затронут файловой валидацией."""
        ingestor = TextIngestor()
        text = "Нейрон — это основная клетка нервной системы. Нейроны передают сигналы."
        events = ingestor.ingest_text(text, source="test")
        # Может быть 0 из-за short text, но не из-за path validation
        # Просто проверяем что не крашится
        assert isinstance(events, list)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Импорт через brain.perception
# ═══════════════════════════════════════════════════════════════════════════════

class TestPerceptionExports:
    """Проверка экспорта validators через brain.perception."""

    def test_import_validate_file_path(self):
        from brain.perception import validate_file_path as vfp
        assert callable(vfp)

    def test_import_check_file_size(self):
        from brain.perception import check_file_size as cfs
        assert callable(cfs)

    def test_import_max_file_size_mb(self):
        from brain.perception import MAX_FILE_SIZE_MB as max_mb
        assert max_mb == 50.0
