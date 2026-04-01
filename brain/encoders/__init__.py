"""
encoders — Модальные энкодеры (перевод сырых данных в векторы).

Реализовано (Этап E):
    text_encoder.py     — TextEncoder (sentence-transformers 768d, fallback: navec 300d)

Реализовано (Этап J — Multimodal Expansion):
    vision_encoder.py   — VisionEncoder (CLIP ViT-B/32, 512d)
    audio_encoder.py    — AudioEncoder (Whisper encoder features, dynamic dim)
    temporal_encoder.py — TemporalEncoder (CLIP mean-pool по кадрам, 512d)
    encoder_router.py   — EncoderRouter (маршрутизация по modality)
"""

from brain.encoders.text_encoder import TextEncoder
from brain.encoders.vision_encoder import VisionEncoder
from brain.encoders.audio_encoder import AudioEncoder
from brain.encoders.temporal_encoder import TemporalEncoder
from brain.encoders.encoder_router import EncoderRouter

__all__ = [
    "TextEncoder",
    "VisionEncoder",
    "AudioEncoder",
    "TemporalEncoder",
    "EncoderRouter",
]
