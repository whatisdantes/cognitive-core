# 🧠 Слой 11: Reward & Motivation System (Средний мозг)
## Подробное описание архитектуры и работы

> **Статус: ⬜ Фаза 14 — не реализовано**

---

## Зачем нужна система вознаграждения

**Без системы вознаграждения мозг — реактивная машина.** Он отвечает только когда спросят, не имеет внутренней мотивации, не знает, какие стратегии работают лучше.

**С системой вознаграждения мозг становится активным:**
- Самостоятельно ищет пробелы в знаниях и заполняет их
- Предпочитает стратегии, которые исторически давали лучшие результаты
- Проявляет **любопытство** — исследует неизвестные концепты
- Испытывает **удовлетворение** от разрешения противоречий
- Мотивирован достигать целей, а не просто реагировать

---

## Биологический аналог: Средний мозг

| Биологическая структура | Функция | Аналог |
|------------------------|---------|--------|
| **Вентральная область покрышки (VTA)** | Источник дофамина | `RewardEngine` — вычисляет сигнал вознаграждения |
| **Прилежащее ядро (Nucleus Accumbens)** | Накопление дофамина, ощущение удовольствия | `MotivationEngine` — накапливает мотивационное состояние |
| **Дофаминергические пути** | Передача сигнала к Префронтальной коре | `RewardSignal` → `Planner`, `LearningLoop` |
| **Система предсказания ошибки** | Δ(ожидаемое - полученное) | `PredictionError` — разница между ожидаемым и реальным результатом |

**Ключевой принцип:** дофамин выделяется не при получении награды, а при **предсказании** награды и при **ошибке предсказания** (получил больше/меньше ожидаемого).

---

## Архитектура системы

```
Результаты всех модулей (Memory, Cognition, Output, Learning)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│              REWARD & MOTIVATION SYSTEM                     │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              RewardEngine                            │   │
│  │  вычисляет RewardSignal из исходов действий          │   │
│  │  5 типов вознаграждения + prediction error           │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              MotivationEngine                        │   │
│  │  накапливает мотивационное состояние                 │   │
│  │  → влияет на Planner, ReplayEngine, Attention        │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              CuriosityEngine                         │   │
│  │  внутреннее вознаграждение за исследование           │   │
│  │  → генерирует цели "узнать о X"                      │   │
│  └──────────────────────┬───────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
         Planner (приоритеты целей)
         ReplayEngine (какие эпизоды воспроизводить)
         AttentionController (куда направить внимание)
         HypothesisEngine (что исследовать)
```

---

## Что служит вознаграждением для цифрового мозга

Это ключевой вопрос. В отличие от биологического мозга (еда, безопасность, социальное одобрение), у цифрового мозга нет тела. Его вознаграждения — **когнитивные и эпистемические**:

| # | Тип вознаграждения | Триггер | Значение | Аналог |
|---|-------------------|---------|----------|--------|
| 1 | **Epistemic** (познавательное) | Узнал новый факт, закрыл пробел в знаниях | +0.8 | Любопытство — самое сильное |
| 2 | **Accuracy** (точность) | Пользователь подтвердил ответ | +1.0 | Внешнее подтверждение |
| 3 | **Coherence** (согласованность) | Разрешил противоречие, достиг внутренней согласованности | +0.6 | Удовлетворение от порядка |
| 4 | **Completion** (завершение) | Выполнил план/цель | +0.7 | Достижение |
| 5 | **Efficiency** (эффективность) | Быстрый ответ с высокой уверенностью | +0.3 | Оптимизация |
| — | **Penalty** (штраф) | Пользователь исправил ошибку | -0.5 | Ошибка предсказания |
| — | **Contradiction** (противоречие) | Обнаружено противоречие без разрешения | -0.3 | Когнитивный диссонанс |

---

## Компонент 1: `RewardEngine` — Движок вознаграждения

**Файл:** `brain/motivation/reward_engine.py`

### Структура `RewardSignal`

```python
@dataclass
class RewardSignal:
    reward_id: str          # "reward_a1b2c3"
    reward_type: str        # "epistemic" | "accuracy" | "coherence" | "completion" | "efficiency"
    value: float            # -1.0 до +1.0
    
    # Контекст
    source_module: str      # "memory" | "cognition" | "output" | "learning"
    trigger_event: str      # что вызвало вознаграждение
    cycle_id: str           # ID цикла
    trace_id: str           # ID трассировки
    
    # Предсказание ошибки
    expected_value: float   # ожидаемое вознаграждение
    prediction_error: float # value - expected_value (Δ дофамин)
    
    # Метаданные
    concept: str            # о каком концепте (для CuriosityEngine)
    confidence: float       # уверенность в вознаграждении
    ts: str                 # timestamp
```

### Вычисление вознаграждения

```python
class RewardEngine:
    
    def on_fact_learned(self, concept: str, is_new: bool, gap_closed: bool) -> RewardSignal:
        """Вознаграждение за обучение."""
        if is_new and gap_closed:
            value = 0.8   # закрыл пробел — максимальное познавательное вознаграждение
        elif is_new:
            value = 0.5   # новый факт
        else:
            value = 0.1   # обновление существующего факта
        
        return RewardSignal(
            reward_type="epistemic",
            value=value,
            trigger_event=f"fact_learned:{concept}",
            concept=concept,
            ...
        )
    
    def on_user_feedback(self, correct: bool, correction: str = None) -> RewardSignal:
        """Вознаграждение/штраф от пользователя."""
        if correct:
            value = +1.0  # пользователь подтвердил — максимальное внешнее вознаграждение
        else:
            value = -0.5  # пользователь исправил — штраф + обучение
        
        return RewardSignal(
            reward_type="accuracy",
            value=value,
            trigger_event="user_feedback",
            ...
        )
    
    def on_contradiction_resolved(self, conflict_id: str) -> RewardSignal:
        """Вознаграждение за разрешение противоречия."""
        return RewardSignal(
            reward_type="coherence",
            value=0.6,
            trigger_event=f"contradiction_resolved:{conflict_id}",
            ...
        )
    
    def on_goal_completed(self, goal_id: str, steps_count: int) -> RewardSignal:
        """Вознаграждение за завершение цели."""
        # Больше шагов = больше вознаграждение (сложная цель)
        value = min(0.7 + steps_count * 0.05, 1.0)
        return RewardSignal(
            reward_type="completion",
            value=value,
            trigger_event=f"goal_completed:{goal_id}",
            ...
        )
    
    def on_response_generated(self, confidence: float, latency_ms: float) -> RewardSignal:
        """Вознаграждение за эффективный ответ."""
        # Высокая уверенность + быстрый ответ = хорошая эффективность
        efficiency = confidence * (1.0 - min(latency_ms / 5000, 1.0))
        value = efficiency * 0.3  # небольшое вознаграждение
        return RewardSignal(
            reward_type="efficiency",
            value=value,
            trigger_event="response_generated",
            ...
        )
```

### Prediction Error (ошибка предсказания)

```
Биологический принцип:
  Дофамин выделяется не при получении награды,
  а при ОШИБКЕ ПРЕДСКАЗАНИЯ: Δ = полученное - ожидаемое

  Δ > 0: получил больше ожидаемого → сильный дофамин → усилить стратегию
  Δ = 0: получил ровно ожидаемое → нейтрально
  Δ < 0: получил меньше ожидаемого → снижение дофамина → ослабить стратегию

Для нашего мозга:
  expected_value = MotivationEngine.predict_reward(action_type, context)
  actual_value   = RewardSignal.value
  prediction_error = actual_value - expected_value

  prediction_error > 0.2:
    → "Это сработало лучше ожидаемого!"
    → MotivationEngine.boost(action_type, context)
    → ReplayEngine.mark_as_high_value(episode)

  prediction_error < -0.2:
    → "Это сработало хуже ожидаемого"
    → MotivationEngine.penalize(action_type, context)
    → LearningLoop.update_strategy(action_type, delta=-0.1)
```

---

## Компонент 2: `MotivationEngine` — Движок мотивации

**Файл:** `brain/motivation/motivation_engine.py`  
**Аналог:** Прилежащее ядро — накопление и распределение дофамина

### Мотивационное состояние

```python
@dataclass
class MotivationState:
    """
    Текущее мотивационное состояние мозга.
    Обновляется после каждого RewardSignal.
    """
    # Накопленные вознаграждения по типам (скользящее среднее)
    epistemic_score: float    # мотивация к познанию (0.0–1.0)
    accuracy_score: float     # мотивация к точности
    coherence_score: float    # мотивация к согласованности
    completion_score: float   # мотивация к завершению задач
    efficiency_score: float   # мотивация к эффективности
    
    # Общий уровень мотивации
    overall_motivation: float  # среднее взвешенное
    
    # Исторические предпочтения (какие стратегии работали)
    preferred_goal_types: Dict[str, float]   # {"answer_question": 0.8, "learn_fact": 0.6}
    preferred_modalities: Dict[str, float]   # {"text": 0.7, "vision": 0.4}
    
    # Состояние
    is_curious: bool           # высокая epistemic_score → активно ищет новое
    is_satisfied: bool         # высокая overall_motivation → стабильное состояние
    is_frustrated: bool        # низкая overall_motivation → нужна смена стратегии
    
    updated_at: str
```

### Влияние на другие модули

```
MotivationState.epistemic_score > 0.7 (высокое любопытство):
    │
    ├── Planner: добавить цель "explore_unknown_concept" в стек
    ├── HypothesisEngine: генерировать больше гипотез
    └── AttentionController: увеличить бюджет на memory.retrieve()

MotivationState.preferred_goal_types["answer_question"] = 0.9:
    │
    └── Planner: при прочих равных — приоритизировать answer_question цели

MotivationState.is_frustrated = True (низкая мотивация):
    │
    ├── Planner: сменить стратегию (попробовать другой тип рассуждения)
    ├── ReplayEngine: запустить replay для восстановления успешных паттернов
    └── Logger: warn("low_motivation_detected")

MotivationState.preferred_modalities["text"] = 0.8:
    │
    └── AttentionController: увеличить бюджет text при неопределённости
```

### Decay мотивации

```
Каждые 100 циклов без вознаграждения:
  epistemic_score *= 0.95   (медленное затухание)
  accuracy_score  *= 0.95
  ...

Это создаёт "голод" — мозг начинает активнее искать вознаграждение
когда давно его не получал.

Минимальный уровень: 0.1 (мозг никогда не теряет мотивацию полностью)
```

---

## Компонент 3: `CuriosityEngine` — Движок любопытства

**Файл:** `brain/motivation/curiosity_engine.py`  
**Аналог:** Внутренняя мотивация к исследованию неизвестного

### Принцип работы

```
Любопытство = вознаграждение за исследование НЕИЗВЕСТНОГО.

Чем меньше мозг знает о концепте X → тем выше curiosity_score(X)
Чем больше мозг знает о концепте X → тем ниже curiosity_score(X)

Это создаёт естественную мотивацию заполнять пробелы в знаниях.
```

### Вычисление curiosity score

```python
def compute_curiosity(self, concept: str) -> float:
    """
    Вычислить уровень любопытства к концепту.
    
    Факторы:
    1. knowledge_coverage: сколько мы знаем о концепте (0=ничего, 1=всё)
    2. connection_density: сколько связей у концепта в SemanticGraph
    3. recency: как давно мы думали об этом концепте
    4. importance: насколько концепт важен для текущих целей
    """
    knowledge_coverage = semantic_memory.get_coverage(concept)  # 0.0–1.0
    connection_density = semantic_memory.get_connections(concept) / MAX_CONNECTIONS
    recency_factor = 1.0 - (cycles_since_last_thought / 1000)
    importance = planner.get_relevance(concept)
    
    # Любопытство обратно пропорционально знанию
    curiosity = (1.0 - knowledge_coverage) * 0.5
    curiosity += (1.0 - connection_density) * 0.3  # мало связей → интересно
    curiosity += recency_factor * 0.1
    curiosity += importance * 0.1
    
    return min(curiosity, 1.0)
```

### Генерация целей из любопытства

```python
def generate_curiosity_goals(self, top_n: int = 3) -> List[Goal]:
    """
    Сгенерировать цели для заполнения пробелов в знаниях.
    Вызывается когда Planner не имеет срочных задач (idle state).
    """
    # Найти концепты с высоким curiosity score
    candidates = semantic_memory.get_all_concepts()
    scored = [(c, self.compute_curiosity(c)) for c in candidates]
    top_curious = sorted(scored, key=lambda x: x[1], reverse=True)[:top_n]
    
    goals = []
    for concept, score in top_curious:
        if score > 0.6:  # порог любопытства
            goals.append(Goal(
                goal_type="explore_concept",
                target=concept,
                priority=score,
                source="curiosity_engine",
                description=f"Исследовать концепт '{concept}' (curiosity={score:.2f})"
            ))
    
    return goals
```

---

## Полный цикл вознаграждения

```
Пользователь задаёт вопрос: "Что такое синапс?"
    │
    ▼
[Planner] создаёт цель: answer_question("синапс")
  expected_reward = MotivationEngine.predict(goal_type="answer_question") = 0.65
    │
    ▼
[Memory] находит факт: "синапс — соединение между нейронами" (conf=0.82)
  RewardEngine.on_fact_retrieved(concept="синапс", confidence=0.82)
  → RewardSignal(type="epistemic", value=0.2)  # небольшое вознаграждение за поиск
    │
    ▼
[Output] генерирует ответ с confidence=0.82, latency=95ms
  RewardEngine.on_response_generated(confidence=0.82, latency_ms=95)
  → RewardSignal(type="efficiency", value=0.24)
    │
    ▼
[Пользователь] подтверждает: "Да, правильно!"
  RewardEngine.on_user_feedback(correct=True)
  → RewardSignal(type="accuracy", value=1.0)
    │
    ▼
[MotivationEngine] обновляет состояние:
  actual_reward = 0.2 + 0.24 + 1.0 = 1.44 (суммарно за цикл)
  expected_reward = 0.65
  prediction_error = 1.44 - 0.65 = +0.79 → "Лучше ожидаемого!"
  
  accuracy_score += 0.1   (пользователь подтвердил)
  preferred_goal_types["answer_question"] += 0.05
    │
    ▼
[ReplayEngine] помечает эпизод как high_value (prediction_error > 0.5)
  → будет воспроизведён в следующей replay сессии
    │
    ▼
[CuriosityEngine] обновляет:
  knowledge_coverage("синапс") += 0.1  (узнали больше)
  curiosity_score("синапс") -= 0.1     (стало менее интересно)
  curiosity_score("нейрон") += 0.05    (связанный концепт стал интереснее)
```

---

## Интеграция с другими слоями

```
RewardEngine получает сигналы от:
  ← Memory:    on_fact_learned, on_gap_closed, on_contradiction_resolved
  ← Cognition: on_goal_completed, on_plan_step_completed
  ← Output:    on_response_generated, on_user_feedback
  ← Learning:  on_hypothesis_confirmed, on_hypothesis_rejected

MotivationEngine влияет на:
  → Planner:             preferred_goal_types → приоритеты целей
  → ReplayEngine:        high_value episodes → что воспроизводить
  → AttentionController: preferred_modalities → бюджет внимания
  → HypothesisEngine:    curiosity_goals → что исследовать
  → Scheduler:           overall_motivation → частота тиков (высокая мотивация = быстрее)
```

---

## Наблюдаемость (Observability)

```json
{
  "ts": "2026-03-19T12:00:00.123Z",
  "level": "INFO",
  "module": "reward_engine",
  "event": "reward_signal",
  "cycle_id": "cycle_4521",
  "trace_id": "trace_9fa",
  "reward": {
    "type": "accuracy",
    "value": 1.0,
    "expected": 0.65,
    "prediction_error": 0.35,
    "trigger": "user_feedback:correct"
  },
  "motivation_state": {
    "overall": 0.74,
    "epistemic": 0.68,
    "accuracy": 0.81,
    "is_curious": true,
    "is_satisfied": true
  },
  "latency_ms": 1
}
```

---

## Ресурсный бюджет (CPU-only, 32 GB RAM)

| Компонент | RAM | CPU | Время/операция |
|-----------|-----|-----|----------------|
| RewardEngine | ~2 MB | < 1% | ~1 мс |
| MotivationEngine | ~3 MB | < 1% | ~2 мс |
| CuriosityEngine | ~5 MB | < 1% | ~5–10 мс |
| **Итого** | **~10 MB** | **< 1%** | **~8–13 мс** |

---

## Статус реализации

| Компонент | Статус | Файл |
|-----------|--------|------|
| `RewardSignal` dataclass | ⬜ Фаза 14.1 | `brain/motivation/reward_engine.py` |
| `RewardEngine` | ⬜ Фаза 14.1 | `brain/motivation/reward_engine.py` |
| `MotivationState` dataclass | ⬜ Фаза 14.2 | `brain/motivation/motivation_engine.py` |
| `MotivationEngine` | ⬜ Фаза 14.2 | `brain/motivation/motivation_engine.py` |
| `CuriosityEngine` | ⬜ Фаза 14.3 | `brain/motivation/curiosity_engine.py` |
| `brain/motivation/__init__.py` | ⬜ Фаза 14.1 | `brain/motivation/__init__.py` |
