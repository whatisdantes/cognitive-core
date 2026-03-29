"""
brain/bridges/safety_wrapper.py

LLM Safety Wrapper — декоратор над LLMBridge, реализующий LLMProvider Protocol.

Архитектура (Decorator pattern):
    Pipeline → LLMSafetyWrapper (LLMProvider) → LLMBridge → LLMProvider impl

Проверки:
  - Длина промпта (max_prompt_length)
  - Запрещённые паттерны (prompt injection, jailbreak)
  - Rate limiting (in-memory, resets on restart)

NOTE: Rate limit хранится в памяти процесса — сбрасывается при перезапуске.
      Для production используйте внешний rate limiter (Redis, etc.).

Использование:
    bridge = LLMBridge(provider=OpenAIProvider(api_key="sk-..."))
    safety = LLMSafetyWrapper(bridge=bridge, max_prompt_length=4096)
    # safety реализует LLMProvider Protocol
    pipeline = CognitivePipeline(..., llm_provider=safety)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import List, Optional

from .llm_bridge import LLMBridge, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Исключения
# ---------------------------------------------------------------------------

class SafetyViolationError(RuntimeError):
    """Нарушение safety политики LLM запроса."""


# ---------------------------------------------------------------------------
# LLMSafetyWrapper — decorator, реализует LLMProvider Protocol
# ---------------------------------------------------------------------------

class LLMSafetyWrapper:
    """
    Декоратор над LLMBridge, реализующий LLMProvider Protocol.

    Добавляет safety проверки перед каждым запросом к LLM:
      1. Длина промпта (max_prompt_length)
      2. Запрещённые паттерны (prompt injection, jailbreak)
      3. Rate limiting (in-memory, resets on restart)

    Цепочка: Pipeline → LLMSafetyWrapper → LLMBridge → LLMProvider

    Pipeline принимает Optional[LLMProvider] и не знает о Bridge/Wrapper.
    LLMSafetyWrapper реализует LLMProvider через structural subtyping.

    NOTE: Rate limit хранится в памяти процесса — сбрасывается при перезапуске.
          Для production используйте внешний rate limiter (Redis, etc.).

    Использование:
        bridge = LLMBridge(provider=MockProvider())
        safety = LLMSafetyWrapper(bridge=bridge)
        result = safety.complete(LLMRequest(prompt="Что такое нейрон?"))
    """

    # Паттерны prompt injection / jailbreak (регистронезависимые)
    DEFAULT_BLOCKED_PATTERNS: List[str] = [
        "ignore previous instructions",
        "ignore all previous",
        "disregard previous",
        "forget your instructions",
        "forget all instructions",
        "you are now",
        "act as if",
        "pretend you are",
        "pretend to be",
        "system prompt",
        "jailbreak",
        "dan mode",
        "developer mode",
        "override safety",
        "bypass safety",
    ]

    def __init__(
        self,
        bridge: LLMBridge,
        max_prompt_length: int = 4096,
        max_requests_per_minute: int = 60,
        blocked_patterns: Optional[List[str]] = None,
    ) -> None:
        """
        Инициализация LLMSafetyWrapper.

        Args:
            bridge:                  LLMBridge для делегирования запросов
            max_prompt_length:       максимальная длина промпта в символах
            max_requests_per_minute: максимальное количество запросов в минуту
                                     NOTE: in-memory, resets on restart
            blocked_patterns:        список запрещённых паттернов (None = DEFAULT)
        """
        self._bridge = bridge
        self._max_prompt_length = max_prompt_length
        self._max_rpm = max_requests_per_minute
        self._blocked_patterns = (
            blocked_patterns
            if blocked_patterns is not None
            else self.DEFAULT_BLOCKED_PATTERNS
        )

        # NOTE: in-memory rate limit, resets on restart
        self._request_timestamps: List[float] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # LLMProvider Protocol — публичный интерфейс
    # ------------------------------------------------------------------

    def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Выполнить запрос с safety проверками.

        Порядок:
          1. _check_prompt() — длина + запрещённые паттерны
          2. _check_rate_limit() — rate limiting
          3. bridge.complete() — делегирование в LLMBridge

        Raises:
            SafetyViolationError: при нарушении safety политики
            LLMUnavailableError:  при недоступности LLM
        """
        self._check_prompt(request.prompt)
        if request.system_prompt:
            self._check_prompt(request.system_prompt)
        self._check_rate_limit()

        response = self._bridge.complete(request)

        logger.info(
            "[LLMSafetyWrapper] complete OK: provider=%s tokens=%d latency=%.1fms",
            response.provider,
            response.tokens_used,
            response.latency_ms,
        )
        return response

    def is_available(self) -> bool:
        """Проверить доступность провайдера через bridge."""
        return self._bridge.is_available()

    @property
    def provider_name(self) -> str:
        """Название провайдера (делегируется в bridge)."""
        return self._bridge.provider_name

    # ------------------------------------------------------------------
    # Safety проверки
    # ------------------------------------------------------------------

    def _check_prompt(self, prompt: str) -> None:
        """
        Проверить промпт на длину и запрещённые паттерны.

        Raises:
            SafetyViolationError: при нарушении
        """
        # Проверка длины
        if len(prompt) > self._max_prompt_length:
            raise SafetyViolationError(
                f"Промпт слишком длинный: {len(prompt)} символов "
                f"(максимум: {self._max_prompt_length})"
            )

        # Проверка запрещённых паттернов (регистронезависимо)
        prompt_lower = prompt.lower()
        for pattern in self._blocked_patterns:
            if pattern.lower() in prompt_lower:
                logger.warning(
                    "[LLMSafetyWrapper] заблокирован запрещённый паттерн: '%s'",
                    pattern,
                )
                raise SafetyViolationError(
                    f"Обнаружен запрещённый паттерн в промпте: '{pattern}'"
                )

    def _check_rate_limit(self) -> None:
        """
        Проверить rate limit (in-memory, resets on restart).

        NOTE: Rate limit хранится в памяти процесса — сбрасывается при перезапуске.
              Для production используйте внешний rate limiter (Redis, etc.).

        Raises:
            SafetyViolationError: при превышении rate limit
        """
        now = time.time()
        with self._lock:
            # Удалить записи старше 60 секунд (скользящее окно)
            self._request_timestamps = [
                ts for ts in self._request_timestamps
                if now - ts < 60.0
            ]
            if len(self._request_timestamps) >= self._max_rpm:
                raise SafetyViolationError(
                    f"Rate limit превышен: {self._max_rpm} запросов/минуту "
                    f"(текущих: {len(self._request_timestamps)}). "
                    f"NOTE: in-memory rate limit, resets on restart."
                )
            self._request_timestamps.append(now)

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """Статус safety wrapper для observability."""
        now = time.time()
        with self._lock:
            recent = [ts for ts in self._request_timestamps if now - ts < 60.0]
        return {
            "provider": self._bridge.provider_name,
            "available": self._bridge.is_available(),
            "max_prompt_length": self._max_prompt_length,
            "max_rpm": self._max_rpm,
            "requests_last_minute": len(recent),
            "blocked_patterns_count": len(self._blocked_patterns),
        }
