# 🤝 Руководство по участию в разработке

> **Проект:** cognitive-core v0.7.0  
> **Язык кода:** Python 3.11+  
> **Язык документации:** Русский (комментарии, docstrings, commit messages)

---

## 📋 Содержание

1. [Быстрый старт](#-быстрый-старт)
2. [Структура проекта](#-структура-проекта)
3. [Стиль кода](#-стиль-кода)
4. [Тестирование](#-тестирование)
5. [Процесс разработки](#-процесс-разработки)
6. [Правила commit messages](#-правила-commit-messages)
7. [Pull Request](#-pull-request)
8. [Правило принятия решений](#-правило-принятия-решений)

---

## ⚡ Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone https://github.com/whatisdantes/cognitive-core.git
cd cognitive-core

# 2. Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows

# 3. Установить зависимости для разработки
pip install -e ".[dev]"

# 4. Опциональные зависимости
pip install -e ".[nlp]"          # pymorphy3, razdel, sentence-transformers
pip install -e ".[encrypted]"    # SQLCipher / шифрование памяти
pip install -e ".[all]"          # все optional extras

# 5. Проверить установку
cognitive-core --version
```

---

## 🗂️ Структура проекта

```
cognitive-core/
├── brain/                      # Основной пакет
│   ├── core/                   # Слой 0–1: контракты, EventBus, Scheduler, ResourceMonitor
│   ├── perception/             # Слой 1: восприятие (TextIngestor, InputRouter)
│   ├── encoders/               # Слой 2: модальные энкодеры (TextEncoder)
│   ├── memory/                 # Слой 4: система памяти (5 видов + SQLite)
│   ├── cognition/              # Слой 5: когнитивное ядро (CognitiveCore + 15 подсистем)
│   ├── output/                 # Слой 7: вывод (OutputPipeline, DialogueResponder)
│   ├── logging/                # Слой 9: логирование (BrainLogger, DigestGenerator)
│   ├── bridges/                # LLM Bridge (OpenAI/Anthropic providers, safety wrapper)
│   ├── fusion/                 # Слой 3: кросс-модальное слияние (stub)
│   ├── learning/               # Слой 6: обучение (OnlineLearner, KnowledgeGapDetector, ReplayEngine)
│   ├── safety/                 # Слой 10: безопасность (stub)
│   └── cli.py                  # CLI entrypoint
├── tests/                      # Тесты (pytest)
├── docs/                       # Документация
│   ├── layers/                 # Спецификации слоёв (00–11)
│   ├── adr/                    # Architecture Decision Records
│   ├── BRAIN.md                # Архитектурная спецификация
│   ├── index.md                # Главная страница документации
│   └── development.md          # Актуальная dev-навигация и extras
├── examples/                   # Примеры использования
├── pyproject.toml              # Конфигурация проекта (setuptools, ruff, mypy, pytest, bandit)
├── TODO.md                     # Мастер-роадмап
└── README.md                   # Обзор проекта и quick start
```

---

## 🎨 Стиль кода

### Язык

- **Комментарии и docstrings** — на **русском языке**
- **Имена переменных, функций, классов** — на **английском языке** (snake_case / PascalCase)
- **Commit messages** — на **русском языке**

### Инструменты

| Инструмент | Команда | Назначение |
|------------|---------|------------|
| **ruff** | `python -m ruff check brain/ tests/` | Lint (E, F, W, I, B, SIM, C4, RET, PIE) |
| **mypy** | `python -m mypy brain/ --ignore-missing-imports` | Type checking |
| **bandit** | `python -m bandit -r brain/ -c pyproject.toml -q` | SAST |

### Правила ruff

Активные правила: `E, F, W, I, B, SIM, C4, RET, PIE`

Обоснованные исключения (см. `pyproject.toml`):
- `RET504` — unnecessary-assign (стилистическое предпочтение)
- `SIM102` — collapsible-if (ухудшает читаемость)
- `SIM108` — if-else-block-instead-of-if-exp (ухудшает читаемость)
- `B905` — zip-without-explicit-strict (Python 3.10+ kwarg)

### Type hints

```python
# ✅ Правильно — явные типы
def store(self, content: str, importance: float = 0.5) -> None:
    ...

# ✅ Правильно — Protocol для DI
def __init__(self, memory_manager: MemoryManagerProtocol) -> None:
    ...

# ❌ Неправильно — Any без обоснования
def process(self, data: Any) -> Any:
    ...
```

### Docstrings

```python
class SemanticMemory:
    """
    Семантическая память — граф понятий и их связей.

    Аналог: декларативная долгосрочная память (кора головного мозга).
    Хранит факты, концепции и отношения между ними.

    Использование:
        sm = SemanticMemory()
        sm.learn_fact("нейрон", "клетка нервной системы")
        nodes = sm.search("нейрон")
    """
```

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты
python -m pytest tests/ -v

# С coverage
python -m pytest tests/ --cov=brain --cov-report=term-missing

# Конкретный файл
python -m pytest tests/test_memory.py -v

# Конкретный тест
python -m pytest tests/test_memory.py::TestSemanticMemory::test_learn_fact -v
```

### Coverage gate

Минимальный coverage: **70%** (ориентируйтесь на актуальный отчёт CI/codecov, а не на зафиксированное число в документации)

```bash
# Проверка coverage gate
python -m pytest tests/ --cov=brain --cov-fail-under=70
```

### Структура тестов

```python
# tests/test_example.py

import pytest
from brain.memory.semantic_memory import SemanticMemory


class TestSemanticMemory:
    """Тесты семантической памяти."""

    def test_learn_fact_basic(self):
        """Базовое сохранение факта."""
        sm = SemanticMemory()
        sm.learn_fact("нейрон", "клетка нервной системы")
        node = sm.get_node("нейрон")
        assert node is not None
        assert "клетка" in node.description

    def test_learn_fact_updates_confidence(self):
        """Повторное обучение повышает confidence."""
        sm = SemanticMemory()
        sm.learn_fact("нейрон", "клетка нервной системы")
        sm.learn_fact("нейрон", "клетка нервной системы")
        node = sm.get_node("нейрон")
        assert node.confirm_count >= 2
```

### Правила написания тестов

- Один тест — одна проверка (принцип единственной ответственности)
- Имена тестов описывают поведение: `test_<что>_<при каком условии>`
- Фикстуры в `tests/conftest.py`
- Нет зависимостей между тестами (каждый тест изолирован)
- Нет обращений к внешним сервисам (mock при необходимости)

---

## 🔄 Процесс разработки

### Принцип приоритизации

```
сначала hardening → затем retrieval → затем расширение
```

### Перед началом работы

1. Свериться с [`TODO.md`](TODO.md) — текущий прогресс и приоритеты
2. Прочитать [`docs/development.md`](docs/development.md) — установка и dev-навигация
3. Убедиться, что задача соответствует текущему этапу

### Правило принятия решений

При возникновении новой идеи — три вопроса:

1. Помогает ли это закрыть текущий этап?
2. Улучшает ли наблюдаемость, стабильность или retrieval?
3. Не уводит ли в research раньше времени?

**да / да / нет** → брать · **нет / нет / да** → откладывать в P3/Research

### Ветки

```
main        — стабильная версия (только через PR)
develop     — текущая разработка
feature/*   — новые функции
fix/*       — исправления
docs/*      — документация
```

---

## 📝 Правила commit messages

Формат: `<тип>(<область>): <описание>`

### Типы

| Тип | Когда использовать |
|-----|-------------------|
| `feat` | Новая функциональность |
| `fix` | Исправление ошибки |
| `refactor` | Рефакторинг без изменения поведения |
| `test` | Добавление/изменение тестов |
| `docs` | Изменения в документации |
| `chore` | Обслуживание (зависимости, CI, конфиги) |
| `perf` | Оптимизация производительности |

### Примеры

```
feat(memory): добавить batch_remove() в WorkingMemory
fix(event_bus): исправить AttributeError для lambda handlers
refactor(cognition): вынести pipeline шаги в отдельные методы
test(storage): добавить тесты для WAL mode
docs(readme): обновить capability matrix
chore(ci): добавить Docker build job
perf(semantic): заменить sorted() на min() в _evict_least_important()
```

---

## 🔀 Pull Request

### Чеклист перед созданием PR

- [ ] Код соответствует стилю проекта (ruff 0 errors)
- [ ] Типы проверены (mypy 0 errors)
- [ ] Тесты написаны для новой функциональности
- [ ] Все тесты проходят (`pytest tests/`)
- [ ] Coverage не упал ниже 70%
- [ ] TODO.md обновлён (задача отмечена как выполненная)
- [ ] Docstrings на русском языке

### Шаблон описания PR

```markdown
## Что изменено

Краткое описание изменений.

## Задача

Ссылка на задачу из TODO.md (например, P3-10).

## Тип изменений

- [ ] Новая функциональность
- [ ] Исправление ошибки
- [ ] Рефакторинг
- [ ] Документация

## Тесты

Описание добавленных/изменённых тестов.

## Чеклист

- [ ] ruff 0 errors
- [ ] mypy 0 errors
- [ ] pytest все проходят
- [ ] coverage >= 70%
```

---

## 🏗️ Архитектурные принципы

1. **Слоистость** — каждый слой имеет чёткую ответственность и биологический аналог
2. **Dependency Injection** — зависимости передаются через конструктор, не создаются внутри
3. **Protocol-типы** — интерфейсы через `typing.Protocol` (structural subtyping)
4. **Thread safety** — `threading.RLock()` для всех разделяемых состояний
5. **Graceful degradation** — система работает без опциональных зависимостей
6. **Immutability** — `dataclasses.replace()` вместо мутации объектов
7. **DRY** — общие утилиты в `brain/core/text_utils.py` и `brain/core/hash_utils.py`

---

## 📚 Полезные ссылки

- [`TODO.md`](TODO.md) — мастер-роадмап
- [`docs/BRAIN.md`](docs/BRAIN.md) — архитектурная спецификация
- [`docs/development.md`](docs/development.md) — установка, extras и dev-поток
- [`docs/layers/`](docs/layers/) — спецификации каждого из 12 слоёв
- [`README.md`](README.md) — обзор проекта и quick start

---

*Спасибо за участие в разработке cognitive-core!*
