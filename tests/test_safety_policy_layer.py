"""Tests for brain/safety/policy_layer.py"""
from __future__ import annotations

import pytest

from brain.safety.policy_layer import SafetyDecision, SafetyPolicyLayer


class TestSafetyDecision:
    def test_fields(self):
        d = SafetyDecision(
            allowed=True,
            action="answer",
            filtered_action="answer",
            reasons=[],
            filters_applied=[],
        )
        assert d.allowed is True
        assert d.action == "answer"
        assert d.filtered_action == "answer"

    def test_not_allowed(self):
        d = SafetyDecision(
            allowed=False,
            action="delete_memory",
            filtered_action="answer",
            reasons=["SF-2: action restricted"],
            filters_applied=["SF-2"],
        )
        assert d.allowed is False
        assert "SF-2" in d.filters_applied


class TestSafetyPolicyLayerSF1:
    """SF-1: confidence gate"""

    def test_high_confidence_allowed(self):
        spl = SafetyPolicyLayer(confidence_threshold=0.40)
        decision = spl.evaluate("Ответ системы", action="answer", confidence=0.9)
        assert decision.allowed is True
        assert "SF-1" not in decision.filters_applied

    def test_low_confidence_blocked(self):
        spl = SafetyPolicyLayer(confidence_threshold=0.40)
        decision = spl.evaluate("Ответ системы", action="answer", confidence=0.2)
        assert decision.allowed is False
        assert "SF-1" in decision.filters_applied

    def test_confidence_at_threshold_allowed(self):
        spl = SafetyPolicyLayer(confidence_threshold=0.40)
        decision = spl.evaluate("Ответ", action="answer", confidence=0.40)
        assert decision.allowed is True

    def test_confidence_below_threshold_blocked(self):
        spl = SafetyPolicyLayer(confidence_threshold=0.40)
        decision = spl.evaluate("Ответ", action="answer", confidence=0.39)
        assert decision.allowed is False


class TestSafetyPolicyLayerSF2:
    """SF-2: action restriction"""

    def test_allowed_action_passes(self):
        spl = SafetyPolicyLayer()
        decision = spl.evaluate("Ответ", action="answer", confidence=0.9)
        assert decision.allowed is True
        assert "SF-2" not in decision.filters_applied

    def test_restricted_action_blocked(self):
        spl = SafetyPolicyLayer()
        decision = spl.evaluate("Ответ", action="override_safety", confidence=0.9)
        assert decision.allowed is False
        assert "SF-2" in decision.filters_applied

    def test_restricted_action_reason_populated(self):
        spl = SafetyPolicyLayer()
        decision = spl.evaluate("Ответ", action="self_modify", confidence=0.9)
        assert len(decision.reasons) >= 1
        assert any("SF-2" in r for r in decision.reasons)

    def test_filtered_action_fallback_on_block(self):
        spl = SafetyPolicyLayer()
        decision = spl.evaluate("Ответ", action="override_safety", confidence=0.9)
        # filtered_action should be a safe fallback
        assert decision.filtered_action != "override_safety"


class TestSafetyPolicyLayerSF3:
    """SF-3: topic filter"""

    def test_clean_text_allowed(self):
        spl = SafetyPolicyLayer(blocked_topics=["violence", "weapons"])
        decision = spl.evaluate("Нейрон — клетка", action="answer", confidence=0.9)
        assert decision.allowed is True
        assert "SF-3" not in decision.filters_applied

    def test_blocked_topic_in_text_blocked(self):
        spl = SafetyPolicyLayer(blocked_topics=["violence"])
        decision = spl.evaluate("Как применять violence", action="answer", confidence=0.9)
        assert decision.allowed is False
        assert "SF-3" in decision.filters_applied

    def test_blocked_topic_case_insensitive(self):
        spl = SafetyPolicyLayer(blocked_topics=["Violence"])
        decision = spl.evaluate("violence is bad", action="answer", confidence=0.9)
        assert decision.allowed is False

    def test_no_blocked_topics_by_default(self):
        spl = SafetyPolicyLayer()
        decision = spl.evaluate("любой текст", action="answer", confidence=0.9)
        assert "SF-3" not in decision.filters_applied


class TestSafetyPolicyLayerAudit:
    def test_audit_logger_called_on_block(self, tmp_path):
        from brain.safety.audit_logger import AuditLogger
        audit = AuditLogger(log_dir=str(tmp_path))
        spl = SafetyPolicyLayer(confidence_threshold=0.40, audit_logger=audit)
        spl.evaluate("Ответ", action="answer", confidence=0.1)
        events = audit.get_by_type("safety_policy_applied")
        assert len(events) >= 1

    def test_audit_logger_not_required(self):
        spl = SafetyPolicyLayer()
        # Should not raise even without audit_logger
        decision = spl.evaluate("Ответ", action="answer", confidence=0.9)
        assert decision.allowed is True
