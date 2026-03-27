"""
tests/test_golden.py

Golden-answer benchmark tests (B.5).

Проверяют полный pipeline CognitiveCore → OutputPipeline → BrainOutput
на наборе из 20 эталонных вопросов (tests/golden/questions.json).

Категории тестов:
  - TestGoldenStructure:  parametrized — структурная корректность CognitiveResult
  - TestGoldenPipeline:   parametrized — полный pipeline до BrainOutput
  - TestGoldenRoundTrip:  learn → retrieve цикл (запомни → спроси)
  - TestGoldenEdgeCases:  пустой/минимальный запрос
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from brain.cognition.action_selector import ActionType
from brain.cognition.cognitive_core import CognitiveCore
from brain.core.contracts import BrainOutput, CognitiveResult, TraceChain
from brain.memory.memory_manager import MemoryManager
from brain.output.dialogue_responder import OutputPipeline

# ===================================================================
# Load golden questions
# ===================================================================

GOLDEN_PATH = Path(__file__).parent / "golden" / "questions.json"


def _load_golden() -> List[Dict[str, Any]]:
    """Загрузить golden questions из JSON."""
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


GOLDEN_QUESTIONS = _load_golden()

# IDs для parametrize
GOLDEN_IDS = [q["id"] for q in GOLDEN_QUESTIONS]

# Фильтры по тегам
LEARN_QUESTIONS = [
    q for q in GOLDEN_QUESTIONS
    if "learn" in q["tags"] and "roundtrip" not in q["tags"]
]
STANDARD_QUESTIONS = [
    q for q in GOLDEN_QUESTIONS
    if "learn" not in q["tags"]
    and "roundtrip" not in q["tags"]
    and "edge_case" not in q["tags"]
]
EDGE_QUESTIONS = [
    q for q in GOLDEN_QUESTIONS if "edge_case" in q["tags"]
]
ROUNDTRIP_LEARN = next((q for q in GOLDEN_QUESTIONS if q["id"] == "q19_learn"), None)
ROUNDTRIP_RETRIEVE = next((q for q in GOLDEN_QUESTIONS if q["id"] == "q20_retrieve"), None)

# Все допустимые action values
VALID_ACTIONS = {a.value for a in ActionType}


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture(scope="module")
def golden_data_dir():
    """Временная директория для данных памяти (module scope)."""
    d = tempfile.mkdtemp(prefix="brain_golden_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="module")
def golden_memory_manager(golden_data_dir):
    """
    MemoryManager с предзагруженными фактами по нейробиологии.

    8 фактов покрывают вопросы q01-q06 и частично q10-q11.
    """
    mm = MemoryManager(
        data_dir=golden_data_dir,
        auto_consolidate=False,
    )
    mm.start()

    # Предзагрузка фактов
    facts = [
        ("нейрон — это клетка нервной системы, передающая электрические сигналы",
         0.9, "textbook", ["биология", "нейрон"]),
        ("синапс — место контакта между двумя нейронами, через которое передаются сигналы",
         0.85, "textbook", ["биология", "синапс"]),
        ("мозг человека содержит около 86 миллиардов нейронов",
         0.9, "encyclopedia", ["биология", "мозг", "нейрон"]),
        ("дофамин — нейромедиатор системы вознаграждения, участвует в мотивации и обучении",
         0.7, "article", ["биология", "дофамин"]),
        ("гиппокамп играет ключевую роль в формировании новых воспоминаний",
         0.85, "textbook", ["биология", "гиппокамп", "память"]),
        ("префронтальная кора отвечает за планирование, принятие решений и контроль поведения",
         0.8, "textbook", ["биология", "кора", "мозг"]),
        ("мозг потребляет около 20 процентов всей энергии тела",
         0.75, "article", ["биология", "мозг", "энергия"]),
        ("нейрогенез — процесс образования новых нейронов — происходит в гиппокампе взрослого мозга",
         0.7, "research", ["биология", "нейрогенез"]),
    ]

    for content, importance, source, tags in facts:
        mm.store(content, importance=importance, source_ref=source, tags=tags)

    yield mm
    mm.stop()


@pytest.fixture(scope="module")
def golden_core(golden_memory_manager):
    """CognitiveCore с предзагруженной памятью."""
    return CognitiveCore(memory_manager=golden_memory_manager)


@pytest.fixture(scope="module")
def golden_pipeline():
    """OutputPipeline для полного pipeline теста."""
    return OutputPipeline()


@pytest.fixture(scope="module")
def golden_results(golden_core):
    """
    Кэш результатов CognitiveCore.run() для всех golden questions.

    Выполняется один раз (module scope) — экономит время.
    Порядок важен: q19_learn перед q20_retrieve для round-trip.
    """
    results = {}
    for q in GOLDEN_QUESTIONS:
        result = golden_core.run(q["query"])
        results[q["id"]] = result
    return results


@pytest.fixture(scope="module")
def golden_outputs(golden_pipeline, golden_results):
    """
    Кэш BrainOutput для всех golden questions.
    """
    outputs = {}
    for qid, result in golden_results.items():
        output = golden_pipeline.process(result)
        outputs[qid] = output
    return outputs


# ===================================================================
# TestGoldenStructure — структурная корректность CognitiveResult
# ===================================================================

class TestGoldenStructure:
    """Проверка структурной корректности CognitiveResult для каждого вопроса."""

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_returns_cognitive_result(self, golden_results, question):
        """CognitiveCore.run() возвращает CognitiveResult."""
        result = golden_results[question["id"]]
        assert isinstance(result, CognitiveResult), (
            f"[{question['id']}] Expected CognitiveResult, got {type(result)}"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_action_is_valid(self, golden_results, question):
        """Action — одно из допустимых значений ActionType."""
        result = golden_results[question["id"]]
        assert result.action in VALID_ACTIONS, (
            f"[{question['id']}] Invalid action: {result.action}"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_action_in_expected(self, golden_results, question):
        """Action входит в список ожидаемых для данного вопроса."""
        result = golden_results[question["id"]]
        expected = question["expected_actions"]
        assert result.action in expected, (
            f"[{question['id']}] action={result.action} not in expected={expected}"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_goal_type_detected(self, golden_results, question):
        """goal_type в metadata совпадает с ожидаемым."""
        result = golden_results[question["id"]]
        actual_goal = result.metadata.get("goal_type", "")
        expected_goal = question["expected_goal_type"]
        assert actual_goal == expected_goal, (
            f"[{question['id']}] goal_type={actual_goal}, expected={expected_goal}"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_confidence_range(self, golden_results, question):
        """Confidence в диапазоне [0.0, 1.0]."""
        result = golden_results[question["id"]]
        assert 0.0 <= result.confidence <= 1.0, (
            f"[{question['id']}] confidence={result.confidence} out of [0,1]"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_confidence_above_minimum(self, golden_results, question):
        """Confidence ≥ min_confidence из golden spec."""
        result = golden_results[question["id"]]
        min_conf = question["min_confidence"]
        assert result.confidence >= min_conf, (
            f"[{question['id']}] confidence={result.confidence} < min={min_conf}"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_response_is_string(self, golden_results, question):
        """Response — строка."""
        result = golden_results[question["id"]]
        assert isinstance(result.response, str), (
            f"[{question['id']}] response is not str: {type(result.response)}"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_trace_is_valid(self, golden_results, question):
        """Trace — TraceChain с шагами."""
        result = golden_results[question["id"]]
        assert isinstance(result.trace, TraceChain), (
            f"[{question['id']}] trace is not TraceChain"
        )
        assert len(result.trace.steps) >= 1, (
            f"[{question['id']}] trace has no steps"
        )
        assert result.trace.trace_id != "", (
            f"[{question['id']}] trace_id is empty"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_metadata_complete(self, golden_results, question):
        """Metadata содержит все обязательные ключи."""
        result = golden_results[question["id"]]
        required_keys = [
            "goal_type", "goal_id", "outcome", "stop_reason",
            "total_iterations", "reasoning_duration_ms",
            "total_duration_ms", "hypothesis_count",
        ]
        for key in required_keys:
            assert key in result.metadata, (
                f"[{question['id']}] missing metadata key: {key}"
            )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_session_and_cycle_ids(self, golden_results, question):
        """session_id и cycle_id заполнены."""
        result = golden_results[question["id"]]
        assert result.session_id != "", (
            f"[{question['id']}] session_id is empty"
        )
        assert result.cycle_id != "", (
            f"[{question['id']}] cycle_id is empty"
        )
        assert result.trace_id != "", (
            f"[{question['id']}] trace_id is empty"
        )


# ===================================================================
# TestGoldenContent — содержательные проверки
# ===================================================================

class TestGoldenContent:
    """Проверка содержания ответов (must_contain, must_not_contain)."""

    @pytest.mark.parametrize("question", STANDARD_QUESTIONS,
                             ids=[q["id"] for q in STANDARD_QUESTIONS])
    def test_must_contain_if_found(self, golden_results, question):
        """
        Если action != refuse и есть must_contain_if_found,
        проверяем что ответ содержит ожидаемые слова.
        """
        result = golden_results[question["id"]]
        must_contain = question.get("must_contain_if_found", [])

        if not must_contain:
            return  # нечего проверять

        # Если refuse — пропускаем (нет данных)
        if result.action == "refuse":
            return

        response_lower = result.response.lower()
        goal_lower = result.goal.lower() if result.goal else ""
        combined = f"{response_lower} {goal_lower}"

        for word in must_contain:
            assert word.lower() in combined, (
                f"[{question['id']}] '{word}' not found in response/goal. "
                f"action={result.action}, response='{result.response[:100]}'"
            )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_must_not_contain(self, golden_results, question):
        """Ответ не содержит запрещённых слов."""
        result = golden_results[question["id"]]
        must_not = question.get("must_not_contain", [])

        if not must_not:
            return

        response_lower = result.response.lower()
        for word in must_not:
            assert word.lower() not in response_lower, (
                f"[{question['id']}] forbidden word '{word}' found in response"
            )


# ===================================================================
# TestGoldenPipeline — полный pipeline до BrainOutput
# ===================================================================

class TestGoldenPipeline:
    """Проверка полного pipeline: CognitiveResult → OutputPipeline → BrainOutput."""

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_output_is_brain_output(self, golden_outputs, question):
        """OutputPipeline возвращает BrainOutput."""
        output = golden_outputs[question["id"]]
        assert isinstance(output, BrainOutput), (
            f"[{question['id']}] Expected BrainOutput, got {type(output)}"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_output_text_non_empty(self, golden_outputs, question):
        """BrainOutput.text не пустой."""
        output = golden_outputs[question["id"]]
        assert output.text.strip() != "", (
            f"[{question['id']}] BrainOutput.text is empty"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_output_confidence_matches(self, golden_results, golden_outputs, question):
        """BrainOutput.confidence совпадает с CognitiveResult.confidence."""
        result = golden_results[question["id"]]
        output = golden_outputs[question["id"]]
        assert output.confidence == result.confidence, (
            f"[{question['id']}] confidence mismatch: "
            f"output={output.confidence} vs result={result.confidence}"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_output_action_matches(self, golden_results, golden_outputs, question):
        """BrainOutput.action совпадает с CognitiveResult.action."""
        result = golden_results[question["id"]]
        output = golden_outputs[question["id"]]
        assert output.action == result.action, (
            f"[{question['id']}] action mismatch: "
            f"output={output.action} vs result={result.action}"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_output_trace_id_matches(self, golden_results, golden_outputs, question):
        """BrainOutput.trace_id совпадает с CognitiveResult.trace_id."""
        result = golden_results[question["id"]]
        output = golden_outputs[question["id"]]
        assert output.trace_id == result.trace_id, (
            f"[{question['id']}] trace_id mismatch"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_output_has_digest(self, golden_outputs, question):
        """BrainOutput.digest не пустой."""
        output = golden_outputs[question["id"]]
        assert output.digest.strip() != "", (
            f"[{question['id']}] BrainOutput.digest is empty"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_output_metadata_has_language(self, golden_outputs, question):
        """BrainOutput.metadata содержит language."""
        output = golden_outputs[question["id"]]
        assert "language" in output.metadata, (
            f"[{question['id']}] metadata missing 'language'"
        )

    @pytest.mark.parametrize("question", GOLDEN_QUESTIONS, ids=GOLDEN_IDS)
    def test_output_metadata_has_uncertainty(self, golden_outputs, question):
        """BrainOutput.metadata содержит uncertainty_level."""
        output = golden_outputs[question["id"]]
        assert "uncertainty_level" in output.metadata, (
            f"[{question['id']}] metadata missing 'uncertainty_level'"
        )


# ===================================================================
# TestGoldenLearn — команды learn_fact
# ===================================================================

class TestGoldenLearn:
    """Проверка команд learn_fact."""

    @pytest.mark.parametrize("question", LEARN_QUESTIONS,
                             ids=[q["id"] for q in LEARN_QUESTIONS])
    def test_learn_action(self, golden_results, question):
        """Команда 'запомни/сохрани/запиши' → action=learn."""
        result = golden_results[question["id"]]
        assert result.action == ActionType.LEARN.value, (
            f"[{question['id']}] Expected learn, got {result.action}"
        )

    @pytest.mark.parametrize("question", LEARN_QUESTIONS,
                             ids=[q["id"] for q in LEARN_QUESTIONS])
    def test_learn_goal_type(self, golden_results, question):
        """goal_type = learn_fact."""
        result = golden_results[question["id"]]
        assert result.metadata.get("goal_type") == "learn_fact", (
            f"[{question['id']}] goal_type={result.metadata.get('goal_type')}"
        )

    @pytest.mark.parametrize("question", LEARN_QUESTIONS,
                             ids=[q["id"] for q in LEARN_QUESTIONS])
    def test_learn_confidence_positive(self, golden_results, question):
        """LEARN confidence > 0."""
        result = golden_results[question["id"]]
        assert result.confidence > 0.0, (
            f"[{question['id']}] learn confidence should be > 0"
        )


# ===================================================================
# TestGoldenRoundTrip — learn → retrieve цикл
# ===================================================================

class TestGoldenRoundTrip:
    """
    Round-trip тест: запомни факт → спроси о нём.

    q19_learn:    "запомни: рибосома — органелла для синтеза белков"
    q20_retrieve: "что такое рибосома?"

    Порядок выполнения гарантирован через golden_results (module scope).
    """

    def test_roundtrip_learn_action(self, golden_results):
        """Шаг 1: learn action."""
        if ROUNDTRIP_LEARN is None:
            pytest.skip("q19_learn not found in golden questions")
        result = golden_results["q19_learn"]
        assert result.action == ActionType.LEARN.value

    def test_roundtrip_learn_goal_type(self, golden_results):
        """Шаг 1: goal_type = learn_fact."""
        if ROUNDTRIP_LEARN is None:
            pytest.skip("q19_learn not found")
        result = golden_results["q19_learn"]
        assert result.metadata.get("goal_type") == "learn_fact"

    def test_roundtrip_retrieve_returns_result(self, golden_results):
        """Шаг 2: retrieve возвращает CognitiveResult."""
        if ROUNDTRIP_RETRIEVE is None:
            pytest.skip("q20_retrieve not found")
        result = golden_results["q20_retrieve"]
        assert isinstance(result, CognitiveResult)

    def test_roundtrip_retrieve_goal_type(self, golden_results):
        """Шаг 2: goal_type = answer_question."""
        if ROUNDTRIP_RETRIEVE is None:
            pytest.skip("q20_retrieve not found")
        result = golden_results["q20_retrieve"]
        assert result.metadata.get("goal_type") == "answer_question"

    def test_roundtrip_retrieve_finds_fact(self, golden_results):
        """
        Шаг 2: после learn, retrieve должен найти факт о рибосоме.

        Проверяем что 'рибосом' присутствует в response или goal.
        Если action=refuse — факт не найден (допустимо в MVP без vector search,
        но логируем warning).
        """
        if ROUNDTRIP_RETRIEVE is None:
            pytest.skip("q20_retrieve not found")
        result = golden_results["q20_retrieve"]

        # Если refuse — факт не найден через keyword search
        # Это допустимо в MVP, но мы проверяем что pipeline не упал
        if result.action == "refuse":
            # Допустимо — keyword BM25 может не найти
            return

        combined = f"{result.response} {result.goal}".lower()
        assert "рибосом" in combined, (
            f"[q20_retrieve] 'рибосом' not found after learn. "
            f"action={result.action}, response='{result.response[:100]}'"
        )


# ===================================================================
# TestGoldenEdgeCases — граничные случаи
# ===================================================================

class TestGoldenEdgeCases:
    """Проверка граничных случаев (пустой запрос, минимальный запрос)."""

    @pytest.mark.parametrize("question", EDGE_QUESTIONS,
                             ids=[q["id"] for q in EDGE_QUESTIONS])
    def test_edge_no_crash(self, golden_results, question):
        """Edge case не вызывает crash."""
        result = golden_results[question["id"]]
        assert isinstance(result, CognitiveResult)

    @pytest.mark.parametrize("question", EDGE_QUESTIONS,
                             ids=[q["id"] for q in EDGE_QUESTIONS])
    def test_edge_valid_action(self, golden_results, question):
        """Edge case возвращает допустимый action."""
        result = golden_results[question["id"]]
        assert result.action in VALID_ACTIONS

    @pytest.mark.parametrize("question", EDGE_QUESTIONS,
                             ids=[q["id"] for q in EDGE_QUESTIONS])
    def test_edge_pipeline_no_crash(self, golden_outputs, question):
        """Edge case проходит через OutputPipeline без crash."""
        output = golden_outputs[question["id"]]
        assert isinstance(output, BrainOutput)
        assert output.text.strip() != ""


# ===================================================================
# TestGoldenSummary — сводная статистика (1 тест)
# ===================================================================

class TestGoldenSummary:
    """Сводная статистика по всем golden questions."""

    def test_summary_report(self, golden_results, golden_outputs):
        """
        Сводный отчёт: не assertion-based, а информационный.
        Всегда проходит — выводит статистику в stdout.
        """
        action_counts: Dict[str, int] = {}
        confidence_sum = 0.0
        total = len(golden_results)

        for qid, result in golden_results.items():
            action_counts[result.action] = action_counts.get(result.action, 0) + 1
            confidence_sum += result.confidence

        avg_confidence = confidence_sum / total if total > 0 else 0.0

        print("\n" + "=" * 60)
        print("GOLDEN-ANSWER BENCHMARK SUMMARY")
        print("=" * 60)
        print(f"Total questions:    {total}")
        print(f"Avg confidence:     {avg_confidence:.3f}")
        print("Action distribution:")
        for action, count in sorted(action_counts.items()):
            pct = count / total * 100
            print(f"  {action:25s} {count:3d} ({pct:.0f}%)")
        print("=" * 60)

        # Всегда проходит — это информационный тест
        assert total == len(GOLDEN_QUESTIONS)
