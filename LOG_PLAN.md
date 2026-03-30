# 📋 LOG_PLAN.md — План интеграции BrainLogger во все слои системы

> **Версия:** 2.0 (обновлён после ревью)  
> **Статус:** Утверждён  
> **Контекст:** BrainLogger, DigestGenerator, TraceBuilder реализованы и покрыты 25 тестами,  
> но **нигде не вызываются** в production-коде (ghost modules).

---

## 🎯 Цель

Интегрировать `BrainLogger` в 8 ключевых модулей системы, чтобы:
1. Каждый когнитивный цикл записывался в JSONL (brain.jsonl + категорийные файлы)
2. `DigestGenerator` генерировал человекочитаемые дайджесты после каждого цикла
3. `TraceBuilder` (reasoning_tracer) получал сквозной `trace_id` для полной трассировки
4. CLI получил флаги `--log-dir` и `--log-level` для управления логированием
5. Все существующие 1774 теста продолжали проходить без изменений

---

## 🏗️ Архитектурное решение: DI + NullObject

### Почему DI, а не глобальный singleton:
- **Паттерн проекта:** CognitiveCore уже принимает MemoryManagerProtocol, TextEncoderProtocol, EventBusProtocol, ResourceMonitorProtocol, LLMProvider — все через конструктор. BrainLogger следует тому же паттерну.
- **Тестируемость:** 1774 теста создают модули без BrainLogger. Singleton заставил бы каждый тест взаимодействовать с глобальным состоянием.
- **Thread safety:** DI делает зависимость явной. Singleton добавил бы неявную связанность.
- **Многопроцессность:** В будущем каждый CognitiveCore сможет иметь свой BrainLogger.

### NullBrainLogger — устранение if-boilerplate (Проблема 1 ✅)

Вместо 50+ проверок `if self._blog:` — NullObject pattern:

```python
# brain/logging/brain_logger.py — добавить в конец файла

class NullBrainLogger:
    """No-op BrainLogger для случаев, когда логирование не нужно."""
    def log(self, *a: Any, **kw: Any) -> None: pass
    def debug(self, *a: Any, **kw: Any) -> None: pass
    def info(self, *a: Any, **kw: Any) -> None: pass
    def warn(self, *a: Any, **kw: Any) -> None: pass
    def error(self, *a: Any, **kw: Any) -> None: pass
    def critical(self, *a: Any, **kw: Any) -> None: pass
    def flush(self) -> None: pass
    def close(self) -> None: pass
    def get_events(self, trace_id: str) -> List[dict]: return []
    def get_session(self, session_id: str) -> List[dict]: return []
    def get_recent(self, n: int = 10, min_level: str = "DEBUG") -> List[dict]: return []

_NULL_LOGGER = NullBrainLogger()
```

Тогда в конструкторах — без проверок:
```python
def __init__(self, ..., brain_logger: Optional[BrainLogger] = None):
    self._blog = brain_logger or _NULL_LOGGER

# В коде — прямой вызов, без if:
self._blog.info("reasoner", "reasoning_completed", ...)
```

**Экономия:** убирает 50+ if-ов, код чище, невозможно забыть guard.

### NullTraceBuilder — консистентность с NullBrainLogger (опционально ✅)

TraceBuilder используется только в Pipeline (3 if-а vs 50+ у BrainLogger), но для единообразия:

```python
# brain/logging/reasoning_tracer.py — добавить в конец файла

class NullTraceBuilder:
    """No-op TraceBuilder для случаев, когда трассировка не нужна."""
    def start_trace(self, *a: Any, **kw: Any) -> None: pass
    def add_step(self, *a: Any, **kw: Any) -> None: pass
    def add_input_ref(self, *a: Any, **kw: Any) -> None: pass
    def add_memory_ref(self, *a: Any, **kw: Any) -> None: pass
    def add_output_ref(self, *a: Any, **kw: Any) -> None: pass
    def set_summary(self, *a: Any, **kw: Any) -> None: pass
    def finish_trace(self, *a: Any, **kw: Any) -> None: pass
    def reconstruct(self, *a: Any, **kw: Any) -> None: return None
    def active_traces(self) -> list: return []

_NULL_TRACE_BUILDER = NullTraceBuilder()
```

Тогда в Pipeline:
```python
def __init__(self, ..., trace_builder: Optional[TraceBuilder] = None):
    self._trace_builder = trace_builder or _NULL_TRACE_BUILDER

# В коде — без if:
self._trace_builder.start_trace(trace_id, ...)
```

### Цепочка инъекции:
```
cli.py (создаёт BrainLogger, TraceBuilder)
  → CognitiveCore(brain_logger=..., trace_builder=...)
    → CognitivePipeline(brain_logger=..., trace_builder=...)
    → MemoryManager(brain_logger=...)
  → OutputPipeline(brain_logger=...)
  → InputRouter(brain_logger=...)  (если используется)
```

---

## 📊 Информация, собранная из анализа файлов

### Текущее состояние логирования по модулям:

| Модуль | Файл | Текущий логгер | BrainLogger |
|--------|-------|----------------|-------------|
| CLI | `brain/cli.py` | `logging.getLogger(__name__)` | ❌ |
| CognitiveCore | `brain/cognition/cognitive_core.py` | `logging.getLogger(__name__)` | ❌ |
| CognitivePipeline | `brain/cognition/pipeline.py` | `logging.getLogger(__name__)` | ❌ |
| MemoryManager | `brain/memory/memory_manager.py` | `logging.getLogger(__name__)` + `on_event` callback | ❌ |
| InputRouter | `brain/perception/input_router.py` | `logging.getLogger(__name__)` | ❌ |
| OutputPipeline | `brain/output/dialogue_responder.py` | `logging.getLogger(__name__)` | ❌ |
| EventBus | `brain/core/event_bus.py` | `logging.getLogger(__name__)` | ❌ |
| Scheduler | `brain/core/scheduler.py` | `logging.getLogger(__name__)` | ❌ |

### BrainLogger API (уже реализован):
```python
BrainLogger.log(level, module, event, *, session_id, cycle_id, trace_id,
                input_ref, memory_refs, state, decision, latency_ms, notes, **extra)
BrainLogger.debug/info/warn/error/critical(module, event, **kwargs)
BrainLogger.get_events(trace_id) → List[dict]
BrainLogger.get_session(session_id) → List[dict]
BrainLogger.get_recent(n, min_level) → List[dict]
```

### Категории событий (автоматическая маршрутизация по event prefix):
- `goal_*`, `plan_*`, `reasoning_*`, `action_*`, `hypothesis_*` → `cognitive.jsonl`
- `fact_*`, `episode_*`, `consolidation_*`, `memory_*`, `confidence_*` → `memory.jsonl`
- `text_ingested`, `percept_*`, `parse_*` → `perception.jsonl`
- `online_update`, `replay_*`, `gap_*`, `learning_*` → `learning.jsonl`
- `blacklist`, `audit_*`, `boundary_*`, `trust_updated` → `safety_audit.jsonl`

### CognitivePipelineContext (уже содержит нужные ID):
```python
ctx.cognitive_context.session_id  # ✅ есть
ctx.cognitive_context.cycle_id    # ✅ есть
ctx.cognitive_context.trace_id    # ✅ есть
```

---

## 📝 Детальный план изменений по файлам

### Фаза 0: NullBrainLogger (инфраструктура)

#### 0.1 `brain/logging/brain_logger.py` — Добавить NullBrainLogger

**Изменения:**
- Добавить класс `NullBrainLogger` с no-op методами
- Добавить модульную константу `_NULL_LOGGER = NullBrainLogger()`
- Экспортировать `NullBrainLogger` из `brain/logging/__init__.py`

---

### Фаза 1: CLI + инфраструктура (точка создания BrainLogger)

#### 1.1 `brain/cli.py` — Создание BrainLogger + CLI флаги

**Изменения:**
- Добавить аргументы `--log-dir` (default: `brain/data/logs`) и `--log-level` (default: `INFO`, choices: DEBUG/INFO/WARN/ERROR/CRITICAL)
- Создать `BrainLogger` и `TraceBuilder` в `main()` и передать в `run_query()` / `run_autonomous()`
- При завершении вызывать `BrainLogger.flush()` + `BrainLogger.close()`

```python
# brain/cli.py — новые аргументы
parser.add_argument("--log-dir", default="brain/data/logs",
                    help="Директория JSONL-логов BrainLogger")
parser.add_argument("--log-level", default="INFO",
                    choices=["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
                    help="Минимальный уровень BrainLogger")

# brain/cli.py — создание в main()
from brain.logging import BrainLogger, DigestGenerator, CycleInfo
from brain.logging.reasoning_tracer import TraceBuilder

blog = BrainLogger(log_dir=args.log_dir, min_level=args.log_level)
digest_gen = DigestGenerator(digest_dir=f"{args.log_dir}/digests")
trace_builder = TraceBuilder()  # ← создаётся здесь, передаётся вниз

# Передача в run_query / run_autonomous
run_query(args.query, args.data_dir, llm_provider=llm,
          brain_logger=blog, digest_gen=digest_gen,
          trace_builder=trace_builder)
```

**Логируемые события:**
- `"cognitive_cycle_start"` — начало цикла (query, session_id)
- `"cognitive_cycle_complete"` — завершение (action, confidence, duration_ms)
- `"autonomous_tick"` — каждый тик автономного режима
- `"memory_consolidated"` — после консолидации

---

### Фаза 2: Когнитивное ядро (основной поток событий)

#### 2.1 `brain/cognition/cognitive_core.py` — Передача BrainLogger + DigestGenerator

**Изменения:**
- Добавить `brain_logger: Optional[BrainLogger] = None` в `__init__`
- Добавить `digest_gen: Optional[DigestGenerator] = None` в `__init__`
- Добавить `trace_builder: Optional[TraceBuilder] = None` в `__init__`
- Передать `brain_logger` и `trace_builder` в `CognitivePipeline`
- После `self._pipeline.run()` — вызвать `DigestGenerator` (Проблема 6 ✅ — SRP: дайджест в CognitiveCore, не в CLI)
- Добавить фабричный метод `CycleInfo.from_result()` в `digest_generator.py`

```python
class CognitiveCore:
    def __init__(self, ..., brain_logger: Optional[BrainLogger] = None,
                 digest_gen: Optional[DigestGenerator] = None,
                 trace_builder: Optional[TraceBuilder] = None):
        self._blog = brain_logger or _NULL_LOGGER
        self._digest_gen = digest_gen
        ...
        self._pipeline = CognitivePipeline(
            ..., brain_logger=brain_logger, trace_builder=trace_builder)

    def run(self, query, ...):
        self._cycle_count += 1
        cc_id = f"cycle_{self._cycle_count}"
        self._blog.info("cognitive_core", "cognitive_cycle_start",
                       cycle_id=cc_id,
                       state={"query": query[:200]})
        result = self._pipeline.run(...)
        self._blog.info("cognitive_core", "cognitive_cycle_complete",
                       trace_id=result.trace_id,
                       session_id=result.session_id,
                       cycle_id=result.cycle_id,
                       decision={"action": result.action,
                                 "confidence": result.confidence},
                       latency_ms=result.metadata.get("total_duration_ms", 0))
        # Дайджест (SRP: здесь, не в CLI)
        if self._digest_gen:
            self._digest_gen.generate_cycle_digest(
                CycleInfo.from_result(result, query))
        return result
```

#### 2.2 `brain/logging/digest_generator.py` — Фабричный метод CycleInfo.from_result()

**Изменения:**
- Добавить `@classmethod from_result(cls, result: CognitiveResult, query: str) -> CycleInfo`
- Маппинг полей CognitiveResult → CycleInfo (убирает ручную сборку 15 полей)

```python
@classmethod
def from_result(cls, result: "CognitiveResult", query: str = "") -> "CycleInfo":
    """Фабричный метод: CognitiveResult → CycleInfo."""
    meta = result.metadata or {}
    return cls(
        cycle_id=result.cycle_id,
        session_id=result.session_id,
        trace_id=result.trace_id,
        goal=result.goal or "",
        input_text=query,
        confidence=result.confidence,
        action=result.action,
        response_preview=(result.response or "")[:120],
        duration_ms=meta.get("total_duration_ms", 0),
        memory_used=[r.ref_id for r in (result.memory_refs or [])[:5]],
        reasoning_type=meta.get("reasoning_type", ""),
        hypotheses_count=meta.get("hypothesis_count", 0),
    )
```

---

### Фаза 2.5: TraceBuilder интеграция (Проблема 4 ✅)

#### 2.5.1 `brain/cognition/pipeline.py` — TraceBuilder в когнитивном цикле

**Изменения:**
- Принять `trace_builder: Optional[TraceBuilder] = None` в `__init__`
- В `run()`:
  - `start_trace(trace_id)` после step_create_context
  - `add_step()` после ключевых шагов (goal_created, reasoning_completed, action_selected)
  - `finish_trace(trace_id)` в конце

```python
# В run(), после step_create_context:
if self._trace_builder and ctx.cognitive_context:
    self._trace_builder.start_trace(
        ctx.cognitive_context.trace_id,
        session_id=ctx.cognitive_context.session_id,
        cycle_id=ctx.cognitive_context.cycle_id)

# После step_create_goal:
if self._trace_builder and ctx.cognitive_context and ctx.goal:
    self._trace_builder.add_step(
        ctx.cognitive_context.trace_id,
        module="goal_manager", action="goal_created",
        confidence=1.0, details={"goal_type": ctx.goal.goal_type})

# В конце run():
if self._trace_builder and ctx.cognitive_context:
    self._trace_builder.finish_trace(ctx.cognitive_context.trace_id)
```

---

### Фаза 3: Pipeline — автоматический per-step timing (Проблема 2 ✅)

#### 3.1 `brain/cognition/pipeline.py` — Логирование 15 шагов

**Изменения:**
- Добавить `brain_logger: Optional[BrainLogger] = None` в `__init__`
- В `run()`: автоматический timing wrapper для всех шагов (не в каждом step-методе)
- В step-методах: только семантически значимые события

**Автоматический timing в run() (не в каждом step):**
```python
def run(self, ...):
    ctx = CognitivePipelineContext(...)
    steps = [self.step_create_context, ...]

    for step in steps:
        if ctx.aborted:
            break
        t0 = time.perf_counter()
        try:
            step(ctx)
        except Exception as e:
            ...
        step_ms = (time.perf_counter() - t0) * 1000
        # Автоматический timing для каждого шага (DEBUG)
        if ctx.cognitive_context:
            cc = ctx.cognitive_context
            self._blog.debug("pipeline", f"step_{step.__name__}_done",
                            session_id=cc.session_id, cycle_id=cc.cycle_id,
                            trace_id=cc.trace_id, latency_ms=step_ms)
    ...
```

**Семантические события в step-методах (без timing):**

| Шаг | Event | Данные |
|-----|-------|--------|
| step_create_context | `goal_context_created` | session_id, cycle_id, trace_id |
| step_create_goal | `goal_created` | goal_type, description |
| step_evaluate_salience | `reasoning_salience_evaluated` | overall, action, reason |
| step_compute_budget | `reasoning_budget_computed` | policy, cognition, memory |
| step_reason | `reasoning_completed` | confidence, iterations, outcome, evidence_refs |
| step_llm_enhance | `action_llm_enhanced` | provider, tokens, success |
| step_select_action | `action_selected` | action, confidence, policy_override |
| step_execute_action | `action_executed` | action, stored_fact (if LEARN) |
| step_build_result | `reasoning_result_built` | total_duration_ms |

```python
# Пример: step_reason (без timing — timing в run())
def step_reason(self, ctx):
    ...
    ctx.trace = self._reasoner.reason(...)
    if ctx.cognitive_context:
        cc = ctx.cognitive_context
        self._blog.info("reasoner", "reasoning_completed",
                       session_id=cc.session_id, cycle_id=cc.cycle_id,
                       trace_id=cc.trace_id,
                       state={"outcome": ctx.trace.outcome,
                              "iterations": ctx.trace.total_iterations,
                              "evidence_count": len(ctx.trace.evidence_refs)},
                       decision={"confidence": ctx.trace.final_confidence,
                                 "best_statement": (ctx.trace.best_statement or "")[:120]})
```

> **TODO:** Рассмотреть PipelineConfig dataclass для группировки параметров конструктора (Проблема 3 — 12-й параметр допустим, но оставить TODO).

---

### Фаза 4: Система памяти

#### 4.1 `brain/memory/memory_manager.py` — Логирование store/retrieve

**Изменения:**
- Добавить `brain_logger: Optional[BrainLogger] = None` в `__init__`
- `on_event` callback сохраняется для backward compatibility
- Логировать: `memory_store`, `memory_retrieve`, `fact_stored`, `episode_stored`, `consolidation_complete`

```python
class MemoryManager:
    def __init__(self, ..., brain_logger: Optional[BrainLogger] = None):
        self._blog = brain_logger or _NULL_LOGGER
        ...

    def store(self, content, ...):
        ...
        self._blog.info("memory_manager", "memory_store",
                       state={"content_preview": str(content)[:100],
                              "importance": importance,
                              "modality": modality},
                       notes=f"stored to: {list(result.keys())}")
        return result

    def retrieve(self, query, ...):
        ...
        self._blog.debug("memory_manager", "memory_retrieve",
                        state={"query": query[:100],
                               "results": {"working": len(result.working),
                                           "semantic": len(result.semantic),
                                           "episodic": len(result.episodic)}})
        return result
```

---

### Фаза 5: Perception Layer

#### 5.1 `brain/perception/input_router.py` — Логирование маршрутизации

**Изменения:**
- Добавить `brain_logger: Optional[BrainLogger] = None` в `__init__`
- Логировать: `percept_routed`, `percept_rejected`, `percept_duplicate`, `text_ingested`

```python
class InputRouter:
    def __init__(self, ..., brain_logger: Optional[BrainLogger] = None):
        self._blog = brain_logger or _NULL_LOGGER

    def route_text(self, text, ...):
        ...
        self._blog.info("input_router", "text_ingested",
                       session_id=session_id, trace_id=trace_id,
                       state={"source": source,
                              "events_count": len(events),
                              "text_preview": text[:80]})
```

---

### Фаза 6: Output Layer

#### 6.1 `brain/output/dialogue_responder.py` — Логирование формирования ответа

**Изменения:**
- Добавить `brain_logger: Optional[BrainLogger] = None` в `OutputPipeline.__init__`
- Логировать: `action_response_generated`, `action_validation_complete`

```python
class OutputPipeline:
    def __init__(self, ..., brain_logger: Optional[BrainLogger] = None):
        self._blog = brain_logger or _NULL_LOGGER

    def process(self, result):
        ...
        self._blog.info("output_pipeline", "action_response_generated",
                       trace_id=result.trace_id,
                       session_id=result.session_id,
                       cycle_id=result.cycle_id,
                       decision={"action": result.action,
                                 "confidence": result.confidence},
                       state={"issues": validation.issue_count,
                              "corrections": validation.applied_corrections},
                       latency_ms=elapsed)
        return output
```

---

### Фаза 7: Core Infrastructure

#### 7.1 `brain/core/event_bus.py` — Логирование событий шины

**Изменения:**
- Добавить `brain_logger: Optional[BrainLogger] = None` в `EventBus.__init__`
- Логировать:
  - `event_published` — каждый publish() на DEBUG (→ только `brain.jsonl`, без категорийного роутинга; prefix `percept_` некорректен — EventBus сквозной, не perception-специфичный)
  - `audit_event_bus_error` — ошибки handlers на ERROR (→ `safety_audit.jsonl`)
  - **НЕ** логировать dispatch каждого handler'а (слишком шумно)

#### 7.2 `brain/core/scheduler.py` — Логирование тиков

**Изменения:**
- Добавить `brain_logger: Optional[BrainLogger] = None` в `Scheduler.__init__`
- Логировать: `action_task_executed`, `action_task_failed`, `action_tick_complete`

---

### Фаза 8: DigestGenerator интеграция (в CognitiveCore, не в CLI — Проблема 6 ✅)

Реализуется в Фазе 2.1 — `CognitiveCore.run()` вызывает `DigestGenerator` после каждого цикла.
CLI только создаёт `DigestGenerator` и передаёт в `CognitiveCore`.

---

### Фаза 9: Тесты

#### 9.1 `tests/test_brain_logger_integration.py` — 19 тестов

Подробности в разделе «Стратегия тестирования» ниже.

---

## 📁 Сводка изменяемых файлов

| # | Файл | Тип изменения | Сложность |
|---|------|---------------|-----------|
| 0 | `brain/logging/brain_logger.py` | Добавить NullBrainLogger + _NULL_LOGGER | Малая |
| 0b | `brain/logging/reasoning_tracer.py` | Добавить NullTraceBuilder + _NULL_TRACE_BUILDER | Малая |
| 0c | `brain/logging/__init__.py` | Экспортировать NullBrainLogger, NullTraceBuilder | Малая |
| 1 | `brain/cli.py` | Создание BrainLogger + DigestGenerator, CLI флаги, передача вниз | Средняя |
| 2 | `brain/cognition/cognitive_core.py` | Принять + передать brain_logger + digest_gen | Средняя |
| 2b | `brain/logging/digest_generator.py` | Добавить CycleInfo.from_result() | Малая |
| 3 | `brain/cognition/pipeline.py` | Логирование 15 шагов + auto-timing + TraceBuilder | Высокая |
| 4 | `brain/memory/memory_manager.py` | Логирование store/retrieve/consolidate | Средняя |
| 5 | `brain/perception/input_router.py` | Логирование route/reject/dedup | Малая |
| 6 | `brain/output/dialogue_responder.py` | Логирование OutputPipeline.process() | Малая |
| 7 | `brain/core/event_bus.py` | Логирование ошибок handlers + publish DEBUG | Малая |
| 8 | `brain/core/scheduler.py` | Логирование тиков и задач | Малая |
| 9 | `tests/test_brain_logger_integration.py` | 19 новых тестов | Средняя |

---

## 🧪 Стратегия тестирования

### Принцип: существующие тесты НЕ ломаются
- Все новые параметры `brain_logger=` имеют default `None` → `_NULL_LOGGER`
- При `_NULL_LOGGER` — никакого логирования, поведение идентично текущему
- Существующие 1774 теста проходят без изменений

### Новые тесты (файл: `tests/test_brain_logger_integration.py`) — 19 тестов

#### A. Основные интеграционные тесты (12)

| # | Тест | Описание |
|---|------|----------|
| 1 | `test_pipeline_logs_all_steps` | Pipeline с BrainLogger → события в brain.jsonl для каждого шага |
| 2 | `test_pipeline_without_logger` | Pipeline без BrainLogger → работает как раньше (NullBrainLogger) |
| 3 | `test_cognitive_core_logs_cycle` | CognitiveCore.run() → cognitive_cycle_start + complete |
| 4 | `test_memory_manager_logs_store` | MemoryManager.store() → memory_store event |
| 5 | `test_memory_manager_logs_retrieve` | MemoryManager.retrieve() → memory_retrieve event |
| 6 | `test_output_pipeline_logs` | OutputPipeline.process() → action_response_generated |
| 7 | `test_input_router_logs` | InputRouter.route_text() → text_ingested event |
| 8 | `test_category_files_populated` | Проверка cognitive.jsonl, memory.jsonl, perception.jsonl |
| 9 | `test_trace_id_propagation` | Один trace_id проходит через все слои |
| 10 | `test_digest_generated_after_cycle` | DigestGenerator создаёт файл дня через CognitiveCore |
| 11 | `test_cli_log_dir_flag` | `--log-dir /tmp/test` создаёт BrainLogger с правильной директорией |
| 12 | `test_cli_log_level_flag` | `--log-level WARN` фильтрует DEBUG/INFO |

#### B. Тесты на корректность данных (3)

| # | Тест | Описание |
|---|------|----------|
| 13 | `test_log_entry_schema_valid` | Каждая запись содержит обязательные поля (ts, level, module, event) |
| 14 | `test_latency_ms_positive` | Все записи с latency_ms имеют значение > 0 |
| 15 | `test_session_id_consistency` | Все записи одного цикла имеют одинаковый session_id |

#### C. Тесты на устойчивость (2)

| # | Тест | Описание |
|---|------|----------|
| 16 | `test_logger_handles_unicode` | BrainLogger корректно логирует Unicode (кириллица, эмодзи) |
| 17 | `test_logger_survives_write_error` | BrainLogger не крашит pipeline при ошибке записи (graceful degradation) |

#### D. Тесты TraceBuilder интеграции (2)

| # | Тест | Описание |
|---|------|----------|
| 18 | `test_trace_builder_reconstructs_from_logger` | TraceBuilder.reconstruct_from_logger() возвращает полную цепочку |
| 19 | `test_trace_chain_matches_pipeline_steps` | Количество шагов в TraceChain соответствует выполненным шагам |

### Запуск тестов:
```bash
# Все существующие тесты (регрессия)
pytest tests/ -x -q

# Только новые тесты интеграции логирования
pytest tests/test_brain_logger_integration.py -v

# Полный прогон с coverage
pytest tests/ --cov=brain --cov-report=term-missing
```

---

## 🔒 Гарантии обратной совместимости

1. **NullBrainLogger** — все модули работают без BrainLogger (default `_NULL_LOGGER`)
2. **Stdlib `logging` остаётся** — BrainLogger дополняет, не заменяет
3. **MemoryManager.on_event callback сохраняется** — для backward compatibility
4. **Тесты не требуют BrainLogger** — создают модули без него
5. **cycle_id не дублируется** — используется `ctx.cognitive_context.cycle_id` из Pipeline

---

## 🚀 Порядок реализации (пошаговый)

```
Шаг 0:  brain/logging/brain_logger.py     — NullBrainLogger + _NULL_LOGGER
Шаг 0b: brain/logging/reasoning_tracer.py — NullTraceBuilder + _NULL_TRACE_BUILDER
Шаг 0c: brain/logging/__init__.py         — экспорт NullBrainLogger, NullTraceBuilder
Шаг 1:  brain/cli.py                      — CLI флаги + создание BrainLogger + TraceBuilder
Шаг 2:  brain/cognition/cognitive_core.py  — принять + передать brain_logger + digest_gen + trace_builder
Шаг 2b: brain/logging/digest_generator.py — CycleInfo.from_result()
Шаг 3:  brain/cognition/pipeline.py       — auto-timing + 9 семантических событий + TraceBuilder
Шаг 4:  brain/memory/memory_manager.py    — логирование store/retrieve
Шаг 5:  brain/perception/input_router.py  — логирование маршрутизации
Шаг 6:  brain/output/dialogue_responder.py — логирование OutputPipeline
Шаг 7:  brain/core/event_bus.py           — логирование publish + ошибок
Шаг 8:  brain/core/scheduler.py           — логирование тиков
Шаг 9:  tests/test_brain_logger_integration.py — 19 новых тестов
Шаг 10: pytest tests/ -x                  — полный регрессионный прогон
```

---

## ⏱️ Оценка трудозатрат

| Фаза | Файлы | Оценка (строки) |
|-------|-------|-----------------|
| Фаза 0: NullBrainLogger + NullTraceBuilder | 3 файла | ~35 строк |
| Фаза 1: CLI | 1 файл | ~35 строк |
| Фаза 2: Когниция + Digest | 2 файла | ~50 строк |
| Фаза 2.5: TraceBuilder | 1 файл (pipeline) | ~25 строк |
| Фаза 3: Pipeline timing + events | 1 файл | ~60 строк |
| Фаза 4: Память | 1 файл | ~30 строк |
| Фаза 5: Perception | 1 файл | ~15 строк |
| Фаза 6: Output | 1 файл | ~15 строк |
| Фаза 7: Core | 2 файла | ~20 строк |
| Фаза 9: Тесты | 1 новый файл | ~250 строк |
| **Итого** | **12 файлов (11 изменённых + 1 новый)** | **~525 строк** |

---

## 🟢 Мелкие замечания (учтены)

| # | Замечание | Решение |
|---|----------|---------|
| 1 | `--log-level` без CRITICAL | Добавлен CRITICAL в choices |
| 2 | `brain/data/logs` — default внутри пакета | Допустимо для dev; для production — `~/.cognitive-core/logs` (будущее) |
| 3 | `cycle_id` дублирование | Используется `ctx.cognitive_context.cycle_id` — не дублируем |
| 4 | Ротация/cleanup дайджестов | BrainLogger имеет `max_size_mb`; для дайджестов — TODO на будущее |
| 5 | `memory_refs[:5]` — магическое число | Вынесено в константу `_MAX_MEMORY_REFS_IN_DIGEST = 5` |
