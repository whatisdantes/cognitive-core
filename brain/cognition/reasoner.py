"""
brain/cognition/reasoner.py

Рассуждатель когнитивного ядра (Ring 1 — быстрое мышление).

Содержит:
  - ReasoningStep   — один шаг рассуждения
  - ReasoningTrace  — полный trace reasoning loop
  - Reasoner        — основной reasoning loop

Аналог: префронтальная кора — рабочая память + рассуждение.

Ring 1: retrieve → detect contradictions → hypothesize → score → select.
Integrates: RetrievalAdapter, ContradictionDetector, UncertaintyMonitor.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from brain.core.contracts import ContractMixin
from .context import (
    CognitiveOutcome,
    EvidencePack,
    GoalTypeLimits,
    PolicyConstraints,
    ReasoningState,
)
from .contradiction_detector import ContradictionDetector
from .goal_manager import Goal
from .hypothesis_engine import Hypothesis, HypothesisEngine
from .planner import Planner
from .retrieval_adapter import RetrievalAdapter
from .uncertainty_monitor import UncertaintyMonitor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ReasoningStep — один шаг рассуждения
# ---------------------------------------------------------------------------

@dataclass
class ReasoningStep(ContractMixin):
    """
    Один шаг рассуждения в reasoning loop.

    step_type: "retrieve" | "hypothesize" | "score" | "select"
    duration_ms: время выполнения шага
    """
    step_id: str = ""
    step_type: str = ""
    description: str = ""
    duration_ms: float = 0.0
    input_summary: str = ""
    output_summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.step_id:
            self.step_id = f"rstep_{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# ReasoningTrace — полный trace reasoning loop
# ---------------------------------------------------------------------------

@dataclass
class ReasoningTrace(ContractMixin):
    """
    Полный trace reasoning loop.

    Расширен по сравнению с базовым TraceChain:
      - best_hypothesis_id: ID лучшей гипотезы
      - best_statement:     текст лучшей гипотезы
      - hypothesis_count:   сколько гипотез было сгенерировано
      - evidence_refs:      ID использованных доказательств
      - outcome:            CognitiveOutcome (код завершения)
      - stop_reason:        человекочитаемая причина остановки
      - total_iterations:   сколько итераций reasoning loop
      - final_confidence:   итоговая уверенность
    """
    trace_id: str = ""
    goal_id: str = ""
    query: str = ""
    steps: List[ReasoningStep] = field(default_factory=list)
    best_hypothesis_id: str = ""
    best_statement: str = ""
    hypothesis_count: int = 0
    evidence_refs: List[str] = field(default_factory=list)
    outcome: str = ""  # CognitiveOutcome.value
    stop_reason: str = ""
    total_iterations: int = 0
    final_confidence: float = 0.0
    total_duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.trace_id:
            self.trace_id = f"trace_{uuid.uuid4().hex[:8]}"

    def add_step(self, step: ReasoningStep) -> None:
        """Добавить шаг в trace."""
        self.steps.append(step)

    @property
    def step_count(self) -> int:
        return len(self.steps)


# ---------------------------------------------------------------------------
# Reasoner — основной reasoning loop (Ring 1)
# ---------------------------------------------------------------------------

class Reasoner:
    """
    Ring 1 reasoning loop:
      retrieve → detect contradictions → hypothesize → score → select.

    Зависимости (инъекция через конструктор):
      - memory_manager:         для извлечения фактов
      - hypothesis_engine:      для генерации и оценки гипотез
      - planner:                для check_stop_conditions
      - retrieval_adapter:      для структурированного retrieval (optional)
      - contradiction_detector: для обнаружения противоречий (optional)
      - uncertainty_monitor:    для мониторинга тренда confidence (optional)

    Использование:
        reasoner = Reasoner(
            memory_manager=mm,
            hypothesis_engine=HypothesisEngine(),
            planner=Planner(),
        )
        trace = reasoner.reason(
            query="что такое нейрон?",
            goal=goal,
            policy=PolicyConstraints(),
            resources={},
        )
    """

    def __init__(
        self,
        memory_manager: Any,
        hypothesis_engine: Optional[HypothesisEngine] = None,
        planner: Optional[Planner] = None,
        retrieval_adapter: Optional[RetrievalAdapter] = None,
        contradiction_detector: Optional[ContradictionDetector] = None,
        uncertainty_monitor: Optional[UncertaintyMonitor] = None,
    ) -> None:
        self._memory = memory_manager
        self._hypothesis_engine = hypothesis_engine or HypothesisEngine()
        self._planner = planner or Planner()
        self._retrieval_adapter = retrieval_adapter
        self._contradiction_detector = contradiction_detector or ContradictionDetector()
        self._uncertainty_monitor = uncertainty_monitor or UncertaintyMonitor()

    # ------------------------------------------------------------------
    # Основной метод
    # ------------------------------------------------------------------

    def reason(
        self,
        query: str,
        goal: Goal,
        policy: Optional[PolicyConstraints] = None,
        resources: Optional[Dict[str, Any]] = None,
        query_vector: Optional[List[float]] = None,
    ) -> ReasoningTrace:
        """
        Выполнить reasoning loop для запроса.

        Цикл:
          1. retrieve evidence
          2. generate hypotheses
          3. score hypotheses
          4. select best
          5. check stop conditions → loop or stop

        Возвращает ReasoningTrace с полной информацией.
        """
        if policy is None:
            policy = PolicyConstraints()
        if resources is None:
            resources = {}

        limits = goal.limits
        start_time = time.perf_counter()

        trace = ReasoningTrace(
            goal_id=goal.goal_id,
            query=query,
        )

        state = ReasoningState()

        # Reset uncertainty monitor for this run
        self._uncertainty_monitor.reset()

        # --- Reasoning loop ---
        while True:
            state.iteration += 1

            # 1. Retrieve evidence (via adapter if available)
            evidence = self._retrieve_evidence(query, state, trace, query_vector)

            if not evidence:
                trace.outcome = CognitiveOutcome.RETRIEVAL_FAILED.value
                trace.stop_reason = "Не удалось извлечь доказательства из памяти"
                break

            # 1b. Detect contradictions & flag evidence
            evidence = self._detect_contradictions(evidence, state, trace)

            state.retrieved_evidence = evidence

            # 2. Generate hypotheses
            hypotheses = self._generate_hypotheses(query, evidence, trace)

            if not hypotheses:
                trace.outcome = CognitiveOutcome.NO_HYPOTHESIS_GENERATED.value
                trace.stop_reason = "Не удалось сгенерировать гипотезы"
                break

            # 3. Score hypotheses
            scored = self._score_hypotheses(hypotheses, evidence, trace)

            # 4. Select best
            best = self._select_best(scored, trace)

            if best:
                state.prev_best_score = state.best_score
                state.best_score = best.final_score
                state.current_confidence = best.confidence
                state.top_hypothesis_id = best.hypothesis_id
                state.active_hypotheses = scored

                trace.best_hypothesis_id = best.hypothesis_id
                trace.best_statement = best.statement
                trace.hypothesis_count = len(scored)
                trace.evidence_refs = sorted(
                    set(eid for h in scored for eid in h.evidence_ids)
                )
                trace.final_confidence = best.confidence

            # 4b. Update uncertainty monitor
            uncertainty = self._uncertainty_monitor.update(state)
            trace.metadata["uncertainty_trend"] = uncertainty.trend
            trace.metadata["uncertainty_delta"] = uncertainty.delta

            if uncertainty.should_stop:
                trace.outcome = CognitiveOutcome.INSUFFICIENT_CONFIDENCE.value
                trace.stop_reason = (
                    f"Stagnation detected: confidence={state.current_confidence:.3f} "
                    f"trend={uncertainty.trend}"
                )
                break

            # 5. Check stop conditions
            outcome = self._planner.check_stop_conditions(
                state, limits, resources,
            )

            if outcome is not None:
                trace.outcome = outcome.value
                trace.stop_reason = self._outcome_to_reason(outcome, state)
                break

        # --- Финализация ---
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        trace.total_duration_ms = round(elapsed_ms, 2)
        trace.total_iterations = state.iteration

        # Если outcome не установлен (не должно быть, но на всякий случай)
        if not trace.outcome:
            trace.outcome = CognitiveOutcome.STEP_LIMIT_REACHED.value
            trace.stop_reason = "Reasoning loop завершён без явного outcome"

        logger.info(
            "[Reasoner] reason complete: query='%s' outcome=%s "
            "iterations=%d confidence=%.3f duration=%.1fms",
            query[:50], trace.outcome, trace.total_iterations,
            trace.final_confidence, trace.total_duration_ms,
        )

        return trace

    # ------------------------------------------------------------------
    # Приватные методы — шаги reasoning loop
    # ------------------------------------------------------------------

    def _retrieve_evidence(
        self,
        query: str,
        state: ReasoningState,
        trace: ReasoningTrace,
        query_vector: Optional[List[float]] = None,
    ) -> List[EvidencePack]:
        """
        Извлечь доказательства из памяти.

        Приоритет:
          1. RetrievalAdapter (если доступен) — структурированный retrieval
             с поддержкой гибридного поиска (keyword + vector)
          2. Fallback: прямой memory_manager.search()
        """
        step_start = time.perf_counter()

        evidence: List[EvidencePack] = []

        try:
            # Приоритет 1: RetrievalAdapter (with optional vector)
            if self._retrieval_adapter is not None:
                evidence = self._retrieval_adapter.retrieve(
                    query, top_n=10, query_vector=query_vector,
                )
            # Fallback: прямой memory_manager.search()
            elif hasattr(self._memory, "search"):
                results = self._memory.search(query, top_k=10)

                for i, result in enumerate(results):
                    if hasattr(result, "content"):
                        content = result.content
                        score = getattr(result, "score", 0.5)
                        memory_type = getattr(result, "memory_type", "unknown")
                        memory_id = getattr(result, "memory_id", f"mem_{i}")
                    elif isinstance(result, dict):
                        content = result.get("content", "")
                        score = result.get("score", 0.5)
                        memory_type = result.get("memory_type", "unknown")
                        memory_id = result.get("memory_id", f"mem_{i}")
                    else:
                        content = str(result)
                        score = 0.5
                        memory_type = "unknown"
                        memory_id = f"mem_{i}"

                    ev = EvidencePack(
                        evidence_id=f"ev_{memory_id}",
                        content=content,
                        memory_type=memory_type,
                        confidence=min(1.0, max(0.0, score)),
                        relevance_score=min(1.0, max(0.0, score)),
                        retrieval_stage=state.iteration,
                    )
                    evidence.append(ev)

        except Exception as e:
            logger.warning(
                "[Reasoner] _retrieve_evidence error: %s", str(e)
            )

        step_duration = (time.perf_counter() - step_start) * 1000

        trace.add_step(ReasoningStep(
            step_type="retrieve",
            description=f"Извлечено {len(evidence)} фактов из памяти",
            duration_ms=round(step_duration, 2),
            input_summary=f"query='{query[:80]}'",
            output_summary=f"{len(evidence)} evidence packs",
            metadata={
                "evidence_count": len(evidence),
                "used_adapter": self._retrieval_adapter is not None,
            },
        ))

        return evidence

    def _detect_contradictions(
        self,
        evidence: List[EvidencePack],
        state: ReasoningState,
        trace: ReasoningTrace,
    ) -> List[EvidencePack]:
        """
        Обнаружить противоречия и пометить evidence.

        Copy-on-write: возвращает новые EvidencePack.
        """
        step_start = time.perf_counter()

        contradictions = self._contradiction_detector.detect(evidence)
        flagged = self._contradiction_detector.flag_evidence(
            evidence, contradictions,
        )

        # Update state
        state.contradiction_flags = [
            f"{c.type}:{c.shared_subject}" for c in contradictions
        ]

        step_duration = (time.perf_counter() - step_start) * 1000

        if contradictions:
            trace.add_step(ReasoningStep(
                step_type="contradiction_check",
                description=(
                    f"Обнаружено {len(contradictions)} противоречий"
                ),
                duration_ms=round(step_duration, 2),
                input_summary=f"{len(evidence)} evidence",
                output_summary=", ".join(
                    f"{c.type}:{c.shared_subject}" for c in contradictions
                ),
                metadata={
                    "contradiction_count": len(contradictions),
                    "types": [c.type for c in contradictions],
                },
            ))

        return flagged

    def _generate_hypotheses(
        self,
        query: str,
        evidence: List[EvidencePack],
        trace: ReasoningTrace,
    ) -> List[Hypothesis]:
        """Сгенерировать гипотезы через HypothesisEngine."""
        step_start = time.perf_counter()

        hypotheses = self._hypothesis_engine.generate(query, evidence)

        step_duration = (time.perf_counter() - step_start) * 1000

        trace.add_step(ReasoningStep(
            step_type="hypothesize",
            description=f"Сгенерировано {len(hypotheses)} гипотез",
            duration_ms=round(step_duration, 2),
            input_summary=f"query='{query[:80]}', {len(evidence)} evidence",
            output_summary=", ".join(
                f"[{h.strategy}] {h.statement[:60]}" for h in hypotheses
            ),
            metadata={"hypothesis_count": len(hypotheses)},
        ))

        return hypotheses

    def _score_hypotheses(
        self,
        hypotheses: List[Hypothesis],
        evidence: List[EvidencePack],
        trace: ReasoningTrace,
    ) -> List[Hypothesis]:
        """Оценить и ранжировать гипотезы."""
        step_start = time.perf_counter()

        self._hypothesis_engine.score_all(hypotheses, evidence)
        ranked = self._hypothesis_engine.rank(hypotheses)

        step_duration = (time.perf_counter() - step_start) * 1000

        trace.add_step(ReasoningStep(
            step_type="score",
            description=f"Оценено и ранжировано {len(ranked)} гипотез",
            duration_ms=round(step_duration, 2),
            input_summary=f"{len(hypotheses)} hypotheses",
            output_summary=", ".join(
                f"{h.hypothesis_id}={h.final_score:.3f}" for h in ranked
            ),
            metadata={
                "scores": {
                    h.hypothesis_id: h.final_score for h in ranked
                },
            },
        ))

        return ranked

    def _select_best(
        self,
        ranked_hypotheses: List[Hypothesis],
        trace: ReasoningTrace,
    ) -> Optional[Hypothesis]:
        """Выбрать лучшую гипотезу (первую в ранжированном списке)."""
        step_start = time.perf_counter()

        best = ranked_hypotheses[0] if ranked_hypotheses else None

        step_duration = (time.perf_counter() - step_start) * 1000

        trace.add_step(ReasoningStep(
            step_type="select",
            description=(
                f"Выбрана: {best.statement[:80]}"
                if best else "Нет подходящей гипотезы"
            ),
            duration_ms=round(step_duration, 2),
            input_summary=f"{len(ranked_hypotheses)} ranked hypotheses",
            output_summary=(
                f"best={best.hypothesis_id} score={best.final_score:.3f}"
                if best else "none"
            ),
            metadata={
                "best_id": best.hypothesis_id if best else None,
                "best_score": best.final_score if best else 0.0,
            },
        ))

        return best

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------

    @staticmethod
    def _outcome_to_reason(
        outcome: CognitiveOutcome,
        state: ReasoningState,
    ) -> str:
        """Человекочитаемая причина остановки."""
        reasons = {
            CognitiveOutcome.GOAL_COMPLETED: (
                f"Цель достигнута: confidence={state.current_confidence:.3f}"
            ),
            CognitiveOutcome.STEP_LIMIT_REACHED: (
                f"Лимит итераций: {state.iteration}"
            ),
            CognitiveOutcome.STOP_CONDITION_MET: (
                "Stop condition выполнено"
            ),
            CognitiveOutcome.RETRIEVAL_FAILED: (
                "Не удалось извлечь доказательства"
            ),
            CognitiveOutcome.NO_HYPOTHESIS_GENERATED: (
                "Не удалось сгенерировать гипотезы"
            ),
            CognitiveOutcome.INSUFFICIENT_CONFIDENCE: (
                f"Недостаточная уверенность: {state.current_confidence:.3f}"
            ),
            CognitiveOutcome.RESOURCE_BLOCKED: (
                "Ресурсы исчерпаны"
            ),
        }
        return reasons.get(outcome, f"Unknown outcome: {outcome.value}")
