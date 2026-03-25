"""
consolidation_engine.py — Движок консолидации памяти (аналог Гиппокампа).

Гиппокамп в человеческом мозге отвечает за:
  - Перенос кратковременной памяти в долговременную
  - Укрепление важных воспоминаний
  - Забывание незначительного

Этот модуль делает то же самое:
  - Working Memory → Episodic Memory (важные события)
  - Working Memory → Semantic Memory (факты и концепты)
  - Decay: снижает confidence неиспользуемых фактов
  - Reinforcement: усиливает часто подтверждаемые факты
  - Работает в фоновом потоке (не блокирует основной цикл)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

_logger = logging.getLogger(__name__)

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from .working_memory import WorkingMemory, MemoryItem  # noqa: E402
from .episodic_memory import EpisodicMemory  # noqa: E402
from .semantic_memory import SemanticMemory  # noqa: E402
from .source_memory import SourceMemory  # noqa: E402
from .procedural_memory import ProceduralMemory  # noqa: E402


# ─── Конфигурация консолидации ───────────────────────────────────────────────

@dataclass
class ConsolidationConfig:
    """Настройки движка консолидации."""

    # Интервалы (в секундах)
    CONSOLIDATION_INTERVAL: float = 30.0    # как часто запускать консолидацию
    DECAY_INTERVAL: float         = 300.0   # как часто применять decay (5 минут)
    SAVE_INTERVAL: float          = 120.0   # как часто сохранять на диск (2 минуты)

    # Пороги
    IMPORTANCE_TO_EPISODIC: float = 0.3     # минимальная важность для переноса в Episodic
    IMPORTANCE_TO_SEMANTIC: float = 0.4     # минимальная важность для переноса в Semantic
    CONFIDENCE_DECAY_RATE: float  = 0.003   # скорость затухания уверенности
    SOURCE_DECAY_RATE: float      = 0.001   # скорость затухания доверия к источникам

    # Ресурсы
    RAM_AGGRESSIVE_DECAY_PCT: float = 85.0  # при RAM > 85% — агрессивное забывание
    RAM_NORMAL_DECAY_PCT: float     = 70.0  # при RAM > 70% — ускоренное затухание

    # Лимиты
    MAX_ITEMS_PER_CONSOLIDATION: int = 50   # максимум элементов за один цикл


# ─── Движок консолидации ─────────────────────────────────────────────────────

class ConsolidationEngine:
    """
    Движок консолидации памяти — аналог Гиппокампа.

    Запускается в фоновом потоке и периодически:
    1. Переносит важные элементы из Working Memory → Episodic/Semantic
    2. Применяет decay к семантической памяти
    3. Сохраняет все виды памяти на диск
    4. При нехватке RAM — агрессивно очищает рабочую память

    Параметры:
        working:    WorkingMemory
        episodic:   EpisodicMemory
        semantic:   SemanticMemory
        source:     SourceMemory
        procedural: ProceduralMemory
        config:     ConsolidationConfig
        on_event:   callback для логирования событий
    """

    def __init__(
        self,
        working: WorkingMemory,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        source: SourceMemory,
        procedural: ProceduralMemory,
        config: Optional[ConsolidationConfig] = None,
        on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self._working = working
        self._episodic = episodic
        self._semantic = semantic
        self._source = source
        self._procedural = procedural
        self._config = config or ConsolidationConfig()
        self._on_event = on_event

        # Статистика
        self._consolidation_count = 0
        self._items_transferred = 0
        self._decay_cycles = 0
        self._save_cycles = 0
        self._started_ts = time.time()

        # Фоновый поток
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Временные метки последних операций
        self._last_consolidation = 0.0
        self._last_decay = 0.0
        self._last_save = 0.0

    # ─── Управление потоком ──────────────────────────────────────────────────

    def start(self):
        """Запустить фоновый поток консолидации."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._background_loop,
            name="ConsolidationEngine",
            daemon=True,  # поток завершается вместе с основным процессом
        )
        self._thread.start()
        self._log("info", "ConsolidationEngine запущен (фоновый поток)")

    def stop(self, save_all: bool = True):
        """Остановить фоновый поток консолидации."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        if save_all:
            self.save_all()
        self._log("info", f"ConsolidationEngine остановлен. Циклов: {self._consolidation_count}")

    def _background_loop(self):
        """Основной цикл фонового потока."""
        while self._running:
            try:
                now = time.time()

                # Консолидация (перенос WM → LTM)
                if now - self._last_consolidation >= self._config.CONSOLIDATION_INTERVAL:
                    self.consolidate()
                    self._last_consolidation = now

                # Decay (затухание)
                if now - self._last_decay >= self._config.DECAY_INTERVAL:
                    self.apply_decay()
                    self._last_decay = now

                # Сохранение на диск
                if now - self._last_save >= self._config.SAVE_INTERVAL:
                    self.save_all()
                    self._last_save = now

            except Exception as e:
                self._log("error", f"Ошибка в фоновом цикле: {e}")

            time.sleep(1.0)  # проверяем каждую секунду

    # ─── Консолидация ────────────────────────────────────────────────────────

    def consolidate(self) -> Dict[str, int]:
        """
        Основной цикл консолидации:
        переносит важные элементы из Working Memory в долговременную память.

        Returns:
            Статистика: {"to_episodic": N, "to_semantic": N, "cleared": N}
        """
        with self._lock:
            stats = {"to_episodic": 0, "to_semantic": 0, "cleared": 0}

            items = self._working.get_all()
            if not items:
                return stats

            # Ограничиваем количество за один цикл
            items = items[:self._config.MAX_ITEMS_PER_CONSOLIDATION]

            for item in items:
                # Перенос в Episodic Memory
                if item.importance >= self._config.IMPORTANCE_TO_EPISODIC:
                    self._transfer_to_episodic(item)
                    stats["to_episodic"] += 1

                # Перенос в Semantic Memory (только текстовые концепты)
                if (item.importance >= self._config.IMPORTANCE_TO_SEMANTIC
                        and item.modality in ("text", "concept")):
                    transferred = self._transfer_to_semantic(item)
                    if transferred:
                        stats["to_semantic"] += 1

            # Очищаем рабочую память от старых неважных элементов
            cleared = self._cleanup_working_memory()
            stats["cleared"] = cleared

            self._consolidation_count += 1
            self._items_transferred += stats["to_episodic"] + stats["to_semantic"]

            if stats["to_episodic"] + stats["to_semantic"] > 0:
                self._log("info", (
                    f"Консолидация #{self._consolidation_count}: "
                    f"→episodic={stats['to_episodic']} "
                    f"→semantic={stats['to_semantic']} "
                    f"cleared={stats['cleared']}"
                ))

            return stats

    def _transfer_to_episodic(self, item: MemoryItem):
        """Перенести элемент рабочей памяти в эпизодическую."""
        content_str = str(item.content)

        # Проверяем дубликат (не добавляем одно и то же дважды)
        existing = self._episodic.search(
            query=content_str[:50],
            top_n=1,
            last_n_hours=1.0,
        )
        if existing and existing[0].content == content_str:
            return  # уже есть

        self._episodic.store(
            content=content_str,
            modality=item.modality,
            source=item.source_ref,
            importance=item.importance,
            confidence=1.0,
            tags=item.tags,
        )

    def _transfer_to_semantic(self, item: MemoryItem) -> bool:
        """
        Попытаться извлечь факт из элемента рабочей памяти и сохранить в Semantic.

        Returns:
            True если факт был сохранён
        """
        content_str = str(item.content)

        # Простая эвристика: ищем паттерн "X это Y" или "X — Y"
        fact = self._extract_fact(content_str)
        if not fact:
            return False

        concept, description = fact
        self._semantic.store_fact(
            concept=concept,
            description=description,
            tags=item.tags,
            confidence=0.8,
            importance=item.importance,
            source_ref=item.source_ref,
        )

        # Регистрируем источник
        if item.source_ref:
            self._source.register(item.source_ref)
            self._source.add_fact(item.source_ref)

        return True

    def _extract_fact(self, text: str):
        """
        Извлечь факт из текста.
        Ищет паттерны: "X это Y", "X — Y", "X: Y", "X is Y"

        Returns:
            (concept, description) или None
        """
        text = text.strip()
        if len(text) < 5 or len(text) > 500:
            return None

        # Паттерны на русском
        for sep in [" это ", " — ", " - ", ": "]:
            if sep in text:
                parts = text.split(sep, 1)
                if len(parts) == 2:
                    concept = parts[0].strip()
                    description = parts[1].strip()
                    if 2 <= len(concept) <= 50 and len(description) >= 5:
                        return concept, description

        # Паттерны на английском
        for sep in [" is ", " are ", " means "]:
            if sep in text.lower():
                idx = text.lower().find(sep)
                concept = text[:idx].strip()
                description = text[idx + len(sep):].strip()
                if 2 <= len(concept) <= 50 and len(description) >= 5:
                    return concept, description

        return None

    def _cleanup_working_memory(self) -> int:
        """
        Очистить рабочую память от старых неважных элементов.

        Returns:
            Количество удалённых элементов
        """
        ram_pct = self._get_ram_pct()
        cleared = 0

        # Агрессивная очистка при нехватке RAM
        if ram_pct > self._config.RAM_AGGRESSIVE_DECAY_PCT:
            # Удаляем всё старше 5 минут с importance < 0.5
            threshold_age = 300.0
            threshold_importance = 0.5
        elif ram_pct > self._config.RAM_NORMAL_DECAY_PCT:
            # Удаляем всё старше 15 минут с importance < 0.3
            threshold_age = 900.0
            threshold_importance = 0.3
        else:
            # Нормальный режим: удаляем старше 30 минут с importance < 0.2
            threshold_age = 1800.0
            threshold_importance = 0.2

        items_to_remove = [
            item for item in self._working.get_all()
            if (item.age_seconds() > threshold_age
                and item.importance < threshold_importance)
        ]

        for item in items_to_remove:
            self._working.remove(item)
            cleared += 1

        return cleared

    # ─── Decay ───────────────────────────────────────────────────────────────

    def apply_decay(self):
        """
        Применить затухание ко всем видам памяти.
        Вызывается периодически.
        """
        ram_pct = self._get_ram_pct()

        # Ускоренное затухание при нехватке RAM
        if ram_pct > self._config.RAM_AGGRESSIVE_DECAY_PCT:
            decay_rate = self._config.CONFIDENCE_DECAY_RATE * 5
            source_decay = self._config.SOURCE_DECAY_RATE * 3
        elif ram_pct > self._config.RAM_NORMAL_DECAY_PCT:
            decay_rate = self._config.CONFIDENCE_DECAY_RATE * 2
            source_decay = self._config.SOURCE_DECAY_RATE * 1.5
        else:
            decay_rate = self._config.CONFIDENCE_DECAY_RATE
            source_decay = self._config.SOURCE_DECAY_RATE

        self._semantic.apply_decay(rate=decay_rate)
        self._source.apply_decay(rate=source_decay)

        self._decay_cycles += 1
        self._log("debug", f"Decay применён (RAM={ram_pct:.1f}%, rate={decay_rate:.4f})")

    # ─── Сохранение ──────────────────────────────────────────────────────────

    def save_all(self):
        """Сохранить все виды памяти на диск."""
        try:
            self._episodic.save()
            self._semantic.save()
            self._source.save()
            self._procedural.save()
            self._save_cycles += 1
        except Exception as e:
            self._log("error", f"Ошибка сохранения памяти: {e}")

    # ─── Принудительные операции ─────────────────────────────────────────────

    def force_consolidate(self) -> Dict[str, int]:
        """Принудительно запустить консолидацию (синхронно)."""
        return self.consolidate()

    def force_decay(self):
        """Принудительно применить decay."""
        self.apply_decay()

    def reinforce(self, concept: str, source_ref: str = ""):
        """
        Усилить факт — повысить confidence в семантической памяти.
        Вызывается когда факт подтверждается новыми данными.
        """
        self._semantic.confirm_fact(concept)
        if source_ref:
            self._source.update_trust(source_ref, confirmed=True)

    def weaken(self, concept: str, source_ref: str = ""):
        """
        Ослабить факт — снизить confidence.
        Вызывается когда факт опровергается.
        """
        self._semantic.deny_fact(concept)
        if source_ref:
            self._source.update_trust(source_ref, confirmed=False)

    # ─── Вспомогательные методы ──────────────────────────────────────────────

    def _get_ram_pct(self) -> float:
        """Получить текущий % использования RAM."""
        if not _PSUTIL_AVAILABLE:
            return 0.0
        try:
            return psutil.virtual_memory().percent
        except Exception:
            return 0.0

    def _log(self, level: str, message: str):
        """Логировать событие."""
        if self._on_event:
            self._on_event(level, {
                "module": "consolidation_engine",
                "message": message,
                "ts": time.time(),
            })
        else:
            # Используем стандартный logging вместо print()
            log_fn = {
                "debug":    _logger.debug,
                "info":     _logger.info,
                "warn":     _logger.warning,
                "error":    _logger.error,
                "critical": _logger.critical,
            }.get(level, _logger.info)
            log_fn("[ConsolidationEngine] %s", message)

    # ─── Статистика ──────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Статус движка консолидации."""
        uptime = time.time() - self._started_ts
        return {
            "running": self._running,
            "uptime_seconds": round(uptime, 1),
            "consolidation_count": self._consolidation_count,
            "items_transferred": self._items_transferred,
            "decay_cycles": self._decay_cycles,
            "save_cycles": self._save_cycles,
            "ram_pct": round(self._get_ram_pct(), 1),
            "last_consolidation_ago": round(time.time() - self._last_consolidation, 1) if self._last_consolidation else None,
        }

    def display_status(self):
        """Вывести статус в консоль."""
        s = self.status()
        print(f"\n{'─'*50}")
        print("🧠 Движок консолидации (Гиппокамп)")
        print(f"  Статус: {'🟢 работает' if s['running'] else '🔴 остановлен'}")
        print(f"  Аптайм: {s['uptime_seconds']:.0f}с")
        print(f"  Циклов консолидации: {s['consolidation_count']}")
        print(f"  Перенесено элементов: {s['items_transferred']}")
        print(f"  Циклов decay: {s['decay_cycles']}")
        print(f"  RAM: {s['ram_pct']}%")
        print(f"{'─'*50}\n")

    def __repr__(self) -> str:
        return (
            f"ConsolidationEngine("
            f"running={self._running} | "
            f"cycles={self._consolidation_count} | "
            f"transferred={self._items_transferred})"
        )
