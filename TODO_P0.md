# P0 — Audit Fixes

## Tasks

- [x] **P0.1** README.md integrity check — ✅ файл чистый
- [x] **P0.2** B.5 Golden-answer benchmarks ✅
  - [x] `tests/golden/questions.json` — 20 Q&A pairs
  - [x] `tests/test_golden.py` — 414 parametrized benchmark tests (7 classes)
  - [x] Run `pytest tests/test_golden.py -v` — 414/414 passed ✅
  - [x] Run full `pytest tests/ -q` — 1249/1249 passed in 14.78s ✅
  - [x] Update `TODO_PHASE_B.md` — B.5 marked ✅
