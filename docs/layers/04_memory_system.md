# 🧠 Слой 4: Memory System (Система памяти)
## Подробное описание архитектуры и работы

> **Статус: ✅ ПОЛНОСТЬЮ РЕАЛИЗОВАНО** — 101/101 тестов пройдено

---

## Что такое память в биологии

В человеческом мозге память — это **не одна структура**, а несколько специализированных систем:

| Биологическая структура | Функция | Аналог в мозге |
|------------------------|---------|----------------|
| **Гиппокамп** | Формирование новых воспоминаний, перенос в LTM | `ConsolidationEngine` |
| **Префронтальная кора** | Рабочая память, активный контекст | `WorkingMemory` |
| **Височная кора** | Семантическая память (факты, понятия) | `SemanticMemory` |
| **Гиппокамп + кора** | Эпизодическая память (события) | `EpisodicMemory` |
| **Базальные ганглии + мозжечок** | Процедурная память (навыки) | `ProceduralMemory` |
| **Префронтальная кора** | Оценка достоверности источников | `SourceMemory` |

---

## Общая архитектура

```
FusedPercept от Ассоциативной коры
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    MEMORY SYSTEM                            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              MemoryManager (диспетчер)              │    │
│  │         единая точка входа store() / retrieve()     │    │
│  └──────────────────────┬──────────────────────────────┘    │
│                         │                                   │
│         ┌───────────────┼───────────────────┐               │
│         │               │                   │               │
│         ▼               ▼                   ▼               │
│  ┌─────────────┐ ┌─────────────┐   ┌──────────────┐        │
│  │  Working    │ │  Semantic   │   │  Episodic    │        │
│  │  Memory     │ │  Memory     │   │  Memory      │        │
│  │  (RAM-only) │ │  (JSON)     │   │  (JSON)      │        │
│  └──────┬──────┘ └─────────────┘   └──────────────┘        │
│         │                                                   │
│         │  ┌──────────────────────────────────────────┐     │
│         └─►│   ConsolidationEngine (Гиппокамп)        │     │
│            │   фоновый daemon-поток                   │     │
│            │   каждые 30с: WM → Episodic/Semantic     │     │
│            │   каждые 5мин: decay                     │     │
│            │   каждые 2мин: autosave JSON             │     │
│            └──────────────────────────────────────────┘     │
│                                                             │
│  ┌─────────────┐   ┌─────────────────────────────────┐      │
│  │  Source     │   │  Procedural Memory              │      │
│  │  Memory     │   │  (навыки и стратегии)           │      │
│  │  (JSON)     │   │  (JSON)                         │      │
│  └─────────────┘   └─────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
  Cognitive Core (Слой 5)
```

---

## Компонент 1: `WorkingMemory` — Рабочая память

**Файл:** `brain/memory/working_memory.py`  
**Аналог:** Префронтальная кора — активный контекст «прямо сейчас»

### Принцип работы

```
Новый элемент → push()
    │
    ├── importance >= 0.8 → PROTECTED LIST (не вытесняется)
    │   max_protected = max(5, max_size // 4)
    │
    └── importance < 0.8 → SLIDING WINDOW (deque)
        │
        └── если len(deque) >= effective_max → evict_oldest()
```

### Ключевые параметры

| Параметр | Значение | Описание |
|----------|----------|----------|
| `max_size` | 20 | Максимум элементов в sliding window |
| `IMPORTANCE_PROTECT_THRESHOLD` | 0.8 | Порог защиты от вытеснения |
| `RAM_LIMIT_PCT` | 80% | При превышении — уменьшить окно |

### Адаптация под RAM (resource-aware)

```python
def _adaptive_max_size() -> int:
    ram_pct = psutil.virtual_memory().percent

    if ram_pct > 80%:   return max(2, max_size // 2)   # 50% от лимита
    if ram_pct > 68%:   return max(3, max_size * 0.75) # 75% от лимита
    else:               return max_size                 # полный лимит
```

### Структура `MemoryItem`

```python
@dataclass
class MemoryItem:
    content: Any          # содержимое (текст, факт, объект)
    modality: str         # 'text' | 'image' | 'audio' | 'concept'
    ts: float             # время добавления (unix timestamp)
    importance: float     # 0.0–1.0 (>= 0.8 → защищён)
    source_ref: str       # "docs/нейрон.pdf#p1", "user_input"
    tags: List[str]       # ["нейрон", "биология"]
    access_count: int     # сколько раз обращались
```

### API

```python
wm = WorkingMemory(max_size=20)

# Добавить элемент
item = wm.push("нейрон — клетка нервной системы", importance=0.7)

# Получить контекст (последние N элементов)
context = wm.get_context(n=10)

# Поиск по содержимому
results = wm.search("нейрон", modality="text", top_n=5)

# Статус
wm.display_status()
# → 15 обычных + 3 защищённых (лимит: 20)
```

---

## Компонент 2: `SemanticMemory` — Семантическая память

**Файл:** `brain/memory/semantic_memory.py`  
**Аналог:** Височная кора — долговременные факты и понятия

### Принцип работы

```
Граф понятий:
  "нейрон" ──[is_a]──► "клетка"
      │
      ├──[part_of]──► "нервная система"
      │
      └──[related]──► "синапс"
                          │
                          └──[related]──► "аксон"

Поиск: BFS от стартового узла → цепочка понятий
```

### Структура `SemanticNode`

```python
@dataclass
class SemanticNode:
    concept: str          # "нейрон"
    description: str      # "основная клетка нервной системы"
    tags: List[str]       # ["биология", "нейронаука"]
    confidence: float     # 0.0–1.0 (снижается со временем через decay)
    importance: float     # 0.0–1.0
    source_ref: str       # откуда пришёл факт
    access_count: int     # сколько раз запрашивался
    created_at: str       # ISO timestamp
    updated_at: str       # ISO timestamp
    relations: List[Relation]  # связи с другими понятиями
```

### Структура `Relation`

```python
@dataclass
class Relation:
    target: str           # "клетка"
    relation_type: str    # "is_a" | "part_of" | "related" | "opposite"
    weight: float         # 0.0–1.0 (сила связи)
```

### Персистентность

```
brain/data/memory/semantic.json
    │
    ├── Автосохранение каждые 50 записей
    ├── Принудительное сохранение через save()
    └── Загрузка при инициализации
```

### API

```python
sm = SemanticMemory(data_path="brain/data/memory/semantic.json")

# Сохранить факт
node = sm.store_fact("нейрон", "основная клетка нервной системы",
                     tags=["биология"], confidence=0.9)

# Получить факт
node = sm.get_fact("нейрон")

# Поиск
results = sm.search("клетка", top_n=5, min_confidence=0.5)

# BFS-цепочка понятий
chain = sm.get_concept_chain("нейрон", max_depth=3)
# → ["нейрон", "клетка", "организм"]

# Связанные понятия
related = sm.get_related("нейрон", top_n=10)

# Подтвердить / опровергнуть факт
sm.confirm_fact("нейрон")  # confidence += 0.05
sm.deny_fact("нейрон")     # confidence -= 0.1

# Decay (вызывается ConsolidationEngine)
sm.apply_decay(rate=0.003)
```

---

## Компонент 3: `EpisodicMemory` — Эпизодическая память

**Файл:** `brain/memory/episodic_memory.py`  
**Аналог:** Гиппокамп + кора — хронология событий

### Принцип работы

```
Хронологический список эпизодов:
  [ep_001] 2026-03-19 12:00 — "Пользователь спросил о нейронах"
  [ep_002] 2026-03-19 12:01 — "Найден факт: нейрон — клетка"
  [ep_003] 2026-03-19 12:02 — "Изображение нейрона обработано"
      │
      ├── Индекс по ID:       {ep_001: Episode, ...}
      └── Индекс по концепту: {"нейрон": [ep_001, ep_002, ep_003]}
```

### Структура `Episode`

```python
@dataclass
class Episode:
    episode_id: str       # "ep_a1b2c3d4"
    content: str          # "Пользователь спросил о нейронах"
    modality: str         # 'text' | 'image' | 'audio' | 'mixed'
    source: str           # "user_input", "docs/нейрон.pdf"
    importance: float     # 0.0–1.0
    confidence: float     # 0.0–1.0
    tags: List[str]       # ["нейрон", "вопрос"]
    concepts: List[str]   # ["нейрон", "нервная система"]
    modal_evidence: List[ModalEvidence]  # кросс-модальные доказательства
    trace_id: str         # для трассировки причинности
    session_id: str       # ID сессии
    created_at: str       # ISO timestamp
    is_protected: bool    # importance >= 0.8 → не удаляется при decay
```

### Кросс-модальные доказательства `ModalEvidence`

```python
@dataclass
class ModalEvidence:
    modality: str         # 'text' | 'image' | 'audio'
    source: str           # "docs/нейрон.pdf#p1"
    content_ref: str      # ссылка на содержимое
    confidence: float     # уверенность в доказательстве
    metadata: Dict        # page, time_range, region, ...
```

**Пример эпизода с кросс-модальными доказательствами:**
```json
{
  "episode_id": "ep_a1b2c3",
  "content": "нейрон — основная клетка нервной системы",
  "modality": "mixed",
  "importance": 0.85,
  "modal_evidence": [
    {"modality": "text",  "source": "нейробиология.pdf#p12", "confidence": 0.92},
    {"modality": "image", "source": "схема_нейрона.png",     "confidence": 0.85},
    {"modality": "audio", "source": "лекция.mp3@t=15.3",     "confidence": 0.91}
  ]
}
```

### Персистентность

```
brain/data/memory/episodes.json
    │
    ├── Автосохранение каждые 20 записей
    └── Загрузка при инициализации
```

### API

```python
em = EpisodicMemory(data_path="brain/data/memory/episodes.json")

# Сохранить эпизод
ep = em.store("нейрон — клетка нервной системы",
              modality="text", importance=0.8,
              concepts=["нейрон"], trace_id="trace_001")

# Поиск
results = em.search("нейрон", top_n=5, last_n_hours=24.0)

# Последние N эпизодов
recent = em.get_recent(n=10)

# По концепту
episodes = em.get_by_concept("нейрон")

# По временному диапазону
episodes = em.get_by_time_range(start_ts, end_ts)
```

---

## Компонент 4: `SourceMemory` — Память об источниках

**Файл:** `brain/memory/source_memory.py`  
**Аналог:** Префронтальная кора — оценка достоверности

### Принцип работы

```
Каждый источник имеет trust score (0.0–1.0):

  Начальные значения по типу:
    system:    1.0  (внутренние данные мозга)
    user:      0.8  (ввод пользователя)
    file:      0.7  (локальные файлы)
    inference: 0.6  (выводы мозга)
    url:       0.5  (веб-источники)
    unknown:   0.4  (неизвестный источник)

  Обновление:
    confirm → trust += 0.05 (но не > 1.0)
    deny    → trust -= 0.1  (но не < 0.0)
    decay   → trust *= (1 - rate)  (медленное затухание)
```

### Структура `SourceRecord`

```python
@dataclass
class SourceRecord:
    source_id: str        # "docs/нейрон.pdf"
    source_type: str      # "file" | "url" | "user" | "system" | "inference"
    trust_score: float    # 0.0–1.0
    fact_count: int       # сколько фактов получено из источника
    confirmed_count: int  # сколько фактов подтверждено
    denied_count: int     # сколько фактов опровергнуто
    first_seen: str       # ISO timestamp
    last_seen: str        # ISO timestamp
    is_blacklisted: bool  # заблокирован
    is_whitelisted: bool  # всегда доверять
    metadata: Dict        # дополнительные данные
```

### API

```python
sm = SourceMemory(data_path="brain/data/memory/sources.json")

# Зарегистрировать источник
record = sm.register("docs/нейрон.pdf", source_type="file")

# Обновить доверие
sm.update_trust("docs/нейрон.pdf", confirmed=True)   # trust += 0.05
sm.update_trust("fake_news.html", confirmed=False)    # trust -= 0.1

# Получить trust score
trust = sm.get_trust("docs/нейрон.pdf")  # → 0.75

# Blacklist / Whitelist
sm.blacklist("spam_source.com")
sm.whitelist("trusted_university.edu")

# Decay
sm.apply_decay(rate=0.001)
```

---

## Компонент 5: `ProceduralMemory` — Процедурная память

**Файл:** `brain/memory/procedural_memory.py`  
**Аналог:** Базальные ганглии + мозжечок — навыки и стратегии

### Принцип работы

```
Процедура = именованная последовательность шагов:

  Процедура "ответить_на_вопрос":
    Шаг 1: retrieve(query) из памяти
    Шаг 2: если найдено → формировать ответ
    Шаг 3: если не найдено → запросить уточнение
    Шаг 4: сохранить эпизод взаимодействия

  После каждого выполнения:
    success=True  → success_rate += (1 - success_rate) * 0.1
    success=False → success_rate -= success_rate * 0.1
```

### Структура `Procedure`

```python
@dataclass
class Procedure:
    procedure_id: str     # "proc_a1b2c3"
    name: str             # "ответить_на_вопрос"
    description: str      # описание процедуры
    steps: List[ProcedureStep]  # шаги
    success_rate: float   # 0.0–1.0 (обновляется после каждого выполнения)
    execution_count: int  # сколько раз выполнялась
    avg_duration_ms: float # среднее время выполнения
    tags: List[str]       # ["диалог", "поиск"]
    created_at: str
    last_used: str
```

### API

```python
pm = ProceduralMemory(data_path="brain/data/memory/procedures.json")

# Создать процедуру
proc = pm.create("ответить_на_вопрос", "Процедура ответа на вопрос пользователя",
                 steps=[...], tags=["диалог"])

# Найти процедуру
proc = pm.get("ответить_на_вопрос")

# Обновить success rate
pm.update_success("ответить_на_вопрос", success=True, duration_ms=150)

# Лучшие процедуры
best = pm.get_best(top_n=5)  # по success_rate
```

---

## Компонент 6: `ConsolidationEngine` — Гиппокамп

**Файл:** `brain/memory/consolidation_engine.py`  
**Аналог:** Гиппокамп — перенос из кратковременной в долговременную память

### Принцип работы

```
Фоновый daemon-поток (запускается при mm.start()):

  Каждую секунду проверяет:
    ├── прошло >= 30с  → consolidate()
    ├── прошло >= 300с → apply_decay()
    └── прошло >= 120с → save_all()
```

### Цикл консолидации `consolidate()`

```
Working Memory → все элементы (до 50 за цикл)
    │
    ├── importance >= 0.3 → _transfer_to_episodic()
    │       │
    │       └── проверить дубликат (поиск за последний час)
    │           если нет дубликата → episodic.store()
    │
    ├── importance >= 0.4 AND modality in ("text", "concept")
    │       → _transfer_to_semantic()
    │           │
    │           └── _extract_fact(content):
    │               ищет паттерны "X это Y", "X — Y", "X: Y", "X is Y"
    │               если найдено → semantic.store_fact()
    │
    └── _cleanup_working_memory():
        RAM > 85% → удалить старше 5мин с importance < 0.5
        RAM > 70% → удалить старше 15мин с importance < 0.3
        норма    → удалить старше 30мин с importance < 0.2
```

### Цикл затухания `apply_decay()`

```
RAM > 85% → decay_rate = 0.003 × 5 = 0.015  (агрессивное)
RAM > 70% → decay_rate = 0.003 × 2 = 0.006  (ускоренное)
норма     → decay_rate = 0.003               (нормальное)

semantic.apply_decay(rate)   → confidence *= (1 - rate)
source.apply_decay(rate)     → trust_score *= (1 - rate)
```

### Конфигурация `ConsolidationConfig`

| Параметр | Значение | Описание |
|----------|----------|----------|
| `CONSOLIDATION_INTERVAL` | 30с | Частота консолидации |
| `DECAY_INTERVAL` | 300с | Частота decay (5 мин) |
| `SAVE_INTERVAL` | 120с | Частота сохранения (2 мин) |
| `IMPORTANCE_TO_EPISODIC` | 0.3 | Минимум для переноса в Episodic |
| `IMPORTANCE_TO_SEMANTIC` | 0.4 | Минимум для переноса в Semantic |
| `CONFIDENCE_DECAY_RATE` | 0.003 | Скорость затухания confidence |
| `SOURCE_DECAY_RATE` | 0.001 | Скорость затухания trust |
| `RAM_AGGRESSIVE_DECAY_PCT` | 85% | Порог агрессивного забывания |
| `RAM_NORMAL_DECAY_PCT` | 70% | Порог ускоренного затухания |
| `MAX_ITEMS_PER_CONSOLIDATION` | 50 | Лимит за один цикл |

---

## Компонент 7: `MemoryManager` — Диспетчер

**Файл:** `brain/memory/memory_manager.py`  
**Роль:** Единая точка входа для всей системы памяти

### Инициализация

```python
mm = MemoryManager(
    data_dir="brain/data/memory",   # директория JSON-файлов
    working_max_size=20,             # лимит рабочей памяти
    semantic_max_nodes=10_000,       # лимит семантических узлов
    episodic_max=5_000,              # лимит эпизодов
    auto_consolidate=True,           # запустить фоновый поток
)
mm.start()  # запускает ConsolidationEngine
```

### Единый интерфейс `store()`

```python
result = mm.store(
    content="нейрон — клетка нервной системы",
    modality="text",
    importance=0.8,
    source_ref="docs/нейрон.pdf#p1",
    tags=["биология"],
    concepts=["нейрон"],
    trace_id="trace_001",
    session_id="sess_01",
    auto_extract_facts=True,  # автоизвлечение в SemanticMemory
)

# result содержит:
# result["working"]  → MemoryItem
# result["episodic"] → Episode (если importance >= 0.4)
# result["semantic"] → SemanticNode (если найден паттерн факта)
```

### Единый интерфейс `retrieve()`

```python
result = mm.retrieve(
    query="нейрон",
    memory_types=["working", "semantic", "episodic"],  # или None (все)
    top_n=5,
    min_importance=0.3,
)

# result.working  → List[MemoryItem]
# result.semantic → List[SemanticNode]
# result.episodic → List[Episode]
# result.total    → общее количество
# result.summary() → текстовое резюме
```

### ⚙️ Multi-stage Retrieval — `retrieve_staged()`

> ⬜ **Статус: НЕ РЕАЛИЗОВАНО** — запланировано для Этапа F (Cognitive MVP).  
> `retrieve_staged()` и `EvidenceBundle` описаны ниже как спецификация для реализации.  
> Сейчас используется `retrieve()` — простой одноуровневый поиск.

> **Проблема простого `retrieve()`:** один проход по памяти возвращает много нерелевантного шума.  
> **Решение:** три последовательных слоя — широкий поиск → фильтрация → переранжирование.

```python
result = mm.retrieve_staged(
    query="нейрон",
    active_goal=planner.peek(),          # текущая цель для goal_relevance
    modality_filter=None,                # None = все модальности
    time_sensitive=False,                # True = фильтровать по свежести
    top_n=5,                             # финальное количество результатов
)
```

**Алгоритм (3 стадии):**

```
Stage 1 — BROAD SEARCH (широкий поиск):
─────────────────────────────────────────────────────────────
  # Goal-aware query expansion: расширение зависит от типа цели
  goal_type = active_goal.goal_type if active_goal else "answer_question"

  if goal_type == "answer_question":
      # Ищем подтверждающие факты + связанные концепты
      expanded = [query] + semantic.get_related(query, top_n=4)
      relation_types = ["is_a", "part_of", "related", "enables"]

  elif goal_type == "verify_claim":
      # CONTRADICTION-FIRST: приоритет конфликтующим доказательствам
      expanded = [query] + semantic.get_related(query, top_n=2)
      relation_types = ["opposite", "contradicts", "related"]
      # Дополнительно: поиск по отрицанию
      expanded += [f"не {query}", f"опровержение {query}"]

  elif goal_type == "explore_topic":
      # Широкое расширение: все связи + соседи второго уровня
      expanded = [query] + semantic.get_concept_chain(query, depth=2)
      relation_types = ["is_a", "part_of", "related", "causes", "enables"]

  else:  # "learn_fact", "plan", default
      expanded = [query] + semantic.get_related(query, top_n=3)
      relation_types = ["is_a", "related"]

  # "нейрон" (answer_question) → ["нейрон", "нервная клетка", "синапс", "аксон", "мозг"]
  # "нейрон" (verify_claim)    → ["нейрон", "синапс", "не нейрон", "опровержение нейрон"]
  # "нейрон" (explore_topic)   → ["нейрон", "клетка", "организм", "нервная система", ...]

  pool = []
  for q in expanded:
      pool += working.search(q,  top_n=10)   # рабочая память
      pool += semantic.search(q, top_n=20)   # семантический граф
      pool += episodic.search(q, top_n=20)   # эпизодическая память

  pool = deduplicate_by_concept(pool)
  # → ~50 кандидатов

Stage 2 — FILTER (фильтрация):
─────────────────────────────────────────────────────────────
  filtered = [item for item in pool if
      source_memory.get_trust(item.source_ref) >= 0.4  # отсеять ненадёжные
      and item.confidence >= 0.3                        # отсеять слабые факты
      and (modality_filter is None                      # фильтр по модальности
           or item.modality == modality_filter)
      and (not time_sensitive                           # фильтр по свежести
           or item.age_hours < 24)
  ]
  # → ~15–20 кандидатов

Stage 3 — RERANK (переранжирование):
─────────────────────────────────────────────────────────────
  def rerank_score(item, goal_type) -> float:
      relevance     = semantic_similarity(item.content, query)
      source_trust  = source_memory.get_trust(item.source_ref)
      recency       = 1.0 / max(1, item.age_days)          # свежесть
      graph_bonus   = 1.0 if item.concept in semantic_neighbors else 0.0

      # Для verify_claim: поднять конфликтующие доказательства выше
      contradiction_boost = 0.0
      if goal_type == "verify_claim":
          contradictions = contradiction_detector.check(item.content)
          contradiction_boost = 0.3 if contradictions else 0.0

      return (
          0.40 * relevance           +   # семантическая близость к запросу
          0.30 * source_trust        +   # доверие к источнику
          0.20 * recency             +   # свежесть данных
          0.10 * graph_bonus         +   # близость в семантическом графе
          contradiction_boost            # бонус для verify_claim
      )

  ranked = sorted(filtered, key=lambda i: rerank_score(i, goal_type), reverse=True)
  return ranked[:top_n]
  # → top-5 результатов
```

**Evidence Bundle** — результат `retrieve_staged()` возвращает не список, а структурированный пакет:

```python
@dataclass
class EvidenceBundle:
    query: str                      # исходный запрос
    expanded_queries: List[str]     # расширенные запросы

    # Результаты по типам
    working_items: List[MemoryItem]     # из рабочей памяти
    semantic_nodes: List[SemanticNode]  # из семантического графа
    episodes: List[Episode]             # из эпизодической памяти

    # Агрегированные метрики
    avg_confidence: float           # среднее confidence по всем результатам
    avg_source_trust: float         # среднее доверие к источникам
    contradictions: List[str]       # обнаруженные противоречия

    # Для Cognitive Core
    top_concepts: List[str]         # наиболее релевантные концепты
    total_retrieved: int            # всего найдено (до фильтрации)
    total_after_filter: int         # после фильтрации
    total_returned: int             # финальное количество
```

**Сравнение `retrieve()` vs `retrieve_staged()`:**

| Аспект | `retrieve()` | `retrieve_staged()` |
|--------|-------------|---------------------|
| Поиск | Один проход | 3 стадии |
| Query expansion | ❌ | ✅ через семантический граф |
| Фильтрация по trust | ❌ | ✅ source_trust >= 0.4 |
| Переранжирование | ❌ | ✅ 4-факторная формула |
| Результат | `MemorySearchResult` | `EvidenceBundle` |
| Использование | Быстрый поиск | Cognitive Core reasoning |

### Обратная связь

```python
mm.confirm("нейрон", source_ref="docs/нейрон.pdf")  # confidence += 0.05
mm.deny("нейрон", source_ref="fake_source.html")     # confidence -= 0.1
```

---

## Поток данных: полный цикл

```
Пользователь: "Что такое нейрон?"
      │
      ▼
mm.store("Что такое нейрон?", importance=0.6, source_ref="user_input")
      │
      ├── WorkingMemory.push()          → MemoryItem в deque
      ├── EpisodicMemory.store()        → Episode (importance >= 0.4)
      └── SemanticMemory: нет паттерна  → не сохраняем
      │
      ▼
mm.retrieve("нейрон")
      │
      ├── WorkingMemory.search()  → [] (только что добавлен вопрос)
      ├── SemanticMemory.search() → [SemanticNode("нейрон", "клетка...")]
      └── EpisodicMemory.search() → [Episode("нейрон — клетка...")]
      │
      ▼
result.summary():
  "[Факт] нейрон: основная клетка нервной системы"
  "[Эпизод] нейрон — клетка нервной системы"
      │
      ▼
Cognitive Core строит ответ...
      │
      ▼
mm.store("Ответ: нейрон — это клетка нервной системы",
         importance=0.7, source_ref="brain_inference")
      │
      ▼
ConsolidationEngine (через 30с):
  → переносит в EpisodicMemory
  → извлекает факт "нейрон — клетка нервной системы" → SemanticMemory
```

---

## Персистентность (JSON-файлы)

```
brain/data/memory/
    ├── semantic.json     — граф понятий (SemanticMemory)
    ├── episodes.json     — хронология событий (EpisodicMemory)
    ├── sources.json      — доверие к источникам (SourceMemory)
    └── procedures.json   — навыки и стратегии (ProceduralMemory)

WorkingMemory — только RAM, не сохраняется (сбрасывается при перезапуске)
```

**Формат `semantic.json`:**
```json
{
  "nodes": {
    "нейрон": {
      "concept": "нейрон",
      "description": "основная клетка нервной системы",
      "confidence": 0.87,
      "importance": 0.9,
      "tags": ["биология"],
      "relations": [
        {"target": "клетка", "relation_type": "is_a", "weight": 0.9}
      ]
    }
  },
  "saved_at": "2026-03-19T12:00:00Z"
}
```

---

## Ресурсный бюджет (CPU-only, 32 GB RAM)

| Компонент | RAM | CPU | Персистентность |
|-----------|-----|-----|-----------------|
| WorkingMemory (20 элементов) | ~1–5 MB | — | ❌ RAM-only |
| SemanticMemory (10 000 узлов) | ~50–200 MB | 1 поток | ✅ JSON |
| EpisodicMemory (5 000 эпизодов) | ~100–500 MB | 1 поток | ✅ JSON |
| SourceMemory | ~5–20 MB | 1 поток | ✅ JSON |
| ProceduralMemory | ~5–10 MB | 1 поток | ✅ JSON |
| ConsolidationEngine (поток) | ~5 MB | 1 daemon-поток | — |
| **Итого** | **~170–740 MB** | **2–4 потока** | — |

---

## Статус реализации

| Файл | Статус | Тестов |
|------|--------|--------|
| `brain/memory/working_memory.py` | ✅ Готово | 13 |
| `brain/memory/semantic_memory.py` | ✅ Готово | 16 |
| `brain/memory/episodic_memory.py` | ✅ Готово | 14 |
| `brain/memory/source_memory.py` | ✅ Готово | 15 |
| `brain/memory/procedural_memory.py` | ✅ Готово | 10 |
| `brain/memory/consolidation_engine.py` | ✅ Готово | 9 |
| `brain/memory/memory_manager.py` | ✅ Готово | 16 |
| `brain/memory/__init__.py` | ✅ Готово | 2 |
| **Итого** | **✅ 101/101** | **101** |

---

## Итог: место Memory System в архитектуре

```
Ассоциативная кора → [MEMORY SYSTEM] → Cognitive Core
                           │
                           ├── WorkingMemory:    "стол" — активный контекст
                           ├── SemanticMemory:   "энциклопедия" — факты и граф
                           ├── EpisodicMemory:   "дневник" — хронология событий
                           ├── SourceMemory:     "репутация" — доверие к источникам
                           ├── ProceduralMemory: "
