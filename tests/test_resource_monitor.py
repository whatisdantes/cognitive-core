"""
Smoke-тесты для brain/core/resource_monitor.py (B.3)
DoD: при эмуляции high load выставляются корректные флаги.
"""

import logging
import os
import subprocess
import sys
import time
import pytest

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

from brain.core import (
    EventBus,
    ResourceMonitor,
    ResourceMonitorConfig,
    DegradationPolicy,
    ResourceState,
    Scheduler,
    SchedulerConfig,
)

PASS = 0
FAIL = 0
_results = []


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    _results.append((msg, True, ""))
    print(f"  ✓ {msg}")


def fail(msg: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    _results.append((msg, False, detail))
    print(f"  ✗ {msg}" + (f": {detail}" if detail else ""))


print("\n══════════════════════════════════════════════════════════════════════")
print("  B.3 ResourceMonitor — smoke tests")
print("══════════════════════════════════════════════════════════════════════")

bus = EventBus()
cfg = ResourceMonitorConfig(
    sample_interval_s=0.1,
    cpu_degraded_pct=70.0,
    cpu_critical_pct=85.0,
    ram_degraded_gb=22.0,
    ram_critical_gb=28.0,
    ram_emergency_gb=30.0,
    cpu_soft_block_off_pct=60.0,
    cpu_ring2_off_pct=75.0,
)
monitor = ResourceMonitor(bus, cfg)

# ── Тест 1: инициализация и начальное состояние ───────────────────────────────
state = monitor.check()
if (
    isinstance(state, ResourceState)
    and state.ring2_allowed is True
    and state.soft_blocked is False
    and monitor.get_policy() == DegradationPolicy.NORMAL
):
    ok("initial state: NORMAL, ring2_allowed=True, soft_blocked=False")
else:
    fail("initial state", f"policy={monitor.get_policy()} state={state}")

# ── Тест 2: inject NORMAL (CPU=50%) ──────────────────────────────────────────
monitor.inject_state(ResourceState(cpu_pct=50.0, ram_used_mb=8192.0))
s = monitor.check()
if (
    monitor.get_policy() == DegradationPolicy.NORMAL
    and s.soft_blocked is False
    and s.ring2_allowed is True
):
    ok("inject NORMAL (cpu=50%): soft_blocked=False, ring2_allowed=True")
else:
    fail("inject NORMAL", f"policy={monitor.get_policy()} sb={s.soft_blocked} r2={s.ring2_allowed}")

# ── Тест 3: inject DEGRADED (CPU=75%) ────────────────────────────────────────
monitor.inject_state(ResourceState(cpu_pct=75.0, ram_used_mb=8192.0))
s = monitor.check()
if (
    monitor.get_policy() == DegradationPolicy.DEGRADED
    and s.soft_blocked is True
    and s.ring2_allowed is True
):
    ok("inject DEGRADED (cpu=75%): soft_blocked=True, ring2_allowed=True")
else:
    fail("inject DEGRADED", f"policy={monitor.get_policy()} sb={s.soft_blocked} r2={s.ring2_allowed}")

# ── Тест 4: inject CRITICAL (CPU=90%) ────────────────────────────────────────
monitor.inject_state(ResourceState(cpu_pct=90.0, ram_used_mb=8192.0))
s = monitor.check()
if (
    monitor.get_policy() == DegradationPolicy.CRITICAL
    and s.soft_blocked is True
    and s.ring2_allowed is False
):
    ok("inject CRITICAL (cpu=90%): soft_blocked=True, ring2_allowed=False")
else:
    fail("inject CRITICAL", f"policy={monitor.get_policy()} sb={s.soft_blocked} r2={s.ring2_allowed}")

# ── Тест 5: inject EMERGENCY (RAM > 30 GB) ───────────────────────────────────
monitor.inject_state(ResourceState(cpu_pct=50.0, ram_used_mb=31_000.0))
s = monitor.check()
if monitor.get_policy() == DegradationPolicy.EMERGENCY:
    ok("inject EMERGENCY (ram=31GB): policy=EMERGENCY")
else:
    fail("inject EMERGENCY", f"policy={monitor.get_policy()}")

# ── Тест 6: гистерезис soft_blocked (CPU 90% → 55%) ─────────────────────────
monitor.inject_state(ResourceState(cpu_pct=90.0, ram_used_mb=8192.0))  # активируем
monitor.inject_state(ResourceState(cpu_pct=55.0, ram_used_mb=8192.0))  # ниже off-порога (60%)
s = monitor.check()
if s.soft_blocked is False and monitor.get_policy() == DegradationPolicy.NORMAL:
    ok("hysteresis soft_blocked: 90%→55% снимает флаг (off_pct=60%)")
else:
    fail("hysteresis soft_blocked", f"sb={s.soft_blocked} policy={monitor.get_policy()}")

# ── Тест 7: гистерезис ring2_allowed (CPU 90% → 70%) ────────────────────────
monitor.inject_state(ResourceState(cpu_pct=90.0, ram_used_mb=8192.0))  # ring2=False
monitor.inject_state(ResourceState(cpu_pct=70.0, ram_used_mb=8192.0))  # между 75% и 85%
s = monitor.check()
# 70% < ring2_off_pct(75%) → ring2 должен восстановиться
if s.ring2_allowed is True:
    ok("hysteresis ring2_allowed: 90%→70% восстанавливает ring2 (off_pct=75%)")
else:
    fail("hysteresis ring2_allowed", f"ring2={s.ring2_allowed} cpu=70%")

# ── Тест 8: гистерезис ring2 НЕ снимается при CPU=80% ────────────────────────
monitor.inject_state(ResourceState(cpu_pct=90.0, ram_used_mb=8192.0))  # ring2=False
monitor.inject_state(ResourceState(cpu_pct=80.0, ram_used_mb=8192.0))  # между 75% и 85%
s = monitor.check()
# 80% > ring2_off_pct(75%) → ring2 остаётся False
if s.ring2_allowed is False:
    ok("hysteresis ring2: 90%→80% НЕ восстанавливает ring2 (off_pct=75%)")
else:
    fail("hysteresis ring2 sticky", f"ring2={s.ring2_allowed} cpu=80%")

# ── Тест 9: policy_changed event публикуется ─────────────────────────────────
events_log = []


def on_policy_change(et, payload, tid):
    events_log.append(payload["new_policy"])


bus.subscribe("resource_policy_changed", on_policy_change)
monitor.clear_injection()
monitor2 = ResourceMonitor(bus, cfg)
monitor2.inject_state(ResourceState(cpu_pct=50.0, ram_used_mb=8192.0))  # NORMAL
monitor2.inject_state(ResourceState(cpu_pct=90.0, ram_used_mb=8192.0))  # → CRITICAL
monitor2.inject_state(ResourceState(cpu_pct=50.0, ram_used_mb=8192.0))  # → NORMAL
if "critical" in events_log and "normal" in events_log:
    ok(f"resource_policy_changed events published: {events_log}")
else:
    fail("policy_changed events", f"got {events_log}")

# ── Тест 10: status() содержит все ключи ─────────────────────────────────────
monitor.inject_state(ResourceState(cpu_pct=75.0, ram_used_mb=10240.0))
st = monitor.status()
required_keys = {
    "running", "psutil_available", "policy", "cpu_pct", "ram_pct",
    "ram_used_mb", "ram_total_mb", "available_threads",
    "soft_blocked", "ring2_allowed", "samples_taken", "policy_changes",
}
missing = required_keys - set(st.keys())
if not missing:
    ok(f"status() содержит все {len(required_keys)} обязательных ключей")
else:
    fail("status() missing keys", str(missing))

# ── Тест 11: start/stop фонового потока ──────────────────────────────────────
monitor3 = ResourceMonitor(EventBus(), ResourceMonitorConfig(sample_interval_s=0.05))
monitor3.start()
time.sleep(0.2)  # дать 2–4 сэмпла
monitor3.stop()
if monitor3.stats.samples_taken >= 1:
    ok(f"background thread: {monitor3.stats.samples_taken} сэмплов за 0.2s")
else:
    fail("background thread", f"samples={monitor3.stats.samples_taken}")

# ── Тест 12: интеграция с Scheduler (tick interval меняется) ─────────────────
sched = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=100))
monitor.inject_state(ResourceState(cpu_pct=50.0))
i_normal = sched.get_tick_interval(monitor.check())
monitor.inject_state(ResourceState(cpu_pct=90.0))
i_critical = sched.get_tick_interval(monitor.check())
if i_critical > i_normal:
    ok(f"Scheduler интеграция: normal={i_normal}s critical={i_critical}s")
else:
    fail("Scheduler интеграция", f"normal={i_normal} critical={i_critical}")

# ── Тест 13: регрессия памяти ─────────────────────────────────────────────────
env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"
r = subprocess.run(
    [sys.executable, "-m", "tests.test_memory"],
    capture_output=True, text=True, encoding="utf-8", env=env,
)
lines = [l for l in r.stdout.splitlines() if l.strip()]
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
    print("  ✅ Все тесты B.3 пройдены! ResourceMonitor работает корректно.")
else:
    print("  ❌ Есть провалы — см. выше.")

# ═══════════════════════════════════════════════════════
# PYTEST PARAMETRIZE — каждая проверка = отдельный тест
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "name,condition,detail",
    _results,
    ids=[r[0] for r in _results],
)
def test_resource_monitor_check(name, condition, detail):
    assert condition, f"{name}" + (f": {detail}" if detail else "")


if __name__ == "__main__" and FAIL != 0:
    sys.exit(1)
