"""
storage.py — SQLite persistence backend для системы памяти.

MemoryDatabase — единая точка доступа к SQLite:
  - Один .db файл для всех видов памяти
  - WAL mode для лучшего concurrent read
  - RLock для thread safety
  - Транзакционный API (begin/commit/rollback)
  - Schema versioning через _meta таблицу

Использование:
    db = MemoryDatabase("brain/data/memory/memory.db")
    db.upsert_semantic_node(concept, data_dict)
    db.commit()
    db.close()
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)

# ─── Версия схемы ────────────────────────────────────────────────────────────

SCHEMA_VERSION = 1


# ─── SQL для создания таблиц ─────────────────────────────────────────────────

_CREATE_TABLES_SQL = """
-- Метаданные схемы
CREATE TABLE IF NOT EXISTS _meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ═══════════════════════════════════════════════════════
-- Семантическая память
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS semantic_nodes (
    concept       TEXT PRIMARY KEY,
    description   TEXT NOT NULL DEFAULT '',
    tags          TEXT NOT NULL DEFAULT '[]',          -- JSON array
    confidence    REAL NOT NULL DEFAULT 1.0,
    importance    REAL NOT NULL DEFAULT 0.5,
    source_refs   TEXT NOT NULL DEFAULT '[]',          -- JSON array
    access_count  INTEGER NOT NULL DEFAULT 0,
    confirm_count INTEGER NOT NULL DEFAULT 0,
    deny_count    INTEGER NOT NULL DEFAULT 0,
    created_ts    REAL NOT NULL,
    updated_ts    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_semantic_confidence ON semantic_nodes(confidence);
CREATE INDEX IF NOT EXISTS idx_semantic_importance ON semantic_nodes(importance);
CREATE INDEX IF NOT EXISTS idx_semantic_updated    ON semantic_nodes(updated_ts);

CREATE TABLE IF NOT EXISTS relations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,                         -- concept (FK)
    target      TEXT NOT NULL,
    weight      REAL NOT NULL DEFAULT 0.5,
    rel_type    TEXT NOT NULL DEFAULT 'related',
    confidence  REAL NOT NULL DEFAULT 1.0,
    source_ref  TEXT NOT NULL DEFAULT '',
    ts          REAL NOT NULL,
    UNIQUE(source, target, rel_type)
);

CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target);

-- ═══════════════════════════════════════════════════════
-- Эпизодическая память
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS episodes (
    episode_id    TEXT PRIMARY KEY,
    ts            REAL NOT NULL,
    content       TEXT NOT NULL DEFAULT '',
    modality      TEXT NOT NULL DEFAULT 'text',
    source        TEXT NOT NULL DEFAULT '',
    importance    REAL NOT NULL DEFAULT 0.5,
    confidence    REAL NOT NULL DEFAULT 1.0,
    tags          TEXT NOT NULL DEFAULT '[]',           -- JSON array
    concepts      TEXT NOT NULL DEFAULT '[]',           -- JSON array
    trace_id      TEXT NOT NULL DEFAULT '',
    session_id    TEXT NOT NULL DEFAULT '',
    access_count  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_episodes_ts         ON episodes(ts);
CREATE INDEX IF NOT EXISTS idx_episodes_importance  ON episodes(importance);
CREATE INDEX IF NOT EXISTS idx_episodes_session     ON episodes(session_id);
CREATE INDEX IF NOT EXISTS idx_episodes_trace       ON episodes(trace_id);

CREATE TABLE IF NOT EXISTS modal_evidence (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id   TEXT NOT NULL,
    modality     TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT '',
    content_ref  TEXT NOT NULL DEFAULT '',
    confidence   REAL NOT NULL DEFAULT 1.0,
    metadata     TEXT NOT NULL DEFAULT '{}',            -- JSON object
    FOREIGN KEY (episode_id) REFERENCES episodes(episode_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_evidence_episode ON modal_evidence(episode_id);

-- ═══════════════════════════════════════════════════════
-- Память об источниках
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS sources (
    source_id       TEXT PRIMARY KEY,
    source_type     TEXT NOT NULL DEFAULT 'file',
    trust_score     REAL NOT NULL DEFAULT 0.7,
    confirmations   INTEGER NOT NULL DEFAULT 0,
    contradictions  INTEGER NOT NULL DEFAULT 0,
    fact_count      INTEGER NOT NULL DEFAULT 0,
    first_seen_ts   REAL NOT NULL,
    last_seen_ts    REAL NOT NULL,
    metadata        TEXT NOT NULL DEFAULT '{}',         -- JSON object
    blacklisted     INTEGER NOT NULL DEFAULT 0          -- boolean
);

CREATE INDEX IF NOT EXISTS idx_sources_trust ON sources(trust_score);

-- ═══════════════════════════════════════════════════════
-- Процедурная память
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS procedures (
    name            TEXT PRIMARY KEY,
    description     TEXT NOT NULL DEFAULT '',
    trigger_pattern TEXT NOT NULL DEFAULT '',
    success_rate    REAL NOT NULL DEFAULT 1.0,
    use_count       INTEGER NOT NULL DEFAULT 0,
    success_count   INTEGER NOT NULL DEFAULT 0,
    fail_count      INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms REAL NOT NULL DEFAULT 0.0,
    tags            TEXT NOT NULL DEFAULT '[]',         -- JSON array
    created_ts      REAL NOT NULL,
    last_used_ts    REAL NOT NULL,
    priority        REAL NOT NULL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS procedure_steps (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    procedure_name   TEXT NOT NULL,
    step_order       INTEGER NOT NULL,
    action           TEXT NOT NULL,
    params           TEXT NOT NULL DEFAULT '{}',        -- JSON object
    expected_outcome TEXT NOT NULL DEFAULT '',
    is_optional      INTEGER NOT NULL DEFAULT 0,        -- boolean
    FOREIGN KEY (procedure_name) REFERENCES procedures(name) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_steps_procedure ON procedure_steps(procedure_name);
"""


# ─── MemoryDatabase ──────────────────────────────────────────────────────────

class MemoryDatabase:
    """
    SQLite persistence backend для всей системы памяти.

    Thread-safe через RLock. WAL mode для concurrent reads.
    Единый .db файл для всех видов памяти.

    Параметры:
        db_path:  путь к файлу базы данных (или ":memory:" для тестов)
        wal_mode: включить WAL mode (рекомендуется для production)
    """

    def __init__(self, db_path: str = "brain/data/memory/memory.db", wal_mode: bool = True):
        self._db_path = db_path
        self._lock = threading.RLock()
        self._closed = False

        # Создаём директорию если нужно
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        # Открываем соединение
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            timeout=10.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

        if wal_mode and db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")

        # Создаём таблицы
        self._init_schema()

        _logger.info("MemoryDatabase открыта: %s (schema v%d)", db_path, SCHEMA_VERSION)

    # ─── Schema ──────────────────────────────────────────────────────────────

    def _init_schema(self):
        """Создать таблицы и проверить версию схемы."""
        with self._lock:
            self._conn.executescript(_CREATE_TABLES_SQL)

            # Проверяем/устанавливаем версию
            row = self._conn.execute(
                "SELECT value FROM _meta WHERE key = 'schema_version'"
            ).fetchone()

            if row is None:
                self._conn.execute(
                    "INSERT INTO _meta (key, value) VALUES (?, ?)",
                    ("schema_version", str(SCHEMA_VERSION)),
                )
                self._conn.execute(
                    "INSERT OR IGNORE INTO _meta (key, value) VALUES (?, ?)",
                    ("created_ts", str(time.time())),
                )
                self._conn.commit()
            else:
                existing_version = int(row["value"])
                if existing_version < SCHEMA_VERSION:
                    self._migrate_schema(existing_version, SCHEMA_VERSION)

    def _migrate_schema(self, from_version: int, to_version: int):
        """Миграция схемы между версиями (заглушка для будущих миграций)."""
        _logger.info(
            "Миграция схемы: v%d → v%d", from_version, to_version
        )
        # Будущие миграции добавляются здесь
        self._conn.execute(
            "UPDATE _meta SET value = ? WHERE key = 'schema_version'",
            (str(to_version),),
        )
        self._conn.commit()

    @property
    def schema_version(self) -> int:
        """Текущая версия схемы."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM _meta WHERE key = 'schema_version'"
            ).fetchone()
            return int(row["value"]) if row else 0

    # ─── Transaction API ─────────────────────────────────────────────────────

    def begin(self):
        """Начать транзакцию (идемпотентно — пропускает если уже в транзакции)."""
        with self._lock:
            if not self._conn.in_transaction:
                self._conn.execute("BEGIN")

    def commit(self):
        """Зафиксировать транзакцию."""
        with self._lock:
            self._conn.commit()

    def rollback(self):
        """Откатить транзакцию."""
        with self._lock:
            self._conn.rollback()

    def close(self):
        """Закрыть соединение с БД."""
        if self._closed:
            return
        with self._lock:
            try:
                self._conn.commit()
                self._conn.close()
            except Exception as e:
                _logger.warning("Ошибка при закрытии БД: %s", e)
            self._closed = True
            _logger.info("MemoryDatabase закрыта: %s", self._db_path)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def db_path(self) -> str:
        return self._db_path

    # ═══════════════════════════════════════════════════════
    # SEMANTIC NODES
    # ═══════════════════════════════════════════════════════

    def upsert_semantic_node(self, concept: str, data: Dict[str, Any]):
        """
        Вставить или обновить узел семантической памяти.

        Args:
            concept: ключ понятия (нормализованный)
            data: словарь из SemanticNode.to_dict()
        """
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO semantic_nodes
                    (concept, description, tags, confidence, importance,
                     source_refs, access_count, confirm_count, deny_count,
                     created_ts, updated_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(concept) DO UPDATE SET
                    description   = excluded.description,
                    tags          = excluded.tags,
                    confidence    = excluded.confidence,
                    importance    = excluded.importance,
                    source_refs   = excluded.source_refs,
                    access_count  = excluded.access_count,
                    confirm_count = excluded.confirm_count,
                    deny_count    = excluded.deny_count,
                    updated_ts    = excluded.updated_ts
                """,
                (
                    concept,
                    data.get("description", ""),
                    json.dumps(data.get("tags", []), ensure_ascii=False),
                    data.get("confidence", 1.0),
                    data.get("importance", 0.5),
                    json.dumps(data.get("source_refs", []), ensure_ascii=False),
                    data.get("access_count", 0),
                    data.get("confirm_count", 0),
                    data.get("deny_count", 0),
                    data.get("created_ts", time.time()),
                    data.get("updated_ts", time.time()),
                ),
            )

    def load_all_semantic_nodes(self) -> List[Dict[str, Any]]:
        """Загрузить все узлы семантической памяти."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM semantic_nodes").fetchall()
            result = []
            for row in rows:
                node_dict = dict(row)
                node_dict["tags"] = json.loads(node_dict["tags"])
                node_dict["source_refs"] = json.loads(node_dict["source_refs"])
                # Загружаем связи для этого узла
                node_dict["relations"] = self._load_relations_for(node_dict["concept"])
                result.append(node_dict)
            return result

    def delete_semantic_node(self, concept: str):
        """Удалить узел и его связи."""
        with self._lock:
            self._conn.execute("DELETE FROM relations WHERE source = ?", (concept,))
            self._conn.execute("DELETE FROM relations WHERE target = ?", (concept,))
            self._conn.execute("DELETE FROM semantic_nodes WHERE concept = ?", (concept,))

    def get_semantic_node_count(self) -> int:
        """Количество узлов."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) as cnt FROM semantic_nodes").fetchone()
            return int(row["cnt"])

    # ─── Relations ───────────────────────────────────────────────────────────

    def upsert_relation(self, source: str, target: str, data: Dict[str, Any]):
        """Вставить или обновить связь."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO relations (source, target, weight, rel_type, confidence, source_ref, ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, target, rel_type) DO UPDATE SET
                    weight     = excluded.weight,
                    confidence = excluded.confidence,
                    source_ref = excluded.source_ref,
                    ts         = excluded.ts
                """,
                (
                    source,
                    target,
                    data.get("weight", 0.5),
                    data.get("rel_type", "related"),
                    data.get("confidence", 1.0),
                    data.get("source_ref", ""),
                    data.get("ts", time.time()),
                ),
            )

    def _load_relations_for(self, concept: str) -> List[Dict[str, Any]]:
        """Загрузить все связи для узла."""
        rows = self._conn.execute(
            "SELECT target, weight, rel_type, confidence, source_ref, ts "
            "FROM relations WHERE source = ?",
            (concept,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_relations_for(self, concept: str):
        """Удалить все связи узла (исходящие)."""
        with self._lock:
            self._conn.execute("DELETE FROM relations WHERE source = ?", (concept,))

    # ═══════════════════════════════════════════════════════
    # EPISODES
    # ═══════════════════════════════════════════════════════

    def upsert_episode(self, episode_id: str, data: Dict[str, Any]):
        """Вставить или обновить эпизод."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO episodes
                    (episode_id, ts, content, modality, source, importance,
                     confidence, tags, concepts, trace_id, session_id, access_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(episode_id) DO UPDATE SET
                    content      = excluded.content,
                    importance   = excluded.importance,
                    confidence   = excluded.confidence,
                    tags         = excluded.tags,
                    concepts     = excluded.concepts,
                    access_count = excluded.access_count
                """,
                (
                    episode_id,
                    data.get("ts", time.time()),
                    data.get("content", ""),
                    data.get("modality", "text"),
                    data.get("source", ""),
                    data.get("importance", 0.5),
                    data.get("confidence", 1.0),
                    json.dumps(data.get("tags", []), ensure_ascii=False),
                    json.dumps(data.get("concepts", []), ensure_ascii=False),
                    data.get("trace_id", ""),
                    data.get("session_id", ""),
                    data.get("access_count", 0),
                ),
            )

            # Modal evidence
            self._conn.execute(
                "DELETE FROM modal_evidence WHERE episode_id = ?", (episode_id,)
            )
            for ev in data.get("modal_evidence", []):
                self._conn.execute(
                    """
                    INSERT INTO modal_evidence
                        (episode_id, modality, source, content_ref, confidence, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode_id,
                        ev.get("modality", ""),
                        ev.get("source", ""),
                        ev.get("content_ref", ""),
                        ev.get("confidence", 1.0),
                        json.dumps(ev.get("metadata", {}), ensure_ascii=False),
                    ),
                )

    def load_all_episodes(self) -> List[Dict[str, Any]]:
        """Загрузить все эпизоды."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM episodes ORDER BY ts ASC"
            ).fetchall()
            result = []
            for row in rows:
                ep = dict(row)
                ep["tags"] = json.loads(ep["tags"])
                ep["concepts"] = json.loads(ep["concepts"])
                ep["modal_evidence"] = self._load_evidence_for(ep["episode_id"])
                result.append(ep)
            return result

    def _load_evidence_for(self, episode_id: str) -> List[Dict[str, Any]]:
        """Загрузить modal evidence для эпизода."""
        rows = self._conn.execute(
            "SELECT modality, source, content_ref, confidence, metadata "
            "FROM modal_evidence WHERE episode_id = ?",
            (episode_id,),
        ).fetchall()
        evidence = []
        for r in rows:
            ev = dict(r)
            ev["metadata"] = json.loads(ev["metadata"])
            evidence.append(ev)
        return evidence

    def delete_episode(self, episode_id: str):
        """Удалить эпизод и его evidence."""
        with self._lock:
            self._conn.execute("DELETE FROM modal_evidence WHERE episode_id = ?", (episode_id,))
            self._conn.execute("DELETE FROM episodes WHERE episode_id = ?", (episode_id,))

    def get_episode_count(self) -> int:
        """Количество эпизодов."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) as cnt FROM episodes").fetchone()
            return int(row["cnt"])

    # ═══════════════════════════════════════════════════════
    # SOURCES
    # ═══════════════════════════════════════════════════════

    def upsert_source(self, source_id: str, data: Dict[str, Any]):
        """Вставить или обновить источник."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sources
                    (source_id, source_type, trust_score, confirmations,
                     contradictions, fact_count, first_seen_ts, last_seen_ts,
                     metadata, blacklisted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_type    = excluded.source_type,
                    trust_score    = excluded.trust_score,
                    confirmations  = excluded.confirmations,
                    contradictions = excluded.contradictions,
                    fact_count     = excluded.fact_count,
                    last_seen_ts   = excluded.last_seen_ts,
                    metadata       = excluded.metadata,
                    blacklisted    = excluded.blacklisted
                """,
                (
                    source_id,
                    data.get("source_type", "file"),
                    data.get("trust_score", 0.7),
                    data.get("confirmations", 0),
                    data.get("contradictions", 0),
                    data.get("fact_count", 0),
                    data.get("first_seen_ts", time.time()),
                    data.get("last_seen_ts", time.time()),
                    json.dumps(data.get("metadata", {}), ensure_ascii=False),
                    1 if data.get("blacklisted", False) else 0,
                ),
            )

    def load_all_sources(self) -> List[Dict[str, Any]]:
        """Загрузить все источники."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM sources").fetchall()
            result = []
            for row in rows:
                src = dict(row)
                src["metadata"] = json.loads(src["metadata"])
                src["blacklisted"] = bool(src["blacklisted"])
                result.append(src)
            return result

    def delete_source(self, source_id: str):
        """Удалить источник."""
        with self._lock:
            self._conn.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))

    def get_source_count(self) -> int:
        """Количество источников."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) as cnt FROM sources").fetchone()
            return int(row["cnt"])

    # ═══════════════════════════════════════════════════════
    # PROCEDURES
    # ═══════════════════════════════════════════════════════

    def upsert_procedure(self, name: str, data: Dict[str, Any]):
        """Вставить или обновить процедуру."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO procedures
                    (name, description, trigger_pattern, success_rate,
                     use_count, success_count, fail_count, avg_duration_ms,
                     tags, created_ts, last_used_ts, priority)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description     = excluded.description,
                    trigger_pattern = excluded.trigger_pattern,
                    success_rate    = excluded.success_rate,
                    use_count       = excluded.use_count,
                    success_count   = excluded.success_count,
                    fail_count      = excluded.fail_count,
                    avg_duration_ms = excluded.avg_duration_ms,
                    tags            = excluded.tags,
                    last_used_ts    = excluded.last_used_ts,
                    priority        = excluded.priority
                """,
                (
                    name,
                    data.get("description", ""),
                    data.get("trigger_pattern", ""),
                    data.get("success_rate", 1.0),
                    data.get("use_count", 0),
                    data.get("success_count", 0),
                    data.get("fail_count", 0),
                    data.get("avg_duration_ms", 0.0),
                    json.dumps(data.get("tags", []), ensure_ascii=False),
                    data.get("created_ts", time.time()),
                    data.get("last_used_ts", time.time()),
                    data.get("priority", 0.5),
                ),
            )

            # Steps: удаляем старые и вставляем новые
            self._conn.execute(
                "DELETE FROM procedure_steps WHERE procedure_name = ?", (name,)
            )
            for i, step in enumerate(data.get("steps", [])):
                self._conn.execute(
                    """
                    INSERT INTO procedure_steps
                        (procedure_name, step_order, action, params,
                         expected_outcome, is_optional)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        i,
                        step.get("action", ""),
                        json.dumps(step.get("params", {}), ensure_ascii=False),
                        step.get("expected_outcome", ""),
                        1 if step.get("is_optional", False) else 0,
                    ),
                )

    def load_all_procedures(self) -> List[Dict[str, Any]]:
        """Загрузить все процедуры."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM procedures").fetchall()
            result = []
            for row in rows:
                proc = dict(row)
                proc["tags"] = json.loads(proc["tags"])
                proc["steps"] = self._load_steps_for(proc["name"])
                result.append(proc)
            return result

    def _load_steps_for(self, procedure_name: str) -> List[Dict[str, Any]]:
        """Загрузить шаги процедуры."""
        rows = self._conn.execute(
            "SELECT action, params, expected_outcome, is_optional "
            "FROM procedure_steps WHERE procedure_name = ? ORDER BY step_order",
            (procedure_name,),
        ).fetchall()
        steps = []
        for r in rows:
            step = dict(r)
            step["params"] = json.loads(step["params"])
            step["is_optional"] = bool(step["is_optional"])
            steps.append(step)
        return steps

    def delete_procedure(self, name: str):
        """Удалить процедуру и её шаги."""
        with self._lock:
            self._conn.execute("DELETE FROM procedure_steps WHERE procedure_name = ?", (name,))
            self._conn.execute("DELETE FROM procedures WHERE name = ?", (name,))

    def get_procedure_count(self) -> int:
        """Количество процедур."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) as cnt FROM procedures").fetchone()
            return int(row["cnt"])

    # ═══════════════════════════════════════════════════════
    # BULK OPERATIONS
    # ═══════════════════════════════════════════════════════

    def save_all_semantic(self, nodes: List[Tuple[str, Dict[str, Any]]]):
        """
        Сохранить все узлы семантической памяти (bulk).

        Args:
            nodes: список (concept, node.to_dict())
        """
        with self._lock:
            for concept, data in nodes:
                self.upsert_semantic_node(concept, data)
                # Связи
                self.delete_relations_for(concept)
                for rel in data.get("relations", []):
                    self.upsert_relation(concept, rel["target"], rel)

    def save_all_episodes(self, episodes: List[Dict[str, Any]]):
        """Сохранить все эпизоды (bulk)."""
        with self._lock:
            for ep in episodes:
                self.upsert_episode(ep["episode_id"], ep)

    def save_all_sources(self, sources: List[Tuple[str, Dict[str, Any]]]):
        """Сохранить все источники (bulk)."""
        with self._lock:
            for source_id, data in sources:
                self.upsert_source(source_id, data)

    def save_all_procedures(self, procedures: List[Tuple[str, Dict[str, Any]]]):
        """Сохранить все процедуры (bulk)."""
        with self._lock:
            for name, data in procedures:
                self.upsert_procedure(name, data)

    # ═══════════════════════════════════════════════════════
    # META & STATS
    # ═══════════════════════════════════════════════════════

    def get_meta(self, key: str) -> Optional[str]:
        """Получить значение из _meta."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM _meta WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def set_meta(self, key: str, value: str):
        """Установить значение в _meta."""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO _meta (key, value) VALUES (?, ?)",
                (key, value),
            )

    def table_counts(self) -> Dict[str, int]:
        """Количество записей в каждой таблице."""
        with self._lock:
            counts = {}
            for table in ("semantic_nodes", "relations", "episodes",
                          "modal_evidence", "sources", "procedures", "procedure_steps"):
                row = self._conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()  # noqa: S608
                counts[table] = row["cnt"]
            return counts

    def status(self) -> Dict[str, Any]:
        """Полный статус базы данных."""
        return {
            "db_path": self._db_path,
            "schema_version": self.schema_version,
            "closed": self._closed,
            "counts": self.table_counts(),
        }

    # ─── Представление ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"MemoryDatabase('{self._db_path}', closed={self._closed})"

    def __del__(self):
        """Попытка закрыть при сборке мусора."""
        if not self._closed:
            try:
                self.close()
            except Exception:
                pass
