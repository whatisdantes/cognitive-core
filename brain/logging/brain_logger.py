"""
brain/logging/brain_logger.py

BrainLogger — потокобезопасный JSONL-логгер для всех модулей мозга.

Особенности:
  - Каждое событие = одна JSON-строка в brain.jsonl
  - Параллельная запись в категорийные файлы (cognitive/memory/perception/learning/safety)
  - In-memory индекс для быстрого поиска по trace_id и session_id
  - Ротация файлов при превышении max_size_mb
  - Thread-safe (threading.Lock)
  - Нулевые зависимости (только stdlib)

Формат записи:
  {
    "ts": "2026-03-19T12:00:00.123Z",
    "level": "INFO",
    "module": "planner",
    "event": "goal_created",
    "session_id": "sess_01",
    "cycle_id": "cycle_4521",
    "trace_id": "trace_9fa",
    "state": {"goal": "answer_question", "cpu_pct": 45},
    "decision": {"action": "respond", "confidence": 0.78},
    "latency_ms": 2.3,
    "notes": "..."
  }
"""

from __future__ import annotations

import atexit
import gzip
import json
import threading
import weakref
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Константы
# ---------------------------------------------------------------------------

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "CRITICAL")
LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}

# Категорийные файлы: event-prefix → имя файла
_CATEGORY_MAP: Dict[str, str] = {
    # Cognitive
    "goal_": "cognitive",
    "plan_": "cognitive",
    "reasoning_": "cognitive",
    "contradiction_": "cognitive",
    "action_": "cognitive",
    "hypothesis_": "cognitive",
    "uncertainty_": "cognitive",
    # Memory
    "fact_": "memory",
    "episode_": "memory",
    "consolidation_": "memory",
    "memory_": "memory",
    "confidence_": "memory",
    "source_": "memory",
    # Perception
    "text_ingested": "perception",
    "image_ingested": "perception",
    "audio_ingested": "perception",
    "ocr_": "perception",
    "asr_": "perception",
    "parse_": "perception",
    "percept_": "perception",
    # Learning
    "online_update": "learning",
    "replay_": "learning",
    "gap_": "learning",
    "encoder_": "learning",
    "learning_": "learning",
    # Safety / Audit
    "blacklist": "safety_audit",
    "data_redacted": "safety_audit",
    "conflict_detected": "safety_audit",
    "trust_updated": "safety_audit",
    "boundary_": "safety_audit",
    "audit_": "safety_audit",
}


def _detect_category(event: str) -> Optional[str]:
    """Определить категорийный файл по имени события."""
    for prefix, cat in _CATEGORY_MAP.items():
        if event.startswith(prefix) or event == prefix.rstrip("_"):
            return cat
    return None


# ---------------------------------------------------------------------------
# BrainLogger
# ---------------------------------------------------------------------------

class BrainLogger:
    """
    Потокобезопасный JSONL-логгер для всех модулей мозга.

    Параметры:
        log_dir      — директория для файлов логов (создаётся автоматически)
        min_level    — минимальный уровень логирования (DEBUG/INFO/WARN/ERROR/CRITICAL)
        max_size_mb  — максимальный размер brain.jsonl до ротации (МБ)
        echo_stdout  — дублировать ли записи в stdout (для dev-режима)
    """

    def __init__(
        self,
        log_dir: str = "brain/data/logs",
        min_level: str = "DEBUG",
        max_size_mb: float = 100.0,
        echo_stdout: bool = False,
    ) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        (self._log_dir / "digests").mkdir(exist_ok=True)

        self._min_level = min_level.upper()
        self._min_rank = LEVEL_RANK.get(self._min_level, 0)
        self._max_bytes = int(max_size_mb * 1024 * 1024)
        self._echo = echo_stdout

        self._lock = threading.Lock()

        # Открытые файловые дескрипторы: имя → file object
        self._files: Dict[str, Any] = {}

        # In-memory индексы для быстрого поиска
        # trace_id  → list of event dicts
        self._trace_index: Dict[str, List[dict]] = defaultdict(list)
        # session_id → list of event dicts
        self._session_index: Dict[str, List[dict]] = defaultdict(list)

        # Открыть основной файл
        self._open_file("brain")

        # Гарантировать закрытие файлов при завершении процесса.
        # weakref предотвращает удержание объекта в памяти только из-за atexit.
        _ref = weakref.ref(self, lambda r: None)

        def _atexit_close() -> None:
            obj = _ref()
            if obj is not None:
                obj.close()

        atexit.register(_atexit_close)

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def log(
        self,
        level: str,
        module: str,
        event: str,
        *,
        session_id: str = "",
        cycle_id: str = "",
        trace_id: str = "",
        input_ref: Optional[List[str]] = None,
        memory_refs: Optional[List[str]] = None,
        state: Optional[Dict[str, Any]] = None,
        decision: Optional[Dict[str, Any]] = None,
        latency_ms: Optional[float] = None,
        notes: str = "",
        **extra: Any,
    ) -> None:
        """Записать событие в JSONL."""
        level = level.upper()
        if LEVEL_RANK.get(level, 0) < self._min_rank:
            return

        record: Dict[str, Any] = {
            "ts": _now_iso(),
            "level": level,
            "module": module,
            "event": event,
            "session_id": session_id,
            "cycle_id": cycle_id,
            "trace_id": trace_id,
        }
        if input_ref is not None:
            record["input_ref"] = input_ref
        if memory_refs is not None:
            record["memory_refs"] = memory_refs
        if state is not None:
            record["state"] = state
        if decision is not None:
            record["decision"] = decision
        if latency_ms is not None:
            record["latency_ms"] = round(latency_ms, 3)
        if notes:
            record["notes"] = notes
        if extra:
            record.update(extra)

        line = json.dumps(record, ensure_ascii=False)

        with self._lock:
            self._write_line("brain", line)
            category = _detect_category(event)
            if category:
                self._write_line(category, line)
            # Обновить индексы
            if trace_id:
                self._trace_index[trace_id].append(record)
            if session_id:
                self._session_index[session_id].append(record)

        if self._echo:
            print(f"[{record['ts']}] {level:8s} {module:20s} {event}")

    # Shortcuts
    def debug(self, module: str, event: str, **kwargs: Any) -> None:
        self.log("DEBUG", module, event, **kwargs)

    def info(self, module: str, event: str, **kwargs: Any) -> None:
        self.log("INFO", module, event, **kwargs)

    def warn(self, module: str, event: str, **kwargs: Any) -> None:
        self.log("WARN", module, event, **kwargs)

    def error(self, module: str, event: str, **kwargs: Any) -> None:
        self.log("ERROR", module, event, **kwargs)

    def critical(self, module: str, event: str, **kwargs: Any) -> None:
        self.log("CRITICAL", module, event, **kwargs)

    # ------------------------------------------------------------------
    # Поиск по индексам
    # ------------------------------------------------------------------

    def get_events(self, trace_id: str) -> List[dict]:
        """Вернуть все события по trace_id (из in-memory индекса)."""
        with self._lock:
            return list(self._trace_index.get(trace_id, []))

    def get_session(self, session_id: str) -> List[dict]:
        """Вернуть все события сессии (из in-memory индекса)."""
        with self._lock:
            return list(self._session_index.get(session_id, []))

    def get_recent(self, n: int = 20, min_level: str = "DEBUG") -> List[dict]:
        """Вернуть последние N событий из brain.jsonl (из индекса)."""
        rank = LEVEL_RANK.get(min_level.upper(), 0)
        with self._lock:
            all_events: List[dict] = []
            for events in self._trace_index.values():
                all_events.extend(events)
            filtered = [e for e in all_events if LEVEL_RANK.get(e.get("level", "DEBUG"), 0) >= rank]
            # Сортировка по ts
            filtered.sort(key=lambda e: e.get("ts", ""))
            return filtered[-n:]

    def flush(self) -> None:
        """Сбросить буферы всех открытых файлов."""
        with self._lock:
            for fh in self._files.values():
                try:
                    fh.flush()
                except Exception:
                    pass

    def close(self) -> None:
        """Закрыть все файловые дескрипторы."""
        with self._lock:
            for fh in self._files.values():
                try:
                    fh.close()
                except Exception:
                    pass
            self._files.clear()

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _open_file(self, name: str) -> None:
        """Открыть (или переоткрыть) файл лога."""
        path = self._log_dir / f"{name}.jsonl"
        self._files[name] = open(path, "a", encoding="utf-8", buffering=1)

    def _write_line(self, name: str, line: str) -> None:
        """Записать строку в файл name.jsonl с проверкой ротации."""
        if name not in self._files:
            self._open_file(name)
        fh = self._files[name]
        fh.write(line + "\n")
        # Ротация
        if name == "brain":
            try:
                size = self._log_dir.joinpath(f"{name}.jsonl").stat().st_size
                if size >= self._max_bytes:
                    self._rotate(name)
            except OSError:
                pass

    def _rotate(self, name: str) -> None:
        """Переименовать текущий файл в архив и открыть новый."""
        fh = self._files.pop(name, None)
        if fh:
            try:
                fh.close()
            except Exception:
                pass
        src = self._log_dir / f"{name}.jsonl"
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        dst = self._log_dir / f"{name}_{ts}.jsonl.gz"
        try:
            with open(src, "rb") as f_in, gzip.open(dst, "wb") as f_out:
                f_out.write(f_in.read())
            src.unlink()
        except Exception:
            pass
        self._open_file(name)

    def __repr__(self) -> str:
        return (
            f"BrainLogger(log_dir={self._log_dir!r}, "
            f"min_level={self._min_level!r}, "
            f"traces={len(self._trace_index)}, "
            f"sessions={len(self._session_index)})"
        )


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Текущее время в ISO 8601 с миллисекундами и Z-суффиксом."""
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
