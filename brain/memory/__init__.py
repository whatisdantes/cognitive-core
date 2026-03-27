"""
brain/memory — Система памяти мозга (многоуровневая, аналог человеческой).

Модули:
    working_memory      — рабочая память (текущий контекст, RAM-only)
    semantic_memory     — семантическая память (факты, понятия, граф связей)
    episodic_memory     — эпизодическая память (история событий)
    source_memory       — память об источниках (доверие, происхождение)
    procedural_memory   — процедурная память (навыки, стратегии)
    consolidation_engine — движок консолидации (Гиппокамп)
    memory_manager      — единый интерфейс ко всей системе памяти
    storage             — SQLite persistence backend
    migrate             — миграция JSON → SQLite
"""

from .consolidation_engine import ConsolidationConfig, ConsolidationEngine
from .episodic_memory import Episode, EpisodicMemory, ModalEvidence
from .memory_manager import MemoryManager, MemorySearchResult
from .migrate import auto_migrate_if_needed, migrate_json_to_sqlite
from .procedural_memory import ProceduralMemory, Procedure, ProcedureStep
from .semantic_memory import Relation, SemanticMemory, SemanticNode
from .source_memory import SourceMemory, SourceRecord
from .storage import MemoryDatabase
from .working_memory import MemoryItem, WorkingMemory

__all__ = [
    # Менеджер (главная точка входа)
    "MemoryManager",
    "MemorySearchResult",
    # SQLite backend
    "MemoryDatabase",
    # Миграция
    "migrate_json_to_sqlite",
    "auto_migrate_if_needed",
    # Рабочая память
    "WorkingMemory",
    "MemoryItem",
    # Семантическая память
    "SemanticMemory",
    "SemanticNode",
    "Relation",
    # Эпизодическая память
    "EpisodicMemory",
    "Episode",
    "ModalEvidence",
    # Память об источниках
    "SourceMemory",
    "SourceRecord",
    # Процедурная память
    "ProceduralMemory",
    "Procedure",
    "ProcedureStep",
    # Консолидация
    "ConsolidationEngine",
    "ConsolidationConfig",
]
