import logging

from brain.perception.metadata_extractor import MetadataExtractor


def test_metadata_extractor_logs_normal_quality_warnings_as_debug(caplog):
    extractor = MetadataExtractor()
    text = (
        "Нейрон — это клетка нервной системы. Он передаёт сигналы между "
        "участками организма и поддерживает работу нервной ткани.\ufffd"
    )

    with caplog.at_level(logging.DEBUG, logger="brain.perception.metadata_extractor"):
        meta = extractor.extract(text, source="materials/manual.pdf#p1", chunk_id=7)

    assert meta["quality"] >= 0.7
    assert any("broken_chars" in warning for warning in meta["warnings"])
    assert any(record.levelno == logging.DEBUG for record in caplog.records)
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


def test_metadata_extractor_logs_low_quality_warnings_as_warning(caplog):
    extractor = MetadataExtractor()

    with caplog.at_level(logging.DEBUG, logger="brain.perception.metadata_extractor"):
        meta = extractor.extract("Короткий текст", source="materials/manual.pdf#p1", chunk_id=8)

    assert meta["quality"] < 0.7
    assert meta["warnings"]
    assert any(record.levelno == logging.WARNING for record in caplog.records)
