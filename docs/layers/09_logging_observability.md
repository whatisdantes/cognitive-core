# 🧠 Слой 9: Logging & Observability (Метапознание)
## Подробное описание архитектуры и работы

> **Статус: ✅ Этап C завершён** · 25/25 тестов  
> ✅ `brain_logger.py` — BrainLogger (JSONL, 5 уровней, категорийные файлы, ротация 100MB)  
> ✅ `digest_generator.py` — DigestGenerator + CycleInfo (cycle/session digests)  
> ✅ `trace_builder.py` — TraceBuilder (start/add_step/finish, reconstruct_from_logger)  
> ⬜ `metrics_collector.py` — MetricsCollector (Этап H/M)  
> ⬜ `dashboard.py` — Dashboard (Этап H/M)  
> ⚠️ Реализуется РАНО — до остальных модулей, чтобы всё логировалось с самого начала.

---

## Зачем нужна наблюдаемость

**Без логирования мозг — чёрный ящик.** Невозможно:
- понять, почему принято конкретное решение
- воспроизвести ошибку
- измерить качество мышления
- диагностировать сбои памяти/планирования
- провести аудит безопасности

**Цель:** каждый вывод системы должен быть **объяснён и прослеживаем** — от входного стимула до финального ответа.

> **Принцип из BRAIN.md §14:** "Никаких «магических» ответов без trace chain."

---

## Архитектура системы логирования

```
Любой модуль мозга
    │
    ▼
brain_logger.log(event)
    │
    ├──► brain.jsonl          (все события, machine format)
    ├──► cognitive.jsonl      (только когнитивные события)
    ├──► memory.jsonl         (только события памяти)
    ├──► perception.jsonl     (только события восприятия)
    ├──► learning.jsonl       (только события обучения)
    ├──► safety_audit.jsonl   (только события безопасности)
    │
    ├──► DigestGenerator      → logs/digests/YYYY-MM-DD.txt
    ├──► TraceBuilder         → trace chain по trace_id
    └──► MetricsCollector     → logs/metrics.jsonl + Dashboard
```

---

## 6 категорий логов (из BRAIN.md §14.2)

> **Примечание:** "6 категорий" — это 6 типов файлов логов (System, Cognitive, Memory,
> Perception, Learning, Safety/Audit). Уровней логирования — **5**: DEBUG/INFO/WARN/ERROR/CRITICAL.

### Слой 1: System Logs
```
Что логируется:
  - запуск/остановка мозга
  - загрузка/выгрузка моделей
  - состояние ресурсов (CPU/RAM каждые 60с)
  - изменение политики деградации
  - критические ошибки

Примеры событий:
  brain_started, brain_stopped, model_loaded, model_unloaded,
  resource_check, policy_changed, emergency_degradation
```

### Слой 2: Cognitive Logs
```
Что логируется:
  - создание/завершение целей (GoalStack)
  - шаги плана (PlanStep)
  - результаты рассуждений (ReasoningTrace)
  - найденные противоречия (ContradictionRecord)
  - выбор действия (ActionDecision)
  - уровень уверенности

Примеры событий:
  goal_created, goal_completed, plan_step_selected,
  reasoning_completed, contradiction_detected, action_selected
```

### Слой 3: Memory Logs
```
Что логируется:
  - запись в память (store)
  - чтение из памяти (retrieve)
  - консолидация (WM → Episodic → Semantic)
  - забывание (decay)
  - обновление confidence

Примеры событий:
  fact_stored, fact_retrieved, episode_created,
  consolidation_run, memory_decayed, confidence_updated
```

### Слой 4: Perception Logs
```
Что логируется:
  - входящие события (text/image/audio)
  - качество извлечения (OCR confidence, ASR confidence)
  - метаданные источника (source, timestamp, language)
  - ошибки парсинга

Примеры событий:
  text_ingested, image_ingested, audio_ingested,
  ocr_completed, asr_completed, parse_error
```

### Слой 5: Learning Logs
```
Что логируется:
  - онлайн-обновления (ассоциации, confidence)
  - replay сессии
  - принятые/отклонённые гипотезы
  - закрытые пробелы в знаниях
  - изменения весов энкодеров

Примеры событий:
  online_update, replay_session, hypothesis_accepted,
  hypothesis_rejected, gap_closed, encoder_updated
```

### Слой 6: Safety/Audit Logs
```
Что логируется:
  - срабатывание политик безопасности
  - redaction приватных данных
  - конфликты источников
  - изменения trust score
  - blacklist/whitelist операции

Примеры событий:
  source_blacklisted, data_redacted, conflict_detected,
  trust_updated, boundary_violated, audit_flag
```

---

## Компонент 1: `BrainLogger` — JSONL-логгер

**Файл:** `brain/logging/brain_logger.py`

### Формат события (единый JSONL)

Каждое событие — одна JSON-строка (из BRAIN.md §14.3):

```json
{
  "ts": "2026-03-19T12:00:00.123Z",
  "level": "INFO",
  "module": "planner",
  "event": "plan_step_selected",
  "session_id": "sess_01",
  "cycle_id": "cycle_4521",
  "trace_id": "trace_9fa",
  "input_ref": ["doc:A.md#p12", "img:frame_33"],
  "state": {
    "goal": "verify_claim",
    "cpu_pct": 62,
    "ram_mb": 4200
  },
  "decision": {
    "action": "cross_modal_check",
    "confidence": 0.81
  },
  "latency_ms": 37,
  "notes": "selected due to contradiction risk"
}
```

### Обязательные поля

| Поле | Тип | Описание |
|------|-----|---------|
| `ts` | str | ISO 8601 timestamp с миллисекундами |
| `level` | str | DEBUG / INFO / WARN / ERROR / CRITICAL |
| `module` | str | имя модуля (planner, memory, perception, ...) |
| `event` | str | тип события (snake_case) |
| `session_id` | str | ID сессии пользователя |
| `cycle_id` | str | ID цикла мышления |
| `trace_id` | str | ID трассировки (для связи событий) |

### Опциональные поля

| Поле | Тип | Описание |
|------|-----|---------|
| `input_ref` | List[str] | ссылки на входные данные |
| `memory_refs` | List[str] | ссылки на факты из памяти |
| `state` | Dict | текущее состояние (цель, CPU, RAM) |
| `decision` | Dict | принятое решение + confidence |
| `latency_ms` | float | время выполнения операции |
| `notes` | str | человекочитаемый комментарий |

### Уровни логов (из BRAIN.md §14.4)

| Уровень | Когда использовать |
|---------|-------------------|
| `DEBUG` | Детальная трассировка (только в dev/исследованиях) |
| `INFO` | Нормальная работа циклов |
| `WARN` | Подозрительные данные, CPU > 70%, низкий confidence |
| `ERROR` | Сбои модулей, невозможность выполнить шаг |
| `CRITICAL` | Риск целостности системы, CPU > 85%, RAM > 28 GB |

### API логгера

```python
class BrainLogger:
    def log(self, level: str, module: str, event: str, **kwargs):
        """Записать событие в JSONL."""
    
    def debug(self, module: str, event: str, **kwargs):
        """Shortcut для DEBUG."""
    
    def info(self, module: str, event: str, **kwargs):
        """Shortcut для INFO."""
    
    def warn(self, module: str, event: str, **kwargs):
        """Shortcut для WARN."""
    
    def error(self, module: str, event: str, **kwargs):
        """Shortcut для ERROR."""
    
    def critical(self, module: str, event: str, **kwargs):
        """Shortcut для CRITICAL."""
    
    def get_events(self, trace_id: str) -> List[dict]:
        """Получить все события по trace_id."""
    
    def get_session(self, session_id: str) -> List[dict]:
        """Получить все события сессии."""
```

### Пример использования

```python
# В любом модуле:
logger.info(
    module="planner",
    event="goal_created",
    session_id=session_id,
    cycle_id=cycle_id,
    trace_id=trace_id,
    state={"goal": "answer_question", "cpu_pct": 45},
    latency_ms=2.3,
    notes="new user question received"
)

logger.warn(
    module="contradiction_detector",
    event="contradiction_detected",
    trace_id=trace_id,
    decision={"fact_a": "нейрон=клетка", "fact_b": "нейрон=орган", "confidence_drop": 0.15},
    notes="conflicting facts from different sources"
)
```

---

## Компонент 2: `DigestGenerator` — Генератор дайджестов

**Файл:** `brain/logging/digest_generator.py`

### Human-readable digest (из BRAIN.md §14.5)

После каждого цикла мышления генерируется читаемая сводка:

```
Cycle 4521  [2026-03-19 12:00:00]
  Session:      sess_01
  Goal:         answer_question("Что такое нейрон?")
  Input:        text (user_input, quality=1.0)
  Memory used:  semantic:нейрон (conf=0.87), episodic:ep_001
  Sources:      user_input (trust=0.80)
  Reasoning:    associative [нейрон → клетка → нервная система]
  Contradiction: none
  Confidence:   0.78 (medium) → hedged response
  Action:       respond_hedged
  Response:     "Вероятно, нейрон — это основная клетка нервной системы..."
  Duration:     142ms | CPU: 45% | RAM: 3.8 GB
  Learning:     association(нейрон↔клетка) += 0.01
```

### Структура файлов дайджестов

```
brain/data/logs/
    ├── brain.jsonl              # все события (ротация при > 100 MB)
    ├── cognitive.jsonl          # только когнитивные
    ├── memory.jsonl             # только память
    ├── perception.jsonl         # только восприятие
    ├── learning.jsonl           # только обучение
    ├── safety_audit.jsonl       # только безопасность
    ├── metrics.jsonl            # KPI метрики
    └── digests/
        ├── 2026-03-19.txt       # дайджест за день
        ├── 2026-03-20.txt
        └── session_sess_01.txt  # дайджест по сессии
```

---

## Компонент 3: `TraceBuilder` — Построитель трассировки

**Файл:** `brain/logging/trace_builder.py`

### Трассировка причинности (из BRAIN.md §14.6)

Каждое решение связано с:

```
trace_id: "trace_9fa"
    │
    ├── input_ref:      ["user_input:sess_01:msg_3"]
    │                   ← откуда пришёл вопрос
    │
    ├── memory_refs:    ["semantic:нейрон", "episodic:ep_001"]
    │                   ← какие факты из памяти использованы
    │
    ├── hypothesis_refs: []
    │                   ← какие гипотезы проверялись
    │
    ├── reasoning:      ["нейрон", "→", "клетка", "→", "нервная система"]
    │                   ← цепочка рассуждений
    │
    ├── decision_ref:   "action:respond_hedged:confidence=0.78"
    │                   ← финальное решение
    │
    └── output_ref:     "response:out_a1b2c3"
                        ← итоговый ответ
```

### Восстановление трассировки

```python
# Восстановить полный ход мышления по trace_id:
trace = trace_builder.reconstruct("trace_9fa")

print(trace.to_human_readable())
# Вывод:
# ═══════════════════════════════════════
# TRACE: trace_9fa | Cycle 4521
# ═══════════════════════════════════════
# INPUT:    "Что такое нейрон?" (user_input)
# MEMORY:   semantic:нейрон (conf=0.87)
#           episodic:ep_001 (нейрон передаёт сигналы)
# REASONING: нейрон → клетка → нервная система
# DECISION: respond_hedged (confidence=0.78)
# OUTPUT:   "Вероятно, нейрон — это основная клетка..."
# DURATION: 142ms | CPU: 45% | RAM: 3.8 GB
# ═══════════════════════════════════════
```

---

## Компонент 4: `MetricsCollector` — Сборщик метрик

**Файл:** `brain/logging/metrics_collector.py`

### 10 KPI метрик (из BRAIN.md §13 + §14.8)

```python
@dataclass
class BrainMetrics:
    # Качество мышления
    cross_modal_retrieval_accuracy: float  # точность поиска по модальностям
    source_reliability_calibration: float  # калибровка доверия к источникам
    contradiction_detection_rate: float    # доля обнаруженных противоречий
    reasoning_depth: float                 # средняя глубина цепочки рассуждений
    reasoning_coherence: float             # связность рассуждений
    
    # Обучение
    learning_velocity: float               # скорость закрытия пробелов
    self_correction_rate: float            # частота самокоррекции ошибок
    
    # Объяснимость
    explainability_completeness: float     # полнота объяснений решений
    trace_completeness: float              # % решений с полной trace chain
    
    # Наблюдаемость
    error_localization_time_ms: float      # время до локализации причины сбоя
    replay_reproducibility: float          # повторяемость инцидента по логам
    contradiction_resolution_time_ms: float
    logging_overhead_pct: float            # % накладных расходов логирования
    
    # Ресурсы
    avg_cycle_duration_ms: float           # среднее время цикла мышления
    avg_cpu_pct: float                     # средняя загрузка CPU
    avg_ram_gb: float                      # среднее использование RAM
    
    # Метаданные
    session_id: str
    cycles_count: int
    updated_at: str
```

### Обновление метрик

```python
# Каждые 60 секунд (фоновый поток):
metrics_collector.update()

# После каждого цикла:
metrics_collector.record_cycle(
    duration_ms=142,
    confidence=0.78,
    trace_complete=True,
    contradiction_found=False,
    memory_hits=2,
    learning_updates=1
)
```

---

## Компонент 5: `Dashboard` — Текстовый дашборд

**Файл:** `brain/logging/dashboard.py`

### Live-дашборд в терминале

```
python -m brain.logging.dashboard
```

```
╔══════════════════════════════════════════════════════════════╗
║  🧠 BRAIN DASHBOARD  |  Session: sess_01  |  Cycle: 4521    ║
╠══════════════════════════════════════════════════════════════╣
║  РЕСУРСЫ                                                     ║
║  CPU: ████████░░░░░░░░  45%    RAM: 3.8 GB / 32 GB (12%)    ║
║  Потоки: 8/16           Policy: NORMAL                       ║
╠══════════════════════════════════════════════════════════════╣
║  ТЕКУЩИЙ ЦИКЛ                                                ║
║  Цель:    answer_question("Что такое нейрон?")               ║
║  Статус:  reasoning → respond_hedged                         ║
║  Время:   142ms  Уверенность: 0.78 (medium)                  ║
╠══════════════════════════════════════════════════════════════╣
║  ПАМЯТЬ                                                      ║
║  Working:   12/20 элементов                                  ║
║  Semantic:  1,247 понятий  |  8,934 связей                   ║
║  Episodic:  342 эпизода                                      ║
║  Sources:   89 источников  (avg trust: 0.74)                 ║
╠══════════════════════════════════════════════════════════════╣
║  KPI (последние 100 циклов)                                  ║
║  Trace completeness:    94%    Avg confidence:    0.71       ║
║  Contradiction rate:    8%     Self-correction:   12%        ║
║  Learning velocity:     3.2 gaps/hour                        ║
║  Avg cycle time:        138ms  Logging overhead:  2.1%       ║
╠══════════════════════════════════════════════════════════════╣
║  ПОСЛЕДНИЕ СОБЫТИЯ                                           ║
║  12:00:00 INFO  planner      goal_created                    ║
║  12:00:00 INFO  memory       fact_retrieved (нейрон)         ║
║  12:00:00 INFO  reasoner     reasoning_completed (0.78)      ║
║  12:00:00 WARN  uncertainty  medium_confidence → hedged      ║
║  12:00:00 INFO  output       response_generated (142ms)      ║
╚══════════════════════════════════════════════════════════════╝
  [q] выход  [r] обновить  [t] trace  [m] метрики  [l] логи
```

---

## Ротация и архивирование логов

```
Правила ротации:
  brain.jsonl      → ротация при > 100 MB
  cognitive.jsonl  → ротация при > 50 MB
  memory.jsonl     → ротация при > 50 MB
  safety_audit.jsonl → ротация при > 20 MB (хранить дольше)

Архивирование:
  brain_2026-03-19.jsonl.gz  (gzip сжатие)
  Хранение: последние 30 дней

Индексация (для быстрого поиска):
  По session_id  → O(1) lookup
  По trace_id    → O(1) lookup
  По module      → O(log n) lookup
  По event type  → O(log n) lookup
  По временному диапазону → O(log n) lookup
```

---

## Детерминированный replay для дебага

```python
# Воспроизвести инцидент по логам:
replayer = LogReplayer(log_file="brain_2026-03-19.jsonl")
replayer.replay_session("sess_01", from_cycle=4500, to_cycle=4530)

# Вывод:
# Replaying 30 cycles from sess_01...
# Cycle 4521: goal=answer_question, confidence=0.78 → respond_hedged ✓
# Cycle 4522: goal=learn_fact, confidence=0.91 → store_fact ✓
# ...
# Replay complete. All cycles reproduced deterministically.
```

---

## Ресурсный бюджет (CPU-only, 32 GB RAM)

| Компонент | RAM | CPU | Поток |
|-----------|-----|-----|-------|
| BrainLogger (JSONL write) | ~10 MB | < 1% | 1 (async) |
| DigestGenerator | ~5 MB | < 1% | 1 (background) |
| TraceBuilder | ~20 MB (индекс) | < 1% | 1 (main) |
| MetricsCollector | ~5 MB | < 1% | 1 (background) |
| Dashboard | ~2 MB | < 1% | 1 (background) |
| **Итого** | **~42 MB** | **< 3%** | **3 потока** |

> Logging overhead должен быть < 5% от общего времени цикла.

---

## Статус реализации

| Компонент | Статус | Файл |
|-----------|--------|------|
| `BrainLogger` (JSONL) | ✅ Реализовано | `brain/logging/brain_logger.py` |
| Уровни логов (DEBUG–CRITICAL) | ✅ Реализовано | `brain/logging/brain_logger.py` |
| `DigestGenerator` | ✅ Реализовано | `brain/logging/digest_generator.py` |
| Ротация логов | ✅ Реализовано | `brain/logging/brain_logger.py` |
| `TraceBuilder` | ✅ Реализовано | `brain/logging/trace_builder.py` |
| `MetricsCollector` | ⬜ Фаза 13.1 | `brain/logging/metrics_collector.py` |
| `Dashboard` | ⬜ Фаза 13.2 | `brain/logging/dashboard.py` |
