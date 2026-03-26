# 🧠 BRAIN.md — Полный разбор человеческого мозга  
## и проектирование искусственного мультимодального мозга (text + media)

> ⚠️ **Disclaimer (март 2026):** Этот документ — **проектная спецификация и vision-документ**.
> Он описывает целевую архитектуру мультимодального мозга, но **не всё из описанного реализовано**.
>
> **Что реализовано (v0.7.0):**
> - ✅ Perception Layer (текст: txt/md/pdf/docx/json) — Этап B
> - ✅ Text Encoder (sentence-transformers 768d, fallback navec 300d) — Этап E
> - ✅ Memory System (5 типов памяти + SQLite WAL persistence) — Этапы D + P1c
> - ✅ Cognitive Core (10-step pipeline, BM25 retrieval, planning, reasoning) — Этапы F/F+/P1b
> - ✅ Output Layer (trace, validation, dialogue, pipeline) — Этап G
> - ✅ Logging & Observability (JSONL, categories, rotation, atexit) — Этап C
> - ✅ Core Infrastructure (EventBus, ResourceMonitor, Scheduler, Contracts) — Этап A
>
> **Что НЕ реализовано:**
> - ⬜ Vision/Audio/Video Ingestors (Этап J — post-MVP)
> - ⬜ Cross-Modal Fusion (Этап K — post-MVP)
> - ⬜ Learning Loop (Этап I — post-MVP)
> - ⬜ Safety Boundaries (Этап L — post-MVP)
> - ⬜ Motivation/Reward System (секция 15) — post-MVP
> - ⬜ CuriosityEngine, MotivationEngine, SalienceEngine — post-MVP
> - ⬜ brain/motivation/ директория — не существует
>
> Актуальный roadmap: [`docs/TODO.md`](TODO.md)

---

## 0) Целевая платформа (Hardware Constraints)

Мозг разрабатывается и запускается на следующей системе:

| Компонент | Характеристика |
|-----------|---------------|
| CPU | AMD Ryzen 7 5700X — 8 ядер / 16 потоков, до 4.6 GHz |
| RAM | DDR4 32 GB, 3200 MHz |
| GPU | — (не используется) |
| Режим | ✅ **CPU-only** |

### Ключевые ограничения и следствия

1. **CPU-only PyTorch** — все тензорные операции на процессоре.  
   → Использовать `torch.set_num_threads(N)` для параллелизма по ядрам.  
   → Избегать тяжёлых трансформеров (GPT-2+, BERT-large) — слишком медленно.

2. **32 GB RAM — главный ресурс** — всё хранится в оперативной памяти.  
   → Лимит рабочей памяти мозга: ~20–22 GB (остальное — ОС + процессы).  
   → Можно использовать модели среднего размера: sentence-transformers large (~1.3 GB), Whisper medium (~1.5 GB).  
   → Суммарный бюджет моделей: до 3 GB без выгрузки.

3. **8 ядер / 16 потоков** — можно использовать параллельную обработку.  
   → Perception pipeline: параллельная обработка разных модальностей.  
   → Scheduler: отдельные потоки для cognitive/memory/learning циклов.

4. **GPU не используется** — все вычисления на CPU.  
   → Зарезервировать возможность подключения GPU в будущем (флаг `USE_GPU=False`).

### Рекомендуемые лимиты ресурсов

| Ресурс | Лимит для мозга | Порог деградации |
|--------|----------------|-----------------|
| RAM | ≤ 22 GB | > 28 GB → снизить частоту тиков |
| CPU | ≤ 70% avg | > 85% → graceful degradation |
| Threads | 8–12 из 16 | оставить 4 потока для ОС |
| Model size | ≤ 3 GB суммарно | > 5 GB → выгружать неактивные |

---

## 1) Цель документа

Этот документ задаёт архитектуру **искусственного мозга**, вдохновлённого принципами человеческого мозга, но адаптированного под цифровую среду.

Ключевая цель:
- не сделать «бота-ответчика»,
- а построить систему, которая **воспринимает, понимает, запоминает, рассуждает, учится и рефлексирует**.

Теперь архитектура учитывает, что мозг сможет работать не только с текстом, но и с:
- документами,
- изображениями,
- аудио,
- видео,
- смешанными мультимодальными источниками.

---

## 2) Как работает человеческий мозг (база для проектирования)

Человеческий мозг — это сеть взаимосвязанных контуров, работающих параллельно и асинхронно:

1. Восприятие сигналов  
2. Предобработка и распознавание  
3. Смысловая интеграция  
4. Оценка значимости/риска  
5. Рабочая память и внимание  
6. Выбор действия  
7. Обучение по ошибке и подкреплению  
8. Консолидация памяти

Главная инженерная идея:  
**разум — это не генерация текста, а управление внутренним состоянием и памятью.**

---

## 3) Ключевые биологические отделы и их инженерные аналоги

### 3.1 Префронтальная кора (лобные доли)
**Функции:** планирование, контроль, цели, принятие решений.  
**Аналог в ИИ:** `Planner`, `GoalManager`, `ExecutiveController`.

### 3.2 Гиппокамп
**Функции:** формирование новых эпизодических воспоминаний, перенос в LTM.  
**Аналог:** `EpisodicMemory`, `ConsolidationEngine`.

### 3.3 Миндалина (amygdala)
**Функции:** быстрая оценка значимости/угрозы, эмоциональная метка.  
**Аналог:** `SalienceEngine`, `PriorityScorer`, `RiskSignal`.

### 3.4 Базальные ганглии
**Функции:** выбор действия среди конкурирующих вариантов.  
**Аналог:** `ActionSelector`, `PolicyGate`.

### 3.5 Таламус
**Функции:** маршрутизация и фильтрация потоков.  
**Аналог:** `InputRouter`, `ModalityRouter`.

### 3.6 Мозжечок
**Функции:** тонкая коррекция, предсказание ошибок, автоматизация навыков.  
**Аналог:** `FastErrorCorrector`, `SkillRefiner`.

---

## 4) Что НЕ нужно в чисто искусственной системе (без физического тела)

Если у системы нет робототехнического тела, можно убрать/упростить:

- моторные контуры управления мышцами и равновесием;
- биологический гомеостаз (голод, жажда, гормоны);
- телесные рефлексы выживания.

---

## 5) Что возвращается при работе с медиафайлами

Если система получает доступ к документам, изображениям, аудио и видео, то требуется цифровой аналог сенсорики:

### 5.1 Цифровое «зрение»
- OCR (извлечение текста с изображений),
- image understanding (объекты, сцены, атрибуты),
- video frame analysis + temporal tracking.

### 5.2 Цифровой «слух»
- ASR (распознавание речи),
- speaker/event detection,
- эмоциональные/интонационные признаки (опционально).

### 5.3 Глубокое чтение документов
- структурный парсинг (заголовки, разделы, таблицы, ссылки),
- извлечение фактов/тезисов/аргументов,
- provenance (из какого источника пришёл факт).

---

## 6) Архитектура мультимодального искусственного мозга

```text
MULTIMODAL BRAIN
├─ 1. Perception Layer
│   ├─ Text Ingestor (txt/md/pdf/docx/json)
│   ├─ Vision Ingestor (img/video frames + OCR)
│   ├─ Audio Ingestor (ASR + acoustic events)
│   └─ Metadata Extractor (source, timestamp, quality)
│
├─ 2. Modality Encoders
│   ├─ Text Encoder
│   ├─ Vision Encoder
│   ├─ Audio Encoder
│   └─ Temporal Encoder (для видео/последовательностей)
│
├─ 3. Cross-Modal Fusion
│   ├─ alignment (text-image/audio-video)
│   ├─ shared latent space
│   └─ confidence calibration
│
├─ 4. Memory System
│   ├─ Working Memory (активный контекст)
│   ├─ Episodic Memory (события во времени)
│   ├─ Semantic Graph (понятия и связи)
│   ├─ Procedural Memory (стратегии/навыки)
│   └─ Source Memory (достоверность и происхождение)
│
├─ 5. Cognitive Core
│   ├─ Planner (цели и план шагов)
│   ├─ Reasoner (causal/associative/analogical)
│   ├─ Uncertainty Monitor
│   └─ Contradiction Detector
│
├─ 6. Learning Loop
│   ├─ online learning
│   ├─ replay + consolidation
│   ├─ hypothesis generation/testing
│   └─ self-reflection
│
└─ 7. Output Layer
    ├─ dialogue answer
    ├─ action proposal
    └─ explainable trace (почему так решено)
```

---

## 7) Кросс-модальная память (обязательный компонент)

Обычной памяти «слово → факт» недостаточно.  
Нужна память связей между разными типами данных:

- `эпизод`: «видео X, кадр t=12s, фраза Y, объект Z»,
- `связь`: «описание в тексте соответствует изображению»,
- `доверие`: источник/качество/уровень шума,
- `время`: когда увидено, как часто подтверждалось.

### Минимальная структура записи

```json
{
  "concept": "нейрон",
  "modal_evidence": [
    {"type": "text", "source": "doc_A.md", "span": "..."},
    {"type": "image", "source": "img_12.png", "region": [0, 0, 100, 100]},
    {"type": "audio", "source": "lecture_3.wav", "time": [12.2, 14.7]}
  ],
  "confidence": 0.81,
  "last_verified": "2026-03-19T10:30:00Z"
}
```

---

## 8) Внимание и приоритизация в мультимодальности

Нужно двухконтурное внимание:

1. **Goal-driven attention** — что важно для текущей цели.
2. **Salience-driven attention** — что выбивается из паттерна/новое/срочное.

Плюс бюджет вычислений (с учётом CPU-only ограничений):
- сколько ресурсов дать тексту,
- сколько — изображениям,
- когда переключаться между модальностями,
- при нехватке CPU — приоритет тексту как наименее затратной модальности.

---

## 9) Обучение в мультимодальном мозге

### 9.1 Online learning
После каждого взаимодействия обновляются:
- ассоциации,
- confidence фактов,
- веса модальных энкодеров (или адаптеров).

### 9.2 Replay learning
Периодически проигрываются важные эпизоды:
- усиливаются устойчивые закономерности,
- удаляется шум,
- корректируются старые гипотезы.

### 9.3 Self-supervised signals
- согласованность «картинка ↔ текст»,
- согласованность «аудио ↔ транскрипт»,
- временная предсказуемость в видео.

---

## 10) Объяснимость (чтобы это был мозг, а не чёрный ящик)

Каждый вывод должен сопровождаться trace:

1. какие источники использованы (text/image/audio/video),
2. какие факты извлечены,
3. какая причинная/ассоциативная цепочка построена,
4. почему выбрано действие,
5. итоговая уверенность и риски.

---

## 11) Границы и безопасность

Мультимодальный мозг обязан иметь:
- оценку надёжности источников,
- детектор конфликтов фактов.

---

## 12) Roadmap реализации (под CPU-only, media-aware архитектуру)

> **Примечание:** Этот roadmap — оригинальный vision из BRAIN.md.
> Актуальный roadmap с точными статусами: [`docs/TODO.md`](TODO.md).
> Ниже — обновлённые статусы по состоянию на v0.7.0.

### Фаза A — Multimodal Perception
- [x] Text ingest pipeline (txt/md/pdf/docx/json) — ✅ Этап B
- [ ] Vision ingest (image parsing + OCR, CPU-only) — ⬜ Этап J
- [ ] Audio ingest (Whisper tiny/base, CPU-only) — ⬜ Этап J
- [x] Унифицированный формат `PerceptEvent` — ✅ Этап A

### Фаза B — Cross-Modal Fusion
- [ ] Shared embedding space (лёгкие модели ≤ 500 MB) — ⬜ Этап K
- [ ] Entity/link alignment между модальностями — ⬜ Этап K
- [ ] Confidence calibration по источникам — ⬜ Этап K

### Фаза C — Memory Upgrade
- [x] Кросс-модальная эпизодическая память — ✅ Этап D (текстовая)
- [x] Source memory (trust/provenance) — ✅ Этап D
- [ ] Temporal indexing + retrieval by evidence — ⬜ Post-MVP

### Фаза D — Cognitive Control
- [x] Planner + Goal stack — ✅ Этап F
- [x] Causal reasoner + contradiction checker — ✅ Этап F/F+
- [x] Resource-aware attention controller (CPU/RAM budget) — ✅ Этап A (ResourceMonitor)

### Фаза E — Self-Development
- [ ] Автоматическое выявление пробелов знаний — ⬜ Post-MVP
- [x] Hypothesis-to-test pipeline — ✅ Этап F+ (HypothesisEngine)
- [ ] Reflection dashboard с метриками качества мышления — ⬜ Post-MVP

---

## 13) Метрики качества мультимодального мозга

1. **Cross-Modal Retrieval Accuracy**  
2. **Source Reliability Calibration**  
3. **Contradiction Detection Rate**  
4. **Reasoning Depth & Coherence**  
5. **Learning Velocity (gap closure)**  
6. **Self-Correction Rate**  
7. **Explainability Completeness**

---

## 14) Обязательная наблюдаемость: читаемое логирование (Readable Logging & Observability)

Для дальнейшего анализа работы искусственного мозга логирование должно быть не «техническим шумом», а инструментом исследования мышления.

### 14.1 Цели логирования
- восстановить ход рассуждения по шагам;
- понять, почему принято конкретное решение;
- видеть источники данных и уровень уверенности;
- диагностировать ошибки памяти/планирования/слияния модальностей;
- поддерживать аудит и безопасность.

### 14.2 Слои логов
1. **System Logs** — запуск/остановка, загрузка модулей, состояние ресурсов (CPU/RAM).
2. **Cognitive Logs** — цели, планы, гипотезы, reasoning-chain, confidence, contradiction flags.
3. **Memory Logs** — запись/чтение из working/episodic/semantic memory, консолидация, забывание.
4. **Perception Logs** — входные события text/image/audio, качество извлечения, метаданные источника.
5. **Learning Logs** — online update, replay, изменения весов/оценок, влияние на качество.
6. **Safety/Audit Logs** — срабатывание политик, фильтров, redaction приватных данных.

### 14.3 Формат события (единый JSONL)
Каждое событие — одна JSON-строка:

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
  "state": {"goal": "verify_claim", "cpu_pct": 62, "ram_mb": 4200},
  "decision": {"action": "cross_modal_check", "confidence": 0.81},
  "latency_ms": 37,
  "notes": "selected due to contradiction risk"
}
```

### 14.4 Уровни логов
- `DEBUG` — детальная трассировка (в dev/исследованиях),
- `INFO` — нормальная работа циклов,
- `WARN` — подозрительные/неполные данные или нагрузка > 70% CPU,
- `ERROR` — сбои модулей/невозможность шага,
- `CRITICAL` — риск целостности системы или нагрузка > 85% CPU.

### 14.5 Читаемость для человека
Обязательно иметь два представления:
- **machine logs** (JSONL),
- **human digest** (сводка по циклу: цель → шаги → решение → ошибки → next actions).

Пример digest:
```
Cycle 4521
  Goal:         validate hypothesis H-17
  Evidence:     doc_A, frame_33, audio_12
  Contradiction: detected in source pair (doc_A vs audio_12)
  Decision:     request additional evidence
  Confidence:   0.81 → 0.66
  CPU:          58% | RAM: 4.1 GB
```

### 14.6 Трассировка причинности
Каждое решение должно быть связано с:
- входными источниками (`input_ref`),
- активированными фактами памяти (`memory_refs`),
- промежуточными гипотезами (`hypothesis_refs`),
- финальным действием (`decision_ref`).

**Никаких «магических» ответов без trace chain.**

### 14.7 Эксплуатация логов
- ротация и лимиты объёма;
- разделение горячих/архивных логов;
- индексация по `session_id`, `trace_id`, `module`, `event`;
- детерминированные replay-сценарии для дебага.

### 14.8 Минимальные KPI наблюдаемости
1. Trace Completeness (% решений с полной цепочкой причинности)  
2. Error Localization Time (время до локализации причины сбоя)  
3. Replay Reproducibility (повторяемость инцидента по логам)  
4. Contradiction Resolution Time  
5. Logging Overhead (% накладных расходов по времени/памяти)

---

## 15) Система мотивации и вознаграждения (Средний мозг)

Без системы вознаграждения мозг — **реактивная машина**. Он отвечает только когда спросят, не имеет внутренней мотивации и не знает, какие стратегии работают лучше.

### 15.1 Что служит вознаграждением для цифрового мозга

| Тип | Триггер | Значение |
|-----|---------|----------|
| **Epistemic** (познавательное) | Узнал новый факт, закрыл пробел в знаниях | +0.8 — самое сильное |
| **Accuracy** (точность) | Пользователь подтвердил ответ | +1.0 — внешнее подтверждение |
| **Coherence** (согласованность) | Разрешил противоречие | +0.6 — удовлетворение от порядка |
| **Completion** (завершение) | Выполнил план/цель | +0.7 — достижение |
| **Efficiency** (эффективность) | Быстрый ответ с высокой уверенностью | +0.3 — оптимизация |
| **Penalty** | Пользователь исправил ошибку | −0.5 — ошибка предсказания |

### 15.2 Биологический аналог

| Структура | Функция | Аналог |
|-----------|---------|--------|
| Вентральная область покрышки (VTA) | Источник дофамина | `RewardEngine` |
| Прилежащее ядро | Накопление дофамина | `MotivationEngine` |
| Дофаминергические пути | Передача к Префронтальной коре | `RewardSignal` → `Planner` |
| Система предсказания ошибки | Δ(ожидаемое − полученное) | `PredictionError` |

**Ключевой принцип:** дофамин выделяется не при получении награды, а при **ошибке предсказания** — разнице между ожидаемым и реальным результатом.

### 15.3 Компоненты

```
brain/motivation/
  ├── reward_engine.py      ← RewardSignal, RewardEngine (5 типов + prediction error)
  ├── motivation_engine.py  ← MotivationState, MotivationEngine (накопление, decay)
  └── curiosity_engine.py   ← CuriosityEngine (внутренняя мотивация к исследованию)
```

### 15.4 Влияние на другие модули

```
MotivationState.epistemic_score > 0.7 (высокое любопытство):
  → Planner: добавить цель "explore_unknown_concept"
  → HypothesisEngine: генерировать больше гипотез
  → AttentionController: увеличить бюджет на memory.retrieve()

MotivationState.preferred_goal_types["answer_question"] = 0.9:
  → Planner: приоритизировать answer_question цели

MotivationState.is_frustrated = True:
  → Planner: сменить стратегию рассуждения
  → ReplayEngine: запустить replay успешных паттернов

prediction_error > 0.2 ("лучше ожидаемого"):
  → MotivationEngine.boost(action_type)
  → ReplayEngine.mark_as_high_value(episode)
```

### 15.5 Любопытство (CuriosityEngine)

Любопытство = вознаграждение за исследование **неизвестного**:
- Чем меньше мозг знает о концепте X → тем выше `curiosity_score(X)`
- Чем больше мозг знает о концепте X → тем ниже `curiosity_score(X)`

Это создаёт естественную мотивацию заполнять пробелы в знаниях без внешних команд.

---

## 17) Алгоритмическая основа — от метафор к формулам

> **Принцип:** каждый биологический модуль = конкретная функция с явными весами.  
> Метафора задаёт *что* делать, формула задаёт *как* это измерить.

### 17.1 Правило проектирования

```
❌ Плохо (метафора без алгоритма):
    SalienceEngine.evaluate(input)  # "как миндалина"

✅ Хорошо (метафора + явная формула):
    salience = 0.25*novelty + 0.35*urgency + 0.25*threat + 0.15*goal_relevance
```

Каждый модуль должен иметь:
1. **Входные данные** — что принимает (типы, диапазоны)
2. **Формулу** — как вычисляет (веса, пороги)
3. **Выходные данные** — что возвращает (структура, диапазон)
4. **Trace** — почему получился именно этот результат

### 17.2 Сводная таблица формул

| Модуль | Биологический аналог | Формула |
|--------|---------------------|---------|
| `SalienceEngine` | Миндалина | `0.25*novelty + 0.35*urgency + 0.25*threat + 0.15*goal_relevance` |
| `ActionSelector` | Базальные ганглии | `0.35*confidence + 0.30*goal_relevance + 0.20*feasibility + 0.15*success_rate` |
| `HypothesisEngine` | Префронтальная кора | `0.40*evidence + 0.20*source_trust + 0.20*coherence − 0.20*contradiction` |
| `UncertaintyMonitor` | Орбитофронтальная кора | Пороги: >0.85 HIGH, >0.60 MEDIUM, >0.40 LOW, <0.40 VERY_LOW |
| `ConsolidationEngine` | Гиппокамп | `decay: confidence *= (1 − rate)`, rate адаптируется к RAM% |
| `RewardEngine` | VTA (дофамин) | `prediction_error = actual_reward − expected_reward` |
| `MotivationEngine` | Прилежащее ядро | `motivation = EMA(reward_signals)`, decay ×0.95 каждые 100 циклов |
| `CuriosityEngine` | Исследовательское поведение | `curiosity(X) ∝ 1 / knowledge_coverage(X)` |

### 17.3 Multi-stage Retrieval (алгоритм поиска в памяти)

Вместо одного поиска — три последовательных слоя:

```
Stage 1 — BROAD SEARCH (широкий поиск):
  semantic.search(query, top_n=20)
  episodic.search(query, top_n=20)
  working.search(query, top_n=10)
  → pool из ~50 кандидатов

Stage 2 — FILTER (фильтрация):
  filter: source_trust >= 0.4          # отсеять ненадёжные источники
  filter: confidence >= 0.3            # отсеять слабые факты
  filter: modality == goal.modality    # если цель требует конкретную модальность
  filter: age < max_age                # если цель time-sensitive
  → pool из ~15–20 кандидатов

Stage 3 — RERANK (переранжирование):
  score(item) = (
      0.40 * relevance_to_query    +   # семантическая близость к запросу
      0.30 * source_trust          +   # доверие к источнику
      0.20 * recency               +   # свежесть (1 / age_days)
      0.10 * graph_distance_bonus      # близость в семантическом графе
  )
  → top-K результатов (обычно K=5–10)
```

**Query Expansion** (расширение запроса через семантический граф):
```python
# "нейрон" → ["нейрон", "нервная клетка", "синапс", "аксон", "мозг"]
expanded = [query] + semantic_memory.get_related(query, top_n=4)
results = [search(q) for q in expanded]
deduplicated = deduplicate_by_concept(results)
```

**Evidence Bundling** (группировка доказательств):
```python
# Не просто список фактов, а структурированный пакет
bundle = EvidenceBundle(
    text_facts   = [f for f in results if f.modality == "text"],
    episodes     = [e for e in results if isinstance(e, Episode)],
    source_trust = mean(source_memory.get_trust(r.source_ref) for r in results),
    confidence   = mean(r.confidence for r in results),
    contradictions = contradiction_detector.check_all(results),
)
```

### 17.4 Reasoning Loop (центральный алгоритм мышления)

```
retrieve_staged(query)          # Stage 1→2→3
    ↓
generate_hypotheses(facts)      # шаблоны: causal, associative, analogical
    ↓
score_hypotheses(hypotheses)    # 0.40*evidence + 0.20*trust + 0.20*coherence − 0.20*contradiction
    ↓
select_best(top_n=2)            # UncertaintyMonitor + ContradictionDetector
    ↓
score_actions(candidates)       # 0.35*confidence + 0.30*relevance + 0.20*feasibility + 0.15*history
    ↓
act(best_action)                # respond / clarify / gather / explore
    ↓
store_episode(result)           # обновить память + source trust
```

### 17.5 Гибридная интеграция LLM (опциональный компонент)

Архитектура позволяет подключить LLM как **один из модулей**, не заменяя символическое ядро:

```
Пользователь
    │
    ▼
[LLM — языковой интерфейс]          ← опциональный компонент
  • понимает запрос на естественном языке
  • превращает в PerceptEvent (JSON)
  • форматирует CognitiveResult для человека
    │
    ▼
[brain/ — символическое ядро]       ← детерминированное ядро
  • memory/ — хранит факты и эпизоды
  • cognition/ — планирует и рассуждает
  • safety/ — верифицирует результат
    │
    ▼
[LLM — языковой выход]              ← опциональный компонент
  • объясняет решение человеку
  • форматирует ответ
```

**Принцип:** LLM — переводчик между языком и структурой. Решения принимает `brain/`.

---

## 16) Финальный принцип

Система становится «мозгом», когда:
- живёт в состоянии и целях,
- помнит опыт,
- извлекает и проверяет знания,
- учится из ошибок,
- объясняет, почему пришла к выводу,
- оставляет **читаемый, воспроизводимый след мышления**,
- и делает всё это **автономно**, в рамках доступных ресурсов системы.

С мультимодальным входом это уже не текстовый агент, а **цифровой когнитивный организм**, где «видеть/слышать/читать» реализовано как вычислительное восприятие данных — даже на CPU-only железе.
