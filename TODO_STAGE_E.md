# TODO Stage E — Minimal Text Encoder

> **Версия:** v1 (2026-03-24)
> **Цель:** `brain/encoders/text_encoder.py` — первый encoder, text-only, CPU-only
> **Оценка:** ~2–3 часа реализации + тесты

---

## Принятые решения (из ревью)

1. **API:** основной путь — `encode_event(PerceptEvent) → EncodedPercept`, wrapper `encode(text, ...) → EncodedPercept`
2. **EncodedPercept расширение — минимальное**, только top-level:
   - `language: str = ""`
   - `message_type: str = "unknown"`
   - `encoder_model: str = ""`
   - `vector_dim: int = 0`
   - Остальное (keywords, sentiment, encoding_time_ms, warnings) → в `metadata`
3. **Navec fallback формализован:**
   - токенизация → векторы известных токенов → mean pooling → L2 norm
   - ни один токен не найден → нулевой вектор + warning
   - размер fallback-вектора фиксирован (300d) и проверяется тестом
4. **Graceful degradation — 4 статуса** в `metadata["encoder_status"]`:
   - `"ok"` — sentence-transformers работает
   - `"fallback"` — navec используется
   - `"degraded"` — частичный результат (мало токенов и т.п.)
   - `"failed"` — пустой вектор, ничего не сработало
   - `metadata["warnings"]` — список предупреждений
5. **Тесты включают семантический sanity-check:**
   - одинаковые тексты → одинаковый вектор (epsilon)
   - парафразы → cosine similarity выше, чем несвязанные
   - batch vs single → совместимые результаты
   - fallback покрыт отдельно (mock отсутствия sentence-transformers)
6. **sentiment — НЕ делаем** в этапе E (оставить `"unknown"`)
7. **message_type — эвристики:** `?` → question, императив → command, иначе statement
8. **keywords — MVP:** regex/token filter, убрать стоп-слова, top-N

---

## Шаги реализации

### Шаг 1: ✅ Расширить `EncodedPercept` в contracts.py
- [x] Добавить 4 поля с defaults: `language`, `message_type`, `encoder_model`, `vector_dim`
- [x] Убедиться: все 229 старых тестов проходят (обратная совместимость)

### Шаг 2: ✅ Реализовать `brain/encoders/text_encoder.py`
- [x] Класс `TextEncoder(model_name=..., fallback=True)`
- [x] `__init__`: попытка загрузить sentence-transformers, при неудаче → navec, при неудаче → degraded mode
- [x] `encode_event(percept: PerceptEvent) → EncodedPercept` — основной API
- [x] `encode(text: str, source="user_input", quality=1.0, ...) → EncodedPercept` — wrapper
- [x] `encode_batch(percepts: List[PerceptEvent]) → List[EncodedPercept]`
- [x] L2-нормализация вектора
- [x] Keywords extraction (MVP: token filter + стоп-слова + top-N)
- [x] Language detection (простая эвристика кириллица/латиница)
- [x] Message type detection (? → question, императив → command, иначе statement)
- [x] In-memory кэш по SHA256(text)
- [x] `metadata["encoder_status"]` = ok/fallback/degraded/failed
- [x] `metadata["warnings"]` = список предупреждений
- [x] `metadata["encoding_time_ms"]` = замер времени
- [x] `metadata["keywords"]` = список ключевых слов

### Шаг 3: ✅ Navec fallback path
- [x] Загрузка navec модели
- [x] Токенизация (regex split)
- [x] Lookup токенов → mean pooling → L2 norm
- [x] Нет токенов → нулевой вектор 300d + warning
- [x] vector_dim = 300 для fallback

### Шаг 4: ✅ Обновить `brain/encoders/__init__.py`
- [x] Экспортировать `TextEncoder`

### Шаг 5: ✅ Тесты `tests/test_text_encoder.py` — 80/80 passed
- [x] Импорт и создание экземпляра
- [x] encode_event(PerceptEvent) → EncodedPercept
- [x] encode(str) → EncodedPercept (wrapper)
- [x] Вектор правильной размерности (768d или 300d fallback)
- [x] L2-нормализация (norm ≈ 1.0, epsilon=1e-4)
- [x] Пустой текст → graceful handling (encoder_status="failed")
- [x] Два одинаковых текста → одинаковый вектор (epsilon)
- [x] Разные тексты → разные векторы
- [x] Batch и single encode → совместимые результаты
- [x] Keywords в metadata
- [x] Language detection
- [x] Message type detection
- [x] encoding_time_ms > 0
- [x] encoder_status в metadata
- [x] Fallback path (mock navec)
- [x] Fallback vector_dim = 300
- [x] Кэш: store/hit/clear
- [x] Все 229 старых тестов не сломаны

### Шаг 6: ✅ Финальная проверка
- [x] `pytest tests/ -v` — 309/309 passed (4.04s)
- [ ] Коммит + push

---

## Что НЕ входит в Этап E

- VisionEncoder, AudioEncoder, TemporalEncoder
- EmbeddingCache на диске
- Vector index / retrieval
- Cross-Modal Fusion
- sentiment analysis
- Сложная NLP-классификация message_type
