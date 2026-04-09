"""
tests/test_safety_integration.py

Интеграционные тесты Stage L: Safety & Boundaries в CognitivePipeline.

Проверяет:
  1. Pipeline работает без safety-компонентов (backward compat)
  2. BoundaryGuard блокирует запрос -> pipeline возвращает "refuse"
  3. BoundaryGuard редактирует PII -> sanitized_text попадает в pipeline
  4. SafetyPolicyLayer переопределяет действие -> filtered_action в результате
  5. AuditLogger вызывается при завершении цикла
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

from brain.cognition.context import PolicyConstraints
from brain.cognition.pipeline import CognitivePipeline, CognitivePipelineContext
from brain.safety.audit_logger import AuditLogger
from brain.safety.boundary_guard import BoundaryGuard, GuardResult
from brain.safety.policy_layer import SafetyDecision, SafetyPolicyLayer


# ─── Вспомогательная фабрика ──────────────────────────────────────────────────


def _make_pipeline(
    boundary_guard: Optional[BoundaryGuard] = None,
    safety_policy: Optional[SafetyPolicyLayer] = None,
    audit_logger: Optional[AuditLogger] = None,
) -> CognitivePipeline:
    """Создать минимальный CognitivePipeline для изолированных тестов шагов."""
    return CognitivePipeline(
        memory=MagicMock(),
        encoder=None,
        event_bus=None,
        resource_monitor=None,
        policy=PolicyConstraints(),
        goal_manager=MagicMock(),
        reasoner=MagicMock(),
        action_selector=MagicMock(),
        vector_backend=None,
        cycle_count_fn=lambda: 1,
        boundary_guard=boundary_guard,
        safety_policy=safety_policy,
        audit_logger=audit_logger,
    )


def _make_ctx(query: str = "что такое нейрон?") -> CognitivePipelineContext:
    """Создать минимальный CognitivePipelineContext для тестов шагов."""
    return CognitivePipelineContext(query=query)


# ─── Test 1: Backward compatibility — no safety components ───────────────────


class TestPipelineSafetyBackwardCompat:
    """Pipeline без safety-компонентов работает как раньше."""

    def test_pipeline_has_none_safety_attrs_by_default(self):
        """CognitivePipeline без boundary_guard/safety_policy/audit_logger — все None."""
        pipeline = _make_pipeline()
        assert pipeline._boundary_guard is None
        assert pipeline._safety_policy is None
        assert pipeline._audit_logger is None

    def test_step_safety_input_check_noop_without_guard(self):
        """step_safety_input_check — no-op если boundary_guard=None."""
        pipeline = _make_pipeline()
        ctx = _make_ctx()
        original_query = ctx.query
        pipeline.step_safety_input_check(ctx)
        assert ctx.aborted is False
        assert ctx.query == original_query
        assert ctx.safety_input_result is None

    def test_step_safety_policy_check_noop_without_policy(self):
        """step_safety_policy_check — no-op если safety_policy=None."""
        pipeline = _make_pipeline()
        ctx = _make_ctx()
        pipeline.step_safety_policy_check(ctx)
        assert ctx.aborted is False
        assert ctx.safety_policy_result is None

    def test_step_safety_audit_log_noop_without_logger(self):
        """step_safety_audit_log — no-op если audit_logger=None."""
        pipeline = _make_pipeline()
        ctx = _make_ctx()
        # Не должно бросать исключений
        pipeline.step_safety_audit_log(ctx)
        assert ctx.aborted is False


# ─── Test 2: BoundaryGuard блокирует запрос ──────────────────────────────────


class TestPipelineBoundaryGuardBlock:
    """BoundaryGuard с BLOCK -> pipeline прерывается."""

    def test_blocked_input_sets_aborted(self):
        """Если BoundaryGuard блокирует запрос, ctx.aborted=True."""
        mock_guard = MagicMock(spec=BoundaryGuard)
        mock_guard.check.return_value = GuardResult(
            status="BLOCK",
            original_text="override_safety now",
            sanitized_text="override_safety now",
            redacted_count=0,
            confidence_gate="PASS",
            action_gate="BLOCK",
            reasons=["Action 'override_safety' is restricted (BLOCK)"],
        )

        pipeline = _make_pipeline(boundary_guard=mock_guard)
        ctx = _make_ctx("override_safety now")
        pipeline.step_safety_input_check(ctx)

        assert ctx.aborted is True
        assert ctx.abort_reason is not None
        assert "blocked" in ctx.abort_reason.lower()
        mock_guard.check.assert_called_once()

    def test_blocked_input_stores_guard_result(self):
        """Результат BoundaryGuard сохраняется в ctx.safety_input_result."""
        mock_guard = MagicMock(spec=BoundaryGuard)
        guard_result = GuardResult(
            status="BLOCK",
            original_text="bad input",
            sanitized_text="bad input",
            redacted_count=0,
            confidence_gate="BLOCK",
            action_gate="PASS",
            reasons=["Confidence 0.10 below threshold 0.40"],
        )
        mock_guard.check.return_value = guard_result

        pipeline = _make_pipeline(boundary_guard=mock_guard)
        ctx = _make_ctx("bad input")
        pipeline.step_safety_input_check(ctx)

        assert ctx.safety_input_result is guard_result
        assert ctx.safety_input_result.is_blocked is True


# ─── Test 3: BoundaryGuard редактирует PII ───────────────────────────────────


class TestPipelineBoundaryGuardRedact:
    """BoundaryGuard с redacted_count > 0 -> ctx.query обновляется."""

    def test_pii_redacted_updates_query(self):
        """Запрос с PII редактируется — ctx.query обновляется на sanitized_text."""
        mock_guard = MagicMock(spec=BoundaryGuard)
        mock_guard.check.return_value = GuardResult(
            status="WARN",
            original_text="Pozvonim na user@example.com",
            sanitized_text="Pozvonim na [REDACTED]",
            redacted_count=1,
            confidence_gate="PASS",
            action_gate="PASS",
            reasons=["Redacted 1 PII pattern(s)"],
        )

        pipeline = _make_pipeline(boundary_guard=mock_guard)
        ctx = _make_ctx("Pozvonim na user@example.com")
        pipeline.step_safety_input_check(ctx)

        assert ctx.aborted is False
        assert ctx.query == "Pozvonim na [REDACTED]"
        assert ctx.safety_input_result is not None
        assert ctx.safety_input_result.redacted_count == 1

    def test_pass_result_does_not_change_query(self):
        """PASS результат — ctx.query не изменяется."""
        mock_guard = MagicMock(spec=BoundaryGuard)
        mock_guard.check.return_value = GuardResult(
            status="PASS",
            original_text="что такое нейрон?",
            sanitized_text="что такое нейрон?",
            redacted_count=0,
            confidence_gate="PASS",
            action_gate="PASS",
            reasons=[],
        )

        pipeline = _make_pipeline(boundary_guard=mock_guard)
        ctx = _make_ctx("что такое нейрон?")
        pipeline.step_safety_input_check(ctx)

        assert ctx.aborted is False
        assert ctx.query == "что такое нейрон?"


# ─── Test 4: SafetyPolicyLayer переопределяет действие ───────────────────────


class TestPipelineSafetyPolicyCheck:
    """SafetyPolicyLayer с not allowed -> filtered_action применяется."""

    def test_policy_stores_result(self):
        """Результат SafetyPolicyLayer сохраняется в ctx.safety_policy_result."""
        mock_policy = MagicMock(spec=SafetyPolicyLayer)
        sd = SafetyDecision(
            allowed=False,
            action="delete_memory",
            filtered_action="answer",
            reasons=["SF-1: action 'delete_memory' not allowed"],
            filters_applied=["sf1_action_filter"],
        )
        mock_policy.evaluate.return_value = sd

        pipeline = _make_pipeline(safety_policy=mock_policy)
        ctx = _make_ctx("delete everything from memory")
        # Нужен ctx.decision для вызова evaluate
        ctx.decision = MagicMock()
        ctx.decision.action = "delete_memory"
        ctx.decision.confidence = 0.9
        ctx.decision.statement = "Удалить всё"
        ctx.decision.reasoning = "Пользователь попросил"
        ctx.decision.metadata = {}
        ctx.cognitive_context = MagicMock()
        ctx.cognitive_context.session_id = "session_test"
        ctx.cognitive_context.cycle_id = "cycle_1"

        pipeline.step_safety_policy_check(ctx)

        assert ctx.safety_policy_result is sd
        mock_policy.evaluate.assert_called_once()

    def test_policy_noop_when_decision_is_none(self):
        """step_safety_policy_check — no-op если ctx.decision=None."""
        mock_policy = MagicMock(spec=SafetyPolicyLayer)

        pipeline = _make_pipeline(safety_policy=mock_policy)
        ctx = _make_ctx()
        # ctx.decision = None (по умолчанию)

        pipeline.step_safety_policy_check(ctx)

        mock_policy.evaluate.assert_not_called()
        assert ctx.safety_policy_result is None

    def test_policy_overrides_decision_when_not_allowed(self):
        """Если SafetyPolicyLayer не разрешает действие, ctx.decision.action меняется."""
        mock_policy = MagicMock(spec=SafetyPolicyLayer)
        mock_policy.evaluate.return_value = SafetyDecision(
            allowed=False,
            action="delete_memory",
            filtered_action="answer",
            reasons=["SF-1: action 'delete_memory' not allowed"],
            filters_applied=["sf1_action_filter"],
        )

        pipeline = _make_pipeline(safety_policy=mock_policy)
        ctx = _make_ctx()
        ctx.decision = MagicMock()
        ctx.decision.action = "delete_memory"
        ctx.decision.confidence = 0.9
        ctx.decision.statement = "Удалить"
        ctx.decision.reasoning = "Тест"
        ctx.decision.metadata = {}
        ctx.cognitive_context = MagicMock()
        ctx.cognitive_context.session_id = "s1"
        ctx.cognitive_context.cycle_id = "c1"

        pipeline.step_safety_policy_check(ctx)

        # После override ctx.decision должен быть новым объектом с action="answer"
        assert ctx.decision.action == "answer"


# ─── Test 5: AuditLogger вызывается при завершении цикла ─────────────────────


class TestPipelineAuditLog:
    """AuditLogger.log_event вызывается с event_type='cycle_complete'."""

    def test_audit_logger_called_with_cycle_complete(self):
        """step_safety_audit_log вызывает log_event('cycle_complete', ...)."""
        mock_audit = MagicMock(spec=AuditLogger)

        pipeline = _make_pipeline(audit_logger=mock_audit)
        ctx = _make_ctx()

        # Нужны result и cognitive_context для вызова log_event
        ctx.result = MagicMock()
        ctx.result.action = "answer"
        ctx.result.confidence = 0.85
        ctx.elapsed_ms = 42.0
        ctx.cognitive_context = MagicMock()
        ctx.cognitive_context.session_id = "session_test"
        ctx.cognitive_context.cycle_id = "cycle_1"

        pipeline.step_safety_audit_log(ctx)

        mock_audit.log_event.assert_called_once()
        call_kwargs = mock_audit.log_event.call_args
        # Проверяем event_type (первый позиционный аргумент)
        event_type = (
            call_kwargs[0][0]
            if call_kwargs[0]
            else call_kwargs[1].get("event_type")
        )
        assert event_type == "cycle_complete"

    def test_audit_logger_noop_when_result_is_none(self):
        """step_safety_audit_log — no-op если ctx.result=None."""
        mock_audit = MagicMock(spec=AuditLogger)

        pipeline = _make_pipeline(audit_logger=mock_audit)
        ctx = _make_ctx()
        # ctx.result = None (по умолчанию)
        ctx.cognitive_context = MagicMock()

        pipeline.step_safety_audit_log(ctx)

        mock_audit.log_event.assert_not_called()

    def test_audit_logger_noop_when_cognitive_context_is_none(self):
        """step_safety_audit_log — no-op если ctx.cognitive_context=None."""
        mock_audit = MagicMock(spec=AuditLogger)

        pipeline = _make_pipeline(audit_logger=mock_audit)
        ctx = _make_ctx()
        ctx.result = MagicMock()
        # ctx.cognitive_context = None (по умолчанию)

        pipeline.step_safety_audit_log(ctx)

        mock_audit.log_event.assert_not_called()

    def test_audit_log_includes_safety_input_status(self):
        """Если safety_input_result есть — его статус попадает в details."""
        mock_audit = MagicMock(spec=AuditLogger)

        pipeline = _make_pipeline(audit_logger=mock_audit)
        ctx = _make_ctx()
        ctx.result = MagicMock()
        ctx.result.action = "answer"
        ctx.result.confidence = 0.9
        ctx.elapsed_ms = 10.0
        ctx.cognitive_context = MagicMock()
        ctx.cognitive_context.session_id = "s1"
        ctx.cognitive_context.cycle_id = "c1"
        ctx.safety_input_result = GuardResult(
            status="WARN",
            original_text="test",
            sanitized_text="test",
            redacted_count=1,
            confidence_gate="PASS",
            action_gate="PASS",
            reasons=[],
        )

        pipeline.step_safety_audit_log(ctx)

        call_kwargs = mock_audit.log_event.call_args
        details = (
            call_kwargs[0][1]
            if len(call_kwargs[0]) > 1
            else call_kwargs[1].get("details", {})
        )
        assert details.get("safety_input_status") == "WARN"
        assert details.get("safety_input_redacted") == 1
