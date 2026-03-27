"""
procedural_memory.py — Процедурная память (навыки, паттерны, стратегии).

Процедурная память — это "мышечная память" мозга:
автоматизированные цепочки действий, которые не нужно обдумывать каждый раз.

Принципы:
  - Procedure = именованная последовательность шагов
  - Success rate: успешные процедуры усиливаются, неуспешные — ослабляются
  - Caching: часто используемые процедуры кэшируются для быстрого доступа
  - Персистентность: JSON на диск
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .storage import MemoryDatabase


# ─── Шаг процедуры ───────────────────────────────────────────────────────────

@dataclass
class ProcedureStep:
    """Один шаг в процедуре."""
    action: str                         # название действия
    params: Dict[str, Any] = field(default_factory=dict)  # параметры
    expected_outcome: str = ""          # ожидаемый результат
    is_optional: bool = False           # опциональный шаг

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "params": self.params,
            "expected_outcome": self.expected_outcome,
            "is_optional": self.is_optional,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProcedureStep":
        return cls(
            action=d["action"],
            params=d.get("params", {}),
            expected_outcome=d.get("expected_outcome", ""),
            is_optional=d.get("is_optional", False),
        )


# ─── Процедура ───────────────────────────────────────────────────────────────

@dataclass
class Procedure:
    """
    Именованная процедура — последовательность шагов для достижения цели.

    Атрибуты:
        name            — уникальное имя процедуры
        description     — описание что делает процедура
        steps           — список шагов
        trigger_pattern — паттерн ситуации, при которой применяется
        success_rate    — доля успешных применений (0.0 — 1.0)
        use_count       — сколько раз применялась
        success_count   — сколько раз успешно
        fail_count      — сколько раз неуспешно
        avg_duration_ms — среднее время выполнения
        tags            — теги для поиска
        created_ts      — время создания
        last_used_ts    — время последнего использования
        priority        — приоритет (выше = применяется первой при конкуренции)
    """
    name: str
    description: str = ""
    steps: List[ProcedureStep] = field(default_factory=list)
    trigger_pattern: str = ""
    success_rate: float = 1.0
    use_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    avg_duration_ms: float = 0.0
    tags: List[str] = field(default_factory=list)
    created_ts: float = field(default_factory=time.time)
    last_used_ts: float = field(default_factory=time.time)
    priority: float = 0.5

    def record_use(self, success: bool, duration_ms: float = 0.0):
        """Зафиксировать использование процедуры."""
        self.use_count += 1
        self.last_used_ts = time.time()

        if success:
            self.success_count += 1
        else:
            self.fail_count += 1

        # Обновляем success_rate (скользящее среднее)
        total = self.success_count + self.fail_count
        self.success_rate = self.success_count / total if total > 0 else 0.0

        # Обновляем среднее время
        if duration_ms > 0:
            if self.avg_duration_ms == 0:
                self.avg_duration_ms = duration_ms
            else:
                self.avg_duration_ms = self.avg_duration_ms * 0.9 + duration_ms * 0.1

    def effectiveness_score(self) -> float:
        """
        Итоговая оценка эффективности процедуры.
        Учитывает success_rate, частоту использования и приоритет.
        """
        frequency_bonus = min(0.2, self.use_count / 100)  # бонус за частое использование
        return self.success_rate * 0.7 + self.priority * 0.2 + frequency_bonus

    def age_days(self) -> float:
        return (time.time() - self.created_ts) / 86400

    def days_since_used(self) -> float:
        return (time.time() - self.last_used_ts) / 86400

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "trigger_pattern": self.trigger_pattern,
            "success_rate": round(self.success_rate, 4),
            "use_count": self.use_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "tags": self.tags,
            "created_ts": self.created_ts,
            "last_used_ts": self.last_used_ts,
            "priority": round(self.priority, 4),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Procedure":
        proc = cls(
            name=d["name"],
            description=d.get("description", ""),
            trigger_pattern=d.get("trigger_pattern", ""),
            success_rate=d.get("success_rate", 1.0),
            use_count=d.get("use_count", 0),
            success_count=d.get("success_count", 0),
            fail_count=d.get("fail_count", 0),
            avg_duration_ms=d.get("avg_duration_ms", 0.0),
            tags=d.get("tags", []),
            created_ts=d.get("created_ts", time.time()),
            last_used_ts=d.get("last_used_ts", time.time()),
            priority=d.get("priority", 0.5),
        )
        proc.steps = [ProcedureStep.from_dict(s) for s in d.get("steps", [])]
        return proc

    def __repr__(self) -> str:
        return (
            f"Procedure('{self.name}' | "
            f"steps={len(self.steps)} | "
            f"success={self.success_rate:.0%} | "
            f"uses={self.use_count})"
        )


# ─── Процедурная память ──────────────────────────────────────────────────────

class ProceduralMemory:
    """
    Процедурная память — хранилище навыков и стратегий.

    Параметры:
        data_path       — путь к JSON-файлу
        autosave_every  — автосохранение каждые N операций
    """

    def __init__(
        self,
        data_path: str = "brain/data/memory/procedures.json",
        autosave_every: int = 20,
        storage_backend: str = "auto",
        db: Optional["MemoryDatabase"] = None,
    ):
        self._data_path = data_path
        self._autosave_every = autosave_every
        self._db = db

        # Определяем backend
        if storage_backend == "auto":
            self._backend = "sqlite" if db is not None else "json"
        else:
            self._backend = storage_backend

        self._procedures: Dict[str, Procedure] = {}
        self._write_count = 0

        self._load()

    # ─── Основные операции ───────────────────────────────────────────────────

    def store(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        description: str = "",
        trigger_pattern: str = "",
        tags: Optional[List[str]] = None,
        priority: float = 0.5,
    ) -> Procedure:
        """
        Сохранить процедуру.

        Args:
            name:            уникальное имя
            steps:           список шагов [{"action": ..., "params": ...}, ...]
            description:     описание
            trigger_pattern: паттерн ситуации
            tags:            теги
            priority:        приоритет (0.0 — 1.0)

        Returns:
            Procedure
        """
        procedure_steps = [
            ProcedureStep(
                action=s.get("action", ""),
                params=s.get("params", {}),
                expected_outcome=s.get("expected_outcome", ""),
                is_optional=s.get("is_optional", False),
            )
            for s in steps
        ]

        if name in self._procedures:
            # Обновляем существующую процедуру
            proc = self._procedures[name]
            proc.steps = procedure_steps
            proc.description = description or proc.description
            proc.trigger_pattern = trigger_pattern or proc.trigger_pattern
            if tags:
                proc.tags = list(set(proc.tags + tags))
            proc.priority = priority
        else:
            proc = Procedure(
                name=name,
                description=description,
                steps=procedure_steps,
                trigger_pattern=trigger_pattern,
                tags=tags or [],
                priority=priority,
            )
            self._procedures[name] = proc

        self._write_count += 1
        self._maybe_autosave()
        return proc

    def get(self, name: str) -> Optional[Procedure]:
        """Получить процедуру по имени."""
        return self._procedures.get(name)

    def retrieve(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        min_success_rate: float = 0.0,
        top_n: int = 5,
    ) -> List[Procedure]:
        """
        Найти подходящие процедуры.

        Args:
            query:            строка поиска (по имени, описанию, trigger_pattern)
            tags:             фильтр по тегам
            min_success_rate: минимальный success rate
            top_n:            максимальное количество результатов

        Returns:
            Список процедур, отсортированных по эффективности
        """
        query_lower = query.lower()
        results = []

        for proc in self._procedures.values():
            if proc.success_rate < min_success_rate:
                continue
            if tags and not any(t in proc.tags for t in tags):
                continue

            score = 0.0
            if query_lower in proc.name.lower():
                score += 0.5
            if query_lower in proc.description.lower():
                score += 0.3
            if query_lower in proc.trigger_pattern.lower():
                score += 0.4
            if any(query_lower in t for t in proc.tags):
                score += 0.2

            if score > 0:
                results.append((score * proc.effectiveness_score(), proc))

        results.sort(key=lambda x: x[0], reverse=True)
        return [proc for _, proc in results[:top_n]]

    def get_best(self, top_n: int = 5) -> List[Procedure]:
        """Получить наиболее эффективные процедуры."""
        procs = list(self._procedures.values())
        procs.sort(key=lambda p: p.effectiveness_score(), reverse=True)
        return procs[:top_n]

    def record_result(self, name: str, success: bool, duration_ms: float = 0.0):
        """Зафиксировать результат применения процедуры."""
        if name in self._procedures:
            self._procedures[name].record_use(success, duration_ms)
            self._write_count += 1
            self._maybe_autosave()

    def delete(self, name: str) -> bool:
        """Удалить процедуру."""
        if name in self._procedures:
            del self._procedures[name]
            return True
        return False

    def prune_ineffective(self, min_success_rate: float = 0.2, min_uses: int = 5):
        """
        Удалить неэффективные процедуры.
        Удаляет только те, что использовались достаточно раз и показали плохой результат.
        """
        to_delete = [
            name for name, proc in self._procedures.items()
            if proc.use_count >= min_uses and proc.success_rate < min_success_rate
        ]
        for name in to_delete:
            del self._procedures[name]
        if to_delete:
            _logger.info("Удалено %d неэффективных процедур", len(to_delete))
        return len(to_delete)

    # ─── Персистентность ─────────────────────────────────────────────────────

    def save(self, path: Optional[str] = None):
        """Сохранить процедурную память (SQLite или JSON)."""
        if self._backend == "sqlite" and self._db is not None:
            self._save_sqlite()
        else:
            self._save_json(path)

    def _save_json(self, path: Optional[str] = None):
        """Сохранить процедурную память на диск (JSON)."""
        path = path or self._data_path
        os.makedirs(os.path.dirname(path), exist_ok=True)

        data = {
            "version": "1.0",
            "saved_ts": time.time(),
            "procedure_count": len(self._procedures),
            "procedures": {name: proc.to_dict() for name, proc in self._procedures.items()},
        }

        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if os.path.exists(path):
            os.replace(tmp_path, path)
        else:
            os.rename(tmp_path, path)

        _logger.info("Процедурная память сохранена (JSON): %d процедур -> %s", len(self._procedures), path)

    def _save_sqlite(self):
        """Сохранить процедурную память в SQLite."""
        if self._db is None:
            return
        procs_data = [
            (name, proc.to_dict()) for name, proc in self._procedures.items()
        ]
        self._db.save_all_procedures(procs_data)
        _logger.info("Процедурная память сохранена (SQLite): %d процедур", len(self._procedures))

    def _load(self):
        """Загрузить процедурную память."""
        if self._backend == "sqlite" and self._db is not None:
            self._load_sqlite()
        else:
            self._load_json()

    def _load_json(self):
        """Загрузить процедурную память с диска (JSON)."""
        if not os.path.exists(self._data_path):
            return

        try:
            with open(self._data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for name, proc_dict in data.get("procedures", {}).items():
                self._procedures[name] = Procedure.from_dict(proc_dict)

            _logger.info(
                "Процедурная память загружена (JSON): %d процедур <- %s",
                len(self._procedures), self._data_path,
            )
        except Exception as e:
            _logger.warning("Ошибка загрузки процедурной памяти: %s", e)

    def _load_sqlite(self):
        """Загрузить процедурную память из SQLite."""
        if self._db is None:
            return
        try:
            rows = self._db.load_all_procedures()
            for proc_dict in rows:
                self._procedures[proc_dict["name"]] = Procedure.from_dict(proc_dict)
            _logger.info("Процедурная память загружена (SQLite): %d процедур", len(self._procedures))
        except Exception as e:
            _logger.warning("Ошибка загрузки процедурной памяти из SQLite: %s", e)

    def _maybe_autosave(self):
        if self._write_count % self._autosave_every == 0:
            self.save()

    # ─── Статистика ──────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Статус процедурной памяти."""
        procs = list(self._procedures.values())
        avg_success = sum(p.success_rate for p in procs) / len(procs) if procs else 0.0
        total_uses = sum(p.use_count for p in procs)

        return {
            "type": "procedural_memory",
            "procedure_count": len(self._procedures),
            "avg_success_rate": round(avg_success, 3),
            "total_uses": total_uses,
            "write_count": self._write_count,
            "data_path": self._data_path,
        }

    def display_status(self):
        """Вывести статус в консоль."""
        s = self.status()
        print(f"\n{'─'*50}")
        print("🧠 Процедурная память")
        print(f"  Процедур: {s['procedure_count']}")
        print(f"  Средний success rate: {s['avg_success_rate']:.2%}")
        print(f"  Всего применений: {s['total_uses']}")
        print(f"{'─'*50}\n")

    def __len__(self) -> int:
        return len(self._procedures)

    def __repr__(self) -> str:
        return f"ProceduralMemory(procedures={len(self._procedures)})"
