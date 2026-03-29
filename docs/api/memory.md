# brain.memory — Система памяти

5 видов памяти + MemoryManager + SQLite backend. Аналог гиппокампа и долговременной памяти.

---

## MemoryManager

Единая точка доступа ко всем видам памяти. Координирует персистентность через `MemoryDatabase`.

::: brain.memory.memory_manager.MemoryManager
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - store
        - retrieve
        - retrieve_by_concept
        - retrieve_recent
        - deny_fact
        - delete_fact
        - status

---

## WorkingMemory

Кратковременная рабочая память с ограниченной ёмкостью и TTL.

::: brain.memory.working_memory.WorkingMemory
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - add
        - get_all
        - get_recent
        - clear
        - status

---

## SemanticMemory

Долговременная семантическая память: граф понятий и связей.

::: brain.memory.semantic_memory.SemanticMemory
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - store
        - retrieve
        - retrieve_by_concept
        - deny_fact
        - delete_fact
        - apply_decay
        - status

---

## EpisodicMemory

Эпизодическая память: события с временными метками и мультимодальными свидетельствами.

::: brain.memory.episodic_memory.EpisodicMemory
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - store
        - retrieve
        - retrieve_recent
        - retrieve_by_concept
        - status

---

## ProceduralMemory

Процедурная память: паттерны действий и их эффективность.

::: brain.memory.procedural_memory.ProceduralMemory
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - store
        - retrieve
        - update_outcome
        - status

---

## SourceMemory

Память об источниках: доверие, подтверждения, противоречия, чёрный список.

::: brain.memory.source_memory.SourceMemory
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - register_source
        - confirm
        - contradict
        - blacklist
        - get_trust
        - status

---

## ConsolidationEngine

Фоновая консолидация памяти: перенос из рабочей в долговременную.

::: brain.memory.consolidation_engine.ConsolidationEngine
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - start
        - stop
        - consolidate_now
        - status

---

## MemoryDatabase

SQLite WAL backend для всей системы памяти. Опциональное шифрование через SQLCipher (P3-12).

::: brain.memory.storage.MemoryDatabase
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - upsert_semantic_node
        - load_all_semantic_nodes
        - delete_semantic_node
        - upsert_episode
        - load_all_episodes
        - delete_episode
        - upsert_source
        - load_all_sources
        - upsert_procedure
        - load_all_procedures
        - commit
        - rollback
        - close
        - status
        - table_counts
        - schema_version

### Шифрование (SQLCipher)

```python
# Установка: pip install cognitive-core[encrypted]
from brain.memory.storage import MemoryDatabase

# Зашифрованная база данных
db = MemoryDatabase(
    db_path="brain/data/memory/secure.db",
    encryption_key="my-secret-key-32-chars-minimum!!"
)

# Без шифрования (по умолчанию)
db = MemoryDatabase("brain/data/memory/memory.db")
```

!!! warning "Требования"
    Для шифрования необходим пакет `sqlcipher3`:
    ```bash
    pip install cognitive-core[encrypted]
    ```
    На Windows может потребоваться предварительная установка SQLCipher C-библиотеки.
