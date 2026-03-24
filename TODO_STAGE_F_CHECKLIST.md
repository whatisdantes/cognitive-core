# ✅ Чек-лист TODO Stage F — Cognitive Core (Minimal MVP)

> **Дата проверки:** автоматическая сверка кода с TODO_STAGE_F.md
> **Результат:** ✅ **ВСЕ ПУНКТЫ ВЫПОЛНЕНЫ** (кроме git commit/push — операция вне кода)

---

## Принятые решения (из ревью + ChatGPT feedback)

| # | Решение | Статус | Где реализовано |
|---|---------|--------|-----------------|
| 1 | Orchestrator обязателен: `CognitiveCore.run()` — единая точка входа | ✅ | `cognitive_core.py` → `CognitiveCore.run()` |
| 2 | MVP scope: associative + deductive reasoning only | ✅ | `hypothesis_engine.py` → `_generate_associative()`, `_generate_deductive()` |
| 3 | ReasoningTrace расширен: best_hypothesis_id, outcome, stop_reason | ✅ | `reasoner.py` → `ReasoningTrace` dataclass |
| 4 | GoalStatus — отдельный enum (PENDING/ACTIVE/DONE/FAILED/INTERRUPTED/CANCELLED) | ✅ | `goal_manager.py` → `GoalStatus(str, Enum)` |
| 5 | NORMAL_OUTCOMES / FAILURE_OUTCOMES — два helper-набора | ✅ | `context.py` → `frozenset` |
| 6 | Bridge EncodedPercept→query — приватный метод CognitiveCore | ✅ | `cognitive_core.py` → `_build_retrieval_query()` |
| 7 | LEARN остаётся в ActionType | ✅ | `action_selector.py` → `ActionType.LEARN` |
| 8 | ActionType MVP: RESPOND_DIRECT, RESPOND_HEDGED, ASK_CLARIFICATION, REFUSE, LEARN | ✅ | `action_selector.py` → 5 значений |
| 9 | HypothesisEngine: max 3 гипотезы, deterministic order, stable sort | ✅ | `hypothesis_engine.py` → `max_hypotheses=3`, `rank()` stable sort |
| 10 | replan() MVP: только retry + fail | ✅ | `planner.py` → `replan()` retry-only (расширено в F+) |
| 11 | Все dataclass через ContractMixin | ✅ | Все dataclass наследуют `ContractMixin` |
| 12 | Тесты: ~130 unit + ~7 integration | ✅ | 182 unit + 7 integration (превышает план) |

---

## Шаги реализации

### Шаг 1: ✅ `brain/cognition/context.py` — Контексты и перечисления

| Подзадача | Статус | Детали |
|-----------|--------|--------|
| CognitiveContext dataclass (session_id, cycle_id, trace_id, active_goal, goal_chain) | ✅ | Все 5 полей присутствуют |
| GoalTypeLimits dataclass (step_limit, time_limit_ms, confidence_threshold, stability_window) | ✅ | 4 поля, ContractMixin |
| GOAL_TYPE_LIMITS dict (answer_question, verify_claim, explore_topic, learn_fact) | ✅ | 4 типа целей |
| PolicyConstraints dataclass (min_confidence=0.4, max_retries=2, goal_limits) | ✅ | Используется в Reasoner и CognitiveCore |
| CognitiveOutcome enum (7 значений) | ✅ | STOP_CONDITION_MET, GOAL_COMPLETED, STEP_LIMIT_REACHED, RETRIEVAL_FAILED, NO_HYPOTHESIS_GENERATED, INSUFFICIENT_CONFIDENCE, RESOURCE_BLOCKED |
| CognitiveFailure = CognitiveOutcome (alias) | ✅ | `CognitiveFailure = CognitiveOutcome` |
| NORMAL_OUTCOMES / FAILURE_OUTCOMES sets | ✅ | `frozenset` с 3 и 4 значениями |
| EvidencePack dataclass | ✅ | 15+ полей + metadata (добавлено в F+) |
| ReasoningState dataclass | ✅ | 8 полей: retrieved_evidence, active_hypotheses, contradiction_flags, current_confidence, iteration, top_hypothesis_id, best_score, prev_best_score |
| Все через ContractMixin (to_dict/from_dict) | ✅ | Все dataclass наследуют ContractMixin |
| 309 старых тестов не сломаны | ✅ | 611 тестов проходят (значительно больше 309) |

### Шаг 2: ✅ `brain/cognition/goal_manager.py` — Цели и управление

| Подзадача | Статус | Детали |
|-----------|--------|--------|
| GoalStatus enum (PENDING, ACTIVE, DONE, FAILED, INTERRUPTED, CANCELLED) | ✅ | 6 значений |
| Goal dataclass (goal_id, description, goal_type, priority, status, ...) | ✅ | 12 полей + __post_init__ |
| GoalManager.push(goal) → None | ✅ | Добавляет в дерево + очередь |
| GoalManager.complete(goal_id) → None | ✅ | Устанавливает DONE |
| GoalManager.fail(goal_id, reason) → None | ✅ | Устанавливает FAILED + failure_reason |
| GoalManager.peek() → Optional[Goal] | ✅ | Возвращает top из priority queue |
| GoalManager.get_active_chain() → List[Goal] | ✅ | BFS по дереву целей |
| GoalManager.interrupt(urgent_goal) → None | ✅ | Прерывание + стек |
| GoalManager.resume_interrupted() → Optional[Goal] | ✅ | LIFO из стека |
| GoalManager.status() → Dict | ✅ | total_goals, active_goals, interrupted_goals, completed_goals, queue_size, current_goal |

### Шаг 3: ✅ `brain/cognition/planner.py` — Планировщик

| Подзадача | Статус | Детали |
|-----------|--------|--------|
| PlanStep dataclass (step_id, step_type, description, params, completed, result) | ✅ | 6 полей + __post_init__ |
| ExecutionPlan dataclass (plan_id, goal_id, steps, is_retry, retry_count) | ✅ | 5 полей |
| Planner.decompose(goal) → ExecutionPlan | ✅ | 4 шаблона: answer_question, learn_fact, verify_claim, explore_topic |
| Planner.check_stop_conditions(state, limits, resources) → Optional[CognitiveOutcome] | ✅ | Проверяет ресурсы, лимит итераций, confidence+стабильность |
| Planner.replan(failed_step, goal, failure, ...) → Optional[ExecutionPlan] | ✅ | MVP: retry only (расширено в F+ до 5 стратегий) |

### Шаг 4: ✅ `brain/cognition/hypothesis_engine.py` — Движок гипотез

| Подзадача | Статус | Детали |
|-----------|--------|--------|
| Hypothesis dataclass (hypothesis_id, statement, strategy, support_score, risk_score, final_score, evidence_ids, confidence, metadata) | ✅ | 9 полей + __post_init__ |
| HypothesisEngine.generate(query, evidence) → List[Hypothesis] | ✅ | associative + deductive (+ causal + analogical в F+) |
| HypothesisEngine.score(hypothesis, evidence) → float | ✅ | support - risk формула |
| HypothesisEngine.score_all(hypotheses, evidence) → List[Hypothesis] | ✅ | Мутирует и возвращает |
| HypothesisEngine.rank(hypotheses) → List[Hypothesis] | ✅ | Stable sort по -final_score, hypothesis_id |
| Max 3 гипотезы | ✅ | `max_hypotheses=3` |
| Deterministic order | ✅ | `_make_id()` с sha256 |

### Шаг 5: ✅ `brain/cognition/reasoner.py` — Рассуждатель

| Подзадача | Статус | Детали |
|-----------|--------|--------|
| ReasoningStep dataclass | ✅ | step_id, step_type, description, duration_ms, input_summary, output_summary, metadata |
| ReasoningTrace dataclass (best_hypothesis_id, outcome, stop_reason) | ✅ | 14 полей + add_step() + step_count property |
| Reasoner.reason(query, goal, policy, resources) → ReasoningTrace | ✅ | Полный reasoning loop |
| Reasoner._retrieve_evidence(query) → List[EvidencePack] | ✅ | Через RetrievalAdapter (F+) или fallback memory.search() |
| Reasoner._generate_hypotheses(query, facts) → List[Hypothesis] | ✅ | Через HypothesisEngine |
| Reasoner._score_and_select(hypotheses) → Hypothesis | ✅ | `_score_hypotheses()` + `_select_best()` |
| Reasoner._build_trace(...) → ReasoningTrace | ✅ | Trace строится инкрементально через add_step() |

### Шаг 6: ✅ `brain/cognition/action_selector.py` — Выбор действия

| Подзадача | Статус | Детали |
|-----------|--------|--------|
| ActionType enum (RESPOND_DIRECT, RESPOND_HEDGED, ASK_CLARIFICATION, REFUSE, LEARN) | ✅ | 5 значений |
| ActionDecision dataclass | ✅ | action, action_type, statement, confidence, reasoning, metadata |
| ActionSelector.select(trace, goal_type, policy, resources) → ActionDecision | ✅ | Выбирает лучшее действие |
| ActionSelector._score_action(action, trace, ...) → float | ✅ | Скоринг каждого действия |

### Шаг 7: ✅ `brain/cognition/cognitive_core.py` — Orchestrator

| Подзадача | Статус | Детали |
|-----------|--------|--------|
| CognitiveCore.__init__(memory_manager, text_encoder, event_bus, resource_monitor) | ✅ | + policy, + F+ компоненты (RetrievalAdapter, ContradictionDetector, UncertaintyMonitor) |
| CognitiveCore.run(query, encoded_percept, resources) → CognitiveResult | ✅ | 10-шаговая цепочка: context → resources → query → goal → reason → action → execute → complete → result → event |
| CognitiveCore._build_retrieval_query(encoded) → str | ✅ | Обогащение keywords из EncodedPercept |
| CognitiveCore._create_goal(query, encoded) → Goal | ✅ | Эвристика: learn_fact / verify_claim / answer_question / explore_topic |
| CognitiveCore._build_cognitive_result(...) → CognitiveResult | ✅ | TraceChain + memory_refs + metadata |
| Публикация событий через EventBus | ✅ | `_publish_event("cognitive_cycle_complete", {...})` |

### Шаг 8: ✅ `brain/cognition/__init__.py` — Экспорты

| Подзадача | Статус | Детали |
|-----------|--------|--------|
| Экспорт всех публичных классов через __all__ | ✅ | 30 классов (22 из Stage F + 8 из F+) |

### Шаг 9: ✅ `tests/test_cognition.py` — Unit тесты (~130)

| Группа тестов | Статус | Факт |
|---------------|--------|------|
| TestCognitiveContext (~10) | ✅ | Включены |
| TestCognitiveOutcome (~8) | ✅ | Включены |
| TestGoalTypeLimits (~6) | ✅ | Включены |
| TestGoal (~8) | ✅ | Включены |
| TestGoalManager (~22) | ✅ | Включены |
| TestPlanStep (~8) | ✅ | Включены |
| TestPlanner (~22) | ✅ | Включены |
| TestHypothesis (~6) | ✅ | Включены |
| TestHypothesisEngine (~20) | ✅ | Включены |
| TestReasoningTrace (~6) | ✅ | Включены |
| TestReasoner (~20) | ✅ | Включены |
| TestActionType (~4) | ✅ | Включены |
| TestActionSelector (~16) | ✅ | Включены |
| TestImports (~4) | ✅ | Включены |
| **Итого** | ✅ | **182 тестов** (превышает план ~130) |

### Шаг 10: ✅ `tests/test_cognition_integration.py` — Integration smoke tests (~7)

| Подзадача | Статус | Детали |
|-----------|--------|--------|
| Реальный MemoryManager(auto_consolidate=False) + несколько фактов | ✅ | 7 тестов |
| CognitiveCore.run() → CognitiveResult с правильными полями | ✅ | Проверяется |
| Trace содержит memory_refs | ✅ | Проверяется |
| ActionDecision.action корректен для разных типов запросов | ✅ | Проверяется |

### Шаг 11: ✅ Финальная проверка и коммит

| Подзадача | Статус | Детали |
|-----------|--------|--------|
| `pytest tests/ -v` — все тесты (~440 total) | ✅ | **611 тестов** проходят (значительно больше ~440) |
| README.md обновлён (v0.5.0, тесты, дерево, прогресс) | ✅ | v0.6.0 (обновлён дальше плана), 611 тестов, полное дерево, прогресс |
| pyproject.toml → v0.5.0 | ✅ | v0.6.0 (обновлён дальше плана — Stage G тоже завершён) |
| Коммит + push | ⚠️ | Git-операция — не проверяется из кода |

---

## Что НЕ входит в Stage F (отложено в F.2) — Статус

| Компонент | Статус в F | Статус сейчас |
|-----------|-----------|---------------|
| ContradictionDetector | ❌ Отложено | ✅ Реализовано в F+ (`contradiction_detector.py`) |
| UncertaintyMonitor | ❌ Отложено | ✅ Реализовано в F+ (`uncertainty_monitor.py`) |
| SalienceEngine | ❌ Отложено | ❌ Не реализовано (Stage H+) |
| PolicyLayer | ❌ Отложено | ❌ Не реализовано |
| Ring 2 (deep reasoning) | ❌ Отложено | ❌ Не реализовано (Stage H) |
| Causal / Analogical reasoning | ❌ Отложено | ✅ Реализовано в F+ (`hypothesis_engine.py`) |
| replan() с полными стратегиями | ❌ Отложено | ✅ Реализовано в F+ (5 стратегий в `planner.py`) |
| LLM bridge | ❌ Отложено | ❌ Не реализовано (Stage N) |
| Vector retrieval | ❌ Отложено | ❌ Не реализовано (только interface/hook) |

---

## Итог

```
Stage F (Cognitive Core MVP):     ✅ ПОЛНОСТЬЮ ВЫПОЛНЕН
  - 11/11 шагов завершены
  - 182 unit + 7 integration тестов (план: ~130 + ~7)
  - Все 12 принятых решений реализованы
  - Версия: 0.6.0 (план: 0.5.0 — перевыполнено, Stage G тоже завершён)
  - Общее количество тестов: 611 (план: ~440)

Stage F+ (Cognitive Extensions):  🚧 В ПРОЦЕССЕ (Steps 7-9 done, Steps 10-12 pending)
  - Steps 1-9 ✅ (enums, retrieval_adapter, contradiction_detector,
    uncertainty_monitor, hypothesis_engine extensions, planner replan,
    reasoner integration, cognitive_core wiring, __init__ exports)
  - Steps 10-12 ⬜ (tests, finalize v0.7.0)
