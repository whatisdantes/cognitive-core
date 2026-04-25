import sqlite3

from brain.memory.storage import SCHEMA_VERSION, MemoryDatabase


def test_schema_v2_created_for_new_database(tmp_path):
    db = MemoryDatabase(str(tmp_path / "memory.db"))
    try:
        assert SCHEMA_VERSION == 2
        assert db.schema_version == 2
        counts = db.table_counts()
        assert "claims" in counts
        assert "claim_conflicts" in counts
        assert "materials_registry" in counts
        assert "material_chunks" in counts
    finally:
        db.close()


def test_v1_database_migrates_to_v2_idempotently(tmp_path):
    db_path = tmp_path / "memory.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO _meta (key, value) VALUES ('schema_version', '1')")
    conn.execute(
        """
        CREATE TABLE semantic_nodes (
            concept TEXT PRIMARY KEY,
            description TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            confidence REAL NOT NULL DEFAULT 1.0,
            importance REAL NOT NULL DEFAULT 0.5,
            source_refs TEXT NOT NULL DEFAULT '[]',
            access_count INTEGER NOT NULL DEFAULT 0,
            confirm_count INTEGER NOT NULL DEFAULT 0,
            deny_count INTEGER NOT NULL DEFAULT 0,
            created_ts REAL NOT NULL,
            updated_ts REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO semantic_nodes
            (concept, description, created_ts, updated_ts)
        VALUES ('python', 'язык программирования', 1.0, 1.0)
        """
    )
    conn.commit()
    conn.close()

    db = MemoryDatabase(str(db_path))
    try:
        assert db.schema_version == 2
        assert db.get_meta("schema_v2_migrated_ts") is not None
        rows = db.load_all_semantic_nodes()
        assert rows[0]["concept"] == "python"
        assert rows[0]["description"] == "язык программирования"
    finally:
        db.close()

    reopened = MemoryDatabase(str(db_path))
    try:
        assert reopened.schema_version == 2
        assert reopened.table_counts()["claims"] == 0
    finally:
        reopened.close()
