# CLI-команды

Сводка CLI-команд проекта `cognitive-core` v0.7.0.

Команды ниже рассчитаны на запуск из корня репозитория. На Windows можно либо активировать `.venv`, либо вызывать инструменты напрямую через `.\.venv\Scripts\...`.

## 1. Окружение

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Без активации:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests/ -v
.\.venv\Scripts\cognitive-core.exe "Что такое нейрон?"
```

### Linux/macOS

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## 2. Установка extras

Минимальная установка ядра:

```powershell
pip install -e .
```

Стандартная dev-установка:

```powershell
pip install -e ".[dev]"
```

Все optional extras:

```powershell
pip install -e ".[all]"
```

Отдельные extras:

```powershell
pip install -e ".[nlp]"
pip install -e ".[vision]"
pip install -e ".[audio]"
pip install -e ".[docs]"
pip install -e ".[apidocs]"
pip install -e ".[encrypted]"
pip install -e ".[openai]"
pip install -e ".[anthropic]"
```

Комбинации extras:

```powershell
pip install -e ".[dev,apidocs]"
pip install -e ".[dev,encrypted]"
pip install -e ".[dev,openai,anthropic]"
```

## 3. Основной CLI: `cognitive-core`

Полный синтаксис:

```text
cognitive-core [-h] [--version] [--verbose] [--data-dir DATA_DIR]
               [--autonomous] [--daemon] [--materials DIR] [--watch]
               [--no-watch] [--stdin] [--ticks N]
               [--llm-provider PROVIDER] [--llm-api-key KEY]
               [--llm-model MODEL] [--log-dir DIR] [--log-level LEVEL]
               [query]
```

### Справка и версия

```powershell
cognitive-core --help
cognitive-core --version
python -m brain.cli --help
python -m brain.cli --version
```

### Одноразовый запрос

```powershell
cognitive-core "Что такое нейрон?"
cognitive-core "Запомни: нейрон — клетка"
cognitive-core --verbose "Что такое синапс?"
cognitive-core --data-dir brain/data/memory "Что известно о рабочей памяти?"
```

### JSONL-логирование

```powershell
cognitive-core --log-dir brain/data/logs "Что такое нейрон?"
cognitive-core --log-dir brain/data/logs --log-level DEBUG "вопрос"
cognitive-core --log-dir brain/data/logs --log-level INFO "Что известно из памяти?"
```

Допустимые уровни:

```text
DEBUG, INFO, WARN, ERROR, CRITICAL
```

### LLM bridge

Допустимые провайдеры:

```text
openai, anthropic, blackbox, mock
```

С ключом через аргумент:

```powershell
cognitive-core --llm-provider openai --llm-api-key KEY "Что такое синапс?"
cognitive-core --llm-provider anthropic --llm-api-key KEY "Суммируй память"
cognitive-core --llm-provider blackbox --llm-api-key KEY "Что такое нейрон?"
cognitive-core --llm-provider mock "Тестовый запрос"
```

С явной моделью:

```powershell
cognitive-core --llm-provider openai --llm-api-key KEY --llm-model gpt-4o-mini "вопрос"
cognitive-core --llm-provider anthropic --llm-api-key KEY --llm-model claude-3-haiku-20240307 "вопрос"
cognitive-core --llm-provider blackbox --llm-api-key KEY --llm-model blackboxai/openai/gpt-5.3-codex "вопрос"
```

Через переменные окружения:

```powershell
$env:OPENAI_API_KEY = "..."
$env:ANTHROPIC_API_KEY = "..."
$env:BLACKBOX_API_KEY = "..."
cognitive-core --llm-provider blackbox "вопрос"
```

CLI также подгружает `.env` из текущей директории. Поддерживаемые имена:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
BLACKBOX_API_KEY
```

### Автономный режим

`--ticks` применяется к `--autonomous`. `--ticks 0` означает бесконечный цикл до остановки процесса.

```powershell
cognitive-core --autonomous
cognitive-core --autonomous --ticks 5
cognitive-core --autonomous --ticks 10 --log-dir brain/data/logs --log-level INFO
cognitive-core --autonomous --ticks 0
cognitive-core --autonomous --data-dir brain/data/memory --ticks 20
cognitive-core --autonomous --llm-provider mock --ticks 10
```

### Daemon mode

Daemon работает до `Ctrl+C` / SIGTERM. Публичный CLI не использует `--ticks` для `--daemon`.

Без материалов и LLM:

```powershell
cognitive-core --daemon
cognitive-core --daemon --data-dir brain/data/memory
cognitive-core --daemon --log-dir brain/data/logs --log-level INFO
```

Startup scan материалов:

```powershell
cognitive-core --daemon --materials materials
cognitive-core --daemon --materials materials --no-watch
```

Watcher материалов:

```powershell
cognitive-core --daemon --materials materials --watch
cognitive-core --daemon --data-dir brain/data/memory --materials materials --watch
```

Stdin reader:

```powershell
cognitive-core --daemon --stdin
cognitive-core --daemon --materials materials --watch --stdin
```

Daemon с логами и LLM:

```powershell
cognitive-core --daemon `
  --data-dir brain/data/memory `
  --materials materials `
  --watch `
  --stdin `
  --llm-provider blackbox `
  --llm-api-key KEY `
  --llm-model "blackboxai/openai/gpt-5.3-codex" `
  --log-dir brain/data/logs `
  --log-level INFO
```

## 4. Импорт материалов

Скрипт:

```powershell
python examples/ingest_material.py --help
```

Полный синтаксис:

```text
python examples/ingest_material.py [options] paths [paths ...]
```

Основные команды:

```powershell
python examples/ingest_material.py materials/example.md
python examples/ingest_material.py materials/
python examples/ingest_material.py materials/ --recursive
python examples/ingest_material.py materials/ --recursive --data-dir brain/data/memory
python examples/ingest_material.py materials/ --recursive --log-dir brain/data/logs --log-level INFO
```

Управление chunk ingestion:

```powershell
python examples/ingest_material.py materials/ --recursive --force
python examples/ingest_material.py materials/ --recursive --importance 0.8
python examples/ingest_material.py materials/ --recursive --max-chunks 100
python examples/ingest_material.py materials/ --recursive --skip-chunks 50 --max-chunks 50
python examples/ingest_material.py materials/ --recursive --no-auto-extract
```

Извлечение facts через LLM:

```powershell
python examples/ingest_material.py materials/ --recursive --extract-facts-with-llm --llm-provider mock
python examples/ingest_material.py materials/ --recursive --extract-facts-with-llm --llm-provider openai --llm-api-key KEY
python examples/ingest_material.py materials/ --recursive --extract-facts-with-llm --llm-provider anthropic --llm-api-key KEY
python examples/ingest_material.py materials/ --recursive --extract-facts-with-llm --llm-provider blackbox --llm-api-key KEY
python examples/ingest_material.py materials/ --recursive --extract-facts-with-llm --llm-provider blackbox --llm-model "blackboxai/openai/gpt-5.3-codex"
python examples/ingest_material.py materials/ --recursive --extract-facts-with-llm --facts-per-chunk 10
```

## 5. Demo

```powershell
python examples/demo.py
```

## 6. Тесты

Все тесты:

```powershell
python -m pytest tests/ -v
```

Тихий режим:

```powershell
python -m pytest tests/ -q
```

Один файл:

```powershell
python -m pytest tests/test_memory.py -v
python -m pytest tests/test_daemon_integration.py -q
```

Один тест:

```powershell
python -m pytest tests/test_memory.py::TestSemanticMemory::test_learn_fact -v
```

Сбор тестов без запуска:

```powershell
python -m pytest --collect-only -q
```

Coverage:

```powershell
python -m pytest tests/ --cov=brain --cov-report=term-missing
python -m pytest tests/ --cov=brain --cov-report=term-missing --cov-fail-under=70
```

Наборы из [`planning/UPDATE_TODO.md`](planning/UPDATE_TODO.md):

```powershell
python -m pytest tests/test_claim_store.py -q
python -m pytest tests/test_storage_migration_v2.py -q
python -m pytest tests/test_conflict_guard_fast.py tests/test_conflict_guard_slow.py -q
python -m pytest tests/test_material_registry.py tests/test_material_ingestor.py -q
python -m pytest tests/test_idle_dispatcher.py tests/test_scheduler_recurring.py -q
python -m pytest tests/test_output_hedged_dispute.py tests/test_daemon_integration.py -q
python -m pytest tests/ --cov=brain --cov-fail-under=70
```

## 7. Lint, types, SAST

Ruff:

```powershell
python -m ruff check brain/ tests/
python -m ruff check brain/ tests/ --fix
```

Mypy:

```powershell
python -m mypy brain/ --ignore-missing-imports
```

Bandit:

```powershell
python -m bandit -r brain/ -c pyproject.toml -q
```

Полный локальный quality gate:

```powershell
python -m ruff check brain/ tests/
python -m mypy brain/ --ignore-missing-imports
python -m bandit -r brain/ -c pyproject.toml -q
python -m pytest tests/ --cov=brain --cov-report=term-missing --cov-fail-under=70
```

## 8. Mutation testing

`mutmut` входит в extra `dev`.

```powershell
python -m mutmut run
python -m mutmut results
python -m mutmut show
```

## 9. Документация

Установка API-docs extras:

```powershell
pip install -e ".[apidocs]"
```

MkDocs:

```powershell
python -m mkdocs serve
python -m mkdocs build
python -m mkdocs build --strict
```

## 10. Docker

Build:

```powershell
docker build -t cognitive-core .
docker build -t cognitive-core:local .
```

Run:

```powershell
docker run cognitive-core "Что такое нейрон?"
docker run cognitive-core:local "Что такое нейрон?"
```

CI-style build:

```powershell
docker build -t cognitive-core:ci .
```

## 11. Полезные Windows aliases

Если окружение не активировано:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
.\.venv\Scripts\python.exe -m ruff check brain/ tests/
.\.venv\Scripts\python.exe -m mypy brain/ --ignore-missing-imports
.\.venv\Scripts\python.exe -m bandit -r brain/ -c pyproject.toml -q
.\.venv\Scripts\cognitive-core.exe "Что такое нейрон?"
```

Если окружение активировано:

```powershell
python -m pytest tests/ -q
python -m ruff check brain/ tests/
python -m mypy brain/ --ignore-missing-imports
python -m bandit -r brain/ -c pyproject.toml -q
cognitive-core "Что такое нейрон?"
```
