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

from .events import (
    BaseEvent,
    PerceptEvent,
    MemoryEvent,
    CognitiveEvent,
    LearningEvent,
    SystemEvent,
    EventFactory,
)
from .contracts import (
    Modality,
    TaskStatus,
    ResourceState,
    Task,
    EncodedPercept,
    FusedPercept,
    TraceRef,
    TraceStep,
    TraceChain,
    CognitiveResult,
    BrainOutput,
)
from .event_bus import EventBus, BusStats
from .scheduler import Scheduler, TaskPriority, SchedulerConfig, SchedulerStats
from .resource_monitor import (
    ResourceMonitor,
    DegradationPolicy,
    ResourceMonitorConfig,
    ResourceMonitorStats,
)

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
