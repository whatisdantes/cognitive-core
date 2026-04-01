"""
brain/bridges/llm_bridge.py

LLM Bridge — абстракция для подключения языковых моделей (Этап N).

Архитектура (Decorator pattern):
    Pipeline → LLMProvider (Protocol)
                    ↑
              LLMSafetyWrapper  (реализует LLMProvider, добавляет safety)
                    ↓
                LLMBridge       (owns provider, retry + timeout + logging)
                    ↓
              LLMProvider impl: MockProvider | OpenAIProvider | AnthropicProvider | BlackboxProvider

Принципы:
  - LLMProvider — Protocol (@runtime_checkable), DI-совместимый
  - LLMBridge   — НЕ реализует LLMProvider, это utility-обёртка с retry/timeout
  - LLMSafetyWrapper — реализует LLMProvider (decorator pattern)
  - Pipeline принимает Optional[LLMProvider], не знает о Bridge/Wrapper
  - Все провайдеры опциональны (try/except ImportError), graceful fallback
  - MockProvider всегда доступен (для тестов и --llm-provider mock)
  - CPU-only совместимость: timeout через threading.Thread, без asyncio

Использование:
    # Минимальный (тест/демо):
    provider = MockProvider(response_text="Тестовый ответ")
    bridge = LLMBridge(provider=provider)
    safety = LLMSafetyWrapper(bridge=bridge)
    pipeline = CognitivePipeline(..., llm_provider=safety)

    # OpenAI:
    provider = OpenAIProvider(api_key="sk-...", model="gpt-4o-mini")
    bridge = LLMBridge(provider=provider, timeout_s=30.0, max_retries=2)
    safety = LLMSafetyWrapper(bridge=bridge, max_prompt_length=4096)
    pipeline = CognitivePipeline(..., llm_provider=safety)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from brain.core.contracts import ContractMixin

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Контракты (ContractMixin — сериализуемые)
# ---------------------------------------------------------------------------

@dataclass
class LLMRequest(ContractMixin):
    """
    Запрос к LLM провайдеру.

    Поля:
        prompt:          основной текст запроса
        system_prompt:   системный промпт (роль/инструкции)
        max_tokens:      максимальное количество токенов в ответе
        temperature:     температура генерации (0.0 = детерминированно)
        stop_sequences:  последовательности для остановки генерации
        metadata:        произвольные метаданные (trace_id, cycle_id и т.д.)
    """
    prompt: str
    system_prompt: str = ""
    max_tokens: int = 512
    temperature: float = 0.7
    stop_sequences: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse(ContractMixin):
    """
    Ответ от LLM провайдера.

    Поля:
        text:          текст ответа
        model:         название модели
        provider:      название провайдера (openai, anthropic, mock)
        tokens_used:   количество использованных токенов
        latency_ms:    задержка запроса в миллисекундах
        finish_reason: причина завершения (stop, length, content_filter)
        metadata:      произвольные метаданные
    """
    text: str
    model: str = ""
    provider: str = ""
    tokens_used: int = 0
    latency_ms: float = 0.0
    finish_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Исключения
# ---------------------------------------------------------------------------

class LLMUnavailableError(RuntimeError):
    """LLM провайдер недоступен или вернул ошибку."""


# ---------------------------------------------------------------------------
# LLMProvider — Protocol (DI-совместимый интерфейс)
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMProvider(Protocol):
    """
    Формальный интерфейс LLM провайдера для dependency injection.

    Любой объект с методами complete(), is_available() и свойством
    provider_name удовлетворяет этому протоколу (structural subtyping).

    Реализации:
        MockProvider      — заглушка для тестов (всегда доступна)
        OpenAIProvider    — OpenAI API (опциональный, openai>=1.0)
        AnthropicProvider — Anthropic API (опциональный, anthropic>=0.20)
        LLMSafetyWrapper  — decorator, реализует LLMProvider поверх LLMBridge
    """

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Выполнить запрос к LLM. Возвращает LLMResponse."""
        ...

    def is_available(self) -> bool:
        """Проверить доступность провайдера."""
        ...

    @property
    def provider_name(self) -> str:
        """Название провайдера (openai, anthropic, mock, ...)."""
        ...


# ---------------------------------------------------------------------------
# MockProvider — заглушка для тестов (всегда доступна)
# ---------------------------------------------------------------------------

class MockProvider:
    """
    Заглушка LLM провайдера для тестов и демо.

    Всегда доступна, не требует внешних зависимостей.
    Возвращает фиксированный или шаблонный ответ.

    Использование:
        provider = MockProvider(response_text="Тестовый ответ")
        provider = MockProvider()  # ответ по умолчанию
    """

    def __init__(
        self,
        response_text: str = "Ответ от MockProvider. LLM не подключён.",
        latency_ms: float = 0.0,
    ) -> None:
        self._response_text = response_text
        self._latency_ms = latency_ms

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Вернуть фиксированный ответ (без реального LLM вызова)."""
        if self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000.0)
        return LLMResponse(
            text=self._response_text,
            model="mock",
            provider="mock",
            tokens_used=len(request.prompt.split()),
            latency_ms=self._latency_ms,
            finish_reason="stop",
            metadata={"mock": True},
        )

    def is_available(self) -> bool:
        """MockProvider всегда доступен."""
        return True

    @property
    def provider_name(self) -> str:
        return "mock"


# ---------------------------------------------------------------------------
# OpenAIProvider — опциональный (требует openai>=1.0)
# ---------------------------------------------------------------------------

class OpenAIProvider:
    """
    OpenAI LLM провайдер.

    Требует: pip install openai>=1.0
    Если openai не установлен — is_available() возвращает False,
    complete() выбрасывает LLMUnavailableError.

    Использование:
        provider = OpenAIProvider(api_key="sk-...", model="gpt-4o-mini")
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
    ) -> None:
        self._model = model
        self._client: Any = None
        self._available = False

        try:
            import openai  # type: ignore[import]
            self._client = openai.OpenAI(api_key=api_key)
            self._available = True
            logger.info("[OpenAIProvider] инициализирован: model=%s", model)
        except ImportError:
            logger.warning(
                "[OpenAIProvider] openai не установлен. "
                "Установите: pip install openai>=1.0"
            )

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Выполнить запрос через OpenAI Chat Completions API."""
        if not self._available or self._client is None:
            raise LLMUnavailableError(
                "OpenAI провайдер недоступен. Установите: pip install openai>=1.0"
            )

        start = time.perf_counter()

        messages: List[Dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stop=request.stop_sequences or None,
        )

        latency_ms = (time.perf_counter() - start) * 1000
        choice = response.choices[0]
        tokens_used = response.usage.total_tokens if response.usage else 0

        return LLMResponse(
            text=choice.message.content or "",
            model=self._model,
            provider="openai",
            tokens_used=tokens_used,
            latency_ms=round(latency_ms, 2),
            finish_reason=choice.finish_reason or "stop",
        )

    def is_available(self) -> bool:
        return self._available

    @property
    def provider_name(self) -> str:
        return "openai"


# ---------------------------------------------------------------------------
# AnthropicProvider — опциональный (требует anthropic>=0.20)
# ---------------------------------------------------------------------------

class AnthropicProvider:
    """
    Anthropic LLM провайдер (Claude).

    Требует: pip install anthropic>=0.20
    Если anthropic не установлен — is_available() возвращает False,
    complete() выбрасывает LLMUnavailableError.

    Использование:
        provider = AnthropicProvider(
            api_key="sk-ant-...",
            model="claude-3-haiku-20240307",
        )
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
    ) -> None:
        self._model = model
        self._client: Any = None
        self._available = False

        try:
            import anthropic  # type: ignore[import]
            self._client = anthropic.Anthropic(api_key=api_key)
            self._available = True
            logger.info("[AnthropicProvider] инициализирован: model=%s", model)
        except ImportError:
            logger.warning(
                "[AnthropicProvider] anthropic не установлен. "
                "Установите: pip install anthropic>=0.20"
            )

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Выполнить запрос через Anthropic Messages API."""
        if not self._available or self._client is None:
            raise LLMUnavailableError(
                "Anthropic провайдер недоступен. Установите: pip install anthropic>=0.20"
            )

        start = time.perf_counter()

        kwargs: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system_prompt:
            kwargs["system"] = request.system_prompt
        if request.stop_sequences:
            kwargs["stop_sequences"] = request.stop_sequences

        response = self._client.messages.create(**kwargs)

        latency_ms = (time.perf_counter() - start) * 1000
        text = response.content[0].text if response.content else ""
        tokens_used = (
            (response.usage.input_tokens + response.usage.output_tokens)
            if response.usage else 0
        )

        return LLMResponse(
            text=text,
            model=self._model,
            provider="anthropic",
            tokens_used=tokens_used,
            latency_ms=round(latency_ms, 2),
            finish_reason=response.stop_reason or "stop",
        )

    def is_available(self) -> bool:
        return self._available

    @property
    def provider_name(self) -> str:
        return "anthropic"


# ---------------------------------------------------------------------------
# BlackboxProvider — Blackbox AI (OpenAI-совместимый API)
# ---------------------------------------------------------------------------

class BlackboxProvider:
    """
    Blackbox AI LLM провайдер.

    Использует OpenAI-совместимый Chat Completions API с кастомным base_url.
    Требует: pip install openai>=1.0 (та же зависимость, что и OpenAIProvider).
    Если openai не установлен — is_available() возвращает False,
    complete() выбрасывает LLMUnavailableError.

    Использование:
        provider = BlackboxProvider(api_key="...", model="gpt-5.4")
    """

    BLACKBOX_BASE_URL = "https://api.blackbox.ai/v1"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.4",
    ) -> None:
        self._model = model
        self._client: Any = None
        self._available = False

        try:
            import openai  # type: ignore[import]
            self._client = openai.OpenAI(
                api_key=api_key,
                base_url=self.BLACKBOX_BASE_URL,
            )
            self._available = True
            logger.info("[BlackboxProvider] инициализирован: model=%s", model)
        except ImportError:
            logger.warning(
                "[BlackboxProvider] openai не установлен. "
                "Установите: pip install openai>=1.0"
            )

    def complete(self, request: LLMRequest) -> LLMResponse:
        """Выполнить запрос через Blackbox AI API (OpenAI-совместимый)."""
        if not self._available or self._client is None:
            raise LLMUnavailableError(
                "Blackbox провайдер недоступен. Установите: pip install openai>=1.0"
            )

        start = time.perf_counter()

        messages: List[Dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stop=request.stop_sequences or None,
        )

        latency_ms = (time.perf_counter() - start) * 1000
        choice = response.choices[0]
        tokens_used = response.usage.total_tokens if response.usage else 0

        return LLMResponse(
            text=choice.message.content or "",
            model=self._model,
            provider="blackbox",
            tokens_used=tokens_used,
            latency_ms=round(latency_ms, 2),
            finish_reason=choice.finish_reason or "stop",
        )

    def is_available(self) -> bool:
        return self._available

    @property
    def provider_name(self) -> str:
        return "blackbox"


# ---------------------------------------------------------------------------
# LLMBridge — utility-обёртка с retry, timeout и logging
# ---------------------------------------------------------------------------

class LLMBridge:
    """
    Utility-обёртка над LLMProvider с retry, timeout и logging.

    НЕ реализует LLMProvider Protocol.
    Используется как внутренний компонент LLMSafetyWrapper.

    Цепочка: LLMSafetyWrapper → LLMBridge → LLMProvider

    Особенности:
      - Timeout через threading.Thread (CPU-only, без asyncio)
      - Exponential backoff при retry (0.5s, 1.0s, ...)
      - LLMUnavailableError не ретраится (провайдер недоступен)
      - Логирование каждого attempt

    Использование:
        bridge = LLMBridge(
            provider=OpenAIProvider(api_key="sk-..."),
            timeout_s=30.0,
            max_retries=2,
        )
        response = bridge.complete(request)
    """

    def __init__(
        self,
        provider: LLMProvider,
        timeout_s: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._provider = provider
        self._timeout_s = timeout_s
        self._max_retries = max_retries

    def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Выполнить запрос с retry и timeout.

        Retry: max_retries попыток с exponential backoff (0.5s, 1.0s, ...).
        Timeout: через threading.Thread (CPU-only, без asyncio).
        LLMUnavailableError не ретраится.
        """
        last_error: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                result: Optional[LLMResponse] = None
                call_error: Optional[Exception] = None

                def _call() -> None:
                    nonlocal result, call_error
                    try:
                        result = self._provider.complete(request)
                    except Exception as exc:
                        call_error = exc

                thread = threading.Thread(target=_call, daemon=True)
                thread.start()
                thread.join(timeout=self._timeout_s)

                if thread.is_alive():
                    raise LLMUnavailableError(
                        f"LLM timeout после {self._timeout_s}s "
                        f"(provider={self._provider.provider_name})"
                    )
                if call_error is not None:
                    raise call_error
                if result is not None:
                    logger.debug(
                        "[LLMBridge] complete OK: provider=%s attempt=%d tokens=%d",
                        self._provider.provider_name, attempt + 1,
                        result.tokens_used,
                    )
                    return result
                raise LLMUnavailableError("LLM вернул None")

            except LLMUnavailableError:
                raise  # не ретраить unavailable / timeout
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[LLMBridge] attempt %d/%d failed (provider=%s): %s",
                    attempt + 1, self._max_retries + 1,
                    self._provider.provider_name, exc,
                )
                if attempt < self._max_retries:
                    time.sleep(0.5 * (attempt + 1))  # exponential backoff

        raise LLMUnavailableError(
            f"LLM failed after {self._max_retries + 1} attempts "
            f"(provider={self._provider.provider_name}): {last_error}"
        )

    def is_available(self) -> bool:
        """Проверить доступность провайдера."""
        return self._provider.is_available()

    @property
    def provider_name(self) -> str:
        """Название провайдера."""
        return self._provider.provider_name
