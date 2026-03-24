"""
brain/cognition/hypothesis_engine.py

Движок гипотез когнитивного ядра.

Содержит:
  - Hypothesis       — dataclass гипотезы
  - HypothesisEngine — генерация, оценка и ранжирование гипотез

Аналог: гиппокамп + префронтальная кора — формирование и оценка
предположений на основе извлечённых фактов.

MVP: 2 стратегии генерации (associative + deductive), max 3 гипотезы,
детерминированный порядок, stable sort.
Causal / Analogical → Stage F.2.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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

class HypothesisEngine:
    """
    Движок гипотез: генерация, оценка и ранжирование.

    MVP:
      - 2 стратегии: associative (по ключевым словам) + deductive (по логике)
      - max_hypotheses = 3
      - Детерминированный порядок (stable sort по final_score desc)
      - Нет causal / analogical (Stage F.2)

    Использование:
        engine = HypothesisEngine()
        hypotheses = engine.generate(query="что такое нейрон?", evidence=[...])
        scored = engine.score_all(hypotheses, evidence)
        ranked = engine.rank(scored)
    """

    def __init__(self, max_hypotheses: int = 3) -> None:
        self.max_hypotheses = max_hypotheses

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

        Стратегии:
          1. Associative — прямое сопоставление: если evidence содержит
             релевантный контент, формируем гипотезу "ответ содержится в X".
          2. Deductive — логический вывод: если несколько evidence
             указывают на одно, формируем обобщающую гипотезу.

        Возвращает до max_hypotheses гипотез.
        """
        if not query or not evidence:
            logger.debug(
                "[HypothesisEngine] generate: пустой query или evidence → []"
            )
            return []

        hypotheses: List[Hypothesis] = []

        # --- Стратегия 1: Associative ---
        assoc = self._generate_associative(query, evidence)
        hypotheses.extend(assoc)

        # --- Стратегия 2: Deductive ---
        deductive = self._generate_deductive(query, evidence)
        hypotheses.extend(deductive)

        # Дедупликация по statement (детерминированный порядок)
        seen_statements: set = set()
        unique: List[Hypothesis] = []
        for h in hypotheses:
            key = h.statement.strip().lower()
            if key not in seen_statements:
                seen_statements.add(key)
                unique.append(h)

        # Ограничить количество
        result = unique[: self.max_hypotheses]

        logger.debug(
            "[HypothesisEngine] generate: query='%s' → %d hypotheses "
            "(from %d assoc + %d deductive)",
            query[:50], len(result), len(assoc), len(deductive),
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

        MVP: простая эвристика — группируем по concept_refs.
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

            ev_ids = sorted(set(e.evidence_id for e in evs))
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
    # Утилиты
    # ------------------------------------------------------------------

    @staticmethod
    def _make_id(prefix: str, seed: str) -> str:
        """Детерминированный ID на основе prefix + seed."""
        digest = hashlib.sha256(f"{prefix}:{seed}".encode()).hexdigest()[:8]
        return f"hyp_{prefix}_{digest}"
