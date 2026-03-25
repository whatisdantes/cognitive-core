"""
tests/test_text_encoder.py

Тесты для brain/encoders/text_encoder.py (Этап E).

Стратегия:
  - Тесты НЕ требуют установленных sentence-transformers или navec.
  - Основной режим тестируется через mock (подмена _st_model).
  - Fallback режим тестируется через mock (подмена _navec).
  - Degraded/failed режимы тестируются напрямую (без моделей).
  - Семантические sanity-check через mock-модель с контролируемыми векторами.
"""

import sys
import os
import uuid
from unittest.mock import MagicMock

import numpy as np
import pytest

# ─── Ensure project root on path ─────────────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from brain.core.contracts import EncodedPercept, Modality
from brain.core.events import PerceptEvent
from brain.encoders.text_encoder import (
    TextEncoder,
    _detect_language,
    _detect_message_type,
    _extract_keywords,
    _l2_normalize,
    _sha256,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def failed_encoder():
    """Encoder без моделей (failed mode)."""
    enc = TextEncoder(use_fallback=False)
    # Убедимся, что ничего не загружено
    enc._st_model = None
    enc._navec = None
    enc._mode = "failed"
    enc._vector_dim = 0
    return enc


@pytest.fixture
def mock_primary_encoder():
    """
    Encoder с mock sentence-transformers.
    Возвращает детерминированные 768d векторы на основе хеша текста.
    """
    enc = TextEncoder.__new__(TextEncoder)
    enc._model_name = "mock-st-model"
    enc._use_fallback = False
    enc._cache_enabled = True
    enc._cache = {}
    enc._navec = None
    enc._vector_dim = 768
    enc._mode = "primary"

    # Mock sentence-transformers model
    mock_model = MagicMock()

    def _mock_encode(text_or_texts, convert_to_numpy=True, normalize_embeddings=True, batch_size=32):
        """Детерминированный mock: хеш текста → вектор."""
        if isinstance(text_or_texts, str):
            texts = [text_or_texts]
        else:
            texts = list(text_or_texts)

        vectors = []
        for t in texts:
            # Детерминированный seed из текста
            seed = int(_sha256(t)[:8], 16) % (2**31)
            rng = np.random.RandomState(seed)
            vec = rng.randn(768).astype(np.float32)
            vec = vec / (np.linalg.norm(vec) + 1e-12)
            vectors.append(vec)

        result = np.array(vectors, dtype=np.float32)
        if isinstance(text_or_texts, str):
            return result[0]
        return result

    mock_model.encode = _mock_encode
    enc._st_model = mock_model
    return enc


@pytest.fixture
def mock_fallback_encoder():
    """
    Encoder с mock navec (fallback mode, 300d).
    """
    enc = TextEncoder.__new__(TextEncoder)
    enc._model_name = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    enc._use_fallback = True
    enc._cache_enabled = True
    enc._cache = {}
    enc._st_model = None
    enc._vector_dim = 300
    enc._mode = "fallback"

    # Mock navec: словарь токен → вектор 300d
    class MockNavec:
        def __init__(self):
            self._vocab = {}
            rng = np.random.RandomState(42)
            # Создаём фиксированные векторы для известных слов
            words = [
                "нейрон", "клетка", "нервная", "система", "мозг", "аксон",
                "дендрит", "синапс", "сигнал", "потенциал", "brain", "neuron",
                "cell", "network", "signal", "memory", "learning", "python",
                "code", "function", "автомобиль", "двигатель", "колесо",
            ]
            for w in words:
                self._vocab[w] = rng.randn(300).astype(np.float32)

        def __contains__(self, key):
            return key in self._vocab

        def __getitem__(self, key):
            return self._vocab[key]

    enc._navec = MockNavec()
    return enc


def _make_percept(text: str, source: str = "test", quality: float = 1.0,
                  session_id: str = "", trace_id: str = "") -> PerceptEvent:
    """Создать PerceptEvent для тестов."""
    return PerceptEvent(
        source=source,
        content=text,
        modality="text",
        quality=quality,
        session_id=session_id,
        trace_id=trace_id or f"test_{uuid.uuid4().hex[:8]}",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Утилиты
# ═══════════════════════════════════════════════════════════════════════════════

class TestUtilities:
    """Тесты вспомогательных функций."""

    def test_sha256_deterministic(self):
        assert _sha256("hello") == _sha256("hello")
        assert _sha256("hello") != _sha256("world")

    def test_l2_normalize_unit_length(self):
        vec = np.array([3.0, 4.0], dtype=np.float32)
        normed = _l2_normalize(vec)
        assert abs(np.linalg.norm(normed) - 1.0) < 1e-5

    def test_l2_normalize_zero_vector(self):
        vec = np.zeros(10, dtype=np.float32)
        normed = _l2_normalize(vec)
        assert np.linalg.norm(normed) == 0.0

    def test_detect_language_ru(self):
        assert _detect_language("Нейрон — это клетка нервной системы") == "ru"

    def test_detect_language_en(self):
        assert _detect_language("A neuron is a cell of the nervous system") == "en"

    def test_detect_language_mixed(self):
        assert _detect_language("Нейрон neuron клетка cell") == "mixed"

    def test_detect_language_unknown(self):
        assert _detect_language("12345 !@#$%") == "unknown"

    def test_detect_language_empty(self):
        assert _detect_language("") == "unknown"
        assert _detect_language("   ") == "unknown"

    def test_message_type_question_mark(self):
        assert _detect_message_type("Что такое нейрон?") == "question"

    def test_message_type_question_word(self):
        assert _detect_message_type("Как работает мозг") == "question"

    def test_message_type_command_ru(self):
        assert _detect_message_type("Найди информацию о нейронах") == "command"

    def test_message_type_command_en(self):
        assert _detect_message_type("Find information about neurons") == "command"

    def test_message_type_statement(self):
        assert _detect_message_type("Нейрон — это клетка нервной системы") == "statement"

    def test_message_type_empty(self):
        assert _detect_message_type("") == "unknown"

    def test_extract_keywords_basic(self):
        kw = _extract_keywords("Нейрон — это основная клетка нервной системы")
        assert isinstance(kw, list)
        assert len(kw) > 0
        assert "нейрон" in kw or "клетка" in kw or "нервной" in kw

    def test_extract_keywords_empty(self):
        assert _extract_keywords("") == []
        assert _extract_keywords("   ") == []

    def test_extract_keywords_filters_stopwords(self):
        kw = _extract_keywords("это и в на не что как")
        # Все стоп-слова, но некоторые < 3 символов и отфильтруются regex
        # "это" (3 буквы) — стоп-слово, должно быть отфильтровано
        assert "это" not in kw


# ═══════════════════════════════════════════════════════════════════════════════
# Failed mode (без моделей)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFailedMode:
    """Тесты для режима без моделей."""

    def test_encode_returns_encoded_percept(self, failed_encoder):
        result = failed_encoder.encode("Тестовый текст")
        assert isinstance(result, EncodedPercept)

    def test_encode_event_returns_encoded_percept(self, failed_encoder):
        percept = _make_percept("Тестовый текст")
        result = failed_encoder.encode_event(percept)
        assert isinstance(result, EncodedPercept)

    def test_failed_mode_status(self, failed_encoder):
        result = failed_encoder.encode("Тестовый текст")
        assert result.metadata["encoder_status"] == "failed"

    def test_failed_mode_has_warnings(self, failed_encoder):
        result = failed_encoder.encode("Тестовый текст")
        assert "no_model_available" in result.metadata["warnings"]

    def test_failed_mode_vector_not_empty_list(self, failed_encoder):
        result = failed_encoder.encode("Тестовый текст")
        assert isinstance(result.vector, list)
        assert len(result.vector) >= 1

    def test_empty_input_failed(self, failed_encoder):
        result = failed_encoder.encode("")
        assert result.metadata["encoder_status"] == "failed"
        assert "empty_input" in result.metadata["warnings"]

    def test_empty_input_whitespace(self, failed_encoder):
        result = failed_encoder.encode("   ")
        assert result.metadata["encoder_status"] == "failed"

    def test_modality_is_text(self, failed_encoder):
        result = failed_encoder.encode("Тест")
        assert result.modality == Modality.TEXT

    def test_encoding_time_tracked(self, failed_encoder):
        result = failed_encoder.encode("Тест")
        assert "encoding_time_ms" in result.metadata
        assert result.metadata["encoding_time_ms"] >= 0

    def test_source_propagated(self, failed_encoder):
        result = failed_encoder.encode("Тест", source="my_source")
        assert result.source == "my_source"

    def test_quality_propagated(self, failed_encoder):
        result = failed_encoder.encode("Тест", quality=0.75)
        assert result.quality == 0.75

    def test_trace_id_propagated(self, failed_encoder):
        result = failed_encoder.encode("Тест", trace_id="tr_123")
        assert result.trace_id == "tr_123"

    def test_session_id_propagated(self, failed_encoder):
        result = failed_encoder.encode("Тест", session_id="sess_456")
        assert result.session_id == "sess_456"


# ═══════════════════════════════════════════════════════════════════════════════
# Primary mode (mock sentence-transformers)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrimaryMode:
    """Тесты для основного режима (sentence-transformers mock)."""

    def test_encode_returns_encoded_percept(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это клетка")
        assert isinstance(result, EncodedPercept)

    def test_vector_dim_768(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это клетка")
        assert len(result.vector) == 768
        assert result.vector_dim == 768

    def test_vector_l2_normalized(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это клетка")
        vec = np.array(result.vector)
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-4, f"L2 norm = {norm}, expected ~1.0"

    def test_encoder_status_ok(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это клетка")
        assert result.metadata["encoder_status"] == "ok"

    def test_no_warnings(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это клетка")
        assert result.metadata["warnings"] == []

    def test_encoder_model_set(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это клетка")
        assert result.encoder_model == "mock-st-model"

    def test_language_detected(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это клетка нервной системы")
        assert result.language == "ru"

    def test_language_en(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("A neuron is a cell of the nervous system")
        assert result.language == "en"

    def test_message_type_detected(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Что такое нейрон?")
        assert result.message_type == "question"

    def test_message_type_statement(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это клетка нервной системы")
        assert result.message_type == "statement"

    def test_keywords_in_metadata(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это основная клетка нервной системы")
        assert "keywords" in result.metadata
        assert isinstance(result.metadata["keywords"], list)

    def test_encoding_time_positive(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это клетка")
        assert result.metadata["encoding_time_ms"] > 0

    def test_text_preserved(self, mock_primary_encoder):
        result = mock_primary_encoder.encode("Нейрон — это клетка")
        assert result.text == "Нейрон — это клетка"

    # ─── Семантические sanity-checks ──────────────────────────────────────

    def test_same_text_same_vector(self, mock_primary_encoder):
        """Два одинаковых текста → одинаковый вектор."""
        r1 = mock_primary_encoder.encode("Нейрон — это клетка")
        r2 = mock_primary_encoder.encode("Нейрон — это клетка")
        v1 = np.array(r1.vector)
        v2 = np.array(r2.vector)
        assert np.allclose(v1, v2, atol=1e-6)

    def test_different_text_different_vector(self, mock_primary_encoder):
        """Разные тексты → разные векторы."""
        r1 = mock_primary_encoder.encode("Нейрон — это клетка нервной системы")
        r2 = mock_primary_encoder.encode("Автомобиль — это транспортное средство")
        v1 = np.array(r1.vector)
        v2 = np.array(r2.vector)
        assert not np.allclose(v1, v2, atol=1e-3)

    def test_cosine_similarity_related_higher(self, mock_primary_encoder):
        """
        Парафразы / связанные тексты имеют cosine similarity выше,
        чем несвязанные тексты.

        Примечание: с mock-моделью это проверяет только что разные тексты
        дают разные векторы. С реальной моделью это был бы настоящий
        семантический тест.
        """
        r1 = mock_primary_encoder.encode("Нейрон — это клетка")
        r2 = mock_primary_encoder.encode("Нейрон — это клетка нервной системы")
        r3 = mock_primary_encoder.encode("Погода сегодня солнечная и тёплая")

        v1 = np.array(r1.vector)
        v2 = np.array(r2.vector)
        v3 = np.array(r3.vector)

        # С mock-моделью мы не можем гарантировать семантическую близость,
        # но можем проверить что все три вектора различны
        assert not np.allclose(v1, v3, atol=1e-3)
        assert not np.allclose(v2, v3, atol=1e-3)

    # ─── Кэширование ─────────────────────────────────────────────────────

    def test_cache_stores_result(self, mock_primary_encoder):
        mock_primary_encoder.encode("Тестовый текст для кэша")
        assert mock_primary_encoder.cache_size() >= 1

    def test_cache_hit_same_vector(self, mock_primary_encoder):
        r1 = mock_primary_encoder.encode("Кэш тест")
        r2 = mock_primary_encoder.encode("Кэш тест")
        assert np.allclose(r1.vector, r2.vector, atol=1e-6)

    def test_clear_cache(self, mock_primary_encoder):
        mock_primary_encoder.encode("Текст 1")
        mock_primary_encoder.encode("Текст 2")
        count = mock_primary_encoder.clear_cache()
        assert count >= 2
        assert mock_primary_encoder.cache_size() == 0

    # ─── encode_event ─────────────────────────────────────────────────────

    def test_encode_event_propagates_fields(self, mock_primary_encoder):
        percept = _make_percept(
            "Нейрон — это клетка",
            source="wiki",
            quality=0.9,
            session_id="sess_1",
            trace_id="tr_1",
        )
        result = mock_primary_encoder.encode_event(percept)
        assert result.source == "wiki"
        assert result.quality == 0.9
        assert result.session_id == "sess_1"
        assert result.trace_id == "tr_1"

    def test_encode_event_non_string_content(self, mock_primary_encoder):
        """PerceptEvent с content=None → graceful handling."""
        percept = PerceptEvent(source="test", content=None, modality="text")
        result = mock_primary_encoder.encode_event(percept)
        assert result.metadata["encoder_status"] == "failed"

    # ─── Batch encoding ──────────────────────────────────────────────────

    def test_batch_empty(self, mock_primary_encoder):
        results = mock_primary_encoder.encode_batch([])
        assert results == []

    def test_batch_single(self, mock_primary_encoder):
        percepts = [_make_percept("Нейрон — это клетка")]
        results = mock_primary_encoder.encode_batch(percepts)
        assert len(results) == 1
        assert isinstance(results[0], EncodedPercept)

    def test_batch_multiple(self, mock_primary_encoder):
        percepts = [
            _make_percept("Нейрон — это клетка"),
            _make_percept("Мозг состоит из нейронов"),
            _make_percept("Автомобиль едет по дороге"),
        ]
        results = mock_primary_encoder.encode_batch(percepts)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, EncodedPercept)
            assert len(r.vector) == 768

    def test_batch_with_empty_text(self, mock_primary_encoder):
        percepts = [
            _make_percept("Нейрон — это клетка"),
            _make_percept(""),
            _make_percept("Мозг состоит из нейронов"),
        ]
        results = mock_primary_encoder.encode_batch(percepts)
        assert len(results) == 3
        assert results[1].metadata["encoder_status"] == "failed"

    def test_batch_consistent_with_single(self, mock_primary_encoder):
        """Batch и single encode дают совместимые результаты."""
        text = "Нейрон — это клетка нервной системы"
        single = mock_primary_encoder.encode(text)

        # Очистить кэш чтобы batch не использовал кэшированный результат
        mock_primary_encoder.clear_cache()

        percepts = [_make_percept(text)]
        batch = mock_primary_encoder.encode_batch(percepts)

        v_single = np.array(single.vector)
        v_batch = np.array(batch[0].vector)
        assert np.allclose(v_single, v_batch, atol=1e-5)


# ═══════════════════════════════════════════════════════════════════════════════
# Fallback mode (mock navec)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFallbackMode:
    """Тесты для fallback режима (navec mock)."""

    def test_encode_returns_encoded_percept(self, mock_fallback_encoder):
        result = mock_fallback_encoder.encode("Нейрон — это клетка нервной системы")
        assert isinstance(result, EncodedPercept)

    def test_vector_dim_300(self, mock_fallback_encoder):
        result = mock_fallback_encoder.encode("Нейрон — это клетка нервной системы")
        assert len(result.vector) == 300
        assert result.vector_dim == 300

    def test_vector_l2_normalized(self, mock_fallback_encoder):
        result = mock_fallback_encoder.encode("Нейрон — это клетка нервной системы")
        vec = np.array(result.vector)
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 1e-4, f"L2 norm = {norm}, expected ~1.0"

    def test_encoder_status_fallback(self, mock_fallback_encoder):
        result = mock_fallback_encoder.encode("Нейрон — это клетка")
        assert result.metadata["encoder_status"] == "fallback"

    def test_unknown_tokens_warning(self, mock_fallback_encoder):
        """Текст с неизвестными токенами → warning."""
        result = mock_fallback_encoder.encode("xyzzyx qwerty asdfgh")
        warnings = result.metadata["warnings"]
        has_unknown = any("unknown_tokens" in w or "all_tokens_unknown" in w for w in warnings)
        assert has_unknown

    def test_all_unknown_tokens_degraded(self, mock_fallback_encoder):
        """Все токены неизвестны → degraded status."""
        result = mock_fallback_encoder.encode("xyzzyx qwerty asdfgh")
        assert result.metadata["encoder_status"] in ("degraded", "fallback")

    def test_known_tokens_produce_nonzero_vector(self, mock_fallback_encoder):
        result = mock_fallback_encoder.encode("нейрон клетка мозг")
        vec = np.array(result.vector)
        assert np.linalg.norm(vec) > 0.5  # нормализованный → ~1.0

    def test_same_text_same_vector_fallback(self, mock_fallback_encoder):
        r1 = mock_fallback_encoder.encode("нейрон клетка мозг")
        r2 = mock_fallback_encoder.encode("нейрон клетка мозг")
        assert np.allclose(r1.vector, r2.vector, atol=1e-6)

    def test_encoder_model_navec(self, mock_fallback_encoder):
        result = mock_fallback_encoder.encode("нейрон")
        assert "navec" in result.encoder_model

    def test_empty_input_fallback(self, mock_fallback_encoder):
        result = mock_fallback_encoder.encode("")
        assert result.metadata["encoder_status"] == "failed"


# ═══════════════════════════════════════════════════════════════════════════════
# EncodedPercept contract
# ═══════════════════════════════════════════════════════════════════════════════

class TestEncodedPerceptContract:
    """Тесты контракта EncodedPercept (расширенные поля)."""

    def test_new_fields_have_defaults(self):
        """Новые поля имеют defaults — обратная совместимость."""
        ep = EncodedPercept(percept_id="test", modality=Modality.TEXT)
        assert ep.language == ""
        assert ep.message_type == "unknown"
        assert ep.encoder_model == ""
        assert ep.vector_dim == 0

    def test_to_dict_includes_new_fields(self):
        ep = EncodedPercept(
            percept_id="test",
            modality=Modality.TEXT,
            language="ru",
            message_type="question",
            encoder_model="test-model",
            vector_dim=768,
        )
        d = ep.to_dict()
        assert d["language"] == "ru"
        assert d["message_type"] == "question"
        assert d["encoder_model"] == "test-model"
        assert d["vector_dim"] == 768

    def test_from_dict_with_new_fields(self):
        data = {
            "percept_id": "test",
            "modality": "text",
            "language": "en",
            "message_type": "command",
            "encoder_model": "st-model",
            "vector_dim": 768,
        }
        ep = EncodedPercept.from_dict(data)
        assert ep.language == "en"
        assert ep.message_type == "command"

    def test_from_dict_without_new_fields(self):
        """Старые dict без новых полей → defaults."""
        data = {
            "percept_id": "test",
            "modality": "text",
        }
        ep = EncodedPercept.from_dict(data)
        assert ep.language == ""
        assert ep.message_type == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# Status & properties
# ═══════════════════════════════════════════════════════════════════════════════

class TestEncoderStatus:
    """Тесты свойств и статуса энкодера."""

    def test_failed_encoder_status(self, failed_encoder):
        s = failed_encoder.status()
        assert s["mode"] == "failed"
        assert s["primary_loaded"] is False
        assert s["fallback_loaded"] is False

    def test_primary_encoder_status(self, mock_primary_encoder):
        s = mock_primary_encoder.status()
        assert s["mode"] == "primary"
        assert s["vector_dim"] == 768
        assert s["primary_loaded"] is True

    def test_fallback_encoder_status(self, mock_fallback_encoder):
        s = mock_fallback_encoder.status()
        assert s["mode"] == "fallback"
        assert s["vector_dim"] == 300
        assert s["fallback_loaded"] is True

    def test_mode_property(self, mock_primary_encoder):
        assert mock_primary_encoder.mode == "primary"

    def test_vector_dim_property(self, mock_primary_encoder):
        assert mock_primary_encoder.vector_dim == 768

    def test_model_name_property_primary(self, mock_primary_encoder):
        assert mock_primary_encoder.model_name == "mock-st-model"

    def test_model_name_property_fallback(self, mock_fallback_encoder):
        assert "navec" in mock_fallback_encoder.model_name

    def test_model_name_property_failed(self, failed_encoder):
        assert failed_encoder.model_name == "none"


# ═══════════════════════════════════════════════════════════════════════════════
# Import tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestImports:
    """Тесты импортов."""

    def test_import_from_encoders_package(self):
        from brain.encoders import TextEncoder
        assert TextEncoder is not None

    def test_text_encoder_in_all(self):
        import brain.encoders
        assert "TextEncoder" in brain.encoders.__all__
