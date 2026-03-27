"""
brain/cognition/hypothesis_engine.py

Движок гипотез когнитивного ядра.

Содержит:
  - Hypothesis       — dataclass гипотезы
  - HypothesisEngine — генерация, оценка и ранжирование гипотез

Аналог: гиппокамп + префронтальная кора — формирование и оценка
предположений на основе извлечённых фактов.

4 стратегии генерации: associative, deductive, causal, analogical.
Budget: max_hypotheses_total=3, max_per_strategy=2, dedup.
Детерминированный порядок, stable sort.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from brain.core.contracts import ContractMixin

from .context import EvidencePack

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hypothesis — dataclass гипотезы
# ---------------------------------------------------------------------------

@dataclass
class Hypothesis(ContractMixin):
    """
    Гипотеза, сгенерированная на основе доказательств.

    hypothesis_id:  уникальный ID
    statement:      текст гипотезы (человекочитаемый)
    strategy:       стратегия генерации ("associative" | "deductive")
    support_score:  сумма поддержки от доказательств [0..∞)
    risk_score:     сумма рисков / противоречий [0..∞)
    final_score:    support_score - risk_score (может быть отрицательным)
    evidence_ids:   ID доказательств, на которых основана
    confidence:     нормализованная уверенность [0..1]
    metadata:       дополнительные данные
    """
    hypothesis_id: str = ""
    statement: str = ""
    strategy: str = "associative"
    support_score: float = 0.0
    risk_score: float = 0.0
    final_score: float = 0.0
    evidence_ids: List[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.hypothesis_id:
            self.hypothesis_id = f"hyp_{uuid.uuid4().hex[:8]}"
        # Пересчитать final_score
        self.final_score = self.support_score - self.risk_score


# ---------------------------------------------------------------------------
# HypothesisEngine — генерация, оценка и ранжирование
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Causal / temporal markers
# ---------------------------------------------------------------------------

_CAUSAL_MARKERS_RU = frozenset({
    "потому что", "из-за", "вызывает", "приводит к", "следствие",
    "причина", "в результате", "поэтому", "так как", "благодаря",
    "обусловлен", "порождает", "влечёт",
})

_CAUSAL_MARKERS_EN = frozenset({
    "because", "therefore", "causes", "leads to", "due to",
    "as a result", "consequently", "hence", "thus", "since",
    "results in", "owing to",
})

_CAUSAL_MARKERS = _CAUSAL_MARKERS_RU | _CAUSAL_MARKERS_EN


class HypothesisEngine:
    """
    Движок гипотез: генерация, оценка и ранжирование.

    4 стратегии:
      - associative: прямое сопоставление по ключевым словам
      - deductive:   логический вывод из нескольких evidence
      - causal:      причинно-следственные связи (temporal/causal markers)
      - analogical:  кросс-доменные аналогии (разные memory_type/concept_refs)

    Budget:
      - max_hypotheses_total = 3 (глобальный лимит)
      - max_per_strategy = 2 (лимит на стратегию)
      - dedup по normalized statement

    Использование:
        engine = HypothesisEngine()
        hypotheses = engine.generate(query="что такое нейрон?", evidence=[...])
        scored = engine.score_all(hypotheses, evidence)
        ranked = engine.rank(scored)
    """

    def __init__(
        self,
        max_hypotheses: int = 3,
        max_per_strategy: int = 2,
    ) -> None:
        self.max_hypotheses = max_hypotheses
        self.max_per_strategy = max_per_strategy

    # ------------------------------------------------------------------
    # Генерация
    # ------------------------------------------------------------------

    def generate(
        self,
        query: str,
        evidence: List[EvidencePack],
    ) -> List[Hypothesis]:
        """
        Сгенерировать гипотезы на основе запроса и доказательств.

        Стратегии (в порядке приоритета):
          1. Associative — прямое сопоставление
          2. Deductive   — логический вывод из нескольких evidence
          3. Causal      — причинно-следственные связи
          4. Analogical  — кросс-доменные аналогии

        Budget: max_per_strategy=2, max_hypotheses_total=3, dedup.
        """
        if not query or not evidence:
            logger.debug(
                "[HypothesisEngine] generate: пустой query или evidence → []"
            )
            return []

        hypotheses: List[Hypothesis] = []

        # --- Стратегия 1: Associative ---
        assoc = self._generate_associative(query, evidence)
        hypotheses.extend(assoc[:self.max_per_strategy])

        # --- Стратегия 2: Deductive ---
        deductive = self._generate_deductive(query, evidence)
        hypotheses.extend(deductive[:self.max_per_strategy])

        # --- Стратегия 3: Causal ---
        causal = self._generate_causal(query, evidence)
        hypotheses.extend(causal[:self.max_per_strategy])

        # --- Стратегия 4: Analogical ---
        analogical = self._generate_analogical(query, evidence)
        hypotheses.extend(analogical[:self.max_per_strategy])

        # Дедупликация по normalized statement
        unique = self._deduplicate(hypotheses)

        # Ограничить количество (global budget)
        result = unique[:self.max_hypotheses]

        logger.debug(
            "[HypothesisEngine] generate: query='%s' → %d hypotheses "
            "(assoc=%d deduct=%d causal=%d analog=%d)",
            query[:50], len(result),
            len(assoc), len(deductive), len(causal), len(analogical),
        )
        return result

    def _generate_associative(
        self,
        query: str,
        evidence: List[EvidencePack],
    ) -> List[Hypothesis]:
        """
        Associative: для каждого evidence с непустым content
        формируем гипотезу "ответ содержится в данном факте".

        Сортируем по relevance_score (desc) для детерминированности.
        """
        hypotheses: List[Hypothesis] = []

        # Сортируем evidence по relevance_score desc, затем по evidence_id (stable)
        sorted_ev = sorted(
            evidence,
            key=lambda e: (-e.relevance_score, e.evidence_id),
        )

        for ev in sorted_ev:
            if not ev.content.strip():
                continue

            # Формируем statement
            content_preview = ev.content.strip()[:200]
            statement = f"Ответ основан на факте: «{content_preview}»"

            h = Hypothesis(
                hypothesis_id=self._make_id("assoc", ev.evidence_id),
                statement=statement,
                strategy="associative",
                support_score=ev.relevance_score * ev.confidence,
                risk_score=len(ev.contradiction_flags) * 0.2,
                evidence_ids=[ev.evidence_id],
                metadata={
                    "source_evidence": ev.evidence_id,
                    "memory_type": ev.memory_type,
                },
            )
            h.final_score = h.support_score - h.risk_score
            hypotheses.append(h)

        return hypotheses

    def _generate_deductive(
        self,
        query: str,
        evidence: List[EvidencePack],
    ) -> List[Hypothesis]:
        """
        Deductive: если ≥2 evidence указывают на общую тему,
        формируем обобщающую гипотезу.

        Группируем по concept_refs.
        """
        if len(evidence) < 2:
            return []

        # Собираем concept_refs → evidence_ids
        concept_to_evidence: Dict[str, List[EvidencePack]] = {}
        for ev in evidence:
            for concept in ev.concept_refs:
                concept_lower = concept.strip().lower()
                if concept_lower:
                    if concept_lower not in concept_to_evidence:
                        concept_to_evidence[concept_lower] = []
                    concept_to_evidence[concept_lower].append(ev)

        hypotheses: List[Hypothesis] = []

        # Для каждого concept с ≥2 evidence — обобщающая гипотеза
        for concept, evs in sorted(concept_to_evidence.items()):
            if len(evs) < 2:
                continue

            ev_ids = sorted({e.evidence_id for e in evs})
            avg_confidence = sum(e.confidence for e in evs) / len(evs)
            avg_relevance = sum(e.relevance_score for e in evs) / len(evs)
            total_contradictions = sum(
                len(e.contradiction_flags) for e in evs
            )

            statement = (
                f"Несколько источников ({len(evs)}) подтверждают "
                f"связь с концептом «{concept}»"
            )

            h = Hypothesis(
                hypothesis_id=self._make_id("deduct", concept),
                statement=statement,
                strategy="deductive",
                support_score=avg_relevance * avg_confidence * len(evs),
                risk_score=total_contradictions * 0.15,
                evidence_ids=ev_ids,
                metadata={
                    "concept": concept,
                    "evidence_count": len(evs),
                },
            )
            h.final_score = h.support_score - h.risk_score
            hypotheses.append(h)

        return hypotheses

    def _generate_causal(
        self,
        query: str,
        evidence: List[EvidencePack],
    ) -> List[Hypothesis]:
        """
        Causal: причинно-следственные связи.

        Требования:
          - ≥2 evidence с causal/temporal markers
          - Общий concept (concept_refs overlap)
          - strategy="causal"
        """
        if len(evidence) < 2:
            return []

        # Найти evidence с causal markers
        causal_evidence: List[EvidencePack] = []
        for ev in evidence:
            if self._has_causal_markers(ev.content):
                causal_evidence.append(ev)

        if len(causal_evidence) < 2:
            return []

        # Группируем по общим concept_refs
        concept_to_causal: Dict[str, List[EvidencePack]] = {}
        for ev in causal_evidence:
            for concept in ev.concept_refs:
                concept_lower = concept.strip().lower()
                if concept_lower:
                    concept_to_causal.setdefault(concept_lower, []).append(ev)

        hypotheses: List[Hypothesis] = []

        for concept, evs in sorted(concept_to_causal.items()):
            if len(evs) < 2:
                continue

            ev_ids = sorted({e.evidence_id for e in evs})
            avg_confidence = sum(e.confidence for e in evs) / len(evs)
            avg_relevance = sum(e.relevance_score for e in evs) / len(evs)

            statement = (
                f"Причинно-следственная связь: {len(evs)} источников "
                f"указывают на каузальную связь с «{concept}»"
            )

            h = Hypothesis(
                hypothesis_id=self._make_id("causal", concept),
                statement=statement,
                strategy="causal",
                support_score=avg_relevance * avg_confidence * len(evs) * 1.1,
                risk_score=sum(len(e.contradiction_flags) for e in evs) * 0.15,
                evidence_ids=ev_ids,
                metadata={
                    "concept": concept,
                    "evidence_count": len(evs),
                    "causal_markers_found": True,
                },
            )
            h.final_score = h.support_score - h.risk_score
            hypotheses.append(h)

        return hypotheses

    def _generate_analogical(
        self,
        query: str,
        evidence: List[EvidencePack],
    ) -> List[Hypothesis]:
        """
        Analogical: кросс-доменные аналогии.

        Требования:
          - ≥2 evidence из разных доменов (разные memory_type ИЛИ
            непересекающиеся concept_refs)
          - strategy="analogical"
        """
        if len(evidence) < 2:
            return []

        hypotheses: List[Hypothesis] = []

        # Ищем пары из разных доменов
        for i in range(len(evidence)):
            for j in range(i + 1, len(evidence)):
                a = evidence[i]
                b = evidence[j]

                if not self._is_cross_domain(a, b):
                    continue

                # Формируем аналогию
                ev_ids = sorted([a.evidence_id, b.evidence_id])
                avg_confidence = (a.confidence + b.confidence) / 2
                avg_relevance = (a.relevance_score + b.relevance_score) / 2

                # Описание аналогии
                domain_a = a.memory_type or "unknown"
                domain_b = b.memory_type or "unknown"
                content_a = a.content[:60].strip()
                content_b = b.content[:60].strip()

                statement = (
                    f"Аналогия между доменами ({domain_a}/{domain_b}): "
                    f"«{content_a}» ↔ «{content_b}»"
                )

                h = Hypothesis(
                    hypothesis_id=self._make_id(
                        "analog", f"{a.evidence_id}:{b.evidence_id}"
                    ),
                    statement=statement,
                    strategy="analogical",
                    support_score=avg_relevance * avg_confidence * 0.9,
                    risk_score=(
                        len(a.contradiction_flags) + len(b.contradiction_flags)
                    ) * 0.15,
                    evidence_ids=ev_ids,
                    metadata={
                        "domain_a": domain_a,
                        "domain_b": domain_b,
                    },
                )
                h.final_score = h.support_score - h.risk_score
                hypotheses.append(h)

        return hypotheses

    # ------------------------------------------------------------------
    # Оценка
    # ------------------------------------------------------------------

    def score(
        self,
        hypothesis: Hypothesis,
        evidence: List[EvidencePack],
    ) -> float:
        """
        Оценить одну гипотезу по доказательствам.

        Формула: support - risk
          support = Σ(relevance * confidence) для связанных evidence
          risk    = Σ(contradiction_count * 0.2) для связанных evidence

        Возвращает final_score (может быть отрицательным).
        """
        support = 0.0
        risk = 0.0

        ev_map = {e.evidence_id: e for e in evidence}

        for eid in hypothesis.evidence_ids:
            ev = ev_map.get(eid)
            if ev:
                support += ev.relevance_score * ev.confidence
                risk += len(ev.contradiction_flags) * 0.2

        hypothesis.support_score = support
        hypothesis.risk_score = risk
        hypothesis.final_score = support - risk

        # Нормализованная confidence [0..1]
        if support > 0:
            hypothesis.confidence = min(1.0, support / (support + risk + 0.01))
        else:
            hypothesis.confidence = 0.0

        return hypothesis.final_score

    def score_all(
        self,
        hypotheses: List[Hypothesis],
        evidence: List[EvidencePack],
    ) -> List[Hypothesis]:
        """Оценить все гипотезы. Возвращает тот же список (мутирует)."""
        for h in hypotheses:
            self.score(h, evidence)
        return hypotheses

    # ------------------------------------------------------------------
    # Ранжирование
    # ------------------------------------------------------------------

    def rank(self, hypotheses: List[Hypothesis]) -> List[Hypothesis]:
        """
        Ранжировать гипотезы по final_score (desc).
        Stable sort: при равном score — порядок сохраняется.
        """
        return sorted(
            hypotheses,
            key=lambda h: (-h.final_score, h.hypothesis_id),
        )

    # ------------------------------------------------------------------
    # Dedup & utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(hypotheses: List[Hypothesis]) -> List[Hypothesis]:
        """
        Дедупликация по normalized statement.
        Сохраняет первое вхождение (порядок стратегий = приоритет).
        """
        seen: Set[str] = set()
        unique: List[Hypothesis] = []
        for h in hypotheses:
            key = h.statement.strip().lower()
            if key not in seen:
                seen.add(key)
                unique.append(h)
        return unique

    @staticmethod
    def _has_causal_markers(text: str) -> bool:
        """Проверить наличие causal/temporal markers в тексте."""
        text_lower = text.lower()
        for marker in _CAUSAL_MARKERS:
            if marker in text_lower:
                return True
        return False

    @staticmethod
    def _is_cross_domain(a: EvidencePack, b: EvidencePack) -> bool:
        """
        Проверить, что два evidence из разных доменов.

        Критерии (любой из):
          1. Разные memory_type
          2. Непересекающиеся concept_refs (оба непустые)
        """
        # Разные memory_type
        if a.memory_type and b.memory_type and a.memory_type != b.memory_type:
            return True

        # Непересекающиеся concept_refs
        refs_a = {r.lower().strip() for r in a.concept_refs if r}
        refs_b = {r.lower().strip() for r in b.concept_refs if r}
        if refs_a and refs_b and not (refs_a & refs_b):
            return True

        return False

    @staticmethod
    def _make_id(prefix: str, seed: str) -> str:
        """Детерминированный ID на основе prefix + seed."""
        digest = hashlib.sha256(f"{prefix}:{seed}".encode()).hexdigest()[:8]
        return f"hyp_{prefix}_{digest}"
