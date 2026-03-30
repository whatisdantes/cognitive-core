# TODO: Интеграция Learning (Этап J)

## Архитектурное решение
- `KnowledgeGapDetector` — НЕ в `MemoryManager` (нарушает слоистость)
- Вместо этого: `step_detect_knowledge_gaps()` как шаг 10 в `CognitivePipeline`
- `MemorySearchResult` пробрасывается через `ReasoningTrace.metadata["memory_search_result"]` из `Reasoner`
- `OnlineLearner` — шаг 17 `step_post_cycle()` в `CognitivePipeline`
- `ReplayEngine` — в `handle_consolidate_memory` в `run_autonomous()` CLI

## Прогресс

- [x] Шаг 1: `brain/cognition/reasoner.py`
      — в `_retrieve_evidence()` сохранять `MemorySearchResult` в `trace.metadata["memory_search_result"]`

- [x] Шаг 2: `brain/cognition/pipeline.py`
      — `CognitivePipelineContext`: добавить `memory_search_result`, `knowledge_gap`
      — `CognitivePipeline.__init__()`: добавить `gap_detector`, `online_learner`
      — `step_reason()`: извлечь `memory_search_result` из `ctx.trace.metadata`
      — Новый `step_detect_knowledge_gaps()` — шаг 10 (между reason и llm_enhance)
      — Новый `step_post_cycle()` — шаг 17 (после publish_event)
      — Обновить список steps (17 шагов)

- [x] Шаг 3: `brain/cognition/cognitive_core.py`
      — Импорт `MemoryManager`, `OnlineLearner`, `KnowledgeGapDetector`
      — Создать `OnlineLearner` + `KnowledgeGapDetector` если `isinstance(memory, MemoryManager)`
      — Передать в `CognitivePipeline`
      — Добавить `has_online_learner`, `has_gap_detector` в `status()`

- [x] Шаг 4: `brain/cli.py`
      — В `run_autonomous()`: создать `ReplayEngine(memory=mm)` (шаг 5)
      — В `handle_consolidate_memory`: вызвать `replay_engine.run_replay_session(force=False)`
      — Исправлен лог: `session.episodes_replayed`, `session.reinforced`, `session.stale_removed`
      — Добавлены `--log-dir`, `--log-level` в `build_parser()`
      — `run_query()` и `run_autonomous()` принимают `log_dir`, `log_level`
      — `BrainLogger` + `TraceBuilder` + `DigestGenerator` создаются и передаются в `CognitiveCore`

- [x] Шаг 5: `tests/test_learning_integration.py` (СОЗДАН)
      — `test_online_learner_called_after_cycle` ✓
      — `test_online_learner_skips_low_confidence` ✓
      — `test_gap_detector_missing_gap` ✓
      — `test_gap_detector_weak_gap` ✓
      — `test_gap_detector_no_gap` ✓
      — `test_replay_engine_in_autonomous` ✓
      — `test_learning_backward_compat` ✓

- [x] Шаг 6: Запустить pytest + ruff + mypy

## Фикс golden-регрессий (q04, q14)

- [x] **q14** ("что такое квантовая хромодинамика?") — `respond_direct` → `respond_hedged`
      — `brain/cognition/reasoner.py`: сохранять `trace.metadata["best_hypothesis_score"] = best.final_score`
      — `brain/cognition/action_selector.py`: в `_decide_by_confidence()` при `conf ≥ min_conf`
        проверять `best_hypothesis_score < 0.3` → понижать до `respond_hedged`
      — Причина: нерелевантный факт найден по стоп-слову "такое", `final_score=0.25` (низкий),
        но `confidence=0.9615` (высокий из importance факта)

- [x] **q04** ("сколько нейронов в мозге человека?") — `ask_clarification` без "миллиард" → с "миллиард"
      — `brain/cognition/action_selector.py`: в `_decide_by_confidence()` при `hypothesis_count > 0`
        включать `trace.best_statement` в ответ: `f"{best_statement}\n\nМожете уточнить вопрос?"`
      — Причина: `confidence < 0.24` → `ask_clarification`, но `best_statement` содержит
        "мозг человека содержит около 86 миллиардов нейронов" → тест `must_contain_if_found=["миллиард"]` проходит

- [x] Шаг 7: Запустить `pytest tests/test_golden.py -v` для верификации фиксов
