# TODO Stage F+ — Cognitive Extensions

> **Версия:** v1 (2026-03-25)
> **Цель:** Расширение когнитивного ядра: retrieval adapter, contradiction detection, uncertainty monitoring, causal/analogical reasoning, full replan
> **Оценка:** ~12-16 часов реализации + тесты

---

## Шаги реализации

### Шаг 1: [x] `brain/cognition/context.py` — Новые enum
- [x] UncertaintyTrend enum (RISING, FALLING, STABLE, UNKNOWN)
- [x] ReplanStrategy enum (RETRY, NARROW_SCOPE, BROADEN_SCOPE, DECOMPOSE, ESCALATE)
- [x] Существующие 611 тестов не сломаны

### Шаг 2: [x] `brain/cognition/retrieval_adapter.py` — Retrieval integration
- [x] RetrievalBackend(Protocol): search(query, top_n) → List[EvidencePack]
- [x] KeywordRetrievalBackend: обёртка над MemoryManager.retrieve()
  - [x] _from_working(MemoryItem) → EvidencePack
  - [x] _from_semantic(SemanticNode) → EvidencePack (concept_refs, confidence, source_refs)
  - [x] _from_episodic(Episode) → EvidencePack (concepts, importance, tags)
  - [x] _compute_relevance(query, content) → float (keyword overlap)
  - [x] _compute_freshness(timestamp) → float
- [x] RetrievalAdapter: facade с metadata enrichment
  - [x] retrieve(query, top_n) → List[EvidencePack]
  - [x] Канонический набор полей гарантирован (11 полей, defaults)
  - [x] metadata: retrieval_backend, retrieved_at, original_memory_type

### Шаг 3: [x] `brain/cognition/contradiction_detector.py` — Обнаружение противоречий
- [x] Contradiction dataclass (evidence_a_id, evidence_b_id, type, severity, description, shared_subject)
- [x] ContradictionDetector class:
  - [x] detect(evidence) → List[Contradiction]
  - [x] flag_evidence(evidence, contradictions) → List[EvidencePack] (COPY-ON-WRITE, не мутирует)
  - [x] _same_subject(a, b) → Tuple[bool, str] (concept_refs overlap обязателен)
  - [x] _check_negation(a, b, subject) → Optional[Contradiction]
  - [x] _check_numeric(a, b, subject) → Optional[Contradiction] (>20% diff, skip if >2 numbers)
  - [x] _check_confidence_gap(a, b, subject) → Optional[Contradiction] (gap > 0.5)

### Шаг 4: [x] `brain/cognition/uncertainty_monitor.py` — Мониторинг неопределённости
- [x] UncertaintySnapshot dataclass (confidence, trend:str, delta, iteration, should_stop, should_escalate)
- [x] UncertaintyMonitor class:
  - [x] __init__(window_size=5, stagnation_threshold=0.02, escalation_count=3)
  - [x] update(state: ReasoningState) → UncertaintySnapshot
  - [x] get_trend() → UncertaintyTrend
  - [x] should_early_stop() → bool (stagnation >= window_size)
  - [x] should_escalate() → bool (falling >= escalation_count)
  - [x] reset() — между reasoning runs
  - [x] Каноническая величина: current_confidence

### Шаг 5: [x] `brain/cognition/hypothesis_engine.py` — Causal + Analogical + Budget
- [x] _generate_causal(query, evidence) → List[Hypothesis]
  - [x] Temporal/causal markers: "потому что", "из-за", "вызывает", "because", "therefore"
  - [x] Нужно ≥2 evidence с causal связью к общему concept
  - [x] strategy="causal"
- [x] _generate_analogical(query, evidence) → List[Hypothesis]
  - [x] Cross-domain: разные memory_type или разные concept_refs
  - [x] strategy="analogical"
- [x] Budget: max_hypotheses_total=3, max_per_strategy=2
- [x] _deduplicate(hypotheses) → List[Hypothesis] (normalized statement, keep first)
- [x] Deterministic tie-breaking сохранён

### Шаг 6: [x] `brain/cognition/planner.py` — Полный replan()
- [x] _select_strategy(failure, used_strategies) → Optional[ReplanStrategy]
  - [x] RETRIEVAL_FAILED → BROADEN_SCOPE
  - [x] NO_HYPOTHESIS_GENERATED → DECOMPOSE
  - [x] INSUFFICIENT_CONFIDENCE → NARROW_SCOPE
  - [x] RESOURCE_BLOCKED → ESCALATE
  - [x] default → RETRY
  - [x] Skip already used strategies
- [x] replan() с 5 стратегиями:
  - [x] RETRY: тот же план
  - [x] NARROW_SCOPE: убрать explore шаги
  - [x] BROADEN_SCOPE: добавить дополнительный retrieve
  - [x] DECOMPOSE: разбить на 2 подплана (depth limit=1)
  - [x] ESCALATE: return None
- [x] Защита от циклов:
  - [x] max_total_replans=3 (глобальный ceiling)
  - [x] used_strategies: Set[ReplanStrategy]
  - [x] Запрет повтора стратегии
  - [x] DECOMPOSE depth limit=1

### Шаг 7: [x] `brain/cognition/reasoner.py` — Интеграция
- [x] Добавить optional параметры: retrieval_adapter, contradiction_detector, uncertainty_monitor
- [x] Обратная совместимость: fallback на старый код если adapter не передан
- [x] reason(..., max_iterations=3) — явный параметр
- [x] uncertainty_monitor.reset() в начале каждого run
- [x] Цикл:
  1. retrieve (через adapter если есть)
  2. detect contradictions → flag_evidence (copy-on-write)
  3. generate hypotheses
  4. score (contradiction_flags теперь заполнены!)
  5. select best
  6. update uncertainty monitor
  7. check stop + check should_early_stop/should_escalate
- [x] Uncertainty info в ReasoningTrace.metadata

### Шаг 8: [x] `brain/cognition/cognitive_core.py` — Wiring
- [x] Создать KeywordRetrievalBackend + RetrievalAdapter в __init__
- [x] Создать ContradictionDetector + UncertaintyMonitor
- [x] Передать в Reasoner
- [x] Uncertainty/contradiction info в CognitiveResult.metadata

### Шаг 9: [x] `brain/cognition/__init__.py` — Экспорты (+8)
- [x] RetrievalAdapter, KeywordRetrievalBackend
- [x] ContradictionDetector, Contradiction
- [x] UncertaintyMonitor, UncertaintySnapshot
- [x] UncertaintyTrend, ReplanStrategy

### Шаг 10: [ ] `tests/test_cognition_fplus.py` — Unit тесты (~90)
- [ ] TestRetrievalAdapter (~20)
  - [ ] from_working, from_semantic, from_episodic
  - [ ] ranking by relevance
  - [ ] empty results
  - [ ] canonical fields guaranteed (11 fields)
  - [ ] metadata enrichment
- [ ] TestContradictionDetector (~18)
  - [ ] same_subject required (no false positives on unrelated)
  - [ ] negation detection
  - [ ] numeric (>20% diff, skip if >2 numbers)
  - [ ] confidence_gap (>0.5)
  - [ ] flag_evidence returns copies (not mutated)
  - [ ] no contradictions on unrelated numbers
- [ ] TestUncertaintyMonitor (~15)
  - [ ] trend rising/falling/stable/unknown
  - [ ] early_stop after stagnation
  - [ ] escalation after falling
  - [ ] reset between runs
  - [ ] canonical = current_confidence
- [ ] TestCausalHypothesis (~8)
  - [ ] temporal markers found
  - [ ] no causal evidence → no hypothesis
  - [ ] strategy="causal"
  - [ ] budget respected
- [ ] TestAnalogicalHypothesis (~8)
  - [ ] cross-domain evidence
  - [ ] no analogies → no hypothesis
  - [ ] strategy="analogical"
  - [ ] budget respected
- [ ] TestReplanStrategies (~14)
  - [ ] each strategy works
  - [ ] select_strategy mapping
  - [ ] max_total_replans=3
  - [ ] no cycle (used_strategies)
  - [ ] DECOMPOSE depth=1
- [ ] TestHypothesisBudget (~4)
  - [ ] max_total=3
  - [ ] max_per_strategy=2
  - [ ] dedup by normalized statement
- [ ] TestImports (~3)

### Шаг 11: [ ] `tests/test_cognition_integration.py` — Integration (+5)
- [ ] RetrievalAdapter with real MemoryManager
- [ ] ContradictionDetector flags reduce hypothesis score
- [ ] UncertaintyMonitor reset between runs
- [ ] Causal hypothesis from temporal evidence
- [ ] Full replan with strategy selection (no infinite loop)

### Шаг 12: [ ] Финальная проверка
- [ ] `pytest tests/ -v` — все тесты (~706 total)
- [ ] pyproject.toml → v0.7.0
- [ ] README.md обновлён
- [ ] docs/TODO.md — F+ ✅
- [ ] Коммит + push

---

## Принятые решения

1. UncertaintyMonitor: Reasoner.reason(max_iterations=3), reset() в начале, проверки между итерациями
2. ContradictionDetector: _same_subject() через concept_refs overlap — обязательное условие
3. _check_numeric(): skip if >2 numbers в evidence, порог >20%
4. flag_evidence(): copy-on-write (возвращает новые EvidencePack, не мутирует)
5. RetrievalAdapter: канонический набор 11 полей EvidencePack гарантирован
6. HypothesisEngine: max_total=3, max_per_strategy=2, dedup, deterministic
7. replan(): max_total_replans=3, used_strategies set, DECOMPOSE depth=1, no repeat
8. UncertaintySnapshot.trend: str (не enum — безопаснее с ContractMixin.from_dict())
9. Contradiction/UncertaintySnapshot — в своих файлах (не раздувать context.py)
10. Обратная совместимость в Reasoner: fallback на старый код если adapter не передан

## Что НЕ входит в F+ (отложено)

- Vector retrieval backend (только interface/hook)
- Full cross-modal ContradictionDetector (→ Stage K)
- ProceduralMemory integration в replan (→ Stage I)
- Ring 2 deep reasoning (→ Stage H)
- LLM bridge (→ Stage N)
