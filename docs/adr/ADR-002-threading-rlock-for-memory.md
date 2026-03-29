# ADR-002: `threading.RLock` для thread safety памяти

**Статус:** ✅ Принято  
**Дата:** 2025-05  
**Авторы:** cognitive-core contributors

---

## Контекст

`ConsolidationEngine` работает как daemon thread и периодически читает/пишет в модули памяти. Одновременно основной поток выполняет `CognitiveCore.run()`, который также обращается к памяти. Без синхронизации возникают race conditions и потеря данных.

Затронутые модули (P0-E1):
- `WorkingMemory`
- `SemanticMemory`
- `EpisodicMemory`
- `SourceMemory`
- `ProceduralMemory`
- `EventBus`

## Рассмотренные варианты

### Вариант 1: `threading.Lock` (простой мьютекс)
**Плюсы:** Минимальный overhead  
**Минусы:** Не реентерабельный — deadlock при рекурсивных вызовах внутри одного потока (например, `store()` вызывает `_evict()`, который тоже берёт lock)

### Вариант 2: `threading.RLock` (реентерабельный мьютекс)
**Плюсы:** Безопасен при рекурсивных вызовах, тот же поток может взять lock повторно  
**Минусы:** Чуть больше overhead чем `Lock` (счётчик рекурсии)

### Вариант 3: `asyncio.Lock` (асинхронный)
**Плюсы:** Подходит для async-архитектуры  
**Минусы:** Требует полного перехода на asyncio — несовместимо с текущей синхронной архитектурой

### Вариант 4: `queue.Queue` (lock-free через очередь)
**Плюсы:** Нет явных lock'ов  
**Минусы:** Требует actor-model рефакторинга всей системы памяти — слишком большой scope

## Решение

Выбран **`threading.RLock`** для всех 6 модулей.

Паттерн реализации:

```python
import threading

class SemanticMemory:
    def __init__(self):
        self._lock = threading.RLock()
        self._nodes: Dict[str, SemanticNode] = {}

    def learn_fact(self, concept: str, description: str) -> SemanticNode:
        with self._lock:
            # безопасная запись
            ...

    def get_all_nodes(self) -> List[SemanticNode]:
        with self._lock:
            return list(self._nodes.values())  # возвращаем копию!
```

**Ключевое правило:** методы, возвращающие коллекции, всегда возвращают **копию** (`list(...)`, `dict(...)`), а не ссылку на внутреннее состояние.

## Последствия

**Положительные:**
- Устранены race conditions в ConsolidationEngine daemon thread
- Реентерабельность позволяет вызывать методы памяти из других методов того же класса
- Единообразный паттерн во всех 6 модулях

**Отрицательные:**
- Небольшой overhead на каждую операцию (счётчик рекурсии RLock)
- Возможен deadlock при взаимной блокировке двух модулей (A ждёт B, B ждёт A) — но в текущей архитектуре такого нет

**Нейтральные:**
- `MemoryDatabase` (SQLite) имеет собственный `RLock` — двойная защита для операций через storage

## Связанные решения

- ADR-001: SQLite backend (также использует RLock)
- P0-E2: Race condition в `ResourceMonitor._apply_state()` — аналогичное исправление
