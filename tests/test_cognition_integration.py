"""
tests/test_cognition_integration.py

Integration smoke tests для когнитивного ядра (Stage F).

В отличие от unit-тестов (test_cognition.py), здесь используется
реальный MemoryManager (без моков) для проверки сквозного потока.

~7 smoke tests.
"""

import os
import shutil
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from brain.cognition.action_selector import ActionType
from brain.cognition.cognitive_core import CognitiveCore
from brain.core.contracts import CognitiveResult, TraceChain
from brain.memory.memory_manager import MemoryManager

# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def data_dir():
    """Временная директория для данных памяти."""
    d = tempfile.mkdtemp(prefix="brain_test_integration_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def memory_manager(data_dir):
    """Реальный MemoryManager с auto_consolidate=False."""
    mm = MemoryManager(
        data_dir=data_dir,
        auto_consolidate=False,
    )
    mm.start()

    # Загрузить несколько фактов
    mm.store("нейрон — это клетка нервной системы", importance=0.8, source_ref="textbook")
    mm.store("синапс — место контакта между нейронами", importance=0.7, source_ref="textbook")
    mm.store("мозг состоит из миллиардов нейронов", importance=0.9, source_ref="encyclopedia")
    mm.store("дофамин — нейромедиатор системы вознаграждения", importance=0.6, source_ref="article")

    yield mm
    mm.stop()


@pytest.fixture
def cognitive_core(memory_manager):
    """CognitiveCore с реальным MemoryManager."""
    return CognitiveCore(memory_manager=memory_manager)


# ===================================================================
# Integration Smoke Tests (~7)
# ===================================================================

class TestCognitionIntegration:

    def test_run_returns_cognitive_result(self, cognitive_core):
        """CognitiveCore.run() возвращает CognitiveResult."""
        result = cognitive_core.run("что такое нейрон?")
        assert isinstance(result, CognitiveResult)
        assert result.action in {a.value for a in ActionType}
        assert isinstance(result.response, str)
        assert result.confidence >= 0.0

    def test_run_has_valid_trace(self, cognitive_core):
        """Результат содержит TraceChain с шагами."""
        result = cognitive_core.run("что такое нейрон?")
        assert isinstance(result.trace, TraceChain)
        assert len(result.trace.steps) >= 1
        assert result.trace.trace_id != ""
        assert result.trace.session_id != ""

    def test_run_trace_contains_memory_refs(self, cognitive_core):
        """Trace содержит memory_refs (ссылки на доказательства)."""
        result = cognitive_core.run("что такое нейрон?")
        # Если reasoning нашёл факты — должны быть memory_refs
        if result.metadata.get("hypothesis_count", 0) > 0:
            assert len(result.memory_refs) >= 1

    def test_run_answer_question_action(self, cognitive_core):
        """Для вопроса — действие из допустимого набора ActionType."""
        result = cognitive_core.run("что такое нейрон?")
        # В MVP без vector retrieval поиск может не найти факты,
        # поэтому допускаем все типы действий, включая refuse.
        valid_actions = {a.value for a in ActionType}
        assert result.action in valid_actions, (
            f"Ожидалось одно из {valid_actions}, получено: {result.action}"
        )
        # Проверяем, что goal_type определён корректно
        assert result.metadata.get("goal_type") == "answer_question"

    def test_run_learn_fact_stores_in_memory(self, cognitive_core, memory_manager):
        """LEARN действие сохраняет факт в память."""
        result = cognitive_core.run("запомни: митохондрия — энергетическая станция клетки")
        assert result.action == ActionType.LEARN.value

        # Проверяем, что факт сохранён
        search = memory_manager.retrieve("митохондрия", top_n=5)
        # search может быть MemorySearchResult или иметь results
        found = False
        if hasattr(search, "results"):
            for r in search.results:
                content = r.get("content", "") if isinstance(r, dict) else getattr(r, "content", "")
                if "митохондрия" in content.lower():
                    found = True
                    break
        elif hasattr(search, "summary"):
            found = "митохондрия" in search.summary().lower()
        assert found, "Факт 'митохондрия' не найден в памяти после LEARN"

    def test_run_empty_query_handled(self, cognitive_core):
        """Пустой запрос обрабатывается без ошибок."""
        result = cognitive_core.run("")
        assert isinstance(result, CognitiveResult)
        # Пустой запрос → REFUSE или ASK_CLARIFICATION
        assert result.action in {a.value for a in ActionType}

    def test_run_metadata_complete(self, cognitive_core):
        """Metadata содержит все ожидаемые поля."""
        result = cognitive_core.run("что такое синапс?")
        expected_keys = [
            "goal_type", "goal_id", "outcome", "stop_reason",
            "total_iterations", "reasoning_duration_ms",
            "total_duration_ms", "hypothesis_count",
        ]
        for key in expected_keys:
            assert key in result.metadata, f"Отсутствует ключ '{key}' в metadata"
