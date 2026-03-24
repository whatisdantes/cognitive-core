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

import hashlib
import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .context import EvidencePack

logger = logging.getLogger(__name__)


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

        # --- Semantic memory ---
        for node in getattr(result, "semantic", []):
            ev = self._from_semantic(node, query)
            evidence.append(ev)

        # --- Episodic memory ---
        for ep in getattr(result, "episodic", []):
            ev = self._from_episodic(ep, query)
            evidence.append(ev)

        # Сортировка по relevance_score (desc), stable
        evidence.sort(key=lambda e: (-e.relevance_score, e.evidence_id))

        return evidence[:top_n]

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

        # concept_refs: сам concept + targets первых 3 relations
        concept_refs = [concept]
        relations = getattr(node, "relations", [])
        for rel in relations[:3]:
            target = getattr(rel, "target", "")
            if target and target not in concept_refs:
                concept_refs.append(target)

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

    # ------------------------------------------------------------------
    # Утилиты
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_relevance(query: str, content: str) -> float:
        """
        Вычислить relevance score на основе keyword overlap.

        Формула: |query_words ∩ content_words| / |query_words|
        Диапазон: [0.0, 1.0]
        """
        if not query or not content:
            return 0.0

        query_words = set(re.findall(r'\w+', query.lower()))
        content_words = set(re.findall(r'\w+', content.lower()))

        if not query_words:
            return 0.0

        overlap = query_words & content_words
        return len(overlap) / len(query_words)

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
# RetrievalAdapter — facade с metadata enrichment
# ---------------------------------------------------------------------------

class RetrievalAdapter:
    """
    Facade для retrieval: делегирует backend, добавляет metadata.

    Гарантирует:
      - Все 11 канонических полей EvidencePack заполнены
      - metadata содержит retrieval_backend и retrieved_at
      - Результат отсортирован по relevance_score (desc)
    """

    def __init__(self, backend: RetrievalBackend):
        """
        Args:
            backend: реализация RetrievalBackend (KeywordRetrievalBackend и т.д.)
        """
        self._backend = backend

    @property
    def backend_name(self) -> str:
        """Имя текущего backend'а."""
        return type(self._backend).__name__

    def retrieve(self, query: str, top_n: int = 10) -> List[EvidencePack]:
        """
        Извлечь evidence через backend с metadata enrichment.

        Args:
            query:  текстовый запрос
            top_n:  максимальное количество результатов

        Returns:
            Список EvidencePack с гарантированными каноническими полями
        """
        if not query or not query.strip():
            return []

        try:
            evidence = self._backend.search(query, top_n=top_n)
        except Exception as e:
            logger.error(
                "[RetrievalAdapter] backend.search() failed: %s", e
            )
            return []

        retrieved_at = time.time()
        backend_name = self.backend_name

        # Ensure canonical fields + enrich with adapter metadata
        enriched = []
        for ev in evidence:
            self._ensure_canonical(ev)
            self._enrich(ev, backend_name, retrieved_at)
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
        """Убедиться что все канонические поля имеют значения."""
        if not ev.evidence_id:
            ev.evidence_id = f"ev_{uuid.uuid4().hex[:8]}"
        if ev.trust is None:
            ev.trust = 0.5
        if ev.contradiction_flags is None:
            ev.contradiction_flags = []
        if ev.concept_refs is None:
            ev.concept_refs = []
        if ev.source_refs is None:
            ev.source_refs = []
        if ev.supports_hypotheses is None:
            ev.supports_hypotheses = []
        return ev

    @staticmethod
    def _enrich(
        ev: EvidencePack,
        backend_name: str,
        retrieved_at: float,
    ) -> EvidencePack:
        """
        Добавить adapter metadata в EvidencePack.

        Мутирует EvidencePack.metadata (оригинал создан backend'ом,
        не shared — безопасно мутировать).
        """
        ev.metadata["retrieval_backend"] = backend_name
        ev.metadata["retrieved_at"] = retrieved_at
        ev.metadata["original_memory_type"] = ev.memory_type
        return ev
