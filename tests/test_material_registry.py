from brain.memory.material_registry import MaterialRegistry
from brain.memory.storage import MemoryDatabase


def test_material_registry_tracks_materials_and_chunks(tmp_path):
    db = MemoryDatabase(str(tmp_path / "memory.db"))
    registry = MaterialRegistry(db)
    try:
        material = registry.upsert_material(
            sha256="abc123",
            path="materials/book.pdf",
            size=42,
            mtime=10.0,
        )
        assert material.sha256 == "abc123"
        assert material.ingest_status == "in_progress"

        chunk = registry.add_chunk("abc123", 0, "chunkhash", "material:abc123#chunk_0")
        duplicate = registry.add_chunk("abc123", 0, "chunkhash", "material:abc123#chunk_0")
        assert duplicate.chunk_hash == chunk.chunk_hash

        registry.set_chunk_status("abc123", 0, "done", claim_count=2)
        assert registry.pending_or_retryable_chunks("abc123") == []

        registry.set_material_status("abc123", "done", chunk_count=1, claim_count=2)
        done = registry.get_material("abc123")
        assert done.ingest_status == "done"
        assert done.chunk_count == 1
        assert done.claim_count == 2
        assert done.last_ingested_at is not None
    finally:
        db.close()


def test_failed_chunks_are_retryable_until_limit(tmp_path):
    db = MemoryDatabase(str(tmp_path / "memory.db"))
    registry = MaterialRegistry(db)
    try:
        registry.upsert_material("abc123", "materials/book.pdf", 42, 10.0)
        registry.add_chunk("abc123", 0, "chunkhash", "material:abc123#chunk_0")
        registry.set_chunk_status("abc123", 0, "failed", increment_retry=True)

        retryable = registry.pending_or_retryable_chunks("abc123", max_chunk_retries=3)
        assert len(retryable) == 1
        assert retryable[0].retry_count == 1

        registry.set_chunk_status("abc123", 0, "failed", increment_retry=True)
        registry.set_chunk_status("abc123", 0, "failed", increment_retry=True)
        assert registry.pending_or_retryable_chunks("abc123", max_chunk_retries=3) == []
    finally:
        db.close()
