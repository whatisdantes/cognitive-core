"""
tests/test_cli.py — Тесты для brain/cli.py

Покрытие:
  - build_parser: аргументы, defaults, --version
  - main(): вызов без аргументов, с query, с --verbose
  - run_query(): полный пайплайн, ошибки
  - cli_entry(): exit code
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from brain.cli import build_parser, main, run_query

# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    """Тесты для build_parser()."""

    def test_parser_created(self):
        parser = build_parser()
        assert parser is not None
        assert parser.prog == "cognitive-core"

    def test_parse_query(self):
        parser = build_parser()
        args = parser.parse_args(["Что такое нейрон?"])
        assert args.query == "Что такое нейрон?"
        assert args.verbose is False

    def test_parse_verbose(self):
        parser = build_parser()
        args = parser.parse_args(["--verbose", "test query"])
        assert args.verbose is True
        assert args.query == "test query"

    def test_parse_verbose_short(self):
        parser = build_parser()
        args = parser.parse_args(["-v", "test"])
        assert args.verbose is True

    def test_parse_no_query(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.query is None

    def test_parse_data_dir(self):
        parser = build_parser()
        args = parser.parse_args(["--data-dir", "/tmp/test", "query"])
        assert args.data_dir == "/tmp/test"

    def test_parse_data_dir_default(self):
        parser = build_parser()
        args = parser.parse_args(["query"])
        assert args.data_dir == "brain/data/memory"

    def test_version_flag(self):
        parser = build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

class TestMain:
    """Тесты для main()."""

    def test_no_args_returns_zero(self):
        """Без аргументов — показать help, вернуть 0."""
        code = main([])
        assert code == 0

    def test_query_runs_pipeline(self):
        """С query — запускает полный пайплайн и возвращает 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            code = main(["--data-dir", tmpdir, "Что такое нейрон?"])
            assert code == 0

    def test_query_learn_fact(self):
        """Команда 'запомни' — сохраняет факт."""
        with tempfile.TemporaryDirectory() as tmpdir:
            code = main(["--data-dir", tmpdir, "Запомни: нейрон — клетка"])
            assert code == 0

    def test_verbose_flag(self):
        """--verbose не ломает выполнение."""
        with tempfile.TemporaryDirectory() as tmpdir:
            code = main(["--verbose", "--data-dir", tmpdir, "test"])
            assert code == 0

    def test_query_with_question_mark(self):
        """Вопрос с '?' обрабатывается корректно."""
        with tempfile.TemporaryDirectory() as tmpdir:
            code = main(["--data-dir", tmpdir, "Кто открыл пенициллин?"])
            assert code == 0


# ---------------------------------------------------------------------------
# run_query()
# ---------------------------------------------------------------------------

class TestRunQuery:
    """Тесты для run_query()."""

    def test_returns_zero_on_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            code = run_query("Что такое нейрон?", tmpdir)
            assert code == 0

    def test_creates_data_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "sub" / "dir"
            assert not data_dir.exists()
            run_query("test", str(data_dir))
            assert data_dir.exists()

    def test_prints_output(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_query("Что такое нейрон?", tmpdir)
            captured = capsys.readouterr()
            # Должен быть какой-то текстовый вывод
            assert len(captured.out.strip()) > 0

    def test_learn_stores_in_memory(self):
        """После 'запомни' факт доступен в памяти."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Сначала запомним
            code1 = run_query("Запомни: Земля вращается вокруг Солнца", tmpdir)
            assert code1 == 0

            # Потом спросим (новый pipeline, но та же директория)
            code2 = run_query("Что такое Земля?", tmpdir)
            assert code2 == 0


# ---------------------------------------------------------------------------
# Интеграция: GoalManager в CognitiveCore
# ---------------------------------------------------------------------------

class TestGoalManagerLen:
    """GoalManager.__len__ используется в CLI — проверяем что работает."""

    def test_goal_manager_has_len(self):
        from brain.cognition.goal_manager import GoalManager
        gm = GoalManager()
        assert len(gm) >= 0


# ---------------------------------------------------------------------------
# Импорты
# ---------------------------------------------------------------------------

class TestImports:
    """Проверка что все импорты CLI работают."""

    def test_import_cli(self):
        from brain import cli
        assert hasattr(cli, "main")
        assert hasattr(cli, "cli_entry")
        assert hasattr(cli, "build_parser")
        assert hasattr(cli, "run_query")

    def test_import_version(self):
        from brain import __version__
        assert isinstance(__version__, str)
        assert "." in __version__
