"""
brain/cognition/uncertainty_monitor.py

Мониторинг неопределённости в reasoning loop.

Содержит:
  - UncertaintySnapshot  — снимок состояния неопределённости
  - UncertaintyMonitor   — отслеживание тренда confidence

Контракт F+.2:
  - Каноническая величина: ReasoningState.current_confidence
  - trend хранится как str (не enum) для совместимости с ContractMixin.from_dict()
  - reset() обязателен между reasoning runs
  - should_early_stop(): stagnation >= window_size
  - should_escalate(): falling >= escalation_count

Аналог: островковая кора — интероцепция, мониторинг внутреннего состояния.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import List

from brain.core.contracts import ContractMixin

from .context import ReasoningState, UncertaintyTrend

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UncertaintySnapshot — снимок состояния неопределённости
# ---------------------------------------------------------------------------

@dataclass
class UncertaintySnapshot(ContractMixin):
    """
    Снимок состояния неопределённости на текущей итерации.

    confidence:      текущая confidence (каноническая величина)
    trend:           тренд как str ("rising"/"falling"/"stable"/"unknown")
    delta:           изменение confidence с предыдущей итерации
    iteration:       номер итерации
    should_stop:     рекомендация остановить reasoning (stagnation)
    should_escalate: рекомендация эскалировать (falling trend)
    history_length:  длина истории confidence
    """
    confidence: float = 0.0
    trend: str = "unknown"
    delta: float = 0.0
    iteration: int = 0
    should_stop: bool = False
    should_escalate: bool = False
    history_length: int = 0


# ---------------------------------------------------------------------------
# UncertaintyMonitor
# ---------------------------------------------------------------------------

class UncertaintyMonitor:
    """
    Мониторинг тренда confidence в reasoning loop.

    Отслеживает историю confidence и определяет:
      - trend: rising / falling / stable / unknown
      - should_early_stop: stagnation (delta < threshold) >= window_size
      - should_escalate: falling trend >= escalation_count итераций подряд

    Использование:
      monitor = UncertaintyMonitor()
      monitor.reset()  # перед каждым reasoning run
      snapshot = monitor.update(state)  # на каждой итерации
    """

    def __init__(
        self,
        window_size: int = 5,
        stagnation_threshold: float = 0.02,
        escalation_count: int = 3,
    ):
        """
        Args:
            window_size:          окно для определения stagnation
            stagnation_threshold: порог delta для "stable" (|delta| < threshold)
            escalation_count:     сколько falling итераций подряд → escalate
        """
        self._window_size = window_size
        self._stagnation_threshold = stagnation_threshold
        self._escalation_count = escalation_count

        # Internal state
        self._history: deque = deque(maxlen=50)  # confidence history
        self._stagnation_counter: int = 0
        self._falling_counter: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, state: ReasoningState) -> UncertaintySnapshot:
        """
        Обновить монитор с текущим состоянием reasoning loop.

        Args:
            state: текущий ReasoningState (используется current_confidence)

        Returns:
            UncertaintySnapshot с текущим анализом
        """
        confidence = state.current_confidence
        iteration = state.iteration

        self._history.append(confidence)

        # Compute delta
        if len(self._history) >= 2:
            delta = confidence - self._history[-2]
        else:
            delta = 0.0

        # Determine trend
        trend = self._compute_trend(delta)

        # Update counters
        self._update_counters(trend, delta)

        # Build snapshot
        snapshot = UncertaintySnapshot(
            confidence=confidence,
            trend=trend.value,  # str for ContractMixin compatibility
            delta=round(delta, 6),
            iteration=iteration,
            should_stop=self.should_early_stop(),
            should_escalate=self.should_escalate(),
            history_length=len(self._history),
        )

        logger.debug(
            "[UncertaintyMonitor] iter=%d conf=%.3f delta=%.4f trend=%s "
            "stagnation=%d falling=%d",
            iteration, confidence, delta, trend.value,
            self._stagnation_counter, self._falling_counter,
        )

        return snapshot

    def get_trend(self) -> UncertaintyTrend:
        """
        Получить текущий тренд на основе последних данных.

        Returns:
            UncertaintyTrend enum value
        """
        if len(self._history) < 2:
            return UncertaintyTrend.UNKNOWN

        delta = self._history[-1] - self._history[-2]
        return self._compute_trend(delta)

    def should_early_stop(self) -> bool:
        """
        Рекомендация остановить reasoning из-за stagnation.

        True если confidence стагнирует >= window_size итераций подряд.
        """
        return self._stagnation_counter >= self._window_size

    def should_escalate(self) -> bool:
        """
        Рекомендация эскалировать из-за falling trend.

        True если confidence падает >= escalation_count итераций подряд.
        """
        return self._falling_counter >= self._escalation_count

    def reset(self) -> None:
        """
        Сбросить состояние монитора.

        Обязательно вызывать между reasoning runs.
        """
        self._history.clear()
        self._stagnation_counter = 0
        self._falling_counter = 0

    @property
    def history(self) -> List[float]:
        """Копия истории confidence (для тестов/отладки)."""
        return list(self._history)

    @property
    def stagnation_counter(self) -> int:
        """Текущий счётчик stagnation."""
        return self._stagnation_counter

    @property
    def falling_counter(self) -> int:
        """Текущий счётчик falling."""
        return self._falling_counter

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute_trend(self, delta: float) -> UncertaintyTrend:
        """Определить тренд по delta."""
        if len(self._history) < 2:
            return UncertaintyTrend.UNKNOWN

        if abs(delta) < self._stagnation_threshold:
            return UncertaintyTrend.STABLE
        if delta > 0:
            return UncertaintyTrend.RISING
        return UncertaintyTrend.FALLING

    def _update_counters(self, trend: UncertaintyTrend, delta: float) -> None:
        """Обновить счётчики stagnation и falling."""
        # Stagnation counter
        if trend == UncertaintyTrend.STABLE:
            self._stagnation_counter += 1
        else:
            self._stagnation_counter = 0

        # Falling counter
        if trend == UncertaintyTrend.FALLING:
            self._falling_counter += 1
        else:
            self._falling_counter = 0
