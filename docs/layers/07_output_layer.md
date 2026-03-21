# 🧠 Слой 7: Output Layer (Речевые зоны + Моторная кора)
## Подробное описание архитектуры и работы

> **Статус: ⬜ Фаза 10 — не реализовано**

---

## Что такое Output Layer в биологии

В человеческом мозге выходной слой — это несколько специализированных зон:

| Биологическая структура | Функция | Аналог |
|------------------------|---------|--------|
| **Зона Брока** | Формирование речи, грамматика | `DialogueResponder` |
| **Моторная кора** | Управление действиями | `ActionProposer` |
| **Передняя поясная кора** | Мониторинг ошибок в ответе | `ResponseValidator` |
| **Угловая извилина** | Интеграция смысла в слова | `TraceBuilder` |

Output Layer — это **последний шаг**: взять результат рассуждения и превратить его в понятный, объяснимый, проверенный ответ.

---

## Роль в искусственном мозге

```
CognitiveResult от Cognitive Core
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    OUTPUT LAYER                             │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              TraceBuilder                            │   │
│  │  собирает полную цепочку причинности:                │   │
│  │  источники → факты → рассуждение → решение           │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              ResponseValidator                       │   │
│  │  проверяет ответ перед отправкой:                    │   │
│  │  полнота, согласованность, безопасность              │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              DialogueResponder                       │   │
│  │  формирует текстовый ответ с учётом:                 │   │
│  │  confidence, стиля, языка, контекста диалога         │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              ActionProposer                          │   │
│  │  предлагает действия (не только текст):              │   │
│  │  сохранить файл, запросить данные, обновить факт     │   │
│  └──────────────────────┬───────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
                  BrainOutput
    {text_response, actions, trace, confidence, digest}
                          │
                          ├──► Пользователь (текст)
                          ├──► Learning Loop (обратная связь)
                          └──► Логгер (JSONL + digest)
```

---

## Компонент 1: `TraceBuilder` — Построитель трассировки

**Файл:** `brain/output/trace_builder.py`  
**Аналог:** Угловая извилина — интеграция всех источников в единый смысл

### Принцип работы

```
CognitiveResult содержит:
  - memory_refs:    ["semantic:нейрон", "episodic:ep_001"]
  - source_refs:    ["docs/нейрон.pdf#p1", "user_input"]
  - reasoning_trace: [шаг_1, шаг_2, шаг_3]
  - contradictions: []
  - uncertainty:    UncertaintyReport(level="medium")
    │
    ▼
TraceBuilder.build(cognitive_result)
    │
    ▼
ExplainabilityTrace(
    input_sources=[...],      # откуда пришли данные
    memory_facts=[...],       # какие факты использованы
    reasoning_chain=[...],    # как рассуждал
    decision=[...],           # почему выбрано это действие
    confidence=0.78,          # итоговая уверенность
    uncertainty_sources=[...] # почему не 1.0
)
```

### Структура `ExplainabilityTrace`

```python
@dataclass
class ExplainabilityTrace:
    trace_id: str                      # "trace_a1b2c3"
    session_id: str
    cycle_id: str

    # Входные данные
    input_query: str                   # исходный вопрос
    input_modalities: List[str]        # ["text", "image"]

    # Источники
    input_sources: List[SourceRef]     # откуда пришли данные
    memory_facts: List[FactRef]        # какие факты из памяти использованы
    modal_evidence: List[ModalRef]     # кросс-модальные доказательства

    # Рассуждение
    reasoning_type: str                # "associative" | "causal" | ...
    reasoning_chain: List[str]         # ["нейрон", "→", "клетка", "→", "организм"]
    key_inferences: List[str]          # ключевые умозаключения

    # Решение
    action_taken: str                  # "respond_hedged"
    action_reason: str                 # почему выбрано это действие
    alternatives_considered: List[str] # другие рассмотренные варианты

    # Качество
    confidence: float                  # итоговая уверенность
    uncertainty_level: str             # "high" | "medium" | "low" | "very_low"
    uncertainty_reasons: List[str]     # причины неопределённости
    contradictions_found: List[str]    # найденные противоречия

    # Метаданные
    total_duration_ms: float
    created_at: str
```

### Форматы трассировки

#### Machine format (JSONL):
```json
{
  "ts": "2026-03-19T12:00:00.123Z",
  "level": "INFO",
  "module": "output_layer",
  "event": "response_generated",
  "session_id": "sess_01",
  "cycle_id": "cycle_4521",
  "trace_id": "trace_9fa",
  "input_ref": ["user_input", "semantic:нейрон"],
  "state": {"goal": "answer_question", "cpu_pct": 45, "ram_mb": 3800},
  "decision": {"action": "respond_hedged", "confidence": 0.78},
  "reasoning": ["нейрон", "→", "клетка", "→", "нервная система"],
  "latency_ms": 142,
  "notes": "medium confidence, hedging applied"
}
```

#### Human digest format:
```
Cycle 4521
  Query:        "Что такое нейрон?"
  Goal:         answer_question
  Memory used:  semantic:нейрон (conf=0.87), episodic:ep_001
  Sources:      docs/нейробиология.pdf (trust=0.87)
  Reasoning:    associative [нейрон → клетка → нервная система]
  Contradiction: none
  Confidence:   0.78 (medium) → hedged response
  Action:       respond_hedged
  Duration:     142ms | CPU: 45% | RAM: 3.8 GB
```

---

## Компонент 2: `ResponseValidator` — Валидатор ответа

**Файл:** `brain/output/response_validator.py`  
**Аналог:** Передняя поясная кора — мониторинг ошибок перед выводом

### Проверки перед отправкой ответа

```
Сформированный ответ R
    │
    ▼
ResponseValidator.validate(R, cognitive_result)
    │
    ├── 1. Проверка полноты:
    │       ответ не пустой?
    │       ответ отвечает на вопрос?
    │       → если нет → INCOMPLETE → запросить повторное рассуждение
    │
    ├── 2. Проверка согласованности:
    │       ответ не противоречит фактам в памяти?
    │       → если противоречит → INCONSISTENT → добавить оговорку
    │
    ├── 3. Проверка уверенности:
    │       confidence соответствует тону ответа?
    │       confidence=0.4 но ответ звучит уверенно → MISMATCH
    │       → добавить hedging phrases
    │
    ├── 4. Проверка безопасности:
    │       нет ли в ответе приватных данных?
    │       нет ли потенциально вредного контента?
    │       → если есть → REDACT → удалить/заменить
    │
    └── 5. Проверка языка:
            язык ответа соответствует языку вопроса?
            → если нет → LANGUAGE_MISMATCH → перевести
```

### Структура `ValidationResult`

```python
@dataclass
class ValidationResult:
    is_valid: bool                     # прошёл ли ответ все проверки
    issues: List[ValidationIssue]      # найденные проблемы
    corrected_response: str            # исправленный ответ (если нужно)
    applied_corrections: List[str]     # что было исправлено

@dataclass
class ValidationIssue:
    issue_type: str    # "incomplete" | "inconsistent" | "mismatch" | "unsafe" | "language"
    severity: str      # "critical" | "warning" | "info"
    description: str   # описание проблемы
    correction: str    # как исправлено
```

---

## Компонент 3: `DialogueResponder` — Формирователь ответа

**Файл:** `brain/output/dialogue_responder.py`  
**Аналог:** Зона Брока — формирование речи

### Принцип работы

```
CognitiveResult + ExplainabilityTrace + ValidationResult
    │
    ▼
DialogueResponder.generate(...)
    │
    ├── 1. Выбрать шаблон ответа по action_type:
    │
    │   RESPOND_DIRECT:
    │     "{conclusion}"
    │
    │   RESPOND_HEDGED (confidence 0.6–0.85):
    │     "Вероятно, {conclusion}. Уверенность: {confidence:.0%}."
    │
    │   RESPOND_LOW_CONFIDENCE (confidence < 0.6):
    │     "Я не уверен, но возможно {conclusion}. "
    │     "Рекомендую проверить в источнике: {source}."
    │
    │   ASK_CLARIFICATION:
    │     "Уточните, пожалуйста: {clarification_question}"
    │
    │   REFUSE:
    │     "У меня недостаточно данных для ответа на этот вопрос."
    │     "Пробел в знаниях: {missing_concepts}"
    │
    ├── 2. Добавить контекст из трассировки (опционально):
    │     "Источник: {source_ref} | Уверенность: {confidence:.0%}"
    │
    └── 3. Адаптировать под язык:
          язык вопроса = "ru" → ответ на русском
          язык вопроса = "en" → ответ на английском
          язык вопроса = "mixed" → ответ на языке большинства
```

### Hedging phrases (фразы неопределённости)

```python
HEDGING_BY_CONFIDENCE = {
    (0.75, 1.00): [],                                    # без оговорок
    (0.60, 0.75): ["Вероятно,", "Скорее всего,"],
    (0.45, 0.60): ["Возможно,", "Я думаю,", "Мне кажется,"],
    (0.30, 0.45): ["Не уверен, но,", "Предположительно,"],
    (0.00, 0.30): ["Очень неуверенно:", "Это лишь предположение:"],
}

HEDGING_BY_CONFIDENCE_EN = {
    (0.75, 1.00): [],
    (0.60, 0.75): ["Probably,", "Most likely,"],
    (0.45, 0.60): ["Perhaps,", "I think,", "It seems,"],
    (0.30, 0.45): ["I'm not sure, but,", "Presumably,"],
    (0.00, 0.30): ["Very uncertain:", "This is just a guess:"],
}
```

### Примеры ответов

```
Вопрос: "Что такое нейрон?"
confidence=0.87 → RESPOND_DIRECT:
  "Нейрон — это основная клетка нервной системы, которая
   передаёт электрические сигналы."

confidence=0.65 → RESPOND_HEDGED:
  "Вероятно, нейрон — это клетка нервной системы.
   [Уверенность: 65% | Источник: нейробиология.pdf]"

confidence=0.35 → RESPOND_LOW_CONFIDENCE:
  "Я не уверен, но возможно нейрон связан с нервной системой.
   Рекомендую проверить в источнике: нейробиология.pdf, стр. 12."

confidence=0.15 → REFUSE:
  "У меня недостаточно данных для точного ответа.
   Пробел в знаниях: 'нейрон'. Могу поискать дополнительную информацию."
```

---

## Компонент 4: `ActionProposer` — Предложение действий

**Файл:** `brain/output/action_proposer.py`  
**Аналог:** Моторная кора — инициация действий

### Типы предлагаемых действий

```python
class ProposedAction:
    """Действие, которое мозг предлагает выполнить."""
    
    action_type: str    # тип действия
    description: str    # описание
    params: Dict        # параметры
    priority: float     # приоритет 0.0–1.0
    reason: str         # почему предлагается
```

### Каталог действий

```
MEMORY_ACTIONS:
  save_fact(concept, description)     — сохранить новый факт
  update_fact(concept, new_desc)      — обновить существующий факт
  delete_fact(concept)                — удалить устаревший факт
  add_association(A, B, weight)       — добавить ассоциацию

FILE_ACTIONS:
  read_file(path)                     — прочитать файл
  write_file(path, content)           — записать файл
  index_directory(path)               — проиндексировать директорию

DIALOGUE_ACTIONS:
  ask_user(question)                  — задать вопрос пользователю
  confirm_fact(concept)               — попросить подтвердить факт
  request_source(concept)             — попросить источник

LEARNING_ACTIONS:
  trigger_replay()                    — запустить replay
  verify_hypothesis(hyp_id)           — проверить гипотезу
  close_gap(concept)                  — устранить пробел в знаниях

SYSTEM_ACTIONS:
  save_memory()                       — сохранить память на диск
  report_status()                     — отчёт о состоянии
  adjust_confidence(concept, delta)   — скорректировать уверенность
```

### Пример предложения действий

```python
# После ответа на вопрос о нейронах:
proposed_actions = [
    ProposedAction(
        action_type="save_fact",
        description="Сохранить факт о нейроне",
        params={"concept": "нейрон", "description": "клетка нервной системы"},
        priority=0.8,
        reason="Новый факт с высокой уверенностью"
    ),
    ProposedAction(
        action_type="add_association",
        description="Связать нейрон и синапс",
        params={"A": "нейрон", "B": "синапс", "weight": 0.85},
        priority=0.6,
        reason="Часто встречаются вместе в контексте"
    ),
    ProposedAction(
        action_type="close_gap",
        description="Изучить подробнее: аксон",
        params={"concept": "аксон"},
        priority=0.4,
        reason="Связан с нейроном, но confidence=0.3"
    ),
]
```

---

## Выходной формат: `BrainOutput`

```python
@dataclass
class BrainOutput:
    # Идентификаторы
    output_id: str              # "out_a1b2c3"
    session_id: str
    cycle_id: str
    trace_id: str

    # Основной ответ
    text_response: str          # текстовый ответ пользователю
    response_language: str      # "ru" | "en"
    confidence: float           # итоговая уверенность 0.0–1.0
    uncertainty_level: str      # "high" | "medium" | "low" | "very_low"

    # Объяснимость
    trace: ExplainabilityTrace  # полная цепочка причинности
    digest: str                 # человекочитаемый digest

    # Действия
    proposed_actions: List[ProposedAction]  # предлагаемые действия

    # Метаданные
    action_taken: str           # "respond_direct" | "respond_hedged" | ...
    validation_passed: bool     # прошёл ли валидацию
    corrections_applied: List[str]  # что было исправлено

    # Производительность
    total_duration_ms: float    # общее время от вопроса до ответа
    created_at: str             # ISO timestamp
```

---

## Полный пример вывода

```python
brain_output = BrainOutput(
    text_response="Вероятно, нейрон — это основная клетка нервной системы, "
                  "которая передаёт электрические сигналы между клетками мозга.",
    confidence=0.78,
    uncertainty_level="medium",

    trace=ExplainabilityTrace(
        input_query="Что такое нейрон?",
        input_sources=[SourceRef("user_input", trust=0.8)],
        memory_facts=[
            FactRef("semantic:нейрон", "клетка нервной системы", conf=0.87),
        ],
        reasoning_chain=["нейрон", "→", "клетка", "→", "нервная система"],
        action_taken="respond_hedged",
        action_reason="confidence=0.78 → medium → hedging applied",
        confidence=0.78,
        uncertainty_reasons=["single_source", "no_cross_modal_evidence"],
        total_duration_ms=142.3,
    ),

    digest="""
Cycle 4521
  Query:        "Что такое нейрон?"
  Memory used:  semantic:нейрон (conf=0.87)
  Sources:      user_input (trust=0.80)
  Reasoning:    associative [нейрон → клетка → нервная система]
  Confidence:   0.78 (medium) → hedged
  Duration:     142ms | CPU: 45% | RAM: 3.8 GB
    """,

    proposed_actions=[
        ProposedAction("save_fact", priority=0.8, ...),
        ProposedAction("close_gap", params={"concept": "синапс"}, priority=0.4, ...),
    ],

    total_duration_ms=142.3,
)
```

---

## Поток данных: от вопроса до ответа (полный путь)

```
Пользователь: "Что такое нейрон?"
      │
      ▼  [Слой 1: Таламус]
PerceptEvent(text, "Что такое нейрон?", source="user_input")
      │
      ▼  [Слой 2: Сенсорная кора]
EncodedPercept(vector=768d, keywords=["нейрон"], type="question")
      │
      ▼  [Слой 3: Ассоциативная кора]
FusedPercept(unified_vector=512d, confidence=0.8, entity_clusters=[])
      │
      ▼  [Слой 4: Memory System]
MemorySearchResult(semantic=[нейрон→клетка], episodic=[ep_001])
      │
      ▼  [Слой 5: Cognitive Core]
CognitiveResult(action=respond_hedged, confidence=0.78,
                reasoning=[нейрон→клетка→нервная система])
      │
      ▼  [Слой 6: Learning Loop]
OnlineLearningUpdate(associations_updated=[нейрон↔клетка])
      │
      ▼  [Слой 7: Output Layer]
BrainOutput(
  text="Вероятно, нейрон — это основная клетка нервной системы...",
  confidence=0.78,
  trace=ExplainabilityTrace(...),
  digest="Cycle 4521 | 142ms | CPU: 45%"
)
      │
      ▼
Пользователь получает ответ
Логгер записывает JSONL
Learning Loop получает обратную связь
```

---

## Наблюдаемость (Observability)

Output Layer — **единственное место**, где формируются все логи:

```
brain/logs/
    ├── brain.jsonl          — все события (machine format)
    ├── cognitive.jsonl      — только cognitive events
    ├── memory.jsonl         — только memory events
    ├── errors.jsonl         — только ошибки
    └── digests/
        ├── 2026-03-19.txt   — человекочитаемые дайджесты по дням
        └── session_01.txt   — дайджест по сессии
```

**Ротация логов:**
- `brain.jsonl` → ротация при > 100 MB
- Архив: `brain_2026-03-19.jsonl.gz`
- Хранение: последние 30 дней

---

## Ресурсный бюджет (CPU-only, 32 GB RAM)

| Компонент | RAM | CPU | Время/запрос |
|-----------|-----|-----|--------------|
| TraceBuilder | ~2 MB | 1 поток | ~5–10 мс |
| ResponseValidator | ~1 MB | 1 поток | ~2–5 мс |
| DialogueResponder | ~1 MB | 1 поток | ~1–3 мс |
| ActionProposer | ~1 MB | 1 поток | ~1–2 мс |
| Logger (JSONL) | ~5 MB | 1 поток | ~1 мс |
| **Итого** | **~10 MB** | **1–2 потока** | **~10–20 мс** |

---

## Статус реализации

| Компонент | Статус | Файл |
|-----------|--------|------|
| `ExplainabilityTrace` dataclass | ⬜ Фаза 10.0 | `brain/core/events.py` (расширить) |
| `BrainOutput` dataclass | ⬜ Фаза 10.0 | `brain/core/events.py` (расширить) |
| `TraceBuilder` | ⬜ Фаза 10.1 | `brain/output/trace_builder.py` |
| `ResponseValidator` | ⬜ Фаза 10.2 | `brain/output/response_validator.py` |
| `DialogueResponder` | ⬜ Фаза 10.3 | `brain/output/dialogue_responder.py` |
| `ActionProposer` | ⬜ Фаза 10.4 | `brain/output/action_proposer.py` |
| `BrainLogger` (JSONL) | ⬜ Фаза 2.1 | `brain/logging/brain_logger.py` |

---

## Итог: место Output Layer в системе

```
Learning Loop → [OUTPUT LAYER] → Пользователь
                     │           Логгер
                     │           Learning Loop (обратная связь)
                     │
                     ├── TraceBuilder:      "почему я так решил"
                     ├── ResponseValidator: "правильно ли я отвечаю"
                     ├── DialogueResponder: "как это сказать"
                     └── ActionProposer:    "что ещё нужно сделать"
```

**Output Layer — это голос мозга. Он не просто выдаёт ответ, он объясняет его, проверяет его и предлагает следующие шаги. Никаких "магических" ответов без trace chain.**
