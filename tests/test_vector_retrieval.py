"""
tests/test_vector_retrieval.py

Unit-тесты для VectorRetrievalBackend и HybridRetrievalBackend.

Покрытие:
  VectorRetrievalBackend (~10 тестов):
    - add/store вектор + метаданные
    - search_by_vector: top-K по косинусному сходству
    - search_by_vector: порог min_similarity
    - search_by_vector: пустое хранилище → []
    - add: нулевой вектор → игнорируется
    - search_by_vector: несовпадение размерности → similarity=0
    - remove: удаление не влияет на остальные
    - clear: очистка хранилища
    - search (keyword fallback): текстовый overlap
    - size property

  HybridRetrievalBackend (~10 тестов):
    - search_hybrid: alpha=1.0 (vector-only weight)
    - search_hybrid: alpha=0.0 (keyword-only weight)
    - search_hybrid: mixed results merged via RRF
    - дедупликация: одна запись не дублируется
    - ранжирование: более релевантный результат выше
    - один бэкенд пуст → второй работает
    - оба пусты → []
    - search (keyword-only, Protocol compliance)
    - search_hybrid без вектора → keyword fallback
    - RetrievalAdapter integration: hybrid dispatch
"""

import math
import pytest
from dataclasses import dataclass, field
from typing import List, Optional

from brain.cognition.context import EvidencePack
from brain.cognition.retrieval_adapter import (
    VectorRetrievalBackend,
    HybridRetrievalBackend,
    KeywordRetrievalBackend,
    RetrievalAdapter,
    RetrievalBackend,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_vector(dim: int = 4, base: float = 1.0) -> List[float]:
    """Create a simple non-zero vector of given dimension."""
    return [base * (i + 1) for i in range(dim)]


def _make_orthogonal_vectors(dim: int = 4):
    """Create two orthogonal vectors (cosine similarity ≈ 0)."""
    v1 = [1.0, 0.0, 0.0, 0.0] + [0.0] * (dim - 4)
    v2 = [0.0, 1.0, 0.0, 0.0] + [0.0] * (dim - 4)
    return v1[:dim], v2[:dim]


def _make_similar_vectors(dim: int = 4):
    """Create two very similar vectors (cosine similarity ≈ 1)."""
    v1 = [1.0] * dim
    v2 = [1.0 + 0.01 * i for i in range(dim)]
    return v1, v2


def _cosine_sim(a: List[float], b: List[float]) -> float:
    """Reference cosine similarity for test assertions."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


# ═══════════════════════════════════════════════════════════════════════════
# Mock MemoryManager for KeywordRetrievalBackend
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MockMemoryItem:
    content: str = ""
    source_ref: str = ""
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5
    ts: Optional[float] = None
    modality: str = "text"


@dataclass
class MockSearchResult:
    working: List[MockMemoryItem] = field(default_factory=list)
    semantic: list = field(default_factory=list)
    episodic: list = field(default_factory=list)


class MockMemoryManager:
    """Mock MemoryManager with configurable retrieve() results."""

    def __init__(self, items: Optional[List[MockMemoryItem]] = None):
        self._items = items or []

    def retrieve(self, query: str, top_n: int = 10) -> MockSearchResult:
        return MockSearchResult(working=self._items[:top_n])


# ═══════════════════════════════════════════════════════════════════════════
# VectorRetrievalBackend Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestVectorRetrievalBackend:
    """Tests for VectorRetrievalBackend."""

    def test_add_and_size(self):
        """add() stores entry, size reflects count."""
        backend = VectorRetrievalBackend()
        assert backend.size == 0

        backend.add("ev_1", content="нейрон", vector=[1.0, 2.0, 3.0])
        assert backend.size == 1

        backend.add("ev_2", content="синапс", vector=[4.0, 5.0, 6.0])
        assert backend.size == 2

    def test_add_zero_vector_ignored(self):
        """add() with all-zero vector is silently ignored."""
        backend = VectorRetrievalBackend()
        backend.add("ev_zero", content="пустой", vector=[0.0, 0.0, 0.0])
        assert backend.size == 0

    def test_add_empty_vector_ignored(self):
        """add() with empty vector is silently ignored."""
        backend = VectorRetrievalBackend()
        backend.add("ev_empty", content="пустой", vector=[])
        assert backend.size == 0

    def test_search_by_vector_returns_top_k(self):
        """search_by_vector returns top-K results sorted by similarity desc."""
        backend = VectorRetrievalBackend()

        # Add 3 vectors with known similarities to query
        query_vec = [1.0, 0.0, 0.0, 0.0]
        backend.add("ev_exact", content="exact match", vector=[1.0, 0.0, 0.0, 0.0])
        backend.add("ev_partial", content="partial", vector=[1.0, 1.0, 0.0, 0.0])
        backend.add("ev_ortho", content="orthogonal", vector=[0.0, 0.0, 1.0, 0.0])

        results = backend.search_by_vector(query_vec, top_n=3)
        assert len(results) == 3

        # First result should be exact match (similarity = 1.0)
        assert results[0].evidence_id == "ev_exact"
        assert results[0].relevance_score == pytest.approx(1.0, abs=1e-4)

        # Second should be partial (similarity ≈ 0.707)
        assert results[1].evidence_id == "ev_partial"
        expected_sim = _cosine_sim(query_vec, [1.0, 1.0, 0.0, 0.0])
        assert results[1].relevance_score == pytest.approx(expected_sim, abs=1e-4)

        # Third should be orthogonal (similarity = 0.0)
        assert results[2].evidence_id == "ev_ortho"
        assert results[2].relevance_score == pytest.approx(0.0, abs=1e-4)

    def test_search_by_vector_top_n_limit(self):
        """search_by_vector respects top_n limit."""
        backend = VectorRetrievalBackend()
        for i in range(10):
            backend.add(f"ev_{i}", content=f"item {i}", vector=[float(i + 1), 0.0, 0.0])

        results = backend.search_by_vector([1.0, 0.0, 0.0], top_n=3)
        assert len(results) == 3

    def test_search_by_vector_min_similarity_threshold(self):
        """search_by_vector filters out results below min_similarity."""
        backend = VectorRetrievalBackend()

        query_vec = [1.0, 0.0, 0.0, 0.0]
        backend.add("ev_high", content="high sim", vector=[1.0, 0.1, 0.0, 0.0])
        backend.add("ev_low", content="low sim", vector=[0.0, 0.0, 1.0, 0.0])

        # With threshold 0.5, only high-sim should pass
        results = backend.search_by_vector(query_vec, top_n=10, min_similarity=0.5)
        assert len(results) == 1
        assert results[0].evidence_id == "ev_high"

    def test_search_by_vector_empty_index(self):
        """search_by_vector on empty index returns []."""
        backend = VectorRetrievalBackend()
        results = backend.search_by_vector([1.0, 2.0, 3.0], top_n=5)
        assert results == []

    def test_search_by_vector_empty_query(self):
        """search_by_vector with empty query vector returns []."""
        backend = VectorRetrievalBackend()
        backend.add("ev_1", content="test", vector=[1.0, 2.0])
        results = backend.search_by_vector([], top_n=5)
        assert results == []

    def test_search_by_vector_dimension_mismatch(self):
        """Mismatched dimensions → cosine_similarity returns 0.0 (no crash)."""
        backend = VectorRetrievalBackend()
        backend.add("ev_3d", content="3d vector", vector=[1.0, 2.0, 3.0])

        # Query with different dimension
        results = backend.search_by_vector([1.0, 2.0], top_n=5)
        # _cosine_similarity returns 0.0 for mismatched lengths
        assert len(results) == 1
        assert results[0].relevance_score == pytest.approx(0.0, abs=1e-6)

    def test_search_by_vector_metadata_preserved(self):
        """search_by_vector preserves metadata fields from add()."""
        backend = VectorRetrievalBackend()
        backend.add(
            "ev_meta",
            content="нейрон — клетка",
            vector=[1.0, 0.0],
            memory_type="semantic",
            confidence=0.95,
            concept_refs=["нейрон", "клетка"],
            source_refs=["textbook"],
            timestamp="2025-01-01T00:00:00",
        )

        results = backend.search_by_vector([1.0, 0.0], top_n=1)
        assert len(results) == 1
        ev = results[0]
        assert ev.evidence_id == "ev_meta"
        assert ev.content == "нейрон — клетка"
        assert ev.memory_type == "semantic"
        assert ev.confidence == 0.95
        assert "нейрон" in ev.concept_refs
        assert "textbook" in ev.source_refs
        assert ev.timestamp == "2025-01-01T00:00:00"
        assert "vector_similarity" in ev.metadata

    def test_remove_entry(self):
        """remove() deletes entry without affecting others."""
        backend = VectorRetrievalBackend()
        backend.add("ev_a", content="a", vector=[1.0, 0.0])
        backend.add("ev_b", content="b", vector=[0.0, 1.0])
        assert backend.size == 2

        backend.remove("ev_a")
        assert backend.size == 1

        results = backend.search_by_vector([1.0, 0.0], top_n=10)
        assert len(results) == 1
        assert results[0].evidence_id == "ev_b"

    def test_remove_nonexistent_no_error(self):
        """remove() on nonexistent ID does not raise."""
        backend = VectorRetrievalBackend()
        backend.remove("nonexistent")  # should not raise
        assert backend.size == 0

    def test_clear(self):
        """clear() empties the entire index."""
        backend = VectorRetrievalBackend()
        backend.add("ev_1", content="a", vector=[1.0])
        backend.add("ev_2", content="b", vector=[2.0])
        assert backend.size == 2

        backend.clear()
        assert backend.size == 0
        assert backend.search_by_vector([1.0], top_n=10) == []

    def test_search_keyword_fallback(self):
        """search() (text-based) returns results based on keyword overlap."""
        backend = VectorRetrievalBackend()
        backend.add("ev_neuron", content="нейрон клетка мозга", vector=[1.0, 0.0])
        backend.add("ev_synapse", content="синапс связь", vector=[0.0, 1.0])

        results = backend.search("нейрон", top_n=10)
        assert len(results) >= 1
        assert results[0].evidence_id == "ev_neuron"

    def test_search_keyword_no_match(self):
        """search() with no keyword overlap returns []."""
        backend = VectorRetrievalBackend()
        backend.add("ev_1", content="нейрон клетка", vector=[1.0, 0.0])

        results = backend.search("квантовая физика", top_n=10)
        assert results == []

    def test_cosine_similarity_identical_vectors(self):
        """Cosine similarity of identical vectors = 1.0."""
        v = [1.0, 2.0, 3.0, 4.0]
        sim = VectorRetrievalBackend._cosine_similarity(v, v)
        assert sim == pytest.approx(1.0, abs=1e-6)

    def test_cosine_similarity_orthogonal_vectors(self):
        """Cosine similarity of orthogonal vectors = 0.0."""
        v1, v2 = _make_orthogonal_vectors(4)
        sim = VectorRetrievalBackend._cosine_similarity(v1, v2)
        assert sim == pytest.approx(0.0, abs=1e-6)

    def test_cosine_similarity_zero_norm(self):
        """Cosine similarity with zero-norm vector = 0.0."""
        sim = VectorRetrievalBackend._cosine_similarity([0.0, 0.0], [1.0, 2.0])
        assert sim == pytest.approx(0.0, abs=1e-6)


# ═══════════════════════════════════════════════════════════════════════════
# HybridRetrievalBackend Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestHybridRetrievalBackend:
    """Tests for HybridRetrievalBackend."""

    def _make_hybrid(
        self,
        memory_items: Optional[List[MockMemoryItem]] = None,
        vector_entries: Optional[List[dict]] = None,
    ) -> HybridRetrievalBackend:
        """Helper: create HybridRetrievalBackend with optional data."""
        mm = MockMemoryManager(memory_items or [])
        keyword_backend = KeywordRetrievalBackend(mm)
        vector_backend = VectorRetrievalBackend()

        if vector_entries:
            for entry in vector_entries:
                vector_backend.add(**entry)

        return HybridRetrievalBackend(keyword_backend, vector_backend)

    def test_search_keyword_only_protocol(self):
        """search() (Protocol method) delegates to keyword backend only."""
        items = [MockMemoryItem(content="нейрон клетка")]
        hybrid = self._make_hybrid(memory_items=items)

        results = hybrid.search("нейрон", top_n=5)
        assert len(results) >= 1
        assert "нейрон" in results[0].content

    def test_search_hybrid_no_vector_falls_back_to_keyword(self):
        """search_hybrid() without query_vector returns keyword results."""
        items = [MockMemoryItem(content="нейрон клетка")]
        hybrid = self._make_hybrid(memory_items=items)

        results = hybrid.search_hybrid("нейрон", query_vector=None, top_n=5)
        assert len(results) >= 1

    def test_search_hybrid_empty_vector_backend_falls_back(self):
        """search_hybrid() with empty vector backend returns keyword results."""
        items = [MockMemoryItem(content="нейрон клетка")]
        hybrid = self._make_hybrid(memory_items=items)

        results = hybrid.search_hybrid(
            "нейрон", query_vector=[1.0, 0.0], top_n=5,
        )
        # Vector backend is empty → falls back to keyword
        assert len(results) >= 1

    def test_search_hybrid_merges_results(self):
        """search_hybrid() merges keyword + vector results via RRF."""
        items = [
            MockMemoryItem(content="нейрон клетка мозга"),
            MockMemoryItem(content="синапс связь нейрон"),
        ]
        vector_entries = [
            {
                "evidence_id": "ev_vec_1",
                "content": "вектор нейрон",
                "vector": [1.0, 0.0, 0.0],
            },
            {
                "evidence_id": "ev_vec_2",
                "content": "вектор синапс",
                "vector": [0.0, 1.0, 0.0],
            },
        ]
        hybrid = self._make_hybrid(
            memory_items=items, vector_entries=vector_entries,
        )

        results = hybrid.search_hybrid(
            "нейрон", query_vector=[1.0, 0.0, 0.0], top_n=10,
        )
        # Should have results from both keyword and vector
        assert len(results) >= 1

        # All results should be EvidencePack
        for r in results:
            assert isinstance(r, EvidencePack)
            assert r.evidence_id != ""

    def test_search_hybrid_deduplication(self):
        """Same evidence_id from both backends appears only once."""
        # Create keyword backend that returns an item
        items = [MockMemoryItem(content="нейрон клетка")]
        mm = MockMemoryManager(items)
        keyword_backend = KeywordRetrievalBackend(mm)

        # Get the evidence_id that keyword backend would generate
        keyword_results = keyword_backend.search("нейрон", top_n=1)
        if keyword_results:
            shared_id = keyword_results[0].evidence_id
        else:
            shared_id = "ev_shared"

        # Add same ID to vector backend
        vector_backend = VectorRetrievalBackend()
        vector_backend.add(
            shared_id, content="нейрон клетка", vector=[1.0, 0.0],
        )

        hybrid = HybridRetrievalBackend(keyword_backend, vector_backend)
        results = hybrid.search_hybrid(
            "нейрон", query_vector=[1.0, 0.0], top_n=10,
        )

        # Count occurrences of shared_id
        ids = [r.evidence_id for r in results]
        assert ids.count(shared_id) == 1, f"Duplicate found: {ids}"

    def test_search_hybrid_ranking_order(self):
        """More relevant results should rank higher in merged output."""
        vector_entries = [
            {
                "evidence_id": "ev_high",
                "content": "высокая релевантность",
                "vector": [1.0, 0.0, 0.0],
            },
            {
                "evidence_id": "ev_low",
                "content": "низкая релевантность",
                "vector": [0.0, 0.0, 1.0],
            },
        ]
        hybrid = self._make_hybrid(vector_entries=vector_entries)

        results = hybrid.search_hybrid(
            "релевантность", query_vector=[1.0, 0.0, 0.0], top_n=10,
        )

        if len(results) >= 2:
            # ev_high should have higher RRF score than ev_low
            high_idx = next(
                (i for i, r in enumerate(results) if r.evidence_id == "ev_high"),
                None,
            )
            low_idx = next(
                (i for i, r in enumerate(results) if r.evidence_id == "ev_low"),
                None,
            )
            if high_idx is not None and low_idx is not None:
                assert high_idx < low_idx, (
                    f"ev_high at {high_idx}, ev_low at {low_idx}"
                )

    def test_both_backends_empty(self):
        """Both backends empty → search_hybrid returns []."""
        hybrid = self._make_hybrid()
        results = hybrid.search_hybrid(
            "нейрон", query_vector=[1.0, 0.0], top_n=10,
        )
        assert results == []

    def test_keyword_backend_empty_vector_has_data(self):
        """Keyword empty, vector has data → returns vector results."""
        vector_entries = [
            {
                "evidence_id": "ev_vec",
                "content": "вектор нейрон",
                "vector": [1.0, 0.0],
            },
        ]
        hybrid = self._make_hybrid(vector_entries=vector_entries)

        results = hybrid.search_hybrid(
            "нейрон", query_vector=[1.0, 0.0], top_n=10,
        )
        # Should still return vector results even without keyword matches
        assert len(results) >= 1

    def test_vector_backend_empty_keyword_has_data(self):
        """Vector empty, keyword has data → returns keyword results."""
        items = [MockMemoryItem(content="нейрон клетка")]
        hybrid = self._make_hybrid(memory_items=items)

        results = hybrid.search_hybrid(
            "нейрон", query_vector=[1.0, 0.0], top_n=10,
        )
        assert len(results) >= 1

    def test_rrf_merge_weights(self):
        """RRF merge respects KEYWORD_WEIGHT and VECTOR_WEIGHT."""
        hybrid = self._make_hybrid()

        # Create mock results
        kw_results = [
            EvidencePack(evidence_id="ev_kw", content="keyword", relevance_score=1.0),
        ]
        vec_results = [
            EvidencePack(evidence_id="ev_vec", content="vector", relevance_score=1.0),
        ]

        merged = hybrid._rrf_merge(kw_results, vec_results, top_n=10)
        assert len(merged) == 2

        scores = {r.evidence_id: r.relevance_score for r in merged}
        # Vector weight (0.6) > keyword weight (0.4), so ev_vec should score higher
        assert scores["ev_vec"] > scores["ev_kw"], (
            f"Expected ev_vec > ev_kw, got {scores}"
        )

    def test_rrf_merge_both_sources_boost(self):
        """Item appearing in both keyword and vector gets boosted RRF score."""
        hybrid = self._make_hybrid()

        shared = EvidencePack(
            evidence_id="ev_shared", content="shared", relevance_score=0.8,
        )
        kw_only = EvidencePack(
            evidence_id="ev_kw_only", content="kw only", relevance_score=0.9,
        )
        vec_only = EvidencePack(
            evidence_id="ev_vec_only", content="vec only", relevance_score=0.9,
        )

        kw_results = [shared, kw_only]
        vec_results = [shared, vec_only]

        merged = hybrid._rrf_merge(kw_results, vec_results, top_n=10)
        scores = {r.evidence_id: r.relevance_score for r in merged}

        # Shared item gets score from both keyword AND vector → highest
        assert scores["ev_shared"] > scores["ev_kw_only"], (
            f"Shared should beat kw_only: {scores}"
        )
        assert scores["ev_shared"] > scores["ev_vec_only"], (
            f"Shared should beat vec_only: {scores}"
        )

    def test_backend_properties(self):
        """keyword_backend and vector_backend properties are accessible."""
        hybrid = self._make_hybrid()
        assert isinstance(hybrid.keyword_backend, KeywordRetrievalBackend)
        assert isinstance(hybrid.vector_backend, VectorRetrievalBackend)

    def test_zero_query_vector_falls_back(self):
        """search_hybrid with all-zero query_vector falls back to keyword."""
        items = [MockMemoryItem(content="нейрон клетка")]
        vector_entries = [
            {
                "evidence_id": "ev_vec",
                "content": "вектор",
                "vector": [1.0, 0.0],
            },
        ]
        hybrid = self._make_hybrid(
            memory_items=items, vector_entries=vector_entries,
        )

        results = hybrid.search_hybrid(
            "нейрон", query_vector=[0.0, 0.0], top_n=10,
        )
        # Zero vector → no vector results → keyword fallback
        assert len(results) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# RetrievalAdapter Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRetrievalAdapterHybrid:
    """Tests for RetrievalAdapter with HybridRetrievalBackend."""

    def test_adapter_dispatches_to_hybrid_search(self):
        """RetrievalAdapter.retrieve() with query_vector dispatches to search_hybrid."""
        items = [MockMemoryItem(content="нейрон клетка")]
        mm = MockMemoryManager(items)
        keyword_backend = KeywordRetrievalBackend(mm)
        vector_backend = VectorRetrievalBackend()
        vector_backend.add("ev_vec", content="нейрон вектор", vector=[1.0, 0.0])

        hybrid = HybridRetrievalBackend(keyword_backend, vector_backend)
        adapter = RetrievalAdapter(backend=hybrid, memory_manager=mm)

        # With query_vector → should use search_hybrid
        results = adapter.retrieve(
            "нейрон", top_n=10, query_vector=[1.0, 0.0],
        )
        assert len(results) >= 1

        # All results should have adapter metadata
        for r in results:
            assert "retrieval_backend" in r.metadata
            assert r.metadata["retrieval_backend"] == "HybridRetrievalBackend"

    def test_adapter_without_vector_uses_keyword(self):
        """RetrievalAdapter.retrieve() without query_vector uses keyword search."""
        items = [MockMemoryItem(content="нейрон клетка")]
        mm = MockMemoryManager(items)
        keyword_backend = KeywordRetrievalBackend(mm)
        vector_backend = VectorRetrievalBackend()

        hybrid = HybridRetrievalBackend(keyword_backend, vector_backend)
        adapter = RetrievalAdapter(backend=hybrid, memory_manager=mm)

        results = adapter.retrieve("нейрон", top_n=10)
        assert len(results) >= 1

    def test_adapter_empty_query_returns_empty(self):
        """RetrievalAdapter.retrieve() with empty query returns []."""
        mm = MockMemoryManager()
        keyword_backend = KeywordRetrievalBackend(mm)
        vector_backend = VectorRetrievalBackend()
        hybrid = HybridRetrievalBackend(keyword_backend, vector_backend)
        adapter = RetrievalAdapter(backend=hybrid, memory_manager=mm)

        assert adapter.retrieve("", top_n=10) == []
        assert adapter.retrieve("   ", top_n=10) == []

    def test_adapter_backend_name(self):
        """RetrievalAdapter.backend_name reflects the actual backend."""
        mm = MockMemoryManager()
        keyword_backend = KeywordRetrievalBackend(mm)
        vector_backend = VectorRetrievalBackend()
        hybrid = HybridRetrievalBackend(keyword_backend, vector_backend)
        adapter = RetrievalAdapter(backend=hybrid)

        assert adapter.backend_name == "HybridRetrievalBackend"

    def test_adapter_with_keyword_backend_ignores_vector(self):
        """RetrievalAdapter with KeywordRetrievalBackend ignores query_vector."""
        items = [MockMemoryItem(content="нейрон клетка")]
        mm = MockMemoryManager(items)
        keyword_backend = KeywordRetrievalBackend(mm)
        adapter = RetrievalAdapter(backend=keyword_backend, memory_manager=mm)

        # query_vector is passed but backend is not Hybrid → ignored
        results = adapter.retrieve(
            "нейрон", top_n=10, query_vector=[1.0, 0.0],
        )
        assert len(results) >= 1
        assert adapter.backend_name == "KeywordRetrievalBackend"


# ═══════════════════════════════════════════════════════════════════════════
# Protocol Compliance
# ═══════════════════════════════════════════════════════════════════════════

class TestProtocolCompliance:
    """Verify that backends satisfy RetrievalBackend Protocol."""

    def test_vector_backend_is_retrieval_backend(self):
        """VectorRetrievalBackend satisfies RetrievalBackend Protocol."""
        backend = VectorRetrievalBackend()
        assert isinstance(backend, RetrievalBackend)

    def test_hybrid_backend_is_retrieval_backend(self):
        """HybridRetrievalBackend satisfies RetrievalBackend Protocol."""
        mm = MockMemoryManager()
        keyword = KeywordRetrievalBackend(mm)
        vector = VectorRetrievalBackend()
        hybrid = HybridRetrievalBackend(keyword, vector)
        assert isinstance(hybrid, RetrievalBackend)

    def test_keyword_backend_is_retrieval_backend(self):
        """KeywordRetrievalBackend satisfies RetrievalBackend Protocol."""
        mm = MockMemoryManager()
        backend = KeywordRetrievalBackend(mm)
        assert isinstance(backend, RetrievalBackend)
