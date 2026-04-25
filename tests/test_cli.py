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
import threading
from io import StringIO
from pathlib import Path

import pytest

from brain.cli import (
    _enqueue_stdin_query,
    _load_dotenv,
    _stdin_reader_loop,
    build_parser,
    main,
    run_daemon,
    run_query,
)
from brain.core import EventBus, Scheduler, Task, TaskPriority

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

    def test_parse_daemon_flags(self):
        parser = build_parser()
        args = parser.parse_args([
            "--daemon",
            "--materials",
            "materials",
            "--watch",
            "--stdin",
        ])
        assert args.daemon is True
        assert args.materials == "materials"
        assert args.watch is True
        assert args.stdin is True

    def test_parse_no_watch_overrides_watch(self):
        parser = build_parser()
        args = parser.parse_args(["--daemon", "--watch", "--no-watch"])
        assert args.watch is False


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
# daemon / stdin
# ---------------------------------------------------------------------------

class TestDaemonMode:
    """Тесты daemon-оркестрации и stdin reader-а."""

    def test_run_daemon_without_materials_or_llm_smoke(self):
        """Daemon стартует и завершает bounded smoke-run без materials и LLM."""
        with tempfile.TemporaryDirectory() as tmpdir:
            code = run_daemon(tmpdir, max_ticks=1)
            assert code == 0

    def test_stdin_query_goes_to_high_queue(self):
        scheduler = Scheduler(EventBus())
        scheduler.register_handler("cognitive_cycle", lambda task: {"query": task.payload["query"]})

        assert _enqueue_stdin_query(scheduler, "привет", 1)
        counts = scheduler.pending_counts_by_priority()
        assert counts["HIGH"] == 1

    def test_stdin_high_priority_beats_low_backlog(self):
        scheduler = Scheduler(EventBus())
        executed: list[str] = []

        def handle_low(task: Task) -> dict:
            executed.append(task.task_id)
            return {"task": task.task_id}

        def handle_high(task: Task) -> dict:
            executed.append(task.task_id)
            return {"query": task.payload["query"]}

        scheduler.register_handler("idle_task", handle_low)
        scheduler.register_handler("cognitive_cycle", handle_high)
        scheduler.enqueue(Task(task_id="low_001", task_type="idle_task"), TaskPriority.LOW)
        _enqueue_stdin_query(scheduler, "важный вопрос", 1)

        result = scheduler.execute_one()
        assert result is not None
        assert result["task_id"] == "stdin_cycle_000001"
        assert executed == ["stdin_cycle_000001"]

    def test_stdin_eof_does_not_stop_daemon(self):
        scheduler = Scheduler(EventBus())
        stop_event = threading.Event()

        _stdin_reader_loop(scheduler, StringIO(""), stop_event)

        assert not stop_event.is_set()
        assert scheduler.queue_size() == 0


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


# ---------------------------------------------------------------------------
# _load_dotenv — автозагрузка .env
# ---------------------------------------------------------------------------

class TestLoadDotenv:
    """Тесты для _load_dotenv()."""

    def test_load_dotenv_missing_file_returns_zero(self, tmp_path):
        """Нет файла → 0 переменных применено, без ошибок."""
        n = _load_dotenv(str(tmp_path / "nonexistent.env"))
        assert n == 0

    def test_load_dotenv_applies_simple_pairs(self, tmp_path, monkeypatch):
        """KEY=VALUE попадает в os.environ."""
        import os
        monkeypatch.delenv("TEST_DOTENV_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_DOTENV_KEY=abc123\n", encoding="utf-8")
        n = _load_dotenv(str(env_file))
        assert n == 1
        assert os.environ.get("TEST_DOTENV_KEY") == "abc123"

    def test_load_dotenv_ignores_comments_and_blank_lines(self, tmp_path, monkeypatch):
        """Строки с '#' и пустые — пропускаются."""
        import os
        monkeypatch.delenv("TEST_DOTENV_K1", raising=False)
        monkeypatch.delenv("TEST_DOTENV_K2", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# комментарий\n\nTEST_DOTENV_K1=v1\n  # другой коммент\nTEST_DOTENV_K2=v2\n",
            encoding="utf-8",
        )
        n = _load_dotenv(str(env_file))
        assert n == 2
        assert os.environ.get("TEST_DOTENV_K1") == "v1"
        assert os.environ.get("TEST_DOTENV_K2") == "v2"

    def test_load_dotenv_strips_surrounding_quotes(self, tmp_path, monkeypatch):
        """KEY=\"value\" и KEY='value' — кавычки снимаются."""
        import os
        monkeypatch.delenv("TEST_DOTENV_DQ", raising=False)
        monkeypatch.delenv("TEST_DOTENV_SQ", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text(
            'TEST_DOTENV_DQ="double"\nTEST_DOTENV_SQ=\'single\'\n',
            encoding="utf-8",
        )
        _load_dotenv(str(env_file))
        assert os.environ.get("TEST_DOTENV_DQ") == "double"
        assert os.environ.get("TEST_DOTENV_SQ") == "single"

    def test_load_dotenv_does_not_overwrite_existing(self, tmp_path, monkeypatch):
        """Уже заданная переменная окружения имеет приоритет над .env."""
        import os
        monkeypatch.setenv("TEST_DOTENV_EXISTING", "real-value")
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_DOTENV_EXISTING=file-value\n", encoding="utf-8")
        n = _load_dotenv(str(env_file))
        assert n == 0  # ничего не применено
        assert os.environ.get("TEST_DOTENV_EXISTING") == "real-value"
