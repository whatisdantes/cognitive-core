# TODO Stage G — Output MVP (Explainable Output)

> **Версия:** v1 (2026-03-24)
> **Цель:** `brain/output/` — минимальный output pipeline
> **Оценка:** ~12 часов реализации + тесты

---

## Принятые решения (из ревью + ChatGPT feedback)

1. **ExplainabilityTrace — минимальный набор полей**, без дублирования TraceChain
   - reasoning_chain и alternatives_considered → опциональные (в metadata)
2. **ResponseValidator — output consistency**, НЕ safety layer
   - Автокоррекция: пустой ответ, длина, hedge при low confidence
   - Только флаг (без автокоррекции): language mismatch
3. **DialogueResponder — только рендерит**, не принимает решений за cognition
   - ActionSelector решает тип → DialogueResponder рендерит шаблон
4. **Явные fallback-тексты** на каждый ActionType + fallback для пустого response
5. **BrainOutput.metadata** стабильно содержит: reasoning_type, uncertainty_level, validation_issues, language, output_style
6. **contracts.py без изменений** — BrainOutput используется как есть

---

## Шаги реализации

### Шаг 1: [x] `brain/output/trace_builder.py` — Output Trace Builder
- [x] ExplainabilityTrace dataclass (ContractMixin):
  - trace_id, session_id, cycle_id
  - input_query, reasoning_type, key_inferences
  - action_taken, confidence
  - uncertainty_level, uncertainty_reasons, contradictions_found
  - memory_facts: List[TraceRef]
  - total_duration_ms, created_at
  - metadata: Dict (для reasoning_chain, alternatives и т.д.)
- [x] OutputTraceBuilder class:
  - build(cognitive_result) → ExplainabilityTrace
  - to_digest(trace) → str (human-readable)
  - to_json(trace) → Dict (machine-readable)

### Шаг 2: [x] `brain/output/response_validator.py` — Output Consistency Validator
- [x] ValidationIssue dataclass (ContractMixin):
  - issue_type, severity, description, correction
- [x] ValidationResult dataclass (ContractMixin):
  - is_valid, issues, corrected_response, applied_corrections
- [x] ResponseValidator class:
  - validate(cognitive_result) → ValidationResult
  - Автокоррекция:
    1. Пустой ответ → fallback message (CRITICAL)
    2. Low confidence без hedge → добавить hedge (WARNING)
    3. Слишком длинный (>2000) → обрезать (WARNING)
  - Только флаг:
    4. Language mismatch → INFO (без автокоррекции)

### Шаг 3: [x] `brain/output/dialogue_responder.py` — Dialogue Responder + Pipeline
- [x] HEDGING_PHRASES_RU / HEDGING_PHRASES_EN dicts по confidence bands
- [x] FALLBACK_TEMPLATES dict для каждого ActionType
- [x] DialogueResponder class:
  - generate(cognitive_result, validation, trace) → BrainOutput
  - Только рендерит шаблон по ActionType (не принимает решений)
  - Стабильный metadata: reasoning_type, uncertainty_level, validation_issues, language, output_style
- [x] OutputPipeline class:
  - process(cognitive_result) → BrainOutput
  - Цепочка: trace_builder → validator → responder → BrainOutput

### Шаг 4: [x] `brain/output/__init__.py` — Экспорты
- [x] __all__ со всеми публичными классами

### Шаг 5: [x] `tests/test_output.py` — Unit тесты (~80-100)
- [x] TestExplainabilityTrace (~8)
- [x] TestOutputTraceBuilder (~15)
- [x] TestValidationIssue (~6)
- [x] TestValidationResult (~6)
- [x] TestResponseValidator (~20)
- [x] TestDialogueResponder (~20)
- [x] TestOutputPipeline (~15)
- [x] TestImports (~4)
- [x] Дополнительные проверки:
  - RESPOND_HEDGED ≠ RESPOND_DIRECT
  - Стабильный шаблон при одинаковом input
  - Validator не ломает trace_id/confidence/action
  - Pipeline работает при response == ""
  - Pipeline работает при пустых uncertainty/contradictions

### Шаг 6: [x] `tests/test_output_integration.py` — Integration smoke tests (~5-7)
- [x] CognitiveCore.run() → OutputPipeline.process() → BrainOutput
- [x] BrainOutput имеет text, confidence, trace_id, digest
- [x] Разные типы запросов → разные стили ответа

### Шаг 7: [x] Финальная проверка и коммит
- [x] `pytest tests/ -v` — все тесты (611 total, план ~580+)
- [x] README.md обновлён (v0.6.0, output section, тесты, прогресс)
- [x] pyproject.toml → v0.6.0
- [x] docs/TODO.md — Stage G marked ✅
- [ ] Коммит + push

---

## Что НЕ входит в Stage G (отложено)

- ActionProposer (предложение действий)
- ExplanationBuilder (расширенные объяснения)
- Полноценный safety layer (brain/safety/)
- LLM-based response generation
- Multi-language auto-translation
