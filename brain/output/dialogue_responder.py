"""
brain/output/dialogue_responder.py

Dialogue Responder — формирование текстового ответа + Output Pipeline.

Содержит:
  - HEDGING_PHRASES_RU / HEDGING_PHRASES_EN — фразы неопределённости
  - FALLBACK_TEMPLATES — дефолтные шаблоны на каждый ActionType
  - DialogueResponder  — рендеринг ответа по ActionType
  - OutputPipeline     — orchestrator: trace → validate → respond → BrainOutput

Аналог: зона Брока — формирование речи.

DialogueResponder только рендерит шаблон по ActionType.
Он НЕ принимает решений за cognition (ActionSelector решает тип).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from brain.core.contracts import BrainOutput, CognitiveResult
from brain.core.text_utils import detect_language as _canonical_detect_language
from brain.logging import _NULL_LOGGER, BrainLogger

from .response_validator import (
    ResponseValidator,
    ValidationResult,
)
from .trace_builder import ExplainabilityTrace, OutputTraceBuilder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hedging phrases по confidence bands
# ---------------------------------------------------------------------------

HEDGING_PHRASES_RU: Dict[Tuple[float, float], List[str]] = {
    (0.75, 1.01): [],                                          # без оговорок
    (0.60, 0.75): ["Вероятно,", "Скорее всего,"],
    (0.45, 0.60): ["Возможно,", "Я думаю,", "Мне кажется,"],
    (0.30, 0.45): ["Не уверен, но", "Предположительно,"],
    (0.00, 0.30): ["Очень неуверенно:", "Это лишь предположение:"],
}

HEDGING_PHRASES_EN: Dict[Tuple[float, float], List[str]] = {
    (0.75, 1.01): [],
    (0.60, 0.75): ["Probably,", "Most likely,"],
    (0.45, 0.60): ["Perhaps,", "I think,", "It seems,"],
    (0.30, 0.45): ["I'm not sure, but", "Presumably,"],
    (0.00, 0.30): ["Very uncertain:", "This is just a guess:"],
}


# ---------------------------------------------------------------------------
# Fallback templates на каждый ActionType
# ---------------------------------------------------------------------------

FALLBACK_TEMPLATES_RU: Dict[str, str] = {
    "respond_direct":    "Ответ на ваш вопрос.",
    "respond_hedged":    "Возможно, ответ связан с данной темой.",
    "ask_clarification": "Уточните, пожалуйста, ваш вопрос.",
    "refuse":            "У меня недостаточно данных для ответа.",
    "learn":             "Факт сохранён.",
}

FALLBACK_TEMPLATES_EN: Dict[str, str] = {
    "respond_direct":    "Here is the answer to your question.",
    "respond_hedged":    "Perhaps the answer is related to this topic.",
    "ask_clarification": "Could you please clarify your question?",
    "refuse":            "I don't have enough data to answer.",
    "learn":             "Fact saved.",
}


# ---------------------------------------------------------------------------
# DialogueResponder — рендеринг ответа по ActionType
# ---------------------------------------------------------------------------

class DialogueResponder:
    """
    Формирователь текстового ответа.

    Только рендерит шаблон по ActionType — не принимает решений.
    ActionSelector решает тип → DialogueResponder рендерит текст.

    MVP Limitation:
        Текущая реализация использует шаблонный рендеринг (template-based)
        с фиксированными hedging phrases и fallback templates.
        Ответы формируются из CognitiveResult.response + confidence-based hedging.
        Нет генерации свободного текста — только подстановка шаблонов.

    TODO (Stage H+): Добавить LLM Bridge для генерации естественного языка.
        - Интеграция с внешним LLM API (OpenAI / local LLM) для свободной генерации
        - DialogueResponder.generate() → LLMBridge.render() fallback → template
        - Контроль hallucination через ResponseValidator
        - Бюджет токенов через ResourceMonitor
        См. docs/layers/07_output_layer.md для деталей архитектуры.

    Использование:
        responder = DialogueResponder()
        output = responder.generate(cognitive_result, validation, trace)
    """

    def __init__(
        self,
        trace_builder: Optional[OutputTraceBuilder] = None,
    ) -> None:
        self._trace_builder = trace_builder or OutputTraceBuilder()

    def generate(
        self,
        result: CognitiveResult,
        validation: ValidationResult,
        trace: ExplainabilityTrace,
    ) -> BrainOutput:
        """
        Сформировать BrainOutput из CognitiveResult + ValidationResult + Trace.

        Шаги:
          1. Определить язык
          2. Получить текст ответа (из validation.corrected_response)
          3. Применить шаблон по ActionType
          4. Сформировать digest
          5. Собрать metadata
          6. Вернуть BrainOutput
        """
        # --- 1. Язык ---
        lang = self._detect_language(result)

        # --- 2. Текст ответа ---
        text = validation.corrected_response or result.response or ""

        # --- 3. Шаблон по ActionType ---
        text = self._apply_template(text, result.action, result.confidence, lang)

        # --- 4. Digest ---
        digest = self._trace_builder.to_digest(trace)

        # --- 5. Metadata ---
        metadata = self._build_metadata(result, validation, trace, lang)

        # --- 6. BrainOutput ---
        return BrainOutput(
            text=text,
            confidence=result.confidence,
            trace_id=result.trace_id,
            session_id=result.session_id,
            cycle_id=result.cycle_id,
            digest=digest,
            action=result.action,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Шаблоны по ActionType
    # ------------------------------------------------------------------

    def _apply_template(
        self,
        text: str,
        action: str,
        confidence: float,
        lang: str,
    ) -> str:
        """
        Применить шаблон по ActionType.

        Если текст пустой — использовать fallback template.
        Для RESPOND_HEDGED — добавить hedging phrase если нет.
        Для LEARN — обернуть в подтверждение.
        """
        fallbacks = (
            FALLBACK_TEMPLATES_EN if lang == "en" else FALLBACK_TEMPLATES_RU
        )

        # Fallback если текст пустой
        if not text.strip():
            text = fallbacks.get(action, fallbacks.get("refuse", ""))

        # Специфичная обработка по типу
        if action == "respond_hedged":
            text = self._ensure_hedging(text, confidence, lang)
        elif action == "learn":
            text = self._format_learn(text, lang)
        elif action == "ask_clarification":
            text = self._format_clarification(text, lang)
        elif action == "refuse":
            text = self._format_refuse(text, lang)
        # respond_direct — без изменений

        return text

    def _ensure_hedging(
        self,
        text: str,
        confidence: float,
        lang: str,
    ) -> str:
        """
        Убедиться что hedged-ответ содержит hedging phrase.

        Если нет — добавить подходящую по confidence band.
        """
        phrases_dict = (
            HEDGING_PHRASES_EN if lang == "en" else HEDGING_PHRASES_RU
        )

        # Проверяем наличие hedge
        text_lower = text.lower()
        all_phrases = []
        for phrases in phrases_dict.values():
            all_phrases.extend(phrases)

        has_hedge = any(p.lower() in text_lower for p in all_phrases if p)
        if has_hedge:
            return text

        # Подбираем phrase по confidence band
        hedge_phrase = self._get_hedge_phrase(confidence, lang)
        if not hedge_phrase:
            return text

        # Добавляем prefix
        if text and text[0].isupper():
            return f"{hedge_phrase} {text[0].lower()}{text[1:]}"
        return f"{hedge_phrase} {text}"

    def _format_learn(self, text: str, lang: str) -> str:
        """Форматировать ответ для LEARN action."""
        # Если текст уже содержит подтверждение — оставить
        confirm_markers_ru = ["сохран", "запомн", "учт", "запис"]
        confirm_markers_en = ["saved", "stored", "remembered", "noted"]
        markers = confirm_markers_en if lang == "en" else confirm_markers_ru

        text_lower = text.lower()
        if any(m in text_lower for m in markers):
            return text

        # Добавить подтверждение
        if lang == "en":
            return f"Noted. {text}" if text else "Fact saved."
        return f"Принято. {text}" if text else "Факт сохранён."

    def _format_clarification(self, text: str, lang: str) -> str:
        """Форматировать ответ для ASK_CLARIFICATION."""
        # Если текст уже содержит вопрос — оставить
        if "?" in text:
            return text

        # Добавить вопросительную форму
        if lang == "en":
            return f"{text} Could you clarify?" if text else "Could you please clarify your question?"
        return f"{text} Можете уточнить?" if text else "Уточните, пожалуйста, ваш вопрос."

    def _format_refuse(self, text: str, lang: str) -> str:
        """Форматировать ответ для REFUSE."""
        # Без изменений — текст уже содержит отказ из ActionSelector
        return text

    # ------------------------------------------------------------------
    # Hedging phrases
    # ------------------------------------------------------------------

    @staticmethod
    def _get_hedge_phrase(confidence: float, lang: str) -> str:
        """Получить hedging phrase по confidence band."""
        phrases_dict = (
            HEDGING_PHRASES_EN if lang == "en" else HEDGING_PHRASES_RU
        )

        for (low, high), phrases in phrases_dict.items():
            if low <= confidence < high and phrases:
                return phrases[0]

        return ""

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _build_metadata(
        result: CognitiveResult,
        validation: ValidationResult,
        trace: ExplainabilityTrace,
        lang: str,
    ) -> Dict[str, Any]:
        """
        Собрать стабильный metadata для BrainOutput.

        Стабильные ключи:
          - reasoning_type
          - uncertainty_level
          - validation_issues
          - language
          - output_style
        """
        # Validation issues summary
        validation_issues = [
            {
                "type": issue.issue_type,
                "severity": issue.severity,
            }
            for issue in validation.issues
        ]

        # Output style
        output_style = result.action
        if result.action == "respond_hedged":
            output_style = f"hedged_{trace.uncertainty_level}"

        return {
            "reasoning_type": trace.reasoning_type,
            "uncertainty_level": trace.uncertainty_level,
            "validation_issues": validation_issues,
            "language": lang,
            "output_style": output_style,
            "corrections_applied": validation.applied_corrections,
            "goal_type": (result.metadata or {}).get("goal_type", ""),
            "total_duration_ms": trace.total_duration_ms,
        }

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_language(result: CognitiveResult) -> str:
        """
        Определить язык из CognitiveResult.

        Адаптер: сначала проверяет metadata, затем делегирует
        в каноническую detect_language() для текстового анализа goal.
        """
        meta = result.metadata or {}
        lang: str = str(meta.get("language", "") or "")
        if lang:
            return lang

        # Fallback: определить по тексту goal через каноническую функцию
        goal = result.goal or ""
        if not goal:
            return "ru"  # default

        detected: str = str(_canonical_detect_language(goal))
        # Каноническая функция возвращает 'unknown'/'mixed' — для output default 'ru'
        if detected in ("unknown", "mixed"):
            return "ru"
        return detected


# ---------------------------------------------------------------------------
# OutputPipeline — orchestrator
# ---------------------------------------------------------------------------

class OutputPipeline:
    """
    Orchestrator output layer.

    Цепочка: trace_builder → validator → responder → BrainOutput.

    Использование:
        pipeline = OutputPipeline()
        output = pipeline.process(cognitive_result)
    """

    def __init__(
        self,
        trace_builder: Optional[OutputTraceBuilder] = None,
        validator: Optional[ResponseValidator] = None,
        responder: Optional[DialogueResponder] = None,
        hedge_threshold: Optional[float] = None,
        brain_logger: Optional[BrainLogger] = None,
    ) -> None:
        self._trace_builder = trace_builder or OutputTraceBuilder()
        # Если передан hedge_threshold и нет кастомного validator — создаём
        # ResponseValidator с указанным порогом. Иначе — дефолт (0.6).
        if validator is not None:
            self._validator = validator
        elif hedge_threshold is not None:
            self._validator = ResponseValidator(
                hedge_confidence_threshold=hedge_threshold,
            )
        else:
            self._validator = ResponseValidator()
        self._responder = responder or DialogueResponder(
            trace_builder=self._trace_builder,
        )

        # --- Phase 6: BrainLogger (NullObject pattern) ---
        self._blog: BrainLogger = brain_logger or _NULL_LOGGER  # type: ignore[assignment]

    def process(self, result: CognitiveResult) -> BrainOutput:
        """
        Обработать CognitiveResult → BrainOutput.

        Шаги:
          1. Build ExplainabilityTrace
          2. Validate response
          3. Generate BrainOutput
        """
        start = time.perf_counter()

        # --- Phase 6: output_start (DEBUG) ---
        self._blog.debug(
            "output", "output_start",
            state={
                "action": result.action,
                "confidence": result.confidence,
                "trace_id": result.trace_id,
            },
        )

        # --- 1. Trace ---
        trace = self._trace_builder.build(result)

        # --- 2. Validate ---
        validation = self._validator.validate(result)

        # --- 3. Generate ---
        output = self._responder.generate(result, validation, trace)

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "[OutputPipeline] process complete: action=%s confidence=%.3f "
            "issues=%d duration=%.1fms",
            result.action, result.confidence,
            validation.issue_count, elapsed,
        )

        # --- Phase 6: output_complete (INFO) ---
        self._blog.info(
            "output", "output_complete",
            state={
                "action": result.action,
                "confidence": result.confidence,
                "issues_count": validation.issue_count,
                "corrections_applied": validation.applied_corrections,
                "trace_id": output.trace_id,
            },
            latency_ms=elapsed,
        )

        return output

    @property
    def trace_builder(self) -> OutputTraceBuilder:
        """Доступ к trace builder."""
        return self._trace_builder

    @property
    def validator(self) -> ResponseValidator:
        """Доступ к validator."""
        return self._validator

    @property
    def responder(self) -> DialogueResponder:
        """Доступ к responder."""
        return self._responder
