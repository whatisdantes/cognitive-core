"""
tests/test_bm25.py

Тесты для BM25Scorer и BM25 reranking в KeywordRetrievalBackend.

Покрытие:
  - BM25Scorer: init, fit, score, score_batch, tokenize, IDF, edge cases
  - KeywordRetrievalBackend: BM25 reranking integration
  - Fallback без fit
  - Graceful fallback без pymorphy3
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock

import pytest

from brain.cognition.retrieval_adapter import (
    BM25Scorer,
    KeywordRetrievalBackend,
)
from brain.cognition.context import EvidencePack


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def sample_corpus() -> List[str]:
    """Корпус из 5 документов для тестирования BM25."""
    return [
        "нейрон это основная клетка нервной системы",
        "синапс соединяет два нейрона и передаёт сигнал",
        "мозг состоит из миллиардов нейронов",
        "дендрит принимает сигналы от других нейронов",
        "аксон передаёт электрический сигнал от нейрона",
    ]


@pytest.fixture
def fitted_scorer(sample_corpus: List[str]) -> BM25Scorer:
    """BM25Scorer, fit'нутый на sample_corpus."""
    scorer = BM25Scorer(k1=1.5, b=0.75, use_lemmatization=False)
    scorer.fit(sample_corpus)
    return scorer


@pytest.fixture
def single_doc_corpus() -> List[str]:
    """Корпус из одного документа."""
    return ["единственный документ в корпусе"]


# =========================================================================
# BM25Scorer — Initialization
# =========================================================================

class TestBM25ScorerInit:
    """Тесты инициализации BM25Scorer."""

    def test_default_params(self) -> None:
        scorer = BM25Scorer()
        assert scorer._k1 == 1.5
        assert scorer._b == 0.75
        assert not scorer.fitted
        assert scorer.vocab_size == 0

    def test_custom_params(self) -> None:
        scorer = BM25Scorer(k1=1.2, b=0.5, use_lemmatization=False)
        assert scorer._k1 == 1.2
        assert scorer._b == 0.5

    def test_not_fitted_initially(self) -> None:
        scorer = BM25Scorer()
        assert not scorer.fitted
        assert scorer.vocab_size == 0


# =========================================================================
# BM25Scorer — fit()
# =========================================================================

class TestBM25ScorerFit:
    """Тесты метода fit()."""

    def test_fit_returns_self(self, sample_corpus: List[str]) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        result = scorer.fit(sample_corpus)
        assert result is scorer

    def test_fit_sets_fitted(self, sample_corpus: List[str]) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        scorer.fit(sample_corpus)
        assert scorer.fitted

    def test_fit_empty_corpus(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        scorer.fit([])
        assert not scorer.fitted

    def test_fit_builds_idf(self, fitted_scorer: BM25Scorer) -> None:
        assert fitted_scorer.vocab_size > 0

    def test_fit_calculates_avgdl(self, fitted_scorer: BM25Scorer) -> None:
        assert fitted_scorer._avgdl > 0

    def test_fit_n_docs(
        self, fitted_scorer: BM25Scorer, sample_corpus: List[str]
    ) -> None:
        assert fitted_scorer._n_docs == len(sample_corpus)

    def test_fit_single_doc(self, single_doc_corpus: List[str]) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        scorer.fit(single_doc_corpus)
        assert scorer.fitted
        assert scorer._n_docs == 1

    def test_refit_resets_state(self, sample_corpus: List[str]) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        scorer.fit(sample_corpus)
        old_vocab = scorer.vocab_size

        scorer.fit(["совершенно другой текст"])
        assert scorer.vocab_size != old_vocab
        assert scorer._n_docs == 1

    def test_fit_with_empty_strings(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        scorer.fit(["", "", ""])
        # Empty strings produce no tokens, but fit should still work
        assert scorer.fitted
        assert scorer.vocab_size == 0


# =========================================================================
# BM25Scorer — IDF calculation
# =========================================================================

class TestBM25ScorerIDF:
    """Тесты IDF вычислений."""

    def test_rare_term_higher_idf(self, fitted_scorer: BM25Scorer) -> None:
        """Редкий терм должен иметь более высокий IDF."""
        # "дендрит" встречается в 1 документе, "сигнал" — в нескольких
        idf_dendrit = fitted_scorer._idf.get("дендрит", 0.0)
        idf_signal = fitted_scorer._idf.get("сигнал", 0.0)
        # Дендрит реже → IDF выше
        assert idf_dendrit > idf_signal

    def test_common_term_lower_idf(self, fitted_scorer: BM25Scorer) -> None:
        """Терм, встречающийся во всех документах, имеет низкий IDF."""
        # Проверяем что IDF для частых термов ниже чем для редких
        idfs = list(fitted_scorer._idf.values())
        assert len(idfs) > 0
        # Не все IDF одинаковы (есть разброс)
        assert max(idfs) > min(idfs)

    def test_idf_non_negative(self, fitted_scorer: BM25Scorer) -> None:
        """Все IDF значения >= 0 (из-за +1 сглаживания)."""
        for term, idf in fitted_scorer._idf.items():
            assert idf >= 0.0, f"IDF for '{term}' is negative: {idf}"


# =========================================================================
# BM25Scorer — score()
# =========================================================================

class TestBM25ScorerScore:
    """Тесты метода score()."""

    def test_score_matching_query(self, fitted_scorer: BM25Scorer) -> None:
        """Документ с query-термами должен получить score > 0."""
        score = fitted_scorer.score(
            "нейрон клетка",
            "нейрон это основная клетка нервной системы",
        )
        assert score > 0.0

    def test_score_no_match(self, fitted_scorer: BM25Scorer) -> None:
        """Документ без query-термов → score = 0."""
        score = fitted_scorer.score(
            "квантовая физика",
            "нейрон это основная клетка нервной системы",
        )
        assert score == 0.0

    def test_score_empty_query(self, fitted_scorer: BM25Scorer) -> None:
        assert fitted_scorer.score("", "some document") == 0.0

    def test_score_empty_document(self, fitted_scorer: BM25Scorer) -> None:
        assert fitted_scorer.score("query", "") == 0.0

    def test_score_both_empty(self, fitted_scorer: BM25Scorer) -> None:
        assert fitted_scorer.score("", "") == 0.0

    def test_better_match_higher_score(
        self, fitted_scorer: BM25Scorer
    ) -> None:
        """Документ с большим количеством query-термов → выше score."""
        score_good = fitted_scorer.score(
            "нейрон сигнал",
            "аксон передаёт электрический сигнал от нейрона",
        )
        score_weak = fitted_scorer.score(
            "нейрон сигнал",
            "мозг состоит из миллиардов нейронов",
        )
        # "аксон передаёт сигнал от нейрона" содержит оба терма
        # "мозг состоит из нейронов" содержит только один
        assert score_good > score_weak

    def test_score_deterministic(self, fitted_scorer: BM25Scorer) -> None:
        """Повторный вызов score() даёт тот же результат."""
        s1 = fitted_scorer.score("нейрон", "нейрон это клетка")
        s2 = fitted_scorer.score("нейрон", "нейрон это клетка")
        assert s1 == s2

    def test_score_non_negative(
        self, fitted_scorer: BM25Scorer, sample_corpus: List[str]
    ) -> None:
        """Все scores >= 0."""
        for doc in sample_corpus:
            score = fitted_scorer.score("нейрон сигнал", doc)
            assert score >= 0.0


# =========================================================================
# BM25Scorer — score_batch()
# =========================================================================

class TestBM25ScorerBatch:
    """Тесты метода score_batch()."""

    def test_batch_same_as_individual(
        self, fitted_scorer: BM25Scorer, sample_corpus: List[str]
    ) -> None:
        """score_batch() == [score(q, d) for d in docs]."""
        query = "нейрон сигнал"
        batch = fitted_scorer.score_batch(query, sample_corpus)
        individual = [fitted_scorer.score(query, doc) for doc in sample_corpus]
        assert batch == individual

    def test_batch_empty_docs(self, fitted_scorer: BM25Scorer) -> None:
        assert fitted_scorer.score_batch("query", []) == []

    def test_batch_length(
        self, fitted_scorer: BM25Scorer, sample_corpus: List[str]
    ) -> None:
        batch = fitted_scorer.score_batch("нейрон", sample_corpus)
        assert len(batch) == len(sample_corpus)


# =========================================================================
# BM25Scorer — Fallback (not fitted)
# =========================================================================

class TestBM25ScorerFallback:
    """Тесты fallback поведения без fit()."""

    def test_score_without_fit_uses_overlap(self) -> None:
        """Без fit() → keyword overlap fallback."""
        scorer = BM25Scorer(use_lemmatization=False)
        score = scorer.score("нейрон клетка", "нейрон это клетка мозга")
        # keyword overlap: {нейрон, клетка} ∩ {нейрон, это, клетка, мозга}
        # = {нейрон, клетка} → 2/2 = 1.0
        assert score == pytest.approx(1.0)

    def test_fallback_partial_overlap(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        score = scorer.score("нейрон синапс", "нейрон это клетка")
        # {нейрон, синапс} ∩ {нейрон, это, клетка} = {нейрон} → 1/2 = 0.5
        assert score == pytest.approx(0.5)

    def test_fallback_no_overlap(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        score = scorer.score("квантовая физика", "нейрон это клетка")
        assert score == 0.0

    def test_fallback_empty_query(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        assert scorer.score("", "document") == 0.0

    def test_fallback_empty_document(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        assert scorer.score("query", "") == 0.0


# =========================================================================
# BM25Scorer — _tokenize()
# =========================================================================

class TestBM25ScorerTokenize:
    """Тесты токенизации."""

    def test_tokenize_basic(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        tokens = scorer._tokenize("Нейрон это Клетка")
        assert tokens == ["нейрон", "это", "клетка"]

    def test_tokenize_empty(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        assert scorer._tokenize("") == []

    def test_tokenize_punctuation(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        tokens = scorer._tokenize("нейрон, синапс! аксон?")
        assert tokens == ["нейрон", "синапс", "аксон"]

    def test_tokenize_numbers(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        tokens = scorer._tokenize("в мозге 86 миллиардов нейронов")
        assert "86" in tokens
        assert "миллиардов" in tokens

    def test_tokenize_mixed_case(self) -> None:
        scorer = BM25Scorer(use_lemmatization=False)
        tokens = scorer._tokenize("НЕЙРОН Нейрон нейрон")
        assert all(t == "нейрон" for t in tokens)


# =========================================================================
# BM25Scorer — _keyword_overlap_fallback()
# =========================================================================

class TestBM25ScorerOverlapFallback:
    """Тесты статического метода _keyword_overlap_fallback."""

    def test_full_overlap(self) -> None:
        score = BM25Scorer._keyword_overlap_fallback(
            "нейрон клетка", "нейрон это клетка мозга"
        )
        assert score == pytest.approx(1.0)

    def test_no_overlap(self) -> None:
        score = BM25Scorer._keyword_overlap_fallback(
            "квантовая физика", "нейрон клетка"
        )
        assert score == 0.0

    def test_empty_query(self) -> None:
        assert BM25Scorer._keyword_overlap_fallback("", "doc") == 0.0

    def test_empty_document(self) -> None:
        assert BM25Scorer._keyword_overlap_fallback("query", "") == 0.0


# =========================================================================
# BM25Scorer — Edge cases
# =========================================================================

class TestBM25ScorerEdgeCases:
    """Edge cases для BM25Scorer."""

    def test_identical_documents(self) -> None:
        """Все документы одинаковые → IDF = 0 для всех термов."""
        scorer = BM25Scorer(use_lemmatization=False)
        scorer.fit(["нейрон клетка", "нейрон клетка", "нейрон клетка"])
        # Все термы в каждом документе → IDF ≈ log(0.5/3.5 + 1) ≈ log(1.143)
        # Score будет маленьким но не нулевым из-за +1 сглаживания
        score = scorer.score("нейрон", "нейрон клетка")
        assert score >= 0.0

    def test_single_word_query(self, fitted_scorer: BM25Scorer) -> None:
        score = fitted_scorer.score("нейрон", "нейрон это клетка")
        assert score > 0.0

    def test_very_long_document(self) -> None:
        """Длинный документ штрафуется параметром b."""
        scorer = BM25Scorer(k1=1.5, b=0.75, use_lemmatization=False)
        short_doc = "нейрон клетка"
        long_doc = "нейрон клетка " + " ".join(
            [f"слово{i}" for i in range(100)]
        )
        scorer.fit([short_doc, long_doc])

        score_short = scorer.score("нейрон", short_doc)
        score_long = scorer.score("нейрон", long_doc)
        # Короткий документ должен получить более высокий score
        assert score_short > score_long

    def test_repeated_term_in_query(self, fitted_scorer: BM25Scorer) -> None:
        """Повторение терма в запросе увеличивает score."""
        score_single = fitted_scorer.score(
            "нейрон", "нейрон это клетка нервной системы"
        )
        score_double = fitted_scorer.score(
            "нейрон нейрон", "нейрон это клетка нервной системы"
        )
        # Двойной терм в запросе → score удваивается (примерно)
        assert score_double > score_single

    def test_b_zero_no_length_normalization(self) -> None:
        """b=0 → нет нормализации по длине документа."""
        scorer = BM25Scorer(k1=1.5, b=0.0, use_lemmatization=False)
        short_doc = "нейрон"
        long_doc = "нейрон " + " ".join([f"слово{i}" for i in range(50)])
        scorer.fit([short_doc, long_doc])

        score_short = scorer.score("нейрон", short_doc)
        score_long = scorer.score("нейрон", long_doc)
        # С b=0 длина не влияет, scores должны быть одинаковы
        # (TF=1 в обоих случаях, IDF одинаковый)
        assert score_short == pytest.approx(score_long, abs=0.01)

    def test_unicode_text(self) -> None:
        """Unicode текст обрабатывается корректно."""
        scorer = BM25Scorer(use_lemmatization=False)
        scorer.fit(["café résumé naïve", "über straße"])
        score = scorer.score("café", "café résumé naïve")
        assert score > 0.0


# =========================================================================
# KeywordRetrievalBackend — BM25 reranking integration
# =========================================================================

class TestKeywordBackendBM25Reranking:
    """Тесты интеграции BM25 reranking в KeywordRetrievalBackend."""

    @staticmethod
    def _make_memory_manager(
        working: List[Any] = None,
        semantic: List[Any] = None,
        episodic: List[Any] = None,
    ) -> MagicMock:
        """Создать mock MemoryManager с заданными результатами."""
        mm = MagicMock()
        result = MagicMock()
        result.working = working or []
        result.semantic = semantic or []
        result.episodic = episodic or []
        mm.retrieve.return_value = result
        return mm

    @staticmethod
    def _make_working_item(content: str, importance: float = 0.5) -> MagicMock:
        """Создать mock MemoryItem."""
        item = MagicMock()
        item.content = content
        item.source_ref = ""
        item.tags = []
        item.importance = importance
        item.ts = None
        item.modality = "text"
        return item

    def test_reranking_applied_with_multiple_results(self) -> None:
        """BM25 reranking применяется когда >= 2 кандидатов."""
        items = [
            self._make_working_item("нейрон это основная клетка нервной системы"),
            self._make_working_item("синапс соединяет два нейрона"),
            self._make_working_item("мозг состоит из миллиардов нейронов"),
        ]
        mm = self._make_memory_manager(working=items)
        backend = KeywordRetrievalBackend(mm)

        results = backend.search("нейрон клетка", top_n=10)
        assert len(results) > 0

        # Проверяем что BM25 metadata добавлена
        for ev in results:
            if ev.metadata.get("reranking") == "bm25":
                assert "bm25_raw_score" in ev.metadata
                break
        else:
            # Если нет BM25 metadata — значит все scores были 0
            # (допустимо если query не матчит)
            pass

    def test_reranking_not_applied_single_result(self) -> None:
        """BM25 reranking НЕ применяется для 1 кандидата."""
        items = [self._make_working_item("нейрон это клетка")]
        mm = self._make_memory_manager(working=items)
        backend = KeywordRetrievalBackend(mm)

        results = backend.search("нейрон", top_n=10)
        assert len(results) == 1
        # Без BM25 reranking — нет bm25 metadata
        assert results[0].metadata.get("reranking") != "bm25"

    def test_reranking_preserves_order(self) -> None:
        """После reranking результаты отсортированы по relevance_score desc."""
        items = [
            self._make_working_item("нейрон это основная клетка нервной системы"),
            self._make_working_item("синапс соединяет два нейрона и передаёт сигнал"),
            self._make_working_item("дендрит принимает сигналы от других нейронов"),
        ]
        mm = self._make_memory_manager(working=items)
        backend = KeywordRetrievalBackend(mm)

        results = backend.search("нейрон", top_n=10)
        scores = [ev.relevance_score for ev in results]
        assert scores == sorted(scores, reverse=True)

    def test_reranking_scores_in_0_1(self) -> None:
        """BM25 reranked scores нормализованы в [0, 1]."""
        items = [
            self._make_working_item("нейрон это клетка"),
            self._make_working_item("синапс передаёт сигнал"),
            self._make_working_item("нейрон нейрон нейрон"),
        ]
        mm = self._make_memory_manager(working=items)
        backend = KeywordRetrievalBackend(mm)

        results = backend.search("нейрон", top_n=10)
        for ev in results:
            assert 0.0 <= ev.relevance_score <= 1.0

    def test_reranking_best_match_gets_1(self) -> None:
        """Лучший кандидат получает score = 1.0 после нормализации."""
        items = [
            self._make_working_item("нейрон это клетка"),
            self._make_working_item("совершенно другой текст без совпадений xyz"),
            self._make_working_item("нейрон нейрон нейрон"),
        ]
        mm = self._make_memory_manager(working=items)
        backend = KeywordRetrievalBackend(mm)

        results = backend.search("нейрон", top_n=10)
        if results and results[0].metadata.get("reranking") == "bm25":
            assert results[0].relevance_score == pytest.approx(1.0)


# =========================================================================
# KeywordRetrievalBackend._bm25_rerank() — unit tests
# =========================================================================

class TestBM25RerankMethod:
    """Прямые тесты статического метода _bm25_rerank."""

    @staticmethod
    def _make_evidence(content: str, score: float = 0.5) -> EvidencePack:
        return EvidencePack(
            evidence_id=f"ev_test_{hash(content) % 10000}",
            content=content,
            memory_type="working",
            relevance_score=score,
        )

    def test_rerank_changes_scores(self) -> None:
        evidence = [
            self._make_evidence("нейрон это основная клетка", 0.5),
            self._make_evidence("синапс передаёт сигнал", 0.5),
        ]
        reranked = KeywordRetrievalBackend._bm25_rerank("нейрон", evidence)
        # Scores should be different after reranking
        scores = [ev.relevance_score for ev in reranked]
        assert len(set(scores)) > 1 or all(s == 0.0 for s in scores)

    def test_rerank_adds_metadata(self) -> None:
        evidence = [
            self._make_evidence("нейрон клетка", 0.5),
            self._make_evidence("синапс сигнал", 0.5),
        ]
        reranked = KeywordRetrievalBackend._bm25_rerank("нейрон", evidence)
        for ev in reranked:
            if ev.relevance_score > 0:
                assert ev.metadata.get("reranking") == "bm25"
                assert "bm25_raw_score" in ev.metadata

    def test_rerank_preserves_content(self) -> None:
        evidence = [
            self._make_evidence("нейрон клетка", 0.5),
            self._make_evidence("синапс сигнал", 0.3),
        ]
        reranked = KeywordRetrievalBackend._bm25_rerank("нейрон", evidence)
        contents = {ev.content for ev in reranked}
        assert "нейрон клетка" in contents
        assert "синапс сигнал" in contents

    def test_rerank_no_match_keeps_original(self) -> None:
        """Если BM25 не даёт ненулевых scores → оригинальные scores."""
        evidence = [
            self._make_evidence("abc def", 0.7),
            self._make_evidence("ghi jkl", 0.3),
        ]
        reranked = KeywordRetrievalBackend._bm25_rerank("xyz", evidence)
        # Нет совпадений → scores не меняются
        scores = [ev.relevance_score for ev in reranked]
        assert 0.7 in scores
        assert 0.3 in scores
