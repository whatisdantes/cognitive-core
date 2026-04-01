"""
brain/encoders/encoder_router.py — Маршрутизатор энкодеров (J.6).

Маршрутизирует PerceptEvent → правильный энкодер по полю modality:
  "text"  → TextEncoder
  "image" → VisionEncoder
  "audio" → AudioEncoder
  "video" → TemporalEncoder
  other   → zeros fallback

Использование:
    router = EncoderRouter(
        text_encoder=TextEncoder(),
        vision_encoder=VisionEncoder(),
        audio_encoder=AudioEncoder(),
        temporal_encoder=TemporalEncoder(),
    )
    encoded = router.route(percept_event)
    all_encoded = router.route_all(percept_events)
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, cast

from brain.core.contracts import EncodedPercept, Modality

logger = logging.getLogger(__name__)

# ─── Размерности по умолчанию для fallback zeros ─────────────────────────────

_DEFAULT_DIMS: Dict[str, int] = {
    "text": 768,
    "image": 512,
    "audio": 768,
    "video": 512,
}
_FALLBACK_DIM = 768

# ─── Маппинг modality str → Modality enum ────────────────────────────────────

_MODALITY_MAP: Dict[str, Modality] = {
    "text": Modality.TEXT,
    "image": Modality.IMAGE,
    "audio": Modality.AUDIO,
    "video": Modality.VIDEO,
}


def _zeros_percept(
    modality_str: str,
    source: str = "",
    trace_id: str = "",
    session_id: str = "",
    cycle_id: str = "",
    status: str = "unavailable",
    reason: str = "",
) -> EncodedPercept:
    """Создать нулевой EncodedPercept для fallback."""
    dim = _DEFAULT_DIMS.get(modality_str, _FALLBACK_DIM)
    modality = _MODALITY_MAP.get(modality_str, Modality.TEXT)
    return EncodedPercept(
        percept_id=f"zero_{uuid.uuid4().hex[:8]}",
        modality=modality,
        vector=[0.0] * dim,
        text="",
        quality=0.0,
        source=source,
        language="unknown",
        message_type=modality_str,
        encoder_model="none",
        vector_dim=dim,
        metadata={
            "encoder_status": status,
            "reason": reason or f"encoder not available for modality={modality_str!r}",
        },
        trace_id=trace_id,
        session_id=session_id,
        cycle_id=cycle_id,
    )


# ─── EncoderRouter ────────────────────────────────────────────────────────────

class EncoderRouter:
    """
    Маршрутизирует PerceptEvent → EncodedPercept через правильный энкодер.

    Параметры (все опциональны — NullObject pattern):
        text_encoder:     TextEncoder или совместимый объект
        vision_encoder:   VisionEncoder или совместимый объект
        audio_encoder:    AudioEncoder или совместимый объект
        temporal_encoder: TemporalEncoder или совместимый объект
    """

    def __init__(
        self,
        text_encoder: Optional[Any] = None,
        vision_encoder: Optional[Any] = None,
        audio_encoder: Optional[Any] = None,
        temporal_encoder: Optional[Any] = None,
    ) -> None:
        self._text_encoder = text_encoder
        self._vision_encoder = vision_encoder
        self._audio_encoder = audio_encoder
        self._temporal_encoder = temporal_encoder

    def route(self, percept: Any) -> EncodedPercept:
        """
        Маршрутизировать один PerceptEvent → EncodedPercept.

        Использует percept.modality для выбора энкодера.
        При отсутствии энкодера или ошибке возвращает zeros fallback.
        """
        modality_str: str = getattr(percept, "modality", "text") or "text"
        source: str = getattr(percept, "source", "") or ""
        trace_id: str = getattr(percept, "trace_id", "") or ""
        session_id: str = getattr(percept, "session_id", "") or ""
        cycle_id: str = getattr(percept, "cycle_id", "") or ""

        try:
            if modality_str == "text":
                return self._route_text(percept, source, trace_id, session_id, cycle_id)
            elif modality_str == "image":
                return self._route_image(percept, source, trace_id, session_id, cycle_id)
            elif modality_str == "audio":
                return self._route_audio(percept, source, trace_id, session_id, cycle_id)
            elif modality_str == "video":
                return self._route_video(percept, source, trace_id, session_id, cycle_id)
            else:
                logger.warning(
                    "[EncoderRouter] неизвестная модальность: %r", modality_str
                )
                return _zeros_percept(
                    modality_str=modality_str,
                    source=source,
                    trace_id=trace_id,
                    session_id=session_id,
                    cycle_id=cycle_id,
                    status="failed",
                    reason=f"unknown modality: {modality_str!r}",
                )
        except Exception as exc:
            logger.warning("[EncoderRouter] ошибка маршрутизации: %s", exc)
            return _zeros_percept(
                modality_str=modality_str,
                source=source,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
                status="failed",
                reason=str(exc),
            )

    def route_all(self, percepts: List[Any]) -> List[EncodedPercept]:
        """Маршрутизировать список PerceptEvent → список EncodedPercept."""
        return [self.route(p) for p in percepts]

    # ─── Внутренние методы маршрутизации ─────────────────────────────────────

    def _route_text(
        self,
        percept: Any,
        source: str,
        trace_id: str,
        session_id: str,
        cycle_id: str,
    ) -> EncodedPercept:
        if self._text_encoder is None:
            return _zeros_percept(
                "text", source, trace_id, session_id, cycle_id,
                status="unavailable", reason="text_encoder not configured",
            )
        content: str = getattr(percept, "content", "") or ""
        return cast(EncodedPercept, self._text_encoder.encode(
            content,
            source=source,
            trace_id=trace_id,
            session_id=session_id,
            cycle_id=cycle_id,
        ))

    def _route_image(
        self,
        percept: Any,
        source: str,
        trace_id: str,
        session_id: str,
        cycle_id: str,
    ) -> EncodedPercept:
        if self._vision_encoder is None:
            return _zeros_percept(
                "image", source, trace_id, session_id, cycle_id,
                status="unavailable", reason="vision_encoder not configured",
            )
        file_path: str = getattr(percept, "file_path", "") or ""
        return cast(EncodedPercept, self._vision_encoder.encode(
            file_path,
            source=source,
            trace_id=trace_id,
            session_id=session_id,
            cycle_id=cycle_id,
        ))

    def _route_audio(
        self,
        percept: Any,
        source: str,
        trace_id: str,
        session_id: str,
        cycle_id: str,
    ) -> EncodedPercept:
        if self._audio_encoder is None:
            return _zeros_percept(
                "audio", source, trace_id, session_id, cycle_id,
                status="unavailable", reason="audio_encoder not configured",
            )
        file_path: str = getattr(percept, "file_path", "") or ""
        return cast(EncodedPercept, self._audio_encoder.encode(
            file_path,
            source=source,
            trace_id=trace_id,
            session_id=session_id,
            cycle_id=cycle_id,
        ))

    def _route_video(
        self,
        percept: Any,
        source: str,
        trace_id: str,
        session_id: str,
        cycle_id: str,
    ) -> EncodedPercept:
        if self._temporal_encoder is None:
            return _zeros_percept(
                "video", source, trace_id, session_id, cycle_id,
                status="unavailable", reason="temporal_encoder not configured",
            )
        file_path: str = getattr(percept, "file_path", "") or ""
        return cast(EncodedPercept, self._temporal_encoder.encode(
            file_path,
            source=source,
            trace_id=trace_id,
            session_id=session_id,
            cycle_id=cycle_id,
        ))

    def status(self) -> Dict[str, Any]:
        """Статус маршрутизатора."""
        def _enc_status(enc: Optional[Any]) -> Optional[str]:
            if enc is None:
                return None
            try:
                s = enc.status()
                return s.get("encoder_status", "configured") if isinstance(s, dict) else "configured"
            except Exception:
                return "configured"

        return {
            "text_encoder": _enc_status(self._text_encoder),
            "vision_encoder": _enc_status(self._vision_encoder),
            "audio_encoder": _enc_status(self._audio_encoder),
            "temporal_encoder": _enc_status(self._temporal_encoder),
        }

    def __repr__(self) -> str:
        return (
            f"EncoderRouter("
            f"text={self._text_encoder is not None}, "
            f"vision={self._vision_encoder is not None}, "
            f"audio={self._audio_encoder is not None}, "
            f"temporal={self._temporal_encoder is not None})"
        )
