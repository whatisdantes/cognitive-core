"""
brain/safety/source_trust.py — Высокоуровневая политика доверия к источникам.

Поверх SourceMemory: добавляет verified флаг и last_checked timestamp.
Делегирует в SourceMemory (не дублирует данные). Thread-safe (RLock).

Использование:
    mgr = SourceTrustManager(source_memory=sm)
    mgr.verify("wikipedia")
    mgr.update_trust("user_input", delta=-0.1)
    if not mgr.is_trusted("unknown_src"):
        ...
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

from brain.memory.source_memory import SourceMemory


@dataclass
class SourceTrustScore:
    """Оценка доверия к источнику с метаданными верификации."""

    source_id: str
    trust: float          # 0.0–1.0
    verified: bool        # явно верифицирован оператором
    last_checked: datetime


class SourceTrustManager:
    """
    Менеджер доверия к источникам.

    Хранит in-memory кэш SourceTrustScore.
    Делегирует изменения в SourceMemory (если передан).
    Thread-safe (RLock).

    Параметры:
        source_memory — опциональный SourceMemory для персистентности
    """

    DEFAULT_TRUST: float = 0.5
    VERIFIED_MIN_TRUST: float = 0.85

    def __init__(self, source_memory: Optional[SourceMemory] = None) -> None:
        self._source_memory = source_memory
        self._scores: Dict[str, SourceTrustScore] = {}
        self._lock = threading.RLock()

    def get_score(self, source_id: str) -> SourceTrustScore:
        """Получить оценку доверия (создаёт запись если нет)."""
        with self._lock:
            if source_id not in self._scores:
                trust = self.DEFAULT_TRUST
                if self._source_memory is not None:
                    record = self._source_memory.get_record(source_id)
                    if record is not None:
                        trust = record.trust_score
                self._scores[source_id] = SourceTrustScore(
                    source_id=source_id,
                    trust=trust,
                    verified=False,
                    last_checked=datetime.now(timezone.utc),
                )
            return self._scores[source_id]

    def update_trust(self, source_id: str, delta: float) -> None:
        """
        Изменить доверие на delta (clamp [0.0, 1.0]).

        delta > 0 → подтверждение, delta < 0 → опровержение.
        Делегирует в SourceMemory.update_trust(confirmed: bool).
        """
        with self._lock:
            score = self.get_score(source_id)
            score.trust = max(0.0, min(1.0, score.trust + delta))
            score.last_checked = datetime.now(timezone.utc)
            if self._source_memory is not None:
                try:
                    self._source_memory.update_trust(
                        source_id,
                        confirmed=delta >= 0,
                        delta=abs(delta),
                    )
                except Exception:  # noqa: BLE001
                    pass

    def verify(self, source_id: str) -> None:
        """Верифицировать источник: verified=True, trust >= VERIFIED_MIN_TRUST."""
        with self._lock:
            score = self.get_score(source_id)
            score.verified = True
            score.trust = max(score.trust, self.VERIFIED_MIN_TRUST)
            score.last_checked = datetime.now(timezone.utc)

    def unverify(self, source_id: str) -> None:
        """Снять верификацию (verified=False, trust не меняется)."""
        with self._lock:
            score = self.get_score(source_id)
            score.verified = False
            score.last_checked = datetime.now(timezone.utc)

    def is_trusted(self, source_id: str, threshold: float = 0.5) -> bool:
        """True если trust >= threshold и источник не в blacklist SourceMemory."""
        score = self.get_score(source_id)
        if self._source_memory is not None:
            if self._source_memory.is_blacklisted(source_id):
                return False
        return score.trust >= threshold

    def get_all_scores(self) -> List[SourceTrustScore]:
        """Все известные оценки (snapshot)."""
        with self._lock:
            return list(self._scores.values())
