"""
output — Слой вывода (формирование ответов и объяснений).

Модули:
    trace_builder.py       — ExplainabilityTrace + OutputTraceBuilder
    response_validator.py  — ValidationIssue + ValidationResult + ResponseValidator
    dialogue_responder.py  — DialogueResponder + OutputPipeline + hedging phrases

Использование:
    from brain.output import OutputPipeline
    pipeline = OutputPipeline()
    brain_output = pipeline.process(cognitive_result)
"""

from .dialogue_responder import (
    FALLBACK_TEMPLATES_EN,
    FALLBACK_TEMPLATES_RU,
    HEDGING_PHRASES_EN,
    HEDGING_PHRASES_RU,
    DialogueResponder,
    OutputPipeline,
)
from .response_validator import (
    FALLBACK_RESPONSE_EN,
    FALLBACK_RESPONSE_RU,
    ResponseValidator,
    ValidationIssue,
    ValidationResult,
)
from .trace_builder import (
    ExplainabilityTrace,
    OutputTraceBuilder,
)

__all__ = [
    # trace_builder
    "ExplainabilityTrace",
    "OutputTraceBuilder",
    # response_validator
    "ValidationIssue",
    "ValidationResult",
    "ResponseValidator",
    "FALLBACK_RESPONSE_RU",
    "FALLBACK_RESPONSE_EN",
    # dialogue_responder
    "DialogueResponder",
    "OutputPipeline",
    "HEDGING_PHRASES_RU",
    "HEDGING_PHRASES_EN",
    "FALLBACK_TEMPLATES_RU",
    "FALLBACK_TEMPLATES_EN",
]
