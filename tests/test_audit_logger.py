"""Tests for brain/safety/audit_logger.py"""
from __future__ import annotations

import json

import pytest

from brain.safety.audit_logger import AUDIT_EVENTS, AuditEvent, AuditLogger


class TestAuditEvent:
    def test_fields(self):
        e = AuditEvent(
            ts="2026-04-01T12:00:00Z",
            level="INFO",
            module="safety",
            event_type="cycle_complete",
            session_id="s1",
            cycle_id="c1",
            details={"action": "answer"},
        )
        assert e.level == "INFO"
        assert e.event_type == "cycle_complete"
        assert e.details == {"action": "answer"}

    def test_default_details_empty(self):
        e = AuditEvent(
            ts="t", level="WARN", module="m", event_type="e",
            session_id="", cycle_id="",
        )
        assert e.details == {}


class TestAuditEventsList:
    def test_contains_required_events(self):
        required = [
            "source_blacklisted",
            "source_whitelisted",
            "source_trust_updated",
            "data_redacted",
            "conflict_detected",
            "action_blocked",
            "action_warned",
            "confidence_gate_blocked",
            "boundary_violated",
            "safety_policy_applied",
            "cycle_complete",
        ]
        for ev in required:
            assert ev in AUDIT_EVENTS, f"Missing event: {ev}"


class TestAuditLogger:
    def test_log_creates_file(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path), filename="audit.jsonl")
        lg.log_event("cycle_complete", {"action": "answer"})
        assert (tmp_path / "audit.jsonl").exists()

    def test_log_jsonl_format(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path), filename="audit.jsonl")
        lg.log_event(
            "boundary_violated",
            {"reason": "blocked"},
            session_id="s1",
            cycle_id="c1",
            level="WARN",
            module="boundary_guard",
        )
        line = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
        r = json.loads(line)
        assert r["level"] == "WARN"
        assert r["module"] == "boundary_guard"
        assert r["event_type"] == "boundary_violated"
        assert r["session_id"] == "s1"
        assert r["cycle_id"] == "c1"
        assert r["details"]["reason"] == "blocked"
        assert "ts" in r

    def test_get_recent_returns_last_n(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path))
        for i in range(5):
            lg.log_event("cycle_complete", {"i": i})
        recent = lg.get_recent(3)
        assert len(recent) == 3
        assert recent[-1].details["i"] == 4

    def test_get_recent_all_when_fewer(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path))
        lg.log_event("cycle_complete", {})
        lg.log_event("action_blocked", {})
        assert len(lg.get_recent(100)) == 2

    def test_get_by_type_filters(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path))
        lg.log_event("cycle_complete", {"a": 1})
        lg.log_event("action_blocked", {"b": 2})
        lg.log_event("cycle_complete", {"c": 3})
        results = lg.get_by_type("cycle_complete")
        assert len(results) == 2
        assert all(e.event_type == "cycle_complete" for e in results)

    def test_get_by_type_empty_no_match(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path))
        lg.log_event("cycle_complete", {})
        assert lg.get_by_type("action_blocked") == []

    def test_default_level_info(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path), filename="t.jsonl")
        lg.log_event("cycle_complete", {})
        r = json.loads((tmp_path / "t.jsonl").read_text(encoding="utf-8").strip())
        assert r["level"] == "INFO"

    def test_default_module_safety(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path), filename="t.jsonl")
        lg.log_event("cycle_complete", {})
        r = json.loads((tmp_path / "t.jsonl").read_text(encoding="utf-8").strip())
        assert r["module"] == "safety"

    def test_multiple_events_multiple_lines(self, tmp_path):
        lg = AuditLogger(log_dir=str(tmp_path), filename="m.jsonl")
        lg.log_event("cycle_complete", {"i": 0})
        lg.log_event("action_blocked", {"i": 1})
        lines = (tmp_path / "m.jsonl").read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["event_type"] == "cycle_complete"
        assert json.loads(lines[1])["event_type"] == "action_blocked"

    def test_rotation_on_size(self, tmp_path):
        # max_size_mb=0.0001 → ~100 bytes → triggers rotation after first large write
        lg = AuditLogger(log_dir=str(tmp_path), filename="r.jsonl", max_size_mb=0.0001)
        lg.log_event("cycle_complete", {"data": "x" * 200})
        lg.log_event("cycle_complete", {"data": "y" * 200})
        assert (tmp_path / "r.jsonl.1").exists()
