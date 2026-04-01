"""
brain/safety/policy_layer.py — Политика безопасности когнитивного цикла.

Три фильтра:
  SF-1: confidence_gate — блокирует если confidence < threshold
  SF-2: action_restriction — блокирует/предупреждает запрещённые действия
  SF-3: topic_filter — блокирует запрещённые темы в тексте

Использование:
    spl = SafetyPolicyLayer(
        blocked_topics=["violence", "weapons"],
        confidence_threshold=0.40,
        audit_logger=audit,
    )
    decision = spl.evaluate("Ответ системы", action="answer", confidence=0.75)
    if not decision.allowed:
        action = decision.filtered_action
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from brain.safety.audit_logger import AuditLogger
from brain.safety.boundary_guard import RESTRICTED_ACTIONS

# Действие-заглушка при блокировке
_FALLBACK_ACTION = "answer"


@dataclass
class SafetyDecision:
    """Решение SafetyPolicyLayer по запросу."""

    allowed: bool
    action: str           # исходное действие
    filtered_action: str  # действие после фильтрации (fallback если заблокировано)
    reasons: List[str]
    filters_applied: List[str]  # ["SF-1", "SF-2", "SF-3"]


class SafetyPolicyLayer:
    """
    Политика безопасности когнитивного цикла.

    Применяет три фильтра последовательно.
    Первый сработавший BLOCK-фильтр останавливает цепочку.
    Thread-safe (stateless evaluate).

    Параметры:
        blocked_topics       — список запрещённых тем (case-insensitive)
        confidence_threshold — порог confidence для SF-1 (default 0.40)
        audit_logger         — опциональный AuditLogger
    """

    def __init__(
        self,
        blocked_topics: Optional[List[str]] = None,
        confidence_threshold: float = 0.40,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self._blocked_topics: List[str] = [t.lower() for t in (blocked_topics or [])]
        self._confidence_threshold = confidence_threshold
        self._audit = audit_logger

    def evaluate(
        self,
        text: str,
        action: str,
        confidence: float,
        session_id: str = "",
        cycle_id: str = "",
    ) -> SafetyDecision:
        """
        Оценить запрос по всем фильтрам.

        Returns:
            SafetyDecision с allowed=True/False и деталями.
        """
        reasons: List[str] = []
        filters_applied: List[str] = []
        allowed = True
        filtered_action = action

        # SF-1: Confidence gate
        if confidence < self._confidence_threshold:
            allowed = False
            filters_applied.append("SF-1")
            reasons.append(
                f"SF-1: confidence {confidence:.2f} < threshold {self._confidence_threshold}"
            )

        # SF-2: Action restriction
        if allowed and action in RESTRICTED_ACTIONS:
            gate = RESTRICTED_ACTIONS[action]
            if gate == "BLOCK":
                allowed = False
                filtered_action = _FALLBACK_ACTION
                filters_applied.append("SF-2")
                reasons.append(f"SF-2: action '{action}' is blocked")
            elif gate == "WARN":
                # WARN не блокирует, но фиксируется
                filters_applied.append("SF-2")
                reasons.append(f"SF-2: action '{action}' is restricted (WARN)")

        # SF-3: Topic filter
        if allowed and self._blocked_topics:
            text_lower = text.lower()
            for topic in self._blocked_topics:
                if topic in text_lower:
                    allowed = False
                    filtered_action = _FALLBACK_ACTION
                    filters_applied.append("SF-3")
                    reasons.append(f"SF-3: blocked topic '{topic}' detected")
                    break

        # Аудит-лог если есть блокировка или предупреждение
        if filters_applied:
            self._audit_event(
                allowed=allowed,
                action=action,
                filters_applied=filters_applied,
                reasons=reasons,
                session_id=session_id,
                cycle_id=cycle_id,
            )

        return SafetyDecision(
            allowed=allowed,
            action=action,
            filtered_action=filtered_action,
            reasons=reasons,
            filters_applied=filters_applied,
        )

    def _audit_event(
        self,
        allowed: bool,
        action: str,
        filters_applied: List[str],
        reasons: List[str],
        session_id: str,
        cycle_id: str,
    ) -> None:
        if self._audit is None:
            return
        self._audit.log_event(
            "safety_policy_applied",
            {
                "allowed": allowed,
                "action": action,
                "filters_applied": filters_applied,
                "reasons": reasons,
            },
            session_id=session_id,
            cycle_id=cycle_id,
            level="WARN" if not allowed else "INFO",
            module="safety_policy",
        )
