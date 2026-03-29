# ADR-003: `typing.Protocol` для dependency injection

**Статус:** ✅ Принято  
**Дата:** 2025-05  
**Авторы:** cognitive-core contributors

---

## Контекст

`CognitiveCore` зависит от `MemoryManager`, `EventBus`, `ResourceMonitor` и `TextEncoder`. Изначально зависимости были типизированы как `Any`, что:
- Скрывало ошибки типов от mypy
- Затрудняло тестирование (нет чёткого интерфейса для mock)
- Нарушало принцип инверсии зависимостей (DIP)

## Рассмотренные варианты

### Вариант 1: Конкретные классы (`MemoryManager`, `EventBus`)
**Плюсы:** Простота, IDE autocomplete  
**Минусы:** Жёсткая связанность — нельзя подменить реализацию без изменения кода; circular imports

### Вариант 2: ABC (Abstract Base Classes)
**Плюсы:** Явная иерархия, `isinstance()` проверки  
**Минусы:** Требует наследования — нарушает принцип «composition over inheritance»; verbose

### Вариант 3: `typing.Protocol` (structural subtyping)
**Плюсы:** Duck typing с проверкой типов; нет наследования; любой объект с нужными методами удовлетворяет протоколу; идеально для тестирования (mock без наследования)  
**Минусы:** Менее очевидно для новичков; `@runtime_checkable` нужен для `isinstance()`

## Решение

Выбраны **`typing.Protocol`** с `@runtime_checkable` для всех внешних зависимостей.

Реализация в `brain/core/contracts.py`:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class MemoryManagerProtocol(Protocol):
    def store(self, content: str, importance: float = 0.5, ...) -> Any: ...
    def retrieve(self, query: str, top_n: int = 5) -> Any: ...
    def store_fact(self, concept: str, description: str, ...) -> Any: ...
    def save_all(self) -> None: ...

@runtime_checkable
class EventBusProtocol(Protocol):
    def publish(self, event_type: str, payload: Any = None, trace_id: str = "") -> int: ...
    def subscribe(self, event_type: str, handler: Any) -> None: ...
    def unsubscribe(self, event_type: str, handler: Any) -> None: ...

@runtime_checkable
class ResourceMonitorProtocol(Protocol):
    def snapshot(self) -> Any: ...
```

Использование в `CognitiveCore`:

```python
class CognitiveCore:
    def __init__(
        self,
        memory_manager: MemoryManagerProtocol,
        text_encoder: Optional[TextEncoderProtocol] = None,
        event_bus: Optional[EventBusProtocol] = None,
        resource_monitor: Optional[ResourceMonitorProtocol] = None,
    ) -> None:
        ...
```

## Последствия

**Положительные:**
- mypy проверяет соответствие протоколу без наследования
- Тесты используют простые mock-объекты без наследования от ABC
- Нет circular imports (Protocol определён в `contracts.py`, не в модулях реализации)
- `@runtime_checkable` позволяет `isinstance(obj, MemoryManagerProtocol)` в runtime

**Отрицательные:**
- Structural subtyping может пропустить объект, случайно имеющий нужные методы
- Нет автоматической проверки сигнатур методов в runtime (только mypy)

**Нейтральные:**
- `type: ignore[arg-type]` в `cli.py` — `MemoryManager` не полностью соответствует протоколу (известное ограничение, задокументировано)

## Связанные решения

- ADR-001: SQLite backend (реализует `MemoryManagerProtocol` через `MemoryManager`)
- P1-E5: Замена `Any` на Protocol-типы
