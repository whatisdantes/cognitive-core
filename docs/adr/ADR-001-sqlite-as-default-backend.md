# ADR-001: SQLite как основной backend персистенции

**Статус:** ✅ Принято  
**Дата:** 2025-04  
**Авторы:** cognitive-core contributors

---

## Контекст

Системе памяти требуется персистентное хранилище для 5 видов памяти:
- `SemanticMemory` — граф понятий (узлы + связи)
- `EpisodicMemory` — эпизоды с мультимодальными доказательствами
- `SourceMemory` — источники и их trust score
- `ProceduralMemory` — процедуры и шаги
- `WorkingMemory` — рабочая память (in-memory, не персистируется)

Требования:
- CPU-only платформа (AMD Ryzen 7 5700X, 32 GB DDR4)
- Нет внешних сервисов (self-contained)
- Concurrent read (ConsolidationEngine daemon thread)
- Транзакционность (атомарные операции)
- Простота развёртывания (один файл)

## Рассмотренные варианты

### Вариант 1: JSON-файлы (один файл на тип памяти)
**Плюсы:** Простота, читаемость, нет зависимостей  
**Минусы:** Нет транзакций, нет concurrent read, полная перезапись при каждом save, O(n) поиск

### Вариант 2: SQLite (один .db файл)
**Плюсы:** ACID транзакции, WAL mode для concurrent read, индексы для быстрого поиска, один файл, stdlib  
**Минусы:** Нет нативного vector search, требует schema versioning

### Вариант 3: PostgreSQL / Redis
**Плюсы:** Масштабируемость, богатый функционал  
**Минусы:** Внешний сервис, сложность развёртывания, избыточность для CPU-only MVP

### Вариант 4: DuckDB
**Плюсы:** Аналитические запросы, columnar storage  
**Минусы:** Избыточность для OLTP-паттерна памяти, дополнительная зависимость

## Решение

Выбран **SQLite** с WAL mode.

Реализация: `brain/memory/storage.py` — `MemoryDatabase`

```python
# WAL mode для лучшего concurrent read
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA foreign_keys=ON")
```

Схема: 7 таблиц (`semantic_nodes`, `relations`, `episodes`, `modal_evidence`, `sources`, `procedures`, `procedure_steps`) + `_meta` для schema versioning.

## Последствия

**Положительные:**
- Единый `.db` файл — простое резервное копирование
- WAL mode — ConsolidationEngine читает без блокировки записи
- Индексы по `confidence`, `importance`, `updated_ts` — быстрый retrieval
- Schema versioning через `_meta` — безопасные миграции

**Отрицательные:**
- Vector search реализован в Python (numpy cosine similarity) — не нативный
- При масштабировании (>10M записей) потребуется миграция на PostgreSQL + pgvector

**Нейтральные:**
- `threading.RLock` для thread safety (SQLite не thread-safe по умолчанию в WAL mode)
- `SCHEMA_VERSION = 1` — задел для будущих миграций

## Связанные решения

- ADR-002: Thread safety через `RLock`
- ADR-004: BM25 + Vector Hybrid Retrieval
