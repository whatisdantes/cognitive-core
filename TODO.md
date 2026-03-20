# 🧠 TODO — Implementation Master Plan
## Искусственный мультимодальный мозг (по BRAIN.md)

> Статусы: `[ ]` — не начато | `[~]` — в процессе | `[x]` — завершено  
> Зависимости указаны как `→ depends on: #N`

---

## ФАЗА 0 — Foundation & Bootstrap
> Цель: создать минимальный запускаемый каркас проекта.

- [ ] **0.1** Создать структуру директорий проекта:
  ```
  brain/
  ├── core/          # always-on loop, scheduler, resource monitor
  ├── perception/    # text/vision/audio ingestors
  ├── encoders/      # text/vision/audio/temporal encoders
  ├── fusion/        # cross-modal fusion
  ├── memory/        # working/episodic/semantic/procedural/source
  ├── cognition/     # planner, reasoner, contradiction, uncertainty
  ├── learning/      # online, replay, self-supervised
  ├── logging/       # JSONL logger, digest generator
  ├── safety/        # source trust, conflict detector
  ├── output/        # dialogue, action, trace
  └── data/          # persistent storage
  ```
  **DoD:** все директории созданы, каждая содержит `__init__.py`.

- [ ] **0.2** Создать `requirements.txt` с базовыми зависимостями:
  - `numpy`, `torch` (CPU-only build), `pymorphy3`, `razdel`, `navec`, `nltk`
  - `sentence-transformers` (text encoder, large модель ~1.3 GB)
  - `pillow`, `open-clip-torch` (vision, CLIP ViT-B/32 ~600 MB)
  - `openai-whisper` (audio, medium модель ~1.5 GB)
  - `jsonlines` (JSONL logging)
  > Суммарный бюджет моделей: ~3.4 GB — в рамках лимита 3 GB (выбрать medium/small при необходимости).
  **DoD:** `pip install -r requirements.txt` проходит без ошибок.

- [ ] **0.3** Создать `main.py` — точка входа always-on цикла:
  - инициализация всех модулей,
  - запуск scheduler/tick loop,
  - graceful shutdown по SIGINT/SIGTERM.
  **DoD:** `python main.py` запускается и выводит системный лог старта.

- [ ] **0.4** Создать единый словарь терминов `GLOSSARY.md`:
  - зафиксировать имена всех модулей и классов,
  - предотвратить расхождение архитектуры в коде.
  **DoD:** все имена из BRAIN.md зафиксированы в GLOSSARY.md.

---

## ФАЗА 1 — Always-On Autonomous Loop (BRAIN.md §14)
> Цель: мозг работает непрерывно, не ждёт команды.

- [ ] **1.1** Реализовать `core/scheduler.py` — тик-планировщик:
  - clock-driven тики (configurable interval),
  - event-driven обработка входящих событий,
  - приоритетная очередь задач.
  **DoD:** scheduler запускается, генерирует тики, логирует каждый цикл.
  → depends on: #0.3

- [ ] **1.2** Реализовать `core/resource_monitor.py`:
  - мониторинг CPU (Ryzen 7 5700X, 16 потоков) и RAM (32 GB),
  - динамический бюджет вычислений (лимит: CPU ≤70%, RAM ≤22 GB),
  - graceful degradation при нехватке ресурсов,
  - флаг `USE_GPU=False` (зарезервировано для будущего подключения GPU).
  **DoD:** при нагрузке >80% CPU система снижает частоту тиков; при RAM >28 GB — выгружает неактивные модели.
  → depends on: #1.1

- [ ] **1.3** Реализовать `core/event_bus.py`:
  - publish/subscribe для всех модулей,
  - типизированные события (`PerceptEvent`, `CognitiveEvent`, `MemoryEvent`).
  **DoD:** модули могут публиковать и подписываться на события без прямых зависимостей.
  → depends on: #1.1

- [ ] **1.4** Определить dataclasses событий в `core/events.py`:
  - `PerceptEvent` (source, modality, content, quality, ts),
  - `CognitiveEvent` (goal, step, confidence, trace_id),
  - `MemoryEvent` (operation, key, value, memory_type),
  - `LearningEvent` (trigger, delta, affected_module).
  **DoD:** все события сериализуются в JSON без ошибок.
  → depends on: #1.3

---

## ФАЗА 2 — Logging & Observability (BRAIN.md §13)
> Цель: читаемый, воспроизводимый след мышления.  
> ⚠️ Реализуется РАНО — до остальных модулей, чтобы всё логировалось с самого начала.

- [ ] **2.1** Реализовать `logging/brain_logger.py`:
  - JSONL-формат (одна строка = одно событие),
  - поля: `ts`, `level`, `module`, `event`, `session_id`, `cycle_id`, `trace_id`,
    `input_ref`, `state`, `decision`, `latency_ms`, `notes`.
  **DoD:** каждый модуль может вызвать `logger.log(...)` и событие появляется в файле.
  → depends on: #0.1

- [ ] **2.2** Реализовать уровни логов: `DEBUG`, `INFO`, `WARN`, `ERROR`, `CRITICAL`.
  **DoD:** фильтрация по уровню работает через конфиг.
  → depends on: #2.1

- [ ] **2.3** Реализовать `logging/digest_generator.py` — human-readable digest:
  - сводка по циклу: цель → шаги → решение → ошибки → next actions,
  - вывод в `logs/digest_YYYYMMDD.txt`.
  **DoD:** после каждого цикла генерируется читаемая сводка.
  → depends on: #2.1

- [ ] **2.4** Реализовать ротацию логов:
  - лимит размера файла (configurable),
  - архивирование старых логов,
  - разделение горячих/архивных.
  **DoD:** при превышении лимита создаётся новый файл, старый архивируется.
  → depends on: #2.1

- [ ] **2.5** Реализовать trace chain:
  - каждое решение связано с `input_ref`, `memory_refs`, `hypothesis_refs`, `decision_ref`,
  - никаких «магических» ответов без trace.
  **DoD:** любой вывод системы можно восстановить по `trace_id`.
  → depends on: #2.1, #1.4

---

## ФАЗА 3 — Perception Layer (BRAIN.md §4, §5.1)
> Цель: мозг умеет принимать text/image/audio/video.

- [ ] **3.1** Реализовать `perception/text_ingestor.py`:
  - поддержка форматов: `.txt`, `.md`, `.pdf`, `.docx`, `.json`,
  - структурный парсинг (заголовки, разделы, таблицы),
  - извлечение фактов/тезисов,
  - provenance (источник, страница, параграф).
  **DoD:** любой текстовый файл → список `PerceptEvent` с метаданными.
  → depends on: #1.4, #2.1

- [ ] **3.2** Реализовать `perception/vision_ingestor.py`:
  - загрузка изображений (jpg/png/webp),
  - OCR (извлечение текста с изображений),
  - базовое image understanding (объекты, сцены).
  **DoD:** изображение → `PerceptEvent` с текстом и описанием объектов.
  → depends on: #1.4, #2.1

- [ ] **3.3** Реализовать `perception/audio_ingestor.py`:
  - ASR (speech-to-text),
  - speaker/event detection,
  - временные метки сегментов.
  **DoD:** аудиофайл → `PerceptEvent` с транскриптом и временными метками.
  → depends on: #1.4, #2.1

- [ ] **3.4** Реализовать `perception/metadata_extractor.py`:
  - извлечение: source, timestamp, quality score, language, modality.
  **DoD:** каждый `PerceptEvent` содержит полные метаданные.
  → depends on: #3.1, #3.2, #3.3

- [ ] **3.5** Реализовать `perception/input_router.py` (аналог Таламуса):
  - маршрутизация входящих данных по типу модальности,
  - фильтрация дубликатов и низкокачественных входов.
  **DoD:** любой входящий файл автоматически направляется в нужный ingestor.
  → depends on: #3.1, #3.2, #3.3

---

## ФАЗА 4 — Modality Encoders (BRAIN.md §5.2)
> Цель: перевести сырые данные в векторные представления.

- [ ] **4.1** Реализовать `encoders/text_encoder.py`:
  - токенизация + лемматизация (RU + EN, pymorphy3 + razdel),
  - эмбеддинги предложений: `sentence-transformers` large (~1.3 GB) — основной вариант,
  - fallback: navec (~200 MB) при нехватке памяти,
  - нормализация векторов.
  **DoD:** текст → вектор фиксированной размерности (768d или 1024d).
  → depends on: #3.1

- [ ] **4.2** Реализовать `encoders/vision_encoder.py`:
  - feature extraction из изображений: CLIP ViT-B/32 (~600 MB) — основной вариант,
  - fallback: ResNet-50 (~100 MB) при нехватке памяти,
  - нормализация в общее пространство с текстовым энкодером.
  **DoD:** изображение → вектор той же размерности, что и текстовый (512d для CLIP).
  → depends on: #3.2

- [ ] **4.3** Реализовать `encoders/audio_encoder.py`:
  - ASR + feature extraction: Whisper medium (~1.5 GB) — основной вариант,
  - fallback: Whisper base (~150 MB) при нехватке памяти,
  - MFCC как лёгкая альтернатива для акустических признаков,
  - нормализация.
  **DoD:** аудио → транскрипт + вектор признаков той же размерности.
  → depends on: #3.3

- [ ] **4.4** Реализовать `encoders/temporal_encoder.py`:
  - кодирование последовательностей (для видео/временных рядов),
  - позиционное кодирование.
  **DoD:** последовательность кадров → вектор с временной информацией.
  → depends on: #4.2

---

## ФАЗА 5 — Cross-Modal Fusion (BRAIN.md §5.3)
> Цель: объединить разные модальности в единое понимание.

- [ ] **5.1** Реализовать `fusion/shared_space.py`:
  - проекция всех модальностей в единое латентное пространство,
  - alignment (text-image, audio-video).
  **DoD:** вектора разных модальностей об одном объекте близки в пространстве.
  → depends on: #4.1, #4.2, #4.3

- [ ] **5.2** Реализовать `fusion/confidence_calibrator.py`:
  - оценка качества слияния по источникам,
  - confidence score для каждого факта.
  **DoD:** каждый слитый факт имеет `confidence` от 0.0 до 1.0.
  → depends on: #5.1

- [ ] **5.3** Реализовать `fusion/entity_linker.py`:
  - связывание одних и тех же сущностей из разных модальностей,
  - обновление кросс-модальной памяти.
  **DoD:** «нейрон» в тексте и «нейрон» на изображении → одна запись в памяти.
  → depends on: #5.1, #5.2

---

## ФАЗА 6 — Memory System (BRAIN.md §5.4, §6)
> Цель: мозг помнит, что видел, слышал и читал.

- [ ] **6.1** Реализовать `memory/working_memory.py`:
  - активный контекст текущего цикла,
  - ограниченный размер (sliding window),
  - быстрый доступ.
  **DoD:** текущий контекст доступен всем когнитивным модулям.
  → depends on: #1.4

- [ ] **6.2** Реализовать `memory/episodic_memory.py`:
  - хранение событий во времени,
  - кросс-модальные записи (text/image/audio/video evidence),
  - поиск по времени, источнику, концепту.
  **DoD:** любое событие можно найти по `trace_id` или временному диапазону.
  → depends on: #6.1, #5.3

- [ ] **6.3** Реализовать `memory/semantic_graph.py`:
  - граф понятий и связей,
  - добавление/обновление/удаление узлов,
  - поиск по смыслу (semantic search).
  **DoD:** запрос «нейрон» возвращает связанные понятия с весами.
  → depends on: #6.2

- [ ] **6.4** Реализовать `memory/procedural_memory.py`:
  - хранение стратегий и навыков,
  - автоматизация повторяющихся паттернов.
  **DoD:** часто используемые цепочки действий кэшируются и ускоряются.
  → depends on: #6.1

- [ ] **6.5** Реализовать `memory/source_memory.py`:
  - trust score для каждого источника,
  - provenance (откуда пришёл факт),
  - история подтверждений/опровержений.
  **DoD:** каждый факт имеет ссылку на источник и уровень доверия.
  → depends on: #6.2

- [ ] **6.6** Реализовать `memory/consolidation_engine.py` (аналог Гиппокампа):
  - перенос важных событий из working → episodic → semantic,
  - забывание неважного (decay),
  - усиление часто используемого.
  **DoD:** после N циклов важные факты переходят в LTM, неважные затухают.
  → depends on: #6.1, #6.2, #6.3

---

## ФАЗА 7 — Cognitive Core (BRAIN.md §5.5, §2.1–2.4)
> Цель: мозг планирует, рассуждает и контролирует себя.

- [ ] **7.1** Реализовать `cognition/planner.py` (аналог Префронтальной коры):
  - стек целей (goal stack),
  - декомпозиция цели на шаги,
  - приоритизация задач.
  **DoD:** при получении задачи система строит план из шагов и выполняет их.
  → depends on: #6.1, #1.3

- [ ] **7.2** Реализовать `cognition/reasoner.py`:
  - причинное рассуждение (causal),
  - ассоциативное рассуждение,
  - аналогическое рассуждение.
  **DoD:** на вопрос «почему X?» система строит цепочку причин из памяти.
  → depends on: #6.3, #7.1

- [ ] **7.3** Реализовать `cognition/contradiction_detector.py`:
  - поиск конфликтующих фактов в памяти,
  - флаг противоречия в логе,
  - запрос дополнительных доказательств.
  **DoD:** при конфликте двух фактов система логирует `WARN` и снижает confidence.
  → depends on: #6.3, #6.5

- [ ] **7.4** Реализовать `cognition/uncertainty_monitor.py`:
  - отслеживание уровня уверенности по всем активным гипотезам,
  - сигнал «нужно больше данных».
  **DoD:** при confidence < threshold система запрашивает дополнительный ввод.
  → depends on: #7.2, #7.3

- [ ] **7.5** Реализовать `cognition/salience_engine.py` (аналог Миндалины):
  - быстрая оценка значимости входящего события,
  - приоритизация срочных/аномальных сигналов.
  **DoD:** аномальный ввод немедленно поднимается в приоритете обработки.
  → depends on: #1.3, #7.1

- [ ] **7.6** Реализовать `cognition/action_selector.py` (аналог Базальных ганглий):
  - выбор действия среди конкурирующих вариантов,
  - policy gate (фильтр нежелательных действий).
  **DoD:** система выбирает одно действие из N кандидатов с обоснованием.
  → depends on: #7.1, #7.2

---

## ФАЗА 8 — Attention & Resource Control (BRAIN.md §7)
> Цель: мозг знает, на что тратить ресурсы.

- [ ] **8.1** Реализовать `core/attention_controller.py`:
  - goal-driven attention (что важно для цели),
  - salience-driven attention (что аномально/новое),
  - бюджет вычислений по модальностям.
  **DoD:** при ограниченных ресурсах система фокусируется на приоритетных модальностях.
  → depends on: #1.2, #7.5

---

## ФАЗА 9 — Learning Loop (BRAIN.md §8)
> Цель: мозг учится из опыта.

- [ ] **9.1** Реализовать `learning/online_learner.py`:
  - обновление ассоциаций после каждого взаимодействия,
  - обновление confidence фактов,
  - адаптация весов энкодеров.
  **DoD:** после каждого цикла веса обновляются и логируются в Learning Logs.
  → depends on: #6.3, #4.1

- [ ] **9.2** Реализовать `learning/replay_engine.py`:
  - периодическое воспроизведение важных эпизодов,
  - усиление устойчивых паттернов,
  - удаление шума.
  **DoD:** каждые N циклов запускается replay, результаты логируются.
  → depends on: #6.2, #9.1

- [ ] **9.3** Реализовать `learning/self_supervised.py`:
  - проверка согласованности «картинка ↔ текст»,
  - проверка «аудио ↔ транскрипт»,
  - сигнал ошибки при несогласованности.
  **DoD:** несогласованные пары снижают confidence источника.
  → depends on: #5.1, #9.1

- [ ] **9.4** Реализовать `learning/hypothesis_engine.py`:
  - генерация гипотез на основе пробелов в знаниях,
  - тестирование гипотез через новые данные,
  - подтверждение/опровержение.
  **DoD:** система самостоятельно формулирует вопросы для заполнения пробелов.
  → depends on: #7.2, #9.1

---

## ФАЗА 10 — Explainability & Output (BRAIN.md §9)
> Цель: каждый вывод объяснён и прослеживаем.

- [ ] **10.1** Реализовать `output/trace_builder.py`:
  - сборка полного trace chain для каждого вывода,
  - поля: источники, факты, гипотезы, решение, confidence, риски.
  **DoD:** любой ответ системы сопровождается полным trace.
  → depends on: #2.5, #7.6

- [ ] **10.2** Реализовать `output/dialogue_responder.py`:
  - формирование текстового ответа,
  - включение объяснения (почему так решено),
  - уровень уверенности в ответе.
  **DoD:** ответ содержит текст + краткое объяснение + confidence.
  → depends on: #10.1

- [ ] **10.3** Реализовать `output/action_proposer.py`:
  - предложение действий (не только текстовых ответов),
  - обоснование каждого действия.
  **DoD:** система может предложить конкретное действие с объяснением.
  → depends on: #7.6, #10.1

---

## ФАЗА 11 — Safety & Boundaries (BRAIN.md §10)
> Цель: мозг не делает вредного и не доверяет ненадёжному.

- [ ] **11.1** Реализовать `safety/source_trust.py`:
  - оценка надёжности источников,
  - blacklist/whitelist источников,
  - decay доверия при противоречиях.
  **DoD:** ненадёжный источник снижает confidence всех связанных фактов.
  → depends on: #6.5

- [ ] **11.2** Реализовать `safety/conflict_detector.py`:
  - детектор конфликтов фактов из разных источников,
  - логирование в Safety/Audit Logs.
  **DoD:** конфликт фактов → `WARN` лог + снижение confidence.
  → depends on: #7.3, #11.1

---

## ФАЗА 12 — Self-Development & Reflection (BRAIN.md §11.E)
> Цель: мозг анализирует себя и улучшается.

- [ ] **12.1** Реализовать `cognition/self_reflector.py`:
  - периодический анализ качества мышления,
  - выявление пробелов в знаниях,
  - отчёт о саморазвитии.
  **DoD:** каждые N циклов генерируется reflection report.
  → depends on: #9.4, #7.4

- [ ] **12.2** Реализовать `cognition/skill_refiner.py` (аналог Мозжечка):
  - тонкая коррекция повторяющихся ошибок,
  - автоматизация успешных паттернов.
  **DoD:** повторяющиеся ошибки снижаются после N итераций.
  → depends on: #9.1, #12.1

---

## ФАЗА 13 — Metrics & KPI Dashboard (BRAIN.md §12, §13.8)
> Цель: измерять качество работы мозга.

- [ ] **13.1** Реализовать `logging/metrics_collector.py`:
  - Cross-Modal Retrieval Accuracy,
  - Source Reliability Calibration,
  - Contradiction Detection Rate,
  - Reasoning Depth & Coherence,
  - Learning Velocity,
  - Self-Correction Rate,
  - Explainability Completeness,
  - Trace Completeness,
  - Error Localization Time,
  - Logging Overhead.
  **DoD:** метрики обновляются каждый цикл и доступны в `logs/metrics.jsonl`.
  → depends on: #2.1, #7.2, #9.1

- [ ] **13.2** Реализовать `logging/dashboard.py` — текстовый дашборд:
  - вывод ключевых метрик в терминал,
  - обновление в реальном времени.
  **DoD:** `python -m brain.logging.dashboard` показывает live-метрики.
  → depends on: #13.1

---

## ПОРЯДОК РЕАЛИЗАЦИИ (рекомендуемый)

```
0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13
```

Минимальный MVP (запускаемый мозг):
```
0.1 → 0.2 → 0.3 → 1.1 → 1.3 → 1.4 → 2.1 → 2.2 → 3.1 → 6.1 → 7.1 → 10.1 → 10.2
```
> ⚠️ 10.1 (trace_builder) обязателен перед 10.2 (dialogue_responder) — зависимость.

---

## ПРОГРЕСС

| Фаза | Название | Статус |
|------|----------|--------|
| 0 | Foundation & Bootstrap | [ ] |
| 1 | Always-On Autonomous Loop | [ ] |
| 2 | Logging & Observability | [ ] |
| 3 | Perception Layer | [ ] |
| 4 | Modality Encoders | [ ] |
| 5 | Cross-Modal Fusion | [ ] |
| 6 | Memory System | [ ] |
| 7 | Cognitive Core | [ ] |
| 8 | Attention & Resource Control | [ ] |
| 9 | Learning Loop | [ ] |
| 10 | Explainability & Output | [ ] |
| 11 | Safety & Boundaries | [ ] |
| 12 | Self-Development & Reflection | [ ] |
| 13 | Metrics & KPI Dashboard | [ ] |
