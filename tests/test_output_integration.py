"""
tests/test_output_integration.py

Integration smoke tests для brain/output/ — Output MVP.

Тестируют полный pipeline:
  CognitiveCore.run() → OutputPipeline.process() → BrainOutput

Используют реальный MemoryManager (auto_consolidate=False).

~7 тестов.
"""

import pytest

from brain.cognition.cognitive_core import CognitiveCore
from brain.core.contracts import BrainOutput, CognitiveResult, TraceChain, TraceRef
from brain.memory.memory_manager import MemoryManager
from brain.output.dialogue_responder import OutputPipeline

# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def memory_manager():
    """Реальный MemoryManager без автоконсолидации."""
    mm = MemoryManager(auto_consolidate=False)
    # Добавляем несколько фактов (concept, description)
    mm.store_fact("нейрон", "Нейрон — это клетка нервной системы.")
    mm.store_fact("синапс", "Синапс — это место контакта между нейронами.")
    mm.store_fact("аксон", "Аксон передаёт сигналы от нейрона.")
    return mm


@pytest.fixture
def cognitive_core(memory_manager):
    """CognitiveCore с реальным MemoryManager."""
    return CognitiveCore(memory_manager=memory_manager)


@pytest.fixture
def pipeline():
    """OutputPipeline с дефолтными компонентами."""
    return OutputPipeline()


# ===========================================================================
# Integration Tests
# ===========================================================================

class TestOutputIntegration:
    """Integration smoke tests: CognitiveCore → OutputPipeline → BrainOutput."""

    def test_full_pipeline_answer_question(self, cognitive_core, pipeline):
        """Полный pipeline: вопрос → CognitiveResult → BrainOutput."""
        result = cognitive_core.run("Что такое нейрон?")
        output = pipeline.process(result)

        assert isinstance(output, BrainOutput)
        assert output.text != ""
        assert output.confidence >= 0.0
        assert output.trace_id != ""
        assert output.digest != ""
        assert output.action is not None

    def test_full_pipeline_has_metadata(self, cognitive_core, pipeline):
        """BrainOutput.metadata содержит стабильные ключи."""
        result = cognitive_core.run("Что такое синапс?")
        output = pipeline.process(result)

        meta = output.metadata
        assert "reasoning_type" in meta
        assert "uncertainty_level" in meta
        assert "language" in meta
        assert "output_style" in meta

    def test_full_pipeline_trace_has_memory_refs(self, cognitive_core, pipeline):
        """CognitiveResult содержит memory_refs."""
        result = cognitive_core.run("Что такое аксон?")

        # CognitiveResult должен содержать memory_refs
        assert isinstance(result.memory_refs, list)

        output = pipeline.process(result)
        assert isinstance(output, BrainOutput)

    def test_full_pipeline_different_actions(self, cognitive_core, pipeline):
        """Разные запросы могут давать разные action types."""
        result1 = cognitive_core.run("Что такое нейрон?")
        result2 = cognitive_core.run("Запомни: дендрит принимает сигналы.")

        output1 = pipeline.process(result1)
        output2 = pipeline.process(result2)

        # Оба должны быть валидными BrainOutput
        assert isinstance(output1, BrainOutput)
        assert isinstance(output2, BrainOutput)
        assert output1.text != ""
        assert output2.text != ""

    def test_full_pipeline_session_preserved(self, cognitive_core, pipeline):
        """session_id и cycle_id сохраняются через pipeline."""
        result = cognitive_core.run("Что такое нейрон?")
        output = pipeline.process(result)

        assert output.session_id == result.session_id
        assert output.cycle_id == result.cycle_id
        assert output.trace_id == result.trace_id

    def test_pipeline_from_manual_result(self, pipeline):
        """Pipeline работает с вручную созданным CognitiveResult."""
        result = CognitiveResult(
            action="respond_direct",
            response="Тестовый ответ.",
            confidence=0.75,
            trace=TraceChain(trace_id="manual_trace"),
            goal="Тестовый вопрос?",
            trace_id="manual_trace",
            session_id="manual_sess",
            cycle_id="manual_cycle",
            memory_refs=[
                TraceRef(ref_type="evidence", ref_id="ev_1"),
            ],
        )
        output = pipeline.process(result)

        assert isinstance(output, BrainOutput)
        assert output.text != ""
        assert output.trace_id == "manual_trace"
        assert output.confidence == 0.75

    def test_pipeline_empty_response_fallback(self, pipeline):
        """Pipeline обрабатывает пустой response через fallback."""
        result = CognitiveResult(
            action="refuse",
            response="",
            confidence=0.0,
            trace=TraceChain(trace_id="empty_trace"),
            goal="Неизвестный вопрос",
            trace_id="empty_trace",
        )
        output = pipeline.process(result)

        assert isinstance(output, BrainOutput)
        assert output.text != ""  # Fallback applied
        assert output.confidence == 0.0
