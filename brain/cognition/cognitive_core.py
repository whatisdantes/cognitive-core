"""
brain/cognition/cognitive_core.py

Orchestrator когнитивного ядра.

Единая точка входа: CognitiveCore.run(query, encoded_percept, resources)
→ CognitiveResult.

Цепочка: encode → goal → plan → reason → action → CognitiveResult.

Аналог: центральный исполнительный контур (central executive) —
координация всех когнитивных подсистем.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from brain.bridges.llm_bridge import LLMProvider
from brain.core.contracts import (
    CognitiveResult,
    EncodedPercept,
    EventBusProtocol,
    MemoryManagerProtocol,
    ResourceMonitorProtocol,
    TextEncoderProtocol,
)

from .action_selector import ActionSelector
from .context import PolicyConstraints
from .contradiction_detector import ContradictionDetector
from .goal_manager import GoalManager
from .hypothesis_engine import HypothesisEngine
from .pipeline import CognitivePipeline
from .planner import Planner
from .reasoner import Reasoner
from .retrieval_adapter import (
    HybridRetrievalBackend,
    KeywordRetrievalBackend,
    RetrievalAdapter,
    VectorRetrievalBackend,
)
from .uncertainty_monitor import UncertaintyMonitor

logger = logging.getLogger(__name__)


class CognitiveCore:
    """
    Orchestrator когнитивного ядра.

    Координирует:
      - GoalManager            — управление целями
      - Planner                — декомпозиция целей
      - HypothesisEngine       — генерация гипотез
      - Reasoner               — reasoning loop (Ring 1)
      - ActionSelector         — выбор действия
      - RetrievalAdapter       — структурированный retrieval
      - ContradictionDetector  — обнаружение противоречий
      - UncertaintyMonitor     — мониторинг тренда confidence

    Зависимости (инъекция через конструктор):
      - memory_manager:   для извлечения/сохранения фактов
      - text_encoder:     для кодирования текста (опционально)
      - event_bus:        для публикации событий (опционально)
      - resource_monitor: для проверки ресурсов (опционально)

    Использование:
        core = CognitiveCore(memory_manager=mm)
        result = core.run("что такое нейрон?")
    """

    def __init__(
        self,
        memory_manager: MemoryManagerProtocol,
        text_encoder: Optional[TextEncoderProtocol] = None,
        event_bus: Optional[EventBusProtocol] = None,
        resource_monitor: Optional[ResourceMonitorProtocol] = None,
        policy: Optional[PolicyConstraints] = None,
        llm_provider: Optional[LLMProvider] = None,
    ) -> None:
        self._memory: MemoryManagerProtocol = memory_manager
        self._encoder = text_encoder
        self._event_bus: Optional[EventBusProtocol] = event_bus
        self._resource_monitor: Optional[ResourceMonitorProtocol] = resource_monitor
        self._policy = policy or PolicyConstraints()

        # Внутренние компоненты
        self._goal_manager = GoalManager()
        self._planner = Planner()
        self._hypothesis_engine = HypothesisEngine()
        self._contradiction_detector = ContradictionDetector()
        self._uncertainty_monitor = UncertaintyMonitor()

        # RetrievalAdapter: создаём если memory_manager поддерживает retrieve()
        # Используем HybridRetrievalBackend (keyword + vector) для связки
        # TextEncoder → Memory → Retrieval
        self._retrieval_adapter: Optional[RetrievalAdapter] = None
        self._vector_backend: Optional[VectorRetrievalBackend] = None
        if hasattr(self._memory, "retrieve"):
            try:
                keyword_backend = KeywordRetrievalBackend(self._memory)
                self._vector_backend = VectorRetrievalBackend()
                hybrid_backend = HybridRetrievalBackend(
                    keyword_backend=keyword_backend,
                    vector_backend=self._vector_backend,
                )
                self._retrieval_adapter = RetrievalAdapter(
                    backend=hybrid_backend,
                    memory_manager=self._memory,
                )
            except Exception as e:
                logger.warning(
                    "[CognitiveCore] Failed to create RetrievalAdapter: %s", e
                )

        self._reasoner = Reasoner(
            memory_manager=self._memory,
            hypothesis_engine=self._hypothesis_engine,
            planner=self._planner,
            retrieval_adapter=self._retrieval_adapter,
            contradiction_detector=self._contradiction_detector,
            uncertainty_monitor=self._uncertainty_monitor,
        )
        self._action_selector = ActionSelector()

        # Счётчик циклов
        self._cycle_count: int = 0

        # LLM Bridge (Этап N, опциональный)
        self._llm_provider: Optional[LLMProvider] = llm_provider

        # --- Построение векторного индекса из персистентного корпуса памяти ---
        self._build_vector_index()

        # --- Явный пайплайн когнитивного цикла (P3-10, Этап H + N) ---
        self._pipeline = CognitivePipeline(
            memory=self._memory,
            encoder=self._encoder,
            event_bus=self._event_bus,
            resource_monitor=self._resource_monitor,
            policy=self._policy,
            goal_manager=self._goal_manager,
            reasoner=self._reasoner,
            action_selector=self._action_selector,
            vector_backend=self._vector_backend,
            cycle_count_fn=lambda: self._cycle_count,
            llm_provider=self._llm_provider,
        )

    # ------------------------------------------------------------------
    # Основной метод
    # ------------------------------------------------------------------

    def run(
        self,
        query: str,
        encoded_percept: Optional[EncodedPercept] = None,
        resources: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> CognitiveResult:
        """
        Выполнить полный когнитивный цикл.

        Делегирует выполнение CognitivePipeline (P3-10, Этап H + N).
        Цепочка из 15 явных шагов:
          create_context → auto_encode → get_resources → build_retrieval_query
          → create_goal → evaluate_salience → compute_budget
          → index_percept_vector → reason → llm_enhance (Этап N)
          → select_action (+PolicyLayer) → execute_action
          → complete_goal → build_result → publish_event

        Args:
            query:           текстовый запрос
            encoded_percept: закодированный перцепт (опционально)
            resources:       состояние ресурсов (опционально)
            session_id:      идентификатор сессии для связывания нескольких
                             вызовов в один диалог. Если None — генерируется
                             автоматически (каждый вызов = новая сессия).

        Возвращает CognitiveResult.
        """
        self._cycle_count += 1
        logger.info(
            "[CognitiveCore] run: query='%s' cycle=%d",
            query[:50], self._cycle_count,
        )
        result = self._pipeline.run(
            query=query,
            encoded_percept=encoded_percept,
            resources=resources,
            session_id=session_id,
        )
        logger.info(
            "[CognitiveCore] run complete: action=%s confidence=%.3f duration=%.1fms",
            result.action, result.confidence,
            result.metadata.get("total_duration_ms", 0),
        )
        return result

    # ------------------------------------------------------------------
    # Наполнение векторного индекса (P0-P1)
    # ------------------------------------------------------------------

    def _build_vector_index(self) -> None:
        """
        Наполнить VectorRetrievalBackend из персистентного корпуса памяти.

        Итерирует по узлам SemanticMemory и эпизодам EpisodicMemory,
        кодирует их текст (если нет кэшированного эмбеддинга) и добавляет
        в векторный бэкенд. Кэшированные эмбеддинги переиспользуются
        для избежания повторного кодирования.

        Вызывается один раз при __init__. Безопасен для повторных вызовов
        (очищает индекс перед построением для предотвращения дубликатов).
        """
        if self._vector_backend is None:
            return
        if self._encoder is None:
            logger.debug(
                "[CognitiveCore] _build_vector_index: no encoder, skipping"
            )
            return

        # Очистка для предотвращения дубликатов при повторных вызовах
        self._vector_backend.clear()

        indexed = 0

        # --- Индексация узлов SemanticMemory ---
        semantic = getattr(self._memory, "semantic", None)
        if semantic is not None:
            try:
                with semantic._lock:
                    nodes_snapshot = list(semantic._nodes.items())
            except AttributeError:
                nodes_snapshot = []

            for concept, node in nodes_snapshot:
                # Пропускаем «мёртвые» факты (confidence обнулён)
                if node.confidence <= 0.0:
                    continue
                text = f"{node.concept}: {node.description}" if node.description else node.concept
                if not text.strip():
                    continue

                vector = node.embedding
                if vector is None:
                    vector = self._encode_text_to_vector(text)
                    if vector is not None:
                        node.embedding = vector

                if vector is not None:
                    self._vector_backend.add(
                        evidence_id=f"ev_sem_{concept}",
                        content=text,
                        vector=list(vector),
                        memory_type="semantic",
                        confidence=node.confidence,
                    )
                    indexed += 1

        # --- Индексация эпизодов EpisodicMemory ---
        episodic = getattr(self._memory, "episodic", None)
        if episodic is not None:
            try:
                with episodic._lock:
                    episodes_snapshot = list(episodic._episodes)
            except AttributeError:
                episodes_snapshot = []

            for ep in episodes_snapshot:
                # Пропускаем «мёртвые» эпизоды (confidence обнулён)
                if ep.confidence <= 0.0:
                    continue
                if not ep.content or not ep.content.strip():
                    continue

                vector = ep.embedding
                if vector is None:
                    vector = self._encode_text_to_vector(ep.content)
                    if vector is not None:
                        ep.embedding = vector

                if vector is not None:
                    self._vector_backend.add(
                        evidence_id=f"ev_ep_{ep.episode_id}",
                        content=ep.content,
                        vector=list(vector),
                        memory_type="episodic",
                        confidence=ep.confidence,
                    )
                    indexed += 1

        if indexed > 0:
            logger.info(
                "[CognitiveCore] _build_vector_index: indexed %d items from memory corpus",
                indexed,
            )

    def _encode_text_to_vector(self, text: str) -> Optional[list]:
        """
        Кодирование текста в вектор через текстовый энкодер.

        Возвращает список float или None при ошибке кодирования.
        """
        if self._encoder is None or not text or not text.strip():
            return None
        try:
            result = self._encoder.encode(text)
            vector = getattr(result, "vector", None)
            if vector and isinstance(vector, list) and not all(v == 0.0 for v in vector):
                return list(vector)
        except Exception as e:
            logger.debug(
                "[CognitiveCore] _encode_text_to_vector failed: %s", e
            )
        return None

    def _index_single_text(
        self,
        evidence_id: str,
        text: str,
        memory_type: str = "semantic",
        confidence: float = 0.5,
    ) -> Optional[list]:
        """
        Кодирование одного текста и добавление в векторный бэкенд (инкрементальная индексация).

        Возвращает вектор при успехе, None в противном случае.
        """
        if self._vector_backend is None or self._encoder is None:
            return None

        vector = self._encode_text_to_vector(text)
        if vector is not None:
            self._vector_backend.add(
                evidence_id=evidence_id,
                content=text,
                vector=vector,
                memory_type=memory_type,
                confidence=confidence,
            )
        return vector

    def remove_from_vector_index(self, evidence_id: str) -> None:
        """
        Удалить элемент из векторного индекса.

        Вызывается при удалении факта, обнулении confidence,
        или замене при разрешении противоречий.
        """
        if self._vector_backend is not None:
            self._vector_backend.remove(evidence_id)

    # ------------------------------------------------------------------
    # Публичные методы: управление фактами с синхронизацией вектора
    # ------------------------------------------------------------------

    def deny_fact(self, concept: str, delta: float = 0.1) -> None:
        """
        Опровергнуть факт — снизить confidence в SemanticMemory
        и удалить из векторного индекса при обнулении.

        Args:
            concept: ключ понятия
            delta:   величина снижения confidence
        """
        semantic = getattr(self._memory, "semantic", None)
        if semantic is None:
            return

        semantic.deny_fact(concept, delta)

        # Проверяем: если confidence упал до 0 — удаляем из вектора
        node = semantic.get_fact(concept)
        if node is None or node.confidence <= 0.0:
            normalized = concept.strip().lower()
            self.remove_from_vector_index(f"ev_sem_{normalized}")
            logger.info(
                "[CognitiveCore] deny_fact: '%s' удалён из векторного индекса (confidence=0)",
                concept,
            )

    def delete_fact(self, concept: str) -> bool:
        """
        Удалить факт из SemanticMemory и векторного индекса.

        Args:
            concept: ключ понятия

        Returns:
            True если факт был удалён, False если не найден
        """
        semantic = getattr(self._memory, "semantic", None)
        if semantic is None:
            return False

        normalized = concept.strip().lower()
        deleted: bool = bool(semantic.delete_fact(concept))

        if deleted:
            self.remove_from_vector_index(f"ev_sem_{normalized}")
            logger.info(
                "[CognitiveCore] delete_fact: '%s' удалён из памяти и векторного индекса",
                concept,
            )

        return deleted

    # ------------------------------------------------------------------
    # Backward compatibility — делегирование к CognitivePipeline
    # ------------------------------------------------------------------

    def _detect_goal_type(self, query: str) -> str:
        """
        Определить тип цели по тексту запроса.

        Делегирует CognitivePipeline._detect_goal_type() для backward
        compatibility с тестами, написанными до P3-10.
        """
        return self._pipeline._detect_goal_type(query)

    def _strip_learn_markers(self, query: str) -> str:
        """
        Убрать маркеры обучения из запроса.

        Делегирует CognitivePipeline._strip_learn_markers() для backward
        compatibility с тестами, написанными до P3-10.
        """
        return self._pipeline._strip_learn_markers(query)

    # ------------------------------------------------------------------
    # Публичные свойства
    # ------------------------------------------------------------------

    @property
    def goal_manager(self) -> GoalManager:
        """Доступ к GoalManager для внешнего мониторинга."""
        return self._goal_manager

    @property
    def cycle_count(self) -> int:
        """Количество выполненных циклов."""
        return self._cycle_count

    def status(self) -> Dict[str, Any]:
        """Статус когнитивного ядра для observability."""
        policy_dict = self._policy.to_dict()
        if not isinstance(policy_dict, dict):
            policy_dict = {}

        return {
            "cycle_count": self._cycle_count,
            "goal_manager": self._goal_manager.status(),
            "has_encoder": self._encoder is not None,
            "has_event_bus": self._event_bus is not None,
            "has_resource_monitor": self._resource_monitor is not None,
            "has_retrieval_adapter": self._retrieval_adapter is not None,
            "has_contradiction_detector": True,
            "has_uncertainty_monitor": True,
            "has_llm_provider": self._llm_provider is not None,
            "llm_provider_name": (
                self._llm_provider.provider_name
                if self._llm_provider is not None
                else None
            ),
            "policy": policy_dict,
        }
