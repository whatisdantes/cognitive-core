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

## OutputTraceBuilder

Построение explainability-trace для output layer.

::: brain.output.trace_builder.OutputTraceBuilder
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - build
        - to_digest
        - to_json
