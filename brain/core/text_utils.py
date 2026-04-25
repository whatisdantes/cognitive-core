"""
brain/core/text_utils.py — Канонические текстовые утилиты.

Phase C: Critical DRY — единственный источник истины для:
  - detect_language(text)      — определение языка по соотношению кириллицы/латиницы
  - parse_fact_pattern(text)   — структурный парсинг факта из текста ("X это Y")

Эти функции ранее дублировались в:
  - brain/perception/metadata_extractor.py
  - brain/encoders/text_encoder.py
  - brain/output/dialogue_responder.py
  - brain/output/response_validator.py
  - brain/memory/consolidation_engine.py
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional, Tuple

# ─── Константы ───────────────────────────────────────────────────────────────

_CYRILLIC_RE = re.compile(r"[а-яёА-ЯЁ]")
_LATIN_RE = re.compile(r"[a-zA-Z]")
_SPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w\s+\-.%]", re.UNICODE)
_NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?(?:\s*[±+/-]\s*\d+(?:[.,]\d+)?)?")
_PAGE_RE = re.compile(r"\bpage\s+\d+\b", re.IGNORECASE)
_SECTION_RE = re.compile(r"\b(?:chapter|part)\s+\d+\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://", re.IGNORECASE)

_QUERY_STOP_WORDS = frozenset({
    "что", "кто", "как", "какой", "какая", "какие", "каких", "каком",
    "какую", "про", "для", "это", "этот", "эта", "эти", "там", "тут",
    "меня", "тебя", "тебе", "вами", "вас", "вам", "мне", "мой", "мои",
    "моя", "моё", "твой", "твоя", "твои", "ты", "вы", "мы", "они",
    "или", "если", "когда", "где", "почему", "зачем", "ли", "же",
    "the", "this", "that", "these", "those", "about", "with", "from",
    "what", "which", "who", "why", "how", "tell", "show", "remember",
    "know",
    "помнишь", "помним", "помнит", "знаешь", "знаете", "знать",
    "скажи", "расскажи", "объясни", "напомни",
})


# ─── detect_language ─────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """
    Определить язык текста по соотношению кириллических и латинских символов.

    Пороги:
      > 60% кириллицы → 'ru'
      > 60% латиницы  → 'en'
      > 10 букв, но ни одна группа не доминирует → 'mixed'
      нет букв или текст пустой → 'unknown'

    Args:
        text: входной текст

    Returns:
        'ru' | 'en' | 'mixed' | 'unknown'
    """
    if not text or not text.strip():
        return "unknown"

    cyrillic = len(_CYRILLIC_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    total_letters = cyrillic + latin

    if total_letters == 0:
        return "unknown"

    cyr_ratio = cyrillic / total_letters
    lat_ratio = latin / total_letters

    if cyr_ratio > 0.6:
        return "ru"
    if lat_ratio > 0.6:
        return "en"
    if total_letters > 10:
        return "mixed"
    return "unknown"


def normalize_concept(concept: str) -> str:
    """Нормализовать concept единообразно для memory/retrieval/conflicts."""
    return _SPACE_RE.sub(" ", concept.strip().lower())


def normalize_claim_text(text: str) -> str:
    """Стабильная лёгкая нормализация claim text для grouping/idempotence."""
    cleaned = _NON_WORD_RE.sub(" ", text.strip().lower())
    return _SPACE_RE.sub(" ", cleaned).strip()


def search_terms(text: str, *, drop_stopwords: bool = False) -> set[str]:
    """
    Выделить стабильные поисковые термы из текста.

    При `drop_stopwords=True` удаляет разговорные и вопросные слова.
    Если после фильтрации всё исчезло, возвращает исходные термы.
    """
    normalized = normalize_claim_text(text or "")
    terms = {term for term in normalized.split() if len(term) > 2}
    if not drop_stopwords:
        return terms
    filtered = {term for term in terms if term not in _QUERY_STOP_WORDS}
    return filtered or terms


def estimate_text_signal(text: str) -> float:
    """
    Оценить, насколько текст похож на полезный факт, а не на шумный хвост.

    Значение около 1.0 — обычное содержательное утверждение.
    Значение ближе к 0.05 — короткий шум, TOC, URL, user-agent, вопрос и т.п.
    """
    raw = (text or "").strip()
    if not raw:
        return 0.0

    normalized = normalize_claim_text(raw)
    score = 1.0

    if len(normalized) < 8:
        score *= 0.15
    elif len(normalized) < 16:
        score *= 0.35
    elif len(normalized) < 24:
        score *= 0.6

    if raw.endswith("?"):
        score *= 0.55

    if len(search_terms(raw)) <= 1:
        score *= 0.45

    lowered = raw.lower()
    if "starts on page" in lowered or _PAGE_RE.search(raw):
        score *= 0.2
    if _SECTION_RE.search(raw):
        score *= 0.35
    if "user-agent" in lowered or "mozilla/" in lowered:
        score *= 0.25
    if _URL_RE.search(raw):
        score *= 0.3
    if raw.count("/") >= 3:
        score *= 0.55

    if ":" in raw:
        _, _, tail = raw.partition(":")
        if len(normalize_claim_text(tail)) >= 20:
            score *= 1.05

    return max(0.05, min(score, 1.1))


def normalize_numeric_stance(raw_number: str) -> str:
    """Нормализовать числовую stance: `7±2` и `7` относятся к одному центру."""
    first = re.match(r"[-+]?\d+(?:[.,]\d+)?", raw_number.strip())
    if first is None:
        return _SPACE_RE.sub("", raw_number.replace(",", "."))
    value = first.group(0).replace(",", ".")
    if value.endswith(".0"):
        value = value[:-2]
    return value


def build_claim_grouping_keys(concept: str, claim_text: str) -> Tuple[str, str]:
    """
    Построить deterministic `claim_family_key` и `stance_key`.

    MVP-эвристика: family привязан к concept и грубо нормализованному
    предикату без чисел; stance — к первой числовой/negation стороне или
    hash нормализованного утверждения.
    """
    concept_key = normalize_concept(concept)
    normalized = normalize_claim_text(claim_text)
    number_match = _NUMBER_RE.search(normalized)
    if number_match:
        family_key = f"{concept_key}:numeric"
        stance = normalize_numeric_stance(number_match.group(0))
        return family_key, f"num:{stance}"

    without_numbers = _NUMBER_RE.sub("<num>", normalized)
    family_seed = without_numbers[:120] or concept_key
    family_hash = hashlib.sha1(
        family_seed.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:12]
    family_key = f"{concept_key}:{family_hash}"

    neg_markers = ("не ", "нет ", "not ", "never ", "без ")
    if any(marker in f" {normalized} " for marker in neg_markers):
        stance_seed = "negated"
    else:
        stance_seed = normalized[:160] or concept_key
    stance_hash = hashlib.sha1(
        stance_seed.encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:12]
    return family_key, f"text:{stance_hash}"


# ─── parse_fact_pattern ──────────────────────────────────────────────────────

def parse_fact_pattern(text: str) -> Optional[Tuple[str, str]]:
    """
    Извлечь структурированный факт из текста.

    Ищет паттерны:
      - "X это Y"
      - "X — Y"
      - "X - Y"
      - "X: Y"
      - "X is Y"
      - "X are Y"
      - "X means Y"

    Ограничения:
      - concept: 2–50 символов
      - description: >= 5 символов
      - text: 5–500 символов

    Функция отвечает только за структурный парсинг, без побочных эффектов
    и без нормализации сверх необходимого минимума.

    Args:
        text: входной текст

    Returns:
        (concept, description) или None если паттерн не найден
    """
    text = text.strip()
    if len(text) < 5 or len(text) > 500:
        return None

    # Паттерны на русском (порядок важен: " это " до " — ")
    for sep in [" это ", " — ", " - ", ": "]:
        if sep in text:
            parts = text.split(sep, 1)
            if len(parts) == 2:
                # Убираем хвостовые тире/дефисы (напр. "нейрон —" → "нейрон")
                concept = parts[0].strip().rstrip(" —–-").strip()
                description = parts[1].strip()
                if 2 <= len(concept) <= 50 and len(description) >= 5:
                    return concept, description

    # Паттерны на английском
    for sep in [" is ", " are ", " means "]:
        if sep in text.lower():
            idx = text.lower().find(sep)
            concept = text[:idx].strip()
            description = text[idx + len(sep):].strip()
            if 2 <= len(concept) <= 50 and len(description) >= 5:
                return concept, description

    return None
