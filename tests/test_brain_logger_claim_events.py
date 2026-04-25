from pathlib import Path

from brain.logging import BrainLogger


def test_claim_and_material_events_go_to_category_logs(tmp_path: Path):
    blog = BrainLogger(log_dir=str(tmp_path), min_level="DEBUG")
    try:
        blog.info("memory", "claim_created", state={"claim_id": "c1"})
        blog.info("perception", "material_ingested", state={"sha256": "abc"})
        blog.info("motivation", "idle_no_candidates")
        blog.flush()

        assert (tmp_path / "memory.jsonl").exists()
        assert "claim_created" in (tmp_path / "memory.jsonl").read_text(encoding="utf-8")
        assert "material_ingested" in (tmp_path / "perception.jsonl").read_text(encoding="utf-8")
        assert "idle_no_candidates" in (tmp_path / "motivation.jsonl").read_text(encoding="utf-8")
    finally:
        blog.close()


def test_safety_audit_file_exists_on_startup(tmp_path: Path):
    blog = BrainLogger(log_dir=str(tmp_path), min_level="DEBUG")
    try:
        blog.flush()
        assert (tmp_path / "safety_audit.jsonl").exists()
    finally:
        blog.close()
