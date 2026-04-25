# Разработка

Эта страница фиксирует актуальный workflow разработки для репозитория и заменяет удалённые внутренние страницы, на которые раньше ссылался `mkdocs.yml`.

## Установка окружения

```bash
git clone https://github.com/whatisdantes/cognitive-core.git
cd cognitive-core

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# Базовый набор для разработки и тестов
pip install -e ".[dev]"

# Полный набор опциональных зависимостей
pip install -e ".[all]"

# Только шифрование памяти (SQLCipher)
pip install -e ".[encrypted]"
```

## Extras

| Extra | Назначение |
|------|------------|
| `dev` | pytest, pytest-cov, ruff, mypy, bandit, hypothesis |
| `nlp` | NLP-зависимости (`pymorphy3`, `razdel`, `nltk`, `navec`, `sentence-transformers`) |
| `vision` | Vision-стек (`open-clip-torch`, `pillow`) |
| `audio` | Аудио-стек (`openai-whisper`) |
| `docs` | Парсинг документов (`pymupdf`, `python-docx`) |
| `apidocs` | Сборка MkDocs-сайта |
| `encrypted` | SQLCipher (`sqlcipher3`) |
| `openai` | OpenAI bridge |
| `anthropic` | Anthropic bridge |
| `all` | Все перечисленные extras, включая `encrypted` |

## Проверки

```bash
python -m pytest tests/ -v
python -m ruff check brain/ tests/
python -m mypy brain/ --ignore-missing-imports
python -m bandit -r brain/ -c pyproject.toml -q
```

## GitHub Actions

- `CI` запускает обычные quality checks и отдельную сборку `mkdocs build --strict`, чтобы проблемы документации были видны как стандартный check на PR.
- `Docs / Pages` собирает MkDocs-сайт, прикладывает preview-артефакт `mkdocs-site` к workflow и публикует GitHub Pages при push в `main`.
- Для локальной проверки docs нужен extra `apidocs`: `pip install -e ".[apidocs]"`.

## Навигация по документации

- Архитектурный обзор: [BRAIN.md](BRAIN.md)
- Детализация по слоям: [layers/](layers/00_autonomous_loop.md)
- Архитектурные решения: [ADR](adr/README.md)
- API-документация: [API Reference](api/index.md)
- Сводка CLI: [commands.md](commands.md)

## Источники истины

- Roadmap и статусы задач: [`planning/TODO.md`](planning/TODO.md) (post-MVP backlog — [`planning/FUTURE_TODO.md`](planning/FUTURE_TODO.md))
- Update-план автономности: [`planning/UPDATE_TODO.md`](planning/UPDATE_TODO.md)
- Зависимости и tooling: `pyproject.toml`
- Правила участия в разработке: корневой `CONTRIBUTING.md`
