"""
tests/test_policy_layer.py

Тесты для Этапа H: PolicyLayer (brain/cognition/policy_layer.py).

Покрывает:
  - PolicyLayer.apply_filters() — F0, F1, F2 фильтры
  - PolicyLayer.apply_modifiers() — M1, M2, M3 модификаторы
  - Граничные случаи: пустые кандидаты, нет модификаций
  - Константы: SOFT_BLOCK_PENALTY, CONTRADICTION_BOOST, HEDGED_BOOST
"""

from __future__ import annotations

from unittest.mock import MagicMock

from brain.cognition.action_selector import ActionType
from brain.cognition.context import CognitiveOutcome, PolicyConstraints, ReasoningState
from brain.cognition.policy_layer import PolicyLayer

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _make_resources(
    ring2_allowed: bool = True,
    soft_blocked: bool = False,
    cpu_pct: float = 10.0,
) -> MagicMock:
    """Создать mock ResourceState."""
    state = MagicMock()
    state.ring2_allowed = ring2_allowed
    state.soft_blocked = soft_blocked
    state.cpu_pct = cpu_pct
    return state


def _make_reasoning_state(
    best_score: float = 0.8,
    contradiction_flags: list | None = None,
) -> ReasoningState:
    """Создать ReasoningState для тестов."""
    state = MagicMock(spec=ReasoningState)
    state.best_score = best_score
    state.contradiction_flags = contradiction_flags or []
    return state


def _make_constraints(min_confidence: float = 0.5) -> PolicyConstraints:
    """Создать PolicyConstraints для тестов."""
    constraints = MagicMock(spec=PolicyConstraints)
    constraints.min_confidence = min_confidence
    return constraints


def _all_action_types() -> list[ActionType]:
    """Вернуть все ActionType как список кандидатов."""
    return list(ActionType)


# ---------------------------------------------------------------------------
# 1. PolicyLayer.apply_filters() — F0: жёсткий ресурсный блок
# ---------------------------------------------------------------------------


class TestApplyFiltersF0:
    """Тесты фильтра F0: жёсткий блок LEARN при resource_blocked."""

    def setup_method(self):
        self.layer = PolicyLayer()
        self.state = _make_reasoning_state(best_score=0.8)
        self.constraints = _make_constraints(min_confidence=0.5)

    def test_f0_blocks_learn_when_ring2_not_allowed(self):
        """F0: LEARN блокируется при ring2_allowed=False."""
        resources = _make_resources(ring2_allowed=False)
        candidates = [ActionType.LEARN, ActionType.RESPOND_DIRECT]
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.LEARN not in result

    def test_f0_blocks_learn_when_outcome_resource_blocked(self):
        """F0: LEARN блокируется при outcome == RESOURCE_BLOCKED."""
        resources = _make_resources(ring2_allowed=True)
        candidates = [ActionType.LEARN, ActionType.RESPOND_DIRECT]
        result = self.layer.apply_filters(
            candidates, self.state, resources, self.constraints,
            outcome=CognitiveOutcome.RESOURCE_BLOCKED,
        )
        assert ActionType.LEARN not in result

    def test_f0_allows_other_actions_when_resource_blocked(self):
        """F0: другие действия не блокируются при resource_blocked."""
        resources = _make_resources(ring2_allowed=False)
        candidates = [ActionType.RESPOND_DIRECT, ActionType.ASK_CLARIFICATION, ActionType.REFUSE]
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.RESPOND_DIRECT in result
        assert ActionType.ASK_CLARIFICATION in result
        assert ActionType.REFUSE in result

    def test_f0_no_block_when_ring2_allowed(self):
        """F0: нет блока при ring2_allowed=True и нет RESOURCE_BLOCKED."""
        resources = _make_resources(ring2_allowed=True)
        candidates = [ActionType.LEARN, ActionType.RESPOND_DIRECT]
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.LEARN in result

    def test_f0_blocked_action_removed_from_all_candidates(self):
        """F0: LEARN удаляется из полного списка кандидатов."""
        resources = _make_resources(ring2_allowed=False)
        candidates = _all_action_types()
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.LEARN not in result
        # Остальные (кроме F1-filtered) должны остаться
        assert ActionType.RESPOND_HEDGED in result
        assert ActionType.ASK_CLARIFICATION in result
        assert ActionType.REFUSE in result

    def test_f0_respond_hedged_not_blocked(self):
        """F0: RESPOND_HEDGED не блокируется при resource_blocked."""
        resources = _make_resources(ring2_allowed=False)
        candidates = [ActionType.RESPOND_HEDGED]
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.RESPOND_HEDGED in result


# ---------------------------------------------------------------------------
# 2. PolicyLayer.apply_filters() — F1: низкая уверенность
# ---------------------------------------------------------------------------


class TestApplyFiltersF1:
    """Тесты фильтра F1: RESPOND_DIRECT при низкой уверенности."""

    def setup_method(self):
        self.layer = PolicyLayer()
        self.resources = _make_resources(ring2_allowed=True)

    def test_f1_blocks_respond_direct_when_low_confidence(self):
        """F1: RESPOND_DIRECT блокируется при best_score < min_confidence."""
        state = _make_reasoning_state(best_score=0.3)
        constraints = _make_constraints(min_confidence=0.5)
        candidates = [ActionType.RESPOND_DIRECT, ActionType.RESPOND_HEDGED]
        result = self.layer.apply_filters(candidates, state, self.resources, constraints)
        assert ActionType.RESPOND_DIRECT not in result

    def test_f1_allows_respond_direct_when_high_confidence(self):
        """F1: RESPOND_DIRECT разрешён при best_score >= min_confidence."""
        state = _make_reasoning_state(best_score=0.8)
        constraints = _make_constraints(min_confidence=0.5)
        candidates = [ActionType.RESPOND_DIRECT, ActionType.RESPOND_HEDGED]
        result = self.layer.apply_filters(candidates, state, self.resources, constraints)
        assert ActionType.RESPOND_DIRECT in result

    def test_f1_allows_respond_direct_at_exact_threshold(self):
        """F1: RESPOND_DIRECT разрешён при best_score == min_confidence."""
        state = _make_reasoning_state(best_score=0.5)
        constraints = _make_constraints(min_confidence=0.5)
        candidates = [ActionType.RESPOND_DIRECT]
        result = self.layer.apply_filters(candidates, state, self.resources, constraints)
        assert ActionType.RESPOND_DIRECT in result

    def test_f1_does_not_block_other_actions(self):
        """F1: другие действия не блокируются при низкой уверенности."""
        state = _make_reasoning_state(best_score=0.1)
        constraints = _make_constraints(min_confidence=0.5)
        candidates = [ActionType.RESPOND_HEDGED, ActionType.ASK_CLARIFICATION, ActionType.REFUSE]
        result = self.layer.apply_filters(candidates, state, self.resources, constraints)
        assert ActionType.RESPOND_HEDGED in result
        assert ActionType.ASK_CLARIFICATION in result
        assert ActionType.REFUSE in result


# ---------------------------------------------------------------------------
# 3. PolicyLayer.apply_filters() — F2: мягкий блок LEARN
# ---------------------------------------------------------------------------


class TestApplyFiltersF2:
    """Тесты фильтра F2: LEARN при soft_blocked."""

    def setup_method(self):
        self.layer = PolicyLayer()
        self.state = _make_reasoning_state(best_score=0.8)
        self.constraints = _make_constraints(min_confidence=0.5)

    def test_f2_blocks_learn_when_soft_blocked(self):
        """F2: LEARN блокируется при soft_blocked=True."""
        resources = _make_resources(ring2_allowed=True, soft_blocked=True)
        candidates = [ActionType.LEARN, ActionType.RESPOND_DIRECT]
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.LEARN not in result

    def test_f2_allows_learn_when_not_soft_blocked(self):
        """F2: LEARN разрешён при soft_blocked=False."""
        resources = _make_resources(ring2_allowed=True, soft_blocked=False)
        candidates = [ActionType.LEARN, ActionType.RESPOND_DIRECT]
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.LEARN in result

    def test_f2_does_not_block_respond_hedged(self):
        """F2: RESPOND_HEDGED не блокируется при soft_blocked."""
        resources = _make_resources(ring2_allowed=True, soft_blocked=True)
        candidates = [ActionType.RESPOND_HEDGED, ActionType.RESPOND_DIRECT]
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.RESPOND_HEDGED in result

    def test_f2_does_not_block_ask_clarification(self):
        """F2: ASK_CLARIFICATION не блокируется при soft_blocked."""
        resources = _make_resources(ring2_allowed=True, soft_blocked=True)
        candidates = [ActionType.ASK_CLARIFICATION]
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.ASK_CLARIFICATION in result


# ---------------------------------------------------------------------------
# 4. PolicyLayer.apply_filters() — граничные случаи
# ---------------------------------------------------------------------------


class TestApplyFiltersEdgeCases:
    """Граничные случаи apply_filters()."""

    def setup_method(self):
        self.layer = PolicyLayer()
        self.state = _make_reasoning_state(best_score=0.8)
        self.resources = _make_resources()
        self.constraints = _make_constraints()

    def test_empty_candidates_returns_empty(self):
        result = self.layer.apply_filters([], self.state, self.resources, self.constraints)
        assert result == []

    def test_order_preserved(self):
        """Порядок кандидатов сохраняется."""
        candidates = [ActionType.REFUSE, ActionType.RESPOND_HEDGED, ActionType.ASK_CLARIFICATION]
        result = self.layer.apply_filters(candidates, self.state, self.resources, self.constraints)
        assert result == candidates

    def test_no_outcome_no_resource_block(self):
        """Без outcome и с ring2_allowed=True — нет F0 блока."""
        resources = _make_resources(ring2_allowed=True)
        candidates = [ActionType.LEARN]
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.LEARN in result

    def test_all_heavy_candidates_can_be_filtered(self):
        """LEARN + RESPOND_DIRECT могут быть отфильтрованы одновременно."""
        resources = _make_resources(ring2_allowed=False, soft_blocked=True)
        state = _make_reasoning_state(best_score=0.1)
        constraints = _make_constraints(min_confidence=0.9)
        candidates = [ActionType.LEARN, ActionType.RESPOND_DIRECT]
        result = self.layer.apply_filters(candidates, state, resources, constraints)
        # LEARN → F0, RESPOND_DIRECT → F1
        assert ActionType.LEARN not in result
        assert ActionType.RESPOND_DIRECT not in result

    def test_f0_and_f2_both_block_learn(self):
        """F0 и F2 оба блокируют LEARN (F0 срабатывает первым)."""
        resources = _make_resources(ring2_allowed=False, soft_blocked=True)
        candidates = [ActionType.LEARN]
        result = self.layer.apply_filters(candidates, self.state, resources, self.constraints)
        assert ActionType.LEARN not in result


# ---------------------------------------------------------------------------
# 5. PolicyLayer.apply_modifiers() — M1: штраф при soft_blocked
# ---------------------------------------------------------------------------


class TestApplyModifiersM1:
    """Тесты модификатора M1: штраф за LEARN при soft_blocked."""

    def setup_method(self):
        self.layer = PolicyLayer()
        self.state = _make_reasoning_state(best_score=0.8)

    def test_m1_penalty_applied_to_learn(self):
        """M1: LEARN получает штраф при soft_blocked."""
        resources = _make_resources(soft_blocked=True)
        scores = {ActionType.LEARN: 0.7, ActionType.RESPOND_DIRECT: 0.8}
        result = self.layer.apply_modifiers(scores, self.state, resources)
        expected = 0.7 - PolicyLayer.SOFT_BLOCK_PENALTY
        assert abs(result[ActionType.LEARN] - expected) < 1e-9

    def test_m1_score_not_below_zero(self):
        """M1: score не опускается ниже 0.0."""
        resources = _make_resources(soft_blocked=True)
        scores = {ActionType.LEARN: 0.05}
        result = self.layer.apply_modifiers(scores, self.state, resources)
        assert result[ActionType.LEARN] >= 0.0

    def test_m1_no_penalty_when_not_soft_blocked(self):
        """M1: нет штрафа при soft_blocked=False."""
        resources = _make_resources(soft_blocked=False)
        scores = {ActionType.LEARN: 0.7}
        result = self.layer.apply_modifiers(scores, self.state, resources)
        assert result[ActionType.LEARN] == 0.7

    def test_m1_does_not_affect_other_actions(self):
        """M1: другие действия не получают штраф."""
        resources = _make_resources(soft_blocked=True)
        scores = {ActionType.RESPOND_DIRECT: 0.8, ActionType.REFUSE: 0.5}
        result = self.layer.apply_modifiers(scores, self.state, resources)
        assert result[ActionType.RESPOND_DIRECT] == 0.8
        assert result[ActionType.REFUSE] == 0.5

    def test_m1_penalty_value_is_soft_block_penalty(self):
        """M1: штраф равен SOFT_BLOCK_PENALTY."""
        resources = _make_resources(soft_blocked=True)
        scores = {ActionType.LEARN: 1.0}
        result = self.layer.apply_modifiers(scores, self.state, resources)
        assert abs(result[ActionType.LEARN] - (1.0 - PolicyLayer.SOFT_BLOCK_PENALTY)) < 1e-9


# ---------------------------------------------------------------------------
# 6. PolicyLayer.apply_modifiers() — M2: буст ASK_CLARIFICATION
# ---------------------------------------------------------------------------


class TestApplyModifiersM2:
    """Тесты модификатора M2: буст ASK_CLARIFICATION при противоречиях."""

    def setup_method(self):
        self.layer = PolicyLayer()
        self.resources = _make_resources(soft_blocked=False)

    def test_m2_boost_applied_when_contradictions(self):
        """M2: ASK_CLARIFICATION получает буст при contradiction_flags."""
        state = _make_reasoning_state(best_score=0.8, contradiction_flags=["c1", "c2"])
        scores = {ActionType.ASK_CLARIFICATION: 0.5}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        expected = 0.5 + PolicyLayer.CONTRADICTION_BOOST
        assert abs(result[ActionType.ASK_CLARIFICATION] - expected) < 1e-9

    def test_m2_no_boost_without_contradictions(self):
        """M2: нет буста без contradiction_flags."""
        state = _make_reasoning_state(best_score=0.8, contradiction_flags=[])
        scores = {ActionType.ASK_CLARIFICATION: 0.5}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        assert result[ActionType.ASK_CLARIFICATION] == 0.5

    def test_m2_score_capped_at_one(self):
        """M2: score не превышает 1.0."""
        state = _make_reasoning_state(best_score=0.8, contradiction_flags=["c1"])
        scores = {ActionType.ASK_CLARIFICATION: 0.95}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        assert result[ActionType.ASK_CLARIFICATION] <= 1.0

    def test_m2_does_not_affect_other_actions(self):
        """M2: другие действия не получают буст."""
        state = _make_reasoning_state(best_score=0.8, contradiction_flags=["c1"])
        scores = {ActionType.RESPOND_DIRECT: 0.7, ActionType.ASK_CLARIFICATION: 0.5}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        assert result[ActionType.RESPOND_DIRECT] == 0.7

    def test_m2_no_boost_if_action_not_in_scores(self):
        """M2: нет буста если ASK_CLARIFICATION не в scores."""
        state = _make_reasoning_state(best_score=0.8, contradiction_flags=["c1"])
        scores = {ActionType.RESPOND_DIRECT: 0.7}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        assert ActionType.ASK_CLARIFICATION not in result


# ---------------------------------------------------------------------------
# 7. PolicyLayer.apply_modifiers() — M3: буст RESPOND_HEDGED
# ---------------------------------------------------------------------------


class TestApplyModifiersM3:
    """Тесты модификатора M3: буст RESPOND_HEDGED при умеренной уверенности."""

    def setup_method(self):
        self.layer = PolicyLayer()
        self.resources = _make_resources(soft_blocked=False)

    def test_m3_boost_applied_at_low_confidence_boundary(self):
        """M3: буст при best_score == 0.5 (нижняя граница)."""
        state = _make_reasoning_state(best_score=0.5)
        scores = {ActionType.RESPOND_HEDGED: 0.4}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        expected = 0.4 + PolicyLayer.HEDGED_BOOST
        assert abs(result[ActionType.RESPOND_HEDGED] - expected) < 1e-9

    def test_m3_boost_applied_at_high_confidence_boundary(self):
        """M3: буст при best_score == 0.7 (верхняя граница)."""
        state = _make_reasoning_state(best_score=0.7)
        scores = {ActionType.RESPOND_HEDGED: 0.4}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        expected = 0.4 + PolicyLayer.HEDGED_BOOST
        assert abs(result[ActionType.RESPOND_HEDGED] - expected) < 1e-9

    def test_m3_boost_applied_in_range(self):
        """M3: буст при best_score в диапазоне [0.5, 0.7]."""
        state = _make_reasoning_state(best_score=0.6)
        scores = {ActionType.RESPOND_HEDGED: 0.4}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        assert result[ActionType.RESPOND_HEDGED] > 0.4

    def test_m3_no_boost_below_range(self):
        """M3: нет буста при best_score < 0.5."""
        state = _make_reasoning_state(best_score=0.3)
        scores = {ActionType.RESPOND_HEDGED: 0.4}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        assert result[ActionType.RESPOND_HEDGED] == 0.4

    def test_m3_no_boost_above_range(self):
        """M3: нет буста при best_score > 0.7."""
        state = _make_reasoning_state(best_score=0.9)
        scores = {ActionType.RESPOND_HEDGED: 0.4}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        assert result[ActionType.RESPOND_HEDGED] == 0.4

    def test_m3_score_capped_at_one(self):
        """M3: score не превышает 1.0."""
        state = _make_reasoning_state(best_score=0.6)
        scores = {ActionType.RESPOND_HEDGED: 0.95}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        assert result[ActionType.RESPOND_HEDGED] <= 1.0

    def test_m3_does_not_affect_other_actions(self):
        """M3: другие действия не получают буст."""
        state = _make_reasoning_state(best_score=0.6)
        scores = {ActionType.RESPOND_DIRECT: 0.7, ActionType.RESPOND_HEDGED: 0.4}
        result = self.layer.apply_modifiers(scores, state, self.resources)
        assert result[ActionType.RESPOND_DIRECT] == 0.7


# ---------------------------------------------------------------------------
# 8. PolicyLayer.apply_modifiers() — граничные случаи
# ---------------------------------------------------------------------------


class TestApplyModifiersEdgeCases:
    """Граничные случаи apply_modifiers()."""

    def setup_method(self):
        self.layer = PolicyLayer()
        self.state = _make_reasoning_state(best_score=0.8)
        self.resources = _make_resources(soft_blocked=False)

    def test_empty_scores_returns_empty(self):
        result = self.layer.apply_modifiers({}, self.state, self.resources)
        assert result == {}

    def test_original_scores_not_mutated(self):
        """Оригинальный словарь scores не мутируется."""
        resources = _make_resources(soft_blocked=True)
        scores = {ActionType.LEARN: 0.7}
        original_score = scores[ActionType.LEARN]
        self.layer.apply_modifiers(scores, self.state, resources)
        assert scores[ActionType.LEARN] == original_score

    def test_multiple_modifiers_applied_together(self):
        """Несколько модификаторов применяются одновременно."""
        resources = _make_resources(soft_blocked=True)
        state = _make_reasoning_state(best_score=0.6, contradiction_flags=["c1"])
        scores = {
            ActionType.LEARN: 0.7,
            ActionType.ASK_CLARIFICATION: 0.5,
            ActionType.RESPOND_HEDGED: 0.4,
        }
        result = self.layer.apply_modifiers(scores, state, resources)
        # M1: LEARN штраф
        assert result[ActionType.LEARN] < 0.7
        # M2: ASK_CLARIFICATION буст
        assert result[ActionType.ASK_CLARIFICATION] > 0.5
        # M3: RESPOND_HEDGED буст
        assert result[ActionType.RESPOND_HEDGED] > 0.4

    def test_returns_new_dict(self):
        """apply_modifiers возвращает новый словарь."""
        scores = {ActionType.RESPOND_DIRECT: 0.8}
        result = self.layer.apply_modifiers(scores, self.state, self.resources)
        assert result is not scores


# ---------------------------------------------------------------------------
# 9. Константы PolicyLayer
# ---------------------------------------------------------------------------


class TestPolicyLayerConstants:
    """Тесты констант PolicyLayer."""

    def test_resource_blocked_actions_contains_learn(self):
        """RESOURCE_BLOCKED_ACTIONS содержит LEARN."""
        assert ActionType.LEARN in PolicyLayer.RESOURCE_BLOCKED_ACTIONS

    def test_resource_blocked_actions_is_frozenset(self):
        """RESOURCE_BLOCKED_ACTIONS — frozenset."""
        assert isinstance(PolicyLayer.RESOURCE_BLOCKED_ACTIONS, frozenset)

    def test_soft_block_penalty_positive(self):
        assert PolicyLayer.SOFT_BLOCK_PENALTY > 0.0

    def test_contradiction_boost_positive(self):
        assert PolicyLayer.CONTRADICTION_BOOST > 0.0

    def test_hedged_boost_positive(self):
        assert PolicyLayer.HEDGED_BOOST > 0.0

    def test_hedged_confidence_range_valid(self):
        assert PolicyLayer.HEDGED_CONFIDENCE_LOW < PolicyLayer.HEDGED_CONFIDENCE_HIGH

    def test_soft_block_penalty_value(self):
        assert PolicyLayer.SOFT_BLOCK_PENALTY == 0.15

    def test_contradiction_boost_value(self):
        assert PolicyLayer.CONTRADICTION_BOOST == 0.20

    def test_hedged_boost_value(self):
        assert PolicyLayer.HEDGED_BOOST == 0.15
