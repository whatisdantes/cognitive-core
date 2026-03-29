"""
tests/test_knowledge_gap_detector.py

Тесты для Этапа I: KnowledgeGapDetector (brain/learning/knowledge_gap_detector.py).

Покрывает:
  - KnowledgeGap — ContractMixin round-trip, defaults
  - GapSeverity / GapType — enum значения
  - KnowledgeGapDetector.analyze() — MISSING, WEAK, OUTDATED, None
  - KnowledgeGapDetector._register_gap() — дедупликация по concept+gap_type
  - KnowledgeGapDetector.get_gaps() — фильтрация по severity и resolved
  - KnowledgeGapDetector.resolve_gap() / resolve_by_concept()
  - KnowledgeGapDetector._evict_resolved() — очистка при max_gaps
  - KnowledgeGapDetector.status() / __repr__()
"""

from __future__ import annotations

from unittest.mock import MagicMock

from brain.learning.knowledge_gap_detector import (
    GapSeverity,
    GapType,
    KnowledgeGap,
    KnowledgeGapDetector,
)

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _make_memory() -> MagicMock:
    """Создать mock MemoryManager."""
    memory = MagicMock()
    memory.semantic = MagicMock()
    return memory


def _make_search_result(
    total: int = 0,
    best_confidence: float = 0.8,
    best_age_days: float = 5.0,
) -> MagicMock:
    """Создать mock MemorySearchResult."""
    result = MagicMock()
    result.total = total

    if total > 0:
        best = MagicMock()
        best.confidence = best_confidence
        best.age_days = MagicMock(return_value=best_age_days)
        result.best_semantic = MagicMock(return_value=best)
    else:
        result.best_semantic = MagicMock(return_value=None)

    return result


def _make_detector(
    weak_threshold: float = 0.5,
    outdated_days: float = 30.0,
    max_gaps: int = 1000,
) -> tuple[KnowledgeGapDetector, MagicMock]:
    """Создать KnowledgeGapDetector с mock memory."""
    memory = _make_memory()
    detector = KnowledgeGapDetector(
        memory=memory,
        weak_threshold=weak_threshold,
        outdated_days=outdated_days,
        max_gaps=max_gaps,
    )
    return detector, memory


# ---------------------------------------------------------------------------
# 1. GapSeverity / GapType — enum значения
# ---------------------------------------------------------------------------


class TestEnums:
    """Тесты GapSeverity и GapType enum."""

    def test_gap_severity_values(self):
        assert GapSeverity.HIGH == "high"
        assert GapSeverity.MEDIUM == "medium"
        assert GapSeverity.LOW == "low"

    def test_gap_type_values(self):
        assert GapType.MISSING == "missing"
        assert GapType.WEAK == "weak"
        assert GapType.OUTDATED == "outdated"
        assert GapType.MODAL == "modal"

    def test_gap_severity_is_str(self):
        assert isinstance(GapSeverity.HIGH, str)

    def test_gap_type_is_str(self):
        assert isinstance(GapType.MISSING, str)


# ---------------------------------------------------------------------------
# 2. KnowledgeGap — ContractMixin round-trip
# ---------------------------------------------------------------------------


class TestKnowledgeGap:
    """Тесты KnowledgeGap — ContractMixin round-trip и defaults."""

    def test_required_fields(self):
        gap = KnowledgeGap(
            gap_id="gap_001",
            concept="нейрон",
            severity=GapSeverity.HIGH,
            gap_type=GapType.MISSING,
            detected_at="2025-01-01T00:00:00",
        )
        assert gap.gap_id == "gap_001"
        assert gap.concept == "нейрон"
        assert gap.severity == GapSeverity.HIGH
        assert gap.gap_type == GapType.MISSING
        assert gap.resolved is False
        assert gap.metadata == {}

    def test_to_dict(self):
        gap = KnowledgeGap(
            gap_id="gap_002",
            concept="синапс",
            severity=GapSeverity.MEDIUM,
            gap_type=GapType.WEAK,
            detected_at="2025-01-01T00:00:00",
            resolved=False,
            metadata={"query": "что такое синапс"},
        )
        d = gap.to_dict()
        assert d["gap_id"] == "gap_002"
        assert d["concept"] == "синапс"
        assert d["severity"] == "medium"
        assert d["gap_type"] == "weak"
        assert d["resolved"] is False
        assert d["metadata"]["query"] == "что такое синапс"

    def test_from_dict_roundtrip(self):
        gap = KnowledgeGap(
            gap_id="gap_003",
            concept="мозг",
            severity=GapSeverity.LOW,
            gap_type=GapType.OUTDATED,
            detected_at="2025-06-01T12:00:00",
            resolved=True,
            metadata={"age_days": 45.0},
        )
        d = gap.to_dict()
        gap2 = KnowledgeGap.from_dict(d)
        assert gap2.gap_id == gap.gap_id
        assert gap2.concept == gap.concept
        assert gap2.severity == gap.severity
        assert gap2.gap_type == gap.gap_type
        assert gap2.resolved == gap.resolved

    def test_all_fields_in_dict(self):
        gap = KnowledgeGap(
            gap_id="gap_004",
            concept="тест",
            severity=GapSeverity.HIGH,
            gap_type=GapType.MISSING,
            detected_at="2025-01-01T00:00:00",
        )
        d = gap.to_dict()
        for key in ("gap_id", "concept", "severity", "gap_type", "detected_at", "resolved", "metadata"):
            assert key in d


# ---------------------------------------------------------------------------
# 3. KnowledgeGapDetector.analyze() — MISSING
# ---------------------------------------------------------------------------


class TestAnalyzeMissing:
    """Тесты analyze() → MISSING gap."""

    def setup_method(self):
        self.detector, self.memory = _make_detector()

    def test_missing_when_total_zero(self):
        """total == 0 → MISSING/HIGH."""
        search_result = _make_search_result(total=0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is not None
        assert gap.gap_type == GapType.MISSING
        assert gap.severity == GapSeverity.HIGH

    def test_missing_concept_set(self):
        search_result = _make_search_result(total=0)
        gap = self.detector.analyze("синапс", search_result)
        assert gap is not None
        assert gap.concept == "синапс"

    def test_missing_gap_id_generated(self):
        search_result = _make_search_result(total=0)
        gap = self.detector.analyze("мозг", search_result)
        assert gap is not None
        assert gap.gap_id != ""

    def test_missing_detected_at_set(self):
        search_result = _make_search_result(total=0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is not None
        assert gap.detected_at != ""

    def test_missing_not_resolved(self):
        search_result = _make_search_result(total=0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is not None
        assert gap.resolved is False

    def test_missing_metadata_contains_query(self):
        search_result = _make_search_result(total=0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is not None
        assert "query" in gap.metadata


# ---------------------------------------------------------------------------
# 4. KnowledgeGapDetector.analyze() — WEAK
# ---------------------------------------------------------------------------


class TestAnalyzeWeak:
    """Тесты analyze() → WEAK gap."""

    def setup_method(self):
        self.detector, self.memory = _make_detector(weak_threshold=0.5)

    def test_weak_when_confidence_below_threshold(self):
        """best.confidence < weak_threshold → WEAK/MEDIUM."""
        search_result = _make_search_result(total=1, best_confidence=0.3, best_age_days=5.0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is not None
        assert gap.gap_type == GapType.WEAK
        assert gap.severity == GapSeverity.MEDIUM

    def test_weak_concept_set(self):
        search_result = _make_search_result(total=1, best_confidence=0.2, best_age_days=5.0)
        gap = self.detector.analyze("синапс", search_result)
        assert gap is not None
        assert gap.concept == "синапс"

    def test_no_weak_when_confidence_at_threshold(self):
        """best.confidence == weak_threshold → не WEAK (нет gap)."""
        search_result = _make_search_result(total=1, best_confidence=0.5, best_age_days=5.0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is None

    def test_no_weak_when_confidence_above_threshold(self):
        """best.confidence > weak_threshold → не WEAK."""
        search_result = _make_search_result(total=1, best_confidence=0.8, best_age_days=5.0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is None

    def test_weak_metadata_contains_confidence(self):
        search_result = _make_search_result(total=1, best_confidence=0.3, best_age_days=5.0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is not None
        assert "confidence" in gap.metadata


# ---------------------------------------------------------------------------
# 5. KnowledgeGapDetector.analyze() — OUTDATED
# ---------------------------------------------------------------------------


class TestAnalyzeOutdated:
    """Тесты analyze() → OUTDATED gap."""

    def setup_method(self):
        self.detector, self.memory = _make_detector(
            weak_threshold=0.5,
            outdated_days=30.0,
        )

    def test_outdated_when_age_exceeds_threshold(self):
        """best.age_days() > outdated_days → OUTDATED/LOW."""
        search_result = _make_search_result(total=1, best_confidence=0.8, best_age_days=45.0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is not None
        assert gap.gap_type == GapType.OUTDATED
        assert gap.severity == GapSeverity.LOW

    def test_no_outdated_when_age_below_threshold(self):
        """best.age_days() <= outdated_days → нет gap."""
        search_result = _make_search_result(total=1, best_confidence=0.8, best_age_days=10.0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is None

    def test_no_outdated_at_exact_threshold(self):
        """best.age_days() == outdated_days → нет gap."""
        search_result = _make_search_result(total=1, best_confidence=0.8, best_age_days=30.0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is None

    def test_outdated_metadata_contains_age_days(self):
        search_result = _make_search_result(total=1, best_confidence=0.8, best_age_days=45.0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is not None
        assert "age_days" in gap.metadata

    def test_weak_takes_priority_over_outdated(self):
        """WEAK проверяется раньше OUTDATED (confidence < threshold)."""
        search_result = _make_search_result(total=1, best_confidence=0.3, best_age_days=45.0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is not None
        assert gap.gap_type == GapType.WEAK


# ---------------------------------------------------------------------------
# 6. KnowledgeGapDetector.analyze() — None (нет gap)
# ---------------------------------------------------------------------------


class TestAnalyzeNoGap:
    """Тесты analyze() → None (нет gap)."""

    def setup_method(self):
        self.detector, self.memory = _make_detector()

    def test_no_gap_when_good_result(self):
        """Хороший результат → None."""
        search_result = _make_search_result(total=1, best_confidence=0.8, best_age_days=5.0)
        gap = self.detector.analyze("нейрон", search_result)
        assert gap is None

    def test_no_gap_returns_none(self):
        search_result = _make_search_result(total=5, best_confidence=0.9, best_age_days=1.0)
        result = self.detector.analyze("синапс", search_result)
        assert result is None


# ---------------------------------------------------------------------------
# 7. KnowledgeGapDetector._register_gap() — дедупликация
# ---------------------------------------------------------------------------


class TestRegisterGapDeduplication:
    """Тесты дедупликации по concept + gap_type."""

    def setup_method(self):
        self.detector, self.memory = _make_detector()

    def test_same_concept_and_type_not_duplicated(self):
        """Повторный analyze с тем же concept+gap_type → тот же gap."""
        search_result = _make_search_result(total=0)
        gap1 = self.detector.analyze("нейрон", search_result)
        gap2 = self.detector.analyze("нейрон", search_result)
        assert gap1 is not None
        assert gap2 is not None
        assert gap1.gap_id == gap2.gap_id

    def test_different_concepts_create_different_gaps(self):
        """Разные концепты → разные gap_id."""
        search_result = _make_search_result(total=0)
        gap1 = self.detector.analyze("нейрон", search_result)
        gap2 = self.detector.analyze("синапс", search_result)
        assert gap1 is not None
        assert gap2 is not None
        assert gap1.gap_id != gap2.gap_id

    def test_different_gap_types_create_different_gaps(self):
        """Один концепт, разные типы → разные gap_id."""
        search_missing = _make_search_result(total=0)
        search_weak = _make_search_result(total=1, best_confidence=0.3, best_age_days=5.0)
        gap1 = self.detector.analyze("нейрон", search_missing)
        gap2 = self.detector.analyze("нейрон", search_weak)
        assert gap1 is not None
        assert gap2 is not None
        assert gap1.gap_id != gap2.gap_id

    def test_total_gaps_count_after_dedup(self):
        """После дедупликации — 1 gap, не 2."""
        search_result = _make_search_result(total=0)
        self.detector.analyze("нейрон", search_result)
        self.detector.analyze("нейрон", search_result)
        gaps = self.detector.get_gaps()
        assert len(gaps) == 1


# ---------------------------------------------------------------------------
# 8. KnowledgeGapDetector.get_gaps() — фильтрация
# ---------------------------------------------------------------------------


class TestGetGaps:
    """Тесты get_gaps() — фильтрация по severity и resolved."""

    def setup_method(self):
        self.detector, self.memory = _make_detector()

    def _add_gap(self, concept: str, severity: GapSeverity, gap_type: GapType) -> KnowledgeGap:
        return self.detector._register_gap(concept, severity, gap_type, {})

    def test_get_all_unresolved_gaps(self):
        self._add_gap("нейрон", GapSeverity.HIGH, GapType.MISSING)
        self._add_gap("синапс", GapSeverity.MEDIUM, GapType.WEAK)
        gaps = self.detector.get_gaps()
        assert len(gaps) == 2

    def test_filter_by_severity_high(self):
        self._add_gap("нейрон", GapSeverity.HIGH, GapType.MISSING)
        self._add_gap("синапс", GapSeverity.MEDIUM, GapType.WEAK)
        gaps = self.detector.get_gaps(severity=GapSeverity.HIGH)
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.HIGH

    def test_filter_by_severity_medium(self):
        self._add_gap("нейрон", GapSeverity.HIGH, GapType.MISSING)
        self._add_gap("синапс", GapSeverity.MEDIUM, GapType.WEAK)
        gaps = self.detector.get_gaps(severity=GapSeverity.MEDIUM)
        assert len(gaps) == 1
        assert gaps[0].severity == GapSeverity.MEDIUM

    def test_get_resolved_gaps(self):
        gap = self._add_gap("нейрон", GapSeverity.HIGH, GapType.MISSING)
        self.detector.resolve_gap(gap.gap_id)
        resolved = self.detector.get_gaps(resolved=True)
        assert len(resolved) == 1
        assert resolved[0].resolved is True

    def test_unresolved_not_in_resolved_filter(self):
        """get_gaps(resolved=True) возвращает все gap'ы (включая нерешённые)."""
        self._add_gap("нейрон", GapSeverity.HIGH, GapType.MISSING)
        resolved = self.detector.get_gaps(resolved=True)
        assert len(resolved) == 1

    def test_empty_when_no_gaps(self):
        gaps = self.detector.get_gaps()
        assert gaps == []

    def test_returns_list(self):
        gaps = self.detector.get_gaps()
        assert isinstance(gaps, list)


# ---------------------------------------------------------------------------
# 9. KnowledgeGapDetector.resolve_gap() / resolve_by_concept()
# ---------------------------------------------------------------------------


class TestResolveGap:
    """Тесты resolve_gap() и resolve_by_concept()."""

    def setup_method(self):
        self.detector, self.memory = _make_detector()

    def test_resolve_gap_by_id(self):
        gap = self.detector._register_gap("нейрон", GapSeverity.HIGH, GapType.MISSING, {})
        result = self.detector.resolve_gap(gap.gap_id)
        assert result is True
        assert gap.resolved is True

    def test_resolve_gap_unknown_id_returns_false(self):
        result = self.detector.resolve_gap("unknown_gap_id")
        assert result is False

    def test_resolve_by_concept_resolves_all_matching(self):
        self.detector._register_gap("нейрон", GapSeverity.HIGH, GapType.MISSING, {})
        self.detector._register_gap("нейрон", GapSeverity.MEDIUM, GapType.WEAK, {})
        count = self.detector.resolve_by_concept("нейрон")
        assert count == 2

    def test_resolve_by_concept_returns_count(self):
        self.detector._register_gap("синапс", GapSeverity.HIGH, GapType.MISSING, {})
        count = self.detector.resolve_by_concept("синапс")
        assert count == 1

    def test_resolve_by_concept_unknown_returns_zero(self):
        count = self.detector.resolve_by_concept("неизвестный_концепт")
        assert count == 0

    def test_resolve_by_concept_does_not_affect_other_concepts(self):
        self.detector._register_gap("нейрон", GapSeverity.HIGH, GapType.MISSING, {})
        self.detector._register_gap("синапс", GapSeverity.HIGH, GapType.MISSING, {})
        self.detector.resolve_by_concept("нейрон")
        unresolved = self.detector.get_gaps()
        assert len(unresolved) == 1
        assert unresolved[0].concept == "синапс"

    def test_resolved_gap_not_in_unresolved_list(self):
        gap = self.detector._register_gap("нейрон", GapSeverity.HIGH, GapType.MISSING, {})
        self.detector.resolve_gap(gap.gap_id)
        unresolved = self.detector.get_gaps(resolved=False)
        assert all(g.gap_id != gap.gap_id for g in unresolved)


# ---------------------------------------------------------------------------
# 10. KnowledgeGapDetector._evict_resolved() — очистка при max_gaps
# ---------------------------------------------------------------------------


class TestEvictResolved:
    """Тесты _evict_resolved() — очистка при достижении max_gaps."""

    def test_evict_resolved_when_max_gaps_reached(self):
        """При max_gaps=3 и 3 gap'ах — resolved удаляются при добавлении нового."""
        detector, _ = _make_detector(max_gaps=3)
        gap1 = detector._register_gap("нейрон", GapSeverity.HIGH, GapType.MISSING, {})
        _gap2 = detector._register_gap("синапс", GapSeverity.MEDIUM, GapType.WEAK, {})
        _gap3 = detector._register_gap("мозг", GapSeverity.LOW, GapType.OUTDATED, {})
        # Разрешаем gap1
        detector.resolve_gap(gap1.gap_id)
        # Добавляем 4-й gap → должна сработать evict
        _gap4 = detector._register_gap("кортекс", GapSeverity.HIGH, GapType.MISSING, {})
        # gap1 (resolved) должен быть удалён
        all_gaps = detector.get_gaps(resolved=False) + detector.get_gaps(resolved=True)
        gap_ids = [g.gap_id for g in all_gaps]
        assert gap1.gap_id not in gap_ids

    def test_unresolved_not_evicted(self):
        """Нерешённые gap'ы не удаляются при evict."""
        detector, _ = _make_detector(max_gaps=2)
        gap1 = detector._register_gap("нейрон", GapSeverity.HIGH, GapType.MISSING, {})
        gap2 = detector._register_gap("синапс", GapSeverity.MEDIUM, GapType.WEAK, {})
        # Добавляем 3-й без resolved → evict не должен удалять нерешённые
        _gap3 = detector._register_gap("мозг", GapSeverity.LOW, GapType.OUTDATED, {})
        unresolved = detector.get_gaps(resolved=False)
        # Все нерешённые должны остаться
        gap_ids = [g.gap_id for g in unresolved]
        assert gap1.gap_id in gap_ids
        assert gap2.gap_id in gap_ids


# ---------------------------------------------------------------------------
# 11. KnowledgeGapDetector.status() / __repr__()
# ---------------------------------------------------------------------------


class TestKnowledgeGapDetectorStatus:
    """Тесты status() и __repr__()."""

    def setup_method(self):
        self.detector, self.memory = _make_detector()

    def test_status_returns_dict(self):
        status = self.detector.status()
        assert isinstance(status, dict)

    def test_status_keys(self):
        status = self.detector.status()
        for key in ("detected_count", "active_gaps", "resolved_count", "weak_threshold",
                    "outdated_days", "max_gaps"):
            assert key in status

    def test_status_initial_values(self):
        status = self.detector.status()
        assert status["detected_count"] == 0
        assert status["active_gaps"] == 0
        assert status["resolved_count"] == 0

    def test_status_after_adding_gaps(self):
        self.detector._register_gap("нейрон", GapSeverity.HIGH, GapType.MISSING, {})
        self.detector._register_gap("синапс", GapSeverity.MEDIUM, GapType.WEAK, {})
        status = self.detector.status()
        assert status["detected_count"] == 2
        assert status["active_gaps"] == 2
        assert status["resolved_count"] == 0

    def test_status_after_resolve(self):
        gap = self.detector._register_gap("нейрон", GapSeverity.HIGH, GapType.MISSING, {})
        self.detector.resolve_gap(gap.gap_id)
        status = self.detector.status()
        assert status["resolved_count"] == 1
        assert status["active_gaps"] == 0

    def test_repr_contains_key_info(self):
        r = repr(self.detector)
        assert "KnowledgeGapDetector" in r
        assert "active=" in r

    def test_status_weak_threshold_matches_init(self):
        detector, _ = _make_detector(weak_threshold=0.3)
        status = detector.status()
        assert status["weak_threshold"] == 0.3

    def test_status_outdated_days_matches_init(self):
        detector, _ = _make_detector(outdated_days=60.0)
        status = detector.status()
        assert status["outdated_days"] == 60.0
