# 🧠 TODO — Master Roadmap
## cognitive-core v0.7.0

> **Обновлено:** 2026-03-25  
> **Принцип:** сначала стабилизировать text-only MVP, затем расширять  
> **Тесты:** 773/773 ✅ · **Ruff:** 0 errors · **CI:** test + lint + typecheck  
> **Связанные документы:**
> - [`cognitive_core_mvp_roadmap_revised.md`](cognitive_core_mvp_roadmap_revised.md) — детальный MVP roadmap с Definition of Done
> - [`PLANS.md`](PLANS.md) — стратегический контекст (Axicor, ARCHITECTURE.md роль, hot/cold path)
> - [`BRAIN.md`](BRAIN.md) — архитектурная спецификация (15 разделов)
> - [`ARCHITECTURE.md`](ARCHITECTURE.md) — R&D концепт когнитивного нейрона (не текущий target)

---

## 📌 Навигация

1. [MVP Roadmap](#-mvp-roadmap-фазы-abc) — что делать сейчас
2. [Post-MVP](#-post-mvp) — что делать после MVP
3. [Backlog](#-backlog-p2p3) — улучшения и research
4. [Completed](#-completed-история-реализации) — что уже сделано
5. [Test Coverage](#-test-coverage) — таблица тестов

---

## 🎯 MVP Roadmap (Фазы A/B/C)

> **MVP = стабильный text-only релиз** с честным запуском, замкнутым пайплайном и минимально вычищенными стыками.
>
> **Что входит в MVP:** CLI entrypoint, auto-encode, memory→reason→output, реальный mypy, perception hardening, README = правда.
>
> **Что НЕ входит:** persisted vector pipeline, ANN/FAISS, multimodal, Ring 2, Attention Controller, reward/motivation, большой DRY-рефакторинг.

### Критерии готовности MVP

- [ ] `pip install -e . && cognitive-core "вопрос"` работает из коробки
- [ ] text-only пайплайн замкнут: `input → encode → memory → reason → output`
- [ ] `CognitiveCore` использует encoder автоматически
- [ ] `ResourceMonitor` передаёт реальные данные в cognition
- [ ] CI зелёный с реальным mypy (без `|| true`)
- [ ] Perception отвергает опасные пути и слишком большие файлы
- [ ] README соответствует фактическому поведению проекта
- [ ] есть `examples/demo.py` или аналогичный рабочий demo

---

### Фаза A — Foundation (1–2 дня)

> Убрать всё, что мешает проекту запускаться и быть воспроизводимым.

- [ ] **A.1** Официальный entrypoint / CLI
  - Создать `brain/cli.py` + `[project.scripts]` в pyproject.toml
  - Команда: `cognitive-core "Что такое нейропластичность?"`
  - Собрать минимальный пайплайн: `MemoryManager → CognitiveCore → OutputPipeline`
  - Добавить `examples/demo.py`
  - **DoD:** `pip install -e . && cognitive-core "вопрос"` → осмысленный ответ

- [ ] **A.2** Починить контракт `ResourceMonitor ↔ CognitiveCore`
  - Синхронизировать `ResourceMonitor`, `ResourceMonitorProtocol`, `CognitiveCore`
  - Один публичный API: `snapshot()` или `check()` с единым return type
  - Unit-тест на protocol conformance + integration-тест с реальным ResourceMonitor
  - **DoD:** `CognitiveCore` получает реальные данные о ресурсах, а не пустой fallback

- [ ] **A.3** Сделать mypy настоящим барьером качества
  - Убрать `|| true` из mypy job для `brain/core`, `brain/cognition`, `brain/memory`
  - Исправить критические type errors
  - Точечные `# type: ignore` с TODO где необходимо
  - **DoD:** CI проходит с реальным mypy без искусственного пропуска ошибок

---

### Фаза B — Close the Loop (2–3 дня)

> Реально замкнуть text-only MVP-пайплайн.

- [ ] **B.1** Auto-encode в `CognitiveCore`
  - Если `encoded_percept is None` и encoder доступен → `CognitiveCore.run()` сам кодирует query
  - Передать результат в retrieval / reasoning
  - Обновить e2e тесты
  - **DoD:** `CognitiveCore.run("запрос")` без ручного `encoded_percept` использует encoder автоматически

- [ ] **B.2** Минимальный hardening perception
  - `validate_file_path(...)`, `check_file_size(...)`, конфиг `MAX_FILE_SIZE_MB`
  - Интегрировать в `TextIngestor` и `InputRouter`
  - Тесты: path traversal, oversized file
  - **DoD:** система предсказуемо отвергает опасные пути и слишком большие файлы

- [ ] **B.3** Зафиксировать retrieval scope для MVP
  - Retrieval = keyword-first + BM25 reranking (текущий)
  - Vector retrieval не позиционируется как fully persisted MVP-capability
  - **DoD:** README и CLI честно описывают retrieval как text-first путь

- [ ] **B.4** README привести к реальности
  - Quick Start → реальный entrypoint (`pip install -e . && cognitive-core "..."`)
  - Multimodal → пометить как "Planned (post-MVP)"
  - Честно описать статус retrieval
  - Обновить "Что сделано / Что дальше"
  - **DoD:** README = единственный правдивый источник запуска и статуса MVP

---

### Фаза C — MVP Cleanup (1–2 дня)

> Убрать самые вредные дубли и сцепки, не уходя в большой рефакторинг.

- [ ] **C.1** Канонический `detect_language()`
  - Вынести в `brain/core/utils.py`
  - Основные runtime-пути используют одну реализацию
  - **DoD:** одна каноническая функция, все модули используют её

- [ ] **C.2** Канонический `extract_fact()`
  - Выделить один общий utility / service API для fact extraction
  - **DoD:** факт-экстракция через явный публичный путь

- [ ] **C.3** Убрать прямой вызов `consolidation._extract_fact()`
  - `MemoryManager` не должен зависеть от приватной внутренности `ConsolidationEngine`
  - **DoD:** приватный `_extract_fact()` не вызывается извне

- [ ] **C.4** Optional: вынести `_sha256()`
  - Если уже создаётся `utils.py`, заодно вынести hash helpers
  - **DoD:** не блокер MVP

---

## 📦 Post-MVP

> Задачи после стабильного text-only MVP. Порядок: D → E → F → H → I → J/K → L → N → M.

### Фаза D — Retrieval Upgrade (2–4 дня)

- [ ] **D.1** Persisted embeddings + schema changes
- [ ] **D.2** Cosine search / ANN (FAISS или hnswlib)
- [ ] **D.3** Hybrid retrieval как официальный путь
- [ ] **D.4** Retrieval quality benchmarks (Recall@5, MRR@10, gold set)

### Фаза E — Clean Code / DRY Sweep (2–3 дня)

- [ ] **E.1** Общий JSON serialization helper
- [ ] **E.2** Cleanup utilities (дублирующиеся функции)
- [ ] **E.3** Частичный разбор дублирующихся функций между модулями

### Фаза F — Hardening & DX (2–3 дня)

- [ ] **F.1** Lazy loading encoder
- [ ] **F.2** Graceful shutdown через `Event.wait()` где оправдано
- [ ] **F.3** Concurrency stress tests
- [ ] **F.4** Lock-файл / reproducible builds

### Этап H — Attention & Resource Control (10–14 часов)

> Подключаем когда text-only цикл уже живой.

- [ ] **H.1** `brain/cognition/salience_engine.py` — оценка значимости (novelty, relevance, urgency, threat)
  - → depends on: F+, B.3
- [ ] **H.2** `brain/core/attention_controller.py` — goal-driven + salience-driven attention, attention budget
  - → depends on: H.1, G, B.3
- [ ] **H.3** Policy деградации — graceful degradation: Ring 2 → Ring 1 → minimal response
  - → depends on: H.2
- [ ] **H.4** Ring 2 — Deep Reasoning (multi-iteration refinement, contradiction signals, uncertainty trends)
  - → depends on: F+, H.3

### Этап I — Learning Loop (8–10 часов)

- [ ] **I.1** `brain/learning/online_learner.py` — обновление confidence по feedback
  - → depends on: H, G
- [ ] **I.2** `brain/learning/knowledge_gap_detector.py` — фиксация пробелов, обучающие подцели
  - → depends on: I.1
- [ ] **I.3** `brain/learning/replay_engine.py` — replay эпизодов в idle
  - → depends on: I.1, H.3

### Этап J — Multimodal Expansion (16–20 часов)

> Расширение за пределы text-only.

- [ ] **J.1** Vision encoder path (ingest + encode)
- [ ] **J.2** Audio encoder path (ingest + encode)
- [ ] **J.3** Temporal/video path (минимум)
  - → depends on: E.2, G

### Этап K — Cross-Modal Fusion (12–16 часов)

- [ ] **K.1** `brain/fusion/shared_space_projector.py`
- [ ] **K.2** `brain/fusion/entity_linker.py`
- [ ] **K.3** `brain/fusion/confidence_calibrator.py`
- [ ] **K.4** `brain/fusion/contradiction_detector.py` (полная кросс-модальная версия)
  - → depends on: J.1, J.2, J.3, F+.2a

### Этап L — Safety & Boundaries (10–12 часов)

- [ ] **L.1** `brain/safety/source_trust.py`
- [ ] **L.2** `brain/safety/conflict_detector.py`
- [ ] **L.3** `brain/safety/boundary_guard.py`
- [ ] **L.4** `brain/safety/audit_logger.py`
- [ ] **L.5** `brain/safety/policy_layer.py` — Decision Policy (confidence gates, escalation rules)
  - → depends on: G, K.4

### Этап N — LLM Bridge (8–10 часов)

> Подключение внешнего LLM после safety boundaries.

- [ ] **N.1** `brain/bridges/llm_bridge.py` — абстракция для OpenAI/Anthropic/local
- [ ] **N.2** Интеграция LLM в reasoning pipeline (optional hypothesis generator / response enhancer)
- [ ] **N.3** Safety wrapper для LLM (фильтрация через PolicyLayer, audit logging)
  - → depends on: L, G

### Этап M — Reward & Motivation (10–12 часов)

> Последний этап — дофаминовая система.

- [ ] **M.1** `brain/motivation/reward_engine.py`
- [ ] **M.2** `brain/motivation/motivation_engine.py`
- [ ] **M.3** `brain/motivation/curiosity_engine.py`
  - → depends on: I.3, L.3

### CUDA Backend (1–3 недели, после понимания bottlenecks)

- [ ] Compute backend abstraction: `brain/compute/cpu_backend.py` + `cuda_backend.py`
- [ ] Приоритет: text encoder → embeddings → reranker → local LLM inference
- [ ] Логика проекта должна работать и на CPU

### Research Branch (отдельно от mainline)

- [ ] Эксперименты из `ARCHITECTURE.md` (cognitive neuron, predictive coding)
- [ ] Predictive neuron prototypes
- [ ] Circuit-level substrate R&D
- [ ] Ternary + LLaMA эксперименты (см. `docs/ideas/ternary+llama.md`)

---

## 📋 Backlog (P2/P3)

> Улучшения качества, масштабируемости и DX. Не блокируют MVP.

### P2 — Улучшения

- [ ] **P2.1** TTL/LRU для in-memory индексов BrainLogger (защита от роста памяти)
- [ ] **P2.2** Ослабить связность EvidencePack (core + metadata разделение)
- [ ] **P2.3** Вынести стратегии HypothesisEngine в Strategy pattern
- [ ] **P2.4** Property-based и benchmark тесты (hypothesis library, perf regression)
- [ ] **P2.5** Убрать Python 3.14 из classifiers в pyproject.toml (не тестируется в CI)
- [ ] **P2.6** Добавить CHANGELOG.md
- [ ] **P2.7** Добавить CONTRIBUTING.md
- [ ] **P2.8** Добавить `.gitkeep` в `brain/data/memory/`
- [ ] **P2.9** CI: добавить pip cache для ускорения билдов
- [ ] **P2.10** ContradictionDetector: заменить `copy.deepcopy` на `dataclasses.replace` (performance)

### P3 — Research / Backlog

- [ ] **P3.1** Contradiction detection: NLI-модель вместо negation-based логики
- [ ] **P3.2** OpenTelemetry: оценить замену части кастомного трейсинга

---

## ✅ Completed (история реализации)

<details>
<summary><strong>P0 — Критические исправления (v0.6.1)</strong></summary>

- [x] **P0.1** Синхронизировать версии: `brain/__init__.py` → `0.6.1`, `pyproject.toml` → `0.6.1`, README → 660 тестов
- [x] **P0.2** Очистить артефакты `NaN` в README.md
- [x] **P0.3** Проверить `NaN` в `brain/core/events.py` (файл уже чист)
- [x] **P0.4** Зафиксировать API-контракты: `MemoryManagerProtocol`, `EventBusProtocol`, `ResourceMonitorProtocol`
- [x] **P0.5** Убрать side effects в retrieval: `dataclasses.replace()` в `_ensure_canonical()`, `_enrich()`, `_rrf_merge()`
- [x] **P0.6** E2E тест + lint блокирующий: `tests/test_e2e_pipeline.py` (10 тестов), ruff blocking в CI

</details>

<details>
<summary><strong>P1a — Quick Wins (v0.7.0)</strong></summary>

- [x] **P1.0** Ruff lint cleanup: 131 → 0 errors
- [x] **P1.4** `session_id: Optional[str] = None` в `CognitiveCore.run()`
- [x] **P1.5** `pytest-cov` в CI с coverage reporting
- [x] **P1.6** Синхронизация зависимостей pyproject.toml ↔ requirements.txt
- [x] **P1.7** Disclaimer в `docs/ARCHITECTURE.md`
- [x] **P1.8** `atexit.register()` в BrainLogger через `weakref.ref`
- [x] **P1.9** mypy typecheck job в CI (non-blocking на первом этапе)

</details>

<details>
<summary><strong>P1b — BM25 Retrieval Quality (v0.7.0)</strong></summary>

- [x] **P1.1** BM25 reranking в KeywordRetrievalBackend
  - `BM25Scorer` класс: TF-IDF с BM25 формулой (k1=1.5, b=0.75)
  - `KeywordRetrievalBackend._bm25_rerank()`: reranking кандидатов
  - Опциональная лемматизация через pymorphy3 (graceful fallback)
  - 55 тестов в `tests/test_bm25.py`

</details>

<details>
<summary><strong>P1c — SQLite Persistence (v0.7.0)</strong></summary>

- [x] **P1.3** SQLite persistence layer
  - `brain/memory/storage.py`: MemoryDatabase (WAL, RLock, schema versioning, full CRUD)
  - `brain/memory/migrate.py`: JSON→SQLite миграция (backup, idempotent, marker)
  - Все memory модули: `storage_backend="auto"|"sqlite"|"json"`, `db` параметр
  - `MemoryManager`: транзакционный `save_all()`, `storage_backend` param
  - 58 тестов в `tests/test_storage.py`

</details>

<details>
<summary><strong>Этапы A→G — Основная реализация</strong></summary>

#### Этап A — Shared Contracts ✅
- [x] A.1 `brain/core/contracts.py`: 9 dataclass, ContractMixin, Modality enum
- [x] A.2 Правила совместимости: `to_dict()`/`from_dict()`, trace_id/session_id/cycle_id

#### Этап B — Minimal Autonomous Runtime ✅
- [x] B.1 `brain/core/event_bus.py`: pub/sub, wildcard, error isolation, BusStats
- [x] B.2 `brain/core/scheduler.py`: heapq, 4 приоритета, адаптивный tick 100/500/2000ms
- [x] B.3 `brain/core/resource_monitor.py`: 4 политики, hysteresis, daemon thread, inject_state()

#### Этап C — Logging & Observability ✅
- [x] C.1 `brain/logging/brain_logger.py`: JSONL, 5 уровней, категорийные файлы, ротация
- [x] C.2 `brain/logging/digest_generator.py`: CycleInfo, cycle/session digests
- [x] C.3 `brain/logging/reasoning_tracer.py`: TraceBuilder, reconstruct, to_human_readable

#### Этап D — Text-Only Perception ✅
- [x] D.1 `brain/perception/text_ingestor.py`: .txt/.md/.pdf/.docx/.json/.csv, chunking
- [x] D.2 `brain/perception/metadata_extractor.py`: language, quality, quality_label
- [x] D.3 `brain/perception/input_router.py`: SHA256 dedup, quality policy

#### Этап E — Minimal Text Encoder ✅
- [x] E.1 `brain/encoders/text_encoder.py`: sentence-transformers 768d / navec 300d fallback
- [x] E.2 Lightweight режим: 4 режима (primary → fallback → degraded → failed)

#### Этап F — Cognitive MVP ✅
- [x] F.1 `brain/cognition/context.py`: CognitiveContext, CognitiveOutcome, EvidencePack, GoalTypeLimits
- [x] F.2 `brain/cognition/goal_manager.py` + `planner.py`: Goal, GoalManager, Planner, 5 replan strategies
- [x] F.3 `brain/cognition/hypothesis_engine.py`: 4 стратегии (assoc+deduct+causal+analog)
- [x] F.4 `brain/cognition/reasoner.py`: reasoning loop (retrieve → hypothesize → score → select)
- [x] F.5 `brain/cognition/action_selector.py`: 5 ActionType, ActionDecision
- [x] F.6 `brain/cognition/cognitive_core.py`: CognitiveCore orchestrator, 10-step run()

#### Этап F+ — Cognitive Extensions ✅
- [x] F+.1a `brain/cognition/retrieval_adapter.py`: RetrievalAdapter, unified evidence format
- [x] F+.1b Vector retrieval hook: RetrievalBackend Protocol, VectorRetrievalBackend, HybridRetrievalBackend
- [x] F+.2a `brain/cognition/contradiction_detector.py`: negation/numeric/confidence_gap checks
- [x] F+.2b `brain/cognition/uncertainty_monitor.py`: trend tracking, early stop, escalation
- [x] F+.2c Causal reasoning стратегия для HypothesisEngine
- [x] F+.2d Analogical reasoning стратегия для HypothesisEngine
- [x] F+.3a `Planner.replan()` с полными стратегиями (retry, narrow, broaden, decompose, escalate)

#### Этап G — Output MVP ✅
- [x] G.1 `brain/output/trace_builder.py`: ExplainabilityTrace, OutputTraceBuilder
- [x] G.2 `brain/output/dialogue_responder.py`: DialogueResponder, OutputPipeline
- [x] G.3 `brain/output/response_validator.py`: 4 проверки, FALLBACK_RESPONSE

</details>

---

## 🧪 Test Coverage

**Всего: 773/773 ✅** (Python 3.14.3, 97.21s)

| Файл | Модуль | Тестов | Статус |
|------|--------|--------|--------|
| `test_bm25.py` | BM25 Scorer + KeywordBackend reranking | 55 | ✅ |
| `test_storage.py` | SQLite Storage + Migration | 58 | ✅ |
| `test_e2e_pipeline.py` | E2E Pipeline + Protocol conformance | 10 | ✅ |
| `test_memory.py` | Memory System (5 types + consolidation + manager) | 101 | ✅ |
| `test_cognition.py` | Cognitive Core (unit) | 182 | ✅ |
| `test_cognition_integration.py` | Cognitive Core (integration) | 7 | ✅ |
| `test_output.py` | Output Layer (unit) | 106 | ✅ |
| `test_output_integration.py` | Output Layer (integration) | 7 | ✅ |
| `test_text_encoder.py` | Text Encoder (4 modes) | 80 | ✅ |
| `test_perception.py` | Perception Layer | 79 | ✅ |
| `test_logging.py` | Logging & Observability | 25 | ✅ |
| `test_resource_monitor.py` | ResourceMonitor | 13 | ✅ |
| `test_scheduler.py` | Scheduler | 11 | ✅ |
| `test_vector_retrieval.py` | Vector Retrieval | 39 | ✅ |
| **Итого** | | **773** | **✅** |

---

## 📊 Прогресс

| Этап | Название | Статус | Тесты |
|------|----------|--------|-------|
| A–G | Foundation → Output MVP | ✅ Завершено | 773 |
| F+ | Cognitive Extensions | ✅ Завершено | (в test_cognition) |
| P0 | Критические исправления | ✅ Завершено | — |
| P1 | BM25 + SQLite + CI | ✅ Завершено | 113 новых |
| **MVP A** | **Foundation** | **[ ] Следующий** | — |
| MVP B | Close the Loop | [ ] | — |
| MVP C | MVP Cleanup | [ ] | — |
| D | Retrieval Upgrade | [ ] Post-MVP | — |
| E | DRY Sweep | [ ] Post-MVP | — |
| F | Hardening & DX | [ ] Post-MVP | — |
| H | Attention & Resource Control | [ ] | — |
| I | Learning Loop | [ ] | — |
| J | Multimodal Expansion | [ ] | — |
| K | Cross-Modal Fusion | [ ] | — |
| L | Safety & Boundaries | [ ] | — |
| N | LLM Bridge | [ ] | — |
| M | Reward & Motivation | [ ] | — |

---

## 🔗 Зависимости между фазами

```text
MVP (обязательно):
  A.1 CLI → A.2 ResourceMonitor → A.3 mypy
  B.1 Auto-encode → B.2 Perception hardening → B.3 Retrieval scope → B.4 README
  C.1 detect_language → C.2 extract_fact → C.3 убрать _extract_fact()

Post-MVP:
  D Retrieval Upgrade
  E DRY Sweep
  F Hardening & DX

Расширение:
  H Attention (depends: F+, MVP)
  I Learning (depends: H, G)
  J Multimodal (depends: E, G)
  K Fusion (depends: J, F+)
  L Safety (depends: G, K)
  N LLM Bridge (depends: L, G)
  M Reward (depends: I, L)

Отдельно:
  CUDA Backend (после понимания bottlenecks)
  Research Branch (ARCHITECTURE.md experiments)
```

---

## 📌 Правило принятия решений

При возникновении новой идеи — три вопроса:

1. Помогает ли это закрыть text-only MVP?
2. Улучшает ли наблюдаемость, стабильность или retrieval?
3. Не уводит ли в research раньше времени?

**да / да / нет** → брать · **нет / нет / да** → откладывать в R&D
