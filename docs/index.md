# Cognitive Core

**Биоинспирированная когнитивная система на Python**

[![Tests](https://img.shields.io/badge/tests-1774%20passed-brightgreen)](https://github.com/whatisdantes/cognitive-core)
[![Coverage](https://img.shields.io/badge/coverage-84.44%25-green)](https://codecov.io)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](../LICENSE)

---

## Что это такое

**Cognitive Core** — это когнитивная система с нуля, вдохновлённая архитектурой человеческого мозга.
Не LLM-обёртка, а полноценный когнитивный цикл: восприятие → кодирование → память → рассуждение → действие.

```
Запрос → Perception → Encoding → Memory → Cognition → Output
```

## Быстрый старт

```bash
pip install cognitive-core
cognitive-core run "что такое нейрон?"
```

Интерактивный режим:

```bash
cognitive-core interactive
```

Автономный режим (5 тиков планировщика):

```bash
cognitive-core run --autonomous --ticks 5
```

## Архитектура — 12 слоёв

| Слой | Модуль | Статус |
|------|--------|--------|
| 00 Autonomous Loop | `brain/core/scheduler.py` | ✅ |
| 01 Perception | `brain/perception/` | ✅ |
| 02 Modality Encoders | `brain/encoders/` | ✅ |
| 03 Cross-Modal Fusion | `brain/fusion/` | 🔵 stub |
| 04 Memory System | `brain/memory/` | ✅ |
| 05 Cognitive Core | `brain/cognition/` | ✅ 15-step pipeline |
| 06 Learning Loop | `brain/learning/` | ⚡ partial (3 модуля) |
| 07 Output Layer | `brain/output/` | ✅ |
| 08 Attention/Resource | `brain/core/`, `brain/cognition/` | ✅ Этап H |
| 09 Logging/Observability | `brain/logging/` | ✅ |
| 10 Safety Boundaries | `brain/safety/` | 🔵 stub |
| 11 Midbrain/Reward | — | 🔵 planned |
| — LLM Bridge | `brain/bridges/` | ✅ Этап N |

## Ключевые возможности

- **5 видов памяти**: рабочая, семантическая, эпизодическая, процедурная, источников
- **Гибридный retrieval**: BM25 + векторный поиск (cosine similarity)
- **15-шаговый CognitivePipeline**: каждый шаг тестируется изолированно (включая salience, budget, LLM enhance)
- **Thread-safe**: `threading.RLock` во всех модулях памяти
- **SQLite WAL**: персистентность с WAL mode, опциональное шифрование (SQLCipher)
- **EventBus**: синхронный + ThreadPool dispatch
- **Планировщик**: автономный цикл с приоритетами задач
- **CLI**: `cognitive-core run / interactive / --autonomous`

## Документация

- [Архитектура (BRAIN.md)](BRAIN.md) — полная спецификация 12 слоёв
- [Action Plan](ACTION_PLAN.md) — детальный план с effort-оценками
- [ADR](adr/README.md) — Architecture Decision Records (7 решений)
- [API Reference](api/index.md) — автогенерированная документация модулей
- [CHANGELOG](../CHANGELOG.md) — история изменений
- [CONTRIBUTING](../CONTRIBUTING.md) — руководство для контрибьюторов

## Метрики

| Параметр | Значение |
|----------|----------|
| Тесты | **1774 / 1774 ✅** (5 skipped) |
| Coverage | **84%+** (gate 70%) |
| Ruff | **0 errors** |
| Mypy | **0 errors** |
| Python | **3.11 / 3.12 / 3.13** |
| Платформа | **CPU-only** |
