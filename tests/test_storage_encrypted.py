"""
tests/test_storage_encrypted.py

Тесты для опционального шифрования MemoryDatabase через SQLCipher (P3-12).

Тесты с реальным SQLCipher пропускаются если sqlcipher3 не установлен.
Тест на ImportError работает всегда через unittest.mock.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from brain.memory.storage import _SQLCIPHER_AVAILABLE, MemoryDatabase

# ─── Маркер: пропустить если sqlcipher3 не установлен ────────────────────────

requires_sqlcipher = pytest.mark.skipif(
    not _SQLCIPHER_AVAILABLE,
    reason="sqlcipher3 не установлен (pip install cognitive-core[encrypted])",
)


# ─── Тест 1: без шифрования — поведение не изменилось ────────────────────────

class TestUnencryptedDatabase:
    """Проверяем, что без encryption_key поведение идентично исходному."""

    def test_default_is_not_encrypted(self, tmp_path):
        """MemoryDatabase без ключа — is_encrypted=False."""
        db = MemoryDatabase(str(tmp_path / "plain.db"))
        try:
            assert db.is_encrypted is False
        finally:
            db.close()

    def test_status_has_encrypted_field(self, tmp_path):
        """status() содержит поле encrypted=False."""
        db = MemoryDatabase(str(tmp_path / "plain.db"))
        try:
            st = db.status()
            assert "encrypted" in st
            assert st["encrypted"] is False
        finally:
            db.close()

    def test_in_memory_db_works(self):
        """':memory:' база данных работает без изменений."""
        db = MemoryDatabase(":memory:")
        try:
            db.upsert_semantic_node("тест", {
                "description": "тестовый узел",
                "confidence": 0.9,
                "importance": 0.5,
                "created_ts": time.time(),
                "updated_ts": time.time(),
            })
            db.commit()
            nodes = db.load_all_semantic_nodes()
            assert len(nodes) == 1
            assert nodes[0]["concept"] == "тест"
        finally:
            db.close()

    def test_encryption_key_none_uses_sqlite3(self, tmp_path):
        """encryption_key=None явно — использует sqlite3."""
        db = MemoryDatabase(str(tmp_path / "plain.db"), encryption_key=None)
        try:
            assert db.is_encrypted is False
            assert db.schema_version == 1
        finally:
            db.close()


# ─── Тест 2: ImportError если sqlcipher3 не установлен ───────────────────────

class TestMissingSqlcipher:
    """Проверяем поведение при отсутствии sqlcipher3."""

    def test_raises_import_error_when_sqlcipher3_missing(self, tmp_path):
        """
        Если sqlcipher3 не установлен и передан encryption_key —
        должен подняться ImportError с понятным сообщением.
        """
        with (
            patch("brain.memory.storage._SQLCIPHER_AVAILABLE", False),
            pytest.raises(ImportError, match="sqlcipher3 не установлен"),
        ):
            MemoryDatabase(
                str(tmp_path / "secure.db"),
                encryption_key="test-key-123",
            )

    def test_error_message_contains_install_hint(self, tmp_path):
        """Сообщение об ошибке содержит подсказку по установке."""
        with patch("brain.memory.storage._SQLCIPHER_AVAILABLE", False):
            with pytest.raises(ImportError) as exc_info:
                MemoryDatabase(
                    str(tmp_path / "secure.db"),
                    encryption_key="any-valid-key",  # 13 chars, passes validation
                )
            assert "pip install" in str(exc_info.value)
            assert "encrypted" in str(exc_info.value)


# ─── Тест 3: реальное шифрование (только если sqlcipher3 установлен) ─────────

@requires_sqlcipher
class TestEncryptedDatabase:
    """Тесты с реальным SQLCipher. Пропускаются если sqlcipher3 не установлен."""

    def test_encrypted_db_creates_successfully(self, tmp_path):
        """Зашифрованная БД создаётся без ошибок."""
        db = MemoryDatabase(
            str(tmp_path / "secure.db"),
            encryption_key="test-secret-key-32chars-minimum00",
        )
        try:
            assert db.is_encrypted is True
            assert db.schema_version == 1
        finally:
            db.close()

    def test_encrypted_db_write_and_read(self, tmp_path):
        """Запись и чтение данных в зашифрованной БД."""
        db_path = str(tmp_path / "secure.db")
        key = "test-secret-key-32chars-minimum00"

        # Запись
        db = MemoryDatabase(db_path, encryption_key=key)
        try:
            db.upsert_semantic_node("нейрон", {
                "description": "базовая единица нервной системы",
                "confidence": 0.95,
                "importance": 0.8,
                "created_ts": time.time(),
                "updated_ts": time.time(),
            })
            db.upsert_episode("ep_001", {
                "ts": time.time(),
                "content": "тестовый эпизод",
                "modality": "text",
                "importance": 0.7,
                "confidence": 0.9,
            })
            db.commit()
        finally:
            db.close()

        # Чтение с тем же ключом
        db2 = MemoryDatabase(db_path, encryption_key=key)
        try:
            nodes = db2.load_all_semantic_nodes()
            episodes = db2.load_all_episodes()
            assert len(nodes) == 1
            assert nodes[0]["concept"] == "нейрон"
            assert nodes[0]["description"] == "базовая единица нервной системы"
            assert len(episodes) == 1
            assert episodes[0]["episode_id"] == "ep_001"
        finally:
            db2.close()

    def test_encrypted_db_status_shows_encrypted_true(self, tmp_path):
        """status() возвращает encrypted=True для зашифрованной БД."""
        db = MemoryDatabase(
            str(tmp_path / "secure.db"),
            encryption_key="my-key-32chars-minimum-padding00",
        )
        try:
            st = db.status()
            assert st["encrypted"] is True
            assert "counts" in st
            assert "schema_version" in st
        finally:
            db.close()

    def test_encrypted_db_wrong_key_raises(self, tmp_path):
        """
        Открытие зашифрованной БД с неверным ключом должно вызвать ошибку
        при первом обращении к данным.
        """
        db_path = str(tmp_path / "secure.db")
        correct_key = "correct-key-32chars-minimum00000"
        wrong_key = "wrong-key-32chars-minimum0000000"

        # Создаём с правильным ключом
        db = MemoryDatabase(db_path, encryption_key=correct_key)
        db.upsert_semantic_node("тест", {
            "description": "тест",
            "confidence": 1.0,
            "importance": 0.5,
            "created_ts": time.time(),
            "updated_ts": time.time(),
        })
        db.commit()
        db.close()

        # Пытаемся открыть с неверным ключом
        with pytest.raises(Exception):  # noqa: B017
            db_wrong = MemoryDatabase(db_path, encryption_key=wrong_key)
            # Чтение должно вызвать ошибку
            db_wrong.load_all_semantic_nodes()
            db_wrong.close()

    def test_encrypted_and_plain_are_independent(self, tmp_path):
        """Зашифрованная и обычная БД работают независимо."""
        plain_path = str(tmp_path / "plain.db")
        secure_path = str(tmp_path / "secure.db")
        key = "independent-key-32chars-minimum00"

        plain_db = MemoryDatabase(plain_path)
        secure_db = MemoryDatabase(secure_path, encryption_key=key)

        try:
            plain_db.upsert_semantic_node("открытый", {
                "description": "открытые данные",
                "confidence": 1.0,
                "importance": 0.5,
                "created_ts": time.time(),
                "updated_ts": time.time(),
            })
            secure_db.upsert_semantic_node("секретный", {
                "description": "секретные данные",
                "confidence": 1.0,
                "importance": 0.5,
                "created_ts": time.time(),
                "updated_ts": time.time(),
            })
            plain_db.commit()
            secure_db.commit()

            plain_nodes = plain_db.load_all_semantic_nodes()
            secure_nodes = secure_db.load_all_semantic_nodes()

            assert len(plain_nodes) == 1
            assert plain_nodes[0]["concept"] == "открытый"
            assert len(secure_nodes) == 1
            assert secure_nodes[0]["concept"] == "секретный"
        finally:
            plain_db.close()
            secure_db.close()


# ─── CC-01: encryption_key validation tests ──────────────────────────────────


class TestEncryptionKeyValidation:
    """Тесты валидации encryption_key (CC-01: SQL injection fix)."""

    def test_valid_key_alphanumeric(self, tmp_path):
        """Валидный ключ из букв и цифр — не должен вызывать исключение."""
        db_path = str(tmp_path / "test.db")
        try:
            db = MemoryDatabase(db_path, encryption_key="ValidKey123")
            db.close()
        except ImportError:
            pytest.skip("sqlcipher3 не установлен")

    def test_valid_key_with_dash_underscore(self, tmp_path):
        """Валидный ключ с дефисом и подчёркиванием."""
        db_path = str(tmp_path / "test2.db")
        try:
            db = MemoryDatabase(db_path, encryption_key="valid-key_123")
            db.close()
        except ImportError:
            pytest.skip("sqlcipher3 не установлен")

    def test_valid_key_min_length(self, tmp_path):
        """Ключ минимальной длины (8 символов) — валиден."""
        db_path = str(tmp_path / "test3.db")
        try:
            db = MemoryDatabase(db_path, encryption_key="Abcd1234")
            db.close()
        except ImportError:
            pytest.skip("sqlcipher3 не установлен")

    def test_valid_key_max_length(self, tmp_path):
        """Ключ максимальной длины (128 символов) — валиден."""
        db_path = str(tmp_path / "test4.db")
        try:
            db = MemoryDatabase(db_path, encryption_key="A" * 128)
            db.close()
        except ImportError:
            pytest.skip("sqlcipher3 не установлен")

    def test_invalid_key_too_short(self, tmp_path):
        """Ключ короче 8 символов — ValueError."""
        db_path = str(tmp_path / "test5.db")
        with pytest.raises(ValueError, match="encryption_key"):
            MemoryDatabase(db_path, encryption_key="short")

    def test_invalid_key_too_long(self, tmp_path):
        """Ключ длиннее 128 символов — ValueError."""
        db_path = str(tmp_path / "test6.db")
        with pytest.raises(ValueError, match="encryption_key"):
            MemoryDatabase(db_path, encryption_key="A" * 129)

    def test_none_key_no_encryption(self, tmp_path):
        """encryption_key=None — шифрование не активируется, БД открывается."""
        db_path = str(tmp_path / "test7.db")
        db = MemoryDatabase(db_path, encryption_key=None)
        assert db.is_encrypted is False
        db.close()

    def test_invalid_key_sql_injection_attempt(self, tmp_path):
        """Попытка SQL injection — ValueError до выполнения PRAGMA."""
        db_path = str(tmp_path / "test8.db")
        with pytest.raises(ValueError, match="encryption_key"):
            MemoryDatabase(
                db_path,
                encryption_key="key'; DROP TABLE semantic_nodes; --",
            )

    def test_invalid_key_spaces(self, tmp_path):
        """Ключ с пробелами — ValueError."""
        db_path = str(tmp_path / "test9.db")
        with pytest.raises(ValueError, match="encryption_key"):
            MemoryDatabase(db_path, encryption_key="key with spaces")

    def test_invalid_key_special_chars(self, tmp_path):
        """Ключ со спецсимволами — ValueError."""
        db_path = str(tmp_path / "test10.db")
        with pytest.raises(ValueError, match="encryption_key"):
            MemoryDatabase(db_path, encryption_key="key@#$%^&*()")

    def test_validate_function_directly_valid(self):
        """Прямой вызов _validate_encryption_key с валидным ключом — нет исключения."""
        from brain.memory.storage import _validate_encryption_key
        _validate_encryption_key("ValidKey-123_abc")  # не должен поднимать

    def test_validate_function_directly_invalid(self):
        """Прямой вызов _validate_encryption_key с невалидным ключом — ValueError."""
        from brain.memory.storage import _validate_encryption_key
        with pytest.raises(ValueError, match="encryption_key"):
            _validate_encryption_key("bad key!")

    def test_validate_function_empty_string(self):
        """Пустая строка — ValueError (слишком короткая)."""
        from brain.memory.storage import _validate_encryption_key
        with pytest.raises(ValueError, match="encryption_key"):
            _validate_encryption_key("")

    def test_validate_function_quotes_injection(self):
        """Одинарные кавычки в ключе — ValueError."""
        from brain.memory.storage import _validate_encryption_key
        with pytest.raises(ValueError, match="encryption_key"):
            _validate_encryption_key("valid'quote")
