"""
brain/perception/audio_ingestor.py — Ingestor для аудиофайлов (J.2).

Поддерживаемые форматы: .wav, .mp3, .flac, .ogg, .aac, .m4a

Fallback-цепочка:
  Whisper → транскрипт + язык, quality=1.0
  no Whisper + WAV → content="", duration из wave stdlib, quality=0.6
  no Whisper + non-WAV → content="", duration_s=None, quality=0.5

Использование:
    ingestor = AudioIngestor()
    events = ingestor.ingest("speech.wav", session_id="s1")
    # events[0].modality == "audio"
    # events[0].content  == "транскрипт или пустая строка"
"""
from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from brain.core.events import EventFactory, PerceptEvent

logger = logging.getLogger(__name__)

# ─── Опциональные зависимости ────────────────────────────────────────────────

try:
    import whisper as _whisper  # type: ignore[import-untyped]
    _WHISPER_AVAILABLE = True
except ImportError:
    _WHISPER_AVAILABLE = False
    logger.debug("openai-whisper не установлен — AudioIngestor работает в degraded режиме")

# ─── Константы ───────────────────────────────────────────────────────────────

AUDIO_EXTENSIONS: frozenset[str] = frozenset({
    ".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a",
})

_MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB
_DEFAULT_WHISPER_MODEL = "tiny"


# ─── Вспомогательные функции (мокируемые в тестах) ───────────────────────────

def _transcribe_audio(file_path: str, model_name: str = _DEFAULT_WHISPER_MODEL) -> Dict[str, Any]:
    """
    Транскрибировать аудио через Whisper. Мокируется в тестах.

    Возвращает dict с ключами: "text", "language".
    """
    model = _whisper.load_model(model_name)
    result = model.transcribe(file_path)
    return {
        "text": result.get("text", "").strip(),
        "language": result.get("language", "unknown"),
    }


def _read_wav_metadata(file_path: str) -> Dict[str, Any]:
    """
    Прочитать метаданные WAV через stdlib wave. Возвращает duration_s и sample_rate.
    """
    try:
        with wave.open(file_path, "r") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            duration_s = frames / rate if rate > 0 else 0.0
            return {
                "duration_s": round(duration_s, 3),
                "sample_rate": rate,
                "channels": wf.getnchannels(),
            }
    except Exception as exc:
        logger.debug("_read_wav_metadata failed for '%s': %s", file_path, exc)
        return {"duration_s": None, "sample_rate": None, "channels": None}


# ─── AudioIngestor ───────────────────────────────────────────────────────────

class AudioIngestor:
    """
    Читает аудиофайлы и преобразует в PerceptEvent(modality="audio").

    Параметры:
        model_name:    имя модели Whisper (default: "tiny")
        max_file_size: максимальный размер файла в байтах (default: 500 MB)
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_WHISPER_MODEL,
        max_file_size: int = _MAX_FILE_SIZE_BYTES,
    ) -> None:
        self._model_name = model_name
        self._max_file_size = max_file_size

    def ingest(
        self,
        file_path: str,
        session_id: str = "",
        trace_id: str = "",
    ) -> List[PerceptEvent]:
        """
        Прочитать аудиофайл → List[PerceptEvent].

        Возвращает [] при:
          - пустом пути
          - несуществующем файле
          - неподдерживаемом расширении
        """
        if not file_path:
            return []

        path = Path(file_path)

        # Проверка расширения
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            logger.debug("AudioIngestor: неподдерживаемое расширение '%s'", path.suffix)
            return []

        # Проверка существования файла
        if not path.exists():
            logger.warning("AudioIngestor: файл не найден '%s'", file_path)
            return []

        file_size_kb = round(path.stat().st_size / 1024, 2)
        is_wav = path.suffix.lower() == ".wav"

        # Инициализация метаданных
        content = ""
        language = "unknown"
        duration_s: Optional[float] = None
        sample_rate: Optional[int] = None
        duration_available = False
        whisper_available = _WHISPER_AVAILABLE

        # WAV: читаем метаданные через stdlib даже без Whisper
        if is_wav:
            wav_meta = _read_wav_metadata(file_path)
            duration_s = wav_meta.get("duration_s")
            sample_rate = wav_meta.get("sample_rate")
            if duration_s is not None:
                duration_available = True

        # Whisper транскрипция
        if _WHISPER_AVAILABLE:
            try:
                result = _transcribe_audio(file_path, self._model_name)
                content = result.get("text", "")
                language = result.get("language", "unknown")
                # Если Whisper дал duration — используем его
                if "duration_s" in result and result["duration_s"] is not None:
                    duration_s = result["duration_s"]
                    duration_available = True
            except Exception as exc:
                logger.warning("AudioIngestor: Whisper ошибка для '%s': %s", file_path, exc)
                content = ""
                whisper_available = False

        # Качество
        if whisper_available and content:
            quality = 1.0
        elif is_wav and duration_available:
            quality = 0.6
        else:
            quality = 0.5

        event = EventFactory.percept(
            source=file_path,
            content=content,
            modality="audio",
            quality=quality,
            language=language,
            session_id=session_id,
            # metadata kwargs:
            whisper_available=whisper_available,
            duration_s=duration_s,
            duration_available=duration_available,
            sample_rate=sample_rate,
            file_size_kb=file_size_kb,
        )
        if trace_id:
            event.trace_id = trace_id

        return [event]

    def status(self) -> Dict[str, Any]:
        """Статус ingestor'а."""
        return {
            "whisper_available": _WHISPER_AVAILABLE,
            "model_name": self._model_name,
            "supported_extensions": sorted(AUDIO_EXTENSIONS),
            "max_file_size_mb": self._max_file_size // (1024 * 1024),
        }

    def __repr__(self) -> str:
        return (
            f"AudioIngestor("
            f"whisper={_WHISPER_AVAILABLE}, "
            f"model={self._model_name!r})"
        )
