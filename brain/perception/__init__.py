"""
perception — Слой восприятия (аналог сенсорики).

Модули:
    text_ingestor.py    — парсинг txt/md/pdf/docx/json → PerceptEvent
    vision_ingestor.py  — загрузка изображений + OCR → PerceptEvent
    audio_ingestor.py   — ASR + временные метки → PerceptEvent
    metadata_extractor.py — извлечение source/timestamp/quality/language
    input_router.py     — маршрутизация входящих данных (аналог Таламуса)
"""
