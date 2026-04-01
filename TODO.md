# 🧠 TODO — Master Roadmap
## cognitive-core v0.7.0

> **Тесты:** 2162/2162 ✅ (5 skipped) · **Coverage:** 84%+ · **Ruff:** 0 · **Mypy:** 0 · **Bandit:** 0 · **CI:** test + lint + typecheck + sast  
> **Спецификация:** [`docs/BRAIN.md`](docs/BRAIN.md) · **ADR:** [`docs/adr/`](docs/adr/) · **История:** [`CHANGELOG.md`](CHANGELOG.md)

---

## 🗺️ Roadmap

| Этап | Название | Статус | Тестов |
|------|----------|--------|--------|
| **P** | Hardening · CI · Алгоритмы · DX (P0–P3) | ✅ 53/53 | 1800 |
| **H** | Attention & Resource Control | ✅ 4/5 | 31 |
| **I** | Learning Loop | ✅ 3/3 | 35 |
| **N** | LLM Bridge | ✅ 5/5 | 70 |
| **J** | Multimodal Expansion | ✅ 5/5 | 109 |
| **K** | Cross-Modal Fusion | ✅ 4/4 | 61 |
| **L** | Safety & Boundaries | ✅ 6/6 | 107 |
| **M** | Reward & Motivation | ✅ 3/3 | 84 |
| **CUDA** | Compute Backend | ⬜ 0/3 | — |

**Следующие шаги:** CUDA Backend

---

## ✅ P — Завершено (53/53)

<details>
<summary><strong>P0 — Критические (7/7) ✅</strong></summary>

| ID | Описание |
|----|----------|
| P0-E1 | Потокобезопасность — 6 модулей → `threading.RLock()`, return copies |
| P0-E2 | Race condition в `ResourceMonitor._apply_state()` |
| P0-E3 | Утечка памяти в `BrainLogger` → TTL/LRU (BoundedIndex) |
| P0-E4 | 100 МБ RAM spike при ротации логов → `shutil.copyfileobj` chunked |
| P0-E5 | `importance ≠ confidence` → разделены параметры |
| P0-P1 | Vector/hybrid retrieval — `_build_vector_index()`, incremental, 60 тестов |
| P0-P2 | `ResponseValidator` — severity `warning`, `is_valid=True` после автокоррекции |

</details>

<details>
<summary><strong>P1 — Высокий приоритет (14/14) ✅</strong></summary>

| ID | Описание |
|----|----------|
| P1-E1 | ContractMixin.from_dict() — рекурсивный с вложенными dataclass/Enum |
| P1-E2 | GoalManager._remove_from_queue() — lazy-delete |
| P1-E3 | EventBusProtocol.publish() — несовпадение сигнатур |
| P1-E4 | mypy → 0 errors (все модули) |
| P1-E5 | Any → Protocol-типы (Reasoner, CognitiveCore) |
| P1-E6 | Coverage gate в CI (`--cov-fail-under=70`) |
| P1-E7 | Lock-файл для reproducible builds |
| P1-E8 | Ruff rules расширены (B, SIM, C4, RET, PIE) |
| P1-E9 | copy.deepcopy → dataclasses.replace в ContradictionDetector |
| P1-E10 | DialogueResponder → переиспользует OutputTraceBuilder |
| P1-E11 | Docker — multi-stage + non-root |
| P1-P1 | Backend "auto" → SQLite по умолчанию |
| P1-P2 | Dedup — хэшировать полный текст |
| P1-P3 | README ↔ Reality — capability matrix |

</details>

<details>
<summary><strong>P2 — Средний приоритет (20/20) ✅</strong></summary>

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
| P2-16 | CI badges в README (4 шт.) |
| P2-17 | JSON ingestion: только строки (`_extract_strings_from_json()`) |
| P2-18 | InputRouter → `InputType` enum (FILE/TEXT/AUTO) |
| P2-19 | Чанкинг → sentence-aware (`razdel` + regex fallback) |
| P2-20 | Integration test: «сохранил → перезапустил → нашёл» (6 тестов) |

</details>

<details>
<summary><strong>P3 — Nice-to-have (12/12) ✅</strong></summary>

| ID | Описание |
|----|----------|
| P3-1 | CHANGELOG.md (Keep a Changelog) |
| P3-2 | CONTRIBUTING.md |
| P3-3 | API reference (mkdocs + mkdocstrings, 7 страниц) |
| P3-4 | ADR → `docs/adr/` (7 ADR + README) |
| P3-5 | Убрать Python 3.14 из classifiers |
| P3-6 | Property-based тесты (hypothesis) для ContractMixin |
| P3-7 | Mutation testing (mutmut) — **ЗАМОРОЖЕНО** (Windows не поддерживается) |
| P3-8 | Concurrent stress tests (EventBus + Scheduler) |
| P3-9 | Async EventBus → `ThreadPoolEventBus` |
| P3-10 | Pipeline pattern → `brain/cognition/pipeline.py` (14 шагов) |
| P3-11 | Scheduler в CLI (`--autonomous`, `--ticks N`) |
| P3-12 | SQLCipher encryption at rest → graceful fallback |

</details>

---

## ✅ H — Attention & Resource Control (4/5)

- [x] **H.1** `SalienceEngine` — `salience = 0.25·novelty + 0.35·urgency + 0.25·threat + 0.15·goal_relevance`; пороги: >0.8→interrupt, >0.5→prioritize ✅
- [x] **H.2** `AttentionController` — 6 пресетов бюджета (text_focused, multimodal, memory_intensive, degraded, critical, emergency) ✅
- [x] **H.3** `PolicyLayer` — 3 фильтра (F0/F1/F2) + 3 модификатора (M1: −0.15, M2: +0.20, M3: +0.15) ✅
- [x] **H.4** `CognitivePipeline` расширен до 14 шагов (salience + budget + policy) ✅
- [ ] **H.5** Ring 2 — Deep Reasoning (multi-iteration refinement) — _отложено на Post-MVP_

---

## ✅ I — Learning Loop (3/3) + Интеграция

- [x] **I.1** `OnlineLearner` — Хеббовское обучение `Δw = lr × conf`, source trust ✅
- [x] **I.2** `KnowledgeGapDetector` — MISSING/WEAK/OUTDATED, дедупликация по (concept, gap_type) ✅
- [x] **I.3** `ReplayEngine` — 4 стратегии, stale pruning (age>7d, imp<0.1) ✅
- [x] Интеграция: `step_detect_knowledge_gaps()` (шаг 10) + `step_post_cycle()` (шаг 17) + CLI replay ✅

---

## ✅ N — LLM Bridge (5/5)

- [x] **N.1–5** `LLMBridge` (retry+timeout) · `MockProvider` · `OpenAIProvider` · `AnthropicProvider` · `LLMSafetyWrapper` · `step_llm_enhance` · CLI флаги · 70 тестов ✅

---

## ✅ J — Multimodal Expansion (5/5)

**Зависит от:** E ✅ (Text Encoder), B ✅ (Perception Layer)  
**Цель:** Vision + Audio + Video ingestors (CPU-only, ≤ 3 GB суммарно)  
**Спецификация:** `docs/superpowers/specs/2026-04-02-multimodal-expansion-design.md`

- [x] **J.1** `brain/perception/vision_ingestor.py` — VisionIngestor (PIL + pytesseract OCR, graceful fallback) ✅ 26 тестов
- [x] **J.2** `brain/perception/audio_ingestor.py` — AudioIngestor (Whisper ASR, WAV metadata, graceful fallback) ✅ 24 тестов
- [x] **J.3** `brain/encoders/vision_encoder.py` — VisionEncoder (CLIP ViT-B/32, 512d, L2-norm, graceful fallback) ✅ 13 тестов
- [x] **J.4** `brain/encoders/audio_encoder.py` — AudioEncoder (Whisper encoder features, dynamic dim, graceful fallback) ✅ 13 тестов
- [x] **J.5** `brain/encoders/temporal_encoder.py` — TemporalEncoder (cv2 + CLIP mean-pool, 512d, graceful fallback) ✅ 14 тестов
- [x] **J.6** `brain/encoders/encoder_router.py` — EncoderRouter (маршрутизация по modality) ✅ 14 тестов
- [x] `brain/encoders/__init__.py` — экспорт VisionEncoder, AudioEncoder, TemporalEncoder, EncoderRouter ✅
- [x] `brain/perception/__init__.py` — экспорт VisionIngestor, AudioIngestor ✅
- [x] `brain/perception/input_router.py` — backward-compatible: vision_ingestor/audio_ingestor params ✅

**Файлы:** 4 новых энкодера · 2 новых ингестора · 1 роутер · 2 обновлённых __init__.py · 1 обновлённый input_router  
**Тесты:** `test_vision_ingestor.py` · `test_audio_ingestor.py` · `test_vision_encoder.py` · `test_audio_encoder.py` · `test_temporal_encoder.py` · `test_encoder_router.py`

---

## ✅ K — Cross-Modal Fusion (4/4)

**Зависит от:** J ✅ (Vision + Audio encoders)  
**Цель:** Выровнять embeddings разных модальностей в единое пространство  
**Спецификация:** `docs/superpowers/specs/2026-04-03-cross-modal-fusion-design.md`

- [x] **K.1** `brain/fusion/shared_space_projector.py` — SharedSpaceProjector (Xavier init, 512d L2-norm, project/project_percept/project_all, save/load) ✅ 17 тестов
- [x] **K.2** `brain/fusion/entity_linker.py` — EntityLinker + CrossModalLink + EntityCluster (union-find, STRONG>0.90/LINK>0.75/WEAK>0.60, только кросс-модальные пары) ✅ 16 тестов
- [x] **K.3** `brain/fusion/confidence_calibrator.py` — ConfidenceCalibrator (base_quality × modality_agreement × source_trust × recency=1.0) ✅ 15 тестов
- [x] **K.4** `brain/fusion/cross_modal_contradiction_detector.py` — CrossModalContradictionDetector + CrossModalContradiction (MODAL_MISMATCH sim<0.20, CONFIDENCE_CONFLICT |q|>0.50) ✅ 13 тестов

**Файлы:** `brain/fusion/__init__.py` (7 публичных экспортов) · 4 новых модуля  
**Тесты:** `test_shared_space_projector.py` · `test_entity_linker.py` · `test_confidence_calibrator.py` · `test_cross_modal_contradiction_detector.py`

---

## ✅ L — Safety & Boundaries (6/6)

**Зависит от:** G ✅ (Output Layer), N ✅ (LLM Bridge)  
**Цель:** Верификация источников, детекция конфликтов, аудит  
**Спецификация:** `docs/BRAIN.md` §11, `docs/layers/10_safety_boundaries.md`

- [x] **L.1** `brain/safety/source_trust.py` — `SourceTrustScore`, `SourceTrustManager` (clamp [0,1], decay, boost) ✅ 16 тестов
- [x] **L.2** `brain/safety/conflict_detector.py` — `Conflict`, `ConflictDetector` (SemanticNode-level, O(n²)) ✅ 19 тестов
- [x] **L.3** `brain/safety/boundary_guard.py` — `GuardResult`, `BoundaryGuard` (PII redaction, confidence gate, RESTRICTED_ACTIONS) ✅ 26 тестов
- [x] **L.4** `brain/safety/audit_logger.py` — `AuditEvent`, `AuditLogger` (JSONL, rotation, RLock) ✅ 13 тестов
- [x] **L.5** `brain/safety/policy_layer.py` — `SafetyDecision`, `SafetyPolicyLayer` (SF-1/2/3) ✅ 16 тестов
- [x] **L.6** `brain/cognition/pipeline.py` — интеграция 3 новых шагов (20 шагов итого) + `tests/test_safety_integration.py` ✅ 17 тестов

**Файлы:** `brain/safety/__init__.py` (11 публичных экспортов) · `brain/cognition/pipeline.py` (шаги 3, 14, 18)  
**Тесты:** `test_audit_logger.py` · `test_source_trust.py` · `test_conflict_detector.py` · `test_boundary_guard.py` · `test_safety_policy_layer.py` · `test_safety_integration.py`

---

## ✅ M — Reward & Motivation (3/3)

**Зависит от:** I ✅ (Learning Loop), L ✅ (Safety)  
**Цель:** Внутренняя мотивация, система вознаграждения, любопытство  
**Спецификация:** `docs/BRAIN.md` §15, §17.2

**Формулы:**
- `RewardEngine`: `prediction_error = actual_reward − expected_reward`
- `MotivationEngine`: `motivation = α·new + (1−α)·old` (α=0.1), decay ×0.95 каждые 100 циклов
- `CuriosityEngine`: `curiosity(X) = 1 / max(knowledge_coverage(X), 0.01)`

**Типы вознаграждений:**

| Тип | Триггер | Значение |
|-----|---------|----------|
| `epistemic` | Узнал новый факт, закрыл пробел | +0.8 |
| `accuracy` | Пользователь подтвердил ответ | +1.0 |
| `coherence` | Разрешил противоречие | +0.6 |
| `completion` | Выполнил план/цель | +0.7 |
| `efficiency` | Быстрый ответ с высокой уверенностью | +0.3 |
| `penalty` | Пользователь исправил ошибку | −0.5 |

- [x] **M.1** `brain/motivation/reward_engine.py` — RewardEngine (RewardType, REWARD_VALUES, RewardSignal, sliding_mean, prediction_error) ✅ 31 тестов
- [x] **M.2** `brain/motivation/motivation_engine.py` — MotivationEngine (EMA α=0.1, decay ×0.95/100 циклов, GoalManager + ReplayEngine side-effects) ✅ 34 тестов
- [x] **M.3** `brain/motivation/curiosity_engine.py` — CuriosityEngine (score=1/coverage, threshold=0.8, GoalManager auto-push) ✅ 19 тестов
- [x] `brain/motivation/__init__.py` — 7 публичных экспортов ✅
- [x] `brain/learning/replay_engine.py` — `mark_as_high_value(episode_id)` добавлен ✅

**Файлы:** `brain/motivation/` (4 файла) · `brain/learning/replay_engine.py` (расширен)  
**Тесты:** `test_reward_engine.py` · `test_motivation_engine.py` · `test_curiosity_engine.py` · **84 теста итого**

---

## ⬜ CUDA Backend

- [ ] Compute backend abstraction: `brain/core/cpu_backend.py` + `brain/core/cuda_backend.py`
- [ ] Приоритет: text encoder → embeddings → reranker → local LLM inference
- [ ] Флаг: `USE_GPU=False` (зарезервировано)

---

## ✅ Completed (история реализации)

<details>
<summary><strong>MVP A–G — Основная реализация (793 теста) ✅</strong></summary>

- [x] **A** Shared Contracts · **B** Autonomous Runtime · **C** Logging · **D** Text Perception · **E** Text Encoder · **F/F+** Cognitive MVP + Extensions · **G** Output MVP

</details>

<details>
<summary><strong>LOG_PLAN.md v2.0 — BrainLogger Integration ✅ 13/13</strong></summary>

- [x] NullBrainLogger + NullTraceBuilder · CLI `--log-dir`/`--log-level` · CognitiveCore + Pipeline + MemoryManager + InputRouter + DialogueResponder + EventBus + Scheduler logging · 19 тестов

</details>

<details>
<summary><strong>Learning Integration ✅ 7/7</strong></summary>

- [x] Reasoner: `MemorySearchResult` в `trace.metadata` · Pipeline: шаги 10 + 17 · CognitiveCore: OnlineLearner + KnowledgeGapDetector · CLI: ReplayEngine · 7 тестов · Golden fixes: q04, q14

</details>

---

## 🧪 Test Coverage

**Всего: 2162/2162 ✅** (5 skipped) · Coverage: 84%+ · 51 test files

| Файл | Модуль | Тестов |
|------|--------|--------|
| `test_bm25.py` | BM25 Scorer + KeywordBackend | 55 |
| `test_cli.py` | CLI entrypoint | 20 |
| `test_cognition.py` | Cognitive Core | 190 |
| `test_cognition_integration.py` | Cognitive Core (integration) | 7 |
| `test_e2e_pipeline.py` | E2E Pipeline | 10 |
| `test_golden.py` | Golden-answer benchmarks | 414 |
| `test_logging.py` | Logging & Observability | 25 |
| `test_memory.py` | Memory System | 101 |
| `test_output.py` | Output Layer | 106 |
| `test_output_integration.py` | Output Layer (integration) | 7 |
| `test_perception.py` | Perception Layer | 79 |
| `test_perception_hardening.py` | Perception Hardening | 34 |
| `test_resource_monitor.py` | ResourceMonitor | 13 |
| `test_scheduler.py` | Scheduler | 11 |
| `test_storage.py` | SQLite Storage + Migration | 58 |
| `test_text_encoder.py` | Text Encoder | 80 |
| `test_utils.py` | text_utils + hash_utils | 63 |
| `test_vector_retrieval.py` | Vector Retrieval + Hybrid Search | 60 |
| `test_persistence_integration.py` | Persistence Integration | 6 |
| `test_contracts_hypothesis.py` | Property-based roundtrip | 4 |
| `test_concurrency_stress.py` | Concurrent stress | 3 |
| `test_storage_encrypted.py` | SQLCipher encryption | 6+5* |
| `test_attention_controller.py` | AttentionController (H) | 10 |
| `test_salience_engine.py` | SalienceEngine (H) | 12 |
| `test_policy_layer.py` | PolicyLayer (H) | 9 |
| `test_brain_logger_integration.py` | BrainLogger integration | 19 |
| `test_llm_bridge.py` | LLMBridge + providers (N) | 70 |
| `test_online_learner.py` | OnlineLearner (I) | 12 |
| `test_knowledge_gap_detector.py` | KnowledgeGapDetector (I) | 8 |
| `test_replay_engine.py` | ReplayEngine (I) | 15 |
| `test_learning_integration.py` | Learning Integration | 7 |
| `test_audit_logger.py` | AuditLogger (L) | 13 |
| `test_source_trust.py` | SourceTrustManager (L) | 16 |
| `test_conflict_detector.py` | ConflictDetector (L) | 19 |
| `test_boundary_guard.py` | BoundaryGuard (L) | 26 |
| `test_safety_policy_layer.py` | SafetyPolicyLayer (L) | 16 |
| `test_safety_integration.py` | Safety Integration (L) | 17 |
| `test_vision_ingestor.py` | VisionIngestor (J) | 26 |
| `test_audio_ingestor.py` | AudioIngestor (J) | 24 |
| `test_vision_encoder.py` | VisionEncoder (J) | 13 |
| `test_audio_encoder.py` | AudioEncoder (J) | 13 |
| `test_temporal_encoder.py` | TemporalEncoder (J) | 14 |
| `test_encoder_router.py` | EncoderRouter (J) | 14 |
| `test_shared_space_projector.py` | SharedSpaceProjector (K) | 17 |
| `test_entity_linker.py` | EntityLinker (K) | 16 |
| `test_confidence_calibrator.py` | ConfidenceCalibrator (K) | 15 |
| `test_cross_modal_contradiction_detector.py` | CrossModalContradictionDetector (K) | 13 |
| `test_reward_engine.py` | RewardEngine (M) | 31 |
| `test_motivation_engine.py` | MotivationEngine (M) | 34 |
| `test_curiosity_engine.py` | CuriosityEngine (M) | 19 |
| **Итого** | | **2162** |

> \* 6 тестов всегда, 5 — только при установленном `sqlcipher3`

---

## ✅ L — Safety & Boundaries Integration (история)

- [x] `brain/safety/audit_logger.py` — AUDIT_EVENTS, AuditEvent, AuditLogger (JSONL, rotation, RLock)
- [x] `brain/safety/source_trust.py` — SourceTrustScore, SourceTrustManager
- [x] `brain/safety/conflict_detector.py` — Conflict, ConflictDetector
- [x] `brain/safety/boundary_guard.py` — GuardResult, BoundaryGuard (PII, confidence gate, RESTRICTED_ACTIONS)
- [x] `brain/safety/policy_layer.py` — SafetyDecision, SafetyPolicyLayer (SF-1/2/3)
- [x] `brain/safety/__init__.py` — 11 публичных экспортов
- [x] `brain/cognition/pipeline.py` — 20 шагов: step_safety_input_check (3), step_safety_policy_check (14), step_safety_audit_log (18)
- [x] `tests/test_safety_integration.py` — 17 интеграционных тестов (T1–T5)

---

## 📌 Правило принятия решений

При возникновении новой идеи — три вопроса:

1. Помогает ли это закрыть текущий этап (J или L)?
2. Улучшает ли наблюдаемость, стабильность или retrieval?
3. Не уводит ли в research раньше времени?

**да / да / нет** → брать · **нет / нет / да** → откладывать в Research Branch
