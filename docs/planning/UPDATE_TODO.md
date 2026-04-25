# План реализации автономности и самообучения

> Исходный design spec: [`superpowers/specs/2026-04-21-autonomy-self-learning-design.md`](../superpowers/specs/2026-04-21-autonomy-self-learning-design.md)  
> Статус: готово к реализации по задачам  
> Область работ: автономный daemon, самообучение на материалах, claim-based memory, сомнение/разрешение конфликтов, hedged-ответы  
> Не входит: IPC/socket, multi-process architecture, web dashboard, legacy backfill `SemanticNode -> Claim`

---

## 0. Инварианты реализации

Эти правила являются частью контракта. Их нельзя ослаблять при реализации отдельных задач.

- `Claim` — первичная единица фактического знания. `SemanticNode.description` становится derived view из active claims.
- `SCHEMA_VERSION = 2` — additive, idempotent in-place migration из v1. Legacy semantic/episodic data должны оставаться читаемыми.
- `ClaimStatus.POSSIBLY_CONFLICTING` относится к claim-у; `claim_conflicts.status` относится к паре и имеет значения `candidate | disputed | resolved | dismissed`.
- `active_claims(concept)` возвращает только `status=active`; `answerable_claims(concept)` возвращает `active + disputed`.
- Majority считается по `(concept, claim_family_key, stance_key, source_group_id)`, а не по буквальному `claim_text`.
- `SourceMemory.get_trust()` вызывается с `source_group_id`. `source_ref` остаётся только citation/evidence pointer.
- LLM — только extractor/advisor. Он может создавать candidate claims или классифицировать конфликт, но не может сам менять статусы claims.
- Timeout не retract-ит unresolved disputes. Он пишет `claim_resolution_timed_out`, оставляет пару `disputed`, снижает confidence и обновляет verification goals.
- Scheduler работает в порядке `HIGH -> NORMAL -> LOW`; idle-задачи добавляются только когда нет pending HIGH/NORMAL и LOW backlog ниже `max_low_queue_backlog = 8`.
- Не создавать `UPGRADE_TODO.md` из этого плана без отдельной явной просьбы.

---

## 1. Roadmap

| Этап | Название | Зависимости | Главный артефакт | Статус |
|---|---|---|---|---|
| **U-0** | Memory foundation + logging wiring | — | `Claim`, `ClaimStore`, v2 schema, `MaterialRegistry`, lifecycle logs | ⏳ частично выполнено |
| **U-A** | Scheduler recurring + budgets | частично U-0 | `register_recurring`, scheduler ordering, `LLMRateLimiter` | [x] |
| **U-B** | Conflict lifecycle | U-0, U-A | `ConflictGuard`, fast candidate detection, slow reconciliation | [x] |
| **U-C** | Material ingestion pipeline | U-0, U-A, U-B | `MaterialIngestor`, chunk idempotence, `FileWatcher` | [x] |
| **U-D** | Curiosity-driven idle | U-A, U-B | `IdleDispatcher`, motivation/curiosity ranking | [x] |
| **U-E** | Output respecting disputed claims | U-0, U-B | claim-aware retrieval, hedged responses | [x] |
| **U-F** | Daemon mode + stdin | U-A..U-E | `--daemon`, startup scan, watcher, stdin reader | [x] |
| **U-G** | Conflict corpus + end-to-end tests | U-F | controlled fixtures and integration tests | [x] |

Рекомендуемый порядок реализации:

1. U-0.1 -> U-0.8: schema, claim model, stores, source trust, logging.
2. U-A.1 -> U-A.3: recurring scheduler и общий LLM budget.
3. U-B.1 -> U-B.4: conflict lifecycle, включая timeout semantics.
4. U-C: ingestion и watcher.
5. U-E: claim-aware output.
6. U-D: idle dispatcher и motivation wiring.
7. U-F: daemon orchestration.
8. U-G: corpus и long integration checks.

---

## 2. U-0 — Memory foundation + logging wiring

### U-0.1 — SQLite schema v2 migration

**Проблема:** текущая memory schema хранит semantic descriptions, но не хранит независимые claims, conflict pairs, material registry и chunk idempotence.

**Решение:**
- Добавить `SCHEMA_VERSION = 2`.
- Реализовать idempotent `_migrate_v1_to_v2()` в существующем storage/migration layer.
- Создать additive tables:
  - `claims`
  - `claim_conflicts`
  - `materials_registry`
  - `material_chunks`
- Добавить индексы для concept/status/source grouping и conflict status.
- Не делать backfill legacy `SemanticNode` rows в claims внутри этой migration.

**Файлы:**
- `brain/memory/storage.py`
- `brain/memory/migrate.py`
- новые/обновлённые migration tests в `tests/`

**Acceptance:**
- [x] Открытие v1 database создаёт все v2 tables.
- [x] Повторный запуск migration является no-op.
- [x] Existing semantic, episodic, source и procedural data остаются читаемыми.
- [x] `tests/test_storage_migration_v2.py` покрывает v1 -> v2 и repeated open.

---

### U-0.2 — Claim contracts и status enums

**Проблема:** `SemanticNode` не может представить несколько независимых, противоречащих, superseded или disputed claims об одном concept.

**Решение:**
- Добавить `Claim`, `ClaimStatus`, `ConflictStatus`, `EvidenceKind` и `ConflictPair`.
- Поля `Claim`:
  - `claim_id`
  - `concept`
  - `claim_text`
  - `claim_family_key`
  - `stance_key`
  - `source_ref`
  - `material_sha256`
  - `source_group_id`
  - `evidence_span`
  - `evidence_kind`
  - `confidence`
  - `status`
  - `supersedes`
  - `superseded_by`
  - `conflict_refs`
  - `created_ts`
  - `updated_ts`
  - `metadata`

**Файлы:**
- `brain/core/contracts.py`
- опционально `brain/memory/claim_store.py`

**Acceptance:**
- [x] Public names точно совпадают со spec: `ClaimStatus`, `ClaimStore`, `ConflictPair`, `EvidenceKind`.
- [x] Docs/comments для `RETRACTED` говорят false/manual/obsolete versioned only, а не timeout.
- [x] Serialization round-trip покрыт тестом, если contracts используют `to_dict()` / `from_dict()`.

---

### U-0.3 — `ClaimStore`

**Проблема:** conflict-aware memory требует claim-level CRUD и явный pair-level lifecycle.

**Решение:**
- Добавить `brain/memory/claim_store.py`.
- Реализовать:
  - `create()`
  - `get()`
  - `find_by_concept()`
  - `active_claims()`
  - `answerable_claims()`
  - `get_conflict_candidates()`
  - `get_disputed_pairs()`
  - `get_unverified()`
  - `set_status()`
  - `mark_disputed()`
  - `resolve()`
  - `retract()`
  - `count()`
- Сделать `create()` idempotent для идентичных `(concept, claim_text, source_ref)`.
- `active_claims()` должен возвращать только `ACTIVE`.
- `answerable_claims()` должен возвращать `ACTIVE + DISPUTED`.

**Файлы:**
- `brain/memory/claim_store.py`
- `brain/memory/memory_manager.py`
- `brain/memory/__init__.py`

**Acceptance:**
- [x] `ClaimStore.resolve()` предотвращает circular supersedes.
- [x] `claim_conflicts.status` меняется независимо от claim status.
- [x] `tests/test_claim_store.py` покрывает CRUD, status transitions, idempotent create, FK behavior, conflict pair APIs.

---

### U-0.4 — `claim_family_key` / `stance_key` normalizer

**Проблема:** majority нельзя считать по буквальному `claim_text`; paraphrases должны считаться одной стороной.

**Решение:**
- Добавить deterministic grouping helper для claims.
- MVP может стартовать с normalized templates:
  - numeric claims
  - negation markers
  - simple capacity/range patterns
  - fallback hash от normalized predicate text
- LLM может предлагать grouping только как `claim_llm_advice`; он не применяет status changes.

**Файлы:**
- `brain/core/text_utils.py`
- `brain/memory/claim_store.py`
- `brain/memory/conflict_guard.py` после старта U-B

**Acceptance:**
- [x] Paraphrases одного assertion имеют одинаковые `claim_family_key` и `stance_key`.
- [x] Opposite claims имеют одинаковый `claim_family_key`, но разные `stance_key`.
- [x] `tests/test_claim_stance_keys.py` покрывает paraphrase и contradiction fixtures.

---

### U-0.5 — `MaterialRegistry` и chunk idempotence

**Проблема:** `InputRouter._seen_hashes` живёт только в памяти процесса; после рестарта daemon снова ingest-ит файлы и дублирует claims.

**Решение:**
- Добавить `MaterialRegistry` wrapper над `materials_registry` и `material_chunks`.
- Отслеживать:
  - `sha256`
  - `path`
  - `size`
  - `mtime`
  - `ingest_status`
  - `chunk_count`
  - `claim_count`
  - `last_ingested_at`
  - `error_message`
- Отслеживать chunks по `(material_sha256, chunk_index)` и unique `(material_sha256, chunk_hash)`.

**Файлы:**
- `brain/memory/material_registry.py` или `brain/perception/material_registry.py`
- `brain/memory/storage.py`

**Acceptance:**
- [x] Re-ingesting уже обработанного material пишет duplicate skip и не создаёт claims.
- [x] Повторный `chunk_hash` не создаёт duplicate claims.
- [x] `failed` chunks retry-ятся до `max_chunk_retries = 3`.
- [x] `tests/test_material_registry.py` покрывает startup, resume, SHA256 idempotence, chunk-level resume.

---

### U-0.6 — Source trust root contract

**Проблема:** trust по `source_ref` делает страницы/чанки одного материала независимыми источниками.

**Решение:**
- Настроить использование source trust так, чтобы `SourceMemory.get_trust()` принимал `source_group_id`.
- Оставить `source_ref` как evidence/citation pointer.
- Для материалов: `source_group_id = material_sha256`.
- Для stdin/user/web: stable root-source IDs вроде `stdin:<session_id>`, `user:<id>`, `url:<normalized_doc_hash>`.

**Файлы:**
- `brain/memory/source_memory.py`
- `brain/memory/claim_store.py`
- `brain/memory/conflict_guard.py`
- `brain/output/dialogue_responder.py`

**Acceptance:**
- [x] Два `source_ref` из одного `source_group_id` не создают majority.
- [x] Conflict lifecycle и output layer вызывают `get_trust(source_group_id)`.
- [x] `tests/test_conflict_guard_slow.py` содержит same-source multi-page case.

---

### U-0.7 — `SemanticNode.description` как derived view

**Проблема:** существующая semantic memory должна продолжать работать, но новая claim memory не должна тихо смешивать disputed facts в обычные descriptions.

**Решение:**
- Оставить `SemanticMemory` и `SemanticNode` без breaking schema changes.
- Если по concept есть active claims, description строится из top active claims.
- Не включать `DISPUTED` claims в derived description.
- Использовать legacy `node.description` только как fallback.

**Файлы:**
- `brain/memory/semantic_memory.py`
- `brain/memory/memory_manager.py`

**Acceptance:**
- [x] Active claims влияют на description.
- [x] Disputed claims доступны output layer, но не попадают в ordinary description.
- [x] Legacy semantic-only data отвечает как раньше.

---

### U-0.8 — Logging wiring и claim lifecycle events

**Проблема:** новое поведение должно быть наблюдаемым до daemon mode; иначе conflict lifecycle невозможно тестировать и отлаживать.

**Решение:**
- Добавить claim lifecycle events в `BrainLogger` category map:
  - `claim_created`
  - `claim_conflict_candidate`
  - `claim_disputed`
  - `claim_conflict_dismissed`
  - `claim_resolved_by_trust`
  - `claim_resolved_by_majority`
  - `claim_resolved_by_recency`
  - `claim_resolution_timed_out`
  - `claim_superseded`
  - `claim_retracted`
  - `claim_llm_advice`
- Добавить material events:
  - `material_ingested`
  - `material_skipped_duplicate`
  - `material_skipped_busy`
  - `material_resumed`
- Убедиться, что `OutputPipeline` получает `brain_logger` из CLI paths.
- Исправить session/trace timing issues из spec.

**Файлы:**
- `brain/logging/brain_logger.py`
- `brain/cli.py`
- `brain/output/*`
- `brain/cognition/pipeline.py`
- `brain/memory/memory_manager.py`

**Acceptance:**
- [x] 0 log records с `session_id=""` в новых memory events.
- [x] `safety_audit.jsonl` создаётся при startup logger-а.
- [x] `claim_resolution_timed_out` содержит before/after confidence и verification goal ID.
- [x] Existing log tests проходят.

---

## 3. U-A — Scheduler recurring + budgets

### U-A.1 — `Scheduler.register_recurring`

**Проблема:** autonomous maintenance требует recurring tasks, но Scheduler пока не имеет recurring API.

**Решение:**
- Реализовать `RecurringTask`.
- Добавить `register_recurring(task_type, handler, every_n_ticks)`.
- Вызывать `_check_recurring()` в начале каждого tick.
- Не создавать duplicate pending recurring tasks одного `task_type`.

**Файлы:**
- `brain/core/scheduler.py`

**Acceptance:**
- [x] Tasks fire at expected ticks.
- [x] Несколько recurring tasks могут сосуществовать.
- [x] Duplicate due tasks не enqueue-ятся бесконечно.
- [x] `tests/test_scheduler_recurring.py` покрывает tick firing и multiple recurring tasks.

---

### U-A.2 — Scheduler ordering и LOW backlog

**Проблема:** idle work не должен задерживать user input, material ingestion или reconciliation.

**Решение:**
- Зафиксировать priority order: `HIGH -> NORMAL -> LOW`.
- Добавить `max_tasks_per_tick`.
- Добавить `max_low_queue_backlog = 8`.
- Вызывать `IdleDispatcher` только когда:
  - нет pending HIGH/NORMAL tasks
  - LOW backlog ниже `max_low_queue_backlog`

**Файлы:**
- `brain/core/scheduler.py`
- позже `brain/motivation/idle_dispatcher.py`

**Acceptance:**
- [x] HIGH/NORMAL tasks имеют приоритет над LOW/idle.
- [x] Idle не enqueue-ит задачи, когда LOW backlog уже 8 или больше.
- [x] `tests/test_scheduler_recurring.py` и `tests/test_idle_dispatcher.py` покрывают backlog behavior.

---

### U-A.3 — `LLMRateLimiter`

**Проблема:** LLM budget не должен жить внутри `IdleDispatcher`; ingestion, reconciliation и idle должны делить общий лимит.

**Решение:**
- Добавить `brain/bridges/llm_budget.py`.
- Реализовать:
  - `LLMRateLimitConfig(llm_calls_per_hour=20)`
  - `LLMRateLimiter.allow(purpose, now=None)`
  - `LLMRateLimiter.record(purpose, now=None)`
  - `LLMRateLimiter.remaining(now=None)`
- Все LLM users проверяют `allow()` перед вызовом и `record()` после реального вызова.

**Файлы:**
- `brain/bridges/llm_budget.py`
- `brain/bridges/__init__.py`

**Acceptance:**
- [x] Default `llm_calls_per_hour = 20`.
- [x] Ingestion деградирует до regex-only, когда budget исчерпан.
- [x] Conflict advice пропускается, когда budget исчерпан.
- [x] Idle не enqueue-ит LLM-dependent work, когда budget исчерпан.

---

## 4. U-B — Conflict lifecycle

### U-B.1 — `ConflictGuard` fast-path

**Проблема:** новые claims должны сразу помечаться suspicious, если cheap checks находят возможные contradictions.

**Решение:**
- Добавить `brain/memory/conflict_guard.py`.
- В `MemoryManager.store_fact()` / claim creation path запускать fast-check после `ClaimStore.create()`.
- Для same concept сравнивать top-K candidates (`K=3`) со статусами `ACTIVE`, `POSSIBLY_CONFLICTING`, `DISPUTED`.
- Использовать cheap existing contradiction checks:
  - negation markers
  - numeric divergence
- Если suspicious:
  - new claim -> `POSSIBLY_CONFLICTING`
  - old active claim -> `POSSIBLY_CONFLICTING`
  - pair -> `claim_conflicts.status="candidate"`
  - event -> `claim_conflict_candidate`
- Если clean:
  - claim -> `ACTIVE`
  - event -> `claim_created`

**Файлы:**
- `brain/memory/conflict_guard.py`
- `brain/cognition/contradiction_detector.py`
- `brain/memory/memory_manager.py`
- `brain/memory/claim_store.py`

**Acceptance:**
- [x] Fast-path создаёт `candidate`, а не `disputed`.
- [x] Intra-source contradictions разрешены, но не majority-resolve themselves.
- [x] `tests/test_conflict_guard_fast.py` покрывает negation, numeric divergence, K=3, intra-source behavior.

---

### U-B.2 — Slow-path candidate confirmation

**Проблема:** fast-path намеренно дешёвый и может давать false positives.

**Решение:**
- Добавить recurring handler `reconcile_disputed`.
- Обрабатывать `ClaimStore.get_conflict_candidates(limit=5)`.
- Повторять cheap checks.
- Опционально спрашивать LLM только classification:
  - `not_a_conflict`
  - `negation`
  - `numeric`
  - `paraphrase`
- Если false positive:
  - pair -> `DISMISSED`
  - `resolution="false_positive"`
  - claims возвращаются в `ACTIVE`, если у них нет других open pairs
  - event -> `claim_conflict_dismissed`
- Если confirmed:
  - pair -> `DISPUTED`
  - claims -> `DISPUTED`
  - event -> `claim_disputed`

**Файлы:**
- `brain/memory/conflict_guard.py`
- `brain/bridges/llm_bridge.py`
- `brain/bridges/llm_budget.py`

**Acceptance:**
- [x] `get_conflict_candidates()` и `get_disputed_pairs()` — отдельные APIs.
- [x] LLM advice создаёт `claim_llm_advice`, без status side effects.
- [x] False positive pairs становятся `DISMISSED`.

---

### U-B.3 — Deterministic dispute resolution

**Проблема:** после подтверждения конфликта resolution должен быть deterministic и auditable.

**Порядок решения:**
1. Trust:
   - сравнить `SourceMemory.get_trust(source_group_id)`
   - если gap >= `0.3`, winner становится `ACTIVE`, loser становится `SUPERSEDED`
   - event -> `claim_resolved_by_trust`
2. Majority:
   - считать unique `(concept, claim_family_key, stance_key, source_group_id)`
   - сторона с >=2 independent sources против 0..1 побеждает
   - event -> `claim_resolved_by_majority`
3. Recency:
   - только для `EvidenceKind.VERSIONED`
   - latest `created_ts` побеждает
   - event -> `claim_resolved_by_recency`
4. Hypothesis:
   - для timeless equal-trust/no-majority conflicts
   - оба остаются `DISPUTED`
   - создаётся verification goal
   - event -> `claim_verification_goal_created`

**Файлы:**
- `brain/memory/conflict_guard.py`
- `brain/cognition/hypothesis_engine.py`
- `brain/cognition/goal_manager.py`
- `brain/memory/source_memory.py`

**Acceptance:**
- [x] `TIMELESS` conflicts не resolve-ятся через `created_ts`.
- [x] Majority никогда не считает pages/chunks одного material как independent votes.
- [x] `tests/test_conflict_guard_slow.py` покрывает trust, majority, versioned recency, timeless hypothesis escalation.

---

### U-B.4 — TTL timeout без retract

**Проблема:** unresolved disputes не должны исчезать так, будто обе стороны false.

**Решение:**
- Добавить `conflict_ttl_ticks = 50`.
- При timeout:
  - оставить pair `status="disputed"`
  - оставить `resolution=NULL`
  - оставить оба claims `ClaimStatus.DISPUTED`
  - снизить confidence через `* 0.9`, floor `0.20`
  - refresh или create verification goal
  - event -> `claim_resolution_timed_out`

**Файлы:**
- `brain/memory/conflict_guard.py`
- `brain/cognition/goal_manager.py`
- `brain/logging/brain_logger.py`

**Acceptance:**
- [x] Timeout не вызывает `ClaimStore.retract()`.
- [x] Timeout не ставит `claim_conflicts.status="resolved"`.
- [x] `tests/test_conflict_guard_slow.py` покрывает TTL timeout без retract.

---

## 5. U-C — Material ingestion pipeline

### U-C.1 — `MaterialIngestor`

**Проблема:** `examples/ingest_material.py` — batch script; daemon нужен один reusable ingestion contract.

**Решение:**
- Добавить `brain/perception/material_ingestor.py`.
- Реализовать:
  - `ingest_path(path, session_id="")`
  - `resume_incomplete()`
- Использовать `InputRouter.route(path, force=True)` или bypass in-memory dedup.
- Persistent idempotence принадлежит `MaterialRegistry` / `material_chunks`.

**Файлы:**
- `brain/perception/material_ingestor.py`
- `brain/perception/input_router.py`
- `brain/memory/material_registry.py`
- `brain/memory/claim_store.py`

**Acceptance:**
- [x] Используется `force=True` или есть эквивалентный bypass in-memory dedup.
- [x] Startup scan и watcher вызывают один и тот же `MaterialIngestor.ingest_path()`.
- [x] `tests/test_material_ingestor.py` покрывает startup scan и idempotence.

---

### U-C.2 — Chunk retry/resume

**Проблема:** crash в середине PDF не должен терять progress или дублировать processed chunks.

**Решение:**
- Записывать chunks как `pending` до extraction.
- Помечать chunk `done` только после successful claim extraction/checking.
- После crash/restart resume-ить `pending` и retryable `failed` chunks.
- Retry failed chunks до `max_chunk_retries = 3`.
- Завершать material как:
  - `done`, если все chunks done
  - `failed`, если остались non-retryable failed chunks

**Файлы:**
- `brain/perception/material_ingestor.py`
- `brain/memory/material_registry.py`

**Acceptance:**
- [x] Повторный `chunk_hash` не создаёт duplicate claims.
- [x] Failed chunks не rollback-ят уже созданные claims.
- [x] Resume after crash покрыт тестом.

---

### U-C.3 — Regex + optional LLM extraction

**Проблема:** система должна учиться без LLM, но улучшать качество, если LLM доступен.

**Решение:**
- Regex extraction запускается всегда.
- Regex claims:
  - `confidence=0.60`
  - `metadata.extraction_method="regex"`
- LLM extraction запускается только если provider существует и `LLMRateLimiter.allow("ingest_extract")`.
- LLM claims:
  - `confidence=0.75`
  - `metadata.extraction_method="llm"`
  - `metadata.llm_model=...`
- Оба пути выставляют:
  - `source_group_id=material_sha256`
  - `claim_family_key`
  - `stance_key`
  - `metadata.chunk_hash`

**Файлы:**
- `brain/perception/material_ingestor.py`
- `brain/core/text_utils.py`
- `brain/bridges/llm_bridge.py`
- `brain/bridges/llm_budget.py`

**Acceptance:**
- [x] Ingestion работает offline regex-only.
- [x] LLM extraction уважает global rate limit.
- [x] LLM failure пишет warning и всё равно завершает chunk, если regex path succeeded.

---

### U-C.4 — `FileWatcher`

**Проблема:** daemon должен воспринимать новые файлы во время runtime.

**Решение:**
- Добавить polling-based `brain/perception/file_watcher.py`.
- Watch `materials/` или configured directory.
- Wait for stabilization:
  - `stabilization_checks = 3`
  - `stabilization_interval_s = 2.0`
  - `max_unstable_polls = 6`
- После стабилизации размера файла enqueue `ingest_file` task.
- Для unstable files писать `material_skipped_busy`.

**Файлы:**
- `brain/perception/file_watcher.py`
- `brain/core/scheduler.py`

**Acceptance:**
- [x] New files enqueue-ятся только после stabilization.
- [x] Busy/locked files не crash-ят daemon.
- [x] `tests/test_file_watcher.py` покрывает polling и FakeFS/stubbed filesystem.

---

## 6. U-D — Curiosity-driven idle

### U-D.1 — `IdleDispatcher`

**Проблема:** Motivation и curiosity уже есть, но пока не управляют тем, что система делает в idle.

**Решение:**
- Добавить `brain/motivation/idle_dispatcher.py`.
- Собирать candidates из:
  - `KnowledgeGapDetector`
  - `SemanticMemory.get_most_important(top_n=5)`
  - `ClaimStore.get_disputed_pairs(limit=10)`
- Ранжировать по:
  - `CuriosityEngine.score(concept)`
  - `MotivationState.preferred_goal_types`
- Создавать LOW tasks для:
  - gap filling
  - self reflection
  - dispute reconciliation

**Файлы:**
- `brain/motivation/idle_dispatcher.py`
- `brain/learning/knowledge_gap_detector.py`
- `brain/motivation/curiosity_engine.py`
- `brain/motivation/motivation_engine.py`
- `brain/core/scheduler.py`

**Acceptance:**
- [x] IdleDispatcher возвращает deterministic choices при fixed seed/config.
- [x] Empty candidate set логирует `idle_no_candidates`.
- [x] `tests/test_idle_dispatcher.py` покрывает ranking и no-candidate path.

---

### U-D.2 — Cooldowns и disputed-priority override

**Проблема:** idle не должен бесконечно крутиться вокруг одного concept, но unresolved conflicts должны иметь приоритет.

**Решение:**
- Добавить config:
  - `max_idle_tasks_per_tick = 3`
  - `cooldown_per_concept_ticks = 15`
  - `max_low_queue_backlog = 8`
- Если `ClaimStore.count(status=DISPUTED) > 0`, добавить `+1.0` bonus к reconcile candidates.
- Если `MotivationEngine.is_frustrated=True`, приоритизировать reconcile, потом gap; отключить reflect.

**Файлы:**
- `brain/motivation/idle_dispatcher.py`
- `brain/motivation/motivation_engine.py`
- `brain/core/scheduler.py`

**Acceptance:**
- [x] Cooldown запрещает repeated same-concept tasks на 15 ticks.
- [x] Disputed claims ранжируются выше reflect.
- [x] LOW backlog guard предотвращает idle queue inflation.

---

## 7. U-E — Output respecting disputed claims

### U-E.1 — Claim-aware retrieval pass-through

**Проблема:** output не может hedge-ить, если получает только semantic node IDs/strings.

**Решение:**
- Добавить `ClaimRef`.
- Изменить `CognitiveResult.memory_refs` на `List[ClaimRef]`.
- Обогатить `MemorySearchResult`:
  - `active_claims`
  - `answerable_claims`
- Протянуть claim-aware evidence через `Reasoner`, `HypothesisEngine` и pipeline context.

**Файлы:**
- `brain/core/contracts.py`
- `brain/memory/memory_manager.py`
- `brain/cognition/retrieval_adapter.py`
- `brain/cognition/reasoner.py`
- `brain/cognition/hypothesis_engine.py`
- `brain/cognition/pipeline.py`

**Acceptance:**
- [x] Output layer видит disputed claim IDs, text, source refs, source group IDs, confidence, conflict refs.
- [x] Existing simple query flow работает с legacy semantic fallback.

---

### U-E.2 — Hedged `DialogueResponder`

**Проблема:** если memory содержит unresolved conflicts, ответ должен показывать неопределённость, а не выдавать одну сторону как settled.

**Решение:**
- В `DialogueResponder` группировать disputed `ClaimRef`s по concept.
- Если concept имеет как минимум два disputed claims, формировать hedged response:
  - показать оба claim texts
  - показать `source_ref`
  - показать trust из `SourceMemory.get_trust(source_group_id)`
  - явно сказать, что conflict unresolved
- Оставить ordinary answer path для non-disputed results.

**Файлы:**
- `brain/output/dialogue_responder.py`
- `brain/memory/source_memory.py`

**Acceptance:**
- [x] Trust lookup использует `source_group_id`.
- [x] Disputed claims не смешиваются в ordinary prose.
- [x] `tests/test_output_hedged_dispute.py` проверяет, что disputed >= 2 даёт hedged text.

---

### U-E.3 — `ValidationResult.reasons`

**Проблема:** `respond_hedged_due_to_dispute` должен быть реальным contract, а не undocumented metadata convention.

**Решение:**
- Расширить `ValidationResult` через `reasons: List[str]` или formal `metadata["reason"]`.
- Предпочтительно явное `reasons: List[str]`, если это не ломает существующий код слишком сильно.
- Добавить reason `respond_hedged_due_to_dispute`.
- Убедиться, что final log всё ещё может писать `decision.reason="dispute"`.

**Файлы:**
- `brain/output/response_validator.py`
- `brain/output/dialogue_responder.py`
- `brain/logging/brain_logger.py`

**Acceptance:**
- [x] Hedged disputed output добавляет `respond_hedged_due_to_dispute`.
- [x] Existing validation behavior остаётся compatible.

---

## 8. U-F — Daemon mode + stdin

### U-F.1 — `DaemonConfig` и CLI flags

**Проблема:** `--autonomous --ticks` конечный и больше подходит для тестов; проекту нужен long-running daemon.

**Решение:**
- Добавить `DaemonConfig` с defaults:
  - `reconcile_every_ticks = 10`
  - `replay_every_ticks = 50`
  - `consolidate_every_ticks = 100`
  - `self_reflect_every_ticks = 20`
  - `llm_calls_per_hour = 20`
- Добавить CLI flags:
  - `--daemon`
  - `--materials DIR`
  - `--watch` / `--no-watch`
  - `--stdin`

**Файлы:**
- `brain/cli.py`
- `brain/core/contracts.py`, если config будет там

**Acceptance:**
- [x] Existing `--autonomous --ticks` всё ещё работает.
- [x] `--daemon --materials materials --watch --stdin` парсится и запускает нужные components.

---

### U-F.2 — Daemon orchestration loop

**Проблема:** components нужно связать в один process с graceful shutdown.

**Решение:**
- Реализовать daemon run loop:
  - initialize memory и v2 stores
  - создать shared `LLMRateLimiter`
  - register recurring tasks
  - startup scan materials, если configured
  - start watcher, если enabled
  - start stdin thread, если enabled
  - tick scheduler до SIGINT/SIGTERM
  - stop watcher/thread gracefully
  - save memory и close DB

**Файлы:**
- `brain/cli.py`
- `brain/core/scheduler.py`
- `brain/perception/material_ingestor.py`
- `brain/perception/file_watcher.py`

**Acceptance:**
- [x] Ctrl+C сохраняет и закрывает DB.
- [x] Daemon может работать без materials.
- [x] Daemon может работать без LLM.
- [x] Long-running smoke test не показывает очевидных resource leaks.

---

### U-F.3 — Stdin reader

**Проблема:** user queries должны попадать в running daemon без restart process.

**Решение:**
- Добавить daemon thread, читающий `sys.stdin`.
- Каждая непустая строка enqueue-ит `Task(type="cognitive_cycle", priority=HIGH)`.
- EOF завершает stdin thread, но daemon продолжает работать через watcher/idle.

**Файлы:**
- `brain/cli.py`

**Acceptance:**
- [x] User query попадает в HIGH queue.
- [x] EOF не завершает daemon.
- [x] HIGH stdin task имеет приоритет над idle LOW backlog.

---

## 9. U-G — Conflict corpus + integration tests

### U-G.1 — Controlled conflict fixtures

**Проблема:** conflict lifecycle требует deterministic fixtures, а не случайные contradictions из больших PDF.

**Решение:**
- Добавить `tests/fixtures/conflicts/`:
  - `high_trust/topology.md`
  - `mid_trust_a/cognitive_basics.md`
  - `mid_trust_b/neuro_update.md`
  - `low_trust/blog_post.md`
- Закодировать working-memory conflict:
  - A: `7±2`
  - paraphrase A: `7`
  - B: `4±1`
  - noise: unrelated/low-trust claim

**Файлы:**
- `tests/fixtures/conflicts/**`

**Acceptance:**
- [x] A claims имеют одинаковые `claim_family_key` и `stance_key=A`.
- [x] B claim имеет тот же family, но `stance_key=B`.
- [x] Fixture sources имеют distinct `source_group_id`.

---

### U-G.2 — End-to-end conflict lifecycle test

**Проблема:** unit tests недостаточно; главное обещание системы — lifecycle behavior.

**Решение:**
- Добавить integration test:
  1. Ingest всех conflict fixtures.
  2. Fast path пишет `claim_conflict_candidate`.
  3. Slow path пишет `claim_disputed`.
  4. Majority resolves A over B.
  5. Loser становится `SUPERSEDED`.
  6. Output references the winner normally.
- Добавить отдельный unresolved fixture для TTL:
  - equal trust
  - no majority
  - timeless
  - после TTL остаётся disputed и hedged.

**Файлы:**
- `tests/test_daemon_integration.py`
- `tests/test_conflict_guard_slow.py`
- `tests/test_output_hedged_dispute.py`

**Acceptance:**
- [x] `claim_resolved_by_majority` появляется в пределах <=20 ticks для majority fixture.
- [x] `claim_resolution_timed_out` появляется для unresolved fixture без retract.
- [x] Hedged output упоминает оба sources для unresolved disputed concept.

---

## 10. Cross-cutting acceptance checks

Запускать после каждого крупного stage, адаптируя под уже существующие tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_claim_store.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_storage_migration_v2.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_conflict_guard_fast.py tests\test_conflict_guard_slow.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_material_registry.py tests\test_material_ingestor.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_idle_dispatcher.py tests\test_scheduler_recurring.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_output_hedged_dispute.py tests\test_daemon_integration.py -q
.\.venv\Scripts\python.exe -m pytest tests\ --cov=brain --cov-fail-under=70
```

Manual smoke после U-F:

```powershell
.\.venv\Scripts\cognitive-core.exe --daemon `
  --data-dir brain\data\memory `
  --materials materials `
  --watch `
  --stdin `
  --llm-provider blackbox `
  --llm-model "blackboxai/anthropic/claude-sonnet-4.6" `
  --log-dir brain\data\logs `
  --log-level INFO
```

Ожидаемые наблюдаемые результаты:

- Новый материал, положенный в `materials/`, создаёт `material_ingested`.
- Новые claims появляются в SQLite без duplicate chunks после restart.
- Conflict corpus создаёт `claim_conflict_candidate`, `claim_disputed` и либо `claim_resolved_by_majority`, либо `claim_resolution_timed_out`.
- Нет новых records в `memory.jsonl` с `session_id=""`.
- Существуют `perception.jsonl`, `safety_audit.jsonl` и `motivation.jsonl`.

---

## 11. Deferred work

Не включать в первый implementation pass:

- Legacy backfill `SemanticNode -> Claim`.
- IPC / Unix socket / Named Pipe server.
- Multi-process architecture.
- Persistent scheduler queue.
- Web dashboard.
- LLM fact-verification as judge.
- Active learning loop, где система сама спрашивает пользователя для resolution disputes.
- Manual UI/CLI для retract и trust override.

---

## 12. Definition of done

Update считается завершённым, когда:

- [ ] `cognitive-core --daemon` работает больше 4 часов без manual intervention.
- [x] Добавление supported file в `materials/` создаёт claims в пределах 2 минут.
- [x] Ingested material idempotent across daemon restarts.
- [x] Contradictory facts становятся `DISPUTED`, а не тихо merge-ятся в `SemanticNode.description`.
- [x] Majority resolution работает по `(claim_family_key, stance_key, source_group_id)`.
- [x] Timeout пишет `claim_resolution_timed_out` и не retract-ит unresolved claims.
- [x] Вопросы о unresolved concepts дают hedged output с обоими sources.
- [x] Coverage остаётся не ниже 70%.
- [x] Public names из spec существуют и совпадают точно:
  - `ClaimStatus`
  - `ClaimStore`
  - `MaterialRegistry`
  - `MaterialIngestor`
  - `ConflictGuard`
  - `IdleDispatcher`
  - `LLMRateLimiter`
