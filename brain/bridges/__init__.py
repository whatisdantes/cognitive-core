"""
bridges — Мосты к внешним системам (LLM, базы данных, API).

Реализованные модули (Этап N):
    llm_bridge.py      — LLMProvider Protocol, LLMRequest, LLMResponse,
                         LLMBridge, MockProvider, OpenAIProvider, AnthropicProvider
    safety_wrapper.py  — LLMSafetyWrapper (decorator pattern, реализует LLMProvider)

Архитектура (Decorator pattern):
    Pipeline → LLMProvider (Protocol)
                    ↑
              LLMSafetyWrapper  (реализует LLMProvider, добавляет safety)
                    ↓
                LLMBridge       (owns provider, retry + timeout + logging)
                    ↓
              LLMProvider impl: MockProvider | OpenAIProvider | AnthropicProvider

Быстрый старт:
    from brain.bridges import MockProvider, LLMBridge, LLMSafetyWrapper, LLMRequest

    provider = MockProvider()
    bridge   = LLMBridge(provider=provider)
    safety   = LLMSafetyWrapper(bridge=bridge)
    response = safety.complete(LLMRequest(prompt="Что такое нейрон?"))
"""

from .llm_bridge import (
    AnthropicProvider,
    LLMBridge,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    LLMUnavailableError,
    MockProvider,
    OpenAIProvider,
)
from .safety_wrapper import LLMSafetyWrapper, SafetyViolationError

__all__ = [
    # Протокол (DI-интерфейс)
    "LLMProvider",
    # Контракты
    "LLMRequest",
    "LLMResponse",
    # Исключения
    "LLMUnavailableError",
    "SafetyViolationError",
    # Провайдеры
    "MockProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    # Bridge (utility, НЕ реализует LLMProvider)
    "LLMBridge",
    # Safety wrapper (реализует LLMProvider, decorator pattern)
    "LLMSafetyWrapper",
]
