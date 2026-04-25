"""
brain/cli.py — CLI entrypoint для cognitive-core.

Использование:
    cognitive-core "Что такое нейропластичность?"
    cognitive-core "Запомни: солнце встает на востоке"
    cognitive-core --verbose "вопрос"
    cognitive-core --autonomous --ticks 20
    cognitive-core --version
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from types import FrameType
from typing import Any, Callable, TextIO

from brain import __version__
from brain.bridges.llm_bridge import BLACKBOX_DEFAULT_MODEL, LLMBridge, LLMProvider
from brain.bridges.llm_budget import LLMRateLimitConfig, LLMRateLimiter
from brain.bridges.safety_wrapper import LLMSafetyWrapper
from brain.cognition.cognitive_core import CognitiveCore
from brain.cognition.context import PolicyConstraints
from brain.core.contracts import DaemonConfig, Task
from brain.core.event_bus import EventBus
from brain.core.resource_monitor import ResourceMonitor, ResourceMonitorConfig
from brain.core.scheduler import Scheduler, SchedulerConfig, TaskPriority
from brain.learning import KnowledgeGapDetector, ReplayEngine
from brain.logging import BrainLogger, DigestGenerator, TraceBuilder
from brain.memory.memory_manager import MemoryManager
from brain.motivation import CuriosityEngine, IdleDispatcher, IdleDispatcherConfig, MotivationEngine
from brain.output.dialogue_responder import OutputPipeline
from brain.perception import FileWatcher, FileWatcherConfig, MaterialIngestor

logger = logging.getLogger(__name__)

_SignalHandler = Callable[[int, FrameType | None], Any] | int | signal.Handlers | None


def build_parser() -> argparse.ArgumentParser:
    """Построить argparse parser."""
    parser = argparse.ArgumentParser(
        prog="cognitive-core",
        description="cognitive-core — искусственный когнитивный мозг (text-only MVP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            '  cognitive-core "Что такое нейрон?"\n'
            '  cognitive-core --verbose "Запомни: нейрон — клетка"\n'
            '  cognitive-core --llm-provider blackbox --llm-api-key KEY "Что такое синапс?"\n'
            "  cognitive-core --version\n"
        ),
    )

    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Текстовый запрос к когнитивному ядру",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"cognitive-core {__version__}",
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Подробный вывод (DEBUG logging)",
    )

    parser.add_argument(
        "--data-dir",
        default="brain/data/memory",
        help="Директория данных памяти (по умолчанию: brain/data/memory)",
    )

    parser.add_argument(
        "--autonomous",
        action="store_true",
        default=False,
        help="Автономный режим: Scheduler управляет когнитивными циклами",
    )

    parser.add_argument(
        "--daemon",
        action="store_true",
        default=False,
        help="Long-running daemon: материалы, watcher, stdin и idle-работа в одном процессе",
    )

    parser.add_argument(
        "--materials",
        default=None,
        metavar="DIR",
        help="Директория материалов для startup scan и watcher в daemon-режиме",
    )

    parser.add_argument(
        "--watch",
        dest="watch",
        action="store_true",
        default=False,
        help="Включить polling watcher для --materials в daemon-режиме",
    )

    parser.add_argument(
        "--no-watch",
        dest="watch",
        action="store_false",
        help="Отключить watcher, оставив только startup scan материалов",
    )

    parser.add_argument(
        "--stdin",
        action="store_true",
        default=False,
        help="Читать пользовательские запросы из stdin и ставить их в HIGH queue",
    )

    parser.add_argument(
        "--ticks",
        type=int,
        default=10,
        metavar="N",
        help="Количество тиков в автономном режиме (0 = бесконечно, по умолчанию: 10)",
    )

    # --- LLM Bridge (Этап N) ---
    parser.add_argument(
        "--llm-provider",
        default=None,
        choices=["openai", "anthropic", "blackbox", "mock"],
        metavar="PROVIDER",
        help="LLM провайдер: openai | anthropic | blackbox | mock (по умолчанию: нет LLM)",
    )

    parser.add_argument(
        "--llm-api-key",
        default=None,
        metavar="KEY",
        help=(
            "API ключ для LLM провайдера. Если не указан — берётся из переменных "
            "окружения OPENAI_API_KEY / ANTHROPIC_API_KEY / BLACKBOX_API_KEY "
            "(также подгружается из .env в текущей директории)"
        ),
    )

    parser.add_argument(
        "--llm-model",
        default=None,
        metavar="MODEL",
        help=(
            "Модель LLM провайдера "
            f"(openai: gpt-4o-mini, anthropic: claude-3-haiku-20240307, blackbox: {BLACKBOX_DEFAULT_MODEL})"
        ),
    )

    # --- BrainLogger (Этап C) ---
    parser.add_argument(
        "--log-dir",
        default=None,
        metavar="DIR",
        help=(
            "Директория для JSONL-логов BrainLogger "
            "(по умолчанию: не логировать; пример: brain/data/logs)"
        ),
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
        metavar="LEVEL",
        help="Минимальный уровень BrainLogger: DEBUG|INFO|WARN|ERROR|CRITICAL (по умолчанию: INFO)",
    )

    return parser


def setup_logging(verbose: bool = False) -> None:
    """Настроить логирование."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


# Предустановленные запросы для автономного режима
_AUTONOMOUS_QUERIES: list[str] = [
    "Что такое нейропластичность?",
    "Как работает рабочая память?",
    "Что такое когнитивный цикл?",
    "Как устроена семантическая память?",
    "Что такое эпизодическая память?",
]


# Сопоставление провайдера и имени переменной окружения с API ключом.
_ENV_KEY_BY_PROVIDER: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "blackbox": "BLACKBOX_API_KEY",
}


def _load_dotenv(path: str = ".env") -> int:
    """
    Загрузить переменные из .env в os.environ.

    Формат: `KEY=VALUE` по одной переменной на строку; строки, начинающиеся
    с '#', и пустые — игнорируются; вокруг значения опционально `"..."` / `'...'`.
    Переменные, уже заданные в реальном окружении, не перезаписываются — таким
    образом `export BLACKBOX_API_KEY=...` имеет приоритет над .env.

    Возвращает количество применённых переменных. Ошибки чтения/парсинга
    проглатываются (graceful degradation — .env опционален).
    """
    applied = 0
    try:
        p = Path(path)
        if not p.is_file():
            return 0
        for raw in p.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
                applied += 1
    except OSError:
        return applied
    return applied


def _build_llm_provider(
    provider_name: str | None,
    api_key: str | None,
    model: str | None,
) -> LLMProvider | None:
    """
    Создать LLM провайдера по имени и параметрам.

    Приоритет API ключа: --llm-api-key > переменная окружения (см.
    `_ENV_KEY_BY_PROVIDER`) > ничего (провайдер не создаётся, WARNING).
    Возвращает LLMSafetyWrapper(provider) или None если провайдер не указан.
    Ошибки импорта (нет openai/anthropic) логируются как WARNING.
    """
    if not provider_name:
        return None

    if not api_key and provider_name in _ENV_KEY_BY_PROVIDER:
        api_key = os.environ.get(_ENV_KEY_BY_PROVIDER[provider_name]) or None

    try:
        if provider_name == "mock":
            from brain.bridges.llm_bridge import MockProvider  # type: ignore[attr-defined]
            raw = MockProvider()
            bridge = LLMBridge(provider=raw)
            wrapped = LLMSafetyWrapper(bridge=bridge)
            logger.info("[CLI] LLM провайдер: mock")
            return wrapped
        if provider_name == "openai":
            if not api_key:
                logger.warning(
                    "[CLI] LLM провайдер 'openai' требует api_key (передайте --llm-api-key)"
                )
                return None
            from brain.bridges.llm_bridge import OpenAIProvider  # type: ignore[attr-defined]
            raw = OpenAIProvider(  # type: ignore[assignment]
                api_key=api_key,
                model=model or "gpt-4o-mini",
            )
            bridge = LLMBridge(provider=raw)
            wrapped = LLMSafetyWrapper(bridge=bridge)
            logger.info("[CLI] LLM провайдер: %s (модель=%s)", provider_name, model)
            return wrapped
        if provider_name == "anthropic":
            if not api_key:
                logger.warning(
                    "[CLI] LLM провайдер 'anthropic' требует api_key (передайте --llm-api-key)"
                )
                return None
            from brain.bridges.llm_bridge import AnthropicProvider  # type: ignore[attr-defined]
            raw = AnthropicProvider(  # type: ignore[assignment]
                api_key=api_key,
                model=model or "claude-3-haiku-20240307",
            )
            bridge = LLMBridge(provider=raw)
            wrapped = LLMSafetyWrapper(bridge=bridge)
            logger.info("[CLI] LLM провайдер: %s (модель=%s)", provider_name, model)
            return wrapped
        if provider_name == "blackbox":
            if not api_key:
                logger.warning(
                    "[CLI] LLM провайдер 'blackbox' требует api_key (передайте --llm-api-key)"
                )
                return None
            from brain.bridges.llm_bridge import BlackboxProvider  # type: ignore[attr-defined]
            raw = BlackboxProvider(  # type: ignore[assignment]
                api_key=api_key,
                model=model or BLACKBOX_DEFAULT_MODEL,
            )
            bridge = LLMBridge(provider=raw)
            wrapped = LLMSafetyWrapper(bridge=bridge)
            logger.info("[CLI] LLM провайдер: %s (модель=%s)", provider_name, model or BLACKBOX_DEFAULT_MODEL)
            return wrapped
        logger.warning("[CLI] Неизвестный LLM провайдер: %s", provider_name)
        return None

    except ImportError as e:
        logger.warning(
            "[CLI] LLM провайдер '%s' недоступен (нет зависимости): %s",
            provider_name, e,
        )
        print(
            f"Предупреждение: LLM провайдер '{provider_name}' недоступен. "
            f"Установите: pip install cognitive-core[{provider_name}]",
            file=sys.stderr,
        )
        return None
    except Exception as e:
        logger.warning("[CLI] Ошибка создания LLM провайдера: %s", e)
        return None


def _enqueue_stdin_query(
    scheduler: Scheduler,
    query: str,
    counter: int,
    *,
    session_id: str = "daemon_stdin",
) -> bool:
    """Поставить строку stdin в HIGH queue daemon-а."""
    text = query.strip()
    if not text:
        return False
    task_id = f"stdin_cycle_{counter:06d}"
    task = Task(
        task_id=task_id,
        task_type="cognitive_cycle",
        payload={"query": text, "source": "stdin"},
        priority=float(TaskPriority.HIGH),
        trace_id=task_id,
        session_id=session_id,
    )
    return scheduler.enqueue(task, TaskPriority.HIGH)


def _stdin_reader_loop(
    scheduler: Scheduler,
    stream: TextIO,
    stop_event: threading.Event,
    *,
    session_id: str = "daemon_stdin",
) -> None:
    """
    Читать stdin до EOF и enqueue-ить непустые строки.

    EOF завершает только stdin-reader: сам daemon продолжает жить за счёт watcher/idle.
    """
    counter = 0
    while not stop_event.is_set():
        line = stream.readline()
        if line == "":
            return
        counter += 1
        _enqueue_stdin_query(
            scheduler,
            line,
            counter,
            session_id=session_id,
        )


def _start_stdin_reader(
    scheduler: Scheduler,
    stop_event: threading.Event,
    *,
    stream: TextIO | None = None,
    session_id: str = "daemon_stdin",
) -> threading.Thread:
    """Запустить daemon-thread чтения stdin."""
    thread = threading.Thread(
        target=_stdin_reader_loop,
        args=(scheduler, stream or sys.stdin, stop_event),
        kwargs={"session_id": session_id},
        name="cognitive-core-stdin",
        daemon=True,
    )
    thread.start()
    return thread


def _install_daemon_signal_handlers(
    stop_event: threading.Event,
    stop_scheduler: Callable[[], None],
) -> dict[int, _SignalHandler]:
    """Подключить SIGINT/SIGTERM к graceful shutdown daemon-а."""
    previous: dict[int, _SignalHandler] = {}

    def _request_stop(signum: int, frame: FrameType | None) -> None:
        del signum, frame
        stop_event.set()
        stop_scheduler()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            previous[int(sig)] = signal.getsignal(sig)
            signal.signal(sig, _request_stop)
        except (OSError, ValueError):
            continue
    return previous


def _restore_daemon_signal_handlers(previous: dict[int, _SignalHandler]) -> None:
    """Вернуть signal handlers после выхода daemon-а."""
    for sig_value, handler in previous.items():
        try:
            signal.signal(sig_value, handler)
        except (OSError, ValueError):
            continue


def run_daemon(
    data_dir: str,
    *,
    materials_dir: str | None = None,
    watch: bool = False,
    stdin_enabled: bool = False,
    llm_provider: LLMProvider | None = None,
    log_dir: str | None = None,
    log_level: str = "INFO",
    config: DaemonConfig | None = None,
    max_ticks: int | None = None,
    stdin_stream: TextIO | None = None,
) -> int:
    """
    Запустить long-running daemon с material ingestion, watcher, stdin и idle-работой.

    `max_ticks` используется тестами/smoke-run; CLI по умолчанию работает до SIGINT/SIGTERM.
    """
    daemon_config = config or DaemonConfig()
    brain_log: BrainLogger | None = None
    if log_dir:
        brain_log = BrainLogger(log_dir=log_dir, min_level=log_level)
        logger.info("[CLI] BrainLogger активирован: log_dir=%s level=%s", log_dir, log_level)

    trace_builder = TraceBuilder()
    digest_gen = DigestGenerator()
    llm_rate_limiter = LLMRateLimiter(
        LLMRateLimitConfig(llm_calls_per_hour=daemon_config.llm_calls_per_hour)
    )
    stop_event = threading.Event()
    stdin_thread: threading.Thread | None = None
    previous_handlers: dict[int, _SignalHandler] = {}

    bus = EventBus()
    rm = ResourceMonitor(bus, ResourceMonitorConfig(sample_interval_s=10.0))

    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    mm = MemoryManager(data_dir=str(data_path))
    mm.start()
    rm.start()

    try:
        policy = PolicyConstraints()
        replay_engine = ReplayEngine(memory=mm)
        core = CognitiveCore(
            memory_manager=mm,  # type: ignore[arg-type]
            event_bus=bus,
            resource_monitor=rm,
            policy=policy,
            llm_provider=llm_provider,
            llm_rate_limiter=llm_rate_limiter,
            brain_logger=brain_log,
            trace_builder=trace_builder,
            digest_gen=digest_gen,
        )
        gap_detector = core.gap_detector or KnowledgeGapDetector(memory=mm)
        curiosity_engine = CuriosityEngine(
            semantic_memory=mm.semantic,
            gap_detector=gap_detector,
        )
        motivation_engine = MotivationEngine(replay_engine=replay_engine)
        output_pipeline = OutputPipeline(
            hedge_threshold=policy.hedge_threshold,
            brain_logger=brain_log,
            source_memory=mm.source,
        )
        scheduler = Scheduler(
            bus,
            SchedulerConfig(
                session_id="daemon",
                max_low_queue_backlog=8,
            ),
            brain_logger=brain_log,
        )
        idle_dispatcher = IdleDispatcher(
            scheduler=scheduler,
            llm_rate_limiter=llm_rate_limiter,
            memory=mm,
            gap_detector=gap_detector,
            curiosity_engine=curiosity_engine,
            motivation_engine=motivation_engine,
            config=IdleDispatcherConfig(max_low_queue_backlog=8),
            brain_logger=brain_log,
        )

        material_ingestor: MaterialIngestor | None = None
        watcher: FileWatcher | None = None
        if materials_dir:
            material_ingestor = MaterialIngestor(
                memory=mm,
                llm_provider=llm_provider,
                llm_rate_limiter=llm_rate_limiter,
                brain_logger=brain_log,
            )
            if watch:
                watcher = FileWatcher(
                    scheduler=scheduler,
                    config=FileWatcherConfig(watch_dir=materials_dir),
                    brain_logger=brain_log,
                )

        def _resource_provider():
            try:
                return rm.snapshot()
            except Exception:
                return None

        def handle_cognitive_cycle(task: Task) -> dict:
            """Обработчик пользовательского когнитивного цикла."""
            query = str(task.payload.get("query", "") or "Что нового в памяти?")
            result = core.run(query, session_id=task.session_id or "daemon")
            output = output_pipeline.process(result)
            print(f"[daemon] {output.text}")
            return {
                "action": result.action,
                "confidence": result.confidence,
                "cycle": core.cycle_count,
                "source": task.payload.get("source", "daemon"),
            }

        def handle_ingest_file(task: Task) -> dict:
            """Обработчик watcher-задачи ingest_file."""
            if material_ingestor is None:
                return {"status": "skipped", "reason": "no_material_ingestor"}
            return material_ingestor.handle_ingest_file_task(task)

        def handle_poll_materials(task: Task) -> dict:
            """Обработчик polling watcher-а."""
            del task
            if watcher is None:
                return {"status": "skipped", "reason": "watcher_disabled"}
            result = watcher.poll_once()
            return {
                "seen": result.seen,
                "enqueued": result.enqueued,
                "skipped_busy": result.skipped_busy,
                "unstable": result.unstable,
                "enqueued_paths": result.enqueued_paths,
            }

        def handle_reconcile_disputed(task: Task) -> dict:
            """Обработчик lifecycle claim-конфликтов."""
            if mm.conflict_guard is None:
                return {"status": "skipped", "reason": "no_conflict_guard"}
            current_tick = scheduler.status()["cycle_counter"]
            results = mm.conflict_guard.reconcile_disputed(
                current_tick=current_tick,
                session_id=task.session_id or "daemon",
                trace_id=task.trace_id,
            )
            return {
                "status": "reconciled",
                "actions": [result.action for result in results],
            }

        def handle_replay_memory(task: Task) -> dict:
            """Обработчик replay-цикла."""
            del task
            session = replay_engine.run_replay_session(force=False)
            return {
                "status": "replayed",
                "episodes_replayed": session.episodes_replayed,
                "reinforced": session.reinforced,
                "stale_removed": session.stale_removed,
                "skipped": bool(session.metadata.get("skipped", False)),
            }

        def handle_consolidate_memory(task: Task) -> dict:
            """Обработчик сохранения и консолидации памяти."""
            del task
            counts = mm.force_consolidate()
            mm.save_all()
            return {"status": "consolidated", "counts": counts}

        def handle_idle_dispatch(task: Task) -> dict:
            """Обработчик постановки idle-задач."""
            del task
            result = idle_dispatcher.dispatch_tick(
                current_tick=scheduler.status()["cycle_counter"]
            )
            return {
                "enqueued": result.enqueued,
                "reason": result.reason,
                "task_ids": result.task_ids,
                "task_types": result.task_types,
                "enqueued_count": result.enqueued_count,
            }

        def handle_self_reflect(task: Task) -> dict:
            """Лёгкая self-reflection задача без внешних побочных эффектов."""
            concept = str(task.payload.get("concept", "") or "")
            if brain_log:
                brain_log.info(
                    "motivation",
                    "self_reflect",
                    session_id=task.session_id or "daemon",
                    trace_id=task.trace_id,
                    state={"concept": concept},
                )
            return {"status": "reflected", "concept": concept}

        def handle_gap_fill(task: Task) -> dict:
            """Лёгкая задача отслеживания knowledge gap для idle-цикла."""
            concept = str(task.payload.get("concept", "") or "")
            return {"status": "queued_for_learning", "concept": concept}

        scheduler.register_handler("cognitive_cycle", handle_cognitive_cycle)
        scheduler.register_handler("ingest_file", handle_ingest_file)
        scheduler.register_handler("reconcile_dispute", handle_reconcile_disputed)
        scheduler.register_handler("self_reflect", handle_self_reflect)
        scheduler.register_handler("gap_fill", handle_gap_fill)
        scheduler.register_recurring(
            "reconcile_disputed",
            handle_reconcile_disputed,
            every_n_ticks=daemon_config.reconcile_every_ticks,
            priority=TaskPriority.LOW,
        )
        scheduler.register_recurring(
            "replay_memory",
            handle_replay_memory,
            every_n_ticks=daemon_config.replay_every_ticks,
            priority=TaskPriority.LOW,
        )
        scheduler.register_recurring(
            "consolidate_memory",
            handle_consolidate_memory,
            every_n_ticks=daemon_config.consolidate_every_ticks,
            priority=TaskPriority.LOW,
        )
        scheduler.register_recurring(
            "idle_dispatch",
            handle_idle_dispatch,
            every_n_ticks=daemon_config.self_reflect_every_ticks,
            priority=TaskPriority.IDLE,
        )
        if watcher is not None:
            scheduler.register_recurring(
                "poll_materials",
                handle_poll_materials,
                every_n_ticks=max(1, daemon_config.reconcile_every_ticks),
                priority=TaskPriority.LOW,
            )

        if material_ingestor is not None and materials_dir:
            resumed = material_ingestor.resume_incomplete(session_id="daemon")
            scanned = material_ingestor.scan_directory(materials_dir, session_id="daemon")
            print(
                f"[daemon] materials scan: resumed={len(resumed)} scanned={len(scanned)} "
                f"watch={'on' if watcher is not None else 'off'}"
            )

        if stdin_enabled:
            stdin_thread = _start_stdin_reader(
                scheduler,
                stop_event,
                stream=stdin_stream,
                session_id="daemon_stdin",
            )

        previous_handlers = _install_daemon_signal_handlers(stop_event, scheduler.stop)
        print(
            f"[daemon] Запуск. materials={materials_dir or '-'} "
            f"watch={'on' if watcher is not None else 'off'} "
            f"stdin={'on' if stdin_enabled else 'off'} "
            f"ticks={max_ticks if max_ticks is not None else '∞'}"
        )
        scheduler.run(max_ticks=max_ticks, resource_provider=_resource_provider)
        mm.save_all()
        stats = scheduler.stats
        print(
            f"[daemon] Завершено. ticks={stats.ticks} "
            f"executed={stats.tasks_executed} failed={stats.tasks_failed}"
        )
        return 0

    except Exception as exc:
        logger.error("Ошибка daemon-режима: %s", exc, exc_info=True)
        print(f"Ошибка daemon: {exc}", file=sys.stderr)
        return 1

    finally:
        stop_event.set()
        if stdin_thread is not None and stdin_thread.is_alive():
            stdin_thread.join(timeout=0.2)
        _restore_daemon_signal_handlers(previous_handlers)
        try:
            mm.save_all()
        except Exception:
            logger.warning("[daemon] memory save failed during shutdown", exc_info=True)
        try:
            rm.stop()
        except Exception:
            logger.warning("[daemon] resource monitor stop failed", exc_info=True)
        mm.stop(save=False)
        if brain_log:
            brain_log.flush()
            brain_log.close()


def run_autonomous(
    data_dir: str,
    ticks: int,
    llm_provider: LLMProvider | None = None,
    log_dir: str | None = None,
    log_level: str = "INFO",
) -> int:
    """
    Запустить автономный режим когнитивного ядра через Scheduler.

    Режим: Scheduler управляет тиками, каждый тик выполняет когнитивный цикл.
    Задачи: cognitive_cycle (NORMAL) + consolidate_memory/reconcile_disputed (LOW).

    Args:
        data_dir:     директория данных памяти
        ticks:        максимальное количество тиков (0 = бесконечно)
        llm_provider: опциональный LLM провайдер
        log_dir:      директория для JSONL-логов (None = не логировать)
        log_level:    минимальный уровень BrainLogger

    Returns:
        0 при успехе, 1 при ошибке.
    """
    # --- 1. BrainLogger + TraceBuilder ---
    brain_log: BrainLogger | None = None
    if log_dir:
        brain_log = BrainLogger(log_dir=log_dir, min_level=log_level)
        logger.info("[CLI] BrainLogger активирован: log_dir=%s level=%s", log_dir, log_level)

    trace_builder = TraceBuilder()
    digest_gen = DigestGenerator()
    llm_rate_limiter = LLMRateLimiter() if llm_provider is not None else None

    # --- 2. EventBus ---
    bus = EventBus()

    # --- 3. ResourceMonitor ---
    rm = ResourceMonitor(bus, ResourceMonitorConfig(sample_interval_s=10.0))

    # --- 4. MemoryManager ---
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    mm = MemoryManager(data_dir=str(data_path))
    mm.start()

    # --- 5. ReplayEngine (Этап J) ---
    replay_engine = ReplayEngine(memory=mm)

    try:
        # --- 6. PolicyConstraints ---
        policy = PolicyConstraints()

        # --- 7. CognitiveCore ---
        core = CognitiveCore(
            memory_manager=mm,  # type: ignore[arg-type]
            event_bus=bus,
            resource_monitor=rm,
            policy=policy,
            llm_provider=llm_provider,
            llm_rate_limiter=llm_rate_limiter,
            brain_logger=brain_log,
            trace_builder=trace_builder,
            digest_gen=digest_gen,
        )

        # --- 8. OutputPipeline ---
        output_pipeline = OutputPipeline(
            hedge_threshold=policy.hedge_threshold,
            brain_logger=brain_log,
            source_memory=mm.source,
        )

        # --- 9. Scheduler ---
        scheduler = Scheduler(bus)

        # --- 10. Регистрация обработчиков ---

        def handle_cognitive_cycle(task: Task) -> dict:
            """Обработчик когнитивного цикла."""
            query: str = task.payload.get("query", "Что нового в памяти?")
            result = core.run(query)
            output = output_pipeline.process(result)
            print(f"[autonomous] {output.text}")
            logger.info(
                "[autonomous] cycle=%d action=%s confidence=%.3f",
                core.cycle_count, result.action, result.confidence,
            )
            return {
                "action": result.action,
                "confidence": result.confidence,
                "cycle": core.cycle_count,
            }

        def handle_consolidate_memory(task: Task) -> dict:
            """Обработчик консолидации памяти с replay (Этап J)."""
            # Replay: повторное обучение на накопленных эпизодах (CPU-aware)
            try:
                session = replay_engine.run_replay_session(force=False)
                logger.info(
                    "[autonomous] replay: replayed=%d reinforced=%d stale=%d",
                    session.episodes_replayed,
                    session.reinforced,
                    session.stale_removed,
                )
            except Exception as exc:
                logger.warning("[autonomous] replay error: %s", exc)
            mm.save_all()
            logger.info("[autonomous] memory consolidated and saved")
            return {"status": "consolidated"}

        def handle_reconcile_disputed(task: Task) -> dict:
            """Обработчик lifecycle claim-конфликтов (U-B)."""
            if mm.conflict_guard is None:
                return {"status": "skipped", "reason": "no_conflict_guard"}
            current_tick = scheduler.status()["cycle_counter"]
            results = mm.conflict_guard.reconcile_disputed(
                current_tick=current_tick,
                session_id=task.session_id,
                trace_id=task.trace_id,
            )
            logger.info("[autonomous] conflict reconciliation: %d actions", len(results))
            return {
                "status": "reconciled",
                "actions": [result.action for result in results],
            }

        scheduler.register_handler("cognitive_cycle", handle_cognitive_cycle)
        scheduler.register_handler("consolidate_memory", handle_consolidate_memory)
        scheduler.register_recurring(
            "reconcile_disputed",
            handle_reconcile_disputed,
            every_n_ticks=5,
            priority=TaskPriority.LOW,
        )

        # --- 11. Начальные задачи ---
        for i, q in enumerate(_AUTONOMOUS_QUERIES):
            scheduler.enqueue(
                Task(
                    task_id=f"auto_cycle_{i + 1:03d}",
                    task_type="cognitive_cycle",
                    payload={"query": q},
                ),
                TaskPriority.NORMAL,
            )

        # Задача консолидации памяти (низкий приоритет — выполнится последней)
        scheduler.enqueue(
            Task(
                task_id="auto_consolidate_001",
                task_type="consolidate_memory",
            ),
            TaskPriority.LOW,
        )

        # --- 12. Запуск ---
        max_ticks: int | None = ticks if ticks > 0 else None
        print(
            f"[autonomous] Запуск автономного режима. "
            f"ticks={max_ticks if max_ticks is not None else '∞'} "
            f"queue={scheduler.queue_size()}"
        )

        def _resource_provider():
            """Провайдер состояния ресурсов для адаптации интервала тика."""
            try:
                snap = rm.snapshot()
                if hasattr(snap, "cpu_pct"):
                    return snap
            except Exception:
                pass
            return None

        scheduler.run(
            max_ticks=max_ticks,
            resource_provider=_resource_provider,
        )

        # --- 13. Сохранение памяти ---
        mm.save_all()

        # --- 14. Статистика ---
        stats = scheduler.stats
        print(
            f"[autonomous] Завершено. "
            f"ticks={stats.ticks} "
            f"executed={stats.tasks_executed} "
            f"failed={stats.tasks_failed}"
        )

        return 0

    except Exception as exc:
        logger.error("Ошибка автономного режима: %s", exc, exc_info=True)
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    finally:
        mm.stop(save=False)
        if brain_log:
            brain_log.flush()
            brain_log.close()


def run_query(
    query: str,
    data_dir: str,
    llm_provider: LLMProvider | None = None,
    log_dir: str | None = None,
    log_level: str = "INFO",
) -> int:
    """
    Выполнить полный когнитивный пайплайн для одного запроса.

    Пайплайн: query -> MemoryManager -> CognitiveCore.run() -> OutputPipeline -> BrainOutput

    Args:
        query:        текстовый запрос
        data_dir:     директория данных памяти
        llm_provider: опциональный LLM провайдер
        log_dir:      директория для JSONL-логов (None = не логировать)
        log_level:    минимальный уровень BrainLogger

    Returns:
        0 при успехе, 1 при ошибке.
    """
    # --- 1. BrainLogger + TraceBuilder ---
    brain_log: BrainLogger | None = None
    if log_dir:
        brain_log = BrainLogger(log_dir=log_dir, min_level=log_level)
        logger.info("[CLI] BrainLogger активирован: log_dir=%s level=%s", log_dir, log_level)

    trace_builder = TraceBuilder()
    digest_gen = DigestGenerator()
    llm_rate_limiter = LLMRateLimiter() if llm_provider is not None else None

    # --- 2. EventBus ---
    bus = EventBus()

    # --- 3. ResourceMonitor ---
    rm = ResourceMonitor(bus, ResourceMonitorConfig(sample_interval_s=10.0))

    # --- 4. MemoryManager ---
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    mm = MemoryManager(data_dir=str(data_path))
    mm.start()

    try:
        # --- 5. PolicyConstraints (единый источник порогов) ---
        policy = PolicyConstraints()

        # --- 6. CognitiveCore ---
        core = CognitiveCore(
            memory_manager=mm,  # type: ignore[arg-type]
            event_bus=bus,
            resource_monitor=rm,
            policy=policy,
            llm_provider=llm_provider,
            llm_rate_limiter=llm_rate_limiter,
            brain_logger=brain_log,
            trace_builder=trace_builder,
            digest_gen=digest_gen,
        )

        # --- 7. Run cognitive cycle ---
        result = core.run(query)

        # --- 8. OutputPipeline (hedge_threshold из policy) ---
        pipeline = OutputPipeline(
            hedge_threshold=policy.hedge_threshold,
            brain_logger=brain_log,
            source_memory=mm.source,
        )
        output = pipeline.process(result)

        # --- 9. Print result ---
        print(output.text)

        logger.info(
            "confidence=%.3f action=%s trace_id=%s",
            output.confidence,
            output.action,
            output.trace_id,
        )

        # --- 10. Save memory ---
        mm.save_all()

        return 0

    except Exception as exc:
        logger.error("Ошибка когнитивного цикла: %s", exc, exc_info=True)
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    finally:
        mm.stop(save=False)
        if brain_log:
            brain_log.flush()
            brain_log.close()


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI. Возвращает exit code."""
    _load_dotenv()  # подгрузить .env (если есть) до чтения env-переменных

    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    # --- LLM провайдер (Этап N) ---
    llm = _build_llm_provider(
        provider_name=args.llm_provider,
        api_key=args.llm_api_key,
        model=args.llm_model,
    )

    if args.autonomous:
        return run_autonomous(
            args.data_dir,
            args.ticks,
            llm_provider=llm,
            log_dir=args.log_dir,
            log_level=args.log_level,
        )

    if args.daemon:
        return run_daemon(
            args.data_dir,
            materials_dir=args.materials,
            watch=args.watch,
            stdin_enabled=args.stdin,
            llm_provider=llm,
            log_dir=args.log_dir,
            log_level=args.log_level,
        )

    if args.query is None:
        parser.print_help()
        return 0

    return run_query(
        args.query,
        args.data_dir,
        llm_provider=llm,
        log_dir=args.log_dir,
        log_level=args.log_level,
    )


def cli_entry() -> None:
    """Entry point для [project.scripts] (без возврата кода)."""
    sys.exit(main())


if __name__ == "__main__":
    cli_entry()
