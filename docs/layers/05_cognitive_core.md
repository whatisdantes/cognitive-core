# 🧠 Слой 5: Cognitive Core (Префронтальная кора)
## Подробное описание архитектуры и работы

> **Статус: ✅ Реализовано (Этап F + F+ + P0/P1)**  
> CognitiveCore orchestrator, GoalManager, Planner, HypothesisEngine, Reasoner,  
> ContradictionDetector, UncertaintyMonitor, ActionSelector — 190+7 тестов (unit+integration).  
> BM25 + Vector + Hybrid retrieval — 60 тестов (`test_vector_retrieval.py`).  
> SalienceEngine и PolicyLayer — запланированы (Этап H).

---

## Что такое Префронтальная кора в биологии

**Префронтальная кора (PFC)** — самая «человеческая» часть мозга:
- **Планирование** — постановка целей и декомпозиция на шаги
- **Рабочая память** — удержание контекста во время рассуждения
- **Принятие решений** — выбор между конкурирующими вариантами
- **Торможение** — подавление импульсивных реакций
- **Самоконтроль** — мониторинг собственных мыслей и ошибок
- **Абстрактное мышление** — работа с понятиями, не привязанными к конкретике

Это «исполнительный директор» мозга — он не воспринимает и не запоминает, он **управляет**.

---

## Роль в искусственном мозге

```
FusedPercept + MemorySearchResult
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    COGNITIVE CORE                           │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                   Planner                            │   │
│  │  GoalManager → декомпозиция → план шагов             │   │
│  │  "ответить на вопрос" → [retrieve, reason, respond]  │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │                   Reasoner                           │   │
│  │  causal / associative / analogical / deductive       │   │
│  │  строит цепочку рассуждений с trace                  │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │            ContradictionDetector                     │   │
│  │  два факта противоречат? → флаг + снизить confidence │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │            UncertaintyMonitor                        │   │
│  │  confidence < threshold → запросить уточнение        │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │            SalienceEngine (Миндалина)                │   │
│  │  срочность / угроза / новизна → приоритет            │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │            ActionSelector (Базальные ганглии)        │   │
│  │  выбор финального действия из конкурирующих вариантов│   │
│  └──────────────────────┬───────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
                  CognitiveResult
    {action, reasoning_trace, confidence, next_goals}
                          │
                          ▼
               Learning Loop (Слой 6)
               Output Layer (Слой 7)
```

---

## Центральные структуры данных

> Все компоненты Cognitive Core получают эти объекты вместо разрозненных параметров.  
> Разделение на 4 фокусированных структуры предотвращает "giant object" антипаттерн.

### `CognitiveContext` — состояние текущего цикла

```python
@dataclass
class CognitiveContext:
    """Состояние текущего цикла мышления. Передаётся всем компонентам."""
    session_id: str           # ID сессии (постоянный)
    cycle_id: str             # ID цикла (новый каждый тик)
    trace_id: str             # ID трассировки (для observability)
    active_goal: Optional[Goal]
    goal_chain: List[Goal]    # цепочка от корневой до активной цели
```

### `ResourceState` — ресурсное состояние

```python
@dataclass
class ResourceState:
    """
    Текущее состояние CPU/RAM. Обновляется ResourceMonitor каждый тик.

    Пороги с гистерезисом (предотвращают флапание при нагрузке на границе):
      Мягкий блок:  soft_blocked=True  при cpu_pct >= 70%, снимается при cpu_pct <= 60%
      Жёсткий блок: ring2_allowed=False при cpu_pct >= 85%, снимается при cpu_pct <= 75%
    """
    cpu_pct: float            # загрузка CPU 0.0–100.0
    ram_pct: float            # загрузка RAM 0.0–100.0
    ring2_allowed: bool       # False если cpu_pct >= 85 или ram_pct >= 85
                              # (снимается только при cpu < 75% и ram < 75%)
    soft_blocked: bool        # True если cpu_pct >= 70% (мягкий режим)
                              # (снимается при cpu < 60%)
    available_threads: int    # свободные потоки для Ring 2
```

### `GoalTypeLimits` + `PolicyConstraints` — ограничения поведения

```python
@dataclass
class GoalTypeLimits:
    """Stop conditions для конкретного типа цели."""
    step_limit: int           # максимум шагов reasoning loop
    time_limit_ms: float      # максимум времени на цикл
    confidence_threshold: float  # порог уверенности для остановки
    stability_window: int     # кол-во итераций без изменений → стоп

# Стартовые значения (подлежат эмпирической калибровке):
GOAL_TYPE_LIMITS: Dict[str, GoalTypeLimits] = {
    "answer_question": GoalTypeLimits(step_limit=3,  time_limit_ms=200, confidence_threshold=0.75, stability_window=2),
    "verify_claim":    GoalTypeLimits(step_limit=7,  time_limit_ms=500, confidence_threshold=0.80, stability_window=2),
    "explore_topic":   GoalTypeLimits(step_limit=10, time_limit_ms=800, confidence_threshold=0.70, stability_window=3),
    "learn_fact":      GoalTypeLimits(step_limit=3,  time_limit_ms=150, confidence_threshold=0.70, stability_window=1),
}

@dataclass
class PolicyConstraints:
    """Ограничения поведения для текущего цикла."""
    min_confidence: float = 0.4
    max_retries: int = 2
    goal_limits: GoalTypeLimits = field(default_factory=lambda: GOAL_TYPE_LIMITS["answer_question"])
```

### `ReasoningState` — состояние цикла рассуждения

```python
@dataclass
class ReasoningState:
    """Изменяемое состояние reasoning loop. Обновляется на каждой итерации."""
    retrieved_evidence: List[EvidencePack]
    active_hypotheses: List[Hypothesis]
    contradiction_flags: List[str]        # ID конфликтующих пар
    current_confidence: float             # лучший score среди гипотез
    iteration: int                        # номер итерации (для stop conditions)
    # Удобные поля для stop conditions и trace:
    top_hypothesis_id: Optional[str]      # ID гипотезы с лучшим score
    best_score: float                     # score лучшей гипотезы
    prev_best_score: float                # score на предыдущей итерации (для stability check)
```

### `EvidencePack` — структурированный объект доказательства

> Reasoning работает не с "голыми фактами", а с объектами доказательства.  
> Это укрепляет retrieval, hypothesis generation, trace и contradiction analysis.

```python
@dataclass
class EvidencePack:
    evidence_id: str
    content: str
    memory_type: str              # "working" | "semantic" | "episodic"
    concept_refs: List[str]       # концепты, упомянутые в доказательстве
    source_refs: List[str]        # источники
    confidence: float             # уверенность в факте 0.0–1.0
    trust: float                  # доверие к источнику 0.0–1.0
    timestamp: Optional[str]      # ISO timestamp создания факта
    modality: str                 # "text" | "image" | "audio"
    contradiction_flags: List[str]  # ID конфликтующих фактов

    # Поля для scoring и retrieval:
    relevance_score: float        # семантическая близость к запросу 0.0–1.0
    freshness_score: float        # эвристика свежести (см. примечание ниже)
    retrieval_stage: int          # 1, 2 или 3 (из какой стадии retrieve_staged)
    supports_hypotheses: List[str]  # ID гипотез, которые это доказательство поддерживает
```

> ⚠️ **Примечание о `freshness_score`:**  
> Простая формула `1.0 / max(1, age_days)` — рабочая эвристика, но грубая.  
> Старые, но верные факты (например, математические теоремы) не должны обесцениваться.  
> Конкретная функция свежести **зависит от типа факта и источника** и подлежит калибровке:
> - Научные факты: медленное затухание (×0.999 в день)
> - Новостные данные: быстрое затухание (×0.95 в день)
> - Пользовательский ввод: без затухания (freshness = 1.0 всегда)

### `CognitiveOutcome` — коды завершения reasoning loop

> **Переименовано из `CognitiveFailure`:** enum содержит как коды ошибок, так и нормальные
> коды завершения (`STOP_CONDITION_MET`, `GOAL_COMPLETED`). Называть их все "Failure" семантически
> некорректно. Используется единый enum с явным разделением через комментарии.

```python
class CognitiveOutcome(Enum):
    """
    Коды завершения reasoning loop.
    Используются в check_stop_conditions(), replan() и логах.

    --- Нормальные завершения (не ошибки) ---
    """
    STOP_CONDITION_MET       = "stop_condition_met"       # confidence достигнут / стабильность
    GOAL_COMPLETED           = "goal_completed"           # цель выполнена успешно
    STEP_LIMIT_REACHED       = "step_limit_reached"       # исчерпан step_limit цели (нормально)

    # --- Ошибки и сбои ---
    RETRIEVAL_FAILED         = "retrieval_failed"         # память не вернула результатов
    NO_HYPOTHESIS_GENERATED  = "no_hypothesis_generated"  # шаблоны не дали гипотез
    CONFLICTING_EVIDENCE     = "conflicting_evidence"     # противоречия не разрешены
    INSUFFICIENT_CONFIDENCE  = "insufficient_confidence"  # confidence < min_threshold
    RESOURCE_BLOCKED         = "resource_blocked"         # CPU/RAM > 85%
    OUT_OF_SCOPE             = "out_of_scope"             # вне области знаний
    REPLAN_LIMIT_REACHED     = "replan_limit_reached"     # превышен max_retries replan()

# Обратная совместимость (псевдоним для переходного периода):
CognitiveFailure = CognitiveOutcome
```

> **Паттерн проверки:**
> ```python
> NORMAL_OUTCOMES = {
>     CognitiveOutcome.STOP_CONDITION_MET,
>     CognitiveOutcome.GOAL_COMPLETED,
>     CognitiveOutcome.STEP_LIMIT_REACHED,
> }
> is_normal = outcome in NORMAL_OUTCOMES  # True → завершение; False → replan()
> ```
> `STEP_LIMIT_REACHED` ≠ `REPLAN_LIMIT_REACHED`:
> - `STEP_LIMIT_REACHED` — reasoning loop законно исчерпал шаги (нормально)
> - `REPLAN_LIMIT_REACHED` — `replan()` вызывался слишком много раз (ошибка)

---

## Компонент 1: `Planner` — Планировщик

**Файл:** `brain/cognition/planner.py`  
**Аналог:** Дорсолатеральная префронтальная кора — планирование и цели

### Принцип работы

```
Входящий стимул (вопрос, задача, событие)
    │
    ▼
GoalManager.push(новая_цель)
    │
    ▼
Planner.decompose(цель) → список подзадач
    │
    ▼
ExecutionPlan = [шаг_1, шаг_2, ..., шаг_N]
    │
    ▼
Выполнение шагов по очереди (или параллельно)
    │
    ▼
GoalManager.complete() при завершении
```

### Структура `Goal`

```python
@dataclass
class Goal:
    goal_id: str          # "goal_a1b2c3"
    description: str      # "ответить на вопрос о нейронах"
    goal_type: str        # "answer_question" | "learn_fact" | "verify_claim"
                          # "explore_topic" | "plan"
                          # ⚠️ Используются полные имена — они же ключи в GOAL_TYPE_LIMITS
    priority: float       # 0.0–1.0 (выше → важнее)
    deadline: Optional[float]  # unix timestamp или None
    parent_goal_id: Optional[str]  # ID родительской цели; None для корневой цели
    sub_goals: List[str]  # ID дочерних целей
    status: str           # "pending" | "active" | "done" | "failed" | "cancelled"
    created_at: str       # ISO timestamp
    context: Dict         # дополнительный контекст
    trace_id: str         # для трассировки
```

### Структура `PlanStep`

```python
@dataclass
class PlanStep:
    step_id: str          # "step_001"
    action: str           # "retrieve_memory" | "reason" | "ask_user" | "respond"
    description: str      # "Найти факты о нейронах в памяти"
    params: Dict          # {"query": "нейрон", "top_n": 5}
    depends_on: List[str] # ID шагов, которые должны выполниться раньше
    status: str           # "pending" | "running" | "done" | "failed"
    result: Any           # результат выполнения шага
    duration_ms: float    # время выполнения
    # Retry и стоимость:
    retry_count: int = 0          # сколько раз уже повторяли
    max_retries: int = 2          # максимум повторов
    step_cost: float = 0.0        # ожидаемые CPU×ms (для cost model)
    failure_reason: Optional[str] = None  # причина неудачи (CognitiveFailure)
```

### Типы целей и их декомпозиция

```
"answer_question" (ответить на вопрос):
    Шаг 1: retrieve_memory(query)
    Шаг 2: check_confidence(results)
    Шаг 3: если confidence < 0.5 → ask_clarification
            иначе → reason(results)
    Шаг 4: build_response(reasoning)
    Шаг 5: store_episode(interaction)

"learn_fact" (запомнить факт):
    Шаг 1: parse_fact(content)
    Шаг 2: check_contradiction(fact)
    Шаг 3: если противоречие → resolve_contradiction
    Шаг 4: store_fact(semantic_memory)
    Шаг 5: update_source_trust(source)

"verify_claim" (проверить утверждение):
    Шаг 1: retrieve_related_facts(claim)
    Шаг 2: cross_modal_check(claim, facts)
    Шаг 3: detect_contradictions(facts)
    Шаг 4: calculate_confidence(evidence)
    Шаг 5: return_verdict(confidence, trace)

"explore_topic" (исследовать тему):
    Шаг 1: get_concept_chain(topic)
    Шаг 2: find_knowledge_gaps(chain)
    Шаг 3: для каждого пробела → create_sub_goal("learn_fact")
    Шаг 4: synthesize_knowledge(results)
```

### `GoalManager` — менеджер целей

> **Важно:** это не чистый стек. Структура данных — **дерево целей с приоритетной очередью активных узлов**.  
> Название `GoalStack` было неточным — здесь есть приоритеты, иерархия и прерывания одновременно.

```python
class GoalManager:
    """
    Дерево целей с приоритетной очередью активных узлов.

    Внутренняя структура:
      goal_tree:         Dict[str, Goal]        — все цели (id → Goal)
      active_queue:      PriorityQueue[Goal]     — активные цели по приоритету
      interrupted_stack: List[Goal]              — прерванные цели (LIFO)
      completed:         List[str]               — завершённые ID
    """

    def push(self, goal: Goal) -> None:
        """Добавить цель в дерево и активную очередь (с учётом приоритета)."""

    def complete(self, goal_id: str) -> None:
        """Пометить цель как выполненную, убрать из active_queue."""

    def fail(self, goal_id: str, reason: str) -> None:
        """Пометить цель как неудачную → передать в replan()."""

    def peek(self) -> Optional[Goal]:
        """Вернуть текущую активную цель (с наивысшим приоритетом)."""

    def interrupt(self, urgent_goal: Goal) -> None:
        """Прервать текущую цель: переместить в interrupted_stack, активировать срочную."""

    def resume_interrupted(self) -> Optional[Goal]:
        """Возобновить последнюю прерванную цель (LIFO)."""

    def get_active_chain(self) -> List[Goal]:
        """Вернуть цепочку от корневой до текущей активной цели."""
```

### `replan()` — перепланирование при неудаче

```python
def replan(self, failed_step: PlanStep, context: CognitiveContext,
           failure: CognitiveFailure) -> Optional[ExecutionPlan]:
    """
    Перепланировать после неудачи шага.
    Возвращает новый план или None если replan невозможен.

    Стратегии (в порядке приоритета):
    """
    if failed_step.retry_count < failed_step.max_retries:
        # Стратегия 1: RETRY — повторить тот же шаг
        failed_step.retry_count += 1
        return ExecutionPlan(steps=[failed_step])

    if failure == CognitiveFailure.RETRIEVAL_FAILED:
        # Стратегия 2: ALTERNATIVE — попробовать другой источник памяти
        return _build_alternative_retrieval_plan(failed_step, context)

    if failure == CognitiveFailure.INSUFFICIENT_CONFIDENCE:
        # Стратегия 3: GATHER — добавить шаг сбора дополнительных данных
        return _build_gather_evidence_plan(context)

    if failure == CognitiveFailure.CONFLICTING_EVIDENCE:
        # Стратегия 4: RESOLVE — добавить шаг разрешения противоречий
        return _build_resolve_contradiction_plan(context)

    # Стратегия 5: ESCALATE — передать в родительскую цель или отказаться
    # replan() — метод класса Planner; self.goal_manager — зависимость через __init__
    self.goal_manager.fail(context.active_goal.goal_id, reason=failure.value)
    return None
```

---

## Компонент 2: `Reasoner` — Рассуждатель

**Файл:** `brain/cognition/reasoner.py`  
**Аналог:** Ассоциативная + префронтальная кора — построение умозаключений

### Типы рассуждений

#### 2.1 Ассоциативное рассуждение (Associative)
```
Вопрос: "Что такое нейрон?"
    │
    ▼
retrieve("нейрон") → SemanticNode("нейрон", "клетка нервной системы")
    │
    ▼
get_related("нейрон") → ["синапс", "аксон", "дендрит", "мозг"]
    │
    ▼
get_concept_chain("нейрон", depth=3) → ["нейрон", "клетка", "организм"]
    │
    ▼
Ответ: "Нейрон — это клетка нервной системы. Связан с: синапс, аксон, дендрит."
Trace: [нейрон → клетка → нервная система → организм]
```

#### 2.2 Причинно-следственное рассуждение (Causal)
```
Вопрос: "Почему нейроны важны?"
    │
    ▼
Найти факты с тегом "нейрон" + паттерн "потому что" / "поэтому" / "следовательно"
    │
    ▼
Построить граф причинности:
  нейрон → передаёт сигналы → мозг работает → мышление возможно
    │
    ▼
Ответ: "Нейроны важны, потому что передают сигналы, что обеспечивает работу мозга."
Trace: [нейрон --causes--> передача_сигналов --enables--> мышление]
```

#### 2.3 Аналогическое рассуждение (Analogical)
```
Вопрос: "Нейрон похож на что?"
    │
    ▼
Найти структурно похожие понятия:
  нейрон: принимает вход → обрабатывает → даёт выход
  транзистор: принимает вход → обрабатывает → даёт выход
    │
    ▼
Аналогия: "Нейрон похож на транзистор — оба принимают сигнал и передают его дальше."
Trace: [нейрон ≈ транзистор (структурная аналогия)]
```

> ⚠️ **Ограничение аналогического рассуждения:**  
> Аналогия — это **гипотеза**, а не вывод. Аналогическая гипотеза не должна получать высокий
> `score` без подтверждающих `EvidencePack`. В `score_hypothesis()` аналогии типично имеют
> низкий `evidence_coverage` (нет прямых фактов "за") и должны конкурировать с ассоциативными
> и дедуктивными гипотезами. Без дополнительных доказательств аналогия остаётся в статусе
> `"uncertain"`, а не `"accepted"`.

#### 2.4 Дедуктивное рассуждение (Deductive)
```
Факт 1: "Все нейроны — клетки"
Факт 2: "Все клетки содержат ДНК"
    │
    ▼
Вывод: "Нейроны содержат ДНК"
Confidence: min(confidence_1, confidence_2) = min(0.95, 0.90) = 0.90
Trace: [нейрон is_a клетка, клетка has ДНК → нейрон has ДНК]
```

### Структура `ReasoningTrace`

```python
@dataclass
class ReasoningTrace:
    trace_id: str              # "trace_a1b2c3"
    reasoning_type: str        # "associative" | "causal" | "analogical" | "deductive"
    query: str                 # исходный вопрос/задача
    
    # Использованные источники
    memory_refs: List[str]     # ["semantic:нейрон", "episodic:ep_001"]
    source_refs: List[str]     # ["docs/нейрон.pdf#p1"]
    
    # Цепочка рассуждений
    steps: List[ReasoningStep] # пошаговый ход мысли
    
    # Результат
    conclusion: str            # итоговый вывод
    confidence: float          # уверенность в выводе 0.0–1.0
    
    # Метаданные
    duration_ms: float         # время рассуждения
    created_at: str            # timestamp
```

```python
@dataclass
class ReasoningStep:
    step_num: int              # 1, 2, 3, ...
    operation: str             # "retrieve", "infer", "compare", "conclude"
    input_refs: List[str]      # что использовалось на этом шаге
    output: str                # что получилось
    confidence: float          # уверенность на этом шаге
```

---

## Компонент 3: `ContradictionDetector` — Детектор противоречий

**Файл:** `brain/cognition/contradiction_detector.py`  
**Аналог:** Передняя поясная кора — мониторинг конфликтов

### Типы структурных конфликтов

> **Важно:** детектор работает не через семантическое сходство (`sim < 0.2`), а через **структурный анализ** пар фактов.  
> Семантическое сходство — ненадёжный прокси: два факта могут быть семантически близки, но не противоречить, и наоборот.

```python
class ConflictType(Enum):
    """5 структурных типов конфликтов между фактами."""

    OPPOSITE_POLARITY    = "opposite_polarity"
    # Прямое отрицание: "нейрон передаёт сигналы" vs "нейрон НЕ передаёт сигналы"
    # Детекция: наличие отрицания (не, нет, never, not) при том же субъекте и предикате

    CONFLICTING_VALUE    = "conflicting_value"
    # Разные значения одного атрибута: "скорость = 100 км/ч" vs "скорость = 200 км/ч"
    # Детекция: одинаковый атрибут, разные числовые/категориальные значения

    SOURCE_CONFLICT      = "source_conflict"
    # Разные источники дают несовместимые утверждения об одном факте
    # Детекция: source_trust разница > 0.3 + несовместимые значения

    RELATION_CONFLICT    = "relation_conflict"
    # Несовместимые отношения: "A is_a B" vs "A is_not_a B"
    # Детекция: одинаковые субъект+объект, противоположные типы отношений

    STALE_EVIDENCE       = "stale_evidence"
    # Устаревание, а не противоречие: "X = 5 (2020)" vs "X = 7 (2024)"
    # Это НЕ конфликт — это обновление. Старый факт помечается как OUTDATED.
    # Детекция: одинаковый атрибут + разные timestamps → победитель: более свежий
```

> ⚠️ **Примечание о `STALE_EVIDENCE`:**  
> Устаревание — это **не противоречие**, а обновление знания.  
> Старый факт не удаляется, а помечается `status="outdated"` и сохраняется для истории.  
> Это принципиально отличается от `OPPOSITE_POLARITY` или `CONFLICTING_VALUE`.

### Принцип работы

```
Новый факт F_new поступает в Cognitive Core
    │
    ▼
Поиск существующих фактов о том же концепте в SemanticMemory
    │
    ▼
Для каждой пары (F_new, F_old):
    │
    ├── Проверка OPPOSITE_POLARITY:
    │   same_subject + same_predicate + negation_marker?
    │   → ConflictRecord(type=OPPOSITE_POLARITY)
    │   → confidence обоих -= 0.15
    │   → Goal("resolve_contradiction")
    │
    ├── Проверка CONFLICTING_VALUE:
    │   same_attribute + different_value?
    │   → ConflictRecord(type=CONFLICTING_VALUE)
    │   → confidence обоих -= 0.10
    │
    ├── Проверка SOURCE_CONFLICT:
    │   incompatible_values + trust_diff > 0.3?
    │   → ConflictRecord(type=SOURCE_CONFLICT)
    │   → победитель: более высокий trust
    │
    ├── Проверка RELATION_CONFLICT:
    │   same_subject + same_object + opposite_relation_type?
    │   → ConflictRecord(type=RELATION_CONFLICT)
    │   → confidence обоих -= 0.12
    │
    ├── Проверка STALE_EVIDENCE:
    │   same_attribute + different_timestamps?
    │   → НЕ конфликт → F_old.status = "outdated"
    │   → F_new становится актуальным
    │
    └── Нет конфликта → СОГЛАСОВАНЫ
        → confidence обоих += 0.02 (взаимное подтверждение)
```

### Стратегии разрешения конфликтов

```
OPPOSITE_POLARITY → MODAL_CONSENSUS или HUMAN_OVERRIDE:
  Текст говорит X, изображение показывает X, аудио говорит ¬X
  → 2 против 1 → победитель: большинство
  → Confidence = weighted_vote(text=0.4, image=0.4, audio=0.2)

CONFLICTING_VALUE → SOURCE_TRUST:
  Факт из university.edu (trust=0.95) vs Факт из blog.com (trust=0.4)
  → Победитель: более доверенный источник
  → Слабый источник: trust -= 0.1

SOURCE_CONFLICT → SOURCE_TRUST (автоматически):
  Победитель определяется по trust_score

RELATION_CONFLICT → HUMAN_OVERRIDE или DEFER:
  Сложные случаи → пометить "requires_human_review"

STALE_EVIDENCE → TEMPORAL_OVERRIDE (автоматически):
  Старый факт: status="outdated", не удаляется
  Новый факт: становится актуальным

HUMAN_OVERRIDE (любой тип):
  Пользователь явно указывает правильный ответ
  → source_trust("user_input") += 0.05
```

---

## Компонент 4: `UncertaintyMonitor` — Монитор неопределённости

**Файл:** `brain/cognition/uncertainty_monitor.py`  
**Аналог:** Орбитофронтальная кора — оценка рисков и неопределённости

### Принцип работы

```
После каждого шага рассуждения:
    │
    ▼
UncertaintyMonitor.evaluate(reasoning_trace)
    │
    ├── confidence > 0.85  → HIGH_CONFIDENCE
    │   → продолжить без уточнений
    │
    ├── confidence > 0.60  → MEDIUM_CONFIDENCE
    │   → добавить оговорку в ответ ("вероятно", "скорее всего")
    │
    ├── confidence > 0.40  → LOW_CONFIDENCE
    │   → запросить дополнительные данные из памяти
    │   → если не найдено → сообщить о неопределённости
    │
    └── confidence < 0.40  → VERY_LOW_CONFIDENCE
        → отказаться от вывода
        → создать цель "gather_more_evidence"
```

### Источники неопределённости

```python
class UncertaintySource(Enum):
    MISSING_DATA      = "missing_data"       # данных нет в памяти
    CONTRADICTING     = "contradicting"      # противоречивые факты
    LOW_SOURCE_TRUST  = "low_source_trust"   # ненадёжный источник
    OUTDATED          = "outdated"           # устаревшие данные
    MODAL_MISMATCH    = "modal_mismatch"     # модальности не согласованы
    INFERENCE_CHAIN   = "inference_chain"    # длинная цепочка выводов
    OUT_OF_SCOPE      = "out_of_scope"       # вне области знаний
```

### Структура `UncertaintyReport`

```python
@dataclass
class UncertaintyReport:
    overall_confidence: float          # итоговая уверенность
    uncertainty_level: str             # "high" | "medium" | "low" | "very_low"
    sources: List[UncertaintySource]   # причины неопределённости
    missing_concepts: List[str]        # каких знаний не хватает
    recommended_action: str            # "proceed" | "clarify" | "gather" | "refuse"
    hedging_phrases: List[str]         # ["вероятно", "скорее всего", "возможно"]
```

---

## Компонент 5: `SalienceEngine` — Детектор значимости (Миндалина)

**Файл:** `brain/cognition/salience_engine.py`  
**Аналог:** Миндалина (amygdala) — быстрая оценка угрозы и важности

### Принцип работы

```
Новый стимул (PerceptEvent или FusedPercept)
    │
    ▼
SalienceEngine.evaluate(stimulus)
    │
    ├── Новизна (novelty):
    │   Насколько это отличается от известного?
    │   sim с WorkingMemory < 0.3 → HIGH NOVELTY → salience += 0.3
    │
    ├── Срочность (urgency):
    │   Есть ли временные маркеры? ("срочно", "немедленно", "сейчас")
    │   → salience += 0.4
    │
    ├── Угроза (threat):
    │   Есть ли негативные маркеры? ("ошибка", "опасность", "критично")
    │   → salience += 0.5
    │
    ├── Релевантность (relevance):
    │   Насколько связано с текущей активной целью?
    │   sim с GoalManager.peek() > 0.7 → HIGH RELEVANCE → salience += 0.3
    │
    └── Итоговый salience score 0.0–1.0
        │
        ├── salience > 0.8 → INTERRUPT (прервать текущую цель)
        ├── salience > 0.5 → PRIORITIZE (поднять в очереди)
        └── salience < 0.5 → NORMAL (обычная обработка)
```

### ⚙️ Явная формула SalienceEngine

```python
def compute_salience(stimulus: str, working_memory, active_goal) -> SalienceScore:
    """
    Взвешенная сумма четырёх компонентов.
    Веса в сумме = 1.0. Результат нормирован в [0.0, 1.0].
    """
    # 1. Новизна: насколько стимул отличается от текущего контекста
    if working_memory:
        max_sim = max(semantic_similarity(stimulus, item.content)
                      for item in working_memory.get_context(n=10))
        novelty = 1.0 - max_sim
    else:
        novelty = 1.0  # нет контекста → всё ново

    # 2. Срочность: наличие временных маркеров
    URGENCY_KEYWORDS = {"срочно", "немедленно", "сейчас", "urgent", "asap", "критично"}
    urgency = 1.0 if any(kw in stimulus.lower() for kw in URGENCY_KEYWORDS) else 0.0

    # 3. Угроза: наличие негативных маркеров
    THREAT_KEYWORDS = {"ошибка", "опасность", "сбой", "error", "fail", "danger", "критическая"}
    threat = 1.0 if any(kw in stimulus.lower() for kw in THREAT_KEYWORDS) else 0.0

    # 4. Релевантность: связь с текущей активной целью
    goal_relevance = (
        semantic_similarity(stimulus, active_goal.description)
        if active_goal else 0.5
    )

    # Взвешенная сумма (веса подобраны эмпирически)
    salience = (
        0.25 * novelty       +   # новизна важна, но не доминирует
        0.35 * urgency       +   # срочность — главный триггер прерывания
        0.25 * threat        +   # угроза требует реакции
        0.15 * goal_relevance    # релевантность — фоновый фильтр
    )

    return SalienceScore(
        overall       = min(1.0, salience),
        novelty       = novelty,
        urgency       = urgency,
        threat        = threat,
        relevance     = goal_relevance,
        action        = ("interrupt"  if salience > 0.8 else
                         "prioritize" if salience > 0.5 else
                         "normal"),
        reason        = f"novelty={novelty:.2f} urgency={urgency:.2f} "
                        f"threat={threat:.2f} relevance={goal_relevance:.2f}",
    )
```

**Веса и их обоснование:**

| Компонент | Вес | Обоснование |
|-----------|-----|-------------|
| `novelty` | 0.25 | Новизна важна, но мозг не должен отвлекаться на каждую мелочь |
| `urgency` | 0.35 | Срочность — главный триггер прерывания текущей задачи |
| `threat` | 0.25 | Угроза требует реакции, но встречается реже |
| `goal_relevance` | 0.15 | Фоновый фильтр — не доминирует, но учитывается |

### Структура `SalienceScore`

```python
@dataclass
class SalienceScore:
    overall: float          # итоговый score 0.0–1.0
    novelty: float          # новизна
    urgency: float          # срочность
    threat: float           # угроза
    relevance: float        # релевантность текущей цели
    action: str             # "interrupt" | "prioritize" | "normal" | "ignore"
    reason: str             # объяснение оценки
```

---

## Компонент 6: `ActionSelector` — Выбор действия (Базальные ганглии)

**Файл:** `brain/cognition/action_selector.py`  
**Аналог:** Базальные ганглии — выбор действия из конкурирующих вариантов

### Принцип работы

```
Planner предлагает N возможных действий:
  [respond_directly, ask_clarification, search_more, refuse]
    │
    ▼
ActionSelector.select(candidates, context)
    │
    ├── Для каждого кандидата вычислить score (явная формула):
    │   score(action) = 0.35*confidence + 0.30*goal_relevance
    │                 + 0.20*feasibility + 0.15*success_rate_history
    │
    ├── Применить ограничения (constraints):
    │   - не отвечать если confidence < 0.4
    │   - не отказывать если есть хоть какие-то данные
    │   - предпочитать действия с высоким success_rate (ProceduralMemory)
    │
    └── Выбрать действие с максимальным score
        → ActionDecision(action, score, reasoning)
```

### Доступные действия

```python
class ActionType(Enum):
    RESPOND_DIRECT    = "respond_direct"    # ответить напрямую
    RESPOND_HEDGED    = "respond_hedged"    # ответить с оговорками
    ASK_CLARIFICATION = "ask_clarification" # запросить уточнение
    SEARCH_MEMORY     = "search_memory"     # поискать ещё в памяти
    GATHER_EVIDENCE   = "gather_evidence"   # запросить больше данных
    REFUSE            = "refuse"            # отказаться отвечать
    LEARN             = "learn"             # запомнить новый факт
    CORRECT           = "correct"           # исправить ошибку
    EXPLORE           = "explore"           # исследовать тему глубже

# Текстовые описания для semantic_similarity (ActionType — enum, поля .description нет)
ACTION_DESCRIPTIONS: Dict[ActionType, str] = {
    ActionType.RESPOND_DIRECT:    "дать прямой ответ на вопрос",
    ActionType.RESPOND_HEDGED:    "дать ответ с оговорками об уверенности",
    ActionType.ASK_CLARIFICATION: "запросить уточнение у пользователя",
    ActionType.SEARCH_MEMORY:     "поискать дополнительные факты в памяти",
    ActionType.GATHER_EVIDENCE:   "собрать больше доказательств из источников",
    ActionType.REFUSE:            "отказаться отвечать из-за недостатка данных",
    ActionType.LEARN:             "запомнить новый факт в семантическую память",
    ActionType.CORRECT:           "исправить ошибочный факт в памяти",
    ActionType.EXPLORE:           "исследовать тему глубже через подцели",
}
```

### ⚙️ Явная формула ActionSelector

> **Соглашение о сигнатурах:** `CognitiveContext` содержит только стабильный контекст цикла
> (session_id, cycle_id, trace_id, active_goal, goal_chain). Операционное состояние reasoning
> и сервисы передаются отдельными параметрами — это предотвращает "giant object" антипаттерн.

```python
def score_action(action: ActionType,
                 ctx: CognitiveContext,
                 state: ReasoningState,
                 resources: ResourceState,
                 services: CognitiveServices) -> float:
    """
    Utility = base_score - cost_penalty.

    ctx       — стабильный контекст цикла (goal, session, trace)
    state     — текущее состояние reasoning (confidence, hypotheses, ...)
    resources — CPU/RAM состояние
    services  — доступ к памяти (procedural, semantic, source)

    ⚠️ Все веса и коэффициенты стартовые — подлежат эмпирической калибровке.
    """
    confidence     = state.best_score                                              # из ReasoningState
    goal_relevance = semantic_similarity(ACTION_DESCRIPTIONS[action],
                                         ctx.active_goal.description)              # ACTION_DESCRIPTIONS — mapping
    feasibility    = _check_feasibility(action, state, resources)                  # данные + ресурсы
    success_rate   = services.procedural_memory.get_success_rate(action.value)     # из CognitiveServices

    base_score = (
        0.35 * confidence     +   # уверенность в результате — главный фактор
        0.30 * goal_relevance +   # насколько действие ведёт к цели
        0.20 * feasibility    +   # выполнимо ли прямо сейчас
        0.15 * success_rate       # исторический success rate из ProceduralMemory
    )

    # Cost model: штраф за ресурсоёмкость
    # CostEstimator — отдельный сервис в CognitiveServices (ResourceState — dataclass, не сервис)
    estimated_cost     = services.cost_estimator.estimate(action, resources)  # нормировано 0.0–1.0
    expected_info_gain = _estimate_info_gain(action, ctx, state)              # 0.0–1.0

    cost_penalty = 0.15 * estimated_cost - 0.10 * expected_info_gain
    # Примечание: expected_info_gain вычитается из штрафа —
    # дорогое действие оправдано, если оно даёт много новой информации.

    return max(0.0, base_score - cost_penalty)
```

**Веса и их обоснование:**

| Фактор | Вес/коэф | Обоснование |
|--------|----------|-------------|
| `confidence` | 0.35 | Главный фактор — нет смысла действовать без уверенности |
| `goal_relevance` | 0.30 | Действие должно вести к цели |
| `feasibility` | 0.20 | Нет данных/ресурсов → действие невозможно |
| `success_rate` | 0.15 | Исторический опыт из ProceduralMemory |
| `estimated_cost` | −0.15 | Штраф за ресурсоёмкость (CPU×ms) |
| `expected_info_gain` | +0.10 | Компенсация штрафа при высокой информативности |

> ⚠️ **Все коэффициенты стартовые** — подлежат эмпирической калибровке.

> **Унификация:** везде используется `RESPOND_HEDGED` (ответить с оговорками).  
> Термин `RESPOND_PARTIAL` не используется — устаревший синоним.

#### Вспомогательные эвристики `_check_feasibility()` и `_estimate_info_gain()`

```python
def _check_feasibility(action: ActionType, state: ReasoningState,
                       resources: ResourceState) -> float:
    """
    Оценивает выполнимость действия прямо сейчас. Возвращает 0.0–1.0.

    RESPOND_DIRECT / RESPOND_HEDGED → state.best_score
        (можно отвечать только если есть уверенность)
    GATHER_EVIDENCE / EXPLORE       → 1.0 если ring2_allowed, иначе 0.0
        (дорогие действия невозможны при жёстком ресурсном блоке)
    SEARCH_MEMORY                   → 1.0 если retrieved_evidence пусто, иначе 0.5
        (поиск всегда возможен, но менее приоритетен если данные уже есть)
    ASK_CLARIFICATION / REFUSE / LEARN / CORRECT → 1.0
        (всегда выполнимы, не требуют ресурсов Ring 2)
    """

def _estimate_info_gain(action: ActionType, ctx: CognitiveContext,
                        state: ReasoningState) -> float:
    """
    Оценивает ожидаемый прирост информации от действия. Возвращает 0.0–1.0.

    GATHER_EVIDENCE   → 1.0 - evidence_coverage (чем меньше покрытие, тем выше gain)
    SEARCH_MEMORY     → 1.0 если retrieved_evidence пусто, иначе 0.3
    EXPLORE           → 1.0 - knowledge_coverage(ctx.active_goal) из SemanticMemory
    RESPOND_DIRECT / RESPOND_HEDGED → 0.0 (ответ не добавляет новых знаний)
    ASK_CLARIFICATION → 0.6 (пользователь может дать новую информацию)
    LEARN / CORRECT   → 0.8 (прямое обновление памяти)
    REFUSE            → 0.0
    """
```

### Структура `ActionDecision`

```python
@dataclass
class ActionDecision:
    action: ActionType        # выбранное действие
    score: float              # итоговый score 0.0–1.0
    confidence: float         # уверенность в правильности выбора
    reasoning: str            # почему выбрано это действие
    alternatives: List[dict]  # другие рассмотренные варианты
    trace_id: str             # для трассировки
```

---

## Компонент 7: `HypothesisEngine` — Генератор гипотез

**Файл:** `brain/cognition/hypothesis_engine.py`  
**Аналог:** Префронтальная кора + Гиппокамп — генерация и проверка гипотез

> **Ключевой компонент мышления.** Без гипотез — нет рассуждения, только поиск.  
> Гипотеза = кандидат на вывод, который нужно подтвердить или опровергнуть.

### Принцип работы (Reasoning Loop)

```
retrieve(query) → top-K фактов из памяти
    │
    ▼
generate_hypotheses(facts) → список гипотез H1, H2, H3...
    │
    ├── H1: "нейрон → передаёт сигналы" (из факта A)
    ├── H2: "нейрон → часть нервной системы" (из факта B)
    └── H3: "нейрон ≈ транзистор" (аналогия)
    │
    ▼
score_hypotheses([H1, H2, H3]) → ранжированный список
    │
    ▼
select_best(top_n=2) → [H1(0.82), H2(0.71)]
    │
    ▼
act(best_hypotheses) → CognitiveResult
```

### ⚙️ Явная формула scoring гипотез

> Формула разделена на **support_score** (что "за") и **risk_score** (что "против").  
> Итоговый score = `max(0.0, support_score - risk_score)`.  
> Это устраняет двойной штраф за противоречия (coherence + penalty одновременно).

```python
def score_hypothesis(H: Hypothesis, memory_manager, source_memory) -> float:
    """
    Раздельный расчёт support и risk. Итог: max(0.0, support - risk).
    
    ⚠️ Веса стартовые — подлежат эмпирической калибровке по реальным данным.
    """
    # === SUPPORT SCORE (что "за" гипотезу) ===

    # 1. Покрытие доказательствами: доля фактов, поддерживающих гипотезу
    # candidate_facts — факты после фильтрации по relevance_score > 0.3.
    # Не "все факты из памяти", а только релевантные кандидаты для данной гипотезы.
    evidence_coverage = len(H.supporting_facts) / max(len(H.candidate_facts), 1)

    # 2. Доверие к источникам: среднее trust_score источников
    source_trust = mean(
        source_memory.get_trust(ref) for ref in H.source_refs
    ) if H.source_refs else 0.5

    # 3. Релевантность: насколько доказательства близки к запросу
    relevance_score = mean(
        e.relevance_score for e in H.evidence_packs
    ) if H.evidence_packs else 0.5

    support_score = (
        0.45 * evidence_coverage  +   # главный фактор — покрытие фактами
        0.35 * source_trust       +   # надёжность источников
        0.20 * relevance_score        # близость к запросу
    )

    # === RISK SCORE (что "против" гипотезы) ===

    # 1. Вес противоречий: нормированное кол-во конфликтов
    contradiction_weight = min(1.0, len(H.conflict_ids) * 0.25)

    # 2. Устаревание: насколько старые доказательства
    staleness = 1.0 - mean(
        e.freshness_score for e in H.evidence_packs
    ) if H.evidence_packs else 0.5

    # 3. Несоответствие модальностей: разные модальности дают разные ответы
    modality_mismatch = _compute_modality_mismatch(H.evidence_packs)

    # 4. Длина цепочки вывода: чем длиннее — тем ненадёжнее
    inference_chain_len = len(H.reasoning_steps) / 10.0  # нормировано к [0, 1]

    risk_score = (
        0.40 * contradiction_weight  +   # противоречия — главный риск
        0.30 * staleness             +   # устаревшие данные
        0.20 * modality_mismatch     +   # несогласованность модальностей
        0.10 * inference_chain_len       # длинная цепочка вывода
    )

    return max(0.0, support_score - risk_score)
```

**Веса и их обоснование:**

| Компонент | Вес | Обоснование |
|-----------|-----|-------------|
| **support:** `evidence_coverage` | 0.45 | Главный фактор — покрытие фактами |
| **support:** `source_trust` | 0.35 | Надёжность источников |
| **support:** `relevance_score` | 0.20 | Близость к запросу |
| **risk:** `contradiction_weight` | 0.40 | Противоречия — главный риск |
| **risk:** `staleness` | 0.30 | Устаревшие данные снижают надёжность |
| **risk:** `modality_mismatch` | 0.20 | Несогласованность модальностей |
| **risk:** `inference_chain_len` | 0.10 | Длинная цепочка вывода ненадёжна |

> ⚠️ **Все веса стартовые** — подлежат эмпирической калибровке по реальным данным и тестам.

### Структура `Hypothesis`

```python
@dataclass
class Hypothesis:
    hypothesis_id: str         # "hyp_a1b2c3"
    statement: str             # "нейрон передаёт электрические сигналы"
    hypothesis_type: str       # "causal" | "associative" | "analogical" | "deductive"

    # Доказательная база
    supporting_facts: List[str]    # ссылки на факты "за"
    opposing_facts: List[str]      # ссылки на факты "против"
    candidate_facts: List[str]     # факты-кандидаты для данной гипотезы
                                   # (только после фильтрации по relevance_score > 0.3)
                                   # ⚠️ Переименовано из all_retrieved_facts — старое имя
                                   # вводило в заблуждение ("все факты из памяти")
    source_refs: List[str]         # источники
    evidence_packs: List[EvidencePack]  # структурированные доказательства
    conflict_ids: List[str]        # ID конфликтов из ContradictionDetector
    reasoning_steps: List[str]     # шаги вывода (для inference_chain_len)

    # Оценка (раздельная)
    score: float               # итоговый score = max(0, support - risk)
    support_score: float       # компонент: поддержка
    risk_score: float          # компонент: риск

    # Статус
    status: str                # "candidate" | "accepted" | "rejected" | "uncertain"
    created_at: str
    trace_id: str
```

### Генерация гипотез (без ML)

```python
def generate_hypotheses(query: str, facts: List[SemanticNode]) -> List[Hypothesis]:
    """
    Генерация гипотез из фактов через шаблоны.
    Не требует нейросетей — работает на CPU-only.
    """
    hypotheses = []

    for fact in facts:
        # Шаблон 1: прямое утверждение
        hypotheses.append(Hypothesis(
            statement=f"{fact.concept} {fact.description}",
            hypothesis_type="associative",
            supporting_facts=[fact.concept],
        ))

        # Шаблон 2: причинно-следственная связь
        for relation in fact.relations:
            if relation.relation_type in ("causes", "enables", "leads_to"):
                hypotheses.append(Hypothesis(
                    statement=f"{fact.concept} → {relation.target}",
                    hypothesis_type="causal",
                    supporting_facts=[fact.concept, relation.target],
                ))

        # Шаблон 3: аналогия (структурное сходство)
        similar = semantic_memory.search(fact.concept, top_n=3)
        for similar_node in similar:
            if similar_node.concept != fact.concept:
                hypotheses.append(Hypothesis(
                    statement=f"{fact.concept} ≈ {similar_node.concept}",
                    hypothesis_type="analogical",
                    supporting_facts=[fact.concept, similar_node.concept],
                ))

    return hypotheses
```

---

## 🔄 Reasoning Loop — Полный цикл рассуждения

Это **центральный алгоритм** Cognitive Core. Каждый цикл мышления проходит 5 шагов:

```
┌─────────────────────────────────────────────────────────────┐
│                    REASONING LOOP                           │
│                                                             │
│  Шаг 1: RETRIEVE                                            │
│  ─────────────────────────────────────────────────────────  │
│  query → MemoryManager.retrieve_staged(query)               │
│    Stage 1: broad search → top-20 кандидатов                │
│    Stage 2: filter by trust/confidence/modality             │
│    Stage 3: rerank by goal_relevance + graph_distance       │
│  → top-K фактов + эпизодов + контекста                      │
│                                                             │
│  Шаг 2: GENERATE HYPOTHESES                                 │
│  ─────────────────────────────────────────────────────────  │
│  HypothesisEngine.generate(query, retrieved_facts)          │
│  → [H1, H2, H3, ...] через шаблоны (без ML)                 │
│                                                             │
│  Шаг 3: SCORE                                               │
│  ─────────────────────────────────────────────────────────  │
│  для каждой гипотезы Hi:                                    │
│    support = 0.45*evidence_coverage + 0.35*source_trust     │
│            + 0.20*relevance_score                           │
│    risk    = 0.40*contradiction_weight + 0.30*staleness     │
│            + 0.20*modality_mismatch + 0.10*chain_len        │
│    score(Hi) = max(0.0, support - risk)                     │
│  → ранжированный список гипотез                             │
│                                                             │
│  Шаг 4: SELECT                                              │
│  ─────────────────────────────────────────────────────────  │
│  best = top-N(scored_hypotheses)                            │
│  UncertaintyMonitor.evaluate(best.score)                    │
│  ContradictionDetector.check(best.statement)                │
│  → ActionDecision через ActionSelector                      │
│                                                             │
│  Шаг 5: ACT                                                 │
│  ─────────────────────────────────────────────────────────  │
│  respond / ask_clarification / gather_evidence / explore    │
│  → CognitiveResult с полным trace                           │
└─────────────────────────────────────────────────────────────┘
```

**Ключевой принцип:** мышление = не "умный код", а **измеримый процесс**:
- каждый шаг имеет входные данные и выходные данные
- каждая гипотеза имеет числовой score с объяснением
- каждое решение трассируется до источников

---

## 🔁 Two-Ring Reasoning — Двухкольцевое рассуждение

> **Идея:** не все запросы требуют одинаковых вычислительных затрат.  
> Дешёвое кольцо обрабатывает большинство случаев. Дорогое — только когда нужно.

```
┌─────────────────────────────────────────────────────────────┐
│                  TWO-RING REASONING                         │
│                                                             │
│  RING 1 — FAST (дешёвое, детерминированное):                │
│  ─────────────────────────────────────────────────────────  │
│  • Associative reasoning (BFS по семантическому графу)      │
│  • Deductive reasoning (силлогизмы из фактов)               │
│  • Contradiction scan (быстрая проверка конфликтов)         │
│  • Latency: ~10–50 мс | CPU: 1 поток | RAM: ~10 MB          │
│                                                             │
│  Запускается ВСЕГДА для каждого запроса.                    │
│                                                             │
│  Если Ring 1 даёт confidence >= 0.75 и нет противоречий:    │
│    → сразу переходим к ActionSelector                       │
│    → Ring 2 не запускается                                  │
│                                                             │
│  RING 2 — DEEP (дорогое, запускается по условию):           │
│  ─────────────────────────────────────────────────────────  │
│  • Causal reasoning (граф причинности)                      │
│  • Analogical reasoning (структурные аналогии)              │
│  • HypothesisEngine (генерация + scoring гипотез)           │
│  • Multi-stage retrieval (retrieve_staged)                  │
│  • Latency: ~100–500 мс | CPU: 2–4 потока | RAM: ~50 MB     │
│                                                             │
│  Запускается ТОЛЬКО при выполнении хотя бы одного условия:  │
│    • confidence < 0.60 (низкая уверенность)                 │
│    • contradictions > 0 (обнаружены противоречия)           │
│    • goal_type == "verify_claim" (проверка утверждения)     │
│    • goal_type == "explore_topic" (исследование темы)       │
│    • salience.novelty > 0.7 (высокая новизна)               │
│    • ctx.active_goal.priority > 0.8 (высокий приоритет цели)│
└─────────────────────────────────────────────────────────────┘
```

**Алгоритм выбора кольца:**

```python
def select_ring(query: str, ctx: CognitiveContext,
                salience: SalienceScore) -> int:
    """
    Возвращает 1 (fast) или 2 (deep).
    По умолчанию — Ring 1. Ring 2 только при явных триггерах.

    Принимает salience отдельно — CognitiveContext не содержит SalienceScore,
    это операционный результат SalienceEngine текущего цикла.
    """
    # Быстрая проверка Ring 1
    ring1_result = ring1_reason(query, ctx)

    # Условия перехода в Ring 2
    triggers = [
        ring1_result.confidence < 0.60,
        len(ring1_result.contradictions) > 0,
        ctx.active_goal.goal_type in ("verify_claim", "explore_topic"),
        salience.novelty > 0.7,           # salience передаётся явно
        ctx.active_goal.priority > 0.8,
    ]

    if any(triggers):
        return 2  # запустить глубокое рассуждение
    return 1      # достаточно быстрого результата
```

**Ресурсный профиль:**

| Кольцо | Типичный случай | Latency | CPU | RAM |
|--------|----------------|---------|-----|-----|
| Ring 1 | Простой вопрос, известный факт | 10–50 мс | 1 поток | ~10 MB |
| Ring 2 | Проверка утверждения, новая тема | 100–500 мс | 2–4 потока | ~50 MB |

**Связь с ResourceMonitor (пороги с гистерезисом):**
```
CPU >= 85% или RAM >= 85% (жёсткий блок, ring2_allowed = False):
  → Ring 2 заблокирован (DegradationPolicy)
  → Только Ring 1 + UncertaintyMonitor.flag("resource_constrained")
  → Ответ с оговоркой: "Ограниченные ресурсы — возможна неполная проверка"
  → Снимается только при CPU <= 75% и RAM <= 75% (гистерезис)

CPU >= 70% (мягкий блок, soft_blocked = True):
  → GATHER_EVIDENCE и EXPLORE заблокированы в PolicyLayer (Фильтр 2)
  → Ring 2 ещё разрешён, но дорогие действия недоступны
  → Снимается при CPU <= 60% (гистерезис)
```

---

## 🛑 Stop Conditions — Условия остановки reasoning loop

> Reasoning loop не должен работать бесконечно.  
> Условия остановки зависят от **типа цели** — разные цели требуют разных критериев.

### Цель-специфичные условия (из `GoalTypeLimits`)

| Тип цели | step_limit | time_limit | confidence | stability_window |
|----------|-----------|------------|------------|-----------------|
| `answer_question` | 3 | 200 мс | ≥ 0.75 | 2 итерации |
| `verify_claim` | 7 | 500 мс | ≥ 0.80 | 2 итерации |
| `explore_topic` | 10 | 800 мс | ≥ 0.70 | 3 итерации |
| `learn_fact` | 3 | 150 мс | ≥ 0.70 | 1 итерация |

> ⚠️ Все значения стартовые — подлежат эмпирической калибровке.

### Алгоритм проверки stop conditions

```python
def check_stop_conditions(state: ReasoningState, limits: GoalTypeLimits,
                          resources: ResourceState) -> Optional[CognitiveFailure]:
    """
    Проверяет все условия остановки. Возвращает причину или None (продолжать).
    Порядок проверки: ресурсы → лимиты → качество → стабильность.
    """
    # 1. Ресурсный блок (приоритет 1 — немедленная остановка)
    if resources.cpu_pct > 85 or resources.ram_pct > 85:
        return CognitiveFailure.RESOURCE_BLOCKED

    # 2. Лимит шагов (нормальная остановка — не ошибка)
    if state.iteration >= limits.step_limit:
        return CognitiveOutcome.STEP_LIMIT_REACHED

    # 3. Лимит времени (проверяется через elapsed_ms в контексте)
    # → обрабатывается в основном цикле через time.monotonic()

    # 4. Достигнут порог уверенности
    if state.best_score >= limits.confidence_threshold:
        return CognitiveFailure.STOP_CONDITION_MET

    # 5. Стабильность: score не меняется N итераций подряд
    score_delta = abs(state.best_score - state.prev_best_score)
    if score_delta < 0.01 and state.iteration >= limits.stability_window:
        return CognitiveFailure.STOP_CONDITION_MET

    # 6. Нет новых доказательств
    if not state.retrieved_evidence:
        return CognitiveFailure.RETRIEVAL_FAILED

    # 7. Нет гипотез
    if not state.active_hypotheses:
        return CognitiveFailure.NO_HYPOTHESIS_GENERATED

    return None  # продолжать reasoning
```

### Универсальные условия (для всех типов целей)

```
no_new_evidence:    retrieve вернул 0 результатов → RETRIEVAL_FAILED
resource_blocked:   CPU > 85% или RAM > 85% → RESOURCE_BLOCKED
replan_limit:       retry_count >= max_retries → REPLAN_LIMIT_REACHED
```

---

## 🔒 PolicyLayer — Слой политик поведения

> PolicyLayer — это **фильтр + модификатор** между scoring и финальным выбором действия.  
> Он не выбирает действие, но может **заблокировать** или **скорректировать** его score.

**Файл:** `brain/cognition/policy_layer.py`

### Фильтры (блокировка действий)

```python
def apply_filters(candidates: List[ActionType], state: ReasoningState,
                  resources: ResourceState, constraints: PolicyConstraints,
                  outcome: Optional[CognitiveOutcome] = None) -> List[ActionType]:
    """
    Убирает недопустимые действия из списка кандидатов.
    """
    # Жёсткий блок при RESOURCE_BLOCKED: дорогие действия запрещены полностью
    RESOURCE_BLOCKED_ACTIONS = {ActionType.GATHER_EVIDENCE, ActionType.EXPLORE}
    resource_blocked = (
        outcome == CognitiveOutcome.RESOURCE_BLOCKED
        or resources.cpu_pct > 85
        or resources.ram_pct > 85
    )

    filtered = []
    for action in candidates:
        # Фильтр 0: жёсткий блок при перегрузке ресурсов
        if resource_blocked and action in RESOURCE_BLOCKED_ACTIONS:
            continue  # жёстко заблокировано (не штраф, а запрет)

        # Фильтр 1: не отвечать напрямую при низкой уверенности
        if action == ActionType.RESPOND_DIRECT and state.best_score < constraints.min_confidence:
            continue  # заблокировано

        # Фильтр 2: мягкий блок GATHER_EVIDENCE при умеренной нагрузке CPU
        # Используем resources.soft_blocked (cpu >= 70%, гистерезис: снимается при < 60%)
        # Зазор 15% до жёсткого блока (85%) предотвращает флапание
        if action == ActionType.GATHER_EVIDENCE and resources.soft_blocked:
            continue  # мягко заблокировано

        filtered.append(action)
    return filtered
```

### Модификаторы utility (корректировка score)

```python
def apply_modifiers(scores: Dict[ActionType, float], state: ReasoningState,
                    resources: ResourceState,
                    services: CognitiveServices) -> Dict[ActionType, float]:
    """
    Корректирует score действий на основе контекста.
    ⚠️ Все дельты стартовые — подлежат эмпирической калибровке.
    """
    modified = dict(scores)

    # Модификатор 1: штраф за дорогие действия при умеренной нагрузке CPU
    # Используем resources.soft_blocked (cpu >= 70%, гистерезис: снимается при < 60%)
    # (CostEstimator — сервис в CognitiveServices, ResourceState — только данные)
    if resources.soft_blocked:
        for action in [ActionType.GATHER_EVIDENCE, ActionType.EXPLORE]:
            if action in modified:
                cost = services.cost_estimator.estimate(action, resources)
                modified[action] -= 0.15 * cost

    # Модификатор 2: буст ASK_CLARIFICATION при наличии противоречий
    if state.contradiction_flags:
        if ActionType.ASK_CLARIFICATION in modified:
            modified[ActionType.ASK_CLARIFICATION] += 0.20

    # Модификатор 3: буст RESPOND_HEDGED при умеренной уверенности
    if 0.5 <= state.best_score <= 0.7:
        if ActionType.RESPOND_HEDGED in modified:
            modified[ActionType.RESPOND_HEDGED] += 0.15

    return modified
```

> **Унификация терминологии:** везде используется `RESPOND_HEDGED` (ответить с оговорками).  
> Термин `RESPOND_PARTIAL` не используется — это был устаревший синоним.

---

## Выходной формат: `CognitiveResult`

```python
@dataclass
class CognitiveResult:
    # Входные данные
    input_query: str                    # исходный запрос
    session_id: str                     # ID сессии
    cycle_id: str                       # ID цикла мышления

    # Результат
    action: ActionDecision              # выбранное действие
    response: str                       # текстовый ответ (если есть)
    confidence: float                   # итоговая уверенность

    # Трассировка
    reasoning_trace: ReasoningTrace     # полная цепочка рассуждений
    goal_chain: List[Goal]              # цепочка целей
    memory_refs: List[str]              # использованные факты из памяти
    source_refs: List[str]              # использованные источники

    # Мета
    contradictions: List[ContradictionRecord]  # найденные противоречия
    uncertainty: UncertaintyReport             # отчёт о неопределённости
    salience: SalienceScore                    # оценка значимости

    # Производительность
    total_duration_ms: float            # общее время обработки
    created_at: str                     # timestamp
```

---

## Полный цикл мышления

```
Вопрос: "Почему нейроны важны для мышления?"
      │
      ▼
[SalienceEngine]
  novelty=0.3, urgency=0.0, threat=0.0, relevance=0.8
  → salience=0.55 → PRIORITIZE
      │
      ▼
[Planner]
  Goal: "answer_question(почему нейроны важны)"
  Plan:
    Шаг 1: retrieve_memory("нейрон", "мышление")
    Шаг 2: reason_causal(results)
    Шаг 3: check_confidence
    Шаг 4: build_response
      │
      ▼
[Шаг 1: retrieve_memory]
  WorkingMemory:  [] (нет в контексте)
  SemanticMemory: [нейрон→клетка, нейрон→синапс, мышление→нейроны]
  EpisodicMemory: [ep_001: "нейрон передаёт сигналы"]
      │
      ▼
[Reasoner: causal]
  нейрон → передаёт_сигналы → мозг_работает → мышление_возможно
  Trace: [нейрон --causes--> сигналы --enables--> мышление]
  Confidence: 0.78
      │
      ▼
[ContradictionDetector]
  Нет противоречий → OK
      │
      ▼
[UncertaintyMonitor]
  confidence=0.78 → MEDIUM_CONFIDENCE
  → добавить "вероятно" в ответ
      │
      ▼
[ActionSelector]
  Кандидаты: [respond_hedged(0.78), ask_clarification(0.3)]
  → Выбор: respond_hedged
      │
      ▼
CognitiveResult(
  response="Нейроны важны для мышления, потому что они передают
            электрические сигналы между клетками мозга, что
            обеспечивает работу нейронных сетей.",
  confidence=0.78,
  reasoning_trace=[нейрон→сигналы→мышление],
  memory_refs=["semantic:нейрон", "semantic:мышление"],
  uncertainty=UncertaintyReport(level="medium", hedging=["вероятно"])
)
```

---

## Человекочитаемый digest (Observability)

Каждый цикл мышления производит digest для логирования:

```
Cycle 4521
  Goal:         answer_question("почему нейроны важны")
  Reasoning:    causal [нейрон → сигналы → мышление]
  Memory used:  semantic:нейрон, semantic:мышление, episodic:ep_001
  Sources:      docs/нейробиология.pdf (trust=0.87)
  Contradiction: none
  Confidence:   0.78 (medium) → hedged response
  Action:       respond_hedged
  Duration:     142ms
  CPU:          45% | RAM: 3.8 GB
```

---

## Ресурсный бюджет (CPU-only, 32 GB RAM)

| Компонент | RAM | CPU | Время/цикл |
|-----------|-----|-----|------------|
| Planner + GoalManager | ~5 MB | 1 поток | ~1–5 мс |
| Reasoner (associative) | ~10 MB | 1–2 потока | ~10–50 мс |
| Reasoner (causal/deductive) | ~10 MB | 1–2 потока | ~20–100 мс |
| ContradictionDetector | ~5 MB | 1 поток | ~5–20 мс |
| UncertaintyMonitor | ~1 MB | 1 поток | < 1 мс |
| SalienceEngine | ~2 MB | 1 поток | ~1–5 мс |
| ActionSelector | ~1 MB | 1 поток | < 1 мс |
| **Итого** | **~35 MB** | **2–4 потока** | **~40–180 мс** |

---

## Статус реализации

| Компонент | Статус | Файл |
|-----------|--------|------|
| `Goal` + `PlanStep` dataclasses | ✅ Этап F | `brain/cognition/planner.py` |
| `GoalManager` | ✅ Этап F | `brain/cognition/planner.py` |
| `Planner` + `replan()` | ✅ Этап F | `brain/cognition/planner.py` |
| `ReasoningTrace` + `ReasoningStep` | ✅ Этап F | `brain/cognition/reasoner.py` |
| `Reasoner` (associative) | ✅ Этап F | `brain/cognition/reasoner.py` |
| `Reasoner` (causal/deductive/analogical) | ✅ Этап F | `brain/cognition/reasoner.py` |
| `ContradictionDetector` + `ConflictType` | ✅ Этап F+ | `brain/cognition/contradiction_detector.py` |
| `UncertaintyMonitor` + `UncertaintyReport` | ✅ Этап F+ | `brain/cognition/uncertainty_monitor.py` |
| `SalienceEngine` + `SalienceScore` | ⬜ Этап H | `brain/cognition/salience_engine.py` |
| `ActionSelector` + cost model | ✅ Этап F | `brain/cognition/action_selector.py` |
| `HypothesisEngine` + `Hypothesis` | ✅ Этап F | `brain/cognition/hypothesis_engine.py` |
| `CognitiveResult` | ✅ Этап F | `brain/cognition/__init__.py` |
| `CognitiveContext` + `ResourceState` | ✅ Этап F | `brain/cognition/context.py` |
| `EvidencePack` + `ReasoningState` | ✅ Этап F | `brain/cognition/context.py` |
| `GoalTypeLimits` + `PolicyConstraints` | ✅ Этап F | `brain/cognition/context.py` |
| `check_stop_conditions()` | ✅ Этап F | `brain/cognition/planner.py` |
| `PolicyLayer` (filters + modifiers) | ⬜ Этап H | `brain/cognition/policy_layer.py` |
| `CognitiveOutcome` enum (+ `CognitiveFailure` alias) | ✅ Этап F | `brain/cognition/context.py` |
