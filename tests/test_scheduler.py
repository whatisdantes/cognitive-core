"""
Smoke-тесты для brain/core/scheduler.py (B.2)
DoD: tick_start -> task_run -> tick_end видны в логе/событиях
"""

import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

from brain.core import (
    EventBus, Scheduler, TaskPriority, SchedulerConfig,
    Task, TaskStatus, ResourceState,
)

PASS = 0
FAIL = 0


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✓ {msg}")


def fail(msg: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    print(f"  ✗ {msg}" + (f": {detail}" if detail else ""))


# ──────────────────────────────────────────────────────────────────────────────
print("\n──────────────────────────────────────────────────────────────────────")
print("  B.2 Scheduler — smoke tests")
print("──────────────────────────────────────────────────────────────────────")

bus = EventBus()
cfg = SchedulerConfig(tick_normal_ms=50, session_id="test-session")
sched = Scheduler(bus, cfg)

tick_log = []


def on_tick_start(et, payload, tid):
    tick_log.append(("tick_start", payload["cycle_id"]))


def on_tick_end(et, payload, tid):
    tick_log.append(("tick_end", payload["cycle_id"], payload["tasks_executed"]))


def on_task_done(et, payload, tid):
    tick_log.append(("task_done", payload["task_id"]))


bus.subscribe("tick_start", on_tick_start)
bus.subscribe("tick_end", on_tick_end)
bus.subscribe("task_done", on_task_done)

# ── Тест 1: idle tick (нет задач) ────────────────────────────────────────────
info = sched.tick()
if info["tasks_executed"] == 0 and sched.stats.idle_ticks == 1:
    ok("idle tick (no tasks, idle_ticks=1)")
else:
    fail("idle tick", f"tasks_executed={info['tasks_executed']} idle={sched.stats.idle_ticks}")

# ── Тест 2: register_handler + enqueue ───────────────────────────────────────
results = []


def handle_think(task: Task):
    results.append(task.task_id)
    return {"thought": "done"}


sched.register_handler("think", handle_think)
t1 = Task(task_id="t1", task_type="think", trace_id="tr1")
enqueued = sched.enqueue(t1, TaskPriority.NORMAL)
if enqueued and sched.queue_size() == 1:
    ok("enqueue task (queue_size=1)")
else:
    fail("enqueue task", f"enqueued={enqueued} queue={sched.queue_size()}")

# ── Тест 3: tick_start -> task_run -> tick_end ────────────────────────────────
info = sched.tick()
if info["tasks_executed"] == 1 and results == ["t1"] and sched.queue_size() == 0:
    ok("tick_start -> task_run -> tick_end (1 task executed)")
else:
    fail("tick execute", f"executed={info['tasks_executed']} results={results}")

# ── Тест 4: приоритет (CRITICAL раньше LOW) ───────────────────────────────────
results2 = []


def handle_job(task: Task):
    results2.append(task.task_id)
    return {}


sched.register_handler("job", handle_job)
t_low  = Task(task_id="low",  task_type="job")
t_crit = Task(task_id="crit", task_type="job")
sched.enqueue(t_low,  TaskPriority.LOW)
sched.enqueue(t_crit, TaskPriority.CRITICAL)
sched.tick()  # выполнит CRITICAL
sched.tick()  # выполнит LOW
if results2 == ["crit", "low"]:
    ok("priority order: CRITICAL before LOW")
else:
    fail("priority order", f"got {results2}")

# ── Тест 5: нет handler -> task_failed ───────────────────────────────────────
failed_log = []


def on_fail(et, payload, tid):
    failed_log.append(payload["task_id"])


bus.subscribe("task_failed", on_fail)
t_unk = Task(task_id="unk", task_type="unknown_type")
sched.enqueue(t_unk, TaskPriority.HIGH)
sched.tick()
if "unk" in failed_log and sched.stats.tasks_failed == 1:
    ok("no handler -> task_failed event published")
else:
    fail("task_failed", f"failed_log={failed_log} stats={sched.stats.tasks_failed}")

# ── Тест 6: tick_start / tick_end события в log ───────────────────────────────
starts = [e for e in tick_log if e[0] == "tick_start"]
ends   = [e for e in tick_log if e[0] == "tick_end"]
if len(starts) >= 5 and len(ends) >= 5:
    ok(f"tick_start/tick_end events logged ({len(starts)} starts, {len(ends)} ends)")
else:
    fail("tick events", f"starts={len(starts)} ends={len(ends)}")

# ── Тест 7: status() ─────────────────────────────────────────────────────────
st = sched.status()
if (
    st["running"] is False
    and st["tasks_executed"] >= 2
    and "think" in st["registered_handlers"]
    and "session_id" in st
):
    ok("status() contains running/tasks_executed/registered_handlers/session_id")
else:
    fail("status()", str(st))

# ── Тест 8: get_tick_interval адаптация ──────────────────────────────────────
rs_normal   = ResourceState(cpu_pct=50.0)
rs_degraded = ResourceState(cpu_pct=75.0)
rs_critical = ResourceState(cpu_pct=90.0)
i_n = sched.get_tick_interval(rs_normal)
i_d = sched.get_tick_interval(rs_degraded)
i_c = sched.get_tick_interval(rs_critical)
if i_n < i_d < i_c:
    ok(f"tick interval adapts: normal={i_n}s degraded={i_d}s critical={i_c}s")
else:
    fail("tick interval", f"n={i_n} d={i_d} c={i_c}")

# ── Тест 9: run(max_ticks=3) ─────────────────────────────────────────────────
sched2 = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1, session_id="run-test"))
sched2.run(max_ticks=3)
if sched2.stats.ticks == 3:
    ok("run(max_ticks=3) executed exactly 3 ticks")
else:
    fail("run(max_ticks=3)", f"ticks={sched2.stats.ticks}")

# ── Тест 10: handler exception -> task_failed (не падает scheduler) ───────────
fail_results = []


def bad_handler(task: Task):
    raise RuntimeError("намеренная ошибка")


sched3 = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1))
sched3.register_handler("bad", bad_handler)
t_bad = Task(task_id="bad1", task_type="bad")
sched3.enqueue(t_bad, TaskPriority.NORMAL)
info3 = sched3.tick()
if sched3.stats.tasks_failed == 1 and info3["executed"][0]["status"] == "failed":
    ok("handler exception -> task_failed, scheduler continues")
else:
    fail("handler exception", str(info3))

# ── Тест 11: регрессия памяти ─────────────────────────────────────────────────
import os
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
r = subprocess.run(
    [sys.executable, "-m", "tests.test_memory"],
    capture_output=True, text=True, encoding="utf-8", env=env,
)
lines = [l for l in r.stdout.splitlines() if l.strip()]
# Ищем строку с итогом (может быть не последней из-за emoji-строки после)
summary = next((l for l in lines if "101" in l and "провалено" in l), None)
if summary and "0 провалено" in summary:
    ok(f"memory regression ({summary.strip()})")
else:
    last = lines[-1] if lines else r.stderr.strip()
    fail("memory regression", last)

# ── Итог ─────────────────────────────────────────────────────────────────────
print()
print("══════════════════════════════════════════════════════════════════════")
print(f"  ИТОГ: {PASS} пройдено | {FAIL} провалено")
print("══════════════════════════════════════════════════════════════════════")
if FAIL == 0:
    print("  ✅ Все тесты B.2 пройдены! Scheduler работает корректно.")
else:
    print("  ❌ Есть провалы — см. выше.")
    sys.exit(1)
