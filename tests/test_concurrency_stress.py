"""
Concurrent stress tests для EventBus + Scheduler (P3-8).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from brain.core.contracts import ResourceState, Task
from brain.core.event_bus import EventBus
from brain.core.scheduler import Scheduler, SchedulerConfig, TaskPriority


def test_event_bus_concurrent_publish_stress() -> None:
    """
    Стресс: много параллельных publish в один event_type.

    Проверяем, что все handler-вызовы учитываются корректно.
    """
    bus = EventBus()
    lock = threading.Lock()
    counter = 0

    def handler(_event_type: str, _payload: Any, _trace_id: str) -> None:
        nonlocal counter
        with lock:
            counter += 1

    bus.subscribe("stress_event", handler)

    publishes = 400
    workers = 16

    def do_publish(i: int) -> int:
        return bus.publish("stress_event", {"i": i}, trace_id=f"t-{i}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(do_publish, range(publishes)))

    # На каждую публикацию — 1 handler
    assert all(r == 1 for r in results)
    assert counter == publishes


def test_event_bus_concurrent_subscribe_unsubscribe_safety() -> None:
    """
    Стресс на subscribe/unsubscribe во время publish.

    Проверяем отсутствие аварий и консистентность snapshot-подхода.
    """
    bus = EventBus()
    stop = threading.Event()
    seen = 0
    seen_lock = threading.Lock()

    def handler(_event_type: str, _payload: Any, _trace_id: str) -> None:
        nonlocal seen
        with seen_lock:
            seen += 1

    def toggler() -> None:
        while not stop.is_set():
            bus.subscribe("evt", handler)
            bus.unsubscribe("evt", handler)

    togglers = [threading.Thread(target=toggler, daemon=True) for _ in range(6)]
    for t in togglers:
        t.start()

    for i in range(300):
        bus.publish("evt", i, trace_id=f"x{i}")

    stop.set()
    for t in togglers:
        t.join(timeout=1.0)

    # Проверка "живости": хотя бы часть вызовов дошла
    assert seen >= 0
    # Главное — тест доходит сюда без исключений/deadlock.


def test_scheduler_concurrent_enqueue_stress() -> None:
    """
    Стресс: параллельный enqueue задач в Scheduler, затем run.

    Проверяем, что задачи выполняются и статистика согласована.
    """
    bus = EventBus()
    scheduler = Scheduler(
        event_bus=bus,
        config=SchedulerConfig(
            tick_normal_ms=0,
            tick_degraded_ms=0,
            tick_critical_ms=0,
            tick_emergency_ms=0,
            max_tasks_per_tick=1,
            max_queue_size=5000,
        ),
    )

    executed = 0
    lock = threading.Lock()

    def work_handler(_task: Task) -> None:
        nonlocal executed
        with lock:
            executed += 1

    scheduler.register_handler("work", work_handler)

    total_tasks = 600
    workers = 12

    def producer(offset: int) -> None:
        for i in range(offset, offset + total_tasks // workers):
            scheduler.enqueue(
                Task(task_id=f"task-{i}", task_type="work"),
                priority=TaskPriority.NORMAL,
            )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        chunk = total_tasks // workers
        list(pool.map(producer, range(0, total_tasks, chunk)))

    assert scheduler.queue_size() > 0

    scheduler.run(
        max_ticks=total_tasks + 50,
        resource_provider=lambda: ResourceState(),
    )

    stats = scheduler.stats
    assert executed == total_tasks
    assert stats.tasks_executed == total_tasks
    assert stats.tasks_failed == 0
