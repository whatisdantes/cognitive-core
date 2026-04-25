"""
brain/encoders/vision_encoder.py — Энкодер изображений (J.3).

Стратегия A: CLIP ViT-B/32 → 512d вектор (без проекции).
Семантическое пространство CLIP сохраняется нетронутым.

Fallback-цепочка:
  CLIP + PIL → 512d L2-нормализованный вектор, status="ok"
  PIL only   → zeros(512d), status="degraded"
  no PIL     → zeros(512d), status="failed"

Использование:
    enc = VisionEncoder()
    result = enc.encode("photo.jpg")
    # result.modality == Modality.IMAGE
    # result.vector   — список из 512 float
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
    from PIL import Image as _PILImage  # type: ignore[import-untyped]
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.debug("Pillow не установлен — VisionEncoder работает в degraded режиме")

try:
    import clip as _clip  # type: ignore[import-untyped]
    import torch as _torch  # type: ignore[import-untyped]
    _CLIP_AVAILABLE = True
except ImportError:
    _CLIP_AVAILABLE = False
    logger.debug("CLIP/torch не установлен — VisionEncoder работает в degraded режиме")

# ─── Константы ───────────────────────────────────────────────────────────────

PRIMARY_DIM: int = 512          # CLIP ViT-B/32 output dimension
_CLIP_MODEL_NAME = "ViT-B/32"
_DEVICE = "cpu"                 # ADR-007: cpu-only


# ─── Вспомогательные функции (мокируемые в тестах) ───────────────────────────

def _open_image(path: str) -> Any:
    """Открыть изображение через PIL. Мокируется в тестах."""
    return _PILImage.open(path).convert("RGB")


def _load_clip_model(model_name: str, device: str) -> tuple:  # type: ignore[type-arg]
    """Загрузить CLIP модель и препроцессор. Мокируется в тестах."""
    return _clip.load(model_name, device=device)  # type: ignore[return-value, no-any-return]


def _encode_image_clip(image: Any, model: Any, preprocess: Any) -> np.ndarray:
    """
    Закодировать изображение через CLIP. Мокируется в тестах.

    Возвращает L2-нормализованный numpy вектор (512d).
    """
    tensor = preprocess(image).unsqueeze(0).to(_DEVICE)
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


# ─── VisionEncoder ───────────────────────────────────────────────────────────

class VisionEncoder:
    """
    Кодирует изображения в 512d вектор через CLIP ViT-B/32 (Strategy A).

    Параметры:
        model_name: имя CLIP модели (default: "ViT-B/32")
        device:     устройство (default: "cpu", ADR-007)
    """

    def __init__(
        self,
        model_name: str = _CLIP_MODEL_NAME,
        device: str = _DEVICE,
    ) -> None:
        self._model_name = model_name
        self._device = device
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
            logger.warning("VisionEncoder: не удалось загрузить CLIP: %s", exc)
            return False

    def encode(
        self,
        image_path: str,
        source: str = "",
        trace_id: str = "",
        session_id: str = "",
        cycle_id: str = "",
    ) -> EncodedPercept:
        """
        Закодировать изображение → EncodedPercept(modality=IMAGE, vector=512d).

        При любой ошибке возвращает zeros(512d) с соответствующим статусом.
        """
        t0 = time.perf_counter()
        percept_id = f"vis_{uuid.uuid4().hex[:8]}"
        effective_source = source or image_path

        # Проверка пути
        if not image_path or not Path(image_path).exists():
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
            )

        # PIL недоступен
        if not _PIL_AVAILABLE:
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(PRIMARY_DIM, dtype=np.float32),
                status="failed",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=["Pillow not available"],
            )

        # Открытие изображения
        try:
            image = _open_image(image_path)
        except Exception as exc:
            logger.warning("VisionEncoder: ошибка открытия '%s': %s", image_path, exc)
            return self._make_result(
                percept_id=percept_id,
                vector=np.zeros(PRIMARY_DIM, dtype=np.float32),
                status="failed",
                source=effective_source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                t0=t0,
                warnings=[f"PIL open error: {exc}"],
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
            )

        # CLIP кодирование
        try:
            vec = _encode_image_clip(image, self._clip_model, self._clip_preprocess)
            vec = _l2_normalize(vec)
        except Exception as exc:
            logger.warning("VisionEncoder: CLIP ошибка для '%s': %s", image_path, exc)
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
            modality=Modality.IMAGE,
            vector=vec_list,
            text="",
            quality=1.0 if status == "ok" else 0.0,
            source=source,
            language="unknown",
            message_type="image",
            encoder_model=self._model_name,
            vector_dim=PRIMARY_DIM,
            metadata={
                "encoder_status": status,
                "warnings": warnings,
                "encoding_time_ms": round(encoding_time_ms, 3),
                "pil_available": _PIL_AVAILABLE,
                "clip_available": _CLIP_AVAILABLE,
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
            "pil_available": _PIL_AVAILABLE,
            "clip_available": _CLIP_AVAILABLE,
            "clip_loaded": self._clip_model is not None,
        }

    def __repr__(self) -> str:
        return (
            f"VisionEncoder("
            f"model={self._model_name!r}, "
            f"clip={_CLIP_AVAILABLE}, "
            f"pil={_PIL_AVAILABLE})"
        )
