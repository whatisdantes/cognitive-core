# PLAN_CC.md — Рабочий план по CC-TODO.md
> Формат: каждая задача = один атомарный шаг с чёткими критериями готовности.
> Обновляю `[x]` после каждого завершённого шага.
> Стратегия: hardening → cleanup → reliability → testing → packaging → expansion

---

## 🔴 P0 — Security, Safety & Честность

> DoD: нет SQL injection · safety покрывает Unicode/obfuscation · API не врёт · README понятен за 2 мин · есть GitHub Release

### CC-01 · SQL injection в `storage.py` ✅ DONE
- [x] Прочитать `brain/memory/storage.py:244`
- [x] Добавить валидацию `encryption_key` через regex `^[a-zA-Z0-9_\-]{8,128}$`
- [x] Удалить `# nosec B608`
- [x] Написать тесты: допустимые / недопустимые ключи (14 тестов в `TestEncryptionKeyValidation`)
- [x] Задокументировать ограничения формата ключа в docstring
- **Файл:** `brain/memory/storage.py` · **Тесты:** `tests/test_storage_encrypted.py`
- **Результат:** 2156 passed (полный прогон) + 14/14 CC-01 тестов ✅
- **Примечание:** `TestEncryptedDatabase` (4 теста) падают из-за pre-existing bug `TypeError: Row() argument 1 must be sqlite3.Cursor, not sqlcipher3.dbapi2.Cursor` — не связан с CC-01, зафиксирован как отдельная задача (см. CC-28 ниже)

### CC-02 · BoundaryGuard hardening ⏱ 3–4 ч
- [ ] Добавить `unicodedata.normalize('NFKD', text)` перед PII-regex
- [ ] Добавить защиту от obfuscation: `[at]`, `[dot]`, spaced text, homoglyphs
- [ ] Расширить паттерны: phone / email / card / passport
- [ ] Написать fuzz / property-based тесты (Hypothesis) для PII-редакции
- **Файл:** `brain/safety/boundary_guard.py` · **Тесты:** `tests/test_boundary_guard.py`

### CC-03 · SafetyPolicyLayer hardening ⏱ 2–3 ч
- [ ] Заменить `if topic in text_lower` → word boundary regex `\bTOPIC\b`
- [ ] Добавить Unicode / leet normalization для topic filtering
- [ ] Разделить WARN и BLOCK политики по чётким правилам
- [ ] Написать тесты на false positive / false negative сценарии
- **Файл:** `brain/safety/policy_layer.py` · **Тесты:** `tests/test_safety_policy_layer.py`

### CC-04 · `storage_backend="auto"` fix ⏱ 30 мин
- [ ] Прочитать `brain/memory/memory_manager.py` → `_should_use_sqlite()`
- [ ] Выбрать: A (переименовать в `"sqlite"`) или B (реальная эвристика)
- [ ] Реализовать выбранный вариант
- [ ] Обновить тесты
- **Файл:** `brain/memory/memory_manager.py`

### CC-05 · Позиционирование проекта ⏱ 2–3 ч
- [ ] Выбрать путь: A (LLM first-class) или B (symbolic reasoning + optional LLM)
- [ ] Обновить README: что умеет без LLM / с LLM / чего не делает
- [ ] Разделить examples на core mode и llm-augmented mode
- [ ] Добавить секцию threat model и ограничения safety в docs
- **Файлы:** `README.md` · `examples/`

### CC-06 · GitHub metadata + первый релиз ⏱ 1 ч
- [ ] Добавить description, website, topics в GitHub
- [ ] Topics: `python`, `cognitive-architecture`, `reasoning`, `memory`, `ai-framework`
- [ ] Создать GitHub Release `v0.7.0-alpha` с changelog
- **Файл:** `CHANGELOG.md`

### CC-07 · Quick-start в README ⏱ 1 ч
- [ ] Добавить секцию «Запуск за 2 минуты» с `pip install` + `python -m`
- [ ] Минимальный Python-пример (5–7 строк)
- [ ] Указать: что работает из коробки, что требует настройки
- **Файл:** `README.md`

**✅ P0 DoD:**
- [ ] Нет небезопасной SQL-интерполяции
- [ ] Safety тесты покрывают obfuscation / Unicode / false positives
- [ ] API не врёт о своём поведении
- [ ] Внешний человек понимает проект за 2 минуты из README
- [ ] Есть хотя бы один GitHub Release

---

## 🟠 P1 — Типизация и архитектура

> DoD: mypy даёт реальную ценность · нет `Any` на границах · нет private coupling · pipeline читаем · нет дублей

### CC-08 · Mypy strict (поэтапно) ⏱ 1–2 дня
- [ ] `pyproject.toml`: включить `check_untyped_defs = true` глобально
- [ ] Включить `disallow_untyped_defs = true` для `brain/memory`
- [ ] Включить `disallow_untyped_defs = true` для `brain/cognition`
- [ ] Включить `disallow_untyped_defs = true` для `brain/safety`
- [ ] Включить `disallow_untyped_defs = true` для `brain/bridges`
- [ ] Добавить `warn_return_any = true`, `warn_unused_ignores = true`
- [ ] Прогнать `mypy brain/` → 0 errors
- **Файл:** `pyproject.toml`

### CC-09 · Сократить `Any` в критичных местах ⏱ 3–4 ч
- [ ] Убрать `Any` из контрактов и мостов между слоями
- [ ] Уточнить типы в `CognitivePipelineContext`
- [ ] Заменить неструктурированные `dict` на typed dataclasses
- [ ] Уточнить типы metadata-структур
- **Файлы:** `brain/core/contracts.py` · `brain/cognition/pipeline.py`

### CC-10 · Публичные итераторы памяти ⏱ 2–3 ч
- [ ] Добавить `iter_nodes()` в `SemanticMemory`
- [ ] Добавить `iter_episodes()` в `EpisodicMemory`
- [ ] Заменить в `cognitive_core.py`: `semantic._lock/_nodes` → `semantic.iter_nodes()`
- [ ] Заменить в `cognitive_core.py`: `episodic._lock/_episodes` → `episodic.iter_episodes()`
- [ ] Обновить тесты
- **Файлы:** `brain/memory/semantic_memory.py` · `brain/memory/episodic_memory.py` · `brain/cognition/cognitive_core.py`

### CC-11 · Разбить `pipeline.py` (1220 строк) ⏱ 1 день
- [ ] Создать пакет `brain/cognition/steps/`
- [ ] Вынести: `steps/context.py` (контекст, парсинг, язык)
- [ ] Вынести: `steps/reasoning.py` (анализ, гипотезы, LLM)
- [ ] Вынести: `steps/safety.py` (проверки, границы)
- [ ] Вынести: `steps/action.py` (действия, ответы)
- [ ] Вынести: `steps/finalize.py` (финализация, выход)
- [ ] Оставить `pipeline.py` как оркестратор (~100 строк)
- [ ] Все тесты проходят после рефакторинга
- **Файлы:** `brain/cognition/pipeline.py` → `brain/cognition/steps/`

### CC-12 · DRY: убить copy-paste ⏱ 1–2 ч
- [ ] Создать `brain/core/math_utils.py` с единственной `_l2_normalize()`
- [ ] Удалить копии из: `shared_space_projector.py`, `vision_encoder.py`, `text_encoder.py`, `temporal_encoder.py`, `audio_encoder.py`
- [ ] Унифицировать 4 обёртки `_detect_language` → `text_utils.detect_language()`
- [ ] Прогнать тесты → 0 failures
- **Файлы:** `brain/core/math_utils.py` (новый) · 5 encoder/fusion файлов

**✅ P1 DoD:**
- [ ] Mypy даёт реальную ценность на каждом PR
- [ ] Критичные слои не зависят от широких `Any`
- [ ] CognitiveCore не лезет в private internals памяти
- [ ] Pipeline разбит на читаемые подмодули
- [ ] Нет дублированных утилит

---

## 🟡 P2 — Reliability & Runtime

> DoD: ошибки не прячутся · concurrency задокументирована · LLM timeout определён · нет hardcoded путей

### CC-13 · Exception handling ⏱ 1 день
- [ ] Найти все `except Exception` (20+ мест) через `search_files`
- [ ] Категоризировать: RetryableError / FatalError / Unknown
- [ ] Убрать все `except Exception: pass`
- [ ] Добавить structured logging с traceback для серьёзных сбоев
- [ ] Прогнать тесты → 0 failures

### CC-14 · Lock ordering ⏱ 3–4 ч
- [ ] Создать `docs/LOCK_ORDERING.md`
- [ ] Определить порядок захвата всех RLock-ов (12 штук)
- [ ] Минимизировать nested-lock сценарии
- [ ] Проверить `ConsolidationEngine` на lock chaining
- [ ] Добавить stress tests на многопоточность
- **Файл:** `docs/LOCK_ORDERING.md` (новый)

### CC-15 · LLM timeout: реальная отмена ⏱ 3–4 ч
- [ ] Заменить `Thread.join(timeout=...)` → `concurrent.futures.ThreadPoolExecutor`
- [ ] Использовать `future.result(timeout=...)` + `future.cancel()`
- [ ] Добавить request lifecycle accounting (request ID, budget, duration)
- [ ] Добавить retry policy с backoff
- [ ] Написать тесты на timeout / retry / cancellation
- **Файл:** `brain/bridges/llm_bridge.py` · **Тесты:** `tests/test_llm_bridge.py`

### CC-16 · Hardcoded paths → конфигурируемые ⏱ 1–2 ч
- [ ] Заменить `"brain/data/memory"` → `XDG_DATA_HOME` или `pathlib.Path`
- [ ] Проверить все относительные пути в проекте
- [ ] Убедиться что `cd /tmp && python -m cognitive_core` работает
- **Файлы:** `brain/memory/storage.py` · `brain/memory/memory_manager.py`

### CC-17 · Consolidation daemon → Event-based ⏱ 30 мин
- [ ] Заменить `while self._running: time.sleep(1.0)` → `threading.Event.wait(timeout=1.0)`
- [ ] Добавить чистый shutdown через `stop_event.set()`
- [ ] Обновить тесты
- **Файл:** `brain/memory/consolidation_engine.py`

**✅ P2 DoD:**
- [ ] Ошибки не прячутся за warning
- [ ] Concurrency model понятна и задокументирована
- [ ] Поведение LLM bridge при timeout формально определено
- [ ] Нет hardcoded путей, зависящих от CWD

---

## 🟢 P3 — Testing & CI

> DoD: safety покрыт fuzz · contracts проверяются round-trip · CI проверяет docs/container/extras

### CC-18 · Safety fuzz / property-based тесты ⏱ 1 день
- [ ] Fuzz-тесты для `BoundaryGuard` (Hypothesis)
- [ ] Property-based тесты для `SafetyPolicyLayer`
- [ ] Покрыть обходы: obfuscation / Unicode / spacing / leet
- [ ] Safety regression suite
- **Тесты:** `tests/test_boundary_guard.py` · `tests/test_safety_policy_layer.py`

### CC-19 · Contract tests ⏱ 3–4 ч
- [ ] Round-trip тесты: `to_dict()` → `from_dict()` для всех dataclasses
- [ ] Проверить сериализацию enum / dataclass metadata
- [ ] Invariant tests для core contracts
- **Тесты:** `tests/test_contracts_hypothesis.py`

### CC-20 · Mutation testing ⏱ 1 день
- [ ] Подключить `mutmut` для `brain/safety`
- [ ] Подключить `mutmut` для `brain/core/event_bus.py`
- [ ] Подключить `mutmut` для `brain/memory/storage.py`
- [ ] Зафиксировать mutation score baseline
- **Примечание:** проверить поддержку Windows (ранее было заморожено)

### CC-21 · CI расширение ⏱ 2–3 ч
- [ ] `mkdocs build --strict` в CI
- [ ] Docker smoke test: `docker run ... cognitive-core --version`
- [ ] Тесты optional extras: `pip install .[openai,anthropic,encrypted,docs]`
- [ ] CLI e2e smoke test
- **Файл:** `.github/workflows/`

**✅ P3 DoD:**
- [ ] Safety покрыт fuzz / property-based тестами
- [ ] Contracts проверяются round-trip
- [ ] CI проверяет не только код, но и docs / container / extras

---

## 🔵 P4 — Packaging, Demos & Feature Expansion

> Только после P0–P3. Сначала прочность — потом рост.

### CC-22 · Release discipline ⏱ 2–3 ч
- [ ] Определить semver-политику
- [ ] Настроить commitlint: `feat(memory):`, `fix(safety):`, `refactor(pipeline):`
- [ ] Автогенерация changelog из коммитов
- [ ] Завести секцию `Unreleased` в CHANGELOG

### CC-23 · Документация: синхронизация ⏱ 3–4 ч
- [ ] Проверить нумерацию шагов в pipeline docs (drift уже начался)
- [ ] Добавить architecture map для контрибьюторов
- [ ] Раздел «Known limitations» в docs
- [ ] Обновить CONTRIBUTING под новый roadmap

### CC-24 · Benchmark suite ⏱ 1 день
- [ ] Latency: полный reasoning cycle
- [ ] Latency: retrieval (memory search)
- [ ] Latency: memory save / load
- [ ] Startup time
- [ ] Результаты → CI artifacts

### CC-25 · LLM integration demo ⏱ 3–4 ч
- [ ] `examples/ollama_demo.py` — полный цикл с бесплатной LLM
- [ ] Показать разницу «без LLM» vs «с LLM» на одном запросе
- [ ] GIF / видео для README

### CC-26 · Rate limiter → persistent storage ⏱ 3–4 ч
- [ ] Вынести rate limiting из in-memory dict → абстракция `RateLimiterBackend`
- [ ] Реализовать SQLite backend

### CC-27 · Feature expansion ⏱ 2+ нед
- [ ] Усилить contradiction resolution
- [ ] Evidence weighting
- [ ] Hypothesis pruning / ranking
- [ ] LLM budget control
- [ ] Structured prompt policies
- [ ] Fallback strategy при недоступности провайдера
- [ ] Background consolidation semantics
- [ ] Memory maintenance jobs
- [ ] Benchmark-набор вопросов и ожиданий

**✅ P4 DoD:**
- [ ] Есть предсказуемый release process
- [ ] Документация синхронизирована с кодом
- [ ] Benchmarks отслеживают регрессии
- [ ] LLM mode демонстрируется наглядно

---

## 🚫 Что НЕ делать

| Анти-цель | Почему |
|---|---|
| Новые modality-подсистемы | Пока не hardened текущее ядро |
| Расширять safety «вширь» | Пока не усилен базовый enforcement |
| Усложнять LLM orchestration | Пока не починены timeout / runtime semantics |
| Aggressive feature growth | Пока pipeline не упрощён |
| Переписывать на async | Проблема в discipline, а не в парадигме |
| Гнаться за 100% coverage | Качество тестов важнее количества |

---

## 📊 Прогресс

| Приоритет | Задач | Выполнено | Статус |
|---|:---:|:---:|---|
| 🔴 P0 | 7 | 1 | 🟡 |
| 🟠 P1 | 5 | 0 | ⬜ |
| 🟡 P2 | 5 | 0 | ⬜ |
| 🟢 P3 | 4 | 0 | ⬜ |
| 🔵 P4 | 6 | 0 | ⬜ |
| **Итого** | **27** | **1** | 🟡 |

---

## 🐛 Known Bugs (зафиксированы, не в scope текущих CC)

### CC-28 · sqlcipher3 Row() cursor incompatibility
- **Симптом:** `TypeError: Row() argument 1 must be sqlite3.Cursor, not sqlcipher3.dbapi2.Cursor`
- **Где:** `brain/memory/storage.py` — `conn.row_factory = sqlite3.Row` несовместим с sqlcipher3 cursor
- **Тесты:** `TestEncryptedDatabase` (4 теста) — падают при наличии sqlcipher3
- **Статус:** Pre-existing, не введён CC-01. Требует отдельного фикса: заменить `sqlite3.Row` на `dict`-based row factory или использовать `sqlcipher3.Row`
- **Приоритет:** P1 (блокирует encrypted DB функциональность)

---

## 🔄 Workflow для каждой задачи

1. **Brainstorm** — уточнить задачу, edge cases
2. **Read** — прочитать затронутые файлы
3. **TDD** — написать тесты первыми (red)
4. **Code** — реализовать (green)
5. **Verify** — `pytest` + `mypy` + `ruff` → 0 errors
6. **Update** — отметить `[x]` в этом файле
