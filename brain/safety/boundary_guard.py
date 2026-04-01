"""
brain/safety/boundary_guard.py — Граничный страж системы.

Три функции:
  1. Редакция PII (email, phone, credit_card, ip_address, passport)
  2. Confidence gate: >0.85 PASS, >=0.60 HEDGE, >=0.40 WARN, <0.40 BLOCK
  3. Action gate: RESTRICTED_ACTIONS dict → WARN/BLOCK

Использование:
    guard = BoundaryGuard(audit_logger=audit)
    result = guard.check("Ответ системы", confidence=0.75, action="answer")
    if result.is_blocked:
        return fallback_response
    output = result.sanitized_text
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from brain.safety.audit_logger import AuditLogger

# ─── Паттерны редакции PII ───────────────────────────────────────────────────

_REDACTION_PATTERNS: Dict[str, re.Pattern[str]] = {
    "email": re.compile(
        r"[\w.+\-]+@[\w\-]+\.[\w.\-]+",
        re.IGNORECASE,
    ),
    "credit_card": re.compile(
        r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",
    ),
    "ip_address": re.compile(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    ),
    "phone": re.compile(
        r"(?<!\d)(?:\+7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)",
    ),
    "passport": re.compile(
        r"\b\d{4}\s?\d{6}\b",
    ),
}

_REDACTED_PLACEHOLDER = "[REDACTED]"

# ─── Ограниченные действия ───────────────────────────────────────────────────

RESTRICTED_ACTIONS: Dict[str, str] = {
    "delete_memory": "WARN",
    "modify_goals": "WARN",
    "reset_state": "WARN",
    "external_call": "BLOCK",
    "self_modify": "BLOCK",
    "override_safety": "BLOCK",
}

# ─── Пороги confidence gate ──────────────────────────────────────────────────

_GATE_PASS = 0.85
_GATE_HEDGE = 0.60
_GATE_WARN = 0.40


# ─── GuardResult ─────────────────────────────────────────────────────────────


@dataclass
class GuardResult:
    """Результат проверки BoundaryGuard."""

    status: str             # "PASS" | "HEDGE" | "WARN" | "BLOCK"
    original_text: str      # исходный текст
    sanitized_text: str     # текст после редакции PII
    redacted_count: int     # количество редакций
    confidence_gate: str    # "PASS" | "HEDGE" | "WARN" | "BLOCK"
    action_gate: str        # "PASS" | "WARN" | "BLOCK"
    reasons: List[str] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        """True если статус BLOCK."""
        return self.status == "BLOCK"


# ─── BoundaryGuard ───────────────────────────────────────────────────────────


class BoundaryGuard:
    """
    Граничный страж системы.

    Параметры:
        audit_logger — опциональный AuditLogger для записи событий
        session_id   — ID сессии для аудит-лога
        cycle_id     — ID цикла для аудит-лога
    """

    def __init__(
        self,
        audit_logger: Optional[AuditLogger] = None,
        session_id: str = "",
        cycle_id: str = "",
    ) -> None:
        self._audit = audit_logger
        self._session_id = session_id
        self._cycle_id = cycle_id

    def check(
        self,
        text: str,
        confidence: float,
        action: Optional[str] = None,
    ) -> GuardResult:
        """
        Проверить текст и действие.

        Args:
            text:       текст ответа системы
            confidence: уверенность (0.0–1.0)
            action:     тип действия (опционально)

        Returns:
            GuardResult с итоговым статусом
        """
        reasons: List[str] = []

        # 1. Редакция PII
        sanitized, redacted_count = self._redact(text)
        if redacted_count > 0:
            reasons.append(f"Redacted {redacted_count} PII pattern(s)")
            self._audit_event("data_redacted", {
                "redacted_count": redacted_count,
                "action": action or "",
            })

        # 2. Confidence gate
        confidence_gate = self._confidence_gate(confidence)
        if confidence_gate == "BLOCK":
            reasons.append(f"Confidence {confidence:.2f} below threshold {_GATE_WARN}")
            self._audit_event("confidence_gate_blocked", {
                "confidence": confidence,
                "gate": confidence_gate,
            })
        elif confidence_gate in ("WARN", "HEDGE"):
            reasons.append(f"Confidence {confidence:.2f} → {confidence_gate}")

        # 3. Action gate
        action_gate = self._action_gate(action)
        if action_gate in ("WARN", "BLOCK"):
            reasons.append(f"Action '{action}' is restricted ({action_gate})")
            self._audit_event("action_blocked" if action_gate == "BLOCK" else "action_warned", {
                "action": action,
                "gate": action_gate,
            })

        # 4. Итоговый статус (BLOCK > WARN > HEDGE > PASS)
        status = self._aggregate_status(confidence_gate, action_gate)

        return GuardResult(
            status=status,
            original_text=text,
            sanitized_text=sanitized,
            redacted_count=redacted_count,
            confidence_gate=confidence_gate,
            action_gate=action_gate,
            reasons=reasons,
        )

    def _redact(self, text: str) -> tuple[str, int]:
        """Применить все паттерны редакции. Возвращает (sanitized, count)."""
        count = 0
        result = text
        for pattern in _REDACTION_PATTERNS.values():
            new_result, n = pattern.subn(_REDACTED_PLACEHOLDER, result)
            count += n
            result = new_result
        return result, count

    def _confidence_gate(self, confidence: float) -> str:
        """Вычислить статус confidence gate."""
        if confidence >= _GATE_PASS:
            return "PASS"
        if confidence >= _GATE_HEDGE:
            return "HEDGE"
        if confidence >= _GATE_WARN:
            return "WARN"
        return "BLOCK"

    def _action_gate(self, action: Optional[str]) -> str:
        """Вычислить статус action gate."""
        if action is None:
            return "PASS"
        return RESTRICTED_ACTIONS.get(action, "PASS")

    def _aggregate_status(self, confidence_gate: str, action_gate: str) -> str:
        """Агрегировать статусы: BLOCK > WARN > HEDGE > PASS."""
        gates = [confidence_gate, action_gate]
        if "BLOCK" in gates:
            return "BLOCK"
        if "WARN" in gates:
            return "WARN"
        if "HEDGE" in gates:
            return "HEDGE"
        return "PASS"

    def _audit_event(self, event_type: str, details: dict) -> None:  # type: ignore[type-arg]
        """Записать событие в AuditLogger (если есть)."""
        if self._audit is not None:
            self._audit.log_event(
                event_type,
                details,
                session_id=self._session_id,
                cycle_id=self._cycle_id,
                level="WARN" if event_type != "data_redacted" else "INFO",
                module="boundary_guard",
            )
