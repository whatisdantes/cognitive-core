"""
brain/cognition/retrieval_adapter.py

Адаптер между системой памяти и когнитивным ядром.

Содержит:
  - RetrievalBackend (Protocol) — интерфейс для подключаемых backend'ов
  - KeywordRetrievalBackend     — keyword-based backend через MemoryManager
  - RetrievalAdapter            — facade: делегирует backend, нормализует результат

Контракт F+.1:
  После RetrievalAdapter каждый EvidencePack гарантированно имеет
  все 11 канонических полей (evidence_id, content, memory_type,
  confidence, trust, relevance_score, freshness_score, concept_refs,
  source_refs, contradiction_flags, metadata). Отсутствующие поля
  получают default-значения.

Архитектура:
  - keyword backend now
  - vector-compatible interface later (через RetrievalBackend Protocol)
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import math
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from brain.core.contracts import ClaimRef, ClaimStatus
from brain.core.text_utils import estimate_text_signal, search_terms

from .context import EvidencePack

logger = logging.getLogger(__name__)
_MIN_RELATION_WEIGHT = 0.05

# Optional: pymorphy3 для лемматизации (graceful fallback)
try:
    import pymorphy3  # noqa: E402

    _morph = pymorphy3.MorphAnalyzer()
    _HAS_MORPH = True
except Exception:  # ImportError, ModuleNotFoundError, etc.
    _morph = None
    _HAS_MORPH = False


# ---------------------------------------------------------------------------
# BM25Scorer — BM25 reranking scorer (pure Python)
# ---------------------------------------------------------------------------

class BM25Scorer:
    """
    BM25 (Okapi BM25) scorer для reranking кандидатов.

    Использование:
        scorer = BM25Scorer(k1=1.5, b=0.75)
        scorer.fit(["документ один", "документ два", ...])
        score = scorer.score("запрос", "документ один")
        scores = scorer.score_batch("запрос", ["документ один", "документ два"])

    Если fit() не вызван — fallback на нормализованный keyword overlap.
    Лемматизация через pymorphy3 (optional, graceful fallback на lower+split).

    Параметры BM25:
        k1:  контроль насыщения TF (default 1.5, range [1.2, 2.0])
        b:   контроль нормализации длины документа (default 0.75, range [0, 1])
    """

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        use_lemmatization: bool = True,
    ) -> None:
        self._k1 = k1
        self._b = b
        self._use_lemma = use_lemmatization and _HAS_MORPH

        # IDF state (populated by fit())
        self._idf: Dict[str, float] = {}
        self._avgdl: float = 0.0
        self._n_docs: int = 0
        self._fitted: bool = False

    @property
    def fitted(self) -> bool:
        """True если fit() был вызван с непустым корпусом."""
        return self._fitted

    @property
    def vocab_size(self) -> int:
        """Размер словаря IDF."""
        return len(self._idf)

    def fit(self, documents: List[str]) -> "BM25Scorer":
        """
        Построить IDF индекс на корпусе документов.

        Args:
            documents: список текстов документов

        Returns:
            self (для chaining)
        """
        if not documents:
            self._fitted = False
            return self

        self._n_docs = len(documents)

        # Токенизировать все документы
        tokenized = [self._tokenize(doc) for doc in documents]

        # Средняя длина документа
        total_len = sum(len(tokens) for tokens in tokenized)
        self._avgdl = total_len / self._n_docs if self._n_docs > 0 else 1.0

        # Document frequency: сколько документов содержат каждый терм
        df: Dict[str, int] = {}
        for tokens in tokenized:
            unique_terms = set(tokens)
            for term in unique_terms:
                df[term] = df.get(term, 0) + 1

        # IDF: log((N - df + 0.5) / (df + 0.5) + 1)
        # Robertson/Sparck-Jones IDF с +1 для сглаживания
        self._idf = {}
        for term, freq in df.items():
            numerator = self._n_docs - freq + 0.5
            denominator = freq + 0.5
            self._idf[term] = math.log(numerator / denominator + 1.0)

        self._fitted = True
        return self

    def score(self, query: str, document: str) -> float:
        """
        Вычислить BM25 score для одного документа.

        Если fit() не вызван — fallback на keyword overlap.

        Args:
            query:    текстовый запрос
            document: текст документа

        Returns:
            BM25 score (float >= 0.0)
        """
        if not query or not document:
            return 0.0

        if not self._fitted:
            return self._keyword_overlap_fallback(query, document)

        query_terms = self._tokenize(query)
        doc_terms = self._tokenize(document)

        if not query_terms or not doc_terms:
            return 0.0

        # Term frequency в документе
        tf: Dict[str, int] = {}
        for term in doc_terms:
            tf[term] = tf.get(term, 0) + 1

        doc_len = len(doc_terms)
        total_score = 0.0

        for term in query_terms:
            if term not in tf:
                continue

            term_freq = tf[term]
            idf = self._idf.get(term, 0.0)

            # BM25 TF component:
            # (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))
            numerator = term_freq * (self._k1 + 1.0)
            denominator = term_freq + self._k1 * (
                1.0 - self._b + self._b * doc_len / self._avgdl
            )
            total_score += idf * (numerator / denominator)

        return total_score

    def score_batch(
        self,
        query: str,
        documents: List[str],
    ) -> List[float]:
        """
        Вычислить BM25 scores для списка документов.

        Args:
            query:     текстовый запрос
            documents: список текстов документов

        Returns:
            Список BM25 scores (same order as documents)
        """
        return [self.score(query, doc) for doc in documents]

    def _tokenize(self, text: str) -> List[str]:
        """
        Токенизация текста.

        Если pymorphy3 доступен и use_lemmatization=True:
            слово → нормальная форма (лемма)
        Иначе:
            lower() + re.findall(r'\\w+')
        """
        if not text:
            return []

        words = re.findall(r'\w+', text.lower())

        if self._use_lemma and _morph is not None:
            lemmas = []
            for word in words:
                try:
                    parsed = _morph.parse(word)
                    if parsed:
                        lemmas.append(parsed[0].normal_form)
                    else:
                        lemmas.append(word)
                except Exception:
                    lemmas.append(word)
            return lemmas

        return words

    @staticmethod
    def _keyword_overlap_fallback(query: str, document: str) -> float:
        """
        Fallback: нормализованный keyword overlap.

        Используется если fit() не был вызван.
        Формула: |query_words ∩ doc_words| / |query_words|
        """
        if not query or not document:
            return 0.0
        query_words = set(re.findall(r'\w+', query.lower()))
        doc_words = set(re.findall(r'\w+', document.lower()))
        if not query_words:
            return 0.0
        return len(query_words & doc_words) / len(query_words)


# ---------------------------------------------------------------------------
# RetrievalBackend — Protocol для подключаемых backend'ов
# ---------------------------------------------------------------------------

@runtime_checkable
class RetrievalBackend(Protocol):
    """
    Интерфейс для подключаемых retrieval backend'ов.

    Текущая реализация: KeywordRetrievalBackend (keyword search).
    Будущие: VectorRetrievalBackend (semantic vector search).
    """

    def search(self, query: str, top_n: int = 10) -> List[EvidencePack]:
        """
        Поиск по запросу, возвращает нормализованные EvidencePack.

        Args:
            query:  текстовый запрос
            top_n:  максимальное количество результатов

        Returns:
            Список EvidencePack, отсортированных по relevance_score (desc)
        """
        ...


# ---------------------------------------------------------------------------
# KeywordRetrievalBackend — keyword-based через MemoryManager
# ---------------------------------------------------------------------------

class KeywordRetrievalBackend:
    """
    Keyword-based retrieval backend через MemoryManager.retrieve().

    Конвертирует MemorySearchResult (working/semantic/episodic)
    в унифицированный List[EvidencePack].

    Каждый EvidencePack гарантированно имеет все канонические поля.
    """

    def __init__(self, memory_manager: Any):
        """
        Args:
            memory_manager: экземпляр MemoryManager с методом retrieve()
        """
        self._memory = memory_manager

    def search(self, query: str, top_n: int = 10) -> List[EvidencePack]:
        """
        Поиск через MemoryManager.retrieve() → List[EvidencePack].

        Конвертирует результаты из трёх видов памяти:
          - working  → MemoryItem  → EvidencePack
          - semantic → SemanticNode → EvidencePack
          - episodic → Episode     → EvidencePack

        Результат отсортирован по relevance_score (desc).
        """
        if not hasattr(self._memory, "retrieve"):
            logger.warning(
                "[KeywordRetrievalBackend] MemoryManager has no retrieve() method"
            )
            return []

        try:
            result = self._memory.retrieve(query, top_n=top_n)
        except Exception as e:
            logger.error(
                "[KeywordRetrievalBackend] retrieve() failed: %s", e
            )
            return []

        evidence: List[EvidencePack] = []

        # --- Working memory ---
        for item in getattr(result, "working", []):
            ev = self._from_working(item, query)
            evidence.append(ev)

        # --- Claim memory ---
        for claim in getattr(result, "answerable_claims", []):
            ev = self._from_claim(claim, query)
            evidence.append(ev)

        # --- Semantic memory ---
        for node in getattr(result, "semantic", []):
            if not self._should_surface_semantic(node):
                continue
            ev = self._from_semantic(node, query)
            evidence.append(ev)

        # --- Episodic memory ---
        for ep in getattr(result, "episodic", []):
            ev = self._from_episodic(ep, query)
            evidence.append(ev)

        # --- BM25 reranking ---
        # Собрать тексты кандидатов, fit BM25, пересчитать relevance_score
        if len(evidence) >= 2:
            evidence = self._bm25_rerank(query, evidence)

        # Сортировка по relevance_score (desc), stable
        evidence.sort(key=lambda e: (-e.relevance_score, e.evidence_id))

        return evidence[:top_n]

    @staticmethod
    def _bm25_rerank(
        query: str,
        evidence: List[EvidencePack],
    ) -> List[EvidencePack]:
        """
        BM25 reranking кандидатов.

        Строит BM25 индекс на текстах кандидатов, пересчитывает
        relevance_score. Если BM25 score > 0 хотя бы для одного
        кандидата, нормализует scores в [0, 1] и заменяет
        relevance_score. Иначе оставляет оригинальные scores.
        """
        texts = [ev.content for ev in evidence]
        query_terms = sorted(search_terms(query, drop_stopwords=True))
        bm25_query = " ".join(query_terms) if query_terms else query
        scorer = BM25Scorer(use_lemmatization=True)
        scorer.fit(texts)

        if not scorer.fitted:
            return evidence

        raw_scores = scorer.score_batch(bm25_query, texts)
        adjusted_scores = [
            raw_score * KeywordRetrievalBackend._evidence_signal_factor(ev)
            for ev, raw_score in zip(evidence, raw_scores)
        ]
        max_score = max(adjusted_scores) if adjusted_scores else 0.0

        # Если BM25 не дал ненулевых scores — оставить оригинальные
        if max_score <= 0.0:
            return evidence

        # Нормализация в [0, 1]
        reranked: List[EvidencePack] = []
        for ev, bm25_score, adjusted_score in zip(evidence, raw_scores, adjusted_scores):
            normalized = adjusted_score / max_score if max_score > 0 else 0.0
            reranked.append(
                dataclasses.replace(
                    ev,
                    relevance_score=round(normalized, 6),
                    metadata={
                        **ev.metadata,
                        "bm25_raw_score": round(bm25_score, 6),
                        "content_signal": round(
                            KeywordRetrievalBackend._evidence_signal_factor(ev),
                            6,
                        ),
                        "reranking": "bm25",
                    },
                )
            )
        return reranked

    # ------------------------------------------------------------------
    # Конвертеры: memory type → EvidencePack
    # ------------------------------------------------------------------

    def _from_working(self, item: Any, query: str) -> EvidencePack:
        """Конвертировать MemoryItem → EvidencePack."""
        content = str(getattr(item, "content", ""))
        source_ref = getattr(item, "source_ref", "")
        tags = getattr(item, "tags", [])
        importance = getattr(item, "importance", 0.5)
        ts = getattr(item, "ts", None)

        relevance = self._compute_relevance(query, content)

        return EvidencePack(
            evidence_id=self._make_evidence_id("wm", content),
            content=content,
            memory_type="working",
            concept_refs=list(tags) if tags else [],
            source_refs=[source_ref] if source_ref else [],
            confidence=importance,
            trust=0.5,
            timestamp=self._format_ts(ts),
            modality=getattr(item, "modality", "text"),
            contradiction_flags=[],
            relevance_score=relevance,
            freshness_score=1.0,  # working memory is always fresh
            retrieval_stage=1,
            supports_hypotheses=[],
        )

    def _from_semantic(self, node: Any, query: str) -> EvidencePack:
        """Конвертировать SemanticNode → EvidencePack."""
        concept = getattr(node, "concept", "")
        description = getattr(node, "description", "")
        content = f"{concept}: {description}" if description else concept
        confidence = getattr(node, "confidence", 1.0)
        importance = getattr(node, "importance", 0.5)
        source_refs = getattr(node, "source_refs", [])
        updated_ts = getattr(node, "updated_ts", None)

        # concept_refs: сам concept + targets только достаточно сильных relations
        concept_refs = [concept]
        relations = sorted(
            getattr(node, "relations", []) or [],
            key=lambda rel: (
                -float(getattr(rel, "weight", 0.0) or 0.0)
                * float(getattr(rel, "confidence", 0.0) or 0.0),
                str(getattr(rel, "target", "")),
            ),
        )
        for rel in relations:
            weight = float(getattr(rel, "weight", 0.0) or 0.0)
            if weight < _MIN_RELATION_WEIGHT:
                continue
            target = getattr(rel, "target", "")
            if target and target not in concept_refs:
                concept_refs.append(target)
            if len(concept_refs) >= 4:
                break

        relevance = self._compute_relevance(query, content)
        freshness = self._compute_freshness(updated_ts)

        return EvidencePack(
            evidence_id=self._make_evidence_id("sem", concept),
            content=content,
            memory_type="semantic",
            concept_refs=concept_refs,
            source_refs=list(source_refs) if source_refs else [],
            confidence=confidence,
            trust=min(1.0, confidence * 0.8 + importance * 0.2),
            timestamp=self._format_ts(updated_ts),
            modality="text",
            contradiction_flags=[],
            relevance_score=relevance,
            freshness_score=freshness,
            retrieval_stage=1,
            supports_hypotheses=[],
        )

    def _from_episodic(self, ep: Any, query: str) -> EvidencePack:
        """Конвертировать Episode → EvidencePack."""
        content = getattr(ep, "content", "")
        concepts = getattr(ep, "concepts", [])
        tags = getattr(ep, "tags", [])
        importance = getattr(ep, "importance", 0.5)
        confidence = getattr(ep, "confidence", 1.0)
        source = getattr(ep, "source", "")
        ts = getattr(ep, "ts", None)
        modality = getattr(ep, "modality", "text")
        episode_id = getattr(ep, "episode_id", "")

        relevance = self._compute_relevance(query, content)
        freshness = self._compute_freshness(ts)

        return EvidencePack(
            evidence_id=self._make_evidence_id("ep", episode_id or content[:50]),
            content=content,
            memory_type="episodic",
            concept_refs=list(concepts) if concepts else list(tags),
            source_refs=[source] if source else [],
            confidence=confidence,
            trust=min(1.0, importance * 0.7 + confidence * 0.3),
            timestamp=self._format_ts(ts),
            modality=modality,
            contradiction_flags=[],
            relevance_score=relevance,
            freshness_score=freshness,
            retrieval_stage=1,
            supports_hypotheses=[],
        )

    def _from_claim(self, claim: Any, query: str) -> EvidencePack:
        """Конвертировать Claim → EvidencePack с provenance для output."""
        concept = getattr(claim, "concept", "")
        claim_text = getattr(claim, "claim_text", "")
        claim_id = getattr(claim, "claim_id", "")
        source_ref = getattr(claim, "source_ref", "")
        source_group_id = getattr(claim, "source_group_id", "")
        confidence = float(getattr(claim, "confidence", 0.5) or 0.5)
        status = getattr(claim, "status", ClaimStatus.ACTIVE)
        status_value = getattr(status, "value", str(status))
        conflict_refs = list(getattr(claim, "conflict_refs", []) or [])
        trust = self._get_source_trust(source_group_id)
        content = f"{concept}: {claim_text}" if concept else claim_text
        query_terms = search_terms(query, drop_stopwords=True)
        concept_terms = search_terms(concept)
        matched_terms = sorted(query_terms & search_terms(content))

        flags: List[str] = []
        if status_value in {
            ClaimStatus.DISPUTED.value,
            ClaimStatus.POSSIBLY_CONFLICTING.value,
        }:
            flags.append(f"claim_status:{status_value}")
        flags.extend(f"conflict_ref:{ref}" for ref in conflict_refs)

        claim_ref = ClaimRef.from_claim(claim, trust=trust)
        relevance = self._compute_relevance(query, content)
        concept_refs = [concept] if concept else []
        for term in matched_terms[:3]:
            if term and term not in concept_refs:
                concept_refs.append(term)

        return EvidencePack(
            evidence_id=self._make_evidence_id("claim", claim_id or content),
            content=content,
            memory_type="claim",
            concept_refs=concept_refs,
            source_refs=[source_ref] if source_ref else [],
            confidence=confidence,
            trust=trust,
            timestamp=self._format_ts(getattr(claim, "updated_ts", None)),
            modality="text",
            contradiction_flags=flags,
            relevance_score=relevance,
            freshness_score=self._compute_freshness(getattr(claim, "updated_ts", None)),
            retrieval_stage=1,
            supports_hypotheses=[],
            metadata={
                "claim_id": claim_id,
                "claim_text": claim_text,
                "claim_status": status_value,
                "source_ref": source_ref,
                "source_group_id": source_group_id,
                "query_overlap_terms": matched_terms,
                "query_concept_match": bool(query_terms & concept_terms),
                "conflict_refs": conflict_refs,
                "claim_family_key": getattr(claim, "claim_family_key", ""),
                "stance_key": getattr(claim, "stance_key", ""),
                "claim_metadata": dict(getattr(claim, "metadata", {}) or {}),
                "claim_ref": claim_ref.to_dict(),
            },
        )

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------

    @staticmethod
    def _should_surface_semantic(node: Any) -> bool:
        """Не показывать пустые semantic-узлы без описания и сильных связей."""
        concept = str(getattr(node, "concept", "") or "").strip()
        description = str(getattr(node, "description", "") or "").strip()
        if not concept:
            return False
        content = f"{concept}: {description}" if description else concept
        if estimate_text_signal(content) >= 0.12:
            return True

        source_refs = list(getattr(node, "source_refs", []) or [])
        if source_refs:
            return True

        for rel in list(getattr(node, "relations", []) or []):
            weight = float(getattr(rel, "weight", 0.0) or 0.0)
            if weight >= _MIN_RELATION_WEIGHT:
                return True
        return False

    @staticmethod
    def _evidence_signal_factor(ev: EvidencePack) -> float:
        """Понизить BM25-score для служебных хвостов, TOC и пустых concept-узлов."""
        factor = estimate_text_signal(ev.content)
        if ev.memory_type == "semantic" and ":" not in ev.content:
            factor *= 0.5
        return max(0.05, min(factor, 1.1))

    @staticmethod
    def _compute_relevance(query: str, content: str) -> float:
        """
        Вычислить relevance score на основе keyword overlap.

        Формула: |query_words ∩ content_words| / |query_words|
        Диапазон: [0.0, 1.0]
        """
        if not query or not content:
            return 0.0

        query_words = search_terms(query, drop_stopwords=True)
        content_words = search_terms(content)

        if not query_words:
            return 0.0

        overlap = query_words & content_words
        return len(overlap) / len(query_words)

    def _get_source_trust(self, source_group_id: str) -> float:
        if not source_group_id:
            return 0.5
        source_memory = getattr(self._memory, "source", None)
        if source_memory is None or not hasattr(source_memory, "get_trust"):
            return 0.5
        try:
            return float(source_memory.get_trust(source_group_id))
        except Exception:
            return 0.5

    @staticmethod
    def _compute_freshness(ts: Any) -> float:
        """
        Вычислить freshness score на основе timestamp.

        Формула: max(0.1, 1.0 - age_days / 30)
        Диапазон: [0.1, 1.0]
        """
        if ts is None:
            return 0.5  # unknown age → neutral

        try:
            ts_float = float(ts)
        except (TypeError, ValueError):
            return 0.5

        age_days = (time.time() - ts_float) / 86400
        if age_days < 0:
            return 1.0
        return max(0.1, 1.0 - age_days / 30.0)

    @staticmethod
    def _make_evidence_id(prefix: str, seed: str) -> str:
        """Детерминированный evidence ID."""
        digest = hashlib.sha256(f"{prefix}:{seed}".encode()).hexdigest()[:8]
        return f"ev_{prefix}_{digest}"

    @staticmethod
    def _format_ts(ts: Any) -> Optional[str]:
        """Форматировать timestamp в ISO строку."""
        if ts is None:
            return None
        try:
            return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(float(ts)))
        except (TypeError, ValueError):
            return None


# ---------------------------------------------------------------------------
# VectorRetrievalBackend — cosine-similarity vector search
# ---------------------------------------------------------------------------

class VectorRetrievalBackend:
    """
    Vector-based retrieval backend using cosine similarity.

    Stores vectors alongside content in an in-memory index.
    Searches by computing cosine similarity between query vector
    and all stored vectors.

    Usage:
        backend = VectorRetrievalBackend()
        backend.add("ev_1", content="нейрон это клетка", vector=[0.1, 0.2, ...],
                     memory_type="semantic", confidence=0.9)
        results = backend.search_by_vector(query_vector=[0.1, 0.2, ...], top_n=5)
    """

    def __init__(self) -> None:
        # evidence_id → {content, vector, memory_type, confidence, ...}
        self._index: Dict[str, Dict[str, Any]] = {}

    def add(
        self,
        evidence_id: str,
        content: str,
        vector: List[float],
        memory_type: str = "unknown",
        confidence: float = 0.5,
        concept_refs: Optional[List[str]] = None,
        source_refs: Optional[List[str]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        """Add a vector entry to the index."""
        if not vector or all(v == 0.0 for v in vector):
            return  # skip zero vectors
        self._index[evidence_id] = {
            "content": content,
            "vector": vector,
            "memory_type": memory_type,
            "confidence": confidence,
            "concept_refs": concept_refs or [],
            "source_refs": source_refs or [],
            "timestamp": timestamp,
        }

    def remove(self, evidence_id: str) -> None:
        """Remove an entry from the index."""
        self._index.pop(evidence_id, None)

    def search(self, query: str, top_n: int = 10) -> List[EvidencePack]:
        """
        Keyword fallback: search by text overlap (same as KeywordRetrievalBackend).
        For vector search, use search_by_vector().
        """
        if not self._index:
            return []

        results: List[EvidencePack] = []
        for eid, entry in self._index.items():
            relevance = self._compute_text_relevance(query, entry["content"])
            if relevance > 0.0:
                results.append(EvidencePack(
                    evidence_id=eid,
                    content=entry["content"],
                    memory_type=entry["memory_type"],
                    confidence=entry["confidence"],
                    concept_refs=list(entry["concept_refs"]),
                    source_refs=list(entry["source_refs"]),
                    timestamp=entry["timestamp"],
                    relevance_score=relevance,
                    freshness_score=0.8,
                    retrieval_stage=1,
                ))

        results.sort(key=lambda e: (-e.relevance_score, e.evidence_id))
        return results[:top_n]

    def search_by_vector(
        self,
        query_vector: List[float],
        top_n: int = 10,
        min_similarity: float = 0.0,
    ) -> List[EvidencePack]:
        """
        Search by cosine similarity between query_vector and stored vectors.

        Args:
            query_vector:    vector to compare against
            top_n:           max results
            min_similarity:  minimum cosine similarity threshold [0..1]

        Returns:
            List[EvidencePack] sorted by relevance_score (cosine sim) desc.
        """
        if not self._index or not query_vector:
            return []

        scored: List[tuple] = []  # (similarity, evidence_id, entry)

        for eid, entry in self._index.items():
            sim = self._cosine_similarity(query_vector, entry["vector"])
            if sim >= min_similarity:
                scored.append((sim, eid, entry))

        # Sort by similarity desc, stable
        scored.sort(key=lambda x: (-x[0], x[1]))

        results: List[EvidencePack] = []
        for sim, eid, entry in scored[:top_n]:
            results.append(EvidencePack(
                evidence_id=eid,
                content=entry["content"],
                memory_type=entry["memory_type"],
                confidence=entry["confidence"],
                concept_refs=list(entry["concept_refs"]),
                source_refs=list(entry["source_refs"]),
                timestamp=entry["timestamp"],
                relevance_score=round(sim, 6),
                freshness_score=0.8,
                retrieval_stage=1,
                supports_hypotheses=[],
                metadata={"vector_similarity": round(sim, 6)},
            ))

        return results

    @property
    def size(self) -> int:
        """Number of entries in the index."""
        return len(self._index)

    def clear(self) -> None:
        """Clear the entire index."""
        self._index.clear()

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a < 1e-12 or norm_b < 1e-12:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _compute_text_relevance(query: str, content: str) -> float:
        """Keyword overlap relevance (fallback for text-only search)."""
        if not query or not content:
            return 0.0
        query_words = set(re.findall(r'\w+', query.lower()))
        content_words = set(re.findall(r'\w+', content.lower()))
        if not query_words:
            return 0.0
        return len(query_words & content_words) / len(query_words)


# ---------------------------------------------------------------------------
# HybridRetrievalBackend — keyword + vector combined search
# ---------------------------------------------------------------------------

class HybridRetrievalBackend:
    """
    Hybrid retrieval backend: combines keyword search and vector search.

    Strategy:
      1. Run keyword search via KeywordRetrievalBackend → keyword_results
      2. Run vector search via VectorRetrievalBackend → vector_results
      3. Merge results using reciprocal rank fusion (RRF)
      4. Return top_n merged results

    If vector_backend has no entries or query_vector is None,
    falls back to keyword-only search.

    Usage:
        keyword_backend = KeywordRetrievalBackend(memory_manager)
        vector_backend = VectorRetrievalBackend()
        hybrid = HybridRetrievalBackend(keyword_backend, vector_backend)
        results = hybrid.search("нейрон", top_n=10)
        results = hybrid.search_hybrid("нейрон", query_vector=[...], top_n=10)
    """

    # Weight for keyword vs vector results in RRF
    KEYWORD_WEIGHT: float = 0.4
    VECTOR_WEIGHT: float = 0.6
    RRF_K: int = 60  # RRF constant

    def __init__(
        self,
        keyword_backend: KeywordRetrievalBackend,
        vector_backend: VectorRetrievalBackend,
    ) -> None:
        self._keyword = keyword_backend
        self._vector = vector_backend

    @property
    def vector_backend(self) -> VectorRetrievalBackend:
        """Access to the vector backend for adding entries."""
        return self._vector

    @property
    def keyword_backend(self) -> KeywordRetrievalBackend:
        """Access to the keyword backend."""
        return self._keyword

    def search(self, query: str, top_n: int = 10) -> List[EvidencePack]:
        """
        Keyword-only search (satisfies RetrievalBackend Protocol).
        For hybrid search with vectors, use search_hybrid().
        """
        return self._keyword.search(query, top_n=top_n)

    def search_hybrid(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        top_n: int = 10,
    ) -> List[EvidencePack]:
        """
        Hybrid search: keyword + vector with reciprocal rank fusion.

        If query_vector is None or vector_backend is empty,
        falls back to keyword-only search.
        """
        # Keyword results
        keyword_results = self._keyword.search(query, top_n=top_n * 2)

        # Vector results (if available)
        vector_results: List[EvidencePack] = []
        if (
            query_vector is not None
            and self._vector.size > 0
            and any(v != 0.0 for v in query_vector)
        ):
            vector_results = self._vector.search_by_vector(
                query_vector, top_n=top_n * 2,
            )

        # If no vector results, return keyword only
        if not vector_results:
            return keyword_results[:top_n]

        # Reciprocal Rank Fusion
        merged = self._rrf_merge(keyword_results, vector_results, top_n)
        return merged

    def _rrf_merge(
        self,
        keyword_results: List[EvidencePack],
        vector_results: List[EvidencePack],
        top_n: int,
    ) -> List[EvidencePack]:
        """
        Merge two ranked lists using Reciprocal Rank Fusion (RRF).

        RRF score = Σ weight / (k + rank)
        where k = RRF_K constant, rank = 1-based position.
        """
        scores: Dict[str, float] = {}
        evidence_map: Dict[str, EvidencePack] = {}

        # Score keyword results
        for rank, ev in enumerate(keyword_results, start=1):
            eid = ev.evidence_id
            rrf_score = self.KEYWORD_WEIGHT / (self.RRF_K + rank)
            scores[eid] = scores.get(eid, 0.0) + rrf_score
            if eid not in evidence_map:
                evidence_map[eid] = ev

        # Score vector results
        for rank, ev in enumerate(vector_results, start=1):
            eid = ev.evidence_id
            rrf_score = self.VECTOR_WEIGHT / (self.RRF_K + rank)
            scores[eid] = scores.get(eid, 0.0) + rrf_score
            if eid not in evidence_map:
                evidence_map[eid] = ev
            else:
                # Merge: keep higher relevance_score and add vector_similarity
                existing = evidence_map[eid]
                if ev.relevance_score > existing.relevance_score:
                    evidence_map[eid] = ev

        # Sort by RRF score desc
        ranked_ids = sorted(scores.keys(), key=lambda eid: -scores[eid])

        results: List[EvidencePack] = []
        for eid in ranked_ids[:top_n]:
            ev = evidence_map[eid]
            # Immutable update: replace relevance_score with RRF score
            ev = dataclasses.replace(ev, relevance_score=round(scores[eid], 6))
            results.append(ev)

        return results


# ---------------------------------------------------------------------------
# RetrievalAdapter — facade с metadata enrichment
# ---------------------------------------------------------------------------

class RetrievalAdapter:
    """
    Facade для retrieval: делегирует backend, добавляет metadata.

    Гарантирует:
      - Все 11 канонических полей EvidencePack заполнены
      - metadata содержит retrieval_backend и retrieved_at
      - Результат отсортирован по relevance_score (desc)

    Supports:
      - keyword-only search via retrieve(query)
      - hybrid search via retrieve(query, query_vector=...)
        when backend is HybridRetrievalBackend
    """

    def __init__(
        self,
        backend: RetrievalBackend,
        memory_manager: Any = None,
    ):
        """
        Args:
            backend:         реализация RetrievalBackend
            memory_manager:  опциональная ссылка на MemoryManager (для совместимости)
        """
        self._backend = backend
        self._memory = memory_manager

    @property
    def backend_name(self) -> str:
        """Имя текущего backend'а."""
        return type(self._backend).__name__

    def retrieve(
        self,
        query: str,
        top_n: int = 10,
        query_vector: Optional[List[float]] = None,
    ) -> List[EvidencePack]:
        """
        Извлечь evidence через backend с metadata enrichment.

        Args:
            query:         текстовый запрос
            top_n:         максимальное количество результатов
            query_vector:  вектор запроса для гибридного поиска (optional)

        Returns:
            Список EvidencePack с гарантированными каноническими полями
        """
        if not query or not query.strip():
            return []

        try:
            # Use hybrid search if backend supports it and vector is provided
            if (
                query_vector is not None
                and isinstance(self._backend, HybridRetrievalBackend)
            ):
                evidence = self._backend.search_hybrid(
                    query, query_vector=query_vector, top_n=top_n,
                )
            else:
                evidence = self._backend.search(query, top_n=top_n)
        except Exception as e:
            logger.error(
                "[RetrievalAdapter] backend.search() failed: %s", e
            )
            return []

        retrieved_at = time.time()
        backend_name = self.backend_name

        # Ensure canonical fields + enrich with adapter metadata (immutable)
        enriched = []
        for ev in evidence:
            ev = self._ensure_canonical(ev)
            ev = self._enrich(ev, backend_name, retrieved_at)
            enriched.append(ev)

        logger.debug(
            "[RetrievalAdapter] retrieved %d evidence for query='%s' via %s",
            len(enriched), query[:50], backend_name,
        )

        return enriched

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_canonical(ev: EvidencePack) -> EvidencePack:
        """
        Убедиться что все канонические поля имеют значения.

        Возвращает новый EvidencePack (immutable) если требуются изменения,
        иначе возвращает оригинал без копирования.
        """
        overrides: Dict[str, Any] = {}
        if not ev.evidence_id:
            overrides["evidence_id"] = f"ev_{uuid.uuid4().hex[:8]}"
        if ev.trust is None:
            overrides["trust"] = 0.5
        if ev.contradiction_flags is None:
            overrides["contradiction_flags"] = []
        if ev.concept_refs is None:
            overrides["concept_refs"] = []
        if ev.source_refs is None:
            overrides["source_refs"] = []
        if ev.supports_hypotheses is None:
            overrides["supports_hypotheses"] = []
        if overrides:
            return dataclasses.replace(ev, **overrides)
        return ev

    @staticmethod
    def _enrich(
        ev: EvidencePack,
        backend_name: str,
        retrieved_at: float,
    ) -> EvidencePack:
        """
        Добавить adapter metadata в EvidencePack.

        Возвращает новый EvidencePack (immutable) с обновлённым metadata dict.
        Оригинальный EvidencePack не мутируется.
        """
        new_metadata = {
            **ev.metadata,
            "retrieval_backend": backend_name,
            "retrieved_at": retrieved_at,
            "original_memory_type": ev.memory_type,
        }
        return dataclasses.replace(ev, metadata=new_metadata)
