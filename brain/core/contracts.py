"""
brain/core/contracts.py

Общие сквозные контракты (dataclass/enum/protocol) для взаимодействия слоёв.
Цель: единый типовой "язык" между perception, encoders, cognition, output, logging.

Правила совместимости (A.2):
  - Не переименовывать поля без миграции (добавлять новые поля с default).
  - Все "действия" несут trace_id / session_id / cycle_id.
  - Сериализация: to_dict() / from_dict() на каждом контракте.
  - Enum-поля сериализуются как строки (.value).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, TypeVar, cast, runtime_checkable

# ---------------------------------------------------------------------------
# Mixin: единый стиль сериализации для всех контрактов
# ---------------------------------------------------------------------------

T = TypeVar("T", bound="ContractMixin")


class ContractMixin:
    """
    Mixin для dataclass-контрактов.
    Предоставляет to_dict() и from_dict() с поддержкой Enum-полей.
    """

    def to_dict(self) -> Dict[str, Any]:
        """Рекурсивно конвертирует dataclass в dict (Enum → str)."""
        raw = dict(vars(self))
        return cast(Dict[str, Any], _enum_to_str(raw))

    @classmethod
    def from_dict(cls: type[T], data: Dict[str, Any]) -> T:
        """
        Создаёт экземпляр из dict.
        Неизвестные ключи игнорируются (forward-compatibility).
        Вложенные dataclass НЕ восстанавливаются автоматически —
        используйте явный from_dict() вложенного типа при необходимости.
        """
        known = set(getattr(cls, "__dataclass_fields__", {}).keys())
        return cls(**{k: v for k, v in data.items() if k in known})


def _enum_to_str(obj: Any) -> Any:
    """Рекурсивно заменяет Enum-значения на их .value (str)."""
    if isinstance(obj, dict):
        return {k: _enum_to_str(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_enum_to_str(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj


class Modality(str, Enum):
    """Поддерживаемые модальности входа/представления."""
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FUSED = "fused"


class TaskStatus(str, Enum):
    """Статус выполнения задачи в scheduler/cognition."""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class ResourceState(ContractMixin):
    """
    Снимок ресурсного состояния системы.
    Используется для degradation policy и принятия решения о тяжёлых ветках.
    """
    cpu_pct: float = 0.0
    ram_pct: float = 0.0
    ram_used_mb: float = 0.0
    ram_total_mb: float = 0.0
    available_threads: int = 1
    ring2_allowed: bool = True
    soft_blocked: bool = False


@dataclass
class Task(ContractMixin):
    """
    Унифицированная задача для scheduler/event loop.
    """
    task_id: str
    task_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: float = 0.5
    status: TaskStatus = TaskStatus.PENDING
    trace_id: str = ""
    session_id: str = ""
    cycle_id: str = ""


@dataclass
class EncodedPercept(ContractMixin):
    """
    Результат кодирования единичного перцепта одной модальности.

    Top-level поля — только стабильные, используемые downstream-слоями.
    Всё остальное (keywords, encoding_time_ms, warnings, sentiment) → metadata.
    """
    percept_id: str
    modality: Modality
    vector: List[float] = field(default_factory=list)
    text: str = ""
    quality: float = 0.0
    source: str = ""
    language: str = ""
    message_type: str = "unknown"
    encoder_model: str = ""
    vector_dim: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    session_id: str = ""
    cycle_id: str = ""


@dataclass
class FusedPercept(ContractMixin):
    """
    Кросс-модальное объединение нескольких EncodedPercept.
    """
    fused_id: str
    inputs: List[EncodedPercept] = field(default_factory=list)
    fused_vector: List[float] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    session_id: str = ""
    cycle_id: str = ""


@dataclass
class TraceRef(ContractMixin):
    """
    Ссылка на источник в цепочке объяснимости.
    Например: memory_ref, hypothesis_ref, source_ref.
    """
    ref_type: str
    ref_id: str
    note: str = ""


@dataclass
class TraceStep(ContractMixin):
    """
    Один шаг reasoning/decision trace.
    """
    step_id: str
    module: str
    action: str
    confidence: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    refs: List[TraceRef] = field(default_factory=list)


@dataclass
class TraceChain(ContractMixin):
    """
    Полная цепочка причинности для одного решения.
    """
    trace_id: str
    session_id: str = ""
    cycle_id: str = ""
    input_refs: List[TraceRef] = field(default_factory=list)
    steps: List[TraceStep] = field(default_factory=list)
    output_refs: List[TraceRef] = field(default_factory=list)
    summary: str = ""


@dataclass
class CognitiveResult(ContractMixin):
    """
    Результат когнитивного цикла (reasoning + action selection).
    """
    action: str
    response: str
    confidence: float
    trace: TraceChain
    goal: str = ""
    trace_id: str = ""
    session_id: str = ""
    cycle_id: str = ""
    contradictions: List[str] = field(default_factory=list)
    uncertainty: float = 0.0
    salience: float = 0.0
    memory_refs: List[TraceRef] = field(default_factory=list)
    source_refs: List[TraceRef] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrainOutput(ContractMixin):
    """
    Финальный внешний вывод системы (для dialogue/action API).
    """
    text: str
    confidence: float
    trace_id: str
    session_id: str = ""
    cycle_id: str = ""
    digest: str = ""
    action: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# API Protocol контракты — формальные интерфейсы для dependency injection
# ---------------------------------------------------------------------------

@runtime_checkable
class MemoryManagerProtocol(Protocol):
    """
    Формальный интерфейс MemoryManager для dependency injection.

    Любой объект с методами store(), retrieve(), store_fact(), save_all()
    удовлетворяет этому протоколу (structural subtyping).
    """

    def store(
        self,
        content: str,
        importance: float = 0.5,
        source_ref: str = "",
        tags: Optional[List[str]] = None,
    ) -> Any:
        """Сохранить контент в память (working + episodic + semantic)."""
        ...

    def retrieve(self, query: str, top_n: int = 5) -> Any:
        """Поиск по всем видам памяти."""
        ...

    def store_fact(
        self,
        concept: str,
        description: str,
        importance: float = 0.5,
    ) -> Any:
        """Явное сохранение факта в семантическую память."""
        ...

    def save_all(self) -> None:
        """Сохранить все виды памяти на диск."""
        ...


@runtime_checkable
class EventBusProtocol(Protocol):
    """
    Формальный интерфейс EventBus для dependency injection.

    Любой объект с методами publish(), subscribe(), unsubscribe()
    удовлетворяет этому протоколу.
    """

    def publish(self, event_type: str, data: Any = None) -> None:
        """Опубликовать событие."""
        ...

    def subscribe(self, event_type: str, handler: Any) -> None:
        """Подписаться на тип события."""
        ...

    def unsubscribe(self, event_type: str, handler: Any) -> None:
        """Отписаться от типа события."""
        ...


@runtime_checkable
class ResourceMonitorProtocol(Protocol):
    """
    Формальный интерфейс ResourceMonitor для dependency injection.

    Любой объект с методом snapshot() удовлетворяет этому протоколу.
    """

    def snapshot(self) -> Any:
        """Получить текущий снимок ресурсов (ResourceState или dict)."""
        ...
