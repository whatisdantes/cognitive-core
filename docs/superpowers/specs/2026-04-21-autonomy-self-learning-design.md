# Design: Cognitive-Core — Autonomy & Self-Learning

**Дата:** 2026-04-21
**Версия проекта на момент дизайна:** cognitive-core v0.7.0
**Автор:** brainstorming-сессия (пользователь + Claude Opus 4.7), ревью: OpenAI Codex (2 раунда)
**Статус:** approved → готов к декомпозиции в [`planning/UPDATE_TODO.md`](../../planning/UPDATE_TODO.md)

---

## 1. Контекст и проблема

Cognitive-core v0.7.0 закрыл этапы A–M (см. `docs/planning/TODO.md`), но декларированная цель «артификальный мозг, который живёт и учится» выполнена лишь инфраструктурно. В реальности:

- `--autonomous --ticks N` завершается после фиксированного списка предустановленных вопросов (`brain/cli.py:_AUTONOMOUS_QUERIES`).
- `KnowledgeGapDetector`, `CuriosityEngine`, `MotivationEngine`, `ReplayEngine` реализованы, но не управляют поведением: idle-активность отсутствует.
- `SemanticMemory.store_fact()` при совпадении concept-а **тихо мёржит** описание и повышает confidence — т.е. конфликтующий факт затирает предыдущий. Модель сомнения в знаниях отсутствует на уровне данных.
- `ContradictionDetector` проверяет evidence **внутри одной retrieval-выдачи**, а не «новый факт vs существующая память».
- `InputRouter` умеет SHA256-дедупликацию только в одном процессе (`_seen_hashes: Set[str]`). Persistent registry для материала отсутствует.
- `ingest_material.py` — отдельный batch-script, не вплетённый в жизненный цикл.
- `materials/` содержит два PDF, но без реального механизма их живой обработки.

Анализ логов (см. предыдущий отчёт от 2026-04-21) выявил дополнительные системные пробелы: 0 WARN/ERROR за 2 часа работы, 35% refuse-ответов без объяснения, `memory.jsonl` без `session_id`, `cycle_start` с пустыми идентификаторами.

## 2. Цели и не-цели

### 2.1. Цели

1. **Автономность (daemon-режим):** один Python-процесс работает до явной остановки. В idle сам генерирует цели. Принимает внешний ввод через stdin и файловый watcher без перезапуска.
2. **Самообучение на материале:** материалы из `materials/` автоматически попадают в память (startup-scan + runtime-watcher), извлечение устойчивых claim-ов идёт через regex + опциональный LLM. Ingestion идемпотентен и устойчив к крэшам.
3. **Проверка памяти:** при появлении нового claim-а по уже известному concept-у система обнаруживает возможный конфликт.
4. **Сомнение при конфликте:** конфликтующие claim-ы переходят в состояние `disputed`; резолюция делается **детерминированной** логикой (source trust → majority → evidence_kind) с опциональной LLM-классификацией как advice. Неразрешённые конфликты влияют на ответы системы (hedged).

### 2.2. Не-цели

- Multi-process / распределённая архитектура (`F-AUTO-12` остаётся post-MVP).
- Persistent scheduler queue (`F-AUTO-13` остаётся post-MVP).
- HTTP/web dashboard (`F-AUTO-14` остаётся post-MVP).
- Замена `SemanticMemory` на новую модель одним шагом — claims добавляются **рядом** (см. §5.1).
- Миграция существующих SemanticNode в claim-формат — опциональная отдельная задача (U-0.7), не блокирует основные этапы.
- LLM как источник истины — LLM используется только как extractor и advisor; решения о статусе claim принимает детерминированная логика.

## 3. Обзор архитектуры

Daemon живёт в одном процессе и состоит из трёх петель, соединённых существующим `EventBus`:

```
┌─────────────── Perception loop ───────────────┐
│  materials/ ──(startup scan + polling watch)─►│
│  MaterialIngestor → InputRouter → PerceptEvents│
│  stdin reader ────────────────────────────────┤
└────────────────────┬───────────────────────────┘
                     │ fast-path: possibly_conflicting?
                     ▼ claim_created | claim_conflict_candidate
┌────────────── Cognitive loop ─────────────────┐
│  Scheduler.tick → CognitivePipeline (20 шагов)│
│  IdleDispatcher (curiosity-driven) ─► LOW task│
│  recurring reconcile_disputed (slow-path)     │
└────────────────────┬───────────────────────────┘
                     │ CognitiveResult (ClaimRef-aware)
                     ▼ claim_disputed | claim_superseded | ...
┌────────── Learning / Motivation loop ─────────┐
│  OnlineLearner.update() (existing)            │
│  RewardEngine.signal() → MotivationEngine     │
│  ReplayEngine (recurring)                     │
│  HypothesisEngine.generate_from_dispute       │
└────────────────────────────────────────────────┘
```

Точек запуска две: новый `cognitive-core --daemon` (бесконечный, до Ctrl+C) и существующий `cognitive-core --autonomous --ticks N` (сохраняется для CI и бенчмарков).

## 4. Основной дизайн-выбор (зафиксировано в brainstorming)

| № | Выбор | Значение |
|---|---|---|
| 1 | Глубина автономии | Daemon-режим (B): один процесс, stdin + watcher + recurring |
| 2 | Belief revision | D (B+C): evidence-weighted с fallback на hypothesis-driven |
| 3 | Conflict check | Hybrid: fast-path на store + slow-path в recurring |
| 4 | Idle-активность | Curiosity-driven: `MotivationEngine` ранжирует кандидатов |
| 5 | Материал | Startup scan + runtime watcher через единый `MaterialIngestor` |
| 6 | Извлечение фактов | Regex всегда + LLM опционально; LLM — extractor, не судья |
| 7 | Формат плана | Hybrid: roadmap-шапка + детальные U-AUTO-* блоки |

## 5. Модель данных

### 5.1. `Claim` — новая первичная единица знания

```python
@dataclass
class Claim:
    claim_id: str                          # uuid4().hex[:16]
    concept: str                           # нормализованный (строчный, trim)
    claim_text: str                        # полное утверждение (до 500 символов)
    claim_family_key: str                  # семейство утверждений для conflict/majority grouping
    stance_key: str                        # каноническая сторона внутри семейства
    source_ref: str                        # "pdf#p12" / "stdin#session_01" / "material:abc123#chunk_42"
    material_sha256: Optional[str]         # FK в MaterialRegistry; None для non-material claims
    source_group_id: str                   # независимый root-source для majority; material_sha256 для файлов
    evidence_span: Optional[Tuple[int, int]]   # (offset, length) в исходном чанке
    evidence_kind: EvidenceKind            # timeless | versioned | opinion
    confidence: float                      # [0.0, 1.0]
    status: ClaimStatus                    # см. статус-граф ниже
    supersedes: Optional[str]              # claim_id, который этот claim заменил
    superseded_by: Optional[str]           # claim_id, который заменил этот
    conflict_refs: List[str]               # claim_ids в конфликте
    created_ts: float
    updated_ts: float
    metadata: Dict[str, Any]               # extraction_method, llm_model, и т.п.

class ClaimStatus(str, Enum):
    UNVERIFIED = "unverified"              # свежий, fast-check ещё не отработал
    ACTIVE = "active"                      # fast-check прошёл, конфликтов не найдено
    POSSIBLY_CONFLICTING = "possibly_conflicting"  # fast-check нашёл кандидатов
    DISPUTED = "disputed"                  # slow-path подтвердил конфликт, ждёт resolution
    SUPERSEDED = "superseded"              # проиграл по trust/majority; сохраняем для аудита
    RETRACTED = "retracted"                # доказанно ложный / ручной retract / obsolete versioned

class EvidenceKind(str, Enum):
    TIMELESS = "timeless"                  # учебное знание; latest_wins НЕ применяется
    VERSIONED = "versioned"                # курс валют, версия API; latest_wins применяется
    OPINION = "opinion"                    # мнение, не факт; только hedged-ответы

class ConflictStatus(str, Enum):
    CANDIDATE = "candidate"                # fast-path нашёл возможное противоречие
    DISPUTED = "disputed"                  # slow-path подтвердил конфликт
    RESOLVED = "resolved"                  # одна сторона superseded/retracted или конфликт снят
    DISMISSED = "dismissed"                # slow-path признал candidate false positive
```

**Статус-граф:**

```
unverified ──fast-check──► active
           \
            ──fast-check──► possibly_conflicting ──slow-reconcile──► disputed
                                                                      │
                                        ┌─────────────────────────────┤
                                        ▼                             ▼
                                  superseded                   active (false conflict)
                                                                      │
                                                                      ▼
                                                                 retracted (false / manual / obsolete versioned)
```

`ClaimStatus.POSSIBLY_CONFLICTING` относится к самому claim-у: он участвует в паре, которую fast-path считает подозрительной. Статус пары живёт отдельно в `claim_conflicts.status`: `candidate` до slow-check, `disputed` после подтверждения, `dismissed` при false positive, `resolved` после resolution. Это разделение запрещает трактовать каждый `possibly_conflicting` claim как уже доказанный конфликт.

`claim_family_key` и `stance_key` нужны, чтобы majority-resolution не зависел от буквального текста. Например, «рабочая память содержит 7±2 элементов» и «рабочая память оперирует примерно семью элементами» получают один `claim_family_key` и один `stance_key`, а противоположное утверждение «рабочая память содержит 4±1 элемента» — тот же `claim_family_key`, но другой `stance_key`.

### 5.2. `ClaimStore` — новая таблица

SQLite в той же базе `brain/data/memory/memory.db`:

```sql
CREATE TABLE claims (
    claim_id TEXT PRIMARY KEY,
    concept TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_family_key TEXT NOT NULL,
    stance_key TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    material_sha256 TEXT,
    source_group_id TEXT NOT NULL,
    evidence_span_offset INTEGER,
    evidence_span_length INTEGER,
    evidence_kind TEXT NOT NULL DEFAULT 'timeless',
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    supersedes TEXT,
    superseded_by TEXT,
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY (material_sha256) REFERENCES materials_registry(sha256),
    FOREIGN KEY (supersedes) REFERENCES claims(claim_id),
    FOREIGN KEY (superseded_by) REFERENCES claims(claim_id)
);

CREATE INDEX idx_claims_concept ON claims(concept);
CREATE INDEX idx_claims_status ON claims(status);
CREATE INDEX idx_claims_material ON claims(material_sha256);
CREATE INDEX idx_claims_source_group ON claims(source_group_id);
CREATE INDEX idx_claims_family ON claims(concept, claim_family_key);
CREATE INDEX idx_claims_stance ON claims(concept, claim_family_key, stance_key);
CREATE UNIQUE INDEX idx_claims_unique_source
    ON claims(concept, claim_text, source_ref);

CREATE TABLE claim_conflicts (
    claim_id_a TEXT NOT NULL,
    claim_id_b TEXT NOT NULL,
    detected_ts REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate', -- candidate|disputed|resolved|dismissed
    resolution TEXT,                       -- null пока не resolved/dismissed, потом trust|majority|recency|false_positive
    resolved_ts REAL,
    PRIMARY KEY (claim_id_a, claim_id_b),
    FOREIGN KEY (claim_id_a) REFERENCES claims(claim_id),
    FOREIGN KEY (claim_id_b) REFERENCES claims(claim_id)
);

CREATE INDEX idx_claim_conflicts_status ON claim_conflicts(status);
```

Эти schema changes применяются через additive SQLite migration `SCHEMA_VERSION = 2`, описанную в §16.1. Legacy backfill `SemanticNode → Claim` в эту миграцию не входит.

`ClaimStore` — новый класс в `brain/memory/claim_store.py`. API:

```python
class ClaimStore:
    def create(self, claim: Claim) -> Claim
    def get(self, claim_id: str) -> Optional[Claim]
    def find_by_concept(self, concept: str, status: Optional[ClaimStatus] = None) -> List[Claim]
    def active_claims(self, concept: str) -> List[Claim]           # только status=active
    def answerable_claims(self, concept: str) -> List[Claim]       # status IN (active, disputed)
    def get_conflict_candidates(self, limit: int = 10) -> List[ConflictPair]
    def get_disputed_pairs(self, limit: int = 10) -> List[ConflictPair]
    def get_unverified(self, limit: int = 50) -> List[Claim]
    def set_status(self, claim_id: str, status: ClaimStatus, reason: str = "") -> None
    def mark_disputed(self, claim_a_id: str, claim_b_id: str) -> None
    def resolve(self, winner_id: str, loser_id: str, resolution: str) -> None
    def retract(self, claim_id: str, reason: str) -> None
    def count(self, status: Optional[ClaimStatus] = None) -> int
```

`ConflictPair` — lightweight DTO из `claim_conflicts` + двух claims: `.a`, `.b`, `.status`, `.detected_ts`, `.resolution`. Это не отдельная таблица и не новая единица знания; он нужен, чтобы slow-path и data-flow работали с теми же статусами, что описаны в `claim_conflicts`.

`active_claims()` намеренно не возвращает `disputed`: агрегированное описание концепта строится только из подтверждённых активных утверждений. `answerable_claims()` используется retrieval/output-слоем, чтобы disputed-claim-ы можно было показать как конфликт, а не смешать с обычным ответом.

### 5.3. `MaterialRegistry` и `material_chunks`

Идемпотентность ingestion даже при крэше посреди обработки PDF:

```sql
CREATE TABLE materials_registry (
    sha256 TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    ingest_status TEXT NOT NULL,           -- pending | in_progress | done | failed
    chunk_count INTEGER NOT NULL DEFAULT 0,
    claim_count INTEGER NOT NULL DEFAULT 0,
    last_ingested_at REAL,
    error_message TEXT
);

CREATE TABLE material_chunks (
    material_sha256 TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_hash TEXT NOT NULL,
    source_ref TEXT NOT NULL,              -- "material:abc123#chunk_42"
    status TEXT NOT NULL,                  -- pending | done | failed
    claim_count INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    processed_ts REAL,
    error_message TEXT,
    PRIMARY KEY (material_sha256, chunk_index),
    FOREIGN KEY (material_sha256) REFERENCES materials_registry(sha256)
);

CREATE INDEX idx_chunks_pending ON material_chunks(material_sha256, status)
    WHERE status = 'pending';
CREATE UNIQUE INDEX idx_chunks_hash ON material_chunks(material_sha256, chunk_hash);
```

**Идемпотентность:**
- На старте ingestion материала создаётся запись в `materials_registry` со статусом `in_progress`.
- Чанки записываются в `material_chunks` сразу со статусом `pending`.
- Повторный `chunk_hash` внутри того же `material_sha256` не создаёт новые claims: существующий `done` chunk пропускается, `pending/failed` chunk резюмируется.
- По мере обработки чанка (regex-extract + fast-check) его статус становится `done`.
- Если процесс падает, при рестарте `MaterialIngestor` видит `in_progress` + наличие `pending`/`failed` чанков → продолжает с них. `failed` чанки ретраятся до `max_chunk_retries=3`, затем остаются `failed`, но не блокируют уже обработанные чанки.
- `materials_registry.ingest_status` становится `done`, когда все чанки `done`.

### 5.4. `SemanticNode.description` как derived view

`SemanticMemory` и `SemanticNode` **остаются без ломающих изменений**. При наличии active claims по concept-у `SemanticNode.description` рассчитывается как производное:

```python
def get_description(node: SemanticNode, claim_store: ClaimStore) -> str:
    active = claim_store.active_claims(node.concept)
    if active:
        # Берём 3 верхних по confidence
        top = sorted(active, key=lambda c: -c.confidence)[:3]
        return "; ".join(c.claim_text for c in top)
    return node.description  # legacy fallback
```

`DISPUTED` claims в derived description не входят: они прокидываются в retrieval/output через `answerable_claims()` и отображаются как конфликт. Это предотвращает ситуацию, где спорное утверждение тихо становится обычным описанием concept-а.

Миграция legacy SemanticNode в claims (`U-0.7`) — опциональная задача с низким приоритетом, сначала делать её не нужно.

## 6. Детали компонентов

### 6.1. `ConflictGuard` (`brain/memory/conflict_guard.py`)

Две точки входа:

**Fast-path** (вызывается в `MemoryManager.store_fact()` → `ClaimStore.create()`):
1. Нормализовать concept.
2. `ClaimStore.find_by_concept(concept, status IN (active, possibly_conflicting, disputed))`.
3. Для top-K (K=3) кандидатов запустить **простые** проверки из существующего `ContradictionDetector`: negation-markers + numeric-divergence. Semantics-check НЕ делается здесь.
4. Если есть хотя бы один потенциально конфликтующий кандидат → новый claim получает `status=possibly_conflicting`, старый тоже переводится в `possibly_conflicting` (если был `active`), создаётся запись в `claim_conflicts(status="candidate")`, событие `claim_conflict_candidate`.
5. Иначе → новый claim `status=active`, событие `claim_created`.

**Slow-path** (recurring task `reconcile_disputed`, по умолчанию каждые 10 тиков):
1. `ClaimStore.get_conflict_candidates(limit=5)` — пары из `claim_conflicts(status="candidate")`.
2. Для каждой candidate-пары:
   - Повторить cheap checks и, если доступен LLM advisor, запросить только классификацию `not_a_conflict | negation | numeric | paraphrase` без side effects.
   - Если slow-path не подтверждает конфликт → `claim_conflicts.status="dismissed"`, `resolution="false_positive"`, оба claim-а возвращаются в `active`, если у них нет других candidate/disputed пар. Событие `claim_conflict_dismissed`.
   - Если конфликт подтверждён → `claim_conflicts.status="disputed"`, оба claim-а получают `status=disputed`, событие `claim_disputed`.
3. `ClaimStore.get_disputed_pairs(limit=5)` — пары из `claim_conflicts(status="disputed")`.
4. Для каждой disputed-пары:
   - Получить `trust_a`, `trust_b` через `SourceMemory.get_trust(pair.a.source_group_id)` и `SourceMemory.get_trust(pair.b.source_group_id)`. `source_ref` остаётся citation/evidence pointer и не используется как trust-root.
   - Если `|trust_a - trust_b| ≥ 0.3` → **trust-resolution**: `winner=max, loser=min`. `ClaimStore.resolve(winner, loser, "trust")`. Событие `claim_resolved_by_trust`.
   - Иначе — majority: `COUNT(DISTINCT source_group_id) WHERE concept=X AND claim_family_key=pair.a.claim_family_key AND stance_key=side AND status IN (active, disputed)`. Голос считается по уникальному `(concept, claim_family_key, stance_key, source_group_id)`, поэтому перефразированные claims из одного источника не дают дополнительных голосов. Если одна сторона имеет ≥2 независимых `source_group_id` и другая — 0 или 1 → **majority-resolution**. Событие `claim_resolved_by_majority`.
   - Иначе, если `evidence_kind = versioned` и оба claim-а versioned → **latest-wins**: winner — с большим `created_ts`. Событие `claim_resolved_by_recency`.
   - Иначе (timeless без majority, равные trust) → создать `HypothesisGoal` через `HypothesisEngine.generate_from_dispute(a, b)`, оставить оба в `disputed`. Событие `claim_verification_goal_created`.
5. TTL: если disputed-pair провисела более `conflict_ttl_ticks` (по умолчанию 50), timeout **не retract-ит** claims и не помечает конфликт `resolved`. Пара остаётся `claim_conflicts.status="disputed"`, `resolution=NULL`; оба claim-а остаются `ClaimStatus.DISPUTED`, confidence мягко понижается (`confidence *= 0.9`, но не ниже `0.20`), verification goal обновляется/перепланируется. Событие `claim_resolution_timed_out`.

`source_group_id` — единица независимого свидетельства для majority. Для материалов это `material_sha256`; для stdin/user/web это root-source id (`stdin:<session_id>`, `user:<id>`, `url:<normalized_host_or_doc_hash>`). Страницы одного PDF (`#p1`, `#p2`) и чанки одного файла не считаются независимыми голосами и не могут победить majority сами себя. `created_ts` не используется как tie-breaker для `EvidenceKind.TIMELESS`: если trust и majority не разрешили конфликт, он остаётся `disputed`.

`ClaimStatus.RETRACTED` используется только для доказанно ложных claims, ручного retract или устаревших `EvidenceKind.VERSIONED` claims, когда новое versioned-утверждение явно заменяет старое. Неразрешённый timeless-конфликт не является доказательством ложности.

**LLM advisor** (опциональная ветка, вызывается только если `llm_provider` доступен):
- Для disputed-пары запрашивается классификация: `{conflict_type: "negation" | "numeric" | "paraphrase" | "not_a_conflict", reasoning: str}`.
- Результат пишется как событие `claim_llm_advice` с полями `{claim_id_a, claim_id_b, advice, model, reasoning}`.
- **Никаких side-effects.** `ClaimStore` не меняется на основе LLM-вывода. Advice существует только для аудита и будущего ручного review.

### 6.2. `MaterialIngestor` (`brain/perception/material_ingestor.py`)

Единый контракт для startup-scan и watcher-runtime:

```python
class MaterialIngestor:
    def __init__(
        self,
        memory: MemoryManager,
        claim_store: ClaimStore,
        material_registry: MaterialRegistry,
        router: InputRouter,
        llm_extractor: Optional[LLMProvider] = None,
        llm_rate_limiter: Optional[LLMRateLimiter] = None,
        brain_logger: Optional[BrainLogger] = None,
    ): ...

    def ingest_path(self, path: Path, session_id: str = "") -> IngestReport:
        """Обработать один файл. Идемпотентен: уже обработанные sha256 пропускает.
        При наличии pending chunks — резюмирует с первого pending."""

    def resume_incomplete(self) -> List[IngestReport]:
        """На старте daemon: найти все materials_registry со status=in_progress
        и резюмировать обработку."""
```

**Поток одного файла:**
1. Вычислить `sha256`, проверить `MaterialRegistry`:
   - `ingest_status = done` → пропустить, событие `material_skipped_duplicate`.
   - `ingest_status = in_progress` → резюмировать с `pending`/`failed` чанков.
   - Нет записи → создать с `in_progress`, продолжить.
2. Через `InputRouter.route(path, force=True)` получить `PerceptEvent`s (существующий механизм, chunked). `force=True` обязателен: in-memory `_seen_hashes` в `InputRouter` не является источником истины для daemon-idempotence, за неё отвечают `MaterialRegistry` и `material_chunks`.
3. Записать все новые чанки в `material_chunks` со `status=pending`; если `(material_sha256, chunk_hash)` уже есть:
   - `done` → chunk пропускается;
   - `pending`/`failed` → chunk ставится в resume-очередь без создания duplicate claims.
4. Для каждого `pending` или retryable `failed` чанка:
   - Regex-extract → создать claim (`confidence=0.60`, `evidence_kind=timeless` по умолчанию, `source_group_id=material_sha256`, `claim_family_key`/`stance_key` из deterministic normalizer-а, `metadata.extraction_method="regex"`, `metadata.chunk_hash=...`).
   - `ClaimStore.create(claim)` → `ConflictGuard.fast_check` встроен.
   - Если `llm_extractor` доступен и `LLMRateLimiter.allow("ingest_extract")` вернул true:
     - Запрос к LLM на извлечение 3–5 claim-ов.
     - Для каждого LLM-claim-а: `confidence=0.75`, `source_group_id=material_sha256`, `claim_family_key`/`stance_key` из deterministic normalizer-а, `metadata.extraction_method="llm"`, `metadata.llm_model=...`, `metadata.chunk_hash=...`.
     - `ClaimStore.create()` — та же fast-check логика.
   - `material_chunks[chunk_index].status = done`.
   - При ошибке chunk-а: `retry_count += 1`, `status=failed`, `error_message=...`. До `max_chunk_retries=3` такой chunk считается retryable при `resume_incomplete()`.
5. Когда все чанки `done` или исчерпали retry как `failed` → `materials_registry.ingest_status = done` при нуле failed, иначе `failed` с `error_message` summary. Уже созданные claims не откатываются.

### 6.3. `FileWatcher` (`brain/perception/file_watcher.py`)

Polling-based, без `watchdog`:

```python
class FileWatcher:
    def __init__(
        self,
        watch_dir: Path,
        ingestor: MaterialIngestor,
        scheduler: Scheduler,
        poll_interval_s: float = 5.0,
        stabilization_checks: int = 3,
        stabilization_interval_s: float = 2.0,
        brain_logger: Optional[BrainLogger] = None,
    ): ...

    def start(self): ...                   # daemon thread
    def stop(self): ...
```

**Wait-for-stabilization:** перед тем как поставить `ingest_file` task в Scheduler, FileWatcher делает `stabilization_checks` чтений размера файла с интервалом `stabilization_interval_s`. Если размер стабилен все проверки — ставит task; иначе помечает файл `watch_pending` и пробует снова на следующем poll-cycle. Если файл не стабилизируется за `max_unstable_polls = 6` циклов — событие `material_skipped_busy`.

### 6.4. `Scheduler.register_recurring` (F-AUTO-3)

```python
@dataclass
class RecurringTask:
    task_type: str
    every_n_ticks: int
    handler: Callable[[Task], Any]
    last_fired_tick: int = -1

class Scheduler:
    def register_recurring(
        self,
        task_type: str,
        handler: Callable[[Task], Any],
        every_n_ticks: int,
    ) -> None: ...

    # В tick():
    def _check_recurring(self) -> None:
        for rt in self._recurring:
            if self._tick_count - rt.last_fired_tick >= rt.every_n_ticks:
                self.enqueue(Task(task_type=rt.task_type, payload={"recurring": True}),
                             TaskPriority.LOW)
                rt.last_fired_tick = self._tick_count
```

**Ordering invariant:**
1. В начале каждого `Scheduler.tick()` вызывается `_check_recurring()`; due recurring-задачи enqueue-ятся как `TaskPriority.LOW`, если такая же `task_type` уже не висит в pending-очереди.
2. Затем Scheduler выполняет общую priority queue до `max_tasks_per_tick`, соблюдая порядок `HIGH → NORMAL → LOW`.
3. `IdleDispatcher.next_task()` вызывается только если нет pending `HIGH`/`NORMAL` задач и размер LOW backlog ниже `max_low_queue_backlog`.
4. `HIGH`/`NORMAL` задачи всегда приоритетнее idle-активности: stdin/user query и ingest/reconcile не должны ждать, пока система «саморазмышляет».

### 6.5. `LLMRateLimiter` (`brain/bridges/llm_budget.py`)

Единый лимитер LLM-вызовов для ingestion, reconcile и idle-задач. Бюджет не должен жить в `IdleDispatcher`, иначе ingestion и conflict-advice смогут обойти общий лимит.

```python
@dataclass
class LLMRateLimitConfig:
    llm_calls_per_hour: int = 20

class LLMRateLimiter:
    def allow(self, purpose: str, now: Optional[float] = None) -> bool: ...
    def record(self, purpose: str, now: Optional[float] = None) -> None: ...
    def remaining(self, now: Optional[float] = None) -> int: ...
```

Все LLM-пользователи вызывают `allow()` перед запросом и `record()` после фактического вызова. Если лимит исчерпан, ingestion продолжает regex-only, reconcile пропускает `claim_llm_advice`, idle не ставит LLM-зависимые задачи. Default сохраняется: `llm_calls_per_hour = 20`.

### 6.6. `IdleDispatcher` (`brain/motivation/idle_dispatcher.py`)

Вызывается Scheduler-ом, когда HIGH/NORMAL очередь пуста. Выбирает одну LOW-задачу.

```python
class IdleDispatcher:
    def __init__(
        self,
        gap_detector: KnowledgeGapDetector,
        semantic: SemanticMemory,
        claim_store: ClaimStore,
        curiosity: CuriosityEngine,
        motivation: MotivationEngine,
        llm_rate_limiter: LLMRateLimiter,
        config: IdleDispatcherConfig,
    ): ...

    def next_task(self) -> Optional[Task]:
        candidates = self._gather_candidates()   # gap + reflect + reconcile
        if not candidates:
            return None
        scored = self._rank(candidates)
        chosen = scored[0]
        if self._in_cooldown(chosen.concept):
            return self._pick_next_not_in_cooldown(scored)
        self._record_cooldown(chosen.concept)
        return self._build_task(chosen)
```

**Кандидаты:**
- `gap`: `KnowledgeGapDetector.detect(memory) → concepts with gap`
- `reflect`: `SemanticMemory.get_most_important(top_n=5)`
- `reconcile`: `ClaimStore.get_disputed_pairs(limit=10) → concepts`

**Ранжирование** = `CuriosityEngine.score(concept) + MotivationState.preferred_goal_types.get(goal_type, 0.0)`.

**Disputed-priority override:** если `ClaimStore.count(status=DISPUTED) > 0`, все `reconcile`-кандидаты получают бонус `+1.0` в score — эффективно прыгают выше `reflect`.

**Бюджеты** (`IdleDispatcherConfig`):
- `max_idle_tasks_per_tick = 3` — верхняя граница вызовов `next_task()` за один `Scheduler.tick()`. Scheduler вызывает `next_task()` в цикле до первого `None` или пока не заполнит `max_idle_tasks_per_tick` слотов. Каждый успешный вызов добавляет concept в cooldown и делает последующие вызовы возвращающими следующий top-выбор.
- `max_low_queue_backlog = 8` — если LOW backlog уже достиг 8 задач, IdleDispatcher не добавляет новые idle-задачи; recurring LOW задачи и уже накопленная работа должны сначала разгрузиться.
- `cooldown_per_concept_ticks = 15` — после выбора concept-а он не может быть выбран повторно в течение 15 тиков.
- LLM-бюджет не хранится в `IdleDispatcher`; используется общий `LLMRateLimiter` из §6.5.

### 6.7. `CognitiveResult` / `MemorySearchResult` — pass-through для disputed

Меняется контракт `memory_refs`:

**До:**
```python
@dataclass
class CognitiveResult:
    memory_refs: List[str]           # raw node_id/concept strings
    ...
```

**После:**
```python
@dataclass
class ClaimRef:
    claim_id: str
    concept: str
    claim_text: str                  # нужен в output-слое без доп. lookup
    status: ClaimStatus
    confidence: float
    source_ref: str
    material_sha256: Optional[str]
    source_group_id: str
    conflict_refs: List[str]         # claim_ids в конфликте

@dataclass
class CognitiveResult:
    memory_refs: List[ClaimRef]      # богатые ссылки на claims
    ...
```

`MemorySearchResult` (возвращается из `MemoryManager.retrieve()`) тоже обогащается: каждому semantic hit добавляется `active_claims: List[Claim]` и `answerable_claims: List[Claim]` по concept-у. `active_claims` нужны для обычного ответа и derived description; `answerable_claims` нужны output-слою, чтобы увидеть disputed claims и сформировать hedged response.

`Reasoner` и `HypothesisEngine` получают claim-aware результаты и передают их дальше через `ctx.evidence` → `result.memory_refs`, не делая отдельных lookup-ов в `ClaimStore` в output-слое.

### 6.8. Output layer — hedged при disputed

`DialogueResponder` получает `result.memory_refs`. Логика:

```python
def format(self, result: CognitiveResult) -> str:
    disputed_refs = [r for r in result.memory_refs if r.status == ClaimStatus.DISPUTED]
    # Группируем по concept и ищем первый concept с ≥2 disputed
    by_concept: Dict[str, List[ClaimRef]] = defaultdict(list)
    for ref in disputed_refs:
        by_concept[ref.concept].append(ref)
    hedged_concept = next((c for c, refs in by_concept.items() if len(refs) >= 2), None)
    if hedged_concept is not None:
        a, b = by_concept[hedged_concept][0], by_concept[hedged_concept][1]
        trust_a = self._source_memory.get_trust(a.source_group_id)
        trust_b = self._source_memory.get_trust(b.source_group_id)
        return (
            f"В памяти два несовместимых утверждения о «{a.concept}»: "
            f"\n  — {a.claim_text} (источник: {a.source_ref}, доверие: {trust_a:.2f})"
            f"\n  — {b.claim_text} (источник: {b.source_ref}, доверие: {trust_b:.2f})"
            f"\nКонфликт пока не разрешён."
        )
    # ... обычная логика
```

`ValidationResult` расширяется явным полем `reasons: List[str]`. `ResponseValidator` добавляет `respond_hedged_due_to_dispute` в `validation_result.reasons`, когда ответ был принудительно hedged из-за disputed claims. Это позволяет policy-layer-у понимать причину hedged-ответа и логировать `cycle_complete` с `decision.reason="dispute"`.

## 7. Потоки данных

### 7.1. Ingestion одного файла (материал)

```
FileWatcher (или startup scan)
  ↓ wait-for-stabilization (3×2s) → стабилен
  ↓ enqueue Task(type="ingest_file", payload={"path": "..."})
Scheduler.tick → handle_ingest_file
  ↓
MaterialIngestor.ingest_path(path, session_id)
  ↓ check MaterialRegistry — новый / in_progress / done
  ↓ InputRouter.route(force=True) → List[PerceptEvent]
  ↓ записать чанки в material_chunks (status=pending)
  for each pending chunk:
    ├─ regex extract → claim_candidates(confidence=0.60)
    │   for each candidate:
    │     candidate.source_group_id = material_sha256
    │     candidate.claim_family_key, candidate.stance_key = deterministic grouping keys
    │     ClaimStore.create(claim)
    │       → ConflictGuard.fast_check()
    │         → claim.status := active | possibly_conflicting
    │         → conflict.status := candidate (если есть конфликтная пара)
    │       → events: claim_created | claim_conflict_candidate
    │
    └─ if llm_extractor and LLMRateLimiter.allow("ingest_extract"):
        LLM.extract(chunk_text) → claim_candidates(confidence=0.75)
        for each candidate:
          candidate.source_group_id = material_sha256
          candidate.claim_family_key, candidate.stance_key = deterministic grouping keys
          ClaimStore.create(claim) → ConflictGuard.fast_check()
    ↓
    chunk.status = done
  ↓ (все чанки done)
  ↓ materials_registry.ingest_status = done
  ↓ event: material_ingested
```

### 7.2. Idle-cycle

```
Scheduler.tick
  ↓ _check_recurring() enqueue due LOW tasks
  ↓ execute priority queue up to max_tasks_per_tick
  ↓ HIGH/NORMAL очереди пусты и LOW backlog < max_low_queue_backlog
IdleDispatcher.next_task()
  ├─ gather_candidates:
  │   gaps       = KnowledgeGapDetector.detect()
  │   reflect    = SemanticMemory.get_most_important(5)
  │   reconcile  = ClaimStore.get_disputed_pairs(10) → concepts
  ├─ if ClaimStore.count(DISPUTED) > 0:
  │     для reconcile кандидатов score += 1.0
  ├─ rank by CuriosityEngine.score() + MotivationState.preferred_goal_types
  ├─ фильтрация по cooldown_per_concept_ticks
  └─ вернуть top-1 (не в cooldown); Scheduler вызовет повторно до max_idle_tasks_per_tick
Scheduler.enqueue(task, LOW)
  ↓ event: idle_candidate_chosen
```

### 7.3. Reconciliation (recurring, каждые 10 тиков)

```
Scheduler.tick → handle_reconcile_disputed
  ↓
for pair in ClaimStore.get_conflict_candidates(batch=5):
  if slow-path confirms:
    pair.status = disputed
    pair.a.status = DISPUTED
    pair.b.status = DISPUTED
    → event: claim_disputed
  else:
    pair.status = dismissed
    pair.resolution = false_positive
    non-conflicting claims return to ACTIVE if they have no other open pairs
    → event: claim_conflict_dismissed

for pair in ClaimStore.get_disputed_pairs(batch=5):
  trust_a, trust_b = SourceMemory.get_trust(pair.a.source_group_id),
                      SourceMemory.get_trust(pair.b.source_group_id)
  
  ├─ if |trust_a - trust_b| ≥ 0.3:
  │     ClaimStore.resolve(winner=max, loser=min, "trust")
  │     → winner.status = ACTIVE, loser.status = SUPERSEDED
  │     → event: claim_resolved_by_trust
  │     → RewardEngine.signal(COHERENCE, +0.3)
  │
  ├─ elif COUNT(DISTINCT source_group_id)
  │        WHERE concept + claim_family_key match и stance_key=side
  │        на одной стороне ≥ 2 и на другой 0..1:
  │     ClaimStore.resolve(..., "majority")
  │     → event: claim_resolved_by_majority
  │     → RewardEngine.signal(COHERENCE, +0.2)
  │
  ├─ elif evidence_kind обоих == versioned:
  │     ClaimStore.resolve(winner=latest, loser=oldest, "recency")
  │     → event: claim_resolved_by_recency
  │
  ├─ else (timeless, равный trust, нет majority):
  │     hyp_goal = HypothesisEngine.generate_from_dispute(pair.a, pair.b)
  │     GoalManager.push(hyp_goal)
  │     → event: claim_verification_goal_created
  │     # остаются disputed
  │
  ├─ if LLM available and LLMRateLimiter.allow("conflict_advice"):
  │     classification = llm.classify_conflict(pair.a, pair.b)
  │     → event: claim_llm_advice (no side effects)

# TTL check
for pair in ClaimStore.get_disputed_pairs():
  if pair.detected_ts more than 50 ticks ago:
    pair.status remains disputed
    pair.resolution remains NULL
    pair.a.confidence = max(0.20, pair.a.confidence * 0.9)
    pair.b.confidence = max(0.20, pair.b.confidence * 0.9)
    GoalManager.refresh_or_push(HypothesisEngine.generate_from_dispute(pair.a, pair.b))
    → event: claim_resolution_timed_out
```

## 8. CLI и конфигурация

### 8.1. Новые флаги

```bash
# Новый живой daemon
cognitive-core --daemon \
    --materials materials/ \
    --watch \
    --stdin

# Варианты
cognitive-core --daemon --materials materials/ --no-watch   # только startup scan
cognitive-core --daemon --materials /path/to/pdfs            # watch включён по умолчанию
cognitive-core --daemon --stdin                               # без материалов, только stdin

# Старый режим — сохраняется для CI
cognitive-core --autonomous --ticks 20

# Разовый запрос — как есть
cognitive-core "Что такое нейрон?"
```

### 8.2. Поведение `--daemon`

- Работает до SIGINT/SIGTERM.
- `--materials DIR` включает `MaterialIngestor`. Без флага материалы не читаются.
- `--watch` (по умолчанию ON при наличии `--materials`) включает `FileWatcher`.
- `--stdin` запускает stdin reader в daemon-потоке (F-AUTO-7): каждая непустая строка → `Task(cognitive_cycle, payload={"query": line})` с `TaskPriority.HIGH`.
- Recurring-задачи регистрируются автоматически:
  - `reconcile_disputed` каждые 10 тиков
  - `replay_episodes` каждые 50 тиков (существующий ReplayEngine)
  - `consolidate_memory` каждые 100 тиков (существующая ConsolidationEngine)
  - `self_reflect` каждые 20 тиков (F-AUTO-2)
  - `fill_gaps` — не recurring, а реактивный через IdleDispatcher

### 8.3. Конфиг

Новый dataclass `DaemonConfig` (в `brain/cli.py` или в `brain/core/contracts.py`) с разумными дефолтами. В него входит `LLMRateLimitConfig(llm_calls_per_hour=20)`, который передаётся в общий `LLMRateLimiter`. Переопределение через CLI-флаги (явные `--reconcile-every 5`, `--llm-calls-per-hour 50` и т.п.) — post-MVP.

## 9. Логирование и наблюдаемость

### 9.1. Новые события

Добавляются в категорийный маппинг `_CATEGORY_MAP` в `brain/logging/brain_logger.py`:

**Category `memory`:**
- `claim_created` — новый claim, status=unverified → active/possibly_conflicting
- `claim_conflict_candidate` — fast-path нашёл potentially_conflicting
- `claim_disputed` — slow-path подтвердил конфликт
- `claim_conflict_dismissed` — slow-path снял candidate как false positive
- `claim_resolved_by_trust` / `_by_majority` / `_by_recency`
- `claim_resolution_timed_out` — disputed-пара не разрешилась за TTL; claims остаются disputed, confidence снижен
- `claim_superseded` / `claim_retracted`
- `claim_llm_advice` — LLM-классификация (advice-only)

**Category `perception`:**
- `material_ingested` — с полями `{sha256, chunk_count, claim_count, ingest_duration_ms}`
- `material_skipped_duplicate` / `material_skipped_busy`
- `material_resumed` — продолжение прерванной обработки

**Category `motivation`** (новый файл `motivation.jsonl`):
- `idle_candidate_chosen` — с полями `{concept, candidate_type, curiosity_score, motivation_score, total_score}`
- `idle_no_candidates`
- `reward_signal` — с полями `{reward_type, value, trigger}`
- `motivation_preference_updated`

**Category `cognitive`:**
- `claim_verification_goal_created` — при hypothesis-driven discovery

### 9.2. Logging wiring fix (U-0.6)

Исправляется **до** даemon'а, так как без этого claim-события будут теряться:

1. `OutputPipeline.__init__` принимает `brain_logger: Optional[BrainLogger] = None`.
2. `run_query()` и `run_autonomous()` передают `brain_log` в создаваемые ими `OutputPipeline` instances. `CognitivePipeline` не создаёт `OutputPipeline`, поэтому wiring фиксируется именно в CLI.
3. В `MemoryManager.store_fact` / `store` / `learn` проверяется, что `session_id` передан — не пустая строка. Если не передан — поднимается WARN (это укажет на ingestion-путь, не передающий контекст).
4. `CognitivePipeline.step_create_context` генерирует `trace_id` и `session_id` **первым действием**. `cycle_start` логируется **после** этого, не до.
5. Исправляется двойной префикс `step_step_*` — в `_log_step_timing()` убирается избыточный `step_` prefix.
6. Создание `safety_audit.jsonl` принудительно при старте BrainLogger (сейчас создаётся лениво при первом match-е, часто нет).
7. `refuse` decisions логируются с `decision.reason` и уровнем WARN при `confidence < 0.3`.

### 9.3. JSON-поля для новых событий

Все claim-события должны содержать:
- `claim_id`, `concept`, `status` (до/после)
- Для пар: `claim_id_a`, `claim_id_b`, `conflict_status`
- Для `_resolved_by_*`: `resolution`, `winner_claim_id`, `loser_claim_id`, `trust_a`, `trust_b`, `majority_a`, `majority_b`
- Для `claim_resolution_timed_out`: `claim_id_a`, `claim_id_b`, `conflict_status="disputed"`, `confidence_a_before/after`, `confidence_b_before/after`, `verification_goal_id`
- `session_id`, `cycle_id`, `trace_id` — обязательные

## 10. Обработка ошибок и edge cases

| Сценарий | Поведение |
|---|---|
| Файл ещё пишется (размер меняется между polling-проверками) | `stabilization_checks=3` с интервалом 2 сек; если не стабилизировался за `max_unstable_polls=6` → `material_skipped_busy`, retry на следующем поле |
| Все источники idle-кандидатов пусты | `idle_no_candidates`, Scheduler sleep до следующего тика |
| Dispute не разрешён 50 тиков | Пара остаётся `disputed`, `resolution=NULL`; confidence обоих claim-ов мягко снижается, verification goal обновляется, event `claim_resolution_timed_out` |
| Противоречащие утверждения из одного `source_group_id` | Допустимо (учебник с разными мнениями); оба → `disputed` с `metadata.intra_source=True`; не резолвится majority-ем (сами себя не побеждают) |
| Claim нужно исключить из памяти | `RETRACTED` разрешён только для доказанно ложных, ручных или устаревших versioned claims; timeout unresolved dispute не является retract-причиной |
| LLM extractor падает mid-flight | Ingestion продолжается на regex-only; WARN с `notes="llm_extract_failed"`; чанк всё равно помечается done |
| LLM classifier (advice) падает | Игнорируется; claim-пара остаётся disputed; reconcile продолжается на детерминированных правилах |
| `MotivationEngine.is_frustrated=True` (epistemic_score < 0.2) | IdleDispatcher принудительно приоритизирует reconcile (если есть disputed), иначе gap; reflect отключается |
| Crash посреди ingestion | На рестарте `MaterialIngestor.resume_incomplete()` находит `in_progress` + `pending`/retryable `failed` чанки и продолжает |
| stdin закрылся (EOF) | stdin reader thread завершается, daemon продолжает работать через watcher и idle |
| Повторный вызов `ClaimStore.create()` с идентичным `(concept, claim_text, source_ref)` | Idempotent: возвращает существующий claim_id, не создаёт дубль |
| Concept-нормализация разошлась между fast-path и slow-path | Фиксируем одну функцию `_normalize_concept()` в `brain/core/text_utils.py`, используем её везде |
| Size-limit превышен для single claim | Claim.claim_text обрезается до 500 символов, остаток в `metadata.truncated_suffix` |
| Circular supersedes (A→B→A) | `ClaimStore.resolve()` проверяет: `loser.superseded_by` ещё не указывает на `winner`; если да — event `claim_resolve_cycle_prevented`, op-пропуск |

## 11. Стратегия тестирования

### 11.1. Новые тест-файлы

| Файл | Покрытие |
|---|---|
| `tests/test_claim_store.py` | CRUD, find_by_concept, active_claims, status transitions, idempotent create, FK constraints |
| `tests/test_storage_migration_v2.py` | idempotent migration `SCHEMA_VERSION = 2`: v1 DB сохраняет legacy tables, получает additive claim/material tables, повторный запуск no-op |
| `tests/test_material_registry.py` | startup + chunk-level resume, SHA256 idempotence |
| `tests/test_claim_stance_keys.py` | `claim_family_key`/`stance_key`: paraphrases группируются в одну сторону, противоположное утверждение получает другой stance |
| `tests/test_conflict_guard_fast.py` | negation & numeric candidate detection, intra-source behavior, K=3 limit |
| `tests/test_conflict_guard_slow.py` | trust-resolution (gap ≥0.3 by `source_group_id`), majority by `(claim_family_key, stance_key, source_group_id)`, recency only for versioned, hypothesis-escalation for timeless equal, TTL timeout без retract |
| `tests/test_material_ingestor.py` | startup scan, idempotence, resume after crash, SHA256 dedup across daemon restarts |
| `tests/test_file_watcher.py` | polling, wait-for-stabilization, FakeFS, max_unstable_polls |
| `tests/test_idle_dispatcher.py` | ranking, cooldowns, disputed-priority override, budget enforcement, `max_low_queue_backlog`, deterministic с seed |
| `tests/test_scheduler_recurring.py` | register_recurring, correct tick-firing, multiple recurring tasks, HIGH/NORMAL outrank idle LOW backlog |
| `tests/test_hypothesis_from_dispute.py` | generate_from_dispute goal creation |
| `tests/test_output_hedged_dispute.py` | DialogueResponder производит hedged на disputed≥2 |
| `tests/test_daemon_integration.py` | end-to-end: startup scan materials/ → watcher → stdin → conflict lifecycle |

### 11.2. Conflict test corpus (U-G)

`tests/fixtures/conflicts/`:
- `high_trust/topology.md` — «Рабочая память содержит 7±2 элементов. (Miller 1956)» (trust=0.85)
- `mid_trust_a/cognitive_basics.md` — «Рабочая память оперирует 7 элементами.» (trust=0.60, support for A)
- `mid_trust_b/neuro_update.md` — «Рабочая память содержит не более 4±1 элементов. (Cowan 2001)» (trust=0.60, contradicts)
- `low_trust/blog_post.md` — «Мозг помнит всё одновременно.» (trust=0.30, noise)

Integration-тест `test_daemon_integration.py::test_majority_resolution_on_fixture`:
1. Ingest все 4 файла.
2. Ожидается: `high_trust` + `mid_trust_a` → 2 поддержки утверждения A (одинаковые `claim_family_key` и `stance_key=A`, но 2 distinct `source_group_id`; для этих fixture это 2 distinct `material_sha256`); `mid_trust_b` → 1 поддержка утверждения B (тот же `claim_family_key`, `stance_key=B`).
3. Reconcile → `claim_resolved_by_majority`, winner — A.
4. `mid_trust_b` → `superseded`.
5. Проверить логи: `claim_conflict_candidate` (fast-path при ingestion B), `claim_disputed` (slow-path), `claim_resolved_by_majority`.

### 11.3. Покрытие

Coverage-gate остаётся **70%** (`--cov-fail-under=70`). Ожидаемый рост общего coverage — на 3–5 процентных пунктов за счёт новых модулей.

## 12. Этапы реализации

| Этап | Название | Зависимости | Примерный объём |
|---|---|---|---|
| **U-0** | Memory foundation + logging wiring | — | ~1200 LOC, 10 новых тест-файлов |
| **U-A** | Scheduler recurring + budgets | U-0 | ~300 LOC |
| **U-B** | Conflict lifecycle (fast + slow) | U-0, U-A | ~600 LOC |
| **U-C** | Material ingestion pipeline | U-0, U-A, U-B | ~500 LOC |
| **U-D** | Curiosity-driven idle with budget | U-A, U-B | ~400 LOC |
| **U-E** | Output respecting disputed | U-0, U-B | ~300 LOC |
| **U-F** | Daemon mode + stdin | U-A..U-E | ~400 LOC |
| **U-G** | Conflict test corpus | U-F | fixtures + ~300 LOC test code |

**Критический путь:** U-0 → U-A → U-B → остальное.

**Параллелизуемые после U-0/U-A/U-B:**
- U-C (ingestion) независим от U-D (idle).
- U-E (output) зависит только от U-0 и U-B.
- U-G (fixtures) требует U-F, но готовится параллельно.

## 13. Явно deferred (не входит в [`planning/UPDATE_TODO.md`](../../planning/UPDATE_TODO.md))

- **U-0.7 — Legacy backfill SemanticNode → Claim.** Опциональная миграция: по каждому существующему `SemanticNode` создать один `Claim(evidence_kind=timeless, status=active, confidence=node.confidence)`. Если не делать, старые SemanticNode остаются как legacy fallback.
- **F-AUTO-8 IPC / Unix socket.** Post-MVP.
- **F-AUTO-12 Multi-process architecture.** Post-MVP.
- **F-AUTO-13 Persistent scheduler queue.** Post-MVP.
- **F-AUTO-14 Web dashboard.** Post-MVP.
- **LLM fact-verification** (retrieval-augmented LLM-judge) — post-MVP; противоречит принципу «LLM не судья».
- **Active learning loop** (система сама задаёт вопросы пользователю при disputed) — post-MVP.

## 14. Связи с существующими документами

- [`planning/FUTURE_TODO.md`](../../planning/FUTURE_TODO.md) — `U-AUTO-*` задачи в [`planning/UPDATE_TODO.md`](../../planning/UPDATE_TODO.md) ссылаются на открытые `F-AUTO-*` (F-AUTO-1/2/3/6/7/9/14), эти ссылки **заменяют** соответствующие F-задачи (они закрываются).
- `docs/layers/09_logging_observability.md` — logging wiring fix (U-0.6) закрывает 5 из 8 пунктов предыдущего анализа логов (trace chain, memory session_id, cycle_start timing, step префикс, safety_audit file).
- `docs/adr/` — потенциально новый ADR (опционально, после реализации U-0 и U-B): **ADR-008 Claim-Store модель памяти и детерминированная resolution**.
- `docs/BRAIN.md` — §5 (Memory) и §14 (Logging) потребуют обновления после U-0; §12 (Autonomy) — после U-F.

## 15. Метрики успеха

После завершения U-0..U-G должны быть измеримы:

1. **Автономность.** `cognitive-core --daemon` работает >4 часов без вмешательства, очередь не пустеет (IdleDispatcher поставляет задачи), RAM не течёт.
2. **Самообучение.** Загрузка новых PDF в `materials/` во время работы → через ≤2 мин в памяти появляются новые claims, событие `material_ingested` в логах.
3. **Проверка памяти.** При подаче на вход conflict-корпуса (см. U-G) через ≤10 тиков появляется событие `claim_disputed`.
4. **Сомнение.** Тот же корпус → через ≤20 тиков: `claim_resolved_by_majority` в логах, winner в `status=active`, loser в `status=superseded`.
5. **Output-адекватность.** Вопрос про концепт с disputed claims → `respond_hedged` с `decision.reason="dispute"` и текст ответа содержит упоминание обоих источников.
6. **Логи-качество.** 0 записей с `session_id=""` в `memory.jsonl`. Существуют `perception.jsonl`, `safety_audit.jsonl`, `motivation.jsonl`. `logging_overhead_pct` < 5% от cycle duration.
7. **Timeout-безопасность.** Неразрешённый disputed conflict после TTL пишет `claim_resolution_timed_out`, но оба claim-а остаются `status=disputed`, а `claim_conflicts.status` не становится `resolved`.

## 16. Implementation invariants and open engineering decisions

Этот раздел фиксирует решения, которые должны быть одинаково поняты при декомпозиции spec-а в [`planning/UPDATE_TODO.md`](../../planning/UPDATE_TODO.md). Если будущая задача противоречит этим инвариантам, менять нужно сначала spec/ADR, а не локальную реализацию.

### 16.1. SQLite schema migration

**Выбранное решение: `SCHEMA_VERSION = 2`, idempotent in-place migration `v1 → v2`.**

Варианты:
- **A. Additive in-place migration (выбрано).** При открытии `MemoryDatabase` проверяется текущий schema version. Если база v1, выполняется `_migrate_v1_to_v2()` в транзакции: создаются `claims`, `claim_conflicts`, `materials_registry`, `material_chunks`, индексы и служебные поля. Повторный запуск безопасен (`CREATE TABLE IF NOT EXISTS`, проверка `PRAGMA user_version`/локального version row).
- **B. Fresh v2 database only.** Проще реализовать, но ломает существующую память пользователя.
- **C. Full backfill `SemanticNode → Claim` внутри migration.** Удобно для единообразия, но рискованно: legacy semantic description не содержит evidence-span/source granularity, поэтому migration начнёт изобретать claims без настоящего evidence.

Инварианты v2:
- `SCHEMA_VERSION = 2` применяется до инициализации `MemoryManager`, `ClaimStore`, `MaterialRegistry`.
- v2 migration только additive: legacy v1 tables не удаляются и не переписываются.
- Legacy backfill `SemanticNode → Claim` остаётся deferred (§13) и не входит в `_migrate_v1_to_v2()`.
- Migration должна быть покрыта `tests/test_storage_migration_v2.py`: v1 fixture → open DB → v2 tables exist → old semantic/episodic data preserved → second open no-op.

### 16.2. Claim grouping for majority

**Выбранное решение: majority считается по normalized stance grouping, а не по literal `claim_text`.**

Варианты:
- **A. Literal text grouping.** Считать сторону конфликта по `claim_text`. Это ломается на перефразировании: «7±2 элементов» и «примерно семь элементов» становятся разными сторонами.
- **B. LLM-decided grouping.** Дать LLM решать, какие claims поддерживают одну сторону. Это нарушает принцип «LLM extractor/advisor only».
- **C. Deterministic keys with optional LLM suggestion (выбрано).** Каждый claim получает `claim_family_key` и `stance_key`. Ключи строятся детерминированным normalizer-ом; LLM может предложить группировку только как `claim_llm_advice`, без side effects.

Инварианты:
- `claim_family_key` отвечает на вопрос: «о каком проверяемом отношении/параметре этот claim?» Например, `working_memory.capacity`.
- `stance_key` отвечает на вопрос: «какую сторону внутри family claim поддерживает?» Например, `capacity:7_plus_minus_2` или `capacity:4_plus_minus_1`.
- Majority query считает уникальные root-sources по `(concept, claim_family_key, stance_key, source_group_id)`.
- Несколько чанков, страниц или перефразированных claims одного PDF имеют один `source_group_id` и не могут создать majority сами себе.
- Fixture `tests/test_claim_stance_keys.py` должен явно проверять paraphrase grouping.

### 16.3. Root-source trust

**Выбранное решение: trust живёт на `source_group_id`, а `source_ref` остаётся citation pointer.**

Варианты:
- **A. Trust by `source_ref`.** Простая адресация, но страница `pdf#p12` и `pdf#p13` начинают выглядеть как разные независимые источники.
- **B. Trust by root-source `source_group_id` (выбрано).** Один материал/URL/stdin-session получает один trust-root, а конкретные evidence spans остаются ссылками через `source_ref`.
- **C. Trust by claim.** Гибко, но смешивает доверие к источнику с confidence конкретного утверждения.

Инварианты:
- `SourceMemory.get_trust()` в conflict lifecycle и output layer вызывается с `source_group_id`.
- `source_ref` используется для цитирования, evidence-span, логов и UI: он не участвует в majority/trust как независимый голос.
- Для материалов `source_group_id = material_sha256`; для stdin/user/web задаётся стабильный root-source id (`stdin:<session_id>`, `user:<id>`, `url:<normalized_doc_hash>`).
- `tests/test_conflict_guard_slow.py` должен иметь кейс, где два `source_ref` одного `source_group_id` не дают majority.

### 16.4. Scheduler / IdleDispatcher ordering

**Выбранное решение: recurring work входит в priority queue перед idle, idle добавляет работу только при свободной системе.**

Варианты:
- **A. Idle always appends LOW tasks.** Может раздувать LOW очередь и задерживать recurring maintenance.
- **B. Priority queue first, idle only under backlog threshold (выбрано).** Сначала due recurring tasks, затем execution budget, затем idle only if нет urgent work.
- **C. Separate idle thread.** Выглядит живее, но усложняет синхронизацию MemoryManager/ClaimStore.

Инварианты:
- В начале `Scheduler.tick()` due recurring tasks enqueue-ятся как LOW.
- Scheduler выполняет priority queue до `max_tasks_per_tick` в порядке `HIGH → NORMAL → LOW`.
- `IdleDispatcher.next_task()` вызывается только если pending `HIGH/NORMAL == 0` и LOW backlog `< max_low_queue_backlog`.
- Default: `max_low_queue_backlog = 8`.
- `max_idle_tasks_per_tick = 3` ограничивает только idle-generated tasks, не общий Scheduler execution budget.
- `tests/test_scheduler_recurring.py` и `tests/test_idle_dispatcher.py` должны покрывать случай, где LOW backlog уже заполнен, и idle не добавляет новые задачи.

### 16.5. TTL for unresolved disputes

**Выбранное решение: timeout не retract-ит disputed claims.**

Варианты:
- **A. Auto-retract both on timeout.** Быстро очищает систему, но уничтожает полезное сомнение и превращает отсутствие resolution в доказательство ложности.
- **B. Timeout keeps dispute, decays confidence, refreshes verification goal (выбрано).** Сохраняет оба claim-а для hedged output и продолжает искать разрешение.
- **C. Timeout auto-picks latest.** Допустимо только для `EvidenceKind.VERSIONED`, но неверно для timeless знаний.

Инварианты:
- При timeout `claim_conflicts.status` остаётся `disputed`, `resolution` остаётся `NULL`.
- Оба claim-а остаются `ClaimStatus.DISPUTED`; confidence снижается мягко (`* 0.9`, floor `0.20`), чтобы retrieval видел неопределённость, но не стирал evidence.
- Пишется событие `claim_resolution_timed_out`.
- Verification goal обновляется или создаётся заново с более высоким приоритетом reconcile/verify.
- `ClaimStatus.RETRACTED` используется только для доказанно ложных, ручных или устаревших versioned claims.
- `tests/test_conflict_guard_slow.py` должен проверять TTL timeout без `retract()` и без `claim_conflicts.status="resolved"`.

### 16.6. Remaining open decisions

Эти решения не блокируют U-0/U-A/U-B, но должны быть оформлены перед daemon hardening:
- Формат `claim_family_key`/`stance_key` normalizer-а: минимальный MVP может использовать regex/numeric templates; расширение через ontology/LLM-advice — post-MVP.
- Где хранить source trust для non-material root-sources: можно расширить `SourceMemory` существующей таблицей или добавить адаптер поверх текущей модели, но публичный контракт остаётся `get_trust(source_group_id)`.
- UI/CLI для ручного retract и ручного trust override не входит в этот spec; это отдельный operator-workflow после стабилизации claim lifecycle.

---

**Конец документа.** Готов к декомпозиции в [`planning/UPDATE_TODO.md`](../../planning/UPDATE_TODO.md) через skill writing-plans.
