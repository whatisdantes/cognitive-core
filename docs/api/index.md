# API Reference

Автогенерированная документация всех публичных модулей **Cognitive Core**.

Документация генерируется из docstring'ов исходного кода с помощью [mkdocstrings](https://mkdocstrings.github.io/).

---

## Модули

| Модуль | Описание | Классов |
|--------|----------|---------|
| [cognition](cognition.md) | Когнитивное ядро: CognitiveCore, CognitivePipeline, Reasoner, GoalManager | 14 |
| [memory](memory.md) | Система памяти: 5 видов + MemoryManager + Storage | 8 |
| [perception](perception.md) | Слой восприятия: InputRouter, TextIngestor, validators | 4 |
| [core](core.md) | Ядро системы: EventBus, Scheduler, contracts, utils | 6 |
| [output](output.md) | Слой вывода: DialogueResponder, ResponseValidator, OutputTraceBuilder | 3 |
| [logging](logging.md) | Логирование: BrainLogger, DigestGenerator, TraceBuilder | 3 |
| [encoders](encoders.md) | Кодировщики: TextEncoder (4 режима) | 1 |

---

## Быстрая навигация

### Точки входа

- [`CognitiveCore`](cognition.md#brain.cognition.cognitive_core.CognitiveCore) — главный orchestrator
- [`CognitivePipeline`](cognition.md#brain.cognition.pipeline.CognitivePipeline) — 12-шаговый пайплайн (P3-10)
- [`MemoryManager`](memory.md#brain.memory.memory_manager.MemoryManager) — единая точка доступа к памяти
- [`InputRouter`](perception.md#brain.perception.input_router.InputRouter) — маршрутизация входных данных

### Протоколы (DI)

Все зависимости инъектируются через `typing.Protocol` из [`brain.core.contracts`](core.md#brain.core.contracts):

- `MemoryManagerProtocol`
- `TextEncoderProtocol`
- `EventBusProtocol`
- `ResourceMonitorProtocol`

### Хранилище

- [`MemoryDatabase`](memory.md#brain.memory.storage.MemoryDatabase) — SQLite WAL backend (опционально SQLCipher)
