"""
brain/cognition/salience_engine.py

Движок оценки значимости стимула (аналог Миндалины — Amygdala).

Этап H: Attention & Resource Control.

SalienceEngine вычисляет многомерную оценку значимости входящего стимула
по четырём осям:
  - novelty    (0.25) — насколько стимул нов относительно рабочей памяти
  - urgency    (0.35) — содержит ли стимул маркеры срочности
  - threat     (0.25) — содержит ли стимул маркеры угрозы/ошибки
  - relevance  (0.15) — насколько стимул релевантен активной цели

Итоговый overall = взвешенная сумма четырёх осей.

Пороги действия:
  overall >= 0.8 → "interrupt"   — прервать текущий процесс
  overall >= 0.5 → "prioritize"  — повысить приоритет
  иначе          → "normal"      — обычная обработка

Примечание v1: urgency и threat — бинарное keyword matching (0.0 или 1.0).
Планируется v2: graduated scoring по количеству и весу маркеров.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from brain.core.contracts import ContractMixin

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SalienceScore — результат оценки значимости
# ---------------------------------------------------------------------------


@dataclass
class SalienceScore(ContractMixin):
    """
    Многомерная оценка значимости стимула.

    Атрибуты:
        overall   — итоговая взвешенная оценка [0.0, 1.0]
        novelty   — новизна относительно рабочей памяти [0.0, 1.0]
        urgency   — маркеры срочности [0.0, 1.0]
        threat    — маркеры угрозы/ошибки [0.0, 1.0]
        relevance — релевантность активной цели [0.0, 1.0]
        action    — рекомендуемое действие: "interrupt" | "prioritize" | "normal"
        reason    — текстовое объяснение оценки
    """

    overall: float = 0.0
    novelty: float = 0.0
    urgency: float = 0.0
    threat: float = 0.0
    relevance: float = 0.0
    action: str = "normal"
    reason: str = ""


# ---------------------------------------------------------------------------
# SalienceEngine — движок оценки значимости
# ---------------------------------------------------------------------------


class SalienceEngine:
    """
    Движок оценки значимости входящего стимула.

    Аналог Миндалины (Amygdala) — быстрая оценка эмоциональной значимости
    до полного когнитивного анализа.

    Вызывается в пайплайне ПОСЛЕ create_goal (шаг 6), чтобы relevance
    мог использовать active_goal.description.

    Использование:
        engine = SalienceEngine()
        score = engine.evaluate(
            stimulus="срочно! ошибка в базе данных",
            active_goal=goal,
        )
        # score.action == "interrupt"
        # score.overall >= 0.8
    """

    # --- Ключевые слова срочности (urgency) ---
    URGENCY_KEYWORDS: frozenset = frozenset({
        "срочно", "немедленно", "сейчас", "экстренно", "критично",
        "urgent", "asap", "immediately", "now", "critical",
    })

    # --- Ключевые слова угрозы/ошибки (threat) ---
    THREAT_KEYWORDS: frozenset = frozenset({
        "ошибка", "опасность", "сбой", "авария", "критическая", "угроза",
        "error", "fail", "failure", "danger", "crash", "threat",
    })

    # --- Веса осей (сумма = 1.0) ---
    W_NOVELTY: float = 0.25
    W_URGENCY: float = 0.35
    W_THREAT: float = 0.25
    W_RELEVANCE: float = 0.15

    # --- Пороги действия ---
    INTERRUPT_THRESHOLD: float = 0.8
    PRIORITIZE_THRESHOLD: float = 0.5

    def evaluate(
        self,
        stimulus: str,
        working_memory: Optional[Any] = None,
        active_goal: Optional[Any] = None,
    ) -> SalienceScore:
        """
        Вычислить оценку значимости стимула.

        Args:
            stimulus:       входящий текстовый стимул
            working_memory: рабочая память (для вычисления novelty)
            active_goal:    активная цель (для вычисления relevance)

        Returns:
            SalienceScore с overall, компонентами и рекомендуемым действием.
        """
        novelty = self._compute_novelty(stimulus, working_memory)
        urgency = self._compute_urgency(stimulus)
        threat = self._compute_threat(stimulus)
        relevance = self._compute_relevance(stimulus, active_goal)

        overall = min(1.0, (
            self.W_NOVELTY * novelty
            + self.W_URGENCY * urgency
            + self.W_THREAT * threat
            + self.W_RELEVANCE * relevance
        ))

        if overall >= self.INTERRUPT_THRESHOLD:
            action = "interrupt"
        elif overall >= self.PRIORITIZE_THRESHOLD:
            action = "prioritize"
        else:
            action = "normal"

        reason = (
            f"novelty={novelty:.2f} urgency={urgency:.2f} "
            f"threat={threat:.2f} relevance={relevance:.2f}"
        )

        score = SalienceScore(
            overall=round(overall, 4),
            novelty=round(novelty, 4),
            urgency=round(urgency, 4),
            threat=round(threat, 4),
            relevance=round(relevance, 4),
            action=action,
            reason=reason,
        )

        logger.debug(
            "[SalienceEngine] stimulus='%s...' overall=%.3f action=%s",
            stimulus[:40],
            overall,
            action,
        )

        return score

    # ------------------------------------------------------------------
    # Вычисление компонентов
    # ------------------------------------------------------------------

    def _compute_novelty(
        self,
        stimulus: str,
        working_memory: Optional[Any] = None,
    ) -> float:
        """
        Новизна стимула относительно рабочей памяти.

        Метрика: 1.0 - max_jaccard_overlap(stimulus, working_memory_items).
        Fallback: 1.0 (полная новизна) если рабочая память недоступна.
        """
        if working_memory is None:
            return 1.0

        try:
            if hasattr(working_memory, "get_context"):
                items = working_memory.get_context(n=10)
            elif hasattr(working_memory, "get_all"):
                items = working_memory.get_all()
            else:
                return 1.0

            if not items:
                return 1.0

            stim_words = set(stimulus.lower().split())
            if not stim_words:
                return 1.0

            max_overlap = 0.0
            for item in items:
                content = getattr(item, "content", None) or str(item)
                item_words = set(content.lower().split())
                if item_words:
                    union = stim_words | item_words
                    intersection = stim_words & item_words
                    overlap = len(intersection) / len(union)
                    max_overlap = max(max_overlap, overlap)

            return round(1.0 - max_overlap, 4)

        except Exception as exc:
            logger.debug("[SalienceEngine] _compute_novelty error: %s", exc)
            return 0.5

    def _compute_urgency(self, stimulus: str) -> float:
        """
        Наличие маркеров срочности в стимуле.

        v1: бинарное keyword matching (0.0 или 1.0).
        Планируется v2: graduated scoring по количеству маркеров.
        """
        s_lower = stimulus.lower()
        return 1.0 if any(kw in s_lower for kw in self.URGENCY_KEYWORDS) else 0.0

    def _compute_threat(self, stimulus: str) -> float:
        """
        Наличие маркеров угрозы/ошибки в стимуле.

        v1: бинарное keyword matching (0.0 или 1.0).
        Планируется v2: graduated scoring по количеству маркеров.
        """
        s_lower = stimulus.lower()
        return 1.0 if any(kw in s_lower for kw in self.THREAT_KEYWORDS) else 0.0

    def _compute_relevance(
        self,
        stimulus: str,
        active_goal: Optional[Any] = None,
    ) -> float:
        """
        Релевантность стимула активной цели.

        Метрика: Jaccard overlap × 3.0 (масштабирование, т.к. Jaccard мал
        для коротких текстов), clamp [0.0, 1.0].
        Fallback: 0.5 если цель недоступна.

        Примечание: вызывается ПОСЛЕ create_goal в пайплайне,
        поэтому active_goal доступен при нормальном flow.
        """
        if active_goal is None:
            return 0.5

        goal_desc = getattr(active_goal, "description", "") or ""
        if not goal_desc:
            return 0.5

        stim_words = set(stimulus.lower().split())
        goal_words = set(goal_desc.lower().split())

        if not stim_words or not goal_words:
            return 0.5

        union = stim_words | goal_words
        intersection = stim_words & goal_words
        if not union:
            return 0.5

        jaccard = len(intersection) / len(union)
        return min(1.0, jaccard * 3.0)
