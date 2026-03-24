"""
encoders — Модальные энкодеры (перевод сырых данных в векторы).

Реализовано:
    text_encoder.py     — TextEncoder (sentence-transformers 768d, fallback: navec 300d)

Планируется:
    vision_encoder.py   — CLIP ViT-B/32 (512d)
    audio_encoder.py    — Whisper medium + TextEncoder
    temporal_encoder.py — позиционное кодирование последовательностей (видео)
"""

from brain.encoders.text_encoder import TextEncoder

__all__ = [
    "TextEncoder",
]
