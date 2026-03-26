# 🎯 Phase A — Foundation

> **Статус:** 🚧 В работе  
> **Цель:** `pip install -e . && cognitive-core "вопрос"` → осмысленный ответ

---

## Задачи

### A.2 — Починить контракт ResourceMonitor ↔ CognitiveCore (~15 мин)
- [ ] `brain/core/resource_monitor.py`: добавить `snapshot()` как алиас `check()`
- [ ] `brain/cognition/cognitive_core.py`: `_get_resources()` — fallback на `check()` если нет `snapshot()`
- [ ] `tests/test_resource_monitor.py`: тест `test_snapshot_alias`
- [ ] Проверить protocol conformance

### A.1 — CLI Entrypoint (~3-4 часа)
- [ ] `brain/cli.py`: argparse, pipeline assembly, text/json output
- [ ] `pyproject.toml`: `[project.scripts] cognitive-core = "brain.cli:main"`
- [ ] `examples/demo.py`: программный API demo
- [ ] `tests/test_cli.py`: smoke, empty query, help, session_id, json output
- [ ] Проверить: `pip install -e . && cognitive-core "Что такое нейрон?"`

### A.1b — Dockerfile (~15 мин)
- [ ] `Dockerfile`: multi-stage, pip install -e ., ENTRYPOINT cognitive-core
- [ ] `.dockerignore`: .venv, .git, __pycache__, brain/data/

### A.3 — mypy как настоящий барьер (~2-3 часа)
- [ ] Локальный `mypy brain/core/ brain/cognition/` — собрать список ошибок
- [ ] Исправить critical type errors
- [ ] `.github/workflows/ci.yml`: убрать `|| true`, scope = brain/core/ brain/cognition/
- [ ] Точечные `# type: ignore[...]` с TODO где необходимо

---

## Порядок: A.2 → A.1 → A.1b → A.3

## Definition of Done:
- [ ] `pip install -e . && cognitive-core "Что такое нейрон?"` → ответ
- [ ] `cognitive-core --json "вопрос"` → JSON
- [ ] `docker build -t cognitive-core . && docker run cognitive-core "вопрос"` → ответ
- [ ] CI зелёный с реальным mypy (без `|| true`)
- [ ] 773+ тестов ✅
