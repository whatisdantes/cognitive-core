"""
brain/core/event_bus.py

Typed publish/subscribe шина событий для межмодульного взаимодействия.

Принципы:
- Ошибка одного handler не прерывает остальных.
- Синхронный вызов (в рамках одного тика scheduler).
- Поддержка wildcard-подписки ("*") для логирования/отладки.
- Минимальная статистика для observability.
"""

from __future__ import annotations

import logging
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


Handler = Callable[[str, Any, str], None]
"""
Сигнатура handler:
    event_type: str   — тип события
    payload: Any      — данные события
    trace_id: str     — идентификатор трассировки
"""


@dataclass
class BusStats:
    """Статистика шины событий."""
    published_count: int = 0
    handled_count: int = 0
    error_count: int = 0
    dropped_count: int = 0   # событий без подписчиков


class EventBus:
    """
    Синхронная typed pub/sub шина событий.

    Использование:
        bus = EventBus()

        def on_percept(event_type, payload, trace_id):
            print(f"[{trace_id}] {event_type}: {payload}")

        bus.subscribe("percept", on_percept)
        bus.publish("percept", {"text": "hello"}, trace_id="t-001")
        bus.unsubscribe("percept", on_percept)

    Wildcard:
        bus.subscribe("*", debug_handler)  # получает ВСЕ события
    """

    def __init__(self) -> None:
        # event_type → список handlers
        self._handlers: Dict[str, List[Handler]] = defaultdict(list)
        self._stats = BusStats()

    # ------------------------------------------------------------------
    # Подписка / отписка
    # ------------------------------------------------------------------

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """
        Подписать handler на event_type.
        Повторная подписка одного и того же handler игнорируется.
        """
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            logger.debug("EventBus: subscribed %s → %s", event_type, handler.__name__)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        """
        Отписать handler от event_type.
        Если handler не был подписан — молча игнорируется.
        """
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            logger.debug("EventBus: unsubscribed %s → %s", event_type, handler.__name__)

    def unsubscribe_all(self, event_type: Optional[str] = None) -> None:
        """
        Удалить все подписки для event_type.
        Если event_type=None — очистить всю шину.
        """
        if event_type is None:
            self._handlers.clear()
        else:
            self._handlers.pop(event_type, None)

    # ------------------------------------------------------------------
    # Публикация
    # ------------------------------------------------------------------

    def publish(
        self,
        event_type: str,
        payload: Any = None,
        trace_id: str = "",
    ) -> int:
        """
        Опубликовать событие.

        Вызывает все handlers подписанные на event_type, а затем
        wildcard-handlers ("*"). Ошибка одного handler логируется
        и не прерывает остальных.

        Returns:
            Количество успешно вызванных handlers.
        """
        self._stats.published_count += 1

        specific = list(self._handlers.get(event_type, []))
        wildcard = list(self._handlers.get("*", []))

        # Wildcard не должен дублироваться если подписан и на конкретный тип
        all_handlers = specific + [h for h in wildcard if h not in specific]

        if not all_handlers:
            self._stats.dropped_count += 1
            logger.debug(
                "EventBus: no handlers for '%s' (trace=%s)", event_type, trace_id
            )
            return 0

        success = 0
        for handler in all_handlers:
            try:
                handler(event_type, payload, trace_id)
                self._stats.handled_count += 1
                success += 1
            except Exception:
                self._stats.error_count += 1
                logger.error(
                    "EventBus: handler '%s' raised on event '%s' (trace=%s):\n%s",
                    handler.__name__,
                    event_type,
                    trace_id,
                    traceback.format_exc(),
                )

        return success

    # ------------------------------------------------------------------
    # Статистика и диагностика
    # ------------------------------------------------------------------

    @property
    def stats(self) -> BusStats:
        """Текущая статистика шины (read-only snapshot)."""
        return BusStats(
            published_count=self._stats.published_count,
            handled_count=self._stats.handled_count,
            error_count=self._stats.error_count,
            dropped_count=self._stats.dropped_count,
        )

    def status(self) -> Dict[str, Any]:
        """Словарь для логирования/observability."""
        return {
            "subscribed_types": list(self._handlers.keys()),
            "total_handlers": sum(len(v) for v in self._handlers.values()),
            "published_count": self._stats.published_count,
            "handled_count": self._stats.handled_count,
            "error_count": self._stats.error_count,
            "dropped_count": self._stats.dropped_count,
        }

    def __repr__(self) -> str:
        s = self._stats
        return (
            f"EventBus(types={len(self._handlers)}, "
            f"pub={s.published_count}, ok={s.handled_count}, "
            f"err={s.error_count}, drop={s.dropped_count})"
        )
