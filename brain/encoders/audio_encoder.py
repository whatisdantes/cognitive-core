"""
brain/encoders/audio_encoder.py — Энкодер аудио (J.4).

Whisper encoder features → dynamic output_dim (по умолчанию 768, совпадает с TextEncoder).
Без проекции — вектор берётся из encoder_hidden_states Whisper.

Fallback-цепочка:
  Whisper → output_dim вектор L2-нормализованный, status="ok"
  no Whisper → zeros(output_dim), status="degraded"
  ошибка → zeros(output_dim), status="failed"

Использование:
    enc = AudioEncoder(output_dim=768)
    result = enc.encode("speech.wav")
    # result.modality == Modality.AUDIO
    # result.vector   — список из output_dim float
    # result.vector_dim == 768
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import numpy as np

from brain.core.contracts import EncodedPercept, Modality

logger = logging.getLogger(__name__)

# ─── Опциональные зависимости ────────────────────────────────────────────────

try:
    import whisper as _whisper  # type: ignore[import-untyped]
    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False
    logger.debug("openai-whisper не установлен — AudioEncoder работает в degraded режиме")

# ─── Константы ───────────────────────────────────────────────────────────────

_DEFAULT_OUTPUT_DIM: int = 768   # совпадает с TextEncoder (multilingual-mpnet)
_DEFAULT_WHISPER_MODEL = "tiny"
_DEVICE = "cpu"                  # ADR-007: cpu-only


# ─── Вспомогательные функции (мокируемые в тестах) ───────────────────────────

def _load_whisper_model(model_name: str) -> Any:
    """Загрузить Whisper модель. Мокируется в тестах."""
    return _whisper.load_model(model_name)


def _encode_audio_whisper(file_path: str, model: Any, output_dim: int) -> np.ndarray:
    """
    Закодировать аудио через Whisper encoder features. Мокируется в тестах.

    Возвращает L2-нормализованный numpy вектор (output_dim).
    Если Whisper не возвращает encoder_hidden_states — используем mean-pool
    из log-mel spectrogram через model.embed_audio().
    """
    # Получаем log-mel spectrogram
    audio = _whisper.load_audio(file_path)
    audio = _whisper.pad_or_trim(audio)
    mel = _whisper.log_mel_spectrogram(audio)

    # Encoder features через embed_audio (возвращает [1, T, D])
    import torch as _torch
    with _torch.no_grad():
        features = model.embed_audio(mel.unsqueeze(0))  # [1, T, D]

    # Mean-pool по временной оси → [D]
    vec = features.squeeze(0).mean(dim=0).cpu().numpy().astype(np.float32)

    # Проекция/обрезка до output_dim
    if len(vec) > output_dim:
        vec = vec[:output_dim]
    elif len(vec) < output_dim:
        vec = np.pad(vec, (0, output_dim - len(vec)))

    # L2-нормализация
    norm = float(np.linalg.norm(vec))
    if norm > 1e-12:
        vec = vec / norm
    return cast(np.ndarray, vec)


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    """L2-нормализация вектора."""
    norm = float(np.linalg.norm(vec))
    if norm < 1e-12:
        return vec
    result: np.ndarray = vec / norm  # type: ignore[assignment]
    return result


# ─── AudioEncoder ────────────────────────────────────────────────────────────

class AudioEncoder:
    """
    Кодирует аудиофайлы в вектор через Whisper encoder features.

    Параметры:
        output_dim:  размерность выходного вектора (default: 768)
        model_name:  имя модели Whisper (default: "tiny")
        device:      устройство (default: "cpu", ADR-007)
    """

    def __init__(
        self,
        output_dim: int = _DEFAULT_OUTPUT_DIM,
        model_name: str = _DEFAULT_WHISPER_MODEL,
        device: str = _DEVICE,
    ) -> None:
        self._output_dim = output_dim
        self._model_name = model_name
        self._device = device
        self._whisper_model: Optional[Any] = None

    @property
    def vector_dim(self) -> int:
        """Размерность выходного вектора."""
        return self._output_dim

    def _load_model(self) -> bool:
        """Ленивая загрузка Whisper модели. Возвращает True при успехе."""
        if self._whisper_model is not None:
            return True
        if not _WHISPER_AVAILABLE:
            return False
        try:
            self._whisper_model = _load_whisper_model(self._model_name)
            return True
        except Exception as exc:
            logger.warning("AudioEncoder: не удалось загрузить Whisper: %s", exc)
            return False

    def encode(
        self,
        audio_path: str,
        source: str = "",
        trace_id: str = "",
        session_id: str = "",
        cycle_id: str = "",
    ) -> EncodedPercept:
        """
        Закодировать аудиофайл → EncodedPercept(modality=AUDIO, vector=output_dim).

        При любой ошибке возвращает zeros(output_dim) с соответствующим статусом.
        """
        t0 = time.perf_counter()
        percept_id = f"aud_{uuid.uuid4().hex[:8]}"
        effective_source = source or audio_path

        # Проверка пути
        if not audio_path or not Path(audio_path).exists():
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(self._output_dim, dtype=np.float32),
                status="failed",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=["file not found or empty path"],
            )

        # Whisper недоступен → degraded
        if not _WHISPER_AVAILABLE:
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(self._output_dim, dtype=np.float32),
                status="degraded",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=["Whisper not available, returning zeros"],
            )

        # Загрузка модели
        if not self._load_model():
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(self._output_dim, dtype=np.float32),
                status="degraded",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=["Whisper model load failed"],
            )

        # Кодирование
        try:
            vec = _encode_audio_whisper(audio_path, self._whisper_model, self._output_dim)
            vec = _l2_normalize(vec)
        except Exception as exc:
            logger.warning("AudioEncoder: Whisper ошибка для '%s': %s", audio_path, exc)
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(self._output_dim, dtype=np.float32),
                status="failed",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=[f"Whisper encode error: {exc}"],
            )

        return self._make_result(
            percept_id=percept_id,
            vector=vec,
            status="ok",
            source=effective_source,
            trace_id=trace_id,
            session_id=session_id,
            cycle_id=cycle_id,
            t0=t0,
            warnings=[],
        )

    def _make_result(
        self,
        percept_id: str,
        vector: np.ndarray,
        status: str,
        source: str,
        trace_id: str,
        session_id: str,
        cycle_id: str,
        t0: float,
        warnings: List[str],
    ) -> EncodedPercept:
        """Собрать EncodedPercept из компонентов."""
        encoding_time_ms = (time.perf_counter() - t0) * 1000.0
        vec_list: List[float] = vector.tolist()
        return EncodedPercept(
            percept_id=percept_id,
            modality=Modality.AUDIO,
            vector=vec_list,
            text="",
            quality=1.0 if status == "ok" else 0.0,
            source=source,
            language="unknown",
            message_type="audio",
            encoder_model=self._model_name,
            vector_dim=self._output_dim,
            metadata={
                "encoder_status": status,
                "warnings": warnings,
                "encoding_time_ms": round(encoding_time_ms, 3),
                "whisper_available": _WHISPER_AVAILABLE,
                "output_dim": self._output_dim,
            },
            trace_id=trace_id,
            session_id=session_id,
            cycle_id=cycle_id,
        )

    def status(self) -> Dict[str, Any]:
        """Статус энкодера."""
        return {
            "model_name": self._model_name,
            "device": self._device,
            "vector_dim": self._output_dim,
            "whisper_available": _WHISPER_AVAILABLE,
            "model_loaded": self._whisper_model is not None,
        }

    def __repr__(self) -> str:
        return (
            f"AudioEncoder("
            f"output_dim={self._output_dim}, "
            f"model={self._model_name!r}, "
            f"whisper={_WHISPER_AVAILABLE})"
        )
