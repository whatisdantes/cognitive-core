# 📊 Полный анализ проекта cognitive-core v0.7.0

> **Метод:** сравнение фактического состояния кода с документацией  
> **Источники:** файловая структура `brain/`, `tests/`, все `.md` файлы, `pyproject.toml`

---

## 1. Общая сводка

| Параметр | Документация | Факт | Расхождение |
|----------|-------------|------|-------------|
| Тесты | 1339 (TODO) / 1346 (README) | **1774 passed, 5 skipped** | ❌ Устарело на ~430 тестов |
| Шаги пайплайна | 10 (BRAIN) / 12 (README, index) | **15 шагов** | ❌ Устарело |
| Модули brain/ | 8 пакетов (README) | **10 пакетов** (+ bridges/, learning/ не stub) | ❌ Не отражены |
| Тестовые файлы | 21 (README) | **29 файлов** (+ 8 новых) | ❌ Не отражены |
| P3 прогресс | 0/13 (TODO) / 9/12 (README) | **~12/13** (только mutmut не сделан) | ❌ Устарело |
| Этап H (Attention) | "⬜ Post-MVP" (README) | **✅ Реализован** | ❌ Не отражён |
| Этап N (LLM Bridge) | Отсутствует в TODO.md | **✅ Реализован** | ❌ Не отражён |
| Этап I (Learning) | "⬜ Post-MVP" (README) | **Частично реализован** (3 модуля) | ❌ Не отражён |

---

## 2. Фактическое состояние кода

### 2.1 Модули brain/ (10 пакетов)

```
brain/
├── core/               ✅ 8 файлов (events, contracts, event_bus, scheduler, resource_monitor,
│                                     attention_controller*, text_utils, hash_utils)
├── perception/         ✅ 5 файлов (input_router, text_ingestor, metadata_extractor, validators, __init__)
├── encoders/           ✅ 2 файла (text_encoder, __init__)
├── memory/             ✅ 10 файлов (7 видов памяти + storage + migrate + manager)
├── cognition/          ✅ 14 файлов (cognitive_core, pipeline, context, goal_manager, planner,
│                                     hypothesis_engine, reasoner, action_selector, retrieval_adapter,
│                                     contradiction_detector, uncertainty_monitor,
│                                     salience_engine*, policy_layer*, __init__)
├── bridges/            ✅ 3 файла (llm_bridge*, safety_wrapper*, __init__) — НЕ В README
├── learning/           ✅ 4 файла (online_learner*, knowledge_gap_detector*,
│                                   replay_engine*, __init__) — README ГОВОРИТ "stub"
├── output/             ✅ 4 файла (trace_builder, response_validator, dialogue_responder, __init__)
├── logging/            ✅ 4 файла (brain_logger, digest_generator, reasoning_tracer, __init__)
├── fusion/             🔵 stub (только __init__.py)
├── safety/             🔵 stub (только __init__.py)
└── cli.py              ✅ CLI entrypoint
```

**Файлы, помеченные `*` — существуют в коде, но НЕ отражены в README/структуре проекта.**

### 2.2 Тестовые файлы (29 файлов)

| Файл | В README? | Статус |
|------|-----------|--------|
| test_bm25.py | ✅ | Документирован |
| test_cli.py | ✅ | Документирован |
| test_cognition.py | ✅ | Документирован |
| test_cognition_integration.py | ✅ | Документирован |
| test_concurrency_stress.py | ✅ | Документирован |
| test_contracts_hypothesis.py | ✅ | Документирован |
| test_e2e_pipeline.py | ✅ | Документирован |
| test_golden.py | ✅ | Документирован |
| test_logging.py | ✅ | Документирован |
| test_memory.py | ✅ | Документирован |
| test_output.py | ✅ | Документирован |
| test_output_integration.py | ✅ | Документирован |
| test_perception.py | ✅ | Документирован |
| test_perception_hardening.py | ✅ | Документирован |
| test_persistence_integration.py | ✅ | Документирован |
| test_resource_monitor.py | ✅ | Документирован |
| test_scheduler.py | ✅ | Документирован |
| test_storage.py | ✅ | Документирован |
| test_text_encoder.py | ✅ | Документирован |
| test_utils.py | ✅ | Документирован |
| test_vector_retrieval.py | ✅ | Документирован |
| **test_attention_controller.py** | ❌ | **Не в README** |
| **test_knowledge_gap_detector.py** | ❌ | **Не в README** |
| **test_llm_bridge.py** | ❌ | **Не в README** |
| **test_online_learner.py** | ❌ | **Не в README** |
| **test_policy_layer.py** | ❌ | **Не в README** |
| **test_replay_engine.py** | ❌ | **Не в README** |
| **test_salience_engine.py** | ❌ | **Не в README** |
| **test_storage_encrypted.py** | ❌ | **Не в README** |

### 2.3 Пайплайн (15 шагов — факт)

```
 1. create_context        — создание контекста
 2. auto_encode           — кодирование запроса
 3. get_resources         — состояние ресурсов
 4. build_retrieval_query — обогащение запроса
 5. create_goal           — определение цели
 6. evaluate_salience     — оценка значимости (Этап H)
 7. compute_budget        — бюджет внимания (Этап H)
 8. index_percept_vector  — индексация вектора
 9. reason                — reasoning loop
10. llm_enhance           — LLM обогащение (Этап N, no-op без LLM)
11. select_action         — выбор действия + PolicyLayer (Этап H)
12. execute_action        — выполнение действия
13. complete_goal         — завершение цели
14. build_result          — сборка результата
15. publish_event         — публикация события
```

### 2.4 Реализованные слои (факт)

| # | Слой | Статус | Модули |
|---|------|--------|--------|
| 00 | Autonomous Loop | ✅ | scheduler, event_bus (ThreadPool), resource_monitor |
| 01 | Perception | ✅ | text_ingestor, input_router, metadata_extractor, validators |
| 02 | Modality Encoders | ✅ | text_encoder (768d/300d) |
| 03 | Cross-Modal Fusion | 🔵 stub | fusion/__init__.py |
| 04 | Memory System | ✅ | 5 видов + consolidation + manager + SQLite + SQLCipher |
| 05 | Cognitive Core | ✅ | 14 модулей (pipeline 15 шагов) |
| 06 | Learning Loop | **⚡ Частично** | online_learner, knowledge_gap_detector, replay_engine |
| 07 | Output Layer | ✅ | trace_builder, response_validator, dialogue_responder |
| 08 | Attention/Resource | **⚡ Реализован** | resource_monitor, attention_controller, salience_engine, policy_layer |
| 09 | Logging | ✅ | brain_logger, digest_generator, reasoning_tracer |
| 10 | Safety | 🔵 stub | safety/__init__.py |
| 11 | Midbrain/Reward | ❌ absent | Не существует |
| — | LLM Bridge | **✅ Новый** | bridges/llm_bridge, bridges/safety_wrapper |

---

## 3. Расхождения по файлам документации

### 3.1 README.md — 14 расхождений

| # | Место | Проблема | Факт |
|---|-------|----------|------|
| 1 | Шапка: "Тесты: 1346/1346" | Устаревшее число | **1774 passed, 5 skipped** |
| 2 | Быстрый старт: "1346 ✅" | Устаревшее число | **1774** |
| 3 | Capability matrix: "12-step CognitivePipeline" | Устаревшее число | **15 шагов** |
| 4 | Capability matrix: "Learning Loop 🔮 Planned" | Частично реализован | **3 модуля в brain/learning/** |
| 5 | Capability matrix: "Reward & Motivation 🔮 Planned" | Корректно | — |
| 6 | Архитектура: "SalienceEngine 🔮 Post-MVP" | Реализован | **brain/cognition/salience_engine.py** |
| 7 | Архитектура: "AttentionController 🔮 Этап H" | Реализован | **brain/core/attention_controller.py** |
| 8 | Архитектура: "OnlineLearner 🔮" | Реализован | **brain/learning/online_learner.py** |
| 9 | Структура проекта: нет brain/bridges/ | Отсутствует | **3 файла в brain/bridges/** |
| 10 | Структура проекта: "brain/learning/ — stub" | Не stub | **3 реальных модуля** |
| 11 | Структура проекта: нет salience_engine, policy_layer, attention_controller | Отсутствуют | **Существуют** |
| 12 | Таблица тестов: 21 файл, 1346 тестов | Устарело | **29 файлов, 1774 тестов** |
| 13 | Прогресс: "P3 🔄 9/12" | Устарело | **~12/13** |
| 14 | Прогресс: "H ⬜ Post-MVP" | Реализован | **Этап H завершён** |

### 3.2 TODO.md — 8 расхождений

| # | Место | Проблема | Факт |
|---|-------|----------|------|
| 1 | Шапка: "Тесты: 1339/1339" | Устаревшее число | **1774** |
| 2 | Шапка: "Coverage: 84.44%" | Возможно устарело | Нужна перепроверка |
| 3 | P3 секция: "[ ] 0/13" | Грубо устарело | **~12/13 завершено** |
| 4 | Нет упоминания Этапа H | Отсутствует | **Реализован полностью** |
| 5 | Нет упоминания Этапа N (LLM Bridge) | Отсутствует | **Реализован полностью** |
| 6 | Нет упоминания Этапа I (Learning) | Только в "Архитектурное расширение" | **Частично реализован** |
| 7 | Правило решений: "закрыть P2 hardening?" | P2 давно закрыт | Нужно обновить на P3/H/N |
| 8 | Таблица прогресса: нет строк для H, N, I | Отсутствуют | **Нужно добавить** |

### 3.3 P3_PROGRESS.md — 10 расхождений

| # | Место | Проблема | Факт |
|---|-------|----------|------|
| 1 | Волна 3: "P3-10 [ ]" | Не отмечен | **✅ Завершён** |
| 2 | Волна 3: "P3-11 [ ]" | Не отмечен | **✅ Завершён** |
| 3 | Волна 3: "P3-9 [ ]" | Не отмечен | **✅ Завершён** |
| 4 | Волна 4: "P3-3 [ ]" | Не отмечен | **✅ Завершён** (mkdocs) |
| 5 | Волна 4: "P3-12 [ ]" | Не отмечен | **✅ Завершён** (SQLCipher) |
| 6 | Волна 4: "P3-13 [ ]" | Не отмечен | **✅ Завершён** (LLM Bridge = Этап N) |
| 7 | Волна 2: "P3-6 [ ]" | Не отмечен | **✅ Завершён** (hypothesis tests) |
| 8 | Волна 2: "P3-8 [ ]" | Не отмечен | **✅ Завершён** (stress tests) |
| 9 | Волна 2: "P3-7 [ ]" | Не отмечен | **[ ] Не завершён** (mutmut) |
| 10 | Нет упоминания Этапов H, N, I | Отсутствуют | **Реализованы** |

### 3.4 docs/index.md — 6 расхождений

| # | Место | Проблема | Факт |
|---|-------|----------|------|
| 1 | Badge: "1346 passed" | Устарело | **1774** |
| 2 | Метрики: "1346 / 1346" | Устарело | **1774** |
| 3 | "12-шаговый CognitivePipeline" | Устарело | **15 шагов** |
| 4 | Таблица слоёв: Layer 06 = "🔵 planned" | Частично реализован | **3 модуля** |
| 5 | Таблица слоёв: Layer 08 = "✅" (только resource_monitor) | Неполно | **+ attention_controller, salience_engine, policy_layer** |
| 6 | Нет упоминания brain/bridges/ (LLM Bridge) | Отсутствует | **Реализован** |

### 3.5 BRAIN.md — 4 расхождения

| # | Место | Проблема | Факт |
|---|-------|----------|------|
| 1 | Disclaimer: "10-step pipeline" | Устарело | **15 шагов** |
| 2 | "SalienceEngine — post-MVP" | Реализован | **brain/cognition/salience_engine.py** |
| 3 | "Learning Loop (Этап I — post-MVP)" | Частично реализован | **3 модуля** |
| 4 | "CuriosityEngine — post-MVP" | Корректно | Не реализован |

### 3.6 CONTRIBUTING.md — 3 расхождения

| # | Место | Проблема | Факт |
|---|-------|----------|------|
| 1 | "brain/learning/ — Слой 6: обучение (stub)" | Не stub | **3 реальных модуля** |
| 2 | "brain/cognition/ — 9 подсистем" | Устарело | **14 файлов, 12+ подсистем** |
| 3 | Нет brain/bridges/ в структуре | Отсутствует | **Существует** |

### 3.7 CHANGELOG.md — 1 расхождение

| # | Место | Проблема | Факт |
|---|-------|----------|------|
| 1 | P3-10: "12-шаговый пайплайн" | Исторически корректно, но может путать | Финально 15 шагов (после H+N) |

**Примечание:** CHANGELOG.md — наиболее актуальный документ. Секция [Unreleased] корректно отражает все изменения H и N.

### 3.8 docs/api/ — 2 расхождения

| # | Место | Проблема | Факт |
|---|-------|----------|------|
| 1 | Нет bridges.md | Отсутствует | **brain/bridges/ существует** |
| 2 | Нет learning.md | Отсутствует | **brain/learning/ имеет 3 модуля** |

---

## 4. Отсутствующие ADR

| Решение | Статус ADR |
|---------|-----------|
| SQLite as default backend | ✅ ADR-001 |
| Threading RLock for memory | ✅ ADR-002 |
| Protocol types for DI | ✅ ADR-003 |
| BM25 hybrid retrieval | ✅ ADR-004 |
| Template responses (no LLM) | ✅ ADR-005 |
| EventBus sync snapshot | ✅ ADR-006 |
| CPU-only platform | ✅ ADR-007 |
| **LLM Bridge architecture** | ❌ **Нет ADR** |
| **SalienceEngine formula** | ❌ **Нет ADR** |
| **SQLCipher encryption** | ❌ **Нет ADR** |
| **15-step pipeline evolution** | ❌ **Нет ADR** |

---

## 5. Сильные стороны проекта

1. **Архитектурная целостность** — 12-слойная биоинспирированная архитектура последовательно реализуется
2. **Тестовое покрытие** — 1774 теста, coverage 84.44%, gate 70%
3. **Качество кода** — ruff 0 errors, mypy 0 errors, bandit 0 issues
4. **Thread safety** — RLock в 6 модулях памяти + EventBus
5. **Graceful degradation** — система работает без опциональных зависимостей (NLP, LLM, SQLCipher)
6. **CHANGELOG.md** — наиболее актуальный документ, корректно отражает все изменения
7. **CI/CD** — полный pipeline (pytest + coverage + ruff + mypy + bandit + Docker build)
8. **ADR** — 7 архитектурных решений задокументированы
9. **Backward compatibility** — LLM Bridge, SQLCipher, SalienceEngine — всё опционально

---

## 6. Риски и технический долг

### 6.1 Документационный долг (критический)

- **README.md** — 14 расхождений, включая числа тестов, структуру проекта, статусы слоёв
- **TODO.md** — не отражает Этапы H, N, I; P3 показан как 0/13
- **P3_PROGRESS.md** — все задачи показаны как незавершённые
- **docs/index.md** — устаревшие метрики и статусы

### 6.2 Архитектурный долг (средний)

- **brain/safety/** — всё ещё stub, нет реализации
- **brain/fusion/** — всё ещё stub
- **brain/motivation/** — не существует (Layer 11)
- **Нет ADR** для 4 ключевых решений (LLM Bridge, SalienceEngine, SQLCipher, pipeline evolution)

### 6.3 Тестовый долг (низкий)

- **P3-7 mutmut** — единственная незавершённая задача P3
- **5 skipped tests** — sqlcipher3 не установлен (ожидаемо)

---

## 7. Рекомендации по приоритету

### Приоритет 1 — Синхронизация документации (критический)

| # | Файл | Действие |
|---|------|----------|
| 1 | **P3_PROGRESS.md** | Отметить все завершённые задачи ✅, добавить Этапы H/N/I |
| 2 | **TODO.md** | Обновить P3 прогресс, добавить строки H/N/I, обновить числа тестов |
| 3 | **README.md** | Обновить: тесты 1774, pipeline 15 шагов, структуру проекта, таблицу тестов, статусы слоёв |
| 4 | **docs/index.md** | Обновить: тесты 1774, pipeline 15 шагов, таблицу слоёв |
| 5 | **BRAIN.md** | Обновить disclaimer: 15-step pipeline, SalienceEngine реализован, Learning частично |
| 6 | **CONTRIBUTING.md** | Обновить структуру проекта: brain/bridges/, brain/learning/ не stub |

### Приоритет 2 — Дополнение документации (средний)

| # | Файл | Действие |
|---|------|----------|
| 7 | **docs/api/bridges.md** | Создать страницу API для brain/bridges/ |
| 8 | **docs/api/learning.md** | Создать страницу API для brain/learning/ |
| 9 | **docs/adr/ADR-008-llm-bridge.md** | Задокументировать решение по LLM Bridge |
| 10 | **docs/adr/ADR-009-salience-engine.md** | Задокументировать формулу SalienceEngine |
| 11 | **docs/adr/ADR-010-sqlcipher-encryption.md** | Задокументировать решение по SQLCipher |
| 12 | **mkdocs.yml** | Добавить bridges и learning в навигацию |

### Приоритет 3 — Завершение P3 (низкий)

| # | Задача | Действие |
|---|--------|----------|
| 13 | **P3-7** | Запустить mutmut, проанализировать результаты |

---

## 8. Итоговая оценка

```
Код:            ██████████ 9/10  — качество высокое, 0 ошибок lint/type/sast
Тесты:          ██████████ 9/10  — 1774 теста, 84%+ coverage, gate 70%
Архитектура:    ████████░░ 8/10  — 9/12 слоёв реализовано, 3 stub/absent
Документация:   ████░░░░░░ 4/10  — КРИТИЧЕСКИ устарела (42+ расхождения)
CI/CD:          █████████░ 9/10  — полный pipeline, Dependabot, Codecov
DX:             ███████░░░ 7/10  — CHANGELOG, CONTRIBUTING, ADR, mkdocs
```

### Главный вывод

**Код значительно опережает документацию.** Реализованы Этапы H (Attention), N (LLM Bridge),
частично I (Learning), завершены ~12/13 задач P3 — но документация (README, TODO, P3_PROGRESS,
BRAIN.md, docs/index.md) отражает состояние на ~2 этапа назад.

**Рекомендация:** перед любой новой разработкой — синхронизировать документацию с фактическим
состоянием кода. Это займёт ~2-3 часа, но устранит 42+ расхождений и приведёт проект
в консистентное состояние.
