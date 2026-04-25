"""Tests for brain/safety/conflict_detector.py"""
from __future__ import annotations

from brain.memory.semantic_memory import SemanticNode
from brain.safety.conflict_detector import Conflict, ConflictDetector


def make_node(
    concept: str,
    description: str,
    confidence: float = 1.0,
    source_refs: list[str] | None = None,
) -> SemanticNode:
    node = SemanticNode(concept=concept, description=description, confidence=confidence)
    if source_refs:
        node.source_refs = source_refs
    return node


class TestConflict:
    def test_conflict_fields(self):
        c = Conflict(
            conflict_id="c1",
            fact_a_id="neuron",
            fact_b_id="neuron",
            fact_a_content="нейрон — клетка",
            fact_b_content="нейрон — не клетка",
            severity="high",
            conflict_type="negation",
            description="negation detected",
            detected_at="2026-04-01T00:00:00Z",
        )
        assert c.severity == "high"
        assert c.conflict_type == "negation"
        assert c.conflict_id == "c1"


class TestConflictDetectorEmpty:
    def test_detect_empty_list(self):
        cd = ConflictDetector()
        assert cd.detect([]) == []

    def test_detect_single_fact(self):
        cd = ConflictDetector()
        assert cd.detect([make_node("neuron", "нейрон — клетка")]) == []

    def test_detect_different_concepts_no_conflict(self):
        cd = ConflictDetector()
        facts = [
            make_node("neuron", "нейрон — клетка"),
            make_node("synapse", "синапс — соединение"),
        ]
        assert cd.detect(facts) == []


class TestConflictDetectorNegation:
    def test_detect_negation_ru_high_severity(self):
        cd = ConflictDetector()
        facts = [
            make_node("neuron", "нейрон — клетка нервной системы"),
            make_node("neuron", "нейрон — не клетка"),
        ]
        conflicts = cd.detect(facts)
        assert len(conflicts) >= 1
        assert conflicts[0].severity == "high"
        assert conflicts[0].conflict_type == "negation"

    def test_detect_negation_en(self):
        cd = ConflictDetector()
        facts = [
            make_node("neuron", "neuron is a cell"),
            make_node("neuron", "neuron is not a cell"),
        ]
        conflicts = cd.detect(facts)
        assert any(c.conflict_type == "negation" for c in conflicts)

    def test_detect_pair_negation_ru(self):
        cd = ConflictDetector()
        a = make_node("neuron", "нейрон — клетка")
        b = make_node("neuron", "нейрон — не клетка")
        conflict = cd.detect_pair(a, b)
        assert conflict is not None
        assert conflict.conflict_type == "negation"
        assert conflict.severity == "high"

    def test_detect_pair_negation_en(self):
        cd = ConflictDetector()
        a = make_node("speed", "speed is constant")
        b = make_node("speed", "speed is not constant")
        conflict = cd.detect_pair(a, b)
        assert conflict is not None
        assert conflict.conflict_type == "negation"

    def test_detect_pair_no_conflict_same_description(self):
        cd = ConflictDetector()
        a = make_node("neuron", "нейрон — клетка")
        b = make_node("neuron", "нейрон — клетка")
        assert cd.detect_pair(a, b) is None

    def test_detect_pair_different_concepts_no_conflict(self):
        cd = ConflictDetector()
        a = make_node("neuron", "нейрон — клетка")
        b = make_node("synapse", "синапс — не клетка")
        assert cd.detect_pair(a, b) is None


class TestConflictDetectorNumeric:
    def test_detect_numeric_conflict_medium_severity(self):
        cd = ConflictDetector()
        facts = [
            make_node("speed", "скорость света 300000 км/с"),
            make_node("speed", "скорость света 100000 км/с"),
        ]
        conflicts = cd.detect(facts)
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == "numeric"
        assert conflicts[0].severity == "medium"

    def test_no_numeric_conflict_same_number(self):
        cd = ConflictDetector()
        facts = [
            make_node("speed", "скорость 300000 км/с"),
            make_node("speed", "скорость 300000 км/с"),
        ]
        conflicts = cd.detect(facts)
        assert not any(c.conflict_type == "numeric" for c in conflicts)

    def test_no_numeric_conflict_no_numbers(self):
        cd = ConflictDetector()
        facts = [
            make_node("neuron", "нейрон — клетка"),
            make_node("neuron", "нейрон — нервная клетка"),
        ]
        conflicts = cd.detect(facts)
        assert not any(c.conflict_type == "numeric" for c in conflicts)

    def test_detect_pair_numeric(self):
        cd = ConflictDetector()
        a = make_node("temp", "температура 100 градусов")
        b = make_node("temp", "температура 200 градусов")
        conflict = cd.detect_pair(a, b)
        assert conflict is not None
        assert conflict.conflict_type == "numeric"


class TestConflictDetectorSourceTrust:
    def test_detect_source_trust_low_severity(self):
        cd = ConflictDetector(trust_gap_threshold=0.40)
        facts = [
            make_node("neuron", "нейрон — клетка", confidence=0.9),
            make_node("neuron", "нейрон — клетка", confidence=0.3),
        ]
        conflicts = cd.detect(facts)
        assert any(c.conflict_type == "source_trust" for c in conflicts)
        trust_conflicts = [c for c in conflicts if c.conflict_type == "source_trust"]
        assert trust_conflicts[0].severity == "low"

    def test_no_source_trust_conflict_small_gap(self):
        cd = ConflictDetector(trust_gap_threshold=0.40)
        facts = [
            make_node("neuron", "нейрон — клетка", confidence=0.8),
            make_node("neuron", "нейрон — клетка", confidence=0.7),
        ]
        conflicts = cd.detect(facts)
        assert not any(c.conflict_type == "source_trust" for c in conflicts)


class TestConflictDetectorPriority:
    def test_negation_takes_priority_over_numeric(self):
        cd = ConflictDetector()
        # Has both negation AND different numbers
        a = make_node("x", "значение 100")
        b = make_node("x", "значение не 300")
        conflict = cd.detect_pair(a, b)
        assert conflict is not None
        assert conflict.conflict_type == "negation"

    def test_conflict_id_is_unique(self):
        cd = ConflictDetector()
        facts = [
            make_node("neuron", "нейрон — клетка"),
            make_node("neuron", "нейрон — не клетка"),
        ]
        conflicts = cd.detect(facts)
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_id != ""

    def test_conflict_contains_fact_content(self):
        cd = ConflictDetector()
        a = make_node("neuron", "нейрон — клетка")
        b = make_node("neuron", "нейрон — не клетка")
        conflict = cd.detect_pair(a, b)
        assert conflict is not None
        assert "клетка" in conflict.fact_a_content or "клетка" in conflict.fact_b_content
