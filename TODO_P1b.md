# P1b: BM25 Reranking for Keyword Retrieval Candidates

> **Scope**: BM25-based reranking в KeywordRetrievalBackend.
> **НЕ** full retrieval replacement, **НЕ** изменение VectorRetrievalBackend.

## Задачи

- [x] **P1b.1** — `BM25Scorer` класс в `brain/cognition/retrieval_adapter.py` ✅
  - `__init__(k1=1.5, b=0.75)`
  - `fit(documents: List[str])` — построить IDF на кандидатах
  - `score(query: str, document: str) -> float`
  - `score_batch(query: str, documents: List[str]) -> List[float]`
  - `_tokenize(text: str) -> List[str]` — optional pymorphy3 лемматизация
  - Graceful fallback без лемматизации

- [x] **P1b.2** — Интеграция в `KeywordRetrievalBackend` ✅
  - `_bm25_rerank()` static method: fit → score_batch → normalize → update metadata
  - Активируется при `len(evidence) >= 2`
  - Fallback: если fit не вызван или 0 кандидатов → старый overlap

- [x] **P1b.3** — `tests/test_bm25.py` (55 тестов) ✅
  - 9 test classes: Init, Fit, IDF, Score, Batch, Fallback, Tokenize, OverlapFallback, EdgeCases
  - + TestKeywordBackendBM25Reranking (5), TestBM25RerankMethod (4)

- [x] **P1b.4** — `brain/cognition/__init__.py` — экспорт `BM25Scorer` ✅

- [x] **P1b.5** — Обновить docs/TODO.md (P1.1 done, 715 тестов) ✅

- [x] **Финал** — 715/715 тестов PASSED ✅ (1 flaky resource_monitor — зависит от реальной нагрузки)

## НЕ делаем в этом этапе

- ❌ Не трогаем `VectorRetrievalBackend._compute_text_relevance()`
- ❌ Не меняем зависимости в pyproject.toml (pymorphy3 уже в [nlp])
- ❌ Не обещаем full retrieval — только reranking improvement
