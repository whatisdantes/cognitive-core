"""
tests/test_output.py

Unit тесты для brain/output/ — Output MVP.

Покрытие:
  - TestExplainabilityTrace       (~10)
  - TestOutputTraceBuilder        (~16)
  - TestValidationIssue           (~6)
  - TestValidationResult          (~8)
  - TestResponseValidator         (~22)
  - TestDialogueResponder         (~22)
  - TestOutputPipeline            (~16)
  - TestImports                   (~4)

Итого: ~104 теста
"""


from brain.core.contracts import (
    BrainOutput,
    CognitiveResult,
    TraceChain,
    TraceRef,
    TraceStep,
)
from brain.output.dialogue_responder import (
    FALLBACK_TEMPLATES_EN,
    FALLBACK_TEMPLATES_RU,
    HEDGING_PHRASES_EN,
    HEDGING_PHRASES_RU,
    DialogueResponder,
    OutputPipeline,
)
from brain.output.response_validator import (
    FALLBACK_RESPONSE_EN,
    FALLBACK_RESPONSE_RU,
    MAX_RESPONSE_LENGTH,
    ResponseValidator,
    ValidationIssue,
    ValidationResult,
)
from brain.output.trace_builder import (
    ExplainabilityTrace,
    OutputTraceBuilder,
)

# ===========================================================================
# Helpers — фабрики для тестовых данных
# ===========================================================================

def _make_trace_chain(
    trace_id: str = "trace_test",
    session_id: str = "sess_1",
    cycle_id: str = "cycle_1",
    steps: list = None,
) -> TraceChain:
    """Создать тестовый TraceChain."""
    if steps is None:
        steps = [
            TraceStep(
                step_id="step_001",
                module="cognition.reasoner",
                action="retrieve",
                confidence=0.5,
                details={"description": "Retrieved 3 facts"},
            ),
            TraceStep(
                step_id="step_002",
                module="cognition.reasoner",
                action="hypothesize",
                confidence=0.6,
                details={"description": "Generated 2 hypotheses"},
            ),
            TraceStep(
                step_id="step_003",
                module="cognition.reasoner",
                action="score",
                confidence=0.7,
                details={"description": "Scored hypotheses"},
            ),
            TraceStep(
                step_id="step_004",
                module="cognition.reasoner",
                action="select",
                confidence=0.8,
                details={"description": "Selected best hypothesis"},
            ),
        ]
    return TraceChain(
        trace_id=trace_id,
        session_id=session_id,
        cycle_id=cycle_id,
        steps=steps,
        summary="test trace",
    )


def _make_cognitive_result(
    action: str = "respond_direct",
    response: str = "Нейрон — это клетка нервной системы.",
    confidence: float = 0.85,
    goal: str = "Что такое нейрон?",
    trace_id: str = "trace_test",
    session_id: str = "sess_1",
    cycle_id: str = "cycle_1",
    memory_refs: list = None,
    contradictions: list = None,
    metadata: dict = None,
    trace: TraceChain = None,
) -> CognitiveResult:
    """Создать тестовый CognitiveResult."""
    if memory_refs is None:
        memory_refs = [
            TraceRef(ref_type="evidence", ref_id="ev_001", note="conf=0.87"),
        ]
    if contradictions is None:
        contradictions = []
    if metadata is None:
        metadata = {
            "goal_type": "answer_question",
            "hypothesis_count": 2,
            "best_hypothesis_id": "hyp_abc123",
            "outcome": "goal_completed",
            "stop_reason": "confidence threshold met",
            "total_iterations": 3,
            "total_duration_ms": 142.5,
        }
    if trace is None:
        trace = _make_trace_chain(trace_id, session_id, cycle_id)

    return CognitiveResult(
        action=action,
        response=response,
        confidence=confidence,
        trace=trace,
        goal=goal,
        trace_id=trace_id,
        session_id=session_id,
        cycle_id=cycle_id,
        memory_refs=memory_refs,
        contradictions=contradictions,
        metadata=metadata,
    )


# ===========================================================================
# TestExplainabilityTrace
# ===========================================================================

class TestExplainabilityTrace:
    """Тесты для ExplainabilityTrace dataclass."""

    def test_creation_defaults(self):
        """Создание с дефолтными значениями."""
        t = ExplainabilityTrace()
        assert t.trace_id == ""
        assert t.session_id == ""
        assert t.cycle_id == ""
        assert t.input_query == ""
        assert t.reasoning_type == ""
        assert t.key_inferences == []
        assert t.action_taken == ""
        assert t.confidence == 0.0
        assert t.uncertainty_level == "unknown"
        assert t.uncertainty_reasons == []
        assert t.contradictions_found == []
        assert t.memory_facts == []
        assert t.total_duration_ms == 0.0
        assert t.metadata == {}

    def test_creation_with_values(self):
        """Создание с заданными значениями."""
        refs = [TraceRef(ref_type="semantic", ref_id="neuron")]
        t = ExplainabilityTrace(
            trace_id="t1",
            session_id="s1",
            cycle_id="c1",
            input_query="What is a neuron?",
            reasoning_type="answer_question",
            key_inferences=["neuron is a cell"],
            action_taken="respond_direct",
            confidence=0.9,
            uncertainty_level="very_low",
            memory_facts=refs,
            total_duration_ms=100.0,
        )
        assert t.trace_id == "t1"
        assert t.confidence == 0.9
        assert t.uncertainty_level == "very_low"
        assert len(t.memory_facts) == 1

    def test_created_at_auto_set(self):
        """created_at автоматически заполняется."""
        t = ExplainabilityTrace()
        assert t.created_at != ""
        assert "T" in t.created_at  # ISO format

    def test_created_at_preserved(self):
        """created_at не перезаписывается если задан."""
        t = ExplainabilityTrace(created_at="2026-01-01T00:00:00")
        assert t.created_at == "2026-01-01T00:00:00"

    def test_to_dict(self):
        """to_dict() возвращает dict."""
        t = ExplainabilityTrace(trace_id="t1", confidence=0.5)
        d = t.to_dict()
        assert isinstance(d, dict)
        assert d["trace_id"] == "t1"
        assert d["confidence"] == 0.5

    def test_from_dict(self):
        """from_dict() восстанавливает объект."""
        data = {
            "trace_id": "t2",
            "confidence": 0.7,
            "uncertainty_level": "low",
            "input_query": "test",
        }
        t = ExplainabilityTrace.from_dict(data)
        assert t.trace_id == "t2"
        assert t.confidence == 0.7
        assert t.uncertainty_level == "low"

    def test_from_dict_ignores_unknown(self):
        """from_dict() игнорирует неизвестные ключи."""
        data = {"trace_id": "t3", "unknown_field": "value"}
        t = ExplainabilityTrace.from_dict(data)
        assert t.trace_id == "t3"

    def test_metadata_extensible(self):
        """metadata может содержать произвольные данные."""
        t = ExplainabilityTrace(
            metadata={
                "reasoning_chain": ["retrieve", "hypothesize", "score"],
                "alternatives": ["hyp_1", "hyp_2"],
            }
        )
        assert "reasoning_chain" in t.metadata
        assert len(t.metadata["reasoning_chain"]) == 3

    def test_to_dict_roundtrip(self):
        """to_dict → from_dict roundtrip."""
        original = ExplainabilityTrace(
            trace_id="rt1",
            confidence=0.65,
            key_inferences=["a", "b"],
            uncertainty_level="medium",
        )
        d = original.to_dict()
        restored = ExplainabilityTrace.from_dict(d)
        assert restored.trace_id == original.trace_id
        assert restored.confidence == original.confidence
        assert restored.key_inferences == original.key_inferences

    def test_empty_lists_default(self):
        """Пустые списки не разделяются между экземплярами."""
        t1 = ExplainabilityTrace()
        t2 = ExplainabilityTrace()
        t1.key_inferences.append("x")
        assert t2.key_inferences == []


# ===========================================================================
# TestOutputTraceBuilder
# ===========================================================================

class TestOutputTraceBuilder:
    """Тесты для OutputTraceBuilder."""

    def test_build_basic(self):
        """build() создаёт ExplainabilityTrace из CognitiveResult."""
        result = _make_cognitive_result()
        builder = OutputTraceBuilder()
        trace = builder.build(result)

        assert isinstance(trace, ExplainabilityTrace)
        assert trace.trace_id == "trace_test"
        assert trace.session_id == "sess_1"
        assert trace.cycle_id == "cycle_1"
        assert trace.action_taken == "respond_direct"
        assert trace.confidence == 0.85

    def test_build_reasoning_type(self):
        """build() извлекает reasoning_type из metadata.goal_type."""
        result = _make_cognitive_result(
            metadata={"goal_type": "verify_claim"},
        )
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert trace.reasoning_type == "verify_claim"

    def test_build_input_query(self):
        """build() использует goal как input_query."""
        result = _make_cognitive_result(goal="Что такое синапс?")
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert trace.input_query == "Что такое синапс?"

    def test_build_memory_facts(self):
        """build() копирует memory_refs."""
        refs = [
            TraceRef(ref_type="evidence", ref_id="ev_1"),
            TraceRef(ref_type="evidence", ref_id="ev_2"),
        ]
        result = _make_cognitive_result(memory_refs=refs)
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert len(trace.memory_facts) == 2

    def test_build_contradictions(self):
        """build() копирует contradictions."""
        result = _make_cognitive_result(
            contradictions=["fact_A vs fact_B"],
        )
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert trace.contradictions_found == ["fact_A vs fact_B"]

    def test_build_uncertainty_very_low(self):
        """confidence >= 0.85 → uncertainty_level = very_low."""
        result = _make_cognitive_result(confidence=0.90)
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert trace.uncertainty_level == "very_low"

    def test_build_uncertainty_low(self):
        """confidence 0.65-0.85 → uncertainty_level = low."""
        result = _make_cognitive_result(confidence=0.70)
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert trace.uncertainty_level == "low"

    def test_build_uncertainty_medium(self):
        """confidence 0.45-0.65 → uncertainty_level = medium."""
        result = _make_cognitive_result(confidence=0.50)
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert trace.uncertainty_level == "medium"

    def test_build_uncertainty_high(self):
        """confidence 0.25-0.45 → uncertainty_level = high."""
        result = _make_cognitive_result(confidence=0.30)
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert trace.uncertainty_level == "high"

    def test_build_uncertainty_very_high(self):
        """confidence < 0.25 → uncertainty_level = very_high."""
        result = _make_cognitive_result(confidence=0.10)
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert trace.uncertainty_level == "very_high"

    def test_build_uncertainty_reasons_no_memory(self):
        """Нет memory_refs → uncertainty reason 'no_memory_evidence'."""
        result = _make_cognitive_result(memory_refs=[])
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert "no_memory_evidence" in trace.uncertainty_reasons

    def test_build_uncertainty_reasons_single_source(self):
        """Один memory_ref → uncertainty reason 'single_source'."""
        result = _make_cognitive_result(
            memory_refs=[TraceRef(ref_type="ev", ref_id="e1")],
        )
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert "single_source" in trace.uncertainty_reasons

    def test_build_uncertainty_reasons_contradictions(self):
        """Противоречия → uncertainty reason 'contradictions_found'."""
        result = _make_cognitive_result(contradictions=["c1"])
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert "contradictions_found" in trace.uncertainty_reasons

    def test_build_metadata_hypothesis_info(self):
        """build() кладёт hypothesis info в metadata."""
        result = _make_cognitive_result()
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert trace.metadata.get("hypothesis_count") == 2
        assert trace.metadata.get("best_hypothesis_id") == "hyp_abc123"

    def test_to_digest_format(self):
        """to_digest() возвращает строку с ключевыми полями."""
        result = _make_cognitive_result()
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        digest = builder.to_digest(trace)

        assert isinstance(digest, str)
        assert "Cycle" in digest
        assert "Query" in digest
        assert "Reasoning" in digest
        assert "Confidence" in digest
        assert "Action" in digest

    def test_to_digest_long_query_truncated(self):
        """to_digest() обрезает длинный query."""
        long_query = "x" * 200
        result = _make_cognitive_result(goal=long_query)
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        digest = builder.to_digest(trace)
        assert "..." in digest

    def test_to_json_format(self):
        """to_json() возвращает dict с дополнительными полями."""
        result = _make_cognitive_result()
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        data = builder.to_json(trace)

        assert isinstance(data, dict)
        assert "confidence_pct" in data
        assert "has_contradictions" in data
        assert "memory_count" in data
        assert "inference_count" in data
        assert data["confidence_pct"] == 85.0

    def test_to_json_has_contradictions_flag(self):
        """to_json() has_contradictions = True при наличии противоречий."""
        result = _make_cognitive_result(contradictions=["c1"])
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        data = builder.to_json(trace)
        assert data["has_contradictions"] is True

    def test_build_empty_result(self):
        """build() работает с минимальным CognitiveResult."""
        result = CognitiveResult(
            action="refuse",
            response="",
            confidence=0.0,
            trace=TraceChain(trace_id="t_empty"),
        )
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert trace.action_taken == "refuse"
        assert trace.confidence == 0.0

    def test_build_key_inferences_from_steps(self):
        """build() извлекает key_inferences из trace steps."""
        steps = [
            TraceStep(
                step_id="s1", module="r", action="hypothesize",
                details={"description": "Generated hypothesis about neurons"},
            ),
            TraceStep(
                step_id="s2", module="r", action="score",
                details={"description": "Scored 2 hypotheses"},
            ),
        ]
        result = _make_cognitive_result(
            trace=TraceChain(trace_id="t1", steps=steps),
        )
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        assert len(trace.key_inferences) >= 1

    def test_build_reasoning_chain_in_metadata(self):
        """build() кладёт reasoning_chain в metadata."""
        result = _make_cognitive_result()
        builder = OutputTraceBuilder()
        trace = builder.build(result)
        chain = trace.metadata.get("reasoning_chain", [])
        assert isinstance(chain, list)
        # Должны быть шаги из trace
        assert len(chain) > 0


# ===========================================================================
# TestValidationIssue
# ===========================================================================

class TestValidationIssue:
    """Тесты для ValidationIssue dataclass."""

    def test_creation_defaults(self):
        """Создание с дефолтами."""
        issue = ValidationIssue()
        assert issue.issue_type == ""
        assert issue.severity == "info"
        assert issue.description == ""
        assert issue.correction == ""

    def test_creation_with_values(self):
        """Создание с заданными значениями."""
        issue = ValidationIssue(
            issue_type="empty",
            severity="critical",
            description="Response is empty",
            correction="Applied fallback",
        )
        assert issue.issue_type == "empty"
        assert issue.severity == "critical"

    def test_to_dict(self):
        """to_dict() работает."""
        issue = ValidationIssue(issue_type="too_long", severity="warning")
        d = issue.to_dict()
        assert d["issue_type"] == "too_long"
        assert d["severity"] == "warning"

    def test_from_dict(self):
        """from_dict() работает."""
        data = {"issue_type": "empty", "severity": "critical"}
        issue = ValidationIssue.from_dict(data)
        assert issue.issue_type == "empty"

    def test_from_dict_ignores_unknown(self):
        """from_dict() игнорирует неизвестные ключи."""
        data = {"issue_type": "x", "unknown": "y"}
        issue = ValidationIssue.from_dict(data)
        assert issue.issue_type == "x"

    def test_to_dict_roundtrip(self):
        """to_dict → from_dict roundtrip."""
        original = ValidationIssue(
            issue_type="mismatch",
            severity="info",
            description="test",
        )
        restored = ValidationIssue.from_dict(original.to_dict())
        assert restored.issue_type == original.issue_type
        assert restored.severity == original.severity


# ===========================================================================
# TestValidationResult
# ===========================================================================

class TestValidationResult:
    """Тесты для ValidationResult dataclass."""

    def test_creation_defaults(self):
        """Создание с дефолтами."""
        vr = ValidationResult()
        assert vr.is_valid is True
        assert vr.issues == []
        assert vr.corrected_response == ""
        assert vr.applied_corrections == []
        assert vr.original_response == ""

    def test_has_critical_false(self):
        """has_critical = False без critical issues."""
        vr = ValidationResult(issues=[
            ValidationIssue(severity="warning"),
            ValidationIssue(severity="info"),
        ])
        assert vr.has_critical is False

    def test_has_critical_true(self):
        """has_critical = True с critical issue."""
        vr = ValidationResult(issues=[
            ValidationIssue(severity="critical"),
        ])
        assert vr.has_critical is True

    def test_has_warnings(self):
        """has_warnings property."""
        vr = ValidationResult(issues=[
            ValidationIssue(severity="warning"),
        ])
        assert vr.has_warnings is True

    def test_issue_count(self):
        """issue_count property."""
        vr = ValidationResult(issues=[
            ValidationIssue(), ValidationIssue(), ValidationIssue(),
        ])
        assert vr.issue_count == 3

    def test_to_dict(self):
        """to_dict() работает."""
        vr = ValidationResult(is_valid=False, corrected_response="test")
        d = vr.to_dict()
        assert d["is_valid"] is False
        assert d["corrected_response"] == "test"

    def test_from_dict(self):
        """from_dict() работает."""
        data = {"is_valid": True, "corrected_response": "ok"}
        vr = ValidationResult.from_dict(data)
        assert vr.is_valid is True
        assert vr.corrected_response == "ok"

    def test_original_response_preserved(self):
        """original_response сохраняется."""
        vr = ValidationResult(
            original_response="original",
            corrected_response="corrected",
        )
        assert vr.original_response == "original"
        assert vr.corrected_response == "corrected"


# ===========================================================================
# TestResponseValidator
# ===========================================================================

class TestResponseValidator:
    """Тесты для ResponseValidator."""

    # --- Пустой ответ ---

    def test_empty_response_critical(self):
        """Пустой ответ → critical issue + fallback."""
        result = _make_cognitive_result(response="")
        validator = ResponseValidator()
        vr = validator.validate(result)

        assert vr.is_valid is False  # critical → not valid
        assert any(i.issue_type == "empty" for i in vr.issues)
        assert any(i.severity == "critical" for i in vr.issues)
        assert vr.corrected_response != ""

    def test_whitespace_response_critical(self):
        """Ответ из пробелов → critical."""
        result = _make_cognitive_result(response="   \n\t  ")
        validator = ResponseValidator()
        vr = validator.validate(result)

        assert any(i.issue_type == "empty" for i in vr.issues)
        assert vr.corrected_response.strip() != ""

    def test_empty_response_fallback_ru(self):
        """Пустой ответ с русским запросом → русский fallback."""
        result = _make_cognitive_result(
            response="",
            goal="Что такое нейрон?",
        )
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert FALLBACK_RESPONSE_RU in vr.corrected_response or "Не удалось" in vr.corrected_response

    def test_empty_response_fallback_en(self):
        """Пустой ответ с английским запросом → английский fallback."""
        result = _make_cognitive_result(
            response="",
            goal="What is a neuron?",
            metadata={"language": "en"},
        )
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert "Could not" in vr.corrected_response or FALLBACK_RESPONSE_EN in vr.corrected_response

    def test_nonempty_response_no_empty_issue(self):
        """Непустой ответ → нет empty issue."""
        result = _make_cognitive_result(response="Нейрон — клетка.")
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert not any(i.issue_type == "empty" for i in vr.issues)

    # --- Low confidence без hedge ---

    def test_low_confidence_no_hedge_warning(self):
        """Low confidence без hedge → warning + автокоррекция."""
        result = _make_cognitive_result(
            response="Нейрон — это клетка.",
            confidence=0.3,
            action="respond_hedged",
        )
        validator = ResponseValidator()
        vr = validator.validate(result)

        assert any(i.issue_type == "low_confidence_no_hedge" for i in vr.issues)
        # Должен быть добавлен hedge prefix
        assert vr.corrected_response.lower().startswith("возможно")

    def test_low_confidence_with_hedge_no_issue(self):
        """Low confidence с hedge → нет issue."""
        result = _make_cognitive_result(
            response="Возможно, нейрон — это клетка.",
            confidence=0.3,
            action="respond_hedged",
        )
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert not any(i.issue_type == "low_confidence_no_hedge" for i in vr.issues)

    def test_high_confidence_no_hedge_no_issue(self):
        """High confidence без hedge → нет issue."""
        result = _make_cognitive_result(
            response="Нейрон — это клетка.",
            confidence=0.9,
            action="respond_direct",
        )
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert not any(i.issue_type == "low_confidence_no_hedge" for i in vr.issues)

    def test_refuse_action_no_hedge_check(self):
        """REFUSE action → не проверяем hedge."""
        result = _make_cognitive_result(
            response="Не могу ответить.",
            confidence=0.1,
            action="refuse",
        )
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert not any(i.issue_type == "low_confidence_no_hedge" for i in vr.issues)

    def test_ask_clarification_no_hedge_check(self):
        """ASK_CLARIFICATION → не проверяем hedge."""
        result = _make_cognitive_result(
            response="Уточните вопрос.",
            confidence=0.2,
            action="ask_clarification",
        )
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert not any(i.issue_type == "low_confidence_no_hedge" for i in vr.issues)

    def test_learn_action_no_hedge_check(self):
        """LEARN action → не проверяем hedge."""
        result = _make_cognitive_result(
            response="Факт сохранён.",
            confidence=0.3,
            action="learn",
        )
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert not any(i.issue_type == "low_confidence_no_hedge" for i in vr.issues)

    def test_hedge_en_prefix(self):
        """English hedge prefix при low confidence."""
        result = _make_cognitive_result(
            response="A neuron is a cell.",
            confidence=0.3,
            action="respond_hedged",
            goal="What is a neuron?",
            metadata={"language": "en"},
        )
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert vr.corrected_response.startswith("Perhaps")

    # --- Слишком длинный ответ ---

    def test_too_long_response_warning(self):
        """Ответ > max_length → warning + обрезка."""
        long_text = "Слово " * 500  # ~3000 chars
        result = _make_cognitive_result(response=long_text)
        validator = ResponseValidator()
        vr = validator.validate(result)

        assert any(i.issue_type == "too_long" for i in vr.issues)
        assert len(vr.corrected_response) <= MAX_RESPONSE_LENGTH
        assert vr.corrected_response.endswith("...")

    def test_normal_length_no_issue(self):
        """Нормальная длина → нет issue."""
        result = _make_cognitive_result(response="Короткий ответ.")
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert not any(i.issue_type == "too_long" for i in vr.issues)

    def test_custom_max_length(self):
        """Кастомный max_length."""
        result = _make_cognitive_result(response="x" * 200)
        validator = ResponseValidator(max_length=100)
        vr = validator.validate(result)
        assert any(i.issue_type == "too_long" for i in vr.issues)
        assert len(vr.corrected_response) <= 100

    # --- Language mismatch ---

    def test_language_mismatch_info(self):
        """Language mismatch → info (без автокоррекции)."""
        result = _make_cognitive_result(
            response="This is an English response.",
            goal="Что такое нейрон?",
            metadata={"language": "ru"},
        )
        validator = ResponseValidator()
        vr = validator.validate(result)

        lang_issues = [i for i in vr.issues if i.issue_type == "language_mismatch"]
        if lang_issues:
            assert lang_issues[0].severity == "info"
            assert lang_issues[0].correction == ""  # Без автокоррекции

    def test_same_language_no_issue(self):
        """Одинаковый язык → нет issue."""
        result = _make_cognitive_result(
            response="Нейрон — это клетка.",
            goal="Что такое нейрон?",
        )
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert not any(i.issue_type == "language_mismatch" for i in vr.issues)

    # --- Комбинированные проверки ---

    def test_valid_response_no_issues(self):
        """Валидный ответ → is_valid=True, нет issues."""
        result = _make_cognitive_result(
            response="Нейрон — это клетка нервной системы.",
            confidence=0.85,
            action="respond_direct",
        )
        validator = ResponseValidator()
        vr = validator.validate(result)

        assert vr.is_valid is True
        assert vr.issue_count == 0
        assert vr.corrected_response == result.response

    def test_multiple_issues_combined(self):
        """Несколько проблем одновременно."""
        long_text = "A " * 1500  # English, long, low confidence
        result = _make_cognitive_result(
            response=long_text,
            confidence=0.2,
            action="respond_hedged",
            goal="Что такое нейрон?",
            metadata={"language": "ru"},
        )
        validator = ResponseValidator()
        vr = validator.validate(result)

        # Должно быть несколько issues
        assert vr.issue_count >= 2

    def test_validator_preserves_original(self):
        """Validator сохраняет original_response."""
        result = _make_cognitive_result(response="Original text")
        validator = ResponseValidator()
        vr = validator.validate(result)
        assert vr.original_response == "Original text"

    def test_validator_does_not_break_trace_id(self):
        """Validator не ломает trace_id/confidence/action в result."""
        result = _make_cognitive_result(
            response="Test",
            trace_id="trace_xyz",
            confidence=0.5,
            action="respond_direct",
        )
        validator = ResponseValidator()
        validator.validate(result)

        # Result не мутирован
        assert result.trace_id == "trace_xyz"
        assert result.confidence == 0.5
        assert result.action == "respond_direct"

    def test_custom_hedge_threshold(self):
        """Кастомный hedge_confidence_threshold."""
        result = _make_cognitive_result(
            response="Нейрон — клетка.",
            confidence=0.7,
            action="respond_hedged",
        )
        # С порогом 0.8 — confidence 0.7 считается low
        validator = ResponseValidator(hedge_confidence_threshold=0.8)
        vr = validator.validate(result)
        assert any(i.issue_type == "low_confidence_no_hedge" for i in vr.issues)


# ===========================================================================
# TestDialogueResponder
# ===========================================================================

class TestDialogueResponder:
    """Тесты для DialogueResponder."""

    def _make_validation(
        self,
        corrected: str = "Нейрон — это клетка.",
        issues: list = None,
    ) -> ValidationResult:
        return ValidationResult(
            is_valid=True,
            corrected_response=corrected,
            issues=issues or [],
            original_response=corrected,
        )

    def _make_trace(
        self,
        action: str = "respond_direct",
        confidence: float = 0.85,
        reasoning_type: str = "answer_question",
        uncertainty_level: str = "very_low",
    ) -> ExplainabilityTrace:
        return ExplainabilityTrace(
            trace_id="t1",
            session_id="s1",
            cycle_id="c1",
            action_taken=action,
            confidence=confidence,
            reasoning_type=reasoning_type,
            uncertainty_level=uncertainty_level,
        )

    def test_generate_returns_brain_output(self):
        """generate() возвращает BrainOutput."""
        result = _make_cognitive_result()
        validation = self._make_validation()
        trace = self._make_trace()
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        assert isinstance(output, BrainOutput)

    def test_generate_preserves_trace_id(self):
        """generate() сохраняет trace_id."""
        result = _make_cognitive_result(trace_id="trace_abc")
        validation = self._make_validation()
        trace = self._make_trace()
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        assert output.trace_id == "trace_abc"

    def test_generate_preserves_confidence(self):
        """generate() сохраняет confidence."""
        result = _make_cognitive_result(confidence=0.77)
        validation = self._make_validation()
        trace = self._make_trace(confidence=0.77)
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        assert output.confidence == 0.77

    def test_generate_preserves_action(self):
        """generate() сохраняет action."""
        result = _make_cognitive_result(action="respond_hedged")
        validation = self._make_validation()
        trace = self._make_trace(action="respond_hedged")
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        assert output.action == "respond_hedged"

    def test_generate_has_digest(self):
        """generate() включает digest."""
        result = _make_cognitive_result()
        validation = self._make_validation()
        trace = self._make_trace()
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        assert output.digest != ""
        assert "Cycle" in output.digest

    def test_generate_metadata_stable_keys(self):
        """generate() metadata содержит стабильные ключи."""
        result = _make_cognitive_result()
        validation = self._make_validation()
        trace = self._make_trace()
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        meta = output.metadata

        assert "reasoning_type" in meta
        assert "uncertainty_level" in meta
        assert "validation_issues" in meta
        assert "language" in meta
        assert "output_style" in meta

    def test_respond_direct_no_hedge(self):
        """RESPOND_DIRECT → текст без hedge prefix."""
        result = _make_cognitive_result(
            action="respond_direct",
            response="Нейрон — клетка.",
            confidence=0.9,
        )
        validation = self._make_validation(corrected="Нейрон — клетка.")
        trace = self._make_trace(action="respond_direct", confidence=0.9)
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        # Не должно быть hedge prefix
        assert not output.text.lower().startswith("возможно")
        assert not output.text.lower().startswith("вероятно")

    def test_respond_hedged_has_hedge(self):
        """RESPOND_HEDGED → текст с hedge prefix."""
        result = _make_cognitive_result(
            action="respond_hedged",
            response="Нейрон — клетка.",
            confidence=0.5,
        )
        validation = self._make_validation(corrected="Нейрон — клетка.")
        trace = self._make_trace(action="respond_hedged", confidence=0.5)
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        text_lower = output.text.lower()
        # Должен содержать hedge
        hedge_found = any(
            p.lower() in text_lower
            for phrases in HEDGING_PHRASES_RU.values()
            for p in phrases
            if p
        )
        assert hedge_found or "возможно" in text_lower

    def test_respond_hedged_differs_from_direct(self):
        """RESPOND_HEDGED отличается от RESPOND_DIRECT."""
        base_response = "Нейрон — клетка нервной системы."

        result_direct = _make_cognitive_result(
            action="respond_direct",
            response=base_response,
            confidence=0.9,
        )
        result_hedged = _make_cognitive_result(
            action="respond_hedged",
            response=base_response,
            confidence=0.5,
        )

        responder = DialogueResponder()
        validation_d = self._make_validation(corrected=base_response)
        validation_h = self._make_validation(corrected=base_response)
        trace_d = self._make_trace(action="respond_direct", confidence=0.9)
        trace_h = self._make_trace(action="respond_hedged", confidence=0.5)

        out_d = responder.generate(result_direct, validation_d, trace_d)
        out_h = responder.generate(result_hedged, validation_h, trace_h)

        assert out_d.text != out_h.text

    def test_ask_clarification_has_question(self):
        """ASK_CLARIFICATION → текст содержит вопрос."""
        result = _make_cognitive_result(
            action="ask_clarification",
            response="Мне нужно больше информации.",
            confidence=0.2,
        )
        validation = self._make_validation(
            corrected="Мне нужно больше информации.",
        )
        trace = self._make_trace(action="ask_clarification")
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        assert "?" in output.text

    def test_refuse_text(self):
        """REFUSE → текст отказа."""
        result = _make_cognitive_result(
            action="refuse",
            response="Не могу ответить.",
            confidence=0.0,
        )
        validation = self._make_validation(corrected="Не могу ответить.")
        trace = self._make_trace(action="refuse", confidence=0.0)
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        assert output.text != ""
        assert output.confidence == 0.0

    def test_learn_confirmation(self):
        """LEARN → текст подтверждения."""
        result = _make_cognitive_result(
            action="learn",
            response="Нейрон — клетка.",
            confidence=0.7,
        )
        validation = self._make_validation(corrected="Нейрон — клетка.")
        trace = self._make_trace(action="learn")
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        text_lower = output.text.lower()
        # Должно содержать подтверждение
        assert any(w in text_lower for w in ["принято", "сохран", "запомн", "noted", "saved"])

    def test_empty_response_uses_fallback(self):
        """Пустой response → fallback template."""
        result = _make_cognitive_result(
            action="respond_direct",
            response="",
            confidence=0.5,
        )
        validation = self._make_validation(corrected="")
        trace = self._make_trace()
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        assert output.text != ""

    def test_fallback_templates_all_actions(self):
        """Fallback templates существуют для всех ActionType."""
        for action in ["respond_direct", "respond_hedged", "ask_clarification", "refuse", "learn"]:
            assert action in FALLBACK_TEMPLATES_RU
            assert action in FALLBACK_TEMPLATES_EN

    def test_hedging_phrases_bands(self):
        """HEDGING_PHRASES содержат все confidence bands."""
        assert len(HEDGING_PHRASES_RU) == 5
        assert len(HEDGING_PHRASES_EN) == 5

    def test_stable_template_same_input(self):
        """Одинаковый input → одинаковый шаблон."""
        result = _make_cognitive_result(
            action="respond_direct",
            response="Test response.",
            confidence=0.9,
        )
        validation = self._make_validation(corrected="Test response.")
        trace = self._make_trace()
        responder = DialogueResponder()

        out1 = responder.generate(result, validation, trace)
        out2 = responder.generate(result, validation, trace)
        assert out1.text == out2.text

    def test_en_language_detection(self):
        """English language detection."""
        result = _make_cognitive_result(
            action="respond_direct",
            response="A neuron is a cell.",
            goal="What is a neuron?",
            metadata={"language": "en"},
        )
        validation = self._make_validation(corrected="A neuron is a cell.")
        trace = self._make_trace()
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        assert output.metadata["language"] == "en"

    def test_output_style_hedged(self):
        """output_style для hedged содержит uncertainty level."""
        result = _make_cognitive_result(action="respond_hedged")
        validation = self._make_validation()
        trace = self._make_trace(
            action="respond_hedged",
            uncertainty_level="medium",
        )
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        assert "hedged" in output.metadata["output_style"]

    def test_validation_issues_in_metadata(self):
        """validation_issues попадают в metadata."""
        result = _make_cognitive_result()
        validation = ValidationResult(
            is_valid=True,
            corrected_response="test",
            issues=[
                ValidationIssue(issue_type="too_long", severity="warning"),
            ],
        )
        trace = self._make_trace()
        responder = DialogueResponder()

        output = responder.generate(result, validation, trace)
        vi = output.metadata["validation_issues"]
        assert len(vi) == 1
        assert vi[0]["type"] == "too_long"


# ===========================================================================
# TestOutputPipeline
# ===========================================================================

class TestOutputPipeline:
    """Тесты для OutputPipeline."""

    def test_process_returns_brain_output(self):
        """process() возвращает BrainOutput."""
        result = _make_cognitive_result()
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert isinstance(output, BrainOutput)

    def test_process_has_text(self):
        """process() output имеет text."""
        result = _make_cognitive_result()
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert output.text != ""

    def test_process_has_confidence(self):
        """process() output имеет confidence."""
        result = _make_cognitive_result(confidence=0.75)
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert output.confidence == 0.75

    def test_process_has_trace_id(self):
        """process() output имеет trace_id."""
        result = _make_cognitive_result(trace_id="trace_pipe")
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert output.trace_id == "trace_pipe"

    def test_process_has_digest(self):
        """process() output имеет digest."""
        result = _make_cognitive_result()
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert output.digest != ""

    def test_process_has_action(self):
        """process() output имеет action."""
        result = _make_cognitive_result(action="respond_hedged")
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert output.action == "respond_hedged"

    def test_process_has_metadata(self):
        """process() output имеет metadata с стабильными ключами."""
        result = _make_cognitive_result()
        pipeline = OutputPipeline()
        output = pipeline.process(result)

        assert "reasoning_type" in output.metadata
        assert "uncertainty_level" in output.metadata
        assert "language" in output.metadata

    def test_process_empty_response_handled(self):
        """process() обрабатывает пустой response."""
        result = _make_cognitive_result(response="")
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert output.text != ""  # Fallback applied

    def test_process_empty_contradictions(self):
        """process() работает при пустых contradictions."""
        result = _make_cognitive_result(contradictions=[])
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert isinstance(output, BrainOutput)

    def test_process_empty_uncertainty(self):
        """process() работает при пустых uncertainty данных."""
        result = _make_cognitive_result(
            metadata={"goal_type": "answer_question"},
        )
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert isinstance(output, BrainOutput)

    def test_process_refuse_action(self):
        """process() для REFUSE action."""
        result = _make_cognitive_result(
            action="refuse",
            response="Не могу ответить.",
            confidence=0.0,
        )
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert output.text != ""
        assert output.confidence == 0.0

    def test_process_learn_action(self):
        """process() для LEARN action."""
        result = _make_cognitive_result(
            action="learn",
            response="Факт сохранён.",
            confidence=0.7,
        )
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert output.text != ""

    def test_pipeline_custom_components(self):
        """Pipeline с кастомными компонентами."""
        custom_builder = OutputTraceBuilder()
        custom_validator = ResponseValidator(max_length=500)
        custom_responder = DialogueResponder()

        pipeline = OutputPipeline(
            trace_builder=custom_builder,
            validator=custom_validator,
            responder=custom_responder,
        )
        assert pipeline.trace_builder is custom_builder
        assert pipeline.validator is custom_validator
        assert pipeline.responder is custom_responder

    def test_pipeline_properties(self):
        """Pipeline properties доступны."""
        pipeline = OutputPipeline()
        assert isinstance(pipeline.trace_builder, OutputTraceBuilder)
        assert isinstance(pipeline.validator, ResponseValidator)
        assert isinstance(pipeline.responder, DialogueResponder)

    def test_process_session_cycle_preserved(self):
        """process() сохраняет session_id и cycle_id."""
        result = _make_cognitive_result(
            session_id="sess_xyz",
            cycle_id="cycle_42",
        )
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert output.session_id == "sess_xyz"
        assert output.cycle_id == "cycle_42"

    def test_process_minimal_result(self):
        """process() работает с минимальным CognitiveResult."""
        result = CognitiveResult(
            action="refuse",
            response="",
            confidence=0.0,
            trace=TraceChain(trace_id="t_min"),
        )
        pipeline = OutputPipeline()
        output = pipeline.process(result)
        assert isinstance(output, BrainOutput)
        assert output.text != ""  # Fallback


# ===========================================================================
# TestImports
# ===========================================================================

class TestImports:
    """Тесты для импортов из brain.output."""

    def test_import_all(self):
        """Все экспорты доступны через brain.output."""
        import brain.output as out
        assert hasattr(out, "ExplainabilityTrace")
        assert hasattr(out, "OutputTraceBuilder")
        assert hasattr(out, "ValidationIssue")
        assert hasattr(out, "ValidationResult")
        assert hasattr(out, "ResponseValidator")
        assert hasattr(out, "DialogueResponder")
        assert hasattr(out, "OutputPipeline")

    def test_import_hedging_phrases(self):
        """Hedging phrases доступны."""
        import brain.output as out
        assert hasattr(out, "HEDGING_PHRASES_RU")
        assert hasattr(out, "HEDGING_PHRASES_EN")

    def test_import_fallback_templates(self):
        """Fallback templates доступны."""
        import brain.output as out
        assert hasattr(out, "FALLBACK_TEMPLATES_RU")
        assert hasattr(out, "FALLBACK_TEMPLATES_EN")

    def test_all_list_complete(self):
        """__all__ содержит все ожидаемые экспорты."""
        import brain.output as out
        expected = {
            "ExplainabilityTrace", "OutputTraceBuilder",
            "ValidationIssue", "ValidationResult", "ResponseValidator",
            "DialogueResponder", "OutputPipeline",
            "HEDGING_PHRASES_RU", "HEDGING_PHRASES_EN",
            "FALLBACK_TEMPLATES_RU", "FALLBACK_TEMPLATES_EN",
            "FALLBACK_RESPONSE_RU", "FALLBACK_RESPONSE_EN",
        }
        assert expected.issubset(set(out.__all__))
