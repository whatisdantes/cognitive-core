"""
events.py — Типизированные события для шины сообщений мозга.

Все модули общаются через события — никаких прямых зависимостей.
Каждое событие сериализуется в JSON для логирования и трассировки.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List


def _now_iso() -> str:
    """Текущее время в ISO 8601 UTC."""
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "") -> str:
    """Генерация короткого уникального ID."""
    uid = str(uuid.uuid4())[:8]
    return f"{prefix}{uid}" if prefix else uid


# ─── Базовое событие ─────────────────────────────────────────────────────────

@dataclass
class BaseEvent:
    """Базовый класс для всех событий мозга."""
    event_type: str = field(default="base")
    ts: str = field(default_factory=_now_iso)
    trace_id: str = field(default_factory=lambda: _new_id("trace_"))
    session_id: str = field(default="")
    cycle_id: str = field(default="")

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация в словарь (для JSON-логирования)."""
        return asdict(self)

    def to_json_line(self) -> str:
        """Сериализация в одну JSON-строку (JSONL формат)."""
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)


# ─── Событие восприятия ───────────────────────────────────────────────────────

@dataclass
class PerceptEvent(BaseEvent):
    """
    Событие восприятия — входящий сигнал из внешнего мира.

    Поля:
        source      — источник (путь к файлу, URL, "user_input", ...)
        modality    — тип данных ('text', 'image', 'audio', 'video', 'mixed')
        content     — содержимое (текст, путь к файлу, байты в base64)
        quality     — оценка качества входных данных (0.0 — 1.0)
        language    — язык ('ru', 'en', 'mixed', 'unknown')
        metadata    — дополнительные метаданные (страница, временная метка, ...)
    """
    event_type: str = field(default="percept")
    source: str = field(default="")
    modality: str = field(default="text")       # 'text' | 'image' | 'audio' | 'video' | 'mixed'
    content: Any = field(default=None)
    quality: float = field(default=1.0)         # 0.0 — 1.0
    language: str = field(default="unknown")    # 'ru' | 'en' | 'mixed' | 'unknown'
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── Событие памяти ───────────────────────────────────────────────────────────

@dataclass
class MemoryEvent(BaseEvent):
    """
    Событие памяти — операция с любым видом памяти.

    Поля:
        operation   — тип операции ('store', 'retrieve', 'update', 'delete', 'consolidate', 'decay')
        memory_type — вид памяти ('working', 'episodic', 'semantic', 'procedural', 'source')
        key         — ключ/концепт
        value       — значение (факт, эпизод, ...)
        importance  — важность записи (0.0 — 1.0)
        confidence  — уверенность в факте (0.0 — 1.0)
        source_ref  — ссылка на источник
        latency_ms  — время операции в мс
    """
    event_type: str = field(default="memory")
    operation: str = field(default="store")     # 'store' | 'retrieve' | 'update' | 'delete' | 'consolidate' | 'decay'
    memory_type: str = field(default="working") # 'working' | 'episodic' | 'semantic' | 'procedural' | 'source'
    key: str = field(default="")
    value: Any = field(default=None)
    importance: float = field(default=0.5)      # 0.0 — 1.0
    confidence: float = field(default=1.0)      # 0.0 — 1.0
    source_ref: str = field(default="")
    latency_ms: float = field(default=0.0)


# ─── Когнитивное событие ─────────────────────────────────────────────────────

@dataclass
class CognitiveEvent(BaseEvent):
    """
    Когнитивное событие — шаг мышления/планирования.

    Поля:
        goal        — текущая цель
        step        — название шага
        confidence  — уверенность в решении (0.0 — 1.0)
        decision    — принятое решение
        reasoning   — цепочка рассуждений
        input_refs  — ссылки на входные данные
        memory_refs — ссылки на использованные факты памяти
        cpu_pct     — загрузка CPU в момент события
        ram_mb      — использование RAM в МБ
    """
    event_type: str = field(default="cognitive")
    goal: str = field(default="")
    step: str = field(default="")
    confidence: float = field(default=1.0)
    decision: str = field(default="")
    reasoning: List[str] = field(default_factory=list)
    input_refs: List[str] = field(default_factory=list)
    memory_refs: List[str] = field(default_factory=list)
    cpu_pct: float = field(default=0.0)
    ram_mb: float = field(default=0.0)


# ─── Событие обучения ────────────────────────────────────────────────────────

@dataclass
class LearningEvent(BaseEvent):
    """
    Событие обучения — изменение весов/оценок/ассоциаций.

    Поля:
        trigger         — что вызвало обучение ('online', 'replay', 'self_supervised')
        affected_module — какой модуль обновился
        delta           — величина изменения
        before          — значение до
        after           — значение после
        notes           — комментарий
    """
    event_type: str = field(default="learning")
    trigger: str = field(default="online")      # 'online' | 'replay' | 'self_supervised'
    affected_module: str = field(default="")
    delta: float = field(default=0.0)
    before: Any = field(default=None)
    after: Any = field(default=None)
    notes: str = field(default="")


# ─── Системное событие ───────────────────────────────────────────────────────

@dataclass
class SystemEvent(BaseEvent):
    """
    Системное событие — запуск, остановка, ресурсы, ошибки.

    Поля:
        level       — уровень ('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL')
        module      — модуль-источник
        message     — сообщение
        cpu_pct     — загрузка CPU
        ram_mb      — использование RAM в МБ
        ram_total_mb — всего RAM в МБ
        error       — текст ошибки (если есть)
    """
    event_type: str = field(default="system")
    level: str = field(default="INFO")          # 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'CRITICAL'
    module: str = field(default="")
    message: str = field(default="")
    cpu_pct: float = field(default=0.0)
    ram_mb: float = field(default=0.0)
    ram_total_mb: float = field(default=0.0)
    error: str = field(default="")


# ─── Фабрика событий ─────────────────────────────────────────────────────────

class EventFactory:
    """Удобные фабричные методы для создания событий."""

    @staticmethod
    def percept(
        source: str,
        content: Any,
        modality: str = "text",
        quality: float = 1.0,
        language: str = "unknown",
        session_id: str = "",
        **metadata,
    ) -> PerceptEvent:
        return PerceptEvent(
            source=source,
            content=content,
            modality=modality,
            quality=quality,
            language=language,
            session_id=session_id,
            metadata=metadata,
        )

    @staticmethod
    def memory_store(
        key: str,
        value: Any,
        memory_type: str = "working",
        importance: float = 0.5,
        confidence: float = 1.0,
        source_ref: str = "",
        trace_id: str = "",
    ) -> MemoryEvent:
        ev = MemoryEvent(
            operation="store",
            memory_type=memory_type,
            key=key,
            value=value,
            importance=importance,
            confidence=confidence,
            source_ref=source_ref,
        )
        if trace_id:
            ev.trace_id = trace_id
        return ev

    @staticmethod
    def memory_retrieve(
        key: str,
        memory_type: str = "working",
        trace_id: str = "",
    ) -> MemoryEvent:
        ev = MemoryEvent(
            operation="retrieve",
            memory_type=memory_type,
            key=key,
        )
        if trace_id:
            ev.trace_id = trace_id
        return ev

    @staticmethod
    def system_info(module: str, message: str, cpu_pct: float = 0.0, ram_mb: float = 0.0) -> SystemEvent:
        return SystemEvent(
            level="INFO",
            module=module,
            message=message,
            cpu_pct=cpu_pct,
            ram_mb=ram_mb,
        )

    @staticmethod
    def system_warn(module: str, message: str, cpu_pct: float = 0.0, ram_mb: float = 0.0) -> SystemEvent:
        return SystemEvent(
            level="WARN",
            module=module,
            message=message,
            cpu_pct=cpu_pct,
            ram_mb=ram_mb,
        )

    @staticmethod
    def system_error(module: str, message: str, error: str = "") -> SystemEvent:
        return SystemEvent(
            level="ERROR",
            module=module,
            message=message,
            error=error,
        )


# ─── Экспорт ─────────────────────────────────────────────────────────────────

__all__ = [
    "BaseEvent",
    "PerceptEvent",
    "MemoryEvent",
    "CognitiveEvent",
    "LearningEvent",
    "SystemEvent",
    "EventFactory",
]
