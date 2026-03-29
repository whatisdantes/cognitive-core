# brain.perception — Слой восприятия

Маршрутизация и нормализация входных данных. Аналог сенсорной коры.

---

## InputRouter

Маршрутизатор входных данных: определяет тип (текст/файл/URL) и направляет к нужному ингестору.

::: brain.perception.input_router.InputRouter
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - route
        - status

---

## TextIngestor

Ингестор текстовых данных: нормализация, чанкинг, извлечение метаданных.

::: brain.perception.text_ingestor.TextIngestor
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - ingest
        - chunk_text

---

## MetadataExtractor

Извлечение метаданных из входных данных (язык, тип контента, источник).

::: brain.perception.metadata_extractor.MetadataExtractor
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## Validators

Валидация входных данных перед обработкой.

::: brain.perception.validators
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
