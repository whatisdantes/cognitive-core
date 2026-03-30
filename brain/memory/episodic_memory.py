"""
episodic_memory.py — Эпизодическая память мозга (история событий).

Эпизодическая память — это "дневник" мозга:
хронологическая запись всего, что мозг воспринял, сделал или подумал.

Принципы:
  - Каждый эпизод привязан ко времени и источнику
  - Кросс-модальные доказательства (text/image/audio/video)
  - Поиск по времени, концепту, источнику, тегам
  - Персистентность: JSON на диск
  - Importance-based retention: важные эпизоды не удаляются
  - Resource-aware: при нехватке RAM — выгружает старые эпизоды
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .storage import MemoryDatabase

# ─── Вспомогательные функции для поиска ─────────────────────────────────────

# Стоп-слова русского языка (предлоги, союзы, частицы, местоимения)
_STOP_WORDS_RU: frozenset[str] = frozenset({
    "в", "на", "и", "с", "по", "к", "у", "о", "из", "за", "от", "до",
    "это", "что", "как", "не", "а", "но", "или", "то", "же", "ли",
    "бы", "ни", "да", "нет", "так", "вот", "уже", "ещё", "ещe",
    "при", "для", "без", "под", "над", "об", "со", "во", "ко",
    "ведь", "ну", "ой", "эй",
    "the", "a", "an", "of", "in", "on", "at", "to", "is", "are",
})

# Типичные падежные/числовые окончания русского языка (от длинных к коротким)
# Используется только как fallback, когда pymorphy3 недоступен
_RU_SUFFIXES: tuple[str, ...] = (
    "ами", "ями",                  # творительный мн.ч.
    "ов", "ев", "ей",              # родительный мн.ч.
    "ах", "ях",                    # предложный мн.ч.
    "ом", "ем", "ём",              # творительный ед.ч.
    "ого", "его", "ёго",           # родительный ед.ч.
    "ому", "ему",                  # дательный ед.ч.
    "ую", "юю",                    # винительный ед.ч. (жен.)
    "ие", "ые",                    # именительный мн.ч. (прил.)
    "ий", "ый",                    # именительный ед.ч. (прил.)
    "ая", "яя",                    # именительный ед.ч. (жен. прил.)
    "ть", "ться",                  # инфинитив
    "ет", "ёт", "ит",              # настоящее время
    "ют", "ут",                    # настоящее время мн.ч.
    "ал", "ял", "ил",              # прошедшее время
    "е", "у", "а", "и", "ы",      # короткие окончания (последними)
)

# ─── pymorphy3 (опциональная зависимость) ────────────────────────────────────
try:
    import pymorphy3 as _pymorphy3_mod
    _morph = _pymorphy3_mod.MorphAnalyzer()
    _HAS_MORPH = True
    _logger_init = logging.getLogger(__name__)
    _logger_init.debug("pymorphy3 доступен — используется морфологическая лемматизация")
except Exception:
    _morph = None
    _HAS_MORPH = False

# Паттерн для определения кириллических слов (pymorphy3 работает только с русским)
_RE_CYRILLIC = re.compile(r"[а-яё]")


def _stem_ru(word: str) -> str:
    """
    Наивный суффикс-стриппер для русского языка (fallback без pymorphy3).

    Обрезает типичные падежные/глагольные окончания.
    Точность ~70% (достаточно для overlap-скоринга).

    Примеры:
        "нейронов" → "нейрон"
        "мозге"    → "мозг"
        "человека" → "человек"
        "миллиардов" → "миллиард"
    """
    if len(word) <= 3:
        return word
    for suffix in _RU_SUFFIXES:
        # Минимальная длина основы — 3 символа
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


@lru_cache(maxsize=4096)
def _lemmatize(word: str) -> str:
    """
    Лемматизировать одно слово.

    Если pymorphy3 доступен — использует морфологический анализ (точность ~96%).
    Иначе — наивный суффикс-стриппер _stem_ru() (точность ~70%).

    Кэшируется через lru_cache(4096) — покрывает типичный сеанс без повторных вычислений.

    Примеры (с pymorphy3):
        "содержит"     → "содержать"
        "электрические" → "электрический"
        "мыши"         → "мышь"
        "нейронов"     → "нейрон"
    """
    if _HAS_MORPH and _morph is not None and _RE_CYRILLIC.search(word):
        try:
            parsed = _morph.parse(word)
            if parsed:
                return str(parsed[0].normal_form)
        except Exception:
            pass
    return _stem_ru(word)


def _tokenize(text: str) -> frozenset[str]:
    """
    Токенизировать текст: извлечь слова, убрать стоп-слова, лемматизировать.

    Использует pymorphy3 если доступен, иначе — наивный стеммер.
    Возвращает frozenset лемматизированных токенов.

    Примеры (с pymorphy3):
        "сколько нейронов в мозге человека?" →
            frozenset({"сколько", "нейрон", "мозг", "человек"})
        "мозг человека содержит около 86 миллиардов нейронов" →
            frozenset({"мозг", "человек", "содержать", "около", "86", "миллиард", "нейрон"})

    Overlap для q04: {"нейрон", "мозг", "человек"} = 3/4 → score=0.45 (вместо 0.216)
    """
    words = re.findall(r"[а-яёa-z0-9]+", text.lower())
    return frozenset(
        _lemmatize(w) for w in words
        if w not in _STOP_WORDS_RU and len(w) > 1
    )

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


# ─── Модальное доказательство ────────────────────────────────────────────────

@dataclass
class ModalEvidence:
    """
    Одно доказательство из конкретной модальности.

    Пример: текстовый фрагмент из документа, регион изображения, сегмент аудио.
    """
    modality: str           # 'text' | 'image' | 'audio' | 'video'
    source: str             # путь к файлу, URL, "user_input"
    content_ref: str = ""   # фрагмент текста, описание региона, временной диапазон
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "modality": self.modality,
            "source": self.source,
            "content_ref": self.content_ref,
            "confidence": round(self.confidence, 4),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModalEvidence":
        return cls(
            modality=d["modality"],
            source=d["source"],
            content_ref=d.get("content_ref", ""),
            confidence=d.get("confidence", 1.0),
            metadata=d.get("metadata", {}),
        )


# ─── Эпизод ──────────────────────────────────────────────────────────────────

@dataclass
class Episode:
    """
    Один эпизод — событие в истории мозга.

    Атрибуты:
        episode_id      — уникальный ID
        ts              — время события (unix timestamp)
        content         — основное содержимое (текст, описание)
        modality        — основная модальность ('text', 'image', 'audio', 'mixed')
        source          — источник события
        importance      — важность (0.0 — 1.0); важные не удаляются
        confidence      — уверенность в достоверности (0.0 — 1.0)
        tags            — теги для поиска
        concepts        — связанные понятия (ключевые слова)
        modal_evidence  — кросс-модальные доказательства
        trace_id        — ID трассировки (связь с когнитивным событием)
        session_id      — ID сессии
        access_count    — сколько раз обращались
    """
    episode_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    ts: float = field(default_factory=time.time)
    content: str = ""
    modality: str = "text"
    source: str = ""
    importance: float = 0.5
    confidence: float = 1.0
    tags: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)
    modal_evidence: List[ModalEvidence] = field(default_factory=list)
    trace_id: str = ""
    session_id: str = ""
    access_count: int = 0
    embedding: Optional[List[float]] = field(default=None, repr=False)

    def touch(self):
        """Зафиксировать обращение."""
        self.access_count += 1

    def age_hours(self) -> float:
        """Возраст эпизода в часах."""
        return (time.time() - self.ts) / 3600

    def age_days(self) -> float:
        """Возраст эпизода в днях."""
        return (time.time() - self.ts) / 86400

    def add_evidence(self, evidence: ModalEvidence):
        """Добавить модальное доказательство."""
        self.modal_evidence.append(evidence)

    def get_evidence_by_modality(self, modality: str) -> List[ModalEvidence]:
        """Получить доказательства определённой модальности."""
        return [e for e in self.modal_evidence if e.modality == modality]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "ts": self.ts,
            "content": self.content,
            "modality": self.modality,
            "source": self.source,
            "importance": round(self.importance, 4),
            "confidence": round(self.confidence, 4),
            "tags": self.tags,
            "concepts": self.concepts,
            "modal_evidence": [e.to_dict() for e in self.modal_evidence],
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "access_count": self.access_count,
            "embedding": self.embedding,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Episode":
        ep = cls(
            episode_id=d.get("episode_id", uuid.uuid4().hex),
            ts=d.get("ts", time.time()),
            content=d.get("content", ""),
            modality=d.get("modality", "text"),
            source=d.get("source", ""),
            importance=d.get("importance", 0.5),
            confidence=d.get("confidence", 1.0),
            tags=d.get("tags", []),
            concepts=d.get("concepts", []),
            trace_id=d.get("trace_id", ""),
            session_id=d.get("session_id", ""),
            access_count=d.get("access_count", 0),
            embedding=d.get("embedding"),
        )
        ep.modal_evidence = [ModalEvidence.from_dict(e) for e in d.get("modal_evidence", [])]
        return ep

    def __repr__(self) -> str:
        content_preview = self.content[:60] + "..." if len(self.content) > 60 else self.content
        return (
            f"Episode('{content_preview}' | "
            f"mod={self.modality} | imp={self.importance:.2f} | "
            f"age={self.age_hours():.1f}h)"
        )


# ─── Эпизодическая память ────────────────────────────────────────────────────

class EpisodicMemory:
    """
    Эпизодическая память — хронологическая история событий мозга.

    Хранит всё, что мозг воспринял, сделал или подумал.
    Работает в RAM, персистируется в JSON.

    Параметры:
        data_path       — путь к JSON-файлу
        max_episodes    — максимальное количество эпизодов в RAM
        importance_threshold — порог важности для защиты от удаления
        autosave_every  — автосохранение каждые N операций записи
    """

    IMPORTANCE_PROTECT = 0.8    # эпизоды выше этого порога не удаляются

    def __init__(
        self,
        data_path: str = "brain/data/memory/episodes.json",
        max_episodes: int = 5_000,
        importance_threshold: float = IMPORTANCE_PROTECT,
        autosave_every: int = 20,
        storage_backend: str = "auto",
        db: Optional["MemoryDatabase"] = None,
    ):
        self._data_path = data_path
        self._max_episodes = max_episodes
        self._importance_threshold = importance_threshold
        self._autosave_every = autosave_every
        self._db = db

        # Определяем backend
        if storage_backend == "auto":
            self._backend = "sqlite" if db is not None else "json"
        else:
            self._backend = storage_backend

        self._lock = threading.RLock()
        self._episodes: List[Episode] = []          # хронологический список
        self._index_by_id: Dict[str, Episode] = {}  # быстрый доступ по ID
        self._index_by_concept: Dict[str, List[str]] = {}  # concept → [episode_ids]

        self._write_count = 0
        self._load_count = 0

        self._load()

    # ─── Основные операции ───────────────────────────────────────────────────

    def store(
        self,
        content: str,
        modality: str = "text",
        source: str = "",
        importance: float = 0.5,
        confidence: float = 1.0,
        tags: Optional[List[str]] = None,
        concepts: Optional[List[str]] = None,
        modal_evidence: Optional[List[ModalEvidence]] = None,
        trace_id: str = "",
        session_id: str = "",
    ) -> Episode:
        """
        Сохранить новый эпизод.

        Returns:
            Созданный Episode
        """
        episode = Episode(
            content=content,
            modality=modality,
            source=source,
            importance=importance,
            confidence=confidence,
            tags=tags or [],
            concepts=concepts or [],
            modal_evidence=modal_evidence or [],
            trace_id=trace_id,
            session_id=session_id,
        )

        with self._lock:
            # Проверяем лимит
            if len(self._episodes) >= self._adaptive_max():
                self._evict_oldest()

            self._episodes.append(episode)
            self._index_by_id[episode.episode_id] = episode

            # Индексируем по концептам
            for concept in episode.concepts:
                key = concept.lower().strip()
                if key not in self._index_by_concept:
                    self._index_by_concept[key] = []
                self._index_by_concept[key].append(episode.episode_id)

            self._write_count += 1
            self._maybe_autosave()
        return episode

    def get_by_id(self, episode_id: str) -> Optional[Episode]:
        """Получить эпизод по ID."""
        with self._lock:
            ep = self._index_by_id.get(episode_id)
            if ep:
                ep.touch()
                self._load_count += 1
            return ep

    def get_recent(self, n: int = 10, modality: Optional[str] = None) -> List[Episode]:
        """
        Получить последние N эпизодов.

        Args:
            n:        количество эпизодов
            modality: фильтр по модальности

        Returns:
            Список эпизодов (новые первые)
        """
        with self._lock:
            episodes = list(self._episodes)  # snapshot
            if modality:
                episodes = [e for e in episodes if e.modality == modality]

            result = episodes[-n:][::-1]  # последние N, в обратном порядке
            for ep in result:
                ep.touch()
            return result

    def retrieve_by_concept(
        self,
        concept: str,
        top_n: int = 10,
        min_importance: float = 0.0,
    ) -> List[Episode]:
        """
        Найти эпизоды, связанные с понятием.

        Returns:
            Список эпизодов, отсортированных по важности и времени
        """
        concept_key = concept.lower().strip()

        with self._lock:
            episode_ids = list(self._index_by_concept.get(concept_key, []))

            results: List[Episode] = []
            seen: set[str] = set()
            for ep_id in episode_ids:
                ep = self._index_by_id.get(ep_id)
                if ep and ep.importance >= min_importance:
                    results.append(ep)
                    seen.add(ep.episode_id)

            # Также ищем по тексту (O(1) проверка дубликатов через seen)
            for ep in self._episodes:
                if ep.episode_id not in seen and concept_key in ep.content.lower():
                    if ep.importance >= min_importance:
                        results.append(ep)
                        seen.add(ep.episode_id)

            results.sort(key=lambda e: (e.importance, e.ts), reverse=True)
            result = results[:top_n]
            for ep in result:
                ep.touch()
            self._load_count += len(result)
            return result

    def retrieve_by_time(
        self,
        start_ts: float,
        end_ts: Optional[float] = None,
        modality: Optional[str] = None,
    ) -> List[Episode]:
        """
        Найти эпизоды в временном диапазоне.

        Args:
            start_ts:   начало диапазона (unix timestamp)
            end_ts:     конец диапазона (None = до сейчас)
            modality:   фильтр по модальности

        Returns:
            Список эпизодов в хронологическом порядке
        """
        end_ts = end_ts or time.time()
        with self._lock:
            results = [
                ep for ep in self._episodes
                if start_ts <= ep.ts <= end_ts
                and (modality is None or ep.modality == modality)
            ]
            for ep in results:
                ep.touch()
            return results

    def search(
        self,
        query: str,
        top_n: int = 10,
        modality: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_importance: float = 0.0,
        last_n_hours: Optional[float] = None,
    ) -> List[Episode]:
        """
        Полнотекстовый поиск по эпизодам.

        Скоринг (двухуровневый):
          1. Полное совпадение строки запроса → score += 0.6 (точный match)
          2. Пословный overlap (fallback) → score += 0.6 * overlap_ratio
             Позволяет находить эпизоды по длинным запросам, например:
             "сколько нейронов в мозге человека?" → Fact3 ("мозг человека
             содержит около 86 миллиардов нейронов") получает overlap=2/5=0.4.

        Args:
            query:          строка поиска
            top_n:          максимальное количество результатов
            modality:       фильтр по модальности
            tags:           фильтр по тегам
            min_importance: минимальная важность
            last_n_hours:   искать только за последние N часов

        Returns:
            Список эпизодов, отсортированных по релевантности
        """
        query_lower = query.lower()
        # Стеммированные токены запроса (без стоп-слов) для overlap-скоринга
        query_tokens: frozenset[str] = _tokenize(query_lower)
        cutoff_ts = time.time() - last_n_hours * 3600 if last_n_hours else 0.0

        results: List[Tuple[float, Episode]] = []

        with self._lock:
            for ep in self._episodes:
                # Временной фильтр
                if cutoff_ts and ep.ts < cutoff_ts:
                    continue
                # Фильтр по важности
                if ep.importance < min_importance:
                    continue
                # Фильтр по модальности
                if modality and ep.modality != modality:
                    continue
                # Фильтр по тегам (аргумент tags — фильтр, не скоринг)
                if tags and not any(t in ep.tags for t in tags):
                    continue

                # ── Скоринг контента ─────────────────────────────────────
                score = 0.0
                content_lower = ep.content.lower()

                if query_lower in content_lower:
                    # Уровень 1: полное совпадение строки запроса (точный match)
                    score += 0.6
                elif query_tokens:
                    # Уровень 2: стеммированный overlap (для длинных запросов)
                    # "мозге" → "мозг", "нейронов" → "нейрон" и т.д.
                    content_tokens: frozenset[str] = _tokenize(content_lower)
                    overlap = query_tokens & content_tokens
                    if overlap:
                        score += 0.6 * (len(overlap) / len(query_tokens))

                # ── Скоринг концептов ────────────────────────────────────
                if any(query_lower in c for c in ep.concepts) or (
                    query_tokens and any(
                        query_tokens & _tokenize(c.lower())
                        for c in ep.concepts
                    )
                ):
                    score += 0.3

                # ── Скоринг тегов ────────────────────────────────────────
                if any(query_lower in t for t in ep.tags) or (
                    query_tokens and any(
                        query_tokens & _tokenize(t.lower())
                        for t in ep.tags
                    )
                ):
                    score += 0.1

                if score > 0:
                    results.append((score * ep.importance * ep.confidence, ep))

            results.sort(key=lambda x: x[0], reverse=True)
            found = [ep for _, ep in results[:top_n]]
            for ep in found:
                ep.touch()
            self._load_count += len(found)
            return found

    def get_by_trace(self, trace_id: str) -> List[Episode]:
        """Найти все эпизоды с данным trace_id."""
        with self._lock:
            return [ep for ep in self._episodes if ep.trace_id == trace_id]

    def get_by_session(self, session_id: str) -> List[Episode]:
        """Найти все эпизоды сессии."""
        with self._lock:
            return [ep for ep in self._episodes if ep.session_id == session_id]

    # ─── Управление памятью ──────────────────────────────────────────────────

    def _evict_oldest(self):
        """
        Вытеснить старейший и наименее важный эпизод.
        Защищённые (importance >= threshold) не вытесняются.
        """
        candidates = [
            (i, ep) for i, ep in enumerate(self._episodes)
            if ep.importance < self._importance_threshold
        ]
        if not candidates:
            # Все защищены — вытесняем самый старый из защищённых
            if self._episodes:
                oldest = self._episodes[0]
                self._remove_episode(oldest)
            return

        # Вытесняем с наименьшим score = importance * confidence
        candidates.sort(key=lambda x: x[1].importance * x[1].confidence)
        _, to_evict = candidates[0]
        self._remove_episode(to_evict)

    def _remove_episode(self, episode: Episode):
        """Удалить эпизод из всех индексов."""
        try:
            self._episodes.remove(episode)
        except ValueError:
            pass
        self._index_by_id.pop(episode.episode_id, None)
        for concept in episode.concepts:
            key = concept.lower().strip()
            if key in self._index_by_concept:
                try:
                    self._index_by_concept[key].remove(episode.episode_id)
                except ValueError:
                    pass

    def _adaptive_max(self) -> int:
        """Адаптировать лимит под доступную RAM."""
        if not _PSUTIL_AVAILABLE:
            return self._max_episodes
        try:
            ram = psutil.virtual_memory()
            if ram.percent > 85:
                return max(500, self._max_episodes // 4)
            if ram.percent > 75:
                return max(1000, self._max_episodes // 2)
        except Exception:
            pass
        return self._max_episodes

    # ─── Персистентность ─────────────────────────────────────────────────────

    def save(self, path: Optional[str] = None):
        """Сохранить эпизодическую память (SQLite или JSON)."""
        with self._lock:
            if self._backend == "sqlite" and self._db is not None:
                self._save_sqlite()
            else:
                self._save_json(path)

    def _save_json(self, path: Optional[str] = None):
        """Сохранить эпизодическую память на диск (JSON)."""
        path = path or self._data_path
        os.makedirs(os.path.dirname(path), exist_ok=True)

        data = {
            "version": "1.0",
            "saved_ts": time.time(),
            "episode_count": len(self._episodes),
            "episodes": [ep.to_dict() for ep in self._episodes],
        }

        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if os.path.exists(path):
            os.replace(tmp_path, path)
        else:
            os.rename(tmp_path, path)

        _logger.info("Эпизодическая память сохранена (JSON): %d эпизодов -> %s", len(self._episodes), path)

    def _save_sqlite(self):
        """Сохранить эпизодическую память в SQLite."""
        if self._db is None:
            return
        episodes_data = [ep.to_dict() for ep in self._episodes]
        self._db.save_all_episodes(episodes_data)
        _logger.info("Эпизодическая память сохранена (SQLite): %d эпизодов", len(self._episodes))

    def _load(self):
        """Загрузить эпизодическую память."""
        if self._backend == "sqlite" and self._db is not None:
            self._load_sqlite()
        else:
            self._load_json()

    def _load_json(self):
        """Загрузить эпизодическую память с диска (JSON)."""
        if not os.path.exists(self._data_path):
            return

        try:
            with open(self._data_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for ep_dict in data.get("episodes", []):
                ep = Episode.from_dict(ep_dict)
                self._episodes.append(ep)
                self._index_by_id[ep.episode_id] = ep
                for concept in ep.concepts:
                    key = concept.lower().strip()
                    if key not in self._index_by_concept:
                        self._index_by_concept[key] = []
                    self._index_by_concept[key].append(ep.episode_id)

            _logger.info(
                "Эпизодическая память загружена (JSON): %d эпизодов <- %s",
                len(self._episodes), self._data_path,
            )
        except Exception as e:
            _logger.warning("Ошибка загрузки эпизодической памяти: %s", e)

    def _load_sqlite(self):
        """Загрузить эпизодическую память из SQLite."""
        if self._db is None:
            return
        try:
            rows = self._db.load_all_episodes()
            for ep_dict in rows:
                ep = Episode.from_dict(ep_dict)
                self._episodes.append(ep)
                self._index_by_id[ep.episode_id] = ep
                for concept in ep.concepts:
                    key = concept.lower().strip()
                    if key not in self._index_by_concept:
                        self._index_by_concept[key] = []
                    self._index_by_concept[key].append(ep.episode_id)
            _logger.info("Эпизодическая память загружена (SQLite): %d эпизодов", len(self._episodes))
        except Exception as e:
            _logger.warning("Ошибка загрузки эпизодической памяти из SQLite: %s", e)

    def _maybe_autosave(self):
        """Автосохранение каждые N операций. autosave_every=0 отключает."""
        if self._autosave_every > 0 and self._write_count % self._autosave_every == 0:
            self.save()

    # ─── Статистика ──────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Статус эпизодической памяти."""
        with self._lock:
            modality_counts: Dict[str, int] = {}
            for ep in self._episodes:
                modality_counts[ep.modality] = modality_counts.get(ep.modality, 0) + 1

            protected = sum(1 for ep in self._episodes if ep.importance >= self._importance_threshold)
            avg_importance = (
                sum(ep.importance for ep in self._episodes) / len(self._episodes)
                if self._episodes else 0.0
            )

            return {
                "type": "episodic_memory",
                "episode_count": len(self._episodes),
                "max_episodes": self._max_episodes,
                "effective_max": self._adaptive_max(),
                "protected_count": protected,
                "modality_breakdown": modality_counts,
                "avg_importance": round(avg_importance, 3),
                "write_count": self._write_count,
                "load_count": self._load_count,
                "data_path": self._data_path,
            }

    def display_status(self):
        """Вывести статус в консоль."""
        s = self.status()
        print(f"\n{'─'*50}")
        print("🧠 Эпизодическая память")
        print(f"  Эпизодов: {s['episode_count']} / {s['max_episodes']}")
        print(f"  Защищённых: {s['protected_count']}")
        print(f"  Средняя важность: {s['avg_importance']:.2%}")
        print(f"  По модальностям: {s['modality_breakdown']}")
        print(f"  Записей: {s['write_count']} | Чтений: {s['load_count']}")
        print(f"{'─'*50}\n")

    def __len__(self) -> int:
        with self._lock:
            return len(self._episodes)

    def __repr__(self) -> str:
        with self._lock:
            return f"EpisodicMemory(episodes={len(self._episodes)}/{self._max_episodes})"
