"""
source_memory.py — Память об источниках (доверие и происхождение знаний).

Каждый факт должен иметь источник. Источники имеют разный уровень доверия.
Противоречия снижают доверие, подтверждения — повышают.

Принципы:
  - Trust score: 0.0 (ненадёжный) — 1.0 (абсолютно надёжный)
  - Decay: доверие затухает если источник давно не подтверждался
  - Provenance: каждый факт знает откуда он пришёл
  - Персистентность: JSON на диск
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .storage import MemoryDatabase


# ─── Запись об источнике ─────────────────────────────────────────────────────

@dataclass
class SourceRecord:
    """
    Запись о конкретном источнике знаний.

    Атрибуты:
        source_id       — уникальный ID источника (путь, URL, "user_input", ...)
        source_type     — тип источника ('file', 'url', 'user', 'system', 'inference')
        trust_score     — уровень доверия (0.0 — 1.0)
        confirmations   — сколько раз факты из источника подтверждались
        contradictions  — сколько раз факты из источника опровергались
        fact_count      — сколько фактов получено из источника
        first_seen_ts   — когда впервые встречен
        last_seen_ts    — когда последний раз встречен
        metadata        — дополнительные метаданные (автор, дата, язык, ...)
        blacklisted     — источник в чёрном списке (игнорировать)
    """
    source_id: str
    source_type: str = "file"           # 'file' | 'url' | 'user' | 'system' | 'inference'
    trust_score: float = 0.7            # начальное доверие
    confirmations: int = 0
    contradictions: int = 0
    fact_count: int = 0
    first_seen_ts: float = field(default_factory=time.time)
    last_seen_ts: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    blacklisted: bool = False

    def confirm(self, delta: float = 0.05):
        """Подтвердить источник — повысить доверие."""
        self.confirmations += 1
        self.trust_score = min(1.0, self.trust_score + delta)
        self.last_seen_ts = time.time()

    def contradict(self, delta: float = 0.1):
        """Опровергнуть источник — снизить доверие."""
        self.contradictions += 1
        self.trust_score = max(0.0, self.trust_score - delta)
        self.last_seen_ts = time.time()

    def decay(self, rate: float = 0.002):
        """
        Затухание доверия со временем.
        Источники, которые давно не подтверждались, теряют доверие.
        """
        days_since = (time.time() - self.last_seen_ts) / 86400
        if days_since > 7:  # затухание только если > 7 дней без активности
            self.trust_score = max(0.1, self.trust_score - rate * days_since)

    def reliability_ratio(self) -> float:
        """
        Соотношение подтверждений к противоречиям.
        Returns: 0.0 — 1.0
        """
        total = self.confirmations + self.contradictions
        if total == 0:
            return 0.5  # нейтральный
        return self.confirmations / total

    def is_reliable(self, threshold: float = 0.5) -> bool:
        """Является ли источник надёжным."""
        return not self.blacklisted and self.trust_score >= threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "trust_score": round(self.trust_score, 4),
            "confirmations": self.confirmations,
            "contradictions": self.contradictions,
            "fact_count": self.fact_count,
            "first_seen_ts": self.first_seen_ts,
            "last_seen_ts": self.last_seen_ts,
            "metadata": self.metadata,
            "blacklisted": self.blacklisted,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SourceRecord":
        return cls(
            source_id=d["source_id"],
            source_type=d.get("source_type", "file"),
            trust_score=d.get("trust_score", 0.7),
            confirmations=d.get("confirmations", 0),
            contradictions=d.get("contradictions", 0),
            fact_count=d.get("fact_count", 0),
            first_seen_ts=d.get("first_seen_ts", time.time()),
            last_seen_ts=d.get("last_seen_ts", time.time()),
            metadata=d.get("metadata", {}),
            blacklisted=d.get("blacklisted", False),
        )

    def __repr__(self) -> str:
        status = "🚫" if self.blacklisted else ("✅" if self.trust_score >= 0.7 else "⚠️")
        return (
            f"SourceRecord({status} '{self.source_id}' | "
            f"trust={self.trust_score:.2f} | "
            f"+{self.confirmations}/-{self.contradictions} | "
            f"facts={self.fact_count})"
        )


# ─── Память об источниках ────────────────────────────────────────────────────

class SourceMemory:
    """
    Память об источниках знаний — кто сказал что и насколько ему доверять.

    Параметры:
        data_path       — путь к JSON-файлу
        default_trust   — начальный уровень доверия для новых источников
        autosave_every  — автосохранение каждые N операций
    """

    # Предустановленные уровни доверия по типу источника
    DEFAULT_TRUST_BY_TYPE = {
        "system": 1.0,      # системные факты — абсолютное доверие
        "user": 0.8,        # пользователь — высокое доверие
        "file": 0.7,        # файлы — среднее доверие
        "url": 0.5,         # веб-источники — умеренное доверие
        "inference": 0.6,   # выводы системы — умеренное доверие
        "unknown": 0.4,     # неизвестный источник — низкое доверие
    }

    def __init__(
        self,
        data_path: str = "brain/data/memory/sources.json",
        default_trust: float = 0.7,
        autosave_every: int = 30,
        storage_backend: str = "auto",
        db: Optional["MemoryDatabase"] = None,
    ):
        self._data_path = data_path
        self._default_trust = default_trust
        self._autosave_every = autosave_every
        self._db = db

        # Определяем backend
        if storage_backend == "auto":
            self._backend = "sqlite" if db is not None else "json"
        else:
            self._backend = storage_backend

        self._sources: Dict[str, SourceRecord] = {}
        self._write_count = 0

        self._load()

    # ─── Основные операции ───────────────────────────────────────────────────

    def register(
        self,
        source_id: str,
        source_type: str = "file",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SourceRecord:
        """
        Зарегистрировать источник (или обновить время последнего обращения).

        Returns:
            SourceRecord — созданная или существующая запись
        """
        if source_id in self._sources:
            record = self._sources[source_id]
            record.last_seen_ts = time.time()
            return record

        # Начальное доверие по типу источника
        initial_trust = self.DEFAULT_TRUST_BY_TYPE.get(source_type, self._default_trust)

        record = SourceRecord(
            source_id=source_id,
            source_type=source_type,
            trust_score=initial_trust,
            metadata=metadata or {},
        )
        self._sources[source_id] = record
        self._write_count += 1
        self._maybe_autosave()
        return record

    def get_trust(self, source_id: str) -> float:
        """
        Получить уровень доверия к источнику.

        Returns:
            float: 0.0 — 1.0 (0.5 если источник неизвестен)
        """
        record = self._sources.get(source_id)
        if not record:
            return 0.5  # нейтральное доверие к неизвестному источнику
        if record.blacklisted:
            return 0.0
        return record.trust_score

    def get_record(self, source_id: str) -> Optional[SourceRecord]:
        """Получить полную запись об источнике."""
        return self._sources.get(source_id)

    def update_trust(
        self,
        source_id: str,
        confirmed: bool,
        delta: Optional[float] = None,
    ):
        """
        Обновить доверие к источнику.

        Args:
            source_id:  ID источника
            confirmed:  True = подтверждение, False = опровержение
            delta:      величина изменения (None = по умолчанию)
        """
        if source_id not in self._sources:
            self.register(source_id)

        record = self._sources[source_id]
        if confirmed:
            record.confirm(delta or 0.05)
        else:
            record.contradict(delta or 0.1)

        self._write_count += 1
        self._maybe_autosave()

    def add_fact(self, source_id: str):
        """Зафиксировать что из источника получен ещё один факт."""
        if source_id not in self._sources:
            self.register(source_id)
        self._sources[source_id].fact_count += 1

    def blacklist(self, source_id: str, reason: str = ""):
        """Добавить источник в чёрный список."""
        if source_id not in self._sources:
            self.register(source_id)
        record = self._sources[source_id]
        record.blacklisted = True
        record.trust_score = 0.0
        if reason:
            record.metadata["blacklist_reason"] = reason
        self._write_count += 1
        self._maybe_autosave()
        _logger.warning("Источник занесён в чёрный список: '%s' — %s", source_id, reason)

    def whitelist(self, source_id: str):
        """Убрать источник из чёрного списка."""
        if source_id in self._sources:
            record = self._sources[source_id]
            record.blacklisted = False
            record.trust_score = max(record.trust_score, 0.5)
            record.metadata.pop("blacklist_reason", None)

    def is_blacklisted(self, source_id: str) -> bool:
        """Проверить, в чёрном ли списке источник."""
        record = self._sources.get(source_id)
        return record.blacklisted if record else False

    def apply_decay(self, rate: float = 0.002):
        """Применить затухание доверия ко всем источникам."""
        for record in self._sources.values():
            if not record.blacklisted:
                record.decay(rate)

    # ─── Аналитика ───────────────────────────────────────────────────────────

    def get_reliable_sources(self, threshold: float = 0.7) -> List[SourceRecord]:
        """Получить список надёжных источников."""
        return [
            r for r in self._sources.values()
            if r.is_reliable(threshold)
        ]

    def get_unreliable_sources(self, threshold: float = 0.4) -> List[SourceRecord]:
        """Получить список ненадёжных источников."""
        return [
            r for r in self._sources.values()
            if r.trust_score < threshold and not r.blacklisted
        ]

    def get_most_trusted(self, top_n: int = 10) -> List[SourceRecord]:
        """Получить наиболее доверенные источники."""
        sources = [r for r in self._sources.values() if not r.blacklisted]
        sources.sort(key=lambda r: r.trust_score, reverse=True)
        return sources[:top_n]

    def get_most_productive(self, top_n: int = 10) -> List[SourceRecord]:
        """Получить источники с наибольшим количеством фактов."""
        sources = list(self._sources.values())
        sources.sort(key=lambda r: r.fact_count, reverse=True)
        return sources[:top_n]

    # ─── Персистентность ─────────────────────────────────────────────────────

    def save(self, path: Optional[str] = None):
        """Сохранить память об источниках (SQLite или JSON)."""
        if self._backend == "sqlite" and self._db is not None:
            self._save_sqlite()
        else:
            self._save_json(path)

    def _save_json(self, path: Optional[str] = None):
        """Сохранить память об источниках на диск (JSON)."""
        path = path or self._data_path
        os.makedirs(os.path.dirname(path), exist_ok=True)

        data = {
            "version": "1.0",
            "saved_ts": time.time(),
            "source_count": len(self._sources),
            "sources": {sid: rec.to_dict() for sid, rec in self._sources.items()},
        }

        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if os.path.exists(path):
            os.replace(tmp_path, path)
        else:
            os.rename(tmp_path, path)

        _logger.info("Память об источниках сохранена (JSON): %d источников -> %s", len(self._sources), path)

    def _save_sqlite(self):
        """Сохранить память об источниках в SQLite."""
        if self._db is None:
            return
        sources_data = [
            (sid, rec.to_dict()) for sid, rec in self._sources.items()
        ]
        self._db.save_all_sources(sources_data)
        _logger.info("Память об источниках сохранена (SQLite): %d источников", len(self._sources))

    def _load(self):
        """Загрузить память об источниках."""
        if self._backend == "sqlite" and self._db is not None:
            self._load_sqlite()
        else:
            self._load_json()

    def _load_json(self):
        """Загрузить память об источниках с диска (JSON)."""
        if not os.path.exists(self._data_path):
            return

        try:
            with open(self._data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for sid, rec_dict in data.get("sources", {}).items():
                self._sources[sid] = SourceRecord.from_dict(rec_dict)

            _logger.info("Память об источниках загружена (JSON): %d источников <- %s", len(self._sources), self._data_path)
        except Exception as e:
            _logger.warning("Ошибка загрузки памяти об источниках: %s", e)

    def _load_sqlite(self):
        """Загрузить память об источниках из SQLite."""
        if self._db is None:
            return
        try:
            rows = self._db.load_all_sources()
            for rec_dict in rows:
                self._sources[rec_dict["source_id"]] = SourceRecord.from_dict(rec_dict)
            _logger.info("Память об источниках загружена (SQLite): %d источников", len(self._sources))
        except Exception as e:
            _logger.warning("Ошибка загрузки памяти об источниках из SQLite: %s", e)

    def _maybe_autosave(self):
        if self._write_count % self._autosave_every == 0:
            self.save()

    # ─── Статистика ──────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Статус памяти об источниках."""
        records = list(self._sources.values())
        blacklisted = sum(1 for r in records if r.blacklisted)
        reliable = sum(1 for r in records if r.is_reliable())
        avg_trust = sum(r.trust_score for r in records) / len(records) if records else 0.0

        type_counts: Dict[str, int] = {}
        for r in records:
            type_counts[r.source_type] = type_counts.get(r.source_type, 0) + 1

        return {
            "type": "source_memory",
            "source_count": len(self._sources),
            "reliable_count": reliable,
            "blacklisted_count": blacklisted,
            "avg_trust_score": round(avg_trust, 3),
            "type_breakdown": type_counts,
            "write_count": self._write_count,
            "data_path": self._data_path,
        }

    def display_status(self):
        """Вывести статус в консоль."""
        s = self.status()
        print(f"\n{'─'*50}")
        print("🧠 Память об источниках")
        print(f"  Источников: {s['source_count']}")
        print(f"  Надёжных: {s['reliable_count']} | Заблокированных: {s['blacklisted_count']}")
        print(f"  Среднее доверие: {s['avg_trust_score']:.2%}")
        print(f"  По типам: {s['type_breakdown']}")
        print(f"{'─'*50}\n")

    def __len__(self) -> int:
        return len(self._sources)

    def __repr__(self) -> str:
        reliable = sum(1 for r in self._sources.values() if r.is_reliable())
        return f"SourceMemory(sources={len(self._sources)} | reliable={reliable})"
