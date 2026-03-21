# 🧠 Слой 8: Attention & Resource Control (Таламус + Гипоталамус)
## Подробное описание архитектуры и работы

> **Статус: ⬜ Этап H — не реализовано**  
> ⚠️ `ResourceState` уже реализован в `brain/core/contracts.py` с полями:
> `cpu_pct`, `ram_pct`, `ram_used_mb`, `ram_total_mb`, `available_threads`, `ring2_allowed`, `soft_blocked`.
> Поля `ram_gb`, `ram_available_gb`, `models_gb`, `policy`, `timestamp` из этого документа
> **не реализованы** в текущем контракте — будут добавлены при реализации Этапа H.

---

## Что такое внимание и ресурсный контроль в биологии

| Биологическая структура | Функция | Аналог |
|------------------------|---------|--------|
| **Таламус** | Маршрутизация сенсорных потоков, фильтрация | `AttentionController`, `ModalityRouter` |
| **Гипоталамус** | Гомеостаз, управление ресурсами тела | `ResourceMonitor`, `DegradationPolicy` |
| **Ретикулярная формация** | Уровень бодрствования, общая активация | `Scheduler` (tick rate) |
| **Передняя поясная кора** | Распределение когнитивных усилий | `CognitiveLoadBalancer` |

**Ключевой принцип:** мозг никогда не обрабатывает всё одновременно с одинаковым приоритетом. Он **выбирает**, на что тратить ограниченные ресурсы.

---

## Роль в искусственном мозге

```
ResourceMonitor (CPU/RAM состояние)
SalienceEngine  (что важно прямо сейчас)
Planner         (текущая цель)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│              ATTENTION & RESOURCE CONTROL                   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           AttentionController                        │   │
│  │  goal-driven + salience-driven внимание              │   │
│  │  → AttentionBudget (доли CPU по модальностям)        │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │           ModalityRouter                             │   │
│  │  маршрутизация входов по текущему бюджету            │   │
│  │  → пропустить / отложить / отклонить                 │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │           CognitiveLoadBalancer                      │   │
│  │  распределение задач по потокам                      │   │
│  │  → параллельная обработка модальностей               │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │           DegradationPolicy                          │   │
│  │  NORMAL → DEGRADED → CRITICAL → EMERGENCY            │   │
│  │  автоматическое снижение нагрузки                    │   │
│  └──────────────────────┬───────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
              Все модули получают свой бюджет
    и знают, сколько ресурсов им доступно в этом цикле
```

---

## Компонент 1: `AttentionController` — Контроллер внимания

**Файл:** `brain/core/attention_controller.py`

### Два контура внимания

#### 1.1 Goal-Driven Attention (сверху вниз)

```
Текущая цель Planner: "ответить на вопрос о нейронах"
    │
    ▼
AttentionController.compute_goal_budget(goal)
    │
    ├── Тип цели = "answer_question" (текстовый вопрос)
    │   → text_weight = 0.60 (главная модальность)
    │   → memory_weight = 0.25 (нужна память)
    │   → cognition_weight = 0.10
    │   → vision_weight = 0.05 (не нужно)
    │   → audio_weight = 0.00
    │
    ├── Тип цели = "analyze_image" (анализ изображения)
    │   → vision_weight = 0.55
    │   → text_weight = 0.20
    │   → memory_weight = 0.15
    │   → cognition_weight = 0.10
    │
    └── Тип цели = "transcribe_audio"
        → audio_weight = 0.60
        → text_weight = 0.20
        → memory_weight = 0.10
        → cognition_weight = 0.10
```

#### 1.2 Salience-Driven Attention (снизу вверх)

```
SalienceEngine сообщает: новый стимул с salience=0.9 (INTERRUPT)
    │
    ▼
AttentionController.handle_interrupt(salience_score)
    │
    ├── salience > 0.8 → INTERRUPT
    │   → приостановить текущую задачу
    │   → перераспределить бюджет на новый стимул
    │   → уведомить Planner о прерывании
    │
    ├── salience 0.5–0.8 → BOOST
    │   → увеличить приоритет в очереди
    │   → не прерывать текущую задачу
    │
    └── salience < 0.5 → NORMAL
        → обработать в обычном порядке
```

### Структура `AttentionBudget`

```python
@dataclass
class AttentionBudget:
    """
    Распределение вычислительных ресурсов по модальностям.
    Сумма всех весов = 1.0.
    Применяется к доступному CPU (после вычета ОС и фоновых процессов).
    """
    text: float       # доля для TextEncoder + TextIngestor
    vision: float     # доля для VisionEncoder + VisionIngestor
    audio: float      # доля для AudioEncoder + AudioIngestor
    memory: float     # доля для Memory System операций
    cognition: float  # доля для Cognitive Core
    learning: float   # доля для Learning Loop (replay, online)
    logging: float    # доля для Logging & Observability

    # Метаданные
    policy: str       # "normal" | "degraded" | "critical" | "emergency"
    reason: str       # почему такой бюджет
    cycle_id: str     # ID цикла
    created_at: str   # timestamp
```

### Предустановленные бюджеты

```python
BUDGETS = {
    "text_focused": AttentionBudget(
        text=0.50, vision=0.05, audio=0.00,
        memory=0.25, cognition=0.12, learning=0.05, logging=0.03,
        policy="normal", reason="text-only question"
    ),
    "multimodal": AttentionBudget(
        text=0.25, vision=0.25, audio=0.15,
        memory=0.15, cognition=0.12, learning=0.05, logging=0.03,
        policy="normal", reason="multimodal input"
    ),
    "memory_intensive": AttentionBudget(
        text=0.20, vision=0.05, audio=0.00,
        memory=0.50, cognition=0.15, learning=0.07, logging=0.03,
        policy="normal", reason="deep memory search"
    ),
    "degraded": AttentionBudget(
        text=0.65, vision=0.00, audio=0.00,
        memory=0.20, cognition=0.10, learning=0.00, logging=0.05,
        policy="degraded", reason="CPU > 70% or RAM > 22GB"
    ),
    "critical": AttentionBudget(
        text=0.75, vision=0.00, audio=0.00,
        memory=0.15, cognition=0.07, learning=0.00, logging=0.03,
        policy="critical", reason="CPU > 85% or RAM > 28GB"
    ),
    "emergency": AttentionBudget(
        text=0.80, vision=0.00, audio=0.00,
        memory=0.10, cognition=0.07, learning=0.00, logging=0.03,
        policy="emergency", reason="RAM > 30GB — unload models"
    ),
}
```

---

## Компонент 2: `ModalityRouter` — Маршрутизатор модальностей

**Файл:** `brain/core/modality_router.py`  
**Аналог:** Таламус — фильтрация и маршрутизация сенсорных потоков

### Принцип работы

```
Входящий PerceptEvent(modality="vision", ...)
    │
    ▼
ModalityRouter.route(event, budget)
    │
    ├── budget.vision > 0.05 → ACCEPT
    │   → передать VisionIngestor → VisionEncoder
    │
    ├── budget.vision == 0.00 → DEFER
    │   → поместить в очередь ожидания
    │   → обработать когда budget.vision > 0
    │
    └── очередь ожидания > 50 событий → DISCARD (oldest)
        → логировать как "modality_deferred_overflow"
```

### Очередь ожидания по модальностям

```python
class ModalityQueue:
    """
    Буфер для событий, которые не могут быть обработаны сейчас.
    FIFO с ограниченным размером (overflow → discard oldest).
    """
    text_queue:   deque  # max_size=100
    vision_queue: deque  # max_size=20 (большие данные)
    audio_queue:  deque  # max_size=20
    
    def drain_when_budget_allows(self, budget: AttentionBudget):
        """Обработать накопленные события при наличии бюджета."""
```

---

## Компонент 3: `CognitiveLoadBalancer` — Балансировщик нагрузки

**Файл:** `brain/core/load_balancer.py`  
**Аналог:** Передняя поясная кора — распределение когнитивных усилий

### Параллельная обработка модальностей

```
Входящий мультимодальный документ (текст + изображения):
    │
    ▼
CognitiveLoadBalancer.distribute(tasks, budget)
    │
    ├── Thread 1 (CPU cores 0–3): TextEncoder.encode(text_parts)
    ├── Thread 2 (CPU cores 4–7): VisionEncoder.encode(images)
    └── Thread 3 (CPU cores 8–11): MemoryManager.retrieve(query)
    │
    ▼
Синхронизация результатов → CrossModalFusion
```

### Ограничения параллелизма

```python
class ThreadBudget:
    """
    Распределение потоков CPU (Ryzen 7 5700X: 16 потоков).
    """
    os_reserved: int = 4      # зарезервировано для ОС
    brain_total: int = 12     # доступно мозгу
    
    # Распределение по модулям:
    perception: int = 3       # text/vision/audio ingestors
    encoders: int = 4         # text/vision/audio encoders (самые тяжёлые)
    memory: int = 2           # memory operations
    cognition: int = 2        # cognitive core
    background: int = 1       # consolidation, replay, metrics
```

---

## Компонент 4: `DegradationPolicy` — Политика деградации

**Файл:** `brain/core/degradation_policy.py`  
**Аналог:** Гипоталамус — защитные реакции при нехватке ресурсов

### Полная таблица состояний

| Состояние | Триггер | Tick | Отключить | Включить |
|-----------|---------|------|-----------|----------|
| **NORMAL** | CPU < 70%, RAM < 22 GB | 100 мс | — | Всё |
| **DEGRADED** | CPU 70–85% ИЛИ RAM 22–28 GB | 500 мс | ReplayEngine, SelfSupervised, VisionEncoder | TextEncoder, Memory, Cognition |
| **CRITICAL** | CPU > 85% ИЛИ RAM 28–30 GB | 2000 мс | Learning Loop, VisionEncoder, AudioEncoder | TextEncoder (navec fallback), Memory, Cognition |
| **EMERGENCY** | RAM > 30 GB | 5000 мс | Всё кроме Memory + Output | Memory.retrieve(), DialogueResponder |

### Переходы между состояниями

```
NORMAL ──(CPU > 70%)──► DEGRADED ──(CPU > 85%)──► CRITICAL ──(RAM > 30GB)──► EMERGENCY
  ▲                        │                          │                           │
  └──(CPU < 60% × 60с)────┘                          │                           │
                           ▲                          │                           │
                           └──(CPU < 75% × 120с)─────┘                           │
                                                      ▲                           │
                                                      └──(RAM < 28GB × 300с)──────┘
```

### Действия при переходе в EMERGENCY

```python
def handle_emergency(self):
    """Экстренное освобождение памяти."""
    
    # 1. Выгрузить Vision Encoder (~600 MB)
    vision_encoder.unload()
    logger.critical("VisionEncoder unloaded (emergency)")
    
    # 2. Выгрузить Audio Encoder (~1.5 GB)
    audio_encoder.unload()
    logger.critical("AudioEncoder unloaded (emergency)")
    
    # 3. Агрессивная очистка памяти
    memory_manager.emergency_cleanup(target_mb=2000)
    
    # 4. Если RAM всё ещё > 31 GB → выгрузить Text Encoder
    if resource_monitor.ram_gb > 31:
        text_encoder.switch_to_fallback()  # navec вместо sentence-transformers
        logger.critical("TextEncoder switched to navec fallback")
    
    # 5. Уведомить пользователя
    event_bus.publish(SystemEvent(
        level="CRITICAL",
        event="emergency_degradation",
        message="Критическая нехватка RAM. Часть функций отключена."
    ))
```

---

## Полный цикл управления вниманием

```
Начало цикла мышления:
    │
    ▼
[ResourceMonitor] → ResourceState(cpu=45%, ram=8.2GB, policy="normal")
    │
    ▼
[SalienceEngine] → SalienceScore(overall=0.55, action="prioritize")
    │
    ▼
[Planner] → Goal(type="answer_question", priority=0.8)
    │
    ▼
[AttentionController]
  goal_budget = BUDGETS["text_focused"]
  salience_boost = +0.05 на cognition (salience=0.55)
  resource_factor = 1.0 (NORMAL)
  
  final_budget = AttentionBudget(
    text=0.50, vision=0.05, audio=0.00,
    memory=0.25, cognition=0.17, learning=0.00, logging=0.03
  )
    │
    ▼
[ModalityRouter]
  vision_event в очереди → budget.vision=0.05 → ACCEPT (низкий приоритет)
  text_event → budget.text=0.50 → ACCEPT (высокий приоритет)
    │
    ▼
[CognitiveLoadBalancer]
  Thread 1: TextEncoder.encode(query)     → 4 ядра
  Thread 2: MemoryManager.retrieve(query) → 2 ядра
  Thread 3: (idle)
    │
    ▼
Результаты → CrossModalFusion → CognitiveCore
```

---

## Наблюдаемость (Observability)

Каждое изменение бюджета логируется:

```json
{
  "ts": "2026-03-19T12:00:00.123Z",
  "level": "INFO",
  "module": "attention_controller",
  "event": "budget_updated",
  "cycle_id": "cycle_4521",
  "old_policy": "normal",
  "new_policy": "degraded",
  "trigger": "cpu_pct=72.3",
  "budget": {
    "text": 0.65, "vision": 0.00, "audio": 0.00,
    "memory": 0.20, "cognition": 0.10, "learning": 0.00, "logging": 0.05
  },
  "disabled_modules": ["replay_engine", "vision_encoder"],
  "latency_ms": 2
}
```

---

## Ресурсный бюджет самого модуля (CPU-only, 32 GB RAM)

| Компонент | RAM | CPU | Поток |
|-----------|-----|-----|-------|
| AttentionController | ~2 MB | < 1% | 1 (main) |
| ModalityRouter + очереди | ~5 MB | < 1% | 1 (main) |
| CognitiveLoadBalancer | ~1 MB | < 1% | 1 (main) |
| DegradationPolicy | ~1 MB | < 1% | 1 (daemon) |
| **Итого** | **~9 MB** | **< 2%** | **2 потока** |

---

## Статус реализации

| Компонент | Статус | Файл |
|-----------|--------|------|
| `AttentionBudget` dataclass | ⬜ Фаза 8.1 | `brain/core/attention_controller.py` |
| `AttentionController` | ⬜ Фаза 8.1 | `brain/core/attention_controller.py` |
| `ModalityRouter` | ⬜ Фаза 8.2 | `brain/core/modality_router.py` |
| `CognitiveLoadBalancer` | ⬜ Фаза 8.3 | `brain/core/load_balancer.py` |
| `DegradationPolicy` | ⬜ Фаза 8.4 | `brain/core/degradation_policy.py` |
