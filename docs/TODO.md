# 🧠 TODO — Dependency-First Roadmap
## Искусственный мультимодальный мозг (по BRAIN.md)

> Статусы: `[ ]` — не начато | `[~]` — в процессе | `[x]` — завершено  
> Формат: dependency-first (сначала контракты и сквозной text-only цикл, затем усложнение).  
> Принцип: **как можно раньше получить живой e2e цикл мышления**, а не “почти готовую инфраструктуру”.

---

## 🎯 Цель первой итерации (обязательный MVP)

Система должна уметь:

1. Принять **текстовый** вопрос  
2. Извлечь релевантное из памяти  
3. Построить 1–3 гипотезы  
4. Выбрать форму ответа  
5. Выдать `text + confidence + trace + log`

**MVP definition of done:**
- один стабильный text-only pipeline работает end-to-end;
- каждый ответ имеет trace chain и запись в JSONL;
- latency и confidence измеряются и видны в логах.

---

## ✅ Что уже реализовано (не переписывать, использовать как базу)

- [x] `brain/core/events.py` — типизированные события + EventFactory  
- [x] `brain/core/contracts.py` — ContractMixin, ResourceState, Task, EncodedPercept, FusedPercept, TraceChain, CognitiveResult, BrainOutput  
- [x] `brain/core/event_bus.py` — EventBus (pub/sub, wildcard, error isolation)  
- [x] `brain/core/scheduler.py` — Scheduler (heapq, 4 приоритета, адаптивный tick 100/500/2000/5000ms)  
- [x] `brain/core/resource_monitor.py` — ResourceMonitor (4 политики, hysteresis, inject_state)  
- [x] `brain/memory/*` — Working/Semantic/Episodic/Source/Procedural/Consolidation/MemoryManager  
- [x] `brain/logging/*` — BrainLogger, DigestGenerator, TraceBuilder  
- [x] `brain/perception/*` — MetadataExtractor, TextIngestor, InputRouter (text-only MVP)  
- [x] `test_memory.py` — 101/101 тестов  
- [x] `test_scheduler.py` — 11/11 тестов  
- [x] `test_resource_monitor.py` — 13/13 тестов  
- [x] `test_logging.py` — 25/25 тестов  
- [x] `test_perception.py` — 79/79 тестов  
- [x] Доки слоёв `docs/layers/00..11` (включая Cognitive Core и Reward)

## ✅ Аудит и исправления (завершено)

- [x] `brain/core/resource_monitor.py` — разделены `brain_level_map`/`python_level_map`, добавлено поле `"level"` в событие EventBus
- [x] `brain/core/scheduler.py` — добавлен `tick_emergency_ms`, `ram_*_gb` поля, `get_tick_interval()` поддерживает 4 уровня
- [x] `brain/__init__.py` — версия исправлена: `"0.1.0"` → `"0.3.0"`
- [x] `test_logging.py` — UnicodeEncodeError: emoji `✅` заменён на `[OK]`
- [x] `brain/memory/consolidation_engine.py` — `@dataclass` для `ConsolidationConfig`, `print()` → `_logger.*`
- [x] `brain/memory/semantic_memory.py` — `log(access_count+1+1)` → `log(access_count+1)`, `print()` → `_logger.*`
- [x] `brain/memory/memory_manager.py` — добавлен `_logger`, `print()` → `_logger.*`
- [x] `brain/memory/episodic_memory.py` — добавлен `import logging`, `_logger`, `print()` → `_logger.*`
- [x] `brain/memory/source_memory.py` — добавлен `import logging`, `_logger`, `print()` → `_logger.*`
- [x] `brain/memory/procedural_memory.py` — добавлен `import logging`, `_logger`, `print()` → `_logger.*`
- [x] `docs/layers/09_logging_observability.md` — статусы обновлены: `⬜` → `✅`
- [x] Регрессия: 229/229 тестов ✅ (101 memory + 11 scheduler + 13 resource_monitor + 25 logging + 79 perception)

---

## ЭТАП A — Shared Contracts (общие типы и протоколы)

> Сначала фиксируем сквозные контракты, чтобы слои не “разъехались”.

- [x] **A.1** Создать `brain/core/contracts.py`:
  - dataclass/enum/protocol для:
    - `ResourceState`
    - `Task`
    - `PerceptEvent` (ссылка на core/events совместимость)
    - `EncodedPercept`
    - `FusedPercept`
    - `CognitiveResult`
    - `BrainOutput`
    - trace-структуры (`TraceRef`, `TraceStep`, `TraceChain`)
  **DoD:** все сущности импортируются из одного места, типы стабильны. ✅

- [x] **A.2** Добавить правила совместимости контрактов:
  - no breaking field rename без миграции (политика зафиксирована в docstring contracts.py),
  - единый стиль сериализации: `ContractMixin.to_dict()` / `from_dict()` на всех 9 dataclass,
  - `trace_id/session_id/cycle_id` добавлены в `TraceChain`, `CognitiveResult`, `BrainOutput`.
  **DoD:** smoke-тест сериализации (7 сценариев) пройден ✅, регрессия 101/101 ✅
  → depends on: A.1

---

## ЭТАП B — Minimal Autonomous Runtime (живой минимальный loop)

> Не “полный ствол мозга”, а минимум: принять задачу → выполнить → опубликовать результат.

- [x] **B.1** Реализовать `brain/core/event_bus.py`:
  - publish/subscribe,
  - typed handlers (wildcard `"*"` поддержан),
  - минимальная защита от падения хэндлера (error isolation).
  **DoD:** событие проходит через 2+ подписчика. ✅ (smoke-тесты пройдены)
  → depends on: A.1

- [x] **B.2** Реализовать `brain/core/scheduler.py`:
  - clock-driven tick (100/500/2000 мс по нагрузке),
  - event-triggered task enqueue (приоритетная очередь heapq),
  - выполнение одной задачи за тик (MVP режим).
  - `TaskPriority` (CRITICAL/HIGH/NORMAL/LOW/IDLE), `SchedulerConfig`, `SchedulerStats`
  - `tick_start` / `tick_end` / `task_done` / `task_failed` через EventBus
  **DoD:** 11/11 smoke-тестов пройдено ✅ (`test_scheduler.py`)
  → depends on: B.1

- [x] **B.3** Реализовать `brain/core/resource_monitor.py`:
  - CPU/RAM sampling (psutil), фоновый daemon-поток,
  - 4 политики деградации: NORMAL/DEGRADED/CRITICAL/EMERGENCY,
  - гистерезис флагов `soft_blocked` и `ring2_allowed`,
  - `inject_state()` для тестирования без реального CPU,
  - `resource_policy_changed` event через EventBus при смене политики.
  **DoD:** 13/13 smoke-тестов пройдено ✅ (`test_resource_monitor.py`)
  → depends on: B.2

---

## ЭТАП C — Logging & Observability (раньше остальных слоёв)

> Без этого дальше всё будет “чёрным ящиком”.

- [x] **C.1** Реализовать `brain/logging/brain_logger.py`:
  - JSONL logger, 5 уровней (DEBUG/INFO/WARN/ERROR/CRITICAL),
  - обязательные поля: `ts, level, module, event, trace_id, session_id, cycle_id`,
  - категорийные файлы: cognitive/memory/perception/learning/safety_audit,
  - in-memory индекс по trace_id и session_id, ротация при > 100 MB.
  **DoD:** каждый тик и ключевое действие логируются. ✅
  → depends on: B.2

- [x] **C.2** Реализовать `brain/logging/digest_generator.py`:
  - `CycleInfo` dataclass, `generate_cycle_digest()`, `generate_session_digest()`,
  - запись в `brain/data/logs/digests/YYYY-MM-DD.txt` и `session_<id>.txt`.
  **DoD:** на каждый завершённый цикл формируется digest-запись. ✅
  → depends on: C.1

- [x] **C.3** Реализовать `brain/logging/trace_builder.py`:
  - `start_trace / add_step / add_input_ref / add_memory_ref / add_output_ref / finish_trace`,
  - `reconstruct(trace_id)` → `TraceChain`, `reconstruct_from_logger(trace_id, logger)`,
  - `to_human_readable(chain)` — читаемый вывод цепочки причинности.
  **DoD:** по `trace_id` восстанавливается полный путь решения. ✅
  → depends on: C.1, A.1

---

## ЭТАП D — Text-Only Perception (первая рабочая вертикаль входа)

> Только текст: без vision/audio/video на этом этапе.

- [x] **D.1** Реализовать `brain/perception/text_ingestor.py`:
  - `.txt/.md/.pdf/.docx/.json/.csv`, paragraph-aware chunking (1000–1500 chars, overlap 120),
  - graceful fallback при отсутствии pymupdf/python-docx.
  **DoD:** любой текстовый файл превращается в `PerceptEvent`. ✅ (79/79 тестов)
  → depends on: A.1, C.1

- [x] **D.2** Реализовать `brain/perception/metadata_extractor.py`:
  - `source`, `language` (ru/en/mixed/unknown), `quality` (0.0–1.0), `timestamp`.
  - quality_label: normal/warning/low_priority; hard reject только для пустого контента.
  **DoD:** каждый `PerceptEvent` дополнен метаданными. ✅
  → depends on: D.1

- [x] **D.3** Реализовать `brain/perception/input_router.py` (MVP):
  - маршрутизация только text-входов, SHA256 дедупликация, quality policy.
  - image/audio/video → warning + пропуск (MVP).
  **DoD:** текстовый input стабильно доходит до энкодера. ✅
  → depends on: D.1, D.2

---

## ЭТАП E — Minimal Text Encoder (дешёвый и стабильный путь)

- [ ] **E.1** Реализовать `brain/encoders/text_encoder.py`:
  - базовый рабочий энкодер (sentence-transformers),
  - fallback при нехватке ресурсов.
  **DoD:** `PerceptEvent -> EncodedPercept` стабильно.
  → depends on: D.3, B.3

- [ ] **E.2** Добавить lightweight режим:
  - переключение на fallback по флагу resource monitor.
  **DoD:** при high load путь не падает, а деградирует предсказуемо.
  → depends on: E.1, B.3

---

## ЭТАП F — Cognitive MVP поверх готовой памяти

> Центральный контур: `retrieve -> hypotheses -> score -> select -> act`.

### F1 — Context + Goal Set
- [ ] **F.1** Реализовать `brain/cognition/context.py`:
  - сбор рабочего контекста из MemoryManager,
  - ограничение по объёму/важности.
  **DoD:** контекст формируется детерминированно и логируется.
  → depends on: E.1, C.1

- [ ] **F.2** Реализовать `brain/cognition/goal_manager.py` + `planner.py` (MVP):
  - цели: `answer_question`, `verify_claim`.
  **DoD:** цель ставится и декомпозируется в 1–3 шага.
  → depends on: F.1

### F2 — Hypotheses + Score
- [ ] **F.3** Реализовать `brain/cognition/hypothesis_engine.py` (template-based):
  - генерация 1–3 гипотез,
  - scoring на базе evidence/trust/coherence/contradiction.
  **DoD:** на один запрос создаётся набор гипотез с числовым score.
  → depends on: F.1, F.2

- [ ] **F.4** Реализовать `brain/cognition/reasoner.py` (Ring 1 only):
  - retrieve + ранжирование + выбор лучшей гипотезы.
  **DoD:** выдаёт `CognitiveResult` со structured reasoning trace.
  → depends on: F.3

### F3 — Uncertainty + Action
- [ ] **F.5** Реализовать `brain/cognition/uncertainty_monitor.py` + `action_selector.py`:
  - ветки: ответить / ответить с оговоркой / запросить уточнение.
  **DoD:** поведение меняется от confidence и contradiction flags.
  → depends on: F.4

---

## ЭТАП F.5 — Retrieval Integration (стык памяти и reasoning)

> Явный интеграционный этап между encoder и cognition, чтобы не прятать критичный стык внутри reasoner.

- [ ] **F.6** Реализовать `MemoryManager.retrieve() -> reasoning input` адаптер:
  - нормализация формата результатов retrieve,
  - ранжирование кандидатов для hypothesis engine,
  - contradiction-first сигнал в reasoning context.
  **DoD:** reasoner получает единый и стабильный вход из memory retrieval без ad-hoc преобразований.
  → depends on: F.2, C.3

---

## ЭТАП G — Output MVP (объяснимый ответ наружу)

- [ ] **G.1** Реализовать `brain/output/trace_builder.py`:
  - превращает внутренний trace в читаемую структуру.
  **DoD:** trace прикладывается к каждому ответу.
  → depends on: C.3, F.4

- [ ] **G.2** Реализовать `brain/output/dialogue_responder.py`:
  - формирует `BrainOutput(text, confidence, trace_ref, digest)`.
  **DoD:** пользователь получает текст + confidence + trace.
  → depends on: G.1, F.5

- [ ] **G.3** Реализовать `brain/output/response_validator.py` (минимум, MVP Safety):
  - фильтр пустых/невалидных/опасных ответов на MVP-уровне.
  **DoD:** невалидный output блокируется и логируется.
  → depends on: G.2

---

## ЭТАП H — Attention & Resource integration (после e2e)

> Подключаем только когда text-only цикл уже живой.

- [ ] **H.1** Реализовать `brain/core/attention_controller.py`:
  - приоритизация задач по goal/salience.
  **DoD:** при нагрузке система сохраняет качество critical-path.
  → depends on: G.2, B.3

- [ ] **H.2** Реализовать policy деградации:
  - отключение тяжёлых веток reasoning при high load.
  **DoD:** деградация предсказуема, без падений.
  → depends on: H.1

---

## ЭТАП I — Learning Loop (урезанный и поздний старт)

- [ ] **I.1** Реализовать `brain/learning/online_learner.py` (MVP):
  - обновление confidence по результатам ответа/фидбэка.
  **DoD:** feedback влияет на последующие ответы.
  → depends on: G.2

- [ ] **I.2** Реализовать `brain/learning/knowledge_gap_detector.py`:
  - фиксирует пробелы и создаёт обучающие подцели.
  **DoD:** при низком покрытии знаний создаётся gap-goal.
  → depends on: I.1

- [ ] **I.3** Реализовать `brain/learning/replay_engine.py`:
  - replay важных эпизодов в idle.
  **DoD:** replay запускается без деградации realtime-ответов.
  → depends on: I.1, H.2

---

## ЭТАП J — Расширение мультимодальности (позже)

- [ ] **J.1** Vision encoder path (ingest + encode)
- [ ] **J.2** Audio encoder path (ingest + encode)
- [ ] **J.3** Temporal/video path (минимум)
  **DoD:** каждая модальность проходит отдельный smoke e2e.
  → depends on: E.2, G.2

---

## ЭТАП K — Cross-Modal Fusion (почти в конце)

- [ ] **K.1** `brain/fusion/shared_space_projector.py`
- [ ] **K.2** `brain/fusion/entity_linker.py`
- [ ] **K.3** `brain/fusion/confidence_calibrator.py`
- [ ] **K.4** `brain/fusion/contradiction_detector.py`
  **DoD:** факты из разных модальностей связываются в единое представление.
  → depends on: J.1, J.2, J.3

---

## ЭТАП L — Safety & Boundaries (Expanded Safety, до Reward)

- [ ] **L.1** `brain/safety/source_trust.py`
- [ ] **L.2** `brain/safety/conflict_detector.py`
- [ ] **L.3** `brain/safety/boundary_guard.py`
- [ ] **L.4** `brain/safety/audit_logger.py`
  **DoD:** high-risk решения блокируются/аудируются.
  → depends on: G.3, K.4

---

## ЭТАП M — Reward & Motivation (последним)

- [ ] **M.1** `brain/motivation/reward_engine.py`
- [ ] **M.2** `brain/motivation/motivation_engine.py`
- [ ] **M.3** `brain/motivation/curiosity_engine.py`
  **DoD:** reward сигнал влияет на приоритет целей и learning.
  → depends on: I.3, L.3

---

## 🧪 Тестовый план по этапам

- [ ] **T.1 Contracts tests** (serialization, backward-compatibility)  
- [ ] **T.2 Runtime tests** (event bus + scheduler + resource flags)  
- [ ] **T.3 Text-only e2e tests** (input -> memory -> reason -> output -> trace/log)  
- [ ] **T.4 Regression memory tests** (`python test_memory.py`, должно остаться 101/101)  
- [ ] **T.5 Load/degradation tests** (CPU/RAM pressure сценарии)

---

## 📅 План на 1 неделю по файлам (первая реализация)

### День 1 — Contracts + skeleton runtime ✅ (почти завершён)
- [x] `brain/core/contracts.py` — реализовано
- [x] `brain/core/event_bus.py` — реализовано (полный, не skeleton)
- [x] `brain/core/scheduler.py` — реализовано (полный, 11/11 тестов)
- [x] `brain/core/resource_monitor.py` — реализовано (полный, 13/13 тестов)

### День 2 — Logging first ✅ ЗАВЕРШЕНО
- [x] `brain/logging/brain_logger.py`   — BrainLogger (25/25 тестов)
- [x] `brain/logging/digest_generator.py` — DigestGenerator + CycleInfo
- [x] `brain/logging/trace_builder.py`  — TraceBuilder + reconstruct_from_logger

### День 3 — Text ingestion MVP ✅ ЗАВЕРШЕНО
- [x] `brain/perception/text_ingestor.py`   — TextIngestor (79/79 тестов)
- [x] `brain/perception/metadata_extractor.py` — MetadataExtractor
- [x] `brain/perception/input_router.py`    — InputRouter (text-only MVP)

### День 4 — Text encoder MVP
- `brain/encoders/text_encoder.py`
- fallback logic + интеграция с resource monitor

### День 5 — Cognitive core MVP (part 1)
- `brain/cognition/context.py`
- `brain/cognition/goal_manager.py`
- `brain/cognition/planner.py`
- `brain/cognition/hypothesis_engine.py`

### День 6 — Cognitive core MVP (part 2)
- `brain/cognition/reasoner.py`
- `brain/cognition/uncertainty_monitor.py`
- `brain/cognition/action_selector.py`
- Retrieval integration (`F.6`) и фиксация формата reasoning input

### День 7 — Output MVP + validation
- `brain/output/trace_builder.py`
- `brain/output/dialogue_responder.py`
- `brain/output/response_validator.py` (MVP safety)

### День 8–9 — E2E stabilization + tests
- e2e test scripts for text-only loop
- `python test_memory.py` regression
- фиксы по trace/log/digest
- минимальная документация новых модулей

**Итог первой итерации (реалистичный горизонт 8–9 дней):**
- живой text-only e2e цикл,
- ответы с trace и confidence,
- стабильный runtime без падений на базовой нагрузке.

---

## 📌 Порядок реализации (коротко)

```text
A Contracts
→ B Runtime
→ C Logging
→ D Text Perception
→ E Text Encoder
→ F Cognitive MVP
→ G Output MVP
→ H Attention/Degradation
→ I Learning (light)
→ J Multimodal encoders
→ K Cross-modal fusion
→ L Safety
→ M Reward/Motivation
```

---

## 📊 Прогресс (новый формат)

| Этап | Название | Статус | Риск/Сложность |
|------|----------|--------|----------------|
| A | Shared Contracts | [x] A.1 ✅, A.2 ✅ | Средний |
| B | Minimal Runtime | [x] B.1 ✅, B.2 ✅, B.3 ✅ | Средний |
| C | Logging & Observability (early) | [x] C.1 ✅, C.2 ✅, C.3 ✅ | Низкий |
| D | Text-Only Perception | [x] D.1 ✅, D.2 ✅, D.3 ✅ | Средний |
| E | Minimal Text Encoder | [ ] | Средний |
| F | Cognitive MVP | [ ] | Высокий |
| G | Output MVP | [ ] | Средний |
| H | Attention & Degradation | [ ] | Средний |
| I | Learning (light) | [ ] | Средний |
| J | Multimodal Expansion | [ ] | Высокий |
| K | Cross-Modal Fusion | [ ] | Высокий |
| L | Safety & Boundaries (Expanded) | [ ] | Средний |
| M | Reward & Motivation | [ ] | Высокий |
