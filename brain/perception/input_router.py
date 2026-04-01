"""
input_router.py — Маршрутизатор входящих данных (аналог Таламуса).

MVP: text-only routing.
  - Определяет модальность по расширению файла
  - Дедупликация через SHA256 хэш
  - Фильтрация по quality (warning / low-priority / hard reject)
  - Для text → TextIngestor → List[PerceptEvent]
  - Для image/audio/video → лог предупреждения, пропуск (MVP)
  - Публикация в EventBus (опционально)
  - Статистика: stats()

Пороги качества (MVP):
  quality >= 0.7  → normal
  0.4 <= q < 0.7  → warning (обрабатывается с пометкой)
  quality < 0.4   → warning + low-priority (обрабатывается, низкий приоритет)
  hard reject     → пустой/нечитаемый контент (не обрабатывается)
"""

from __future__ import annotations

import enum
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from brain.core.events import PerceptEvent
from brain.core.hash_utils import sha256_file as _sha256_file
from brain.core.hash_utils import sha256_text
from brain.logging import _NULL_LOGGER, BrainLogger
from brain.perception.metadata_extractor import MetadataExtractor
from brain.perception.text_ingestor import TextIngestor
from brain.perception.validators import check_file_size, validate_file_path
from brain.perception.vision_ingestor import VisionIngestor
from brain.perception.audio_ingestor import AudioIngestor

# ─── Тип входных данных ──────────────────────────────────────────────────────

class InputType(enum.Enum):
    """
    Явный тип входных данных для InputRouter.

    FILE  — источник — путь к файлу на диске
    TEXT  — источник — строка текста (user input, API, etc.)
    AUTO  — автоопределение по os.path.exists() (backward compatible default)

    Использование:
        router.route("docs/report.pdf", input_type=InputType.FILE)
        router.route("Нейрон — это клетка", input_type=InputType.TEXT)
        router.route(source, input_type=InputType.AUTO)  # default
    """
    FILE = "file"
    TEXT = "text"
    AUTO = "auto"

_logger = logging.getLogger(__name__)

# ─── Константы ───────────────────────────────────────────────────────────────

# Расширения по модальности
_TEXT_EXTS  = {".txt", ".md", ".pdf", ".docx", ".json", ".csv"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff"}
_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".aac", ".m4a"}
_VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def _detect_modality(source: str) -> str:
    """Определить модальность по расширению файла."""
    ext = Path(source).suffix.lower()
    if ext in _TEXT_EXTS:
        return "text"
    if ext in _IMAGE_EXTS:
        return "image"
    if ext in _AUDIO_EXTS:
        return "audio"
    if ext in _VIDEO_EXTS:
        return "video"
    return "unknown"


# _sha256 и _sha256_file импортированы из brain.core.hash_utils
# (sha256_text с truncate=16 по умолчанию, sha256_file с truncate=16)


# ─── RouterStats ─────────────────────────────────────────────────────────────

class RouterStats:
    """Статистика работы InputRouter."""

    def __init__(self):
        self.total_routed: int = 0
        self.total_events: int = 0
        self.duplicates_skipped: int = 0
        self.hard_rejected: int = 0
        self.warnings_issued: int = 0
        self.low_priority: int = 0
        self.unsupported_modality: int = 0
        self.errors: int = 0
        self._by_modality: Dict[str, int] = {}

    def record(self, modality: str, events: int):
        self.total_routed += 1
        self.total_events += events
        self._by_modality[modality] = self._by_modality.get(modality, 0) + events

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_routed": self.total_routed,
            "total_events": self.total_events,
            "duplicates_skipped": self.duplicates_skipped,
            "hard_rejected": self.hard_rejected,
            "warnings_issued": self.warnings_issued,
            "low_priority": self.low_priority,
            "unsupported_modality": self.unsupported_modality,
            "errors": self.errors,
            "by_modality": dict(self._by_modality),
        }


# ─── InputRouter ─────────────────────────────────────────────────────────────

class InputRouter:
    """
    Маршрутизатор входящих данных — аналог Таламуса.

    MVP: обрабатывает только text-модальность.
    Image/audio/video — логируются как предупреждение и пропускаются.

    Параметры:
        text_ingestor:  экземпляр TextIngestor (создаётся автоматически)
        event_bus:      EventBus для публикации событий (опционально)
        dedup:          включить дедупликацию по SHA256 (default: True)

    Использование:
        router = InputRouter()

        # Маршрутизация файла
        events = router.route("docs/нейрон.pdf", session_id="s1")

        # Маршрутизация прямого текста
        events = router.route_text("Нейрон — это клетка...", source="user_input")

        # Статистика
        print(router.stats())
    """

    def __init__(
        self,
        text_ingestor: Optional[TextIngestor] = None,
        event_bus=None,
        dedup: bool = True,
        brain_logger: Optional[BrainLogger] = None,
        vision_ingestor: Optional[VisionIngestor] = None,
        audio_ingestor: Optional[AudioIngestor] = None,
    ):
        self._ingestor = text_ingestor or TextIngestor()
        self._bus = event_bus
        self._dedup = dedup
        self._seen_hashes: Set[str] = set()
        self._stats = RouterStats()

        # --- Phase 5: BrainLogger (NullObject pattern) ---
        self._blog: BrainLogger = brain_logger or _NULL_LOGGER  # type: ignore[assignment]

        # --- Этап J: Multimodal ingestors (NullObject pattern — None = skip) ---
        self._vision_ingestor: Optional[VisionIngestor] = vision_ingestor
        self._audio_ingestor: Optional[AudioIngestor] = audio_ingestor

    # ─── Публичный API ───────────────────────────────────────────────────────

    def route(
        self,
        source: str,
        session_id: str = "",
        trace_id: str = "",
        force: bool = False,
        input_type: InputType = InputType.AUTO,
    ) -> List[PerceptEvent]:
        """
        Маршрутизировать входящий источник (файл или строка текста).

        Args:
            source:     путь к файлу ИЛИ строка текста
            session_id: ID сессии
            trace_id:   ID трассировки
            force:      игнорировать дедупликацию (default: False)
            input_type: явный тип входных данных (FILE / TEXT / AUTO)

        Returns:
            List[PerceptEvent] — пустой список при дубликате/reject/ошибке
        """
        if input_type == InputType.FILE:
            return self._route_file(source, session_id, trace_id, force)
        if input_type == InputType.TEXT:
            return self.route_text(source, source="user_input", session_id=session_id, trace_id=trace_id)

        # AUTO: определяем по наличию файла на диске
        if os.path.exists(source):
            return self._route_file(source, session_id, trace_id, force)
        # Считаем source строкой текста
        return self.route_text(source, source="user_input", session_id=session_id, trace_id=trace_id)

    def route_file(
        self,
        file_path: str,
        session_id: str = "",
        trace_id: str = "",
        force: bool = False,
    ) -> List[PerceptEvent]:
        """
        Явная маршрутизация файла.

        Args:
            file_path:  путь к файлу
            session_id: ID сессии
            trace_id:   ID трассировки
            force:      игнорировать дедупликацию

        Returns:
            List[PerceptEvent]
        """
        return self._route_file(file_path, session_id, trace_id, force)

    def route_text(
        self,
        text: str,
        source: str = "user_input",
        session_id: str = "",
        trace_id: str = "",
        force: bool = False,
    ) -> List[PerceptEvent]:
        """
        Маршрутизировать прямой текстовый ввод.

        Args:
            text:       входной текст
            source:     идентификатор источника
            session_id: ID сессии
            trace_id:   ID трассировки
            force:      игнорировать дедупликацию

        Returns:
            List[PerceptEvent]
        """
        # Hard reject
        reject, reason = MetadataExtractor.should_reject(text)
        if reject:
            _logger.warning("InputRouter: hard reject text source='%s' — %s", source, reason)
            self._stats.hard_rejected += 1
            # --- Phase 5: input_rejected (WARN) ---
            self._blog.warn(
                "perception", "input_rejected",
                state={"source": source, "reason": reason, "modality": "text"},
            )
            return []

        # Дедупликация
        if self._dedup and not force:
            h = sha256_text(text, truncate=16)  # хэшируем полный текст
            if h in self._seen_hashes:
                _logger.debug("InputRouter: дубликат text source='%s' hash=%s", source, h)
                self._stats.duplicates_skipped += 1
                # --- Phase 5: input_duplicate (DEBUG) ---
                self._blog.debug(
                    "perception", "input_duplicate",
                    state={"source": source, "hash": h, "modality": "text"},
                )
                return []
            self._seen_hashes.add(h)

        try:
            events = self._ingestor.ingest_text(
                text=text,
                source=source,
                session_id=session_id,
                trace_id=trace_id,
            )
        except Exception as e:
            _logger.error("InputRouter: ошибка обработки text source='%s': %s", source, e)
            self._stats.errors += 1
            return []

        events = self._apply_quality_policy(events)
        self._stats.record("text", len(events))
        self._publish_events(events)

        _logger.info(
            "InputRouter: text source='%s' → %d событий",
            source, len(events),
        )

        # --- Phase 5: input_routed (INFO) ---
        self._blog.info(
            "perception", "input_routed",
            state={
                "source": source,
                "modality": "text",
                "events_count": len(events),
                "session_id": session_id,
            },
        )

        return events

    def route_batch(
        self,
        sources: List[str],
        session_id: str = "",
        trace_id: str = "",
    ) -> List[PerceptEvent]:
        """
        Маршрутизировать список источников (файлов или текстов).

        Returns:
            Объединённый список PerceptEvent
        """
        all_events: List[PerceptEvent] = []
        for source in sources:
            events = self.route(source, session_id=session_id, trace_id=trace_id)
            all_events.extend(events)
        return all_events

    def stats(self) -> Dict[str, Any]:
        """Статистика маршрутизатора."""
        return self._stats.to_dict()

    def reset_dedup(self):
        """Очистить кэш дедупликации."""
        self._seen_hashes.clear()
        _logger.info("InputRouter: кэш дедупликации очищен")

    # ─── Внутренние методы ───────────────────────────────────────────────────

    def _route_file(
        self,
        file_path: str,
        session_id: str,
        trace_id: str,
        force: bool,
    ) -> List[PerceptEvent]:
        """Маршрутизировать файл."""
        # B.2: Валидация пути (path traversal, null bytes, system dirs)
        safe, reason = validate_file_path(file_path)
        if not safe:
            _logger.warning(
                "InputRouter: файл отклонён валидацией — %s: %s",
                reason, file_path,
            )
            self._stats.hard_rejected += 1
            return []

        path = Path(file_path)

        # Проверка существования
        if not path.exists():
            _logger.error("InputRouter: файл не найден: %s", file_path)
            self._stats.errors += 1
            return []

        # B.2: Проверка размера файла
        size_ok, size_mb = check_file_size(file_path)
        if not size_ok:
            _logger.warning(
                "InputRouter: файл слишком большой (%.1f MB): %s",
                size_mb, file_path,
            )
            self._stats.hard_rejected += 1
            return []

        # Определяем модальность
        modality = _detect_modality(file_path)

        # Этап J: image → VisionIngestor (если задан), иначе пропуск
        if modality == "image":
            if self._vision_ingestor is None:
                _logger.warning(
                    "InputRouter: image — vision_ingestor не задан, пропуск: %s",
                    file_path,
                )
                self._stats.unsupported_modality += 1
                return []
            return self._route_vision(file_path, session_id, trace_id, force)

        # Этап J: audio → AudioIngestor (если задан), иначе пропуск
        if modality == "audio":
            if self._audio_ingestor is None:
                _logger.warning(
                    "InputRouter: audio — audio_ingestor не задан, пропуск: %s",
                    file_path,
                )
                self._stats.unsupported_modality += 1
                return []
            return self._route_audio_file(file_path, session_id, trace_id, force)

        if modality == "video":
            _logger.warning(
                "InputRouter: video не поддерживается (Этап J+), пропуск: %s",
                file_path,
            )
            self._stats.unsupported_modality += 1
            return []

        if modality == "unknown":
            _logger.warning(
                "InputRouter: неизвестная модальность для файла: %s",
                file_path,
            )
            self._stats.unsupported_modality += 1
            return []

        # Дедупликация по SHA256 файла
        if self._dedup and not force:
            file_hash = _sha256_file(file_path)
            if file_hash in self._seen_hashes:
                _logger.info(
                    "InputRouter: дубликат файла пропущен: %s (hash=%s)",
                    file_path, file_hash,
                )
                self._stats.duplicates_skipped += 1
                # --- Phase 5: input_duplicate (DEBUG) ---
                self._blog.debug(
                    "perception", "input_duplicate",
                    state={"source": file_path, "hash": file_hash, "modality": modality},
                )
                return []
            self._seen_hashes.add(file_hash)

        # Обработка через TextIngestor
        try:
            events = self._ingestor.ingest(
                file_path=file_path,
                session_id=session_id,
                trace_id=trace_id,
            )
        except Exception as e:
            _logger.error("InputRouter: ошибка обработки файла %s: %s", file_path, e)
            self._stats.errors += 1
            return []

        if not events:
            _logger.warning("InputRouter: файл не дал событий (пустой?): %s", file_path)
            self._stats.hard_rejected += 1
            return []

        events = self._apply_quality_policy(events)
        self._stats.record(modality, len(events))
        self._publish_events(events)

        _logger.info(
            "InputRouter: файл %s → %d событий (modality=%s)",
            file_path, len(events), modality,
        )

        # --- Phase 5: input_routed (INFO) ---
        self._blog.info(
            "perception", "input_routed",
            state={
                "source": file_path,
                "modality": modality,
                "events_count": len(events),
                "session_id": session_id,
            },
        )

        return events

    def _route_vision(
        self,
        file_path: str,
        session_id: str,
        trace_id: str,
        force: bool,
    ) -> List[PerceptEvent]:
        """Маршрутизировать изображение через VisionIngestor (Этап J)."""
        # Дедупликация
        if self._dedup and not force:
            file_hash = _sha256_file(file_path)
            if file_hash in self._seen_hashes:
                _logger.debug("InputRouter: дубликат image пропущен: %s", file_path)
                self._stats.duplicates_skipped += 1
                return []
            self._seen_hashes.add(file_hash)

        try:
            events = self._vision_ingestor.ingest(  # type: ignore[union-attr]
                file_path=file_path,
                session_id=session_id,
                trace_id=trace_id,
            )
        except Exception as exc:
            _logger.error("InputRouter: ошибка VisionIngestor %s: %s", file_path, exc)
            self._stats.errors += 1
            return []

        if not events:
            _logger.warning("InputRouter: image не дал событий: %s", file_path)
            self._stats.hard_rejected += 1
            return []

        events = self._apply_quality_policy(events)
        self._stats.record("image", len(events))
        self._publish_events(events)
        _logger.info("InputRouter: image %s → %d событий", file_path, len(events))
        return events

    def _route_audio_file(
        self,
        file_path: str,
        session_id: str,
        trace_id: str,
        force: bool,
    ) -> List[PerceptEvent]:
        """Маршрутизировать аудио через AudioIngestor (Этап J)."""
        # Дедупликация
        if self._dedup and not force:
            file_hash = _sha256_file(file_path)
            if file_hash in self._seen_hashes:
                _logger.debug("InputRouter: дубликат audio пропущен: %s", file_path)
                self._stats.duplicates_skipped += 1
                return []
            self._seen_hashes.add(file_hash)

        try:
            events = self._audio_ingestor.ingest(  # type: ignore[union-attr]
                file_path=file_path,
                session_id=session_id,
                trace_id=trace_id,
            )
        except Exception as exc:
            _logger.error("InputRouter: ошибка AudioIngestor %s: %s", file_path, exc)
            self._stats.errors += 1
            return []

        if not events:
            _logger.warning("InputRouter: audio не дал событий: %s", file_path)
            self._stats.hard_rejected += 1
            return []

        events = self._apply_quality_policy(events)
        self._stats.record("audio", len(events))
        self._publish_events(events)
        _logger.info("InputRouter: audio %s → %d событий", file_path, len(events))
        return events

    def _apply_quality_policy(self, events: List[PerceptEvent]) -> List[PerceptEvent]:
        """
        Применить политику качества к списку событий.

        quality >= 0.7  → normal, без изменений
        0.4 <= q < 0.7  → warning, событие сохраняется
        quality < 0.4   → warning + low-priority (metadata["priority"] = "low")
        """
        result: List[PerceptEvent] = []
        for event in events:
            q = event.quality
            label = MetadataExtractor.quality_label(q)

            if label == "warning":
                self._stats.warnings_issued += 1
                _logger.warning(
                    "InputRouter: низкое качество (warning) source='%s' quality=%.2f",
                    event.source, q,
                )
                event.metadata["quality_label"] = "warning"
                result.append(event)

            elif label == "low_priority":
                self._stats.warnings_issued += 1
                self._stats.low_priority += 1
                _logger.warning(
                    "InputRouter: очень низкое качество (low_priority) source='%s' quality=%.2f",
                    event.source, q,
                )
                event.metadata["quality_label"] = "low_priority"
                event.metadata["priority"] = "low"
                result.append(event)

            else:
                # normal
                event.metadata["quality_label"] = "normal"
                result.append(event)

        return result

    def _publish_events(self, events: List[PerceptEvent]):
        """Опубликовать события в EventBus (если подключён)."""
        if self._bus is None:
            return
        for event in events:
            try:
                self._bus.publish(event.event_type, event)
            except Exception as e:
                _logger.error("InputRouter: ошибка публикации в EventBus: %s", e)

    def __repr__(self) -> str:
        return (
            f"InputRouter("
            f"dedup={self._dedup}, "
            f"seen={len(self._seen_hashes)}, "
            f"routed={self._stats.total_routed})"
        )
