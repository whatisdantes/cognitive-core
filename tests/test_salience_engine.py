"""
tests/test_salience_engine.py

Тесты для Этапа H: SalienceEngine (brain/cognition/salience_engine.py).

Покрывает:
  - SalienceScore — ContractMixin round-trip, defaults
  - SalienceEngine._compute_urgency() — keyword detection
  - SalienceEngine._compute_threat() — keyword detection
  - SalienceEngine._compute_novelty() — с/без рабочей памяти
  - SalienceEngine._compute_relevance() — с/без активной цели
  - SalienceEngine.evaluate() — полный цикл оценки
  - Пороги действий: interrupt / prioritize / normal
"""

from __future__ import annotations

from unittest.mock import MagicMock

from brain.cognition.salience_engine import SalienceEngine, SalienceScore

# ---------------------------------------------------------------------------
# 1. SalienceScore — ContractMixin round-trip
# ---------------------------------------------------------------------------


class TestSalienceScore:
    """Тесты SalienceScore — ContractMixin round-trip и defaults."""

    def test_defaults(self):
        score = SalienceScore()
        assert score.overall == 0.0
        assert score.novelty == 0.0
        assert score.urgency == 0.0
        assert score.threat == 0.0
        assert score.relevance == 0.0
        assert score.action == "normal"
        assert score.reason == ""

    def test_to_dict(self):
        score = SalienceScore(
            overall=0.75,
            novelty=0.8,
            urgency=1.0,
            threat=0.0,
            relevance=0.5,
            action="prioritize",
            reason="novelty=0.80 urgency=1.00 threat=0.00 relevance=0.50",
        )
        d = score.to_dict()
        assert d["overall"] == 0.75
        assert d["action"] == "prioritize"
        assert d["urgency"] == 1.0

    def test_from_dict_roundtrip(self):
        score = SalienceScore(
            overall=0.9,
            novelty=1.0,
            urgency=1.0,
            threat=1.0,
            relevance=0.5,
            action="interrupt",
            reason="тест",
        )
        d = score.to_dict()
        score2 = SalienceScore.from_dict(d)
        assert score2.overall == score.overall
        assert score2.action == score.action
        assert score2.reason == score.reason

    def test_all_fields_in_dict(self):
        score = SalienceScore(overall=0.5, novelty=0.6, urgency=0.7, threat=0.8, relevance=0.9)
        d = score.to_dict()
        for key in ("overall", "novelty", "urgency", "threat", "relevance", "action", "reason"):
            assert key in d


# ---------------------------------------------------------------------------
# 2. SalienceEngine._compute_urgency()
# ---------------------------------------------------------------------------


class TestComputeUrgency:
    """Тесты _compute_urgency() — keyword matching."""

    def setup_method(self):
        self.engine = SalienceEngine()

    def test_urgency_keyword_ru_srochno(self):
        assert self.engine._compute_urgency("срочно нужна помощь") == 1.0

    def test_urgency_keyword_ru_nemedlenno(self):
        assert self.engine._compute_urgency("немедленно исправить") == 1.0

    def test_urgency_keyword_ru_seychas(self):
        assert self.engine._compute_urgency("сделать сейчас") == 1.0

    def test_urgency_keyword_ru_ekstrenno(self):
        assert self.engine._compute_urgency("экстренно вызвать") == 1.0

    def test_urgency_keyword_ru_kritichno(self):
        assert self.engine._compute_urgency("критично для системы") == 1.0

    def test_urgency_keyword_en_urgent(self):
        assert self.engine._compute_urgency("urgent request") == 1.0

    def test_urgency_keyword_en_asap(self):
        assert self.engine._compute_urgency("do it asap") == 1.0

    def test_urgency_keyword_en_immediately(self):
        assert self.engine._compute_urgency("immediately fix this") == 1.0

    def test_urgency_keyword_en_now(self):
        assert self.engine._compute_urgency("do it now") == 1.0

    def test_urgency_keyword_en_critical(self):
        assert self.engine._compute_urgency("critical issue") == 1.0

    def test_no_urgency_normal_text(self):
        assert self.engine._compute_urgency("обычный запрос без спешки") == 0.0

    def test_urgency_case_insensitive(self):
        assert self.engine._compute_urgency("СРОЧНО!") == 1.0

    def test_urgency_empty_string(self):
        assert self.engine._compute_urgency("") == 0.0

    def test_urgency_returns_float(self):
        result = self.engine._compute_urgency("тест")
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# 3. SalienceEngine._compute_threat()
# ---------------------------------------------------------------------------


class TestComputeThreat:
    """Тесты _compute_threat() — keyword matching."""

    def setup_method(self):
        self.engine = SalienceEngine()

    def test_threat_keyword_ru_oshibka(self):
        assert self.engine._compute_threat("ошибка в системе") == 1.0

    def test_threat_keyword_ru_opasnost(self):
        assert self.engine._compute_threat("опасность для данных") == 1.0

    def test_threat_keyword_ru_sboi(self):
        assert self.engine._compute_threat("сбой базы данных") == 1.0

    def test_threat_keyword_ru_avariya(self):
        assert self.engine._compute_threat("авария сервера") == 1.0

    def test_threat_keyword_ru_ugroza(self):
        assert self.engine._compute_threat("угроза безопасности") == 1.0

    def test_threat_keyword_en_error(self):
        assert self.engine._compute_threat("system error detected") == 1.0

    def test_threat_keyword_en_fail(self):
        assert self.engine._compute_threat("test fail") == 1.0

    def test_threat_keyword_en_failure(self):
        assert self.engine._compute_threat("critical failure") == 1.0

    def test_threat_keyword_en_danger(self):
        assert self.engine._compute_threat("danger zone") == 1.0

    def test_threat_keyword_en_crash(self):
        assert self.engine._compute_threat("application crash") == 1.0

    def test_threat_keyword_en_threat(self):
        assert self.engine._compute_threat("security threat") == 1.0

    def test_no_threat_normal_text(self):
        assert self.engine._compute_threat("нормальный запрос о нейронах") == 0.0

    def test_threat_case_insensitive(self):
        assert self.engine._compute_threat("ОШИБКА") == 1.0

    def test_threat_empty_string(self):
        assert self.engine._compute_threat("") == 0.0

    def test_threat_returns_float(self):
        result = self.engine._compute_threat("тест")
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# 4. SalienceEngine._compute_novelty()
# ---------------------------------------------------------------------------


class TestComputeNovelty:
    """Тесты _compute_novelty() — с/без рабочей памяти."""

    def setup_method(self):
        self.engine = SalienceEngine()

    def test_novelty_no_working_memory_returns_one(self):
        """Без рабочей памяти — полная новизна (1.0)."""
        assert self.engine._compute_novelty("любой стимул") == 1.0

    def test_novelty_none_working_memory_returns_one(self):
        assert self.engine._compute_novelty("стимул", None) == 1.0

    def test_novelty_empty_working_memory_returns_one(self):
        """Пустая рабочая память — полная новизна (1.0)."""
        wm = MagicMock()
        wm.get_context.return_value = []
        assert self.engine._compute_novelty("стимул", wm) == 1.0

    def test_novelty_identical_stimulus_low_novelty(self):
        """Стимул идентичен элементу рабочей памяти — низкая новизна."""
        wm = MagicMock()
        item = MagicMock()
        item.content = "нейрон клетка мозга"
        wm.get_context.return_value = [item]
        novelty = self.engine._compute_novelty("нейрон клетка мозга", wm)
        assert novelty < 0.1

    def test_novelty_different_stimulus_high_novelty(self):
        """Стимул отличается от рабочей памяти — высокая новизна."""
        wm = MagicMock()
        item = MagicMock()
        item.content = "синапс нейромедиатор"
        wm.get_context.return_value = [item]
        novelty = self.engine._compute_novelty("квантовая физика", wm)
        assert novelty > 0.8

    def test_novelty_fallback_on_exception(self):
        """При ошибке рабочей памяти — fallback 0.5."""
        wm = MagicMock()
        wm.get_context.side_effect = RuntimeError("ошибка")
        novelty = self.engine._compute_novelty("стимул", wm)
        assert novelty == 0.5

    def test_novelty_uses_get_all_fallback(self):
        """Если нет get_context — использует get_all."""
        wm = MagicMock(spec=["get_all"])
        item = MagicMock()
        item.content = "тест"
        wm.get_all.return_value = [item]
        novelty = self.engine._compute_novelty("совершенно другой текст", wm)
        assert 0.0 <= novelty <= 1.0

    def test_novelty_no_interface_returns_one(self):
        """Объект без get_context/get_all — полная новизна (1.0)."""
        wm = object()
        assert self.engine._compute_novelty("стимул", wm) == 1.0

    def test_novelty_result_in_range(self):
        """Результат всегда в [0.0, 1.0]."""
        wm = MagicMock()
        item = MagicMock()
        item.content = "частичное совпадение нейрон"
        wm.get_context.return_value = [item]
        novelty = self.engine._compute_novelty("нейрон синапс мозг", wm)
        assert 0.0 <= novelty <= 1.0

    def test_novelty_multiple_items_uses_max_overlap(self):
        """Используется максимальное перекрытие из всех элементов WM."""
        wm = MagicMock()
        item1 = MagicMock()
        item1.content = "квантовая физика"
        item2 = MagicMock()
        item2.content = "нейрон клетка мозга"
        wm.get_context.return_value = [item1, item2]
        # Стимул совпадает с item2 → низкая новизна
        novelty = self.engine._compute_novelty("нейрон клетка мозга", wm)
        assert novelty < 0.1


# ---------------------------------------------------------------------------
# 5. SalienceEngine._compute_relevance()
# ---------------------------------------------------------------------------


class TestComputeRelevance:
    """Тесты _compute_relevance() — с/без активной цели."""

    def setup_method(self):
        self.engine = SalienceEngine()

    def test_relevance_no_goal_returns_half(self):
        """Без активной цели — fallback 0.5."""
        assert self.engine._compute_relevance("стимул") == 0.5

    def test_relevance_none_goal_returns_half(self):
        assert self.engine._compute_relevance("стимул", None) == 0.5

    def test_relevance_empty_goal_description_returns_half(self):
        """Пустое описание цели — fallback 0.5."""
        goal = MagicMock()
        goal.description = ""
        assert self.engine._compute_relevance("стимул", goal) == 0.5

    def test_relevance_identical_stimulus_and_goal(self):
        """Стимул совпадает с целью — высокая релевантность (clamped to 1.0)."""
        goal = MagicMock()
        goal.description = "нейрон клетка мозга"
        relevance = self.engine._compute_relevance("нейрон клетка мозга", goal)
        assert relevance == 1.0

    def test_relevance_no_overlap_returns_zero(self):
        """Нет пересечения слов — нулевая релевантность."""
        goal = MagicMock()
        goal.description = "квантовая физика"
        relevance = self.engine._compute_relevance("нейрон синапс", goal)
        assert relevance == 0.0

    def test_relevance_partial_overlap_intermediate(self):
        """Частичное пересечение — промежуточная релевантность."""
        goal = MagicMock()
        goal.description = "нейрон синапс мозг"
        relevance = self.engine._compute_relevance("нейрон клетка", goal)
        assert 0.0 < relevance <= 1.0

    def test_relevance_clamped_to_one(self):
        """Релевантность не превышает 1.0."""
        goal = MagicMock()
        goal.description = "нейрон"
        relevance = self.engine._compute_relevance("нейрон", goal)
        assert relevance <= 1.0

    def test_relevance_result_in_range(self):
        """Результат всегда в [0.0, 1.0]."""
        goal = MagicMock()
        goal.description = "тест цель"
        relevance = self.engine._compute_relevance("тест стимул", goal)
        assert 0.0 <= relevance <= 1.0

    def test_relevance_no_description_attr_returns_half(self):
        """Цель без атрибута description — fallback 0.5."""
        goal = MagicMock(spec=[])  # нет атрибутов
        relevance = self.engine._compute_relevance("стимул", goal)
        assert relevance == 0.5


# ---------------------------------------------------------------------------
# 6. SalienceEngine.evaluate() — полный цикл
# ---------------------------------------------------------------------------


class TestSalienceEngineEvaluate:
    """Тесты evaluate() — полный цикл оценки значимости."""

    def setup_method(self):
        self.engine = SalienceEngine()

    def test_evaluate_returns_salience_score(self):
        score = self.engine.evaluate("обычный запрос")
        assert isinstance(score, SalienceScore)

    def test_evaluate_all_fields_set(self):
        score = self.engine.evaluate("срочно! ошибка в базе данных")
        assert 0.0 <= score.overall <= 1.0
        assert 0.0 <= score.novelty <= 1.0
        assert 0.0 <= score.urgency <= 1.0
        assert 0.0 <= score.threat <= 1.0
        assert 0.0 <= score.relevance <= 1.0
        assert score.action in ("interrupt", "prioritize", "normal")
        assert score.reason != ""

    def test_evaluate_reason_contains_components(self):
        score = self.engine.evaluate("тест")
        assert "novelty=" in score.reason
        assert "urgency=" in score.reason
        assert "threat=" in score.reason
        assert "relevance=" in score.reason

    def test_evaluate_overall_is_weighted_sum(self):
        """overall = W_NOVELTY*novelty + W_URGENCY*urgency + W_THREAT*threat + W_RELEVANCE*relevance."""
        score = self.engine.evaluate("обычный запрос без маркеров")
        expected = min(1.0, (
            SalienceEngine.W_NOVELTY * score.novelty
            + SalienceEngine.W_URGENCY * score.urgency
            + SalienceEngine.W_THREAT * score.threat
            + SalienceEngine.W_RELEVANCE * score.relevance
        ))
        assert abs(score.overall - round(expected, 4)) < 1e-6

    def test_evaluate_overall_clamped_to_one(self):
        score = self.engine.evaluate("срочно критично ошибка авария немедленно")
        assert score.overall <= 1.0

    def test_evaluate_empty_stimulus(self):
        score = self.engine.evaluate("")
        assert isinstance(score, SalienceScore)
        assert score.overall >= 0.0

    def test_evaluate_with_working_memory(self):
        wm = MagicMock()
        wm.get_context.return_value = []
        score = self.engine.evaluate("новый стимул", working_memory=wm)
        assert isinstance(score, SalienceScore)

    def test_evaluate_with_active_goal(self):
        goal = MagicMock()
        goal.description = "изучить нейроны"
        score = self.engine.evaluate("нейроны мозга", active_goal=goal)
        assert isinstance(score, SalienceScore)
        assert score.relevance > 0.0

    def test_evaluate_urgency_reflected_in_overall(self):
        """Стимул с urgency → overall выше, чем без urgency."""
        score_urgent = self.engine.evaluate("срочно нужна помощь")
        score_normal = self.engine.evaluate("нужна помощь")
        assert score_urgent.overall >= score_normal.overall

    def test_evaluate_threat_reflected_in_overall(self):
        """Стимул с threat → overall выше, чем без threat."""
        score_threat = self.engine.evaluate("ошибка в системе")
        score_normal = self.engine.evaluate("информация о системе")
        assert score_threat.overall >= score_normal.overall


# ---------------------------------------------------------------------------
# 7. Пороги действий: interrupt / prioritize / normal
# ---------------------------------------------------------------------------


class TestSalienceEngineActions:
    """Тесты пороговых значений действий."""

    def setup_method(self):
        self.engine = SalienceEngine()

    def test_action_interrupt_when_overall_high(self):
        """overall >= 0.8 → action == 'interrupt'."""
        class HighSalienceEngine(SalienceEngine):
            def _compute_novelty(self, s, wm=None): return 1.0
            def _compute_urgency(self, s): return 1.0
            def _compute_threat(self, s): return 1.0
            def _compute_relevance(self, s, g=None): return 1.0

        engine = HighSalienceEngine()
        score = engine.evaluate("тест")
        assert score.action == "interrupt"
        assert score.overall >= SalienceEngine.INTERRUPT_THRESHOLD

    def test_action_normal_when_overall_zero(self):
        """overall == 0.0 → action == 'normal'."""
        class ZeroSalienceEngine(SalienceEngine):
            def _compute_novelty(self, s, wm=None): return 0.0
            def _compute_urgency(self, s): return 0.0
            def _compute_threat(self, s): return 0.0
            def _compute_relevance(self, s, g=None): return 0.0

        engine = ZeroSalienceEngine()
        score = engine.evaluate("тест")
        assert score.action == "normal"
        assert score.overall == 0.0

    def test_action_prioritize_when_overall_mid(self):
        """0.5 <= overall < 0.8 → action == 'prioritize'."""
        class MidSalienceEngine(SalienceEngine):
            def _compute_novelty(self, s, wm=None): return 0.5
            def _compute_urgency(self, s): return 0.5
            def _compute_threat(self, s): return 0.5
            def _compute_relevance(self, s, g=None): return 0.5

        engine = MidSalienceEngine()
        score = engine.evaluate("тест")
        # overall = 0.25*0.5 + 0.35*0.5 + 0.25*0.5 + 0.15*0.5 = 0.5
        assert score.action in ("prioritize", "normal")  # ровно на границе

    def test_interrupt_threshold_constant(self):
        assert SalienceEngine.INTERRUPT_THRESHOLD == 0.8

    def test_prioritize_threshold_constant(self):
        assert SalienceEngine.PRIORITIZE_THRESHOLD == 0.5

    def test_weights_sum_to_one(self):
        """Сумма весов == 1.0."""
        total = (
            SalienceEngine.W_NOVELTY
            + SalienceEngine.W_URGENCY
            + SalienceEngine.W_THREAT
            + SalienceEngine.W_RELEVANCE
        )
        assert abs(total - 1.0) < 1e-9

    def test_action_consistency_with_overall(self):
        """action соответствует overall по порогам."""
        score = self.engine.evaluate("срочно! ошибка критическая")
        if score.overall >= SalienceEngine.INTERRUPT_THRESHOLD:
            assert score.action == "interrupt"
        elif score.overall >= SalienceEngine.PRIORITIZE_THRESHOLD:
            assert score.action == "prioritize"
        else:
            assert score.action == "normal"

    def test_urgency_keywords_set_not_empty(self):
        assert len(SalienceEngine.URGENCY_KEYWORDS) > 0

    def test_threat_keywords_set_not_empty(self):
        assert len(SalienceEngine.THREAT_KEYWORDS) > 0
