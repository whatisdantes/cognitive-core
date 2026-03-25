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
    TraceChain,
    TraceRef,
    TraceStep,
)
from .context import (
    CognitiveContext,
    CognitiveOutcome,
    FAILURE_OUTCOMES,
    PolicyConstraints,
)
from .contradiction_detector import ContradictionDetector
from .goal_manager import Goal, GoalManager
from .planner import Planner
from .hypothesis_engine import HypothesisEngine
from .reasoner import Reasoner, ReasoningTrace
from .retrieval_adapter import (
    RetrievalAdapter,
    KeywordRetrievalBackend,
    VectorRetrievalBackend,
    HybridRetrievalBackend,
)
from .action_selector import ActionDecision, ActionSelector, ActionType
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
        text_encoder: Any = None,
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

        # --- 2. Ресурсы ---
        if resources is None:
            resources = self._get_resources()

        # --- 3. Retrieval query ---
        retrieval_query = self._build_retrieval_query(
            query, encoded_percept,
        )

        # --- 4. Создать цель ---
        goal = self._create_goal(query, encoded_percept)
        self._goal_manager.push(goal)
        context.active_goal = goal

        # --- 5. Index vector from encoded_percept (if available) ---
        query_vector = self._index_percept_vector(encoded_percept, query)

        # --- 6. Reasoning loop ---
        trace = self._reasoner.reason(
            query=retrieval_query,
            goal=goal,
            policy=self._policy,
            resources=resources,
            query_vector=query_vector,
        )

        # --- 7. Выбор действия ---
        decision = self._action_selector.select(
            trace=trace,
            goal_type=goal.goal_type,
            policy=self._policy,
            resources=resources,
        )

        # --- 8. Выполнить действие (LEARN → store) ---
        self._execute_action(decision, query, trace)

        # --- 9. Завершить цель ---
        outcome = self._parse_outcome(trace.outcome)
        if outcome and outcome in FAILURE_OUTCOMES:
            self._goal_manager.fail(goal.goal_id, trace.stop_reason)
        else:
            self._goal_manager.complete(goal.goal_id)

        # --- 10. Собрать CognitiveResult ---
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        result = self._build_cognitive_result(
            query=query,
            goal=goal,
            trace=trace,
            decision=decision,
            context=context,
            elapsed_ms=elapsed_ms,
        )

        # --- 11. Публикация события ---
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
                    return snap.to_dict()
                if isinstance(snap, dict):
                    return snap
            except Exception as e:
                logger.warning(
                    "[CognitiveCore] resource_monitor.snapshot() error: %s", e
                )
        return {}

    def _index_percept_vector(
        self,
        encoded_percept: Optional[EncodedPercept] = None,
        query: str = "",
    ) -> Optional[list]:
        """
        Index the vector from EncodedPercept into VectorRetrievalBackend
        and return the query vector for hybrid search.

        This bridges TextEncoder → Memory retrieval:
          - EncodedPercept.vector is stored in the vector index
          - The same vector is returned for use as query_vector in hybrid search
        """
        if encoded_percept is None:
            return None

        vector = getattr(encoded_percept, "vector", None)
        if not vector or (isinstance(vector, list) and all(v == 0.0 for v in vector)):
            return None

        # Store in vector backend for future retrieval
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

        MVP: только LEARN → memory_manager.store().
        Остальные действия — без side effects (ответ формируется в result).
        """
        if decision.action_type == ActionType.LEARN:
            try:
                # Извлекаем факт из query (убираем маркеры)
                fact = self._extract_fact(query)
                if fact and hasattr(self._memory, "store"):
                    self._memory.store(fact, importance=0.7)
                    logger.info(
                        "[CognitiveCore] LEARN: stored fact '%s'",
                        fact[:80],
                    )
                    decision.metadata["stored_fact"] = fact
                    decision.metadata["store_success"] = True
            except Exception as e:
                logger.warning(
                    "[CognitiveCore] LEARN store error: %s", e
                )
                decision.metadata["store_success"] = False
                decision.metadata["store_error"] = str(e)

    def _extract_fact(self, query: str) -> str:
        """Извлечь факт из команды 'запомни: ...'."""
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
        return {
            "cycle_count": self._cycle_count,
            "goal_manager": self._goal_manager.status(),
            "has_encoder": self._encoder is not None,
            "has_event_bus": self._event_bus is not None,
            "has_resource_monitor": self._resource_monitor is not None,
            "has_retrieval_adapter": self._retrieval_adapter is not None,
            "has_contradiction_detector": True,
            "has_uncertainty_monitor": True,
            "policy": self._policy.to_dict(),
        }
