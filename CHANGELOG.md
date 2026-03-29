# Changelog

Все значимые изменения в проекте документируются в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/),
проект следует [Semantic Versioning](https://semver.org/lang/ru/).

---

## [Unreleased]

### Добавлено
- **P3-1** `CHANGELOG.md` — история изменений в формате Keep a Changelog
- **P3-2** `CONTRIBUTING.md` — гайд для контрибьюторов
- **P3-4** ADR (Architecture Decision Records) — 7 ADR + README в `docs/adr/`
- **P3-5** Убран Python 3.14 из classifiers в `pyproject.toml`
- **P3-9** `ThreadPoolEventBus` — async dispatch через `ThreadPoolExecutor` (`brain/core/event_bus.py`)
  - `publish()` → non-blocking submit, `publish_sync()` → sync fallback
  - `wait_all(timeout)`, `shutdown(wait)`, расширенный `status()`
- **P3-10** `CognitivePipeline` — явный 12-шаговый пайплайн вместо god-method (`brain/cognition/pipeline.py`)
  - `CognitivePipelineContext` dataclass для передачи состояния между шагами
  - `CognitiveCore.run()` делегирует `self._pipeline.run()`
- **P3-11** `--autonomous` режим в CLI (`brain/cli.py`)
  - `--autonomous` + `--ticks N` аргументы
  - Handlers: `cognitive_cycle` (NORMAL) + `consolidate_memory` (LOW)
  - 5 предустановленных запросов + адаптивный интервал тика
- **P3-6** Property-based тесты (Hypothesis) для ContractMixin roundtrip (`tests/test_contracts_hypothesis.py`)
- **P3-8** Concurrent stress tests для EventBus + Scheduler (`tests/test_concurrency_stress.py`)
- **P3-3** API reference (mkdocs + mkdocstrings)
  - `mkdocs.yml` — конфиг с Material theme, навигацией, поиском на русском
  - `docs/index.md` — главная страница с метриками и архитектурой
  - `docs/api/` — 7 страниц: cognition, memory, perception, core, output, logging, encoders
  - `pyproject.toml`: группа `apidocs` (mkdocs, mkdocs-material, mkdocstrings[python])
- **P3-12** SQLCipher для encryption at rest
  - `MemoryDatabase(encryption_key=...)` — опциональное шифрование через sqlcipher3
  - Graceful fallback: без ключа → sqlite3, с ключом → sqlcipher3
  - `is_encrypted` property + поле `encrypted` в `status()`
  - `pyproject.toml`: группа `encrypted` (sqlcipher3>=0.5)
  - `tests/test_storage_encrypted.py` — 11 тестов (6 без sqlcipher3, 5 с sqlcipher3)
- `hypothesis>=6.112.0` и `mutmut>=2.4.4` в dev-зависимости
- **Этап H** Attention & Resource Control
  - `brain/cognition/salience_engine.py` — `SalienceEngine` + `SalienceScore` (novelty/urgency/threat/relevance)
  - `brain/core/attention_controller.py` — `AttentionController` + `AttentionBudget` + `PRESET_BUDGETS` (6 пресетов)
  - `brain/cognition/policy_layer.py` — `PolicyLayer` (3 фильтра + 3 модификатора)
  - `brain/cognition/pipeline.py` расширен до 14 шагов: `step_evaluate_salience` (шаг 6), `step_compute_budget` (шаг 7), PolicyLayer в `step_select_action`, salience/budget metadata в `step_build_result`
  - Экспорт в `brain/cognition/__init__.py` и `brain/core/__init__.py`
- **Этап N** LLM Bridge — опциональная интеграция внешних LLM
  - `brain/bridges/llm_bridge.py` — `LLMProvider` Protocol, `LLMRequest`, `LLMResponse`, `LLMBridge` (retry + timeout), `OpenAIProvider`, `AnthropicProvider`
  - `brain/bridges/safety_wrapper.py` — `LLMSafetyWrapper` (rate limit, content filter, max_tokens guard)
  - `brain/bridges/__init__.py` — публичный API модуля bridges
  - `brain/cognition/pipeline.py` расширен до 15 шагов: `step_llm_enhance` (шаг 10) — no-op если LLM не настроен, llm metadata в `step_build_result`
  - `brain/cognition/cognitive_core.py` — параметр `llm_provider: Optional[LLMProvider]` в `__init__`, передаётся в `CognitivePipeline`
  - `brain/cli.py` — флаги `--llm-provider`, `--llm-api-key`, `--llm-model`; `_build_llm_provider()` с graceful fallback
  - `pyproject.toml` — optional deps: `openai` (openai>=1.0), `anthropic` (anthropic>=0.20)
  - Backward compatible: без `llm_provider` поведение идентично предыдущей версии

---

## [0.7.0] — 2025-07-14

### Добавлено
- **P2-19** Sentence-aware chunking через `razdel.sentenize()` с regex fallback
- **P2-18** `InputType` enum (FILE / TEXT / AUTO) в `InputRouter`
- **P2-17** `_extract_strings_from_json()` пропускает числа/bool/None — только строки
- **P2-20** Integration test «сохранил → перезапустил → нашёл» (`test_persistence_integration.py`, 6 тестов)
- **P2-12** Docker build job в CI (build only, без push)
- **P2-13** Dependabot для security updates (pip + github-actions, weekly)
- **P2-14** Bandit SAST в CI (`bandit -r brain/ -c pyproject.toml`)
- **P2-15** Codecov интеграция (`codecov/codecov-action@v4`)
- **P2-16** CI badges в README (CI, Codecov, Python 3.11+, Apache-2.0)
- **P2-10** Единая шкала порогов уверенности через `PolicyConstraints.hedge_threshold`
- **P2-7** `_handler_name()` helper в `EventBus` — безопасное имя для lambda/partial
- **P2-3** `batch_remove()` в `WorkingMemory` + использование в `ConsolidationEngine`
- **P2-1** BFS в `SemanticMemory`: `list.pop(0)` → `collections.deque`

### Исправлено
- **P2-6** `ZeroDivisionError` при `autosave_every == 0` — guard в 4 модулях
- **P2-5** UUID4 обрезался до 12 hex (48 бит) → теперь полный `uuid4().hex` (128 бит)
- **P2-8** `apply_decay()` обновлял `updated_ts` всех узлов → только изменённых
- **P2-9** Ротация логов только для `brain.jsonl` → теперь все категорийные файлы
- **P2-4** `_evict_least_important()`: `sorted()` → `min()` для O(n) вместо O(n log n)
- **P2-2** `retrieve_by_concept()`: O(n²) → O(1) через `seen: set[str]`
- **P2-11** Задокументирован round-trip контракт `to_dict()/from_dict()` в `SemanticNode` и `Relation`

---

## [0.6.2] — 2025-06 (P0 new + P1 new)

### Добавлено
- **P0-VEC** `_build_vector_index()` при инициализации `CognitiveCore` — реальная индексация корпуса
- **P0-VEC** Инкрементальная индексация при LEARN-событии
- **P0-VEC** `remove_from_vector_index()` при `deny_fact()` / `delete_fact()`
- **P0-VEC** Персистенция embedding в `to_dict()` / `from_dict()` для `SemanticNode` и `Episode`
- **P1-E11** Docker multi-stage build + non-root user (`brain:brain`)
- **P1-E6** Coverage gate в CI (`--cov-fail-under=70`)
- **P1-E8** Расширены Ruff rules: B, SIM, C4, RET, PIE
- **P1-E4** mypy scope расширен до всех модулей `brain/` — 0 errors
- **P1-E5** Protocol-типы вместо `Any` в `Reasoner` и `CognitiveCore`
- **P1-E1** `ContractMixin.from_dict()` — рекурсивный с вложенными dataclass/Enum
- **P1-P3** README актуализирован: capability matrix, реальные метрики
- **P1-P1** SQLite — default backend (вместо JSON)
- 60 тестов для vector/hybrid retrieval (`test_vector_retrieval.py`)

### Исправлено
- **P0-E1** Thread safety — `threading.RLock()` в 6 модулях памяти + `EventBus`
- **P0-E2** Race condition в `ResourceMonitor._apply_state()`
- **P0-E3** Утечка памяти в `BrainLogger` — TTL/LRU через `BoundedIndex`
- **P0-E4** 100 МБ RAM spike при ротации логов → `shutil.copyfileobj(64KB chunks)`
- **P0-E5** `importance ≠ confidence` — разделены параметры
- **P0-P2** `ResponseValidator` — severity снижен до `warning`, `is_valid=True` после автокоррекции
- **P1-E3** `EventBusProtocol.publish()` — сигнатура синхронизирована с реальным `EventBus`
- **P1-E9** `copy.deepcopy` → `dataclasses.replace` в `ContradictionDetector`
- **P1-E2** `GoalManager._remove_from_queue()` — lazy-delete pattern
- **P1-P2** Dedup хэширует полный текст (убран срез `[:2000]`)
- **BUG** `storage.py`: `begin()` — идемпотентная защита от вложенных транзакций

---

## [0.6.1] — 2025-05 (P0 old)

### Добавлено
- `MemoryManagerProtocol`, `EventBusProtocol`, `ResourceMonitorProtocol` — API-контракты
- E2E тест + lint как blocking check в CI
- `session_id: Optional[str] = None` в `CognitiveCore.run()`

### Исправлено
- Синхронизация версий между `pyproject.toml` и `brain/__init__.py`
- Очистка артефактов `NaN` в `README.md`
- Side effects в retrieval устранены через `dataclasses.replace()`

---

## [0.7.0-beta] — 2025-04 (P1 old — BM25 + SQLite)

### Добавлено
- **BM25 reranking** в `KeywordRetrievalBackend` (55 тестов)
- **SQLite persistence layer** — `MemoryDatabase` с WAL mode (58 тестов)
- `pytest-cov` в CI
- `mypy` typecheck job в CI
- `atexit.register()` через `weakref.ref` для безопасного shutdown
- Disclaimer в `docs/ARCHITECTURE.md`

### Исправлено
- Ruff lint: 131 → 0 errors

---

## [0.5.0] — 2025-03 (MVP A–G)

### Добавлено
- **Этап A** Shared Contracts (`contracts.py`: 9 dataclass, `ContractMixin`, `Modality`)
- **Этап B** Minimal Autonomous Runtime (`EventBus`, `Scheduler`, `ResourceMonitor`)
- **Этап C** Logging & Observability (`BrainLogger`, `DigestGenerator`, `ReasoningTracer`)
- **Этап D** Text-Only Perception (`TextIngestor`, `MetadataExtractor`, `InputRouter`)
- **Этап E** Minimal Text Encoder (sentence-transformers 768d / navec 300d fallback)
- **Этап F** Cognitive MVP (`GoalManager`, `HypothesisEngine`, `Reasoner`, `ActionSelector`, `CognitiveCore`)
- **Этап F+** Cognitive Extensions (`RetrievalAdapter`, `ContradictionDetector`, `UncertaintyMonitor`)
- **Этап G** Output MVP (`TraceBuilder`, `DialogueResponder`, `ResponseValidator`)
- **MVP A** CLI entrypoint (`brain/cli.py`, `[project.scripts]`, 20 тестов)
- **MVP A** Dockerfile (multi-stage + `.dockerignore`)
- **MVP B** Auto-encode в `CognitiveCore` (456 тестов)
- **MVP B** Perception hardening (path traversal, oversized files, 34 теста)
- **MVP B** Golden-answer benchmarks (20 Q&A, 414 параметризованных тестов)
- **MVP C** DRY: `detect_language()`, `parse_fact_pattern()`, `sha256_text/file()` → `brain/core/text_utils.py`, `brain/core/hash_utils.py`

---

## Легенда типов изменений

| Тип | Описание |
|-----|----------|
| **Добавлено** | Новая функциональность |
| **Изменено** | Изменения в существующей функциональности |
| **Устарело** | Функциональность, которая будет удалена в будущем |
| **Удалено** | Удалённая функциональность |
| **Исправлено** | Исправления ошибок |
| **Безопасность** | Исправления уязвимостей |

[Unreleased]: https://github.com/whatisdantes/cognitive-core/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/whatisdantes/cognitive-core/compare/v0.6.2...v0.7.0
[0.6.2]: https://github.com/whatisdantes/cognitive-core/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/whatisdantes/cognitive-core/compare/v0.5.0...v0.6.1
[0.5.0]: https://github.com/whatisdantes/cognitive-core/releases/tag/v0.5.0
