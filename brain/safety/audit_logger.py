"""
brain/safety/audit_logger.py — Аудит-лог safety-событий.

JSONL формат, совместим с BrainLogger. Append-only.
Ротация при достижении max_size_mb. Thread-safe (RLock).
NullObject: если log_dir недоступен — работает только in-memory.

Использование:
    logger = AuditLogger(log_dir="brain/data/logs")
    logger.log_event("boundary_violated", {"reason": "blocked"}, session_id="s1")
    events = logger.get_recent(50)
    blocked = logger.get_by_type("action_blocked")
"""
from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

AUDIT_EVENTS: List[str] = [
    "source_blacklisted",
    "source_whitelisted",
    "source_trust_updated",
    "data_redacted",
    "conflict_detected",
    "action_blocked",
    "action_warned",
    "confidence_gate_blocked",
    "boundary_violated",
    "safety_policy_applied",
    "cycle_complete",
]


@dataclass
class AuditEvent:
    """Одна запись аудит-лога."""

    ts: str
    level: str
    module: str
    event_type: str
    session_id: str
    cycle_id: str
    details: Dict[str, Any] = field(default_factory=dict)


class AuditLogger:
    """
    Аудит-лог safety-событий.

    Пишет JSONL в brain/data/logs/safety_audit.jsonl.
    Ротация при достижении max_size_mb: текущий файл → .1, новый пустой.
    Thread-safe (RLock). Fail-silent: ошибки I/O не роняют систему.
    """

    def __init__(
        self,
        log_dir: str = "brain/data/logs",
        filename: str = "safety_audit.jsonl",
        max_size_mb: float = 10.0,
    ) -> None:
        self._log_dir = log_dir
        self._filename = filename
        self._max_size_bytes = int(max_size_mb * 1024 * 1024)
        self._lock = threading.RLock()
        self._events: List[AuditEvent] = []
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError:
            pass

    @property
    def _log_path(self) -> str:
        return os.path.join(self._log_dir, self._filename)

    def log_event(
        self,
        event_type: str,
        details: Dict[str, Any],
        session_id: str = "",
        cycle_id: str = "",
        level: str = "INFO",
        module: str = "safety",
    ) -> None:
        """Записать safety-событие в лог (in-memory + JSONL файл)."""
        event = AuditEvent(
            ts=datetime.now(timezone.utc).isoformat(),
            level=level,
            module=module,
            event_type=event_type,
            session_id=session_id,
            cycle_id=cycle_id,
            details=details,
        )
        with self._lock:
            self._events.append(event)
            self._write_event(event)

    def _write_event(self, event: AuditEvent) -> None:
        """Записать событие в JSONL файл. Fail-silent."""
        try:
            if os.path.exists(self._log_path):
                if os.path.getsize(self._log_path) >= self._max_size_bytes:
                    self._rotate()
            record = {
                "ts": event.ts,
                "level": event.level,
                "module": event.module,
                "event_type": event.event_type,
                "session_id": event.session_id,
                "cycle_id": event.cycle_id,
                "details": event.details,
            }
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass  # Аудит не должен ронять систему

    def _rotate(self) -> None:
        """Ротация: текущий файл → .1, новый файл пустой."""
        backup = self._log_path + ".1"
        try:
            if os.path.exists(backup):
                os.remove(backup)
            with open(self._log_path, "rb") as src, open(backup, "wb") as dst:
                shutil.copyfileobj(src, dst)
            open(self._log_path, "w", encoding="utf-8").close()  # truncate  # noqa: WPS515
        except OSError:
            pass

    def get_recent(self, n: int = 100) -> List[AuditEvent]:
        """Получить последние n событий (из in-memory кэша)."""
        with self._lock:
            return list(self._events[-n:])

    def get_by_type(self, event_type: str) -> List[AuditEvent]:
        """Получить все события заданного типа."""
        with self._lock:
            return [e for e in self._events if e.event_type == event_type]
