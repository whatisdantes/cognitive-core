# Architecture Decision Records (ADR)

> ADR — это короткие документы, фиксирующие архитектурные решения, принятые в ходе разработки проекта.  
> Формат: [MADR (Markdown Architectural Decision Records)](https://adr.github.io/madr/)

---

## Индекс решений

| # | Название | Статус | Дата |
|---|----------|--------|------|
| [ADR-001](ADR-001-sqlite-as-default-backend.md) | SQLite как основной backend персистенции | ✅ Принято | 2025-04 |
| [ADR-002](ADR-002-threading-rlock-for-memory.md) | `threading.RLock` для thread safety памяти | ✅ Принято | 2025-05 |
| [ADR-003](ADR-003-protocol-types-for-di.md) | `typing.Protocol` для dependency injection | ✅ Принято | 2025-05 |
| [ADR-004](ADR-004-bm25-hybrid-retrieval.md) | BM25 + Vector Hybrid Retrieval с RRF | ✅ Принято | 2025-06 |
| [ADR-005](ADR-005-template-responses-no-llm.md) | Шаблонные ответы без LLM на MVP-этапе | ✅ Принято | 2025-06 |
| [ADR-006](ADR-006-event-bus-sync-snapshot.md) | Синхронный EventBus со snapshot pattern | ✅ Принято | 2025-06 |
| [ADR-007](ADR-007-cpu-only-platform.md) | CPU-only платформа (без GPU) | ✅ Принято | 2025-03 |

---

## Статусы

| Статус | Описание |
|--------|----------|
| 🔵 Предложено | Решение предложено, обсуждается |
| ✅ Принято | Решение принято и реализовано |
| ⚠️ Устарело | Решение заменено другим ADR |
| ❌ Отклонено | Решение отклонено с обоснованием |

---

## Как добавить новый ADR

1. Скопировать шаблон `ADR-000-template.md`
2. Присвоить следующий номер
3. Заполнить все секции
4. Добавить в индекс выше
5. Обновить статус при изменении решения
