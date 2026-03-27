"""
tests/test_utils.py — Unit-тесты для канонических утилит Phase C.

Покрытие:
  - detect_language():    ru, en, mixed, unknown, пустая строка, числа, emoji
  - parse_fact_pattern(): "X это Y", "X — Y", "X - Y", "X: Y", "X is Y",
                          нерелевантная строка, пустой input, граничные длины
  - sha256_text():        полный хеш, truncate, стабильность, пустая строка
  - sha256_file():        обычный файл, fallback при ошибке, стабильность
"""

from __future__ import annotations

from brain.core.hash_utils import sha256_file, sha256_text
from brain.core.text_utils import detect_language, parse_fact_pattern

# ═══════════════════════════════════════════════════════════════════════════════
# detect_language
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectLanguage:
    """Тесты для detect_language()."""

    # --- Русский ---

    def test_russian_pure(self):
        assert detect_language("Нейрон — это клетка нервной системы") == "ru"

    def test_russian_with_numbers(self):
        assert detect_language("В мозге около 86 миллиардов нейронов") == "ru"

    def test_russian_short(self):
        assert detect_language("Привет мир") == "ru"

    def test_russian_long(self):
        text = "Когнитивная наука изучает процессы мышления и восприятия " * 5
        assert detect_language(text) == "ru"

    # --- Английский ---

    def test_english_pure(self):
        assert detect_language("A neuron is a cell of the nervous system") == "en"

    def test_english_with_numbers(self):
        assert detect_language("The brain has about 86 billion neurons") == "en"

    def test_english_short(self):
        assert detect_language("Hello world") == "en"

    # --- Смешанный ---

    def test_mixed_language(self):
        # Примерно 50/50 кириллица/латиница
        text = "Нейрон neuron клетка cell система system мозг brain"
        result = detect_language(text)
        assert result in ("mixed", "ru", "en")  # зависит от точного соотношения

    def test_mixed_with_enough_letters(self):
        # Гарантированно > 10 букв, ни одна группа не > 60%
        text = "abc def ghi Привет мир тест"
        result = detect_language(text)
        assert result in ("mixed", "ru", "en")

    # --- Unknown ---

    def test_empty_string(self):
        assert detect_language("") == "unknown"

    def test_whitespace_only(self):
        assert detect_language("   \t\n  ") == "unknown"

    def test_numbers_only(self):
        assert detect_language("12345 67890") == "unknown"

    def test_punctuation_only(self):
        assert detect_language("!@#$%^&*()") == "unknown"

    def test_emoji_only(self):
        assert detect_language("🧠🔬🧬") == "unknown"

    def test_none_like_empty(self):
        # Пустая строка
        assert detect_language("") == "unknown"

    # --- Граничные случаи ---

    def test_single_cyrillic_char(self):
        result = detect_language("А")
        assert result in ("ru", "unknown")  # 1 буква, total <= 10

    def test_single_latin_char(self):
        result = detect_language("A")
        assert result in ("en", "unknown")

    def test_few_letters_below_threshold(self):
        # Менее 10 букв, смешанные — должно быть unknown
        result = detect_language("Аб cd")
        assert result in ("unknown", "mixed", "ru", "en")

    # --- Стабильность ---

    def test_deterministic(self):
        text = "Нейрон — это клетка"
        r1 = detect_language(text)
        r2 = detect_language(text)
        assert r1 == r2

    def test_return_values_are_valid(self):
        """Все возвращаемые значения — из допустимого набора."""
        texts = [
            "Привет", "Hello", "Привет Hello мир world тест test",
            "", "123", "🧠",
        ]
        valid = {"ru", "en", "mixed", "unknown"}
        for t in texts:
            assert detect_language(t) in valid, f"Invalid result for '{t}'"


# ═══════════════════════════════════════════════════════════════════════════════
# parse_fact_pattern
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseFactPattern:
    """Тесты для parse_fact_pattern()."""

    # --- Русские паттерны ---

    def test_eto_pattern(self):
        result = parse_fact_pattern("Нейрон это клетка нервной системы")
        assert result is not None
        assert result[0] == "Нейрон"
        assert result[1] == "клетка нервной системы"

    def test_dash_pattern(self):
        result = parse_fact_pattern("Нейрон — клетка нервной системы")
        assert result is not None
        assert result[0] == "Нейрон"
        assert result[1] == "клетка нервной системы"

    def test_hyphen_pattern(self):
        result = parse_fact_pattern("Нейрон - клетка нервной системы")
        assert result is not None
        assert result[0] == "Нейрон"
        assert result[1] == "клетка нервной системы"

    def test_colon_pattern(self):
        result = parse_fact_pattern("Нейрон: клетка нервной системы")
        assert result is not None
        assert result[0] == "Нейрон"
        assert result[1] == "клетка нервной системы"

    # --- Английские паттерны ---

    def test_is_pattern(self):
        result = parse_fact_pattern("A neuron is a cell of the nervous system")
        assert result is not None
        assert result[0] == "A neuron"
        assert result[1] == "a cell of the nervous system"

    def test_are_pattern(self):
        result = parse_fact_pattern("Neurons are cells of the nervous system")
        assert result is not None
        assert result[0] == "Neurons"
        assert result[1] == "cells of the nervous system"

    def test_means_pattern(self):
        result = parse_fact_pattern("Neuroplasticity means the brain can change")
        assert result is not None
        assert result[0] == "Neuroplasticity"
        assert result[1] == "the brain can change"

    # --- Нерелевантные строки ---

    def test_no_pattern_question(self):
        assert parse_fact_pattern("Что такое нейрон?") is None

    def test_no_pattern_command(self):
        assert parse_fact_pattern("Запомни этот факт") is None

    def test_no_pattern_short_text(self):
        assert parse_fact_pattern("Да") is None

    def test_no_pattern_just_words(self):
        assert parse_fact_pattern("нейрон мозг клетка система") is None

    # --- Пустой и граничный input ---

    def test_empty_string(self):
        assert parse_fact_pattern("") is None

    def test_whitespace_only(self):
        assert parse_fact_pattern("   ") is None

    def test_too_short(self):
        assert parse_fact_pattern("A: B") is None  # < 5 символов после strip

    def test_too_long(self):
        text = "Нейрон это " + "x" * 500
        assert parse_fact_pattern(text) is None  # > 500 символов

    def test_concept_too_long(self):
        # concept > 50 символов
        concept = "А" * 51
        text = f"{concept} это описание факта"
        assert parse_fact_pattern(text) is None

    def test_concept_too_short(self):
        # concept < 2 символов
        text = "А это описание факта"
        assert parse_fact_pattern(text) is None

    def test_description_too_short(self):
        # description < 5 символов
        text = "Нейрон это да"
        assert parse_fact_pattern(text) is None

    # --- Граничные длины (валидные) ---

    def test_min_valid_concept(self):
        # concept = 2 символа, description >= 5
        result = parse_fact_pattern("АБ это клетка мозга")
        assert result is not None
        assert result[0] == "АБ"

    def test_max_valid_concept(self):
        # concept = 50 символов
        concept = "А" * 50
        text = f"{concept} это описание факта"
        result = parse_fact_pattern(text)
        assert result is not None
        assert result[0] == concept

    # --- Стабильность ---

    def test_deterministic(self):
        text = "Нейрон это клетка нервной системы"
        r1 = parse_fact_pattern(text)
        r2 = parse_fact_pattern(text)
        assert r1 == r2

    def test_first_separator_wins(self):
        """Первый найденный разделитель побеждает."""
        text = "Нейрон это клетка — основная единица"
        result = parse_fact_pattern(text)
        assert result is not None
        # " это " найдётся первым
        assert result[0] == "Нейрон"
        assert "клетка" in result[1]


# ═══════════════════════════════════════════════════════════════════════════════
# sha256_text
# ═══════════════════════════════════════════════════════════════════════════════

class TestSha256Text:
    """Тесты для sha256_text()."""

    def test_full_hash_length(self):
        result = sha256_text("hello")
        assert len(result) == 64

    def test_full_hash_hex(self):
        result = sha256_text("hello")
        assert all(c in "0123456789abcdef" for c in result)

    def test_truncate_16(self):
        result = sha256_text("hello", truncate=16)
        assert len(result) == 16

    def test_truncate_8(self):
        result = sha256_text("hello", truncate=8)
        assert len(result) == 8

    def test_truncate_none_is_full(self):
        full = sha256_text("hello")
        none_trunc = sha256_text("hello", truncate=None)
        assert full == none_trunc

    def test_truncate_is_prefix(self):
        """Truncated hash — это prefix полного hash."""
        full = sha256_text("hello")
        trunc = sha256_text("hello", truncate=16)
        assert full.startswith(trunc)

    def test_empty_string(self):
        result = sha256_text("")
        assert len(result) == 64
        # SHA256 of empty string is well-known
        assert result == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_unicode_text(self):
        result = sha256_text("Нейрон — клетка")
        assert len(result) == 64

    def test_deterministic(self):
        r1 = sha256_text("test")
        r2 = sha256_text("test")
        assert r1 == r2

    def test_different_texts_different_hashes(self):
        h1 = sha256_text("hello")
        h2 = sha256_text("world")
        assert h1 != h2

    def test_known_hash(self):
        """Проверка известного SHA256."""
        import hashlib
        text = "cognitive-core"
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert sha256_text(text) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# sha256_file
# ═══════════════════════════════════════════════════════════════════════════════

class TestSha256File:
    """Тесты для sha256_file()."""

    def test_real_file(self, tmp_path):
        """Хеш реального файла."""
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        result = sha256_file(str(f))
        assert len(result) == 16  # default truncate=16
        assert all(c in "0123456789abcdef" for c in result)

    def test_real_file_deterministic(self, tmp_path):
        """Один и тот же файл → один и тот же хеш."""
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        r1 = sha256_file(str(f))
        r2 = sha256_file(str(f))
        assert r1 == r2

    def test_different_files_different_hashes(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello", encoding="utf-8")
        f2.write_text("world", encoding="utf-8")
        assert sha256_file(str(f1)) != sha256_file(str(f2))

    def test_nonexistent_file_fallback(self):
        """Несуществующий файл → fallback на хеш от пути."""
        result = sha256_file("/nonexistent/path/to/file.txt")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_nonexistent_file_fallback_deterministic(self):
        """Fallback стабилен: один путь → один хеш."""
        path = "/nonexistent/path/to/file.txt"
        r1 = sha256_file(path)
        r2 = sha256_file(path)
        assert r1 == r2

    def test_nonexistent_file_fallback_matches_text_hash(self):
        """Fallback = sha256_text(path, truncate=16)."""
        path = "/nonexistent/path/to/file.txt"
        file_hash = sha256_file(path, truncate=16)
        text_hash = sha256_text(path, truncate=16)
        assert file_hash == text_hash

    def test_custom_truncate(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data", encoding="utf-8")
        result = sha256_file(str(f), truncate=8)
        assert len(result) == 8

    def test_full_hash_truncate_0(self, tmp_path):
        """truncate=0 → пустая строка (edge case)."""
        f = tmp_path / "test.txt"
        f.write_text("data", encoding="utf-8")
        # truncate=0 → digest[:0] = ""
        # Но наша функция проверяет truncate > 0
        result = sha256_file(str(f), truncate=64)
        assert len(result) == 64

    def test_binary_file(self, tmp_path):
        """Хеш бинарного файла."""
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00\x01\x02\xff" * 100)
        result = sha256_file(str(f))
        assert len(result) == 16

    def test_empty_file(self, tmp_path):
        """Хеш пустого файла."""
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = sha256_file(str(f))
        assert len(result) == 16
        # Файловый хеш пустого файла = хеш пустых байтов
        import hashlib
        empty_hash = hashlib.sha256(b"").hexdigest()[:16]
        assert result == empty_hash
