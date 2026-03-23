# PLANS.md

# План развития проекта с учётом текущего состояния, идей из Axicor и коррекции по ARCHITECTURE.md

## Changelog

- **v3 (2026-03-23)**: добавлены формат тестового корпуса, правило graceful degradation для pipeline и журнал версий плана.
- **v2 (2026-03-23)**: добавлены Definition of Done, dependency graph, test data strategy, fallback для Этапа F, optional LLM bridge, checkpoints, тайминги и retrieval-метрики.
- **v1 (2026-03-23)**: начальная версия стратегического плана с учётом текущего проекта, Axicor и роли `ARCHITECTURE.md`.

## 1. Зачем этот документ

Этот файл фиксирует итог обсуждения по трём направлениям:

1. текущее положение проекта;
2. что именно стоит взять из Axicor;
3. как скорректировать роль `ARCHITECTURE.md` в общем roadmap.

Цель документа — не переписать `README.md`, `TODO.md` или `BRAIN.md`, а дать **практический стратегический слой**:
- что делать сейчас;
- что делать позже;
- что не тащить в ядро проекта;
- как не потерять темп MVP;
- какие условия считать закрытием ключевых фаз.

---

## 2. Текущее состояние проекта

### Уже реализовано и должно оставаться базой

Проект уже имеет сильный фундамент. В ядре уже есть:

- `brain/core/*`:
  - `events.py`
  - `contracts.py`
  - `event_bus.py`
  - `scheduler.py`
  - `resource_monitor.py`
- `brain/logging/*`
- `brain/perception/*` для text-only MVP
- `brain/memory/*`:
  - WorkingMemory
  - SemanticMemory
  - EpisodicMemory
  - SourceMemory
  - ProceduralMemory
  - ConsolidationEngine
  - MemoryManager

Это **не переписывать**. Это текущая опорная платформа проекта.

### Текущий фактический статус

Проект уже закрыл:

- Runtime / always-on loop
- Logging & observability
- Text-only perception
- Memory system

Критический следующий путь:

```text
E → F → G → T.3
```

Где:

- **E** — Minimal Text Encoder
- **F** — Cognitive MVP
- **G** — Explainable Output
- **T.3** — text-only e2e tests

### Главный принцип

Сейчас приоритет — **не архитектурная экспансия**, а:
- довести живой text-only pipeline;
- получить стабильный end-to-end reasoning loop;
- только после этого расширять retrieval, CUDA, multimodal и research-ветки.

---

## 3. Главный итог обсуждения

### Что признано верным

#### 3.1. База проекта сильная
Проект уже ближе к системной cognitive platform, чем к pet-project.

#### 3.2. Самый зрелый модуль сейчас — память
Memory layer — самый стабильный и ценный слой проекта. На него должен опираться весь cognitive MVP.

#### 3.3. Этап F — главный gate
Именно Cognitive Core решит, станет ли проект просто инфраструктурой или живой reasoning-системой.

#### 3.4. Template-based reasoning — нормальный старт, но не финал
Для MVP допустимо:
- retrieve
- hypotheses
- score
- select
- act

Но в будущем нужен **гибрид**:
- символическое ядро — основное;
- LLM — как дополнительный языковой и гипотезный модуль, а не как замена `brain/`.

#### 3.5. Semantic graph не заменяет embedding retrieval
Graph retrieval полезен для:
- явных связей,
- причинности,
- объяснимости.

Embedding/vector retrieval нужен для:
- zero-shot similarity,
- парафразов,
- fuzzy input,
- масштабирования корпуса.

Итог:
- для раннего MVP graph + staged retrieval достаточно;
- после первого рабочего text-only e2e почти наверняка понадобится vector layer.

---

## 4. Что брать из Axicor

Важно: брать **не код как основу**, а архитектурные паттерны.

### Брать в проект

#### 4.1. Разделение на hot path и cold path
Нужен аналог Day/Night-cycle, но в форме cognitive runtime.

**Hot path**:
- ingest
- encode
- retrieve
- reason
- answer
- log

**Cold path**:
- consolidation
- reindex
- replay
- pruning
- checkpoints
- self-reflection
- distillation

#### 4.2. Event-driven discipline
У проекта уже есть `EventBus`. Это надо не просто сохранить, а усилить как основу внутренних состояний:

- `percept_received`
- `memory_updated`
- `hypothesis_generated`
- `reasoning_completed`
- `response_emitted`
- `resource_policy_changed`
- `maintenance_cycle_started`
- `maintenance_cycle_done`

Axicor полезен здесь не механикой спайков, а дисциплиной событий и циклов.

#### 4.3. Разделение runtime-state и artifacts
Нужно жёстко разделить:

- исходные данные,
- memory state,
- embeddings/vector state,
- checkpoints,
- traces/logs,
- derived artifacts.

Это сильно упростит масштабирование и восстановление.

#### 4.4. Maintenance-first thinking
Не только отвечать, но и обслуживать собственное состояние.

После MVP обязательно добавить:
- memory compaction
- replay
- checkpointing
- background validation
- self-reflection hooks

#### 4.5. Compute backend abstraction
Полезная идея из Axicor — отделять вычислительный слой от логики.

В проекте это должно принять форму:

```text
brain/logic
    ↓
compute backend
    ├─ CPU
    └─ CUDA (позже)
```

Не связывать reasoning-логику напрямую с CUDA.

### Не брать в ядро проекта

#### 4.6. Не переносить в core
Не нужно тащить в основной roadmap:

- SNN как основу когнитивного ядра;
- voxel/brain-simulation;
- ghost axons / shard routing;
- integer-only physics как универсальный стандарт проекта;
- low-level GPU runtime как центр всей архитектуры.

Это исследовательские идеи для другого класса систем.

#### 4.7. Не использовать код Axicor как прямую основу
Причины:
- проект pre-alpha;
- есть признаки drift между спеками и кодом;
- у него рискованные low-level контракты;
- в hot path уже видны потенциальные рассогласования по ABI/типам/копированию.

Брать идеи — да. Брать как фундамент — нет.

---

## 5. Коррекция по ARCHITECTURE.md

### Итоговая позиция

`ARCHITECTURE.md` — это **интересная исследовательская линия**, но не то, что должно определять ближайший MVP.

Его нельзя ставить в центр текущего roadmap.

### Почему
Текущий проект уже строится как:

- text-first MVP
- memory-first cognition
- deterministic symbolic core
- explainable output
- observable runtime

А `ARCHITECTURE.md` описывает **богатый когнитивный нейронный примитив**:
- basal/apical dendrites
- prediction error
- tonic/burst regimes
- neuromodulation
- six plasticity rules
- structural plasticity
- metaplasticity

Это хорошо как R&D-концепт, но слишком тяжело как ближайший engineering target.

### Новая роль ARCHITECTURE.md

Использовать его как:

#### 5.1. Research Track
Отдельная экспериментальная ветка, а не часть обязательного MVP.

#### 5.2. Источник будущих идей
Оттуда можно позже забрать:
- predictive coding motifs
- surprise / novelty signal
- burst-like salience
- local confidence/error logic
- gated plasticity ideas

#### 5.3. Не использовать как блокер этапов E/F/G
Ни Text Encoder, ни Cognitive MVP, ни Output layer не должны ждать реализации “когнитивного нейрона”.

---

## 6. Как упростить ARCHITECTURE.md до реалистичной v1

Если к нему вернуться позже, делать это как **упрощённый прототип**, а не как полный brain-cell stack.

### Оставить в v1

1. basal/apical split  
2. prediction error  
3. tonic/burst-like response regimes  
4. один локальный learning rule  
5. один reward-modulated rule  
6. простую homeostasis/adaptation

### Не тащить в v1

- все 6 правил пластичности одновременно;
- полную нейромодуляторную систему;
- full structural plasticity;
- мета-пластичность;
- глубокую многослойную circuit-иерархию как обязательный baseline.

### Новая формулировка

`ARCHITECTURE.md` = **R&D module for future cognitive substrate experiments**,  
а не **current implementation target for the core project**.

---

## 7. Retrieval-план после обсуждения

### Текущий правильный стек retrieval

#### Сейчас
- semantic graph
- source trust
- episodic recall
- staged retrieval
- evidence bundling

#### Следующее усиление
Добавить embedding/vector layer как отдельный модуль.

### Целевая retrieval-схема

```text
Query
 → query normalization
 → graph expansion
 → vector retrieval
 → merge candidates
 → rerank
 → evidence bundle
 → reasoner
```

### Правильное разделение ролей

- **Graph** = explicit knowledge
- **Vector index** = latent similarity
- **Reranker** = precision
- **Reasoner** = final decision

### Практический вывод
Embedding layer не обязателен как условие старта MVP,  
но почти наверняка обязателен как условие роста системы после первого стабильного text-only e2e.

---

## 8. CUDA-план

### Позиция
CUDA в проекте нужно рассматривать как **compute backend**, а не как центр архитектуры.

### Где CUDA будет полезна потом

#### В первую очередь
- text encoder
- embeddings
- reranker
- local LLM inference
- batch maintenance jobs

#### Позже
- multimodal encoders
- heavier retrieval/ranking
- replay/distillation jobs

### Чего не делать
Не переписывать core architecture “под CUDA”.
Логика проекта должна работать и на CPU.

### Целевой compute слой

```text
brain/
├─ logic/
├─ memory/
├─ cognition/
├─ output/
└─ compute/
   ├─ cpu_backend.py
   └─ cuda_backend.py
```

---

## 9. Обновлённый стратегический roadmap

### Фаза 0 — не трогать базу
Считать завершённые модули опорой.
Не переписывать memory/runtime/logging/perception без конкретной причины.

### Фаза 1 — довести обязательный text-only MVP (~4–6 недель)
Приоритет:

1. **E — Text Encoder**
2. **F — Cognitive Core MVP**
3. **G — Output MVP**
4. **T.3 — Text-only e2e tests**

Это главный ближайший коридор.

### Фаза 2 — стабилизация и верификация (~2–3 недели)
После первого e2e:

- regression
- load/degradation tests
- confidence validation
- reasoning trace validation
- performance profiling

### Фаза 2.5 — Optional LLM Bridge (~1–2 недели)
Подключается только если:
- template-based hypothesis generation упирается в качество;
- symbolic core уже стабилен;
- нужен быстрый способ усилить generation hypotheses без слома explainability.

Роль LLM в этой фазе:
- hypothesis generator;
- paraphrase helper;
- language-facing assistant;
- optional query reformulation.

Не роль LLM:
- не замена memory;
- не замена symbolic scoring;
- не замена final decision layer.

### Фаза 3 — retrieval uplift (~2–4 недели)
После стабильного e2e:

- vector index
- embedding cache
- reranker
- retrieval quality benchmarks

### Фаза 4 — maintenance loop (~2–3 недели)
После retrieval uplift:

- replay
- compaction
- checkpointing
- self-reflection
- gap detection

### Фаза 5 — CUDA backend (~1–3 недели на первый useful backend)
Только после того, как будут понятны реальные bottlenecks.

### Фаза 6 — multimodal path
Затем уже J/K и полноценная multimodality.

### Фаза 7 — research branch
Отдельно от mainline:
- experiments from `ARCHITECTURE.md`
- predictive neuron prototypes
- circuit-level substrate R&D

---

## 10. Что делать прямо сейчас

### 10.0. Definition of Done для Фазы 1

**Text-only e2e считается закрытым, когда одновременно выполнены все условия:**

- [ ] Система принимает текстовый вопрос на естественном языке.
- [ ] Проходит путь: `encode → retrieve → hypothesize → score → select → generate`.
- [ ] Возвращает ответ в формате `text + confidence + trace + log`.
- [ ] Trace включает:
  - использованные источники,
  - confidence,
  - альтернативные гипотезы,
  - финальный критерий выбора.
- [ ] Работает минимум на 3 типах вопросов:
  - factual,
  - causal,
  - comparative.
- [ ] Работает на минимальном фиксированном тестовом корпусе.
- [ ] На CPU укладывается в целевой бюджет ответа:
  - target: `< 5 секунд` на end-to-end запрос,
  - желательно p50 заметно ниже этого порога.
- [ ] Выдерживает `100` последовательных запросов без crash и без потери обязательных артефактов trace/log.
- [ ] Имеет хотя бы один e2e regression scenario на каждый тип вопроса.

**Принцип graceful degradation:** если на любом этапе pipeline (`encode`, `retrieve`, `hypothesize`, `score`, `select`, `generate`) результат пустой или недостаточный, система возвращает partial response с явным указанием места разрыва и доступных артефактов, а не crash.

Пока хотя бы один пункт не закрыт, Фаза 1 считается **в процессе**, а не завершённой.

### 10.1. Порядок зависимостей внутри Фазы 1

Ниже — рекомендуемый порядок реализации, чтобы не строить слои в вакууме.

#### Шаг 1 — можно начинать сразу
- `brain/encoders/text_encoder.py`

Зависимости: нет.

#### Шаг 2 — контекст и сбор входа в cognitive core
- `brain/cognition/context.py`

Зависимости:
- encoder
- memory access layer
- staged retrieval hooks

#### Шаг 3 — управление целями и простое планирование
- `goal_manager.py`
- `planner.py`

Зависимости:
- context

#### Шаг 4 — hypothesis and reasoning core
- `hypothesis_engine.py`
- `reasoner.py`
- `uncertainty_monitor.py`
- `action_selector.py`

Зависимости:
- context
- retrieval outputs
- planner / goals

Рекомендуемый порядок внутри блока:
1. `hypothesis_engine.py`
2. `reasoner.py`
3. `uncertainty_monitor.py`
4. `action_selector.py`

#### Шаг 5 — explainable output
- `brain/output/*`

Зависимости:
- action selector
- reasoner outputs
- trace objects

#### Шаг 6 — сквозные тесты
- text-only e2e tests

Зависимости:
- всё выше

#### Сводная зависимость

```text
text_encoder
  ↓
context
  ↓
goal_manager + planner
  ↓
hypothesis_engine
  ↓
reasoner
  ↓
uncertainty_monitor
  ↓
action_selector
  ↓
output
  ↓
e2e tests
```

### 10.2. Checkpoints и метрики внутри Фазы 1

#### После Text Encoder
Проверить:
- CPU latency;
- размер модели;
- устойчивость к базовым парафразам;
- качество на минимальном корпусе.

Минимальные ориентиры:
- модель не должна разрушать CPU-only режим;
- encoder должен быть достаточно быстрым для интеграции в `< 5 сек` e2e budget.

#### После Cognitive Core
Проверить:
- есть ли не пустые гипотезы на всех 3 типах вопросов;
- виден ли смысловой разрыв между основной и альтернативными гипотезами;
- работает ли confidence как полезный сигнал, а не случайное число.

#### После Output Layer
Проверить:
- trace читаем человеком;
- trace стабилен между повторными прогонами;
- источники и confidence действительно доходят до финального ответа.

#### Для Фазы 3 заранее закрепить метрики retrieval
Минимум:
- Recall@5
- MRR@10
- manual eval на небольшом gold set

### 10.3. Жёсткий ближайший приоритет
Закрыть:
- `brain/encoders/text_encoder.py`
- `brain/cognition/context.py`
- `goal_manager.py`
- `planner.py`
- `hypothesis_engine.py`
- `reasoner.py`
- `uncertainty_monitor.py`
- `action_selector.py`
- `brain/output/*`
- text-only e2e tests

### 10.4. Test Data Strategy

Нельзя ждать хорошего e2e без нормального тестового корпуса.

#### Минимальный corpus v1
Собрать фиксированную text-only knowledge base, достаточную для валидации pipeline:
- 20–50 коротких документов / фактов / заметок;
- явные связи между понятиями;
- несколько синонимов / парафразов;
- несколько причинных связей;
- несколько сравнительных фактов.

#### Требования к тестовым данным
Корпус должен покрывать:
- factual вопросы;
- causal вопросы;
- comparative вопросы;
- fuzzy/noisy phrasing;
- минимум несколько случаев с конфликтующими или близкими фактами.

#### Что нужно хранить рядом с корпусом
- gold answers;
- expected evidence / source set;
- допустимые альтернативные гипотезы;
- expected confidence band (грубо, не как жёсткое число).

#### Рекомендуемая структура хранения v1

```text
test_data/
├── corpus/
│   ├── doc_001.md
│   ├── doc_002.md
│   └── ...
├── questions/
│   ├── factual.yaml
│   ├── causal.yaml
│   └── comparative.yaml
└── README.md
```

Где:
- `corpus/` — исходные документы или fact sheets;
- `questions/*.yaml` — вопросы, gold answers, expected sources, допустимые альтернативы;
- `README.md` — правила пополнения корпуса и договорённости по разметке.

#### Практическое правило
Пока нет зафиксированного минимального корпуса и набора gold-questions, e2e-тесты считаются скорее smoke tests, а не валидацией reasoning pipeline.

### 10.5. Fallback-план для Этапа F

Этап F — главный gate. Значит, у него должен быть заранее определённый fallback.

#### Условие срабатывания fallback
Если после **2 осмысленных итераций улучшения** template-based hypothesis engine:
- hypotheses остаются слишком плоскими;
- coverage на test corpus неудовлетворителен;
- quality reasoning не позволяет закрыть Definition of Done Фазы 1,

то включается fallback.

#### Fallback-сценарий
Подключить **LLM как hypothesis generator**, при этом оставить:
- symbolic retrieval,
- symbolic scoring,
- symbolic selection,
- explainable output,
- trace/logging.

#### Как трактовать fallback
Это **не провал проекта**, а **гибридный MVP**.

То есть:
- если template-based reasoning хватает — отлично;
- если нет — проект всё равно движется дальше через hybrid bridge.

### 10.6. Внести архитектурные уточнения
После создания этого файла стоит:
- отметить `ARCHITECTURE.md` как R&D / experimental track;
- добавить в TODO/notes напоминание, что vector retrieval идёт после первого стабильного e2e;
- заранее выделить место под `compute/` и будущий backend abstraction;
- продумать maintenance-cycle как следующий слой после MVP.

### 10.7. Не расползаться
До завершения text-only e2e не расширять проект в сторону:
- vision/audio/video;
- full multimodal fusion;
- reward system;
- research neuron integration.

---

## 11. Короткий вердикт

### В одной фразе

Проект уже имеет сильную базу и правильное направление;  
из Axicor стоит взять runtime-дисциплину, hot/cold split, maintenance thinking и backend abstraction;  
`ARCHITECTURE.md` нужно оставить как сильную research-ветку, но не как ближайший блокер MVP;  
главный следующий шаг — довести живой text-only e2e цикл, а затем усилить retrieval через embeddings/vector index и только потом думать о CUDA и более глубоком когнитивном субстрате.

---

## 12. Правило принятия решений на ближайшие этапы

Если возникает идея, задавать три вопроса:

1. Помогает ли это закрыть text-only e2e?
2. Улучшает ли это наблюдаемость, стабильность или retrieval?
3. Не уводит ли это проект в research раньше времени?

Если ответы:
- **да / да / нет** → брать;
- **нет / нет / да** → откладывать в R&D.

---

## 13. Финальная формула проекта

```text
Strong memory foundation
+ deterministic cognitive MVP
+ explainable output
+ staged retrieval
+ future vector layer
+ optional LLM bridge
+ optional CUDA backend
+ separate R&D neuron branch
=
реалистичная и масштабируемая траектория проекта
```
