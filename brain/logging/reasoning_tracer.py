"""
brain/logging/reasoning_tracer.py

TraceBuilder — построитель цепочки причинности (trace chain).
Renamed from trace_builder.py to avoid conflict with brain/output/trace_builder.py.

Каждое решение системы должно быть прослеживаемо:
  input → memory → hypotheses → reasoning → decision → output

TraceBuilder накапливает шаги по trace_id и позволяет:
  - добавлять шаги из любого модуля (add_step)
  - добавлять ссылки на входы/выходы (add_input_ref, add_output_ref)
  - восстанавливать полную цепочку (reconstruct → TraceChain)
  - форматировать в читаемый вид (to_human_readable)

Интеграция с BrainLogger:
  - TraceBuilder может восстанавливать trace из событий BrainLogger
    через reconstruct_from_logger(trace_id, logger)
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from brain.core.contracts import TraceChain, TraceRef, TraceStep

if TYPE_CHECKING:
    from brain.logging.brain_logger import BrainLogger


# ---------------------------------------------------------------------------
# TraceBuilder
# ---------------------------------------------------------------------------

class TraceBuilder:
    """
    Построитель цепочки причинности для когнитивных решений.

    Использование:
        builder = TraceBuilder()

        # В начале цикла:
        builder.start_trace(trace_id, session_id, cycle_id)

        # В каждом модуле:
        builder.add_step(trace_id, module="planner", action="goal_created",
                         confidence=1.0, details={"goal": "answer_question"})
        builder.add_input_ref(trace_id, ref_type="user_input", ref_id="msg_3")
        builder.add_memory_ref(trace_id, ref_type="semantic", ref_id="нейрон",
                               note="conf=0.87")

        # В конце цикла:
        chain = builder.reconstruct(trace_id)
        print(builder.to_human_readable(chain))

        # Очистить завершённый trace:
        builder.finish_trace(trace_id)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # trace_id → _TraceAccumulator
        self._traces: Dict[str, _TraceAccumulator] = {}

        # Завершённые цепочки (кэш последних N)
        self._completed: Dict[str, TraceChain] = {}
        self._max_completed = 500

    # ------------------------------------------------------------------
    # Управление жизненным циклом trace
    # ------------------------------------------------------------------

    def start_trace(
        self,
        trace_id: str,
        session_id: str = "",
        cycle_id: str = "",
    ) -> None:
        """Начать новый trace. Если уже существует — сбросить."""
        with self._lock:
            self._traces[trace_id] = _TraceAccumulator(
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
            )

    def finish_trace(self, trace_id: str) -> Optional[TraceChain]:
        """
        Завершить trace: построить TraceChain, сохранить в кэш, удалить аккумулятор.
        Возвращает готовую TraceChain или None если trace не найден.
        """
        with self._lock:
            acc = self._traces.pop(trace_id, None)
            if acc is None:
                return self._completed.get(trace_id)
            chain = acc.build()
            # Кэш с ограничением размера
            if len(self._completed) >= self._max_completed:
                oldest = next(iter(self._completed))
                del self._completed[oldest]
            self._completed[trace_id] = chain
            return chain

    # ------------------------------------------------------------------
    # Добавление данных в trace
    # ------------------------------------------------------------------

    def add_step(
        self,
        trace_id: str,
        module: str,
        action: str,
        confidence: float = 0.0,
        details: Optional[Dict[str, Any]] = None,
        refs: Optional[List[TraceRef]] = None,
    ) -> None:
        """Добавить шаг reasoning/decision в trace."""
        with self._lock:
            acc = self._get_or_create(trace_id)
            step_id = f"step_{len(acc.steps) + 1:03d}"
            acc.steps.append(TraceStep(
                step_id=step_id,
                module=module,
                action=action,
                confidence=confidence,
                details=details or {},
                refs=refs or [],
            ))

    def add_input_ref(
        self,
        trace_id: str,
        ref_type: str,
        ref_id: str,
        note: str = "",
    ) -> None:
        """Добавить ссылку на входные данные."""
        with self._lock:
            acc = self._get_or_create(trace_id)
            acc.input_refs.append(TraceRef(ref_type=ref_type, ref_id=ref_id, note=note))

    def add_memory_ref(
        self,
        trace_id: str,
        ref_type: str,
        ref_id: str,
        note: str = "",
    ) -> None:
        """Добавить ссылку на использованный факт из памяти."""
        with self._lock:
            acc = self._get_or_create(trace_id)
            acc.memory_refs.append(TraceRef(ref_type=ref_type, ref_id=ref_id, note=note))

    def add_output_ref(
        self,
        trace_id: str,
        ref_type: str,
        ref_id: str,
        note: str = "",
    ) -> None:
        """Добавить ссылку на выходные данные."""
        with self._lock:
            acc = self._get_or_create(trace_id)
            acc.output_refs.append(TraceRef(ref_type=ref_type, ref_id=ref_id, note=note))

    def set_summary(self, trace_id: str, summary: str) -> None:
        """Установить краткое резюме trace."""
        with self._lock:
            acc = self._get_or_create(trace_id)
            acc.summary = summary

    # ------------------------------------------------------------------
    # Восстановление и форматирование
    # ------------------------------------------------------------------

    def reconstruct(self, trace_id: str) -> Optional[TraceChain]:
        """
        Восстановить TraceChain по trace_id.

        Сначала ищет в активных аккумуляторах, затем в кэше завершённых.
        """
        with self._lock:
            if trace_id in self._traces:
                return self._traces[trace_id].build()
            return self._completed.get(trace_id)

    def reconstruct_from_logger(
        self,
        trace_id: str,
        logger: "BrainLogger",
    ) -> TraceChain:
        """
        Восстановить TraceChain из событий BrainLogger по trace_id.

        Используется для post-hoc анализа когда TraceBuilder не был активен.
        """
        events = logger.get_events(trace_id)
        acc = _TraceAccumulator(trace_id=trace_id)

        for ev in events:
            module = ev.get("module", "unknown")
            event_name = ev.get("event", "unknown")
            session_id = ev.get("session_id", "")
            cycle_id = ev.get("cycle_id", "")

            if not acc.session_id and session_id:
                acc.session_id = session_id
            if not acc.cycle_id and cycle_id:
                acc.cycle_id = cycle_id

            # Входные ссылки
            for ref in ev.get("input_ref", []):
                acc.input_refs.append(TraceRef(ref_type="input", ref_id=ref))

            # Ссылки на память
            for ref in ev.get("memory_refs", []):
                acc.memory_refs.append(TraceRef(ref_type="memory", ref_id=ref))

            # Шаг
            decision = ev.get("decision", {})
            confidence = float(decision.get("confidence", 0.0)) if decision else 0.0
            step_id = f"step_{len(acc.steps) + 1:03d}"
            acc.steps.append(TraceStep(
                step_id=step_id,
                module=module,
                action=event_name,
                confidence=confidence,
                details={
                    "state": ev.get("state", {}),
                    "decision": decision,
                    "latency_ms": ev.get("latency_ms"),
                    "notes": ev.get("notes", ""),
                },
            ))

        return acc.build()

    def to_human_readable(self, chain: TraceChain) -> str:
        """Форматировать TraceChain в читаемый текст."""
        lines: List[str] = []
        sep = "═" * 55

        lines.append(sep)
        lines.append(f"TRACE: {chain.trace_id}")
        if chain.cycle_id:
            lines.append(f"Cycle: {chain.cycle_id}  Session: {chain.session_id}")
        lines.append(sep)

        # Разделяем input_refs и memory_refs по маркеру '[memory] '
        actual_inputs = [r for r in chain.input_refs if not r.note.startswith("[memory]")]
        memory_refs   = [r for r in chain.input_refs if r.note.startswith("[memory]")]

        # Входы
        if actual_inputs:
            lines.append("INPUT:")
            for ref in actual_inputs:
                note = f"  ({ref.note})" if ref.note else ""
                lines.append(f"  [{ref.ref_type}] {ref.ref_id}{note}")

        # Память (отдельный блок)
        if memory_refs:
            lines.append("MEMORY:")
            for ref in memory_refs:
                clean_note = ref.note.replace("[memory] ", "", 1).strip()
                note_str = f"  ({clean_note})" if clean_note else ""
                lines.append(f"  [{ref.ref_type}] {ref.ref_id}{note_str}")

        # Шаги
        if chain.steps:
            lines.append("STEPS:")
            for step in chain.steps:
                conf_str = f"  conf={step.confidence:.2f}" if step.confidence > 0 else ""
                lines.append(f"  [{step.step_id}] {step.module}.{step.action}{conf_str}")
                # Детали шага
                details = step.details
                if details.get("state"):
                    state = details["state"]
                    if isinstance(state, dict) and state.get("goal"):
                        lines.append(f"           goal={state['goal']}")
                if details.get("decision"):
                    dec = details["decision"]
                    if isinstance(dec, dict):
                        dec_str = ", ".join(f"{k}={v}" for k, v in dec.items() if k != "confidence")
                        if dec_str:
                            lines.append(f"           {dec_str}")
                if details.get("notes"):
                    lines.append(f"           note: {details['notes']}")
                # Ссылки шага
                for ref in step.refs:
                    note = f" ({ref.note})" if ref.note else ""
                    lines.append(f"           → [{ref.ref_type}] {ref.ref_id}{note}")

        # Выходы
        if chain.output_refs:
            lines.append("OUTPUT:")
            for ref in chain.output_refs:
                note = f"  ({ref.note})" if ref.note else ""
                lines.append(f"  [{ref.ref_type}] {ref.ref_id}{note}")

        # Резюме
        if chain.summary:
            lines.append(f"SUMMARY: {chain.summary}")

        lines.append(sep)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Статистика
    # ------------------------------------------------------------------

    def active_traces(self) -> List[str]:
        """Список активных (незавершённых) trace_id."""
        with self._lock:
            return list(self._traces.keys())

    def completed_count(self) -> int:
        """Количество завершённых trace в кэше."""
        with self._lock:
            return len(self._completed)

    def __repr__(self) -> str:
        return (
            f"TraceBuilder(active={len(self._traces)}, "
            f"completed={len(self._completed)})"
        )

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _get_or_create(self, trace_id: str) -> "_TraceAccumulator":
        """Получить аккумулятор или создать новый (без блокировки — вызывать под lock)."""
        if trace_id not in self._traces:
            self._traces[trace_id] = _TraceAccumulator(trace_id=trace_id)
        return self._traces[trace_id]


# ---------------------------------------------------------------------------
# _TraceAccumulator — внутренний накопитель данных trace
# ---------------------------------------------------------------------------

@dataclass
class _TraceAccumulator:
    """Внутренний накопитель данных для одного trace."""
    trace_id: str
    session_id: str = ""
    cycle_id: str = ""
    input_refs: List[TraceRef] = field(default_factory=list)
    memory_refs: List[TraceRef] = field(default_factory=list)
    output_refs: List[TraceRef] = field(default_factory=list)
    steps: List[TraceStep] = field(default_factory=list)
    summary: str = ""

    def build(self) -> TraceChain:
        """Построить TraceChain из накопленных данных.

        memory_refs объединяются с input_refs, но помечаются префиксом
        '[memory] ' в поле note — это позволяет to_human_readable()
        отображать их в отдельном блоке MEMORY, сохраняя совместимость
        с TraceChain (у которого нет отдельного поля memory_refs).
        """
        all_input_refs = list(self.input_refs)
        for ref in self.memory_refs:
            tagged_note = ("[memory] " + ref.note).strip()
            all_input_refs.append(
                TraceRef(ref_type=ref.ref_type, ref_id=ref.ref_id, note=tagged_note)
            )
        return TraceChain(
            trace_id=self.trace_id,
            session_id=self.session_id,
            cycle_id=self.cycle_id,
            input_refs=all_input_refs,
            steps=list(self.steps),
            output_refs=list(self.output_refs),
            summary=self.summary,
        )
