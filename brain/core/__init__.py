"""
brain/core — Ядро автономного цикла мозга.

Модули:
    events.py           — dataclasses всех типов событий (реализовано)
    scheduler.py        — тик-планировщик (clock-driven + event-driven)
    event_bus.py        — publish/subscribe шина событий
    resource_monitor.py — мониторинг CPU/RAM, graceful degradation
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

__all__ = [
    "BaseEvent",
    "PerceptEvent",
    "MemoryEvent",
    "CognitiveEvent",
    "LearningEvent",
    "SystemEvent",
    "EventFactory",
]
