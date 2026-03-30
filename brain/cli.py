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
import sys
from pathlib import Path

from brain import __version__
from brain.bridges.llm_bridge import LLMBridge, LLMProvider
from brain.bridges.safety_wrapper import LLMSafetyWrapper
from brain.cognition.cognitive_core import CognitiveCore
from brain.cognition.context import PolicyConstraints
from brain.core.contracts import Task
from brain.core.event_bus import EventBus
from brain.core.resource_monitor import ResourceMonitor, ResourceMonitorConfig
from brain.core.scheduler import Scheduler, TaskPriority
from brain.logging import BrainLogger, DigestGenerator, TraceBuilder
from brain.memory.memory_manager import MemoryManager
from brain.output.dialogue_responder import OutputPipeline

logger = logging.getLogger(__name__)


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
        choices=["openai", "anthropic", "mock"],
        metavar="PROVIDER",
        help="LLM провайдер: openai | anthropic | mock (по умолчанию: нет LLM)",
    )

    parser.add_argument(
        "--llm-api-key",
        default=None,
        metavar="KEY",
        help="API ключ для LLM провайдера (или переменная окружения OPENAI_API_KEY / ANTHROPIC_API_KEY)",
    )

    parser.add_argument(
        "--llm-model",
        default=None,
        metavar="MODEL",
        help=(
            "Модель LLM провайдера "
            "(openai: gpt-4o-mini, anthropic: claude-3-haiku-20240307)"
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


def _build_llm_provider(
    provider_name: str | None,
    api_key: str | None,
    model: str | None,
) -> LLMProvider | None:
    """
    Создать LLM провайдера по имени и параметрам.

    Возвращает LLMSafetyWrapper(provider) или None если провайдер не указан.
    Ошибки импорта (нет openai/anthropic) логируются как WARNING.
    """
    if not provider_name:
        return None

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
    Задачи: cognitive_cycle (NORMAL) + consolidate_memory (LOW).

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
        # --- 5. PolicyConstraints ---
        policy = PolicyConstraints()

        # --- 6. CognitiveCore ---
        core = CognitiveCore(
            memory_manager=mm,  # type: ignore[arg-type]
            event_bus=bus,
            resource_monitor=rm,
            policy=policy,
            llm_provider=llm_provider,
            brain_logger=brain_log,
            trace_builder=trace_builder,
            digest_gen=digest_gen,
        )

        # --- 7. OutputPipeline ---
        output_pipeline = OutputPipeline(hedge_threshold=policy.hedge_threshold)

        # --- 8. Scheduler ---
        scheduler = Scheduler(bus)

        # --- 9. Регистрация обработчиков ---

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
            """Обработчик консолидации памяти."""
            mm.save_all()
            logger.info("[autonomous] memory consolidated and saved")
            return {"status": "consolidated"}

        scheduler.register_handler("cognitive_cycle", handle_cognitive_cycle)
        scheduler.register_handler("consolidate_memory", handle_consolidate_memory)

        # --- 10. Начальные задачи ---
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

        # --- 11. Запуск ---
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

        # --- 12. Сохранение памяти ---
        mm.save_all()

        # --- 13. Статистика ---
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
            brain_logger=brain_log,
            trace_builder=trace_builder,
            digest_gen=digest_gen,
        )

        # --- 7. Run cognitive cycle ---
        result = core.run(query)

        # --- 8. OutputPipeline (hedge_threshold из policy) ---
        pipeline = OutputPipeline(hedge_threshold=policy.hedge_threshold)
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
