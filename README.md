# 🧠 Cognitive Core

[![CI](https://github.com/whatisdantes/cognitive-core/actions/workflows/ci.yml/badge.svg)](https://github.com/whatisdantes/cognitive-core/actions/workflows/ci.yml)
[![Docs workflow](https://github.com/whatisdantes/cognitive-core/actions/workflows/docs.yml/badge.svg)](https://github.com/whatisdantes/cognitive-core/actions/workflows/docs.yml)
[![codecov](https://codecov.io/gh/whatisdantes/cognitive-core/graph/badge.svg)](https://codecov.io/gh/whatisdantes/cognitive-core)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-github%20pages-blue.svg)](https://whatisdantes.github.io/cognitive-core/)

> **Версия:** 0.7.0  
> **Статус:** 🚧 В разработке — MVP Phase A ✅, Phase B ✅, Phase C ✅, P0/P1/P2 ✅, H/I/N/J/K/L/M ✅  
> **Платформа:** CPU-only · AMD Ryzen 7 5700X · 32 GB DDR4  
> **CI/CD:** GitHub Actions (Python 3.11/3.12/3.13, pytest + pytest-cov, ruff lint, mypy)  
> **Тестовый набор:** 2311 collected в текущем дереве · **Ruff/Mypy/Bandit:** проверяются в CI · **Coverage gate:** 70%

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

```bash
# 1. Клонировать и установить
git clone https://github.com/whatisdantes/cognitive-core.git
cd cognitive-core
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -e ".[dev]"

# Полный набор optional extras
pip install -e ".[all]"

# SQLCipher отдельно
pip install -e ".[encrypted]"

# 2. Задать вопрос через CLI
cognitive-core "Что такое нейропластичность?"

# 3. Запустить тесты
python -m pytest tests/ -v

# 4. Автономный режим (Scheduler-driven)
cognitive-core --autonomous --ticks 5

# 5. С BrainLogger (JSONL-логи в директорию)
cognitive-core --log-dir brain/data/logs --log-level DEBUG "Что такое нейрон?"

# 6. Docker (опционально)
docker build -t cognitive-core .
docker run cognitive-core "Что такое нейрон?"
```

### Программный API

```python
from brain.core import EventBus, ResourceMonitor
from brain.memory import MemoryManager
from brain.cognition import CognitiveCore
from brain.output import OutputPipeline

bus = EventBus()
rm  = ResourceMonitor(event_bus=bus)
mm  = MemoryManager(data_dir="brain/data/memory", auto_consolidate=False)
mm.start()

core = CognitiveCore(memory_manager=mm, event_bus=bus, resource_monitor=rm)
result = core.run("Что такое нейрон?")

pipeline = OutputPipeline()
output = pipeline.process(result)
print(output.text)

mm.stop()
```

> ⚠️ **Retrieval scope (v0.7.0):** поиск по памяти использует keyword BM25 + hybrid vector retrieval (in-memory cosine similarity).
> При инициализации CognitiveCore автоматически строит vector index из персистентного корпуса памяти (SemanticMemory + EpisodicMemory).
> Новые факты индексируются инкрементально при LEARN. Persisted ANN/FAISS индексы запланированы на Post-MVP.
> Без предварительно загруженных данных в памяти ответы будут шаблонными.

### Матрица возможностей (v0.7.0)

| Возможность | Статус | Описание |
|-------------|--------|----------|
| Текстовый ввод (txt/md/pdf/docx/json) | ✅ Реализовано | Полный pipeline восприятия |
| Text Encoder (sentence-transformers/navec) | ✅ Реализовано | 768d/300d векторизация |
| Hybrid Retrieval (BM25 + Vector) | ✅ Реализовано | Keyword + cosine similarity |
| 5 видов памяти (WM/SM/EM/Source/Procedural) | ✅ Реализовано | JSON + SQLite persistence |
| Когнитивное ядро (Goal→Plan→Reason→Act) | ✅ Реализовано | 20-step CognitivePipeline |
| Обнаружение противоречий | ✅ Реализовано | ContradictionDetector |
| Мониторинг неопределённости | ✅ Реализовано | UncertaintyMonitor |
| Output Layer (trace + validation + dialogue) | ✅ Реализовано | Template MVP |
| CLI entrypoint | ✅ Реализовано | `cognitive-core "вопрос"` + `--autonomous` mode |
| Docker (multi-stage + non-root) | ✅ Реализовано | Python 3.12-slim |
| CI/CD (GitHub Actions) | ✅ Реализовано | pytest + coverage + ruff + mypy |
| Attention & Resource Control | ✅ Реализовано | SalienceEngine, AttentionController, PolicyLayer (Этап H) |
| LLM Bridge | ✅ Реализовано | OpenAI/Anthropic/Blackbox providers, safety wrapper (Этап N) |
| BrainLogger Integration | ✅ Реализовано | JSONL-логи через `--log-dir`/`--log-level` |
| Learning Loop | ✅ Реализовано | OnlineLearner + KnowledgeGapDetector + ReplayEngine + интеграция в pipeline (Этап I) |
| Vision/Audio/Temporal Encoders + EncoderRouter | ✅ Реализовано | VisionEncoder, AudioEncoder, TemporalEncoder, EncoderRouter (Этап J) |
| Vision/Audio Ingestors | ✅ Реализовано | VisionIngestor, AudioIngestor (Этап J) |
| Cross-Modal Fusion | ✅ Реализовано | SharedSpaceProjector, EntityLinker, ConfidenceCalibrator, CrossModalContradictionDetector (Этап K) |
| Safety & Boundaries | ✅ Реализовано | BoundaryGuard, AuditLogger, SourceTrustManager, ConflictDetector, SafetyPolicyLayer (Этап L) |
| Reward & Motivation | ✅ Реализовано | RewardEngine, MotivationEngine, CuriosityEngine (Этап M) |

> 📖 Полная архитектурная спецификация: [`BRAIN.md`](docs/BRAIN.md)  
> 📋 **Единый план реализации (MVP + Post-MVP):** [`docs/planning/TODO.md`](docs/planning/TODO.md)  
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

Система работает с текстовыми данными (MVP), с планами на мультимодальность:
- 📄 **Документы** (`.txt`, `.md`, `.pdf`, `.docx`, `.json`) — ✅ реализовано
- 🖼️ Изображения (OCR + понимание сцен) — ✅ Реализовано (Этап J, VisionIngestor + VisionEncoder)
- 🎙️ Аудио (ASR + временные метки) — ✅ Реализовано (Этап J, AudioIngestor + AudioEncoder)
- 🎬 Видео (покадровый анализ + временное отслеживание) — ✅ Реализовано (Этап J, TemporalEncoder)

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

| Модуль | Модель (основная) | Размер | Fallback | Статус |
|--------|------------------|--------|----------|--------|
| Text Encoder | sentence-transformers large | ~1.3 GB | navec (~200 MB) | ✅ Реализовано |
| Vision Encoder | CLIP ViT-B/32 | ~600 MB | ResNet-50 (~100 MB) | ✅ Реализовано (Этап J, CPU-only stub) |
| Audio ASR | Whisper medium | ~1.5 GB | Whisper base (~150 MB) | ✅ Реализовано (Этап J, CPU-only stub) |

> ℹ️ Vision/Audio энкодеры реализованы как CPU-only stubs (Этап J). Реальные модели (CLIP, Whisper) подключаются через graceful degradation при наличии зависимостей.

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
│   ├─ TextIngestor             ✅ txt / md / pdf / docx / json
│   ├─ VisionIngestor           ✅ img / video frames + OCR (Этап J)
│   ├─ AudioIngestor            ✅ ASR + acoustic events (Этап J)
│   ├─ MetadataExtractor        ✅ source, timestamp, quality, language
│   └─ InputRouter              ✅ маршрутизация по типу модальности
│
├─ 2. Modality Encoders         ← Сенсорная кора (векторизация)
│   ├─ TextEncoder              ✅ sentence-transformers (768d/1024d)
│   ├─ VisionEncoder            ✅ CLIP ViT-B/32 (512d) (Этап J)
│   ├─ AudioEncoder             ✅ Whisper medium + MFCC (Этап J)
│   ├─ TemporalEncoder          ✅ позиционное кодирование (видео) (Этап J)
│   └─ EncoderRouter            ✅ маршрутизация по модальности (Этап J)
│
├─ 3. Cross-Modal Fusion        ← Ассоциативная кора (слияние) ✅ Этап K
│   ├─ SharedSpaceProjector     ✅ единое латентное пространство
│   ├─ EntityLinker             ✅ связывание сущностей из разных источников
│   ├─ ConfidenceCalibrator     ✅ оценка качества слияния
│   └─ CrossModalContradictionDetector ✅ обнаружение противоречий между модальностями
│
├─ 4. Memory System             ← Гиппокамп + Кора (память)
│   ├─ WorkingMemory            активный контекст (sliding window, max=20)
│   ├─ SemanticMemory           граф понятий и связей (BFS, JSON)
│   ├─ EpisodicMemory           хронология событий (кросс-модальные записи)
│   ├─ SourceMemory             доверие к источникам (trust score, blacklist)
│   ├─ ProceduralMemory         навыки и стратегии (success rate tracking)
│   ├─ ConsolidationEngine      WM → LTM (фоновый поток, RAM-aware)
│   └─ MemoryManager            единый интерфейс store()/retrieve()
│
├─ 5. Cognitive Core            ← Префронтальная кора (мышление)
│   ├─ GoalManager              ✅ управление целями (создание, приоритизация, завершение)
│   ├─ Planner                  ✅ декомпозиция целей на шаги + выбор стратегии
│   ├─ HypothesisEngine         ✅ генерация и оценка гипотез (causal/associative/analogical)
│   ├─ Reasoner                 ✅ reasoning loop (retrieve → hypothesize → score → act)
│   ├─ ContradictionDetector    ✅ поиск конфликтующих фактов
│   ├─ UncertaintyMonitor       ✅ оценка уверенности по гипотезам
│   ├─ SalienceEngine           ✅ оценка значимости (аналог Миндалины) (Этап H)
│   └─ ActionSelector           ✅ выбор действия (аналог Базальных ганглий)
│
├─ 6. Learning Loop             ← Мозжечок + Гиппокамп (обучение) ✅ Этап I
│   ├─ OnlineLearner            ✅ обновление после каждого взаимодействия
│   ├─ ReplayEngine             ✅ периодическое воспроизведение эпизодов
│   ├─ KnowledgeGapDetector     ✅ выявление пробелов в знаниях
│   ├─ SelfSupervisedLearner    🔮 согласованность картинка ↔ текст ↔ аудио
│   └─ HypothesisEngine         ✅ генерация и проверка гипотез (в cognition/)
│
├─ 7. Output Layer              ← Речевые зоны (вывод)
│   ├─ DialogueResponder        ✅ текстовый ответ + объяснение + confidence
│   ├─ ActionProposer           🔮 предложение действий с обоснованием (Post-MVP)
│   └─ TraceBuilder             ✅ полная цепочка причинности
│
├─ 8. Attention & Resources     ← Таламус + Гипоталамус ✅ Этап H
│   ├─ AttentionController      ✅ goal-driven + salience-driven внимание
│   ├─ SalienceEngine           ✅ оценка значимости (аналог Миндалины)
│   ├─ PolicyLayer              ✅ политики когнитивного цикла
│   ├─ ModalityRouter           🔮 маршрутизация по приоритету
│   ├─ CognitiveLoadBalancer    🔮 балансировка нагрузки
│   └─ DegradationPolicy        ✅ политика деградации (в ResourceMonitor)
│
├─ 9. Logging & Observability   ← Метапознание
│   ├─ BrainLogger              JSONL-логгер (одна строка = одно событие)
│   ├─ DigestGenerator          human-readable сводка по циклу
│   ├─ TraceBuilder             trace chain для каждого решения
│   └─ MetricsCollector         KPI метрики в реальном времени
│
├─ 10. Safety & Boundaries      ← Иммунная система ✅ Этап L
│   ├─ SourceTrustManager       ✅ оценка надёжности источников (Этап L)
│   ├─ ConflictDetector         ✅ детектор конфликтов фактов (Этап L)
│   ├─ BoundaryGuard            ✅ ограничения на действия системы (Этап L)
│   ├─ AuditLogger              ✅ аудит решений с высоким риском (Этап L)
│   └─ SafetyPolicyLayer        ✅ политики безопасности SF-1/2/3 (Этап L)
│
└─ 11. Reward & Motivation      ← Средний мозг (дофаминовая система) ✅ Этап M
    ├─ RewardEngine             ✅ 5 типов вознаграждения + prediction error
    ├─ MotivationEngine         ✅ накопление reward signals, decay мотивации
    └─ CuriosityEngine          ✅ любопытство ∝ 1/knowledge_coverage
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
│   │   ├── event_bus.py                # ✅ EventBus + ThreadPoolEventBus — typed pub/sub шина событий
│   │   ├── scheduler.py                # ✅ Scheduler — тик-планировщик (heapq, 4 приоритета, адаптивный tick)
│   │   ├── resource_monitor.py         # ✅ ResourceMonitor — CPU/RAM мониторинг, 4 политики деградации
│   │   ├── text_utils.py               # ✅ detect_language(), parse_fact_pattern() — Phase C canonical
│   │   └── hash_utils.py              # ✅ sha256_text(), sha256_file() — Phase C canonical
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
│   ├── cli.py                          # ✅ CLI entrypoint (cognitive-core "вопрос") — MVP Phase A
│   │
│   ├── perception/                     # Слой восприятия ✅ РЕАЛИЗОВАНО (Этап D + B.2 hardening)
│   │   ├── __init__.py                 # Экспорты: MetadataExtractor, TextIngestor, InputRouter, validators
│   │   ├── metadata_extractor.py       # ✅ MetadataExtractor — quality scoring, language detection
│   │   ├── text_ingestor.py            # ✅ TextIngestor — .txt/.md/.pdf/.docx/.json/.csv + path/size guards
│   │   ├── input_router.py             # ✅ InputRouter — SHA256 dedup, quality policy + path/size guards
│   │   └── validators.py              # ✅ validate_file_path(), check_file_size() — B.2 hardening
│   │
│   ├── encoders/                       # Модальные энкодеры ✅ РЕАЛИЗОВАНО (Этап E + J)
│   │   ├── __init__.py                 # Экспорты: TextEncoder, VisionEncoder, AudioEncoder, TemporalEncoder, EncoderRouter
│   │   ├── text_encoder.py             # ✅ TextEncoder — sentence-transformers 768d / navec 300d fallback
│   │   ├── vision_encoder.py           # ✅ VisionEncoder — CLIP ViT-B/32 CPU-only stub (Этап J)
│   │   ├── audio_encoder.py            # ✅ AudioEncoder — Whisper/MFCC CPU-only stub (Этап J)
│   │   ├── temporal_encoder.py         # ✅ TemporalEncoder — позиционное кодирование видео (Этап J)
│   │   └── encoder_router.py           # ✅ EncoderRouter — маршрутизация по модальности (Этап J)
│   │
│   ├── fusion/                         # Кросс-модальное слияние ✅ РЕАЛИЗОВАНО (Этап K)
│   │   ├── __init__.py                 # Экспорты: SharedSpaceProjector, EntityLinker, ConfidenceCalibrator, CrossModalContradictionDetector
│   │   ├── shared_space_projector.py   # ✅ SharedSpaceProjector — единое латентное пространство
│   │   ├── entity_linker.py            # ✅ EntityLinker — связывание сущностей из разных источников
│   │   ├── confidence_calibrator.py    # ✅ ConfidenceCalibrator — оценка качества слияния
│   │   └── cross_modal_contradiction_detector.py # ✅ CrossModalContradictionDetector (Этап K)
│   │
│   ├── cognition/              # Когнитивное ядро ✅ РЕАЛИЗОВАНО (Этап F + F+ + P3 + H + L)
│   │   ├── __init__.py                 # Экспорты: 35+ классов
│   │   ├── context.py                  # ✅ CognitiveContext, CognitiveOutcome, EvidencePack,
│   │   │                               #    GoalTypeLimits, PolicyConstraints, ReasoningState,
│   │   │                               #    UncertaintyTrend, ReplanStrategy
│   │   ├── goal_manager.py             # ✅ GoalStatus, Goal, GoalManager
│   │   ├── planner.py                  # ✅ PlanStep, ExecutionPlan, Planner (5 replan strategies)
│   │   ├── hypothesis_engine.py        # ✅ Hypothesis, HypothesisEngine (assoc+deduct+causal+analog)
│   │   ├── reasoner.py                 # ✅ ReasoningStep, ReasoningTrace, Reasoner
│   │   ├── action_selector.py          # ✅ ActionType, ActionDecision, ActionSelector
│   │   ├── cognitive_core.py           # ✅ CognitiveCore — orchestrator (delegates to CognitivePipeline)
│   │   ├── pipeline.py                 # ✅ CognitivePipeline (20 шагов) + CognitivePipelineContext (P3-10 + Этап L)
│   │   ├── retrieval_adapter.py        # ✅ RetrievalAdapter, KeywordRetrievalBackend (BM25 reranking),
│   │   │                               #    VectorRetrievalBackend, HybridRetrievalBackend, BM25Scorer
│   │   ├── contradiction_detector.py   # ✅ Contradiction, ContradictionDetector (F+)
│   │   ├── salience_engine.py          # ✅ SalienceEngine — оценка значимости (Этап H)
│   │   ├── policy_layer.py             # ✅ PolicyLayer — политики когнитивного цикла (Этап H)
│   │   └── uncertainty_monitor.py      # ✅ UncertaintySnapshot, UncertaintyMonitor (F+)
│   │
│   ├── bridges/                        # LLM Bridge ✅ РЕАЛИЗОВАНО (Этап N)
│   │   ├── __init__.py                 # Экспорты: LLMBridge, OpenAIProvider, AnthropicProvider, BlackboxProvider
│   │   ├── llm_bridge.py              # ✅ LLMBridge + providers (OpenAI/Anthropic/Blackbox)
│   │   └── safety_wrapper.py          # ✅ SafetyWrapper — фильтрация LLM ответов
│   │
│   ├── learning/                       # Система обучения ✅ РЕАЛИЗОВАНО (Этап I)
│   │   ├── __init__.py
│   │   ├── online_learner.py           # ✅ OnlineLearner — обновление после взаимодействия
│   │   ├── knowledge_gap_detector.py   # ✅ KnowledgeGapDetector — выявление пробелов
│   │   └── replay_engine.py            # ✅ ReplayEngine — воспроизведение эпизодов
│   │
│   ├── logging/                        # Логирование ✅ РЕАЛИЗОВАНО (Этап C)
│   │   ├── __init__.py                 # Экспорты: BrainLogger, DigestGenerator, CycleInfo, TraceBuilder
│   │   ├── brain_logger.py             # ✅ BrainLogger — JSONL, 5 уровней, категорийные файлы, индекс
│   │   ├── digest_generator.py         # ✅ DigestGenerator + CycleInfo — human-readable сводки
│   │   └── reasoning_tracer.py         # ✅ TraceBuilder — trace chain, reconstruct_from_logger
│   │                                   #    (renamed from trace_builder.py to avoid conflict with output/)
│   │
│   ├── safety/                         # Safety & Boundaries ✅ РЕАЛИЗОВАНО (Этап L)
│   │   ├── __init__.py                 # Экспорты: AuditLogger, SourceTrustManager, ConflictDetector, BoundaryGuard, SafetyPolicyLayer
│   │   ├── audit_logger.py             # ✅ AuditLogger — JSONL аудит, ротация, RLock
│   │   ├── source_trust.py             # ✅ SourceTrustManager — оценка надёжности источников
│   │   ├── conflict_detector.py        # ✅ ConflictDetector — детектор конфликтов фактов
│   │   ├── boundary_guard.py           # ✅ BoundaryGuard — PII redaction, confidence gate, action gate
│   │   └── policy_layer.py             # ✅ SafetyPolicyLayer — политики SF-1/2/3
│   │
│   ├── motivation/                     # Reward & Motivation ✅ РЕАЛИЗОВАНО (Этап M)
│   │   ├── __init__.py                 # Экспорты: RewardEngine, MotivationEngine, CuriosityEngine
│   │   ├── reward_engine.py            # ✅ RewardEngine — 5 типов вознаграждения + prediction error
│   │   ├── motivation_engine.py        # ✅ MotivationEngine — EMA α=0.1, decay ×0.95/100 циклов
│   │   └── curiosity_engine.py         # ✅ CuriosityEngine — score=1/max(coverage,0.01), threshold=0.8
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
├── examples/                           # Примеры использования
│   └── demo.py                         # ✅ Демо: полный pipeline в 30 строк
│
├── CONTRIBUTING.md                     # ✅ Гайд для контрибьюторов — P3-2
├── tests/                              # Тесты (pytest-совместимые, 2311 collected в текущем дереве)
│   ├── conftest.py                     # Общая конфигурация pytest + fixtures
│   ├── test_bm25.py                    # ✅ 55/55 тестов BM25 Scorer + KeywordBackend reranking
│   ├── test_cli.py                    # ✅ 20/20 тестов CLI entrypoint (Phase A)
│   ├── test_cognition.py             # ✅ 190/190 тестов Cognitive Core (unit + auto-encode)
│   ├── test_cognition_integration.py  # ✅ 7/7 тестов Cognitive Core (integration)
│   ├── test_e2e_pipeline.py           # ✅ 10/10 тестов E2E Pipeline
│   ├── test_golden.py                 # ✅ 414/414 тестов Golden-answer benchmarks (Phase B.5)
│   ├── test_logging.py                 # ✅ 25/25 тестов Logging & Observability (unittest)
│   ├── test_memory.py                  # ✅ 101/101 тестов системы памяти
│   ├── test_output.py                 # ✅ 106/106 тестов Output Layer (unit)
│   ├── test_output_integration.py     # ✅ 7/7 тестов Output Layer (integration)
│   ├── test_perception.py              # ✅ 79/79 тестов Perception Layer
│   ├── test_perception_hardening.py   # ✅ 34/34 тестов Perception Hardening (Phase B.2)
│   ├── test_resource_monitor.py        # ✅ 13/13 тестов ResourceMonitor
│   ├── test_scheduler.py              # ✅ 11/11 тестов Scheduler
│   ├── test_storage.py                # ✅ 58/58 тестов SQLite Storage + Migration
│   ├── test_text_encoder.py           # ✅ 80/80 тестов Text Encoder
│   ├── test_utils.py                  # ✅ 63/63 тестов text_utils + hash_utils (Phase C)
│   ├── test_vector_retrieval.py       # ✅ 60/60 тестов Vector Retrieval + Index Population
│   ├── test_persistence_integration.py # ✅ 6/6 тестов Persistence Integration (P2-20)
│   ├── test_contracts_hypothesis.py   # ✅ 4/4 тестов Property-based roundtrip (P3-6)
│   ├── test_concurrency_stress.py     # ✅ 3/3 тестов Concurrent stress (P3-8)
│   ├── test_attention_controller.py   # ✅ AttentionController (Этап H)
│   ├── test_salience_engine.py        # ✅ SalienceEngine (Этап H)
│   ├── test_policy_layer.py           # ✅ PolicyLayer (Этап H)
│   ├── test_llm_bridge.py            # ✅ LLM Bridge (Этап N)
│   ├── test_online_learner.py         # ✅ OnlineLearner (Этап I)
│   ├── test_knowledge_gap_detector.py # ✅ KnowledgeGapDetector (Этап I)
│   ├── test_replay_engine.py          # ✅ ReplayEngine (Этап I)
│   └── test_storage_encrypted.py      # ✅ SQLCipher encryption (P3-12, optional extra `encrypted`)
│
├── docs/                               # Документация
│   ├── BRAIN.md                        # Архитектурная спецификация (15 разделов)
│   ├── adr/                            # ✅ Architecture Decision Records (P3-4)
│   │   ├── README.md                   # Индекс ADR
│   │   ├── ADR-001-sqlite-as-default-backend.md
│   │   ├── ADR-002-threading-rlock-for-memory.md
│   │   ├── ADR-003-protocol-types-for-di.md
│   │   ├── ADR-004-bm25-hybrid-retrieval.md
│   │   ├── ADR-005-template-responses-no-llm.md
│   │   ├── ADR-006-event-bus-sync-snapshot.md
│   │   └── ADR-007-cpu-only-platform.md
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
├── .dockerignore                       # Docker ignore rules
├── Dockerfile                          # ✅ Multi-stage Docker build (Phase A.1b)
├── pyproject.toml                      # Конфигурация проекта + зависимости + pytest + [project.scripts]
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
# Ядро (обязательные)
numpy>=1.26.0
jsonlines>=4.0.0
psutil>=5.9.0
tqdm>=4.66.0

# Документы
pymupdf>=1.24.0
python-docx>=1.1.0

# Русский язык (NLP)
pymorphy3>=1.0.0               # лемматизация для BM25
razdel>=0.5.0                  # токенизация
nltk>=3.8.0                    # стоп-слова

# Text Encoder (опционально — graceful fallback)
sentence-transformers>=2.7.0   # основной (~1.3 GB при первом запуске)
navec>=0.10.0                  # fallback text encoder (~200 MB)

# Dev
pytest>=8.0
pytest-cov>=4.0
ruff>=0.4.0
mypy>=1.10

# ─── Этап J (реализованы как CPU-only stubs, реальные модели опциональны) ───
# open-clip-torch>=2.24.0      # Vision Encoder (CLIP ViT-B/32) — опционально
# pillow>=10.0.0               # Image processing — опционально
# openai-whisper>=20231117     # Audio ASR (Whisper) — опционально
# torch>=2.2.0                 # PyTorch CPU-only — опционально
```

---

## 🚀 Установка

### Требования

- Python 3.11+
- Windows 10/11, Linux или macOS
- 4 GB RAM минимум (32 GB рекомендуется для полного стека)
- ~500 MB свободного места (+ ~1.3 GB для sentence-transformers при первом запуске)

### Установка

```bash
# Создать виртуальное окружение
python -m venv .venv

# Активировать (Windows)
.venv\Scripts\activate

# Активировать (Linux/macOS)
source .venv/bin/activate

# Установить проект с dev-зависимостями
pip install -e ".[dev]"

# Полный набор optional extras, включая SQLCipher
pip install -e ".[all]"

# Только SQLCipher
pip install -e ".[encrypted]"

# Или минимальная установка (только ядро)
pip install -e .
```

> **Рекомендуемый способ установки:** `pip install -e ".[dev]"`
>
> `.[all]` включает optional extras для NLP, vision, audio, docs, API docs, OpenAI, Anthropic и SQLCipher.

---

## ▶️ Запуск тестов

```bash
# Активировать окружение
.venv\Scripts\activate

# Запустить все тесты
python -m pytest tests/ -v

# Или отдельный файл
python -m pytest tests/test_memory.py -v

# С покрытием
python -m pytest tests/ --cov=brain --cov-report=term-missing
```

### Состав тестового набора

В текущем рабочем дереве `pytest` собирает 2311 тестов. Точный total может меняться по мере развития проекта, поэтому ниже приведён состав набора по файлам, а актуальный status лучше сверять по CI и локальному `pytest --collect-only`.

| Файл | Модуль | Тестов |
|------|--------|--------|
| `test_bm25.py` | BM25 Scorer + KeywordBackend reranking | 55 |
| `test_cli.py` | CLI entrypoint (argparse, pipeline assembly, error handling) | 20 |
| `test_cognition.py` | Cognitive Core (unit + auto-encode) | 190 |
| `test_cognition_integration.py` | Cognitive Core (integration, real MemoryManager) | 7 |
| `test_e2e_pipeline.py` | E2E Pipeline (protocol conformance + full pipeline) | 10 |
| `test_golden.py` | Golden-answer benchmarks (20 Q&A × 7 checks + pipeline + round-trip) | 414 |
| `test_logging.py` | Logging & Observability (BrainLogger, DigestGenerator, TraceBuilder) | 25 |
| `test_memory.py` | Memory System (Events, WM, SM, EM, Source, Procedural, Manager) | 101 |
| `test_output.py` | Output Layer (Trace, Validator, Responder, Pipeline) | 106 |
| `test_output_integration.py` | Output Layer Integration (CognitiveCore → OutputPipeline) | 7 |
| `test_perception.py` | Perception Layer (MetadataExtractor, TextIngestor, InputRouter) | 79 |
| `test_perception_hardening.py` | Perception Hardening (path traversal, null bytes, symlinks, size) | 34 |
| `test_resource_monitor.py` | ResourceMonitor (policies, hysteresis, background thread) | 13 |
| `test_scheduler.py` | Scheduler (ticks, priorities, adaptive interval) | 11 |
| `test_storage.py` | SQLite Storage (CRUD, transactions, threads, migration) | 58 |
| `test_text_encoder.py` | Text Encoder (primary/fallback/failed, semantic, batch, cache) | 80 |
| `test_utils.py` | text_utils + hash_utils (Phase C DRY) | 63 |
| `test_vector_retrieval.py` | Vector Retrieval (Vector, Hybrid, cosine similarity, corpus population) | 60 |
| `test_persistence_integration.py` | Persistence Integration (SQLite round-trip) | 6 |
| `test_contracts_hypothesis.py` | Property-based roundtrip (Hypothesis) | 4 |
| `test_concurrency_stress.py` | Concurrent stress (EventBus + Scheduler) | 3 |
| `test_storage_encrypted.py` | SQLCipher encryption at rest (P3-12) | 6+5* |
| `test_attention_controller.py` | AttentionController + budgets (Этап H) | 10 |
| `test_salience_engine.py` | SalienceEngine + scoring (Этап H) | 12 |
| `test_policy_layer.py` | PolicyLayer filters + modifiers (Этап H) | 9 |
| `test_brain_logger_integration.py` | BrainLogger integration | 19 |
| `test_llm_bridge.py` | LLMBridge + providers + safety (Этап N) | 82 |
| `test_online_learner.py` | OnlineLearner (Этап I) | 12 |
| `test_knowledge_gap_detector.py` | KnowledgeGapDetector (Этап I) | 8 |
| `test_replay_engine.py` | ReplayEngine + strategies (Этап I) | 15 |
| `test_learning_integration.py` | Learning Loop Integration (OnlineLearner + KnowledgeGapDetector + ReplayEngine + CognitivePipeline) | 7 |
| `test_vision_ingestor.py` | VisionIngestor (Этап J) | 15 |
| `test_audio_ingestor.py` | AudioIngestor (Этап J) | 15 |
| `test_vision_encoder.py` | VisionEncoder (Этап J) | 20 |
| `test_audio_encoder.py` | AudioEncoder (Этап J) | 20 |
| `test_temporal_encoder.py` | TemporalEncoder (Этап J) | 20 |
| `test_encoder_router.py` | EncoderRouter (Этап J) | 19 |
| `test_shared_space_projector.py` | SharedSpaceProjector (Этап K) | 15 |
| `test_entity_linker.py` | EntityLinker (Этап K) | 15 |
| `test_confidence_calibrator.py` | ConfidenceCalibrator (Этап K) | 16 |
| `test_cross_modal_contradiction_detector.py` | CrossModalContradictionDetector (Этап K) | 15 |
| `test_audit_logger.py` | AuditLogger (Этап L) | 13 |
| `test_source_trust.py` | SourceTrustManager (Этап L) | 16 |
| `test_conflict_detector.py` | ConflictDetector (Этап L) | 19 |
| `test_boundary_guard.py` | BoundaryGuard (Этап L) | 26 |
| `test_safety_policy_layer.py` | SafetyPolicyLayer (Этап L) | 16 |
| `test_safety_integration.py` | Safety Integration (pipeline + safety) | 7 |
| `test_reward_engine.py` | RewardEngine (Этап M) | 28 |
| `test_motivation_engine.py` | MotivationEngine (Этап M) | 28 |
| `test_curiosity_engine.py` | CuriosityEngine (Этап M) | 28 |
| | **Итого** | **см. `pytest --collect-only`** |

> Тесты SQLCipher требуют установленного extra `encrypted` (`pip install -e ".[encrypted]"` или `pip install -e ".[all]"`).

---

## 📊 Логирование

### BrainLogger CLI

```bash
# Включить JSONL-логирование через CLI
cognitive-core --log-dir brain/data/logs "Что такое нейрон?"
cognitive-core --log-dir brain/data/logs --log-level DEBUG "вопрос"
cognitive-core --autonomous --ticks 10 --log-dir brain/data/logs --log-level INFO
```

Создаёт файлы в `brain/data/logs/`:
- `brain.jsonl` — все события
- `memory.jsonl` — операции с памятью
- `cognition.jsonl` — когнитивные шаги
- `safety_audit.jsonl` — события безопасности
- `digests/YYYY-MM-DD.txt` — human-readable сводки

### Формат события

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

Сайт документации: [https://whatisdantes.github.io/cognitive-core/](https://whatisdantes.github.io/cognitive-core/)

| Файл | Слой | Биологический аналог | Статус |
|------|------|---------------------|--------|
| [`00_autonomous_loop.md`](docs/layers/00_autonomous_loop.md) | Always-On Loop | Ствол мозга | ✅ Реализовано (Этап B) |
| [`01_perception_layer.md`](docs/layers/01_perception_layer.md) | Perception Layer | Таламус | ✅ Реализовано (Этап D, text-only) |
| [`02_modality_encoders.md`](docs/layers/02_modality_encoders.md) | Modality Encoders | Сенсорная кора | ✅ Реализовано (Этап E, text-only, 80/80) |
| [`03_cross_modal_fusion.md`](docs/layers/03_cross_modal_fusion.md) | Cross-Modal Fusion | Ассоциативная кора | ✅ Реализовано (Этап K, 61 тест) |
| [`04_memory_system.md`](docs/layers/04_memory_system.md) | Memory System | Гиппокамп + Кора | ✅ Реализовано (101/101) |
| [`05_cognitive_core.md`](docs/layers/05_cognitive_core.md) | Cognitive Core | Префронтальная кора | ✅ Реализовано (Этап F+F+, 190+7) |
| [`06_learning_loop.md`](docs/layers/06_learning_loop.md) | Learning Loop | Мозжечок + Гиппокамп | ✅ Реализовано (Этап I) |
| [`07_output_layer.md`](docs/layers/07_output_layer.md) | Output Layer | Речевые зоны Брока/Вернике | ✅ Реализовано (Этап G, 106+7) |
| [`08_attention_resource.md`](docs/layers/08_attention_resource.md) | Attention & Resources | Таламус + Гипоталамус | ✅ Реализовано (Этап H) |
| [`09_logging_observability.md`](docs/layers/09_logging_observability.md) | Logging & Observability | Метапознание | ✅ Реализовано (Этап C, 25/25) |
| [`10_safety_boundaries.md`](docs/layers/10_safety_boundaries.md) | Safety & Boundaries | Иммунная система | ✅ Реализовано (Этап L, 107 тестов) |
| [`11_midbrain_reward.md`](docs/layers/11_midbrain_reward.md) | Reward & Motivation | Средний мозг | ✅ Реализовано (Этап M, 84 теста) |

Архитектурная спецификация: [`BRAIN.md`](docs/BRAIN.md) (15 разделов)  
**Единый план реализации (MVP + Post-MVP):** [`docs/planning/TODO.md`](docs/planning/TODO.md)

---

## ✅ Прогресс реализации

> **Примечание:** Нумерация этапов ниже — историческая (из BRAIN.md).
> Актуальный roadmap с MVP-фазами: [`docs/planning/TODO.md`](docs/planning/TODO.md).

| Этап | Название | Статус | Тестов |
|------|----------|--------|--------|
| A | Core Infrastructure (events, contracts, bus, scheduler, monitor) | ✅ Завершено | 24 |
| B | Perception Layer (text-only) | ✅ Завершено | 79 |
| C | Logging & Observability | ✅ Завершено | 25 |
| D | Memory System (5 типов + consolidation) | ✅ Завершено | 101 |
| E | Modality Encoders (text-only) | ✅ Завершено | 80 |
| F/F+ | Cognitive Core (10-step pipeline + F+ extensions) | ✅ Завершено | 182+7 |
| G | Output Layer (trace, validation, dialogue) | ✅ Завершено | 106+7 |
| P0 | Audit fixes (ruff, e2e tests, protocol conformance) | ✅ Завершено | 10 |
| P1a | Quick wins (session_id, pytest-cov, deps sync, atexit, mypy) | ✅ Завершено | — |
| P1b | BM25 Retrieval Quality | ✅ Завершено | 55 |
| P1c | SQLite Persistence | ✅ Завершено | 58 |
| **MVP A** | **CLI, Docker, ResourceMonitor, mypy** | **✅ Завершено** | **20** |
| **MVP B** | **Auto-encode, Perception hardening, Golden benchmarks** | **✅ Завершено** | **456** |
| **MVP C** | **Critical DRY (text_utils, hash_utils)** | **✅ Завершено** | **63** |
| **P0 (new)** | **Critical Hardening (thread safety, vector retrieval)** | **✅ Завершено 7/7** | **1333** |
| **P1 (new)** | **High Priority (CI, types, Docker, lint)** | **✅ Завершено 14/14** | **1333** |
| **P2** | **Medium Priority (algorithms, infra, product quality)** | **✅ Завершено 20/20** | **1800** |
| **P3** | **Nice-to-have (DX, architecture, testing)** | **✅ 12/12** | **1800** |
| **H** | **Attention & Resource Control (SalienceEngine, AttentionController, PolicyLayer)** | **✅ Завершено 4/5** | **31 (в 1800)** |
| **N** | **LLM Bridge (OpenAI/Anthropic/Blackbox, safety wrapper, CLI)** | **✅ Завершено 5/5** | **82 (в 1812)** |
| **LOG** | **BrainLogger Integration (13 фаз)** | **✅ Завершено 13/13** | **19 (в 1800)** |
| **I** | **Learning Loop (OnlineLearner, KnowledgeGapDetector, ReplayEngine + интеграция)** | **✅ Завершено** | **42 (в 1800)** |
| **J** | **Vision/Audio/Temporal Encoders + Ingestors (VisionIngestor, AudioIngestor, VisionEncoder, AudioEncoder, TemporalEncoder, EncoderRouter)** | **✅ Завершено** | **109** |
| **K** | **Cross-Modal Fusion (SharedSpaceProjector, EntityLinker, ConfidenceCalibrator, CrossModalContradictionDetector)** | **✅ Завершено** | **61** |
| **L** | **Safety & Boundaries (AuditLogger, SourceTrustManager, ConflictDetector, BoundaryGuard, SafetyPolicyLayer + pipeline integration)** | **✅ Завершено** | **107** |
| **M** | **Reward & Motivation (RewardEngine, MotivationEngine, CuriosityEngine)** | **✅ Завершено** | **84** |

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
│   ├── resource_monitor.py    ← ResourceMonitor (psutil, daemon thread,
│   │                             NORMAL/DEGRADED/CRITICAL/EMERGENCY policies,
│   │                             hysteresis soft_blocked/ring2_allowed,
│   │                             inject_state() для тестов)
│   ├── text_utils.py          ← detect_language(), parse_fact_pattern() (Phase C canonical)
│   └── hash_utils.py          ← sha256_text(), sha256_file() (Phase C canonical)
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
├── cognitive_core.py       ← CognitiveCore — orchestrator (delegates to CognitivePipeline)
├── pipeline.py             ← CognitivePipeline (20 шагов) + CognitivePipelineContext (P3-10 + Этап L)
├── retrieval_adapter.py    ← RetrievalAdapter, KeywordRetrievalBackend,
│                              VectorRetrievalBackend, HybridRetrievalBackend (F+)
├── contradiction_detector.py ← Contradiction, ContradictionDetector (F+)
├── uncertainty_monitor.py  ← UncertaintySnapshot, UncertaintyMonitor (F+)
└── __init__.py             ← экспорты 32 класса

tests/
├── test_cognition.py           ← 190/190 unit тестов ✅
├── test_cognition_integration.py ← 7/7 integration smoke тестов ✅
└── test_vector_retrieval.py    ← 60/60 тестов ✅

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

### Следующий шаг

> 📋 Единый план реализации: [`docs/planning/TODO.md`](docs/planning/TODO.md)

**MVP Phase A** ✅ — CLI entrypoint, Docker, ResourceMonitor.snapshot(), mypy без `|| true`.  
**MVP Phase B** ✅ — Auto-encode, Perception hardening, Retrieval scope docs, README update, Golden-answer benchmarks (414 тестов).  
**MVP Phase C** ✅ — Critical DRY: `detect_language`, `parse_fact_pattern`, `sha256` вынесены в `brain/core/text_utils.py` и `brain/core/hash_utils.py` (63 теста).  
**P0 Hardening** ✅ — Thread safety (6 модулей), memory leaks, real vector/hybrid retrieval (60 тестов).  
**P1 Hardening** ✅ — CI coverage gate 70%, ruff rules (B/SIM/C4/RET/PIE), mypy 0 errors, Docker multi-stage + non-root, Protocol types.  
**P2 Hardening** ✅ — Алгоритмические оптимизации (BFS deque, batch_remove, min вместо sorted), локальные дефекты (UUID, ZeroDivisionError, decay), инфраструктура (Dependabot, Bandit, Codecov).  
**P3 (mostly done)** ✅ — DX (CONTRIBUTING, ADR, mkdocs, development docs), архитектура (CognitivePipeline 20 шагов, ThreadPoolEventBus, --autonomous CLI, SQLCipher), тестирование (Hypothesis, stress tests).  
**Этап H** ✅ — Attention & Resource Control (SalienceEngine, AttentionController, PolicyLayer).  
**Этап N** ✅ — LLM Bridge (OpenAI/Anthropic/Blackbox providers, safety wrapper, CLI integration).  
**Этап I** ✅ — Learning Loop (OnlineLearner, KnowledgeGapDetector, ReplayEngine — модули + интеграция в CognitivePipeline + CLI).  
**Этап J** ✅ — Vision/Audio/Temporal Encoders + Ingestors (VisionIngestor, AudioIngestor, VisionEncoder, AudioEncoder, TemporalEncoder, EncoderRouter — 109 тестов).  
**Этап K** ✅ — Cross-Modal Fusion (SharedSpaceProjector, EntityLinker, ConfidenceCalibrator, CrossModalContradictionDetector — 61 тест).  
**Этап L** ✅ — Safety & Boundaries (AuditLogger, SourceTrustManager, ConflictDetector, BoundaryGuard, SafetyPolicyLayer + интеграция в CognitivePipeline 20 шагов — 107 тестов).  
**Этап M** ✅ — Reward & Motivation (RewardEngine, MotivationEngine, CuriosityEngine — 84 теста).  
Roadmap: [`docs/planning/TODO.md`](docs/planning/TODO.md).
