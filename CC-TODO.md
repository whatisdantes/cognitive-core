# TODO.md — Cognitive Core Roadmap

> **Стратегия:** hardening → cleanup → reliability → testing → packaging → expansion
> **Принцип:** не добавлять новое, пока не уплотнено старое.
> Приоритет: 🔴 P0 (неделя 1) → 🟠 P1 (недели 2–3) → 🟡 P2 (недели 3–4) → 🟢 P3 (неделя 5+) → 🔵 P4 (после hardening)

---

## Принципы

- Сначала риски, потом удобство, потом фичи.
- Два режима проекта — **core mode** (без LLM) и **llm-augmented mode** (с LLM) — оба first-class.
- Каждый этап имеет Definition of Done — критерий «когда хватит».
- Есть явный список того, что **НЕ** делать (см. конец документа).

---

## 🔴 P0 — Security, Safety & Честность (неделя 1)

> 80% эффекта за 20% усилий. После этого этапа проект выглядит и работает в разы серьёзнее.

### 1. Починить SQL injection в `PRAGMA key`

- [ ] **Файл:** `brain/memory/storage.py:244`
- [ ] Добавить валидацию `encryption_key` через regex: `^[a-zA-Z0-9_\-]{8,128}$`
- [ ] Удалить `# nosec B608` — это заглушка, а не фикс
- [ ] Добавить тесты на допустимые / недопустимые ключи
- [ ] Задокументировать ограничения на формат ключа

**Зачем:** `f"PRAGMA key = '{encryption_key}'"` — прямая интерполяция в SQL. Сейчас ключ из конфига, но завтра его протянут из API — и привет, injection. Единственная реальная уязвимость в проекте.

**Усилия:** 30–60 мин

---

### 2. Усилить BoundaryGuard

- [ ] Добавить `unicodedata.normalize('NFKD', text)` перед PII-regex
- [ ] Добавить защиту от obfuscation: `[at]`, `[dot]`, spaced text, homoglyphs
- [ ] Расширить паттерны phone / email / card / passport
- [ ] Добавить fuzz / property-based тесты для PII-редакции

**Зачем:** кириллическое «а» вместо латинского «a» обходит PII regex. `[at]` вместо `@` — тоже. Safety layer должен быть стеной, а не занавеской.

**Усилия:** 3–4 часа

---

### 3. Усилить SafetyPolicyLayer

- [ ] **Topic filter:** `if topic in text_lower` → word boundary regex (`\b...\b`)
- [ ] Добавить Unicode / leet normalization для topic filtering
- [ ] Разделить `WARN` и `BLOCK` политики по чётким правилам
- [ ] Добавить тесты на false positive / false negative сценарии

**Зачем:** `"violence" in "nonviolence"` = True. Safety, который фильтрует ложно — хуже, чем отсутствие safety.

**Усилия:** 2–3 часа

---

### 4. Починить `storage_backend="auto"`

- [ ] **Файл:** `brain/memory/memory_manager.py`
- [ ] `_should_use_sqlite()` сейчас всегда возвращает `True`
- [ ] **Вариант A:** Переименовать `"auto"` в `"sqlite"` (честно)
- [ ] **Вариант B:** Реализовать реальную эвристику

**Зачем:** API обещает умный выбор бэкенда. Реализация тупо возвращает `True`. Обман интерфейса.

**Усилия:** 30 мин

---

### 5. Решить позиционирование

- [ ] Выбрать один из двух путей:

| Путь | Что сделать |
|---|---|
| **A. «Когнитивный фреймворк»** | LLM → first-class, бесплатный провайдер (Ollama), reasoning через LLM — основной режим |
| **B. «Symbolic reasoning engine»** | Описать честно: «rule-based reasoning framework with optional LLM augmentation» |

- [ ] В README чётко указать: что умеет система без LLM, что появляется с LLM, чего система не делает
- [ ] Разделить examples на core mode и llm-augmented mode

**Зачем:** Название говорит «cognitive core», а по умолчанию LLM выключен. Оба пути честные. Нечестно — оставить как есть.

**Усилия:** 2–3 часа

---

### 6. Заполнить GitHub metadata + первый релиз

- [ ] Добавить description, website (ссылка на docs), topics
- [ ] Topics: `python`, `cognitive-architecture`, `reasoning`, `memory`, `ai-framework`
- [ ] Создать GitHub Release: `v0.7.0-alpha` с changelog

**Зачем:** Проект снаружи выглядит хуже, чем он есть внутри. 0 stars, 0 description, 0 релизов = сигнал «заброшено».

**Усилия:** 1 час

---

### 7. Quick-start в README

- [ ] Секция «Запуск за 2 минуты»:
  ```bash
  pip install cognitive-core
  python -m cognitive_core "Что такое когнитивная архитектура?"
  ```
- [ ] Минимальный Python-пример (5–7 строк)
- [ ] Что работает из коробки, что требует настройки

**Зачем:** Сейчас README — стена текста. Человек хочет попробовать за 2 минуты — если не может, уходит.

**Усилия:** 1 час

---

### ✅ Definition of Done для P0

- [ ] Нет небезопасной SQL-интерполяции
- [ ] Safety тесты покрывают obfuscation / Unicode / false positives
- [ ] API не врёт о своём поведении
- [ ] Есть секция в docs про threat model и ограничения safety
- [ ] Внешний человек понимает проект за 2 минуты из README
- [ ] Есть хотя бы один GitHub Release

---

## 🟠 P1 — Типизация и архитектура (недели 2–3)

> Внутренний порядок: типы, инкапсуляция, DRY, декомпозиция.

### 8. Ужесточить mypy поэтапно

- [ ] **Файл:** `pyproject.toml` → `[tool.mypy]`
- [ ] Включить `check_untyped_defs = true` глобально
- [ ] Включить `disallow_untyped_defs = true` поэтапно по пакетам:
  1. `brain/memory`
  2. `brain/cognition`
  3. `brain/safety`
  4. `brain/bridges`
- [ ] Поставить `warn_return_any = true`, `warn_unused_ignores = true`
- [ ] Оставить `ignore_missing_imports = true` (ок для optional deps)

**Зачем:** Сейчас mypy в CI — декорация. `check_untyped_defs = false` = проверка ничего не проверяет.

**Усилия:** 1–2 дня (поэтапно)

---

### 9. Сократить `Any` в критичных местах

- [ ] Убрать `Any` из контрактов и мостов между слоями
- [ ] Уточнить типы в `CognitivePipelineContext`
- [ ] Добавить typed dataclasses вместо неструктурированных `dict`
- [ ] Уточнить типы metadata-структур

**Зачем:** `Any` — дыра в типизации. Чем меньше `Any` на границах слоёв, тем надёжнее проект при росте.

**Усилия:** 3–4 часа

---

### 10. Публичные итераторы памяти

- [ ] **Файл:** `brain/cognition/cognitive_core.py` → `_build_vector_index()`
- [ ] Заменить `semantic._lock` / `semantic._nodes` → `semantic.iter_nodes()`
- [ ] Заменить `episodic._lock` / `episodic._episodes` → `episodic.iter_episodes()`
- [ ] Добавить публичные методы `iter_semantic_nodes()`, `iter_episodes()`, `iter_indexable_items()` в SemanticMemory и EpisodicMemory

**Зачем:** CognitiveCore лезет в private поля памяти. Любой рефакторинг памяти сломает когнитивный слой. Coupling через underscore — хрупко.

**Усилия:** 2–3 часа

---

### 11. Разбить `pipeline.py` (1220 строк)

- [ ] Создать пакет `brain/cognition/steps/`
- [ ] Вынести шаги по группам:
  - `steps/context.py` — контекст, парсинг, язык
  - `steps/reasoning.py` — анализ, гипотезы, LLM
  - `steps/safety.py` — проверки, границы
  - `steps/action.py` — действия, ответы
  - `steps/finalize.py` — финализация, выход
- [ ] Сократить shared mutable state в `CognitivePipelineContext`
- [ ] Явно задокументировать обязательные поля каждого шага
- [ ] Оставить `pipeline.py` как оркестратор (~100 строк)

**Зачем:** 1220 строк + 20 шагов + mutable context = god-class. Невозможно тестировать шаги изолированно.

**Усилия:** 1 день

---

### 12. Убить copy-paste

- [ ] Создать `brain/core/math_utils.py` с единственной `_l2_normalize`
- [ ] Удалить 5 копий из: `shared_space_projector.py`, `vision_encoder.py`, `text_encoder.py`, `temporal_encoder.py`, `audio_encoder.py`
- [ ] 4 обёртки `_detect_language` → прямой вызов `text_utils.detect_language()`
- [ ] Провести cleanup повторяющихся утилит в encoder / output / safety слоях

**Зачем:** Баг в нормализации → нужно чинить в 5 местах. Забыл одно — расхождение embeddings. Одна функция, один источник правды.

**Усилия:** 1–2 часа

---

### ✅ Definition of Done для P1

- [ ] Mypy даёт реальную ценность на каждом PR
- [ ] Критичные слои не зависят от широких `Any`
- [ ] CognitiveCore не лезет в private internals памяти
- [ ] Pipeline разбит на читаемые подмодули
- [ ] Нет дублированных утилит

---

## 🟡 P2 — Reliability & Runtime (недели 3–4)

> Потокобезопасность, обработка ошибок, предсказуемость runtime-путей.

### 13. Exception handling: перестать глотать ошибки

- [ ] Найти все `except Exception` (20+ мест)
- [ ] Разделить на категории:
  - `RetryableError` → retry с backoff
  - `FatalError` → raise
  - `Exception` (неизвестное) → log с traceback + raise
- [ ] Убрать все `except Exception: pass`
- [ ] Добавить structured logging для серьёзных сбоев

**Зачем:** Silent failures — самый дорогой вид долга. 20+ мест, где ошибки тихо проглатываются = 20 мёртвых зон для дебага.

**Усилия:** 1 день

---

### 14. Lock ordering

- [ ] Создать `docs/LOCK_ORDERING.md`
- [ ] Определить порядок захвата 12 RLock-ов:
  ```
  1. WorkingMemory._lock
  2. SemanticMemory._lock
  3. EpisodicMemory._lock
  4. SourceMemory._lock
  5. ProceduralMemory._lock
  6. ConsolidationEngine._lock
  ...
  ```
- [ ] Минимизировать nested-lock сценарии
- [ ] Проверить ConsolidationEngine на lock chaining
- [ ] (Опционально) Debug-assertion проверяющий порядок
- [ ] Добавить stress tests на многопоточность

**Зачем:** 12 RLock-ов без порядка = рецепт для deadlock. Один разработчик — ок. Двое — бомба.

**Усилия:** 3–4 часа

---

### 15. LLM timeout: отменять реальный запрос

- [ ] **Файл:** `brain/bridges/llm_bridge.py`
- [ ] Заменить `Thread.join(timeout=...)` на `concurrent.futures.ThreadPoolExecutor`
- [ ] Использовать `future.result(timeout=...)` + `future.cancel()`
- [ ] Добавить request lifecycle accounting (request ID, budget, duration)
- [ ] Добавить retry policy с backoff
- [ ] Добавить тесты на timeout / retry / cancellation
- [ ] Задокументировать поведение при timeout

**Зачем:** `thread.join(timeout)` перестаёт ждать, но запрос живёт в фоне. Утечка ресурсов, лишние API-расходы, race conditions.

**Усилия:** 3–4 часа

---

### 16. Hardcoded paths → конфигурируемые

- [ ] `data_dir: str = "brain/data/memory"` → через `XDG_DATA_HOME` или `pathlib.Path`
- [ ] Проверить все относительные пути — они сломаются при запуске из другой директории

**Зачем:** `cd /tmp && python -m cognitive_core` — и всё упало. Docker, systemd, cron — везде другой CWD.

**Усилия:** 1–2 часа

---

### 17. Consolidation daemon → Event-based

- [ ] Заменить `while self._running: time.sleep(1.0)` → `threading.Event.wait(timeout=1.0)`
- [ ] Добавить чистый shutdown через `stop_event.set()`

**Зачем:** `time.sleep(1)` в цикле — busy wait. `Event.wait()` — мгновенный graceful shutdown.

**Усилия:** 30 мин

---

### ✅ Definition of Done для P2

- [ ] Ошибки не прячутся за warning
- [ ] Concurrency model понятна и задокументирована
- [ ] Поведение LLM bridge при timeout формально определено
- [ ] Нет hardcoded путей, зависящих от CWD

---

## 🟢 P3 — Testing & CI (неделя 5)

> Тесты, которые ловят regressions, а не просто подтверждают happy path.

### 18. Safety-тесты и fuzz

- [ ] Fuzz-тесты для BoundaryGuard (Hypothesis)
- [ ] Property-based тесты для SafetyPolicyLayer
- [ ] Покрыть обходы: obfuscation / Unicode / spacing / leet
- [ ] Safety regression suite

**Усилия:** 1 день

---

### 19. Contract tests

- [ ] Round-trip тесты: `to_dict()` → `from_dict()` для всех dataclasses
- [ ] Проверить сериализацию enum / dataclass metadata
- [ ] Invariant tests для core contracts

**Усилия:** 3–4 часа

---

### 20. Mutation testing

- [ ] Подключить `mutmut` для:
  - `brain/safety`
  - `brain/core/event_bus.py`
  - `brain/memory/storage.py`

**Зачем:** 84% coverage — число красивое, но не говорит о качестве. Mutation testing проверяет: «если сломать код, упадёт ли хоть один тест?»

**Усилия:** 1 день

---

### 21. CI: расширить quality gate

- [ ] `mkdocs build --strict` — ловить doc drift автоматически
- [ ] Docker smoke test: `docker run ... cognitive-core --version`
- [ ] Тесты optional extras: `pip install .[openai,anthropic,encrypted,docs]`
- [ ] CLI e2e smoke test

**Усилия:** 2–3 часа

---

### ✅ Definition of Done для P3

- [ ] Safety покрыт fuzz / property-based тестами
- [ ] Contracts проверяются round-trip
- [ ] CI проверяет не только код, но и docs / container / extras

---

## 🔵 P4 — Packaging, Demos & Feature Expansion (после hardening)

> Только после P0–P3. Сначала прочность — потом рост.

### 22. Release discipline

- [ ] Определить semver-политику
- [ ] Настроить commitlint: `feat(memory):`, `fix(safety):`, `refactor(pipeline):`
- [ ] Автогенерация changelog из коммитов
- [ ] Завести секцию `Unreleased` в CHANGELOG

**Усилия:** 2–3 часа

---

### 23. Документация: синхронизация и карта

- [ ] Проверить нумерацию шагов в pipeline docs — drift уже начался
- [ ] Добавить architecture map для контрибьюторов
- [ ] Раздел «Known limitations» в docs
- [ ] Обновить CONTRIBUTING под новый roadmap

**Усилия:** 3–4 часа

---

### 24. Benchmark suite

- [ ] Latency на полный reasoning cycle
- [ ] Retrieval latency (memory search)
- [ ] Memory save / load time
- [ ] Startup time
- [ ] Результаты → CI artifacts для отслеживания регрессий

**Усилия:** 1 день

---

### 25. LLM integration demo

- [ ] `examples/ollama_demo.py` — полный цикл reasoning с бесплатной LLM
- [ ] Показать разницу «без LLM» vs «с LLM» на одном запросе
- [ ] GIF / видео для README

**Усилия:** 3–4 часа

---

### 26. Rate limiter → persistent storage

- [ ] Вынести rate limiting из in-memory dict → Redis / SQLite / абстракция `RateLimiterBackend`

**Усилия:** 3–4 часа

---

### 27. Feature expansion: reasoning & memory

- [ ] Усилить contradiction resolution
- [ ] Добавить evidence weighting
- [ ] Улучшить hypothesis pruning / ranking
- [ ] LLM budget control для вызовов
- [ ] Structured prompt policies
- [ ] Fallback strategy при недоступности провайдера
- [ ] Улучшить background consolidation semantics
- [ ] Memory maintenance jobs
- [ ] Benchmark-набор вопросов и ожиданий

**Усилия:** 2+ недели

---

### ✅ Definition of Done для P4

- [ ] Есть предсказуемый release process
- [ ] Документация синхронизирована с кодом
- [ ] Benchmarks отслеживают регрессии
- [ ] LLM mode демонстрируется наглядно
- [ ] Reasoning стал заметно качественнее

---

## 🚫 Что сознательно НЕ делать сейчас

| Анти-цель | Почему |
|---|---|
| Не добавлять новые modality-подсистемы | Пока не hardened текущее ядро |
| Не расширять safety «вширь» | Пока не усилен базовый enforcement |
| Не усложнять LLM orchestration | Пока не починены timeout / runtime semantics |
| Не делать aggressive feature growth | Пока pipeline не упрощён |
| Не переписывать на async | Sync/threaded — нормально для текущего scope; проблема в discipline, а не в парадигме |
| Не гнаться за 100% coverage | Качество тестов важнее количества |

---

## 📊 Сводная таблица

| # | Задача | Приоритет | Усилия | Эффект |
|---|---|:---:|:---:|:---:|
| 1 | PRAGMA key injection | 🔴 P0 | 30–60 мин | 🔒 Security |
| 2 | BoundaryGuard hardening | 🔴 P0 | 3–4 ч | 🔒 Safety |
| 3 | SafetyPolicyLayer hardening | 🔴 P0 | 2–3 ч | 🔒 Safety |
| 4 | storage_backend fix | 🔴 P0 | 30 мин | 🎯 Честность |
| 5 | Позиционирование | 🔴 P0 | 2–3 ч | 🎯 Честность |
| 6 | GitHub metadata + release | 🔴 P0 | 1 ч | 📦 Упаковка |
| 7 | Quick-start README | 🔴 P0 | 1 ч | 📦 Onboarding |
| 8 | Mypy strict (поэтапно) | 🟠 P1 | 1–2 дня | 🛡️ Type safety |
| 9 | Сократить `Any` | 🟠 P1 | 3–4 ч | 🛡️ Type safety |
| 10 | Публичные итераторы | 🟠 P1 | 2–3 ч | 🏗️ Архитектура |
| 11 | Pipeline → steps/ | 🟠 P1 | 1 день | 🏗️ Архитектура |
| 12 | DRY: math_utils + wrappers | 🟠 P1 | 1–2 ч | 🧹 Гигиена |
| 13 | Exception handling | 🟡 P2 | 1 день | 🐛 Debuggability |
| 14 | Lock ordering | 🟡 P2 | 3–4 ч | 🔒 Thread safety |
| 15 | LLM timeout / cancellation | 🟡 P2 | 3–4 ч | 🔒 Resource safety |
| 16 | Hardcoded paths | 🟡 P2 | 1–2 ч | 🐛 Portability |
| 17 | Event-based daemon | 🟡 P2 | 30 мин | 🧹 Гигиена |
| 18 | Safety fuzz/property tests | 🟢 P3 | 1 день | ✅ Test quality |
| 19 | Contract tests | 🟢 P3 | 3–4 ч | ✅ Test quality |
| 20 | Mutation testing | 🟢 P3 | 1 день | ✅ Test quality |
| 21 | CI расширение | 🟢 P3 | 2–3 ч | ✅ Quality gate |
| 22 | Release discipline | 🔵 P4 | 2–3 ч | 📦 Process |
| 23 | Docs sync + arch map | 🔵 P4 | 3–4 ч | 📖 Documentation |
| 24 | Benchmarks | 🔵 P4 | 1 день | 📊 Observability |
| 25 | LLM demo + GIF | 🔵 P4 | 3–4 ч | 📦 Подача |
| 26 | Persistent rate limiter | 🔵 P4 | 3–4 ч | 🔒 Production |
| 27 | Feature expansion | 🔵 P4 | 2+ нед | 🚀 Capabilities |

---

**Общая оценка:** ~3–4 недели focused work для P0–P3, ещё ~2–3 недели для P4.

> К концу этого roadmap проект станет: безопаснее, честнее, проще в сопровождении, лучше протестирован, зрелее как OSS — и только после этого сильнее по reasoning/LLM-возможностям.
