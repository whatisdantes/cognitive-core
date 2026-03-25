# 🧠 cognitive-core — Revised MVP Roadmap

> **Дата:** 2026-03-25  
> **Основа:** объединение результатов аудита, merged-аудита и исходного MVP roadmap  
> **Подход:** сначала **стабилизировать и замкнуть** уже реализованный text-only контур, а не расширять архитектуру ради новых фич

---

## 1. Что считается MVP

### MVP-цель
**Запускаемая, стабильная text-only система** с полным контуром:

`input → encode → memory → reason → output`

### Что обязательно входит в MVP
- один официальный entrypoint / CLI;
- рабочий путь для текстового ввода и текстовых файлов;
- автоматическое кодирование текста;
- сохранение и извлечение памяти;
- reasoning + output + confidence + trace;
- реальные данные о ресурсах доходят до cognition;
- CI проходит с настоящим mypy;
- README и запуск соответствуют реальному состоянию проекта.

### Что сознательно НЕ входит в MVP
- persisted vector pipeline как обязательный путь;
- полноценный ANN / FAISS / hnswlib retrieval;
- multimodal vision/audio/video;
- Ring 2 / deep reasoning;
- Attention Controller;
- reward / motivation;
- большой DRY-рефакторинг всей кодовой базы;
- lock-файл и reproducible builds как релизный блокер.

> **Причина:** это всё полезно, но раздувает scope MVP. MVP должен быть **стабильным text-only релизом**, а не мини-переписыванием архитектуры.

---

## 2. Ключевая стратегия

Проект уже имеет сильную архитектурную базу, но текущая проблема не в недостатке модулей, а в **незамкнутых стыках** между ними.

### Главный принцип
Не добавлять крупные новые возможности до тех пор, пока не закрыты:
1. **runtime-стыки**;
2. **запуск и онбординг**;
3. **честный CI**;
4. **минимальный hardening input-пути**.

---

## 3. Roadmap по фазам

# Фаза A — Foundation
**Срок:** 1–2 дня  
**Цель:** убрать всё, что мешает проекту запускаться и быть воспроизводимым.

## A.1 Официальный entrypoint / CLI
### Проблема
Сейчас запуск проекта противоречив:
- README, bat-скрипт и структура репозитория расходятся;
- `main.py` в корне не является надёжной точкой истины;
- нет одной официальной команды запуска.

### Решение
Сделать один официальный способ запуска:
- `brain/cli.py` или `brain/demo.py`;
- добавить `[project.scripts]` в `pyproject.toml`;
- команда вида:
  ```bash
  cognitive-core "Что такое нейропластичность?"
  ```

### Задачи
- создать CLI entrypoint;
- собрать в нём минимальный полный пайплайн:
  `MemoryManager -> CognitiveCore -> OutputPipeline`;
- добавить `examples/demo.py`;
- унифицировать `.venv` / `venv`;
- синхронизировать Python minimum version везде.

### Definition of Done
Пользователь может:
```bash
git clone ...
pip install -e .
cognitive-core "Что такое нейропластичность?"
```
и получить осмысленный ответ.

---

## A.2 Починить контракт `ResourceMonitor ↔ CognitiveCore`
### Проблема
Resource-aware cognition сейчас не до конца замкнут: контракты и реальные классы расходятся.

### Решение
Выбрать **один официальный публичный API** для передачи ресурсо-снимка:
- либо `snapshot()`,
- либо `check()` с единым return type.

### Задачи
- синхронизировать `ResourceMonitor`, `ResourceMonitorProtocol`, `CognitiveCore`;
- добавить unit-тест на protocol conformance;
- добавить integration-тест с реальным `ResourceMonitor`.

### Definition of Done
`CognitiveCore` получает реальные данные о ресурсах, а не пустой fallback.

---

## A.3 Сделать mypy настоящим барьером качества
### Проблема
Typecheck в CI сейчас частично декоративный, если ошибки не валят пайплайн.

### Решение
Убрать `|| true` из mypy job хотя бы для критических пакетов:
- `brain/core`
- `brain/cognition`
- `brain/memory`

### Задачи
- убрать `|| true`;
- локально собрать список ошибок;
- исправить критические type errors;
- при необходимости временно оставить точечные `# type: ignore` с понятными TODO.

### Definition of Done
CI проходит с реальным mypy без искусственного пропуска ошибок.

---

# Фаза B — Close the Loop
**Срок:** 2–3 дня  
**Цель:** реально замкнуть text-only MVP-пайплайн.

## B.1 Auto-encode в `CognitiveCore`
### Проблема
Если `encoded_percept` не передан извне, encoder фактически не участвует автоматически.

### Решение
Если:
- `encoded_percept is None`,
- и encoder доступен,

то `CognitiveCore.run()` должен сам кодировать query.

### Задачи
- встроить auto-encode в `CognitiveCore.run()`;
- передавать результат в retrieval / reasoning;
- обновить e2e тесты.

### Definition of Done
`CognitiveCore.run("запрос")` без ручного `encoded_percept` использует encoder автоматически.

---

## B.2 Минимальный hardening perception
### Проблема
Входной путь для файлов слишком доверчивый:
- нет явной нормализации пути;
- нет предела размера файла;
- при больших / странных входах поведение недостаточно жёстко определено.

### Решение
Добавить:
- `validate_file_path(...)`;
- `check_file_size(...)`;
- конфиг `MAX_FILE_SIZE_MB`.

### Задачи
- создать security/helper-модуль;
- интегрировать проверки в `TextIngestor` и `InputRouter`;
- покрыть тестами path traversal / oversized file.

### Definition of Done
Система предсказуемо отвергает опасные пути и слишком большие файлы.

---

## B.3 Зафиксировать retrieval scope для MVP
### Проблема
В проекте уже есть vector / hybrid retrieval hooks, но их фактическая зрелость пока ниже, чем звучит из описания.

### Решение
Для MVP официально зафиксировать:
- retrieval = keyword-first;
- BM25 / текущий reranking остаётся основным путём;
- vector retrieval не позиционируется как fully persisted MVP-capability.

### Почему это важно
Это сознательный **scope cut**:
мы не тянем persisted vector pipeline в MVP, чтобы не открывать новую большую ветку:
- schema changes,
- embedding storage,
- hybrid retrieval semantics,
- новая серия регрессий.

### Definition of Done
README и CLI честно описывают retrieval как текущий text-first путь, без переобещания.

---

## B.4 README привести к реальности
### Задачи
- обновить Quick Start под реальный entrypoint;
- честно описать статус retrieval;
- явно пометить MVP как text-only;
- обновить разделы “Что сделано / Что дальше”.

### Definition of Done
README можно читать как единственный правдивый источник запуска и статуса MVP.

---

# Фаза C — MVP Cleanup
**Срок:** 1–2 дня  
**Цель:** убрать самые вредные дубли и сцепки, не уходя в большой рефакторинг.

## C.1 Канонический `detect_language()`
### Проблема
Похожие эвристики определения языка размазаны по нескольким модулям.

### Решение
Вынести один канонический helper:
```python
brain/core/utils.py -> detect_language(text)
```

### Definition of Done
Основные runtime-пути используют одну реализацию.

---

## C.2 Канонический `extract_fact()`
### Проблема
Логика “извлечения факта” размазана между разными слоями:
- command parsing;
- pattern-based fact extraction.

### Решение
Выделить один общий utility / service API для fact extraction.

### Важно
Не обязательно делать “идеальный универсальный extractor”.
Нужно только убрать размазанную ответственность и прямые приватные вызовы.

### Definition of Done
Факт-экстракция идёт через явный публичный путь, а не через приватные внутренности других модулей.

---

## C.3 Убрать прямой вызов `consolidation._extract_fact()`
### Проблема
`MemoryManager` не должен зависеть от приватной внутренности `ConsolidationEngine`.

### Решение
Либо:
- публичный `extract_fact(...)`,
либо:
- общий utility helper.

### Definition of Done
Приватный `_extract_fact()` не вызывается извне.

---

## C.4 Optional: вынести `_sha256()`
### Статус
Это не блокер MVP, но если уже создаётся `utils.py`, можно заодно вынести hash helpers.

---

## 4. Что переносится в post-MVP

Следующие пункты **не входят в MVP-релиз**, но идут сразу после него.

### D. Retrieval Upgrade
**Срок:** 2–4 дня
- persisted embeddings;
- schema changes;
- cosine search;
- hybrid retrieval как официальный путь.

### E. Clean Code / DRY Sweep
**Срок:** 2–3 дня
- общий JSON serialization helper;
- более широкий cleanup utilities;
- частичный разбор дублирующихся функций.

### F. Hardening & DX
**Срок:** 2–3 дня
- lazy loading encoder;
- graceful shutdown через `Event.wait()` там, где это оправдано;
- concurrency stress tests;
- lock-файл / reproducible builds.

---

## 5. Сводная таблица

| Фаза | Название | Срок | Входит в MVP | Основной результат |
|---|---|---:|:---:|---|
| A | Foundation | 1–2 дня | ✅ | проект запускается и проходит честный CI |
| B | Close the Loop | 2–3 дня | ✅ | text-only пайплайн реально замкнут |
| C | MVP Cleanup | 1–2 дня | ✅ | убраны самые вредные дубли и сцепки |
| D | Retrieval Upgrade | 2–4 дня | ❌ | persisted vector / hybrid retrieval |
| E | DRY Sweep | 2–3 дня | ❌ | более чистая кодовая база |
| F | Hardening & DX | 2–3 дня | ❌ | contributor-ready и reproducible setup |

---

## 6. Зависимости между фазами

```text
Фаза A — обязательный фундамент
├── A.1 Entrypoint / CLI
├── A.2 ResourceMonitor ↔ CognitiveCore
└── A.3 Real mypy

Фаза B — замыкает MVP
├── B.1 Auto-encode
├── B.2 Perception hardening
├── B.3 Retrieval scope freeze
└── B.4 README reality sync

Фаза C — минимальный cleanup
├── C.1 detect_language
├── C.2 extract_fact
├── C.3 убрать приватный _extract_fact()
└── C.4 optional _sha256()

Post-MVP
├── D. Retrieval Upgrade
├── E. DRY Sweep
└── F. Hardening & DX
```

---

## 7. Критерии готовности MVP

MVP считается готовым, если выполняется всё ниже:

- [ ] `pip install -e . && cognitive-core "вопрос"` работает из коробки
- [ ] text-only пайплайн реально замкнут: `input -> encode -> memory -> reason -> output`
- [ ] `CognitiveCore` использует encoder автоматически
- [ ] `ResourceMonitor` передаёт реальные данные в cognition
- [ ] CI зелёный с реальным mypy
- [ ] Perception отвергает опасные пути и слишком большие файлы
- [ ] README соответствует фактическому поведению проекта
- [ ] есть `examples/demo.py` или аналогичный рабочий demo-entrypoint

---

## 8. Короткий вывод

### Этот roadmap делает две вещи
1. **не раздувает MVP**;
2. **доводит уже реализованный text-only контур до честного релизного состояния**.

### Одной строкой
> **MVP cognitive-core = стабильный text-only релиз с честным запуском, замкнутым пайплайном и минимально вычищенными стыками.**
