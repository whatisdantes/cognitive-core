# 🔮 FUTURE_TODO.md — Нереализованные функции для автономности системы

> **Версия:** 0.7.0  
> **Дата:** 2026  
> **Контекст:** Инфраструктура автономности (Scheduler, EventBus, ResourceMonitor,
> KnowledgeGapDetector, ReplayEngine) реализована. Не хватает интеграционного слоя —
> логики "что делать в idle" и механизма приёма внешних запросов в работающий процесс.
>
> **Обновление v0.7.0:** F-AUTO-4, F-AUTO-5, F-LOG-1, F-LOG-2, F-LOG-3, F-LOG-4 — ✅ ВЫПОЛНЕНО.
> BrainLogger интегрирован в CLI/Pipeline/MemoryManager/OutputPipeline (NullObject pattern).
> OnlineLearner вызывается в `step_post_cycle` (pipeline.py шаг 20).
> ReplayEngine интегрирован в `run_autonomous()` (cli.py).
> `--log-dir` / `--log-level` флаги добавлены в CLI.

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

### F-AUTO-4 — ReplayEngine в автономном цикле ✅ ВЫПОЛНЕНО

~~**Проблема:** `ReplayEngine` реализован, но не интегрирован в `run_autonomous()`.~~

**Статус:** ✅ Реализовано в v0.7.0. `ReplayEngine` интегрирован в `run_autonomous()` в `brain/cli.py`
(строки 155–170). Периодически воспроизводит эпизоды из `EpisodicMemory` для укрепления памяти.

**Файлы:** `brain/cli.py` ✅, `brain/learning/replay_engine.py` ✅  
**Приоритет:** ~~🟡 Средний~~ → ✅ Завершено

---

### F-AUTO-5 — OnlineLearner в когнитивном цикле ✅ ВЫПОЛНЕНО

~~**Проблема:** `OnlineLearner` реализован, но не вызывается после каждого взаимодействия.~~

**Статус:** ✅ Реализовано в v0.7.0. `OnlineLearner.update()` вызывается в `step_post_cycle`
(шаг 20 `CognitivePipeline`, `brain/cognition/pipeline.py`) после каждого когнитивного цикла.

**Файлы:** `brain/cognition/pipeline.py` ✅, `brain/learning/online_learner.py` ✅  
**Приоритет:** ~~🟡 Средний~~ → ✅ Завершено

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

> **Статус v0.7.0:** `BrainLogger`, `DigestGenerator`, `TraceBuilder` реализованы, протестированы
> (25 тестов) и **полностью интегрированы** в production-код (CLI, Pipeline, MemoryManager,
> OutputPipeline, EventBus, Scheduler). NullObject pattern обеспечивает backward compatibility.
> F-LOG-1 / F-LOG-2 / F-LOG-3 / F-LOG-4 — ✅ ВЫПОЛНЕНО.

### F-LOG-1 — BrainLogger интеграция в CognitivePipeline ✅ ВЫПОЛНЕНО

~~**Проблема:** `brain/cognition/pipeline.py` использует только `logging.getLogger()`. JSONL-логи не пишутся.~~

**Статус:** ✅ Реализовано в v0.7.0. `BrainLogger` интегрирован в `CognitivePipeline`, `MemoryManager`,
`InputRouter`, `OutputPipeline`, `EventBus`, `Scheduler` и `CLI` через NullObject pattern
(backward compatibility сохранена). JSONL-логи пишутся при передаче `--log-dir`.

**Файлы:** `brain/cognition/pipeline.py` ✅, `brain/cli.py` ✅  
**Приоритет:** ~~🔴 Высокий~~ → ✅ Завершено

---

### F-LOG-2 — DigestGenerator интеграция в run_query / run_autonomous ✅ ВЫПОЛНЕНО

~~**Проблема:** После каждого когнитивного цикла дайджест не генерируется. `brain/data/logs/digests/` пуст.~~

**Статус:** ✅ Реализовано в v0.7.0. `DigestGenerator` создаётся в `brain/cli.py` и вызывается
после каждого когнитивного цикла. Дайджесты записываются в `brain/data/logs/digests/YYYY-MM-DD.txt`
при активном `--log-dir`.

**Файлы:** `brain/cli.py` ✅  
**Приоритет:** ~~🟡 Средний~~ → ✅ Завершено

---

### F-LOG-3 — BrainLogger в CLI (--log-dir флаг) ✅ ВЫПОЛНЕНО

~~**Проблема:** Нет способа включить JSONL-логирование через CLI.~~

**Статус:** ✅ Реализовано в v0.7.0. Флаги `--log-dir` и `--log-level` добавлены в `build_parser()`
в `brain/cli.py`. Примеры:
```bash
cognitive-core --log-dir brain/data/logs --log-level INFO "Что такое нейрон?"
cognitive-core --autonomous --ticks 10 --log-dir brain/data/logs --log-level DEBUG
```

**Файлы:** `brain/cli.py` ✅  
**Приоритет:** ~~🟡 Средний~~ → ✅ Завершено

---

### F-LOG-4 — TraceBuilder интеграция (trace_id сквозной) ✅ ВЫПОЛНЕНО

~~**Проблема:** `trace_id` генерируется в `OutputTraceBuilder` (output layer), но не передаётся в `BrainLogger`. Нет сквозной трассировки запрос → память → рассуждение → ответ.~~

**Статус:** ✅ Реализовано в v0.7.0. `TraceBuilder` создаётся в `brain/cli.py`. `trace_id` генерируется
в начале `CognitivePipeline.run()` и сквозно передаётся во все шаги pipeline и в `BrainLogger`.

**Файлы:** `brain/cognition/pipeline.py` ✅, `brain/cli.py` ✅  
**Приоритет:** ~~🟡 Средний~~ → ✅ Завершено

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
| ~~**F-LOG-1**~~ | ~~**BrainLogger → CognitivePipeline**~~ | ✅ Завершено | — | — |
| F-AUTO-11 | Форматирование факта (без LLM) | 🟠 Средний-высокий | Малая | — |
| F-AUTO-6 | Периодическая консолидация | 🟠 Средний-высокий | Малая | F-AUTO-3 |
| ~~F-AUTO-4~~ | ~~ReplayEngine интеграция~~ | ✅ Завершено | — | — |
| ~~F-AUTO-5~~ | ~~OnlineLearner интеграция~~ | ✅ Завершено | — | — |
| F-AUTO-10 | LLM Bridge → OutputPipeline | 🟡 Средний | Средняя | — |
| F-AUTO-2 | Self-Reflection Loop | 🟡 Средний | Средняя | F-AUTO-3 |
| F-AUTO-14 | Метрики автономного режима | 🟡 Средний | Малая | — |
| ~~F-LOG-2~~ | ~~DigestGenerator интеграция~~ | ✅ Завершено | — | — |
| ~~F-LOG-3~~ | ~~--log-dir CLI флаг~~ | ✅ Завершено | — | — |
| ~~F-LOG-4~~ | ~~TraceBuilder сквозной trace_id~~ | ✅ Завершено | — | — |
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
5. ~~F-AUTO-4 — ReplayEngine~~ ✅ Завершено
6. ~~F-AUTO-5 — OnlineLearner~~ ✅ Завершено
7. F-AUTO-6 — Периодическая консолидация
8. F-AUTO-2 — Self-Reflection

**Фаза 3 (качество и наблюдаемость):**
9. ~~F-LOG-1 — BrainLogger → CognitivePipeline~~ ✅ Завершено
10. ~~F-LOG-2 — DigestGenerator~~ ✅ Завершено
11. ~~F-LOG-3 — --log-dir CLI~~ ✅ Завершено
12. ~~F-LOG-4 — сквозной trace_id~~ ✅ Завершено
13. F-AUTO-10 — LLM Bridge → Output
14. F-AUTO-14 — Метрики
15. F-AUTO-8 — IPC

**Фаза 4 (масштабирование):**
16. F-AUTO-9 — File Watcher
17. F-AUTO-13 — Персистентный Scheduler
18. F-LOG-5 — Просмотр логов через CLI
19. F-AUTO-12 — Многопроцессность
