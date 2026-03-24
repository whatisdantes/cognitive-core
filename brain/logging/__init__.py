"""
brain/logging — Система логирования и наблюдаемости (Этап C).

Реализовано (C.1–C.3):
    BrainLogger      — потокобезопасный JSONL-логгер (brain_logger.py)
    DigestGenerator  — человекочитаемые дайджесты по циклам (digest_generator.py)
    TraceBuilder     — цепочка причинности по trace_id (reasoning_tracer.py)
                       (renamed from trace_builder.py to avoid conflict with brain/output/trace_builder.py)

Запланировано (Этап 13):
    MetricsCollector — KPI метрики (metrics_collector.py)
    Dashboard        — live-дашборд в терминале (dashboard.py)

Быстрый старт:
    from brain.logging import BrainLogger, DigestGenerator, TraceBuilder, CycleInfo

    logger  = BrainLogger(log_dir="brain/data/logs")
    digest  = DigestGenerator()
    tracer  = TraceBuilder()

    logger.info("planner", "goal_created",
                trace_id="t-001", session_id="sess_01", cycle_id="cycle_1",
                state={"goal": "answer_question"})

    tracer.start_trace("t-001", session_id="sess_01", cycle_id="cycle_1")
    tracer.add_step("t-001", module="planner", action="goal_created", confidence=1.0)
    chain = tracer.finish_trace("t-001")
    print(tracer.to_human_readable(chain))
"""

from brain.logging.brain_logger import BrainLogger
from brain.logging.digest_generator import DigestGenerator, CycleInfo
from brain.logging.reasoning_tracer import TraceBuilder

__all__ = [
    "BrainLogger",
    "DigestGenerator",
    "CycleInfo",
    "TraceBuilder",
]
