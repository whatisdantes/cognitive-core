"""Тесты периодических задач Scheduler (U-A.1)."""

from brain.core import EventBus, RecurringTask, Scheduler, SchedulerConfig, Task, TaskPriority


def test_recurring_task_fires_at_expected_ticks():
    bus = EventBus()
    scheduler = Scheduler(
        bus,
        SchedulerConfig(tick_normal_ms=1, max_tasks_per_tick=1, session_id="recurring-test"),
    )
    executed_ticks: list[int] = []

    def handle_replay(task: Task):
        executed_ticks.append(task.payload["due_tick"])
        return {"ok": True}

    recurring = scheduler.register_recurring("replay", handle_replay, every_n_ticks=2)

    assert isinstance(recurring, RecurringTask)
    assert recurring.priority == TaskPriority.LOW

    scheduler.tick()
    scheduler.tick()
    scheduler.tick()
    scheduler.tick()
    scheduler.tick()

    assert executed_ticks == [2, 4]
    assert scheduler.stats.tasks_executed == 2
    assert recurring.enqueued_count == 2


def test_multiple_recurring_tasks_can_coexist():
    scheduler = Scheduler(
        EventBus(),
        SchedulerConfig(tick_normal_ms=1, max_tasks_per_tick=2, session_id="multi-recurring"),
    )
    executed: list[tuple[str, int]] = []

    def handle_task(task: Task):
        executed.append((task.task_type, task.payload["due_tick"]))
        return {}

    scheduler.register_recurring("replay", handle_task, every_n_ticks=2)
    scheduler.register_recurring("consolidate", handle_task, every_n_ticks=3)

    for _ in range(6):
        scheduler.tick()

    assert executed == [
        ("replay", 2),
        ("consolidate", 3),
        ("replay", 4),
        ("replay", 6),
        ("consolidate", 6),
    ]
    assert scheduler.status()["registered_recurring"] == ["replay", "consolidate"]


def test_due_recurring_task_does_not_duplicate_pending_task():
    scheduler = Scheduler(
        EventBus(),
        SchedulerConfig(tick_normal_ms=1, max_tasks_per_tick=0, session_id="no-duplicates"),
    )

    def handle_idle(task: Task):
        return {}

    recurring = scheduler.register_recurring("idle_gap_fill", handle_idle, every_n_ticks=1)

    scheduler.tick()
    scheduler.tick()
    scheduler.tick()

    assert scheduler.queue_size() == 1
    assert scheduler.stats.tasks_enqueued == 1
    assert recurring.enqueued_count == 1
    assert scheduler.status()["registered_recurring"] == ["idle_gap_fill"]


def test_register_recurring_rejects_non_positive_interval():
    scheduler = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1))

    def handle_task(task: Task):
        return {}

    try:
        scheduler.register_recurring("bad", handle_task, every_n_ticks=0)
    except ValueError as exc:
        assert "every_n_ticks" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_high_and_normal_tasks_have_priority_over_low_idle_work():
    scheduler = Scheduler(
        EventBus(),
        SchedulerConfig(tick_normal_ms=1, max_tasks_per_tick=1, session_id="priority-order"),
    )
    executed: list[str] = []

    def handle_job(task: Task):
        executed.append(task.task_id)
        return {}

    scheduler.register_handler("job", handle_job)
    scheduler.enqueue(Task(task_id="low", task_type="job"), TaskPriority.LOW)
    scheduler.enqueue(Task(task_id="normal", task_type="job"), TaskPriority.NORMAL)
    scheduler.enqueue(Task(task_id="high", task_type="job"), TaskPriority.HIGH)

    scheduler.tick()
    scheduler.tick()
    scheduler.tick()

    assert executed == ["high", "normal", "low"]


def test_idle_enqueue_respects_high_normal_and_low_backlog_guards():
    scheduler = Scheduler(
        EventBus(),
        SchedulerConfig(tick_normal_ms=1, max_low_queue_backlog=2, session_id="idle-guard"),
    )

    assert scheduler.enqueue_idle(Task(task_id="idle-1", task_type="idle"))
    assert scheduler.enqueue_idle(Task(task_id="idle-2", task_type="idle"))
    assert not scheduler.enqueue_idle(Task(task_id="idle-3", task_type="idle"))
    assert scheduler.low_backlog_size() == 2

    scheduler.enqueue(Task(task_id="user", task_type="user"), TaskPriority.HIGH)
    assert not scheduler.can_enqueue_idle_work()


def test_idle_enqueue_rejects_user_priority():
    scheduler = Scheduler(EventBus(), SchedulerConfig(tick_normal_ms=1))

    try:
        scheduler.enqueue_idle(
            Task(task_id="bad", task_type="bad"),
            priority=TaskPriority.NORMAL,
        )
    except ValueError as exc:
        assert "LOW or IDLE" in str(exc)
    else:
        raise AssertionError("expected ValueError")
