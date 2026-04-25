# brain.cognition — Когнитивное ядро

Аналог префронтальной коры: координация всех когнитивных подсистем.

---

## CognitiveCore

Главный orchestrator когнитивного цикла. Делегирует выполнение `CognitivePipeline`.

::: brain.cognition.cognitive_core.CognitiveCore
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - run
        - deny_fact
        - delete_fact
        - remove_from_vector_index
        - goal_manager
        - cycle_count
        - status

---

## CognitivePipeline

Явный 20-шаговый пайплайн когнитивного цикла (P3-10, расширен этапами H/L).

::: brain.cognition.pipeline.CognitivePipeline
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - run
        - step_create_context
        - step_auto_encode
        - step_get_resources
        - step_build_retrieval_query
        - step_create_goal
        - step_index_percept_vector
        - step_reason
        - step_select_action
        - step_execute_action
        - step_complete_goal
        - step_build_result
        - step_publish_event

## CognitivePipelineContext

Контекст, передаваемый между шагами пайплайна.

::: brain.cognition.pipeline.CognitivePipelineContext
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## GoalManager

Управление целями с приоритетной очередью.

::: brain.cognition.goal_manager.GoalManager
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - create_goal
        - complete_goal
        - fail_goal
        - get_active_goals
        - status

::: brain.cognition.goal_manager.Goal
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.goal_manager.GoalStatus
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## Reasoner

Reasoning loop с гипотезами и итерациями.

::: brain.cognition.reasoner.Reasoner
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
      members:
        - __init__
        - reason

::: brain.cognition.reasoner.ReasoningTrace
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.reasoner.ReasoningStep
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## ActionSelector

Выбор действия на основе reasoning trace.

::: brain.cognition.action_selector.ActionSelector
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.action_selector.ActionDecision
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.action_selector.ActionType
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## Planner

Декомпозиция целей на шаги с 5 стратегиями реплана.

::: brain.cognition.planner.Planner
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.planner.ExecutionPlan
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.planner.PlanStep
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## HypothesisEngine

Генерация и оценка гипотез (4 стратегии + бюджет).

::: brain.cognition.hypothesis_engine.HypothesisEngine
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.hypothesis_engine.Hypothesis
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## RetrievalAdapter

Структурированный retrieval: BM25 + векторный поиск.

::: brain.cognition.retrieval_adapter.RetrievalAdapter
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.retrieval_adapter.HybridRetrievalBackend
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.retrieval_adapter.BM25Scorer
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## ContradictionDetector

Обнаружение противоречий в базе знаний.

::: brain.cognition.contradiction_detector.ContradictionDetector
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.contradiction_detector.Contradiction
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## UncertaintyMonitor

Мониторинг тренда уверенности.

::: brain.cognition.uncertainty_monitor.UncertaintyMonitor
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.uncertainty_monitor.UncertaintySnapshot
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

---

## CognitiveContext

Контекст когнитивного цикла: состояние, ограничения, исходы.

::: brain.cognition.context.CognitiveContext
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.context.CognitiveOutcome
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3

::: brain.cognition.context.PolicyConstraints
    options:
      show_source: false
      show_root_heading: true
      heading_level: 3
