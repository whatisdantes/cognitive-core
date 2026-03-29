# ADR-007: CPU-only платформа (без GPU)

**Статус:** ✅ Принято  
**Дата:** 2025-03  
**Авторы:** cognitive-core contributors

---

## Контекст

Проект разрабатывается на конкретном железе: **AMD Ryzen 7 5700X, 32 GB DDR4** — без дискретного GPU. Нужно определить стратегию для компонентов, которые традиционно требуют GPU (text encoder, vector search, LLM inference).

## Рассмотренные варианты

### Вариант 1: GPU-first (CUDA)
**Плюсы:** Максимальная производительность для embeddings и LLM  
**Минусы:** Недоступно на целевом железе; усложняет CI (нет GPU в GitHub Actions)

### Вариант 2: CPU-only с graceful degradation
**Плюсы:** Работает на любом железе; CI без GPU; постепенное добавление GPU-поддержки  
**Минусы:** Медленнее для тяжёлых моделей

### Вариант 3: Cloud API (OpenAI embeddings, Cohere)
**Плюсы:** Качественные embeddings без GPU  
**Минусы:** Внешняя зависимость, стоимость, latency, нет offline-режима

## Решение

Выбрана **CPU-only платформа** с многоуровневым graceful degradation для encoder.

Иерархия fallback в `brain/encoders/text_encoder.py`:

```
Уровень 1: sentence-transformers (768d)
    ↓ если не установлен
Уровень 2: navec (300d, русский язык)
    ↓ если не установлен
Уровень 3: TF-IDF (sparse, sklearn)
    ↓ если не установлен
Уровень 4: hash-based (детерминированный, нет зависимостей)
```

Для vector search: **numpy cosine similarity** вместо FAISS/HNSW:

```python
# O(n) поиск — приемлемо для корпуса < 100K документов
similarities = np.dot(matrix, query_vec) / (
    np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vec) + 1e-8
)
```

## Последствия

**Положительные:**
- Работает на любом железе без GPU
- CI в GitHub Actions без специальных runner'ов
- Нет зависимости от CUDA/cuDNN версий
- Graceful degradation — система работает даже без NLP-зависимостей

**Отрицательные:**
- sentence-transformers на CPU: ~50–200ms на encode (vs ~5ms на GPU)
- numpy vector search: O(n) — при корпусе >100K документов станет узким местом
- Нет поддержки тяжёлых local LLM (Llama 70B требует GPU)

**Нейтральные:**
- CUDA Backend запланирован как отдельный этап (после понимания bottlenecks)
- Абстракция `TextEncoderProtocol` позволит добавить GPU-backend без изменения интерфейса

## Путь к CUDA Backend

```
brain/encoders/
├── text_encoder.py          — текущий CPU encoder
├── cpu_backend.py           — явный CPU backend (рефакторинг)
└── cuda_backend.py          — будущий CUDA backend

Приоритет: text encoder → embeddings → reranker → local LLM inference
```

## Связанные решения

- ADR-004: BM25 + Vector Hybrid — numpy вместо FAISS из-за CPU-only
- ADR-005: Шаблонные ответы — LLM отложен из-за CPU-only
- TODO.md: CUDA Backend (после понимания bottlenecks)
