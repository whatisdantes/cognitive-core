# 🧠 TODO — Master Roadmap

> **Назначение документа:** зафиксировать путь от старта проекта до MVP-complete (этапы A–M).
> Активный backlog пост-MVP работы живёт в [`FUTURE_TODO.md`](FUTURE_TODO.md).
>
> **Спецификация:** [`BRAIN.md`](../BRAIN.md) · **ADR:** [`../adr/README.md`](../adr/README.md)
>
> **Живые метрики** в этот файл намеренно не вшиваются — их получают локально:
>
> ```bash
> python -m pytest tests/ --collect-only -q        # число собранных тестов
> python -m pytest tests/ --cov=brain              # покрытие
> python -m ruff check brain/ tests/               # lint
> python -m mypy brain/ --ignore-missing-imports   # type check
> python -m bandit -r brain/ -c pyproject.toml -q  # SAST
> ```

---

## 🗺️ Roadmap

| Этап    | Название                                             | Статус                           |
|---------|------------------------------------------------------|----------------------------------|
| **A–G**  | MVP: Core · Perception · Memory · Cognition · Output | ✅ Завершено                     |
| **P**    | Hardening · CI · Алгоритмы · DX (P0–P3)              | ✅ 53/53                         |
| **H**    | Attention & Resource Control                         | ✅ 4/5 (H.5 — deferred)          |
| **I**    | Learning Loop + интеграция                           | ✅ 3/3                           |
| **N**    | LLM Bridge                                           | ✅ 5/5                           |
| **J**    | Multimodal Expansion                                 | ✅ 5/5                           |
| **K**    | Cross-Modal Fusion                                   | ✅ 4/4                           |
| **L**    | Safety & Boundaries                                  | ✅ 6/6                           |
| **M**    | Reward & Motivation                                  | ✅ 3/3                           |
| **CUDA** | Compute Backend (зарезервировано)                    | ⬜ 0/3                           |

**MVP-complete:** этапы A–M закрыты. Следующие треки развития:

- [`FUTURE_TODO.md`](FUTURE_TODO.md) — post-MVP backlog: настоящая автономность (idle-loop, stdin/IPC, self-reflection, LLM-augmented output, метрики).
- **CUDA Backend** — зарезервированный слот; триггер старта — CPU bottleneck на реальной нагрузке.

---

## ✅ P — Hardening · CI · Алгоритмы · DX (53/53)

<details>
<summary><strong>P0 — Критические (7/7)</strong></summary>

| ID | Описание |
|----|----------|
| P0-E1 | Потокобезопасность — 6 модулей → `threading.RLock()`, return copies |
| P0-E2 | Race condition в `ResourceMonitor._apply_state()` |
| P0-E3 | Утечка памяти в `BrainLogger` → TTL/LRU (BoundedIndex) |
| P0-E4 | 100 МБ RAM spike при ротации логов → `shutil.copyfileobj` chunked |
| P0-E5 | `importance ≠ confidence` → разделены параметры |
| P0-P1 | Vector/hybrid retrieval — `_build_vector_index()`, incremental |
| P0-P2 | `ResponseValidator` — severity `warning`, `is_valid=True` после автокоррекции |

</details>

<details>
<summary><strong>P1 — Высокий приоритет (14/14)</strong></summary>

| ID | Описание |
|----|----------|
| P1-E1 | `ContractMixin.from_dict()` — рекурсивный с вложенными dataclass/Enum |
| P1-E2 | `GoalManager._remove_from_queue()` — lazy-delete |
| P1-E3 | `EventBusProtocol.publish()` — несовпадение сигнатур |
| P1-E4 | `mypy` → 0 errors (все модули) |
| P1-E5 | `Any` → Protocol-типы (`Reasoner`, `CognitiveCore`) |
| P1-E6 | Coverage gate в CI (`--cov-fail-under=70`) |
| P1-E7 | Lock-файл для reproducible builds |
| P1-E8 | Ruff rules расширены (B, SIM, C4, RET, PIE) |
| P1-E9 | `copy.deepcopy` → `dataclasses.replace` в `ContradictionDetector` |
| P1-E10 | `DialogueResponder` → переиспользует `OutputTraceBuilder` |
| P1-E11 | Docker — multi-stage + non-root |
| P1-P1 | Backend "auto" → SQLite по умолчанию |
| P1-P2 | Dedup — хэшировать полный текст |
| P1-P3 | README ↔ Reality — capability matrix |

</details>

<details>
<summary><strong>P2 — Средний приоритет (20/20)</strong></summary>

| ID | Описание |
|----|----------|
| P2-1 | BFS: `list.pop(0)` → `deque.popleft()` |
| P2-2 | `retrieve_by_concept()`: O(n²) → `seen: set[str]` |
| P2-3 | `_cleanup_working_memory()` → `batch_remove()` |
| P2-4 | `_evict_least_important()`: `sorted()` → `min()` |
| P2-5 | `_new_id()`: UUID4 12 hex → `uuid4().hex` (128 бит) |
| P2-6 | `_maybe_autosave()` при `autosave_every==0` → ZeroDivisionError guard |
| P2-7 | `handler.__name__` → `_handler_name()` helper (lambda/partial safe) |
| P2-8 | `apply_decay()` → обновлять только изменённые узлы |
| P2-9 | Ротация логов → все файлы (не только `brain.jsonl`) |
| P2-10 | Три шкалы порогов → единая `hedge_threshold` в `PolicyConstraints` |
| P2-11 | `to_dict()` round-trip контракт задокументирован |
| P2-12 | Docker build job в CI |
| P2-13 | Dependabot (pip + github-actions, weekly) |
| P2-14 | Bandit (SAST) в CI |
| P2-15 | Codecov интеграция |
| P2-16 | CI badges в README |
| P2-17 | JSON ingestion: только строки (`_extract_strings_from_json()`) |
| P2-18 | `InputRouter` → `InputType` enum (FILE/TEXT/AUTO) |
| P2-19 | Чанкинг → sentence-aware (`razdel` + regex fallback) |
| P2-20 | Integration test: «сохранил → перезапустил → нашёл» |

</details>

<details>
<summary><strong>P3 — Nice-to-have (12/12)</strong></summary>

| ID | Описание |
|----|----------|
| P3-2 | CONTRIBUTING.md |
| P3-3 | API reference (mkdocs + mkdocstrings) |
| P3-4 | ADR → `docs/adr/` (7 ADR + README) |
| P3-5 | Убрать Python 3.14 из classifiers |
| P3-6 | Property-based тесты (hypothesis) для `ContractMixin` |
| P3-7 | Mutation testing (`mutmut`) — **ЗАМОРОЖЕНО** (Windows не поддерживается) |
| P3-8 | Concurrent stress tests (EventBus + Scheduler) |
| P3-9 | Async EventBus → `ThreadPoolEventBus` |
| P3-10 | Pipeline pattern → `brain/cognition/pipeline.py` (20 шагов) |
| P3-11 | Scheduler в CLI (`--autonomous`, `--ticks N`) |
| P3-12 | SQLCipher encryption at rest → graceful fallback |

</details>

---

## ✅ H — Attention & Resource Control (4/5)

- [x] **H.1** `SalienceEngine` — `salience = 0.25·novelty + 0.35·urgency + 0.25·threat + 0.15·goal_relevance`; пороги: >0.8 → interrupt, >0.5 → prioritize
- [x] **H.2** `AttentionController` — 6 пресетов бюджета (`text_focused`, `multimodal`, `memory_intensive`, `degraded`, `critical`, `emergency`)
- [x] **H.3** `PolicyLayer` — 3 фильтра (F0/F1/F2) + 3 модификатора (M1: −0.15, M2: +0.20, M3: +0.15)
- [x] **H.4** `CognitivePipeline` расширен до 20 шагов (salience + budget + policy)
- [ ] **H.5** Ring 2 — Deep Reasoning (multi-iteration refinement) — _отложено на Post-MVP_

---

## ✅ I — Learning Loop (3/3) + Интеграция

- [x] **I.1** `OnlineLearner` — Хеббовское обучение `Δw = lr × conf`, source trust
- [x] **I.2** `KnowledgeGapDetector` — MISSING / WEAK / OUTDATED, дедупликация по `(concept, gap_type)`
- [x] **I.3** `ReplayEngine` — 4 стратегии, stale pruning (age > 7d, imp < 0.1)
- [x] Интеграция в Pipeline: `step_detect_knowledge_gaps` (шаг 10) + `step_post_cycle` (шаг 17) + CLI replay

---

## ✅ N — LLM Bridge (5/5)

- [x] **N.1–5** `LLMBridge` (retry + timeout) · `MockProvider` · `OpenAIProvider` · `AnthropicProvider` · `LLMSafetyWrapper` · `step_llm_enhance` · CLI флаги (`--llm-provider`, `--llm-api-key`)

---

## ✅ J — Multimodal Expansion (5/5)

**Цель:** Vision + Audio + Video ingestors (CPU-only, ≤ 3 GB суммарно).

- [x] **J.1** `brain/perception/vision_ingestor.py` — `VisionIngestor` (PIL + pytesseract OCR, graceful fallback)
- [x] **J.2** `brain/perception/audio_ingestor.py` — `AudioIngestor` (Whisper ASR, WAV metadata, graceful fallback)
- [x] **J.3** `brain/encoders/vision_encoder.py` — `VisionEncoder` (CLIP ViT-B/32, 512d, L2-norm, graceful fallback)
- [x] **J.4** `brain/encoders/audio_encoder.py` — `AudioEncoder` (Whisper encoder features, dynamic dim, graceful fallback)
- [x] **J.5** `brain/encoders/temporal_encoder.py` — `TemporalEncoder` (cv2 + CLIP mean-pool, 512d, graceful fallback)
- [x] **J.6** `brain/encoders/encoder_router.py` — `EncoderRouter` (маршрутизация по modality)
- [x] `brain/perception/input_router.py` — backward-compatible расширение: `vision_ingestor` / `audio_ingestor` params

---

## ✅ K — Cross-Modal Fusion (4/4)

**Цель:** выровнять embeddings разных модальностей в единое пространство.

- [x] **K.1** `brain/fusion/shared_space_projector.py` — `SharedSpaceProjector` (Xavier init, 512d L2-norm, `project` / `project_percept` / `project_all`, save/load)
- [x] **K.2** `brain/fusion/entity_linker.py` — `EntityLinker` + `CrossModalLink` + `EntityCluster` (union-find, STRONG > 0.90 / LINK > 0.75 / WEAK > 0.60, только кросс-модальные пары)
- [x] **K.3** `brain/fusion/confidence_calibrator.py` — `ConfidenceCalibrator` (`base_quality × modality_agreement × source_trust × recency`)
- [x] **K.4** `brain/fusion/cross_modal_contradiction_detector.py` — `CrossModalContradictionDetector` (MODAL_MISMATCH: sim < 0.20, CONFIDENCE_CONFLICT: |Δq| > 0.50)

---

## ✅ L — Safety & Boundaries (6/6)

**Цель:** верификация источников, детекция конфликтов, аудит.

- [x] **L.1** `brain/safety/source_trust.py` — `SourceTrustScore`, `SourceTrustManager` (clamp [0, 1], decay, boost)
- [x] **L.2** `brain/safety/conflict_detector.py` — `Conflict`, `ConflictDetector` (SemanticNode-level, O(n²))
- [x] **L.3** `brain/safety/boundary_guard.py` — `GuardResult`, `BoundaryGuard` (PII redaction, confidence gate, `RESTRICTED_ACTIONS`)
- [x] **L.4** `brain/safety/audit_logger.py` — `AuditEvent`, `AuditLogger` (JSONL, rotation, RLock)
- [x] **L.5** `brain/safety/policy_layer.py` — `SafetyDecision`, `SafetyPolicyLayer` (SF-1 / SF-2 / SF-3)
- [x] **L.6** `brain/cognition/pipeline.py` — 20 шагов: `step_safety_input_check` (3), `step_safety_policy_check` (14), `step_safety_audit_log` (18)

---

## ✅ M — Reward & Motivation (3/3)

**Цель:** внутренняя мотивация, система вознаграждения, любопытство.

**Формулы:**

- `RewardEngine`: `prediction_error = actual_reward − expected_reward`
- `MotivationEngine`: `motivation = α·new + (1 − α)·old` (α = 0.1), decay ×0.95 каждые 100 циклов
- `CuriosityEngine`: `curiosity(X) = 1 / max(knowledge_coverage(X), 0.01)`

**Типы вознаграждений:**

| Тип          | Триггер                                  | Значение |
|--------------|------------------------------------------|----------|
| `epistemic`  | Узнал новый факт, закрыл пробел          | +0.8     |
| `accuracy`   | Пользователь подтвердил ответ            | +1.0     |
| `coherence`  | Разрешил противоречие                    | +0.6     |
| `completion` | Выполнил план/цель                       | +0.7     |
| `efficiency` | Быстрый ответ с высокой уверенностью     | +0.3     |
| `penalty`    | Пользователь исправил ошибку             | −0.5     |

- [x] **M.1** `brain/motivation/reward_engine.py` — `RewardEngine` (`RewardType`, `REWARD_VALUES`, `RewardSignal`, sliding mean, prediction error)
- [x] **M.2** `brain/motivation/motivation_engine.py` — `MotivationEngine` (EMA α = 0.1, decay ×0.95 / 100 циклов, side-effects в `GoalManager` и `ReplayEngine`)
- [x] **M.3** `brain/motivation/curiosity_engine.py` — `CuriosityEngine` (score = 1/coverage, threshold = 0.8, `GoalManager` auto-push)
- [x] `brain/learning/replay_engine.py` — `mark_as_high_value(episode_id)` добавлен

---

## ⬜ CUDA Backend (зарезервировано)

- [ ] Compute backend abstraction: `brain/core/cpu_backend.py` + `brain/core/cuda_backend.py`
- [ ] Приоритет переноса: text encoder → embeddings → reranker → local LLM inference
- [ ] Флаг: `USE_GPU=False` (зарезервировано)

**Триггер старта:** профилировка показала CPU bottleneck на реальной нагрузке.
До тех пор приоритет — post-MVP автономия ([`FUTURE_TODO.md`](FUTURE_TODO.md)).

---

## 📜 Исторические вехи

<details>
<summary><strong>MVP A–G — Основная реализация</strong></summary>

**A** Shared Contracts · **B** Autonomous Runtime · **C** Logging · **D** Text Perception · **E** Text Encoder · **F / F+** Cognitive MVP + Extensions · **G** Output MVP

</details>

<details>
<summary><strong>BrainLogger Integration</strong></summary>

`NullBrainLogger` + `NullTraceBuilder` · CLI `--log-dir` / `--log-level` · интеграция в `CognitiveCore` · `CognitivePipeline` · `MemoryManager` · `InputRouter` · `DialogueResponder` · `EventBus` · `Scheduler`

</details>

<details>
<summary><strong>Learning Integration</strong></summary>

`Reasoner`: `MemorySearchResult` в `trace.metadata` · Pipeline: шаги 10 + 17 · `CognitiveCore`: `OnlineLearner` + `KnowledgeGapDetector` · CLI: `ReplayEngine` · Golden fixes: q04, q14

</details>

---

## 🧪 Тестирование

- **Живой счёт и поломки:** `python -m pytest tests/ -v` (или `--collect-only -q` для сбора без запуска).
- **Coverage gate:** 70% (`--cov-fail-under=70`) — см. `pyproject.toml` и CI.
- **Известное ограничение:** 4 теста `TestEncryptedDatabase` в `tests/test_storage_encrypted.py` помечены `@pytest.mark.xfail(strict=False)` — `sqlite3.Row` не принимает `sqlcipher3.dbapi2.Cursor`. Валидация ключа, plain-SQLite пути и ветка `ImportError` не затронуты. При починке в `brain/memory/storage.py` снять декоратор.

---

## 📌 Правило принятия решений

При возникновении новой идеи — три вопроса:

1. Помогает ли это закрыть открытую задачу (CUDA Backend или пункт из [`FUTURE_TODO.md`](FUTURE_TODO.md))?
2. Улучшает ли наблюдаемость, стабильность или retrieval?
3. Не уводит ли в research раньше времени?

**да / да / нет** → брать  
**нет / нет / да** → откладывать в [`FUTURE_TODO.md`](FUTURE_TODO.md) или фиксировать как ADR в [`../adr/README.md`](../adr/README.md)
