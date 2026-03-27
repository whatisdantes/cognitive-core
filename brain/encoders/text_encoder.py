"""
brain/encoders/text_encoder.py

Minimal Text Encoder — Этап E.

Основной путь:  sentence-transformers (paraphrase-multilingual-mpnet-base-v2, 768d)
Fallback:       navec (mean-pooled token embeddings, 300d)
Degraded:       нулевой вектор + warning

API:
    encode_event(PerceptEvent) → EncodedPercept   — основной
    encode(text, ...)          → EncodedPercept   — удобный wrapper
    encode_batch([PerceptEvent, ...]) → [EncodedPercept, ...]

metadata содержит:
    encoder_status:    "ok" | "fallback" | "degraded" | "failed"
    warnings:          List[str]
    encoding_time_ms:  float
    keywords:          List[str]
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any, Dict, List

import numpy as np

from brain.core.contracts import EncodedPercept, Modality
from brain.core.events import PerceptEvent
from brain.core.hash_utils import sha256_text as _sha256
from brain.core.text_utils import detect_language as _canonical_detect_language

logger = logging.getLogger(__name__)


# ─── Стоп-слова (MVP: минимальный набор ru + en) ─────────────────────────────

_STOP_WORDS_RU = frozenset(
    "и в на не что это как с по из за к о у а но от до он она они мы вы "
    "его её их был была было были быть бы же ли то так уже ещё тоже для "
    "при все всё этот эта эти тот та те свой своя своё свои который которая "
    "которое которые где когда если чтобы потому между через после перед "
    "только можно нужно надо очень более менее также однако поэтому".split()
)

_STOP_WORDS_EN = frozenset(
    "the a an is are was were be been being have has had do does did will "
    "would shall should may might can could of in to for on with at by from "
    "as into through during before after above below between under again "
    "further then once here there when where why how all both each few more "
    "most other some such no nor not only own same so than too very and but "
    "or if while about against".split()
)

_STOP_WORDS = _STOP_WORDS_RU | _STOP_WORDS_EN


# ─── Утилиты ─────────────────────────────────────────────────────────────────

def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    """L2-нормализация вектора. Нулевой вектор остаётся нулевым."""
    norm = float(np.linalg.norm(vec))
    if norm < 1e-12:
        return vec
    result: np.ndarray = vec / norm
    return result


def _detect_language(text: str) -> str:
    """
    Определение языка — делегирует в каноническую реализацию.

    Возвращает: 'ru', 'en', 'mixed', 'unknown'.
    """
    return _canonical_detect_language(text)


def _detect_message_type(text: str) -> str:
    """
    Эвристика определения типа сообщения.
    Возвращает: 'question', 'command', 'statement'.
    """
    stripped = text.strip()
    if not stripped:
        return "unknown"

    # Вопрос: заканчивается на ? или начинается с вопросительных слов
    if stripped.endswith("?"):
        return "question"
    first_word = stripped.split()[0].lower().rstrip(".,!?")
    question_words_ru = {"что", "кто", "где", "когда", "как", "почему", "зачем",
                         "какой", "какая", "какое", "какие", "сколько", "чем",
                         "откуда", "куда", "ли"}
    question_words_en = {"what", "who", "where", "when", "how", "why", "which",
                         "whose", "whom", "is", "are", "do", "does", "did",
                         "can", "could", "will", "would", "shall", "should"}
    if first_word in question_words_ru or first_word in question_words_en:
        return "question"

    # Команда: императивные маркеры
    command_words_ru = {"найди", "покажи", "открой", "запусти", "сделай",
                        "создай", "удали", "обнови", "проверь", "расскажи",
                        "объясни", "вычисли", "посчитай", "выведи", "загрузи"}
    command_words_en = {"find", "show", "open", "run", "create", "delete",
                        "update", "check", "tell", "explain", "compute",
                        "calculate", "print", "load", "start", "stop"}
    if first_word in command_words_ru or first_word in command_words_en:
        return "command"

    return "statement"


def _extract_keywords(text: str, top_n: int = 10) -> List[str]:
    """
    MVP keyword extraction: токенизация → фильтр стоп-слов → top-N по длине.
    """
    if not text or not text.strip():
        return []
    # Простая токенизация: слова из букв (кириллица + латиница)
    tokens = re.findall(r"[а-яёa-z]{3,}", text.lower())
    # Убрать стоп-слова
    filtered = [t for t in tokens if t not in _STOP_WORDS]
    # Уникальные, сортировка по длине (длинные = более информативные), потом по частоте
    from collections import Counter
    counts = Counter(filtered)
    # Сортировка: частота desc, длина desc
    ranked = sorted(counts.keys(), key=lambda w: (counts[w], len(w)), reverse=True)
    return ranked[:top_n]


# ─── TextEncoder ──────────────────────────────────────────────────────────────

class TextEncoder:
    """
    Minimal Text Encoder для text-only MVP.

    Основной режим:  sentence-transformers (768d)
    Fallback:        navec mean-pooled (300d)
    Degraded:        нулевой вектор + warning

    Использование:
        encoder = TextEncoder()
        result = encoder.encode_event(percept_event)
        result = encoder.encode("Нейрон — это клетка нервной системы")
    """

    # Имя модели по умолчанию
    DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    FALLBACK_DIM = 300
    PRIMARY_DIM = 768

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        use_fallback: bool = True,
        cache_enabled: bool = True,
    ):
        """
        Args:
            model_name:    имя sentence-transformers модели
            use_fallback:  пытаться ли загрузить navec при неудаче основной модели
            cache_enabled: включить in-memory кэш по SHA256(text)
        """
        self._model_name = model_name
        self._use_fallback = use_fallback
        self._cache_enabled = cache_enabled

        # Состояние
        self._st_model: Any = None   # sentence-transformers model
        self._navec: Any = None      # navec model
        self._mode: str = "failed"   # "primary" | "fallback" | "failed"
        self._vector_dim: int = 0

        # In-memory кэш: sha256 → np.ndarray
        self._cache: Dict[str, np.ndarray] = {}

        # Попытка загрузки
        self._try_load_primary()
        if self._mode != "primary" and self._use_fallback:
            self._try_load_fallback()

        if self._mode == "failed":
            logger.warning(
                "TextEncoder: ни sentence-transformers, ни navec не загружены. "
                "Режим: failed — будет возвращаться нулевой вектор."
            )

    # ─── Загрузка моделей ─────────────────────────────────────────────────

    def _try_load_primary(self) -> None:
        """Попытка загрузить sentence-transformers модель."""
        try:
            from sentence_transformers import SentenceTransformer
            self._st_model = SentenceTransformer(self._model_name)
            self._mode = "primary"
            self._vector_dim = self.PRIMARY_DIM
            logger.info(
                "TextEncoder: sentence-transformers загружен (%s, %dd)",
                self._model_name, self._vector_dim,
            )
        except Exception as exc:
            logger.warning(
                "TextEncoder: не удалось загрузить sentence-transformers: %s", exc
            )
            self._st_model = None

    def _try_load_fallback(self) -> None:
        """Попытка загрузить navec как fallback."""
        try:
            import os

            from navec import Navec

            # Ищем navec файл в стандартных местах
            navec_paths = [
                os.path.join(
                    os.path.dirname(__file__), "..", "data",
                    "navec_hudlit_v1_12B_500K_300d_100q.tar",
                ),
                os.path.expanduser(
                    "~/.navec/navec_hudlit_v1_12B_500K_300d_100q.tar"
                ),
            ]
            navec_path = None
            for p in navec_paths:
                if os.path.exists(p):
                    navec_path = p
                    break

            if navec_path is None:
                # Попробовать скачать через navec API
                try:
                    from navec import Navec as NavecLoader
                    # navec может иметь встроенный download
                    navec_path = NavecLoader.download("hudlit_12B_500K_300d_100q")
                except Exception:
                    pass

            if navec_path and os.path.exists(navec_path):
                self._navec = Navec.load(navec_path)
                self._mode = "fallback"
                self._vector_dim = self.FALLBACK_DIM
                logger.info("TextEncoder: navec загружен как fallback (%dd)", self._vector_dim)
            else:
                logger.warning("TextEncoder: navec модель не найдена на диске")
        except Exception as exc:
            logger.warning("TextEncoder: не удалось загрузить navec: %s", exc)
            self._navec = None

    # ─── Свойства ─────────────────────────────────────────────────────────

    @property
    def mode(self) -> str:
        """Текущий режим: 'primary', 'fallback', 'failed'."""
        return self._mode

    @property
    def vector_dim(self) -> int:
        """Размерность выходного вектора."""
        return self._vector_dim

    @property
    def model_name(self) -> str:
        """Имя используемой модели."""
        if self._mode == "primary":
            return self._model_name
        if self._mode == "fallback":
            return "navec_hudlit_300d"
        return "none"

    # ─── Основной API ─────────────────────────────────────────────────────

    def encode_event(self, percept: PerceptEvent) -> EncodedPercept:
        """
        Основной API: кодирует PerceptEvent → EncodedPercept.

        Переносит trace_id, session_id, cycle_id, source, quality из percept.
        """
        text = percept.content if isinstance(percept.content, str) else str(percept.content or "")

        return self._encode_impl(
            text=text,
            source=percept.source,
            quality=percept.quality,
            trace_id=percept.trace_id,
            session_id=percept.session_id,
            cycle_id=percept.cycle_id,
            percept_id=percept.trace_id,  # используем trace_id как percept_id
        )

    def encode(
        self,
        text: str,
        source: str = "user_input",
        quality: float = 1.0,
        trace_id: str = "",
        session_id: str = "",
        cycle_id: str = "",
    ) -> EncodedPercept:
        """
        Удобный wrapper: кодирует строку → EncodedPercept.
        """
        percept_id = trace_id or f"enc_{uuid.uuid4().hex[:8]}"
        return self._encode_impl(
            text=text,
            source=source,
            quality=quality,
            trace_id=trace_id,
            session_id=session_id,
            cycle_id=cycle_id,
            percept_id=percept_id,
        )

    def encode_batch(self, percepts: List[PerceptEvent]) -> List[EncodedPercept]:
        """
        Batch encoding: кодирует список PerceptEvent.
        Для primary mode использует batch-inference sentence-transformers.
        """
        if not percepts:
            return []

        texts = [
            p.content if isinstance(p.content, str) else str(p.content or "")
            for p in percepts
        ]

        # Для primary mode — batch encode через sentence-transformers
        if self._mode == "primary" and self._st_model is not None:
            return self._encode_batch_primary(percepts, texts)

        # Для fallback/failed — поштучно
        return [self.encode_event(p) for p in percepts]

    # ─── Внутренняя реализация ────────────────────────────────────────────

    def _encode_impl(
        self,
        text: str,
        source: str,
        quality: float,
        trace_id: str,
        session_id: str,
        cycle_id: str,
        percept_id: str,
    ) -> EncodedPercept:
        """Единая точка кодирования текста."""
        t0 = time.perf_counter()
        warnings: List[str] = []

        # Пустой / слишком короткий текст
        clean_text = (text or "").strip()
        if not clean_text:
            return self._make_result(
                percept_id=percept_id,
                text="",
                vector=np.zeros(max(self._vector_dim, 1), dtype=np.float32),
                source=source,
                quality=quality,
                language="unknown",
                message_type="unknown",
                encoder_status="failed",
                warnings=["empty_input"],
                t0=t0,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
            )

        # Проверить кэш
        text_hash = _sha256(clean_text)
        if self._cache_enabled and text_hash in self._cache:
            cached_vec = self._cache[text_hash]
            status = "ok" if self._mode == "primary" else (
                "fallback" if self._mode == "fallback" else "failed"
            )
            return self._make_result(
                percept_id=percept_id,
                text=clean_text,
                vector=cached_vec,
                source=source,
                quality=quality,
                language=_detect_language(clean_text),
                message_type=_detect_message_type(clean_text),
                encoder_status=status,
                warnings=[],
                t0=t0,
                trace_id=trace_id,
                session_id=session_id,
                cycle_id=cycle_id,
            )

        # Кодирование
        vector: np.ndarray
        encoder_status: str

        if self._mode == "primary":
            vector, encoder_status, enc_warnings = self._encode_primary(clean_text)
        elif self._mode == "fallback":
            vector, encoder_status, enc_warnings = self._encode_fallback(clean_text)
        else:
            vector = np.zeros(1, dtype=np.float32)
            encoder_status = "failed"
            enc_warnings = ["no_model_available"]

        warnings.extend(enc_warnings)

        # Кэшировать
        if self._cache_enabled and encoder_status in ("ok", "fallback"):
            self._cache[text_hash] = vector

        return self._make_result(
            percept_id=percept_id,
            text=clean_text,
            vector=vector,
            source=source,
            quality=quality,
            language=_detect_language(clean_text),
            message_type=_detect_message_type(clean_text),
            encoder_status=encoder_status,
            warnings=warnings,
            t0=t0,
            trace_id=trace_id,
            session_id=session_id,
            cycle_id=cycle_id,
        )

    def _encode_primary(self, text: str) -> tuple:
        """Кодирование через sentence-transformers."""
        try:
            vec = self._st_model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            vec = np.asarray(vec, dtype=np.float32).flatten()
            vec = _l2_normalize(vec)
            return vec, "ok", []
        except Exception as exc:
            logger.warning("TextEncoder primary encode failed: %s", exc)
            zeros = np.zeros(self._vector_dim, dtype=np.float32)
            return zeros, "degraded", [f"primary_error: {exc}"]

    def _encode_fallback(self, text: str) -> tuple:
        """Кодирование через navec (mean-pooled token embeddings)."""
        try:
            # Простая токенизация
            tokens = re.findall(r"[а-яёa-z0-9]+", text.lower())
            if not tokens:
                return (
                    np.zeros(self.FALLBACK_DIM, dtype=np.float32),
                    "degraded",
                    ["no_tokens_found"],
                )

            # Собрать векторы известных токенов
            vectors = []
            unknown_count = 0
            for token in tokens:
                if token in self._navec:
                    vectors.append(self._navec[token])
                else:
                    unknown_count += 1

            warnings = []
            if unknown_count > 0:
                warnings.append(f"unknown_tokens: {unknown_count}/{len(tokens)}")

            if not vectors:
                return (
                    np.zeros(self.FALLBACK_DIM, dtype=np.float32),
                    "degraded",
                    ["all_tokens_unknown"],
                )

            # Mean pooling + L2 norm
            mean_vec = np.mean(vectors, axis=0).astype(np.float32)
            mean_vec = _l2_normalize(mean_vec)

            status = "fallback"
            if unknown_count > len(tokens) * 0.8:
                status = "degraded"
                warnings.append("high_unknown_ratio")

            return mean_vec, status, warnings

        except Exception as exc:
            logger.warning("TextEncoder fallback encode failed: %s", exc)
            return (
                np.zeros(self.FALLBACK_DIM, dtype=np.float32),
                "failed",
                [f"fallback_error: {exc}"],
            )

    def _encode_batch_primary(
        self, percepts: List[PerceptEvent], texts: List[str]
    ) -> List[EncodedPercept]:
        """Batch encoding через sentence-transformers."""
        t0 = time.perf_counter()
        results = []

        try:
            # Batch encode
            clean_texts = [(t or "").strip() for t in texts]
            non_empty_mask = [bool(t) for t in clean_texts]
            non_empty_texts = [t for t, m in zip(clean_texts, non_empty_mask) if m]

            if non_empty_texts:
                vectors = self._st_model.encode(
                    non_empty_texts,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    batch_size=32,
                )
                vectors = np.asarray(vectors, dtype=np.float32)
            else:
                vectors = np.empty((0, self._vector_dim), dtype=np.float32)

            vec_idx = 0
            for i, percept in enumerate(percepts):
                text = clean_texts[i]
                if not text:
                    result = self._make_result(
                        percept_id=percept.trace_id,
                        text="",
                        vector=np.zeros(self._vector_dim, dtype=np.float32),
                        source=percept.source,
                        quality=percept.quality,
                        language="unknown",
                        message_type="unknown",
                        encoder_status="failed",
                        warnings=["empty_input"],
                        t0=t0,
                        trace_id=percept.trace_id,
                        session_id=percept.session_id,
                        cycle_id=percept.cycle_id,
                    )
                else:
                    vec = _l2_normalize(vectors[vec_idx])
                    vec_idx += 1

                    # Кэшировать
                    if self._cache_enabled:
                        self._cache[_sha256(text)] = vec

                    result = self._make_result(
                        percept_id=percept.trace_id,
                        text=text,
                        vector=vec,
                        source=percept.source,
                        quality=percept.quality,
                        language=_detect_language(text),
                        message_type=_detect_message_type(text),
                        encoder_status="ok",
                        warnings=[],
                        t0=t0,
                        trace_id=percept.trace_id,
                        session_id=percept.session_id,
                        cycle_id=percept.cycle_id,
                    )
                results.append(result)

        except Exception as exc:
            logger.warning("TextEncoder batch encode failed, falling back to single: %s", exc)
            return [self.encode_event(p) for p in percepts]

        return results

    # ─── Формирование результата ──────────────────────────────────────────

    def _make_result(
        self,
        percept_id: str,
        text: str,
        vector: np.ndarray,
        source: str,
        quality: float,
        language: str,
        message_type: str,
        encoder_status: str,
        warnings: List[str],
        t0: float,
        trace_id: str,
        session_id: str,
        cycle_id: str,
    ) -> EncodedPercept:
        """Собирает EncodedPercept из компонентов."""
        encoding_time_ms = (time.perf_counter() - t0) * 1000.0
        keywords = _extract_keywords(text) if text else []

        vec_dim = len(vector) if vector is not None else 0

        return EncodedPercept(
            percept_id=percept_id,
            modality=Modality.TEXT,
            vector=vector.tolist() if isinstance(vector, np.ndarray) else list(vector),
            text=text,
            quality=quality,
            source=source,
            language=language,
            message_type=message_type,
            encoder_model=self.model_name,
            vector_dim=vec_dim,
            metadata={
                "encoder_status": encoder_status,
                "warnings": warnings,
                "encoding_time_ms": round(encoding_time_ms, 3),
                "keywords": keywords,
            },
            trace_id=trace_id,
            session_id=session_id,
            cycle_id=cycle_id,
        )

    # ─── Утилиты ──────────────────────────────────────────────────────────

    def clear_cache(self) -> int:
        """Очистить in-memory кэш. Возвращает количество удалённых записей."""
        count = len(self._cache)
        self._cache.clear()
        return count

    def cache_size(self) -> int:
        """Количество записей в кэше."""
        return len(self._cache)

    def status(self) -> Dict[str, Any]:
        """Статус энкодера."""
        return {
            "mode": self._mode,
            "model_name": self.model_name,
            "vector_dim": self._vector_dim,
            "cache_enabled": self._cache_enabled,
            "cache_size": len(self._cache),
            "primary_loaded": self._st_model is not None,
            "fallback_loaded": self._navec is not None,
        }
