# brain.output — Слой вывода

Формирование ответов, валидация, построение трейсов. Аналог речевых центров.

---

## DialogueResponder

Генерация текстовых ответов на основе шаблонов (без LLM).

::: brain.output.dialogue_responder.DialogueResponder
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - respond
        - format_response

---

## ResponseValidator

Валидация ответов: логическая консистентность, длина, формат.

::: brain.output.response_validator.ResponseValidator
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - validate
        - autocorrect

---

## TraceBuilder

Построение цепочки трейсов для observability.

::: brain.output.trace_builder.TraceBuilder
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - build
        - add_step
        - finalize
