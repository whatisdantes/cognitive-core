"""
brain/learning/knowledge_gap_detector.py

Детектор пробелов в знаниях (Этап I.2).

KnowledgeGapDetector анализирует результаты поиска после retrieve()
и фиксирует пробелы трёх типов:
  - MISSING  (HIGH)   — total == 0, нет ни одного результата
  - WEAK     (MEDIUM) — semantic[0].confidence < weak_threshold
  - OUTDATED (LOW)    — semantic[0].age_days() > outdated_days

Дедупликация: повторный пробел для того же concept + gap_type
не создаётся, пока предыдущий не решён.

v1: single-result heuristic — анализируется только top-1 результат.
Planned: aggregate scoring по всем результатам.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from brain.core.contracts import ContractMixin
from brain.memory.memory_manager import MemoryManager, MemorySearchResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Перечисления
# ---------------------------------------------------------------------------

class GapSeverity(str, Enum):
    """Серьёзность пробела в знаниях."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class GapType(str, Enum):
    """Тип пробела в знаниях."""
    MISSING = "missing"      # нет ни одного результата
    WEAK = "weak"            # низкая уверенность в top-1 факте
    OUTDATED = "outdated"    # устаревший top-1 факт (age > threshold)
    MODAL = "modal"          # нет результатов в конкретной модальности (planned)


# ---------------------------------------------------------------------------
# Dataclass пробела
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeGap(ContractMixin):
    """
    Зафиксированный пробел в знаниях.

    Поля:
        gap_id      — уникальный ID пробела
        concept     — нормализованный запрос/концепт
        severity    — серьёзность (HIGH / MEDIUM / LOW)
        gap_type    — тип пробела (MISSING / WEAK / OUTDATED / MODAL)
        detected_at — unix timestamp обнаружения
        resolved    — решён ли пробел
        metadata    — дополнительный контекст (confidence, age_days, ...)
    """
    gap_id: str
    concept: str
    severity: GapSeverity
    gap_type: GapType
    detected_at: float = field(default_factory=time.time)
    resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Детектор пробелов
# ---------------------------------------------------------------------------

class KnowledgeGapDetector:
    """
    Детектор пробелов в знаниях.

    Анализирует результаты поиска после retrieve() и фиксирует пробелы.

    v1: single-result heuristic — анализируется только top-1 результат.
    Planned: aggregate scoring по всем результатам.

    Параметры:
        memory          — MemoryManager (фасад системы памяти)
        weak_threshold  — порог confidence для WEAK (по умолчанию 0.5)
        outdated_days   — порог возраста для OUTDATED в днях (по умолчанию 30.0)
        max_gaps        — максимальное количество хранимых пробелов (1000)
    """

    def __init__(
        self,
        memory: MemoryManager,
        weak_threshold: float = 0.5,
        outdated_days: float = 30.0,
        max_gaps: int = 1000,
    ) -> None:
        self._memory = memory
        self._weak_threshold = weak_threshold
        self._outdated_days = outdated_days
        self._max_gaps = max_gaps

        self._lock = threading.RLock()
        self._gaps: Dict[str, KnowledgeGap] = {}  # gap_id → KnowledgeGap

        # Статистика
        self._detected_count: int = 0
        self._resolved_count: int = 0

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def analyze(
        self,
        query: str,
        search_result: MemorySearchResult,
    ) -> Optional[KnowledgeGap]:
        """
        Проанализировать результат поиска и зафиксировать пробел (если есть).

        v1: single-result heuristic:
          - total == 0                              → MISSING / HIGH
          - semantic[0].confidence < weak_threshold → WEAK / MEDIUM
          - semantic[0].age_days() > outdated_days  → OUTDATED / LOW
          - иначе                                   → None (пробела нет)

        Planned: aggregate scoring по всем результатам.

        Args:
            query:         исходный запрос (нормализуется до 100 символов)
            search_result: результат MemoryManager.retrieve()

        Returns:
            KnowledgeGap если пробел обнаружен, иначе None
        """
        concept = query.strip().lower()[:100]

        # --- MISSING: нет ни одного результата ---
        if search_result.total == 0:
            return self._register_gap(
                concept=concept,
                severity=GapSeverity.HIGH,
                gap_type=GapType.MISSING,
                metadata={"query": query},
            )

        # --- Анализ top-1 семантического результата ---
        best = search_result.best_semantic()
        if best is not None:
            # WEAK: низкая уверенность в top-1 факте
            if best.confidence < self._weak_threshold:
                return self._register_gap(
                    concept=concept,
                    severity=GapSeverity.MEDIUM,
                    gap_type=GapType.WEAK,
                    metadata={
                        "query": query,
                        "confidence": round(best.confidence, 4),
                        "threshold": self._weak_threshold,
                        "concept_found": best.concept,
                    },
                )

            # OUTDATED: устаревший top-1 факт
            age = best.age_days()
            if age > self._outdated_days:
                return self._register_gap(
                    concept=concept,
                    severity=GapSeverity.LOW,
                    gap_type=GapType.OUTDATED,
                    metadata={
                        "query": query,
                        "age_days": round(age, 1),
                        "outdated_threshold": self._outdated_days,
                        "concept_found": best.concept,
                    },
                )

        return None

    def get_gaps(
        self,
        severity: Optional[GapSeverity] = None,
        resolved: bool = False,
    ) -> List[KnowledgeGap]:
        """
        Получить список пробелов.

        Args:
            severity: фильтр по серьёзности (None = все)
            resolved: включать ли решённые пробелы (по умолчанию False)

        Returns:
            Список KnowledgeGap, отсортированных по severity → detected_at
        """
        _SEVERITY_ORDER = {GapSeverity.HIGH: 0, GapSeverity.MEDIUM: 1, GapSeverity.LOW: 2}

        with self._lock:
            result = [
                g for g in self._gaps.values()
                if (resolved or not g.resolved)
                and (severity is None or g.severity == severity)
            ]

        result.sort(key=lambda g: (_SEVERITY_ORDER.get(g.severity, 9), g.detected_at))
        return result

    def resolve_gap(self, gap_id: str) -> bool:
        """
        Отметить пробел как решённый.

        Args:
            gap_id: ID пробела

        Returns:
            True если пробел найден и помечен решённым, False иначе
        """
        with self._lock:
            gap = self._gaps.get(gap_id)
            if gap and not gap.resolved:
                gap.resolved = True
                self._resolved_count += 1
                logger.debug(
                    "[KnowledgeGapDetector] пробел решён: %s (concept='%s')",
                    gap_id, gap.concept,
                )
                return True
        return False

    def resolve_by_concept(self, concept: str) -> int:
        """
        Решить все активные пробелы для данного концепта.

        Args:
            concept: концепт/запрос (нормализуется)

        Returns:
            Количество решённых пробелов
        """
        concept = concept.strip().lower()[:100]
        count = 0
        with self._lock:
            for gap in self._gaps.values():
                if gap.concept == concept and not gap.resolved:
                    gap.resolved = True
                    self._resolved_count += 1
                    count += 1
        if count:
            logger.debug(
                "[KnowledgeGapDetector] решено %d пробелов для concept='%s'",
                count, concept,
            )
        return count

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _register_gap(
        self,
        concept: str,
        severity: GapSeverity,
        gap_type: GapType,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeGap:
        """
        Зарегистрировать пробел с дедупликацией по (concept, gap_type).

        Если уже есть нерешённый пробел для этого concept + gap_type —
        возвращает существующий без создания нового.
        """
        with self._lock:
            # Дедупликация
            for gap in self._gaps.values():
                if (
                    gap.concept == concept
                    and gap.gap_type == gap_type
                    and not gap.resolved
                ):
                    return gap

            # Лимит: вытесняем решённые пробелы
            if len(self._gaps) >= self._max_gaps:
                self._evict_resolved()

            gap = KnowledgeGap(
                gap_id=f"gap_{uuid.uuid4().hex[:8]}",
                concept=concept,
                severity=severity,
                gap_type=gap_type,
                metadata=metadata or {},
            )
            self._gaps[gap.gap_id] = gap
            self._detected_count += 1

        logger.debug(
            "[KnowledgeGapDetector] пробел: concept='%s' type=%s severity=%s",
            concept, gap_type.value, severity.value,
        )
        return gap

    def _evict_resolved(self) -> None:
        """Удалить половину решённых пробелов для освобождения места."""
        resolved_ids = [gid for gid, g in self._gaps.items() if g.resolved]
        evict_n = max(1, len(resolved_ids) // 2)
        for gid in resolved_ids[:evict_n]:
            del self._gaps[gid]

    # ------------------------------------------------------------------
    # Статус и repr
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Статус детектора пробелов."""
        with self._lock:
            active = [g for g in self._gaps.values() if not g.resolved]
            by_severity = {s.value: 0 for s in GapSeverity}
            by_type = {t.value: 0 for t in GapType}
            for g in active:
                by_severity[g.severity.value] += 1
                by_type[g.gap_type.value] += 1

        return {
            "detected_count": self._detected_count,
            "resolved_count": self._resolved_count,
            "active_gaps": len(active),
            "by_severity": by_severity,
            "by_type": by_type,
            "weak_threshold": self._weak_threshold,
            "outdated_days": self._outdated_days,
            "max_gaps": self._max_gaps,
        }

    def __repr__(self) -> str:
        with self._lock:
            active = sum(1 for g in self._gaps.values() if not g.resolved)
        return (
            f"KnowledgeGapDetector("
            f"active={active} | "
            f"detected={self._detected_count} | "
            f"resolved={self._resolved_count})"
        )
