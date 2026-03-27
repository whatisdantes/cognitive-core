# 🎯 Merged Action Plan: cognitive-core

> **Источники:** Tasklet audit (инженерный) + ChatGPT audit (продуктовый)  
> **Проект:** [whatisdantes/cognitive-core](https://github.com/whatisdantes/cognitive-core) v0.7.0  
> **Дата:** 27 марта 2026 (обновлено: июнь 2026)  
> **Принцип:** Engineering hardening (Tasklet) → Product value path (ChatGPT) → Scale  
> **Ревизия:** v3 — P0 (7/7 ✅) и P1 (14/14 ✅) завершены. Актуальный roadmap: [`TODO.md`](../TODO.md)

---

## Как читать этот план

| Приоритет | Значение | Когда | Источник |
|-----------|----------|-------|----------|
| 🔴 **P0** | Crash, data loss, нерабочий value path | Неделя 1–2 | Оба аудита |
| 🟠 **P1** | Качество, масштаб, честность позиционирования | Неделя 2–3 | Оба аудита |
| 🟡 **P2** | Техдолг, DX, minor bugs | Неделя 3–4 | Оба аудита |
| 🔵 **P3** | Nice-to-have, стратегия | Месяц 2+ | Оба аудита |

Каждая задача маркирована: **[T]** = Tasklet, **[C]** = ChatGPT, **[T+C]** = оба сходятся.

---

## 🔴 P0 — Критические (Неделя 1–2) — ✅ ЗАВЕРШЕНО 7/7

### P0-E: Инженерные (Tasklet)

#### P0-E1. ✅ Потокобезопасность — 6 модулей  
**Риск:** `RuntimeError`, потеря данных, crash при ConsolidationEngine daemon thread  
**Модули:** WorkingMemory, SemanticMemory, EpisodicMemory, SourceMemory, ProceduralMemory, EventBus  
**Fix:**  
```python
# Добавить threading.RLock в каждый memory store
import threading

class WorkingMemory:
    def __init__(self):
        self._lock = threading.RLock()
    
    def add(self, item):
        with self._lock:
            ...
    
    def get_all(self):
        with self._lock:
            return list(self._items)  # return copy
```
**Тест:** Concurrent stress test — 10 потоков × 1000 операций, assert no exceptions  
**Effort:** 1–2 дня  
**[T]**

---

#### P0-E2. ✅ Race condition в ResourceMonitor._apply_state()
**Риск:** `old_policy` читается вне lock → два потока получают некорректные значения  
**Fix:** Расширить scope `with self._lock:` на чтение `old_policy`  
**Effort:** 30 минут  
**[T]**

---

#### P0-E3. ✅ Утечка памяти в BrainLogger
**Риск:** `_trace_index`, `_session_index` растут бесконечно → OOM при long-running  
**Fix:** Добавить TTL или max-size LRU для индексных словарей  
```python
from collections import OrderedDict

class BoundedIndex(OrderedDict):
    def __init__(self, max_size=10_000):
        super().__init__()
        self._max = max_size
    
    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if len(self) > self._max:
            self.popitem(last=False)
```
**Effort:** 1–2 часа  
**[T]**

---

#### P0-E4. ✅ 100 МБ RAM spike при ротации логов
**Риск:** `f_in.read()` загружает весь файл в память одним куском  
**Fix:**  
```python
# Было:
data = f_in.read()
f_out.write(data)

# Стало:
import shutil
shutil.copyfileobj(f_in, f_out, length=64*1024)
```
**Effort:** 15 минут  
**[T]**

---

#### P0-E5. ✅ importance ≠ confidence — семантическое несоответствие
**Риск:** `min_importance` передаётся как `min_confidence` → неожиданные результаты retrieval  
**Fix:** Разделить параметры, или переименовать для ясности  
**Effort:** 30 минут  
**[T]**

---

### P0-P: Продуктовые (ChatGPT)

#### P0-P1. ✅ Vector/hybrid retrieval — «декоративный» → ИСПРАВЛЕНО
**Центральная проблема проекта — РЕШЕНА.**  
`_build_vector_index()` теперь вызывается при `__init__` CognitiveCore и строит индекс из всего персистентного корпуса (SemanticMemory + EpisodicMemory). Инкрементальная индексация при LEARN. `remove_from_vector_index()` при deny/delete. Embedding persistence в `to_dict()/from_dict()`.

**Тесты:** 60/60 в `test_vector_retrieval.py` ✅  
**[C]**

---

#### P0-P2. ✅ ResponseValidator — логическая противоречивость
**Исправлено.** После автокоррекции severity снижается, `is_valid=True`.  
**[C]**

---

## 🟠 P1 — Высокий приоритет (Неделя 2–3) — ✅ ЗАВЕРШЕНО 14/14

### P1-E: Инженерные

#### P1-E1. ✅ ContractMixin.from_dict() не восстанавливает вложенные dataclass/Enum
**Исправлено.** Рекурсивный `from_dict()` с type introspection.  
**Fix:** Рекурсивный `from_dict()` с type introspection через `typing.get_type_hints()`  
**Effort:** 2–4 часа (+ тесты)  
**[T] ↓ понижено из P0 по итогам перекрёстной рецензии**

---

#### P1-E2. ✅ GoalManager._remove_from_queue() — no-op (pass)
**Исправлено.** Lazy-delete pattern реализован.  
**Fix:** Реализовать удаление из priority queue (heapq mark-lazy-delete pattern)  
```python
def _remove_from_queue(self, goal_id: str):
    self._removed_ids.add(goal_id)

def peek(self):
    while self._queue and self._queue[0].id in self._removed_ids:
        heapq.heappop(self._queue)
        self._removed_ids.discard(...)
    return self._queue[0] if self._queue else None
```
**Effort:** 1 час  
**[T] ↓ понижено из P0 по итогам перекрёстной рецензии**

---

#### P1-E3. ✅ EventBusProtocol.publish() — несовпадение сигнатур
**Исправлено.** Protocol сигнатура синхронизирована с реальным EventBus.  
**Fix:**  
```python
class EventBusProtocol(Protocol):
    def publish(self, event_type: str, payload: Any = None, trace_id: str = "") -> int: ...
```
**Effort:** 15 минут  
**[T+C] ↓ понижено из P0 по итогам перекрёстной рецензии**

---

#### P1-E4. ✅ Расширить mypy до всех модулей [T+C]
**Исправлено.** `packages = ["brain"]`, `check_untyped_defs = true`, mypy 0 errors.

---

#### P1-E5. ✅ Заменить `Any` на Protocol-типы [T]
**Исправлено.** `MemoryManagerProtocol` и другие Protocol-типы внедрены.

---

#### P1-E6. ✅ Coverage gate в CI [T]
**Исправлено.** `--cov-fail-under=70`, текущее покрытие 84.44%.

---

#### P1-E7. ✅ Lock-файл для reproducible builds [T]
**Исправлено.** `requirements.lock` генерируется через pip-tools.

---

#### P1-E8. ✅ Расширить Ruff rules [T+C]
**Исправлено.** B/SIM/C4/RET/PIE добавлены, ruff 0 errors.

---

#### P1-E9. ✅ copy.deepcopy → dataclasses.replace [T]
**Исправлено.**

---

#### P1-E10. ✅ DialogueResponder: переиспользовать OutputTraceBuilder [T]
**Исправлено.**

---

#### P1-E11. ✅ Docker — multi-stage + non-root [T]
**Исправлено.** Multi-stage build, non-root user, HEALTHCHECK.

---

### P1-P: Продуктовые

#### P1-P1. ✅ Backend "auto" → SQLite по умолчанию [C]
**Исправлено.** SQLite — default backend.

---

#### P1-P2. ✅ Dedup — не хэшировать только первые 2000 символов [C]
**Исправлено.** Полный текст хэшируется.

---

#### P1-P3. ✅ README ↔ Reality — capability matrix [C]
**Исправлено.** README актуализирован: Vector ✅, Hybrid ✅, 1333 тестов, P0/P1 в прогрессе.

---

## 🟡 P2 — Средний приоритет (Неделя 3–4)

### Алгоритмические оптимизации [T]

| # | Проблема | Текущее | Цель | Fix |
|---|----------|---------|------|-----|
| P2-1 | BFS в SemanticMemory | `list.pop(0)` → O(V²) | O(V+E) | `collections.deque` |
| P2-2 | `retrieve_by_concept()` | `ep not in results` → O(n²) | O(1) lookup | `seen = set()` |
| P2-3 | `_cleanup_working_memory()` | get_all + remove в цикле → O(n²) | O(n) | batch remove |
| P2-4 | `_evict_least_important()` | `sorted()` для удаления одного → O(n log n) | O(n) | `min()` |

**Effort:** 2–3 часа (все четыре вместе)

---

### Локальные дефекты [T]

| # | Проблема | Риск | Fix |
|---|----------|------|-----|
| P2-5 | `_new_id()` обрезает UUID4 до 8 hex (32 бита) | Коллизии при ~65K событиях (birthday paradox) | UUID4 полный или 16 hex |
| P2-6 | `_maybe_autosave()` при `autosave_every == 0` | `ZeroDivisionError` | Guard: `if not self.autosave_every: return` |
| P2-7 | `handler.__name__` | `AttributeError` для lambda/partial | `getattr(handler, '__name__', repr(handler))` |
| P2-8 | `apply_decay()` обновляет `updated_ts` ВСЕХ узлов | Метрика «последнее обновление» теряет смысл | Обновлять только если decay изменил значение |
| P2-9 | Ротация логов только для `brain.jsonl` | Категорийные лог-файлы растут бесконечно | Ротировать все файлы |
| P2-10 | Три разных шкалы порогов уверенности | Путаница между trace_builder / digest / validator | Единая шкала в config |
| P2-11 | `to_dict()`: `dataclasses.asdict()` vs `vars(self)` | Мутация вложенных объектов | Единый подход через ContractMixin |

**Effort:** 3–4 часа (все вместе)

---

### Инфраструктура [T]

| # | Задача | Effort |
|---|--------|--------|
| P2-12 | Docker build job в CI | 15 мин |
| P2-13 | Dependabot для security updates | 15 мин |
| P2-14 | Bandit (SAST) в CI: `bandit -r brain/ -ll` | 30 мин |
| P2-15 | Codecov интеграция | 30 мин |
| P2-16 | CI badge в README | 5 мин |

---

### Продуктовое качество [C]

| # | Задача | Effort |
|---|--------|--------|
| P2-17 | JSON ingestion: числа/bool → строки → шум в semantic search | 1 час |
| P2-18 | InputRouter `os.path.exists()` guessing → explicit type hint | 1 час |
| P2-19 | Чанкинг по символам → sentence-aware boundaries | 2–3 часа |
| P2-20 | Integration test: «сохранил → перезапустил → нашёл» | 1 час |

---

## 🔵 P3 — Nice-to-have (Месяц 2+)

> ⚠️ **Не распыляться на P3**, пока не закрыты: thread safety на горячих путях, bounded memory/logging, persisted retrieval, integration tests «сохранил → перезапустил → нашёл».

### Документация и DX

| # | Задача | Effort |
|---|--------|--------|
| P3-1 | CHANGELOG.md (Keep a Changelog format) | 1 час |
| P3-2 | CONTRIBUTING.md | 1 час |
| P3-3 | API reference (mkdocs + mkdocstrings) | 1 день |
| P3-4 | ADR (Architecture Decision Records) | 2 часа |
| P3-5 | Убрать Python 3.14 из classifiers (не тестируется в CI) | 5 мин |

### Тестирование

| # | Задача | Effort |
|---|--------|--------|
| P3-6 | Property-based тесты (hypothesis) для ContractMixin roundtrip | 2–3 часа |
| P3-7 | Mutation testing (mutmut) — верификация качества тестов | 1 день |
| P3-8 | Concurrent stress tests для EventBus + Scheduler | 2–3 часа |

### Архитектура

| # | Задача | Effort |
|---|--------|--------|
| P3-9 | Async EventBus (asyncio или thread pool dispatch) | 2–3 дня |
| P3-10 | Pipeline pattern для CognitiveCore.run() (вместо god-method) | 1–2 дня |
| P3-11 | Scheduler интеграция в CLI (`--autonomous` mode) | 1 день |
| P3-12 | SQLCipher для encryption at rest (если данные чувствительные) | 1 день |
| P3-13 | LLM Bridge (Этап N) — стратегический приоритет для демо | 1–2 недели |

---

## 📅 Timeline — сводка

```
✅ Неделя 1:  P0-E1..E5  — Thread safety, memory leaks, critical bugs — DONE
✅            P0-P2      — ResponseValidator fix — DONE
           
✅ Неделя 2:  P0-P1      — Real vector retrieval — DONE (60 тестов)
✅            P1-E1..E11 — from_dict, GoalManager, EventBus Protocol,
                           mypy, types, Docker, CI hardening — DONE
✅            P1-P1..P3  — Backend default, dedup, capability matrix — DONE

⬜ Неделя 3:  P2-1..P2-11 — Algorithms, local defects

⬜ Неделя 4:  P2-12..P2-20 — Infra, product quality
           
⬜ Месяц 2+:  P3-1..P3-13 — DX, testing depth, architecture evolution
```

---

## 📊 Effort Estimate

| Приоритет | Задач | Effort |
|-----------|-------|--------|
| 🔴 P0 | 7 | ~4–6 дней |
| 🟠 P1 | 14 | ~4–6 дней |
| 🟡 P2 | 20 | ~4–6 дней |
| 🔵 P3 | 13 | ~3–4 недели |
| **Итого** | **54** | **~3–4 недели до strong beta-level** |

---

## 💡 Стратегическая рекомендация

**Формула из обоих аудитов:**

```
1. 🔴 Thread safety + memory leaks     (Tasklet P0 — без этого crash в runtime)
2. 🔴 Real retrieval pipeline           (ChatGPT P0 — без этого нет value)
3. 🟠 Type safety + CI hardening        (Tasklet P1 — масштаб и надёжность)
4. 🟠 README ↔ Reality alignment        (ChatGPT P1 — доверие пользователей)
5. 🔵 LLM Bridge                        (Обе стороны — стратегический unlock)
```

> **Проект уникален** — это не LLM wrapper, а когнитивная система с нуля.  
> Сначала — hardening, чтобы не crash'илась.  
> Потом — retrieval, чтобы реально работала.  
> Потом — LLM Bridge, чтобы впечатляла.

---

## 📝 История ревизий

| Версия | Дата | Изменения |
|--------|------|-----------|
| v1 | 27.03.2026 | Первоначальный merged plan |
| v2 | 27.03.2026 | Перекрёстная рецензия: P0-E5 (from_dict) → P1, P0-E6 (GoalManager) → P1, P0-E8 (EventBusProtocol) → P1. Таймлайн скорректирован на «strong beta-level». |
| v3 | июнь 2026 | P0 (7/7 ✅) и P1 (14/14 ✅) завершены. Vector retrieval полностью функционален. 1333 тестов, 84.44% coverage, ruff 0, mypy 0. Ссылки на TODO.md обновлены на корневой файл. |

---

*Merged action plan v2 — на основе двух независимых аудитов (Tasklet + ChatGPT) и перекрёстной рецензии обоих аудиторов.*
