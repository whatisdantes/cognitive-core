# brain.encoders — Кодировщики модальностей

Преобразование входных данных в векторные представления. Аналог сенсорных кортексов.

---

## TextEncoder

Кодировщик текста с 4 режимами работы:

| Режим | Описание | Зависимости |
|-------|----------|-------------|
| `tfidf` | TF-IDF на основе словаря | встроен |
| `hash` | Feature hashing (MurmurHash) | встроен |
| `navec` | Предобученные русские эмбеддинги | `navec` |
| `sentence_transformers` | Многоязычные трансформеры | `sentence-transformers` |

::: brain.encoders.text_encoder.TextEncoder
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - encode
        - encode_batch
        - mode
        - vector_dim
        - status

### Пример использования

```python
from brain.encoders.text_encoder import TextEncoder

# Режим по умолчанию (tfidf — без внешних зависимостей)
encoder = TextEncoder(mode="tfidf")
result = encoder.encode("что такое нейрон?")
print(result.vector[:5])   # [0.12, 0.0, 0.34, ...]
print(result.mode)         # "tfidf"

# Режим hash (детерминированный, без обучения)
encoder = TextEncoder(mode="hash", vector_dim=256)
result = encoder.encode("нейрон — базовая единица нервной системы")

# Режим navec (русские эмбеддинги, требует pip install cognitive-core[nlp])
encoder = TextEncoder(mode="navec", navec_path="navec_hudlit_v1_12B.tar")
result = encoder.encode("нейрон")
print(len(result.vector))  # 300
```

### EncodedPercept

Результат кодирования.

::: brain.core.contracts.EncodedPercept
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
