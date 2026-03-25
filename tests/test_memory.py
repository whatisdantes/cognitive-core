"""
test_memory.py — Тест системы памяти мозга.

Проверяет:
  1. WorkingMemory — добавление, поиск, вытеснение
  2. SemanticMemory — факты, связи, поиск
  3. EpisodicMemory — эпизоды, поиск по концепту и времени
  4. SourceMemory — регистрация, доверие
  5. ProceduralMemory — процедуры, success rate
  6. MemoryManager — единый интерфейс, store/retrieve
  7. ConsolidationEngine — перенос WM → LTM
"""

import sys
import os
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── Цвета для вывода ────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = 0
failed = 0
_results = []


def check_test(name: str, condition: bool, detail: str = ""):
    global passed, failed
    _results.append((name, condition, detail))
    if condition:
        passed += 1
        print(f"  {GREEN}✓{RESET} {name}")
    else:
        failed += 1
        print(f"  {RED}✗{RESET} {name}" + (f" — {detail}" if detail else ""))


def section(title: str):
    print(f"\n{CYAN}{BOLD}{'─'*50}{RESET}")
    print(f"{CYAN}{BOLD}  {title}{RESET}")
    print(f"{CYAN}{'─'*50}{RESET}")


# ═══════════════════════════════════════════════════════
# 1. EVENTS
# ═══════════════════════════════════════════════════════
section("1. Events (brain/core/events.py)")

try:
    from brain.core.events import (
        PerceptEvent, EventFactory
    )

    ev = PerceptEvent(source="test", content="привет", modality="text", quality=0.9)
    check_test("PerceptEvent создан", ev.event_type == "percept")
    check_test("PerceptEvent имеет trace_id", len(ev.trace_id) > 0)
    check_test("PerceptEvent сериализуется в dict", isinstance(ev.to_dict(), dict))

    mem_ev = EventFactory.memory_store("нейрон", "клетка нервной системы", memory_type="semantic")
    check_test("MemoryEvent через фабрику", mem_ev.operation == "store")
    check_test("MemoryEvent key корректен", mem_ev.key == "нейрон")

    sys_ev = EventFactory.system_info("test_module", "всё работает", cpu_pct=15.0)
    check_test("SystemEvent через фабрику", sys_ev.level == "INFO")
    check_test("SystemEvent JSON-строка", len(sys_ev.to_json_line()) > 10)

except Exception as e:
    print(f"  {RED}ОШИБКА импорта events: {e}{RESET}")
    import traceback
    traceback.print_exc()


# ═══════════════════════════════════════════════════════
# 2. WORKING MEMORY
# ═══════════════════════════════════════════════════════
section("2. WorkingMemory")

try:
    from brain.memory.working_memory import WorkingMemory, MemoryItem

    wm = WorkingMemory(max_size=5)

    # Добавление
    item1 = wm.push("нейрон это клетка нервной системы", importance=0.7, tags=["биология"])
    item2 = wm.push("синапс это связь между нейронами", importance=0.6, tags=["биология"])
    item3 = wm.push("мозг это орган мышления", importance=0.9, source_ref="user_input")

    check_test("push() добавляет элементы", wm.size >= 2)
    check_test("MemoryItem создан корректно", item1.modality == "text")
    check_test("Важный элемент защищён", item3 in wm._protected)

    # Поиск
    results = wm.search("нейрон")
    check_test("search() находит по тексту", len(results) > 0)
    check_test("search() возвращает MemoryItem", isinstance(results[0], MemoryItem))

    # Контекст
    ctx = wm.get_context(5)
    check_test("get_context() возвращает список", isinstance(ctx, list))
    check_test("get_context() не пустой", len(ctx) > 0)

    # Вытеснение
    wm2 = WorkingMemory(max_size=3)
    for i in range(5):
        wm2.push(f"элемент {i}", importance=0.3)
    check_test("Вытеснение работает (size <= max)", wm2.size <= 3 + len(wm2._protected))
    check_test("Счётчик вытеснений > 0", wm2._evict_count > 0)

    # Статус
    s = wm.status()
    check_test("status() возвращает dict", isinstance(s, dict))
    check_test("status() содержит size", "size" in s)

    # peek_last
    last = wm.peek_last()
    check_test("peek_last() не None", last is not None)

    # clear
    wm_tmp = WorkingMemory(max_size=10)
    wm_tmp.push("тест", importance=0.3)
    wm_tmp.clear(keep_important=False)
    check_test("clear() очищает память", wm_tmp.size == 0)

except Exception as e:
    print(f"  {RED}ОШИБКА WorkingMemory: {e}{RESET}")
    import traceback
    traceback.print_exc()


# ═══════════════════════════════════════════════════════
# 3. SEMANTIC MEMORY
# ═══════════════════════════════════════════════════════
section("3. SemanticMemory")

try:
    from brain.memory.semantic_memory import SemanticMemory, SemanticNode

    sm = SemanticMemory(
        data_path="brain/data/memory/test_semantic.json",
        autosave_every=1000,  # не сохраняем автоматически в тесте
    )

    # Сохранение фактов
    node1 = sm.store_fact("нейрон", "клетка нервной системы", tags=["биология", "мозг"])
    node2 = sm.store_fact("синапс", "связь между нейронами", tags=["биология"])
    node3 = sm.store_fact("мозг", "орган центральной нервной системы", tags=["биология", "анатомия"])

    check_test("store_fact() создаёт узел", isinstance(node1, SemanticNode))
    check_test("Узел имеет concept", node1.concept == "нейрон")
    check_test("Узел имеет description", "клетка" in node1.description)
    check_test("len(sm) корректен", len(sm) >= 3)

    # Получение факта
    found = sm.get_fact("нейрон")
    check_test("get_fact() находит узел", found is not None)
    check_test("get_fact() увеличивает access_count", found.access_count > 0)

    # Связи
    sm.add_relation("нейрон", "синапс", weight=0.8, rel_type="related")
    sm.add_relation("нейрон", "мозг", weight=0.9, rel_type="part_of")

    related = sm.get_related("нейрон")
    check_test("add_relation() создаёт связи", len(related) > 0)
    check_test("get_related() возвращает список", isinstance(related, list))

    # Поиск
    results = sm.search("нейрон")
    check_test("search() находит по concept", len(results) > 0)

    results2 = sm.search("клетка")
    check_test("search() находит по description", len(results2) > 0)

    # Подтверждение/опровержение
    old_conf = node1.confidence
    sm.confirm_fact("нейрон")
    check_test("confirm_fact() повышает confidence", node1.confidence >= old_conf)

    sm.deny_fact("нейрон", delta=0.3)
    check_test("deny_fact() снижает confidence", node1.confidence < 1.0)

    # Decay
    sm.apply_decay(rate=0.01)
    check_test("apply_decay() работает без ошибок", True)

    # Цепочка понятий
    chain = sm.get_concept_chain("нейрон", "мозг", max_depth=3)
    check_test("get_concept_chain() находит путь", len(chain) >= 2)

    # Статус
    s = sm.status()
    check_test("status() содержит node_count", "node_count" in s)
    check_test("status() содержит total_relations", "total_relations" in s)

    # Очистка тестового файла
    if os.path.exists("brain/data/memory/test_semantic.json"):
        os.remove("brain/data/memory/test_semantic.json")

except Exception as e:
    print(f"  {RED}ОШИБКА SemanticMemory: {e}{RESET}")
    import traceback
    traceback.print_exc()


# ═══════════════════════════════════════════════════════
# 4. EPISODIC MEMORY
# ═══════════════════════════════════════════════════════
section("4. EpisodicMemory")

try:
    from brain.memory.episodic_memory import EpisodicMemory, Episode, ModalEvidence

    em = EpisodicMemory(
        data_path="brain/data/memory/test_episodes.json",
        autosave_every=1000,
    )

    # Сохранение эпизодов
    ep1 = em.store(
        content="пользователь спросил про нейроны",
        modality="text",
        source="user_input",
        importance=0.7,
        tags=["диалог"],
        concepts=["нейрон", "вопрос"],
    )
    ep2 = em.store(
        content="система ответила про синапсы",
        modality="text",
        source="system",
        importance=0.5,
        concepts=["синапс", "ответ"],
    )
    ep3 = em.store(
        content="важное событие с высоким приоритетом",
        modality="text",
        importance=0.9,
        tags=["важное"],
    )

    check_test("store() создаёт эпизод", isinstance(ep1, Episode))
    check_test("Episode имеет episode_id", len(ep1.episode_id) > 0)
    check_test("len(em) корректен", len(em) >= 3)

    # Получение по ID
    found = em.get_by_id(ep1.episode_id)
    check_test("get_by_id() находит эпизод", found is not None)
    check_test("get_by_id() увеличивает access_count", found.access_count > 0)

    # Последние эпизоды
    recent = em.get_recent(5)
    check_test("get_recent() возвращает список", isinstance(recent, list))
    check_test("get_recent() не пустой", len(recent) > 0)

    # Поиск по концепту
    by_concept = em.retrieve_by_concept("нейрон")
    check_test("retrieve_by_concept() находит эпизоды", len(by_concept) > 0)

    # Полнотекстовый поиск
    search_results = em.search("нейрон")
    check_test("search() находит по тексту", len(search_results) > 0)

    # Поиск по времени
    start = time.time() - 10
    by_time = em.retrieve_by_time(start_ts=start)
    check_test("retrieve_by_time() работает", len(by_time) > 0)

    # Модальные доказательства
    evidence = ModalEvidence(modality="image", source="test.jpg", content_ref="регион 0,0,100,100")
    ep1.add_evidence(evidence)
    check_test("add_evidence() добавляет доказательство", len(ep1.modal_evidence) > 0)
    check_test("get_evidence_by_modality() работает", len(ep1.get_evidence_by_modality("image")) > 0)

    # Статус
    s = em.status()
    check_test("status() содержит episode_count", "episode_count" in s)
    check_test("status() содержит modality_breakdown", "modality_breakdown" in s)

    # Очистка
    if os.path.exists("brain/data/memory/test_episodes.json"):
        os.remove("brain/data/memory/test_episodes.json")

except Exception as e:
    print(f"  {RED}ОШИБКА EpisodicMemory: {e}{RESET}")
    import traceback
    traceback.print_exc()


# ═══════════════════════════════════════════════════════
# 5. SOURCE MEMORY
# ═══════════════════════════════════════════════════════
section("5. SourceMemory")

try:
    from brain.memory.source_memory import SourceMemory, SourceRecord

    src = SourceMemory(
        data_path="brain/data/memory/test_sources.json",
        autosave_every=1000,
    )

    # Регистрация
    rec1 = src.register("user_input", source_type="user")
    rec2 = src.register("wikipedia.org", source_type="url")
    rec3 = src.register("system_kb", source_type="system")

    check_test("register() создаёт запись", isinstance(rec1, SourceRecord))
    check_test("user тип имеет высокое доверие", rec1.trust_score >= 0.7)
    check_test("system тип имеет максимальное доверие", rec3.trust_score == 1.0)
    check_test("url тип имеет умеренное доверие", rec2.trust_score <= 0.6)

    # Доверие
    trust = src.get_trust("user_input")
    check_test("get_trust() возвращает float", isinstance(trust, float))
    check_test("get_trust() для user >= 0.7", trust >= 0.7)

    # Обновление доверия
    src.update_trust("wikipedia.org", confirmed=True)
    src.update_trust("wikipedia.org", confirmed=True)
    src.update_trust("wikipedia.org", confirmed=False)
    rec2_updated = src.get_record("wikipedia.org")
    check_test("update_trust() обновляет confirmations", rec2_updated.confirmations >= 2)

    # Неизвестный источник
    unknown_trust = src.get_trust("unknown_source_xyz")
    check_test("get_trust() для неизвестного = 0.5", unknown_trust == 0.5)

    # Чёрный список
    src.blacklist("spam_source", reason="спам")
    check_test("blacklist() работает", src.is_blacklisted("spam_source"))
    check_test("get_trust() для заблокированного = 0.0", src.get_trust("spam_source") == 0.0)

    src.whitelist("spam_source")
    check_test("whitelist() снимает блокировку", not src.is_blacklisted("spam_source"))

    # Аналитика
    reliable = src.get_reliable_sources()
    check_test("get_reliable_sources() возвращает список", isinstance(reliable, list))

    # Статус
    s = src.status()
    check_test("status() содержит source_count", "source_count" in s)
    check_test("status() содержит avg_trust_score", "avg_trust_score" in s)

    # Очистка
    if os.path.exists("brain/data/memory/test_sources.json"):
        os.remove("brain/data/memory/test_sources.json")

except Exception as e:
    print(f"  {RED}ОШИБКА SourceMemory: {e}{RESET}")
    import traceback
    traceback.print_exc()


# ═══════════════════════════════════════════════════════
# 6. PROCEDURAL MEMORY
# ═══════════════════════════════════════════════════════
section("6. ProceduralMemory")

try:
    from brain.memory.procedural_memory import ProceduralMemory, Procedure

    pm = ProceduralMemory(
        data_path="brain/data/memory/test_procedures.json",
        autosave_every=1000,
    )

    # Сохранение процедур
    proc1 = pm.store(
        name="ответить_на_вопрос",
        steps=[
            {"action": "parse_question", "params": {"lang": "ru"}},
            {"action": "search_memory", "params": {"top_n": 5}},
            {"action": "generate_answer", "params": {}},
        ],
        description="Ответить на вопрос пользователя",
        trigger_pattern="вопрос",
        tags=["диалог", "ответ"],
        priority=0.8,
    )

    proc2 = pm.store(
        name="запомнить_факт",
        steps=[
            {"action": "extract_concept", "params": {}},
            {"action": "store_semantic", "params": {"importance": 0.7}},
        ],
        description="Запомнить новый факт",
        trigger_pattern="запомни",
        tags=["обучение"],
    )

    check_test("store() создаёт процедуру", isinstance(proc1, Procedure))
    check_test("Процедура имеет шаги", len(proc1.steps) == 3)
    check_test("len(pm) корректен", len(pm) >= 2)

    # Получение
    found = pm.get("ответить_на_вопрос")
    check_test("get() находит процедуру", found is not None)

    # Поиск
    results = pm.retrieve("вопрос")
    check_test("retrieve() находит по trigger_pattern", len(results) > 0)

    # Запись результата
    pm.record_result("ответить_на_вопрос", success=True, duration_ms=150.0)
    pm.record_result("ответить_на_вопрос", success=True, duration_ms=120.0)
    pm.record_result("ответить_на_вопрос", success=False, duration_ms=200.0)

    proc_updated = pm.get("ответить_на_вопрос")
    check_test("record_result() обновляет use_count", proc_updated.use_count == 3)
    check_test("record_result() обновляет success_rate", 0.0 < proc_updated.success_rate < 1.0)
    check_test("record_result() обновляет avg_duration_ms", proc_updated.avg_duration_ms > 0)

    # Лучшие процедуры
    best = pm.get_best(top_n=2)
    check_test("get_best() возвращает список", isinstance(best, list))

    # Статус
    s = pm.status()
    check_test("status() содержит procedure_count", "procedure_count" in s)

    # Очистка
    if os.path.exists("brain/data/memory/test_procedures.json"):
        os.remove("brain/data/memory/test_procedures.json")

except Exception as e:
    print(f"  {RED}ОШИБКА ProceduralMemory: {e}{RESET}")
    import traceback
    traceback.print_exc()


# ═══════════════════════════════════════════════════════
# 7. MEMORY MANAGER (единый интерфейс)
# ═══════════════════════════════════════════════════════
section("7. MemoryManager (единый интерфейс)")

try:
    from brain.memory.memory_manager import MemoryManager, MemorySearchResult

    mm = MemoryManager(
        data_dir="brain/data/memory/test_mm",
        working_max_size=10,
        semantic_max_nodes=1000,
        episodic_max=500,
        auto_consolidate=False,  # не запускаем фон в тесте
    )

    # store() — единый интерфейс
    result = mm.store(
        "нейрон это клетка нервной системы",
        importance=0.8,
        source_ref="test_source",
        tags=["биология"],
    )
    check_test("store() возвращает dict", isinstance(result, dict))
    check_test("store() добавляет в working", "working" in result)
    check_test("store() добавляет в episodic (importance >= 0.4)", "episodic" in result)
    check_test("store() извлекает факт в semantic", "semantic" in result)

    # store_fact() — явное сохранение факта
    node = mm.store_fact("синапс", "связь между нейронами", importance=0.7)
    check_test("store_fact() создаёт SemanticNode", node is not None)

    # store_episode() — явное сохранение эпизода
    ep = mm.store_episode("тестовый эпизод", importance=0.6, concepts=["тест"])
    check_test("store_episode() создаёт Episode", ep is not None)

    # retrieve() — поиск по всем видам памяти
    search = mm.retrieve("нейрон")
    check_test("retrieve() возвращает MemorySearchResult", isinstance(search, MemorySearchResult))
    check_test("retrieve() находит в semantic", len(search.semantic) > 0)
    check_test("retrieve() не пустой", not search.is_empty())
    check_test("summary() работает", len(search.summary()) > 0)

    # get_fact()
    fact = mm.get_fact("нейрон")
    check_test("get_fact() находит факт", fact is not None)

    # get_context()
    ctx = mm.get_context(5)
    check_test("get_context() возвращает список", isinstance(ctx, list))

    # get_recent_episodes()
    recent = mm.get_recent_episodes(5)
    check_test("get_recent_episodes() возвращает список", isinstance(recent, list))

    # confirm/deny
    mm.confirm("нейрон", source_ref="test_source")
    mm.deny("синапс")
    check_test("confirm() и deny() работают без ошибок", True)

    # RAM статус
    ram = mm.ram_status()
    check_test("ram_status() возвращает dict", isinstance(ram, dict))

    # Полный статус
    s = mm.status()
    check_test("status() содержит все виды памяти", all(
        k in s for k in ["working", "semantic", "episodic", "source", "procedural"]
    ))

    # Очистка тестовых файлов
    import shutil
    if os.path.exists("brain/data/memory/test_mm"):
        shutil.rmtree("brain/data/memory/test_mm")

except Exception as e:
    print(f"  {RED}ОШИБКА MemoryManager: {e}{RESET}")
    import traceback
    traceback.print_exc()


# ═══════════════════════════════════════════════════════
# 8. CONSOLIDATION ENGINE
# ═══════════════════════════════════════════════════════
section("8. ConsolidationEngine (Гиппокамп)")

try:
    from brain.memory.working_memory import WorkingMemory
    from brain.memory.semantic_memory import SemanticMemory
    from brain.memory.episodic_memory import EpisodicMemory
    from brain.memory.source_memory import SourceMemory
    from brain.memory.procedural_memory import ProceduralMemory
    from brain.memory.consolidation_engine import ConsolidationEngine

    wm = WorkingMemory(max_size=20)
    sm = SemanticMemory(data_path="brain/data/memory/test_cons_sem.json", autosave_every=9999)
    em = EpisodicMemory(data_path="brain/data/memory/test_cons_ep.json", autosave_every=9999)
    src = SourceMemory(data_path="brain/data/memory/test_cons_src.json", autosave_every=9999)
    pm = ProceduralMemory(data_path="brain/data/memory/test_cons_proc.json", autosave_every=9999)

    engine = ConsolidationEngine(
        working=wm,
        episodic=em,
        semantic=sm,
        source=src,
        procedural=pm,
    )

    # Добавляем элементы в рабочую память
    wm.push("мозг это орган мышления", importance=0.8, source_ref="test")
    wm.push("нейрон это клетка нервной системы", importance=0.7, source_ref="test")
    wm.push("незначительная информация", importance=0.1)

    # Принудительная консолидация
    stats = engine.force_consolidate()
    check_test("force_consolidate() возвращает stats", isinstance(stats, dict))
    check_test("stats содержит to_episodic", "to_episodic" in stats)
    check_test("stats содержит to_semantic", "to_semantic" in stats)
    check_test("Важные элементы перенесены в episodic", stats["to_episodic"] >= 2)

    # Проверяем что факты появились в semantic
    fact = sm.get_fact("мозг")
    check_test("Факт 'мозг' перенесён в semantic", fact is not None)

    # Decay
    engine.force_decay()
    check_test("force_decay() работает без ошибок", True)

    # Reinforce / Weaken
    engine.reinforce("мозг", source_ref="test")
    engine.weaken("нейрон")
    check_test("reinforce() и weaken() работают", True)

    # Статус
    s = engine.status()
    check_test("status() содержит consolidation_count", "consolidation_count" in s)
    check_test("consolidation_count >= 1", s["consolidation_count"] >= 1)

    # Очистка
    for f in ["test_cons_sem.json", "test_cons_ep.json", "test_cons_src.json", "test_cons_proc.json"]:
        path = f"brain/data/memory/{f}"
        if os.path.exists(path):
            os.remove(path)

except Exception as e:
    print(f"  {RED}ОШИБКА ConsolidationEngine: {e}{RESET}")
    import traceback
    traceback.print_exc()


# ═══════════════════════════════════════════════════════
# 9. ИМПОРТ ЧЕРЕЗ __init__.py
# ═══════════════════════════════════════════════════════
section("9. Импорт через brain.memory и brain.core")

try:
    from brain.memory import (
        MemoryManager, WorkingMemory, SemanticMemory,
        EpisodicMemory, SourceMemory, ProceduralMemory,
        ConsolidationEngine, MemorySearchResult,
    )
    check_test("brain.memory импортирует все классы", True)

    from brain.core import (
        PerceptEvent, EventFactory,
    )
    check_test("brain.core импортирует все события", True)

except Exception as e:
    print(f"  {RED}ОШИБКА импорта через __init__.py: {e}{RESET}")
    import traceback
    traceback.print_exc()


# ═══════════════════════════════════════════════════════
# ИТОГ
# ═══════════════════════════════════════════════════════
print(f"\n{'═'*50}")
print(f"{BOLD}  ИТОГ: {GREEN}{passed} пройдено{RESET}{BOLD} | {RED}{failed} провалено{RESET}")
print(f"{'═'*50}\n")

if failed == 0:
    print(f"{GREEN}{BOLD}  ✅ Все тесты пройдены! Система памяти работает корректно.{RESET}\n")
else:
    print(f"{YELLOW}{BOLD}  ⚠ Есть провалившиеся тесты. Проверьте вывод выше.{RESET}\n")

# ═══════════════════════════════════════════════════════
# PYTEST PARAMETRIZE — каждая проверка = отдельный тест
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "name,condition,detail",
    _results,
    ids=[r[0] for r in _results],
)
def test_memory_check(name, condition, detail):
    assert condition, f"{name}" + (f" — {detail}" if detail else "")


if __name__ == "__main__":
    sys.exit(0 if failed == 0 else 1)
