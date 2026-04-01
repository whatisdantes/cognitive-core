# 🧠 Слой 10: Safety & Boundaries (Иммунная система мозга)
## Подробное описание архитектуры и работы

> **Статус: ✅ Этап L — реализовано (107 тестов, v0.7.0)**

---

## Что такое безопасность в биологии

В человеческом мозге нет единого «модуля безопасности» — защита встроена повсюду:

| Биологический механизм | Функция | Аналог |
|------------------------|---------|--------|
| **Иммунная система** | Распознавание «своего» и «чужого» | `SourceTrust` — доверие к источникам |
| **Передняя поясная кора** | Детектор конфликтов и ошибок | `ConflictDetector` |
| **Орбитофронтальная кора** | Оценка рисков, торможение импульсов | `BoundaryGuard` |
| **Гиппокамп** | Контекстуальная память о прошлых ошибках | `AuditLogger` |

**Ключевой принцип:** безопасность — это не фильтр на выходе, а **встроенное свойство** каждого слоя.

---

## Роль в искусственном мозге

```
Любой входящий факт / источник / действие
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                  SAFETY & BOUNDARIES                        │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              SourceTrust                             │   │
│  │  оценка надёжности источников                        │   │
│  │  blacklist / whitelist / decay                       │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              ConflictDetector                        │   │
│  │  детектор конфликтов фактов из разных источников     │   │
│  │  → флаг + снижение confidence + уведомление          │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              BoundaryGuard                           │   │
│  │  ограничения на действия и выводы системы            │   │
│  │  redaction приватных данных                          │   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐   │
│  │              AuditLogger                             │   │
│  │  аудит-лог всех решений с высоким риском             │   │
│  │  → safety_audit.jsonl                                │   │
│  └──────────────────────┬───────────────────────────────┘   │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
              Очищенный / проверенный факт/действие
              ИЛИ отклонение с объяснением
```

---

## Компонент 1: `SourceTrust` — Доверие к источникам

**Файл:** `brain/safety/source_trust.py`  
**Аналог:** Иммунная система — распознавание надёжного и ненадёжного

### Базовые уровни доверия

```python
DEFAULT_TRUST_BY_TYPE = {
    "system":       1.00,  # внутренние данные системы
    "user_input":   0.80,  # прямой ввод пользователя
    "verified_doc": 0.90,  # верифицированный документ
    "file":         0.70,  # локальный файл
    "url_trusted":  0.75,  # доверенный URL (whitelist)
    "url_unknown":  0.50,  # неизвестный URL
    "url_untrusted":0.30,  # подозрительный URL
    "generated":    0.60,  # сгенерированный контент
    "unknown":      0.40,  # неизвестный источник
}
```

### Динамическое обновление trust score

```
Факт из источника S подтверждён другим источником:
  S.trust += 0.02 (max 1.0)

Факт из источника S опровергнут:
  S.trust -= 0.05 (min 0.0)

Факт из источника S противоречит 3+ другим фактам:
  S.trust -= 0.15
  → если S.trust < 0.2 → автоматически в blacklist

Источник S в whitelist:
  S.trust = max(S.trust, 0.85)  # минимальный trust для whitelist

Источник S в blacklist:
  S.trust = 0.0
  → все факты из S игнорируются
  → уже сохранённые факты из S: confidence *= 0.1
```

### Decay (затухание доверия)

```
Каждые 7 дней без подтверждений:
  S.trust *= 0.95  (медленное затухание)

Если источник не использовался > 30 дней:
  S.trust *= 0.90  (более быстрое затухание)

Минимальный trust после decay: 0.1 (не обнуляется полностью)
```

### Структура `SourceRecord`

```python
@dataclass
class SourceRecord:
    source_id: str          # "url:https://example.com" | "file:doc.pdf" | "user:sess_01"
    source_type: str        # "url" | "file" | "user_input" | "system" | ...
    trust_score: float      # 0.0–1.0
    
    # История
    confirmations: int      # сколько раз факты подтверждены
    contradictions: int     # сколько раз факты опровергнуты
    total_facts: int        # сколько фактов получено из источника
    
    # Статус
    is_blacklisted: bool    # в чёрном списке
    is_whitelisted: bool    # в белом списке
    blacklist_reason: str   # причина блокировки
    
    # Метаданные
    first_seen: str         # ISO timestamp
    last_seen: str          # ISO timestamp
    last_updated: str       # ISO timestamp
```

### Влияние trust на confidence фактов

```
Новый факт F из источника S:
  F.confidence = base_confidence × S.trust_score

Пример:
  base_confidence = 0.9 (высокое качество извлечения)
  S.trust_score = 0.5 (неизвестный URL)
  F.confidence = 0.9 × 0.5 = 0.45 → LOW_CONFIDENCE
```

---

## Компонент 2: `ConflictDetector` — Детектор конфликтов

**Файл:** `brain/safety/conflict_detector.py`  
**Аналог:** Передняя поясная кора — мониторинг конфликтов

### Типы конфликтов

```python
class ConflictType(Enum):
    DIRECT_CONTRADICTION  = "direct"      # A утверждает X, B утверждает ¬X
    TEMPORAL_CONFLICT     = "temporal"    # старый факт vs новый факт
    SOURCE_CONFLICT       = "source"      # конфликт между источниками
    MODAL_CONFLICT        = "modal"       # текст говорит X, изображение показывает ¬X
    CONFIDENCE_CONFLICT   = "confidence"  # один источник уверен, другой нет
```

### Алгоритм обнаружения

```
Новый факт F_new поступает в SemanticMemory:
    │
    ▼
ConflictDetector.check(F_new, existing_facts)
    │
    ├── Найти все факты о том же концепте
    │
    ├── Для каждой пары (F_new, F_old):
    │   │
    │   ├── semantic_sim > 0.85 → СОГЛАСОВАНЫ
    │   │   → confidence обоих += 0.02
    │   │   → логировать как "facts_confirmed"
    │   │
    │   ├── semantic_sim < 0.20 → ПРЯМОЕ ПРОТИВОРЕЧИЕ
    │   │   → ConflictRecord создан
    │   │   → confidence обоих -= 0.15
    │   │   → logger.warn("contradiction_detected")
    │   │   → уведомить ContradictionDetector (Cognitive Core)
    │   │
    │   └── 0.20 ≤ sim ≤ 0.85 → НЕОПРЕДЕЛЁННОСТЬ
    │       → пометить как "requires_verification"
    │       → confidence -= 0.05
    │
    └── Вернуть ConflictReport
```

### Структура `ConflictRecord`

```python
@dataclass
class ConflictRecord:
    conflict_id: str          # "conflict_a1b2c3"
    conflict_type: ConflictType
    
    # Конфликтующие факты
    fact_a_ref: str           # "semantic:нейрон:source_1"
    fact_b_ref: str           # "semantic:нейрон:source_2"
    fact_a_content: str       # содержание факта A
    fact_b_content: str       # содержание факта B
    
    # Источники
    source_a: str             # источник факта A
    source_b: str             # источник факта B
    source_a_trust: float     # доверие к источнику A
    source_b_trust: float     # доверие к источнику B
    
    # Разрешение
    resolution: str           # "unresolved" | "temporal" | "source_trust" | "modal" | "user"
    winner: str               # какой факт победил
    resolved_at: str          # когда разрешён
    
    # Метаданные
    detected_at: str
    severity: str             # "high" | "medium" | "low"
```

### Стратегии разрешения конфликтов

```
TEMPORAL (временной):
  Факт 2020: "X = 5"  vs  Факт 2024: "X = 7"
  → Победитель: более свежий факт
  → Старый: помечается "outdated", не удаляется

SOURCE_TRUST (по доверию):
  Факт из university.edu (trust=0.95) vs Факт из blog.com (trust=0.4)
  → Победитель: более доверенный источник
  → Слабый источник: trust -= 0.1

MODAL_CONSENSUS (консенсус модальностей):
  Текст: X, Изображение: X, Аудио: ¬X
  → 2 против 1 → победитель: большинство
  → Confidence = weighted_vote(text=0.4, image=0.4, audio=0.2)

USER_OVERRIDE (ручное разрешение):
  Пользователь явно указывает правильный ответ
  → Победитель: ответ пользователя
  → source_trust("user_input") += 0.05
```

---

## Компонент 3: `BoundaryGuard` — Страж границ

**Файл:** `brain/safety/boundary_guard.py`  
**Аналог:** Орбитофронтальная кора — торможение нежелательных действий

### Типы ограничений

```python
class BoundaryType(Enum):
    PRIVACY_REDACTION   = "privacy"    # удаление приватных данных
    ACTION_RESTRICTION  = "action"     # запрет опасных действий
    OUTPUT_FILTER       = "output"     # фильтрация вывода
    CONFIDENCE_GATE     = "confidence" # блокировка при низкой уверенности
    SOURCE_GATE         = "source"     # блокировка ненадёжных источников
```

### Privacy Redaction (удаление приватных данных)

```
Входящий текст или ответ:
    │
    ▼
BoundaryGuard.redact(text)
    │
    ├── Паттерны для redaction:
    │   - email: [a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}
    │   - phone: \+?[0-9]{10,15}
    │   - credit card: [0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{4}[-\s]?[0-9]{4}
    │   - passport: [A-Z]{2}[0-9]{7}
    │   - IP address: \b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b
    │
    ├── Замена: "[REDACTED:email]", "[REDACTED:phone]", ...
    │
    └── Логировать в safety_audit.jsonl:
        {"event": "data_redacted", "type": "email", "count": 2}
```

### Action Restrictions (ограничения действий)

```python
RESTRICTED_ACTIONS = {
    # Файловая система
    "delete_file":      "BLOCKED",   # нельзя удалять файлы
    "overwrite_file":   "WARN",      # предупреждение при перезаписи
    "execute_code":     "BLOCKED",   # нельзя выполнять код
    
    # Сеть
    "send_request":     "WARN",      # предупреждение при HTTP запросах
    "download_file":    "WARN",      # предупреждение при загрузке
    
    # Память
    "clear_all_memory": "BLOCKED",   # нельзя очищать всю память
    "export_memory":    "WARN",      # предупреждение при экспорте
    
    # Пользователь
    "impersonate_user": "BLOCKED",   # нельзя выдавать себя за пользователя
}
```

### Confidence Gate (блокировка при низкой уверенности)

```
Перед отправкой ответа:
    │
    ▼
BoundaryGuard.check_confidence(response, confidence)
    │
    ├── confidence > 0.85 → PASS (без изменений)
    ├── confidence > 0.60 → HEDGE (добавить оговорки)
    ├── confidence > 0.40 → WARN_USER (явно предупредить)
    └── confidence < 0.40 → BLOCK (отказаться отвечать)
        → "У меня недостаточно данных для ответа."
```

---

## Компонент 4: `AuditLogger` — Аудит-логгер

**Файл:** `brain/safety/audit_logger.py`  
**Аналог:** Долгосрочная память об ошибках и нарушениях

### Что логируется в аудит

```python
AUDIT_EVENTS = [
    "source_blacklisted",       # источник добавлен в blacklist
    "source_whitelisted",       # источник добавлен в whitelist
    "data_redacted",            # данные удалены (privacy)
    "conflict_detected",        # обнаружен конфликт фактов
    "conflict_resolved",        # конфликт разрешён
    "action_blocked",           # действие заблокировано
    "action_warned",            # предупреждение о действии
    "confidence_gate_blocked",  # ответ заблокирован (низкая уверенность)
    "boundary_violated",        # нарушение границы
    "trust_score_changed",      # изменение trust score
    "emergency_degradation",    # экстренная деградация системы
]
```

### Формат аудит-записи

```json
{
  "ts": "2026-03-19T12:00:00.123Z",
  "level": "WARN",
  "module": "conflict_detector",
  "event": "conflict_detected",
  "session_id": "sess_01",
  "cycle_id": "cycle_4521",
  "trace_id": "trace_9fa",
  "conflict": {
    "type": "direct_contradiction",
    "fact_a": "нейрон — клетка нервной системы",
    "fact_b": "нейрон — орган",
    "source_a": "university.edu (trust=0.95)",
    "source_b": "blog.com (trust=0.40)",
    "resolution": "source_trust",
    "winner": "fact_a"
  },
  "impact": {
    "confidence_drop": 0.15,
    "source_b_trust_delta": -0.10
  },
  "notes": "Resolved by source trust: university.edu > blog.com"
}
```

---

## Интеграция с другими слоями

```
Safety & Boundaries встроена в каждый слой:

Perception Layer:
  SourceTrust.evaluate(source) → confidence modifier
  BoundaryGuard.redact(content) → privacy protection

Memory System:
  ConflictDetector.check(new_fact) → before store()
  SourceTrust.update(source, confirmed/denied) → after retrieve()

Cognitive Core:
  ContradictionDetector использует ConflictRecord из ConflictDetector
  BoundaryGuard.check_confidence(response) → before ActionSelector

Output Layer:
  BoundaryGuard.redact(response) → before sending to user
  BoundaryGuard.check_action(proposed_action) → before ActionProposer
  AuditLogger.log(high_risk_decision) → for all WARN/BLOCK events

Learning Loop:
  SourceTrust.decay() → периодически
  ConflictDetector.resolve_pending() → при replay
```

---

## Пример полного цикла безопасности

```
Пользователь отправляет документ с URL: "http://suspicious-blog.com/facts.txt"
    │
    ▼
[SourceTrust]
  source_type = "url_unknown"
  initial_trust = 0.50
  → confidence modifier = 0.50
    │
    ▼
[TextIngestor] извлекает факт: "нейрон — это орган"
  base_confidence = 0.85
  adjusted_confidence = 0.85 × 0.50 = 0.425 → LOW_CONFIDENCE
    │
    ▼
[ConflictDetector]
  Существующий факт: "нейрон — клетка нервной системы" (conf=0.87, source=university.edu)
  Новый факт: "нейрон — орган" (conf=0.425, source=suspicious-blog.com)
  semantic_sim = 0.15 → ПРЯМОЕ ПРОТИВОРЕЧИЕ
  → ConflictRecord создан (severity="high")
  → confidence обоих -= 0.15
  → logger.warn("contradiction_detected")
    │
    ▼
[ConflictDetector.resolve]
  Стратегия: SOURCE_TRUST
  university.edu (trust=0.95) > suspicious-blog.com (trust=0.50)
  → Победитель: "нейрон — клетка нервной системы"
  → suspicious-blog.com: trust -= 0.10 → 0.40
    │
    ▼
[AuditLogger]
  Записать в safety_audit.jsonl:
  {"event": "conflict_resolved", "winner": "university.edu", ...}
    │
    ▼
[BoundaryGuard]
  Ответ пользователю: confidence=0.87 → PASS (без изменений)
  "Нейрон — это клетка нервной системы."
  + примечание: "Обнаружено противоречие в источнике suspicious-blog.com"
```

---

## Ресурсный бюджет (CPU-only, 32 GB RAM)

| Компонент | RAM | CPU | Время/операция |
|-----------|-----|-----|----------------|
| SourceTrust | ~5 MB | < 1% | ~1 мс |
| ConflictDetector | ~5 MB | < 1% | ~5–20 мс |
| BoundaryGuard | ~2 MB | < 1% | ~1–5 мс |
| AuditLogger | ~3 MB | < 1% | ~1 мс |
| **Итого** | **~15 MB** | **< 2%** | **~8–27 мс** |

---

## Статус реализации

| Компонент | Статус | Файл | Тесты |
|-----------|--------|------|-------|
| `SourceTrustManager` | ✅ Этап L.1 | `brain/safety/source_trust.py` | 16/16 |
| `ConflictDetector` | ✅ Этап L.2 | `brain/safety/conflict_detector.py` | 19/19 |
| `BoundaryGuard` | ✅ Этап L.3 | `brain/safety/boundary_guard.py` | 26/26 |
| `AuditLogger` | ✅ Этап L.4 | `brain/safety/audit_logger.py` | 13/13 |
| `SafetyPolicyLayer` | ✅ Этап L.5 | `brain/safety/policy_layer.py` | 16/16 |
| Pipeline integration | ✅ Этап L.6 | `brain/cognition/pipeline.py` | 17/17 |

> **Примечание:** `SourceMemory` (из Фазы 6 ✅) уже реализует базовый trust score для источников. `SourceTrustManager` в Safety layer — это более высокоуровневая политика поверх `SourceMemory`. Pipeline интегрирует 3 новых шага: `step_safety_input_check`, `step_safety_policy_check`, `step_safety_audit_log`.
