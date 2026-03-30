# TODO: Интеграция BrainLogger (LOG_PLAN.md v2.0)

## Прогресс

- [x] Фаза 0a: brain/logging/brain_logger.py — NullBrainLogger + _NULL_LOGGER
- [x] Фаза 0b: brain/logging/reasoning_tracer.py — NullTraceBuilder + _NULL_TRACE_BUILDER
- [x] Фаза 0c: brain/logging/__init__.py — экспорт NullBrainLogger, NullTraceBuilder
- [x] Фаза 1:  brain/cli.py — --log-dir, --log-level, создание BrainLogger + TraceBuilder
- [x] Фаза 2:  brain/cognition/cognitive_core.py — brain_logger + digest_gen + trace_builder
- [x] Фаза 2b: brain/logging/digest_generator.py — CycleInfo.from_result()
- [x] Фаза 3:  brain/cognition/pipeline.py — auto-timing + 9 событий + TraceBuilder
- [x] Фаза 4:  brain/memory/memory_manager.py — store/retrieve logging
- [x] Фаза 5:  brain/perception/input_router.py — route logging
- [x] Фаза 6:  brain/output/dialogue_responder.py — OutputPipeline logging
- [x] Фаза 7a: brain/core/event_bus.py — publish + error logging
- [x] Фаза 7b: brain/core/scheduler.py — tick + task logging
- [x] Фаза 9:  tests/test_brain_logger_integration.py — 19 тестов
