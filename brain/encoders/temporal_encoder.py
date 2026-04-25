"""
brain/encoders/temporal_encoder.py — Энкодер видео (J.5).

Стратегия: cv2 → извлечение кадров → CLIP ViT-B/32 → mean-pool → 512d вектор.
Совместимо с VisionEncoder (одно пространство CLIP 512d).

Fallback-цепочка:
  cv2 + CLIP → 512d L2-нормализованный mean-pool, status="ok"
  cv2 only   → zeros(512d), status="degraded"
  no cv2     → zeros(512d), status="failed"
  no frames  → zeros(512d), status="failed"

Использование:
    enc = TemporalEncoder()
    result = enc.encode("video.mp4")
    # result.modality == Modality.VIDEO
    # result.vector   — список из 512 float (mean-pool по кадрам)
    # result.vector_dim == 512
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
    import cv2 as _cv2  # type: ignore[import-untyped]
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False
    logger.debug("opencv-python не установлен — TemporalEncoder работает в degraded режиме")

try:
    import clip as _clip  # type: ignore[import-untyped]
    import torch as _torch  # type: ignore[import-untyped]
    _CLIP_AVAILABLE = True
except ImportError:
    _CLIP_AVAILABLE = False
    logger.debug("CLIP/torch не установлен — TemporalEncoder работает в degraded режиме")

try:
    from PIL import Image as _PILImage  # type: ignore[import-untyped]
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

# ─── Константы ───────────────────────────────────────────────────────────────

PRIMARY_DIM: int = 512          # CLIP ViT-B/32 output dimension
_CLIP_MODEL_NAME = "ViT-B/32"
_DEVICE = "cpu"                 # ADR-007: cpu-only
_DEFAULT_MAX_FRAMES = 8         # максимальное количество кадров для mean-pool
_DEFAULT_FRAME_STEP = 30        # шаг между кадрами (в кадрах)


# ─── Вспомогательные функции (мокируемые в тестах) ───────────────────────────

def _extract_frames(
    video_path: str,
    max_frames: int = _DEFAULT_MAX_FRAMES,
    frame_step: int = _DEFAULT_FRAME_STEP,
) -> List[Any]:
    """
    Извлечь кадры из видео через cv2. Мокируется в тестах.

    Возвращает список PIL Image объектов (или numpy arrays).
    """
    cap = _cv2.VideoCapture(video_path)
    frames: List[Any] = []
    frame_idx = 0
    extracted = 0

    while cap.isOpened() and extracted < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_step == 0:
            # BGR → RGB → PIL Image
            if _PIL_AVAILABLE:
                rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
                pil_img = _PILImage.fromarray(rgb)
                frames.append(pil_img)
            else:
                frames.append(frame)
            extracted += 1
        frame_idx += 1

    cap.release()
    return frames


def _load_clip_model(model_name: str, device: str) -> tuple:  # type: ignore[type-arg]
    """Загрузить CLIP модель и препроцессор. Мокируется в тестах."""
    return _clip.load(model_name, device=device)  # type: ignore[return-value, no-any-return]


def _encode_frame_clip(frame: Any, model: Any, preprocess: Any) -> np.ndarray:
    """
    Закодировать один кадр через CLIP. Мокируется в тестах.

    Возвращает L2-нормализованный numpy вектор (512d).
    """
    tensor = preprocess(frame).unsqueeze(0).to(_DEVICE)
    with _torch.no_grad():
        features = model.encode_image(tensor)
    vec = features.cpu().numpy().flatten().astype(np.float32)
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


# ─── TemporalEncoder ─────────────────────────────────────────────────────────

class TemporalEncoder:
    """
    Кодирует видеофайлы в 512d вектор через mean-pool CLIP frame embeddings.

    Параметры:
        model_name:  имя CLIP модели (default: "ViT-B/32")
        device:      устройство (default: "cpu", ADR-007)
        max_frames:  максимальное количество кадров (default: 8)
        frame_step:  шаг между кадрами (default: 30)
    """

    def __init__(
        self,
        model_name: str = _CLIP_MODEL_NAME,
        device: str = _DEVICE,
        max_frames: int = _DEFAULT_MAX_FRAMES,
        frame_step: int = _DEFAULT_FRAME_STEP,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._max_frames = max_frames
        self._frame_step = frame_step
        self._clip_model: Optional[Any] = None
        self._clip_preprocess: Optional[Any] = None

    @property
    def vector_dim(self) -> int:
        """Размерность выходного вектора."""
        return PRIMARY_DIM

    def _load_clip(self) -> bool:
        """Ленивая загрузка CLIP модели. Возвращает True при успехе."""
        if self._clip_model is not None:
            return True
        if not _CLIP_AVAILABLE:
            return False
        try:
            self._clip_model, self._clip_preprocess = _load_clip_model(
                self._model_name, self._device
            )
            return True
        except Exception as exc:
            logger.warning("TemporalEncoder: не удалось загрузить CLIP: %s", exc)
            return False

    def encode(
        self,
        video_path: str,
        source: str = "",
        trace_id: str = "",
        session_id: str = "",
        cycle_id: str = "",
    ) -> EncodedPercept:
        """
        Закодировать видеофайл → EncodedPercept(modality=VIDEO, vector=512d).

        При любой ошибке возвращает zeros(512d) с соответствующим статусом.
        """
        t0 = time.perf_counter()
        percept_id = f"vid_{uuid.uuid4().hex[:8]}"
        effective_source = source or video_path

        # Проверка пути
        if not video_path or not Path(video_path).exists():
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(PRIMARY_DIM, dtype=np.float32),
                status="failed",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=["file not found or empty path"],
                frames_extracted=0,
            )

        # cv2 недоступен
        if not _CV2_AVAILABLE:
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(PRIMARY_DIM, dtype=np.float32),
                status="failed",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=["opencv-python not available"],
                frames_extracted=0,
            )

        # Извлечение кадров
        try:
            frames = _extract_frames(video_path, self._max_frames, self._frame_step)
        except Exception as exc:
            logger.warning("TemporalEncoder: ошибка извлечения кадров '%s': %s", video_path, exc)
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(PRIMARY_DIM, dtype=np.float32),
                status="failed",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=[f"frame extraction error: {exc}"],
                frames_extracted=0,
            )

        # Нет кадров
        if not frames:
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(PRIMARY_DIM, dtype=np.float32),
                status="failed",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=["no frames extracted from video"],
                frames_extracted=0,
            )

        # CLIP недоступен → degraded
        if not _CLIP_AVAILABLE:
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(PRIMARY_DIM, dtype=np.float32),
                status="degraded",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=["CLIP not available, returning zeros"],
                frames_extracted=len(frames),
            )

        # Загрузка CLIP
        if not self._load_clip():
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(PRIMARY_DIM, dtype=np.float32),
                status="degraded",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=["CLIP model load failed"],
                frames_extracted=len(frames),
            )

        # Кодирование кадров + mean-pool
        try:
            frame_vectors: List[np.ndarray] = []
            for frame in frames:
                vec = _encode_frame_clip(frame, self._clip_model, self._clip_preprocess)
                frame_vectors.append(vec)

            # Mean-pool по кадрам
            stacked = np.stack(frame_vectors, axis=0)  # [N, 512]
            mean_vec = stacked.mean(axis=0)             # [512]
            mean_vec = _l2_normalize(mean_vec)

        except Exception as exc:
            logger.warning("TemporalEncoder: CLIP ошибка для '%s': %s", video_path, exc)
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(PRIMARY_DIM, dtype=np.float32),
                status="failed",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=[f"CLIP encode error: {exc}"],
                frames_extracted=len(frames),
            )

        return self._make_result(
            percept_id=percept_id,
            vector=mean_vec,
            status="ok",
            source=effective_source,
            trace_id=trace_id,
            session_id=session_id,
            cycle_id=cycle_id,
            t0=t0,
            warnings=[],
            frames_extracted=len(frames),
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
        frames_extracted: int,
    ) -> EncodedPercept:
        """Собрать EncodedPercept из компонентов."""
        encoding_time_ms = (time.perf_counter() - t0) * 1000.0
        vec_list: List[float] = vector.tolist()
        return EncodedPercept(
            percept_id=percept_id,
            modality=Modality.VIDEO,
            vector=vec_list,
            text="",
            quality=1.0 if status == "ok" else 0.0,
            source=source,
            language="unknown",
            message_type="video",
            encoder_model=self._model_name,
            vector_dim=PRIMARY_DIM,
            metadata={
                "encoder_status": status,
                "warnings": warnings,
                "encoding_time_ms": round(encoding_time_ms, 3),
                "cv2_available": _CV2_AVAILABLE,
                "clip_available": _CLIP_AVAILABLE,
                "frames_extracted": frames_extracted,
                "max_frames": self._max_frames,
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
            "vector_dim": PRIMARY_DIM,
            "cv2_available": _CV2_AVAILABLE,
            "clip_available": _CLIP_AVAILABLE,
            "clip_loaded": self._clip_model is not None,
            "max_frames": self._max_frames,
            "frame_step": self._frame_step,
        }

    def __repr__(self) -> str:
        return (
            f"TemporalEncoder("
            f"model={self._model_name!r}, "
            f"cv2={_CV2_AVAILABLE}, "
            f"clip={_CLIP_AVAILABLE}, "
            f"max_frames={self._max_frames})"
        )
