# 🧠 Слой 0: Always-On Autonomous Loop (Ствол мозга)
## Подробное описание архитектуры и работы

> **Статус: ✅ Этап B завершён (Scheduler + ResourceMonitor реализованы)**  
> ✅ `events.py` — все типы событий + EventFactory  
> ✅ `contracts.py` — общие сквозные типы (Modality, Task, EncodedPercept, FusedPercept, TraceChain, BrainOutput)  
> ✅ `event_bus.py` — typed pub/sub шина событий  
> ✅ `scheduler.py` — тик-планировщик (heapq, 4 приоритета, адаптивный tick 100/500/2000ms) · 11/11 тестов  
> ✅ `resource_monitor.py` — CPU/RAM мониторинг, 4 политики деградации, гистерезис · 13/13 тестов  
> ⬜ `attention_controller.py` — контроллер внимания (Этап H.1)

---

## Что такое автономный цикл в биологии

**Ствол мозга** — самая древняя часть мозга. Он работает **непрерывно**, даже во сне:
- поддерживает дыхание, сердцебиение, температуру тела
- маршрутизирует сигналы между телом и корой
- управляет циклами сна/бодрствования
- никогда не «выключается»

**Ключевой принцип:** мозг — это не программа, которую запускают и останавливают. Это **живой процесс**, который существует непрерывно.

---

## Роль в искусственном мозге

```
Внешний мир (файлы, пользователь, события)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                 AUTONOMOUS LOOP (Ствол мозга)               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Scheduler (Тик-планировщик)             │   │
│  │  clock-driven тики + event-driven обработка          │   │
│  │  приоритетная очередь задач                          │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              EventBus (Шина событий)                 │   │
│  │  publish/subscribe для всех модулей                  │   │
│  │  типизированные события (PerceptEvent, MemoryEvent…) │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              ResourceMonitor (Гомеостаз)             │   │
│  │  CPU/RAM мониторинг → graceful degradation           │   │
│  │  динамический бюджет вычислений                      │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              AttentionController (Таламус)           │   │
│  │  бюджет внимания по модальностям                     │   │
│  │  goal-driven + salience-driven переключение          │   │
│  └──────────────────────┬───────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
              Все остальные модули мозга
    (Perception → Encoders → Fusion → Memory → Cognition → Output)
```

---

## Компонент 1: `Scheduler` — Тик-планировщик

**Файл:** `brain/core/scheduler.py`  
**Аналог:** Циркадные ритмы + ретикулярная формация ствола мозга

### Два режима работы

```
CLOCK-DRIVEN (регулярные тики):
  каждые T мс → запустить когнитивный цикл
  T = 100 мс (10 Hz) при нормальной нагрузке
  T = 500 мс при CPU > 70%
  T = 2000 мс при CPU > 85% (graceful degradation)

EVENT-DRIVEN (по событию):
  новый файл → немедленно запустить Perception
  сообщение пользователя → немедленно запустить Cognitive Core
  RAM > 85% → немедленно запустить ConsolidationEngine.cleanup()
```

### Приоритетная очередь задач

```python
class TaskPriority(Enum):
    CRITICAL  = 0   # угроза целостности системы (RAM > 90%)
    HIGH      = 1   # пользовательский ввод, срочные события
    NORMAL    = 2   # обычный когнитивный цикл
    LOW       = 3   # replay, consolidation, self-reflection
    IDLE      = 4   # метрики, дашборд, cleanup
```

### Структура `Task` (реализовано в `brain/core/contracts.py` ✅)

```python
@dataclass
class Task(ContractMixin):
    """Унифицированная задача для scheduler/event loop."""
    task_id: str                          # "task_a1b2c3"
    task_type: str                        # "think" | "consolidate" | "perceive" | ...
    payload: Dict[str, Any] = {}          # параметры задачи
    priority: float = 0.5                 # числовой приоритет (0.0–1.0)
    status: TaskStatus = PENDING          # PENDING | RUNNING | DONE | FAILED
    trace_id: str = ""                    # сквозной trace
    session_id: str = ""                  # ID сессии
    cycle_id: str = ""                    # ID тика
```

> ⚠️ **MVP-упрощение:** поля `module`, `action`, `deadline`, `created_at`,
> `retry_count`, `max_retries` из ранних спецификаций **не реализованы**.
> `priority` — числовой `float`, а не `TaskPriority` enum (enum используется
> только в `Scheduler.enqueue(task, priority=TaskPriority.NORMAL)`).
> Расширенная модель Task будет добавлена при реализации Этапа F (Cognitive Core).

### Цикл планировщика (реализовано ✅)

```python
# Реальный API Scheduler (brain/core/scheduler.py):

bus = EventBus()
scheduler = Scheduler(bus)

# Регистрация обработчика задачи
def handle_think(task: Task) -> Any:
    return {"result": "thought"}

scheduler.register_handler("think", handle_think)

# Добавление задачи в очередь
scheduler.enqueue(
    Task(task_id="t1", task_type="think", payload={"query": "нейрон"}),
    priority=TaskPriority.NORMAL,
)

# Один тик вручную (возвращает сводку)
info = scheduler.tick(resource_state=resource_monitor.check())

# Основной цикл (блокирующий, с адаптивным интервалом)
scheduler.run(
    max_ticks=None,                          # бесконечно
    resource_provider=resource_monitor.check # адаптация tick по CPU
)

# Остановка из другого потока
scheduler.stop()
```

> ✅ **Реализовано полностью:** `get_tick_interval()` адаптирует тик по CPU **и** RAM:
> NORMAL (CPU<70%, RAM<22GB)=100ms, DEGRADED (CPU 70–85%, RAM 22–28GB)=500ms,
> CRITICAL (CPU>85%, RAM 28–30GB)=2000ms, EMERGENCY (RAM>30GB)=5000ms.
> Все 4 уровня реализованы в `SchedulerConfig` (поля `tick_emergency_ms`, `ram_*_gb`).

---

## Компонент 2: `EventBus` — Шина событий

**Файл:** `brain/core/event_bus.py`  
**Аналог:** Нейромедиаторы — химические сигналы между отделами мозга

### Принцип работы

```
Модуль A публикует событие:
  event_bus.publish(PerceptEvent(text="нейрон", source="user"))
      │
      ▼
EventBus маршрутизирует подписчикам:
  ├── Encoders.on_percept(event)
  ├── WorkingMemory.on_percept(event)
  └── Logger.on_any(event)
```

### Типы событий (из `brain/core/events.py` ✅)

```python
# Уже реализовано в Фазе 1.4:

PerceptEvent      # новый входящий стимул (text/image/audio)
MemoryEvent       # операция с памятью (store/retrieve/forget)
CognitiveEvent    # когнитивное событие (goal/plan/decision)
LearningEvent     # событие обучения (update/replay/hypothesis)
SystemEvent       # системное событие (start/stop/error/resource)
```

### API (✅ реализовано в `brain/core/event_bus.py`)

> ⚠️ **MVP-решение: строковый API.**
> EventBus использует строковые `event_type` и произвольный `payload: Any`.
> Это **намеренное упрощение** для MVP — не требует импорта конкретных классов событий.
> В будущем (Этап C/D) будет добавлен адаптер для передачи dataclass-событий
> (`PerceptEvent`, `SystemEvent`) напрямую через шину.

```python
from brain.core import EventBus, BusStats

bus = EventBus()

# Сигнатура handler: (event_type: str, payload: Any, trace_id: str) -> None
def on_percept(event_type: str, payload, trace_id: str):
    print(f"[{trace_id}] {event_type}: {payload}")

# Подписка на строковый тип события
bus.subscribe("percept", on_percept)

# Wildcard — получать ВСЕ события (для логирования)
bus.subscribe("*", logger_handler)

# Публикация (payload — любой объект: dict, dataclass, str)
n_handled = bus.publish(
    event_type="percept",
    payload={"text": "Что такое нейрон?", "modality": "text"},
    trace_id="t-001",
)

# Отписка
bus.unsubscribe("percept", on_percept)

# Статистика
stats: BusStats = bus.stats
# stats.published_count, stats.handled_count, stats.error_count, stats.dropped_count

# Observability
print(bus.status())
# {'subscribed_types': ['percept', '*'], 'total_handlers': 2,
#  'published_count': 1, 'handled_count': 1, 'error_count': 0, 'dropped_count': 0}
```

### Гарантии доставки

```
СИНХРОННЫЙ ВЫЗОВ:
  publish() вызывает все handlers в текущем потоке (в рамках тика).
  Ошибка одного handler логируется и НЕ прерывает остальных.

WILDCARD ("*"):
  Подписчик на "*" получает все события любого типа.
  Используется для BrainLogger и MetricsCollector.

DROPPED:
  Если для event_type нет ни одного подписчика — dropped_count++.
  Событие не теряется молча: счётчик виден в status().
```

---

## Компонент 3: `ResourceMonitor` — Монитор ресурсов (Гомеостаз)

**Файл:** `brain/core/resource_monitor.py`  
**Аналог:** Гипоталамус — поддержание гомеостаза (температура, давление, ресурсы)

### Принцип работы

```
Каждые 5 секунд (фоновый поток):
    │
    ▼
ResourceMonitor.check()
    │
    ├── CPU usage (psutil.cpu_percent)
    ├── RAM usage (psutil.virtual_memory)
    ├── Thread count (threading.active_count)
    └── Model memory (оценка по размерам загруженных моделей)
    │
    ▼
ResourceState(cpu_pct, ram_gb, ram_pct, threads, models_gb)
    │
    ▼
Применить политику деградации:
    ├── NORMAL    (CPU < 70%, RAM < 22 GB) → tick=100ms, все модули активны
    ├── DEGRADED  (CPU 70–85%, RAM 22–28 GB) → tick=500ms, отключить replay
    ├── CRITICAL  (CPU > 85%, RAM > 28 GB) → tick=2000ms, только core функции
    └── EMERGENCY (RAM > 30 GB) → принудительная выгрузка моделей
```

### Таблица политик деградации

| Состояние | CPU | RAM | Tick | Отключить |
|-----------|-----|-----|------|-----------|
| NORMAL | < 70% | < 22 GB | 100 мс | — |
| DEGRADED | 70–85% | 22–28 GB | 500 мс | ReplayEngine, SelfSupervised |
| CRITICAL | > 85% | 28–30 GB | 2000 мс | Learning Loop, Vision/Audio |
| EMERGENCY | любой | > 30 GB | 5000 мс | Все кроме Memory + Output |

### Структура `ResourceState` (реализовано в `brain/core/contracts.py` ✅)

```python
@dataclass
class ResourceState(ContractMixin):
    """Снимок ресурсного состояния системы."""
    cpu_pct: float = 0.0          # загрузка CPU 0–100%
    ram_pct: float = 0.0          # использовано RAM в %
    ram_used_mb: float = 0.0      # использовано RAM в MB
    ram_total_mb: float = 0.0     # всего RAM в MB
    available_threads: int = 1    # доступных потоков
    ring2_allowed: bool = True    # разрешены тяжёлые ветки (CPU < 85%)
    soft_blocked: bool = False    # мягкая блокировка (CPU > 70%)
```

> ⚠️ **MVP-упрощение:** поля `ram_gb`, `ram_available_gb`, `models_gb`, `policy`, `timestamp`
> из ранних спецификаций **не реализованы** в текущем контракте.
> `policy` и `timestamp` доступны через `ResourceMonitor.status()` и `DegradationPolicy`.
> Будут добавлены в контракт при реализации Этапа H (AttentionController).

### Graceful Degradation

```
EMERGENCY (RAM > 30 GB):
  1. Выгрузить Vision Encoder (освободить ~600 MB)
  2. Выгрузить Audio Encoder (освободить ~1.5 GB)
  3. Принудительный ConsolidationEngine.aggressive_cleanup()
  4. Уведомить через SystemEvent(level="CRITICAL", ...)
  5. Если RAM > 31 GB → выгрузить Text Encoder (fallback: navec)
```

---

## Компонент 4: `AttentionController` — Контроллер внимания

**Файл:** `brain/core/attention_controller.py`  
**Аналог:** Таламус — маршрутизация и фильтрация потоков внимания

### Два контура внимания

```
GOAL-DRIVEN ATTENTION (сверху вниз):
  Текущая цель: "ответить на вопрос о нейронах"
      │
      ▼
  Приоритет: текст > изображения > аудио
  Бюджет CPU: 60% на text encoder, 30% на memory, 10% на остальное
  Фильтр: игнорировать нерелевантные входы

SALIENCE-DRIVEN ATTENTION (снизу вверх):
  Новый стимул с высоким salience (urgency=0.9)
      │
      ▼
  Прервать текущую задачу
  Переключить внимание на новый стимул
  Обновить бюджет CPU
```

### Бюджет вычислений по модальностям

```python
class AttentionBudget:
    """
    Распределение вычислительных ресурсов по модальностям.
    Сумма всегда = 1.0 (100% доступного CPU).
    """
    text: float    # доля CPU для текстовой обработки
    vision: float  # доля CPU для визуальной обработки
    audio: float   # доля CPU для аудио обработки
    memory: float  # доля CPU для операций с памятью
    cognition: float  # доля CPU для когнитивного ядра

# Примеры бюджетов:
BUDGET_TEXT_FOCUSED = AttentionBudget(
    text=0.50, vision=0.10, audio=0.05, memory=0.25, cognition=0.10
)
BUDGET_MULTIMODAL = AttentionBudget(
    text=0.30, vision=0.25, audio=0.20, memory=0.15, cognition=0.10
)
BUDGET_DEGRADED = AttentionBudget(
    text=0.70, vision=0.00, audio=0.00, memory=0.20, cognition=0.10
)
```

### Адаптация бюджета

```
При CPU > 70%:
  → vision = 0, audio = 0 (самые дорогие модальности)
  → text += 0.3 (самая дешёвая модальность)

При новом срочном событии (salience > 0.8):
  → cognition += 0.2 (больше ресурсов на обработку)
  → memory -= 0.1 (временно снизить фоновые операции)

При idle (CPU < 30%):
  → replay += 0.2 (использовать простой для обучения)
  → metrics += 0.1 (обновить дашборд)
```

---

## Жизненный цикл мозга

```
python main.py
    │
    ▼
[INIT]
  1. Создать EventBus
  2. Создать ResourceMonitor (запустить фоновый поток)
  3. Создать Scheduler
  4. Инициализировать все модули (Memory, Encoders, Cognition, ...)
  5. Загрузить состояние из JSON (если есть)
  6. Опубликовать SystemEvent(event="brain_started")
    │
    ▼
[MAIN LOOP] ← Scheduler.run()
  while brain.is_alive:
    check_resources()
    process_events()
    execute_tasks()
    run_idle_tasks()
    sleep(tick_interval)
    │
    ▼
[SHUTDOWN] ← SIGINT / SIGTERM / /выход
  1. Опубликовать SystemEvent(event="brain_stopping")
  2. Дождаться завершения текущих задач (timeout=10с)
  3. Сохранить состояние в JSON
  4. Остановить фоновые потоки (ConsolidationEngine, ResourceMonitor)
  5. Опубликовать SystemEvent(event="brain_stopped")
  6. Выход
```

---

## Взаимодействие с другими модулями

```
Autonomous Loop — это ИНФРАСТРУКТУРА, не слой обработки.
Все остальные модули зависят от него:

EventBus:
  ← Perception публикует PerceptEvent
  ← Memory публикует MemoryEvent
  ← Cognition публикует CognitiveEvent
  → Все модули подписываются на нужные события

Scheduler:
  → запускает Perception (по событию или по таймеру)
  → запускает Cognitive Core (по событию)
  → запускает ConsolidationEngine (каждые 30с)
  → запускает ReplayEngine (каждые 30 мин при idle)
  → запускает MetricsCollector (каждые 60с)

ResourceMonitor:
  → уведомляет Scheduler об изменении политики
  → уведомляет AttentionController об изменении бюджета
  → уведомляет ConsolidationEngine о необходимости cleanup
```

---

## Ресурсный бюджет (CPU-only, 32 GB RAM)

| Компонент | RAM | CPU | Поток |
|-----------|-----|-----|-------|
| Scheduler | ~1 MB | < 1% | 1 (main) |
| EventBus | ~2 MB | < 1% | 1 (main) |
| ResourceMonitor | ~1 MB | < 1% | 1 (daemon) |
| AttentionController | ~1 MB | < 1% | 1 (main) |
| **Итого** | **~5 MB** | **< 2%** | **2 потока** |

> Autonomous Loop намеренно минималистичен — он не должен потреблять ресурсы, нужные для мышления.

---

## Статус реализации

| Компонент | Статус | Файл |
|-----------|--------|------|
| `BaseEvent` + все dataclasses событий | ✅ Реализовано | `brain/core/events.py` |
| `contracts.py` — общие типы | ✅ Реализовано | `brain/core/contracts.py` |
| `EventBus` — typed pub/sub шина | ✅ Реализовано | `brain/core/event_bus.py` |
| `Scheduler` | ✅ Реализовано (11/11 тестов) | `brain/core/scheduler.py` |
| `ResourceMonitor` | ✅ Реализовано (13/13 тестов) | `brain/core/resource_monitor.py` |
| `AttentionController` | ⬜ Этап H.1 | `brain/core/attention_controller.py` |
