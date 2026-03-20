"""
encoders — Модальные энкодеры (перевод сырых данных в векторы).

Модули:
    text_encoder.py     — sentence-transformers large (768d/1024d), fallback: navec
    vision_encoder.py   — CLIP ViT-B/32 (512d), fallback: ResNet-50
    audio_encoder.py    — Whisper medium + MFCC, fallback: Whisper base
    temporal_encoder.py — позиционное кодирование последовательностей (видео)
"""
