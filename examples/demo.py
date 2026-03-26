#!/usr/bin/env python3
"""
examples/demo.py — Демонстрация cognitive-core pipeline.

Показывает полный цикл:
    1. Инициализация компонентов (EventBus, ResourceMonitor, MemoryManager, CognitiveCore)
    2. Запуск нескольких запросов
    3. Вывод результатов через OutputPipeline

Запуск:
    python examples/demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from brain import __version__
from brain.core.event_bus import EventBus
from brain.core.resource_monitor import ResourceMonitor, ResourceMonitorConfig
from brain.memory.memory_manager import MemoryManager
from brain.cognition.cognitive_core import CognitiveCore
from brain.output.dialogue_responder import OutputPipeline


def main() -> None:
    print(f"🧠 cognitive-core v{__version__} — demo")
    print("=" * 60)

    # --- Инициализация ---
    # Используем временную директорию для demo (не засоряем проект)
    data_dir = Path(tempfile.mkdtemp(prefix="cognitive_core_demo_"))
    print(f"📁 Данные: {data_dir}\n")

    bus = EventBus()
    rm = ResourceMonitor(bus, ResourceMonitorConfig(sample_interval_s=10.0))
    mm = MemoryManager(data_dir=str(data_dir))
    mm.start()

    core = CognitiveCore(
        memory_manager=mm,
        event_bus=bus,
        resource_monitor=rm,
    )

    pipeline = OutputPipeline()

    # --- Запросы ---
    queries = [
        "Запомни: нейрон — это клетка нервной системы",
        "Что такое нейрон?",
        "Правда ли что мозг состоит из нейронов?",
    ]

    for i, query in enumerate(queries, 1):
        print(f"--- Запрос {i}: {query}")

        result = core.run(query)
        output = pipeline.process(result)

        print(f"  🤖 Ответ:      {output.text}")
        print(f"  📊 Confidence:  {output.confidence:.1%}")
        print(f"  🎯 Action:      {output.action}")
        print(f"  🔗 Trace ID:    {output.trace_id}")
        print()

    # --- Статус ---
    print("=" * 60)
    print(f"📈 Циклов выполнено: {core.cycle_count}")
    print(f"📋 Целей в менеджере: {len(core.goal_manager)}")

    status = mm.status()
    wm = status.get("working", {})
    sm = status.get("semantic", {})
    em = status.get("episodic", {})
    print(f"🧠 Память: working={wm.get('normal_items', 0)} "
          f"semantic={sm.get('node_count', 0)} "
          f"episodic={em.get('episode_count', 0)}")

    # --- Cleanup ---
    mm.stop(save=False)
    print("\n✅ Demo завершён.")


if __name__ == "__main__":
    main()
