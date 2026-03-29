"""
brain/learning/replay_engine.py

Движок воспроизведения эпизодов (Replay Engine) — Этап I.3.

ReplayEngine воспроизводит эпизоды из эпизодической памяти в idle-режиме:
  - Выбирает эпизоды по стратегии (importance, recency, frequency, random)
  - Проверяет согласованность с семантической памятью
  - Усиливает согласованные эпизоды (confidence += REINFORCE_DELTA)
  - Удаляет устаревшие и незначимые эпизоды (stale pruning)

Интеграция (Этап J):
  - Вызывается из idle hook (когда CPU < idle_cpu_threshold)
  - Или из post-cycle hook после каждого N-го цикла
  - _should_run() проверяет CPU через psutil (если доступен)

Кто потребляет:
  - CognitivePipeline.step_post_cycle() (Этап J) — post-cycle hook
  - CLI --autonomous mode (P3-11) — idle trigger
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from brain.core.contracts import ContractMixin
from brain.memory.episodic_memory import Episode
from brain.memory.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Стратегии воспроизведения
# ---------------------------------------------------------------------------

class ReplayStrategy(str, Enum):
    """Стратегия выбора эпизодов для воспроизведения."""
    IMPORTANCE_BASED = "importance"   # сначала самые важные
    RECENCY_BASED = "recency"         # сначала самые свежие
    FREQUENCY_BASED = "frequency"     # сначала самые часто используемые
    RANDOM = "random"                 # случайная выборка


# ---------------------------------------------------------------------------
# Результат сессии воспроизведения
# ---------------------------------------------------------------------------

@dataclass
class ReplaySession(ContractMixin):
    """
    Результат одной сессии воспроизведения.

    Поля:
        session_id        — уникальный ID сессии
        strategy          — использованная стратегия
        episodes_replayed — количество обработанных эпизодов
        reinforced        — количество усиленных эпизодов (confidence += delta)
        stale_removed     — количество удалённых устаревших эпизодов
        duration_ms       — время выполнения в мс
        metadata          — дополнительный контекст (skipped, reason, ...)
    """
    session_id: str
    strategy: ReplayStrategy
    episodes_replayed: int = 0
    reinforced: int = 0
    stale_removed: int = 0
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Движок воспроизведения
# ---------------------------------------------------------------------------

class ReplayEngine:
    """
    Движок воспроизведения эпизодов.

    Воспроизводит эпизоды из эпизодической памяти в idle-режиме.
    Усиливает согласованные эпизоды, удаляет устаревшие.

    Параметры:
        memory                — MemoryManager (фасад системы памяти)
        batch_size            — размер батча по умолчанию (10)
        idle_cpu_threshold    — порог CPU% для запуска (30.0)
                                Если CPU > threshold → пропустить сессию
                                Если psutil недоступен → всегда запускать

    Интеграция (Этап J):
        - Вызывается из idle hook (CPU < idle_cpu_threshold)
        - Или из post-cycle hook после каждого N-го цикла
        - Кто потребляет: CognitivePipeline.step_post_cycle(), CLI --autonomous
    """

    # Константы
    STALE_AGE_DAYS: float = 7.0
    STALE_MIN_IMPORTANCE: float = 0.1
    REINFORCE_DELTA: float = 0.01
    CONSISTENCY_CONFIDENCE_THRESHOLD: float = 0.5
    MAX_EPISODES_POOL: int = 200  # максимальный пул для выборки

    def __init__(
        self,
        memory: MemoryManager,
        batch_size: int = 10,
        idle_cpu_threshold: float = 30.0,
    ) -> None:
        self._memory = memory
        self._batch_size = batch_size
        self._idle_cpu_threshold = idle_cpu_threshold

        # Статистика
        self._session_count: int = 0
        self._total_replayed: int = 0
        self._total_reinforced: int = 0
        self._total_removed: int = 0

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def run_replay_session(
        self,
        strategy: ReplayStrategy = ReplayStrategy.IMPORTANCE_BASED,
        batch_size: Optional[int] = None,
        force: bool = False,
    ) -> ReplaySession:
        """
        Запустить сессию воспроизведения эпизодов.

        Args:
            strategy:   стратегия выбора эпизодов
            batch_size: размер батча (None = self._batch_size)
            force:      игнорировать проверку CPU (_should_run)

        Returns:
            ReplaySession с результатами сессии
        """
        t0 = time.perf_counter()
        session = ReplaySession(
            session_id=f"replay_{uuid.uuid4().hex[:8]}",
            strategy=strategy,
        )

        # Проверка CPU (если не force)
        if not force and not self._should_run():
            logger.debug(
                "[ReplayEngine] пропуск: CPU выше порога %.1f%%",
                self._idle_cpu_threshold,
            )
            session.metadata["skipped"] = True
            session.metadata["reason"] = "cpu_busy"
            session.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            return session

        n = batch_size if batch_size is not None else self._batch_size
        episodes = self._select_episodes(strategy, n)

        for ep in episodes:
            outcome = self._replay_episode(ep)
            session.episodes_replayed += 1
            if outcome == "reinforced":
                session.reinforced += 1
            elif outcome == "stale":
                session.stale_removed += 1

        # Обновляем статистику
        self._session_count += 1
        self._total_replayed += session.episodes_replayed
        self._total_reinforced += session.reinforced
        self._total_removed += session.stale_removed

        session.duration_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(
            "[ReplayEngine] сессия %s: replayed=%d reinforced=%d stale=%d %.1fms",
            session.session_id,
            session.episodes_replayed,
            session.reinforced,
            session.stale_removed,
            session.duration_ms,
        )
        return session

    def cleanup_stale(
        self,
        age_days: float = STALE_AGE_DAYS,
        min_importance: float = STALE_MIN_IMPORTANCE,
    ) -> int:
        """
        Принудительная очистка устаревших эпизодов.

        Удаляет эпизоды с:
          - importance < min_importance
          - age > age_days
          - access_count == 0

        Args:
            age_days:       порог возраста в днях (по умолчанию 7.0)
            min_importance: порог важности (по умолчанию 0.1)

        Returns:
            Количество удалённых эпизодов
        """
        removed = 0
        try:
            episodes = self._memory.episodic.get_recent(n=self.MAX_EPISODES_POOL)
            for ep in episodes:
                if (
                    ep.importance < min_importance
                    and ep.age_days() > age_days
                    and ep.access_count == 0
                ):
                    try:
                        self._memory.episodic._remove_episode(ep)
                        removed += 1
                    except Exception as exc:
                        logger.debug("[ReplayEngine] ошибка удаления эпизода: %s", exc)
        except Exception as exc:
            logger.warning("[ReplayEngine] cleanup_stale error: %s", exc)

        if removed:
            logger.info("[ReplayEngine] cleanup_stale: удалено %d эпизодов", removed)
            self._total_removed += removed

        return removed

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _should_run(self) -> bool:
        """
        Проверить, можно ли запустить replay (CPU < idle_cpu_threshold).

        Если psutil недоступен — всегда True (не блокируем выполнение).
        """
        if not _PSUTIL_AVAILABLE:
            return True
        try:
            cpu_pct = psutil.cpu_percent(interval=0.1)
            return float(cpu_pct) < self._idle_cpu_threshold
        except Exception:
            return True

    def _select_episodes(
        self,
        strategy: ReplayStrategy,
        n: int,
    ) -> List[Episode]:
        """
        Выбрать эпизоды для воспроизведения по стратегии.

        Получает пул из MAX_EPISODES_POOL последних эпизодов,
        затем сортирует/выбирает по стратегии.

        Args:
            strategy: стратегия выбора
            n:        количество эпизодов

        Returns:
            Список Episode для воспроизведения
        """
        try:
            pool = self._memory.episodic.get_recent(n=min(n * 5, self.MAX_EPISODES_POOL))
        except Exception as exc:
            logger.warning("[ReplayEngine] ошибка получения эпизодов: %s", exc)
            return []

        if not pool:
            return []

        if strategy == ReplayStrategy.IMPORTANCE_BASED:
            pool.sort(key=lambda e: e.importance, reverse=True)
            return pool[:n]

        if strategy == ReplayStrategy.RECENCY_BASED:
            pool.sort(key=lambda e: e.ts, reverse=True)
            return pool[:n]

        if strategy == ReplayStrategy.FREQUENCY_BASED:
            pool.sort(key=lambda e: e.access_count, reverse=True)
            return pool[:n]

        if strategy == ReplayStrategy.RANDOM:
            sample_size = min(n, len(pool))
            return random.sample(pool, sample_size)  # nosec B311

        # Fallback: importance
        pool.sort(key=lambda e: e.importance, reverse=True)
        return pool[:n]

    def _replay_episode(self, episode: Episode) -> str:
        """
        Воспроизвести один эпизод.

        Логика:
          1. Если stale (importance < threshold AND age > threshold AND access == 0)
             → удалить эпизод, вернуть "stale"
          2. Если согласован с семантической памятью
             → усилить confidence += REINFORCE_DELTA, вернуть "reinforced"
          3. Иначе → вернуть "ok"

        Returns:
            "reinforced" — confidence усилен
            "stale"      — эпизод устаревший и удалён
            "ok"         — без изменений
        """
        # Проверка на stale
        if (
            episode.importance < self.STALE_MIN_IMPORTANCE
            and episode.age_days() > self.STALE_AGE_DAYS
            and episode.access_count == 0
        ):
            try:
                self._memory.episodic._remove_episode(episode)
            except Exception as exc:
                logger.debug("[ReplayEngine] ошибка удаления stale эпизода: %s", exc)
            return "stale"

        # Проверка согласованности с семантической памятью
        if self._check_consistency(episode):
            episode.confidence = min(1.0, episode.confidence + self.REINFORCE_DELTA)
            return "reinforced"

        return "ok"

    def _check_consistency(self, episode: Episode) -> bool:
        """
        Проверить согласованность эпизода с семантической памятью.

        Эпизод считается согласованным, если хотя бы один из его концептов
        присутствует в семантической памяти с confidence > CONSISTENCY_CONFIDENCE_THRESHOLD.

        Проверяются первые 3 концепта для производительности.

        Args:
            episode: эпизод для проверки

        Returns:
            True если эпизод согласован с семантической памятью
        """
        if not episode.concepts:
            return False

        for concept in episode.concepts[:3]:
            try:
                node = self._memory.semantic.get_fact(concept)
                if node and node.confidence > self.CONSISTENCY_CONFIDENCE_THRESHOLD:
                    return True
            except Exception as exc:
                logger.debug(
                    "[ReplayEngine] _check_consistency error for '%s': %s", concept, exc
                )

        return False

    # ------------------------------------------------------------------
    # Статус и repr
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Статус движка воспроизведения."""
        return {
            "session_count": self._session_count,
            "total_replayed": self._total_replayed,
            "total_reinforced": self._total_reinforced,
            "total_removed": self._total_removed,
            "batch_size": self._batch_size,
            "idle_cpu_threshold": self._idle_cpu_threshold,
            "psutil_available": _PSUTIL_AVAILABLE,
        }

    def __repr__(self) -> str:
        return (
            f"ReplayEngine("
            f"sessions={self._session_count} | "
            f"replayed={self._total_replayed} | "
            f"reinforced={self._total_reinforced} | "
            f"removed={self._total_removed})"
        )
