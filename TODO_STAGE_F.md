# TODO Stage F — Cognitive Core (Minimal MVP)

> **Версия:** v1 (2026-03-24)
> **Цель:** `brain/cognition/` — минимальный рабочий reasoning loop
> **Оценка:** ~16 часов реализации + тесты

---

## Принятые решения (из ревью + ChatGPT feedback)

1. **Orchestrator обязателен:** `CognitiveCore.run()` — единая точка входа
2. **MVP scope:** associative + deductive reasoning only (causal → F.2)
3. **ReasoningTrace расширен:** best_hypothesis_id, outcome, stop_reason
4. **GoalStatus — отдельный enum** (не TaskStatus): PENDING/ACTIVE/DONE/FAILED/INTERRUPTED/CANCELLED
5. **NORMAL_OUTCOMES / FAILURE_OUTCOMES** — два helper-набора
6. **Bridge EncodedPercept→query** — приватный метод CognitiveCore, не отдельный файл
7. **LEARN остаётся** в ActionType (explicit memory action ≠ Learning Loop)
8. **ActionType MVP:** RESPOND_DIRECT, RESPOND_HEDGED, ASK_CLARIFICATION, REFUSE, LEARN
9. **HypothesisEngine:** max 3 гипотезы, deterministic order, stable sort
10. **replan() MVP:** только retry + fail (без умного replanning)
11. **Все dataclass через ContractMixin** (to_dict/from_dict)
12. **Тесты:** ~130 unit (mocked) + ~7 integration smoke tests (отдельный файл)

---

## Шаги реализации

### Шаг 1: [x] `brain/cognition/context.py` — Контексты и перечисления
- [x] CognitiveContext dataclass (session_id, cycle_id, trace_id, active_goal, goal_chain)
- [x] GoalTypeLimits dataclass (step_limit, time_limit_ms, confidence_threshold, stability_window)
- [x] GOAL_TYPE_LIMITS dict (answer_question, verify_claim, explore_topic, learn_fact)
- [x] PolicyConstraints dataclass (min_confidence=0.4, max_retries=2, goal_limits)
- [x] CognitiveOutcome enum (7 значений)
- [x] CognitiveFailure = CognitiveOutcome (alias)
- [x] NORMAL_OUTCOMES / FAILURE_OUTCOMES sets
- [x] EvidencePack dataclass
- [x] ReasoningState dataclass
- [x] Все через ContractMixin (to_dict/from_dict)
- [x] 309 старых тестов не сломаны

### Шаг 2: [x] `brain/cognition/goal_manager.py` — Цели и управление
- [x] GoalStatus enum (PENDING, ACTIVE, DONE, FAILED, INTERRUPTED, CANCELLED)
- [x] Goal dataclass (goal_id, description, goal_type, priority, status, ...)
- [x] GoalManager class:
  - [x] push(goal) → None
  - [x] complete(goal_id) → None
  - [x] fail(goal_id, reason) → None
  - [x] peek() → Optional[Goal]
  - [x] get_active_chain() → List[Goal]
  - [x] interrupt(urgent_goal) → None
  - [x] resume_interrupted() → Optional[Goal]
  - [x] status() → Dict

### Шаг 3: [x] `brain/cognition/planner.py` — Планирование
- [x] PlanStep dataclass
- [x] ExecutionPlan dataclass
- [x] Planner class:
  - [x] decompose(goal) → ExecutionPlan (4 шаблона: answer_question, learn_fact, verify_claim, explore_topic)
  - [x] check_stop_conditions(state, limits, resources) → Optional[CognitiveOutcome]
  - [x] replan(failed_step, context, failure) → Optional[ExecutionPlan] (retry only)

### Шаг 4: [x] `brain/cognition/hypothesis_engine.py` — Гипотезы
- [x] Hypothesis dataclass (с support_score, risk_score)
- [x] HypothesisEngine class:
  - [x] generate(query, facts) → List[Hypothesis] (max 3, associative + deductive)
  - [x] score(hypothesis, memory_manager) → float (support - risk formula)
  - [x] rank(hypotheses) → List[Hypothesis] (sorted, stable)

### Шаг 5: [x] `brain/cognition/reasoner.py` — Рассуждатель (Ring 1)
- [x] ReasoningStep dataclass
- [x] ReasoningTrace dataclass (+best_hypothesis_id, outcome, stop_reason)
- [x] Reasoner class:
  - [x] reason(query, context, resources) → ReasoningTrace
  - [x] _retrieve_evidence(query) → List[EvidencePack]
  - [x] _generate_hypotheses(query, facts) → List[Hypothesis]
  - [x] _score_and_select(hypotheses) → Hypothesis
  - [x] _build_trace(...) → ReasoningTrace

### Шаг 6: [x] `brain/cognition/action_selector.py` — Выбор действия
- [x] ActionType enum (RESPOND_DIRECT, RESPOND_HEDGED, ASK_CLARIFICATION, REFUSE, LEARN)
- [x] ActionDecision dataclass
- [x] ActionSelector class:
  - [x] select(reasoning_trace, context, resources) → ActionDecision
  - [x] _score_action(action, trace, context, resources) → float

### Шаг 7: [x] `brain/cognition/cognitive_core.py` — Orchestrator
- [x] CognitiveCore class:
  - [x] __init__(memory_manager, text_encoder, event_bus, resource_monitor)
  - [x] run(query, encoded_percept, resources) → CognitiveResult
  - [x] _build_retrieval_query(encoded) → str
  - [x] _create_goal(query, encoded) → Goal
  - [x] _build_cognitive_result(...) → CognitiveResult
- [x] Публикация событий через EventBus

### Шаг 8: [x] `brain/cognition/__init__.py` — Экспорты
- [x] Экспорт всех публичных классов через __all__

### Шаг 9: [x] `tests/test_cognition.py` — Unit тесты (~130)
- [x] TestCognitiveContext (~10)
- [x] TestCognitiveOutcome (~8)
- [x] TestGoalTypeLimits (~6)
- [x] TestGoal (~8)
- [x] TestGoalManager (~22)
- [x] TestPlanStep (~8)
- [x] TestPlanner (~22)
- [x] TestHypothesis (~6)
- [x] TestHypothesisEngine (~20)
- [x] TestReasoningTrace (~6)
- [x] TestReasoner (~20)
- [x] TestActionType (~4)
- [x] TestActionSelector (~16)
- [x] TestImports (~4)

### Шаг 10: [x] `tests/test_cognition_integration.py` — Integration smoke tests (~7)
- [x] Реальный MemoryManager(auto_consolidate=False) + несколько фактов
- [x] CognitiveCore.run() → CognitiveResult с правильными полями
- [x] Trace содержит memory_refs
- [x] ActionDecision.action корректен для разных типов запросов

### Шаг 11: [x] Финальная проверка и коммит
- [x] `pytest tests/ -v` — все тесты (611 total, план ~440)
- [x] README.md обновлён (v0.6.0, тесты, дерево, прогресс)
- [x] pyproject.toml → v0.6.0
- [ ] Коммит + push

---

## Что НЕ входит в Stage F (отложено в F.2)

- ContradictionDetector
- UncertaintyMonitor
- SalienceEngine
- PolicyLayer
- Ring 2 (deep reasoning)
- Causal / Analogical reasoning
- replan() с полными стратегиями
- LLM bridge
- Vector retrieval
