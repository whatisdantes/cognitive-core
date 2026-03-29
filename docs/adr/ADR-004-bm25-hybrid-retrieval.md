# ADR-004: BM25 + Vector Hybrid Retrieval с RRF

**Статус:** ✅ Принято  
**Дата:** 2025-06  
**Авторы:** cognitive-core contributors

---

## Контекст

Система памяти должна находить релевантные факты и эпизоды по текстовому запросу. Изначально retrieval был «декоративным» — возвращал случайные результаты без реального ранжирования. Это был центральный продуктовый дефект (P0-P1).

Требования:
- CPU-only (нет GPU для тяжёлых моделей)
- Работа без внешних сервисов (нет Elasticsearch, Pinecone)
- Поддержка русского языка
- Graceful degradation при отсутствии NLP-зависимостей

## Рассмотренные варианты

### Вариант 1: Только keyword search (TF-IDF / BM25)
**Плюсы:** Быстро, нет зависимостей, хорошо для точных совпадений  
**Минусы:** Не улавливает семантическую близость («нейрон» ≠ «клетка мозга»)

### Вариант 2: Только vector search (sentence-transformers)
**Плюсы:** Семантическое понимание, работает с перефразировками  
**Минусы:** Медленнее на CPU, требует sentence-transformers, плохо для точных терминов

### Вариант 3: Hybrid (BM25 + Vector) с Reciprocal Rank Fusion (RRF)
**Плюсы:** Лучшее из обоих миров; RRF — простое и эффективное слияние рангов; graceful degradation (если нет embeddings — только BM25)  
**Минусы:** Сложнее реализация; два индекса вместо одного

### Вариант 4: Elasticsearch / OpenSearch
**Плюсы:** Production-ready, встроенный BM25 + kNN  
**Минусы:** Внешний сервис, Docker dependency, избыточность для CPU-only MVP

## Решение

Выбран **Hybrid Retrieval (BM25 + Vector) с RRF**.

Архитектура в `brain/cognition/retrieval_adapter.py`:

```
RetrievalAdapter
├── KeywordRetrievalBackend  — BM25 через BM25Scorer
│   ├── BM25Scorer.fit(corpus)
│   ├── BM25Scorer.score(query, doc)
│   └── pymorphy3 лемматизация (optional, graceful fallback)
├── VectorRetrievalBackend   — cosine similarity через numpy
│   ├── _build_vector_index() при init
│   ├── incremental indexing при LEARN
│   └── remove_from_vector_index() при deny/delete
└── HybridRetrievalBackend   — RRF слияние
    └── rrf_score = Σ 1/(k + rank_i), k=60
```

BM25 параметры: `k1=1.5, b=0.75` (стандартные Okapi BM25).

RRF формула:
```python
def _rrf_score(ranks: List[int], k: int = 60) -> float:
    return sum(1.0 / (k + r) for r in ranks)
```

## Последствия

**Положительные:**
- Реальный retrieval — система находит релевантные факты
- Graceful degradation: без sentence-transformers работает только BM25
- Инкрементальная индексация — новые факты сразу доступны для поиска
- Персистенция embeddings в `to_dict()/from_dict()` — нет пересчёта при перезапуске

**Отрицательные:**
- Два индекса в памяти (BM25 corpus + vector matrix)
- При большом корпусе (>100K документов) numpy cosine similarity станет узким местом
- Нет HNSW/IVF индекса — O(n) поиск по вектору

**Нейтральные:**
- `pymorphy3` опционален — без него BM25 работает на lower+split токенизации
- 60 тестов в `test_vector_retrieval.py` покрывают все сценарии

## Связанные решения

- ADR-001: SQLite хранит embeddings в JSON-поле
- ADR-007: CPU-only платформа определяет выбор numpy вместо FAISS/CUDA
