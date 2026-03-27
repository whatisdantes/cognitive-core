# Общий review проекта `cognitive-core`

> ⚠️ **ИСТОРИЧЕСКИЙ ДОКУМЕНТ** — снимок состояния проекта на 25 марта 2026 (773 теста).  
> С момента написания завершены **Phase A** (CLI, Docker, mypy), **Phase B** (auto-encode, perception hardening, golden benchmarks) и **Phase C** (DRY refactoring).  
> Текущее состояние: **1312 тестов**, CLI entrypoint, Dockerfile, 19 test files, ruff clean.  
> Многие проблемы, описанные ниже (нет CLI, нет Docker, legacy-артефакты, нет golden-тестов), **уже решены**.  
> Актуальный roadmap: [`docs/TODO.md`](TODO.md)

**Автор проекта:** whatisdantes  
**Период оценки:** первые 5 дней разработки (20–25 марта 2026)  
**Основа ревью:** технический разбор репозитория + внешний аудит + peer review с коррекцией оценок  
**Обновлено:** 2026-03-25 (v0.7.0, post-audit consensus)

---

## Итоговая оценка

**Сводная оценка: 8.0 / 10 — как результат 5 дней сольной разработки.**

Это **сильный инженерный старт**: у проекта уже есть архитектурный каркас, тестовая дисциплина, persistence, retrieval, когнитивный pipeline и CI.  
Но это пока **foundation-first проект**, а не зрелый пользовательский продукт: runnable entrypoint, демонстрационный сценарий и производственная обвязка ещё отстают.

> **Примечание:** первоначальная оценка 8.2/10 была скорректирована до 8.0 после peer review, который выявил завышение в категориях архитектуры (8.8→8.4), тестирования (8.1→7.7) и недооценку output layer. Детали коррекции — в разделе «Коррекция оценок».

---

## Короткий вердикт

`cognitive-core` уже выглядит не как "идея на будущее", а как **реальный каркас когнитивной системы**, написанный с заметным инженерным вкусом.  
Особенно сильны: **memory subsystem**, **архитектурная декомпозиция**, **тестовая база**, **SQLite + BM25 + CI**.

Главный риск проекта сейчас не в слабом коде, а в **разрыве между архитектурной амбицией и удобством реального использования**.  
Проще говоря: ядро уже выглядит серьёзно, а путь "скачал → запустил → увидел ценность" пока ещё недостаточно короткий.

---

## Ключевые выводы

### 1. Для 5 дней объём выполненной работы очень сильный
Оба разбора сходятся в том, что темп разработки впечатляет: проект успел вырасти от scaffold до многоуровневой системы с тестами, документацией и несколькими зрелыми подсистемами.

### 2. Самая сильная часть проекта — memory / core foundation
Система памяти — это не декоративный слой, а реально проработанный модуль:
- working / semantic / episodic / source / procedural memory;
- consolidation engine;
- unified `MemoryManager`;
- persistence через SQLite backend;
- миграционный слой JSON → SQLite;
- отдельные тесты под storage и roundtrip-сценарии.

### 3. Архитектура продумана лучше среднего, но используется проще, чем спроектирована
Слои, контракты, событийная модель, typed-объекты, façade-подход, логирование и трассировка решений — всё это выглядит системно.

Однако есть нюансы:
- `EventBus` существует и работает, но в основном pipeline почти не используется (события публикуются, мало кто подписывается);
- `ResourceMonitor` с 4 политиками (NORMAL/DEGRADED/CRITICAL/EMERGENCY) — красиво, но `CognitiveCore` реально использует только `is_critical()`;
- `CognitiveCore.run()` — 10-шаговый pipeline, но шаги жёстко захардкожены, нет plugin/middleware механизма.

Архитектура **спроектирована на вырост**, и это хорошо. Но текущее использование проще, чем структура предполагает.

### 4. Cognitive pipeline — heuristic scoring, не reasoning engine
Важная честная оговорка: текущий `Reasoner` и `HypothesisEngine` — это не «rule-based reasoning» в классическом смысле (нет правил, нет inference engine). Это ближе к **heuristic cognitive pipeline**: retrieval → scoring → contradiction checks → uncertainty tracking → action selection.

Это уже не просто glue code, но ещё и не тот reasoning, который обычно имеют в виду под rule engine или symbolic inference. Называть это полноценным «reasoning engine» без оговорок — натяжка.

При этом **отсутствие LLM на этом этапе — скорее плюс**: логика остаётся детерминированной и тестируемой, проще наблюдать качество pipeline, меньше магии. LLM-интеграция важна как следующий шаг (Этап N), но не обнуляет ценность текущего ядра.

### 5. Продуктовая зрелость пока ниже архитектурной зрелости
Это один из главных выводов:
- нет удобного CLI / `main.py` / REPL entrypoint;
- нет короткого demo path для нового пользователя;
- часть возможностей пока находится в стадии specification/planned;
- output-слой менее выразителен, чем cognition/memory;
- реальный user-facing MVP слабее, чем внутренний engineering foundation.

### 6. README и позиционирование — частично исправлены
> **Обновление (v0.7.0):** README обновлён в рамках D3 — Quick Start приведён к реальности, multimodal помечен как "Planned (post-MVP)", layer statuses синхронизированы. Но полная честность README зависит от появления runnable entrypoint (Фаза A.1).

---

## Коррекция оценок (peer review)

После детального peer review кода были выявлены расхождения с первоначальными оценками:

### Архитектура: 8.8 → 8.4
- `ContradictionDetector.flag_evidence()` делает `copy.deepcopy` для всего evidence, включая случай без противоречий — потенциальный O(n) bottleneck
- `CognitiveCore.run()` — 10 шагов захардкожены, нет plugin/middleware
- `EventBus` и `ResourceMonitor` спроектированы богаче, чем реально используются

### Тестирование: 8.1 → 7.7
- 773 теста — впечатляющее число, но:
  - Много тестов проверяют конструкторы и дефолтные значения (`assert ctx.session_id == "..."`)
  - Мало тестов на граничные случаи (пустой ввод, огромный ввод, Unicode edge cases, concurrent access)
  - E2E тесты (`test_e2e_pipeline.py`) используют моки для MemoryManager — это не настоящий E2E
  - Нет golden-answer тестов (ожидаемый ответ на конкретный вопрос)
  - Нет property-based тестов
- Количество тестов сильное, но **глубина покрытия** могла бы быть выше

### Output: ~6.5 (implied) → 7.2
Первоначальная формулировка «в основном шаблонный рендеринг» была слишком узкой. Output layer включает:
- `ResponseValidator` с 4 проверками (empty response, hedge при низкой уверенности, length limit, language mismatch)
- `OutputTraceBuilder` с полной цепочкой explainability
- `OutputPipeline` как façade с валидацией + трассировкой + форматированием

Шаблонность ответов — да, но **инфраструктура вокруг ответов** уже серьёзная и готова к LLM-интеграции. Самое точное описание: output сейчас не слабый, а **менее выразительный, чем cognition/memory**, при этом инфраструктурно уже неплохо подготовлен к следующему этапу.

> **Уточнение:** `ResponseValidator` содержит именно 4 проверки (empty, hedge, length, language), а не "6+" — hallucination detection и contradiction check в этом файле **не реализованы**, хотя архитектурно предусмотрены.

### Retrieval: 8.4 → 8.1
- BM25 reranking работает хорошо
- Но vector search всё ещё brute-force O(n·d), ANN/FAISS — в планах (Этап D.2)

---

## Пропущенные в первом ревью пункты

### 1. Legacy-артефакты: `check_deps.py` и `download_libraries.bat`
Эти файлы не нужны при `pip install -e ".[dev]"`. `download_libraries.bat` инструктирует запускать `python main.py`, хотя runnable entrypoint отсутствует. Создают путаницу для нового пользователя.

### 2. `requirements.txt` дублирует `pyproject.toml`
Файл содержал `tqdm` (отсутствовал в pyproject.toml) и дублировал зависимости. Частично исправлено в P1.6 (файл помечен как deprecated, канонический источник — pyproject.toml), но как blind spot первого ревью — это было упущение.

### 3. `docs/ARCHITECTURE.md` описывает нереализованную архитектуру
Документ описывает `CognitiveNeuron` с дендритами и мембранным потенциалом — ничего из этого не реализовано в коде. Disclaimer добавлен (P1.7), но это яркий пример «документация опережает реализацию», который стоило отметить отдельно.

### 4. `ContradictionDetector` — `copy.deepcopy` bottleneck
`flag_evidence()` делает `copy.deepcopy` для evidence на каждом вызове, включая случай без противоречий. Это архитектурно чистый copy-on-write подход, но потенциальный bottleneck при росте данных. Запланировано в P2.10 (замена на `dataclasses.replace`).

---

## Сильные стороны проекта

### 1. Архитектурный фундамент
Проект хорошо разложен на подсистемы: `core`, `memory`, `perception`, `encoders`, `cognition`, `output`, `logging`. Это делает код расширяемым и позволяет развивать систему по слоям.

### 2. Система памяти — главный технический актив
Если выбирать одну подсистему, которая выглядит наиболее зрелой, это **memory**. Там уже есть внутренняя модель мира проекта, а не просто "хранилище строк".

Особенно ценно:
- разделение памяти по типам (5 видов);
- trust/provenance;
- consolidation;
- SQLite backend с WAL;
- migration story (JSON → SQLite);
- отдельные тесты именно на хранилище (58 тестов).

### 3. Retrieval и persistence уже на хорошем уровне
BM25 reranking, vector backend, hybrid retrieval (RRF merge) и SQLite — это задел на практическую полезность, а не просто архитектурный "замысел".

### 4. Наблюдаемость и explainability
`BrainLogger`, digest generation, trace builders, explainability trace — очень сильный сигнал инженерной культуры. Многие проекты такого масштаба вообще не доходят до нормальной observability на ранней стадии.

### 5. Хорошая дисциплина упаковки
`pyproject.toml`, optional dependencies, CI (3 jobs: test + lint + typecheck), лицензия, структура docs — всё это улучшает репозиторий не только как код, но и как open-source артефакт.

---

## Ограничения и слабые места

### 1. Нет короткого runnable сценария
Сейчас проект сильнее как библиотечное ядро, чем как инструмент, который можно быстро показать другому человеку.

**Чего не хватает:**
- CLI entrypoint (`cognitive-core "вопрос"`);
- одного demo-скрипта, который прогоняет полный happy-path;
- небольшого sample dataset.

Это самый полезный следующий шаг (→ Фаза A.1 в [TODO.md](TODO.md)).

### 2. Output менее выразителен, чем cognition/memory
`DialogueResponder` генерирует ответы по шаблонам. `ResponseValidator` проверяет 4 аспекта (empty, hedge, length, language), но hallucination detection и contradiction check пока не реализованы. Инфраструктурно слой готов к LLM-интеграции, но текущий output — самое слабое звено в цепочке восприятия проекта.

### 3. Документация местами опережает реализацию
`docs/ARCHITECTURE.md` описывает CognitiveNeuron с дендритами — ничего из этого не в коде (disclaimer добавлен). Часть layer-документов содержала статусы "⬜ не реализовано" для уже реализованных компонентов (исправлено в D4). Документация сильная, но требует постоянной синхронизации.

### 4. Production-readiness пока невысокая
Не хватает:
- Dockerfile / container story;
- явной конфигурации (TOML/YAML config, профили dev/demo/prod);
- воспроизводимой установки для Linux/macOS;
- более строгого dependency pinning;
- бенчмарков и performance budget.

### 5. Legacy-артефакты создают путаницу
`check_deps.py` и `download_libraries.bat` — остатки раннего этапа, не нужны при `pip install -e ".[dev]"`. `requirements.txt` дублирует pyproject.toml (помечен как deprecated, но всё ещё в репозитории).

### 6. Масштабирование некоторых решений ещё впереди
- Vector search — brute-force O(n·d), ANN/FAISS запланирован (Этап D.2);
- `ContradictionDetector` — `copy.deepcopy` на каждом вызове (P2.10);
- In-memory индексы BrainLogger без TTL/LRU (P2.1);
- Template-based response generation.

---

## Где я корректирую внешний аудит

### 1. Оценка 7.5/10 немного занижает инженерную глубину
Внешний аудит разумно критикует product readiness, но **недооценивает плотность инженерной базы**, собранной за 5 дней.

У проекта уже есть: пакетирование через `pyproject.toml`, CI на нескольких версиях Python, storage backend, retrieval abstraction, fallback/degraded режимы, unit + integration + e2e smoke coverage, внятная структура модулей.

Для такого срока это тянет ближе к **8.0**, если оценивать именно как early-stage technical foundation.

### 2. Утверждение "нет end-to-end тестов" некорректно в строгом виде
В репозитории есть `tests/test_e2e_pipeline.py`, который прогоняет цепочку `MemoryManager → CognitiveCore → OutputPipeline → BrainOutput`, а также smoke-сценарии на вопросах, обучении, unknown-topic и нескольких циклах подряд.

Правильнее: **E2E smoke coverage уже есть, но её пока мало для заявленной архитектурной сложности**, и часть E2E тестов использует моки вместо реальных компонентов.

### 3. Тестовый набор не сводится только к мокам
Есть и "живые" проверки: SQLite CRUD / migration / transactions, roundtrip интеграции memory-модулей, e2e pipeline smoke tests. Проблема не в отсутствии реальных тестов, а в том, что **доля высокоценных сценарных тестов пока меньше, чем хотелось бы**.

---

## Сводная оценка по категориям

| Категория | Оценка | Комментарий |
|---|---:|---|
| Архитектура | **8.4/10** | Сильная декомпозиция, хорошие контракты; спроектирована на вырост, используется проще |
| Реализация foundation | **8.5/10** | Много реального кода, не только docs и заглушки |
| Система памяти | **9.0/10** | Самая зрелая и убедительная часть проекта |
| Retrieval / persistence | **8.1/10** | BM25 + SQLite — практический скелет; vector search пока brute-force |
| Тестирование | **7.7/10** | Количество сильное (773), глубина покрытия — средняя |
| Документация | **8.0/10** | Подробная и полезная, нуждается в постоянной синхронизации |
| Output layer | **7.2/10** | Инфраструктурно готов к LLM, но ответы шаблонные |
| User-facing MVP | **6.2/10** | Нет CLI, нет demo path |
| Production readiness | **5.8/10** | Нет Docker, config, stricter gates, reproducibility |
| **Итог** | **8.0/10** | **Сильный foundation-first результат за 5 дней** |

---

## Что делать дальше

> **Авторитетный roadmap:** [`docs/TODO.md`](TODO.md) — единый мастер-документ с фазами A/B/C (MVP), Post-MVP (D→N), Backlog (P2/P3).

### Ближайший приоритет — Фаза A (Foundation)

| Задача | Описание | Ссылка |
|---|---|---|
| **A.1** CLI entrypoint | `cognitive-core "вопрос"` + `examples/demo.py` | [TODO.md → A.1](TODO.md) |
| **A.2** ResourceMonitor ↔ CognitiveCore | Синхронизировать контракт, реальные данные вместо fallback | [TODO.md → A.2](TODO.md) |
| **A.3** Настоящий mypy gate | Убрать `\|\| true`, исправить критические type errors | [TODO.md → A.3](TODO.md) |

### Затем — Фаза B (Close the Loop)

| Задача | Описание |
|---|---|
| **B.1** Auto-encode в CognitiveCore | `run("запрос")` без ручного `encoded_percept` |
| **B.2** Perception hardening | Валидация путей, ограничение размера файлов |
| **B.3** Retrieval scope | Честное описание text-first retrieval |
| **B.4** README = правда | Полная синхронизация с реальным поведением |

### Post-MVP приоритеты

| Этап | Что | Зачем |
|---|---|---|
| **D** | Retrieval Upgrade | Persisted embeddings, ANN/FAISS, quality benchmarks |
| **E** | DRY Sweep | Убрать дубли (detect_language, extract_fact, JSON helpers) |
| **F** | Hardening & DX | Lazy loading, graceful shutdown, concurrency tests, Docker |
| **N** | LLM Bridge | Опциональная интеграция для richer response generation |
| **H** | Attention & Resource Control | SalienceEngine, PolicyLayer, Ring 2 |

### Backlog (не блокирует MVP)

- P2.1: TTL/LRU для BrainLogger индексов
- P2.4: Property-based / fuzz testing
- P2.10: `copy.deepcopy` → `dataclasses.replace` в ContradictionDetector
- P3.1: NLI-модель для contradiction detection
- P3.2: OpenTelemetry вместо кастомного трейсинга

---

## Финальный вывод

`cognitive-core` за первые 5 дней — это **не "ещё один амбициозный AI-репозиторий с красивыми словами"**, а уже **собранный технический каркас**, на котором действительно можно строить дальше.

Сильнейшие стороны проекта:
- хорошая архитектура (спроектирована на вырост);
- очень достойная система памяти;
- дисциплина тестов и CI;
- observability / traceability;
- разумный foundation для дальнейшего cognitive pipeline.

Честные слабости:
- cognitive pipeline — heuristic scoring, не полноценный reasoning engine;
- output — инфраструктурно готов, но ответы шаблонные;
- тесты — количество сильное, глубина средняя;
- legacy-артефакты создают путаницу.

Главный следующий вызов:
> **Сделать проект не только хорошо спроектированным, но и легко запускаемым, демонстрируемым и проверяемым извне.**

Если коротко:

**Сейчас это сильный инженерный фундамент (8.0/10).  
Следующий шаг — превратить его в убедительный runnable MVP (Фаза A → B → C).**
