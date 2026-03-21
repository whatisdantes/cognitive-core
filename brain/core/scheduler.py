"""
brain/core/scheduler.py

Тик-планировщик автономного цикла мозга.

Два режима работы:
  - CLOCK-DRIVEN: регулярные тики (100 мс / 500 мс / 2000 мс в зависимости от нагрузки)
  - EVENT-DRIVEN: задачи добавляются в очередь при получении событий

Принципы MVP:
  - Одна задача за тик (max_tasks_per_tick=1)
  - Приоритетная очередь (CRITICAL → HIGH → NORMAL → LOW → IDLE)
  - Публикует tick_start / tick_end / task_done / task_failed через EventBus
  - Не запускает фоновых потоков — управляется вызывающим кодом (main.py)
  - Graceful shutdown: дожидается завершения текущей задачи
"""

from __future__ import annotations

import heapq
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional, Tuple

from .contracts import ResourceState, Task, TaskStatus
from .event_bus import EventBus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Приоритеты задач
# ---------------------------------------------------------------------------

class TaskPriority(IntEnum):
    """
    Приоритет задачи в очереди планировщика.
    Меньшее значение = выше приоритет (heapq — min-heap).
    """
    CRITICAL = 0   # угроза целостности системы (RAM > 90%)
    HIGH     = 1   # пользовательский ввод, срочные события
    NORMAL   = 2   # обычный когнитивный цикл
    LOW      = 3   # replay, consolidation, self-reflection
    IDLE     = 4   # метрики, дашборд, cleanup


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

@dataclass
class SchedulerConfig:
    """Параметры планировщика."""
    tick_normal_ms: int   = 100    # 10 Hz при нормальной нагрузке
    tick_degraded_ms: int = 500    # 2 Hz при CPU > 70%
    tick_critical_ms: int = 2000   # 0.5 Hz при CPU > 85%
    tick_emergency_ms: int = 5000  # 0.2 Hz при RAM > 30 GB (EMERGENCY)
    max_queue_size: int   = 256    # максимум задач в очереди
    max_tasks_per_tick: int = 1    # MVP: одна задача за тик
    cpu_degraded_threshold: float = 70.0
    cpu_critical_threshold: float = 85.0
    ram_degraded_gb: float = 22.0  # порог DEGRADED по RAM (GB)
    ram_critical_gb: float = 28.0  # порог CRITICAL по RAM (GB)
    ram_emergency_gb: float = 30.0 # порог EMERGENCY по RAM (GB)
    session_id: str = ""           # идентификатор сессии (заполняется при старте)


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------

@dataclass
class SchedulerStats:
    """Накопленная статистика планировщика."""
    ticks: int          = 0
    tasks_enqueued: int = 0
    tasks_executed: int = 0
    tasks_failed: int   = 0
    tasks_dropped: int  = 0   # очередь переполнена
    idle_ticks: int     = 0   # тики без задач


# ---------------------------------------------------------------------------
# Планировщик
# ---------------------------------------------------------------------------

class Scheduler:
    """
    Тик-планировщик автономного цикла мозга.

    Использование (MVP):
        bus = EventBus()
        scheduler = Scheduler(bus)

        def handle_think(task: Task) -> Any:
            return {"result": "thought"}

        scheduler.register_handler("think", handle_think)
        scheduler.enqueue(Task(task_id="t1", task_type="think"), TaskPriority.NORMAL)

        # Один тик вручную:
        info = scheduler.tick()

        # Или основной цикл (блокирующий):
        scheduler.run(max_ticks=10)
    """

    def __init__(
        self,
        event_bus: EventBus,
        config: Optional[SchedulerConfig] = None,
    ) -> None:
        self._bus    = event_bus
        self._config = config or SchedulerConfig()
        self._stats  = SchedulerStats()
        self._running = False
        self._cycle_counter = 0

        # Приоритетная очередь: (priority_int, created_at, task_id, task)
        # task_id нужен для стабильной сортировки при одинаковом приоритете
        self._queue: List[Tuple[int, float, str, Task]] = []

        # Зарегистрированные обработчики задач: task_type → callable
        self._handlers: Dict[str, Callable[[Task], Any]] = {}

        if not self._config.session_id:
            self._config.session_id = f"session-{uuid.uuid4().hex[:8]}"

        logger.info(
            "[Scheduler] Инициализирован. session=%s tick_normal=%dms",
            self._config.session_id,
            self._config.tick_normal_ms,
        )

    # ------------------------------------------------------------------
    # Регистрация обработчиков
    # ------------------------------------------------------------------

    def register_handler(
        self,
        task_type: str,
        handler: Callable[[Task], Any],
    ) -> None:
        """
        Зарегистрировать обработчик для task_type.
        Повторная регистрация перезаписывает предыдущий handler.
        """
        self._handlers[task_type] = handler
        logger.debug("[Scheduler] handler зарегистрирован: %s → %s", task_type, handler.__name__)

    # ------------------------------------------------------------------
    # Управление очередью
    # ------------------------------------------------------------------

    def enqueue(
        self,
        task: Task,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> bool:
        """
        Добавить задачу в приоритетную очередь.

        Returns:
            True если задача добавлена, False если очередь переполнена.
        """
        if len(self._queue) >= self._config.max_queue_size:
            self._stats.tasks_dropped += 1
            logger.warning(
                "[Scheduler] Очередь переполнена (%d), задача %s отброшена",
                self._config.max_queue_size,
                task.task_id,
            )
            return False

        task.status = TaskStatus.PENDING
        heapq.heappush(
            self._queue,
            (int(priority), time.monotonic(), task.task_id, task),
        )
        self._stats.tasks_enqueued += 1
        logger.debug(
            "[Scheduler] enqueue task_id=%s type=%s priority=%s",
            task.task_id,
            task.task_type,
            priority.name,
        )
        return True

    def dequeue(self) -> Optional[Task]:
        """Извлечь задачу с наивысшим приоритетом (или None если очередь пуста)."""
        if not self._queue:
            return None
        _, _, _, task = heapq.heappop(self._queue)
        return task

    def queue_size(self) -> int:
        """Текущий размер очереди."""
        return len(self._queue)

    # ------------------------------------------------------------------
    # Выполнение одной задачи
    # ------------------------------------------------------------------

    def execute_one(self, cycle_id: str = "") -> Optional[Dict[str, Any]]:
        """
        Извлечь и выполнить одну задачу из очереди.

        Returns:
            Словарь с результатом выполнения или None если очередь пуста.
        """
        task = self.dequeue()
        if task is None:
            return None

        task.status = TaskStatus.RUNNING
        task.cycle_id = cycle_id
        task.session_id = self._config.session_id

        handler = self._handlers.get(task.task_type)
        if handler is None:
            task.status = TaskStatus.FAILED
            self._stats.tasks_failed += 1
            logger.warning(
                "[Scheduler] Нет handler для task_type='%s' (task_id=%s)",
                task.task_type,
                task.task_id,
            )
            self._bus.publish(
                "task_failed",
                {"task_id": task.task_id, "reason": f"no handler for '{task.task_type}'"},
                trace_id=task.trace_id,
            )
            return {"task_id": task.task_id, "status": "failed", "reason": "no_handler"}

        try:
            result = handler(task)
            task.status = TaskStatus.DONE
            self._stats.tasks_executed += 1
            logger.info(
                "[Scheduler] task_done task_id=%s type=%s",
                task.task_id,
                task.task_type,
            )
            self._bus.publish(
                "task_done",
                {"task_id": task.task_id, "task_type": task.task_type, "result": result},
                trace_id=task.trace_id,
            )
            return {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": "done",
                "result": result,
            }

        except Exception:
            task.status = TaskStatus.FAILED
            self._stats.tasks_failed += 1
            err = traceback.format_exc()
            logger.error(
                "[Scheduler] task_failed task_id=%s type=%s:\n%s",
                task.task_id,
                task.task_type,
                err,
            )
            self._bus.publish(
                "task_failed",
                {"task_id": task.task_id, "task_type": task.task_type, "error": err},
                trace_id=task.trace_id,
            )
            return {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "status": "failed",
                "error": err,
            }

    # ------------------------------------------------------------------
    # Один тик
    # ------------------------------------------------------------------

    def tick(
        self,
        resource_state: Optional[ResourceState] = None,
    ) -> Dict[str, Any]:
        """
        Выполнить один тик планировщика.

        Последовательность:
          1. Опубликовать tick_start
          2. Выполнить max_tasks_per_tick задач
          3. Опубликовать tick_end
          4. Вернуть сводку тика

        Args:
            resource_state: текущее состояние ресурсов (опционально).
                            Если None — используется ResourceState по умолчанию.

        Returns:
            Словарь с информацией о тике.
        """
        self._cycle_counter += 1
        self._stats.ticks += 1
        cycle_id = f"cycle-{self._cycle_counter:06d}"
        ts_start = time.monotonic()

        # Публикуем tick_start
        self._bus.publish(
            "tick_start",
            {
                "cycle_id": cycle_id,
                "tick_number": self._cycle_counter,
                "queue_size": self.queue_size(),
                "resource_state": resource_state.to_dict() if resource_state else None,
            },
            trace_id=cycle_id,
        )
        logger.debug("[Scheduler] tick_start cycle=%s queue=%d", cycle_id, self.queue_size())

        # Выполняем задачи (MVP: одна за тик)
        executed = []
        for _ in range(self._config.max_tasks_per_tick):
            result = self.execute_one(cycle_id=cycle_id)
            if result is None:
                self._stats.idle_ticks += 1
                break
            executed.append(result)

        ts_end = time.monotonic()
        duration_ms = (ts_end - ts_start) * 1000

        # Публикуем tick_end
        self._bus.publish(
            "tick_end",
            {
                "cycle_id": cycle_id,
                "tick_number": self._cycle_counter,
                "tasks_executed": len(executed),
                "duration_ms": round(duration_ms, 2),
                "queue_size": self.queue_size(),
            },
            trace_id=cycle_id,
        )
        logger.debug(
            "[Scheduler] tick_end cycle=%s tasks=%d duration=%.1fms",
            cycle_id,
            len(executed),
            duration_ms,
        )

        return {
            "cycle_id": cycle_id,
            "tick_number": self._cycle_counter,
            "tasks_executed": len(executed),
            "executed": executed,
            "duration_ms": round(duration_ms, 2),
            "queue_size": self.queue_size(),
        }

    # ------------------------------------------------------------------
    # Адаптация интервала тика
    # ------------------------------------------------------------------

    def get_tick_interval(
        self,
        resource_state: Optional[ResourceState] = None,
    ) -> float:
        """
        Вернуть интервал тика в секундах на основе состояния ресурсов.

        NORMAL    (CPU < 70%,  RAM < 22 GB):  100 мс  (10 Hz)
        DEGRADED  (CPU 70–85%, RAM 22–28 GB): 500 мс  (2 Hz)
        CRITICAL  (CPU > 85%,  RAM 28–30 GB): 2000 мс (0.5 Hz)
        EMERGENCY (RAM > 30 GB):              5000 мс (0.2 Hz)
        """
        if resource_state is None:
            return self._config.tick_normal_ms / 1000.0

        cpu    = resource_state.cpu_pct
        ram_gb = resource_state.ram_used_mb / 1024.0

        # EMERGENCY: RAM > 30 GB — самый медленный тик
        if ram_gb >= self._config.ram_emergency_gb:
            return self._config.tick_emergency_ms / 1000.0
        # CRITICAL: CPU > 85% или RAM > 28 GB
        if cpu >= self._config.cpu_critical_threshold or ram_gb >= self._config.ram_critical_gb:
            return self._config.tick_critical_ms / 1000.0
        # DEGRADED: CPU > 70% или RAM > 22 GB
        if cpu >= self._config.cpu_degraded_threshold or ram_gb >= self._config.ram_degraded_gb:
            return self._config.tick_degraded_ms / 1000.0
        return self._config.tick_normal_ms / 1000.0

    # ------------------------------------------------------------------
    # Основной цикл
    # ------------------------------------------------------------------

    def run(
        self,
        max_ticks: Optional[int] = None,
        resource_provider: Optional[Callable[[], ResourceState]] = None,
    ) -> None:
        """
        Запустить основной цикл планировщика (блокирующий).

        Args:
            max_ticks: максимальное количество тиков (None = бесконечно).
            resource_provider: callable() → ResourceState для адаптации интервала.
                               Если None — используется фиксированный tick_normal_ms.

        Остановка:
            scheduler.stop()  — из другого потока или обработчика сигнала.
        """
        self._running = True
        logger.info(
            "[Scheduler] Запуск основного цикла. max_ticks=%s session=%s",
            max_ticks,
            self._config.session_id,
        )
        self._bus.publish(
            "scheduler_started",
            {"session_id": self._config.session_id, "max_ticks": max_ticks},
            trace_id=self._config.session_id,
        )

        ticks_done = 0
        try:
            while self._running:
                if max_ticks is not None and ticks_done >= max_ticks:
                    break

                resource_state = resource_provider() if resource_provider else None
                interval = self.get_tick_interval(resource_state)

                self.tick(resource_state=resource_state)
                ticks_done += 1

                time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("[Scheduler] KeyboardInterrupt — остановка.")
        finally:
            self._running = False
            logger.info(
                "[Scheduler] Цикл завершён. ticks=%d executed=%d failed=%d",
                self._stats.ticks,
                self._stats.tasks_executed,
                self._stats.tasks_failed,
            )
            self._bus.publish(
                "scheduler_stopped",
                {
                    "session_id": self._config.session_id,
                    "ticks": self._stats.ticks,
                    "tasks_executed": self._stats.tasks_executed,
                    "tasks_failed": self._stats.tasks_failed,
                },
                trace_id=self._config.session_id,
            )

    def stop(self) -> None:
        """Остановить основной цикл после завершения текущего тика."""
        self._running = False
        logger.info("[Scheduler] Получен сигнал остановки.")

    # ------------------------------------------------------------------
    # Статистика и диагностика
    # ------------------------------------------------------------------

    @property
    def stats(self) -> SchedulerStats:
        """Снимок текущей статистики."""
        return SchedulerStats(
            ticks=self._stats.ticks,
            tasks_enqueued=self._stats.tasks_enqueued,
            tasks_executed=self._stats.tasks_executed,
            tasks_failed=self._stats.tasks_failed,
            tasks_dropped=self._stats.tasks_dropped,
            idle_ticks=self._stats.idle_ticks,
        )

    def status(self) -> Dict[str, Any]:
        """Словарь для логирования/observability."""
        s = self._stats
        return {
            "session_id": self._config.session_id,
            "running": self._running,
            "cycle_counter": self._cycle_counter,
            "queue_size": self.queue_size(),
            "registered_handlers": list(self._handlers.keys()),
            "ticks": s.ticks,
            "tasks_enqueued": s.tasks_enqueued,
            "tasks_executed": s.tasks_executed,
            "tasks_failed": s.tasks_failed,
            "tasks_dropped": s.tasks_dropped,
            "idle_ticks": s.idle_ticks,
        }

    def __repr__(self) -> str:
        s = self._stats
        return (
            f"Scheduler(ticks={s.ticks}, "
            f"queue={self.queue_size()}, "
            f"exec={s.tasks_executed}, "
            f"fail={s.tasks_failed})"
        )
