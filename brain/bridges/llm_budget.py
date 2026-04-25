"""Общий rate limit для LLM-вызовов."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple


@dataclass
class LLMRateLimitConfig:
    """Настройки часового бюджета LLM-вызовов."""
    llm_calls_per_hour: int = 20
    window_seconds: float = 3600.0


class LLMRateLimiter:
    """
    Скользящий часовой лимитер для всех LLM users.

    `allow()` только проверяет бюджет, `record()` фиксирует реальный вызов.
    Это позволяет компонентам деградировать до offline/regex-only режима до
    обращения к провайдеру.
    """

    def __init__(self, config: Optional[LLMRateLimitConfig] = None) -> None:
        self._config = config or LLMRateLimitConfig()
        self._calls: Deque[Tuple[float, str]] = deque()
        self._lock = threading.RLock()

    @property
    def config(self) -> LLMRateLimitConfig:
        """Текущая конфигурация лимитера."""
        return self._config

    def allow(self, purpose: str, now: Optional[float] = None) -> bool:
        """True если для `purpose` можно выполнить LLM-вызов."""
        del purpose  # purpose сохраняется в record(); allow проверяет общий бюджет
        ts = time.time() if now is None else now
        with self._lock:
            self._prune(ts)
            return len(self._calls) < self._config.llm_calls_per_hour

    def record(self, purpose: str, now: Optional[float] = None) -> None:
        """Записать факт реального LLM-вызова."""
        ts = time.time() if now is None else now
        with self._lock:
            self._prune(ts)
            self._calls.append((ts, purpose))

    def remaining(self, now: Optional[float] = None) -> int:
        """Остаток LLM-вызовов в текущем часовом окне."""
        ts = time.time() if now is None else now
        with self._lock:
            self._prune(ts)
            return max(0, self._config.llm_calls_per_hour - len(self._calls))

    def usage_by_purpose(self, now: Optional[float] = None) -> Dict[str, int]:
        """Счётчик использованных вызовов по purpose в текущем окне."""
        ts = time.time() if now is None else now
        with self._lock:
            self._prune(ts)
            usage: Dict[str, int] = {}
            for _, purpose in self._calls:
                usage[purpose] = usage.get(purpose, 0) + 1
            return usage

    def _prune(self, now: float) -> None:
        """Удалить вызовы за пределами окна."""
        cutoff = now - self._config.window_seconds
        while self._calls and self._calls[0][0] <= cutoff:
            self._calls.popleft()
