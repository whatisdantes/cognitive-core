"""
brain/output/trace_builder.py

Output Trace Builder — построитель объяснимого trace для output layer.

Содержит:
  - ExplainabilityTrace  — минимальный набор полей для объяснимости
  - OutputTraceBuilder   — конвертация CognitiveResult → ExplainabilityTrace

Аналог: угловая извилина — интеграция всех источников в единый смысл.

Работает поверх brain/logging/trace_builder.py (низкоуровневый trace chain).
Добавляет слой объяснимости: что спросили, как рассуждали, почему так решили.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from brain.core.contracts import (
    CognitiveResult,
    ContractMixin,
    TraceRef,
)


# ---------------------------------------------------------------------------
# ExplainabilityTrace — минимальный набор полей для объяснимости
# ---------------------------------------------------------------------------

@dataclass
class ExplainabilityTrace(ContractMixin):
    """
    Структурированный объект объяснимости для output layer.

    Минимальный набор полей (без дублирования TraceChain):
      - Идентификаторы: trace_id, session_id, cycle_id
      - Вход: input_query
      - Рассуждение: reasoning_type, key_inferences
      - Решение: action_taken, confidence
      - Качество: uncertainty_level, uncertainty_reasons, contradictions_found
      - Источники: memory_facts (List[TraceRef])
      - Метаданные: total_duration_ms, created_at, metadata

    reasoning_chain и alternatives_considered — опциональные (в metadata).
    """
    # Идентификаторы
    trace_id: str = ""
    session_id: str = ""
    cycle_id: str = ""

    # Вход
    input_query: str = ""

    # Рассуждение
    reasoning_type: str = ""
    key_inferences: List[str] = field(default_factory=list)

    # Решение
    action_taken: str = ""
    confidence: float = 0.0

    # Качество
    uncertainty_level: str = "unknown"
    uncertainty_reasons: List[str] = field(default_factory=list)
    contradictions_found: List[str] = field(default_factory=list)

    # Источники
    memory_facts: List[TraceRef] = field(default_factory=list)

    # Производительность
    total_duration_ms: float = 0.0
    created_at: str = ""

    # Расширяемые данные (reasoning_chain, alternatives и т.д.)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# OutputTraceBuilder — конвертация CognitiveResult → ExplainabilityTrace
# ---------------------------------------------------------------------------

class OutputTraceBuilder:
    """
    Построитель объяснимого trace из CognitiveResult.

    Использование:
        builder = OutputTraceBuilder()
        trace = builder.build(cognitive_result)
        digest = builder.to_digest(trace)
        data = builder.to_json(trace)
    """

    def build(self, result: CognitiveResult) -> ExplainabilityTrace:
        """
        Конвертировать CognitiveResult → ExplainabilityTrace.

        Извлекает данные из CognitiveResult.metadata, trace, memory_refs.
        """
        meta = result.metadata or {}

        # --- Reasoning type ---
        reasoning_type = meta.get("goal_type", "unknown")

        # --- Key inferences из trace steps ---
        key_inferences = self._extract_inferences(result)

        # --- Uncertainty level ---
        uncertainty_level = self._compute_uncertainty_level(result.confidence)

        # --- Uncertainty reasons ---
        uncertainty_reasons = self._compute_uncertainty_reasons(result)

        # --- Contradictions ---
        contradictions = list(result.contradictions) if result.contradictions else []

        # --- Memory facts ---
        memory_facts = list(result.memory_refs) if result.memory_refs else []

        # --- Duration ---
        total_duration_ms = meta.get("total_duration_ms", 0.0)

        # --- Metadata (расширяемые данные) ---
        trace_metadata: Dict[str, Any] = {}

        # reasoning_chain из trace steps (опционально)
        reasoning_chain = self._extract_reasoning_chain(result)
        if reasoning_chain:
            trace_metadata["reasoning_chain"] = reasoning_chain

        # hypothesis info
        if meta.get("hypothesis_count"):
            trace_metadata["hypothesis_count"] = meta["hypothesis_count"]
        if meta.get("best_hypothesis_id"):
            trace_metadata["best_hypothesis_id"] = meta["best_hypothesis_id"]

        # outcome info
        if meta.get("outcome"):
            trace_metadata["outcome"] = meta["outcome"]
        if meta.get("stop_reason"):
            trace_metadata["stop_reason"] = meta["stop_reason"]

        # iterations
        if meta.get("total_iterations"):
            trace_metadata["total_iterations"] = meta["total_iterations"]

        return ExplainabilityTrace(
            trace_id=result.trace_id,
            session_id=result.session_id,
            cycle_id=result.cycle_id,
            input_query=result.goal or "",
            reasoning_type=reasoning_type,
            key_inferences=key_inferences,
            action_taken=result.action,
            confidence=result.confidence,
            uncertainty_level=uncertainty_level,
            uncertainty_reasons=uncertainty_reasons,
            contradictions_found=contradictions,
            memory_facts=memory_facts,
            total_duration_ms=total_duration_ms,
            metadata=trace_metadata,
        )

    def to_digest(self, trace: ExplainabilityTrace) -> str:
        """
        Форматировать ExplainabilityTrace в человекочитаемый digest.

        Формат:
            Cycle <cycle_id>
              Query:        "<input_query>"
              Reasoning:    <reasoning_type> [<key_inferences>]
              Memory used:  <memory_facts>
              Confidence:   <confidence> (<uncertainty_level>)
              Action:       <action_taken>
              Duration:     <total_duration_ms>ms
        """
        lines: List[str] = []
        sep = "─" * 50

        lines.append(sep)

        # Cycle header
        cycle = trace.cycle_id or trace.trace_id or "unknown"
        lines.append(f"Cycle {cycle}")

        # Query
        query = trace.input_query or "(no query)"
        if len(query) > 80:
            query = query[:77] + "..."
        lines.append(f'  Query:        "{query}"')

        # Reasoning
        reasoning_parts = [trace.reasoning_type or "unknown"]
        if trace.key_inferences:
            inferences_str = " → ".join(trace.key_inferences[:5])
            reasoning_parts.append(f"[{inferences_str}]")
        lines.append(f"  Reasoning:    {' '.join(reasoning_parts)}")

        # Memory used
        if trace.memory_facts:
            mem_strs = []
            for ref in trace.memory_facts[:5]:
                note = f" ({ref.note})" if ref.note else ""
                mem_strs.append(f"{ref.ref_type}:{ref.ref_id}{note}")
            lines.append(f"  Memory used:  {', '.join(mem_strs)}")
        else:
            lines.append("  Memory used:  (none)")

        # Contradictions
        if trace.contradictions_found:
            lines.append(
                f"  Contradictions: {', '.join(trace.contradictions_found[:3])}"
            )

        # Confidence + uncertainty
        conf_pct = f"{trace.confidence:.0%}"
        lines.append(
            f"  Confidence:   {trace.confidence:.3f} ({conf_pct}, "
            f"{trace.uncertainty_level})"
        )

        # Uncertainty reasons
        if trace.uncertainty_reasons:
            reasons_str = ", ".join(trace.uncertainty_reasons[:3])
            lines.append(f"  Uncertainty:  {reasons_str}")

        # Action
        lines.append(f"  Action:       {trace.action_taken}")

        # Duration
        if trace.total_duration_ms > 0:
            lines.append(f"  Duration:     {trace.total_duration_ms:.1f}ms")

        lines.append(sep)
        return "\n".join(lines)

    def to_json(self, trace: ExplainabilityTrace) -> Dict[str, Any]:
        """
        Конвертировать ExplainabilityTrace в machine-readable dict.

        Использует to_dict() из ContractMixin + добавляет
        вычисляемые поля.
        """
        data = trace.to_dict()
        # Добавляем вычисляемые поля для удобства потребителей
        data["confidence_pct"] = round(trace.confidence * 100, 1)
        data["has_contradictions"] = len(trace.contradictions_found) > 0
        data["memory_count"] = len(trace.memory_facts)
        data["inference_count"] = len(trace.key_inferences)
        return data

    # ------------------------------------------------------------------
    # Приватные методы
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_uncertainty_level(confidence: float) -> str:
        """
        Вычислить уровень неопределённости по confidence.

        Шкала:
          confidence ≥ 0.85 → "very_low"
          confidence ≥ 0.65 → "low"
          confidence ≥ 0.45 → "medium"
          confidence ≥ 0.25 → "high"
          confidence < 0.25 → "very_high"
        """
        if confidence >= 0.85:
            return "very_low"
        if confidence >= 0.65:
            return "low"
        if confidence >= 0.45:
            return "medium"
        if confidence >= 0.25:
            return "high"
        return "very_high"

    @staticmethod
    def _compute_uncertainty_reasons(result: CognitiveResult) -> List[str]:
        """Вычислить причины неопределённости."""
        reasons: List[str] = []
        meta = result.metadata or {}

        # Мало гипотез
        hyp_count = meta.get("hypothesis_count", 0)
        if hyp_count == 0:
            reasons.append("no_hypotheses")
        elif hyp_count == 1:
            reasons.append("single_hypothesis")

        # Мало доказательств из памяти
        if not result.memory_refs:
            reasons.append("no_memory_evidence")
        elif len(result.memory_refs) == 1:
            reasons.append("single_source")

        # Противоречия
        if result.contradictions:
            reasons.append("contradictions_found")

        # Низкая уверенность
        if result.confidence < 0.3:
            reasons.append("very_low_confidence")

        # Failure outcome
        outcome = meta.get("outcome", "")
        if outcome in (
            "retrieval_failed",
            "no_hypothesis_generated",
            "insufficient_confidence",
            "resource_blocked",
        ):
            reasons.append(f"outcome_{outcome}")

        return reasons

    @staticmethod
    def _extract_inferences(result: CognitiveResult) -> List[str]:
        """Извлечь ключевые умозаключения из trace steps."""
        inferences: List[str] = []

        if result.trace and result.trace.steps:
            for step in result.trace.steps:
                # Шаги reasoning содержат описания в details
                desc = step.details.get("description", "")
                if desc and step.action in ("hypothesize", "score", "select"):
                    # Берём первые 100 символов описания
                    short = desc[:100].strip()
                    if short:
                        inferences.append(short)

        # Ограничиваем количество
        return inferences[:5]

    @staticmethod
    def _extract_reasoning_chain(result: CognitiveResult) -> List[str]:
        """Извлечь цепочку рассуждений из trace steps."""
        chain: List[str] = []

        if result.trace and result.trace.steps:
            for step in result.trace.steps:
                action = step.action
                if action in ("retrieve", "hypothesize", "score", "select"):
                    chain.append(action)

        return chain
