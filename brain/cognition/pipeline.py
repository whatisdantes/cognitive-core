"""
brain/cognition/pipeline.py

Явный пайплайн когнитивного цикла (P3-10).

Заменяет «god-method» CognitiveCore.run() на цепочку явных шагов (15 шагов, Этап H + N):
  1.  create_context        — создание контекста (session_id, cycle_id, trace_id)
  2.  auto_encode           — кодирование запроса через TextEncoder
  3.  get_resources         — получение состояния ресурсов
  4.  build_retrieval_query — обогащение запроса ключевыми словами
  5.  create_goal           — определение типа цели и создание Goal
  6.  evaluate_salience     — оценка значимости стимула (SalienceEngine) [Этап H]
  7.  compute_budget        — вычисление AttentionBudget (AttentionController) [Этап H]
  8.  index_percept_vector  — индексация вектора перцепта
  9.  reason                — reasoning loop → ReasoningTrace
  10. llm_enhance           — LLM-обогащение best_statement (no-op если LLM нет) [Этап N]
  11. select_action         — выбор действия + PolicyLayer фильтрация [Этап H]
  12. execute_action        — выполнение действия (LEARN → store)
  13. complete_goal         — завершение/провал цели в GoalManager
  14. build_result          — сборка CognitiveResult + salience/budget/llm metadata
  15. publish_event         — публикация события через EventBus

Преимущества:
  - Каждый шаг тестируется изолированно
  - Шаги можно переопределять в подклассах
  - Явная последовательность вместо неявного god-method
  - CognitivePipelineContext несёт всё состояние между шагами

Использование:
    pipeline = CognitivePipeline(memory=mm, ...)
    result = pipeline.run("что такое нейрон?")
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from brain.bridges.llm_bridge import LLMProvider, LLMRequest, LLMUnavailableError
from brain.core.attention_controller import AttentionBudget, AttentionController
from brain.core.contracts import (
    CognitiveResult,
    EncodedPercept,
    EventBusProtocol,
    MemoryManagerProtocol,
    ResourceMonitorProtocol,
    ResourceState,
    TextEncoderProtocol,
    TraceChain,
    TraceRef,
    TraceStep,
)
from brain.logging import (
    _NULL_LOGGER,
    _NULL_TRACE_BUILDER,
    BrainLogger,
    TraceBuilder,
)

from .action_selector import ActionDecision, ActionSelector, ActionType
from .context import (
    FAILURE_OUTCOMES,
    CognitiveContext,
    CognitiveOutcome,
    PolicyConstraints,
    ReasoningState,
)
from .goal_manager import Goal, GoalManager
from .policy_layer import PolicyLayer
from .reasoner import Reasoner, ReasoningTrace
from .retrieval_adapter import VectorRetrievalBackend
from .salience_engine import SalienceEngine, SalienceScore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Контекст пайплайна — несёт всё состояние между шагами
# ---------------------------------------------------------------------------

@dataclass
class CognitivePipelineContext:
    """
    Контекст, передаваемый между шагами когнитивного пайплайна.

    Каждый шаг читает нужные поля и записывает результаты.
    Поля заполняются последовательно по мере прохождения шагов.
    """

    # --- Входные данные ---
    query: str
    session_id: Optional[str] = None
    encoded_percept: Optional[EncodedPercept] = None

    # --- Заполняется шагами ---
    resources: Dict[str, Any] = field(default_factory=dict)
    retrieval_query: str = ""
    goal: Optional[Goal] = None
    query_vector: Optional[list] = None
    trace: Optional[ReasoningTrace] = None
    decision: Optional[ActionDecision] = None
    cognitive_context: Optional[CognitiveContext] = None
    result: Optional[CognitiveResult] = None

    # --- Этап H: Attention & Resource Control ---
    salience: Optional[SalienceScore] = None
    budget: Optional[AttentionBudget] = None

    # --- Этап N: LLM Bridge ---
    llm_enhanced: bool = False
    llm_response_text: str = ""
    llm_provider_name: str = ""

    # --- Метрики ---
    start_time: float = field(default_factory=time.perf_counter)
    elapsed_ms: float = 0.0

    # --- Флаги ---
    aborted: bool = False
    abort_reason: str = ""


# ---------------------------------------------------------------------------
# Тип шага пайплайна
# ---------------------------------------------------------------------------

PipelineStep = Callable[["CognitivePipelineContext"], None]
"""
Сигнатура шага пайплайна:
    ctx: CognitivePipelineContext — контекст (читает и пишет)
    Возвращает None. Для прерывания — устанавливает ctx.aborted = True.
"""


# ---------------------------------------------------------------------------
# CognitivePipeline — явный пайплайн когнитивного цикла
# ---------------------------------------------------------------------------

class CognitivePipeline:
    """
    Явный пайплайн когнитивного цикла.

    Каждый шаг — отдельный метод, принимающий CognitivePipelineContext.
    Шаги выполняются последовательно в методе run().

    Для расширения — переопределить нужные step_* методы в подклассе.

    Использование:
        pipeline = CognitivePipeline(
            memory=mm,
            encoder=enc,
            event_bus=bus,
            resource_monitor=rm,
            policy=policy,
            goal_manager=gm,
            reasoner=reasoner,
            action_selector=selector,
            vector_backend=vb,
            cycle_count_fn=lambda: core.cycle_count,
        )
        result = pipeline.run("что такое нейрон?")
    """

    def __init__(
        self,
        memory: MemoryManagerProtocol,
        encoder: Optional[TextEncoderProtocol],
        event_bus: Optional[EventBusProtocol],
        resource_monitor: Optional[ResourceMonitorProtocol],
        policy: PolicyConstraints,
        goal_manager: GoalManager,
        reasoner: Reasoner,
        action_selector: ActionSelector,
        vector_backend: Optional[VectorRetrievalBackend],
        cycle_count_fn: Callable[[], int],
        llm_provider: Optional[LLMProvider] = None,
        brain_logger: Optional[BrainLogger] = None,
        trace_builder: Optional[TraceBuilder] = None,
    ) -> None:
        self._memory = memory
        self._encoder = encoder
        self._event_bus = event_bus
        self._resource_monitor = resource_monitor
        self._policy = policy
        self._goal_manager = goal_manager
        self._reasoner = reasoner
        self._action_selector = action_selector
        self._vector_backend = vector_backend
        self._cycle_count_fn = cycle_count_fn

        # --- Этап H: Attention & Resource Control ---
        self._salience_engine = SalienceEngine()
        self._attention_controller = AttentionController()
        self._policy_layer = PolicyLayer()

        # --- Этап N: LLM Bridge (опциональный) ---
        self._llm_provider: Optional[LLMProvider] = llm_provider

        # --- Phase 3: BrainLogger + TraceBuilder (NullObject pattern) ---
        self._blog: BrainLogger = brain_logger or _NULL_LOGGER  # type: ignore[assignment]
        self._trace_builder: TraceBuilder = trace_builder or _NULL_TRACE_BUILDER  # type: ignore[assignment]

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
        Выполнить полный когнитивный цикл через явный пайплайн.

        Args:
            query:           текстовый запрос
            encoded_percept: закодированный перцепт (опционально)
            resources:       состояние ресурсов (опционально)
            session_id:      идентификатор сессии

        Returns:
            CognitiveResult
        """
        ctx = CognitivePipelineContext(
            query=query,
            session_id=session_id,
            encoded_percept=encoded_percept,
            resources=resources or {},
        )

        # --- 1. cycle_start (Phase 3, LOG_PLAN.md v2.0) ---
        self._blog.info(
            "pipeline", "cycle_start",
            session_id=session_id or "",
            state={"query_preview": query[:80]},
        )

        # Явная последовательность шагов (15 шагов, Этап H + N)
        steps: List[PipelineStep] = [
            self.step_create_context,       # 1
            self.step_auto_encode,          # 2
            self.step_get_resources,        # 3
            self.step_build_retrieval_query,# 4
            self.step_create_goal,          # 5
            self.step_evaluate_salience,    # 6  ← Этап H (после goal)
            self.step_compute_budget,       # 7  ← Этап H (после salience)
            self.step_index_percept_vector, # 8
            self.step_reason,               # 9
            self.step_llm_enhance,          # 10 ← Этап N (no-op если LLM нет)
            self.step_select_action,        # 11 ← + PolicyLayer
            self.step_execute_action,       # 12
            self.step_complete_goal,        # 13
            self.step_build_result,         # 14 ← + salience/budget/llm metadata
            self.step_publish_event,        # 15
        ]

        for step in steps:
            if ctx.aborted:
                logger.warning(
                    "[CognitivePipeline] пайплайн прерван на шаге '%s': %s",
                    step.__name__, ctx.abort_reason,
                )
                break
            try:
                t0 = time.perf_counter()
                step(ctx)
                step_ms = (time.perf_counter() - t0) * 1000
                # --- auto-timing debug log (Phase 3) ---
                self._blog.debug(
                    "pipeline",
                    f"step_{step.__name__}_done",
                    trace_id=ctx.cognitive_context.trace_id if ctx.cognitive_context else "",
                    session_id=ctx.cognitive_context.session_id if ctx.cognitive_context else "",
                    cycle_id=ctx.cognitive_context.cycle_id if ctx.cognitive_context else "",
                    latency_ms=step_ms,
                )
                # Запустить TraceBuilder сразу после step_create_context
                if step is self.step_create_context and ctx.cognitive_context:
                    self._trace_builder.start_trace(
                        ctx.cognitive_context.trace_id,
                        session_id=ctx.cognitive_context.session_id,
                        cycle_id=ctx.cognitive_context.cycle_id,
                    )
            except Exception as e:
                logger.error(
                    "[CognitivePipeline] ошибка в шаге '%s': %s",
                    step.__name__, e, exc_info=True,
                )
                ctx.aborted = True
                ctx.abort_reason = f"{step.__name__}: {e}"
                break

        # --- 9. cycle_complete (Phase 3) ---
        if ctx.result is not None and ctx.cognitive_context is not None:
            self._blog.info(
                "pipeline", "cycle_complete",
                trace_id=ctx.cognitive_context.trace_id,
                session_id=ctx.cognitive_context.session_id,
                cycle_id=ctx.cognitive_context.cycle_id,
                latency_ms=ctx.elapsed_ms,
                decision={
                    "action": ctx.result.action,
                    "confidence": ctx.result.confidence,
                },
            )
            self._trace_builder.set_summary(
                ctx.cognitive_context.trace_id,
                f"query='{query[:80]}' → {ctx.result.action} "
                f"(conf={ctx.result.confidence:.3f})",
            )
            self._trace_builder.finish_trace(ctx.cognitive_context.trace_id)

        # Если пайплайн прерван — возвращаем fallback result
        if ctx.aborted or ctx.result is None:
            return self._build_fallback_result(ctx)

        return ctx.result

    # ------------------------------------------------------------------
    # Шаги пайплайна
    # ------------------------------------------------------------------

    def step_create_context(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 1: Создать контекст (session_id, cycle_id, trace_id)."""
        ctx.cognitive_context = CognitiveContext(
            session_id=ctx.session_id or f"session_{uuid.uuid4().hex[:8]}",
            cycle_id=f"cycle_{self._cycle_count_fn()}",
            trace_id=f"trace_{uuid.uuid4().hex[:8]}",
        )

    def step_auto_encode(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 2: Автоматическое кодирование запроса через TextEncoder."""
        if ctx.encoded_percept is not None or self._encoder is None:
            return
        try:
            ctx.encoded_percept = self._encoder.encode(ctx.query)
            logger.debug(
                "[CognitivePipeline] auto-encoded: mode=%s dim=%d",
                getattr(ctx.encoded_percept, "encoder_model", "?"),
                getattr(ctx.encoded_percept, "vector_dim", 0),
            )
            # --- 2. encode_done (Phase 3) ---
            self._blog.info(
                "pipeline", "encode_done",
                trace_id=ctx.cognitive_context.trace_id if ctx.cognitive_context else "",
                session_id=ctx.cognitive_context.session_id if ctx.cognitive_context else "",
                state={
                    "modality": str(getattr(ctx.encoded_percept, "modality", "text")),
                    "vector_dim": getattr(ctx.encoded_percept, "vector_dim", 0),
                },
            )
        except Exception as e:
            logger.warning("[CognitivePipeline] auto-encode failed: %s", e)
            ctx.encoded_percept = None

    def step_get_resources(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 3: Получить состояние ресурсов."""
        if ctx.resources:
            return  # уже заполнено извне
        if self._resource_monitor and hasattr(self._resource_monitor, "snapshot"):
            try:
                snap = self._resource_monitor.snapshot()
                if hasattr(snap, "to_dict"):
                    snap_dict = snap.to_dict()
                    ctx.resources = snap_dict if isinstance(snap_dict, dict) else {}
                elif isinstance(snap, dict):
                    ctx.resources = snap
            except Exception as e:
                logger.warning("[CognitivePipeline] resource_monitor.snapshot() error: %s", e)

    def step_build_retrieval_query(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 4: Обогатить запрос ключевыми словами из EncodedPercept."""
        if ctx.encoded_percept is None:
            ctx.retrieval_query = ctx.query
            return
        keywords = ctx.encoded_percept.metadata.get("keywords", [])
        if not keywords:
            ctx.retrieval_query = ctx.query
            return
        kw_str = " ".join(keywords[:5])
        ctx.retrieval_query = f"{ctx.query} {kw_str}".strip()
        logger.debug(
            "[CognitivePipeline] retrieval_query: '%s' → '%s'",
            ctx.query[:50], ctx.retrieval_query[:80],
        )

    def step_create_goal(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 5: Определить тип цели и создать Goal."""
        goal_type = self._detect_goal_type(ctx.query, ctx.encoded_percept)
        ctx.goal = Goal(
            description=ctx.query[:200],
            goal_type=goal_type,
            priority=0.5,
            context={
                "original_query": ctx.query,
                "has_percept": ctx.encoded_percept is not None,
            },
        )
        self._goal_manager.push(ctx.goal)
        if ctx.cognitive_context is not None:
            ctx.cognitive_context.active_goal = ctx.goal
        # --- 3. goal_created (Phase 3) ---
        if ctx.cognitive_context is not None and ctx.goal is not None:
            self._blog.info(
                "pipeline", "goal_created",
                trace_id=ctx.cognitive_context.trace_id,
                session_id=ctx.cognitive_context.session_id,
                state={"goal_type": goal_type, "goal_id": ctx.goal.goal_id},
            )
            self._trace_builder.add_step(
                ctx.cognitive_context.trace_id,
                module="pipeline",
                action="goal_created",
                confidence=1.0,
                details={"goal_type": goal_type, "goal_id": ctx.goal.goal_id},
            )

    def step_evaluate_salience(self, ctx: CognitivePipelineContext) -> None:
        """
        Шаг 6: Оценить значимость стимула через SalienceEngine.

        Вызывается ПОСЛЕ create_goal, чтобы relevance мог использовать
        active_goal.description. Результат записывается в ctx.salience.
        """
        ctx.salience = self._salience_engine.evaluate(
            stimulus=ctx.query,
            active_goal=ctx.goal,
        )
        logger.debug(
            "[CognitivePipeline] salience: overall=%.3f action=%s",
            ctx.salience.overall,
            ctx.salience.action,
        )
        # --- 4. salience_evaluated (Phase 3) ---
        if ctx.cognitive_context is not None:
            self._blog.debug(
                "pipeline", "salience_evaluated",
                trace_id=ctx.cognitive_context.trace_id,
                session_id=ctx.cognitive_context.session_id,
                state={
                    "overall": round(ctx.salience.overall, 4),
                    "action": ctx.salience.action,
                    "reason": ctx.salience.reason,
                },
            )

    def step_compute_budget(self, ctx: CognitivePipelineContext) -> None:
        """
        Шаг 7: Вычислить AttentionBudget через AttentionController.

        Учитывает состояние ресурсов, тип цели и оценку значимости.
        Результат записывается в ctx.budget.

        # TODO: budget enforcement в step_reason и step_execute_action
        #        (ограничение числа итераций reasoning по budget.cognition,
        #         пропуск learning при budget.learning == 0.0)
        """
        resource_state = self._build_resource_state(ctx.resources)
        goal_type = ctx.goal.goal_type if ctx.goal else "answer_question"
        cycle_id = (
            ctx.cognitive_context.cycle_id
            if ctx.cognitive_context
            else f"cycle_{self._cycle_count_fn()}"
        )

        ctx.budget = self._attention_controller.compute_budget(
            goal_type=goal_type,
            resource_state=resource_state,
            salience=ctx.salience,
            cycle_id=cycle_id,
        )
        logger.debug(
            "[CognitivePipeline] budget: policy=%s cognition=%.2f memory=%.2f",
            ctx.budget.policy,
            ctx.budget.cognition,
            ctx.budget.memory,
        )
        # --- 5. budget_computed (Phase 3) ---
        if ctx.cognitive_context is not None:
            self._blog.debug(
                "pipeline", "budget_computed",
                trace_id=ctx.cognitive_context.trace_id,
                session_id=ctx.cognitive_context.session_id,
                state={
                    "policy": ctx.budget.policy,
                    "cognition": round(ctx.budget.cognition, 4),
                    "memory": round(ctx.budget.memory, 4),
                    "reason": ctx.budget.reason,
                },
            )

    def step_index_percept_vector(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 8: Индексировать вектор перцепта в VectorRetrievalBackend."""
        if ctx.encoded_percept is None:
            return
        vector = getattr(ctx.encoded_percept, "vector", None)
        if not vector or (isinstance(vector, list) and all(v == 0.0 for v in vector)):
            return
        if self._vector_backend is not None:
            percept_id = getattr(ctx.encoded_percept, "percept_id", "") or f"enc_{id(ctx.encoded_percept)}"
            text = getattr(ctx.encoded_percept, "text", ctx.query)
            self._vector_backend.add(
                evidence_id=f"ev_enc_{percept_id}",
                content=text or ctx.query,
                vector=list(vector),
                memory_type="encoded_percept",
                confidence=getattr(ctx.encoded_percept, "quality", 0.5),
            )
        ctx.query_vector = list(vector)

    def step_reason(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 9: Reasoning loop → ReasoningTrace."""
        if ctx.goal is None:
            ctx.aborted = True
            ctx.abort_reason = "step_reason: goal is None"
            return
        ctx.trace = self._reasoner.reason(
            query=ctx.retrieval_query or ctx.query,
            goal=ctx.goal,
            policy=self._policy,
            resources=ctx.resources,
            query_vector=ctx.query_vector,
        )
        # --- 6. reason_done (Phase 3) ---
        if ctx.cognitive_context is not None and ctx.trace is not None:
            self._blog.info(
                "pipeline", "reason_done",
                trace_id=ctx.cognitive_context.trace_id,
                session_id=ctx.cognitive_context.session_id,
                latency_ms=ctx.trace.total_duration_ms,
                state={
                    "confidence": round(ctx.trace.final_confidence, 4),
                    "iterations": ctx.trace.total_iterations,
                    "outcome": ctx.trace.outcome,
                    "hypothesis_count": ctx.trace.hypothesis_count,
                },
            )

    def step_llm_enhance(self, ctx: CognitivePipelineContext) -> None:
        """
        Шаг 10: LLM-обогащение best_statement из ReasoningTrace (Этап N).

        Если LLM провайдер не настроен или недоступен — no-op (backward compatible).
        Если LLM доступен — берёт best_statement из trace, строит промпт
        из query + evidence, вызывает LLM и обновляет best_statement.

        Результат записывается в:
          ctx.llm_enhanced      — True если LLM успешно обогатил ответ
          ctx.llm_response_text — текст LLM ответа
          ctx.llm_provider_name — название провайдера
          ctx.trace.best_statement — обновлённый ответ (если LLM успешен)
        """
        if self._llm_provider is None or not self._llm_provider.is_available():
            return  # no-op: LLM не настроен или недоступен
        if ctx.trace is None:
            return  # no-op: reasoning не выполнен

        try:
            # Строим промпт из query + best_statement + evidence
            best = ctx.trace.best_statement or ""
            evidence_refs = ctx.trace.evidence_refs[:3]  # топ-3 для краткости

            system_prompt = (
                "Ты — когнитивный ассистент. Улучши и уточни ответ на вопрос, "
                "сохраняя фактическую точность. Отвечай кратко и по существу."
            )
            prompt_parts = [f"Вопрос: {ctx.query}"]
            if best:
                prompt_parts.append(f"Предварительный ответ: {best}")
            if evidence_refs:
                prompt_parts.append(f"Источники: {', '.join(evidence_refs)}")
            prompt_parts.append("Улучшенный ответ:")
            prompt = "\n".join(prompt_parts)

            request = LLMRequest(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=256,
                temperature=0.3,
                metadata={
                    "trace_id": ctx.cognitive_context.trace_id if ctx.cognitive_context else "",
                    "cycle_id": ctx.cognitive_context.cycle_id if ctx.cognitive_context else "",
                    "step": "llm_enhance",
                },
            )

            response = self._llm_provider.complete(request)

            if response.text and response.text.strip():
                ctx.trace.best_statement = response.text.strip()
                ctx.llm_enhanced = True
                ctx.llm_response_text = response.text.strip()
                ctx.llm_provider_name = response.provider
                logger.info(
                    "[CognitivePipeline] LLM enhance OK: provider=%s tokens=%d",
                    response.provider, response.tokens_used,
                )
                # --- 7. llm_enhance_done (Phase 3) ---
                if ctx.cognitive_context is not None:
                    self._blog.info(
                        "pipeline", "llm_enhance_done",
                        trace_id=ctx.cognitive_context.trace_id,
                        session_id=ctx.cognitive_context.session_id,
                        state={
                            "provider": response.provider,
                            "tokens_used": response.tokens_used,
                        },
                    )

        except LLMUnavailableError as e:
            logger.warning("[CognitivePipeline] LLM enhance unavailable: %s", e)
        except Exception as e:
            logger.warning("[CognitivePipeline] LLM enhance error: %s", e)
            # Не прерываем пайплайн — LLM enhance опциональный

    def step_select_action(self, ctx: CognitivePipelineContext) -> None:
        """
        Шаг 11: Выбор действия → ActionDecision (с PolicyLayer).

        Порядок:
          1. ActionSelector.select() → первичное решение
          2. PolicyLayer.apply_filters() → проверка допустимости
          3. Если действие заблокировано — override на первый допустимый
        """
        if ctx.trace is None or ctx.goal is None:
            ctx.aborted = True
            ctx.abort_reason = "step_select_action: trace or goal is None"
            return

        # 1. Первичное решение от ActionSelector
        ctx.decision = self._action_selector.select(
            trace=ctx.trace,
            goal_type=ctx.goal.goal_type,
            policy=self._policy,
            resources=ctx.resources,
        )

        # 2. PolicyLayer: проверить допустимость выбранного действия
        resource_state = self._build_resource_state(ctx.resources)
        reasoning_state = self._build_reasoning_state(ctx.trace)
        outcome = self._parse_outcome(ctx.trace.outcome)

        allowed = self._policy_layer.apply_filters(
            candidates=list(ActionType),
            state=reasoning_state,
            resources=resource_state,
            constraints=self._policy,
            outcome=outcome,
        )

        # 3. Если действие заблокировано — override на первый допустимый
        try:
            current_action_type = ActionType(ctx.decision.action)
        except ValueError:
            current_action_type = ActionType.REFUSE

        if allowed and current_action_type not in allowed:
            fallback_type = allowed[0]
            logger.info(
                "[CognitivePipeline] PolicyLayer override: %s → %s",
                current_action_type.value,
                fallback_type.value,
            )
            ctx.decision = ActionDecision(
                action=fallback_type.value,
                statement=ctx.decision.statement,
                confidence=round(ctx.decision.confidence * 0.8, 4),
                reasoning=(
                    f"PolicyLayer: {current_action_type.value} заблокирован, "
                    f"fallback → {fallback_type.value}"
                ),
                metadata={
                    **ctx.decision.metadata,
                    "policy_layer_applied": True,
                    "original_action": current_action_type.value,
                },
            )

        # --- 8. action_selected (Phase 3) ---
        if ctx.cognitive_context is not None and ctx.decision is not None:
            self._blog.info(
                "pipeline", "action_selected",
                trace_id=ctx.cognitive_context.trace_id,
                session_id=ctx.cognitive_context.session_id,
                decision={
                    "action": ctx.decision.action,
                    "confidence": ctx.decision.confidence,
                },
            )
            self._trace_builder.add_step(
                ctx.cognitive_context.trace_id,
                module="pipeline",
                action="action_selected",
                confidence=ctx.decision.confidence,
                details={
                    "action": ctx.decision.action,
                    "policy_layer_applied": ctx.decision.metadata.get(
                        "policy_layer_applied", False
                    ),
                },
            )

    def step_execute_action(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 12: Выполнить действие (LEARN → store + инкрементальная индексация)."""
        if ctx.decision is None:
            return
        if ctx.decision.action == ActionType.LEARN.value:
            try:
                fact = self._strip_learn_markers(ctx.query)
                if fact and hasattr(self._memory, "store"):
                    self._memory.store(fact, importance=0.7)
                    logger.info("[CognitivePipeline] LEARN: stored '%s'", fact[:80])
                    ctx.decision.metadata["stored_fact"] = fact
                    ctx.decision.metadata["store_success"] = True
                    # Инкрементальная векторная индексация
                    self._index_single_text(
                        evidence_id=f"ev_learn_{self._cycle_count_fn()}",
                        text=fact,
                        memory_type="learned_fact",
                        confidence=0.7,
                    )
            except Exception as e:
                logger.warning("[CognitivePipeline] LEARN store error: %s", e)
                ctx.decision.metadata["store_success"] = False
                ctx.decision.metadata["store_error"] = str(e)

    def step_complete_goal(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 13: Завершить или провалить цель в GoalManager."""
        if ctx.goal is None or ctx.trace is None:
            return
        outcome = self._parse_outcome(ctx.trace.outcome)
        if outcome and outcome in FAILURE_OUTCOMES:
            self._goal_manager.fail(ctx.goal.goal_id, ctx.trace.stop_reason)
        else:
            self._goal_manager.complete(ctx.goal.goal_id)

    def step_build_result(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 14: Собрать CognitiveResult из всех компонентов."""
        if ctx.goal is None or ctx.trace is None or ctx.decision is None or ctx.cognitive_context is None:
            ctx.aborted = True
            ctx.abort_reason = "step_build_result: missing required context"
            return

        ctx.elapsed_ms = (time.perf_counter() - ctx.start_time) * 1000

        # TraceChain из ReasoningTrace
        trace_steps = []
        for rs in ctx.trace.steps:
            trace_steps.append(TraceStep(
                step_id=rs.step_id,
                module="cognition.reasoner",
                action=rs.step_type,
                confidence=ctx.trace.final_confidence,
                details={
                    "description": rs.description,
                    "duration_ms": rs.duration_ms,
                    **rs.metadata,
                },
            ))
        trace_steps.append(TraceStep(
            step_id=f"action_{uuid.uuid4().hex[:6]}",
            module="cognition.action_selector",
            action=ctx.decision.action,
            confidence=ctx.decision.confidence,
            details={
                "reasoning": ctx.decision.reasoning,
                **ctx.decision.metadata,
            },
        ))

        trace_chain = TraceChain(
            trace_id=ctx.cognitive_context.trace_id,
            session_id=ctx.cognitive_context.session_id,
            cycle_id=ctx.cognitive_context.cycle_id,
            steps=trace_steps,
            summary=(
                f"query='{ctx.query[:80]}' → {ctx.decision.action} "
                f"(confidence={ctx.decision.confidence:.3f})"
            ),
        )

        memory_refs = [
            TraceRef(ref_type="evidence", ref_id=eid)
            for eid in ctx.trace.evidence_refs
        ]

        # Salience и budget в metadata (Этап H)
        salience_meta: Dict[str, Any] = {}
        if ctx.salience is not None:
            salience_meta = {
                "salience_overall": ctx.salience.overall,
                "salience_action": ctx.salience.action,
                "salience_reason": ctx.salience.reason,
            }

        budget_meta: Dict[str, Any] = {}
        if ctx.budget is not None:
            budget_meta = {
                "budget_policy": ctx.budget.policy,
                "budget_cognition": ctx.budget.cognition,
                "budget_memory": ctx.budget.memory,
                "budget_reason": ctx.budget.reason,
            }

        # LLM metadata (Этап N)
        llm_meta: Dict[str, Any] = {}
        if ctx.llm_enhanced:
            llm_meta = {
                "llm_enhanced": True,
                "llm_provider": ctx.llm_provider_name,
            }

        ctx.result = CognitiveResult(
            action=ctx.decision.action,
            response=ctx.decision.statement,
            confidence=ctx.decision.confidence,
            trace=trace_chain,
            goal=ctx.goal.description,
            trace_id=ctx.cognitive_context.trace_id,
            session_id=ctx.cognitive_context.session_id,
            cycle_id=ctx.cognitive_context.cycle_id,
            memory_refs=memory_refs,
            metadata={
                "goal_type": ctx.goal.goal_type,
                "goal_id": ctx.goal.goal_id,
                "outcome": ctx.trace.outcome,
                "stop_reason": ctx.trace.stop_reason,
                "total_iterations": ctx.trace.total_iterations,
                "reasoning_duration_ms": ctx.trace.total_duration_ms,
                "total_duration_ms": round(ctx.elapsed_ms, 2),
                "hypothesis_count": ctx.trace.hypothesis_count,
                "best_hypothesis_id": ctx.trace.best_hypothesis_id,
                **salience_meta,
                **budget_meta,
                **llm_meta,
            },
        )

    def step_publish_event(self, ctx: CognitivePipelineContext) -> None:
        """Шаг 15: Публикация события через EventBus."""
        if ctx.result is None or ctx.cognitive_context is None or ctx.decision is None or ctx.trace is None:
            return
        if self._event_bus and hasattr(self._event_bus, "publish"):
            try:
                self._event_bus.publish("cognitive_cycle_complete", {
                    "trace_id": ctx.cognitive_context.trace_id,
                    "cycle_id": ctx.cognitive_context.cycle_id,
                    "action": ctx.decision.action,
                    "confidence": ctx.decision.confidence,
                    "outcome": ctx.trace.outcome,
                    "duration_ms": round(ctx.elapsed_ms, 2),
                })
            except Exception as e:
                logger.warning("[CognitivePipeline] event_bus.publish error: %s", e)

    # ------------------------------------------------------------------
    # Вспомогательные методы (Этап H + базовые)
    # ------------------------------------------------------------------

    def _build_resource_state(self, resources: Dict[str, Any]) -> ResourceState:
        """Построить ResourceState из словаря ресурсов ctx.resources."""
        return ResourceState(
            cpu_pct=float(resources.get("cpu_pct", 0.0)),
            ram_pct=float(resources.get("ram_pct", 0.0)),
            ram_used_mb=float(resources.get("ram_used_mb", 0.0)),
            ram_total_mb=float(resources.get("ram_total_mb", 0.0)),
            available_threads=int(resources.get("available_threads", 4)),
            ring2_allowed=bool(resources.get("ring2_allowed", True)),
            soft_blocked=bool(resources.get("soft_blocked", False)),
        )

    def _build_reasoning_state(self, trace: ReasoningTrace) -> ReasoningState:
        """Построить ReasoningState из ReasoningTrace для PolicyLayer."""
        return ReasoningState(
            best_score=trace.final_confidence,
            current_confidence=trace.final_confidence,
            iteration=trace.total_iterations,
            contradiction_flags=[],  # не доступно в ReasoningTrace
        )

    def _detect_goal_type(
        self,
        query: str,
        encoded_percept: Optional[EncodedPercept] = None,
    ) -> str:
        """Эвристика определения типа цели по тексту запроса."""
        q_lower = query.lower().strip()

        learn_markers = ["запомни", "сохрани", "учти", "запиши", "remember", "save"]
        for marker in learn_markers:
            if marker in q_lower:
                return "learn_fact"

        verify_markers = [
            "правда ли", "верно ли", "так ли", "действительно ли",
            "is it true", "is it correct",
        ]
        for marker in verify_markers:
            if marker in q_lower:
                return "verify_claim"

        if "?" in query or q_lower.startswith((
            "что ", "кто ", "где ", "когда ", "как ", "почему ", "зачем ",
            "what ", "who ", "where ", "when ", "how ", "why ",
        )):
            return "answer_question"

        if len(query.split()) > 10 and "?" not in query:
            return "explore_topic"

        return "answer_question"

    def _strip_learn_markers(self, query: str) -> str:
        """Убрать маркеры команды ('запомни:', 'сохрани:' и т.д.)."""
        q = query.strip()
        markers = [
            "запомни:", "запомни ", "сохрани:", "сохрани ",
            "учти:", "учти ", "запиши:", "запиши ",
            "remember:", "remember ", "save:", "save ",
        ]
        for marker in markers:
            if q.lower().startswith(marker):
                return q[len(marker):].strip()
        return q

    def _index_single_text(
        self,
        evidence_id: str,
        text: str,
        memory_type: str = "semantic",
        confidence: float = 0.5,
    ) -> Optional[list]:
        """Кодирование текста и добавление в векторный бэкенд (инкрементально)."""
        if self._vector_backend is None or self._encoder is None:
            return None
        try:
            result = self._encoder.encode(text)
            vector = getattr(result, "vector", None)
            if vector and isinstance(vector, list) and not all(v == 0.0 for v in vector):
                self._vector_backend.add(
                    evidence_id=evidence_id,
                    content=text,
                    vector=list(vector),
                    memory_type=memory_type,
                    confidence=confidence,
                )
                return list(vector)
        except Exception as e:
            logger.debug("[CognitivePipeline] _index_single_text failed: %s", e)
        return None

    @staticmethod
    def _parse_outcome(outcome_str: str) -> Optional[CognitiveOutcome]:
        """Парсинг строки outcome в CognitiveOutcome enum."""
        if not outcome_str:
            return None
        try:
            return CognitiveOutcome(outcome_str)
        except ValueError:
            return None

    def _build_fallback_result(self, ctx: CognitivePipelineContext) -> CognitiveResult:
        """Fallback CognitiveResult при прерывании пайплайна."""
        trace_id = f"trace_{uuid.uuid4().hex[:8]}"
        session_id = ctx.session_id or f"session_{uuid.uuid4().hex[:8]}"
        return CognitiveResult(
            action="refuse",
            response="Произошла внутренняя ошибка когнитивного цикла.",
            confidence=0.0,
            trace=TraceChain(
                trace_id=trace_id,
                session_id=session_id,
                cycle_id="cycle_error",
                steps=[],
                summary=f"pipeline aborted: {ctx.abort_reason}",
            ),
            goal=ctx.query[:200],
            trace_id=trace_id,
            session_id=session_id,
            cycle_id="cycle_error",
            memory_refs=[],
            metadata={
                "aborted": True,
                "abort_reason": ctx.abort_reason,
            },
        )
