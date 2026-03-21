# 🧠 Слой 1: Perception Layer (Таламус)
## Подробное описание архитектуры и работы

> **Статус: ✅ Этап D завершён (Text-Only Perception реализован)** · 79/79 тестов  
> ✅ `metadata_extractor.py` — MetadataExtractor (quality scoring, language detection)  
> ✅ `text_ingestor.py` — TextIngestor (.txt/.md/.pdf/.docx/.json/.csv, paragraph-aware chunking)  
> ✅ `input_router.py` — InputRouter (text-only MVP, SHA256 dedup, quality policy)  
> ⬜ `vision_ingestor.py` — Этап J (мультимодальное расширение)  
> ⬜ `audio_ingestor.py` — Этап J (мультимодальное расширение)

---

## Что такое Таламус в биологии

В человеческом мозге **Таламус** — это «центральная телефонная станция»:
- принимает **все** сенсорные сигналы (зрение, слух, осязание, вкус, обоняние),
- **фильтрует** шум и нерелевантные сигналы,
- **маршрутизирует** каждый сигнал в нужную зону коры,
- **не обрабатывает смысл** — только доставляет и приоритизирует.

Аналогично работает наш Perception Layer.

---

## Роль в искусственном мозге

```
Внешний мир
(файлы, пользователь, сенсоры)
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                  PERCEPTION LAYER                       │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ TextIngestor │  │VisionIngestor│  │AudioIngestor │  │
│  │  .txt .md    │  │  .jpg .png   │  │  .wav .mp3   │  │
│  │  .pdf .docx  │  │  .webp .gif  │  │  .ogg .flac  │  │
│  │  .json .csv  │  │  .mp4 (кадры)│  │  .mp4 (звук) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │           │
│         └─────────────────┼─────────────────┘           │
│                           │                             │
│                  ┌────────▼────────┐                    │
│                  │MetadataExtractor│                    │
│                  │ source, ts,     │                    │
│                  │ quality, lang   │                    │
│                  └────────┬────────┘                    │
│                           │                             │
│                  ┌────────▼────────┐                    │
│                  │  InputRouter    │                    │
│                  │ (маршрутизатор) │                    │
│                  │ дедупликация    │                    │
│                  │ фильтрация шума │                    │
│                  └────────┬────────┘                    │
└───────────────────────────┼─────────────────────────────┘
                            │
                            ▼
                    PerceptEvent(s)
              (унифицированный формат)
                            │
                            ▼
                   Modality Encoders
                      (Слой 2)
```

---

## Компоненты Perception Layer

### 1. `TextIngestor` — обработка текстовых данных

**Поддерживаемые форматы:**

| Формат | Библиотека | Что извлекается |
|--------|-----------|-----------------|
| `.txt`, `.md` | встроенный Python | сырой текст, заголовки |
| `.pdf` | `pymupdf` (fitz) | текст, таблицы, метаданные, номера страниц |
| `.docx` | `python-docx` | параграфы, таблицы, стили |
| `.json` | `json` | структурированные данные |
| `.csv` | `csv` / `pandas` | табличные данные |

**Что делает:**
1. Читает файл в сыром виде
2. Извлекает структуру (заголовки → разделы → параграфы)
3. Разбивает на **чанки** (фрагменты ~512 токенов) с перекрытием
4. Извлекает факты/тезисы (паттерны "X это Y", "X — Y")
5. Добавляет **provenance** (откуда пришёл фрагмент: файл, страница, параграф)
6. Создаёт `PerceptEvent` для каждого чанка

**Пример чанкинга:**
```
Документ: "нейрон.pdf" (50 страниц)
    │
    ▼
Страница 1: "Нейрон — это основная клетка нервной системы..."
    │
    ▼
Чанк 1: {text: "Нейрон — это основная клетка...", page: 1, para: 0}
Чанк 2: {text: "...нервной системы. Нейроны передают...", page: 1, para: 1}
    │
    ▼
PerceptEvent(modality="text", source="нейрон.pdf#p1", content=чанк)
```

---

### 2. `VisionIngestor` — обработка изображений и видео

**Поддерживаемые форматы:**

| Формат | Библиотека | Что извлекается |
|--------|-----------|-----------------|
| `.jpg`, `.png`, `.webp` | `Pillow` | изображение → PIL.Image |
| `.gif` | `Pillow` | кадры анимации |
| `.mp4`, `.avi` | `cv2` (OpenCV) | кадры с временными метками |

**Что делает:**
1. Загружает изображение/видео
2. **OCR** — извлекает текст с изображения (если есть)
3. **Image Understanding** — описание объектов и сцены (через CLIP или caption модель)
4. Для видео — семплирует ключевые кадры (каждые N секунд)
5. Создаёт `PerceptEvent` с изображением + описанием + OCR-текстом

**Пример:**
```
Файл: "схема_мозга.png"
    │
    ▼
OCR: "Нейрон, Синапс, Аксон, Дендрит"
Image desc: "Схематическое изображение нейрона с подписями"
    │
    ▼
PerceptEvent(
    modality="image",
    source="схема_мозга.png",
    content={
        "image": PIL.Image,
        "ocr_text": "Нейрон, Синапс...",
        "description": "Схематическое изображение...",
        "objects": ["нейрон", "синапс", "аксон"]
    }
)
```

---

### 3. `AudioIngestor` — обработка аудио

**Поддерживаемые форматы:**

| Формат | Библиотека | Что извлекается |
|--------|-----------|-----------------|
| `.wav`, `.mp3`, `.ogg`, `.flac` | `openai-whisper` | транскрипт + временные метки |
| `.mp4` (аудиодорожка) | `ffmpeg` + `whisper` | транскрипт |

**Что делает:**
1. Загружает аудиофайл
2. **ASR** (Automatic Speech Recognition) через Whisper medium
3. Разбивает транскрипт на сегменты с временными метками
4. Определяет язык (RU/EN/mixed)
5. Опционально: детекция спикеров, эмоциональный тон
6. Создаёт `PerceptEvent` для каждого сегмента

**Пример:**
```
Файл: "лекция_нейробиология.mp3" (60 мин)
    │
    ▼
Whisper medium → транскрипт с метками времени:
  [00:00–00:15] "Сегодня мы поговорим о нейронах..."
  [00:15–00:32] "Нейрон состоит из тела клетки..."
    │
    ▼
PerceptEvent(
    modality="audio",
    source="лекция.mp3",
    content={
        "transcript": "Сегодня мы поговорим о нейронах...",
        "time_start": 0.0,
        "time_end": 15.3,
        "language": "ru",
        "confidence": 0.94
    }
)
```

---

### 4. `MetadataExtractor` — извлечение метаданных

Работает **поверх всех ingestor'ов** и добавляет к каждому событию:

| Поле | Описание | Пример |
|------|----------|--------|
| `source` | путь к файлу или URL | `"docs/нейрон.pdf#p3"` |
| `ts` | время обработки (ISO 8601) | `"2026-03-19T12:00:00Z"` |
| `quality` | оценка качества 0.0–1.0 | `0.87` |
| `language` | язык контента | `"ru"`, `"en"`, `"mixed"` |
| `modality` | тип данных | `"text"`, `"image"`, `"audio"` |
| `file_size_kb` | размер файла | `1024` |
| `encoding` | кодировка (для текста) | `"utf-8"` |
| `page` | номер страницы (для PDF) | `3` |
| `time_range` | временной диапазон (для аудио/видео) | `[12.2, 14.7]` |

**Оценка качества (quality score):**
```
Текст:  длина > 50 символов → +0.3
        нет битых символов  → +0.3
        язык определён      → +0.2
        структура есть      → +0.2

Изображение: разрешение > 256px → +0.4
             не размытое        → +0.3
             OCR успешен        → +0.3

Аудио:  SNR > 20dB             → +0.4
        Whisper confidence > 0.8 → +0.4
        длина > 3 секунды       → +0.2
```

---

### 5. `InputRouter` — маршрутизатор и фильтр

**Главный компонент Таламуса.** Принимает все входящие данные и:

#### Определение модальности:
```python
def detect_modality(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext in {'.txt', '.md', '.pdf', '.docx', '.json', '.csv'}:
        return 'text'
    elif ext in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}:
        return 'image'
    elif ext in {'.wav', '.mp3', '.ogg', '.flac', '.aac'}:
        return 'audio'
    elif ext in {'.mp4', '.avi', '.mov', '.mkv'}:
        return 'video'  # → VisionIngestor + AudioIngestor
    else:
        return 'unknown'
```

#### Дедупликация:
```
Новый файл → SHA256 хэш → проверка в SourceMemory
    │
    ├── Хэш уже есть → SKIP (дубликат)
    └── Хэш новый   → PROCESS → добавить в SourceMemory
```

#### Фильтрация низкокачественных входов:
```
quality < 0.2  → REJECT (слишком плохое качество)
quality < 0.5  → WARN + PROCESS (обработать с пометкой)
quality >= 0.5 → PROCESS (нормальная обработка)
```

#### Приоритизация (при нехватке CPU):
```
Приоритет 1 (высший): user_input (прямой ввод пользователя)
Приоритет 2:          text файлы (наименее затратные)
Приоритет 3:          image файлы
Приоритет 4 (низший): audio/video (наиболее затратные)

При CPU > 70%: приостановить audio/video обработку
При CPU > 85%: обрабатывать только user_input + text
```

---

## Унифицированный формат: `PerceptEvent`

Все ingestor'ы производят **один и тот же формат** — `PerceptEvent`:

```python
@dataclass
class PerceptEvent(BaseEvent):
    event_type: str = "percept"
    source: str = ""          # путь к файлу, URL, "user_input"
    modality: str = "text"    # 'text' | 'image' | 'audio' | 'video' | 'mixed'
    content: Any = None       # содержимое (текст, PIL.Image, dict)
    quality: float = 1.0      # 0.0 — 1.0
    language: str = "unknown" # 'ru' | 'en' | 'mixed' | 'unknown'
    metadata: Dict = {}       # page, time_range, file_size, encoding, ...
```

**Примеры PerceptEvent для разных модальностей:**

```json
// Текст
{
  "event_type": "percept",
  "modality": "text",
  "source": "docs/нейрон.pdf#p1",
  "content": "Нейрон — это основная клетка нервной системы...",
  "quality": 0.92,
  "language": "ru",
  "metadata": {"page": 1, "para": 0, "chunk_id": 0}
}

// Изображение
{
  "event_type": "percept",
  "modality": "image",
  "source": "images/схема_мозга.png",
  "content": {"ocr_text": "Нейрон, Синапс", "description": "Схема нейрона"},
  "quality": 0.85,
  "language": "ru",
  "metadata": {"width": 1024, "height": 768, "has_text": true}
}

// Аудио
{
  "event_type": "percept",
  "modality": "audio",
  "source": "audio/лекция.mp3",
  "content": {"transcript": "Нейрон состоит из...", "time_start": 15.3, "time_end": 32.1},
  "quality": 0.91,
  "language": "ru",
  "metadata": {"duration_sec": 3600, "whisper_model": "medium"}
}
```

---

## Параллельная обработка (CPU-aware)

На 8-ядерном Ryzen 7 5700X обработка разных модальностей идёт **параллельно**:

```
Входящие файлы:
  doc_A.pdf  ──► TextIngestor    (поток 1)
  img_B.png  ──► VisionIngestor  (поток 2)
  audio_C.mp3 ─► AudioIngestor   (поток 3)
                                  │
                                  ▼
                         InputRouter (поток 0)
                         собирает PerceptEvent'ы
                         и отправляет в EventBus
```

**Ограничения:**
- Whisper (аудио) — самый тяжёлый: ~1.5 GB RAM, ~2-4 ядра
- CLIP (изображения) — средний: ~0.6 GB RAM, ~1-2 ядра
- Текст — лёгкий: ~100 MB RAM, ~1 ядро

При нехватке ресурсов — очередь с приоритетами.

---

## Провенанс (Provenance) — откуда пришёл факт

Каждый `PerceptEvent` несёт **полную цепочку происхождения**:

```
Факт: "нейрон — клетка нервной системы"
    │
    ├── source:    "docs/нейробиология.pdf"
    ├── page:      12
    ├── paragraph: 3
    ├── chunk_id:  47
    ├── quality:   0.89
    ├── language:  "ru"
    └── ts:        "2026-03-19T12:00:00Z"
```

Это позволяет:
- **проверить** факт (вернуться к источнику),
- **оценить доверие** (качество источника),
- **построить trace** (объяснить откуда знание),
- **обнаружить противоречия** (два источника говорят разное).

---

## Что Perception Layer НЕ делает

| Задача | Кто делает |
|--------|-----------|
| Понимание смысла текста | Modality Encoders (Слой 2) |
| Создание эмбеддингов | Modality Encoders (Слой 2) |
| Связывание понятий | Cross-Modal Fusion (Слой 3) |
| Сохранение в память | Memory System (Слой 4) |
| Рассуждение | Cognitive Core (Слой 5) |

Perception Layer только **принимает, очищает, форматирует и маршрутизирует**.

---

## Статус реализации

| Компонент | Статус | Файл |
|-----------|--------|------|
| `PerceptEvent` dataclass | ✅ Готово | `brain/core/events.py` |
| `MetadataExtractor` | ✅ Готово (Этап D) | `brain/perception/metadata_extractor.py` |
| `TextIngestor` | ✅ Готово (Этап D) | `brain/perception/text_ingestor.py` |
| `InputRouter` | ✅ Готово (Этап D) | `brain/perception/input_router.py` |
| `VisionIngestor` | ⬜ Этап J | `brain/perception/vision_ingestor.py` |
| `AudioIngestor` | ⬜ Этап J | `brain/perception/audio_ingestor.py` |

**Тесты Этапа D: 79/79 ✅** (`test_perception.py`)

---

## Зависимости

```
brain/core/events.py     ✅ (PerceptEvent определён)
brain/core/event_bus.py  ✅ (EventBus реализован)
brain/logging/           ✅ (BrainLogger реализован)

Python пакеты (уже в requirements.txt):
  pymupdf (fitz)     — PDF парсинг (опционально, graceful fallback)
  python-docx        — DOCX парсинг (опционально, graceful fallback)
  pillow             — изображения (Этап J)
  openai-whisper     — ASR (Этап J)
  numpy              — обработка данных
```

---

## Итог: место Таламуса в системе

```
Внешний мир → [ТАЛАМУС] → PerceptEvent → Encoders → Fusion → Memory → Cognition
                  │
                  ├── Принимает ВСЁ
                  ├── Фильтрует шум
                  ├── Унифицирует формат
                  ├── Добавляет провенанс
                  ├── Приоритизирует по CPU
                  └── Маршрутизирует дальше
```

**Таламус — это граница между хаосом внешнего мира и порядком внутреннего состояния мозга.**
