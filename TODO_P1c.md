# P1c-a: SQLite Persistence (persistence parity)

> Заменить JSON на SQLite как backend хранения. Без изменения search semantics.
> FTS5 и indexed search → отдельный этап P1c-b.

## Принципы

- SQLite = persistence layer only, hot path остаётся in-memory
- Единый `memory.db` внутри `data_dir`
- `storage_backend="auto"|"sqlite"|"json"` — явный переключатель
- JSON fallback сохраняется
- Автомиграция JSON→SQLite с backup и логированием
- Одна connection + RLock + `check_same_thread=False`
- WAL mode
- Транзакционная граница в `MemoryManager.save_all()`

## Задачи

- [x] **P1c.1** — `brain/memory/storage.py` — MemoryDatabase ✅
  - sqlite3, WAL, RLock, check_same_thread=False
  - Таблицы: semantic_nodes, relations, episodes, modal_evidence, sources, procedures, procedure_steps, _meta
  - UNIQUE constraints, FOREIGN KEY, индексы (concept, episode_id, source_id, name, ts, updated_ts)
  - begin/commit/rollback API
  - Schema versioning в _meta

- [x] **P1c.2** — `brain/memory/migrate.py` — JSON→SQLite миграция ✅
  - Backup JSON перед миграцией
  - Идемпотентная (повторный запуск безопасен)
  - Marker в _meta после успешной миграции
  - При ошибке — не удалять JSON, логировать
  - Ручная утилита + auto-path

- [x] **P1c.3** — Модификация `SemanticMemory` ✅
  - `save()` → INSERT/UPDATE в SQLite
  - `_load()` → SELECT из SQLite в _nodes cache
  - `search()` — БЕЗ ИЗМЕНЕНИЙ (по кэшу в Python)
  - Параметр `storage_backend="auto"` 

- [x] **P1c.4** — Модификация `EpisodicMemory` ✅
  - Аналогично SemanticMemory
  - search(), retrieve_by_concept(), retrieve_by_time() — по кэшу

- [x] **P1c.5** — Модификация `SourceMemory` ✅

- [x] **P1c.6** — Модификация `ProceduralMemory` ✅

- [x] **P1c.7** — Обновление `MemoryManager` ✅
  - `storage_backend` параметр
  - Создание MemoryDatabase, передача db в sub-modules
  - Транзакционный `save_all()` с begin/commit/rollback
  - `db.close()` в `stop()`
  - `effective_backend` / `db` properties

- [x] **P1c.8** — Обновление `brain/memory/__init__.py` ✅
  - Экспорт MemoryDatabase, migrate_json_to_sqlite, auto_migrate_if_needed

- [x] **P1c.9** — `tests/test_storage.py` — 58 тестов ✅
  - CRUD для каждой таблицы (semantic, relations, episodes, sources, procedures)
  - Bulk operations
  - Транзакции (commit, rollback)
  - Meta API
  - Thread safety (concurrent writes)
  - Интеграция с memory модулями (sqlite backend roundtrip)
  - Миграция JSON→SQLite (13 тестов)

- [x] **P1c.10** — Регрессия: 773 тестов ✅ (ожидание подтверждения)

- [x] **P1c.11** — Документация: `docs/TODO.md` ✅
  - P1.3 отмечен как выполненный
  - Таблица тестов обновлена: 773 тестов, добавлен test_storage.py (58)

- [x] **Финал** — Прогон всех тестов + ruff lint ✅
  - Ruff: 0 errors ✅
  - Тесты: 773/773 passed (115s + 119s, два прогона) ✅
  - Версия: 0.6.1 → 0.7.0 (brain/__init__.py, pyproject.toml, README.md)

## НЕ входит в P1c-a (→ P1c-b)

- FTS5 полнотекстовый поиск
- search() через SQL
- Indexed retrieval
- Сокращение RAM residency
- Partial offloading в БД
