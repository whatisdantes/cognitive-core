# 🧠 Слой 3: Cross-Modal Fusion (Ассоциативная кора)
## Подробное описание архитектуры и работы

---

## Что такое Ассоциативная кора в биологии

В человеческом мозге **Ассоциативная кора** — это зоны, которые:
- **объединяют** сигналы от разных сенсорных зон (зрение + слух + осязание),
- **связывают** новую информацию с уже известной,
- **формируют** единое восприятие объекта из разных модальностей,
- **обнаруживают** противоречия между источниками.

Пример: когда вы видите собаку и слышите лай — ассоциативная кора связывает эти два сигнала в единый образ «собака».

Аналогично работает наш **Cross-Modal Fusion** — он берёт векторы от разных энкодеров и **выравнивает их в единое смысловое пространство**.

---

## Роль в искусственном мозге

```
EncodedPercept(s) от Сенсорной коры
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                 CROSS-MODAL FUSION                      │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │           1. SharedSpaceProjector                │   │
│  │                                                  │   │
│  │  text_vec  (768d) → Linear(768→512) → 512d       │   │
│  │  image_vec (512d) → (уже 512d, CLIP)  → 512d     │   │
│  │  audio_vec (768d) → Linear(768→512) → 512d       │   │
│  │                                                  │   │
│  │  Все векторы → единое пространство 512d          │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                               │
│  ┌──────────────────────▼───────────────────────────┐   │
│  │           2. EntityLinker                        │   │
│  │                                                  │   │
│  │  "нейрон" (текст) ←→ фото_нейрона.jpg (образ)   │   │
│  │  "нейрон" (текст) ←→ "нейрон" (аудио)           │   │
│  │                                                  │   │
│  │  cosine_sim > threshold → создать связь          │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                               │
│  ┌──────────────────────▼───────────────────────────┐   │
│  │           3. ConfidenceCalibrator                │   │
│  │                                                  │   │
│  │  quality источника × согласованность модальностей│   │
│  │  → итоговый confidence 0.0–1.0                   │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                               │
│  ┌──────────────────────▼───────────────────────────┐   │
│  │           4. ContradictionDetector               │   │
│  │                                                  │   │
│  │  текст говорит X, изображение показывает ¬X      │   │
│  │  → флаг CONTRADICTION + снизить confidence       │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         │                               │
└─────────────────────────┼───────────────────────────────┘
                          │
                          ▼
                  FusedPercept(s)
    {unified_vector, entity_links, confidence, contradictions}
                          │
                          ▼
               Memory System (Слой 4)
```

---

## Компоненты Cross-Modal Fusion

### 1. `SharedSpaceProjector` — единое пространство

**Проблема:** разные энкодеры дают векторы разной размерности:
- TextEncoder → 768d
- VisionEncoder → 512d (CLIP)
- AudioEncoder → 768d

Для сравнения нужно привести всё к **одной размерности**.

**Решение:** линейные проекции в общее пространство 512d:

```
text_vec  (768d) ──► W_text  (768×512) ──► proj_text  (512d)
image_vec (512d) ──► Identity           ──► proj_image (512d)  ← CLIP уже 512d
audio_vec (768d) ──► W_audio (768×512) ──► proj_audio (512d)
```

**Обучение проекций:**
- `W_text` и `W_audio` обучаются на парах (текст, изображение) через CLIP-like loss
- Цель: `cosine_sim(proj_text, proj_image)` → максимум для совпадающих пар
- Начальная инициализация: Xavier uniform

**Пример:**
```python
text_vec  = TextEncoder.encode("нейрон под микроскопом")   # 768d
image_vec = VisionEncoder.encode(фото_нейрона)              # 512d

proj_text  = W_text @ text_vec    # 512d
proj_image = image_vec            # 512d (уже готов)

similarity = cosine_similarity(proj_text, proj_image)
# → 0.87  ← текст и изображение говорят об одном
```

---

### 2. `EntityLinker` — связывание сущностей между модальностями

**Задача:** найти, что одно и то же понятие встречается в разных модальностях.

```
Входные данные за сессию:
  text_1:  "Нейрон — клетка нервной системы"  → proj_vec_1
  image_1: фото_нейрона.jpg                   → proj_vec_2
  audio_1: "...это нейрон..."                 → proj_vec_3

EntityLinker:
  sim(proj_vec_1, proj_vec_2) = 0.87 > threshold(0.75) → LINK
  sim(proj_vec_1, proj_vec_3) = 0.91 > threshold(0.75) → LINK
  sim(proj_vec_2, proj_vec_3) = 0.84 > threshold(0.75) → LINK

Результат: EntityCluster("нейрон") = {text_1, image_1, audio_1}
```

**Алгоритм:**
1. Для каждого нового `EncodedPercept` вычислить проекцию в 512d
2. Сравнить с существующими кластерами (cosine similarity)
3. Если `sim > threshold` → добавить в кластер
4. Если нет совпадений → создать новый кластер
5. Кластер → `EntityCluster` с именем (из ключевых слов)

**Пороги:**
```
sim > 0.90  → STRONG LINK   (почти наверняка одно и то же)
sim > 0.75  → LINK          (вероятно одно и то же)
sim > 0.60  → WEAK LINK     (возможно связано)
sim < 0.60  → NO LINK       (разные понятия)
```

**Структура `EntityCluster`:**
```python
@dataclass
class EntityCluster:
    cluster_id: str              # уникальный ID
    name: str                    # "нейрон" (из ключевых слов)
    centroid: np.ndarray         # средний вектор кластера (512d)
    members: List[EncodedPercept] # все связанные перцепты
    modalities: Set[str]         # {"text", "image", "audio"}
    confidence: float            # уверенность в кластере
    created_at: str              # время создания
    last_updated: str            # последнее обновление
```

---

### 3. `ConfidenceCalibrator` — калибровка уверенности

**Задача:** вычислить итоговый `confidence` для каждого факта/кластера.

**Формула:**
```
confidence = base_quality × modality_agreement × source_trust × recency_factor

где:
  base_quality      = среднее quality всех источников в кластере
  modality_agreement = согласованность между модальностями (0.0–1.0)
  source_trust      = доверие к источникам (из SourceMemory)
  recency_factor    = насколько свежие данные (экспоненциальное затухание)
```

**Примеры:**

```
Кластер "нейрон":
  Источники: [pdf(quality=0.9), jpg(quality=0.85), mp3(quality=0.91)]
  base_quality = (0.9 + 0.85 + 0.91) / 3 = 0.887

  Согласованность:
    sim(text, image) = 0.87
    sim(text, audio) = 0.91
    sim(image, audio) = 0.84
    modality_agreement = mean([0.87, 0.91, 0.84]) = 0.873

  source_trust = 0.9  (из SourceMemory, доверенный источник)
  recency_factor = 1.0  (только что получено)

  confidence = 0.887 × 0.873 × 0.9 × 1.0 = 0.697 ≈ 0.70
```

**Уровни уверенности:**
```
confidence > 0.85  → ВЫСОКАЯ    (факт надёжен, можно использовать)
confidence > 0.65  → СРЕДНЯЯ    (факт вероятен, нужна проверка)
confidence > 0.40  → НИЗКАЯ     (факт сомнителен, пометить)
confidence < 0.40  → ОЧЕНЬ НИЗКАЯ (не использовать без верификации)
```

---

### 4. `ContradictionDetector` — детектор противоречий

**Задача:** обнаружить, когда разные источники говорят противоположное.

**Типы противоречий:**

| Тип | Пример | Действие |
|-----|--------|----------|
| **Прямое** | текст: "X=5", другой текст: "X=7" | флаг CONTRADICTION |
| **Модальное** | текст: "кот чёрный", фото: белый кот | флаг MODAL_MISMATCH |
| **Временное** | факт 2020: "X=5", факт 2024: "X=7" | обновить, сохранить историю |
| **Источниковое** | надёжный vs ненадёжный источник | приоритет надёжному |

**Алгоритм обнаружения:**
```
Новый факт F_new о концепте C
    │
    ▼
Найти существующие факты F_old о концепте C в SemanticMemory
    │
    ▼
Для каждой пары (F_new, F_old):
    │
    ├── semantic_sim(F_new, F_old) > 0.8  → СОГЛАСОВАНЫ (подтверждение)
    │   → confidence += 0.05
    │
    ├── semantic_sim(F_new, F_old) < 0.2  → ПРОТИВОРЕЧИЕ
    │   → создать ContradictionRecord
    │   → снизить confidence обоих
    │   → уведомить Cognitive Core
    │
    └── 0.2 ≤ sim ≤ 0.8  → НЕОПРЕДЕЛЁННОСТЬ
        → пометить как "требует уточнения"
```

**Структура `ContradictionRecord`:**
```python
@dataclass
class ContradictionRecord:
    contradiction_id: str
    concept: str                    # "нейрон"
    fact_a: str                     # "нейрон — клетка мозга"
    fact_b: str                     # "нейрон — клетка нервной системы"
    source_a: str                   # "учебник_2020.pdf"
    source_b: str                   # "статья_2024.md"
    similarity: float               # 0.15 (очень разные)
    contradiction_type: str         # "DIRECT" | "MODAL" | "TEMPORAL"
    resolution: str                 # "UNRESOLVED" | "A_WINS" | "B_WINS" | "MERGED"
    detected_at: str                # timestamp
```

---

## Выходной формат: `FusedPercept`

```python
@dataclass
class FusedPercept:
    # Исходные данные
    source_percepts: List[EncodedPercept]  # все входные перцепты

    # Унифицированный вектор
    unified_vector: np.ndarray    # 512d, нормализованный
    vector_dim: int               # 512

    # Связи между модальностями
    entity_clusters: List[EntityCluster]   # найденные кластеры сущностей
    cross_modal_links: List[dict]          # [{source, target, similarity}, ...]

    # Качество и уверенность
    confidence: float             # итоговый confidence 0.0–1.0
    modality_agreement: float     # согласованность модальностей 0.0–1.0

    # Противоречия
    contradictions: List[ContradictionRecord]  # найденные противоречия
    has_contradictions: bool      # быстрая проверка

    # Извлечённые факты
    extracted_facts: List[dict]   # [{concept, description, confidence}, ...]
    keywords: List[str]           # объединённые ключевые слова

    # Метаданные
    fusion_time_ms: float         # время слияния
    modalities_present: Set[str]  # {"text", "image", "audio"}
```

---

## Пример полного цикла Fusion

```
Входные данные:
  1. text:  "Нейрон — основная клетка нервной системы"  (quality=0.92)
  2. image: схема_нейрона.png  (quality=0.85)
  3. audio: "...нейрон передаёт сигналы..."  (quality=0.91)

Шаг 1: SharedSpaceProjector
  text_proj  = W_text @ text_vec   → [0.45, -0.12, 0.78, ...]  (512d)
  image_proj = image_vec           → [0.43, -0.10, 0.81, ...]  (512d)
  audio_proj = W_audio @ audio_vec → [0.44, -0.11, 0.79, ...]  (512d)

Шаг 2: EntityLinker
  sim(text, image) = 0.89 > 0.75  → LINK
  sim(text, audio) = 0.93 > 0.75  → LINK
  sim(image, audio) = 0.87 > 0.75 → LINK
  → EntityCluster("нейрон") = {text, image, audio}
  → centroid = mean([text_proj, image_proj, audio_proj])

Шаг 3: ConfidenceCalibrator
  base_quality      = (0.92 + 0.85 + 0.91) / 3 = 0.893
  modality_agreement = (0.89 + 0.93 + 0.87) / 3 = 0.897
  source_trust      = 0.85  (из SourceMemory)
  recency_factor    = 1.0
  confidence = 0.893 × 0.897 × 0.85 × 1.0 = 0.681

Шаг 4: ContradictionDetector
  Нет существующих фактов о "нейрон" → нет противоречий

Результат: FusedPercept(
  unified_vector = centroid,
  entity_clusters = [EntityCluster("нейрон")],
  confidence = 0.681,
  modality_agreement = 0.897,
  contradictions = [],
  extracted_facts = [
    {"concept": "нейрон", "description": "основная клетка нервной системы", "confidence": 0.681}
  ]
)
```

---

## Обучение проекционных матриц

Матрицы `W_text` и `W_audio` обучаются **онлайн** по мере накопления данных:

```
Обучающий сигнал:
  Пара (текст T, изображение I) о одном понятии
  → хотим: cosine_sim(W_text @ T, I) → 1.0

  Пара (текст T, изображение I) о разных понятиях
  → хотим: cosine_sim(W_text @ T, I) → 0.0

Loss = InfoNCE (contrastive loss):
  L = -log( exp(sim_pos/τ) / Σ exp(sim_neg/τ) )
  где τ = 0.07 (temperature)

Обновление:
  W_text  -= lr × ∂L/∂W_text
  W_audio -= lr × ∂L/∂W_audio
  lr = 0.0001  (медленное обучение, CPU-only)
```

**Начальное состояние:** матрицы инициализируются случайно (Xavier).  
После ~1000 пар текст-изображение качество выравнивания значительно улучшается.

---

## Ресурсный бюджет (CPU-only, 32 GB RAM)

| Компонент | RAM | CPU | Время/запрос |
|-----------|-----|-----|--------------|
| SharedSpaceProjector (W_text, W_audio) | ~8 MB | 1 поток | ~1 мс |
| EntityLinker (поиск по кластерам) | ~50–500 MB | 2 потока | ~5–50 мс |
| ConfidenceCalibrator | ~1 MB | 1 поток | < 1 мс |
| ContradictionDetector | ~10 MB | 1 поток | ~2–10 мс |
| **Итого** | **~60–520 MB** | **2–4 потока** | **~10–60 мс** |

---

## Что Cross-Modal Fusion НЕ делает

| Задача | Кто делает |
|--------|-----------|
| Создание эмбеддингов | Modality Encoders (Слой 2) |
| Сохранение фактов в память | Memory System (Слой 4) |
| Построение цепочек рассуждений | Cognitive Core (Слой 5) |
| Принятие решений | Cognitive Core (Слой 5) |
| Генерация ответов | Output Layer (Слой 7) |

Fusion только **выравнивает, связывает и оценивает** — не рассуждает.

---

## Статус реализации

| Компонент | Статус | Файл |
|-----------|--------|------|
| `FusedPercept` dataclass | ⬜ Фаза 5.0 | `brain/core/events.py` (расширить) |
| `EntityCluster` dataclass | ⬜ Фаза 5.0 | `brain/fusion/entity_cluster.py` |
| `ContradictionRecord` dataclass | ⬜ Фаза 5.0 | `brain/fusion/contradiction.py` |
| `SharedSpaceProjector` | ⬜ Фаза 5.1 | `brain/fusion/shared_space.py` |
| `EntityLinker` | ⬜ Фаза 5.2 | `brain/fusion/entity_linker.py` |
| `ConfidenceCalibrator` | ⬜ Фаза 5.3 | `brain/fusion/confidence_calibrator.py` |
| `ContradictionDetector` | ⬜ Фаза 5.4 | `brain/fusion/contradiction_detector.py` |
| `CrossModalFusion` (оркестратор) | ⬜ Фаза 5.5 | `brain/fusion/fusion_engine.py` |

---

## Зависимости

```
numpy>=1.24.0          — матричные операции, cosine similarity
torch>=2.0.0           — обучение проекционных матриц (CPU)
brain/core/events.py   ✅ (PerceptEvent, EncodedPercept)
brain/memory/          ✅ (SemanticMemory для поиска противоречий)
brain/memory/source_memory.py ✅ (trust scores для ConfidenceCalibrator)
```

---

## Итог: место Ассоциативной коры в системе

```
Сенсорная кора → [АССОЦИАТИВНАЯ КОРА] → Memory → Cognition
                         │
                         ├── SharedSpaceProjector:
                         │   text(768d) + audio(768d) → 512d
                         │   image(512d) → 512d (уже готов)
                         │
                         ├── EntityLinker:
                         │   "нейрон" в тексте = "нейрон" на фото
                         │   cosine_sim > 0.75 → EntityCluster
                         │
                         ├── ConfidenceCalibrator:
                         │   quality × agreement × trust × recency
                         │   → confidence 0.0–1.0
                         │
                         └── ContradictionDetector:
                             два источника говорят разное?
                             → флаг + снизить confidence
                             → уведомить Cognitive Core
```

**Ассоциативная кора — это мост между «видеть/слышать/читать» и «понимать».**  
После неё мозг знает не просто «вот текст» и «вот картинка», а «это одно и то же понятие, и я уверен в нём на 68%».
