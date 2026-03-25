# P0 — Критические исправления

## Статус: ✅ ВСЕ P0 ВЫПОЛНЕНЫ — 660/660 тестов

## Чеклист

- [x] **P0.1** Синхронизировать версии → `0.6.1`
  - [x] `brain/__init__.py`: `"0.3.0"` → `"0.6.1"`
  - [x] `pyproject.toml`: `"0.6.0"` → `"0.6.1"`
  - [x] `README.md`: тесты `611` → `660`, версия `0.4.0` → `0.6.1`
- [x] **P0.2** Очистить NaN-артефакты в `README.md`
  - [x] Убраны `NaN retry-only MVP)` и починены обрезанные блоки кода
  - [x] Добавлена строка `test_vector_retrieval.py` в таблицу тестов
- [x] **P0.3** NaN в `events.py` — уже чисто ✅
- [x] **P0.4** API-контракты (протоколы)
  - [x] Добавлены `MemoryManagerProtocol`, `EventBusProtocol`, `ResourceMonitorProtocol` в `brain/core/contracts.py`
  - [x] Экспортированы из `brain/core/__init__.py`
  - [x] Типизирован `brain/cognition/cognitive_core.py` (конструктор с Protocol-типами)
- [x] **P0.5** Убрать мутацию EvidencePack в RRF merge
  - [x] `retrieval_adapter.py`: `dataclasses.replace()` в `_ensure_canonical()`, `_enrich()`, `_rrf_merge()`
  - [x] `retrieve()` loop captures return values
- [x] **P0.6** E2E тест + lint blocking
  - [x] `.github/workflows/ci.yml`: убран `continue-on-error: true` → ruff теперь блокирующий ✅
  - [x] `tests/test_e2e_pipeline.py`: 10 E2E тестов (Protocol conformance + full pipeline)
- [x] **P1.0** Ruff cleanup: 131 → 0 errors
  - [x] `ruff --fix` auto-fixed 103 violations (F401, F541)
  - [x] Manual fixes: E741 (`l` → `line`), E702 (semicolons split), E402 (`# noqa`)
  - [x] `# noqa` annotations for intentional late imports (memory_manager, consolidation_engine, conftest)
- [x] **Финал** ruff check → 0 errors ✅ · pytest 660/660 ✅ · CI lint blocking ✅

## Изменённые файлы

| Файл | Изменение |
|------|-----------|
| `brain/__init__.py` | `__version__` → `"0.6.1"` |
| `pyproject.toml` | `version` → `"0.6.1"` |
| `README.md` | 8 правок: счётчики 611→660, NaN cleanup, v0.6.1, +vector_retrieval row |
| `brain/core/contracts.py` | +3 Protocol (MemoryManager, EventBus, ResourceMonitor) |
| `brain/core/__init__.py` | +3 Protocol exports в `__all__` |
| `brain/cognition/cognitive_core.py` | Constructor typed с Protocol'ами |
| `brain/cognition/retrieval_adapter.py` | Immutable EvidencePack via `dataclasses.replace()` |
| `.github/workflows/ci.yml` | Removed `continue-on-error: true` from ruff step |
| `tests/test_e2e_pipeline.py` | **NEW** — 10 E2E тестов |

## Ruff cleanup (P1.0) — DONE ✅

131 pre-existing warnings → **0 errors** after cleanup:
- 103 auto-fixed by `ruff --fix` (F401 unused imports, F541 f-strings)
- 9× E702 semicolons split manually (`test_memory.py`)
- 4× E741 ambiguous variable `l` → `line` (`test_scheduler.py`, `test_resource_monitor.py`)
- 14× `# noqa: E402` for intentional late imports after try/except blocks
- 2× `# noqa: F401` for side-effect imports (`numpy`, `psutil` in `semantic_memory.py`)

CI ruff lint step is now **blocking** (no `continue-on-error`).
