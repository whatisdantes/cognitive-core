"""
tests/test_online_learner.py

Тесты для Этапа I: OnlineLearner (brain/learning/online_learner.py).

Покрывает:
  - OnlineLearningUpdate — ContractMixin round-trip, defaults
  - OnlineLearner.update() — action=learn, contradict, answer, no-op при confidence < 0.3
  - OnlineLearner.confirm_fact() / deny_fact() — делегирование в semantic
  - OnlineLearner._update_associations() — Хеббовское обучение
  - OnlineLearner._extract_concepts() — токенизация, стоп-слова, дедупликация
  - OnlineLearner.status() / __repr__()
  - Важно: deny_fact() ТОЛЬКО при action == "contradict"
"""

from __future__ import annotations

from unittest.mock import MagicMock

from brain.core.contracts import CognitiveResult, TraceChain, TraceRef
from brain.learning.online_learner import OnlineLearner, OnlineLearningUpdate

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _make_memory() -> MagicMock:
    """Создать mock MemoryManager."""
    memory = MagicMock()
    memory.semantic = MagicMock()
    memory.semantic.confirm_fact = MagicMock()
    memory.semantic.deny_fact = MagicMock()
    memory.semantic.add_relation = MagicMock()
    memory.source = MagicMock()
    memory.source.update_trust = MagicMock()
    return memory


def _make_trace_chain() -> TraceChain:
    """Создать минимальный TraceChain."""
    return TraceChain(
        trace_id="trace_001",
        session_id="session_001",
        cycle_id="cycle_1",
        steps=[],
        summary="тест",
    )


def _make_result(
    action: str = "answer",
    confidence: float = 0.8,
    memory_refs: list | None = None,
    source_refs: list | None = None,
    goal: str = "что такое нейрон",
    cycle_id: str = "cycle_1",
    metadata: dict | None = None,
) -> CognitiveResult:
    """Создать CognitiveResult для тестов."""
    if memory_refs is None:
        memory_refs = []
    if source_refs is None:
        source_refs = []

    return CognitiveResult(
        action=action,
        response="Тестовый ответ",
        confidence=confidence,
        trace=_make_trace_chain(),
        goal=goal,
        trace_id="trace_001",
        session_id="session_001",
        cycle_id=cycle_id,
        memory_refs=memory_refs,
        source_refs=source_refs,
        metadata=metadata or {},
    )


def _make_trace_ref(ref_id: str, note: str = "") -> TraceRef:
    """Создать TraceRef для тестов."""
    return TraceRef(ref_type="memory", ref_id=ref_id, note=note)


# ---------------------------------------------------------------------------
# 1. OnlineLearningUpdate — ContractMixin round-trip
# ---------------------------------------------------------------------------


class TestOnlineLearningUpdate:
    """Тесты OnlineLearningUpdate — ContractMixin round-trip и defaults."""

    def test_defaults(self):
        update = OnlineLearningUpdate(cycle_id="cycle_1")
        assert update.cycle_id == "cycle_1"
        assert update.facts_confirmed == []
        assert update.facts_denied == []
        assert update.associations_updated == []
        assert update.sources_updated == []
        assert update.duration_ms == 0.0

    def test_to_dict(self):
        update = OnlineLearningUpdate(
            cycle_id="cycle_42",
            facts_confirmed=["нейрон", "синапс"],
            facts_denied=["миф"],
            duration_ms=5.5,
        )
        d = update.to_dict()
        assert d["cycle_id"] == "cycle_42"
        assert d["facts_confirmed"] == ["нейрон", "синапс"]
        assert d["facts_denied"] == ["миф"]
        assert d["duration_ms"] == 5.5

    def test_from_dict_roundtrip(self):
        update = OnlineLearningUpdate(
            cycle_id="cycle_7",
            facts_confirmed=["факт1"],
            facts_denied=["ложь1"],
            associations_updated=[{"a": "x", "b": "y", "delta": 0.01}],
            sources_updated=[{"source": "wiki", "confirmed": True}],
            duration_ms=12.3,
        )
        d = update.to_dict()
        update2 = OnlineLearningUpdate.from_dict(d)
        assert update2.cycle_id == update.cycle_id
        assert update2.facts_confirmed == update.facts_confirmed
        assert update2.facts_denied == update.facts_denied
        assert update2.duration_ms == update.duration_ms


# ---------------------------------------------------------------------------
# 2. OnlineLearner — инициализация
# ---------------------------------------------------------------------------


class TestOnlineLearnerInit:
    """Тесты инициализации OnlineLearner."""

    def test_default_params(self):
        memory = _make_memory()
        learner = OnlineLearner(memory=memory)
        status = learner.status()
        assert status["learning_rate"] == 0.01
        assert status["confirm_delta"] == 0.05
        assert status["deny_delta"] == 0.1
        assert status["update_count"] == 0
        assert status["total_confirmed"] == 0
        assert status["total_denied"] == 0
        assert status["total_associations"] == 0

    def test_custom_params(self):
        memory = _make_memory()
        learner = OnlineLearner(
            memory=memory,
            learning_rate=0.05,
            confirm_delta=0.1,
            deny_delta=0.2,
        )
        status = learner.status()
        assert status["learning_rate"] == 0.05
        assert status["confirm_delta"] == 0.1
        assert status["deny_delta"] == 0.2

    def test_repr(self):
        memory = _make_memory()
        learner = OnlineLearner(memory=memory)
        r = repr(learner)
        assert "OnlineLearner" in r
        assert "updates=0" in r


# ---------------------------------------------------------------------------
# 3. OnlineLearner.update() — no-op при низком confidence
# ---------------------------------------------------------------------------


class TestOnlineLearnerUpdateLowConfidence:
    """Тесты no-op при confidence < 0.3."""

    def setup_method(self):
        self.memory = _make_memory()
        self.learner = OnlineLearner(memory=self.memory)

    def test_noop_when_confidence_below_threshold(self):
        """confidence < 0.3 → no-op, ничего не вызывается."""
        result = _make_result(action="learn", confidence=0.2)
        update = self.learner.update(result)
        assert update.facts_confirmed == []
        assert update.facts_denied == []
        assert update.associations_updated == []
        self.memory.semantic.confirm_fact.assert_not_called()

    def test_noop_at_exactly_zero_confidence(self):
        result = _make_result(action="learn", confidence=0.0)
        update = self.learner.update(result)
        assert update.facts_confirmed == []

    def test_noop_at_029_confidence(self):
        result = _make_result(action="learn", confidence=0.29)
        update = self.learner.update(result)
        assert update.facts_confirmed == []

    def test_update_count_not_incremented_on_noop(self):
        result = _make_result(action="learn", confidence=0.1)
        self.learner.update(result)
        assert self.learner.status()["update_count"] == 0

    def test_duration_ms_set_even_on_noop(self):
        result = _make_result(action="learn", confidence=0.1)
        update = self.learner.update(result)
        assert update.duration_ms >= 0.0

    def test_cycle_id_set_on_noop(self):
        result = _make_result(action="learn", confidence=0.1, cycle_id="cycle_noop")
        update = self.learner.update(result)
        assert update.cycle_id == "cycle_noop"


# ---------------------------------------------------------------------------
# 4. OnlineLearner.update() — action == "learn"
# ---------------------------------------------------------------------------


class TestOnlineLearnerUpdateLearn:
    """Тесты update() при action == 'learn'."""

    def setup_method(self):
        self.memory = _make_memory()
        self.learner = OnlineLearner(memory=self.memory)

    def test_confirm_fact_called_for_each_memory_ref(self):
        """confirm_fact() вызывается для каждого memory_ref."""
        refs = [_make_trace_ref("нейрон"), _make_trace_ref("синапс")]
        result = _make_result(action="learn", confidence=0.8, memory_refs=refs)
        update = self.learner.update(result)
        assert "нейрон" in update.facts_confirmed
        assert "синапс" in update.facts_confirmed
        assert self.memory.semantic.confirm_fact.call_count == 2

    def test_deny_fact_not_called_on_learn(self):
        """deny_fact() НЕ вызывается при action == 'learn'."""
        refs = [_make_trace_ref("нейрон")]
        result = _make_result(action="learn", confidence=0.8, memory_refs=refs)
        self.learner.update(result)
        self.memory.semantic.deny_fact.assert_not_called()

    def test_update_count_incremented(self):
        result = _make_result(action="learn", confidence=0.8)
        self.learner.update(result)
        assert self.learner.status()["update_count"] == 1

    def test_total_confirmed_incremented(self):
        refs = [_make_trace_ref("нейрон"), _make_trace_ref("синапс")]
        result = _make_result(action="learn", confidence=0.8, memory_refs=refs)
        self.learner.update(result)
        assert self.learner.status()["total_confirmed"] == 2

    def test_no_memory_refs_no_confirm(self):
        """Нет memory_refs → confirm_fact не вызывается."""
        result = _make_result(action="learn", confidence=0.8, memory_refs=[])
        update = self.learner.update(result)
        assert update.facts_confirmed == []
        self.memory.semantic.confirm_fact.assert_not_called()

    def test_confirm_fact_with_source_ref(self):
        """confirm_fact вызывается с source_ref из note."""
        refs = [_make_trace_ref("нейрон", note="wiki")]
        result = _make_result(action="learn", confidence=0.8, memory_refs=refs)
        self.learner.update(result)
        # confirm_fact вызван с concept="нейрон"
        call_args = self.memory.semantic.confirm_fact.call_args
        assert call_args[0][0] == "нейрон" or call_args[1].get("concept") == "нейрон"


# ---------------------------------------------------------------------------
# 5. OnlineLearner.update() — action == "contradict"
# ---------------------------------------------------------------------------


class TestOnlineLearnerUpdateContradict:
    """Тесты update() при action == 'contradict'."""

    def setup_method(self):
        self.memory = _make_memory()
        self.learner = OnlineLearner(memory=self.memory)

    def test_deny_fact_called_for_each_memory_ref(self):
        """deny_fact() вызывается для каждого memory_ref при contradict."""
        refs = [_make_trace_ref("миф"), _make_trace_ref("заблуждение")]
        result = _make_result(action="contradict", confidence=0.8, memory_refs=refs)
        update = self.learner.update(result)
        assert "миф" in update.facts_denied
        assert "заблуждение" in update.facts_denied
        assert self.memory.semantic.deny_fact.call_count == 2

    def test_confirm_fact_not_called_on_contradict(self):
        """confirm_fact() НЕ вызывается при action == 'contradict'."""
        refs = [_make_trace_ref("миф")]
        result = _make_result(action="contradict", confidence=0.8, memory_refs=refs)
        self.learner.update(result)
        self.memory.semantic.confirm_fact.assert_not_called()

    def test_total_denied_incremented(self):
        refs = [_make_trace_ref("миф")]
        result = _make_result(action="contradict", confidence=0.8, memory_refs=refs)
        self.learner.update(result)
        assert self.learner.status()["total_denied"] == 1

    def test_deny_fact_not_called_on_low_confidence_retrieval(self):
        """
        Важно: deny_fact() НЕ вызывается при низком confidence retrieval.
        Низкий confidence при поиске ≠ «факт ложный».
        deny_fact() ТОЛЬКО при явном action == 'contradict'.
        """
        refs = [_make_trace_ref("нейрон")]
        # action="answer" с низким confidence — НЕ contradict
        result = _make_result(action="answer", confidence=0.4, memory_refs=refs)
        self.learner.update(result)
        self.memory.semantic.deny_fact.assert_not_called()


# ---------------------------------------------------------------------------
# 6. OnlineLearner.update() — Хеббовское обучение
# ---------------------------------------------------------------------------


class TestOnlineLearnerHebbian:
    """Тесты Хеббовского обучения при confidence > 0.7."""

    def setup_method(self):
        self.memory = _make_memory()
        self.learner = OnlineLearner(memory=self.memory)

    def test_associations_updated_when_high_confidence(self):
        """confidence > 0.7 и goal с ≥2 концептами → add_relation вызывается."""
        result = _make_result(
            action="answer",
            confidence=0.9,
            goal="нейрон синапс мозг",
        )
        update = self.learner.update(result)
        assert len(update.associations_updated) > 0
        assert self.memory.semantic.add_relation.called

    def test_no_associations_when_low_confidence(self):
        """confidence <= 0.7 → нет Хеббовского обучения."""
        result = _make_result(
            action="answer",
            confidence=0.5,
            goal="нейрон синапс мозг",
        )
        update = self.learner.update(result)
        assert update.associations_updated == []

    def test_no_associations_when_single_concept(self):
        """Один концепт → нет ассоциаций (нужно ≥2)."""
        result = _make_result(
            action="answer",
            confidence=0.9,
            goal="нейрон",
        )
        update = self.learner.update(result)
        assert update.associations_updated == []

    def test_no_associations_when_empty_goal(self):
        """Пустой goal → нет ассоциаций."""
        result = _make_result(action="answer", confidence=0.9, goal="")
        update = self.learner.update(result)
        assert update.associations_updated == []

    def test_total_associations_incremented(self):
        result = _make_result(
            action="answer",
            confidence=0.9,
            goal="нейрон синапс мозг",
        )
        self.learner.update(result)
        assert self.learner.status()["total_associations"] > 0

    def test_association_delta_formula(self):
        """Δweight = learning_rate × confidence."""
        learner = OnlineLearner(memory=self.memory, learning_rate=0.01)
        result = _make_result(action="answer", confidence=0.9, goal="нейрон синапс")
        update = learner.update(result)
        if update.associations_updated:
            expected_delta = round(0.01 * 0.9, 4)
            assert update.associations_updated[0]["delta"] == expected_delta

    def test_no_associations_for_answer_question_goal_type(self):
        """Обычный пользовательский вопрос не должен создавать новые связи."""
        result = _make_result(
            action="answer",
            confidence=0.9,
            goal="Что ты помнишь про Linux?",
            metadata={"goal_type": "answer_question"},
        )
        update = self.learner.update(result)
        assert update.associations_updated == []
        self.memory.semantic.add_relation.assert_not_called()


# ---------------------------------------------------------------------------
# 7. OnlineLearner.update() — обновление источников
# ---------------------------------------------------------------------------


class TestOnlineLearnerSourceTrust:
    """Тесты обновления доверия к источникам."""

    def setup_method(self):
        self.memory = _make_memory()
        self.learner = OnlineLearner(memory=self.memory)

    def test_source_trust_updated_on_learn(self):
        """update_trust вызывается для source_refs при action=learn."""
        source_refs = [_make_trace_ref("wiki")]
        result = _make_result(action="learn", confidence=0.8, source_refs=source_refs)
        update = self.learner.update(result)
        assert len(update.sources_updated) == 1
        assert update.sources_updated[0]["source"] == "wiki"
        assert update.sources_updated[0]["confirmed"] is True

    def test_source_trust_updated_on_answer(self):
        """update_trust вызывается при action=answer."""
        source_refs = [_make_trace_ref("arxiv")]
        result = _make_result(action="answer", confidence=0.8, source_refs=source_refs)
        update = self.learner.update(result)
        assert len(update.sources_updated) == 1
        assert update.sources_updated[0]["confirmed"] is True

    def test_source_trust_not_confirmed_on_contradict(self):
        """update_trust с confirmed=False при action=contradict."""
        source_refs = [_make_trace_ref("bad_source")]
        result = _make_result(action="contradict", confidence=0.8, source_refs=source_refs)
        update = self.learner.update(result)
        assert len(update.sources_updated) == 1
        assert update.sources_updated[0]["confirmed"] is False

    def test_no_source_update_when_empty_ref_id(self):
        """Пустой ref_id → update_trust не вызывается."""
        source_refs = [_make_trace_ref("")]
        result = _make_result(action="learn", confidence=0.8, source_refs=source_refs)
        self.learner.update(result)
        self.memory.source.update_trust.assert_not_called()

    def test_multiple_sources_updated(self):
        source_refs = [_make_trace_ref("wiki"), _make_trace_ref("arxiv")]
        result = _make_result(action="learn", confidence=0.8, source_refs=source_refs)
        update = self.learner.update(result)
        assert len(update.sources_updated) == 2


# ---------------------------------------------------------------------------
# 8. OnlineLearner.confirm_fact() / deny_fact()
# ---------------------------------------------------------------------------


class TestOnlineLearnerConfirmDeny:
    """Тесты confirm_fact() и deny_fact() напрямую."""

    def setup_method(self):
        self.memory = _make_memory()
        self.learner = OnlineLearner(memory=self.memory)

    def test_confirm_fact_calls_semantic(self):
        self.learner.confirm_fact("нейрон")
        self.memory.semantic.confirm_fact.assert_called_once_with("нейрон", delta=0.05)

    def test_confirm_fact_empty_concept_noop(self):
        self.learner.confirm_fact("")
        self.memory.semantic.confirm_fact.assert_not_called()

    def test_deny_fact_calls_semantic(self):
        self.learner.deny_fact("миф")
        self.memory.semantic.deny_fact.assert_called_once_with("миф", delta=0.1)

    def test_deny_fact_empty_concept_noop(self):
        self.learner.deny_fact("")
        self.memory.semantic.deny_fact.assert_not_called()

    def test_confirm_fact_with_source_ref_updates_trust(self):
        self.learner.confirm_fact("нейрон", source_ref="wiki")
        self.memory.source.update_trust.assert_called_once_with("wiki", confirmed=True)

    def test_deny_fact_with_source_ref_updates_trust(self):
        self.learner.deny_fact("миф", source_ref="bad_source")
        self.memory.source.update_trust.assert_called_once_with("bad_source", confirmed=False)

    def test_confirm_fact_exception_handled_gracefully(self):
        """Исключение в semantic.confirm_fact не пробрасывается."""
        self.memory.semantic.confirm_fact.side_effect = RuntimeError("ошибка")
        # Не должно выбрасывать исключение
        self.learner.confirm_fact("нейрон")

    def test_deny_fact_exception_handled_gracefully(self):
        """Исключение в semantic.deny_fact не пробрасывается."""
        self.memory.semantic.deny_fact.side_effect = RuntimeError("ошибка")
        self.learner.deny_fact("миф")


# ---------------------------------------------------------------------------
# 9. OnlineLearner._extract_concepts()
# ---------------------------------------------------------------------------


class TestExtractConcepts:
    """Тесты _extract_concepts() — токенизация и фильтрация."""

    def test_basic_extraction(self):
        concepts = OnlineLearner._extract_concepts("нейрон синапс мозг")
        assert "нейрон" in concepts
        assert "синапс" in concepts
        assert "мозг" in concepts

    def test_stop_words_filtered(self):
        """Стоп-слова фильтруются."""
        concepts = OnlineLearner._extract_concepts("что такое нейрон")
        assert "что" not in concepts

    def test_short_words_filtered(self):
        """Слова короче 4 символов фильтруются."""
        concepts = OnlineLearner._extract_concepts("нейрон и мозг")
        assert "и" not in concepts

    def test_max_five_concepts(self):
        """Возвращается не более 5 концептов."""
        text = "нейрон синапс мозг гиппокамп кортекс амигдала таламус"
        concepts = OnlineLearner._extract_concepts(text)
        assert len(concepts) <= 5

    def test_deduplication(self):
        """Дубликаты удаляются."""
        concepts = OnlineLearner._extract_concepts("нейрон нейрон синапс")
        assert concepts.count("нейрон") == 1

    def test_punctuation_stripped(self):
        """Пунктуация удаляется."""
        concepts = OnlineLearner._extract_concepts("нейрон, синапс!")
        assert "нейрон" in concepts
        assert "синапс" in concepts

    def test_empty_text_returns_empty(self):
        concepts = OnlineLearner._extract_concepts("")
        assert concepts == []

    def test_order_preserved(self):
        """Порядок концептов сохраняется (первые 5)."""
        concepts = OnlineLearner._extract_concepts("нейрон синапс мозг")
        assert concepts[0] == "нейрон"
        assert concepts[1] == "синапс"

    def test_returns_list(self):
        concepts = OnlineLearner._extract_concepts("нейрон синапс")
        assert isinstance(concepts, list)

    def test_question_words_filtered(self):
        concepts = OnlineLearner._extract_concepts("Что ты помнишь про Linux")
        assert "помнишь" not in concepts
        assert "linux" in concepts


# ---------------------------------------------------------------------------
# 10. OnlineLearner.status() / __repr__()
# ---------------------------------------------------------------------------


class TestOnlineLearnerStatus:
    """Тесты status() и __repr__()."""

    def setup_method(self):
        self.memory = _make_memory()
        self.learner = OnlineLearner(memory=self.memory)

    def test_status_returns_dict(self):
        status = self.learner.status()
        assert isinstance(status, dict)

    def test_status_keys(self):
        status = self.learner.status()
        for key in ("update_count", "total_confirmed", "total_denied",
                    "total_associations", "learning_rate", "confirm_delta", "deny_delta"):
            assert key in status

    def test_status_increments_after_update(self):
        refs = [_make_trace_ref("нейрон")]
        result = _make_result(action="learn", confidence=0.8, memory_refs=refs)
        self.learner.update(result)
        status = self.learner.status()
        assert status["update_count"] == 1
        assert status["total_confirmed"] == 1

    def test_repr_contains_key_info(self):
        r = repr(self.learner)
        assert "OnlineLearner" in r
        assert "updates=" in r
        assert "confirmed=" in r
        assert "denied=" in r
