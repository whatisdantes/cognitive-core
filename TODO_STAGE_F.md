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

### Шаг 1: [ ] `brain/cognition/context.py` — Контексты и перечисления
- [ ] CognitiveContext dataclass (session_id, cycle_id, trace_id, active_goal, goal_chain)
- [ ] GoalTypeLimits dataclass (step_limit, time_limit_ms, confidence_threshold, stability_window)
- [ ] GOAL_TYPE_LIMITS dict (answer_question, verify_claim, explore_topic, learn_fact)
- [ ] PolicyConstraints dataclass (min_confidence=0.4, max_retries=2, goal_limits)
- [ ] CognitiveOutcome enum (7 значений)
- [ ] CognitiveFailure = CognitiveOutcome (alias)
- [ ] NORMAL_OUTCOMES / FAILURE_OUTCOMES sets
- [ ] EvidencePack dataclass
- [ ] ReasoningState dataclass
- [ ] Все через ContractMixin (to_dict/from_dict)
- [ ] 309 старых тестов не сломаны

### Шаг 2: [ ] `brain/cognition/goal_manager.py` — Цели и управление
- [ ] GoalStatus enum (PENDING, ACTIVE, DONE, FAILED, INTERRUPTED, CANCELLED)
- [ ] Goal dataclass (goal_id, description, goal_type, priority, status, ...)
- [ ] GoalManager class:
  - [ ] push(goal) → None
  - [ ] complete(goal_id) → None
  - [ ] fail(goal_id, reason) → None
  - [ ] peek() → Optional[Goal]
  - [ ] get_active_chain() → List[Goal]
  - [ ] interrupt(urgent_goal) → None
  - [ ] resume_interrupted() → Optional[Goal]
  - [ ] status() → Dict

### Шаг 3: [ ] `brain/cognition/planner.py` — Планирование
- [ ] PlanStep dataclass
- [ ] ExecutionPlan dataclass
- [ ] Planner class:
  - [ ] decompose(goal) → ExecutionPlan (4 шаблона: answer_question, learn_fact, verify_claim, explore_topic)
  - [ ] check_stop_conditions(state, limits, resources) → Optional[CognitiveOutcome]
  - [ ] replan(failed_step, context, failure) → Optional[ExecutionPlan] (retry only)

### Шаг 4: [ ] `brain/cognition/hypothesis_engine.py` — Гипотезы
- [ ] Hypothesis dataclass (с support_score, risk_score)
- [ ] HypothesisEngine class:
  - [ ] generate(query, facts) → List[Hypothesis] (max 3, associative + deductive)
  - [ ] score(hypothesis, memory_manager) → float (support - risk formula)
  - [ ] rank(hypotheses) → List[Hypothesis] (sorted, stable)

### Шаг 5: [ ] `brain/cognition/reasoner.py` — Рассуждатель (Ring 1)
- [ ] ReasoningStep dataclass
- [ ] ReasoningTrace dataclass (+best_hypothesis_id, outcome, stop_reason)
- [ ] Reasoner class:
  - [ ] reason(query, context, resources) → ReasoningTrace
  - [ ] _retrieve_evidence(query) → List[EvidencePack]
  - [ ] _generate_hypotheses(query, facts) → List[Hypothesis]
  - [ ] _score_and_select(hypotheses) → Hypothesis
  - [ ] _build_trace(...) → ReasoningTrace

### Шаг 6: [ ] `brain/cognition/action_selector.py` — Выбор действия
- [ ] ActionType enum (RESPOND_DIRECT, RESPOND_HEDGED, ASK_CLARIFICATION, REFUSE, LEARN)
- [ ] ActionDecision dataclass
- [ ] ActionSelector class:
  - [ ] select(reasoning_trace, context, resources) → ActionDecision
  - [ ] _score_action(action, trace, context, resources) → float

### Шаг 7: [ ] `brain/cognition/cognitive_core.py` — Orchestrator
- [ ] CognitiveCore class:
  - [ ] __init__(memory_manager, text_encoder, event_bus, resource_monitor)
  - [ ] run(query, encoded_percept, resources) → CognitiveResult
  - [ ] _build_retrieval_query(encoded) → str
  - [ ] _create_goal(query, encoded) → Goal
  - [ ] _build_cognitive_result(...) → CognitiveResult
- [ ] Публикация событий через EventBus

### Шаг 8: [ ] `brain/cognition/__init__.py` — Экспорты
- [ ] Экспорт всех публичных классов через __all__

### Шаг 9: [ ] `tests/test_cognition.py` — Unit тесты (~130)
- [ ] TestCognitiveContext (~10)
- [ ] TestCognitiveOutcome (~8)
- [ ] TestGoalTypeLimits (~6)
- [ ] TestGoal (~8)
- [ ] TestGoalManager (~22)
- [ ] TestPlanStep (~8)
- [ ] TestPlanner (~22)
- [ ] TestHypothesis (~6)
- [ ] TestHypothesisEngine (~20)
- [ ] TestReasoningTrace (~6)
- [ ] TestReasoner (~20)
- [ ] TestActionType (~4)
- [ ] TestActionSelector (~16)
- [ ] TestImports (~4)

### Шаг 10: [ ] `tests/test_cognition_integration.py` — Integration smoke tests (~7)
- [ ] Реальный MemoryManager(auto_consolidate=False) + несколько фактов
- [ ] CognitiveCore.run() → CognitiveResult с правильными полями
- [ ] Trace содержит memory_refs
- [ ] ActionDecision.action корректен для разных типов запросов

### Шаг 11: [ ] Финальная проверка и коммит
- [ ] `pytest tests/ -v` — все тесты (~440 total)
- [ ] README.md обновлён (v0.5.0, тесты, дерево, прогресс)
- [ ] pyproject.toml → v0.5.0
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
