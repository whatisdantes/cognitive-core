"""
tests/test_safety_integration.py

Интеграционные тесты Stage L: Safety & Boundaries в CognitivePipeline.

Проверяет:
  T1. no-op при отсутствии safety-компонентов (backward compat)
  T2. step_safety_input_check: PII-редакция обновляет ctx.query
  T3. step_safety_input_check: blocked запрос → aborted pipeline → fallback result
  T4. step_safety_policy_check: blocked action → filtered_action override
  T5. step_safety_audit_log: AuditLogger.log_event вызывается с правильными аргументами
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from brain.cognition.pipeline import CognitivePipeline, CognitivePipelineContext
from brain.safety.audit_logger import AuditLogger
from brain.safety.boundary_guard import BoundaryGuard
from brain.safety.policy_layer import SafetyPolicyLayer


# ---------------------------------------------------------------------------
# Фикстуры — минимальный пайплайн
# ---------------------------------------------------------------------------

def _make_pipeline(
    boundary_guard: Optional[BoundaryGuard] = None,
    safety_policy: Optional[SafetyPolicyLayer] = None,
    audit_logger: Optional[AuditLogger] = None,
    tmp_dir: Optional[str] = None,
) -> CognitivePipeline:
    """Создать CognitivePipeline с реальными зависимостями (минимальный набор)."""
    import tempfile
    from brain.cognition.action_selector import ActionSelector
    from brain.cognition.context import PolicyConstraints
    from brain.cognition.goal_manager import GoalManager
    from brain.cognition.reasoner import Reasoner
    from brain.memory.memory_manager import MemoryManager

    data_dir = tmp_dir or tempfile.mkdtemp()
    memory = MemoryManager(data_dir=data_dir)
    policy = PolicyConstraints()
    goal_manager = GoalManager()
    reasoner = Reasoner(memory_manager=memory)
    action_selector = ActionSelector()

    return CognitivePipeline(
        memory=memory,
        encoder=None,
        event_bus=None,
        resource_monitor=None,
        policy=policy,
        goal_manager=goal_manager,
        reasoner=reasoner,
        action_selector=action_selector,
        vector_backend=None,
        cycle_count_fn=lambda: 1,
        boundary_guard=boundary_guard,
        safety_policy=safety_policy,
        audit_logger=audit_logger,
    )


# ---------------------------------------------------------------------------
# T1: no-op при отсутствии safety-компонентов
# ---------------------------------------------------------------------------

class TestSafetyNoOp:
    """T1: Пайплайн без safety-компонентов работает как раньше."""

    def test_pipeline_runs_without_safety_components(self) -> None:
        """Без boundary_guard/safety_policy/audit_logger пайплайн завершается успешно."""
        pipeline = _make_pipeline()
        result = pipeline.run("что такое нейрон?")
        assert result is not None
        assert result.action in ("answer", "refuse", "explore", "learn", "hedge")
        assert result.confidence >= 0.0

    def test_context_safety_fields_none_without_components(self) -> None:
        """ctx.safety_input_result и ctx.safety_policy_result остаются None."""
        pipeline = _make_pipeline()
        ctx = CognitivePipelineContext(query="тест")
        pipeline.step_safety_input_check(ctx)
        pipeline.step_safety_policy_check(ctx)
        assert ctx.safety_input_result is None
        assert ctx.safety_policy_result is None
        assert not ctx.aborted

    def test_audit_log_no_op_without_logger(self) -> None:
        """step_safety_audit_log — no-op если audit_logger не задан."""
        pipeline = _make_pipeline()
        ctx = CognitivePipelineContext(query="тест")
        # Не должно бросать исключений
        pipeline.step_safety_audit_log(ctx)


# ---------------------------------------------------------------------------
# T2: PII-редакция обновляет ctx.query
# ---------------------------------------------------------------------------

class TestSafetyInputCheckRedaction:
    """T2: BoundaryGuard редактирует PII в запросе."""

    def test_pii_email_redacted_in_query(self) -> None:
        """Email в запросе должен быть заменён на [REDACTED]."""
        guard = BoundaryGuard()
        pipeline = _make_pipeline(boundary_guard=guard)

        ctx = CognitivePipelineContext(query="напиши на user@example.com")
        pipeline.step_safety_input_check(ctx)

        assert ctx.safety_input_result is not None
        assert ctx.safety_input_result.redacted_count >= 1
        assert "[REDACTED]" in ctx.query
        assert "user@example.com" not in ctx.query
        assert not ctx.aborted

    def test_pii_phone_redacted_in_query(self) -> None:
        """Телефон в запросе должен быть заменён на [REDACTED]."""
        guard = BoundaryGuard()
        pipeline = _make_pipeline(boundary_guard=guard)

        ctx = CognitivePipelineContext(query="позвони на +7 999 123-45-67")
        pipeline.step_safety_input_check(ctx)

        assert ctx.safety_input_result is not None
        assert ctx.safety_input_result.redacted_count >= 1
        assert "[REDACTED]" in ctx.query
        assert not ctx.aborted

    def test_clean_query_passes_unchanged(self) -> None:
        """Чистый запрос без PII проходит без изменений."""
        guard = BoundaryGuard()
        pipeline = _make_pipeline(boundary_guard=guard)

        original = "что такое нейрон?"
        ctx = CognitivePipelineContext(query=original)
        pipeline.step_safety_input_check(ctx)

        assert ctx.query == original
        assert ctx.safety_input_result is not None
        assert ctx.safety_input_result.redacted_count == 0
        assert not ctx.aborted

    def test_full_pipeline_with_pii_redaction(self) -> None:
        """Полный пайплайн с PII в запросе завершается успешно (не блокируется)."""
        guard = BoundaryGuard()
        pipeline = _make_pipeline(boundary_guard=guard)

        result = pipeline.run("напиши на test@mail.ru про нейроны")
        assert result is not None
        # Пайплайн не должен быть прерван из-за PII (только редакция)
        assert result.action != "refuse" or result.metadata.get("aborted") is not True


# ---------------------------------------------------------------------------
# T3: Blocked запрос → aborted pipeline → fallback result
# ---------------------------------------------------------------------------

class TestSafetyInputCheckBlocked:
    """T3: BoundaryGuard блокирует запрос → пайплайн прерывается."""

    def test_low_confidence_blocks_pipeline(self) -> None:
        """
        BoundaryGuard с confidence < 0.40 блокирует.
        Но step_safety_input_check вызывает check(confidence=1.0),
        поэтому блокировка через confidence gate не происходит на входе.
        Тестируем через mock blocked result.
        """
        guard = BoundaryGuard()
        pipeline = _make_pipeline(boundary_guard=guard)

        # Мокаем check() чтобы вернуть BLOCK
        from brain.safety.boundary_guard import GuardResult
        blocked_result = GuardResult(
            status="BLOCK",
            original_text="опасный запрос",
            sanitized_text="опасный запрос",
            redacted_count=0,
            confidence_gate="BLOCK",
            action_gate="PASS",
            reasons=["test block"],
        )
        guard.check = MagicMock(return_value=blocked_result)  # type: ignore[method-assign]

        ctx = CognitivePipelineContext(query="опасный запрос")
        pipeline.step_safety_input_check(ctx)

        assert ctx.aborted is True
        assert "blocked" in ctx.abort_reason
        assert ctx.safety_input_result is not None
        assert ctx.safety_input_result.is_blocked

    def test_blocked_input_returns_fallback_result(self) -> None:
        """Полный пайплайн с заблокированным входом возвращает fallback result."""
        guard = BoundaryGuard()
        pipeline = _make_pipeline(boundary_guard=guard)

        from brain.safety.boundary_guard import GuardResult
        blocked_result = GuardResult(
            status="BLOCK",
            original_text="запрос",
            sanitized_text="запрос",
            redacted_count=0,
            confidence_gate="BLOCK",
            action_gate="PASS",
            reasons=["confidence too low"],
        )
        guard.check = MagicMock(return_value=blocked_result)  # type: ignore[method-assign]

        result = pipeline.run("запрос")
        # Fallback result: action="refuse", confidence=0.0, aborted=True
        assert result.action == "refuse"
        assert result.confidence == 0.0
        assert result.metadata.get("aborted") is True


# ---------------------------------------------------------------------------
# T4: SafetyPolicyLayer блокирует действие → filtered_action override
# ---------------------------------------------------------------------------

class TestSafetyPolicyCheck:
    """T4: SafetyPolicyLayer переопределяет заблокированное действие."""

    def test_blocked_action_overridden_to_filtered(self) -> None:
        """Если SafetyPolicyLayer блокирует действие — ctx.decision обновляется."""
        from brain.cognition.action_selector import ActionDecision
        from brain.cognition.context import CognitiveContext

        safety_policy = SafetyPolicyLayer(blocked_topics=["violence"])
        pipeline = _make_pipeline(safety_policy=safety_policy)

        ctx = CognitivePipelineContext(query="расскажи про violence")
        ctx.cognitive_context = CognitiveContext(
            session_id="s1", cycle_id="c1", trace_id="t1"
        )
        ctx.decision = ActionDecision(
            action="answer",
            statement="ответ про violence",
            confidence=0.8,
            reasoning="test",
            metadata={},
        )

        pipeline.step_safety_policy_check(ctx)

        assert ctx.safety_policy_result is not None
        assert not ctx.safety_policy_result.allowed
        # Действие должно быть переопределено
        assert ctx.decision.action == "answer"  # filtered_action = "answer" (fallback)
        assert ctx.decision.metadata.get("safety_policy_applied") is True
        assert "SF-3" in ctx.decision.metadata.get("safety_filters", [])

    def test_allowed_action_unchanged(self) -> None:
        """Разрешённое действие не изменяется SafetyPolicyLayer."""
        from brain.cognition.action_selector import ActionDecision
        from brain.cognition.context import CognitiveContext

        safety_policy = SafetyPolicyLayer()
        pipeline = _make_pipeline(safety_policy=safety_policy)

        ctx = CognitivePipelineContext(query="что такое нейрон?")
        ctx.cognitive_context = CognitiveContext(
            session_id="s1", cycle_id="c1", trace_id="t1"
        )
        ctx.decision = ActionDecision(
            action="answer",
            statement="нейрон — это...",
            confidence=0.9,
            reasoning="test",
            metadata={},
        )

        original_action = ctx.decision.action
        pipeline.step_safety_policy_check(ctx)

        assert ctx.safety_policy_result is not None
        assert ctx.safety_policy_result.allowed
        assert ctx.decision.action == original_action
        assert "safety_policy_applied" not in ctx.decision.metadata

    def test_no_op_without_safety_policy(self) -> None:
        """Без safety_policy — ctx.decision не изменяется."""
        from brain.cognition.action_selector import ActionDecision

        pipeline = _make_pipeline()  # safety_policy=None
        ctx = CognitivePipelineContext(query="тест")
        ctx.decision = ActionDecision(
            action="answer",
            statement="ответ",
            confidence=0.9,
            reasoning="test",
            metadata={},
        )

        pipeline.step_safety_policy_check(ctx)
        assert ctx.safety_policy_result is None
        assert ctx.decision.action == "answer"

    def test_full_pipeline_with_blocked_topic(self) -> None:
        """Полный пайплайн с blocked_topics завершается успешно."""
        safety_policy = SafetyPolicyLayer(blocked_topics=["violence"])
        pipeline = _make_pipeline(safety_policy=safety_policy)

        result = pipeline.run("расскажи про violence в истории")
        assert result is not None
        # Пайплайн не должен быть прерван — только action переопределён
        assert result.metadata.get("aborted") is not True


# ---------------------------------------------------------------------------
# T5: AuditLogger.log_event вызывается с правильными аргументами
# ---------------------------------------------------------------------------

class TestSafetyAuditLog:
    """T5: AuditLogger получает корректный вызов log_event."""

    def test_audit_log_called_on_successful_cycle(self) -> None:
        """AuditLogger.log_event вызывается после успешного цикла."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            log_dir = str(Path(tmpdir) / "logs")
            audit_logger = AuditLogger(log_dir=log_dir, filename="audit.jsonl")
            pipeline = _make_pipeline(audit_logger=audit_logger, tmp_dir=tmpdir)

            result = pipeline.run("что такое нейрон?", session_id="sess_test")
            assert result is not None

            # Проверяем что лог-файл создан и содержит запись
            log_path = Path(log_dir) / "audit.jsonl"
            assert log_path.exists()
            content = log_path.read_text(encoding="utf-8")
            assert "cycle_complete" in content
            assert "pipeline" in content

    def test_audit_log_contains_action_and_confidence(self) -> None:
        """Аудит-лог содержит action и confidence из результата."""
        import json

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            log_dir = str(Path(tmpdir) / "logs")
            audit_logger = AuditLogger(log_dir=log_dir, filename="audit.jsonl")
            pipeline = _make_pipeline(audit_logger=audit_logger, tmp_dir=tmpdir)

            pipeline.run("что такое нейрон?", session_id="sess_audit")

            log_path = Path(log_dir) / "audit.jsonl"
            lines = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            cycle_events = [e for e in lines if e.get("event_type") == "cycle_complete"]
            assert len(cycle_events) >= 1

            event = cycle_events[0]
            details = event.get("details", {})
            assert "action" in details
            assert "confidence" in details
            assert "query_preview" in details

    def test_audit_log_includes_safety_fields_when_present(self) -> None:
        """Аудит-лог включает safety_input_status если BoundaryGuard активен."""
        import json

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            log_dir = str(Path(tmpdir) / "logs")
            audit_logger = AuditLogger(log_dir=log_dir, filename="audit.jsonl")
            guard = BoundaryGuard()
            pipeline = _make_pipeline(
                boundary_guard=guard,
                audit_logger=audit_logger,
                tmp_dir=tmpdir,
            )

            pipeline.run("что такое нейрон?", session_id="sess_safety")

            log_path = Path(log_dir) / "audit.jsonl"
            lines = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            cycle_events = [e for e in lines if e.get("event_type") == "cycle_complete"]
            assert len(cycle_events) >= 1

            details = cycle_events[0].get("details", {})
            assert "safety_input_status" in details
            assert details["safety_input_status"] in ("PASS", "HEDGE", "WARN", "BLOCK")

    def test_no_op_audit_log_without_result(self) -> None:
        """step_safety_audit_log — no-op если ctx.result is None."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            log_dir = str(Path(tmpdir) / "logs")
            audit_logger = AuditLogger(log_dir=log_dir, filename="audit.jsonl")
            pipeline = _make_pipeline(audit_logger=audit_logger, tmp_dir=tmpdir)

            ctx = CognitivePipelineContext(query="тест")
            # ctx.result = None, ctx.cognitive_context = None
            pipeline.step_safety_audit_log(ctx)

            # Файл не должен быть создан (или пустой)
            log_path = Path(log_dir) / "audit.jsonl"
            if log_path.exists():
                assert log_path.read_text(encoding="utf-8").strip() == ""
