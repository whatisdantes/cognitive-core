"""
brain/core/event_bus.py

Typed publish/subscribe шина событий для межмодульного взаимодействия.

Принципы:
- Ошибка одного handler не прерывает остальных.
- Синхронный вызов (в рамках одного тика scheduler).
- Поддержка wildcard-подписки ("*") для логирования/отладки.
- Минимальная статистика для observability.

Классы:
    EventBus            — синхронная шина (snapshot pattern, RLock)
    ThreadPoolEventBus  — async диспетчеризация через ThreadPoolExecutor (P3-9)
"""

from __future__ import annotations

import logging
import threading
import traceback
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from brain.logging import _NULL_LOGGER, BrainLogger

logger = logging.getLogger(__name__)


Handler = Callable[[str, Any, str], None]
"""
Сигнатура handler:
    event_type: str   — тип события
    payload: Any      — данные события
    trace_id: str     — идентификатор трассировки
"""


def _handler_name(handler: Handler) -> str:
    """Безопасное извлечение имени handler (lambda, partial, callable-объект)."""
    return getattr(handler, "__name__", None) or getattr(handler, "__qualname__", None) or repr(handler)


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

    def __init__(self, brain_logger: Optional[BrainLogger] = None) -> None:
        self._lock = threading.RLock()
        # event_type → список handlers
        self._handlers: Dict[str, List[Handler]] = defaultdict(list)
        self._stats = BusStats()

        # --- Phase 7a: BrainLogger (NullObject pattern) ---
        self._blog: BrainLogger = brain_logger or _NULL_LOGGER  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Подписка / отписка
    # ------------------------------------------------------------------

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """
        Подписать handler на event_type.
        Повторная подписка одного и того же handler игнорируется.
        """
        with self._lock:
            if handler not in self._handlers[event_type]:
                self._handlers[event_type].append(handler)
                logger.debug("EventBus: subscribed %s → %s", event_type, _handler_name(handler))

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        """
        Отписать handler от event_type.
        Если handler не был подписан — молча игнорируется.
        """
        with self._lock:
            handlers = self._handlers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)
                logger.debug("EventBus: unsubscribed %s → %s", event_type, _handler_name(handler))

    def unsubscribe_all(self, event_type: Optional[str] = None) -> None:
        """
        Удалить все подписки для event_type.
        Если event_type=None — очистить всю шину.
        """
        with self._lock:
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

        Snapshot pattern: копируем список handlers под lock,
        вызываем вне lock — предотвращает deadlock при re-entrant publish.

        Returns:
            Количество успешно вызванных handlers.
        """
        # --- snapshot under lock ---
        with self._lock:
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

        # --- call handlers outside lock (snapshot pattern) ---
        success = 0
        for handler in all_handlers:
            try:
                handler(event_type, payload, trace_id)
                with self._lock:
                    self._stats.handled_count += 1
                success += 1
            except Exception:
                with self._lock:
                    self._stats.error_count += 1
                tb = traceback.format_exc()
                logger.error(
                    "EventBus: handler '%s' raised on event '%s' (trace=%s):\n%s",
                    _handler_name(handler),
                    event_type,
                    trace_id,
                    tb,
                )
                # --- Phase 7a: audit_event_bus_error (ERROR → safety_audit.jsonl) ---
                self._blog.error(
                    "event_bus", "audit_event_bus_error",
                    trace_id=trace_id,
                    state={
                        "event_type": event_type,
                        "handler": _handler_name(handler),
                        "traceback": tb.splitlines()[-1] if tb else "",
                    },
                )

        # --- Phase 7a: event_published (DEBUG → brain.jsonl) ---
        self._blog.debug(
            "event_bus", "event_published",
            trace_id=trace_id,
            state={
                "event_type": event_type,
                "handlers_called": success,
                "handlers_total": len(all_handlers),
            },
        )

        return success

    # ------------------------------------------------------------------
    # Статистика и диагностика
    # ------------------------------------------------------------------

    @property
    def stats(self) -> BusStats:
        """Текущая статистика шины (read-only snapshot)."""
        with self._lock:
            return BusStats(
                published_count=self._stats.published_count,
                handled_count=self._stats.handled_count,
                error_count=self._stats.error_count,
                dropped_count=self._stats.dropped_count,
            )

    def status(self) -> Dict[str, Any]:
        """Словарь для логирования/observability."""
        with self._lock:
            return {
                "subscribed_types": list(self._handlers.keys()),
                "total_handlers": sum(len(v) for v in self._handlers.values()),
                "published_count": self._stats.published_count,
                "handled_count": self._stats.handled_count,
                "error_count": self._stats.error_count,
                "dropped_count": self._stats.dropped_count,
            }

    def __repr__(self) -> str:
        with self._lock:
            s = self._stats
            return (
                f"EventBus(types={len(self._handlers)}, "
                f"pub={s.published_count}, ok={s.handled_count}, "
                f"err={s.error_count}, drop={s.dropped_count})"
            )


# ---------------------------------------------------------------------------
# ThreadPoolEventBus — async диспетчеризация (P3-9)
# ---------------------------------------------------------------------------


class ThreadPoolEventBus(EventBus):
    """
    EventBus с диспетчеризацией handlers через ThreadPoolExecutor (P3-9).

    Handlers вызываются в отдельных потоках пула — publish() не блокирует
    вызывающий поток. Ошибки handlers логируются асинхронно.

    Дополнительные методы:
        publish_sync()  — синхронная публикация (как в базовом EventBus)
        wait_all()      — дождаться завершения всех pending futures
        shutdown()      — завершить ThreadPoolExecutor

    Использование:
        bus = ThreadPoolEventBus(max_workers=4)
        bus.subscribe("tick_end", on_tick)
        bus.publish("tick_end", {"cycle": 1})   # async
        bus.publish_sync("tick_end", {"cycle": 2})  # sync
        bus.wait_all()
        bus.shutdown(wait=True)
    """

    def __init__(
        self,
        max_workers: int = 4,
        brain_logger: Optional[BrainLogger] = None,
    ) -> None:
        super().__init__(brain_logger=brain_logger)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="event-bus",
        )
        self._futures: List[Future] = []
        self._futures_lock = threading.Lock()
        logger.debug(
            "[ThreadPoolEventBus] Инициализирован. max_workers=%d", max_workers
        )

    # ------------------------------------------------------------------
    # Публикация (async)
    # ------------------------------------------------------------------

    def publish(
        self,
        event_type: str,
        payload: Any = None,
        trace_id: str = "",
    ) -> int:
        """
        Опубликовать событие через ThreadPoolExecutor.

        Handlers вызываются в отдельных потоках пула.
        Ошибки логируются в _call_handler (не прерывают остальных).

        Returns:
            Количество отправленных задач (futures submitted).
        """
        # --- snapshot under lock ---
        with self._lock:
            self._stats.published_count += 1
            specific = list(self._handlers.get(event_type, []))
            wildcard = list(self._handlers.get("*", []))
            all_handlers = specific + [h for h in wildcard if h not in specific]

            if not all_handlers:
                self._stats.dropped_count += 1
                logger.debug(
                    "[ThreadPoolEventBus] no handlers for '%s' (trace=%s)",
                    event_type, trace_id,
                )
                return 0

        # --- submit to thread pool (outside lock) ---
        submitted = 0
        for handler in all_handlers:
            future: Future = self._executor.submit(
                self._call_handler, handler, event_type, payload, trace_id
            )
            with self._futures_lock:
                self._futures.append(future)
            submitted += 1

        logger.debug(
            "[ThreadPoolEventBus] publish '%s' → %d futures (trace=%s)",
            event_type, submitted, trace_id,
        )
        return submitted

    def _call_handler(
        self,
        handler: Handler,
        event_type: str,
        payload: Any,
        trace_id: str,
    ) -> None:
        """Вызов handler в потоке пула. Ошибки логируются, не пробрасываются."""
        try:
            handler(event_type, payload, trace_id)
            with self._lock:
                self._stats.handled_count += 1
        except Exception:
            with self._lock:
                self._stats.error_count += 1
            tb = traceback.format_exc()
            logger.error(
                "[ThreadPoolEventBus] handler '%s' raised on event '%s' (trace=%s):\n%s",
                _handler_name(handler),
                event_type,
                trace_id,
                tb,
            )
            # --- Phase 7a: audit_event_bus_error (ERROR → safety_audit.jsonl) ---
            self._blog.error(
                "event_bus", "audit_event_bus_error",
                trace_id=trace_id,
                state={
                    "event_type": event_type,
                    "handler": _handler_name(handler),
                    "traceback": tb.splitlines()[-1] if tb else "",
                    "bus_type": "thread_pool",
                },
            )

    # ------------------------------------------------------------------
    # Синхронная публикация (fallback)
    # ------------------------------------------------------------------

    def publish_sync(
        self,
        event_type: str,
        payload: Any = None,
        trace_id: str = "",
    ) -> int:
        """
        Синхронная публикация (как в базовом EventBus).

        Используется когда нужна гарантия завершения handlers
        до возврата из publish (например, в тестах).
        """
        return super().publish(event_type, payload, trace_id)

    # ------------------------------------------------------------------
    # Управление futures
    # ------------------------------------------------------------------

    def wait_all(self, timeout: Optional[float] = None) -> None:
        """
        Дождаться завершения всех pending futures.

        Args:
            timeout: максимальное время ожидания каждого future (секунды).
                     None = ждать бесконечно.
        """
        with self._futures_lock:
            futures = list(self._futures)

        for future in futures:
            try:
                future.result(timeout=timeout)
            except Exception:
                pass  # уже залогировано в _call_handler

        # Очистить завершённые futures
        with self._futures_lock:
            self._futures = [f for f in self._futures if not f.done()]

    def shutdown(self, wait: bool = True) -> None:
        """
        Завершить ThreadPoolExecutor.

        Args:
            wait: True = дождаться завершения всех running tasks.
        """
        self._executor.shutdown(wait=wait)
        logger.info("[ThreadPoolEventBus] shutdown (wait=%s)", wait)

    # ------------------------------------------------------------------
    # Статистика и диагностика
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Расширенный статус с информацией о пуле потоков."""
        base = super().status()
        with self._futures_lock:
            pending = sum(1 for f in self._futures if not f.done())
            total = len(self._futures)
        base["thread_pool"] = {
            "max_workers": self._executor._max_workers,  # type: ignore[attr-defined]
            "pending_futures": pending,
            "total_futures": total,
        }
        return base

    def __repr__(self) -> str:
        with self._lock:
            s = self._stats
        with self._futures_lock:
            pending = sum(1 for f in self._futures if not f.done())
        return (
            f"ThreadPoolEventBus(types={len(self._handlers)}, "
            f"pub={s.published_count}, ok={s.handled_count}, "
            f"err={s.error_count}, pending={pending})"
        )
