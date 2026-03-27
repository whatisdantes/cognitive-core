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
import time
import uuid
from typing import Any, Dict, Optional

from brain.core.contracts import (
    CognitiveResult,
    EncodedPercept,
    EventBusProtocol,
    MemoryManagerProtocol,
    ResourceMonitorProtocol,
    TextEncoderProtocol,
    TraceChain,
    TraceRef,
    TraceStep,
)

from .action_selector import ActionDecision, ActionSelector, ActionType
from .context import (
    FAILURE_OUTCOMES,
    CognitiveContext,
    CognitiveOutcome,
    PolicyConstraints,
)
from .contradiction_detector import ContradictionDetector
from .goal_manager import Goal, GoalManager
from .hypothesis_engine import HypothesisEngine
from .planner import Planner
from .reasoner import Reasoner, ReasoningTrace
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

        # --- Построение векторного индекса из персистентного корпуса памяти ---
        self._build_vector_index()

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

        Цепочка:
          1. Создать контекст (session_id, cycle_id, trace_id)
          2. Определить тип цели и создать Goal
          3. Выполнить reasoning loop → ReasoningTrace
          4. Выбрать действие → ActionDecision
          5. Выполнить действие (LEARN → store в память)
          6. Собрать CognitiveResult

        Args:
            query:           текстовый запрос
            encoded_percept: закодированный перцепт (опционально)
            resources:       состояние ресурсов (опционально)
            session_id:      идентификатор сессии для связывания нескольких
                             вызовов в один диалог. Если None — генерируется
                             автоматически (каждый вызов = новая сессия).

        Возвращает CognitiveResult.
        """
        start_time = time.perf_counter()
        self._cycle_count += 1

        # --- 1. Контекст ---
        context = self._create_context(session_id=session_id)

        # --- 2. Auto-encode (B.1) ---
        if encoded_percept is None and self._encoder is not None:
            try:
                encoded_percept = self._encoder.encode(query)
                logger.debug(
                    "[CognitiveCore] auto-encoded query: mode=%s dim=%d",
                    getattr(encoded_percept, "encoder_model", "?"),
                    getattr(encoded_percept, "vector_dim", 0),
                )
            except Exception as e:
                logger.warning("[CognitiveCore] auto-encode failed: %s", e)
                encoded_percept = None

        # --- 3. Ресурсы ---
        if resources is None:
            resources = self._get_resources()

        # --- 4. Retrieval query ---
        retrieval_query = self._build_retrieval_query(
            query, encoded_percept,
        )

        # --- 5. Создать цель ---
        goal = self._create_goal(query, encoded_percept)
        self._goal_manager.push(goal)
        context.active_goal = goal

        # --- 6. Index vector from encoded_percept (if available) ---
        query_vector = self._index_percept_vector(encoded_percept, query)

        # --- 7. Reasoning loop ---
        trace = self._reasoner.reason(
            query=retrieval_query,
            goal=goal,
            policy=self._policy,
            resources=resources,
            query_vector=query_vector,
        )

        # --- 8. Выбор действия ---
        decision = self._action_selector.select(
            trace=trace,
            goal_type=goal.goal_type,
            policy=self._policy,
            resources=resources,
        )

        # --- 9. Выполнить действие (LEARN → store) ---
        self._execute_action(decision, query, trace)

        # --- 10. Завершить цель ---
        outcome = self._parse_outcome(trace.outcome)
        if outcome and outcome in FAILURE_OUTCOMES:
            self._goal_manager.fail(goal.goal_id, trace.stop_reason)
        else:
            self._goal_manager.complete(goal.goal_id)

        # --- 11. Собрать CognitiveResult ---
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        result = self._build_cognitive_result(
            query=query,
            goal=goal,
            trace=trace,
            decision=decision,
            context=context,
            elapsed_ms=elapsed_ms,
        )

        # --- 12. Публикация события ---
        self._publish_event("cognitive_cycle_complete", {
            "trace_id": context.trace_id,
            "cycle_id": context.cycle_id,
            "action": decision.action,
            "confidence": decision.confidence,
            "outcome": trace.outcome,
            "duration_ms": round(elapsed_ms, 2),
        })

        logger.info(
            "[CognitiveCore] run complete: query='%s' action=%s "
            "confidence=%.3f outcome=%s duration=%.1fms",
            query[:50], decision.action, decision.confidence,
            trace.outcome, elapsed_ms,
        )

        return result

    # ------------------------------------------------------------------
    # Приватные методы
    # ------------------------------------------------------------------

    def _create_context(
        self,
        session_id: Optional[str] = None,
    ) -> CognitiveContext:
        """Создать контекст для текущего цикла.

        Args:
            session_id: внешний session_id для связывания вызовов.
                        Если None — генерируется автоматически.
        """
        return CognitiveContext(
            session_id=session_id or f"session_{uuid.uuid4().hex[:8]}",
            cycle_id=f"cycle_{self._cycle_count}",
            trace_id=f"trace_{uuid.uuid4().hex[:8]}",
        )

    def _get_resources(self) -> Dict[str, Any]:
        """Получить текущее состояние ресурсов."""
        if self._resource_monitor and hasattr(self._resource_monitor, "snapshot"):
            try:
                snap = self._resource_monitor.snapshot()
                if hasattr(snap, "to_dict"):
                    snap_dict = snap.to_dict()
                    if isinstance(snap_dict, dict):
                        return snap_dict
                    return {}
                if isinstance(snap, dict):
                    return snap
            except Exception as e:
                logger.warning(
                    "[CognitiveCore] resource_monitor.snapshot() error: %s", e
                )
        return {}

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

    def _index_percept_vector(
        self,
        encoded_percept: Optional[EncodedPercept] = None,
        query: str = "",
    ) -> Optional[list]:
        """
        Индексация вектора из EncodedPercept в VectorRetrievalBackend
        и возврат query-вектора для гибридного поиска.

        Мост TextEncoder → Memory retrieval:
          - EncodedPercept.vector сохраняется в векторном индексе
          - Тот же вектор возвращается для использования как query_vector в гибридном поиске
        """
        if encoded_percept is None:
            return None

        vector = getattr(encoded_percept, "vector", None)
        if not vector or (isinstance(vector, list) and all(v == 0.0 for v in vector)):
            return None

        # Сохраняем в векторный бэкенд для будущего поиска
        if self._vector_backend is not None:
            percept_id = getattr(encoded_percept, "percept_id", "") or f"enc_{id(encoded_percept)}"
            text = getattr(encoded_percept, "text", query)
            self._vector_backend.add(
                evidence_id=f"ev_enc_{percept_id}",
                content=text or query,
                vector=list(vector),
                memory_type="encoded_percept",
                confidence=getattr(encoded_percept, "quality", 0.5),
            )

        return list(vector)

    def _build_retrieval_query(
        self,
        query: str,
        encoded_percept: Optional[EncodedPercept] = None,
    ) -> str:
        """
        Bridge EncodedPercept → retrieval query.

        MVP: приватный метод (не отдельный adapter).
        Если есть encoded_percept с keywords — обогащаем запрос.
        """
        if encoded_percept is None:
            return query

        # Извлекаем keywords из metadata
        keywords = encoded_percept.metadata.get("keywords", [])
        if not keywords:
            return query

        # Обогащаем запрос ключевыми словами
        kw_str = " ".join(keywords[:5])
        enriched = f"{query} {kw_str}".strip()

        logger.debug(
            "[CognitiveCore] _build_retrieval_query: '%s' → '%s'",
            query[:50], enriched[:80],
        )
        return enriched

    def _create_goal(
        self,
        query: str,
        encoded_percept: Optional[EncodedPercept] = None,
    ) -> Goal:
        """
        Создать цель на основе запроса.

        Эвристика определения goal_type:
          - "запомни" / "сохрани" / "учти" → learn_fact
          - "?" в конце → answer_question
          - "правда ли" / "верно ли" → verify_claim
          - иначе → answer_question (default)
        """
        goal_type = self._detect_goal_type(query, encoded_percept)

        return Goal(
            description=query[:200],
            goal_type=goal_type,
            priority=0.5,
            context={
                "original_query": query,
                "has_percept": encoded_percept is not None,
            },
        )

    def _detect_goal_type(
        self,
        query: str,
        encoded_percept: Optional[EncodedPercept] = None,
    ) -> str:
        """Эвристика определения типа цели."""
        q_lower = query.lower().strip()

        # learn_fact
        learn_markers = ["запомни", "сохрани", "учти", "запиши", "remember", "save"]
        for marker in learn_markers:
            if marker in q_lower:
                return "learn_fact"

        # message_type из encoded_percept
        if encoded_percept and encoded_percept.message_type == "command":
            # Команды типа "запомни" уже обработаны выше
            pass

        # verify_claim
        verify_markers = [
            "правда ли", "верно ли", "так ли", "действительно ли",
            "is it true", "is it correct",
        ]
        for marker in verify_markers:
            if marker in q_lower:
                return "verify_claim"

        # answer_question (по умолчанию для вопросов)
        if "?" in query or q_lower.startswith(("что ", "кто ", "где ", "когда ",
                                                "как ", "почему ", "зачем ",
                                                "what ", "who ", "where ",
                                                "when ", "how ", "why ")):
            return "answer_question"

        # explore_topic (длинные запросы без вопроса)
        if len(query.split()) > 10 and "?" not in query:
            return "explore_topic"

        return "answer_question"

    def _execute_action(
        self,
        decision: ActionDecision,
        query: str,
        trace: ReasoningTrace,
    ) -> None:
        """
        Выполнить действие (side effects).

        LEARN → memory_manager.store() + инкрементальная векторная индексация.
        Остальные действия — без side effects (ответ формируется в result).
        """
        if decision.action_type == ActionType.LEARN:
            try:
                # Извлекаем факт из query (убираем маркеры)
                fact = self._strip_learn_markers(query)
                if fact and hasattr(self._memory, "store"):
                    self._memory.store(fact, importance=0.7)
                    logger.info(
                        "[CognitiveCore] LEARN: stored fact '%s'",
                        fact[:80],
                    )
                    decision.metadata["stored_fact"] = fact
                    decision.metadata["store_success"] = True

                    # Инкрементальная векторная индексация (P0-P1)
                    self._index_single_text(
                        evidence_id=f"ev_learn_{self._cycle_count}",
                        text=fact,
                        memory_type="learned_fact",
                        confidence=0.7,
                    )
            except Exception as e:
                logger.warning(
                    "[CognitiveCore] LEARN store error: %s", e
                )
                decision.metadata["store_success"] = False
                decision.metadata["store_error"] = str(e)

    def _strip_learn_markers(self, query: str) -> str:
        """Убрать маркеры команды ('запомни:', 'сохрани:' и т.д.) и вернуть чистый факт."""
        q = query.strip()
        # Убираем маркеры
        markers = [
            "запомни:", "запомни ", "сохрани:", "сохрани ",
            "учти:", "учти ", "запиши:", "запиши ",
            "remember:", "remember ", "save:", "save ",
        ]
        for marker in markers:
            if q.lower().startswith(marker):
                return q[len(marker):].strip()
        return q

    def _build_cognitive_result(
        self,
        query: str,
        goal: Goal,
        trace: ReasoningTrace,
        decision: ActionDecision,
        context: CognitiveContext,
        elapsed_ms: float,
    ) -> CognitiveResult:
        """Собрать CognitiveResult из всех компонентов."""

        # Построить TraceChain из ReasoningTrace
        trace_steps = []
        for rs in trace.steps:
            trace_steps.append(TraceStep(
                step_id=rs.step_id,
                module="cognition.reasoner",
                action=rs.step_type,
                confidence=trace.final_confidence,
                details={
                    "description": rs.description,
                    "duration_ms": rs.duration_ms,
                    **rs.metadata,
                },
            ))

        # Добавить шаг action_selection
        trace_steps.append(TraceStep(
            step_id=f"action_{uuid.uuid4().hex[:6]}",
            module="cognition.action_selector",
            action=decision.action,
            confidence=decision.confidence,
            details={
                "reasoning": decision.reasoning,
                **decision.metadata,
            },
        ))

        trace_chain = TraceChain(
            trace_id=context.trace_id,
            session_id=context.session_id,
            cycle_id=context.cycle_id,
            steps=trace_steps,
            summary=(
                f"query='{query[:80]}' → {decision.action} "
                f"(confidence={decision.confidence:.3f})"
            ),
        )

        # Memory refs из evidence
        memory_refs = [
            TraceRef(ref_type="evidence", ref_id=eid)
            for eid in trace.evidence_refs
        ]

        return CognitiveResult(
            action=decision.action,
            response=decision.statement,
            confidence=decision.confidence,
            trace=trace_chain,
            goal=goal.description,
            trace_id=context.trace_id,
            session_id=context.session_id,
            cycle_id=context.cycle_id,
            memory_refs=memory_refs,
            metadata={
                "goal_type": goal.goal_type,
                "goal_id": goal.goal_id,
                "outcome": trace.outcome,
                "stop_reason": trace.stop_reason,
                "total_iterations": trace.total_iterations,
                "reasoning_duration_ms": trace.total_duration_ms,
                "total_duration_ms": round(elapsed_ms, 2),
                "hypothesis_count": trace.hypothesis_count,
                "best_hypothesis_id": trace.best_hypothesis_id,
            },
        )

    def _publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Публикация события через EventBus (если доступен)."""
        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish(event_type, data)
            except Exception as e:
                logger.warning(
                    "[CognitiveCore] event_bus.publish error: %s", e
                )

    @staticmethod
    def _parse_outcome(outcome_str: str) -> Optional[CognitiveOutcome]:
        """Парсинг строки outcome."""
        if not outcome_str:
            return None
        try:
            return CognitiveOutcome(outcome_str)
        except ValueError:
            return None

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
            "policy": policy_dict,
        }
