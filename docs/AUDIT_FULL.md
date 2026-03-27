# 🔍 Полный аудит проекта cognitive-core

> ⚠️ **ИСТОРИЧЕСКИЙ ДОКУМЕНТ** — снимок состояния проекта на момент 835 тестов (16 test files).  
> С момента написания завершены **Phase B** (golden benchmarks — 414 тестов, perception hardening) и **Phase C** (DRY refactoring).  
> Текущее состояние: **1312 тестов**, 19 test files, ruff clean.  
> **Исправлено в Phase C:** DRY violations #1–#5 (detect_language → text_utils.py, sha256 → hash_utils.py, extract_fact → parse_fact_pattern, encapsulation violation в MemoryManager).  
> **Исправлено в Phase B:** golden-answer benchmarks (B.5 — 414 тестов).  
> Актуальный roadmap: [`docs/TODO.md`](TODO.md)

> **Дата:** 2025-07-14  
> **Версия:** 0.7.0  
> **Тесты:** 835/835 ✅ (14.99s)  
> **Аудитор:** BLACKBOXAI

---

## 📋 Содержание

1. [Общая оценка](#1-общая-оценка)
2. [Архитектура](#2-архитектура)
3. [Модуль-по-модулю](#3-модуль-по-модулю)
4. [Качество кода](#4-качество-кода)
5. [Дублирование (DRY)](#5-дублирование-dry)
6. [Безопасность](#6-безопасность)
7. [Тестирование](#7-тестирование)
8. [CI/CD и DevOps](#8-cicd-и-devops)
9. [Документация](#9-документация)
10. [Производительность](#10-производительность)
11. [Рекомендации по приоритету](#11-рекомендации-по-приоритету)

---

## 1. Общая оценка

| Критерий | Оценка | Комментарий |
|----------|--------|-------------|
| **Архитектура** | ⭐⭐⭐⭐☆ | Чистая слоистая архитектура, хорошее разделение ответственности. Биологические аналоги уместны. |
| **Качество кода** | ⭐⭐⭐⭐☆ | Хорошие docstrings, типизация, ContractMixin. Есть DRY-нарушения. |
| **Тестирование** | ⭐⭐⭐⭐⭐ | 835 тестов, 100% pass rate, хорошее покрытие всех модулей. |
| **Безопасность** | ⭐⭐⭐☆☆ | Perception hardening сделан (B.2), но safety layer пуст. |
| **Документация** | ⭐⭐⭐⭐☆ | Отличные docstrings и .md файлы. README требует финальной вычитки. |
| **DevOps** | ⭐⭐⭐⭐☆ | CI на 3 версиях Python, Dockerfile, mypy blocking. |
| **Производительность** | ⭐⭐⭐☆☆ | CPU-only дизайн корректен, но нет персистентного ANN-индекса. |

**Итого: 4.0/5 — зрелый MVP с чёткой архитектурой и отличным тестовым покрытием.**

---

## 2. Архитектура

### 2.1 Слоистая структура (11 слоёв)

```
┌─────────────────────────────────────────────────────┐
│  Perception (Таламус)     — text_ingestor, router   │ ✅ Реализован
│  Encoders (Сенсорная кора) — TextEncoder             │ ✅ Реализован
│  Fusion (Ассоциативная кора)                         │ ⬜ Stub (Stage K)
│  Memory (Гиппокамп)       — 5 видов + consolidation  │ ✅ Реализован
│  Cognition (Префронтальная кора) — CognitiveCore     │ ✅ Реализован
│  Learning (Обучение)                                 │ ⬜ Stub (Stage I)
│  Output (Зона Брока)      — trace + validate + respond│ ✅ Реализован
│  Core (Инфраструктура)    — EventBus, Scheduler, RM  │ ✅ Реализован
│  Logging (Наблюдаемость)  — BrainLogger, TraceBuilder│ ✅ Реализован
│  Safety (Безопасность)                               │ ⬜ Stub (Stage L)
│  Data (Хранение)          — SQLite + JSON             │ ✅ Реализован
└─────────────────────────────────────────────────────┘
```

### 2.2 Pipeline (основной поток данных)

```
Query → CLI → EventBus → MemoryManager.start()
  → CognitiveCore.run(query)
    → Auto-encode (B.1) → Resources → RetrievalQuery
    → Goal → IndexVector → Reasoning → ActionSelect
    → ExecuteAction → CompleteGoal → BuildResult → PublishEvent
  → CognitiveResult
  → OutputPipeline.process(result)
    → TraceBuilder → Validator → Responder
  → BrainOutput (text + confidence + trace_id + digest)
```

### 2.3 Сильные стороны архитектуры

- **Protocol-based DI**: `MemoryManagerProtocol`, `EventBusProtocol`, `ResourceMonitorProtocol` — чистая инъекция зависимостей через structural subtyping
- **ContractMixin**: единообразная сериализация `to_dict()`/`from_dict()` для всех dataclass
- **EventBus**: синхронная pub/sub шина с wildcard, error isolation, статистикой
- **Graceful degradation**: 4 уровня (NORMAL → DEGRADED → CRITICAL → EMERGENCY) с гистерезисом
- **Trace chain**: полная прослеживаемость решений (input → memory → hypotheses → decision → output)

### 2.4 Архитектурные риски

| Риск | Серьёзность | Описание |
|------|-------------|----------|
| **Синхронный EventBus** | 🟡 Средний | Все handlers вызываются синхронно в одном потоке. При росте числа подписчиков может стать bottleneck. |
| **In-memory vector index** | 🟡 Средний | `VectorRetrievalBackend` хранит всё в RAM dict. Не масштабируется > 100K записей. |
| **Нет TTL/eviction для кэша** | 🟡 Средний | `TextEncoder._cache` растёт бесконечно (нет LRU/TTL). |
| **Один Reasoner loop** | 🟢 Низкий | Ring 1 only. Ring 2 (deep reasoning) запланирован, но не реализован. |
| **Fusion/Learning/Safety — stubs** | 🟢 Низкий | Ожидаемо для MVP. Чётко задокументировано. |

---

## 3. Модуль-по-модулю

### 3.1 `brain/core/` — Инфраструктурное ядро

| Файл | LOC | Оценка | Замечания |
|------|-----|--------|-----------|
| `contracts.py` | ~250 | ✅ Отлично | 15 dataclass + 3 Protocol + ContractMixin. Чистый "язык" между слоями. |
| `events.py` | ~200 | ✅ Отлично | 6 типов событий + EventFactory. Хорошая сериализация. |
| `event_bus.py` | ~170 | ✅ Хорошо | Wildcard, error isolation, BusStats. Нет async — ок для MVP. |
| `scheduler.py` | ~350 | ✅ Хорошо | Приоритетная очередь, адаптивный tick, graceful shutdown. |
| `resource_monitor.py` | ~320 | ✅ Хорошо | Daemon thread, гистерезис, inject_state для тестов, `snapshot()` alias. |

**Замечания:**
- `ResourceMonitor.check()` и `snapshot()` — дублирование (snapshot = alias). Это осознанное решение для Protocol conformance (A.2). ✅
- `Scheduler.run()` использует `time.sleep()` — блокирующий. Для MVP это нормально.

### 3.2 `brain/perception/` — Слой восприятия

| Файл | LOC | Оценка | Замечания |
|------|-----|--------|-----------|
| `text_ingestor.py` | ~300 | ✅ Хорошо | txt/md/pdf/docx/json/csv. Validator guards (B.2). |
| `metadata_extractor.py` | ~150 | ✅ Хорошо | source/timestamp/quality/language extraction. |
| `input_router.py` | ~200 | ✅ Хорошо | Маршрутизация text/file → PerceptEvent. Validator guards. |
| `validators.py` | ~130 | ✅ Хорошо | Path traversal, null bytes, symlink, file size. (B.2) |

**Замечания:**
- `_sha256()` в `input_router.py` дублирует `_sha256()` в `text_encoder.py` → **DRY violation** (Phase C target)
- `detect_language()` в `metadata_extractor.py` дублирует `_detect_language()` в `text_encoder.py` → **DRY violation**

### 3.3 `brain/encoders/` — Кодировщики

| Файл | LOC | Оценка | Замечания |
|------|-----|--------|-----------|
| `text_encoder.py` | ~500 | ✅ Хорошо | Primary (sentence-transformers 768d) → Fallback (navec 300d) → Degraded (zero). SHA256 cache, batch encode. |

**Замечания:**
- Хорошая graceful degradation (primary → fallback → failed)
- `_cache: Dict[str, np.ndarray]` — **нет LRU/TTL eviction**. При длительной работе может занять значительную RAM.
- `_extract_keywords()` — единственная копия, но использует `from collections import Counter` внутри функции (minor: лучше на уровне модуля)
- `_STOP_WORDS` — хардкод ru+en. Для MVP достаточно.

### 3.4 `brain/memory/` — Система памяти

| Файл | LOC | Оценка | Замечания |
|------|-----|--------|-----------|
| `memory_manager.py` | ~350 | ✅ Хорошо | Единый фасад для 5 видов памяти. SQLite/JSON dual backend. |
| `working_memory.py` | ~200 | ✅ Хорошо | Ring buffer с protected items, RAM-aware max_size. |
| `semantic_memory.py` | ~300 | ✅ Хорошо | Concept → description + relations + confidence. BM25 search. |
| `episodic_memory.py` | ~300 | ✅ Хорошо | Episodes с modal evidence, decay, protected. |
| `source_memory.py` | ~200 | ✅ Хорошо | Trust scores, fact counting, reliability tracking. |
| `procedural_memory.py` | ~200 | ✅ Хорошо | Procedures с success rate tracking. |
| `consolidation_engine.py` | ~250 | ✅ Хорошо | Background thread, working → episodic → semantic transfer. |
| `storage.py` | ~200 | ✅ Хорошо | SQLite backend с транзакциями. |

**Замечания:**
- `MemoryManager.store()` вызывает `consolidation._extract_fact()` напрямую (private method access) → **encapsulation violation**
- `_extract_fact()` дублируется в `cognitive_core.py` и `consolidation_engine.py` → **DRY violation**
- SQLite backend с `begin()`/`commit()`/`rollback()` — хорошая транзакционность
- `auto` backend selection по наличию `memory.db` — разумная эвристика

### 3.5 `brain/cognition/` — Когнитивное ядро

| Файл | LOC | Оценка | Замечания |
|------|-----|--------|-----------|
| `cognitive_core.py` | ~400 | ✅ Хорошо | 12-step orchestrator. Auto-encode (B.1), hybrid retrieval bridge. |
| `context.py` | ~250 | ✅ Отлично | CognitiveOutcome, EvidencePack, PolicyConstraints, GoalTypeLimits. |
| `goal_manager.py` | ~200 | ✅ Хорошо | Goal lifecycle (push → complete/fail), `__len__()`. |
| `planner.py` | ~200 | ✅ Хорошо | Stop conditions, replan strategies. |
| `hypothesis_engine.py` | ~250 | ✅ Хорошо | 4 strategies (direct, composite, negation, analogy). |
| `reasoner.py` | ~350 | ✅ Хорошо | Ring 1 loop: retrieve → contradict → hypothesize → score → select. |
| `action_selector.py` | ~200 | ✅ Хорошо | 5 ActionTypes (RESPOND_DIRECT/HEDGED/ASK/REFUSE/LEARN). |
| `retrieval_adapter.py` | ~700 | ✅ Хорошо | BM25Scorer + Keyword + Vector + Hybrid (RRF merge). |
| `contradiction_detector.py` | ~150 | ✅ Хорошо | Negation, numeric, temporal contradictions. |
| `uncertainty_monitor.py` | ~100 | ✅ Хорошо | Confidence trend tracking, stagnation detection. |

**Замечания:**
- `CognitiveCore.__init__()` — 10 компонентов инициализируются в конструкторе. Сложность управляема, но на грани.
- `_detect_goal_type()` — эвристика на маркерах. Для MVP достаточно, но хрупкая.
- `retrieval_adapter.py` — самый большой файл в cognition (~700 LOC). Содержит 4 класса (BM25Scorer, Keyword, Vector, Hybrid backends) + RetrievalAdapter. Можно разбить на подмодули.
- `BM25Scorer` — чистая Python реализация, корректная формула Robertson/Sparck-Jones.
- `HybridRetrievalBackend` — RRF merge с настраиваемыми весами (0.4 keyword / 0.6 vector). Хорошо.

### 3.6 `brain/output/` — Выходной слой

| Файл | LOC | Оценка | Замечания |
|------|-----|--------|-----------|
| `trace_builder.py` | ~150 | ✅ Хорошо | ExplainabilityTrace, OutputTraceBuilder. 5 uncertainty levels. |
| `response_validator.py` | ~200 | ✅ Хорошо | Empty/hedge/length/language checks. Fallback responses. |
| `dialogue_responder.py` | ~300 | ✅ Хорошо | Template-based rendering по ActionType. 5 confidence bands. |

**Замечания:**
- `DialogueResponder._detect_language()` и `ResponseValidator._detect_language()` — **два разных метода с одинаковым именем**, но разной логикой. Оба определяют язык из `CognitiveResult`, но по-разному. → **DRY violation + потенциальная несогласованность**
- `OutputPipeline` — чистый orchestrator (trace → validate → respond). Хорошо.
- TODO: LLM Bridge (Stage H+) — правильно задокументирован.

### 3.7 `brain/logging/` — Наблюдаемость

| Файл | LOC | Оценка | Замечания |
|------|-----|--------|-----------|
| `brain_logger.py` | ~300 | ✅ Хорошо | JSONL logging, rotation, structured events. |
| `reasoning_tracer.py` | ~300 | ✅ Хорошо | TraceBuilder с thread-safe accumulator, human-readable format. |
| `digest_generator.py` | ~100 | ✅ Хорошо | Digest generation для BrainOutput. |

**Замечания:**
- `TraceBuilder` в `reasoning_tracer.py` и `OutputTraceBuilder` в `output/trace_builder.py` — **два разных TraceBuilder'а** с разными целями. Naming может путать. Рекомендация: переименовать один из них (например `ReasoningTraceBuilder`).
- `_TraceAccumulator.build()` — memory_refs объединяются с input_refs через `[memory]` prefix в note. Это workaround для отсутствия `memory_refs` в `TraceChain`. → **Архитектурный долг** (добавить `memory_refs` в `TraceChain`).

### 3.8 Stubs: `brain/fusion/`, `brain/learning/`, `brain/safety/`

Все три модуля — пустые `__init__.py` с подробными TODO-комментариями. Это корректно для текущей стадии MVP. Зависимости и этапы реализации чётко задокументированы.

---

## 4. Качество кода

### 4.1 Сильные стороны

- ✅ **Типизация**: `from __future__ import annotations`, Protocol, Optional, List, Dict повсеместно
- ✅ **Docstrings**: Каждый класс и публичный метод имеет docstring (русский + английский)
- ✅ **ContractMixin**: Единообразная сериализация для всех dataclass
- ✅ **Logging**: `logging.getLogger(__name__)` в каждом модуле
- ✅ **Error isolation**: `except Exception` с logging, не прерывает основной поток
- ✅ **Immutable updates**: `dataclasses.replace()` в retrieval_adapter (copy-on-write)

### 4.2 Проблемы

| # | Проблема | Серьёзность | Файлы |
|---|----------|-------------|-------|
| 1 | `_detect_language()` дублируется 4 раза | 🔴 Высокая | text_encoder, metadata_extractor, dialogue_responder, response_validator |
| 2 | `_sha256()` дублируется 2 раза | 🟡 Средняя | input_router, text_encoder |
| 3 | `_extract_fact()` дублируется 2 раза | 🟡 Средняя | cognitive_core, consolidation_engine |
| 4 | `TextEncoder._cache` без LRU/TTL | 🟡 Средняя | text_encoder |
| 5 | `MemoryManager.store()` вызывает `consolidation._extract_fact()` | 🟡 Средняя | memory_manager |
| 6 | `retrieval_adapter.py` — 700 LOC, 4 класса | 🟢 Низкая | retrieval_adapter |
| 7 | `import Counter` внутри функции | 🟢 Низкая | text_encoder |
| 8 | Два TraceBuilder'а с похожими именами | 🟢 Низкая | reasoning_tracer, output/trace_builder |

---

## 5. Дублирование (DRY)

### 5.1 Критические дубликаты (Phase C targets)

#### `detect_language()` — 4 копии

| Файл | Сигнатура | Логика |
|------|-----------|--------|
| `brain/encoders/text_encoder.py` | `_detect_language(text: str) → str` | Кириллица/латиница ratio → ru/en/mixed/unknown |
| `brain/perception/metadata_extractor.py` | `detect_language(text: str) → str` | Аналогичная, но может отличаться в деталях |
| `brain/output/dialogue_responder.py` | `_detect_language(result: CognitiveResult) → str` | Из metadata или goal text |
| `brain/output/response_validator.py` | `_detect_language(result: CognitiveResult) → str` | Из metadata |

**Рекомендация:** Вынести в `brain/core/utils.py`:
```python
def detect_language(text: str) -> str: ...  # базовая (text → ru/en/mixed/unknown)
def detect_language_from_result(result: CognitiveResult) -> str: ...  # из metadata
```

#### `_sha256()` — 2 копии

| Файл | Сигнатура |
|------|-----------|
| `brain/perception/input_router.py` | `_sha256(text: str) → str` (первые 16 символов) |
| `brain/encoders/text_encoder.py` | `_sha256(text: str) → str` (полный hex) |

**Внимание:** Разная длина возврата! input_router возвращает `[:16]`, text_encoder — полный. Нужна единая функция с параметром `truncate`.

#### `_extract_fact()` — 2 копии

| Файл | Логика |
|------|--------|
| `brain/cognition/cognitive_core.py` | Убирает маркеры "запомни:", "сохрани:" и т.д. |
| `brain/memory/consolidation_engine.py` | Извлекает concept:description из текста |

**Внимание:** Разная логика! Это не чистый дубликат, а два разных алгоритма с одинаковым именем. Рекомендация: переименовать один (`strip_command_markers` vs `extract_concept_description`).

---

## 6. Безопасность

### 6.1 Реализовано ✅

- **Path traversal protection** (B.2): `validators.py` — null bytes, `..`, symlink escape, system dirs
- **File size limits** (B.2): `MAX_FILE_SIZE_MB = 50.0`
- **Validator guards** в `text_ingestor.py` и `input_router.py`
- **Error isolation**: `except Exception` с logging, не прерывает pipeline
- **No eval/exec**: Нигде в коде нет `eval()`, `exec()`, `__import__()`

### 6.2 Не реализовано ⬜

- **Safety layer** (`brain/safety/`): Полностью stub. Нет:
  - Source trust enforcement (SourceTrust)
  - Conflict detection между источниками (ConflictDetector)
  - Boundary guards (запрещённые темы, лимиты)
  - Audit logging для high-risk decisions
- **Input sanitization**: Текстовый ввод не проверяется на injection patterns
- **Rate limiting**: Нет ограничений на частоту запросов через CLI
- **Memory limits**: `TextEncoder._cache` растёт бесконечно

### 6.3 Рекомендации

1. **P1**: Добавить LRU-кэш в TextEncoder (maxsize=10000)
2. **P2**: Реализовать базовый BoundaryGuard (запрещённые паттерны)
3. **P3**: Реализовать AuditLogger для LEARN actions

---

## 7. Тестирование

### 7.1 Покрытие

| Тестовый файл | Тестов | Модуль |
|---------------|--------|--------|
| `test_bm25.py` | 55 | retrieval_adapter (BM25Scorer) |
| `test_cli.py` | 20 | brain/cli.py |
| `test_cognition.py` | 190 | cognition/* (включая auto-encode) |
| `test_cognition_integration.py` | 7 | cognition integration smoke |
| `test_e2e_pipeline.py` | 10 | end-to-end pipeline |
| `test_logging.py` | 25 | logging/* |
| `test_memory.py` | 101 | memory/* |
| `test_output.py` | 106 | output/* |
| `test_output_integration.py` | 7 | output integration smoke |
| `test_perception.py` | 79 | perception/* |
| `test_perception_hardening.py` | 34 | perception/validators.py |
| `test_resource_monitor.py` | 13 | core/resource_monitor.py |
| `test_scheduler.py` | 11 | core/scheduler.py |
| `test_storage.py` | 58 | memory/storage.py (SQLite) |
| `test_text_encoder.py` | 80 | encoders/text_encoder.py |
| `test_vector_retrieval.py` | 39 | retrieval_adapter (Vector/Hybrid) |
| **ИТОГО** | **835** | |

### 7.2 Сильные стороны

- ✅ 100% pass rate (835/835)
- ✅ Быстрое выполнение (~15s)
- ✅ Integration smoke tests для cognition и output
- ✅ E2E pipeline test
- ✅ Hardening tests для security (34 теста)
- ✅ `conftest.py` с shared fixtures

### 7.3 Пробелы

| Пробел | Серьёзность | Описание |
|--------|-------------|----------|
| Нет golden-answer benchmarks | 🟡 Средняя | B.5 запланирован, но не реализован |
| Нет property-based tests | 🟢 Низкая | Hypothesis library не используется |
| Нет stress/load tests | 🟢 Низкая | Нет тестов на большие объёмы данных |
| Нет mutation testing | 🟢 Низкая | mutmut/cosmic-ray не настроены |
| Coverage report не в CI artifacts | 🟢 Низкая | XML генерируется, но не публикуется |

---

## 8. CI/CD и DevOps

### 8.1 GitHub Actions (`ci.yml`)

- ✅ 3 версии Python (3.11, 3.12, 3.13)
- ✅ pytest + coverage
- ✅ ruff lint (E, F, W; ignore E501)
- ✅ mypy blocking (brain/core, brain/cognition)
- ✅ Smoke import tests
- ✅ pip cache

**Замечания:**
- mypy scope ограничен `brain/core` и `brain/cognition`. Не покрывает `brain/memory`, `brain/perception`, `brain/output`, `brain/encoders`. → **Рекомендация**: расширить scope постепенно.
- Нет upload coverage artifacts (codecov/coveralls)
- Нет dependabot/renovate для dependency updates

### 8.2 Dockerfile

```dockerfile
FROM python:3.12-slim
ENTRYPOINT ["cognitive-core"]
CMD ["Что такое нейропластичность?"]
```

- ✅ Slim base image
- ✅ `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`
- ⚠️ **Не multi-stage** (README говорит "multi-stage", но Dockerfile — single stage)
- ⚠️ `COPY . /app` копирует всё (включая .git, tests, docs). `.dockerignore` должен фильтровать.

### 8.3 pyproject.toml

- ✅ `[project.scripts]` cognitive-core = brain.cli:cli_entry
- ✅ `[project.optional-dependencies]` dev = pytest, pytest-cov, ruff, mypy
- ✅ `[tool.pytest.ini_options]` с markers и filterwarnings

---

## 9. Документация

### 9.1 Файлы документации

| Файл | Статус | Описание |
|------|--------|----------|
| `README.md` | 🚧 В процессе (B.4) | Основной README, 5/6 правок применены |
| `docs/ARCHITECTURE.md` | ✅ | Архитектурный обзор |
| `docs/BRAIN.md` | ✅ | Описание "мозга" |
| `docs/PLANS.md` | ✅ | Планы развития |
| `docs/TODO.md` | ✅ | Master roadmap |
| `docs/layers/*.md` (11 файлов) | ✅ | Детальное описание каждого слоя |
| `TODO_PHASE_A.md` | ✅ | Phase A tracker |
| `TODO_PHASE_B.md` | ✅ | Phase B tracker |

### 9.2 Качество docstrings

- ✅ Каждый модуль имеет module-level docstring
- ✅ Каждый класс имеет class-level docstring с описанием и примерами
- ✅ Публичные методы документированы (Args, Returns)
- ✅ TODO-комментарии с указанием Stage (H+, I, K, L)

### 9.3 Замечания

- README diff показывает повреждённый контент в середине файла (`pythNaNrt` вместо нормального текста). **Требуется проверка и исправление.**
- Некоторые docs/layers/*.md могут быть устаревшими после Phase A/B изменений.

---

## 10. Производительность

### 10.1 Текущие характеристики

- **Тесты**: 835 за ~15s (≈56 тестов/сек) — отлично
- **Cognitive cycle**: ~1-5ms (без реальных моделей)
- **Memory**: In-memory с SQLite persistence
- **TextEncoder**: Degraded mode (zero vector) — мгновенно; Navec fallback — ~5ms; sentence-transformers — ~50-200ms

### 10.2 Bottlenecks

| Компонент | Проблема | Влияние |
|-----------|----------|---------|
| `TextEncoder._cache` | Нет LRU/TTL, растёт бесконечно | RAM leak при длительной работе |
| `VectorRetrievalBackend` | In-memory dict, cosine similarity O(n) | Не масштабируется > 100K записей |
| `BM25Scorer.fit()` | Пересчёт IDF при каждом fit() | O(n·m) при большом корпусе |
| `ConsolidationEngine` | Background thread с `time.sleep()` | Не реагирует мгновенно на stop() |
| `SemanticMemory.search()` | Линейный поиск по всем nodes | O(n) при большом количестве понятий |

### 10.3 Рекомендации

1. **P1**: LRU-кэш для TextEncoder (`functools.lru_cache` или `cachetools.LRUCache`, maxsize=10000)
2. **P2**: Persisted ANN-индекс (FAISS/hnswlib) для VectorRetrievalBackend
3. **P2**: Инкрементальный BM25 (добавление документов без полного пересчёта)
4. **P3**: Async EventBus (asyncio или thread pool) для масштабирования

---

## 11. Рекомендации по приоритету

### 🔴 P0 — Критические (сделать сейчас)

| # | Задача | Обоснование |
|---|--------|-------------|
| 1 | **Проверить README.md** на повреждённый контент | Diff показывает `pythNaNrt` — возможно артефакт рендеринга |
| 2 | **Завершить B.5** — golden-answer benchmarks | Единственная незакрытая задача Phase B |

### 🟡 P1 — Важные (Phase C)

| # | Задача | Обоснование |
|---|--------|-------------|
| 3 | **DRY: `detect_language()`** → `brain/core/utils.py` | 4 копии — главный DRY-нарушитель |
| 4 | **DRY: `_sha256()`** → `brain/core/utils.py` | 2 копии с разной длиной возврата |
| 5 | **DRY: `_extract_fact()`** — переименовать | 2 разных алгоритма с одинаковым именем |
| 6 | **LRU-кэш для TextEncoder** | Предотвращение RAM leak |
| 7 | **Расширить mypy scope** на brain/memory, brain/output | Увеличить type safety |

### 🟢 P2 — Улучшения (Phase D+)

| # | Задача | Обоснование |
|---|--------|-------------|
| 8 | Разбить `retrieval_adapter.py` на подмодули | 700 LOC, 4 класса |
| 9 | Добавить `memory_refs` в `TraceChain` | Убрать workaround с `[memory]` prefix |
| 10 | Persisted ANN-индекс (FAISS/hnswlib) | Масштабирование vector search |
| 11 | Coverage upload в CI (codecov) | Отслеживание покрытия |
| 12 | Dependabot/Renovate | Автоматические dependency updates |
| 13 | Multi-stage Dockerfile | Уменьшить размер образа |

### ⚪ P3 — Долгосрочные (Post-MVP)

| # | Задача | Обоснование |
|---|--------|-------------|
| 14 | Safety layer (Stage L) | SourceTrust, BoundaryGuard, AuditLogger |
| 15 | Learning loop (Stage I) | OnlineLearner, ReplayEngine |
| 16 | Cross-modal fusion (Stage K) | SharedSpaceProjector, EntityLinker |
| 17 | Async EventBus | Масштабирование подписчиков |
| 18 | Ring 2 deep reasoning | Медленное, глубокое рассуждение |
| 19 | LLM Bridge (Stage H+) | Замена template-based ответов на LLM |

---

## Приложение A: Файловая статистика

```
brain/                          ~50 .py файлов
├── core/          (5 файлов)   ~1300 LOC  — инфраструктура
├── perception/    (5 файлов)   ~780 LOC   — восприятие
├── encoders/      (2 файла)    ~550 LOC   — кодирование
├── memory/        (8 файлов)   ~1800 LOC  — память
├── cognition/     (11 файлов)  ~3000 LOC  — когнитивное ядро
├── output/        (4 файла)    ~650 LOC   — выходной слой
├── logging/       (4 файла)    ~700 LOC   — наблюдаемость
├── fusion/        (1 файл)     stub       — кросс-модальное слияние
├── learning/      (1 файл)     stub       — обучение
├── safety/        (1 файл)     stub       — безопасность
├── cli.py                      ~150 LOC   — CLI entrypoint
└── __init__.py                 ~50 LOC    — версия + экспорты

tests/             (16 файлов)  ~4000 LOC  — 835 тестов
docs/              (15 файлов)  ~3000 LOC  — документация
```

**Общий объём кода:** ~12,000 LOC (brain/) + ~4,000 LOC (tests/) = **~16,000 LOC**

## Приложение B: Граф зависимостей модулей

```
CLI ──→ CognitiveCore ──→ GoalManager
  │         │                  │
  │         ├──→ Planner ──────┘
  │         ├──→ HypothesisEngine
  │         ├──→ Reasoner ──→ RetrievalAdapter ──→ MemoryManager
  │         │                     │                    │
  │         │                     ├──→ BM25Scorer      ├──→ WorkingMemory
  │         │                     ├──→ KeywordBackend   ├──→ SemanticMemory
  │         │                     └──→ VectorBackend    ├──→ EpisodicMemory
  │         │                                          ├──→ SourceMemory
  │         ├──→ ActionSelector                        ├──→ ProceduralMemory
  │         ├──→ ContradictionDetector                 └──→ ConsolidationEngine
  │         └──→ UncertaintyMonitor
  │
  ├──→ OutputPipeline ──→ TraceBuilder
  │         │              ├──→ ResponseValidator
  │         │              └──→ DialogueResponder
  │
  ├──→ EventBus (pub/sub)
  ├──→ ResourceMonitor (daemon thread)
  └──→ MemoryManager (5 memories + SQLite)
```

---

> **Заключение:** Проект cognitive-core v0.7.0 — это зрелый MVP с чистой архитектурой, отличным тестовым покрытием (835 тестов) и хорошей документацией. Основные области для улучшения: DRY-рефакторинг (Phase C), LRU-кэш для TextEncoder, расширение mypy scope, и завершение golden-answer benchmarks (B.5). Архитектурные решения (Protocol DI, ContractMixin, EventBus, graceful degradation) — правильные и масштабируемые.
