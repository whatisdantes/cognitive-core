# 🧠 Слой 6: Learning Loop (Мозжечок + Гиппокамп)
## Подробное описание архитектуры и работы

> **Статус: ⚡ Этап I — частично реализовано** (OnlineLearner ✅, ReplayEngine ✅, KnowledgeGapDetector ✅)

---

## Что такое обучение в биологии

В человеческом мозге обучение — это **изменение синаптических связей** под влиянием опыта:

| Биологическая структура | Функция обучения | Аналог |
|------------------------|-----------------|--------|
| **Гиппокамп** | Формирование новых воспоминаний, replay во сне | `ConsolidationEngine` + `ReplayEngine` |
| **Мозжечок** | Тонкая коррекция ошибок, автоматизация навыков | `OnlineLearner` + `SkillRefiner` |
| **Базальные ганглии** | Обучение с подкреплением (reward/punishment) | `ReinforcementSignal` |
| **Кора** | Долгосрочное изменение весов (LTP/LTD) | `WeightUpdater` |

**Ключевой принцип:** мозг учится **непрерывно** — не только во время явного обучения, но и во время каждого взаимодействия, и даже во сне (replay).

---

## Роль в искусственном мозге

```
CognitiveResult от Cognitive Core
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    LEARNING LOOP                            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              OnlineLearner                           │   │
│  │  после каждого взаимодействия:                       │   │
│  │  обновить ассоциации, confidence, source trust       │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              ReplayEngine                            │   │
│  │  периодически воспроизводит важные эпизоды:          │   │
│  │  усиливает устойчивые паттерны, удаляет шум          │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              SelfSupervisedLearner                   │   │
│  │  text↔image согласованность                         │   │
│  │  audio↔transcript согласованность                   │   │
│  │  temporal предсказуемость в видео                    │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              HypothesisEngine                        │   │
│  │  генерация гипотез → проверка → принятие/отклонение  │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              KnowledgeGapDetector                    │   │
│  │  что мозг не знает? → создать цели для изучения      │   │
│  └──────────────────────┬───────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
              LearningUpdate(s)
  {updated_facts, new_associations, gap_goals, hypothesis_results}
                          │
                          ├──► Memory System (обновить)
                          └──► Planner (новые цели для изучения)
```

---

## Компонент 1: `OnlineLearner` — Онлайн-обучение

**Файл:** `brain/learning/online_learner.py`  
**Аналог:** Мозжечок — мгновенная коррекция после каждого действия

### Принцип работы

```
После каждого цикла мышления (CognitiveResult):
    │
    ▼
OnlineLearner.update(cognitive_result)
    │
    ├── 1. Обновить confidence фактов
    │       если action=RESPOND и пользователь подтвердил → confirm_fact()
    │       если пользователь опроверг → deny_fact()
    │
    ├── 2. Обновить ассоциации в SemanticMemory
    │       все понятия из reasoning_trace → усилить связи между ними
    │       Δweight = learning_rate × co_activation_strength
    │
    ├── 3. Обновить trust источников
    │       если факт подтверждён → source_trust += 0.02
    │       если факт опровергнут → source_trust -= 0.05
    │
    ├── 4. Обновить success_rate процедур
    │       ProceduralMemory.update_success(procedure_name, success, duration_ms)
    │
    └── 5. Обновить проекционные матрицы (SharedSpaceProjector)
            если есть новые пары (текст, изображение) → mini-batch update
            lr = 0.0001, batch_size = 1 (онлайн)
```

### Хеббовское обучение для ассоциаций

```
"Нейроны, которые активируются вместе — связываются сильнее"

Если в одном reasoning_trace встретились понятия A и B:
  current_weight = semantic.get_relation_weight(A, B)
  Δweight = learning_rate × activation_A × activation_B
  new_weight = clip(current_weight + Δweight, 0.0, 1.0)
  semantic.update_relation(A, B, new_weight)

learning_rate = 0.01  (медленное обучение для стабильности)
```

### Структура `OnlineLearningUpdate`

```python
@dataclass
class OnlineLearningUpdate:
    cycle_id: str                    # ID цикла мышления
    facts_confirmed: List[str]       # подтверждённые концепты
    facts_denied: List[str]          # опровергнутые концепты
    associations_updated: List[dict] # [{A, B, old_weight, new_weight}]
    sources_updated: List[dict]      # [{source, old_trust, new_trust}]
    procedures_updated: List[dict]   # [{name, success, new_rate}]
    projections_updated: bool        # обновлены ли матрицы проекций
    duration_ms: float
```

---

## Компонент 2: `ReplayEngine` — Воспроизведение эпизодов

**Файл:** `brain/learning/replay_engine.py`  
**Аналог:** Гиппокамп во время сна — консолидация через replay

### Принцип работы

```
Периодически (каждые N минут или при низкой нагрузке CPU):
    │
    ▼
ReplayEngine.run_replay_session()
    │
    ├── 1. Выбрать эпизоды для replay:
    │       - высокая важность (importance > 0.7)
    │       - часто запрашиваемые (access_count > 5)
    │       - недавно добавленные (< 24 часов)
    │       - случайная выборка (для разнообразия)
    │
    ├── 2. Для каждого эпизода:
    │       a. Извлечь факты и ассоциации
    │       b. Проверить согласованность с текущей SemanticMemory
    │       c. Если согласован → усилить (confidence += 0.01)
    │       d. Если противоречит → флаг для ContradictionDetector
    │       e. Если устарел → снизить importance
    │
    └── 3. Удалить "шум":
            эпизоды с importance < 0.1 AND access_count == 0
            AND age > 7 дней → удалить
```

### Стратегии выбора эпизодов для replay

```python
class ReplayStrategy(Enum):
    IMPORTANCE_BASED  = "importance"   # самые важные
    RECENCY_BASED     = "recency"      # самые свежие
    FREQUENCY_BASED   = "frequency"    # самые часто запрашиваемые
    RANDOM            = "random"       # случайные (для генерализации)
    CONTRADICTION     = "contradiction" # эпизоды с противоречиями
    GAP_FILLING       = "gap_filling"  # эпизоды по пробелам знаний
```

### Расписание replay

```
Триггеры для запуска replay:
  1. CPU < 30% в течение 5 минут → запустить replay (idle time)
  2. Каждые 30 минут → короткий replay (10 эпизодов)
  3. Каждые 6 часов → полный replay (100 эпизодов)
  4. При явном вызове mm.force_replay()
```

---

## Компонент 3: `SelfSupervisedLearner` — Самообучение

**Файл:** `brain/learning/self_supervised.py`  
**Аналог:** Кора — обучение без учителя на внутренних сигналах

### Принцип работы

Самообучение использует **внутренние сигналы согласованности** вместо внешних меток:

#### 3.1 Text-Image согласованность
```
Текст T описывает изображение I?
    │
    ▼
sim(proj_text(T), proj_image(I)) → score
    │
    ├── score > 0.8 → СОГЛАСОВАНЫ
    │   → positive pair → обновить W_text, W_image (contrastive loss)
    │
    └── score < 0.3 → НЕ СОГЛАСОВАНЫ
        → negative pair → обновить (отталкивать)
```

#### 3.2 Audio-Transcript согласованность
```
Транскрипт Whisper T соответствует аудио A?
    │
    ▼
Whisper confidence > 0.85 → высокое качество транскрипта
    │
    ├── Использовать как positive pair (audio, transcript)
    └── Обновить AudioEncoder (если обучаемый)
```

#### 3.3 Temporal предсказуемость (для видео)
```
Кадр t предсказывает кадр t+1?
    │
    ▼
sim(frame_t, frame_t+1) → temporal_coherence
    │
    ├── coherence > 0.7 → плавное видео → нормально
    └── coherence < 0.3 → резкая смена → ключевой момент
        → создать отдельный эпизод для этого момента
```

#### 3.4 Cross-session согласованность
```
Факт из сессии 1 согласован с фактом из сессии 2?
    │
    ▼
Если согласован → confidence обоих += 0.03
Если противоречит → ContradictionDetector.flag()
```

---

## Компонент 4: `HypothesisEngine` — Генератор гипотез

**Файл:** `brain/learning/hypothesis_engine.py`  
**Аналог:** Префронтальная кора — научный метод внутри мозга

### Принцип работы

```
Мозг замечает паттерн или пробел в знаниях
    │
    ▼
HypothesisEngine.generate(observation)
    │
    ▼
Hypothesis(
    statement="нейроны, возможно, связаны с памятью",
    confidence=0.4,  # начальная уверенность низкая
    evidence_for=[],
    evidence_against=[],
    status="unverified"
)
    │
    ▼
Planner.push_goal("verify_hypothesis", hypothesis)
    │
    ▼
При следующих взаимодействиях:
    ├── Найдено подтверждение → evidence_for.append() → confidence += 0.1
    └── Найдено опровержение → evidence_against.append() → confidence -= 0.15
    │
    ▼
Если confidence > 0.75 → ACCEPTED → store_fact(semantic_memory)
Если confidence < 0.15 → REJECTED → удалить гипотезу
Иначе                  → PENDING  → продолжать проверку
```

### Структура `Hypothesis`

```python
@dataclass
class Hypothesis:
    hypothesis_id: str          # "hyp_a1b2c3"
    statement: str              # "нейроны связаны с памятью"
    generated_from: str         # "observation" | "gap" | "analogy" | "contradiction"
    confidence: float           # 0.0–1.0 (обновляется по мере проверки)
    evidence_for: List[str]     # ссылки на подтверждающие факты
    evidence_against: List[str] # ссылки на опровергающие факты
    status: str                 # "unverified" | "accepted" | "rejected" | "pending"
    created_at: str
    last_updated: str
    verification_count: int     # сколько раз проверялась
```

---

## Компонент 5: `KnowledgeGapDetector` — Детектор пробелов

**Файл:** `brain/learning/gap_detector.py`  
**Аналог:** Метакогниция — "я знаю, что я не знаю"

### Принцип работы

```
После каждого retrieve() из памяти:
    │
    ▼
KnowledgeGapDetector.analyze(query, search_result)
    │
    ├── result.total == 0 → ПОЛНЫЙ ПРОБЕЛ
    │   → gap = KnowledgeGap(concept=query, severity="high")
    │   → Planner.push_goal("learn_fact", concept=query)
    │
    ├── result.semantic[0].confidence < 0.5 → СЛАБОЕ ЗНАНИЕ
    │   → gap = KnowledgeGap(concept=query, severity="medium")
    │   → Planner.push_goal("verify_claim", concept=query)
    │
    ├── result.semantic[0].updated_at > 30 дней → УСТАРЕВШЕЕ ЗНАНИЕ
    │   → gap = KnowledgeGap(concept=query, severity="low")
    │   → пометить для обновления
    │
    └── Нет кросс-модальных доказательств → ОДНОМОДАЛЬНОЕ ЗНАНИЕ
        → gap = KnowledgeGap(concept=query, severity="low", type="modal")
        → предпочесть источники с изображениями/аудио
```

### Структура `KnowledgeGap`

```python
@dataclass
class KnowledgeGap:
    gap_id: str             # "gap_a1b2c3"
    concept: str            # "квантовая механика"
    severity: str           # "high" | "medium" | "low"
    gap_type: str           # "missing" | "weak" | "outdated" | "modal"
    detected_at: str        # timestamp
    resolution_goal_id: str # ID цели для устранения пробела
    resolved: bool          # устранён ли пробел
```

---

## Полный цикл обучения

```
Взаимодействие:
  Пользователь: "Нейроны — это клетки мозга"
  Мозг: "Запомнил"
      │
      ▼
[OnlineLearner]
  store_fact("нейрон", "клетка мозга", confidence=0.8)
  update_association("нейрон", "мозг", Δweight=+0.01)
  update_source_trust("user_input", confirmed=True)
      │
      ▼
[KnowledgeGapDetector]
  retrieve("нейрон") → confidence=0.8 → OK
  retrieve("мозг") → confidence=0.6 → СЛАБОЕ ЗНАНИЕ
  → gap = KnowledgeGap("мозг", severity="medium")
  → Planner.push_goal("verify_claim", "мозг")
      │
      ▼
[HypothesisEngine]
  Наблюдение: "нейрон" и "мозг" часто встречаются вместе
  → Hypothesis("нейроны — основной компонент мозга", confidence=0.5)
      │
      ▼
[ReplayEngine] (через 30 минут, при CPU < 30%)
  Replay эпизода "нейрон — клетка мозга"
  Согласован с SemanticMemory → confidence += 0.01 → 0.81
      │
      ▼
[SelfSupervisedLearner] (если есть изображение нейрона)
  sim(text_proj("нейрон клетка мозга"), image_proj(фото_нейрона)) = 0.87
  → positive pair → обновить W_text (lr=0.0001)
```

---

## Метрики качества обучения

```python
class LearningMetrics:
    """Метрики для оценки качества обучения."""
    
    knowledge_growth_rate: float      # прирост фактов в день
    avg_confidence_delta: float       # среднее изменение confidence за сессию
    contradiction_resolution_rate: float  # % разрешённых противоречий
    hypothesis_acceptance_rate: float # % принятых гипотез
    gap_closure_rate: float           # % устранённых пробелов
    replay_reinforcement_rate: float  # % фактов, усиленных через replay
    cross_modal_coverage: float       # % фактов с кросс-модальными доказательствами
```

---

## Ресурсный бюджет (CPU-only, 32 GB RAM)

| Компонент | RAM | CPU | Частота |
|-----------|-----|-----|---------|
| OnlineLearner | ~5 MB | 1 поток | каждый цикл (~100–200 мс) |
| ReplayEngine | ~20 MB | 1–2 потока | каждые 30 мин (idle) |
| SelfSupervisedLearner | ~50 MB | 2–4 потока | каждые 10 мин |
| HypothesisEngine | ~5 MB | 1 поток | по событию |
| KnowledgeGapDetector | ~2 MB | 1 поток | каждый retrieve() |
| **Итого** | **~82 MB** | **2–4 потока** | — |

---

## Статус реализации

| Компонент | Статус | Файл |
|-----------|--------|------|
| `OnlineLearner` | ✅ Реализовано (Этап I) | `brain/learning/online_learner.py` |
| `ReplayEngine` | ✅ Реализовано (Этап I) | `brain/learning/replay_engine.py` |
| `KnowledgeGapDetector` | ✅ Реализовано (Этап I) | `brain/learning/knowledge_gap_detector.py` |
| `SelfSupervisedLearner` | ⬜ Post-MVP | `brain/learning/self_supervised.py` |
| `HypothesisEngine` | ✅ Реализовано (Этап F+) | `brain/cognition/hypothesis_engine.py` |
| `LearningMetrics` | ⬜ Post-MVP | `brain/learning/metrics.py` |

---

## Итог: место Learning Loop в системе

```
Cognitive Core → [LEARNING LOOP] → Memory System (обновить)
                       │           Planner (новые цели)
                       │
                       ├── OnlineLearner:    учиться после каждого цикла
                       ├── ReplayEngine:     укреплять во время простоя
                       ├── SelfSupervised:   учиться без учителя
                       ├── HypothesisEngine: генерировать и проверять гипотезы
                       └── GapDetector:      знать, чего не знаешь
```

**Learning Loop — это то, что превращает мозг из статической базы знаний в живую систему, которая становится умнее с каждым взаимодействием.**
