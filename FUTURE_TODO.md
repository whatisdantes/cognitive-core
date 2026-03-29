# 🔮 FUTURE_TODO.md — Нереализованные функции для автономности системы

> **Версия:** 0.7.0  
> **Дата:** 2025  
> **Контекст:** Инфраструктура автономности (Scheduler, EventBus, ResourceMonitor,
> KnowledgeGapDetector, ReplayEngine) реализована. Не хватает интеграционного слоя —
> логики "что делать в idle" и механизма приёма внешних запросов в работающий процесс.

---

## 🎯 Цель: настоящая автономность

Система должна работать **непрерывно** — как живой процесс:
- запускается один раз и работает всегда
- самостоятельно занимает себя в idle (обучение, рефлексия, консолидация)
- обращения пользователя — лишь **один из каналов** получения новой информации
- адаптируется к ресурсам (CPU/RAM) без остановки

---

## 📋 Блок 1: Самогенерация задач (Idle Loop)

### F-AUTO-1 — KnowledgeGapDetector → Scheduler интеграция

**Проблема:** В idle очередь Scheduler пустеет. Система ничего не делает.

**Решение:** В `run_autonomous()` добавить idle-loop:
```python
def handle_idle_tick(task: Task) -> dict:
    """Генерировать задачи из пробелов в знаниях."""
    gaps = knowledge_gap_detector.detect(memory_manager)
    for gap in gaps[:3]:  # не более 3 за тик
        scheduler.enqueue(
            Task(task_type="cognitive_cycle", payload={"query": gap.question}),
            TaskPriority.LOW,
        )
    return {"gaps_found": len(gaps)}

# Регистрировать как повторяющуюся задачу каждые N тиков
scheduler.register_recurring("idle_gap_fill", handle_idle_tick, every_n_ticks=5)
```

**Файлы:** `brain/cli.py`, `brain/learning/knowledge_gap_detector.py`, `brain/core/scheduler.py`  
**Зависимости:** `KnowledgeGapDetector` реализован ✅, нужна интеграция  
**Приоритет:** 🔴 Высокий — без этого автономность невозможна

---

### F-AUTO-2 — Self-Reflection Loop

**Проблема:** Система не анализирует собственную память и не генерирует гипотезы самостоятельно.

**Решение:** Периодическая задача `self_reflect`:
```python
def handle_self_reflect(task: Task) -> dict:
    """Анализировать память → генерировать вопросы для углубления знаний."""
    # Взять топ-N наиболее важных концептов
    top_concepts = memory_manager.semantic.get_most_important(top_n=5)
    for node in top_concepts:
        # Генерировать уточняющий вопрос
        question = f"Что ещё известно о {node.concept}?"
        scheduler.enqueue(
            Task(task_type="cognitive_cycle", payload={"query": question}),
            TaskPriority.LOW,
        )
    return {"reflected_on": len(top_concepts)}
```

**Файлы:** `brain/cli.py`, `brain/memory/semantic_memory.py`  
**Приоритет:** 🟡 Средний

---

### F-AUTO-3 — Recurring Task API в Scheduler

**Проблема:** `Scheduler` не поддерживает повторяющиеся задачи (`every_n_ticks`).

**Решение:** Добавить `register_recurring(task_type, handler, every_n_ticks)` в `Scheduler`:
```python
@dataclass
class RecurringTask:
    task_type: str
    every_n_ticks: int
    last_tick: int = 0

class Scheduler:
    def register_recurring(self, task_type: str, handler, every_n_ticks: int): ...
    def _check_recurring(self, current_tick: int): ...  # вызывать в tick()
```

**Файлы:** `brain/core/scheduler.py`  
**Приоритет:** 🔴 Высокий — нужен для F-AUTO-1, F-AUTO-4, F-AUTO-5

---

## 📋 Блок 2: Фоновое обучение

### F-AUTO-4 — ReplayEngine в автономном цикле

**Проблема:** `ReplayEngine` реализован, но не интегрирован в `run_autonomous()`.

**Решение:** Периодическая задача `replay_episodes` каждые 30 тиков при idle:
```python
def handle_replay(task: Task) -> dict:
    """Воспроизвести эпизоды для укрепления памяти."""
    replayed = replay_engine.replay(memory_manager, n_episodes=10)
    return {"replayed": replayed}

scheduler.register_recurring("replay_episodes", handle_replay, every_n_ticks=30)
```

**Файлы:** `brain/cli.py`, `brain/learning/replay_engine.py`  
**Зависимости:** `ReplayEngine` реализован ✅, нужна интеграция  
**Приоритет:** 🟡 Средний

---

### F-AUTO-5 — OnlineLearner в когнитивном цикле

**Проблема:** `OnlineLearner` реализован, но не вызывается после каждого взаимодействия.

**Решение:** В `handle_cognitive_cycle` после `core.run()` вызывать `online_learner.update()`:
```python
result = core.run(query)
online_learner.update(
    query=query,
    response=result.response,
    action=result.action,
    confidence=result.confidence,
)
```

**Файлы:** `brain/cli.py`, `brain/learning/online_learner.py`  
**Зависимости:** `OnlineLearner` реализован ✅, нужна интеграция  
**Приоритет:** 🟡 Средний

---

### F-AUTO-6 — Периодическая консолидация памяти

**Проблема:** `mm.save_all()` вызывается только в конце. При долгой работе данные могут потеряться.

**Решение:** Периодическая задача `consolidate_memory` каждые 10 тиков:
```python
scheduler.register_recurring("consolidate_memory", handle_consolidate_memory, every_n_ticks=10)
```

**Файлы:** `brain/cli.py`  
**Приоритет:** 🟠 Средний-высокий (надёжность данных)

---

## 📋 Блок 3: Внешний ввод в работающий процесс

### F-AUTO-7 — Stdin Reader (интерактивный режим)

**Проблема:** Нельзя отправить запрос в работающий автономный процесс. Пользователь и автономный режим — два отдельных процесса.

**Решение:** Читать stdin в отдельном потоке и добавлять запросы в очередь Scheduler:
```python
import threading

def _stdin_reader(scheduler: Scheduler):
    """Читать запросы из stdin и добавлять в очередь с HIGH приоритетом."""
    for line in sys.stdin:
        query = line.strip()
        if query:
            scheduler.enqueue(
                Task(task_type="cognitive_cycle", payload={"query": query}),
                TaskPriority.HIGH,
            )

stdin_thread = threading.Thread(target=_stdin_reader, args=(scheduler,), daemon=True)
stdin_thread.start()
```

**Файлы:** `brain/cli.py`  
**Приоритет:** 🔴 Высокий — ключевой для интерактивной автономности

---

### F-AUTO-8 — Unix Socket / Named Pipe IPC

**Проблема:** Stdin reader работает только в терминале. Для интеграции с другими процессами нужен IPC.

**Решение:** Unix socket сервер в отдельном потоке:
```python
# brain/core/ipc_server.py
class IPCServer:
    """Принимать запросы через Unix socket → Scheduler.enqueue()."""
    def __init__(self, socket_path: str, scheduler: Scheduler): ...
    def start(self): ...  # daemon thread
    def stop(self): ...
```

**Файлы:** `brain/core/ipc_server.py` (новый), `brain/cli.py`  
**Приоритет:** 🟡 Средний (нужен для интеграции с внешними системами)

---

### F-AUTO-9 — File Watcher (Perception из среды)

**Проблема:** Система не воспринимает новые данные из файловой системы автономно.

**Решение:** Наблюдатель за директорией `--watch-dir`:
```python
# brain/perception/file_watcher.py
class FileWatcher:
    """Следить за директорией → публиковать PerceptEvent при новых файлах."""
    def __init__(self, watch_dir: str, bus: EventBus): ...
    def start(self): ...  # daemon thread
```

**Файлы:** `brain/perception/file_watcher.py` (новый), `brain/cli.py`  
**Зависимости:** `watchdog` (опциональная зависимость)  
**Приоритет:** 🟢 Низкий (Post-MVP)

---

## 📋 Блок 4: Улучшение качества ответов

### F-AUTO-10 — LLM Bridge интеграция в OutputPipeline

**Проблема:** LLM Bridge реализован (Этап N), но не интегрирован в `OutputPipeline`. Ответы шаблонные.

**Решение:** В `DialogueResponder.generate()` добавить опциональный LLM вызов:
```python
if self._llm_provider and result.action in ("respond_direct", "respond_hedged"):
    llm_text = self._llm_provider.generate(
        prompt=f"Ответь на вопрос: {result.goal}\nФакт: {result.response}",
        max_tokens=200,
    )
    if llm_text:
        text = llm_text
```

**Файлы:** `brain/output/dialogue_responder.py`, `brain/bridges/llm_bridge.py`  
**Зависимости:** LLM Bridge реализован ✅, нужна интеграция  
**Приоритет:** 🟡 Средний (значительно улучшает качество ответов)

---

### F-AUTO-11 — Форматирование факта в естественный язык (без LLM)

**Проблема:** Ответ показывает raw storage format: `«нейрон: основная клетка...»` вместо `«Нейрон — это основная клетка...»`.

**Решение:** В `HypothesisEngine._generate_associative()` парсить `ev.content`:
```python
# Если content = "concept: description" → форматировать как "Concept — это description"
if ": " in content_preview:
    concept_part, desc_part = content_preview.split(": ", 1)
    statement = f"Ответ: {concept_part.capitalize()} — это {desc_part}"
else:
    statement = f"Ответ основан на факте: «{content_preview}»"
```

**Файлы:** `brain/cognition/hypothesis_engine.py`  
**Приоритет:** 🟠 Средний-высокий (UX без LLM)

---

## 📋 Блок 5: Долгосрочная архитектура

### F-AUTO-12 — Многопроцессная архитектура

**Проблема:** Всё работает в одном процессе. Тяжёлые операции (LLM, encoding) блокируют когнитивный цикл.

**Решение:** Разделить на процессы:
- `brain-core` — основной когнитивный процесс
- `brain-perception` — восприятие (file watcher, stdin)
- `brain-llm` — LLM Bridge (опционально)
- Коммуникация через IPC/Redis

**Приоритет:** 🟢 Низкий (Post-MVP, архитектурное решение)

---

### F-AUTO-13 — Персистентное состояние Scheduler

**Проблема:** При перезапуске очередь задач теряется.

**Решение:** Сохранять очередь в SQLite при shutdown, восстанавливать при startup.

**Файлы:** `brain/core/scheduler.py`, `brain/memory/storage.py`  
**Приоритет:** 🟢 Низкий

---

### F-AUTO-14 — Метрики и дашборд автономного режима

**Проблема:** Нет наблюдаемости за работой автономного процесса в реальном времени.

**Решение:** Периодический вывод метрик или HTTP endpoint:
```
[autonomous] tick=42 queue=3 cycles=38 memory_nodes=127 avg_confidence=0.73
```

**Файлы:** `brain/cli.py`, `brain/logging/brain_logger.py`  
**Приоритет:** 🟡 Средний (observability)

---

## 📋 Блок 6: Интеграция системы логирования

> **Статус:** `BrainLogger`, `DigestGenerator`, `TraceBuilder` реализованы и протестированы
> (25 тестов), но **нигде не вызываются** в production-коде. Ghost modules.

### F-LOG-1 — BrainLogger интеграция в CognitivePipeline

**Проблема:** `brain/cognition/pipeline.py` использует только `logging.getLogger()`. JSONL-логи не пишутся.

**Решение:** Передать `BrainLogger` в `CognitivePipeline` и логировать каждый шаг:
```python
# brain/cognition/pipeline.py
class CognitivePipeline:
    def __init__(self, ..., brain_logger: Optional[BrainLogger] = None):
        self._brain_logger = brain_logger

    def _step_reason(self, ctx):
        result = self._reasoner.reason(...)
        if self._brain_logger:
            self._brain_logger.info(
                module="reasoner",
                event="reasoning_complete",
                trace_id=ctx.trace_id,
                state={"confidence": result.confidence, "action": result.action},
            )
```

**Файлы:** `brain/cognition/pipeline.py`, `brain/cli.py`  
**Приоритет:** 🔴 Высокий — без этого observability отсутствует

---

### F-LOG-2 — DigestGenerator интеграция в run_query / run_autonomous

**Проблема:** После каждого когнитивного цикла дайджест не генерируется. `brain/data/logs/digests/` пуст.

**Решение:** В `run_query()` и `handle_cognitive_cycle()` вызывать `DigestGenerator`:
```python
from brain.logging import BrainLogger, DigestGenerator, CycleInfo

digest_gen = DigestGenerator()

# После core.run():
cycle_info = CycleInfo(
    cycle_id=f"cycle_{core.cycle_count}",
    goal=query,
    confidence=result.confidence,
    action=result.action,
    response_preview=output.text[:120],
    duration_ms=elapsed_ms,
)
digest_gen.generate_cycle_digest(cycle_info)
```

**Файлы:** `brain/cli.py`  
**Приоритет:** 🟡 Средний

---

### F-LOG-3 — BrainLogger в CLI (--log-dir флаг)

**Проблема:** Нет способа включить JSONL-логирование через CLI.

**Решение:** Добавить `--log-dir` и `--log-level` флаги:
```bash
cognitive-core --log-dir brain/data/logs --log-level INFO "Что такое нейрон?"
cognitive-core --autonomous --log-dir /var/log/brain --ticks 0
```

**Файлы:** `brain/cli.py`  
**Приоритет:** 🟡 Средний

---

### F-LOG-4 — TraceBuilder интеграция (trace_id сквозной)

**Проблема:** `trace_id` генерируется в `OutputTraceBuilder` (output layer), но не передаётся в `BrainLogger`. Нет сквозной трассировки запрос → память → рассуждение → ответ.

**Решение:** Генерировать `trace_id` в начале `CognitivePipeline.run()` и передавать во все шаги + `BrainLogger`.

**Файлы:** `brain/cognition/pipeline.py`, `brain/output/trace_builder.py`  
**Приоритет:** 🟡 Средний

---

### F-LOG-5 — Просмотр логов через CLI

**Проблема:** Нет команды для просмотра накопленных логов.

**Решение:**
```bash
cognitive-core --show-logs --last 20          # последние 20 событий
cognitive-core --show-digest --date 2025-01-15 # дайджест за день
cognitive-core --show-trace <trace_id>         # трассировка по ID
```

**Файлы:** `brain/cli.py`  
**Приоритет:** 🟢 Низкий

---

## 📊 Сводная таблица приоритетов

| ID | Название | Приоритет | Сложность | Зависимости |
|----|----------|-----------|-----------|-------------|
| F-AUTO-3 | Recurring Task API в Scheduler | 🔴 Высокий | Средняя | — |
| F-AUTO-1 | KnowledgeGapDetector → Scheduler | 🔴 Высокий | Малая | F-AUTO-3 |
| F-AUTO-7 | Stdin Reader | 🔴 Высокий | Малая | — |
| **F-LOG-1** | **BrainLogger → CognitivePipeline** | **🔴 Высокий** | **Малая** | **—** |
| F-AUTO-11 | Форматирование факта (без LLM) | 🟠 Средний-высокий | Малая | — |
| F-AUTO-6 | Периодическая консолидация | 🟠 Средний-высокий | Малая | F-AUTO-3 |
| F-AUTO-4 | ReplayEngine интеграция | 🟡 Средний | Малая | F-AUTO-3 |
| F-AUTO-5 | OnlineLearner интеграция | 🟡 Средний | Малая | — |
| F-AUTO-10 | LLM Bridge → OutputPipeline | 🟡 Средний | Средняя | — |
| F-AUTO-2 | Self-Reflection Loop | 🟡 Средний | Средняя | F-AUTO-3 |
| F-AUTO-14 | Метрики автономного режима | 🟡 Средний | Малая | — |
| F-LOG-2 | DigestGenerator интеграция | 🟡 Средний | Малая | F-LOG-1 |
| F-LOG-3 | --log-dir CLI флаг | 🟡 Средний | Малая | F-LOG-1 |
| F-LOG-4 | TraceBuilder сквозной trace_id | 🟡 Средний | Средняя | F-LOG-1 |
| F-AUTO-8 | Unix Socket IPC | 🟡 Средний | Средняя | — |
| F-AUTO-9 | File Watcher | 🟢 Низкий | Средняя | — |
| F-AUTO-13 | Персистентный Scheduler | 🟢 Низкий | Средняя | — |
| F-LOG-5 | Просмотр логов через CLI | 🟢 Низкий | Малая | F-LOG-1 |
| F-AUTO-12 | Многопроцессная архитектура | 🟢 Низкий | Высокая | — |

---

## 🚀 Рекомендуемый порядок реализации

**Фаза 1 (минимальная автономность):**
1. F-AUTO-3 — Recurring Task API (основа для всего)
2. F-AUTO-7 — Stdin Reader (интерактивность)
3. F-AUTO-1 — KnowledgeGapDetector интеграция (самогенерация)
4. F-AUTO-11 — Форматирование ответа (UX)

**Фаза 2 (обучение в фоне):**
5. F-AUTO-4 — ReplayEngine
6. F-AUTO-5 — OnlineLearner
7. F-AUTO-6 — Периодическая консолидация
8. F-AUTO-2 — Self-Reflection

**Фаза 3 (качество и наблюдаемость):**
9. F-LOG-1 — BrainLogger → CognitivePipeline
10. F-LOG-2 — DigestGenerator
11. F-LOG-3 — --log-dir CLI
12. F-LOG-4 — сквозной trace_id
13. F-AUTO-10 — LLM Bridge → Output
14. F-AUTO-14 — Метрики
15. F-AUTO-8 — IPC

**Фаза 4 (масштабирование):**
16. F-AUTO-9 — File Watcher
17. F-AUTO-13 — Персистентный Scheduler
18. F-LOG-5 — Просмотр логов через CLI
19. F-AUTO-12 — Многопроцессность
