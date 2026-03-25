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

## 🔧 Аудит v2 — Проблемы для исправления перед Этапом H

> Выявлено аудитом (AUDIT_REPORT.md + внешний ревью). Исправить ДО начала Этапа H.
> Приоритеты: P0 — блокирует / P1 — важно после стабилизации / P2 — улучшения / P3 — backlog

### P0 — Критические ✅ (ВСЕ ВЫПОЛНЕНЫ — 660/660 тестов)

- [x] **P0.1** Синхронизировать версии во всех файлах:
  - `brain/__init__.py`: `"0.3.0"` → `"0.6.1"` ✅
  - `pyproject.toml`: `"0.6.0"` → `"0.6.1"` ✅
  - `README.md`: тесты `611` → `660`, версия → `0.6.1` ✅

- [x] **P0.2** Очистить артефакты `NaN` в README.md ✅:
  - Убраны `NaN retry-only MVP)` и починены обрезанные блоки кода
  - Добавлена строка `test_vector_retrieval.py` в таблицу тестов

- [x] **P0.3** Проверить/очистить артефакт `NaN` в `brain/core/events.py` ✅:
  - Файл уже чист (NaN был в README, не в events.py)

- [x] **P0.4** Зафиксировать API-контракты между слоями ✅:
  - Добавлены `MemoryManagerProtocol`, `EventBusProtocol`, `ResourceMonitorProtocol` в `contracts.py`
  - Экспортированы из `brain/core/__init__.py`
  - `CognitiveCore` конструктор типизирован Protocol'ами

- [x] **P0.5** Убрать скрытые side effects в retrieval ✅:
  - `retrieval_adapter.py`: `dataclasses.replace()` в `_ensure_canonical()`, `_enrich()`, `_rrf_merge()`
  - `retrieve()` loop captures return values

- [x] **P0.6** Добавить E2E тест полного pipeline + сделать lint блокирующим ✅:
  - `tests/test_e2e_pipeline.py`: 10 E2E тестов (Protocol conformance + full pipeline)
  - `.github/workflows/ci.yml`: убран `continue-on-error: true` для ruff

### P1 — Важно после стабилизации базы

- [x] **P1.0** Ruff lint cleanup — 131 → 0 errors ✅:
  - 103 auto-fixed by `ruff --fix` (F401 unused imports, F541 f-strings)
  - 9× E702 semicolons split manually (`test_memory.py`)
  - 4× E741 ambiguous variable `l` → `line` (`test_scheduler.py`, `test_resource_monitor.py`)
  - 14× `# noqa: E402` for intentional late imports after try/except blocks
  - 2× `# noqa: F401` for side-effect imports (`numpy`, `psutil` in `semantic_memory.py`)
  - CI ruff lint step is now **blocking** (no `continue-on-error`)

- [x] **P1.1** Усилить keyword retrieval: BM25 reranking ✅:
  - `BM25Scorer` класс в `retrieval_adapter.py`: TF-IDF с BM25 формулой (k1=1.5, b=0.75)
  - `KeywordRetrievalBackend._bm25_rerank()`: reranking кандидатов после keyword overlap
  - Опциональная лемматизация через pymorphy3 (graceful fallback без зависимости)
  - 55 тестов в `tests/test_bm25.py` (unit + integration)
  - **Scope:** reranking only, НЕ замена VectorRetrievalBackend

- [ ] **P1.2** Заменить brute-force vector search на ANN:
  - Вынести vector retrieval на FAISS или hnswlib
  - **Зачем:** текущий O(n*d) подходит для MVP, но станет узким местом при росте памяти

- [x] **P1.3** SQLite persistence layer (P1c-a) ✅:
  - `brain/memory/storage.py`: MemoryDatabase (WAL, RLock, schema versioning, full CRUD)
  - `brain/memory/migrate.py`: JSON→SQLite миграция (backup, idempotent, marker)
  - Все memory модули: `storage_backend="auto"|"sqlite"|"json"`, `db` параметр
  - `MemoryManager`: создаёт MemoryDatabase, транзакционный `save_all()`
  - 58 тестов в `tests/test_storage.py` (CRUD, transactions, threads, migration, integration)
  - **Scope:** persistence parity only. FTS5/indexed search → P1c-b

- [x] **P1.4** Передавать `session_id` в `CognitiveCore.run()` ✅:
  - Добавлен `session_id: Optional[str] = None` в `run()` и `_create_context()`
  - Если None — генерируется автоматически (обратная совместимость)

- [x] **P1.5** CI: добавить `pytest-cov` для измерения покрытия ✅:
  - `pytest-cov>=5.0` в dev deps, `--cov=brain --cov-report=term-missing --cov-report=xml` в CI

- [x] **P1.6** Синхронизировать зависимости ✅:
  - `tqdm>=4.66.0` добавлен в core deps pyproject.toml
  - `ruff>=0.4.0`, `mypy>=1.10` добавлены в dev deps
  - `requirements.txt` помечен DEPRECATED, синхронизирован с pyproject.toml

- [x] **P1.7** `docs/ARCHITECTURE.md` — пометить как концептуальный ✅:
  - Добавлен disclaimer ⚠️ КОНЦЕПТУАЛЬНЫЙ ДОКУМЕНТ вверху файла

- [x] **P1.8** BrainLogger: добавить `atexit` handler ✅:
  - `atexit.register()` через `weakref.ref` (не удерживает объект в памяти)

- [x] **P1.9** CI: добавить mypy/pyright для type checking ✅:
  - Новый job `typecheck` в CI с `mypy --ignore-missing-imports`
  - Секция `[tool.mypy]` в pyproject.toml
  - Non-blocking (`|| true`) на первом этапе

### P2 — Улучшения качества и масштабируемости

- [ ] **P2.1** Добавить TTL/LRU для in-memory индексов BrainLogger:
  - Ограничить и очищать in-memory индексы (trace_index, session_index)
  - **Зачем:** защита от бесконтрольного роста памяти на длинных сессиях

- [ ] **P2.2** Ослабить связность EvidencePack:
  - Разделить на core + metadata или чётко развести неизменяемые и обогащаемые поля
  - **Зачем:** объект слишком удобен для "сложить всё", ведёт к скрытой связанности

- [ ] **P2.3** Вынести стратегии HypothesisEngine в Strategy pattern:
  - Более явная модель для генерации гипотез
  - **Зачем:** при росте числа стратегий логика распухнет в большой switch-case

- [ ] **P2.4** Добавить property-based и benchmark тесты:
  - Property-based через `hypothesis` library
  - Benchmark/perf regression tests для retrieval и cognition
  - **Зачем:** лучше ловить edge cases и регрессии по скорости

- [ ] **P2.5** Убрать Python 3.14 из classifiers в pyproject.toml (не тестируется в CI)
- [ ] **P2.6** Добавить CHANGELOG.md
- [ ] **P2.7** Добавить CONTRIBUTING.md
- [ ] **P2.8** Добавить `.gitkeep` в `brain/data/memory/`
- [ ] **P2.9** CI: добавить pip cache для ускорения билдов

### P3 — Research / Backlog

- [ ] **P3.1** Сделать contradiction detection умнее:
  - Уйти от negation-based логики к NLI-модели или более сильному синтаксическому анализу
  - **Зачем:** простые маркеры отрицания быстро ошибаются на реальном тексте

- [ ] **P3.2** Подумать о переходе на OpenTelemetry:
  - Оценить замену части кастомного трейсинга на OpenTelemetry или гибридную схему
  - **Зачем:** стандартная observability-модель при росте в сторону сервиса

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

## ЭТАП E — Minimal Text Encoder (дешёвый и стабильный путь) ✅

- [x] **E.1** Реализовать `brain/encoders/text_encoder.py`:
  - базовый рабочий энкодер (sentence-transformers),
  - fallback при нехватке ресурсов (navec 300d).
  - primary mode (768d), fallback mode (300d), degraded mode, failed mode.
  - language detection (ru/en/mixed/unknown), message_type detection, keyword extraction.
  - L2 normalization, caching, batch encoding.
  **DoD:** `PerceptEvent -> EncodedPercept` стабильно. ✅ (80/80 тестов)
  → depends on: D.3, B.3

- [x] **E.2** Добавить lightweight режим:
  - переключение на fallback по флагу resource monitor.
  - 4 режима: primary → fallback → degraded → failed.
  - graceful degradation при отсутствии моделей.
  **DoD:** при high load путь не падает, а деградирует предсказуемо. ✅
  → depends on: E.1, B.3

---

## ЭТАП F — Cognitive MVP поверх готовой памяти ✅

> Центральный контур: `retrieve -> hypotheses -> score -> select -> act`.

### F1 — Context + Goal Set ✅
- [x] **F.1** Реализовать `brain/cognition/context.py`:
  - CognitiveContext, CognitiveOutcome (7 значений), EvidencePack, ReasoningState,
  - PolicyConstraints, GoalTypeLimits, GOAL_TYPE_LIMITS (4 типа),
  - NORMAL_OUTCOMES / FAILURE_OUTCOMES helper-наборы.
  - Все dataclass через ContractMixin (to_dict/from_dict).
  **DoD:** контекст формируется детерминированно и логируется. ✅
  → depends on: E.1, C.1

- [x] **F.2** Реализовать `brain/cognition/goal_manager.py` + `planner.py` (MVP):
  - GoalStatus enum (PENDING/ACTIVE/DONE/FAILED/INTERRUPTED/CANCELLED),
  - Goal dataclass (12 полей), GoalManager (priority queue + interrupted stack),
  - PlanStep, ExecutionPlan, Planner (4 шаблона: answer_question, learn_fact, verify_claim, explore_topic),
  - check_stop_conditions(), replan() (retry only MVP).
  **DoD:** цель ставится и декомпозируется в 1–3 шага. ✅
  → depends on: F.1

### F2 — Hypotheses + Score ✅
- [x] **F.3** Реализовать `brain/cognition/hypothesis_engine.py` (template-based):
  - Hypothesis dataclass (support_score, risk_score, final_score),
  - HypothesisEngine: 2 стратегии (associative + deductive), max 3 гипотезы,
  - score(), score_all(), rank() (stable sort, deterministic order).
  **DoD:** на один запрос создаётся набор гипотез с числовым score. ✅
  → depends on: F.1, F.2

- [x] **F.4** Реализовать `brain/cognition/reasoner.py` (Ring 1 only):
  - ReasoningStep, ReasoningTrace (best_hypothesis_id, outcome, stop_reason),
  - Reasoner: полный loop retrieve→hypothesize→score→select→check_stop.
  **DoD:** выдаёт `CognitiveResult` со structured reasoning trace. ✅
  → depends on: F.3

### F3 — Uncertainty + Action ✅
- [x] **F.5** Реализовать `brain/cognition/action_selector.py`:
  - ActionType enum (RESPOND_DIRECT, RESPOND_HEDGED, ASK_CLARIFICATION, REFUSE, LEARN),
  - ActionDecision dataclass, ActionSelector (6 стратегий выбора).
  - Ветки: ответить / ответить с оговоркой / запросить уточнение / отказать / запомнить.
  **DoD:** поведение меняется от confidence и contradiction flags. ✅
  → depends on: F.4

### F4 — Orchestrator ✅
- [x] **F.6** Реализовать `brain/cognition/cognitive_core.py`:
  - CognitiveCore.run() — единая точка входа (10-шаговая цепочка),
  - _build_retrieval_query(), _create_goal(), _build_cognitive_result(),
  - Публикация событий через EventBus.
  **DoD:** CognitiveCore.run(query) → CognitiveResult с trace. ✅
  → depends on: F.5

### Тесты Stage F ✅
- [x] 182 unit тестов в `tests/test_cognition.py` (182/182 passed)
- [x] 7 integration smoke тестов в `tests/test_cognition_integration.py` (7/7 passed)
- [x] `brain/cognition/__init__.py` — 22 публичных экспорта

---

## ЭТАП G — Output MVP (объяснимый ответ наружу) ✅

- [x] **G.1** Реализовать `brain/output/trace_builder.py`:
  - ExplainabilityTrace dataclass (ContractMixin), OutputTraceBuilder,
  - uncertainty levels: very_low/low/medium/high/very_high,
  - build(), to_digest(), to_json().
  **DoD:** trace прикладывается к каждому ответу. ✅
  → depends on: C.3, F.4

- [x] **G.2** Реализовать `brain/output/dialogue_responder.py`:
  - DialogueResponder (generate → BrainOutput), hedging phrases (5 confidence bands),
  - fallback templates per ActionType (RU/EN),
  - OutputPipeline (trace_builder → validator → responder).
  **DoD:** пользователь получает текст + confidence + trace. ✅
  → depends on: G.1, F.5

- [x] **G.3** Реализовать `brain/output/response_validator.py` (минимум, MVP Safety):
  - ValidationIssue, ValidationResult, ResponseValidator (max_length=2000),
  - 4 проверки: empty→CRITICAL+fallback, low_confidence_no_hedge→WARNING+hedge,
    too_long→WARNING+truncate, language_mismatch→INFO.
  **DoD:** невалидный output блокируется и логируется. ✅
  → depends on: G.2

### Тесты Stage G ✅
- [x] 106 unit тестов в `tests/test_output.py` (106/106 passed)
- [x] 7 integration smoke тестов в `tests/test_output_integration.py` (7/7 passed)
- [x] `brain/output/__init__.py` — 13 публичных экспортов

---

## ЭТАП F+ — Cognitive Extensions (расширение когнитивного ядра)

> Отложенные из Stage F пункты + retrieval integration.
> Три подгруппы: Retrieval, Reasoning, Planning.

### F+.1 — Retrieval Integration (стык памяти и reasoning)

- [x] **F+.1a** Реализовать `brain/cognition/retrieval_adapter.py`:
  - `MemoryManager.retrieve() → List[EvidencePack]` адаптер,
  - нормализация формата результатов retrieve в unified evidence format,
  - ранжирование кандидатов для hypothesis engine,
  - contradiction-first сигнал в reasoning context.
  **DoD:** reasoner получает единый и стабильный вход из memory retrieval без ad-hoc преобразований. ✅
  → depends on: F.6, C.3

- [x] **F+.1b** Vector retrieval hook/interface:
  - абстракция для подключения vector DB (FAISS/ChromaDB) в будущем,
  - fallback на текущий keyword-based retrieval.
  **DoD:** интерфейс готов, текущий retrieval работает через него. ✅ (RetrievalBackend Protocol)
  → depends on: F+.1a, E.1

### F+.2 — Reasoning Extensions (обогащение рассуждений)

- [x] **F+.2a** Реализовать `brain/cognition/contradiction_detector.py` (text-only):
  - обнаружение противоречий между evidence packs,
  - contradiction score для гипотез,
  - интеграция с ReasoningState.contradiction_flags.
  **DoD:** противоречия обнаруживаются и влияют на scoring гипотез. ✅
  → depends on: F.6, F+.1a

- [x] **F+.2b** Реализовать `brain/cognition/uncertainty_monitor.py`:
  - мониторинг уверенности на каждой итерации reasoning loop,
  - uncertainty trend (растёт/падает/стабильна),
  - сигнал для early stop или escalation.
  **DoD:** uncertainty отслеживается и доступна в trace. ✅
  → depends on: F.6

- [x] **F+.2c** Causal reasoning стратегия для HypothesisEngine:
  - новая стратегия генерации: причинно-следственные связи,
  - `strategy="causal"` в Hypothesis.
  **DoD:** HypothesisEngine генерирует causal гипотезы при наличии temporal/causal evidence. ✅
  → depends on: F+.2a

- [x] **F+.2d** Analogical reasoning стратегия для HypothesisEngine:
  - новая стратегия генерации: аналогии между доменами,
  - `strategy="analogical"` в Hypothesis.
  **DoD:** HypothesisEngine генерирует analogical гипотезы при наличии cross-domain evidence. ✅
  → depends on: F+.2a

### F+.3 — Planning Extensions (умное перепланирование)

- [x] **F+.3a** Реализовать `Planner.replan()` с полными стратегиями:
  - стратегии: retry, narrow_scope, broaden_scope, decompose, escalate,
  - выбор стратегии на основе типа failure и истории попыток,
  - интеграция с ProceduralMemory (успешность стратегий).
  **DoD:** replan() выбирает оптимальную стратегию, а не только retry. ✅ (ProceduralMemory integration → Stage I)
  → depends on: F.6, F+.2b

---

## ЭТАП H — Attention & Resource Control (расширен)

> Подключаем когда text-only цикл уже живой.
> Включает SalienceEngine и Ring 2 (deep reasoning).

- [ ] **H.1** Реализовать `brain/cognition/salience_engine.py`:
  - оценка значимости (salience) входящих percepts и evidence,
  - факторы: novelty, relevance to active goal, emotional weight, recency,
  - salience score [0..1] для приоритизации.
  **DoD:** каждый percept/evidence получает salience score.
  → depends on: F+.1a, B.3

- [ ] **H.2** Реализовать `brain/core/attention_controller.py`:
  - goal-driven attention (фокус на активной цели),
  - salience-driven attention (переключение на значимые стимулы),
  - attention budget (ограничение параллельных потоков обработки),
  - приоритизация задач по goal + salience.
  **DoD:** при нагрузке система сохраняет качество critical-path.
  → depends on: H.1, G.2, B.3

- [ ] **H.3** Реализовать policy деградации:
  - отключение тяжёлых веток reasoning при high load,
  - graceful degradation: Ring 2 → Ring 1 → minimal response,
  - интеграция с ResourceMonitor policies.
  **DoD:** деградация предсказуема, без падений.
  → depends on: H.2

- [ ] **H.4** Ring 2 — Deep Reasoning (при наличии ресурсов):
  - расширенный reasoning loop с multi-iteration refinement,
  - использование contradiction signals и uncertainty trends,
  - активируется только при достаточных ресурсах (ResourceMonitor.NORMAL/DEGRADED).
  **DoD:** Ring 2 улучшает качество ответов при наличии ресурсов, не блокирует при их отсутствии.
  → depends on: **F+ + H.3** (требует и когнитивные расширения, и ресурсный контроль)

---

## ЭТАП I — Learning Loop

- [ ] **I.1** Реализовать `brain/learning/online_learner.py` (MVP):
  - обновление confidence по результатам ответа/фидбэка,
  - запись успешных/неуспешных reasoning traces в ProceduralMemory.
  **DoD:** feedback влияет на последующие ответы.
  → depends on: H, G

- [ ] **I.2** Реализовать `brain/learning/knowledge_gap_detector.py`:
  - фиксирует пробелы и создаёт обучающие подцели,
  - анализ INSUFFICIENT_CONFIDENCE и RETRIEVAL_FAILED outcomes.
  **DoD:** при низком покрытии знаний создаётся gap-goal.
  → depends on: I.1

- [ ] **I.3** Реализовать `brain/learning/replay_engine.py`:
  - replay важных эпизодов в idle,
  - приоритизация по salience и recency.
  **DoD:** replay запускается без деградации realtime-ответов.
  → depends on: I.1, H.3

---

## ЭТАП J — Расширение мультимодальности

- [ ] **J.1** Vision encoder path (ingest + encode)
- [ ] **J.2** Audio encoder path (ingest + encode)
- [ ] **J.3** Temporal/video path (минимум)
  **DoD:** каждая модальность проходит отдельный smoke e2e.
  → depends on: E.2, G.2

---

## ЭТАП K — Cross-Modal Fusion

- [ ] **K.1** `brain/fusion/shared_space_projector.py`
- [ ] **K.2** `brain/fusion/entity_linker.py`
- [ ] **K.3** `brain/fusion/confidence_calibrator.py`
- [ ] **K.4** `brain/fusion/contradiction_detector.py` (полная кросс-модальная версия):
  - расширение text-only ContradictionDetector (F+.2a) на все модальности,
  - shared multimodal evidence model.
  **DoD:** факты из разных модальностей связываются в единое представление, противоречия обнаруживаются кросс-модально.
  → depends on: J.1, J.2, J.3, F+.2a

---

## ЭТАП L — Safety & Boundaries

- [ ] **L.1** `brain/safety/source_trust.py`:
  - оценка доверия к источникам информации.
- [ ] **L.2** `brain/safety/conflict_detector.py`:
  - обнаружение конфликтов между решениями и ограничениями.
- [ ] **L.3** `brain/safety/boundary_guard.py`:
  - жёсткие границы допустимых действий.
- [ ] **L.4** `brain/safety/audit_logger.py`:
  - аудит-лог всех safety-значимых решений.
- [ ] **L.5** `brain/safety/policy_layer.py` — Decision Policy:
  - ограничения на допустимые действия (action constraints),
  - confidence gates (минимальный порог для действий),
  - escalation rules (когда передавать решение выше),
  - external tool/use policies (ограничения на внешние вызовы).
  **Примечание:** PolicyLayer — это именно decision policy, а не дублирование
  output validator (G.3) или degradation policy (H.3) или action selector (F.5).
  **DoD:** high-risk решения блокируются/аудируются, policy gates работают.
  → depends on: G.3, K.4

---

## ЭТАП N — LLM Bridge (внешний LLM как расширение)

> Подключение внешнего LLM после того, как safety boundaries установлены.
> LLM Bridge зависит от output layer + cognition + safety, НЕ от reward.

- [ ] **N.1** Реализовать `brain/bridges/llm_bridge.py`:
  - абстракция для подключения внешнего LLM (OpenAI/Anthropic/local),
  - request/response format adapter,
  - rate limiting и cost tracking.
- [ ] **N.2** Интеграция LLM в reasoning pipeline:
  - LLM как optional hypothesis generator,
  - LLM как optional response enhancer,
  - fallback на local reasoning при недоступности LLM.
- [ ] **N.3** Safety wrapper для LLM:
  - фильтрация input/output через PolicyLayer,
  - audit logging всех LLM вызовов.
  **DoD:** LLM подключается как optional extension, система работает и без него.
  → depends on: L, G.2

---

## ЭТАП M — Reward & Motivation (последним)

- [ ] **M.1** `brain/motivation/reward_engine.py`:
  - reward signal на основе feedback и outcome quality.
- [ ] **M.2** `brain/motivation/motivation_engine.py`:
  - влияние reward на приоритет целей.
- [ ] **M.3** `brain/motivation/curiosity_engine.py`:
  - intrinsic motivation для exploration.
  **DoD:** reward сигнал влияет на приоритет целей и learning.
  → depends on: I.3, L.3

---

## 🧪 Тестовый план по этапам

- [x] **T.1 Contracts tests** (serialization, backward-compatibility) — ✅ покрыто в test_cognition.py + test_output.py
- [x] **T.2 Runtime tests** (event bus + scheduler + resource flags) — ✅ 24/24 (scheduler:11 + resource_monitor:13)
- [ ] **T.3 Text-only e2e tests** (input → memory → reason → output → trace/log) — частично покрыто integration tests
- [x] **T.4 Regression memory tests** — ✅ 101/101 (`test_memory.py`)
- [ ] **T.5 Load/degradation tests** (CPU/RAM pressure сценарии) — ожидает Этап H

**Текущее покрытие:** 773 тестов, 0 failures (подтверждено: Python 3.14.3)
| Файл | Тестов | Статус |
|------|--------|--------|
| test_bm25.py | 55 | ✅ |
| test_memory.py | 101 | ✅ |
| test_cognition.py | 182 | ✅ |
| test_cognition_integration.py | 7 | ✅ |
| test_e2e_pipeline.py | 10 | ✅ |
| test_output.py | 106 | ✅ |
| test_output_integration.py | 7 | ✅ |
| test_text_encoder.py | 80 | ✅ |
| test_perception.py | 79 | ✅ |
| test_logging.py | 25 | ✅ |
| test_resource_monitor.py | 13 | ✅ |
| test_scheduler.py | 11 | ✅ |
| test_storage.py | 58 | ✅ |
| test_vector_retrieval.py | 39 | ✅ |
| **Итого** | **773** | **✅** |

---

## 📅 Статус реализации (актуальный)

### Завершено (Дни 1–7+) ✅
- [x] День 1: Contracts + Runtime (A + B) — contracts.py, event_bus.py, scheduler.py, resource_monitor.py
- [x] День 2: Logging (C) — brain_logger.py, digest_generator.py, trace_builder.py
- [x] День 3: Text Perception (D) — text_ingestor.py, metadata_extractor.py, input_router.py
- [x] День 4: Text Encoder (E) — text_encoder.py (primary + fallback + degraded modes)
- [x] День 5–6: Cognitive Core (F) — 7 файлов cognition/, 182+7 тестов
- [x] День 7: Output MVP (G) — 3 файла output/, 106+7 тестов

### Следующие этапы
- [~] **F+** — Cognitive Extensions: retrieval adapter ✅, contradiction detector ✅, uncertainty monitor ✅, causal/analogical reasoning ✅, full replan ✅. Осталось: тесты (~90 unit + ~5 integration), финализация v0.7.0
- [ ] **H** — Attention & Resource Control (~10–14 часов): salience engine, attention controller, degradation policy, Ring 2
- [ ] **I** — Learning Loop (~8–10 часов): online learner, knowledge gap detector, replay engine
- [ ] **J** — Multimodal Expansion (~16–20 часов): vision, audio, temporal encoders
- [ ] **K** — Cross-Modal Fusion (~12–16 часов): shared space, entity linker, calibrator, full contradiction detector
- [ ] **L** — Safety & Boundaries (~10–12 часов): source trust, conflict detector, boundary guard, audit, policy layer
- [ ] **N** — LLM Bridge (~8–10 часов): LLM abstraction, reasoning integration, safety wrapper
- [ ] **M** — Reward & Motivation (~10–12 часов): reward, motivation, curiosity engines

---

## 📌 Порядок реализации (коротко)

```text
A Contracts           ✅
→ B Runtime           ✅
→ C Logging           ✅
→ D Text Perception   ✅
→ E Text Encoder      ✅
→ F Cognitive MVP     ✅
→ G Output MVP        ✅
→ F+ Cognitive Extensions
→ H Attention & Resource Control
→ I Learning Loop
→ J Multimodal Expansion
→ K Cross-Modal Fusion
→ L Safety & Boundaries
→ N LLM Bridge
→ M Reward & Motivation
```

---

## 📊 Прогресс

| Этап | Название | Статус | Тесты | Риск/Сложность |
|------|----------|--------|-------|----------------|
| A | Shared Contracts | ✅ A.1, A.2 | — | Средний |
| B | Minimal Runtime | ✅ B.1, B.2, B.3 | 24 | Средний |
| C | Logging & Observability | ✅ C.1, C.2, C.3 | 25 | Низкий |
| D | Text-Only Perception | ✅ D.1, D.2, D.3 | 79 | Средний |
| E | Minimal Text Encoder | ✅ E.1, E.2 | 80 | Средний |
| F | Cognitive MVP | ✅ F.1–F.6 | 189 | Высокий |
| G | Output MVP | ✅ G.1–G.3 | 113 | Средний |
| **F+** | **Cognitive Extensions** | **[~] В ПРОЦЕССЕ** (Steps 1-9 ✅, 10-12 ⬜) | — | **Высокий** |
| H | Attention & Resource Control | [ ] | — | Средний |
| I | Learning Loop | [ ] | — | Средний |
| J | Multimodal Expansion | [ ] | — | Высокий |
| K | Cross-Modal Fusion | [ ] | — | Высокий |
| L | Safety & Boundaries | [ ] | — | Средний |
| N | LLM Bridge | [ ] | — | Средний |
| M | Reward & Motivation | [ ] | — | Высокий |
