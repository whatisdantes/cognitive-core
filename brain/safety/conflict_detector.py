"""
brain/safety/conflict_detector.py — Обнаружение конфликтов между фактами.

Работает с SemanticNode (не EvidencePack). O(n²) попарное сравнение.
Три типа конфликтов:
  - negation:     одно описание содержит отрицание другого → severity='high'
  - numeric:      числовые значения в описаниях различаются → severity='medium'
  - source_trust: разница confidence источников >threshold → severity='low'

Приоритет: negation > numeric > source_trust.

Использование:
    cd = ConflictDetector()
    conflicts = cd.detect(semantic_nodes)
    pair_conflict = cd.detect_pair(node_a, node_b)
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from brain.memory.semantic_memory import SemanticNode
from brain.safety.source_trust import SourceTrustManager

# ─── Паттерны отрицания ──────────────────────────────────────────────────────

_NEGATION_RU = re.compile(
    r"\bне\b|\bнет\b|\bникогда\b|\bневозможно\b|\bнельзя\b",
    re.IGNORECASE,
)
_NEGATION_EN = re.compile(
    r"\bnot\b|\bno\b|\bnever\b|\bimpossible\b|\bcannot\b|\bcan't\b",
    re.IGNORECASE,
)

# ─── Паттерн чисел ───────────────────────────────────────────────────────────

_NUMBERS = re.compile(r"\d+(?:[.,]\d+)?")


def _has_negation(text: str) -> bool:
    """True если текст содержит маркер отрицания (RU или EN)."""
    return bool(_NEGATION_RU.search(text) or _NEGATION_EN.search(text))


def _extract_numbers(text: str) -> set[float]:
    """Извлечь все числа из текста."""
    return {float(n.replace(",", ".")) for n in _NUMBERS.findall(text)}


# ─── Dataclass ───────────────────────────────────────────────────────────────


@dataclass
class Conflict:
    """Обнаруженный конфликт между двумя фактами."""

    conflict_id: str
    fact_a_id: str        # concept узла A
    fact_b_id: str        # concept узла B (обычно совпадает с A)
    fact_a_content: str   # description узла A
    fact_b_content: str   # description узла B
    severity: str         # "high" | "medium" | "low"
    conflict_type: str    # "negation" | "numeric" | "source_trust"
    description: str      # человекочитаемое описание конфликта
    detected_at: str      # ISO timestamp


# ─── ConflictDetector ────────────────────────────────────────────────────────


class ConflictDetector:
    """
    Детектор конфликтов между SemanticNode.

    Параметры:
        trust_gap_threshold — порог разницы confidence для source_trust конфликта
        trust_manager       — опциональный SourceTrustManager для проверки source_refs
    """

    def __init__(
        self,
        trust_gap_threshold: float = 0.40,
        trust_manager: Optional[SourceTrustManager] = None,
    ) -> None:
        self._trust_gap_threshold = trust_gap_threshold
        self._trust_manager = trust_manager

    def detect(self, facts: List[SemanticNode]) -> List[Conflict]:
        """
        Обнаружить конфликты в списке фактов.

        Группирует по concept, сравнивает попарно O(n²).
        Returns: список Conflict (может быть пустым).
        """
        if len(facts) < 2:
            return []

        # Группировка по concept
        by_concept: dict[str, list[SemanticNode]] = {}
        for node in facts:
            by_concept.setdefault(node.concept, []).append(node)

        conflicts: List[Conflict] = []
        for nodes in by_concept.values():
            if len(nodes) < 2:
                continue
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    conflict = self.detect_pair(nodes[i], nodes[j])
                    if conflict is not None:
                        conflicts.append(conflict)

        return conflicts

    def detect_pair(
        self, a: SemanticNode, b: SemanticNode
    ) -> Optional[Conflict]:
        """
        Проверить пару фактов на конфликт.

        Возвращает Conflict или None.
        Приоритет: negation > numeric > source_trust.
        Факты с разными concept не конфликтуют.
        """
        if a.concept != b.concept:
            return None

        desc_a = a.description
        desc_b = b.description

        # 1. Negation (highest priority, severity=high)
        neg_a = _has_negation(desc_a)
        neg_b = _has_negation(desc_b)
        if neg_a != neg_b:
            return self._make_conflict(
                a, b,
                conflict_type="negation",
                severity="high",
                description=(
                    f"Negation conflict: '{desc_a[:60]}' vs '{desc_b[:60]}'"
                ),
            )

        # 2. Numeric (medium priority, severity=medium)
        nums_a = _extract_numbers(desc_a)
        nums_b = _extract_numbers(desc_b)
        if nums_a and nums_b and nums_a != nums_b:
            return self._make_conflict(
                a, b,
                conflict_type="numeric",
                severity="medium",
                description=(
                    f"Numeric conflict: {nums_a} vs {nums_b} in '{a.concept}'"
                ),
            )

        # 3. Source trust (lowest priority, severity=low)
        trust_gap = self._compute_trust_gap(a, b)
        if trust_gap > self._trust_gap_threshold:
            return self._make_conflict(
                a, b,
                conflict_type="source_trust",
                severity="low",
                description=(
                    f"Source trust gap {trust_gap:.2f} > {self._trust_gap_threshold} "
                    f"for '{a.concept}'"
                ),
            )

        return None

    def _compute_trust_gap(self, a: SemanticNode, b: SemanticNode) -> float:
        """
        Вычислить разницу доверия между двумя фактами.

        Если есть SourceTrustManager и source_refs — использует его.
        Иначе — разница confidence как прокси.
        """
        if self._trust_manager is not None and (a.source_refs or b.source_refs):
            trust_a = max(
                (self._trust_manager.get_score(ref).trust for ref in a.source_refs),
                default=a.confidence,
            )
            trust_b = max(
                (self._trust_manager.get_score(ref).trust for ref in b.source_refs),
                default=b.confidence,
            )
            return abs(trust_a - trust_b)

        # Fallback: confidence gap
        return abs(a.confidence - b.confidence)

    def _make_conflict(
        self,
        a: SemanticNode,
        b: SemanticNode,
        conflict_type: str,
        severity: str,
        description: str,
    ) -> Conflict:
        return Conflict(
            conflict_id=str(uuid.uuid4()),
            fact_a_id=a.concept,
            fact_b_id=b.concept,
            fact_a_content=a.description,
            fact_b_content=b.description,
            severity=severity,
            conflict_type=conflict_type,
            description=description,
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
