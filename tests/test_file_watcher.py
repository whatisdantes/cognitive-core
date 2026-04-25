from types import SimpleNamespace

from brain.core.event_bus import EventBus
from brain.core.scheduler import Scheduler
from brain.memory import MemoryManager
from brain.perception.file_watcher import FileWatcher, FileWatcherConfig
from brain.perception.material_ingestor import MaterialIngestor


def _scheduler() -> Scheduler:
    return Scheduler(EventBus())


def test_file_watcher_enqueues_only_after_stabilization(tmp_path):
    material = tmp_path / "materials" / "facts.md"
    material.parent.mkdir()
    material.write_text("Нейрон: клетка нервной системы.", encoding="utf-8")
    scheduler = _scheduler()
    watcher = FileWatcher(
        scheduler,
        FileWatcherConfig(
            watch_dir=str(material.parent),
            stabilization_checks=3,
            stabilization_interval_s=0.0,
        ),
        list_files_fn=lambda: [material],
        readable_probe=lambda path: None,
    )

    assert watcher.poll_once(now=1.0).enqueued == 0
    assert scheduler.queue_size() == 0
    assert watcher.poll_once(now=2.0).enqueued == 0
    assert scheduler.queue_size() == 0

    result = watcher.poll_once(now=3.0)

    assert result.enqueued == 1
    assert result.enqueued_paths == [str(material)]
    assert scheduler.queue_size() == 1
    task = scheduler.dequeue()
    assert task.task_type == "ingest_file"
    assert task.payload["path"] == str(material)
    assert task.payload["watch_dir"] == str(material.parent)


def test_file_watcher_default_patterns_include_pdf(tmp_path):
    material = tmp_path / "materials" / "manual.pdf"
    material.parent.mkdir()
    material.write_bytes(b"%PDF-1.4\n")
    scheduler = _scheduler()
    watcher = FileWatcher(
        scheduler,
        FileWatcherConfig(
            watch_dir=str(material.parent),
            stabilization_checks=1,
            stabilization_interval_s=0.0,
        ),
        readable_probe=lambda path: None,
    )

    result = watcher.poll_once(now=1.0)

    assert result.enqueued == 1
    assert result.enqueued_paths == [str(material)]
    assert scheduler.queue_size() == 1


def test_file_watcher_requeues_changed_file_after_new_stabilization(tmp_path):
    material = tmp_path / "materials" / "facts.md"
    material.parent.mkdir()
    material.write_text("Нейрон: клетка нервной системы.", encoding="utf-8")
    scheduler = _scheduler()
    watcher = FileWatcher(
        scheduler,
        FileWatcherConfig(
            watch_dir=str(material.parent),
            stabilization_checks=2,
            stabilization_interval_s=0.0,
        ),
        list_files_fn=lambda: [material],
        readable_probe=lambda path: None,
    )

    watcher.poll_once(now=1.0)
    assert watcher.poll_once(now=2.0).enqueued == 1
    assert scheduler.queue_size() == 1

    material.write_text("Нейрон: клетка нервной системы.\nГлия: вспомогательная клетка.", encoding="utf-8")
    assert watcher.poll_once(now=3.0).enqueued == 0
    assert watcher.poll_once(now=4.0).enqueued == 1
    assert scheduler.queue_size() == 2


def test_file_watcher_busy_file_does_not_crash(tmp_path):
    material = tmp_path / "materials" / "locked.md"
    material.parent.mkdir()
    material.write_text("Память: способность сохранять опыт.", encoding="utf-8")
    scheduler = _scheduler()

    def locked_stat(path):
        raise PermissionError("locked")

    watcher = FileWatcher(
        scheduler,
        FileWatcherConfig(watch_dir=str(material.parent)),
        list_files_fn=lambda: [material],
        stat_fn=locked_stat,
        readable_probe=lambda path: None,
    )

    result = watcher.poll_once(now=1.0)

    assert result.skipped_busy == 1
    assert scheduler.queue_size() == 0


def test_file_watcher_logs_unstable_file_as_busy(tmp_path):
    material = tmp_path / "materials" / "writing.md"
    material.parent.mkdir()
    scheduler = _scheduler()
    stats = [
        SimpleNamespace(st_size=10, st_mtime=1.0),
        SimpleNamespace(st_size=20, st_mtime=2.0),
    ]

    def next_stat(path):
        return stats.pop(0) if stats else SimpleNamespace(st_size=30, st_mtime=3.0)

    watcher = FileWatcher(
        scheduler,
        FileWatcherConfig(
            watch_dir=str(material.parent),
            stabilization_checks=3,
            stabilization_interval_s=0.0,
            max_unstable_polls=1,
        ),
        list_files_fn=lambda: [material],
        stat_fn=next_stat,
        readable_probe=lambda path: None,
    )

    watcher.poll_once(now=1.0)
    result = watcher.poll_once(now=2.0)

    assert result.unstable == 1
    assert result.skipped_busy == 1
    assert scheduler.queue_size() == 0


def test_watcher_ingest_file_task_uses_material_ingestor_contract(tmp_path):
    material = tmp_path / "materials" / "watched.md"
    material.parent.mkdir()
    material.write_text("Таламус: центр маршрутизации сигналов.", encoding="utf-8")
    scheduler = _scheduler()
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    memory = MemoryManager(
        data_dir=str(memory_dir),
        auto_consolidate=False,
        storage_backend="sqlite",
    )
    try:
        ingestor = MaterialIngestor(memory)
        scheduler.register_handler("ingest_file", ingestor.handle_ingest_file_task)
        watcher = FileWatcher(
            scheduler,
            FileWatcherConfig(
                watch_dir=str(material.parent),
                stabilization_checks=1,
                stabilization_interval_s=0.0,
            ),
            list_files_fn=lambda: [material],
            readable_probe=lambda path: None,
        )

        result = watcher.poll_once(now=1.0)
        assert result.enqueued == 1

        tick = scheduler.tick()

        assert tick["tasks_executed"] == 1
        executed = tick["executed"][0]
        assert executed["task_type"] == "ingest_file"
        assert executed["result"]["status"] == "done"
        assert memory.claim_store.count() == 1
        claim = memory.claim_store.find_by_concept("таламус")[0]
        assert claim.metadata["source"] == "material_ingestor"
    finally:
        memory.stop(save=False)
