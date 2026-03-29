# ADR-005: Шаблонные ответы без LLM на MVP-этапе

**Статус:** ✅ Принято  
**Дата:** 2025-06  
**Авторы:** cognitive-core contributors

---

## Контекст

`DialogueResponder` должен формировать текстовые ответы пользователю. Система имеет `ActionSelector`, который определяет тип действия (`respond_direct`, `respond_hedged`, `ask_clarification`, `refuse`, `learn`). Вопрос: как генерировать текст ответа?

## Рассмотренные варианты

### Вариант 1: LLM (OpenAI GPT / Anthropic Claude / local Llama)
**Плюсы:** Естественный язык, гибкость, контекстуальность  
**Минусы:** Внешний API (зависимость, стоимость, latency); local LLM требует GPU или много RAM; не соответствует CPU-only платформе; усложняет тестирование (недетерминированность)

### Вариант 2: Шаблоны по `ActionType` с hedging phrases
**Плюсы:** Детерминированность, тестируемость, нет внешних зависимостей, быстро  
**Минусы:** Ограниченная выразительность, шаблонность ответов

### Вариант 3: Retrieval-Augmented Generation (RAG) без LLM
**Плюсы:** Использует реальные факты из памяти  
**Минусы:** Без LLM сложно связно объединить факты в текст

## Решение

Выбраны **шаблонные ответы** на MVP-этапе с явным TODO для LLM Bridge (Этап N).

Реализация в `brain/output/dialogue_responder.py`:

```python
FALLBACK_TEMPLATES_RU = {
    "respond_direct":    "Ответ на ваш вопрос.",
    "respond_hedged":    "Возможно, ответ связан с данной темой.",
    "ask_clarification": "Уточните, пожалуйста, ваш вопрос.",
    "refuse":            "У меня недостаточно данных для ответа.",
    "learn":             "Факт сохранён.",
}

# Hedging phrases по confidence bands
HEDGING_PHRASES_RU = {
    (0.75, 1.01): [],                                    # без оговорок
    (0.60, 0.75): ["Вероятно,", "Скорее всего,"],
    (0.45, 0.60): ["Возможно,", "Я думаю,"],
    (0.30, 0.45): ["Не уверен, но", "Предположительно,"],
    (0.00, 0.30): ["Очень неуверенно:", "Это лишь предположение:"],
}
```

Ответ формируется как: `[hedging_phrase] [template_or_content]`

## Последствия

**Положительные:**
- 100% детерминированные ответы — тесты стабильны
- Нет внешних зависимостей — работает offline
- Быстро (< 1ms на генерацию)
- Явная точка расширения: `TODO: LLM bridge Stage H+` в коде

**Отрицательные:**
- Ответы шаблонные — не подходят для production демо
- Нет контекстуальной генерации текста

**Нейтральные:**
- `OutputPipeline` спроектирован так, что замена `DialogueResponder` на LLM-версию не требует изменений в остальных компонентах
- Двуязычность (RU/EN) через `detect_language()` из `brain/core/text_utils.py`

## Путь к LLM Bridge (Этап N)

```
brain/bridges/llm_bridge.py
├── LLMBridgeProtocol  — абстракция (generate(prompt) -> str)
├── OpenAIBridge       — OpenAI API
├── AnthropicBridge    — Anthropic API
└── LocalLlamaBridge   — llama.cpp / ollama
```

`DialogueResponder` получит опциональный `llm_bridge: Optional[LLMBridgeProtocol]` — при наличии использует LLM, иначе шаблоны.

## Связанные решения

- ADR-007: CPU-only платформа — причина отложить LLM
- TODO.md P3-13: LLM Bridge — стратегический unlock
