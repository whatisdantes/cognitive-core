"""
brain/core — Ядро автономного цикла мозга.

Модули:
    events.py               — dataclasses всех типов событий (реализовано) ✅
    contracts.py            — общие сквозные типы (реализовано) ✅
    event_bus.py            — EventBus (sync) + ThreadPoolEventBus (async, P3-9) ✅
    scheduler.py            — тик-планировщик (clock-driven + event-driven) ✅
    resource_monitor.py     — мониторинг CPU/RAM, graceful degradation ✅
    attention_controller.py — AttentionBudget, AttentionController (Этап H) ✅
"""

from .attention_controller import (
    PRESET_BUDGETS,
    AttentionBudget,
    AttentionController,
)
from .contracts import (
    BrainOutput,
    CognitiveResult,
    DaemonConfig,
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
from .event_bus import BusStats, EventBus, ThreadPoolEventBus
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
from .scheduler import RecurringTask, Scheduler, SchedulerConfig, SchedulerStats, TaskPriority

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
    "DaemonConfig",
    # protocols
    "MemoryManagerProtocol",
    "EventBusProtocol",
    "ResourceMonitorProtocol",
    # event_bus
    "EventBus",
    "ThreadPoolEventBus",
    "BusStats",
    # scheduler
    "Scheduler",
    "TaskPriority",
    "RecurringTask",
    "SchedulerConfig",
    "SchedulerStats",
    # resource_monitor
    "ResourceMonitor",
    "DegradationPolicy",
    "ResourceMonitorConfig",
    "ResourceMonitorStats",
    # attention_controller (Этап H)
    "AttentionBudget",
    "AttentionController",
    "PRESET_BUDGETS",
]
