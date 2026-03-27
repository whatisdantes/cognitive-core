"""
tests/test_e2e_pipeline.py

End-to-end pipeline smoke tests.

Проверяет полный цикл:
  MemoryManager (real) → CognitiveCore → OutputPipeline → BrainOutput

Лёгкий тест: без тяжёлых моделей, без GPU.
Все зависимости — из самого проекта.
"""

import pytest

from brain.cognition import CognitiveCore
from brain.core.contracts import (
    BrainOutput,
    CognitiveResult,
    EncodedPercept,
    MemoryManagerProtocol,
    Modality,
)
from brain.memory import MemoryManager
from brain.output import OutputPipeline

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def memory_manager(tmp_data_dir):
    """Real MemoryManager с временной директорией."""
    mm = MemoryManager(data_dir=tmp_data_dir, auto_consolidate=False)
    mm.start()
    yield mm
    mm.stop()


@pytest.fixture
def seeded_memory(memory_manager):
    """MemoryManager с предзагруженными фактами."""
    memory_manager.store(
        "нейрон это клетка нервной системы",
        importance=0.9,
        source_ref="test_e2e",
    )
    memory_manager.store(
        "синапс это место контакта между нейронами",
        importance=0.8,
        source_ref="test_e2e",
    )
    memory_manager.store(
        "гиппокамп отвечает за формирование воспоминаний",
        importance=0.85,
        source_ref="test_e2e",
    )
    return memory_manager


@pytest.fixture
def cognitive_core(seeded_memory):
    """CognitiveCore с real MemoryManager."""
    return CognitiveCore(memory_manager=seeded_memory)


@pytest.fixture
def output_pipeline():
    """OutputPipeline (default config)."""
    return OutputPipeline()


# ---------------------------------------------------------------------------
# Protocol conformance tests
# ---------------------------------------------------------------------------

class TestProtocolConformance:
    """Проверка что реальные классы удовлетворяют Protocol'ам."""

    def test_memory_manager_satisfies_protocol(self, memory_manager):
        """MemoryManager должен удовлетворять MemoryManagerProtocol."""
        assert isinstance(memory_manager, MemoryManagerProtocol)

    def test_memory_manager_has_required_methods(self, memory_manager):
        """MemoryManager имеет все методы из Protocol."""
        assert hasattr(memory_manager, "store")
        assert hasattr(memory_manager, "retrieve")
        assert hasattr(memory_manager, "save_all")
        assert callable(memory_manager.store)
        assert callable(memory_manager.retrieve)
        assert callable(memory_manager.save_all)


# ---------------------------------------------------------------------------
# E2E Pipeline tests
# ---------------------------------------------------------------------------

class TestE2EPipeline:
    """End-to-end pipeline: CognitiveCore → OutputPipeline → BrainOutput."""

    def test_simple_question_pipeline(self, cognitive_core, output_pipeline):
        """Простой вопрос → CognitiveResult → BrainOutput."""
        # CognitiveCore.run()
        result = cognitive_core.run("что такое нейрон?")

        # Проверяем CognitiveResult
        assert isinstance(result, CognitiveResult)
        assert result.action  # не пустой
        assert result.response  # не пустой
        assert 0.0 <= result.confidence <= 1.0
        assert result.trace is not None
        assert result.trace_id  # не пустой

        # OutputPipeline.process()
        brain_output = output_pipeline.process(result)

        # Проверяем BrainOutput
        assert isinstance(brain_output, BrainOutput)
        assert brain_output.text  # не пустой
        assert len(brain_output.text) > 0
        assert 0.0 <= brain_output.confidence <= 1.0
        assert brain_output.trace_id  # не пустой

    def test_learn_command_pipeline(self, cognitive_core, output_pipeline):
        """Команда 'запомни' → LEARN action → BrainOutput."""
        result = cognitive_core.run("запомни: митохондрия это энергетическая станция клетки")

        assert isinstance(result, CognitiveResult)
        # Должен быть LEARN action
        assert "learn" in result.action.lower() or "LEARN" in result.action

        brain_output = output_pipeline.process(result)
        assert isinstance(brain_output, BrainOutput)
        assert brain_output.text

    def test_verify_claim_pipeline(self, cognitive_core, output_pipeline):
        """Верификация утверждения → CognitiveResult → BrainOutput."""
        result = cognitive_core.run("правда ли что нейрон это клетка?")

        assert isinstance(result, CognitiveResult)
        assert result.response
        assert result.confidence >= 0.0

        brain_output = output_pipeline.process(result)
        assert isinstance(brain_output, BrainOutput)
        assert brain_output.text

    def test_unknown_topic_pipeline(self, cognitive_core, output_pipeline):
        """Вопрос по неизвестной теме → graceful response."""
        result = cognitive_core.run("что такое квантовая хромодинамика?")

        assert isinstance(result, CognitiveResult)
        # Даже без данных — должен вернуть ответ
        assert result.response is not None

        brain_output = output_pipeline.process(result)
        assert isinstance(brain_output, BrainOutput)
        assert brain_output.text  # не пустой, даже если fallback

    def test_pipeline_with_encoded_percept(self, cognitive_core, output_pipeline):
        """Pipeline с EncodedPercept (mock vector)."""
        percept = EncodedPercept(
            percept_id="test_percept_001",
            modality=Modality.TEXT,
            vector=[0.1, 0.2, 0.3, 0.4, 0.5],
            text="нейрон клетка нервная система",
            quality=0.9,
            source="test_e2e",
            language="ru",
            message_type="question",
            metadata={"keywords": ["нейрон", "клетка"]},
        )

        result = cognitive_core.run(
            "что такое нейрон?",
            encoded_percept=percept,
        )

        assert isinstance(result, CognitiveResult)
        assert result.trace_id

        brain_output = output_pipeline.process(result)
        assert isinstance(brain_output, BrainOutput)
        assert brain_output.text

    def test_multiple_cycles_stable(self, cognitive_core, output_pipeline):
        """Несколько циклов подряд — система стабильна."""
        queries = [
            "что такое нейрон?",
            "запомни: аксон передаёт сигналы от нейрона",
            "что такое синапс?",
        ]

        for i, query in enumerate(queries):
            result = cognitive_core.run(query)
            assert isinstance(result, CognitiveResult), f"Cycle {i} failed: not CognitiveResult"

            brain_output = output_pipeline.process(result)
            assert isinstance(brain_output, BrainOutput), f"Cycle {i} failed: not BrainOutput"
            assert brain_output.text, f"Cycle {i} failed: empty text"

        # Проверяем что cycle_count корректен
        assert cognitive_core.cycle_count == len(queries)

    def test_cognitive_result_metadata_complete(self, cognitive_core):
        """CognitiveResult.metadata содержит все ожидаемые ключи."""
        result = cognitive_core.run("что такое гиппокамп?")

        expected_keys = {
            "goal_type",
            "goal_id",
            "outcome",
            "stop_reason",
            "total_iterations",
            "reasoning_duration_ms",
            "total_duration_ms",
            "hypothesis_count",
            "best_hypothesis_id",
        }

        assert expected_keys.issubset(set(result.metadata.keys())), (
            f"Missing keys: {expected_keys - set(result.metadata.keys())}"
        )

    def test_trace_chain_has_steps(self, cognitive_core):
        """TraceChain содержит хотя бы один шаг."""
        result = cognitive_core.run("что такое нейрон?")

        assert result.trace is not None
        assert len(result.trace.steps) >= 1, "TraceChain should have at least 1 step"
        assert result.trace.trace_id
        assert result.trace.session_id
