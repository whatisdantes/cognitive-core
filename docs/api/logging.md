# brain.logging — Логирование и наблюдаемость

Структурированное логирование, дайджесты, трейсинг рассуждений. Аналог метакогниции.

---

## BrainLogger

Структурированный логгер с TTL/LRU индексами, ротацией файлов и категорийными потоками.

::: brain.logging.brain_logger.BrainLogger
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - log
        - log_cycle
        - log_memory_event
        - log_reasoning_step
        - get_session_traces
        - rotate
        - status

---

## DigestGenerator

Генерация периодических дайджестов активности системы.

::: brain.logging.digest_generator.DigestGenerator
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - generate
        - generate_session_digest

---

## ReasoningTracer

Трейсинг шагов рассуждения для отладки и анализа.

::: brain.logging.reasoning_tracer.ReasoningTracer
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - start_trace
        - add_step
        - finish_trace
        - get_trace
