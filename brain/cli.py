"""
brain/cli.py — CLI entrypoint для cognitive-core.

Использование:
    cognitive-core "Что такое нейропластичность?"
    cognitive-core "Запомни: солнце встает на востоке"
    cognitive-core --verbose "вопрос"
    cognitive-core --version
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from brain import __version__
from brain.core.event_bus import EventBus
from brain.core.resource_monitor import ResourceMonitor, ResourceMonitorConfig
from brain.memory.memory_manager import MemoryManager
from brain.cognition.cognitive_core import CognitiveCore
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

    return parser


def setup_logging(verbose: bool = False) -> None:
    """Настроить логирование."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def run_query(query: str, data_dir: str) -> int:
    """
    Выполнить полный когнитивный пайплайн для одного запроса.

    Пайплайн: query -> MemoryManager -> CognitiveCore.run() -> OutputPipeline -> BrainOutput

    Returns:
        0 при успехе, 1 при ошибке.
    """
    # --- 1. EventBus ---
    bus = EventBus()

    # --- 2. ResourceMonitor ---
    rm = ResourceMonitor(bus, ResourceMonitorConfig(sample_interval_s=10.0))

    # --- 3. MemoryManager ---
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    mm = MemoryManager(data_dir=str(data_path))
    mm.start()

    try:
        # --- 4. CognitiveCore ---
        core = CognitiveCore(
            memory_manager=mm,
            event_bus=bus,
            resource_monitor=rm,
        )

        # --- 5. Run cognitive cycle ---
        result = core.run(query)

        # --- 6. OutputPipeline ---
        pipeline = OutputPipeline()
        output = pipeline.process(result)

        # --- 7. Print result ---
        print(output.text)

        logger.info(
            "confidence=%.3f action=%s trace_id=%s",
            output.confidence,
            output.action,
            output.trace_id,
        )

        # --- 8. Save memory ---
        mm.save_all()

        return 0

    except Exception as exc:
        logger.error("Ошибка когнитивного цикла: %s", exc, exc_info=True)
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    finally:
        mm.stop(save=False)


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI. Возвращает exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    if args.query is None:
        parser.print_help()
        return 0

    return run_query(args.query, args.data_dir)


def cli_entry() -> None:
    """Entry point для [project.scripts] (без возврата кода)."""
    sys.exit(main())


if __name__ == "__main__":
    cli_entry()
