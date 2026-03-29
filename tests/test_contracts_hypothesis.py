"""
Property-based тесты для ContractMixin (P3-6).

Покрывает roundtrip to_dict()/from_dict() для контрактов:
- ResourceState
- Task (включая Enum TaskStatus)
- EncodedPercept (включая Enum Modality)
- TraceChain (вложенные TraceStep/TraceRef)
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from brain.core.contracts import (
    EncodedPercept,
    Modality,
    ResourceState,
    Task,
    TaskStatus,
    TraceChain,
    TraceRef,
    TraceStep,
)


def _finite_float(min_value: float = -1e6, max_value: float = 1e6) -> st.SearchStrategy[float]:
    """Конечные float без NaN/Inf для стабильного roundtrip."""
    return st.floats(
        min_value=min_value,
        max_value=max_value,
        allow_nan=False,
        allow_infinity=False,
    )


text_strat = st.text(max_size=64)
small_dict = st.dictionaries(
    keys=st.text(min_size=1, max_size=16),
    values=st.one_of(st.integers(), _finite_float(), st.booleans(), st.text(max_size=32)),
    max_size=8,
)


@settings(max_examples=80, deadline=None)
@given(
    cpu_pct=_finite_float(0.0, 100.0),
    ram_pct=_finite_float(0.0, 100.0),
    ram_used_mb=_finite_float(0.0, 1_000_000.0),
    ram_total_mb=_finite_float(0.0, 1_000_000.0),
    available_threads=st.integers(min_value=1, max_value=2048),
    ring2_allowed=st.booleans(),
    soft_blocked=st.booleans(),
)
def test_resource_state_roundtrip_property(
    cpu_pct: float,
    ram_pct: float,
    ram_used_mb: float,
    ram_total_mb: float,
    available_threads: int,
    ring2_allowed: bool,
    soft_blocked: bool,
) -> None:
    obj = ResourceState(
        cpu_pct=cpu_pct,
        ram_pct=ram_pct,
        ram_used_mb=ram_used_mb,
        ram_total_mb=ram_total_mb,
        available_threads=available_threads,
        ring2_allowed=ring2_allowed,
        soft_blocked=soft_blocked,
    )
    restored = ResourceState.from_dict(obj.to_dict())
    assert restored == obj


@settings(max_examples=80, deadline=None)
@given(
    task_id=text_strat,
    task_type=text_strat,
    priority=_finite_float(0.0, 1.0),
    status=st.sampled_from(list(TaskStatus)),
    trace_id=text_strat,
    session_id=text_strat,
    cycle_id=text_strat,
    payload=small_dict,
)
def test_task_roundtrip_property(
    task_id: str,
    task_type: str,
    priority: float,
    status: TaskStatus,
    trace_id: str,
    session_id: str,
    cycle_id: str,
    payload: dict[str, object],
) -> None:
    obj = Task(
        task_id=task_id,
        task_type=task_type,
        payload=payload,
        priority=priority,
        status=status,
        trace_id=trace_id,
        session_id=session_id,
        cycle_id=cycle_id,
    )
    restored = Task.from_dict(obj.to_dict())
    assert restored == obj
    assert isinstance(restored.status, TaskStatus)


@settings(max_examples=80, deadline=None)
@given(
    percept_id=text_strat,
    modality=st.sampled_from(list(Modality)),
    vector=st.lists(_finite_float(-1000.0, 1000.0), max_size=64),
    text=text_strat,
    quality=_finite_float(0.0, 1.0),
    source=text_strat,
    language=text_strat,
    message_type=text_strat,
    encoder_model=text_strat,
    vector_dim=st.integers(min_value=0, max_value=8192),
    metadata=small_dict,
    trace_id=text_strat,
    session_id=text_strat,
    cycle_id=text_strat,
)
def test_encoded_percept_roundtrip_property(
    percept_id: str,
    modality: Modality,
    vector: list[float],
    text: str,
    quality: float,
    source: str,
    language: str,
    message_type: str,
    encoder_model: str,
    vector_dim: int,
    metadata: dict[str, object],
    trace_id: str,
    session_id: str,
    cycle_id: str,
) -> None:
    obj = EncodedPercept(
        percept_id=percept_id,
        modality=modality,
        vector=vector,
        text=text,
        quality=quality,
        source=source,
        language=language,
        message_type=message_type,
        encoder_model=encoder_model,
        vector_dim=vector_dim,
        metadata=metadata,
        trace_id=trace_id,
        session_id=session_id,
        cycle_id=cycle_id,
    )
    restored = EncodedPercept.from_dict(obj.to_dict())
    assert restored == obj
    assert isinstance(restored.modality, Modality)


@settings(max_examples=60, deadline=None)
@given(
    trace_id=text_strat,
    session_id=text_strat,
    cycle_id=text_strat,
    summary=text_strat,
    input_refs=st.lists(
        st.builds(TraceRef, ref_type=text_strat, ref_id=text_strat, note=text_strat),
        max_size=8,
    ),
    output_refs=st.lists(
        st.builds(TraceRef, ref_type=text_strat, ref_id=text_strat, note=text_strat),
        max_size=8,
    ),
    steps=st.lists(
        st.builds(
            TraceStep,
            step_id=text_strat,
            module=text_strat,
            action=text_strat,
            confidence=_finite_float(0.0, 1.0),
            details=small_dict,
            refs=st.lists(
                st.builds(TraceRef, ref_type=text_strat, ref_id=text_strat, note=text_strat),
                max_size=4,
            ),
        ),
        max_size=8,
    ),
)
def test_trace_chain_nested_roundtrip_property(
    trace_id: str,
    session_id: str,
    cycle_id: str,
    summary: str,
    input_refs: list[TraceRef],
    output_refs: list[TraceRef],
    steps: list[TraceStep],
) -> None:
    obj = TraceChain(
        trace_id=trace_id,
        session_id=session_id,
        cycle_id=cycle_id,
        input_refs=input_refs,
        steps=steps,
        output_refs=output_refs,
        summary=summary,
    )
    restored = TraceChain.from_dict(obj.to_dict())
    assert restored == obj
    assert all(isinstance(ref, TraceRef) for ref in restored.input_refs)
    assert all(isinstance(step, TraceStep) for step in restored.steps)
