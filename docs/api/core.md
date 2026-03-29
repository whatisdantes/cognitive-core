# brain.core — Ядро системы

Базовые компоненты: EventBus, Scheduler, Protocol-контракты, утилиты.

---

## Contracts (Protocol DI)

Все зависимости инъектируются через `typing.Protocol` (`@runtime_checkable`).

::: brain.core.contracts
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

### Ключевые протоколы

| Протокол | Реализация | Используется в |
|----------|-----------|----------------|
| `MemoryManagerProtocol` | `MemoryManager` | `CognitiveCore`, `CognitivePipeline` |
| `TextEncoderProtocol` | `TextEncoder` | `CognitiveCore`, `CognitivePipeline` |
| `EventBusProtocol` | `EventBus`, `ThreadPoolEventBus` | `CognitiveCore`, `CognitivePipeline` |
| `ResourceMonitorProtocol` | `ResourceMonitor` | `CognitiveCore`, `CognitivePipeline` |

---

## EventBus

Синхронная шина событий с поддержкой снапшотов.

::: brain.core.event_bus.EventBus
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - subscribe
        - unsubscribe
        - publish
        - snapshot
        - clear
        - status

## ThreadPoolEventBus

Асинхронная шина событий на основе `ThreadPoolExecutor` (P3-9).

::: brain.core.event_bus.ThreadPoolEventBus
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - publish
        - shutdown

---

## Scheduler

Планировщик задач с приоритетами для автономного цикла (P3-11).

::: brain.core.scheduler.Scheduler
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - schedule
        - cancel
        - start
        - stop
        - status

::: brain.core.scheduler.SchedulerConfig
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.core.scheduler.TaskPriority
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.core.scheduler.SchedulerStats
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## ResourceMonitor

Мониторинг ресурсов: CPU, RAM, политика ограничений.

::: brain.core.resource_monitor.ResourceMonitor
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - get_state
        - apply_state
        - status

---

## Events

Типы событий системы.

::: brain.core.events
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## Утилиты

### text_utils

::: brain.core.text_utils
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

### hash_utils

::: brain.core.hash_utils
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
