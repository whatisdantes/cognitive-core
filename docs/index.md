# Cognitive Core

**Биоинспирированная когнитивная система на Python**

[![Tests](https://img.shields.io/badge/test%20suite-2311%20collected-brightgreen)](https://github.com/whatisdantes/cognitive-core)
[![Coverage](https://img.shields.io/badge/coverage-gate%2070%25-green)](https://codecov.io)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](https://github.com/whatisdantes/cognitive-core/blob/main/LICENSE)

---

## Что это такое

**Cognitive Core** — это когнитивная система с нуля, вдохновлённая архитектурой человеческого мозга.
Не LLM-обёртка, а полноценный когнитивный цикл: восприятие → кодирование → память → рассуждение → действие.

```
Запрос → Perception → Encoding → Memory → Cognition → Output
```

## Быстрый старт

```bash
git clone https://github.com/whatisdantes/cognitive-core.git
cd cognitive-core
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
cognitive-core "что такое нейрон?"
```

Для полного набора опциональных зависимостей:

```bash
pip install -e ".[all]"
```

Для поддержки SQLCipher отдельно:

```bash
pip install -e ".[encrypted]"
```

Автономный режим (5 тиков планировщика):

```bash
cognitive-core --autonomous --ticks 5
```

С JSONL-логированием:

```bash
cognitive-core --log-dir brain/data/logs --log-level DEBUG "что такое нейрон?"
```

## Архитектура — 12 слоёв

| Слой | Модуль | Статус |
|------|--------|--------|
| 00 Autonomous Loop | `brain/core/scheduler.py` | ✅ |
| 01 Perception | `brain/perception/` | ✅ |
| 02 Modality Encoders | `brain/encoders/` | ✅ |
| 03 Cross-Modal Fusion | `brain/fusion/` | ✅ Этап K (61 тест) |
| 04 Memory System | `brain/memory/` | ✅ |
| 05 Cognitive Core | `brain/cognition/` | ✅ 20-step pipeline |
| 06 Learning Loop | `brain/learning/` | ✅ (OnlineLearner + KnowledgeGapDetector + ReplayEngine + интеграция) |
| 07 Output Layer | `brain/output/` | ✅ |
| 08 Attention/Resource | `brain/core/`, `brain/cognition/` | ✅ Этап H |
| 09 Logging/Observability | `brain/logging/` | ✅ |
| 10 Safety Boundaries | `brain/safety/` | ✅ Этап L (107 тестов) |
| 11 Midbrain/Reward | `brain/motivation/` | ✅ Этап M (84 теста) |
| — LLM Bridge | `brain/bridges/` | ✅ Этап N |

## Ключевые возможности

- **5 видов памяти**: рабочая, семантическая, эпизодическая, процедурная, источников
- **Гибридный retrieval**: BM25 + векторный поиск (cosine similarity)
- **20-шаговый CognitivePipeline**: каждый шаг тестируется изолированно (salience, budget, LLM enhance, safety input/policy/audit)
- **Safety & Boundaries**: BoundaryGuard (PII redaction), SafetyPolicyLayer (SF-1/2/3), AuditLogger (JSONL)
- **Reward & Motivation**: RewardEngine (5 типов), MotivationEngine (EMA + decay), CuriosityEngine
- **Cross-Modal Fusion**: SharedSpaceProjector, EntityLinker, ConfidenceCalibrator, CrossModalContradictionDetector
- **Thread-safe**: `threading.RLock` во всех модулях памяти
- **SQLite WAL**: персистентность с WAL mode, опциональное шифрование через extra `encrypted`
- **EventBus**: синхронный + ThreadPool dispatch
- **Планировщик**: автономный цикл с приоритетами задач
- **CLI**: `cognitive-core "запрос"` / `cognitive-core --autonomous --ticks N` / `cognitive-core --log-dir DIR`

## Документация

- [Архитектура (BRAIN.md)](BRAIN.md) — полная спецификация 12 слоёв
- [ADR](adr/README.md) — Architecture Decision Records (7 решений)
- [API Reference](api/index.md) — автогенерированная документация модулей
- [Разработка](development.md) — установка extras, проверка и инструменты разработки
- [CONTRIBUTING](https://github.com/whatisdantes/cognitive-core/blob/main/CONTRIBUTING.md) — руководство для контрибьюторов

## Метрики

| Параметр | Значение |
|----------|----------|
| Тестовый набор | **2311 collected** в текущем дереве |
| Coverage | **gate 70%** в CI |
| Ruff | **0 errors** |
| Mypy | **0 errors** |
| Python | **3.11 / 3.12 / 3.13** |
| Платформа | **CPU-only** |
