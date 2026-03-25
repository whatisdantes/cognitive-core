"""
brain/output/response_validator.py

Output Consistency Validator — проверка ответа перед отправкой.

Содержит:
  - ValidationIssue   — одна проблема валидации
  - ValidationResult  — результат валидации
  - ResponseValidator — проверка и автокоррекция ответа

Аналог: передняя поясная кора — мониторинг ошибок перед выводом.

Это НЕ safety layer (brain/safety/). Это output consistency:
  - полнота (не пустой)
  - тон vs confidence (hedge при низкой уверенности)
  - длина (не слишком длинный)
  - язык (флаг, без автокоррекции)

Автокоррекция: пустой ответ, длина, hedge.
Только флаг: language mismatch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from brain.core.contracts import CognitiveResult, ContractMixin

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

MAX_RESPONSE_LENGTH = 2000

FALLBACK_RESPONSE_RU = "Не удалось сформировать ответ. Попробуйте переформулировать вопрос."
FALLBACK_RESPONSE_EN = "Could not generate a response. Please try rephrasing your question."

# Hedging prefixes для автокоррекции (когда confidence < 0.6 и нет hedge)
HEDGE_PREFIXES_RU = [
    "возможно", "вероятно", "скорее всего", "мне кажется",
    "я думаю", "предположительно", "не уверен",
    "насколько я понимаю", "по имеющимся данным",
]
HEDGE_PREFIXES_EN = [
    "perhaps", "probably", "most likely", "i think",
    "it seems", "presumably", "not sure",
    "as far as i understand", "based on available data",
]

# Маркеры hedged-ответов (для проверки наличия hedge)
HEDGE_MARKERS_RU = HEDGE_PREFIXES_RU + [
    "может быть", "не исключено", "есть вероятность",
]
HEDGE_MARKERS_EN = HEDGE_PREFIXES_EN + [
    "maybe", "might be", "could be", "there is a chance",
]


# ---------------------------------------------------------------------------
# ValidationIssue — одна проблема валидации
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue(ContractMixin):
    """
    Одна проблема, найденная при валидации ответа.

    issue_type: "empty" | "low_confidence_no_hedge" | "too_long" | "language_mismatch"
    severity:   "critical" | "warning" | "info"
    description: описание проблемы
    correction:  что было исправлено (пустая строка если только флаг)
    """
    issue_type: str = ""
    severity: str = "info"
    description: str = ""
    correction: str = ""


# ---------------------------------------------------------------------------
# ValidationResult — результат валидации
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult(ContractMixin):
    """
    Результат валидации ответа.

    is_valid:            True если нет critical issues
    issues:              список найденных проблем
    corrected_response:  исправленный ответ (или оригинал если без коррекций)
    applied_corrections: список применённых коррекций
    original_response:   оригинальный ответ до коррекций
    """
    is_valid: bool = True
    issues: List[ValidationIssue] = field(default_factory=list)
    corrected_response: str = ""
    applied_corrections: List[str] = field(default_factory=list)
    original_response: str = ""

    @property
    def has_critical(self) -> bool:
        """Есть ли критические проблемы."""
        return any(i.severity == "critical" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Есть ли предупреждения."""
        return any(i.severity == "warning" for i in self.issues)

    @property
    def issue_count(self) -> int:
        """Количество проблем."""
        return len(self.issues)


# ---------------------------------------------------------------------------
# ResponseValidator — проверка и автокоррекция ответа
# ---------------------------------------------------------------------------

class ResponseValidator:
    """
    Валидатор ответа перед отправкой.

    Проверки (в порядке приоритета):
      1. Пустой ответ → CRITICAL, автокоррекция (fallback message)
      2. Low confidence без hedge → WARNING, автокоррекция (добавить hedge)
      3. Слишком длинный (>2000) → WARNING, автокоррекция (обрезать)
      4. Language mismatch → INFO, только флаг (без автокоррекции)

    Использование:
        validator = ResponseValidator()
        result = validator.validate(cognitive_result)
        # result.corrected_response — исправленный ответ
        # result.issues — список проблем
    """

    def __init__(
        self,
        max_length: int = MAX_RESPONSE_LENGTH,
        hedge_confidence_threshold: float = 0.6,
    ) -> None:
        self._max_length = max_length
        self._hedge_threshold = hedge_confidence_threshold

    def validate(self, result: CognitiveResult) -> ValidationResult:
        """
        Валидировать CognitiveResult и вернуть ValidationResult.

        Применяет проверки последовательно. Автокоррекции кумулятивны.
        """
        response = result.response or ""
        original = response
        issues: List[ValidationIssue] = []
        corrections: List[str] = []

        # --- 1. Пустой ответ ---
        response, empty_issue, empty_correction = self._check_empty(
            response, result,
        )
        if empty_issue:
            issues.append(empty_issue)
        if empty_correction:
            corrections.append(empty_correction)

        # --- 2. Low confidence без hedge ---
        response, hedge_issue, hedge_correction = self._check_hedge(
            response, result,
        )
        if hedge_issue:
            issues.append(hedge_issue)
        if hedge_correction:
            corrections.append(hedge_correction)

        # --- 3. Слишком длинный ---
        response, length_issue, length_correction = self._check_length(
            response,
        )
        if length_issue:
            issues.append(length_issue)
        if length_correction:
            corrections.append(length_correction)

        # --- 4. Language mismatch (только флаг) ---
        lang_issue = self._check_language(response, result)
        if lang_issue:
            issues.append(lang_issue)

        # --- Результат ---
        is_valid = not any(i.severity == "critical" for i in issues)

        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            corrected_response=response,
            applied_corrections=corrections,
            original_response=original,
        )

    # ------------------------------------------------------------------
    # Проверки
    # ------------------------------------------------------------------

    def _check_empty(
        self,
        response: str,
        result: CognitiveResult,
    ) -> tuple:
        """
        Проверка 1: пустой ответ.

        Если ответ пустой или только пробелы → CRITICAL.
        Автокоррекция: fallback message.
        """
        stripped = response.strip()
        if stripped:
            return response, None, None

        # Определяем язык для fallback
        lang = self._detect_language(result)
        fallback = (
            FALLBACK_RESPONSE_EN if lang == "en" else FALLBACK_RESPONSE_RU
        )

        issue = ValidationIssue(
            issue_type="empty",
            severity="critical",
            description="Response is empty or whitespace-only",
            correction=f"Replaced with fallback: '{fallback[:50]}...'",
        )

        logger.warning(
            "[ResponseValidator] empty response, applying fallback"
        )

        return fallback, issue, "empty_response_fallback"

    def _check_hedge(
        self,
        response: str,
        result: CognitiveResult,
    ) -> tuple:
        """
        Проверка 2: low confidence без hedge.

        Если confidence < threshold и ответ не содержит hedge markers
        и action не REFUSE/ASK_CLARIFICATION → WARNING.
        Автокоррекция: добавить hedge prefix.
        """
        # Не применяем hedge к REFUSE, ASK_CLARIFICATION, LEARN
        skip_actions = {"refuse", "ask_clarification", "learn"}
        if result.action in skip_actions:
            return response, None, None

        # Проверяем confidence
        if result.confidence >= self._hedge_threshold:
            return response, None, None

        # Проверяем наличие hedge markers
        response_lower = response.lower()
        lang = self._detect_language(result)

        markers = HEDGE_MARKERS_EN if lang == "en" else HEDGE_MARKERS_RU
        has_hedge = any(m in response_lower for m in markers)

        if has_hedge:
            return response, None, None

        # Нужна автокоррекция: добавить hedge prefix
        if lang == "en":
            prefix = "Perhaps, "
        else:
            prefix = "Возможно, "

        # Первая буква ответа → lowercase после prefix
        if response and response[0].isupper():
            corrected = f"{prefix}{response[0].lower()}{response[1:]}"
        else:
            corrected = f"{prefix}{response}"

        issue = ValidationIssue(
            issue_type="low_confidence_no_hedge",
            severity="warning",
            description=(
                f"Confidence={result.confidence:.3f} < {self._hedge_threshold} "
                f"but response has no hedging language"
            ),
            correction=f"Added hedge prefix: '{prefix.strip()}'",
        )

        logger.info(
            "[ResponseValidator] added hedge prefix (confidence=%.3f)",
            result.confidence,
        )

        return corrected, issue, "hedge_prefix_added"

    def _check_length(self, response: str) -> tuple:
        """
        Проверка 3: слишком длинный ответ.

        Если len(response) > max_length → WARNING.
        Автокоррекция: обрезать + добавить "..."
        """
        if len(response) <= self._max_length:
            return response, None, None

        # Обрезаем по последнему пробелу перед лимитом
        truncated = response[: self._max_length - 3]
        last_space = truncated.rfind(" ")
        if last_space > self._max_length // 2:
            truncated = truncated[:last_space]
        truncated = truncated.rstrip(".,;:!? ") + "..."

        issue = ValidationIssue(
            issue_type="too_long",
            severity="warning",
            description=(
                f"Response length {len(response)} exceeds "
                f"max {self._max_length}"
            ),
            correction=f"Truncated to {len(truncated)} chars",
        )

        logger.info(
            "[ResponseValidator] truncated response: %d → %d chars",
            len(response), len(truncated),
        )

        return truncated, issue, "response_truncated"

    def _check_language(
        self,
        response: str,
        result: CognitiveResult,
    ) -> Optional[ValidationIssue]:
        """
        Проверка 4: language mismatch.

        Если язык запроса ≠ язык ответа → INFO (только флаг).
        Без автокоррекции.
        """
        meta = result.metadata or {}
        query_lang = meta.get("language", "")
        if not query_lang:
            # Пытаемся определить из goal
            query_lang = self._guess_language(result.goal or "")

        response_lang = self._guess_language(response)

        if not query_lang or not response_lang:
            return None

        if query_lang == response_lang:
            return None

        return ValidationIssue(
            issue_type="language_mismatch",
            severity="info",
            description=(
                f"Query language '{query_lang}' differs from "
                f"response language '{response_lang}'"
            ),
            correction="",  # Без автокоррекции
        )

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_language(result: CognitiveResult) -> str:
        """Определить язык из CognitiveResult metadata."""
        meta = result.metadata or {}
        lang = meta.get("language", "")
        if lang:
            return lang

        # Эвристика по тексту goal
        goal = result.goal or ""
        return ResponseValidator._guess_language(goal)

    @staticmethod
    def _guess_language(text: str) -> str:
        """
        Простая эвристика определения языка.

        Если > 30% символов кириллица → "ru"
        Если > 30% символов латиница → "en"
        Иначе → "" (неизвестно)
        """
        if not text:
            return ""

        # Считаем только буквы
        cyrillic = 0
        latin = 0
        for ch in text:
            if "\u0400" <= ch <= "\u04ff":
                cyrillic += 1
            elif "a" <= ch.lower() <= "z":
                latin += 1

        total = cyrillic + latin
        if total == 0:
            return ""

        if cyrillic / total > 0.3:
            return "ru"
        if latin / total > 0.3:
            return "en"
        return ""
