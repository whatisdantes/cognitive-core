# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**cognitive-core** v0.7.0 — artificial multimodal "brain" in Python 3.11+. The package root is `brain/`; the distribution name on PyPI-style metadata is `cognitive-core` (see `pyproject.toml`). Target platform is CPU-only (AMD Ryzen 7 5700X / 32 GB class), Windows primary, Linux/macOS compatible. Versions 3.11, 3.12, 3.13 are all tested in CI.

Source-of-truth documents (prefer reading these over CLAUDE.md when answering architecture questions):
- `README.md` — long overview + capability matrix + per-module API examples (Russian)
- `CONTRIBUTING.md` — code style, commit format, PR checklist (Russian)
- `docs/planning/TODO.md` — master roadmap and current-phase priorities (also `docs/planning/FUTURE_TODO.md` for post-MVP backlog)
- `docs/BRAIN.md` — full architectural spec (15 sections)
- `docs/layers/00..11_*.md` — per-layer specifications
- `docs/adr/ADR-*.md` — architectural decisions (SQLite default, RLock, Protocol DI, BM25+hybrid retrieval, template-only responses, sync EventBus, CPU-only)

## Language convention (important)

- **Comments, docstrings, commit messages, PR descriptions — Russian.**
- **Identifiers (modules, classes, functions, variables) — English** (`snake_case` / `PascalCase`).
- Do not translate existing Russian docstrings into English when editing; keep the project's voice.

Commit format: `<type>(<scope>): <russian description>` where type ∈ `feat | fix | refactor | test | docs | chore | perf`. Example: `feat(memory): добавить batch_remove() в WorkingMemory`.

## Commands

Work inside the project's `.venv` — activation line on Windows is `.venv\Scripts\activate`.

### Install
```bash
pip install -e ".[dev]"      # standard dev install (pytest, ruff, mypy, bandit, hypothesis, mutmut)
pip install -e ".[all]"      # everything: dev + nlp + vision + audio + docs + apidocs + encrypted + openai + anthropic
pip install -e ".[encrypted]"  # just SQLCipher
```
Optional extras (`nlp`, `vision`, `audio`, `docs`, `apidocs`, `encrypted`, `openai`, `anthropic`) are deliberately isolated because every subsystem has a graceful-degradation path — do not promote an optional dependency into the core `dependencies` list.

### Tests
```bash
python -m pytest tests/ -v
python -m pytest tests/test_memory.py -v                                    # one file
python -m pytest tests/test_memory.py::TestSemanticMemory::test_learn_fact -v   # one test
python -m pytest tests/ --cov=brain --cov-report=term-missing --cov-fail-under=70
```
The coverage gate in CI is **70%** (`--cov-fail-under=70`). Do not lower it to make a PR pass — investigate the regression instead. The suite currently collects ~2200 tests; run `pytest --collect-only -q` to get the live count.

Tests that depend on an optional extra (e.g. `test_storage_encrypted.py` needs `[encrypted]`) skip automatically when the extra is missing — do not guard them behind flags by hand.

Known limitation: four `TestEncryptedDatabase` tests in `test_storage_encrypted.py` are marked `@xfail(strict=False)` because `sqlite3.Row` row_factory does not accept `sqlcipher3.dbapi2.Cursor` (`TypeError: Row() argument 1 must be sqlite3.Cursor, not sqlcipher3.dbapi2.Cursor`). Key validation, plain-SQLite paths, and the `ImportError` branch all work. When fixing this in `brain/memory/storage.py`, drop the xfail decorator.

### Lint / type / SAST
```bash
python -m ruff check brain/ tests/                       # lint (rules: E, F, W, I, B, SIM, C4, RET, PIE; exceptions in pyproject.toml)
python -m mypy brain/ --ignore-missing-imports           # type check
python -m bandit -r brain/ -c pyproject.toml -q          # SAST (B101/B110 skipped by config)
```
All three must pass clean (0 errors) before a PR merges.

### Running the system
```bash
cognitive-core "Что такое нейрон?"                        # one-shot query (CLI entrypoint → brain.cli:cli_entry)
cognitive-core --autonomous --ticks 10                    # Scheduler-driven autonomous mode
cognitive-core --log-dir brain/data/logs --log-level DEBUG "вопрос"   # JSONL logging enabled
cognitive-core --llm-provider blackbox --llm-api-key KEY "вопрос"     # with LLM bridge
python examples/demo.py                                   # full programmatic pipeline in ~30 lines
docker build -t cognitive-core . && docker run cognitive-core "вопрос"
```

## Architecture (big picture)

The system is organised as **12 numbered layers** (0–11), each modelled on a brain region. Layer ownership is encoded in the top-level package names under `brain/`:

| # | Package | Biological analogue | Role |
|---|---------|--------------------|------|
| 0 | `core/` | Brainstem | EventBus, Scheduler, ResourceMonitor, AttentionController, shared contracts |
| 1 | `perception/` | Thalamus | File ingestors + InputRouter (SHA256 dedup, quality gating, path/size guards) |
| 2 | `encoders/` | Sensory cortex | Text/Vision/Audio/Temporal encoders + EncoderRouter (Vision/Audio are CPU-only stubs) |
| 3 | `fusion/` | Associative cortex | SharedSpaceProjector, EntityLinker, ConfidenceCalibrator, CrossModalContradictionDetector |
| 4 | `memory/` | Hippocampus + cortex | 5 memory types (Working/Semantic/Episodic/Source/Procedural) + ConsolidationEngine + SQLite/WAL backend |
| 5 | `cognition/` | Prefrontal cortex | GoalManager, Planner, HypothesisEngine, Reasoner, ContradictionDetector, UncertaintyMonitor, SalienceEngine, PolicyLayer, ActionSelector, CognitivePipeline |
| 6 | `learning/` | Cerebellum + hippocampus | OnlineLearner, KnowledgeGapDetector, ReplayEngine |
| 7 | `output/` | Broca/Wernicke | OutputTraceBuilder, ResponseValidator, DialogueResponder, OutputPipeline (template MVP — no live LLM by default; see ADR-005) |
| — | `bridges/` | — | LLMBridge + OpenAI/Anthropic/Blackbox providers + SafetyWrapper |
| 9 | `logging/` | Metacognition | BrainLogger (JSONL, 5 levels, category files + trace/session index), DigestGenerator, TraceBuilder |
| 10 | `safety/` | Immune system | AuditLogger, SourceTrustManager, ConflictDetector, BoundaryGuard (PII), SafetyPolicyLayer (SF-1/2/3) |
| 11 | `motivation/` | Midbrain / dopamine | RewardEngine, MotivationEngine, CuriosityEngine |

### Two orchestration entry points

1. **`brain/cognition/cognitive_core.py` — `CognitiveCore`**: the high-level facade. Accepts `MemoryManager`, `EventBus`, `ResourceMonitor`, optional `TextEncoder`, `LLMProvider`, `BrainLogger`, `TraceBuilder`, safety/learning components in its constructor. `.run(query)` returns a `CognitiveResult`. Internally delegates to `CognitivePipeline`.

2. **`brain/cognition/pipeline.py` — `CognitivePipeline`**: the actual 20-step pipeline (P3-10 refactor replacing an earlier god-method). Each step (`create_context`, `auto_encode`, `safety_input_check`, `get_resources`, `build_retrieval_query`, `create_goal`, `evaluate_salience`, `compute_budget`, `index_percept_vector`, `reason`, `detect_knowledge_gaps`, `llm_enhance`, `select_action`, `safety_policy_check`, `execute_action`, `complete_goal`, `build_result`, `safety_audit_log`, `publish_event`, `post_cycle`) is individually testable and overridable. `CognitivePipelineContext` is the per-cycle state carrier. When adding new cognitive behaviour, prefer adding/modifying a pipeline step to threading logic through `CognitiveCore`.

### Cross-cutting principles (from ADRs + CONTRIBUTING.md)

- **Event-driven integration**: modules do not import each other's internals; they talk through `EventBus` (sync publish-with-snapshot semantics, see ADR-006) using typed events from `brain/core/events.py` (`PerceptEvent`, `MemoryEvent`, `CognitiveEvent`, `LearningEvent`, `SystemEvent`). Use `EventFactory` to construct them — it fills `ts`, `trace_id`, `session_id`, `cycle_id` consistently.
- **Protocol-based DI** (ADR-003): layer boundaries are `typing.Protocol` interfaces declared in `brain/core/contracts.py` (e.g. `MemoryManagerProtocol`, `EventBusProtocol`, `TextEncoderProtocol`, `ResourceMonitorProtocol`). Inject dependencies through constructors — never instantiate collaborators inside a class.
- **Thread safety** (ADR-002): every shared-mutable-state class guards its state with `threading.RLock()`. When adding state, wrap with the existing lock; do not add `threading.Lock` (not reentrant).
- **Graceful degradation**: `TextEncoder` reports `ok/fallback/degraded/failed` instead of raising when sentence-transformers is missing; `ResourceMonitor` has `NORMAL/DEGRADED/CRITICAL/EMERGENCY` policies; the whole system must still boot with only core dependencies installed. Preserve this when touching any module with an optional extra.
- **Immutability**: prefer `dataclasses.replace(obj, field=value)` over mutating dataclass fields after construction.
- **Shared utilities** live in `brain/core/text_utils.py` (`detect_language`, `parse_fact_pattern`) and `brain/core/hash_utils.py` (`sha256_text`, `sha256_file`). Use these instead of re-rolling.

### Memory system specifics

`MemoryManager` is the single entry point that aggregates all five memory types + `ConsolidationEngine`. The persistent backend is SQLite with WAL mode (ADR-001) at `brain/data/memory/memory.db`; the legacy JSON files (`semantic.json` etc.) are still supported as a fallback / migration source via `brain/memory/migrate.py`. Retrieval in v0.7.0 is **keyword BM25 + in-memory cosine-similarity hybrid** (ADR-004); persisted ANN/FAISS is post-MVP. The vector index is built on init from `SemanticMemory + EpisodicMemory` and grown incrementally on `LEARN` — if a query lands empty, suspect memory wasn't populated, not that retrieval is broken.

### Output layer specifics (ADR-005)

Default responses are **template-generated**, not LLM-generated. The `--llm-provider` flag and `brain/bridges/` exist to *augment* template output, not replace it. Keep the core-mode path working without any LLM key — it is first-class, not fallback.

## Repo layout shortcuts

- `brain/cli.py` — argparse entrypoint (`cognitive-core "..."`)
- `brain/core/contracts.py` — all `Protocol`s and cross-layer dataclasses (`EncodedPercept`, `FusedPercept`, `TraceChain`, `CognitiveResult`, `BrainOutput`, `Modality`, `ResourceState`, `Task`)
- `brain/core/events.py` — event classes + `EventFactory`
- `brain/cognition/pipeline.py` — the 20-step pipeline (single most important file for cognition changes)
- `tests/conftest.py` — inserts the project root into `sys.path` and provides `tmp_data_dir`, `sample_text_short`, `sample_text_long` fixtures
- `examples/demo.py` — minimal end-to-end assembly (good reference for wiring tests)

## Git / CI

- CI (`.github/workflows/ci.yml`) runs on push to `main` / `develop` and on PRs to `main`: ruff + mypy, pytest on Python 3.11/3.12/3.13 with coverage gate 70%, bandit, Docker build. Codecov upload happens only from the 3.12 job.
- Branches: `main` (stable, PR-only), `develop` (current work), `feature/*`, `fix/*`, `docs/*`.
- Never push coverage artefacts, `.venv/`, `.pytest_tmp*/`, `.ai/`, `.coverage` files — they are gitignored for a reason.
