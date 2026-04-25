# ADR-006: Синхронный EventBus со snapshot pattern

**Статус:** ✅ Принято  
**Дата:** 2025-06  
**Авторы:** cognitive-core contributors

---

## Контекст

`EventBus` — центральная шина событий для межмодульного взаимодействия. Модули публикуют события (`percept`, `learn`, `cognitive_result` и др.), другие модули подписываются на них. Вопрос: синхронный или асинхронный dispatch?

## Рассмотренные варианты

### Вариант 1: Синхронный dispatch (прямой вызов handlers)
**Плюсы:** Простота, предсказуемость, нет overhead на очереди/потоки, легко тестировать  
**Минусы:** Медленный handler блокирует publisher; нет параллелизма

### Вариант 2: Асинхронный dispatch (asyncio)
**Плюсы:** Параллельное выполнение handlers; publisher не блокируется  
**Минусы:** Требует полного перехода на asyncio; сложнее тестировать; overhead на event loop

### Вариант 3: Thread pool dispatch
**Плюсы:** Параллелизм без asyncio; publisher не блокируется  
**Минусы:** Сложнее управление ошибками; нет гарантии порядка; overhead на thread creation

### Вариант 4: Синхронный + snapshot pattern (выбранный)
**Плюсы:** Простота синхронного dispatch + thread safety через snapshot; ошибка одного handler не прерывает остальных  
**Минусы:** Handlers вызываются последовательно

## Решение

Выбран **синхронный EventBus со snapshot pattern** для thread safety.

Ключевые принципы реализации в `brain/core/event_bus.py`:

```python
def publish(self, event_type: str, payload: Any = None, trace_id: str = "") -> int:
    # 1. Берём snapshot handlers под lock
    with self._lock:
        specific = list(self._handlers.get(event_type, []))
        wildcard = list(self._handlers.get("*", []))
        all_handlers = specific + [h for h in wildcard if h not in specific]
        ...

    # 2. Вызываем handlers ВНЕ lock (snapshot pattern)
    for handler in all_handlers:
        try:
            handler(event_type, payload, trace_id)
        except Exception:
            # Ошибка одного handler не прерывает остальных
            logger.error(...)
```

**Snapshot pattern:** список handlers копируется под lock, затем вызывается вне lock. Это предотвращает deadlock при subscribe/unsubscribe внутри handler.

**Wildcard подписка:** `bus.subscribe("*", debug_handler)` — получает все события.

**Статистика:** `BusStats` — `published_count`, `handled_count`, `error_count`, `dropped_count`.

## Последствия

**Положительные:**
- Нет deadlock при subscribe/unsubscribe внутри handler
- Ошибка одного handler изолирована — остальные продолжают работу
- Простое тестирование — синхронный вызов, нет race conditions в тестах
- `BusStats` для observability

**Отрицательные:**
- Медленный handler блокирует весь publish() — нет параллелизма
- Нет backpressure — при перегрузке события не буферизуются

**Нейтральные:**
- P3-9 (Async EventBus) — запланированное расширение для thread pool dispatch
- Текущая архитектура совместима с async-расширением (интерфейс не изменится)

## Путь к Async EventBus (P3-9)

```python
# Будущая реализация
class AsyncEventBus(EventBus):
    def __init__(self, max_workers: int = 4):
        super().__init__()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def publish_async(self, event_type: str, payload: Any = None) -> Future:
        return self._executor.submit(self.publish, event_type, payload)
```

## Связанные решения

- ADR-002: RLock для thread safety (используется в EventBus)
- `docs/planning/TODO.md` P3-9: Async EventBus — запланированное расширение
