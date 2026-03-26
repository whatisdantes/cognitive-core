"""
brain/cognition/goal_manager.py

Менеджер целей когнитивного ядра.

Содержит:
  - GoalStatus   — статусы цели (отдельный от TaskStatus)
  - Goal         — dataclass цели
  - GoalManager  — дерево целей с приоритетной очередью

Аналог: дорсолатеральная префронтальная кора — планирование и цели.

GoalManager — это НЕ чистый стек. Структура данных — дерево целей
с приоритетной очередью активных узлов + стек прерванных целей (LIFO).
"""

from __future__ import annotations

import heapq
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from brain.core.contracts import ContractMixin
from .context import GoalTypeLimits, GOAL_TYPE_LIMITS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GoalStatus — статусы цели
# ---------------------------------------------------------------------------

class GoalStatus(str, Enum):
    """
    Статусы цели.

    Отдельный от TaskStatus, потому что цель и задача — разные сущности.
    У цели есть INTERRUPTED и CANCELLED, у задачи — нет.
    """
    PENDING     = "pending"
    ACTIVE      = "active"
    DONE        = "done"
    FAILED      = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED   = "cancelled"


# ---------------------------------------------------------------------------
# Goal — dataclass цели
# ---------------------------------------------------------------------------

@dataclass
class Goal(ContractMixin):
    """
    Цель когнитивного ядра.

    goal_type определяет шаблон декомпозиции и stop conditions.
    Допустимые типы: "answer_question", "learn_fact", "verify_claim",
                     "explore_topic", "plan".
    """
    goal_id: str = ""
    description: str = ""
    goal_type: str = "answer_question"
    priority: float = 0.5
    deadline: Optional[float] = None
    parent_goal_id: Optional[str] = None
    sub_goals: List[str] = field(default_factory=list)
    status: GoalStatus = GoalStatus.PENDING
    created_at: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    failure_reason: str = ""

    def __post_init__(self):
        if not self.goal_id:
            self.goal_id = f"goal_{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    @property
    def is_terminal(self) -> bool:
        """Цель в терминальном состоянии (done/failed/cancelled)."""
        return self.status in (GoalStatus.DONE, GoalStatus.FAILED, GoalStatus.CANCELLED)

    @property
    def limits(self) -> GoalTypeLimits:
        """Stop conditions для данного типа цели."""
        return GOAL_TYPE_LIMITS.get(self.goal_type, GoalTypeLimits())

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация с GoalStatus → str."""
        d = {
            "goal_id": self.goal_id,
            "description": self.description,
            "goal_type": self.goal_type,
            "priority": self.priority,
            "deadline": self.deadline,
            "parent_goal_id": self.parent_goal_id,
            "sub_goals": list(self.sub_goals),
            "status": self.status.value if isinstance(self.status, GoalStatus) else self.status,
            "created_at": self.created_at,
            "context": dict(self.context),
            "trace_id": self.trace_id,
            "failure_reason": self.failure_reason,
        }
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Goal":
        """Десериализация с str → GoalStatus."""
        status_val = data.get("status", "pending")
        if isinstance(status_val, str):
            try:
                status_val = GoalStatus(status_val)
            except ValueError:
                status_val = GoalStatus.PENDING
        return cls(
            goal_id=data.get("goal_id", ""),
            description=data.get("description", ""),
            goal_type=data.get("goal_type", "answer_question"),
            priority=data.get("priority", 0.5),
            deadline=data.get("deadline"),
            parent_goal_id=data.get("parent_goal_id"),
            sub_goals=data.get("sub_goals", []),
            status=status_val,
            created_at=data.get("created_at", ""),
            context=data.get("context", {}),
            trace_id=data.get("trace_id", ""),
            failure_reason=data.get("failure_reason", ""),
        )


# ---------------------------------------------------------------------------
# GoalManager — менеджер целей
# ---------------------------------------------------------------------------

class GoalManager:
    """
    Дерево целей с приоритетной очередью активных узлов.

    Внутренняя структура:
      goal_tree:         Dict[str, Goal]        — все цели (id → Goal)
      active_queue:      min-heap по (-priority, created_at, goal_id)
      interrupted_stack: List[Goal]              — прерванные цели (LIFO)
      completed:         List[str]               — завершённые ID

    Использование:
        gm = GoalManager()
        goal = Goal(description="ответить на вопрос", goal_type="answer_question")
        gm.push(goal)
        current = gm.peek()  # → goal
        gm.complete(goal.goal_id)
    """

    def __init__(self) -> None:
        self._goal_tree: Dict[str, Goal] = {}
        # min-heap: (-priority, created_at_float, goal_id)
        self._active_queue: List[Tuple[float, float, str]] = []
        self._interrupted_stack: List[str] = []  # goal_ids
        self._completed: List[str] = []
        self._counter: int = 0  # для стабильной сортировки

    # ------------------------------------------------------------------
    # Основные операции
    # ------------------------------------------------------------------

    def push(self, goal: Goal) -> None:
        """
        Добавить цель в дерево и активную очередь.

        Если цель с таким goal_id уже существует — игнорируется.
        Приоритет: выше значение priority → раньше обработка.
        """
        if goal.goal_id in self._goal_tree:
            logger.warning(
                "[GoalManager] Цель %s уже существует, пропускаем.",
                goal.goal_id,
            )
            return

        goal.status = GoalStatus.ACTIVE
        self._goal_tree[goal.goal_id] = goal

        # Связь parent → sub_goal
        if goal.parent_goal_id and goal.parent_goal_id in self._goal_tree:
            parent = self._goal_tree[goal.parent_goal_id]
            if goal.goal_id not in parent.sub_goals:
                parent.sub_goals.append(goal.goal_id)

        # В очередь: -priority для max-heap через min-heap
        self._counter += 1
        heapq.heappush(
            self._active_queue,
            (-goal.priority, self._counter, goal.goal_id),
        )
        logger.debug(
            "[GoalManager] push goal_id=%s type=%s priority=%.2f",
            goal.goal_id, goal.goal_type, goal.priority,
        )

    def complete(self, goal_id: str) -> None:
        """Пометить цель как выполненную."""
        goal = self._goal_tree.get(goal_id)
        if goal is None:
            logger.warning("[GoalManager] complete: цель %s не найдена.", goal_id)
            return
        if goal.is_terminal:
            return

        goal.status = GoalStatus.DONE
        self._completed.append(goal_id)
        self._remove_from_queue(goal_id)
        logger.info("[GoalManager] complete goal_id=%s", goal_id)

    def fail(self, goal_id: str, reason: str = "") -> None:
        """Пометить цель как неудачную."""
        goal = self._goal_tree.get(goal_id)
        if goal is None:
            logger.warning("[GoalManager] fail: цель %s не найдена.", goal_id)
            return
        if goal.is_terminal:
            return

        goal.status = GoalStatus.FAILED
        goal.failure_reason = reason
        self._remove_from_queue(goal_id)
        logger.info("[GoalManager] fail goal_id=%s reason=%s", goal_id, reason)

    def cancel(self, goal_id: str) -> None:
        """Отменить цель."""
        goal = self._goal_tree.get(goal_id)
        if goal is None:
            return
        if goal.is_terminal:
            return

        goal.status = GoalStatus.CANCELLED
        self._remove_from_queue(goal_id)
        # Убрать из interrupted_stack если была прервана
        if goal_id in self._interrupted_stack:
            self._interrupted_stack.remove(goal_id)
        logger.info("[GoalManager] cancel goal_id=%s", goal_id)

    def peek(self) -> Optional[Goal]:
        """
        Вернуть текущую активную цель (с наивысшим приоритетом).
        Не извлекает из очереди.
        """
        # Пропускаем терминальные цели в голове очереди
        while self._active_queue:
            _, _, gid = self._active_queue[0]
            goal = self._goal_tree.get(gid)
            if goal and not goal.is_terminal and goal.status == GoalStatus.ACTIVE:
                return goal
            # Удаляем устаревшую запись
            heapq.heappop(self._active_queue)
        return None

    # ------------------------------------------------------------------
    # Прерывание / возобновление
    # ------------------------------------------------------------------

    def interrupt(self, urgent_goal: Goal) -> None:
        """
        Прервать текущую цель: переместить в interrupted_stack,
        активировать срочную цель.
        """
        current = self.peek()
        if current is not None:
            current.status = GoalStatus.INTERRUPTED
            self._remove_from_queue(current.goal_id)
            self._interrupted_stack.append(current.goal_id)
            logger.info(
                "[GoalManager] interrupt: %s → interrupted, activating %s",
                current.goal_id, urgent_goal.goal_id,
            )

        self.push(urgent_goal)

    def resume_interrupted(self) -> Optional[Goal]:
        """
        Возобновить последнюю прерванную цель (LIFO).
        Возвращает возобновлённую цель или None.
        """
        while self._interrupted_stack:
            gid = self._interrupted_stack.pop()
            goal = self._goal_tree.get(gid)
            if goal and goal.status == GoalStatus.INTERRUPTED:
                goal.status = GoalStatus.ACTIVE
                self._counter += 1
                heapq.heappush(
                    self._active_queue,
                    (-goal.priority, self._counter, goal.goal_id),
                )
                logger.info("[GoalManager] resume goal_id=%s", gid)
                return goal
        return None

    # ------------------------------------------------------------------
    # Запросы
    # ------------------------------------------------------------------

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Получить цель по ID."""
        return self._goal_tree.get(goal_id)

    def get_active_chain(self) -> List[Goal]:
        """
        Вернуть цепочку от корневой до текущей активной цели.
        """
        current = self.peek()
        if current is None:
            return []

        chain = [current]
        visited = {current.goal_id}

        # Поднимаемся по parent_goal_id
        node = current
        while node.parent_goal_id:
            if node.parent_goal_id in visited:
                break  # защита от циклов
            parent = self._goal_tree.get(node.parent_goal_id)
            if parent is None:
                break
            chain.append(parent)
            visited.add(parent.goal_id)
            node = parent

        chain.reverse()
        return chain

    @property
    def active_count(self) -> int:
        """Количество активных (не терминальных) целей."""
        return sum(
            1 for g in self._goal_tree.values()
            if g.status == GoalStatus.ACTIVE
        )

    @property
    def total_count(self) -> int:
        """Общее количество целей в дереве."""
        return len(self._goal_tree)

    @property
    def interrupted_count(self) -> int:
        """Количество прерванных целей."""
        return len(self._interrupted_stack)

    # ------------------------------------------------------------------
    # Статистика
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Словарь для логирования/observability."""
        current = self.peek()
        return {
            "total_goals": self.total_count,
            "active_goals": self.active_count,
            "interrupted_goals": self.interrupted_count,
            "completed_goals": len(self._completed),
            "queue_size": len(self._active_queue),
            "current_goal": current.goal_id if current else None,
        }

    def clear(self) -> None:
        """Очистить все цели (для тестов)."""
        self._goal_tree.clear()
        self._active_queue.clear()
        self._interrupted_stack.clear()
        self._completed.clear()
        self._counter = 0

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _remove_from_queue(self, goal_id: str) -> None:
        """
        Удалить цель из active_queue.
        Ленивое удаление: помечаем цель как терминальную,
        peek() пропустит её при следующем вызове.
        """
        # Фактическое удаление не нужно — peek() фильтрует.
        # Но для чистоты можно пересобрать очередь при большом размере.
        pass

    def __len__(self) -> int:
        """Общее количество целей в дереве."""
        return self.total_count

    def __repr__(self) -> str:
        current = self.peek()
        return (
            f"GoalManager(total={self.total_count}, "
            f"active={self.active_count}, "
            f"interrupted={self.interrupted_count}, "
            f"current={current.goal_id if current else None})"
        )
