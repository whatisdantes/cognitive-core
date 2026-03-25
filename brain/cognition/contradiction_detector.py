"""
brain/cognition/contradiction_detector.py

Детектор противоречий между доказательствами.

Содержит:
  - Contradiction          — dataclass описания противоречия
  - ContradictionDetector  — обнаружение и пометка противоречий

Контракт F+.2:
  - Противоречие фиксируется ТОЛЬКО между evidence с общим subject
    (concept_refs overlap обязателен).
  - flag_evidence() — copy-on-write: возвращает новые EvidencePack,
    не мутирует оригиналы.
  - Три типа проверок: negation, numeric (>20% diff), confidence_gap (>0.5).
  - _check_numeric() пропускает evidence с >2 числами.

Аналог: передняя поясная кора — мониторинг конфликтов.
"""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from brain.core.contracts import ContractMixin
from .context import EvidencePack

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Negation markers
# ---------------------------------------------------------------------------

_NEGATION_MARKERS_RU = frozenset({
    "не", "нет", "ни", "без", "никогда", "никак", "нельзя",
    "невозможно", "отсутствует", "неверно", "ложно", "опровергнуто",
})

_NEGATION_MARKERS_EN = frozenset({
    "not", "no", "never", "none", "neither", "nor", "cannot",
    "impossible", "false", "incorrect", "wrong", "disproven",
})

_NEGATION_MARKERS = _NEGATION_MARKERS_RU | _NEGATION_MARKERS_EN


# ---------------------------------------------------------------------------
# Contradiction — dataclass описания противоречия
# ---------------------------------------------------------------------------

@dataclass
class Contradiction(ContractMixin):
    """
    Описание противоречия между двумя evidence.

    evidence_a_id:  ID первого evidence
    evidence_b_id:  ID второго evidence
    type:           тип противоречия ("negation" | "numeric" | "confidence_gap")
    severity:       серьёзность [0.0, 1.0]
    description:    человекочитаемое описание
    shared_subject: общий subject (concept из concept_refs overlap)
    """
    evidence_a_id: str = ""
    evidence_b_id: str = ""
    type: str = ""
    severity: float = 0.0
    description: str = ""
    shared_subject: str = ""


# ---------------------------------------------------------------------------
# ContradictionDetector
# ---------------------------------------------------------------------------

class ContradictionDetector:
    """
    Детектор противоречий между доказательствами.

    Проверяет все пары evidence с общим subject (concept_refs overlap).
    Три типа проверок:
      1. Negation — одно evidence отрицает другое
      2. Numeric  — числовые значения расходятся >20%
      3. Confidence gap — разница confidence >0.5

    flag_evidence() — copy-on-write: возвращает новые EvidencePack.
    """

    def __init__(
        self,
        numeric_threshold: float = 0.20,
        confidence_gap_threshold: float = 0.50,
        max_numbers_per_evidence: int = 2,
    ):
        """
        Args:
            numeric_threshold:         порог расхождения чисел (20%)
            confidence_gap_threshold:  порог разницы confidence (0.5)
            max_numbers_per_evidence:  пропустить numeric check если >N чисел
        """
        self._numeric_threshold = numeric_threshold
        self._confidence_gap_threshold = confidence_gap_threshold
        self._max_numbers = max_numbers_per_evidence

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, evidence: List[EvidencePack]) -> List[Contradiction]:
        """
        Обнаружить противоречия между всеми парами evidence.

        Проверяет только пары с общим subject (concept_refs overlap).

        Args:
            evidence: список EvidencePack

        Returns:
            Список обнаруженных Contradiction
        """
        contradictions: List[Contradiction] = []

        if len(evidence) < 2:
            return contradictions

        for i in range(len(evidence)):
            for j in range(i + 1, len(evidence)):
                a = evidence[i]
                b = evidence[j]

                # Обязательное условие: общий subject
                has_shared, subject = self._same_subject(a, b)
                if not has_shared:
                    continue

                # Проверка 1: negation
                c = self._check_negation(a, b, subject)
                if c:
                    contradictions.append(c)

                # Проверка 2: numeric
                c = self._check_numeric(a, b, subject)
                if c:
                    contradictions.append(c)

                # Проверка 3: confidence gap
                c = self._check_confidence_gap(a, b, subject)
                if c:
                    contradictions.append(c)

        if contradictions:
            logger.info(
                "[ContradictionDetector] found %d contradictions in %d evidence",
                len(contradictions), len(evidence),
            )

        return contradictions

    def flag_evidence(
        self,
        evidence: List[EvidencePack],
        contradictions: List[Contradiction],
    ) -> List[EvidencePack]:
        """
        Пометить evidence, участвующие в противоречиях.

        COPY-ON-WRITE: возвращает новые EvidencePack, не мутирует оригиналы.
        Добавляет contradiction type в contradiction_flags.

        Args:
            evidence:       оригинальный список EvidencePack
            contradictions: обнаруженные противоречия

        Returns:
            Новый список EvidencePack (копии с обновлёнными flags)
        """
        if not contradictions:
            # Всё равно возвращаем копии для consistency
            return [copy.deepcopy(ev) for ev in evidence]

        # Собрать флаги для каждого evidence_id
        flags_map: Dict[str, List[str]] = {}
        for c in contradictions:
            flag = f"{c.type}:{c.shared_subject}"
            flags_map.setdefault(c.evidence_a_id, []).append(flag)
            flags_map.setdefault(c.evidence_b_id, []).append(flag)

        # Создать копии с обновлёнными flags
        result = []
        for ev in evidence:
            new_ev = copy.deepcopy(ev)
            extra_flags = flags_map.get(ev.evidence_id, [])
            for f in extra_flags:
                if f not in new_ev.contradiction_flags:
                    new_ev.contradiction_flags.append(f)
            result.append(new_ev)

        return result

    # ------------------------------------------------------------------
    # Subject matching
    # ------------------------------------------------------------------

    def _same_subject(
        self,
        a: EvidencePack,
        b: EvidencePack,
    ) -> Tuple[bool, str]:
        """
        Проверить, есть ли общий subject (concept_refs overlap).

        Returns:
            (True, first_shared_concept) или (False, "")
        """
        refs_a = set(r.lower().strip() for r in a.concept_refs if r)
        refs_b = set(r.lower().strip() for r in b.concept_refs if r)

        overlap = refs_a & refs_b
        if overlap:
            # Берём первый в алфавитном порядке для детерминизма
            subject = sorted(overlap)[0]
            return True, subject

        return False, ""

    # ------------------------------------------------------------------
    # Contradiction checks
    # ------------------------------------------------------------------

    def _check_negation(
        self,
        a: EvidencePack,
        b: EvidencePack,
        subject: str,
    ) -> Optional[Contradiction]:
        """
        Проверить negation: одно evidence содержит маркеры отрицания,
        другое — нет (или оба содержат, но разные).

        Логика: если одно содержит negation markers, а другое нет →
        противоречие.
        """
        words_a = set(re.findall(r'\w+', a.content.lower()))
        words_b = set(re.findall(r'\w+', b.content.lower()))

        neg_a = bool(words_a & _NEGATION_MARKERS)
        neg_b = bool(words_b & _NEGATION_MARKERS)

        if neg_a != neg_b:
            # Одно отрицает, другое утверждает
            severity = 0.8
            return Contradiction(
                evidence_a_id=a.evidence_id,
                evidence_b_id=b.evidence_id,
                type="negation",
                severity=severity,
                description=(
                    f"Negation conflict on '{subject}': "
                    f"one affirms, other negates"
                ),
                shared_subject=subject,
            )

        return None

    def _check_numeric(
        self,
        a: EvidencePack,
        b: EvidencePack,
        subject: str,
    ) -> Optional[Contradiction]:
        """
        Проверить numeric contradiction: числа расходятся >20%.

        Пропускает если в любом evidence >2 чисел (слишком неоднозначно).
        """
        nums_a = self._extract_numbers(a.content)
        nums_b = self._extract_numbers(b.content)

        # Skip if too many numbers (ambiguous)
        if len(nums_a) > self._max_numbers or len(nums_b) > self._max_numbers:
            return None

        if not nums_a or not nums_b:
            return None

        # Сравниваем первое число из каждого evidence
        val_a = nums_a[0]
        val_b = nums_b[0]

        if val_a == 0 and val_b == 0:
            return None

        # Relative difference
        max_val = max(abs(val_a), abs(val_b))
        if max_val == 0:
            return None

        diff = abs(val_a - val_b) / max_val

        if diff > self._numeric_threshold:
            severity = min(1.0, diff)  # cap at 1.0
            return Contradiction(
                evidence_a_id=a.evidence_id,
                evidence_b_id=b.evidence_id,
                type="numeric",
                severity=severity,
                description=(
                    f"Numeric conflict on '{subject}': "
                    f"{val_a} vs {val_b} (diff={diff:.1%})"
                ),
                shared_subject=subject,
            )

        return None

    def _check_confidence_gap(
        self,
        a: EvidencePack,
        b: EvidencePack,
        subject: str,
    ) -> Optional[Contradiction]:
        """
        Проверить confidence gap: разница confidence >0.5.
        """
        gap = abs(a.confidence - b.confidence)

        if gap > self._confidence_gap_threshold:
            severity = min(1.0, gap)
            return Contradiction(
                evidence_a_id=a.evidence_id,
                evidence_b_id=b.evidence_id,
                type="confidence_gap",
                severity=severity,
                description=(
                    f"Confidence gap on '{subject}': "
                    f"{a.confidence:.2f} vs {b.confidence:.2f} (gap={gap:.2f})"
                ),
                shared_subject=subject,
            )

        return None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_numbers(text: str) -> List[float]:
        """
        Извлечь числа из текста.

        Поддерживает целые и дробные числа (с точкой).
        Возвращает список float в порядке появления.
        """
        # Match integers and decimals, but not parts of words
        pattern = r'(?<!\w)[-+]?\d+(?:\.\d+)?(?!\w)'
        matches = re.findall(pattern, text)
        result = []
        for m in matches:
            try:
                result.append(float(m))
            except ValueError:
                continue
        return result
