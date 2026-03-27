"""
memory_manager.py — Единый интерфейс ко всем видам памяти.

MemoryManager — это "диспетчер" памяти мозга:
  - Агрегирует все 5 видов памяти + движок консолидации
  - Единая точка входа для store/retrieve операций
  - Resource-aware: мониторит RAM и адаптирует поведение
  - Автозапуск консолидации в фоне
  - Единый метод save_all() / load_all()

Использование:
    mm = MemoryManager()
    mm.start()

    mm.store("нейрон это клетка нервной системы", importance=0.8)
    results = mm.retrieve("нейрон")
    mm.save_all()
    mm.stop()
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

_logger = logging.getLogger(__name__)

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from brain.core.text_utils import parse_fact_pattern  # noqa: E402

from .consolidation_engine import ConsolidationEngine  # noqa: E402
from .episodic_memory import Episode, EpisodicMemory, ModalEvidence  # noqa: E402
from .procedural_memory import ProceduralMemory  # noqa: E402
from .semantic_memory import SemanticMemory, SemanticNode  # noqa: E402
from .source_memory import SourceMemory  # noqa: E402
from .storage import MemoryDatabase  # noqa: E402
from .working_memory import MemoryItem, WorkingMemory  # noqa: E402

# ─── Результат поиска ────────────────────────────────────────────────────────

class MemorySearchResult:
    """Агрегированный результат поиска по всем видам памяти."""

    def __init__(self):
        self.working: List[MemoryItem] = []
        self.semantic: List[SemanticNode] = []
        self.episodic: List[Episode] = []
        self.total: int = 0

    def is_empty(self) -> bool:
        return self.total == 0

    def best_semantic(self) -> Optional[SemanticNode]:
        """Лучший результат из семантической памяти."""
        return self.semantic[0] if self.semantic else None

    def best_episodic(self) -> Optional[Episode]:
        """Лучший результат из эпизодической памяти."""
        return self.episodic[0] if self.episodic else None

    def summary(self) -> str:
        """Краткое текстовое резюме результатов поиска."""
        parts = []
        if self.semantic:
            node = self.semantic[0]
            parts.append(f"[Факт] {node.concept}: {node.description[:100]}")
        if self.episodic:
            ep = self.episodic[0]
            parts.append(f"[Эпизод] {ep.content[:100]}")
        if self.working:
            item = self.working[0]
            parts.append(f"[Контекст] {str(item.content)[:100]}")
        return "\n".join(parts) if parts else "(ничего не найдено)"

    def __repr__(self) -> str:
        return (
            f"MemorySearchResult("
            f"working={len(self.working)} | "
            f"semantic={len(self.semantic)} | "
            f"episodic={len(self.episodic)} | "
            f"total={self.total})"
        )


# ─── Менеджер памяти ─────────────────────────────────────────────────────────

class MemoryManager:
    """
    Единый интерфейс ко всей системе памяти мозга.

    Параметры:
        data_dir            — директория для хранения JSON-файлов
        working_max_size    — максимальный размер рабочей памяти
        semantic_max_nodes  — максимальное количество узлов семантической памяти
        episodic_max        — максимальное количество эпизодов
        auto_consolidate    — запускать ли фоновую консолидацию
        on_event            — callback для логирования событий
    """

    def __init__(
        self,
        data_dir: str = "brain/data/memory",
        working_max_size: int = 20,
        semantic_max_nodes: int = 10_000,
        episodic_max: int = 5_000,
        auto_consolidate: bool = True,
        on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        storage_backend: str = "auto",
    ):
        self._data_dir = data_dir
        self._auto_consolidate = auto_consolidate
        self._on_event = on_event
        self._started = False
        self._storage_backend = storage_backend

        # ── SQLite backend (если запрошен) ────────────────────────────────────
        self._db: Optional[MemoryDatabase] = None

        if storage_backend == "sqlite" or (
            storage_backend == "auto" and self._should_use_sqlite()
        ):
            self._db = MemoryDatabase(
                db_path=f"{data_dir}/memory.db",
            )
            self._effective_backend = "sqlite"
        else:
            self._effective_backend = "json"

        # ── Инициализация всех видов памяти ──────────────────────────────────
        self.working = WorkingMemory(max_size=working_max_size)

        self.semantic = SemanticMemory(
            data_path=f"{data_dir}/semantic.json",
            max_nodes=semantic_max_nodes,
            storage_backend=self._effective_backend,
            db=self._db,
        )

        self.episodic = EpisodicMemory(
            data_path=f"{data_dir}/episodes.json",
            max_episodes=episodic_max,
            storage_backend=self._effective_backend,
            db=self._db,
        )

        self.source = SourceMemory(
            data_path=f"{data_dir}/sources.json",
            storage_backend=self._effective_backend,
            db=self._db,
        )

        self.procedural = ProceduralMemory(
            data_path=f"{data_dir}/procedures.json",
            storage_backend=self._effective_backend,
            db=self._db,
        )

        # ── Движок консолидации (Гиппокамп) ──────────────────────────────────
        self.consolidation = ConsolidationEngine(
            working=self.working,
            episodic=self.episodic,
            semantic=self.semantic,
            source=self.source,
            procedural=self.procedural,
            on_event=on_event,
        )

        self._store_count = 0
        self._retrieve_count = 0

    def _should_use_sqlite(self) -> bool:
        """
        Определить, стоит ли использовать SQLite в режиме 'auto'.

        Логика: если уже есть memory.db — используем SQLite.
        Иначе — JSON (обратная совместимость).
        """
        import os
        db_path = f"{self._data_dir}/memory.db"
        return os.path.exists(db_path)

    # ─── Жизненный цикл ──────────────────────────────────────────────────────

    def start(self):
        """Запустить менеджер памяти (и фоновую консолидацию)."""
        if self._started:
            return
        self._started = True
        if self._auto_consolidate:
            self.consolidation.start()
        self._log("info", "MemoryManager запущен")

    def stop(self, save: bool = True):
        """Остановить менеджер памяти."""
        self.consolidation.stop(save_all=save)
        if self._db is not None:
            self._db.close()
        self._started = False
        self._log("info", "MemoryManager остановлен")

    # ─── Единый интерфейс store ──────────────────────────────────────────────

    def store(
        self,
        content: Any,
        modality: str = "text",
        importance: float = 0.5,
        source_ref: str = "",
        tags: Optional[List[str]] = None,
        concepts: Optional[List[str]] = None,
        trace_id: str = "",
        session_id: str = "",
        auto_extract_facts: bool = True,
    ) -> Dict[str, Any]:
        """
        Сохранить информацию в память.

        Автоматически:
        1. Добавляет в рабочую память (всегда)
        2. Если importance >= 0.4 → добавляет в эпизодическую
        3. Если auto_extract_facts → пытается извлечь факт в семантическую
        4. Регистрирует источник

        Returns:
            Словарь с результатами: {"working": item, "episodic": ep, "semantic": node}
        """
        result: Dict[str, Any] = {}
        content_str = str(content)

        # 1. Рабочая память (всегда)
        item = self.working.push(
            content=content,
            modality=modality,
            importance=importance,
            source_ref=source_ref,
            tags=tags or [],
        )
        result["working"] = item

        # 2. Эпизодическая память (если достаточно важно)
        if importance >= 0.4:
            ep = self.episodic.store(
                content=content_str,
                modality=modality,
                source=source_ref,
                importance=importance,
                tags=tags or [],
                concepts=concepts or [],
                trace_id=trace_id,
                session_id=session_id,
            )
            result["episodic"] = ep

        # 3. Семантическая память (автоизвлечение фактов)
        if auto_extract_facts and modality in ("text", "concept"):
            fact = parse_fact_pattern(content_str)
            if fact:
                concept, description = fact
                node = self.semantic.store_fact(
                    concept=concept,
                    description=description,
                    tags=tags or [],
                    importance=importance,
                    source_ref=source_ref,
                )
                result["semantic"] = node

        # 4. Регистрация источника
        if source_ref:
            self.source.register(source_ref)
            self.source.add_fact(source_ref)

        self._store_count += 1
        return result

    def store_fact(
        self,
        concept: str,
        description: str,
        tags: Optional[List[str]] = None,
        confidence: float = 1.0,
        importance: float = 0.7,
        source_ref: str = "",
    ) -> SemanticNode:
        """
        Явно сохранить факт в семантическую память.

        Returns:
            SemanticNode
        """
        node = self.semantic.store_fact(
            concept=concept,
            description=description,
            tags=tags or [],
            confidence=confidence,
            importance=importance,
            source_ref=source_ref,
        )
        if source_ref:
            self.source.register(source_ref)
            self.source.add_fact(source_ref)
        self._store_count += 1
        return node

    def store_episode(
        self,
        content: str,
        modality: str = "text",
        source: str = "",
        importance: float = 0.5,
        tags: Optional[List[str]] = None,
        concepts: Optional[List[str]] = None,
        modal_evidence: Optional[List[ModalEvidence]] = None,
        trace_id: str = "",
        session_id: str = "",
    ) -> Episode:
        """Явно сохранить эпизод в эпизодическую память."""
        ep = self.episodic.store(
            content=content,
            modality=modality,
            source=source,
            importance=importance,
            tags=tags or [],
            concepts=concepts or [],
            modal_evidence=modal_evidence or [],
            trace_id=trace_id,
            session_id=session_id,
        )
        self._store_count += 1
        return ep

    # ─── Единый интерфейс retrieve ───────────────────────────────────────────

    def retrieve(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        top_n: int = 5,
        min_importance: float = 0.0,
    ) -> MemorySearchResult:
        """
        Поиск по всем видам памяти.

        Args:
            query:          строка поиска
            memory_types:   список видов памяти для поиска
                            ['working', 'semantic', 'episodic'] или None (все)
            top_n:          максимальное количество результатов из каждого вида
            min_importance: минимальная важность

        Returns:
            MemorySearchResult с результатами из всех видов памяти
        """
        if memory_types is None:
            memory_types = ["working", "semantic", "episodic"]

        result = MemorySearchResult()

        if "working" in memory_types:
            result.working = self.working.search(query, top_n=top_n)

        if "semantic" in memory_types:
            result.semantic = self.semantic.search(
                query, top_n=top_n, min_confidence=min_importance
            )

        if "episodic" in memory_types:
            result.episodic = self.episodic.search(
                query, top_n=top_n, min_importance=min_importance
            )

        result.total = len(result.working) + len(result.semantic) + len(result.episodic)
        self._retrieve_count += 1
        return result

    def get_fact(self, concept: str) -> Optional[SemanticNode]:
        """Быстрый доступ к факту из семантической памяти."""
        return self.semantic.get_fact(concept)

    def get_context(self, n: int = 10) -> List[MemoryItem]:
        """Получить текущий контекст из рабочей памяти."""
        return self.working.get_context(n)

    def get_recent_episodes(self, n: int = 10) -> List[Episode]:
        """Получить последние N эпизодов."""
        return self.episodic.get_recent(n)

    def get_related(self, concept: str, top_n: int = 10):
        """Получить связанные понятия из семантической памяти."""
        return self.semantic.get_related(concept, top_n=top_n)

    # ─── Обратная связь (подтверждение/опровержение) ─────────────────────────

    def confirm(self, concept: str, source_ref: str = ""):
        """Подтвердить факт — повысить confidence."""
        self.consolidation.reinforce(concept, source_ref)

    def deny(self, concept: str, source_ref: str = ""):
        """Опровергнуть факт — снизить confidence."""
        self.consolidation.weaken(concept, source_ref)

    # ─── Персистентность ─────────────────────────────────────────────────────

    def save_all(self):
        """Сохранить все виды памяти (JSON или SQLite с транзакцией)."""
        if self._db is not None:
            try:
                self._db.begin()
                self.semantic.save()
                self.episodic.save()
                self.source.save()
                self.procedural.save()
                self._db.commit()
                _logger.info("save_all: транзакция SQLite зафиксирована")
            except Exception:
                self._db.rollback()
                _logger.exception("save_all: откат транзакции SQLite")
                raise
        else:
            self.consolidation.save_all()

    def force_consolidate(self) -> Dict[str, int]:
        """Принудительно запустить консолидацию."""
        return self.consolidation.force_consolidate()

    # ─── Ресурсы ─────────────────────────────────────────────────────────────

    def ram_status(self) -> Dict[str, Any]:
        """Текущее состояние RAM."""
        if not _PSUTIL_AVAILABLE:
            return {"available": False}
        try:
            vm = psutil.virtual_memory()
            return {
                "total_gb": round(vm.total / (1024**3), 2),
                "available_gb": round(vm.available / (1024**3), 2),
                "used_gb": round(vm.used / (1024**3), 2),
                "percent": vm.percent,
                "status": (
                    "🔴 критично" if vm.percent > 85
                    else "🟡 высокая" if vm.percent > 70
                    else "🟢 норма"
                ),
            }
        except Exception:
            return {"available": False}

    # ─── Статистика ──────────────────────────────────────────────────────────

    @property
    def db(self) -> Optional[MemoryDatabase]:
        """Доступ к SQLite backend (None если JSON)."""
        return self._db

    @property
    def effective_backend(self) -> str:
        """Текущий backend: 'sqlite' или 'json'."""
        return self._effective_backend

    def status(self) -> Dict[str, Any]:
        """Полный статус системы памяти."""
        result = {
            "memory_manager": {
                "started": self._started,
                "store_count": self._store_count,
                "retrieve_count": self._retrieve_count,
                "data_dir": self._data_dir,
                "storage_backend": self._effective_backend,
            },
            "working": self.working.status(),
            "semantic": self.semantic.status(),
            "episodic": self.episodic.status(),
            "source": self.source.status(),
            "procedural": self.procedural.status(),
            "consolidation": self.consolidation.status(),
            "ram": self.ram_status(),
        }
        if self._db is not None:
            result["sqlite"] = self._db.status()
        return result

    def display_status(self):
        """Вывести полный статус в консоль."""
        print(f"\n{'═'*55}")
        print("🧠 СИСТЕМА ПАМЯТИ — СТАТУС")
        print(f"{'═'*55}")

        # RAM
        ram = self.ram_status()
        if "percent" in ram:
            print(f"\n💾 RAM: {ram['used_gb']} GB / {ram['total_gb']} GB "
                  f"({ram['percent']:.1f}%) {ram['status']}")

        # Рабочая память
        wm = self.working.status()
        print("\n📋 Рабочая память:")
        print(f"   {wm['normal_items']} обычных + {wm['protected_items']} защищённых "
              f"(лимит: {wm['effective_max']})")

        # Семантическая память
        sm = self.semantic.status()
        print("\n📚 Семантическая память:")
        print(f"   {sm['node_count']} понятий | {sm['total_relations']} связей | "
              f"уверенность: {sm['avg_confidence']:.0%}")

        # Эпизодическая память
        em = self.episodic.status()
        print("\n📖 Эпизодическая память:")
        print(f"   {em['episode_count']} эпизодов | "
              f"защищённых: {em['protected_count']} | "
              f"модальности: {em['modality_breakdown']}")

        # Источники
        src = self.source.status()
        print("\n🔗 Источники:")
        print(f"   {src['source_count']} источников | "
              f"надёжных: {src['reliable_count']} | "
              f"среднее доверие: {src['avg_trust_score']:.0%}")

        # Процедуры
        proc = self.procedural.status()
        print("\n⚙️  Процедурная память:")
        print(f"   {proc['procedure_count']} процедур | "
              f"success rate: {proc['avg_success_rate']:.0%}")

        # Консолидация
        cons = self.consolidation.status()
        print("\n🔄 Консолидация (Гиппокамп):")
        print(f"   {'🟢 работает' if cons['running'] else '🔴 остановлена'} | "
              f"циклов: {cons['consolidation_count']} | "
              f"перенесено: {cons['items_transferred']}")

        print(f"\n{'═'*55}\n")

    def _log(self, level: str, message: str):
        """Логировать событие."""
        if self._on_event:
            self._on_event(level, {"module": "memory_manager", "message": message})
        else:
            log_fn = {
                "debug":    _logger.debug,
                "info":     _logger.info,
                "warn":     _logger.warning,
                "error":    _logger.error,
                "critical": _logger.critical,
            }.get(level, _logger.info)
            log_fn("[MemoryManager] %s", message)

    def __repr__(self) -> str:
        return (
            f"MemoryManager("
            f"working={len(self.working)} | "
            f"semantic={len(self.semantic)} | "
            f"episodic={len(self.episodic)} | "
            f"sources={len(self.source)} | "
            f"procedures={len(self.procedural)})"
        )
