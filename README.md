# 🧠 Искусственный Мультимодальный Мозг

> **Версия:** 0.1.0 — Foundation & Bootstrap  
> **Статус:** 🚧 В разработке (Фаза 0)  
> **Платформа:** CPU-only · AMD Ryzen 7 5700X · 32 GB DDR4

Проект по созданию **искусственного мозга**, вдохновлённого принципами человеческого мозга и адаптированного под цифровую среду. Система воспринимает, понимает, запоминает, рассуждает, учится и рефлексирует — автономно, без постоянного участия человека.

Это **не бот-ответчик**. Это когнитивный организм с внутренним состоянием, памятью и целями.

---

## 📋 Содержание

- [Концепция](#-концепция)
- [Целевая платформа](#-целевая-платформа)
- [Архитектура](#-архитектура)
- [Биологические аналоги](#-биологические-аналоги)
- [Структура проекта](#-структура-проекта)
- [Зависимости](#-зависимости)
- [Установка](#-установка)
- [Запуск](#-запуск)
- [Модули](#-модули)
- [Логирование](#-логирование)
- [Метрики качества](#-метрики-качества)
- [Roadmap](#-roadmap)
- [Прогресс реализации](#-прогресс-реализации)

---

## 💡 Концепция

Человеческий мозг — это сеть взаимосвязанных контуров, работающих **параллельно и асинхронно**:

1. Восприятие сигналов
2. Предобработка и распознавание
3. Смысловая интеграция
4. Оценка значимости / риска
5. Рабочая память и внимание
6. Выбор действия
7. Обучение по ошибке и подкреплению
8. Консолидация памяти

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
|-----------|---------------|
| CPU | AMD Ryzen 7 5700X — 8 ядер / 16 потоков, до 4.6 GHz |
| RAM | DDR4 32 GB, 3200 MHz |
| GPU | — (не используется) |
| Режим | ✅ **CPU-only** (`USE_GPU=False`) |

### Ресурсные лимиты

| Ресурс | Лимит для мозга | Порог деградации |
|--------|----------------|-----------------|
| RAM | ≤ 22 GB | > 28 GB → снизить частоту тиков |
| CPU | ≤ 70% avg | > 85% → graceful degradation |
| Потоки | 8–12 из 16 | оставить 4 потока для ОС |
| Модели | ≤ 3 GB суммарно | > 5 GB → выгружать неактивные |

### Модели и их размеры

| Модуль | Модель (основная) | Размер | Fallback |
|--------|------------------|--------|---------|
| Text Encoder | sentence-transformers large | ~1.3 GB | navec (~200 MB) |
| Vision Encoder | CLIP ViT-B/32 | ~600 MB | ResNet-50 (~100 MB) |
| Audio ASR | Whisper medium | ~1.5 GB | Whisper base (~150 MB) |
| **Итого** | | **~3.4 GB** | **~450 MB** |

> ⚠️ Модели загружаются автоматически при первом запуске.

---

## 🏗️ Архитектура

```
MULTIMODAL BRAIN
│
├─ 1. Perception Layer          ← Восприятие (аналог сенсорики)
│   ├─ Text Ingestor            txt / md / pdf / docx / json
│   ├─ Vision Ingestor          img / video frames + OCR
│   ├─ Audio Ingestor           ASR + acoustic events
│   └─ Metadata Extractor       source, timestamp, quality, language
│
├─ 2. Modality Encoders         ← Кодирование в векторы
│   ├─ Text Encoder             sentence-transformers (768d/1024d)
│   ├─ Vision Encoder           CLIP ViT-B/32 (512d)
│   ├─ Audio Encoder            Whisper medium + MFCC
│   └─ Temporal Encoder         позиционное кодирование (видео)
│
├─ 3. Cross-Modal Fusion        ← Слияние модальностей
│   ├─ Shared Latent Space      единое пространство для всех модальностей
│   ├─ Entity Linker            связывание сущностей из разных источников
│   └─ Confidence Calibrator    оценка качества слияния
│
├─ 4. Memory System             ← Многоуровневая память
│   ├─ Working Memory           активный контекст (~7 элементов)
│   ├─ Episodic Memory          события во времени + кросс-модальные записи
│   ├─ Semantic Graph           граф понятий и связей
│   ├─ Procedural Memory        стратегии и навыки
│   └─ Source Memory            доверие к источникам + provenance
│
├─ 5. Cognitive Core            ← Когнитивное ядро
│   ├─ Planner                  стек целей + декомпозиция
│   ├─ Reasoner                 causal / associative / analogical
│   ├─ Contradiction Detector   поиск конфликтующих фактов
│   ├─ Uncertainty Monitor      оценка уверенности по гипотезам
│   ├─ Salience Engine          оценка значимости входящих событий
│   └─ Action Selector          выбор действия среди кандидатов
│
├─ 6. Learning Loop             ← Обучение из опыта
│   ├─ Online Learner           обновление после каждого взаимодействия
│   ├─ Replay Engine            периодическое воспроизведение эпизодов
│   ├─ Self-Supervised          согласованность картинка ↔ текст ↔ аудио
│   └─ Hypothesis Engine        генерация и проверка гипотез
│
└─ 7. Output Layer              ← Вывод с объяснением
    ├─ Dialogue Responder       текстовый ответ + объяснение + confidence
    ├─ Action Proposer          предложение действий с обоснованием
    └─ Trace Builder            полная цепочка причинности
```

---

## 🧬 Биологические аналоги

| Отдел мозга | Функции | Аналог в системе |
|-------------|---------|-----------------|
| Префронтальная кора | Планирование, цели, решения | `Planner`, `GoalManager`, `ExecutiveController` |
| Гиппокамп | Формирование эпизодических воспоминаний | `EpisodicMemory`, `ConsolidationEngine` |
| Миндалина (amygdala) | Быстрая оценка значимости/угрозы | `SalienceEngine`, `PriorityScorer`, `RiskSignal` |
| Базальные ганглии | Выбор действия среди конкурирующих | `ActionSelector`, `PolicyGate` |
| Таламус | Маршрутизация и фильтрация потоков | `InputRouter`, `ModalityRouter` |
| Мозжечок | Тонкая коррекция, автоматизация навыков | `FastErrorCorrector`, `SkillRefiner` |

---

## 📁 Структура проекта

```
AI/
│
├── brain/                          # Основной пакет мозга
│   ├── __init__.py                 # Корневой пакет (v0.1.0)
│   │
│   ├── core/                       # Ядро автономного цикла
│   │   └── __init__.py             # scheduler, event_bus, resource_monitor, attention_controller
│   │
│   ├── perception/                 # Слой восприятия
│   │   └── __init__.py             # text/vision/audio ingestors, input_router
│   │
│   ├── encoders/                   # Модальные энкодеры
│   │   └── __init__.py             # text/vision/audio/temporal encoders
│   │
│   ├── fusion/                     # Кросс-модальное слияние
│   │   └── __init__.py             # cross_modal_fusion, entity_linker, confidence_calibrator
│   │
│   ├── memory/                     # Система памяти
│   │   └── __init__.py             # working/episodic/semantic/procedural/source memory
│   │
│   ├── cognition/                  # Когнитивное ядро
│   │   └── __init__.py             # planner, reasoner, contradiction, uncertainty, salience
│   │
│   ├── learning/                   # Система обучения
│   │   └── __init__.py             # online_learner, replay_engine, self_supervised, hypothesis
│   │
│   ├── logging/                    # Логирование и наблюдаемость
│   │   └── __init__.py             # brain_logger, digest_generator, metrics_collector, dashboard
│   │
│   ├── safety/                     # Безопасность и границы
│   │   └── __init__.py             # source_trust, conflict_detector, boundary_guard
│   │
│   ├── output/                     # Слой вывода
│   │   └── __init__.py             # dialogue_responder, action_proposer, trace_builder
│   │
│   └── data/                       # Постоянное хранилище
│       ├── memory/                 # Файлы памяти
│       ├── logs/                   # JSONL логи
│       └── weights/                # Веса моделей
│
├── BRAIN.md                        # Архитектурная спецификация (15 разделов)
├── TODO.md                         # План реализации (14 фаз, 35+ задач)
├── requirements.txt                # Зависимости Python
├── download_libraries.bat          # Скрипт установки (Windows)
├── check_deps.py                   # Проверка зависимостей
└── README.md                       # Этот файл
```

---

## 📦 Зависимости

```
# Ядро
numpy>=1.26.0
jsonlines>=4.0.0

# PyTorch (CPU-only — устанавливается отдельно)
torch>=2.2.0  # через download_libraries.bat

# Русский язык
pymorphy3>=1.0.0
razdel>=0.5.0
nltk>=3.8.0
navec>=0.10.0          # fallback text encoder (~200 MB)

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

- Python 3.10+
- Windows 10/11 (или Linux/macOS с адаптацией скрипта)
- 32 GB RAM (рекомендуется)
- ~5 GB свободного места на диске (для моделей)

### Шаг 1 — Автоматическая установка (Windows)

```bat
download_libraries.bat
```

Скрипт выполняет:
1. Создание виртуального окружения `venv/`
2. Обновление `pip`
3. Установку PyTorch CPU-only build
4. Установку всех зависимостей из `requirements.txt`
5. Загрузку данных NLTK (`punkt`, `stopwords`)

### Шаг 2 — Ручная установка

```bash
# Создать виртуальное окружение
python -m venv venv

# Активировать (Windows)
venv\Scripts\activate

# Активировать (Linux/macOS)
source venv/bin/activate

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

## ▶️ Запуск

> ⚠️ **Примечание:** Основной цикл (`main.py`) находится в разработке (Фаза 0).  
> Текущий статус: структура директорий и пакеты созданы.

```bash
# Активировать окружение
venv\Scripts\activate

# Запустить мозг (после реализации Фазы 0.3)
python main.py
```

---

## 🔧 Модули

### `brain/core/` — Ядро автономного цикла

| Файл | Описание |
|------|---------|
| `scheduler.py` | Тик-планировщик: clock-driven + event-driven тики, приоритетная очередь |
| `event_bus.py` | Publish/subscribe шина событий для всех модулей |
| `events.py` | Dataclasses: `PerceptEvent`, `CognitiveEvent`, `MemoryEvent`, `LearningEvent` |
| `resource_monitor.py` | Мониторинг CPU/RAM, graceful degradation при перегрузке |
| `attention_controller.py` | Бюджет вычислений по модальностям (goal-driven + salience-driven) |

### `brain/perception/` — Слой восприятия

| Файл | Описание |
|------|---------|
| `text_ingestor.py` | Парсинг txt/md/pdf/docx/json → `PerceptEvent` с provenance |
| `vision_ingestor.py` | Загрузка изображений + OCR → `PerceptEvent` |
| `audio_ingestor.py` | ASR + временные метки → `PerceptEvent` |
| `metadata_extractor.py` | Извлечение source/timestamp/quality/language |
| `input_router.py` | Маршрутизация входящих данных (аналог Таламуса) |

### `brain/encoders/` — Модальные энкодеры

| Файл | Описание |
|------|---------|
| `text_encoder.py` | sentence-transformers large (768d/1024d), fallback: navec |
| `vision_encoder.py` | CLIP ViT-B/32 (512d), fallback: ResNet-50 |
| `audio_encoder.py` | Whisper medium + MFCC, fallback: Whisper base |
| `temporal_encoder.py` | Позиционное кодирование последовательностей (видео) |

### `brain/fusion/` — Кросс-модальное слияние

| Файл | Описание |
|------|---------|
| `cross_modal_fusion.py` | Объединение векторов разных модальностей |
| `entity_linker.py` | Связывание одних и тех же сущностей из разных источников |
| `confidence_calibrator.py` | Калибровка уверенности по согласованности модальностей |
| `contradiction_detector.py` | Обнаружение противоречий между модальностями |

### `brain/memory/` — Система памяти

| Файл | Описание |
|------|---------|
| `working_memory.py` | Рабочая память (текущий контекст, sliding window) |
| `episodic_memory.py` | Эпизодическая память с кросс-модальными записями |
| `semantic_graph.py` | Граф понятий и связей, semantic search |
| `procedural_memory.py` | Стратегии и навыки, кэширование паттернов |
| `source_memory.py` | Trust score источников + provenance |
| `consolidation_engine.py` | Перенос working → episodic → semantic (аналог Гиппокампа) |

### `brain/cognition/` — Когнитивное ядро

| Файл | Описание |
|------|---------|
| `planner.py` | Стек целей, декомпозиция, приоритизация (аналог Префронтальной коры) |
| `reasoner.py` | Причинное / ассоциативное / аналогическое рассуждение |
| `contradiction_resolver.py` | Разрешение конфликтов между фактами |
| `uncertainty_monitor.py` | Оценка уверенности, сигнал «нужно больше данных» |
| `salience_engine.py` | Быстрая оценка значимости (аналог Миндалины) |
| `action_selector.py` | Выбор действия среди кандидатов (аналог Базальных ганглий) |
| `self_reflector.py` | Периодический анализ качества мышления |
| `skill_refiner.py` | Тонкая коррекция ошибок (аналог Мозжечка) |

### `brain/learning/` — Система обучения

| Файл | Описание |
|------|---------|
| `online_learner.py` | Обновление знаний из новых данных в реальном времени |
| `replay_engine.py` | Периодическое воспроизведение эпизодов для закрепления |
| `self_supervised.py` | Самообучение: согласованность картинка ↔ текст ↔ аудио |
| `hypothesis_engine.py` | Генерация и проверка гипотез |
| `forgetting_manager.py` | Управляемое забывание (кривая Эббингауза) |

### `brain/logging/` — Логирование и наблюдаемость

| Файл | Описание |
|------|---------|
| `brain_logger.py` | JSONL-логгер (одна строка = одно событие) |
| `digest_generator.py` | Human-readable сводка по циклу |
| `trace_builder.py` | Построение цепочки причинности (trace chain) |
| `metrics_collector.py` | Сбор и обновление KPI метрик |
| `dashboard.py` | Текстовый live-дашборд метрик в терминале |

### `brain/safety/` — Безопасность

| Файл | Описание |
|------|---------|
| `source_trust.py` | Оценка надёжности источников, blacklist/whitelist |
| `conflict_detector.py` | Детектор конфликтов фактов из разных источников |
| `boundary_guard.py` | Ограничения на действия и выводы системы |
| `audit_logger.py` | Аудит-лог решений с высоким риском |

### `brain/output/` — Слой вывода

| Файл | Описание |
|------|---------|
| `dialogue_responder.py` | Текстовый ответ + объяснение + confidence |
| `action_proposer.py` | Предложение действий с обоснованием |
| `trace_builder.py` | Построение и экспорт trace chain |
| `explanation_builder.py` | Человекочитаемые объяснения решений |

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

### Human Digest (пример)

```
Cycle 4521
  Goal:         validate hypothesis H-17
  Evidence:     doc_A, frame_33, audio_12
  Contradiction: detected in source pair (doc_A vs audio_12)
  Decision:     request additional evidence
  Confidence:   0.81 → 0.66
  CPU:          58% | RAM: 4.1 GB
```

### Кросс-модальная запись памяти

```json
{
  "concept": "нейрон",
  "modal_evidence": [
    {"type": "text",  "source": "doc_A.md",      "span": "..."},
    {"type": "image", "source": "img_12.png",     "region": [0, 0, 100, 100]},
    {"type": "audio", "source": "lecture_3.wav",  "time": [12.2, 14.7]}
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

## 🗺️ Roadmap

### Фаза A — Multimodal Perception
- [ ] Text ingest pipeline (txt/md/pdf/docx/json)
- [ ] Vision ingest (image parsing + OCR, CPU-only)
- [ ] Audio ingest (Whisper tiny/base, CPU-only)
- [ ] Унифицированный формат `PerceptEvent`

### Фаза B — Cross-Modal Fusion
- [ ] Shared embedding space (лёгкие модели ≤ 500 MB)
- [ ] Entity/link alignment между модальностями
- [ ] Confidence calibration по источникам

### Фаза C — Memory Upgrade
- [ ] Кросс-модальная эпизодическая память
- [ ] Source memory (trust/provenance)
- [ ] Temporal indexing + retrieval by evidence

### Фаза D — Cognitive Control
- [ ] Planner + Goal stack
- [ ] Causal reasoner + contradiction checker
- [ ] Resource-aware attention controller (CPU/RAM budget)

### Фаза E — Self-Development
- [ ] Автоматическое выявление пробелов знаний
- [ ] Hypothesis-to-test pipeline
- [ ] Reflection dashboard с метриками качества мышления

---

## ✅ Прогресс реализации

| Фаза | Название | Статус |
|------|----------|--------|
| **0** | Foundation & Bootstrap | 🚧 В процессе |
| 1 | Always-On Autonomous Loop | ⬜ Не начато |
| 2 | Logging & Observability | ⬜ Не начато |
| 3 | Perception Layer | ⬜ Не начато |
| 4 | Modality Encoders | ⬜ Не начато |
| 5 | Cross-Modal Fusion | ⬜ Не начато |
| 6 | Memory System | ⬜ Не начато |
| 7 | Cognitive Core | ⬜ Не начато |
| 8 | Attention & Resource Control | ⬜ Не начато |
| 9 | Learning Loop | ⬜ Не начато |
| 10 | Explainability & Output | ⬜ Не нач
