"""
brain/core — Ядро автономного цикла мозга.

Модули:
    events.py               — dataclasses всех типов событий (реализовано) ✅
    contracts.py            — общие сквозные типы (реализовано) ✅
    event_bus.py            — publish/subscribe шина событий (реализовано) ✅
    scheduler.py            — тик-планировщик (clock-driven + event-driven) ✅
    resource_monitor.py     — мониторинг CPU/RAM, graceful degradation ✅
    attention_controller.py — бюджет вычислений по модальностям
"""

from .contracts import (
    BrainOutput,
    CognitiveResult,
    EncodedPercept,
    EventBusProtocol,
    FusedPercept,
    MemoryManagerProtocol,
    Modality,
    ResourceMonitorProtocol,
    ResourceState,
    Task,
    TaskStatus,
    TraceChain,
    TraceRef,
    TraceStep,
)
from .event_bus import BusStats, EventBus
from .events import (
    BaseEvent,
    CognitiveEvent,
    EventFactory,
    LearningEvent,
    MemoryEvent,
    PerceptEvent,
    SystemEvent,
)
from .resource_monitor import (
    DegradationPolicy,
    ResourceMonitor,
    ResourceMonitorConfig,
    ResourceMonitorStats,
)
from .scheduler import Scheduler, SchedulerConfig, SchedulerStats, TaskPriority

__all__ = [
    # events
    "BaseEvent",
    "PerceptEvent",
    "MemoryEvent",
    "CognitiveEvent",
    "LearningEvent",
    "SystemEvent",
    "EventFactory",
    # contracts
    "Modality",
    "TaskStatus",
    "ResourceState",
    "Task",
    "EncodedPercept",
    "FusedPercept",
    "TraceRef",
    "TraceStep",
    "TraceChain",
    "CognitiveResult",
    "BrainOutput",
    # protocols
    "MemoryManagerProtocol",
    "EventBusProtocol",
    "ResourceMonitorProtocol",
    # event_bus
    "EventBus",
    "BusStats",
    # scheduler
    "Scheduler",
    "TaskPriority",
    "SchedulerConfig",
    "SchedulerStats",
    # resource_monitor
    "ResourceMonitor",
    "DegradationPolicy",
    "ResourceMonitorConfig",
    "ResourceMonitorStats",
]
