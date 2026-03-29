"""
tests/test_attention_controller.py

Тесты для Этапа H: AttentionController (brain/core/attention_controller.py).

Покрывает:
  - AttentionBudget — ContractMixin round-trip, defaults
  - PRESET_BUDGETS — все 6 пресетов существуют и корректны
  - AttentionController._select_preset() — выбор пресета по ресурсам
  - AttentionController._apply_salience_boost() — boost к cognition
  - AttentionController.compute_budget() — полный цикл
  - Корректировка по типу цели (memory_intensive)
  - cycle_id и created_at проставляются
"""

from __future__ import annotations

from unittest.mock import MagicMock

from brain.core.attention_controller import (
    PRESET_BUDGETS,
    AttentionBudget,
    AttentionController,
)

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _make_resource_state(
    cpu_pct: float = 10.0,
    ram_used_mb: float = 4096.0,
    ring2_allowed: bool = True,
    soft_blocked: bool = False,
) -> MagicMock:
    """Создать mock ResourceState для тестов."""
    state = MagicMock()
    state.cpu_pct = cpu_pct
    state.ram_used_mb = ram_used_mb
    state.ring2_allowed = ring2_allowed
    state.soft_blocked = soft_blocked
    return state


def _make_salience(overall: float = 0.0) -> MagicMock:
    """Создать mock SalienceScore."""
    salience = MagicMock()
    salience.overall = overall
    return salience


# ---------------------------------------------------------------------------
# 1. AttentionBudget — ContractMixin round-trip
# ---------------------------------------------------------------------------


class TestAttentionBudget:
    """Тесты AttentionBudget — ContractMixin round-trip и defaults."""

    def test_defaults(self):
        budget = AttentionBudget()
        assert budget.text == 0.50
        assert budget.vision == 0.05
        assert budget.audio == 0.00
        assert budget.memory == 0.25
        assert budget.cognition == 0.12
        assert budget.learning == 0.05
        assert budget.logging == 0.03
        assert budget.policy == "normal"
        assert budget.reason == ""
        assert budget.cycle_id == ""
        assert budget.created_at == ""

    def test_to_dict(self):
        budget = AttentionBudget(
            text=0.60,
            vision=0.10,
            memory=0.20,
            cognition=0.08,
            policy="degraded",
            reason="тест",
            cycle_id="cycle_1",
        )
        d = budget.to_dict()
        assert d["text"] == 0.60
        assert d["policy"] == "degraded"
        assert d["cycle_id"] == "cycle_1"
        assert d["reason"] == "тест"

    def test_from_dict_roundtrip(self):
        budget = AttentionBudget(
            text=0.75,
            vision=0.00,
            audio=0.00,
            memory=0.15,
            cognition=0.07,
            learning=0.00,
            logging=0.03,
            policy="critical",
            reason="CPU > 85%",
            cycle_id="cycle_42",
        )
        d = budget.to_dict()
        budget2 = AttentionBudget.from_dict(d)
        assert budget2.text == budget.text
        assert budget2.policy == budget.policy
        assert budget2.cycle_id == budget.cycle_id
        assert budget2.reason == budget.reason

    def test_all_fields_in_dict(self):
        budget = AttentionBudget()
        d = budget.to_dict()
        for key in ("text", "vision", "audio", "memory", "cognition", "learning", "logging", "policy"):
            assert key in d


# ---------------------------------------------------------------------------
# 2. PRESET_BUDGETS — все 6 пресетов
# ---------------------------------------------------------------------------


class TestPresetBudgets:
    """Тесты PRESET_BUDGETS — все 6 пресетов существуют и корректны."""

    def test_all_presets_exist(self):
        expected = {"text_focused", "multimodal", "memory_intensive", "degraded", "critical", "emergency"}
        assert set(PRESET_BUDGETS.keys()) == expected

    def test_text_focused_preset_values(self):
        b = PRESET_BUDGETS["text_focused"]
        assert b.text == 0.50
        assert b.memory == 0.25
        assert b.policy == "normal"

    def test_degraded_preset_values(self):
        b = PRESET_BUDGETS["degraded"]
        assert b.policy == "degraded"
        assert b.vision == 0.00
        assert b.learning == 0.00

    def test_critical_preset_values(self):
        b = PRESET_BUDGETS["critical"]
        assert b.policy == "critical"
        assert b.text >= 0.70
        assert b.vision == 0.00

    def test_emergency_preset_values(self):
        b = PRESET_BUDGETS["emergency"]
        assert b.policy == "emergency"
        assert b.text >= 0.75
        assert b.vision == 0.00
        assert b.learning == 0.00

    def test_memory_intensive_preset_values(self):
        b = PRESET_BUDGETS["memory_intensive"]
        assert b.memory >= 0.40
        assert b.policy == "normal"

    def test_multimodal_preset_values(self):
        b = PRESET_BUDGETS["multimodal"]
        assert b.vision > 0.0
        assert b.audio > 0.0

    def test_presets_are_attention_budget_instances(self):
        for key, budget in PRESET_BUDGETS.items():
            assert isinstance(budget, AttentionBudget), f"Пресет '{key}' не является AttentionBudget"

    def test_degraded_text_higher_than_text_focused(self):
        """В degraded режиме больше ресурсов на текст (меньше на остальное)."""
        assert PRESET_BUDGETS["degraded"].text > PRESET_BUDGETS["text_focused"].text

    def test_emergency_text_highest(self):
        """В emergency режиме максимальная доля на текст."""
        texts = [b.text for b in PRESET_BUDGETS.values()]
        assert PRESET_BUDGETS["emergency"].text == max(texts)


# ---------------------------------------------------------------------------
# 3. AttentionController._select_preset()
# ---------------------------------------------------------------------------


class TestSelectPreset:
    """Тесты _select_preset() — выбор пресета по состоянию ресурсов."""

    def setup_method(self):
        self.controller = AttentionController()

    def test_no_resource_state_returns_text_focused(self):
        assert self.controller._select_preset(None) == "text_focused"

    def test_normal_cpu_and_ram_returns_text_focused(self):
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=4096.0)
        assert self.controller._select_preset(state) == "text_focused"

    def test_cpu_above_degraded_threshold(self):
        # CPU_DEGRADED_PCT = 70.0
        state = _make_resource_state(cpu_pct=75.0, ram_used_mb=4096.0)
        assert self.controller._select_preset(state) == "degraded"

    def test_cpu_exactly_at_degraded_threshold(self):
        state = _make_resource_state(cpu_pct=70.0, ram_used_mb=4096.0)
        assert self.controller._select_preset(state) == "degraded"

    def test_cpu_above_critical_threshold(self):
        # CPU_CRITICAL_PCT = 85.0
        state = _make_resource_state(cpu_pct=90.0, ram_used_mb=4096.0)
        assert self.controller._select_preset(state) == "critical"

    def test_cpu_exactly_at_critical_threshold(self):
        state = _make_resource_state(cpu_pct=85.0, ram_used_mb=4096.0)
        assert self.controller._select_preset(state) == "critical"

    def test_ram_above_degraded_threshold(self):
        # RAM_DEGRADED_GB = 22.0 → 22528 MB
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=23000.0)
        assert self.controller._select_preset(state) == "degraded"

    def test_ram_above_critical_threshold(self):
        # RAM_CRITICAL_GB = 28.0 → 28672 MB
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=29000.0)
        assert self.controller._select_preset(state) == "critical"

    def test_ram_above_emergency_threshold(self):
        # RAM_EMERGENCY_GB = 30.0 → 30720 MB
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=31000.0)
        assert self.controller._select_preset(state) == "emergency"

    def test_emergency_takes_priority_over_critical_cpu(self):
        """RAM emergency > CPU critical."""
        state = _make_resource_state(cpu_pct=90.0, ram_used_mb=31000.0)
        assert self.controller._select_preset(state) == "emergency"

    def test_cpu_below_degraded_threshold_normal(self):
        state = _make_resource_state(cpu_pct=69.9, ram_used_mb=4096.0)
        assert self.controller._select_preset(state) == "text_focused"

    def test_ram_below_degraded_threshold_normal(self):
        # 21 GB = 21504 MB
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=21504.0)
        assert self.controller._select_preset(state) == "text_focused"


# ---------------------------------------------------------------------------
# 4. AttentionController._apply_salience_boost()
# ---------------------------------------------------------------------------


class TestApplySalienceBoost:
    """Тесты _apply_salience_boost() — boost к cognition."""

    def setup_method(self):
        self.controller = AttentionController()

    def test_no_boost_when_overall_below_threshold(self):
        """overall <= 0.5 → нет boost."""
        import copy
        budget = copy.copy(PRESET_BUDGETS["text_focused"])
        original_cognition = budget.cognition
        salience = _make_salience(overall=0.3)
        result = self.controller._apply_salience_boost(budget, salience)
        assert result.cognition == original_cognition

    def test_no_boost_at_exactly_half(self):
        """overall == 0.5 → нет boost (граничное значение)."""
        import copy
        budget = copy.copy(PRESET_BUDGETS["text_focused"])
        original_cognition = budget.cognition
        salience = _make_salience(overall=0.5)
        result = self.controller._apply_salience_boost(budget, salience)
        assert result.cognition == original_cognition

    def test_boost_applied_when_overall_above_half(self):
        """overall > 0.5 → cognition увеличивается."""
        import copy
        budget = copy.copy(PRESET_BUDGETS["text_focused"])
        original_cognition = budget.cognition
        salience = _make_salience(overall=0.8)
        result = self.controller._apply_salience_boost(budget, salience)
        assert result.cognition > original_cognition

    def test_boost_reduces_learning(self):
        """Boost к cognition уменьшает learning."""
        import copy
        budget = copy.copy(PRESET_BUDGETS["text_focused"])
        original_learning = budget.learning
        salience = _make_salience(overall=0.8)
        result = self.controller._apply_salience_boost(budget, salience)
        assert result.learning < original_learning

    def test_cognition_capped_at_030(self):
        """cognition не превышает 0.30."""
        import copy
        budget = copy.copy(PRESET_BUDGETS["text_focused"])
        budget.cognition = 0.29
        salience = _make_salience(overall=1.0)
        result = self.controller._apply_salience_boost(budget, salience)
        assert result.cognition <= 0.30

    def test_learning_not_below_zero(self):
        """learning не опускается ниже 0.0."""
        import copy
        budget = copy.copy(PRESET_BUDGETS["text_focused"])
        budget.learning = 0.0
        salience = _make_salience(overall=1.0)
        result = self.controller._apply_salience_boost(budget, salience)
        assert result.learning >= 0.0

    def test_boost_reason_updated(self):
        """reason обновляется с salience_boost."""
        import copy
        budget = copy.copy(PRESET_BUDGETS["text_focused"])
        salience = _make_salience(overall=0.8)
        result = self.controller._apply_salience_boost(budget, salience)
        assert "salience_boost" in result.reason

    def test_original_budget_not_mutated(self):
        """Оригинальный бюджет не мутируется."""
        import copy
        budget = copy.copy(PRESET_BUDGETS["text_focused"])
        original_cognition = budget.cognition
        salience = _make_salience(overall=0.9)
        self.controller._apply_salience_boost(budget, salience)
        assert budget.cognition == original_cognition

    def test_boost_max_is_005(self):
        """Максимальный boost = 0.05."""
        import copy
        budget = copy.copy(PRESET_BUDGETS["text_focused"])
        original_cognition = budget.cognition
        salience = _make_salience(overall=1.0)
        result = self.controller._apply_salience_boost(budget, salience)
        assert result.cognition - original_cognition <= 0.05 + 1e-9

    def test_no_overall_attribute_no_boost(self):
        """Объект без overall → нет boost."""
        import copy
        budget = copy.copy(PRESET_BUDGETS["text_focused"])
        original_cognition = budget.cognition
        salience = MagicMock(spec=[])  # нет атрибута overall
        result = self.controller._apply_salience_boost(budget, salience)
        assert result.cognition == original_cognition


# ---------------------------------------------------------------------------
# 5. AttentionController.compute_budget() — полный цикл
# ---------------------------------------------------------------------------


class TestComputeBudget:
    """Тесты compute_budget() — полный цикл."""

    def setup_method(self):
        self.controller = AttentionController()

    def test_returns_attention_budget(self):
        budget = self.controller.compute_budget(goal_type="answer_question")
        assert isinstance(budget, AttentionBudget)

    def test_cycle_id_set(self):
        budget = self.controller.compute_budget(goal_type="answer_question", cycle_id="cycle_42")
        assert budget.cycle_id == "cycle_42"

    def test_created_at_set(self):
        budget = self.controller.compute_budget(goal_type="answer_question")
        assert budget.created_at != ""

    def test_no_resource_state_uses_text_focused(self):
        budget = self.controller.compute_budget(goal_type="answer_question")
        assert budget.policy == "normal"

    def test_explore_topic_uses_memory_intensive(self):
        """explore_topic при нормальных ресурсах → memory_intensive."""
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=4096.0)
        budget = self.controller.compute_budget(goal_type="explore_topic", resource_state=state)
        assert budget.memory >= PRESET_BUDGETS["memory_intensive"].memory

    def test_verify_claim_uses_memory_intensive(self):
        """verify_claim при нормальных ресурсах → memory_intensive."""
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=4096.0)
        budget = self.controller.compute_budget(goal_type="verify_claim", resource_state=state)
        assert budget.memory >= PRESET_BUDGETS["memory_intensive"].memory

    def test_answer_question_uses_text_focused(self):
        """answer_question при нормальных ресурсах → text_focused."""
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=4096.0)
        budget = self.controller.compute_budget(goal_type="answer_question", resource_state=state)
        assert budget.text == PRESET_BUDGETS["text_focused"].text

    def test_degraded_resources_override_goal_type(self):
        """При деградации ресурсов — degraded пресет, независимо от типа цели."""
        state = _make_resource_state(cpu_pct=80.0, ram_used_mb=4096.0)
        budget = self.controller.compute_budget(goal_type="explore_topic", resource_state=state)
        assert budget.policy == "degraded"

    def test_critical_resources_override_goal_type(self):
        """При критических ресурсах — critical пресет."""
        state = _make_resource_state(cpu_pct=90.0, ram_used_mb=4096.0)
        budget = self.controller.compute_budget(goal_type="explore_topic", resource_state=state)
        assert budget.policy == "critical"

    def test_emergency_resources(self):
        """При аварийных ресурсах — emergency пресет."""
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=31000.0)
        budget = self.controller.compute_budget(goal_type="answer_question", resource_state=state)
        assert budget.policy == "emergency"

    def test_salience_boost_applied(self):
        """Salience boost применяется при overall > 0.5."""
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=4096.0)
        salience = _make_salience(overall=0.9)
        budget_no_salience = self.controller.compute_budget(
            goal_type="answer_question", resource_state=state
        )
        budget_with_salience = self.controller.compute_budget(
            goal_type="answer_question", resource_state=state, salience=salience
        )
        assert budget_with_salience.cognition >= budget_no_salience.cognition

    def test_no_salience_no_boost(self):
        """Без salience — нет boost."""
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=4096.0)
        budget = self.controller.compute_budget(
            goal_type="answer_question", resource_state=state, salience=None
        )
        assert budget.cognition == PRESET_BUDGETS["text_focused"].cognition

    def test_preset_not_mutated(self):
        """Оригинальный пресет не мутируется после compute_budget."""
        original_text = PRESET_BUDGETS["text_focused"].text
        self.controller.compute_budget(goal_type="answer_question")
        assert PRESET_BUDGETS["text_focused"].text == original_text

    def test_memory_intensive_goals_set(self):
        """MEMORY_INTENSIVE_GOALS содержит explore_topic и verify_claim."""
        assert "explore_topic" in AttentionController.MEMORY_INTENSIVE_GOALS
        assert "verify_claim" in AttentionController.MEMORY_INTENSIVE_GOALS

    def test_learn_fact_uses_text_focused(self):
        """learn_fact не является memory_intensive → text_focused."""
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=4096.0)
        budget = self.controller.compute_budget(goal_type="learn_fact", resource_state=state)
        assert budget.text == PRESET_BUDGETS["text_focused"].text

    def test_unknown_goal_type_uses_text_focused(self):
        """Неизвестный тип цели → text_focused."""
        state = _make_resource_state(cpu_pct=10.0, ram_used_mb=4096.0)
        budget = self.controller.compute_budget(goal_type="unknown_goal", resource_state=state)
        assert budget.policy == "normal"
