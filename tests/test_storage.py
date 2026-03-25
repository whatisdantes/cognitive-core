"""
test_storage.py — Тесты для SQLite persistence backend (MemoryDatabase).

Покрывает:
  - Создание БД (in-memory и файловая)
  - Schema versioning
  - CRUD для semantic_nodes, relations, episodes, sources, procedures
  - Bulk operations
  - Transaction API (begin/commit/rollback)
  - Meta API
  - Thread safety (базовый)
  - Интеграция с memory модулями (sqlite backend)
"""

from __future__ import annotations

import json
import os
import time
import threading
import pytest

from brain.memory.storage import MemoryDatabase, SCHEMA_VERSION


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def db():
    """In-memory MemoryDatabase для тестов."""
    database = MemoryDatabase(db_path=":memory:", wal_mode=False)
    yield database
    database.close()


@pytest.fixture
def file_db(tmp_path):
    """File-based MemoryDatabase для тестов."""
    db_path = str(tmp_path / "test_memory.db")
    database = MemoryDatabase(db_path=db_path)
    yield database
    database.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Schema & Init
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryDatabaseInit:
    """Тесты инициализации БД."""

    def test_in_memory_creation(self, db):
        assert not db.closed
        assert db.db_path == ":memory:"

    def test_file_creation(self, file_db):
        assert not file_db.closed
        assert os.path.exists(file_db.db_path)

    def test_schema_version(self, db):
        assert db.schema_version == SCHEMA_VERSION

    def test_table_counts_empty(self, db):
        counts = db.table_counts()
        assert counts["semantic_nodes"] == 0
        assert counts["relations"] == 0
        assert counts["episodes"] == 0
        assert counts["sources"] == 0
        assert counts["procedures"] == 0

    def test_status(self, db):
        status = db.status()
        assert status["schema_version"] == SCHEMA_VERSION
        assert status["closed"] is False
        assert "counts" in status

    def test_repr(self, db):
        r = repr(db)
        assert "MemoryDatabase" in r

    def test_close_idempotent(self, db):
        db.close()
        assert db.closed
        db.close()  # второй раз — без ошибки
        assert db.closed

    def test_creates_directory(self, tmp_path):
        nested = str(tmp_path / "a" / "b" / "c" / "test.db")
        database = MemoryDatabase(db_path=nested)
        assert os.path.exists(nested)
        database.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Semantic Nodes
# ═══════════════════════════════════════════════════════════════════════════════

class TestSemanticNodes:
    """Тесты CRUD для semantic_nodes."""

    def _make_node(self, concept="нейрон", **overrides):
        data = {
            "description": "клетка нервной системы",
            "tags": ["биология", "нейронаука"],
            "confidence": 0.95,
            "importance": 0.8,
            "source_refs": ["учебник"],
            "access_count": 3,
            "confirm_count": 2,
            "deny_count": 0,
            "created_ts": time.time(),
            "updated_ts": time.time(),
            "relations": [],
        }
        data.update(overrides)
        return concept, data

    def test_upsert_and_load(self, db):
        concept, data = self._make_node()
        db.upsert_semantic_node(concept, data)
        db.commit()

        nodes = db.load_all_semantic_nodes()
        assert len(nodes) == 1
        assert nodes[0]["concept"] == "нейрон"
        assert nodes[0]["description"] == "клетка нервной системы"
        assert nodes[0]["confidence"] == 0.95
        assert "биология" in nodes[0]["tags"]

    def test_upsert_updates_existing(self, db):
        concept, data = self._make_node()
        db.upsert_semantic_node(concept, data)
        db.commit()

        data["description"] = "обновлённое описание"
        data["confidence"] = 0.99
        db.upsert_semantic_node(concept, data)
        db.commit()

        nodes = db.load_all_semantic_nodes()
        assert len(nodes) == 1
        assert nodes[0]["description"] == "обновлённое описание"
        assert nodes[0]["confidence"] == 0.99

    def test_delete_node(self, db):
        concept, data = self._make_node()
        db.upsert_semantic_node(concept, data)
        db.commit()

        db.delete_semantic_node(concept)
        db.commit()

        assert db.get_semantic_node_count() == 0

    def test_node_count(self, db):
        for i in range(5):
            c, d = self._make_node(concept=f"concept_{i}")
            db.upsert_semantic_node(c, d)
        db.commit()
        assert db.get_semantic_node_count() == 5

    def test_bulk_save(self, db):
        nodes = []
        for i in range(10):
            c, d = self._make_node(concept=f"bulk_{i}")
            nodes.append((c, d))
        db.save_all_semantic(nodes)
        db.commit()
        assert db.get_semantic_node_count() == 10


# ═══════════════════════════════════════════════════════════════════════════════
# Relations
# ═══════════════════════════════════════════════════════════════════════════════

class TestRelations:
    """Тесты для связей между узлами."""

    def test_upsert_relation(self, db):
        # Создаём два узла
        now = time.time()
        db.upsert_semantic_node("нейрон", {
            "description": "клетка", "tags": [], "confidence": 1.0,
            "importance": 0.5, "source_refs": [], "access_count": 0,
            "confirm_count": 0, "deny_count": 0,
            "created_ts": now, "updated_ts": now,
        })
        db.upsert_semantic_node("синапс", {
            "description": "соединение", "tags": [], "confidence": 1.0,
            "importance": 0.5, "source_refs": [], "access_count": 0,
            "confirm_count": 0, "deny_count": 0,
            "created_ts": now, "updated_ts": now,
        })

        db.upsert_relation("нейрон", "синапс", {
            "weight": 0.8,
            "rel_type": "has_part",
            "confidence": 0.9,
            "source_ref": "учебник",
            "ts": now,
        })
        db.commit()

        nodes = db.load_all_semantic_nodes()
        neuron = [n for n in nodes if n["concept"] == "нейрон"][0]
        assert len(neuron["relations"]) == 1
        assert neuron["relations"][0]["target"] == "синапс"
        assert neuron["relations"][0]["weight"] == 0.8

    def test_delete_relations(self, db):
        now = time.time()
        db.upsert_semantic_node("a", {
            "description": "", "tags": [], "confidence": 1.0,
            "importance": 0.5, "source_refs": [], "access_count": 0,
            "confirm_count": 0, "deny_count": 0,
            "created_ts": now, "updated_ts": now,
        })
        db.upsert_relation("a", "b", {"weight": 0.5, "rel_type": "related", "confidence": 1.0, "ts": now})
        db.upsert_relation("a", "c", {"weight": 0.3, "rel_type": "related", "confidence": 1.0, "ts": now})
        db.commit()

        db.delete_relations_for("a")
        db.commit()

        nodes = db.load_all_semantic_nodes()
        a_node = [n for n in nodes if n["concept"] == "a"][0]
        assert len(a_node["relations"]) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Episodes
# ═══════════════════════════════════════════════════════════════════════════════

class TestEpisodes:
    """Тесты CRUD для episodes."""

    def _make_episode(self, episode_id="ep_001", **overrides):
        data = {
            "episode_id": episode_id,
            "ts": time.time(),
            "content": "пользователь спросил о нейронах",
            "modality": "text",
            "source": "user_input",
            "importance": 0.7,
            "confidence": 1.0,
            "tags": ["вопрос", "нейронаука"],
            "concepts": ["нейрон"],
            "trace_id": "trace_001",
            "session_id": "session_001",
            "access_count": 0,
            "modal_evidence": [
                {
                    "modality": "text",
                    "source": "user",
                    "content_ref": "input_001",
                    "confidence": 1.0,
                    "metadata": {"lang": "ru"},
                }
            ],
        }
        data.update(overrides)
        return data

    def test_upsert_and_load(self, db):
        ep = self._make_episode()
        db.upsert_episode(ep["episode_id"], ep)
        db.commit()

        episodes = db.load_all_episodes()
        assert len(episodes) == 1
        assert episodes[0]["content"] == "пользователь спросил о нейронах"
        assert "нейронаука" in episodes[0]["tags"]
        assert len(episodes[0]["modal_evidence"]) == 1

    def test_upsert_updates_existing(self, db):
        ep = self._make_episode()
        db.upsert_episode(ep["episode_id"], ep)
        db.commit()

        ep["content"] = "обновлённый контент"
        ep["importance"] = 0.9
        db.upsert_episode(ep["episode_id"], ep)
        db.commit()

        episodes = db.load_all_episodes()
        assert len(episodes) == 1
        assert episodes[0]["content"] == "обновлённый контент"

    def test_delete_episode(self, db):
        ep = self._make_episode()
        db.upsert_episode(ep["episode_id"], ep)
        db.commit()

        db.delete_episode(ep["episode_id"])
        db.commit()

        assert db.get_episode_count() == 0

    def test_episode_count(self, db):
        for i in range(7):
            ep = self._make_episode(episode_id=f"ep_{i:03d}")
            db.upsert_episode(ep["episode_id"], ep)
        db.commit()
        assert db.get_episode_count() == 7

    def test_bulk_save(self, db):
        episodes = [self._make_episode(episode_id=f"bulk_{i}") for i in range(5)]
        db.save_all_episodes(episodes)
        db.commit()
        assert db.get_episode_count() == 5

    def test_modal_evidence_cascade_delete(self, db):
        ep = self._make_episode()
        db.upsert_episode(ep["episode_id"], ep)
        db.commit()

        counts_before = db.table_counts()
        assert counts_before["modal_evidence"] == 1

        db.delete_episode(ep["episode_id"])
        db.commit()

        counts_after = db.table_counts()
        assert counts_after["modal_evidence"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Sources
# ═══════════════════════════════════════════════════════════════════════════════

class TestSources:
    """Тесты CRUD для sources."""

    def _make_source(self, source_id="wiki_ru", **overrides):
        data = {
            "source_id": source_id,
            "source_type": "url",
            "trust_score": 0.8,
            "confirmations": 5,
            "contradictions": 1,
            "fact_count": 42,
            "first_seen_ts": time.time() - 86400,
            "last_seen_ts": time.time(),
            "metadata": {"domain": "ru.wikipedia.org"},
            "blacklisted": False,
        }
        data.update(overrides)
        return data

    def test_upsert_and_load(self, db):
        src = self._make_source()
        db.upsert_source(src["source_id"], src)
        db.commit()

        sources = db.load_all_sources()
        assert len(sources) == 1
        assert sources[0]["source_id"] == "wiki_ru"
        assert sources[0]["trust_score"] == 0.8
        assert sources[0]["metadata"]["domain"] == "ru.wikipedia.org"
        assert sources[0]["blacklisted"] is False

    def test_blacklisted_stored_as_bool(self, db):
        src = self._make_source(blacklisted=True)
        db.upsert_source(src["source_id"], src)
        db.commit()

        sources = db.load_all_sources()
        assert sources[0]["blacklisted"] is True

    def test_delete_source(self, db):
        src = self._make_source()
        db.upsert_source(src["source_id"], src)
        db.commit()

        db.delete_source(src["source_id"])
        db.commit()
        assert db.get_source_count() == 0

    def test_source_count(self, db):
        for i in range(3):
            src = self._make_source(source_id=f"src_{i}")
            db.upsert_source(src["source_id"], src)
        db.commit()
        assert db.get_source_count() == 3

    def test_bulk_save(self, db):
        sources = [(f"bulk_{i}", self._make_source(source_id=f"bulk_{i}")) for i in range(4)]
        db.save_all_sources(sources)
        db.commit()
        assert db.get_source_count() == 4


# ═══════════════════════════════════════════════════════════════════════════════
# Procedures
# ═══════════════════════════════════════════════════════════════════════════════

class TestProcedures:
    """Тесты CRUD для procedures."""

    def _make_procedure(self, name="greet_user", **overrides):
        data = {
            "name": name,
            "description": "Приветствие пользователя",
            "trigger_pattern": "привет|здравствуй",
            "success_rate": 0.95,
            "use_count": 10,
            "success_count": 9,
            "fail_count": 1,
            "avg_duration_ms": 50.0,
            "tags": ["greeting", "social"],
            "created_ts": time.time() - 3600,
            "last_used_ts": time.time(),
            "priority": 0.7,
            "steps": [
                {"action": "detect_language", "params": {"default": "ru"}, "expected_outcome": "lang_detected", "is_optional": False},
                {"action": "generate_greeting", "params": {}, "expected_outcome": "greeting_text", "is_optional": False},
                {"action": "add_emoji", "params": {"emoji": "👋"}, "expected_outcome": "", "is_optional": True},
            ],
        }
        data.update(overrides)
        return data

    def test_upsert_and_load(self, db):
        proc = self._make_procedure()
        db.upsert_procedure(proc["name"], proc)
        db.commit()

        procs = db.load_all_procedures()
        assert len(procs) == 1
        assert procs[0]["name"] == "greet_user"
        assert procs[0]["success_rate"] == 0.95
        assert len(procs[0]["steps"]) == 3
        assert procs[0]["steps"][0]["action"] == "detect_language"
        assert procs[0]["steps"][2]["is_optional"] is True

    def test_steps_order_preserved(self, db):
        proc = self._make_procedure()
        db.upsert_procedure(proc["name"], proc)
        db.commit()

        procs = db.load_all_procedures()
        actions = [s["action"] for s in procs[0]["steps"]]
        assert actions == ["detect_language", "generate_greeting", "add_emoji"]

    def test_upsert_replaces_steps(self, db):
        proc = self._make_procedure()
        db.upsert_procedure(proc["name"], proc)
        db.commit()

        proc["steps"] = [{"action": "new_step", "params": {}, "expected_outcome": "", "is_optional": False}]
        db.upsert_procedure(proc["name"], proc)
        db.commit()

        procs = db.load_all_procedures()
        assert len(procs[0]["steps"]) == 1
        assert procs[0]["steps"][0]["action"] == "new_step"

    def test_delete_procedure(self, db):
        proc = self._make_procedure()
        db.upsert_procedure(proc["name"], proc)
        db.commit()

        db.delete_procedure(proc["name"])
        db.commit()
        assert db.get_procedure_count() == 0

        # Шаги тоже удалены (CASCADE)
        counts = db.table_counts()
        assert counts["procedure_steps"] == 0

    def test_bulk_save(self, db):
        procs = [(f"proc_{i}", self._make_procedure(name=f"proc_{i}")) for i in range(3)]
        db.save_all_procedures(procs)
        db.commit()
        assert db.get_procedure_count() == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Transactions
# ═══════════════════════════════════════════════════════════════════════════════

class TestTransactions:
    """Тесты транзакционного API."""

    def test_commit(self, db):
        db.upsert_source("src_1", {
            "source_type": "file", "trust_score": 0.7,
            "confirmations": 0, "contradictions": 0, "fact_count": 0,
            "first_seen_ts": time.time(), "last_seen_ts": time.time(),
            "metadata": {}, "blacklisted": False,
        })
        db.commit()
        assert db.get_source_count() == 1

    def test_rollback(self, db):
        db.begin()
        db.upsert_source("src_rollback", {
            "source_type": "file", "trust_score": 0.7,
            "confirmations": 0, "contradictions": 0, "fact_count": 0,
            "first_seen_ts": time.time(), "last_seen_ts": time.time(),
            "metadata": {}, "blacklisted": False,
        })
        db.rollback()
        assert db.get_source_count() == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Meta API
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetaAPI:
    """Тесты для _meta таблицы."""

    def test_get_set_meta(self, db):
        db.set_meta("test_key", "test_value")
        db.commit()
        assert db.get_meta("test_key") == "test_value"

    def test_get_nonexistent_meta(self, db):
        assert db.get_meta("nonexistent") is None

    def test_overwrite_meta(self, db):
        db.set_meta("key", "v1")
        db.set_meta("key", "v2")
        db.commit()
        assert db.get_meta("key") == "v2"

    def test_schema_version_in_meta(self, db):
        assert db.get_meta("schema_version") == str(SCHEMA_VERSION)

    def test_created_ts_in_meta(self, db):
        ts = db.get_meta("created_ts")
        assert ts is not None
        assert float(ts) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Thread Safety (базовый)
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreadSafety:
    """Базовые тесты thread safety."""

    def test_concurrent_writes(self, db):
        """Параллельная запись не вызывает ошибок."""
        errors = []

        def writer(thread_id):
            try:
                for i in range(10):
                    db.upsert_source(f"thread_{thread_id}_src_{i}", {
                        "source_type": "file", "trust_score": 0.5,
                        "confirmations": 0, "contradictions": 0, "fact_count": 0,
                        "first_seen_ts": time.time(), "last_seen_ts": time.time(),
                        "metadata": {}, "blacklisted": False,
                    })
                db.commit()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert db.get_source_count() == 40


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: Memory modules with SQLite backend
# ═══════════════════════════════════════════════════════════════════════════════

class TestMemoryModulesSQLiteIntegration:
    """Интеграционные тесты: memory модули с SQLite backend."""

    def test_semantic_memory_sqlite_roundtrip(self, db):
        from brain.memory.semantic_memory import SemanticMemory

        sm = SemanticMemory(
            data_path="/dev/null",
            storage_backend="sqlite",
            db=db,
        )
        sm.store_fact(
            concept="нейрон",
            description="клетка нервной системы",
            tags=["биология"],
            importance=0.8,
        )
        sm.save()
        db.commit()

        # Создаём новый экземпляр — загрузка из SQLite
        sm2 = SemanticMemory(
            data_path="/dev/null",
            storage_backend="sqlite",
            db=db,
        )
        node = sm2.get_fact("нейрон")
        assert node is not None
        assert node.description == "клетка нервной системы"

    def test_episodic_memory_sqlite_roundtrip(self, db):
        from brain.memory.episodic_memory import EpisodicMemory

        em = EpisodicMemory(
            data_path="/dev/null",
            storage_backend="sqlite",
            db=db,
        )
        em.store(
            content="тестовый эпизод",
            modality="text",
            importance=0.6,
        )
        em.save()
        db.commit()

        em2 = EpisodicMemory(
            data_path="/dev/null",
            storage_backend="sqlite",
            db=db,
        )
        assert len(em2) >= 1

    def test_source_memory_sqlite_roundtrip(self, db):
        from brain.memory.source_memory import SourceMemory

        sm = SourceMemory(
            data_path="/dev/null",
            storage_backend="sqlite",
            db=db,
        )
        sm.register("wiki", source_type="url")
        sm.save()
        db.commit()

        sm2 = SourceMemory(
            data_path="/dev/null",
            storage_backend="sqlite",
            db=db,
        )
        assert sm2.get_trust("wiki") > 0

    def test_procedural_memory_sqlite_roundtrip(self, db):
        from brain.memory.procedural_memory import ProceduralMemory

        pm = ProceduralMemory(
            data_path="/dev/null",
            storage_backend="sqlite",
            db=db,
        )
        pm.store(
            name="test_proc",
            steps=[{"action": "step1", "params": {}}],
            description="тестовая процедура",
        )
        pm.save()
        db.commit()

        pm2 = ProceduralMemory(
            data_path="/dev/null",
            storage_backend="sqlite",
            db=db,
        )
        proc = pm2.get("test_proc")
        assert proc is not None
        assert proc.description == "тестовая процедура"

    def test_memory_manager_sqlite_backend(self, tmp_path):
        from brain.memory.memory_manager import MemoryManager

        mm = MemoryManager(
            data_dir=str(tmp_path),
            auto_consolidate=False,
            storage_backend="sqlite",
        )
        assert mm.effective_backend == "sqlite"
        assert mm.db is not None

        mm.store_fact(concept="тест", description="тестовый факт")
        mm.save_all()

        # Проверяем что данные в SQLite
        counts = mm.db.table_counts()
        assert counts["semantic_nodes"] >= 1

        mm.stop(save=False)

    def test_memory_manager_json_backend(self, tmp_path):
        from brain.memory.memory_manager import MemoryManager

        mm = MemoryManager(
            data_dir=str(tmp_path),
            auto_consolidate=False,
            storage_backend="json",
        )
        assert mm.effective_backend == "json"
        assert mm.db is None
        mm.stop(save=False)

    def test_memory_manager_transactional_save(self, tmp_path):
        from brain.memory.memory_manager import MemoryManager

        mm = MemoryManager(
            data_dir=str(tmp_path),
            auto_consolidate=False,
            storage_backend="sqlite",
        )
        mm.store_fact(concept="факт1", description="описание1")
        mm.store_fact(concept="факт2", description="описание2")
        mm.save_all()

        counts = mm.db.table_counts()
        assert counts["semantic_nodes"] >= 2
        mm.stop(save=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Migration
# ═══════════════════════════════════════════════════════════════════════════════

class TestMigration:
    """Тесты миграции JSON → SQLite."""

    def test_migrate_empty_dir_no_json(self, tmp_path):
        """Пустая директория без JSON → status='no_json_files'."""
        from brain.memory.migrate import migrate_json_to_sqlite

        db_path = str(tmp_path / "memory.db")
        result = migrate_json_to_sqlite(str(tmp_path), db_path)
        assert result["status"] == "no_json_files"

    def test_migrate_nonexistent_dir(self, tmp_path):
        """Несуществующая директория → status='error'."""
        from brain.memory.migrate import migrate_json_to_sqlite

        result = migrate_json_to_sqlite(str(tmp_path / "nonexistent"), str(tmp_path / "m.db"))
        assert result["status"] == "error"

    def test_migrate_with_semantic_json(self, tmp_path):
        """Миграция semantic.json → SQLite."""
        from brain.memory.migrate import migrate_json_to_sqlite

        semantic_data = {
            "version": "1.0",
            "nodes": {
                "нейрон": {
                    "concept": "нейрон",
                    "description": "клетка",
                    "tags": [],
                    "confidence": 1.0,
                    "importance": 0.5,
                    "source_refs": [],
                    "access_count": 0,
                    "confirm_count": 0,
                    "deny_count": 0,
                    "created_ts": time.time(),
                    "updated_ts": time.time(),
                    "relations": [],
                }
            },
        }
        with open(tmp_path / "semantic.json", "w", encoding="utf-8") as f:
            json.dump(semantic_data, f, ensure_ascii=False)

        db_path = str(tmp_path / "memory.db")
        result = migrate_json_to_sqlite(str(tmp_path), db_path)
        assert result["status"] == "success"
        assert result["semantic"] == 1

    def test_migrate_with_episodes_json(self, tmp_path):
        """Миграция episodes.json → SQLite."""
        from brain.memory.migrate import migrate_json_to_sqlite

        episodes_data = {
            "episodes": [
                {
                    "episode_id": "ep_001",
                    "ts": time.time(),
                    "content": "тест",
                    "modality": "text",
                    "source": "user",
                    "importance": 0.5,
                    "confidence": 1.0,
                    "tags": [],
                    "concepts": [],
                    "trace_id": "",
                    "session_id": "s1",
                    "access_count": 0,
                    "modal_evidence": [],
                }
            ]
        }
        with open(tmp_path / "episodes.json", "w", encoding="utf-8") as f:
            json.dump(episodes_data, f, ensure_ascii=False)

        db_path = str(tmp_path / "memory.db")
        result = migrate_json_to_sqlite(str(tmp_path), db_path)
        assert result["status"] == "success"
        assert result["episodes"] == 1

    def test_is_migrated_false_on_fresh_db(self, tmp_path):
        """is_migrated() → False на свежей БД без маркера."""
        from brain.memory.migrate import is_migrated

        db_path = str(tmp_path / "fresh.db")
        fresh_db = MemoryDatabase(db_path=db_path)
        try:
            assert is_migrated(fresh_db) is False
        finally:
            fresh_db.close()

    def test_is_migrated_true_after_migration(self, tmp_path):
        """is_migrated() → True после успешной миграции."""
        from brain.memory.migrate import migrate_json_to_sqlite, is_migrated

        # Создаём JSON чтобы триггернуть миграцию
        with open(tmp_path / "semantic.json", "w") as f:
            json.dump({"version": "1.0", "nodes": {"x": {
                "description": "", "tags": [], "confidence": 1.0,
                "importance": 0.5, "source_refs": [], "access_count": 0,
                "confirm_count": 0, "deny_count": 0,
                "created_ts": time.time(), "updated_ts": time.time(),
                "relations": [],
            }}}, f)

        db_path = str(tmp_path / "memory.db")
        result = migrate_json_to_sqlite(str(tmp_path), db_path)
        assert result["status"] == "success"

        # Проверяем маркер
        check_db = MemoryDatabase(db_path=db_path)
        try:
            assert is_migrated(check_db) is True
        finally:
            check_db.close()

    def test_already_migrated_skips(self, tmp_path):
        """Повторная миграция → status='already_migrated'."""
        from brain.memory.migrate import migrate_json_to_sqlite

        with open(tmp_path / "semantic.json", "w") as f:
            json.dump({"version": "1.0", "nodes": {"y": {
                "description": "", "tags": [], "confidence": 1.0,
                "importance": 0.5, "source_refs": [], "access_count": 0,
                "confirm_count": 0, "deny_count": 0,
                "created_ts": time.time(), "updated_ts": time.time(),
                "relations": [],
            }}}, f)

        db_path = str(tmp_path / "memory.db")
        r1 = migrate_json_to_sqlite(str(tmp_path), db_path)
        assert r1["status"] == "success"

        r2 = migrate_json_to_sqlite(str(tmp_path), db_path)
        assert r2["status"] == "already_migrated"

    def test_force_re_migration(self, tmp_path):
        """force=True → повторная миграция выполняется."""
        from brain.memory.migrate import migrate_json_to_sqlite

        with open(tmp_path / "semantic.json", "w") as f:
            json.dump({"version": "1.0", "nodes": {"z": {
                "description": "", "tags": [], "confidence": 1.0,
                "importance": 0.5, "source_refs": [], "access_count": 0,
                "confirm_count": 0, "deny_count": 0,
                "created_ts": time.time(), "updated_ts": time.time(),
                "relations": [],
            }}}, f)

        db_path = str(tmp_path / "memory.db")
        migrate_json_to_sqlite(str(tmp_path), db_path)

        r2 = migrate_json_to_sqlite(str(tmp_path), db_path, force=True)
        assert r2["status"] == "success"

    def test_auto_migrate_if_needed_with_json(self, tmp_path):
        """auto_migrate_if_needed() → True когда есть JSON файлы."""
        from brain.memory.migrate import auto_migrate_if_needed

        with open(tmp_path / "semantic.json", "w") as f:
            json.dump({"version": "1.0", "nodes": {"a": {
                "description": "", "tags": [], "confidence": 1.0,
                "importance": 0.5, "source_refs": [], "access_count": 0,
                "confirm_count": 0, "deny_count": 0,
                "created_ts": time.time(), "updated_ts": time.time(),
                "relations": [],
            }}}, f)

        result = auto_migrate_if_needed(str(tmp_path))
        assert result is True

    def test_auto_migrate_if_needed_no_json(self, tmp_path):
        """auto_migrate_if_needed() → False когда нет JSON файлов."""
        from brain.memory.migrate import auto_migrate_if_needed

        result = auto_migrate_if_needed(str(tmp_path))
        assert result is False

    def test_auto_migrate_idempotent(self, tmp_path):
        """Повторный auto_migrate → False (уже мигрировано)."""
        from brain.memory.migrate import auto_migrate_if_needed

        with open(tmp_path / "semantic.json", "w") as f:
            json.dump({"version": "1.0", "nodes": {"b": {
                "description": "", "tags": [], "confidence": 1.0,
                "importance": 0.5, "source_refs": [], "access_count": 0,
                "confirm_count": 0, "deny_count": 0,
                "created_ts": time.time(), "updated_ts": time.time(),
                "relations": [],
            }}}, f)

        r1 = auto_migrate_if_needed(str(tmp_path))
        assert r1 is True

        r2 = auto_migrate_if_needed(str(tmp_path))
        assert r2 is False

    def test_backup_created(self, tmp_path):
        """Миграция создаёт backup директорию."""
        from brain.memory.migrate import migrate_json_to_sqlite

        with open(tmp_path / "semantic.json", "w") as f:
            json.dump({"version": "1.0", "nodes": {}}, f)

        db_path = str(tmp_path / "memory.db")
        result = migrate_json_to_sqlite(str(tmp_path), db_path, backup=True)
        assert result["status"] == "success"
        assert result["backup_dir"] is not None
        assert os.path.isdir(result["backup_dir"])
