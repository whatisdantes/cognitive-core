"""Polling FileWatcher для ingestion материалов во время daemon runtime."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from brain.core.contracts import Task
from brain.core.hash_utils import sha256_text
from brain.core.scheduler import Scheduler, TaskPriority
from brain.logging import _NULL_LOGGER, BrainLogger

logger = logging.getLogger(__name__)


@dataclass
class FileWatcherConfig:
    """Настройки polling watcher-а для директории материалов."""
    watch_dir: str = "materials"
    patterns: Tuple[str, ...] = ("*.txt", "*.md", "*.pdf", "*.json", "*.csv")
    recursive: bool = True
    stabilization_checks: int = 3
    stabilization_interval_s: float = 2.0
    max_unstable_polls: int = 6
    session_id: str = "file_watcher"


@dataclass
class FileWatchState:
    """Внутреннее состояние наблюдаемого файла между polling-циклами."""
    last_size: int
    last_mtime: float
    stable_count: int = 1
    last_check_ts: float = 0.0
    unstable_polls: int = 0
    enqueued: bool = False


@dataclass
class FileWatcherPollResult:
    """Краткий итог одного polling-цикла."""
    seen: int = 0
    enqueued: int = 0
    skipped_busy: int = 0
    unstable: int = 0
    enqueued_paths: List[str] = field(default_factory=list)


class FileWatcher:
    """
    Polling watcher без фонового потока.

    Daemon вызывает `poll_once()` как recurring/maintenance task. После
    стабилизации файла watcher ставит LOW-задачу `ingest_file` в Scheduler.
    """

    def __init__(
        self,
        scheduler: Scheduler,
        config: Optional[FileWatcherConfig] = None,
        brain_logger: Optional[BrainLogger] = None,
        list_files_fn: Optional[Callable[[], Iterable[Path | str]]] = None,
        stat_fn: Optional[Callable[[Path], Any]] = None,
        readable_probe: Optional[Callable[[Path], None]] = None,
    ) -> None:
        self._scheduler = scheduler
        self._config = config or FileWatcherConfig()
        self._blog: BrainLogger = brain_logger or _NULL_LOGGER  # type: ignore[assignment]
        self._list_files_fn = list_files_fn
        self._stat_fn = stat_fn or (lambda path: path.stat())
        self._readable_probe = readable_probe or self._default_readable_probe
        self._states: Dict[str, FileWatchState] = {}

    @property
    def config(self) -> FileWatcherConfig:
        """Текущая конфигурация watcher-а."""
        return self._config

    def poll_once(self, now: Optional[float] = None) -> FileWatcherPollResult:
        """Проверить каталог один раз и enqueue-нуть стабилизированные файлы."""
        ts = time.monotonic() if now is None else now
        result = FileWatcherPollResult()
        try:
            paths = list(self._iter_paths())
        except OSError as exc:
            self._log_busy(Path(self._config.watch_dir), "list_failed", exc)
            result.skipped_busy += 1
            return result

        current_keys: set[str] = set()
        for raw_path in paths:
            path = Path(raw_path)
            key = str(path)
            current_keys.add(key)
            result.seen += 1

            try:
                stat = self._stat_fn(path)
                self._readable_probe(path)
            except OSError as exc:
                self._log_busy(path, "busy_or_locked", exc)
                result.skipped_busy += 1
                continue

            size = int(stat.st_size)
            mtime = float(stat.st_mtime)
            state = self._states.get(key)
            if state is None:
                state = FileWatchState(
                    last_size=size,
                    last_mtime=mtime,
                    stable_count=1,
                    last_check_ts=ts,
                )
                self._states[key] = state
            elif state.last_size != size or state.last_mtime != mtime:
                state.last_size = size
                state.last_mtime = mtime
                state.stable_count = 1
                state.last_check_ts = ts
                state.unstable_polls += 1
                state.enqueued = False
                result.unstable += 1
                if state.unstable_polls >= max(1, self._config.max_unstable_polls):
                    self._log_busy(path, "unstable", None)
                    result.skipped_busy += 1
                    state.unstable_polls = 0
            elif ts - state.last_check_ts >= max(0.0, self._config.stabilization_interval_s):
                state.stable_count += 1
                state.last_check_ts = ts

            if state.stable_count >= max(1, self._config.stabilization_checks):
                if not state.enqueued and self._enqueue_ingest(path, size, mtime):
                    state.enqueued = True
                    state.unstable_polls = 0
                    result.enqueued += 1
                    result.enqueued_paths.append(str(path))

        for key in list(self._states):
            if key not in current_keys:
                self._states.pop(key, None)

        return result

    def status(self) -> Dict[str, Any]:
        """Снимок состояния для observability."""
        return {
            "watch_dir": self._config.watch_dir,
            "patterns": list(self._config.patterns),
            "tracked_files": len(self._states),
            "stabilization_checks": self._config.stabilization_checks,
            "stabilization_interval_s": self._config.stabilization_interval_s,
            "max_unstable_polls": self._config.max_unstable_polls,
        }

    def _iter_paths(self) -> Iterable[Path]:
        if self._list_files_fn is not None:
            for raw_path in self._list_files_fn():
                yield Path(raw_path)
            return

        base = Path(self._config.watch_dir)
        if not base.exists() or not base.is_dir():
            return
        for pattern in self._config.patterns:
            iterator = base.rglob(pattern) if self._config.recursive else base.glob(pattern)
            for path in iterator:
                if path.is_file():
                    yield path

    def _enqueue_ingest(self, path: Path, size: int, mtime: float) -> bool:
        seed = f"{path}:{size}:{mtime:.6f}"
        task_id = f"ingest_file_{sha256_text(seed, truncate=12)}"
        task = Task(
            task_id=task_id,
            task_type="ingest_file",
            payload={
                "path": str(path),
                "watch_dir": self._config.watch_dir,
                "stable_size": size,
                "stable_mtime": mtime,
            },
            priority=float(TaskPriority.LOW),
            trace_id=task_id,
            session_id=self._config.session_id,
        )
        enqueued = self._scheduler.enqueue(task, TaskPriority.LOW)
        if enqueued:
            logger.info("[FileWatcher] enqueue ingest_file: %s", path)
        return enqueued

    def _log_busy(self, path: Path, reason: str, exc: Optional[BaseException]) -> None:
        logger.warning("[FileWatcher] material skipped busy: %s (%s)", path, reason)
        self._blog.warn(
            "perception",
            "material_skipped_busy",
            session_id=self._config.session_id or "file_watcher",
            state={
                "path": str(path),
                "reason": reason,
                "error": str(exc) if exc is not None else "",
            },
        )

    @staticmethod
    def _default_readable_probe(path: Path) -> None:
        with path.open("rb") as handle:
            handle.read(0)
