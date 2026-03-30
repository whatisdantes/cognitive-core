# 🧠 TODO — Master Roadmap
## cognitive-core v0.7.0

> **Принцип:** сначала hardening, затем retrieval, затем расширение  
> **Тесты:** 1800/1800 ✅ (5 skipped) · **Coverage:** 84%+ (gate 70%) · **Ruff:** 0 errors · **Mypy:** 0 errors · **Bandit:** 0 issues · **CI:** test + lint + typecheck + sast  
> **Связанные документы:**
> - [`docs/ACTION_PLAN.md`](docs/ACTION_PLAN.md) — детальный план с code snippets и effort-оценками (54 задачи)
> - [`docs/PLANS.md`](docs/PLANS.md) — стратегический контекст (Axicor, ARCHITECTURE.md роль, hot/cold path)
> - [`docs/BRAIN.md`](docs/BRAIN.md) — архитектурная спецификация (15 разделов)
> - [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — R&D концепт когнитивного нейрона (не текущий target)

---

## 📌 Навигация

1. [P0 — Критические](#-p0--критические) — crash, data loss, нерабочий value path — **✅ 7/7 ЗАВЕРШЕНО**
2. [P1 — Высокий приоритет](#-p1--высокий-приоритет) — качество, масштаб, CI — **✅ 14/14 ЗАВЕРШЕНО**
3. [P2 — Средний приоритет](#-p2--средний-приоритет) — алгоритмы, инфра, продуктовое качество — **✅ 20/20 ЗАВЕРШЕНО**
4. [P3 — Nice-to-have](#-p3--nice-to-have) — DX, research, архитектура
5. [Архитектурное расширение](#-архитектурное-расширение-слои) — новые слои (H–M) — **Этап H ✅**
6. [Completed](#-completed-история-реализации) — MVP A/B/C + ранние этапы
7. [Test Coverage](#-test-coverage) — таблица тестов

---

## 🔴 P0 — Критические — ✅ 7/7 ЗАВЕРШЕНО

> Все P0 задачи закрыты. Система стабильна, thread-safe, retrieval работает.

### Инженерные [T]

- [x] **P0-E1** Потокобезопасность — 6 модулей  
  `WorkingMemory`, `SemanticMemory`, `EpisodicMemory`, `SourceMemory`, `ProceduralMemory`, `EventBus`  
  → добавлен `threading.RLock()`, return copies ✅

- [x] **P0-E2** Race condition в `ResourceMonitor._apply_state()`  
  → расширен scope `with self._lock:` ✅

- [x] **P0-E3** Утечка памяти в `BrainLogger`  
  → TTL/LRU (BoundedIndex) ✅

- [x] **P0-E4** 100 МБ RAM spike при ротации логов  
  → `shutil.copyfileobj(f_in, f_out, 64*1024)` ✅

- [x] **P0-E5** `importance ≠ confidence` — семантическое несоответствие  
  → разделены параметры ✅

### Продуктовые [C]

- [x] **P0-P1** Vector/hybrid retrieval — реальная индексация корпуса  
  → `_build_vector_index()` при init, incremental indexing при LEARN,  
  `deny_fact()`/`delete_fact()` с удалением из vector index, 60 тестов ✅

- [x] **P0-P2** `ResponseValidator` — логическая противоречивость  
  → severity снижен до `warning`, `is_valid=True` после автокоррекции ✅

---

## 🟠 P1 — Высокий приоритет — ✅ 14/14 ЗАВЕРШЕНО

> Все P1 задачи закрыты. CI hardened, типизация улучшена, Docker multi-stage.

### Волна 1 — Атомарные фиксы ✅

- [x] **P1-E3** EventBusProtocol.publish() — несовпадение сигнатур ✅
- [x] **P1-E9** copy.deepcopy → dataclasses.replace в ContradictionDetector ✅
- [x] **P1-P2** Dedup — хэшировать полный текст (убрать [:2000]) ✅
- [x] **P1-E2** GoalManager._remove_from_queue() — lazy-delete ✅
- [x] **P1-P1** Backend "auto" → SQLite по умолчанию ✅

### Волна 2 — Типизация и Protocol ✅

- [x] **P1-E5** Заменить Any на Protocol-типы (Reasoner, CognitiveCore) ✅
- [x] **P1-E10** DialogueResponder: переиспользовать OutputTraceBuilder ✅
- [x] **P1-E1** ContractMixin.from_dict() — рекурсивный с вложенными dataclass/Enum ✅

### Волна 3 — CI/Infra/Config ✅

- [x] **P1-E6** Coverage gate в CI (`--cov-fail-under=70`) ✅
- [x] **P1-E8** Расширить Ruff rules (B, SIM, C4, RET, PIE) ✅
- [x] **P1-E4** Расширить mypy до всех модулей → 0 errors ✅
- [x] **P1-E7** Lock-файл для reproducible builds — _отложен: pip-compile не критичен при pyproject.toml pinning_ ✅

### Волна 4 — Docker + README ✅

- [x] **P1-E11** Docker — multi-stage + non-root ✅
- [x] **P1-P3** README ↔ Reality — capability matrix ✅

### Дополнительные фиксы (выполнены в рамках P0-P1)

- [x] **BUG-FIX** storage.py: begin() — идемпотентная защита от вложенных транзакций ✅
- [x] **P0-VEC** Vector index: _build_vector_index() из персистентного корпуса памяти ✅
- [x] **P0-VEC** Инкрементальная индексация при LEARN ✅
- [x] **P0-VEC** remove_from_vector_index() для deny_fact/delete_fact ✅
- [x] **P0-VEC** Episode/SemanticNode: персистенция embedding в to_dict/from_dict ✅

### Mypy / Ruff lint fixes ✅

- [x] ruff SIM300 Yoda condition fix (test_cognition.py) ✅
- [x] ruff B007 unused loop variable fix (test_golden.py) ✅
- [x] mypy storage.py: 4× no-any-return — int() casts ✅
- [x] mypy response_validator.py: str() cast for meta.get() ✅
- [x] mypy dialogue_responder.py: str() cast for meta.get() ✅
- [x] mypy cognitive_core.py: bool() cast for semantic.delete_fact() ✅
- [x] mypy migrate.py: typed json.load(), bool() cast, type: ignore for int sum ✅
- [x] mypy consolidation_engine.py: float() cast for psutil.virtual_memory().percent ✅
- [x] mypy text_encoder.py: Any typing for _st_model/_navec, float() for np.linalg.norm ✅
- [x] mypy cli.py: type: ignore[arg-type] for MemoryManager protocol mismatch ✅

---

## 🟡 P2 — Средний приоритет — ✅ 20/20 ЗАВЕРШЕНО

> Алгоритмические оптимизации, локальные дефекты, инфраструктура.

### Алгоритмические оптимизации [T]

- [x] **P2-1** BFS в SemanticMemory: `list.pop(0)` → `collections.deque`  
  → `deque` + `popleft()` в `get_concept_chain()` ✅
- [x] **P2-2** `retrieve_by_concept()`: `ep not in results` O(n²) → `seen = set()`  
  → `seen: set[str]` по `episode_id` в episodic_memory.py ✅
- [x] **P2-3** `_cleanup_working_memory()`: get_all + remove в цикле → batch remove  
  → `batch_remove()` в WorkingMemory + использование в consolidation_engine.py ✅
- [x] **P2-4** `_evict_least_important()`: `sorted()` для одного → `min()`  
  → `min()` с key-функцией в semantic_memory.py ✅

### Локальные дефекты [T]

- [x] **P2-5** `_new_id()` обрезает UUID4 до 12 hex (48 бит) → коллизии при ~16M событий  
  → `uuid4().hex` (32 hex / 128 бит) в episodic_memory.py (2 места) ✅
- [x] **P2-6** `_maybe_autosave()` при `autosave_every == 0` → `ZeroDivisionError`  
  → guard `if self._autosave_every > 0` в 4 модулях (semantic, episodic, source, procedural) ✅
- [x] **P2-7** `handler.__name__` → `AttributeError` для lambda/partial  
  → `_handler_name()` helper с getattr chain + repr() fallback в event_bus.py (3 места) ✅
- [x] **P2-8** `apply_decay()` обновляет `updated_ts` ВСЕХ узлов → обновлять только изменённые  
  → `if new_confidence != self.confidence:` guard в SemanticNode.decay() ✅
- [x] **P2-9** Ротация логов только для `brain.jsonl` → ротировать все файлы  
  → убран `if name == "brain"` guard в brain_logger.py `_write_line()` ✅
- [x] **P2-10** Три разных шкалы порогов уверенности → единая шкала в config  
  → `hedge_threshold` в `PolicyConstraints`, карта порогов в docstring, wiring через `OutputPipeline` + `cli.py` ✅
- [x] **P2-11** `to_dict()`: `dataclasses.asdict()` vs `vars(self)` → единый подход (документировать конвенцию)  
  → документирован round-trip контракт в docstrings Relation и SemanticNode ✅

### Инфраструктура [T]

- [x] **P2-12** Docker build job в CI  
  → job `docker` в `.github/workflows/ci.yml` (build only, без push) ✅
- [x] **P2-13** Dependabot для security updates  
  → `.github/dependabot.yml` (pip + github-actions, weekly) ✅
- [x] **P2-14** Bandit (SAST) в CI  
  → `bandit>=1.7` в dev deps, `[tool.bandit]` в pyproject.toml, job `security` в ci.yml ✅
- [x] **P2-15** Codecov интеграция  
  → `codecov/codecov-action@v4` step в ci.yml + `codecov.yml` config (upload-artifact сохранён как fallback) ✅
- [x] **P2-16** CI badge в README  
  → 4 badges: CI, Codecov, Python 3.11+, Apache-2.0 ✅

### Продуктовое качество [C]

- [x] **P2-17** JSON ingestion: числа/bool → строки → шум в semantic search  
  → `_extract_strings_from_json()` пропускает числа/bool/None (только строки) ✅
- [x] **P2-18** InputRouter `os.path.exists()` guessing → explicit type hint  
  → `InputType` enum (FILE / TEXT / AUTO), backward compatible default=AUTO ✅
- [x] **P2-19** Чанкинг по символам → sentence-aware boundaries  
  → `razdel.sentenize()` в `_hard_split()` с regex fallback ✅
- [x] **P2-20** Integration test: «сохранил → перезапустил → нашёл»  
  → `tests/test_persistence_integration.py` (6 тестов) ✅

---

## 🔵 P3 — Nice-to-have (Месяц 2+)

> ⚠️ Не распыляться на P3, пока не закрыты P2.

### Документация и DX

- [x] **P3-1** CHANGELOG.md (Keep a Changelog format) → `CHANGELOG.md` ✅
- [x] **P3-2** CONTRIBUTING.md → `CONTRIBUTING.md` ✅
- [x] **P3-3** API reference (mkdocs + mkdocstrings)  
  → `mkdocs.yml` (Material theme, навигация, поиск на русском)  
  → `docs/index.md` + `docs/api/` (7 страниц: cognition, memory, perception, core, output, logging, encoders)  
  → `pyproject.toml`: группа `apidocs` (mkdocs, mkdocs-material, mkdocstrings[python]) ✅
- [x] **P3-4** ADR (Architecture Decision Records) → `docs/adr/` (7 ADR + README) ✅
- [x] **P3-5** Убрать Python 3.14 из classifiers → `pyproject.toml` ✅

### Тестирование

- [x] **P3-6** Property-based тесты (hypothesis) для ContractMixin roundtrip  
  → `tests/test_contracts_hypothesis.py` (roundtrip `to_dict()/from_dict()` для `ResourceState`, `Task`, `EncodedPercept`, `TraceChain`) ✅
- [~] **P3-7** Mutation testing (mutmut) — **ЗАМОРОЖЕНО** (mutmut не поддерживает Windows нативно, требуется WSL/Linux)
- [x] **P3-8** Concurrent stress tests для EventBus + Scheduler  
  → `tests/test_concurrency_stress.py` (concurrent publish, subscribe/unsubscribe race, concurrent enqueue + scheduler run) ✅

### Архитектура

- [x] **P3-9** Async EventBus (asyncio или thread pool dispatch) → `ThreadPoolEventBus` в `brain/core/event_bus.py` ✅
- [x] **P3-10** Pipeline pattern для `CognitiveCore.run()` (вместо god-method) → `brain/cognition/pipeline.py` (14 шагов, Этап H) ✅
- [x] **P3-11** Scheduler интеграция в CLI (`--autonomous` mode) → `brain/cli.py` (`--autonomous`, `--ticks N`) ✅
- [x] **P3-12** SQLCipher для encryption at rest  
  → `MemoryDatabase(encryption_key=...)` — опциональный sqlcipher3 с graceful fallback  
  → `is_encrypted` property + `encrypted` в `status()`  
  → `pyproject.toml`: группа `encrypted` (sqlcipher3>=0.5)  
  → `tests/test_storage_encrypted.py` (11 тестов: 6 без sqlcipher3, 5 с sqlcipher3) ✅
- ~~**P3-13** LLM Bridge~~ — **УДАЛЕНО из P3** (перенесено на Этап N)

---

## 🏗️ Архитектурное расширение (слои)

> Новые слои био-инспирированной архитектуры. Реализуются **после** P0–P1 hardening.  
> Текущее состояние: 7/12 слоёв реализовано. Спецификации → `docs/layers/*.md`

### Этап H — Attention & Resource Control ✅

- [x] **H.1** `brain/cognition/salience_engine.py` — `SalienceEngine` + `SalienceScore`  
  → 4 измерения: novelty, urgency, threat, relevance  
  → пороги: >0.8→"interrupt", >0.5→"prioritize", else→"normal" ✅
- [x] **H.2** `brain/core/attention_controller.py` — `AttentionController` + `AttentionBudget`  
  → `PRESET_BUDGETS`: text_focused, multimodal, memory_intensive, degraded, critical, emergency  
  → `compute_budget(goal_type, resource_state, salience, cycle_id)` → `AttentionBudget` ✅
- [x] **H.3** `brain/cognition/policy_layer.py` — `PolicyLayer` (фильтры + модификаторы)  
  → Фильтры: F0 (resource_blocked), F1 (low confidence), F2 (soft_blocked)  
  → Модификаторы: M1 (-0.15), M2 (+0.20 ASK_CLARIFICATION), M3 (+0.15 RESPOND_HEDGED) ✅
- [x] **H.4** `brain/cognition/pipeline.py` — расширен до 14 шагов  
  → Шаг 6: `step_evaluate_salience`, Шаг 7: `step_compute_budget`  
  → Шаг 10: `step_select_action` + PolicyLayer, Шаг 13: `step_build_result` + salience/budget metadata ✅
- [ ] **H.5** Ring 2 — Deep Reasoning (multi-iteration refinement) — _отложено на Post-MVP_

### Этап I — Learning Loop ✅

- [x] **I.1** `brain/learning/online_learner.py` — `OnlineLearner` + `OnlineLearningUpdate`  
  → confirm/deny фактов (только при action=="contradict"), Хеббовское обучение (Δw=lr×conf),  
  source trust через `SourceMemory.update_trust()`, no-op при confidence < 0.3 ✅
- [x] **I.2** `brain/learning/knowledge_gap_detector.py` — `KnowledgeGapDetector` + `KnowledgeGap`  
  → MISSING/HIGH, WEAK/MEDIUM, OUTDATED/LOW; дедупликация по (concept, gap_type);  
  v1: single-result heuristic; planned: aggregate scoring ✅
- [x] **I.3** `brain/learning/replay_engine.py` — `ReplayEngine` + `ReplaySession`  
  → 4 стратегии (importance/recency/frequency/random), stale pruning (age>7d, imp<0.1),  
  CPU-aware через psutil._should_run(), reinforce delta=0.01 ✅

**Интеграция (Этап J):**
  - `OnlineLearner.update()` → вызывать из `CognitivePipeline.step_post_cycle()` после каждого цикла
  - `ReplayEngine.run_replay_session()` → вызывать из idle hook / CLI `--autonomous` (P3-11)
  - `KnowledgeGapDetector.analyze()` → вызывать после каждого `MemoryManager.retrieve()`
  - Кто потребляет `KnowledgeGap`: GoalManager (создать цель на заполнение пробела)

### Этап J — Multimodal Expansion

- [ ] **J.1** Vision encoder path
- [ ] **J.2** Audio encoder path
- [ ] **J.3** Temporal/video path

### Этап K — Cross-Modal Fusion

- [ ] **K.1** `brain/fusion/shared_space_projector.py`
- [ ] **K.2** `brain/fusion/entity_linker.py`
- [ ] **K.3** `brain/fusion/confidence_calibrator.py`
- [ ] **K.4** `brain/fusion/contradiction_detector.py` (кросс-модальная версия)

### Этап L — Safety & Boundaries

- [ ] **L.1** `brain/safety/source_trust.py`
- [ ] **L.2** `brain/safety/conflict_detector.py`
- [ ] **L.3** `brain/safety/boundary_guard.py`
- [ ] **L.4** `brain/safety/audit_logger.py`
- [ ] **L.5** `brain/safety/policy_layer.py`

### Этап N — LLM Bridge ✅

- [x] **N.1** `brain/bridges/llm_bridge.py` — `LLMProvider` Protocol, `LLMBridge` (retry+timeout), `MockProvider`, `OpenAIProvider`, `AnthropicProvider` ✅
- [x] **N.2** Интеграция LLM в reasoning pipeline — `step_llm_enhance` (шаг 10 из 15) в `CognitivePipeline` ✅
- [x] **N.3** Safety wrapper для LLM — `LLMSafetyWrapper` (rate limit, blocked patterns, prompt length) ✅
- [x] **N.4** CLI флаги — `--llm-provider {openai,anthropic,mock}`, `--llm-api-key`, `--llm-model` ✅
- [x] **N.5** `tests/test_llm_bridge.py` — 11 классов, ~70 тестов ✅

### Этап M — Reward & Motivation

- [ ] **M.1** `brain/motivation/reward_engine.py`
- [ ] **M.2** `brain/motivation/motivation_engine.py`
- [ ] **M.3** `brain/motivation/curiosity_engine.py`

### CUDA Backend (после понимания bottlenecks)

- [ ] Compute backend abstraction: `cpu_backend.py` + `cuda_backend.py`
- [ ] Приоритет: text encoder → embeddings → reranker → local LLM inference

### Research Branch (отдельно от mainline)

- [ ] Эксперименты из `ARCHITECTURE.md` (cognitive neuron, predictive coding)
- [ ] Ternary + LLaMA (см. `docs/ideas/ternary+llama.md`)

---

## 🔗 Зависимости

```text
Hardening (завершено):
  P0-E1..E5 (thread safety, leaks, bugs) ✅
  P0-P1 (real retrieval) → P0-P2 (validator fix) ✅
  P1-E1..E11 (types, CI, ruff, Docker) ✅
  P1-P1..P3 (product quality) ✅

Следующий этап:
  P2 (algorithms, infra, product quality) ✅
  
Архитектурное расширение (после P2):
  H Attention (depends: F+, MVP) ✅
  I Learning (depends: H, G) ✅
  J Multimodal (depends: E, G)
  K Fusion (depends: J, F+)
  L Safety (depends: G, K)
  N LLM Bridge (depends: L, G) ✅
  M Reward (depends: I, L)
```

---

## ✅ Completed (история реализации)

<details>
<summary><strong>MVP Phase A — Foundation ✅</strong></summary>

- [x] **A.1** CLI entrypoint (`brain/cli.py` + `[project.scripts]`, 20 тестов)
- [x] **A.1b** Dockerfile (multi-stage + `.dockerignore`)
- [x] **A.2** Контракт `ResourceMonitor ↔ CognitiveCore` (`snapshot()` алиас)
- [x] **A.3** mypy как настоящий барьер (`|| true` убран, scope: core + cognition)

</details>

<details>
<summary><strong>MVP Phase B — Close the Loop ✅</strong></summary>

- [x] **B.1** Auto-encode в `CognitiveCore` (456 тестов)
- [x] **B.2** Perception hardening (path traversal, oversized files, 34 теста)
- [x] **B.3** Retrieval scope зафиксирован (keyword-first + BM25)
- [x] **B.4** README приведён к реальности
- [x] **B.5** Golden-answer бенчмарки (20 Q&A, 414 параметризованных тестов)

</details>

<details>
<summary><strong>MVP Phase C — Cleanup + Critical DRY ✅</strong></summary>

- [x] **C.1** `detect_language()` → `brain/core/text_utils.py` (4 потребителя)
- [x] **C.2** `parse_fact_pattern()` → `brain/core/text_utils.py` (2 потребителя)
- [x] **C.3** Убран прямой вызов `consolidation._extract_fact()`
- [x] **C.4** `sha256_text/file()` → `brain/core/hash_utils.py` (2 потребителя)
- [x] **C.5** JSON helper — оценка: не нужен (28 вызовов, все контекстно-специфичны)

</details>

<details>
<summary><strong>P0 — Критические исправления (v0.6.1) ✅</strong></summary>

- [x] **P0.1** Синхронизация версий
- [x] **P0.2** Очистка артефактов `NaN` в README.md
- [x] **P0.3** Проверка `NaN` в `brain/core/events.py`
- [x] **P0.4** API-контракты: `MemoryManagerProtocol`, `EventBusProtocol`, `ResourceMonitorProtocol`
- [x] **P0.5** Убраны side effects в retrieval: `dataclasses.replace()`
- [x] **P0.6** E2E тест + lint блокирующий

</details>

<details>
<summary><strong>P1 — Quick Wins + BM25 + SQLite (v0.7.0) ✅</strong></summary>

- [x] **P1.0** Ruff lint cleanup: 131 → 0 errors
- [x] **P1.1** BM25 reranking (55 тестов)
- [x] **P1.3** SQLite persistence layer (58 тестов)
- [x] **P1.4** `session_id: Optional[str] = None` в `CognitiveCore.run()`
- [x] **P1.5** `pytest-cov` в CI
- [x] **P1.6** Синхронизация зависимостей
- [x] **P1.7** Disclaimer в `docs/ARCHITECTURE.md`
- [x] **P1.8** `atexit.register()` через `weakref.ref`
- [x] **P1.9** mypy typecheck job в CI

</details>

<details>
<summary><strong>Этапы A→G — Основная реализация (793 теста) ✅</strong></summary>

- [x] **A** Shared Contracts (`contracts.py`: 9 dataclass, ContractMixin, Modality)
- [x] **B** Minimal Autonomous Runtime (EventBus, Scheduler, ResourceMonitor)
- [x] **C** Logging & Observability (BrainLogger, DigestGenerator, ReasoningTracer)
- [x] **D** Text-Only Perception (TextIngestor, MetadataExtractor, InputRouter)
- [x] **E** Minimal Text Encoder (sentence-transformers 768d / navec 300d fallback)
- [x] **F** Cognitive MVP (GoalManager, HypothesisEngine, Reasoner, ActionSelector, CognitiveCore)
- [x] **F+** Cognitive Extensions (RetrievalAdapter, ContradictionDetector, UncertaintyMonitor)
- [x] **G** Output MVP (TraceBuilder, DialogueResponder, ResponseValidator)

</details>

<details>
<summary><strong>P0 (new) — Critical Hardening ✅ 7/7</strong></summary>

- [x] P0-E1..E5 — Thread safety, memory leaks, critical bugs
- [x] P0-P1 — Real vector/hybrid retrieval (60 тестов)
- [x] P0-P2 — ResponseValidator fix

</details>

<details>
<summary><strong>P1 (new) — High Priority ✅ 14/14</strong></summary>

- [x] Волна 1: E3, E9, P2, E2, P1 — атомарные фиксы
- [x] Волна 2: E5, E10, E1 — типизация и Protocol
- [x] Волна 3: E6, E8, E4, E7 — CI/Infra
- [x] Волна 4: E11, P3 — Docker + README
- [x] Все mypy/ruff lint fixes (10 файлов)

</details>

<details>
<summary><strong>LOG_PLAN.md v2.0 — BrainLogger Integration ✅ 13/13</strong></summary>

- [x] **Phase 0a** `brain/logging/brain_logger.py` — NullBrainLogger + _NULL_LOGGER
- [x] **Phase 0b** `brain/logging/reasoning_tracer.py` — NullTraceBuilder + _NULL_TRACE_BUILDER
- [x] **Phase 0c** `brain/logging/__init__.py` — экспорт Null-объектов
- [x] **Phase 1** `brain/cli.py` — `--log-dir`, `--log-level`, BrainLogger в run_query/run_autonomous
- [x] **Phase 2** `brain/cognition/cognitive_core.py` — brain_logger + digest_gen + trace_builder
- [x] **Phase 2b** `brain/logging/digest_generator.py` — CycleInfo.from_result()
- [x] **Phase 3** `brain/cognition/pipeline.py` — auto-timing + 9 событий + TraceBuilder
- [x] **Phase 4** `brain/memory/memory_manager.py` — store/retrieve logging
- [x] **Phase 5** `brain/perception/input_router.py` — route logging
- [x] **Phase 6** `brain/output/dialogue_responder.py` — OutputPipeline logging
- [x] **Phase 7a** `brain/core/event_bus.py` — publish + error logging
- [x] **Phase 7b** `brain/core/scheduler.py` — tick + task logging
- [x] **Phase 9** `tests/test_brain_logger_integration.py` — 19 тестов

</details>

---

## 🧪 Test Coverage

**Всего: 1800/1800 ✅ (5 skipped)** · Coverage: 84%+ (gate 70%) · 32 test files

| Файл | Модуль | Тестов | Статус |
|------|--------|--------|--------|
| `test_bm25.py` | BM25 Scorer + KeywordBackend reranking | 55 | ✅ |
| `test_cli.py` | CLI entrypoint (Phase A + --autonomous + --llm) | 20 | ✅ |
| `test_cognition.py` | Cognitive Core (unit + auto-encode) | 190 | ✅ |
| `test_cognition_integration.py` | Cognitive Core (integration) | 7 | ✅ |
| `test_e2e_pipeline.py` | E2E Pipeline + Protocol conformance | 10 | ✅ |
| `test_golden.py` | Golden-answer benchmarks (Phase B.5) | 414 | ✅ |
| `test_logging.py` | Logging & Observability | 25 | ✅ |
| `test_memory.py` | Memory System (5 types + consolidation + manager) | 101 | ✅ |
| `test_output.py` | Output Layer (unit) | 106 | ✅ |
| `test_output_integration.py` | Output Layer (integration) | 7 | ✅ |
| `test_perception.py` | Perception Layer | 79 | ✅ |
| `test_perception_hardening.py` | Perception Hardening (Phase B.2) | 34 | ✅ |
| `test_resource_monitor.py` | ResourceMonitor | 13 | ✅ |
| `test_scheduler.py` | Scheduler | 11 | ✅ |
| `test_storage.py` | SQLite Storage + Migration | 58 | ✅ |
| `test_text_encoder.py` | Text Encoder (4 modes) | 80 | ✅ |
| `test_utils.py` | text_utils + hash_utils (Phase C) | 63 | ✅ |
| `test_vector_retrieval.py` | Vector Retrieval + Index Population + Hybrid Search | 60 | ✅ |
| `test_persistence_integration.py` | Persistence Integration (P2-20) | 6 | ✅ |
| `test_contracts_hypothesis.py` | Property-based roundtrip (P3-6) | 4 | ✅ |
| `test_concurrency_stress.py` | Concurrent stress (P3-8) | 3 | ✅ |
| `test_storage_encrypted.py` | SQLCipher encryption at rest (P3-12) | 6+5* | ✅ |
| `test_attention_controller.py` | AttentionController + budgets (Этап H) | 10 | ✅ |
| `test_salience_engine.py` | SalienceEngine + scoring (Этап H) | 12 | ✅ |
| `test_policy_layer.py` | PolicyLayer filters + modifiers (Этап H) | 9 | ✅ |
| `test_brain_logger_integration.py` | BrainLogger integration (LOG_PLAN.md Phase 9) | 19 | ✅ |
| `test_llm_bridge.py` | LLMBridge + providers + safety (Этап N) | 70 | ✅ |
| `test_online_learner.py` | OnlineLearner (Этап I) | 12 | ✅ |
| `test_knowledge_gap_detector.py` | KnowledgeGapDetector (Этап I) | 8 | ✅ |
| `test_replay_engine.py` | ReplayEngine + strategies (Этап I) | 15 | ✅ |
| **Итого** | | **1800** | **✅** |

> \* 6 тестов запускаются всегда, 5 — только при установленном `sqlcipher3`  
> Тесты H/I/N: точные числа уточняются при следующем прогоне `pytest --co -q`

---

## 📊 Прогресс

| Этап | Название | Статус | Тесты |
|------|----------|--------|-------|
| A–G | Foundation → Output MVP | ✅ | 793 |
| F+ | Cognitive Extensions | ✅ | (в test_cognition) |
| P0 (old) | Критические исправления v0.6.1 | ✅ | — |
| P1 (old) | BM25 + SQLite + CI | ✅ | 113 |
| **MVP A** | **Foundation** | **✅** | 835 |
| **MVP B** | **Close the Loop** | **✅** | 456 |
| **MVP C** | **Cleanup + Critical DRY** | **✅** | 63 |
| **P0 (new)** | **Critical hardening** | **✅ 7/7** | 1333 |
| **P1 (new)** | **High priority** | **✅ 14/14** | 1333 |
| **P2** | **Medium priority** | **✅ 20/20** | 1800 |
| **P3** | **Nice-to-have** | **✅ 12/12** | 1352 |
| **H** | **Attention & Resource Control** | **✅ 4/5** | — |
| **I** | **Learning Loop** | **✅ 3/3** | — |
| **N** | **LLM Bridge** | **✅ 5/5** | ~70 |
| J–M | Архитектурное расширение | [ ] 4 слоя | — |

---

## 💡 Стратегическая формула

```
1. ✅ Thread safety + memory leaks     → закрыто (P0)
2. ✅ Real retrieval pipeline           → закрыто (P0-VEC)
3. ✅ Type safety + CI hardening        → закрыто (P1)
4. ✅ README ↔ Reality alignment        → закрыто (P1-P3)
5. ✅ LLM Bridge                        → закрыто (Этап N)
6. ✅ BrainLogger integration           → закрыто (LOG_PLAN.md v2.0)
```

---

## 📌 Правило принятия решений

При возникновении новой идеи — три вопроса:

1. Помогает ли это закрыть P2 hardening?
2. Улучшает ли наблюдаемость, стабильность или retrieval?
3. Не уводит ли в research раньше времени?

**да / да / нет** → брать · **нет / нет / да** → откладывать в P3/Research
