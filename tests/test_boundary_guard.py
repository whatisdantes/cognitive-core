"""Tests for brain/safety/boundary_guard.py"""
from __future__ import annotations

import pytest

from brain.safety.boundary_guard import BoundaryGuard, GuardResult


class TestGuardResult:
    def test_fields(self):
        r = GuardResult(
            status="PASS",
            original_text="hello",
            sanitized_text="hello",
            redacted_count=0,
            confidence_gate="PASS",
            action_gate="PASS",
            reasons=[],
        )
        assert r.status == "PASS"
        assert r.redacted_count == 0

    def test_is_blocked_true(self):
        r = GuardResult(
            status="BLOCK",
            original_text="x",
            sanitized_text="x",
            redacted_count=0,
            confidence_gate="BLOCK",
            action_gate="PASS",
            reasons=["low confidence"],
        )
        assert r.is_blocked is True

    def test_is_blocked_false(self):
        r = GuardResult(
            status="PASS",
            original_text="x",
            sanitized_text="x",
            redacted_count=0,
            confidence_gate="PASS",
            action_gate="PASS",
            reasons=[],
        )
        assert r.is_blocked is False


class TestBoundaryGuardRedaction:
    def test_redact_email(self):
        guard = BoundaryGuard()
        result = guard.check("Напиши на user@example.com пожалуйста", confidence=0.9)
        assert "user@example.com" not in result.sanitized_text
        assert result.redacted_count >= 1

    def test_redact_phone_ru(self):
        guard = BoundaryGuard()
        result = guard.check("Позвони +7 (999) 123-45-67", confidence=0.9)
        assert result.redacted_count >= 1

    def test_redact_credit_card(self):
        guard = BoundaryGuard()
        result = guard.check("Карта 4111 1111 1111 1111", confidence=0.9)
        assert result.redacted_count >= 1

    def test_redact_ip_address(self):
        guard = BoundaryGuard()
        result = guard.check("Сервер 192.168.1.100", confidence=0.9)
        assert result.redacted_count >= 1

    def test_no_redaction_clean_text(self):
        guard = BoundaryGuard()
        result = guard.check("Нейрон — клетка нервной системы", confidence=0.9)
        assert result.redacted_count == 0
        assert result.sanitized_text == "Нейрон — клетка нервной системы"

    def test_redacted_text_contains_placeholder(self):
        guard = BoundaryGuard()
        result = guard.check("Email: test@test.com", confidence=0.9)
        assert "[REDACTED]" in result.sanitized_text

    def test_original_text_preserved(self):
        guard = BoundaryGuard()
        original = "Email: test@test.com"
        result = guard.check(original, confidence=0.9)
        assert result.original_text == original


class TestBoundaryGuardConfidenceGate:
    def test_confidence_above_085_pass(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ на вопрос", confidence=0.9)
        assert result.confidence_gate == "PASS"
        assert result.status == "PASS"

    def test_confidence_above_060_hedge(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ на вопрос", confidence=0.7)
        assert result.confidence_gate == "HEDGE"

    def test_confidence_above_040_warn(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ на вопрос", confidence=0.5)
        assert result.confidence_gate == "WARN"

    def test_confidence_below_040_block(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ на вопрос", confidence=0.3)
        assert result.confidence_gate == "BLOCK"
        assert result.status == "BLOCK"
        assert result.is_blocked is True

    def test_confidence_exactly_085_pass(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.85)
        assert result.confidence_gate == "PASS"

    def test_confidence_exactly_060_hedge(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.60)
        assert result.confidence_gate == "HEDGE"

    def test_confidence_exactly_040_warn(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.40)
        assert result.confidence_gate == "WARN"


class TestBoundaryGuardActionGate:
    def test_allowed_action_pass(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.9, action="answer")
        assert result.action_gate == "PASS"

    def test_restricted_action_warn(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.9, action="delete_memory")
        assert result.action_gate in ("WARN", "BLOCK")

    def test_unknown_action_pass(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.9, action="custom_action")
        assert result.action_gate == "PASS"

    def test_none_action_pass(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.9, action=None)
        assert result.action_gate == "PASS"


class TestBoundaryGuardStatus:
    def test_block_overrides_hedge(self):
        guard = BoundaryGuard()
        # confidence=0.3 → BLOCK, even if action is fine
        result = guard.check("Ответ", confidence=0.3)
        assert result.status == "BLOCK"

    def test_warn_status_when_warn_gate(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.5)
        assert result.status in ("WARN", "PASS", "HEDGE")

    def test_reasons_populated_on_block(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.2)
        assert len(result.reasons) >= 1

    def test_audit_logger_called_on_block(self, tmp_path):
        from brain.safety.audit_logger import AuditLogger
        audit = AuditLogger(log_dir=str(tmp_path))
        guard = BoundaryGuard(audit_logger=audit)
        guard.check("Ответ", confidence=0.1)
        blocked = audit.get_by_type("confidence_gate_blocked")
        assert len(blocked) >= 1

    def test_audit_logger_called_on_redaction(self, tmp_path):
        from brain.safety.audit_logger import AuditLogger
        audit = AuditLogger(log_dir=str(tmp_path))
        guard = BoundaryGuard(audit_logger=audit)
        guard.check("Email: test@test.com", confidence=0.9)
        redacted = audit.get_by_type("data_redacted")
        assert len(redacted) >= 1
