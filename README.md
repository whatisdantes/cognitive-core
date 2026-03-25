# 🧠 Искусственный Мультимодальный Мозг

> **Версия:** 0.7.0  
> **Статус:** 🚧 В разработке — P1a–P1c ✅ (BM25 + SQLite + CI), Этап H в очереди  
> **Платформа:** CPU-only · AMD Ryzen 7 5700X · 32 GB DDR4  
> **CI/CD:** GitHub Actions (Python 3.11/3.12/3.13, pytest + pytest-cov, ruff lint, mypy)  
> **Тесты:** 773/773 ✅ — `test_bm25.py` (55) · `test_memory.py` (101) · `test_cognition.py` (182) · `test_cognition_integration.py` (7) · `test_e2e_pipeline.py` (10) · `test_output.py` (106) · `test_output_integration.py` (7) · `test_text_encoder.py` (80) · `test_perception.py` (79) · `test_logging.py` (25) · `test_resource_monitor.py` (13) · `test_scheduler.py` (11) · `test_storage.py` (58) · `test_vector_retrieval.py` (39)

Проект по созданию **искусственного мозга**, вдохновлённого принципами человеческого мозга и адаптированного под цифровую среду. Система воспринимает, понимает, запоминает, рассуждает, учится и рефлексирует — автономно, без постоянного участия человека.

Это **не бот-ответчик**. Это когнитивный организм с внутренним состоянием, памятью и целями.

---

## 📋 Содержание

- [Быстрый старт](#-быстрый-старт)
- [Концепция](#-концепция)
- [Целевая платформа](#-целевая-платформа)
- [Архитектура](#-архитектура)
- [Биологические аналоги](#-биологические-аналоги)
- [Структура проекта](#-структура-проекта)
- [Реализованные модули](#-реализованные-модули)
- [Зависимости](#-зависимости)
- [Установка](#-установка)
- [Запуск тестов](#-запуск-тестов)
- [Система памяти — API](#-система-памяти--api)
- [Система событий — API](#-система-событий--api)
- [Логирование](#-логирование)
- [Метрики качества](#-метрики-качества)
- [Документация](#-документация)
- [Прогресс реализации](#-прогресс-реализации)

---

## ⚡ Быстрый старт

> Для запуска достаточно установить зависимости и запустить тесты. Полный мозг (all phases) ещё в разработке.

```bash
# 1. Клонировать репозиторий
git clone https://github.com/whatisdantes/cognitive-core.git
cd cognitive-core

# 2. Установить зависимости (Windows — автоматически)
download_libraries.bat

# 3. Активировать окружение
.venv\Scripts\activate

# 4. Проверить установку
python check_deps.py

# 5. Запустить все тесты (773)
python -m pytest tests/ -v

# 6. Использовать Memory System в коде
python -c "
from brain.memory import MemoryManager
mm = MemoryManager(data_dir='brain/data/memory', auto_consolidate=False)
mm.start()
mm.store('нейрон это клетка нервной системы', importance=0.8, source_ref='test')
result = mm.retrieve('нейрон')
print(result.summary())
mm.stop()
"
```

> 📖 Полная архитектурная спецификация: [`BRAIN.md`](docs/BRAIN.md)  
> 📋 План реализации (14 фаз): [`TODO.md`](docs/TODO.md)  
> 🗂️ Документация по слоям: [`docs/layers/`](docs/layers/)

---

## 💡 Концепция

Человеческий мозг — это сеть взаимосвязанных контуров, работающих **параллельно и асинхронно**:

1. Восприятие сигналов из внешнего мира
2. Предобработка и распознавание паттернов
3. Смысловая интеграция из разных источников
4. Оценка значимости и риска
5. Рабочая память и управление вниманием
6. Выбор действия среди конкурирующих вариантов
7. Обучение по ошибке и подкреплению
8. Консолидация памяти (краткосрочная → долгосрочная)

**Главная инженерная идея:**
> Разум — это не генерация текста, а **управление внутренним состоянием и памятью**.

Система работает с несколькими модальностями:
- 📄 Документы (`.txt`, `.md`, `.pdf`, `.docx`, `.json`)
- 🖼️ Изображения (OCR + понимание сцен)
- 🎙️ Аудио (ASR + временные метки)
- 🎬 Видео (покадровый анализ + временное отслеживание)

---

## 💻 Целевая платформа

| Компонент | Характеристика |
|-----------|----------------|
| CPU | AMD Ryzen 7 5700X — 8 ядер / 16 потоков, до 4.6 GHz |
| RAM | DDR4 32 GB, 3200 MHz |
| GPU | — (не используется, `USE_GPU=False`) |
| ОС | Windows 10/11 (основная), Linux/macOS (совместимо) |
| Python | 3.11+ |

### Ресурсные лимиты

| Ресурс | Рабочий лимит | Порог деградации |
|--------|--------------|-----------------|
| RAM | ≤ 22 GB | > 28 GB → сжать рабочую память |
| CPU | ≤ 70% avg | > 85% → снизить частоту тиков |
| Потоки | 8–12 из 16 | оставить 4 потока для ОС |
| Модели | ≤ 3 GB суммарно | > 5 GB → выгружать неактивные |

### Модели и их размеры

| Модуль | Модель (основная) | Размер | Fallback |
|--------|------------------|--------|----------|
| Text Encoder | sentence-transformers large | ~1.3 GB | navec (~200 MB) |
| Vision Encoder | CLIP ViT-B/32 | ~600 MB | ResNet-50 (~100 MB) |
| Audio ASR | Whisper medium | ~1.5 GB | Whisper base (~150 MB) |
| **Итого** | | **~3.4 GB** | **~450 MB** |

> ⚠️ Модели загружаются автоматически при первом запуске соответствующего энкодера.

---

## 🏗️ Архитектура

```
MULTIMODAL BRAIN
│
├─ 0. Autonomous Loop           ← Ствол мозга (always-on)
│   ├─ Scheduler                clock-driven + event-driven тики
│   ├─ EventBus                 publish/subscribe шина событий
│   ├─ ResourceMonitor          CPU/RAM мониторинг, graceful degradation
│   └─ AttentionController      бюджет вычислений по модальностям
│
├─ 1. Perception Layer          ← Таламус (маршрутизация входов)
│   ├─ TextIngestor             txt / md / pdf / docx / json
│   ├─ VisionIngestor           img / video frames + OCR
│   ├─ AudioIngestor            ASR + acoustic events
│   ├─ MetadataExtractor        source, timestamp, quality, language
│   └─ InputRouter              маршрутизация по типу модальности
│
├─ 2. Modality Encoders         ← Сенсорная кора (векторизация)
│   ├─ TextEncoder              sentence-transformers (768d/1024d)
│   ├─ VisionEncoder            CLIP ViT-B/32 (512d)
│   ├─ AudioEncoder             Whisper medium + MFCC
│   └─ TemporalEncoder          позиционное кодирование (видео)
│
├─ 3. Cross-Modal Fusion        ← Ассоциативная кора (слияние)
│   ├─ SharedSpaceProjector     единое латентное пространство
│   ├─ EntityLinker             связывание сущностей из разных источников
│   ├─ ConfidenceCalibrator     оценка качества слияния
│   └─ ContradictionDetector    обнаружение противоречий между модальностями
│
├─ 4. Memory System ✅          ← Гиппокамп + Кора (память)
│   ├─ WorkingMemory            активный контекст (sliding window, max=20)
│   ├─ SemanticMemory           граф понятий и связей (BFS, JSON)
│   ├─ EpisodicMemory           хронология событий (кросс-модальные записи)
│   ├─ SourceMemory             доверие к источникам (trust score, blacklist)
│   ├─ ProceduralMemory         навыки и стратегии (success rate tracking)
│   ├─ ConsolidationEngine      WM → LTM (фоновый поток, RAM-aware)
│   └─ MemoryManager            единый интерфейс store()/retrieve()
│
├─ 5. Cognitive Core            ← Префронтальная кора (мышление)
│   ├─ GoalManager              управление целями (создание, приоритизация, завершение)
│   ├─ Planner                  декомпозиция целей на шаги + выбор стратегии
│   ├─ HypothesisEngine         генерация и оценка гипотез (causal/associative/analogical)
│   ├─ Reasoner                 reasoning loop (retrieve → hypothesize → score → act)
│   ├─ ContradictionDetector    поиск конфликтующих фактов
│   ├─ UncertaintyMonitor       оценка уверенности по гипотезам
│   ├─ SalienceEngine           оценка значимости (аналог Миндалины)
│   └─ ActionSelector           выбор действия (аналог Базальных ганглий)
│
├─ 6. Learning Loop             ← Мозжечок + Гиппокамп (обучение)
│   ├─ OnlineLearner            обновление после каждого взаимодействия
│   ├─ ReplayEngine             периодическое воспроизведение эпизодов
│   ├─ SelfSupervisedLearner    согласованность картинка ↔ текст ↔ аудио
│   └─ HypothesisEngine         генерация и проверка гипотез
│
├─ 7. Output Layer              ← Речевые зоны (вывод)
│   ├─ DialogueResponder        текстовый ответ + объяснение + confidence
│   ├─ ActionProposer           предложение действий с обоснованием
│   └─ TraceBuilder             полная цепочка причинности
│
├─ 8. Attention & Resources     ← Таламус + Гипоталамус
│   ├─ AttentionController      goal-driven + salience-driven внимание
│   ├─ ModalityRouter           маршрутизация по приоритету
│   ├─ CognitiveLoadBalancer    балансировка нагрузки
│   └─ DegradationPolicy        политика деградации при нехватке ресурсов
│
├─ 9. Logging & Observability   ← Метапознание
│   ├─ BrainLogger              JSONL-логгер (одна строка = одно событие)
│   ├─ DigestGenerator          human-readable сводка по циклу
│   ├─ TraceBuilder             trace chain для каждого решения
│   └─ MetricsCollector         KPI метрики в реальном времени
│
├─ 10. Safety & Boundaries      ← Иммунная система
│   ├─ SourceTrust              оценка надёжности источников
│   ├─ ConflictDetector         детектор конфликтов фактов
│   ├─ BoundaryGuard            ограничения на действия системы
│   └─ AuditLogger              аудит решений с высоким риском
│
└─ 11. Reward & Motivation      ← Средний мозг (дофаминовая система)
    ├─ RewardEngine             5 типов вознаграждения + prediction error
    ├─ MotivationEngine         накопление reward signals, decay мотивации
    └─ CuriosityEngine          любопытство ∝ 1/knowledge_coverage
```

---

## 🧬 Биологические аналоги

| Отдел мозга | Функции | Аналог в системе |
|-------------|---------|-----------------|
| Ствол мозга | Базовые жизненные функции, автономный цикл | `Scheduler`, `EventBus`, `ResourceMonitor` |
| Таламус | Маршрутизация и фильтрация сенсорных потоков | `InputRouter`, `ModalityRouter`, `AttentionController` |
| Сенсорная кора | Обработка сигналов каждой модальности | `TextEncoder`, `VisionEncoder`, `AudioEncoder` |
| Ассоциативная кора | Интеграция информации из разных источников | `CrossModalFusion`, `EntityLinker` |
| Гиппокамп | Формирование и консолидация воспоминаний | `EpisodicMemory`, `ConsolidationEngine` |
| Префронтальная кора | Планирование, цели, принятие решений | `Planner`, `Reasoner`, `ActionSelector` |
| Миндалина | Быстрая оценка значимости и угрозы | `SalienceEngine`, `PriorityScorer` |
| Базальные ганглии | Выбор действия среди конкурирующих | `ActionSelector`, `PolicyGate` |
| Мозжечок | Тонкая коррекция, автоматизация навыков | `SkillRefiner`, `OnlineLearner` |
| Гипоталамус | Регуляция ресурсов и гомеостаз | `ResourceMonitor`, `DegradationPolicy` |
| Средний мозг | Дофаминовая система, мотивация | `RewardEngine`, `MotivationEngine`, `CuriosityEngine` |

---

## 📁 Структура проекта

```
cognitive-core/
│
├── brain/                              # Основной пакет мозга (v0.7.0)
│   ├── __init__.py                     # Корневой пакет
│   │
│   ├── core/                           # Ядро автономного цикла
│   │   ├── __init__.py                 # ✅ Экспорты: 26 классов (events+contracts+bus+scheduler+monitor)
│   │   ├── events.py                   # ✅ 6 типов событий + EventFactory
│   │   ├── contracts.py                # ✅ Общие типы: Modality, Task, ResourceState,
│   │   │                               #    EncodedPercept, FusedPercept, TraceChain,
│   │   │                               #    CognitiveResult, BrainOutput (contracts.py)
│   │   ├── event_bus.py                # ✅ EventBus — typed pub/sub шина событий
│   │   ├── scheduler.py                # ✅ Scheduler — тик-планировщик (heapq, 4 приоритета, адаптивный tick)
│   │   └── resource_monitor.py         # ✅ ResourceMonitor — CPU/RAM мониторинг, 4 политики деградации
│   │
│   ├── memory/                         # Система памяти ✅ РЕАЛИЗОВАНО (JSON + SQLite)
│   │   ├── __init__.py                 # Экспорты 17 классов
│   │   ├── working_memory.py           # ✅ WorkingMemory + MemoryItem (RAM-only)
│   │   ├── semantic_memory.py          # ✅ SemanticMemory + SemanticNode + Relation
│   │   ├── episodic_memory.py          # ✅ EpisodicMemory + Episode + ModalEvidence
│   │   ├── source_memory.py            # ✅ SourceMemory + SourceRecord
│   │   ├── procedural_memory.py        # ✅ ProceduralMemory + Procedure + ProcedureStep
│   │   ├── consolidation_engine.py     # ✅ ConsolidationEngine + ConsolidationConfig
│   │   ├── memory_manager.py           # ✅ MemoryManager + MemorySearchResult (SQLite transactions)
│   │   ├── storage.py                  # ✅ MemoryDatabase — SQLite WAL backend (P1c)
│   │   └── migrate.py                  # ✅ JSON→SQLite миграция (backup, idempotent)
│   │
│   ├── perception/                     # Слой восприятия ✅ РЕАЛИЗОВАНО (Этап D)
│   │   ├── __init__.py                 # Экспорты: MetadataExtractor, TextIngestor, InputRouter
│   │   ├── metadata_extractor.py       # ✅ MetadataExtractor — quality scoring, language detection
│   │   ├── text_ingestor.py            # ✅ TextIngestor — .txt/.md/.pdf/.docx/.json/.csv
│   │   └── input_router.py             # ✅ InputRouter — SHA256 dedup, quality policy, text-only MVP
│   │
│   ├── encoders/                       # Модальные энкодеры ✅ РЕАЛИЗОВАНО (Этап E, text-only)
│   │   ├── __init__.py                 # Экспорты: TextEncoder
│   │   └── text_encoder.py             # ✅ TextEncoder — sentence-transformers 768d / navec 300d fallback
│   │
│   ├── fusion/                         # Кросс-модальное слияние (Фаза 5 — запланировано)
│   │   └── __init__.py
│   │
│   ├── cognition/                      # Когнитивное ядро ✅ РЕАЛИЗОВАНО (Этап F + F+)
│   │   ├── __init__.py                 # Экспорты: 30 классов (22 Stage F + 8 Stage F+)
│   │   ├── context.py                  # ✅ CognitiveContext, CognitiveOutcome, EvidencePack,
│   │   │                               #    GoalTypeLimits, PolicyConstraints, ReasoningState,
│   │   │                               #    UncertaintyTrend, ReplanStrategy
│   │   ├── goal_manager.py             # ✅ GoalStatus, Goal, GoalManager
│   │   ├── planner.py                  # ✅ PlanStep, ExecutionPlan, Planner (5 replan strategies)
│   │   ├── hypothesis_engine.py        # ✅ Hypothesis, HypothesisEngine (assoc+deduct+causal+analog)
│   │   ├── reasoner.py                 # ✅ ReasoningStep, ReasoningTrace, Reasoner
│   │   ├── action_selector.py          # ✅ ActionType, ActionDecision, ActionSelector
│   │   ├── cognitive_core.py           # ✅ CognitiveCore — orchestrator (run → CognitiveResult)
│   │   ├── retrieval_adapter.py        # ✅ RetrievalAdapter, KeywordRetrievalBackend (BM25 reranking),
│   │   │                               #    VectorRetrievalBackend, HybridRetrievalBackend, BM25Scorer
│   │   ├── contradiction_detector.py   # ✅ Contradiction, ContradictionDetector (F+)
│   │   └── uncertainty_monitor.py      # ✅ UncertaintySnapshot, UncertaintyMonitor (F+)
│   │
│   ├── learning/                       # Система обучения (Этап I — запланировано)
│   │   └── __init__.py
│   │
│   ├── logging/                        # Логирование ✅ РЕАЛИЗОВАНО (Этап C)
│   │   ├── __init__.py                 # Экспорты: BrainLogger, DigestGenerator, CycleInfo, TraceBuilder
│   │   ├── brain_logger.py             # ✅ BrainLogger — JSONL, 5 уровней, категорийные файлы, индекс
│   │   ├── digest_generator.py         # ✅ DigestGenerator + CycleInfo — human-readable сводки
│   │   └── reasoning_tracer.py         # ✅ TraceBuilder — trace chain, reconstruct_from_logger
│   │                                   #    (renamed from trace_builder.py to avoid conflict with output/)
│   │
│   ├── safety/                         # Безопасность (Фаза 11 — запланировано)
│   │   └── __init__.py
│   │
│   ├── output/                         # Слой вывода ✅ РЕАЛИЗОВАНО (Этап G)
│   │   ├── __init__.py                 # Экспорты: 13 классов
│   │   ├── trace_builder.py            # ✅ ExplainabilityTrace, OutputTraceBuilder
│   │   ├── response_validator.py       # ✅ ValidationIssue, ValidationResult, ResponseValidator
│   │   └── dialogue_responder.py       # ✅ DialogueResponder (template MVP + LLM TODO), OutputPipeline
│   │
│   └── data/                           # Постоянное хранилище
│       └── memory/                     # Данные памяти (создаются автоматически)
│           ├── memory.db               # SQLite WAL база (основной backend v0.7.0+)
│           ├── semantic.json           # граф понятий (legacy JSON fallback)
│           ├── episodes.json           # хронология событий (legacy JSON fallback)
│           ├── sources.json            # доверие к источникам (legacy JSON fallback)
│           └── procedures.json         # навыки и стратегии (legacy JSON fallback)
│
├── tests/                              # Тесты (pytest-совместимые, 773 ✅)
│   ├── conftest.py                     # Общая конфигурация pytest + fixtures
│   ├── test_bm25.py                    # ✅ 55/55 тестов BM25 Scorer + KeywordBackend reranking
│   ├── test_logging.py                 # ✅ 25/25 тестов Logging & Observability (unittest)
│   ├── test_memory.py                  # ✅ 101/101 тестов системы памяти
│   ├── test_perception.py              # ✅ 79/79 тестов Perception Layer
│   ├── test_resource_monitor.py        # ✅ 13/13 тестов ResourceMonitor
│   ├── test_scheduler.py              # ✅ 11/11 тестов Scheduler
│   ├── test_storage.py                # ✅ 58/58 тестов SQLite Storage + Migration
│   ├── test_text_encoder.py           # ✅ 80/80 тестов Text Encoder
│   ├── test_cognition.py             # ✅ 182/182 тестов Cognitive Core (unit)
│   ├── test_cognition_integration.py  # ✅ 7/7 тестов Cognitive Core (integration)
│   ├── test_e2e_pipeline.py           # ✅ 10/10 тестов E2E Pipeline
│   ├── test_output.py                 # ✅ 106/106 тестов Output Layer (unit)
│   ├── test_output_integration.py     # ✅ 7/7 тестов Output Layer (integration)
│   └── test_vector_retrieval.py       # ✅ 39/39 тестов Vector Retrieval
│
├── docs/                               # Документация
│   ├── BRAIN.md                        # Архитектурная спецификация (15 разделов)
│   ├── TODO.md                         # План реализации (14 фаз, 35+ задач)
│   ├── ARCHITECTURE.md                 # Архитектурные решения
│   ├── PLANS.md                        # Стратегический план
│   ├── DAILY_REPORT_2026-03-21.md      # Дневной отчёт
│   └── layers/                         # Описание каждого слоя (12 файлов)
│       ├── 00_autonomous_loop.md       # Ствол мозга — always-on цикл
│       ├── 01_perception_layer.md      # Таламус — восприятие и маршрутизация
│       ├── 02_modality_encoders.md     # Сенсорная кора — кодирование в векторы
│       ├── 03_cross_modal_fusion.md    # Ассоциативная кора — слияние модальностей
│       ├── 04_memory_system.md         # Memory System — 5 видов памяти + Гиппокамп
│       ├── 05_cognitive_core.md        # Префронтальная кора — планирование
│       ├── 06_learning_loop.md         # Мозжечок — обучение из опыта
│       ├── 07_output_layer.md          # Речевые зоны — вывод с объяснением
│       ├── 08_attention_resource.md    # Таламус+Гипоталамус — внимание и ресурсы
│       ├── 09_logging_observability.md # Метапознание — JSONL логи, trace chain, KPI
│       ├── 10_safety_boundaries.md     # Иммунная система — source trust, аудит
│       └── 11_midbrain_reward.md       # Средний мозг — мотивация, вознаграждение
│
├── .gitignore                          # Git ignore rules
├── pyproject.toml                      # Конфигурация проекта + pytest
├── requirements.txt                    # Зависимости Python
├── download_libraries.bat              # Автоустановка зависимостей (Windows)
├── check_deps.py                       # Проверка установленных зависимостей
└── README.md                           # Этот файл
```

---

## ✅ Реализованные модули

### `brain/core/events.py` — Типизированные события

Все модули общаются через события — никаких прямых зависимостей между модулями.

| Класс | Описание | Ключевые поля |
|-------|---------|---------------|
| `BaseEvent` | Базовый класс всех событий | `event_type`, `ts`, `trace_id`, `session_id`, `cycle_id` |
| `PerceptEvent` | Входящий сигнал из внешнего мира | `source`, `modality`, `content`, `quality`, `language`, `metadata` |
| `MemoryEvent` | Операция с памятью | `operation`, `memory_type`, `key`, `value`, `importance`, `confidence` |
| `CognitiveEvent` | Шаг мышления/планирования | `goal`, `step`, `confidence`, `decision`, `reasoning`, `cpu_pct`, `ram_mb` |
| `LearningEvent` | Изменение весов/оценок | `trigger`, `affected_module`, `delta`, `before`, `after` |
| `SystemEvent` | Системные события (запуск, ошибки) | `level`, `module`, `message`, `cpu_pct`, `ram_mb`, `error` |
| `EventFactory` | Фабричные методы создания событий | `percept()`, `memory_store()`, `memory_retrieve()`, `system_info()`, ... |

```python
from brain.core import PerceptEvent, EventFactory

# Создание события восприятия
ev = EventFactory.percept(
    source="doc.pdf",
    content="нейрон это клетка нервной системы",
    modality="text",
    quality=0.95,
    language="ru",
)

# Сериализация в JSONL
print(ev.to_json_line())
```

---

### `brain/memory/` — Система памяти (101/101 тестов ✅)

#### `WorkingMemory` — Рабочая память

Активный контекст текущего цикла. Аналог кратковременной памяти (~7 чанков по Миллеру).

| Параметр | Значение | Описание |
|----------|---------|---------|
| `max_size` | 20 | Максимальное количество элементов |
| `IMPORTANCE_PROTECT_THRESHOLD` | 0.8 | Порог защиты от вытеснения |
| `RAM_LIMIT_PCT` | 80% | При превышении — сжать окно до 50% |

```python
from brain.memory import WorkingMemory

wm = WorkingMemory(max_size=20)

# Добавить элемент
item = wm.push("нейрон это клетка нервной системы", importance=0.7, tags=["биология"])

# Поиск по содержимому
results = wm.search("нейрон", top_n=5)

# Получить текущий контекст
context = wm.get_context(n=10)

# Статус
wm.display_status()
```

#### `SemanticMemory` — Семантическая память (граф понятий)

Граф понятий и связей. Аналог долгосрочной декларативной памяти.

```python
from brain.memory import SemanticMemory

sm = SemanticMemory(data_path="brain/data/memory/semantic.json")

# Сохранить факт
node = sm.store_fact("нейрон", "клетка нервной системы", tags=["биология"])

# Добавить связь
sm.add_relation("нейрон", "синапс", weight=0.8, rel_type="related")

# Поиск
results = sm.search("нейрон")

# BFS-цепочка понятий
chain = sm.get_concept_chain("нейрон", "мозг", max_depth=3)

# Подтверждение/опровержение факта
sm.confirm_fact("нейрон")
sm.deny_fact("нейрон", delta=0.3)
```

#### `EpisodicMemory` — Эпизодическая память

Хронология событий с кросс-модальными доказательствами.

```python
from brain.memory import EpisodicMemory, ModalEvidence

em = EpisodicMemory(data_path="brain/data/memory/episodes.json")

# Сохранить эпизод
ep = em.store(
    content="пользователь спросил про нейроны",
    modality="text",
    source="user_input",
    importance=0.7,
    concepts=["нейрон", "вопрос"],
)

# Добавить кросс-модальное доказательство
evidence = ModalEvidence(modality="image", source="diagram.png", content_ref="регион 0,0,100,100")
ep.add_evidence(evidence)

# Поиск
by_concept = em.retrieve_by_concept("нейрон")
by_time    = em.retrieve_by_time(start_ts=time.time() - 3600)
by_text    = em.search("нейрон")
```

#### `SourceMemory` — Память об источниках

Trust score для каждого источника. Provenance для каждого факта.

| Тип источника | Trust score по умолчанию |
|--------------|------------------------|
| `system` | 1.0 |
| `user` | 0.8 |
| `file` | 0.7 |
| `url` | 0.5 |
| неизвестный | 0.5 |
| blacklisted | 0.0 |

```python
from brain.memory import SourceMemory

src = SourceMemory(data_path="brain/data/memory/sources.json")

rec = src.register("wikipedia.org", source_type="url")
src.update_trust("wikipedia.org", confirmed=True)
src.blacklist("spam_source", reason="спам")

trust = src.get_trust("wikipedia.org")  # float 0.0–1.0
```

#### `ProceduralMemory` — Процедурная память

Навыки и стратегии с отслеживанием успешности.

```python
from brain.memory import ProceduralMemory

pm = ProceduralMemory(data_path="brain/data/memory/procedures.json")

proc = pm.store(
    name="ответить_на_вопрос",
    steps=[
        {"action": "parse_question", "params": {"lang": "ru"}},
        {"action": "search_memory",  "params": {"top_n": 5}},
        {"action": "generate_answer","params": {}},
    ],
    trigger_pattern="вопрос",
    priority=0.8,
)

pm.record_result("ответить_на_вопрос", success=True, duration_ms=150.0)
best = pm.get_best(top_n=3)
```

#### `ConsolidationEngine` — Движок консолидации (Гиппокамп)

Фоновый daemon-поток, переносящий важные элементы из рабочей памяти в долгосрочную.

| Параметр | Значение | Описание |
|----------|---------|---------|
| Интервал консолидации | 30 сек | WM → Episodic/Semantic |
| Интервал decay | 5 мин | Затухание неважных фактов |
| RAM-порог агрессивного забывания | 85% | Принудительная очистка |
| Порог переноса в LTM | importance ≥ 0.4 | Минимальная важность |

```python
from brain.memory import ConsolidationEngine

engine = ConsolidationEngine(
    working=wm, episodic=em, semantic=sm, source=src, procedural=pm
)

# Принудительная консолидация
stats = engine.force_consolidate()
# stats = {"to_episodic": 3, "to_semantic": 2, "decayed": 1}

# Принудительный decay
engine.force_decay()

# Подкрепление / ослабление факта
engine.reinforce("нейрон", source_ref="user_input")
engine.weaken("устаревший_факт")
```

#### `MemoryManager` — Единый интерфейс

Агрегирует все 5 видов памяти + ConsolidationEngine. Главная точка входа.

```python
from brain.memory import MemoryManager

mm = MemoryManager(
    data_dir="brain/data/memory",
    working_max_size=20,
    semantic_max_nodes=10_000,
    episodic_max=5_000,
    auto_consolidate=True,
)
mm.start()

# Сохранить (автоматически в working + episodic + semantic)
result = mm.store(
    "нейрон это клетка нервной системы",
    importance=0.8,
    source_ref="textbook.pdf",
    tags=["биология"],
)

# Явное сохранение факта
node = mm.store_fact("синапс", "связь между нейронами", importance=0.7)

# Поиск по всем видам памяти
search = mm.retrieve("нейрон", top_n=5)
print(search.summary())
# [Факт] нейрон: клетка нервной системы
# [Эпизод] пользователь спросил про нейроны
# [Контекст] нейрон это клетка нервной системы

# Подтверждение / опровержение
mm.confirm("нейрон", source_ref="textbook.pdf")
mm.deny("устаревший_факт")

# Сохранить всё на диск
mm.save_all()
mm.stop()

# Полный статус
mm.display_status()
```

---

## 📦 Зависимости

```
# Ядро
numpy>=1.26.0
jsonlines>=4.0.0

# PyTorch (CPU-only — устанавливается отдельно через download_libraries.bat)
torch>=2.2.0

# Русский язык
pymorphy3>=1.0.0
razdel>=0.5.0
nltk>=3.8.0
navec>=0.10.0              # fallback text encoder (~200 MB)

# Text Encoder
sentence-transformers>=2.7.0   # основной (~1.3 GB при первом запуске)

# Vision Encoder
open-clip-torch>=2.24.0        # CLIP ViT-B/32 (~600 MB при первом запуске)
pillow>=10.0.0

# Audio ASR
openai-whisper>=20231117       # Whisper medium (~1.5 GB при первом запуске)

# Документы
pymupdf>=1.24.0
python-docx>=1.1.0

# Утилиты
psutil>=5.9.0
tqdm>=4.66.0
```

---

## 🚀 Установка

### Требования

- Python 3.11+
- Windows 10/11 (или Linux/macOS с адаптацией скрипта)
- 32 GB RAM (рекомендуется)
- ~5 GB свободного места на диске (для моделей)

### Шаг 1 — Автоматическая установка (Windows)

```bat
download_libraries.bat
```

Скрипт выполняет 8 шагов:
1. Проверка Python 3.10+
2. Создание виртуального окружения `venv/`
3. Активация `venv` и обновление `pip`
4. Установка PyTorch CPU-only (`--index-url https://download.pytorch.org/whl/cpu`)
5. Установка базовых зависимостей (numpy, psutil, pymorphy3, razdel, nltk, navec, pillow, pymupdf, python-docx)
6. Установка `sentence-transformers` (Text Encoder)
7. Установка `open-clip-torch` (Vision Encoder)
8. Установка `openai-whisper` (Audio ASR) + загрузка NLTK данных

### Шаг 2 — Ручная установка

```bash
# Создать виртуальное окружение
python -m venv .venv

# Активировать (Windows)
.venv\Scripts\activate

# Активировать (Linux/macOS)
source .venv/bin/activate

# Установить PyTorch CPU-only
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Установить остальные зависимости
pip install -r requirements.txt
```

### Шаг 3 — Проверка установки

```bash
python check_deps.py
```

Ожидаемый вывод:
```
====================================================
  ✅  УСТАНОВЛЕНО:
====================================================
  PyTorch (CPU-only)             v2.x.x+cpu
  NumPy                          v2.x.x
  sentence-transformers          v2.x.x
  open-clip-torch (CLIP)         v2.x.x
  openai-whisper                 v20231117
  pymorphy3                      v1.x.x
  psutil                         v5.x.x
  ...
  Все зависимости установлены корректно!

====================================================
  🔍  PyTorch детали:
====================================================
  CUDA доступна: False
  CPU потоков:  16
  Тест матрицы: OK (3x3 mm)
```

---

## ▶️ Запуск тестов

```bash
# Активировать окружение
.venv\Scripts\activate

# Запустить все тесты (773 ✅)
python -m pytest tests/ -v

# Или отдельный файл
python -m pytest tests/test_memory.py -v
```

### Состав тестового набора (773 тестов)

| Файл | Модуль | Тестов |
|------|--------|--------|
| `tests/test_bm25.py` | BM25 Scorer (unit + KeywordBackend reranking integration) | 55 |
| `tests/test_logging.py` | Logging & Observability (BrainLogger, DigestGenerator, TraceBuilder) | 25 |
| `tests/test_memory.py` | Memory System (Events, WM, SM, EM, Source, Procedural, Manager, Consolidation) | 101 |
| `tests/test_perception.py` | Perception Layer (MetadataExtractor, TextIngestor, InputRouter) | 79 |
| `tests/test_resource_monitor.py` | ResourceMonitor (policies, hysteresis, background thread) | 13 |
| `tests/test_scheduler.py` | Scheduler (ticks, priorities, adaptive interval, error handling) | 11 |
| `tests/test_storage.py` | SQLite Storage (MemoryDatabase CRUD, transactions, threads, migration) | 58 |
| `tests/test_text_encoder.py` | Text Encoder (primary/fallback/failed modes, semantic checks, batch, cache) | 80 |
| `tests/test_cognition.py` | Cognitive Core (Context, Goals, Planner, Hypotheses, Reasoner, Actions, Core) | 182 |
| `tests/test_cognition_integration.py` | Cognitive Core Integration (smoke tests with real MemoryManager) | 7 |
| `tests/test_e2e_pipeline.py` | E2E Pipeline (Protocol conformance + full pipeline) | 10 |
| `tests/test_output.py` | Output Layer (ExplainabilityTrace, OutputTraceBuilder, Validator, Responder, Pipeline) | 106 |
| `tests/test_output_integration.py` | Output Layer Integration (CognitiveCore → OutputPipeline → BrainOutput) | 7 |
| `tests/test_vector_retrieval.py` | Vector Retrieval (VectorRetrievalBackend, HybridRetrievalBackend, cosine similarity) | 39 |
| | **Итого** | **773** |

---

## 📊 Логирование

Каждое событие — одна JSON-строка в JSONL-файле:

```json
{
  "ts": "2026-03-19T12:00:00.123Z",
  "level": "INFO",
  "module": "planner",
  "event": "plan_step_selected",
  "session_id": "sess_01",
  "cycle_id": "cycle_4521",
  "trace_id": "trace_9fa",
  "input_ref": ["doc:A.md#p12", "img:frame_33"],
  "state": {"goal": "verify_claim", "cpu_pct": 62, "ram_mb": 4200},
  "decision": {"action": "cross_modal_check", "confidence": 0.81},
  "latency_ms": 37,
  "notes": "selected due to contradiction risk"
}
```

### Уровни логов

| Уровень | Когда |
|---------|-------|
| `DEBUG` | Детальная трассировка (dev/исследования) |
| `INFO` | Нормальная работа циклов |
| `WARN` | Подозрительные данные или CPU > 70% |
| `ERROR` | Сбои модулей / невозможность шага |
| `CRITICAL` | Риск целостности системы или CPU > 85% |

### Кросс-модальная запись памяти

```json
{
  "concept": "нейрон",
  "modal_evidence": [
    {"type": "text",  "source": "doc_A.md",     "span": "..."},
    {"type": "image", "source": "img_12.png",    "region": [0, 0, 100, 100]},
    {"type": "audio", "source": "lecture_3.wav", "time": [12.2, 14.7]}
  ],
  "confidence": 0.81,
  "last_verified": "2026-03-19T10:30:00Z"
}
```

---

## 📈 Метрики качества

| # | Метрика | Описание |
|---|---------|---------|
| 1 | Cross-Modal Retrieval Accuracy | Точность поиска по разным модальностям |
| 2 | Source Reliability Calibration | Калибровка доверия к источникам |
| 3 | Contradiction Detection Rate | Доля обнаруженных противоречий |
| 4 | Reasoning Depth & Coherence | Глубина и связность рассуждений |
| 5 | Learning Velocity | Скорость закрытия пробелов в знаниях |
| 6 | Self-Correction Rate | Частота самокоррекции ошибок |
| 7 | Explainability Completeness | Полнота объяснений решений |
| 8 | Trace Completeness | % решений с полной цепочкой причинности |
| 9 | Error Localization Time | Время до локализации причины сбоя |
| 10 | Logging Overhead | % накладных расходов логирования |

---

## 📚 Документация

Подробная документация по каждому слою архитектуры находится в [`docs/layers/`](docs/layers/):

| Файл | Слой | Биологический аналог | Статус |
|------|------|---------------------|--------|
| [`00_autonomous_loop.md`](docs/layers/00_autonomous_loop.md) | Always-On Loop | Ствол мозга | ✅ Реализовано (Этап B) |
| [`01_perception_layer.md`](docs/layers/01_perception_layer.md) | Perception Layer | Таламус | ✅ Реализовано (Этап D, text-only) |
| [`02_modality_encoders.md`](docs/layers/02_modality_encoders.md) | Modality Encoders | Сенсорная кора | ✅ Реализовано (Этап E, text-only, 80/80) |
| [`03_cross_modal_fusion.md`](docs/layers/03_cross_modal_fusion.md) | Cross-Modal Fusion | Ассоциативная кора | 📄 Спецификация (Этап K) |
| [`04_memory_system.md`](docs/layers/04_memory_system.md) | Memory System | Гиппокамп + Кора | ✅ Реализовано (101/101) |
| [`05_cognitive_core.md`](docs/layers/05_cognitive_core.md) | Cognitive Core | Префронтальная кора | 📋 Детальная спецификация (Этап F) |
| [`06_learning_loop.md`](docs/layers/06_learning_loop.md) | Learning Loop | Мозжечок + Гиппокамп | 📄 Спецификация (Этап I) |
| [`07_output_layer.md`](docs/layers/07_output_layer.md) | Output Layer | Речевые зоны Брока/Вернике | 📄 Спецификация (Этап G) |
| [`08_attention_resource.md`](docs/layers/08_attention_resource.md) | Attention & Resources | Таламус + Гипоталамус | 📄 Спецификация (Этап H) |
| [`09_logging_observability.md`](docs/layers/09_logging_observability.md) | Logging & Observability | Метапознание | ✅ Реализовано (Этап C, 25/25) |
| [`10_safety_boundaries.md`](docs/layers/10_safety_boundaries.md) | Safety & Boundaries | Иммунная система | 📄 Спецификация (Этап L) |
| [`11_midbrain_reward.md`](docs/layers/11_midbrain_reward.md) | Reward & Motivation | Средний мозг | 📄 Спецификация (Этап M) |

Архитектурная спецификация: [`BRAIN.md`](docs/BRAIN.md) (15 разделов)  
План реализации: [`TODO.md`](docs/TODO.md) (14 фаз, 35+ задач)

---

## ✅ Прогресс реализации

| Фаза | Название | Статус | Тестов |
|------|----------|--------|--------|
| 0 | Foundation & Bootstrap | 🚧 В процессе | — |
| 1 | Always-On Autonomous Loop | ✅ Этап B завершён (events ✅, contracts ✅, event_bus ✅, scheduler ✅, resource_monitor ✅) | 11+13 |
| **2** | **Logging & Observability** | **✅ Завершено** | **25/25** |
| **3** | **Perception Layer (text-only)** | **✅ Завершено (Этап D)** | **79/79** |
| **4** | **Modality Encoders (text-only)** | **✅ Завершено (Этап E)** | **80/80** |
| 5 | Cross-Modal Fusion | ⬜ Не начато | — |
| **6** | **Memory System** | **✅ Завершено** | **101/101** |
| **7** | **Cognitive Core** | **✅ Завершено (Этап F)** | **182+7** |
| **8** | **Explainability & Output** | **✅ Завершено (Этап G)** | **106+7** |
| 9 | Attention & Resource Control | ⬜ Не начато | — |
| 10 | Learning Loop | ⬜ Не начато | — |
| 11 | Safety & Boundaries | ⬜ Не начато | — |
| 12 | Self-Development & Reflection | ⬜ Не начато | — |
| 13 | Metrics & KPI Dashboard | ⬜ Не начато | — |
| 14 | Reward & Motivation System | ⬜ Не начато | — |

### Что реализовано сейчас

```
brain/
├── core/
│   ├── events.py              ← BaseEvent, PerceptEvent, MemoryEvent,
│   │                             CognitiveEvent, LearningEvent, SystemEvent,
│   │                             EventFactory
│   ├── contracts.py           ← Modality, TaskStatus, ResourceState, Task,
│   │                             EncodedPercept, FusedPercept, TraceRef,
│   │                             TraceStep, TraceChain, CognitiveResult,
│   │                             BrainOutput (ContractMixin: to_dict/from_dict)
│   ├── event_bus.py           ← EventBus (subscribe/unsubscribe/publish,
│   │                             wildcard "*", error isolation, BusStats)
│   ├── scheduler.py           ← Scheduler (heapq priority queue, adaptive tick
│   │                             100/500/2000ms, TaskPriority CRITICAL→IDLE,
│   │                             tick_start/tick_end/task_done/task_failed events)
│   └── resource_monitor.py    ← ResourceMonitor (psutil, daemon thread,
│                                 NORMAL/DEGRADED/CRITICAL/EMERGENCY policies,
│                                 hysteresis soft_blocked/ring2_allowed,
│                                 inject_state() для тестов)
└── memory/
    ├── working_memory.py       ← WorkingMemory + MemoryItem
    ├── semantic_memory.py      ← SemanticMemory + SemanticNode + Relation
    ├── episodic_memory.py      ← EpisodicMemory + Episode + ModalEvidence
    ├── source_memory.py        ← SourceMemory + SourceRecord
    ├── procedural_memory.py    ← ProceduralMemory + Procedure + ProcedureStep
    ├── consolidation_engine.py ← ConsolidationEngine + ConsolidationConfig
    ├── memory_manager.py       ← MemoryManager + MemorySearchResult
    └── __init__.py             ← экспорты всех 14 классов

brain/logging/
├── brain_logger.py         ← BrainLogger (JSONL, 5 уровней, категорийные файлы,
│                              in-memory индекс trace_id/session_id, ротация 100 MB)
├── digest_generator.py     ← DigestGenerator + CycleInfo (cycle/session digests,
│                              запись в digests/YYYY-MM-DD.txt)
├── reasoning_tracer.py     ← TraceBuilder (start/add_step/finish, reconstruct,
│                              reconstruct_from_logger, to_human_readable)
│                              (renamed from trace_builder.py to avoid conflict with output/)
└── __init__.py             ← экспорты: BrainLogger, DigestGenerator, CycleInfo, TraceBuilder

brain/perception/
├── text_ingestor.py        ← TextIngestor (.txt/.md/.pdf/.docx/.json/.csv → PerceptEvent,
│                              paragraph-aware chunking 1000–1500 chars, overlap 120)
├── metadata_extractor.py   ← MetadataExtractor (language ru/en/mixed/unknown,
│                              quality 0.0–1.0, quality_label, should_reject)
├── input_router.py         ← InputRouter (SHA256 dedup, quality policy,
│                              image/audio/video → warning+skip MVP)
└── __init__.py             ← экспорты: TextIngestor, MetadataExtractor, InputRouter

brain/encoders/
├── text_encoder.py         ← TextEncoder (sentence-transformers 768d / navec 300d,
│                              encode_event/encode/encode_batch, L2 norm,
│                              SHA256 cache, language/message_type/keywords,
│                              graceful degradation: ok/fallback/degraded/failed)
└── __init__.py             ← экспорты: TextEncoder

tests/
├── conftest.py             ← pytest fixtures + sys.path
├── test_memory.py          ← 101/101 тестов ✅
├── test_scheduler.py       ← 11/11 тестов ✅
├── test_resource_monitor.py← 13/13 тестов ✅
├── test_logging.py         ← 25/25 тестов ✅
├── test_perception.py      ← 79/79 тестов ✅
└── test_text_encoder.py    ← 80/80 тестов ✅

brain/cognition/
├── context.py              ← CognitiveContext, CognitiveOutcome, EvidencePack,
│                              GoalTypeLimits, PolicyConstraints, ReasoningState,
│                              GOAL_TYPE_LIMITS, NORMAL_OUTCOMES, FAILURE_OUTCOMES
├── goal_manager.py         ← GoalStatus, Goal, GoalManager (push/complete/fail/
│                              cancel/interrupt/resume, priority queue + tree)
├── planner.py              ← PlanStep, ExecutionPlan, Planner (decompose 4 templates,
│                              check_stop_conditions, replan with 5 strategies)
├── hypothesis_engine.py    ← Hypothesis, HypothesisEngine (associative + deductive
│                              + causal + analogical, max 3, stable sort, score/rank)
├── reasoner.py             ← ReasoningStep, ReasoningTrace, Reasoner
│                              (retrieve → hypothesize → score → select loop)
├── action_selector.py      ← ActionType (5 types), ActionDecision, ActionSelector
│                              (RESPOND_DIRECT/HEDGED/ASK/REFUSE/LEARN)
├── cognitive_core.py       ← CognitiveCore — orchestrator (run → CognitiveResult,
│                              goal detection, EventBus publish, trace chain,
│                              HybridRetrievalBackend vector bridge)
├── retrieval_adapter.py    ← RetrievalAdapter, KeywordRetrievalBackend,
│                              VectorRetrievalBackend, HybridRetrievalBackend (F+)
├── contradiction_detector.py ← Contradiction, ContradictionDetector (F+)
├── uncertainty_monitor.py  ← UncertaintySnapshot, UncertaintyMonitor (F+)
└── __init__.py             ← экспорты 30 классов

tests/
├── test_cognition.py           ← 182/182 unit тестов ✅
├── test_cognition_integration.py ← 7/7 integration smoke тестов ✅
└── test_vector_retrieval.py    ← 39/39 тестов ✅

brain/output/
├── trace_builder.py        ← ExplainabilityTrace (dataclass, ContractMixin),
│                              OutputTraceBuilder (build → trace, to_digest, to_json,
│                              uncertainty levels: very_low/low/medium/high/very_high)
├── response_validator.py   ← ValidationIssue, ValidationResult, ResponseValidator
│                              (empty check, hedge check, length check, language check,
│                              FALLBACK_RESPONSE_RU/EN, HEDGE_MARKERS_RU/EN)
├── dialogue_responder.py   ← DialogueResponder (generate → BrainOutput, hedging phrases
│                              5 confidence bands, fallback templates per ActionType,
│                              MVP: template-only, TODO: LLM bridge Stage H+),
│                              OutputPipeline (trace_builder → validator → responder)
└── __init__.py             ← экспорты 13 классов

tests/
├── test_output.py              ← 106/106 unit тестов ✅
└── test_output_integration.py  ← 7/7 integration smoke тестов ✅
```

### Следующий шаг: завершение F+ (тесты) → Этап H — Attention & Resource Control

**F+ осталось:** Steps 10-12 — ~90 unit тестов, ~5 integration тестов, bump v0.7.0

```
brain/attention/
├── attention_controller.py ← AttentionController (goal-driven + salience-driven)
├── modality_router.py      ← ModalityRouter (маршрутизация по приоритету)
├── load_balancer.py        ← CognitiveLoadBalancer (балансировка нагрузки)
└── __init__.py             ← экспорты
```
