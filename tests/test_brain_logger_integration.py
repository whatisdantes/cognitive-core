"""
tests/test_brain_logger_integration.py

Интеграционные тесты BrainLogger (LOG_PLAN.md v2.0, Фаза 9).

Покрывает:
  - NullBrainLogger / _NULL_LOGGER — no-op поведение (тесты 1–2)
  - EventBus — event_published + audit_event_bus_error (тесты 3–5)
  - Scheduler — scheduler_tick + task_done + task_failed (тесты 6–9)
  - OutputPipeline — output_start + output_complete (тесты 10–12)
  - BrainLogger — JSONL-запись, индексы, фильтрация, категории (тесты 13–18)
  - Сквозной тест EventBus + Scheduler (тест 19)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

import pytest

from brain.core.contracts import CognitiveResult, Task, TraceChain
from brain.core.event_bus import EventBus
from brain.core.scheduler import Scheduler, SchedulerConfig, TaskPriority
from brain.logging import _NULL_LOGGER, BrainLogger, NullBrainLogger
from brain.output.dialogue_responder import OutputPipeline

# ---------------------------------------------------------------------------
# Вспомогательный шпион-логгер
# ---------------------------------------------------------------------------

class _SpyLogger:
    """
    Шпион-логгер для перехвата вызовов BrainLogger без записи на диск.

    Реализует тот же интерфейс, что и BrainLogger / NullBrainLogger,
    но сохраняет все вызовы в self.calls для последующей проверки.
    """

    def __init__(self) -> None:
        self.calls: List[dict] = []

    def log(self, level: str, module: str, event: str, **kwargs: Any) -> None:
        self.calls.append({"level": level, "module": module, "event": event, **kwargs})

    def debug(self, module: str, event: str, **kwargs: Any) -> None:
        self.log("DEBUG", module, event, **kwargs)

    def info(self, module: str, event: str, **kwargs: Any) -> None:
        self.log("INFO", module, event, **kwargs)

    def warn(self, module: str, event: str, **kwargs: Any) -> None:
        self.log("WARN", module, event, **kwargs)

    def error(self, module: str, event: str, **kwargs: Any) -> None:
        self.log("ERROR", module, event, **kwargs)

    def critical(self, module: str, event: str, **kwargs: Any) -> None:
        self.log("CRITICAL", module, event, **kwargs)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def get_events(self, trace_id: str) -> List[dict]:
        return []

    def get_session(self, session_id: str) -> List[dict]:
        return []

    def get_recent(self, n: int = 10, min_level: str = "DEBUG") -> List[dict]:
        return []

    def has_event(self, event_name: str) -> bool:
        """Проверить, было ли залогировано событие с данным именем."""
        return any(c["event"] == event_name for c in self.calls)

    def events_of(self, event_name: str) -> List[dict]:
        """Вернуть все вызовы с данным именем события."""
        return [c for c in self.calls if c["event"] == event_name]


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture
def spy() -> _SpyLogger:
    """Шпион-логгер для тестов."""
    return _SpyLogger()


@pytest.fixture
def simple_result() -> CognitiveResult:
    """Минимальный CognitiveResult для тестов OutputPipeline."""
    return CognitiveResult(
        action="respond_direct",
        response="Тестовый ответ",
        confidence=0.8,
        trace=TraceChain(
            trace_id="trace-test-001",
            session_id="sess-test-001",
            cycle_id="cycle-000001",
        ),
        goal="тест",
        trace_id="trace-test-001",
        session_id="sess-test-001",
        cycle_id="cycle-000001",
    )


# ===========================================================================
# Тест 1: NullBrainLogger — no-op при любых вызовах
# ===========================================================================

def test_null_logger_no_op() -> None:
    """NullBrainLogger не вызывает исключений при любых вызовах."""
    null = NullBrainLogger()
    null.debug("mod", "event", state={"x": 1})
    null.info("mod", "event")
    null.warn("mod", "event", latency_ms=1.5)
    null.error("mod", "event", trace_id="t1")
    null.critical("mod", "event")
    null.flush()
    null.close()
    assert null.get_events("any") == []
    assert null.get_session("any") == []
    assert null.get_recent() == []


# ===========================================================================
# Тест 2: _NULL_LOGGER — глобальный синглтон типа NullBrainLogger
# ===========================================================================

def test_null_logger_singleton() -> None:
    """_NULL_LOGGER — глобальный синглтон типа NullBrainLogger."""
    assert isinstance(_NULL_LOGGER, NullBrainLogger)
    # Повторные вызовы не должны бросать исключений
    _NULL_LOGGER.info("mod", "event")
    _NULL_LOGGER.warn("mod", "event", latency_ms=0.5)


# ===========================================================================
# Тест 3: EventBus — event_published логируется
# ===========================================================================

def test_event_bus_logs_event_published(spy: _SpyLogger) -> None:
    """EventBus.publish() логирует event_published через BrainLogger."""
    bus = EventBus(brain_logger=spy)  # type: ignore[arg-type]
    bus.subscribe("test_event", lambda et, p, tid: None)
    bus.publish("test_event", {"data": 1}, trace_id="t-001")

    assert spy.has_event("event_published"), f"Ожидалось event_published, calls={spy.calls}"
    ev = spy.events_of("event_published")[0]
    assert ev["module"] == "event_bus"
    assert ev["level"] == "DEBUG"
    assert ev["state"]["event_type"] == "test_event"
    assert ev["state"]["handlers_called"] == 1


# ===========================================================================
# Тест 4: EventBus — audit_event_bus_error при исключении в handler
# ===========================================================================

def test_event_bus_logs_audit_error(spy: _SpyLogger) -> None:
    """EventBus.publish() логирует audit_event_bus_error при исключении в handler."""
    bus = EventBus(brain_logger=spy)  # type: ignore[arg-type]

    def bad_handler(et: str, p: Any, tid: str) -> None:
        raise ValueError("тест ошибки handler")

    bus.subscribe("fail_event", bad_handler)
    bus.publish("fail_event", {}, trace_id="t-002")

    assert spy.has_event("audit_event_bus_error"), (
        f"Ожидалось audit_event_bus_error, calls={spy.calls}"
    )
    ev = spy.events_of("audit_event_bus_error")[0]
    assert ev["level"] == "ERROR"
    assert ev["state"]["event_type"] == "fail_event"


# ===========================================================================
# Тест 5: EventBus без brain_logger — backward compatibility
# ===========================================================================

def test_event_bus_no_brain_logger() -> None:
    """EventBus без brain_logger работает без ошибок (NullObject pattern)."""
    bus = EventBus()
    bus.subscribe("ev", lambda et, p, tid: None)
    result = bus.publish("ev", {}, trace_id="t-003")
    assert result == 1


# ===========================================================================
# Тест 6: Scheduler — scheduler_tick логируется
# ===========================================================================

def test_scheduler_logs_tick(spy: _SpyLogger) -> None:
    """Scheduler.tick() логирует scheduler_tick через BrainLogger."""
    bus = EventBus()
    cfg = SchedulerConfig(session_id="sess-tick-test")
    scheduler = Scheduler(bus, config=cfg, brain_logger=spy)  # type: ignore[arg-type]

    scheduler.tick()

    assert spy.has_event("scheduler_tick"), (
        f"Ожидалось scheduler_tick, calls={spy.calls}"
    )
    ev = spy.events_of("scheduler_tick")[0]
    assert ev["module"] == "scheduler"
    assert ev["level"] == "INFO"
    assert "tick_number" in ev["state"]
    assert "tasks_executed" in ev["state"]
    assert "queue_size" in ev["state"]


# ===========================================================================
# Тест 7: Scheduler — scheduler_task_done логируется при успехе
# ===========================================================================

def test_scheduler_logs_task_done(spy: _SpyLogger) -> None:
    """Scheduler.execute_one() логирует scheduler_task_done при успешном выполнении."""
    bus = EventBus()
    cfg = SchedulerConfig(session_id="sess-done-test")
    scheduler = Scheduler(bus, config=cfg, brain_logger=spy)  # type: ignore[arg-type]

    scheduler.register_handler("think", lambda t: {"ok": True})
    scheduler.enqueue(
        Task(task_id="task-done-1", task_type="think"),
        TaskPriority.NORMAL,
    )
    scheduler.execute_one(cycle_id="cycle-000001")

    assert spy.has_event("scheduler_task_done"), (
        f"Ожидалось scheduler_task_done, calls={spy.calls}"
    )
    ev = spy.events_of("scheduler_task_done")[0]
    assert ev["level"] == "INFO"
    assert ev["state"]["task_type"] == "think"
    assert ev["state"]["task_id"] == "task-done-1"


# ===========================================================================
# Тест 8: Scheduler — scheduler_task_failed логируется при исключении
# ===========================================================================

def test_scheduler_logs_task_failed(spy: _SpyLogger) -> None:
    """Scheduler.execute_one() логирует scheduler_task_failed при исключении в handler."""
    bus = EventBus()
    cfg = SchedulerConfig(session_id="sess-fail-test")
    scheduler = Scheduler(bus, config=cfg, brain_logger=spy)  # type: ignore[arg-type]

    def failing_handler(t: Task) -> None:
        raise RuntimeError("тест сбоя задачи")

    scheduler.register_handler("fail_task", failing_handler)
    scheduler.enqueue(
        Task(task_id="task-fail-1", task_type="fail_task"),
        TaskPriority.NORMAL,
    )
    scheduler.execute_one(cycle_id="cycle-000001")

    assert spy.has_event("scheduler_task_failed"), (
        f"Ожидалось scheduler_task_failed, calls={spy.calls}"
    )
    ev = spy.events_of("scheduler_task_failed")[0]
    assert ev["level"] == "WARN"
    assert ev["state"]["task_type"] == "fail_task"
    assert "error" in ev["state"]


# ===========================================================================
# Тест 9: Scheduler без brain_logger — backward compatibility
# ===========================================================================

def test_scheduler_no_brain_logger() -> None:
    """Scheduler без brain_logger работает без ошибок (NullObject pattern)."""
    bus = EventBus()
    scheduler = Scheduler(bus)
    scheduler.register_handler("noop", lambda t: None)
    scheduler.enqueue(
        Task(task_id="task-noop-1", task_type="noop"),
        TaskPriority.NORMAL,
    )
    info = scheduler.tick()
    assert info["tasks_executed"] == 1


# ===========================================================================
# Тест 10: OutputPipeline — output_start логируется
# ===========================================================================

def test_output_pipeline_logs_start(
    spy: _SpyLogger, simple_result: CognitiveResult
) -> None:
    """OutputPipeline.process() логирует output_start через BrainLogger."""
    pipeline = OutputPipeline(brain_logger=spy)  # type: ignore[arg-type]
    pipeline.process(simple_result)

    assert spy.has_event("output_start"), (
        f"Ожидалось output_start, calls={spy.calls}"
    )
    ev = spy.events_of("output_start")[0]
    assert ev["module"] == "output"
    assert ev["level"] == "DEBUG"
    assert ev["state"]["action"] == "respond_direct"
    assert ev["state"]["confidence"] == pytest.approx(0.8)


# ===========================================================================
# Тест 11: OutputPipeline — output_complete логируется
# ===========================================================================

def test_output_pipeline_logs_complete(
    spy: _SpyLogger, simple_result: CognitiveResult
) -> None:
    """OutputPipeline.process() логирует output_complete через BrainLogger."""
    pipeline = OutputPipeline(brain_logger=spy)  # type: ignore[arg-type]
    pipeline.process(simple_result)

    assert spy.has_event("output_complete"), (
        f"Ожидалось output_complete, calls={spy.calls}"
    )
    ev = spy.events_of("output_complete")[0]
    assert ev["level"] == "INFO"
    assert ev["state"]["action"] == "respond_direct"
    assert "latency_ms" in ev
    assert ev["latency_ms"] >= 0.0


# ===========================================================================
# Тест 12: OutputPipeline без brain_logger — backward compatibility
# ===========================================================================

def test_output_pipeline_no_brain_logger(simple_result: CognitiveResult) -> None:
    """OutputPipeline без brain_logger работает без ошибок (NullObject pattern)."""
    pipeline = OutputPipeline()
    output = pipeline.process(simple_result)
    assert output.text


# ===========================================================================
# Тест 13: BrainLogger — запись в brain.jsonl
# ===========================================================================

def test_brain_logger_writes_jsonl(tmp_path: Path) -> None:
    """BrainLogger записывает события в brain.jsonl в корректном JSON-формате."""
    blog = BrainLogger(log_dir=str(tmp_path), min_level="DEBUG")
    blog.info(
        "test_module",
        "test_event",
        trace_id="t-100",
        state={"x": 42},
        latency_ms=1.23,
    )
    blog.flush()
    blog.close()

    jsonl_path = tmp_path / "brain.jsonl"
    assert jsonl_path.exists(), "brain.jsonl должен быть создан"
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1

    record = json.loads(lines[-1])
    assert record["event"] == "test_event"
    assert record["module"] == "test_module"
    assert record["level"] == "INFO"
    assert record["trace_id"] == "t-100"
    assert record["state"]["x"] == 42
    assert record["latency_ms"] == pytest.approx(1.23, abs=0.01)


# ===========================================================================
# Тест 14: BrainLogger — get_events по trace_id
# ===========================================================================

def test_brain_logger_get_events(tmp_path: Path) -> None:
    """BrainLogger.get_events() возвращает только события с указанным trace_id."""
    blog = BrainLogger(log_dir=str(tmp_path), min_level="DEBUG")
    blog.info("mod", "ev1", trace_id="trace-abc", state={"n": 1})
    blog.info("mod", "ev2", trace_id="trace-abc", state={"n": 2})
    blog.info("mod", "ev3", trace_id="trace-xyz", state={"n": 3})
    blog.close()

    events_abc = blog.get_events("trace-abc")
    assert len(events_abc) == 2
    assert all(e["trace_id"] == "trace-abc" for e in events_abc)

    events_xyz = blog.get_events("trace-xyz")
    assert len(events_xyz) == 1

    events_none = blog.get_events("trace-nonexistent")
    assert events_none == []


# ===========================================================================
# Тест 15: BrainLogger — get_session по session_id
# ===========================================================================

def test_brain_logger_get_session(tmp_path: Path) -> None:
    """BrainLogger.get_session() возвращает только события с указанным session_id."""
    blog = BrainLogger(log_dir=str(tmp_path), min_level="DEBUG")
    blog.info("mod", "ev1", session_id="sess-001")
    blog.info("mod", "ev2", session_id="sess-001")
    blog.info("mod", "ev3", session_id="sess-002")
    blog.close()

    events_001 = blog.get_session("sess-001")
    assert len(events_001) == 2
    assert all(e["session_id"] == "sess-001" for e in events_001)

    events_002 = blog.get_session("sess-002")
    assert len(events_002) == 1


# ===========================================================================
# Тест 16: BrainLogger — фильтрация по min_level
# ===========================================================================

def test_brain_logger_min_level_filter(tmp_path: Path) -> None:
    """BrainLogger с min_level=WARN не записывает DEBUG/INFO события."""
    blog = BrainLogger(log_dir=str(tmp_path), min_level="WARN")
    blog.debug("mod", "debug_event")
    blog.info("mod", "info_event")
    blog.warn("mod", "warn_event")
    blog.error("mod", "error_event")
    blog.flush()
    blog.close()

    jsonl_path = tmp_path / "brain.jsonl"
    lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    recorded_events = [json.loads(line)["event"] for line in lines]

    assert "debug_event" not in recorded_events
    assert "info_event" not in recorded_events
    assert "warn_event" in recorded_events
    assert "error_event" in recorded_events


# ===========================================================================
# Тест 17: BrainLogger — категорийный файл memory.jsonl
# ===========================================================================

def test_brain_logger_category_memory(tmp_path: Path) -> None:
    """BrainLogger записывает memory_* события в memory.jsonl."""
    blog = BrainLogger(log_dir=str(tmp_path), min_level="DEBUG")
    blog.info("memory", "memory_store", state={"concept": "нейрон"})
    blog.flush()
    blog.close()

    memory_path = tmp_path / "memory.jsonl"
    assert memory_path.exists(), "memory.jsonl должен быть создан для memory_* событий"
    lines = memory_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    record = json.loads(lines[0])
    assert record["event"] == "memory_store"
    assert record["module"] == "memory"


# ===========================================================================
# Тест 18: BrainLogger — категорийный файл safety_audit.jsonl
# ===========================================================================

def test_brain_logger_category_safety_audit(tmp_path: Path) -> None:
    """BrainLogger записывает audit_* события в safety_audit.jsonl."""
    blog = BrainLogger(log_dir=str(tmp_path), min_level="DEBUG")
    blog.error(
        "event_bus",
        "audit_event_bus_error",
        state={"event_type": "test_ev", "handler": "bad_fn"},
    )
    blog.flush()
    blog.close()

    audit_path = tmp_path / "safety_audit.jsonl"
    assert audit_path.exists(), "safety_audit.jsonl должен быть создан для audit_* событий"
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    record = json.loads(lines[0])
    assert record["event"] == "audit_event_bus_error"
    assert record["level"] == "ERROR"


# ===========================================================================
# Тест 19: Сквозной тест EventBus + Scheduler через один BrainLogger
# ===========================================================================

def test_event_bus_scheduler_end_to_end(spy: _SpyLogger) -> None:
    """
    Сквозной тест: EventBus + Scheduler оба логируют через один _SpyLogger.

    Проверяет, что оба модуля корректно вызывают BrainLogger
    и события не теряются при совместном использовании.
    """
    bus = EventBus(brain_logger=spy)  # type: ignore[arg-type]
    cfg = SchedulerConfig(session_id="e2e-sess-001")
    scheduler = Scheduler(bus, config=cfg, brain_logger=spy)  # type: ignore[arg-type]

    # Подписываемся на tick_end — EventBus логирует event_published только при наличии handlers
    bus.subscribe("tick_end", lambda et, p, tid: None)

    scheduler.register_handler("work", lambda t: {"done": True})
    scheduler.enqueue(
        Task(task_id="e2e-task-1", task_type="work"),
        TaskPriority.NORMAL,
    )

    # tick() выполняет задачу + публикует события через EventBus
    tick_info = scheduler.tick()
    assert tick_info["tasks_executed"] == 1

    # Scheduler должен залогировать scheduler_tick и scheduler_task_done
    assert spy.has_event("scheduler_tick"), (
        f"Ожидалось scheduler_tick, calls={[c['event'] for c in spy.calls]}"
    )
    assert spy.has_event("scheduler_task_done"), (
        f"Ожидалось scheduler_task_done, calls={[c['event'] for c in spy.calls]}"
    )

    # EventBus логирует event_published для tick_end (есть подписчик)
    assert spy.has_event("event_published"), (
        f"Ожидалось event_published, calls={[c['event'] for c in spy.calls]}"
    )
    ev_pub = spy.events_of("event_published")[0]
    assert ev_pub["state"]["event_type"] == "tick_end"
    assert ev_pub["state"]["handlers_called"] == 1

    # Проверяем, что scheduler_tick содержит корректные данные
    tick_ev = spy.events_of("scheduler_tick")[0]
    assert tick_ev["state"]["tasks_executed"] == 1
    assert tick_ev["state"]["session_id"] == "e2e-sess-001"
