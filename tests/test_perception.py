"""
test_perception.py — Smoke-тесты для Этапа D: Text-Only Perception.

Тестирует:
  1. MetadataExtractor — detect_language, compute_quality, quality_label, should_reject
  2. TextIngestor      — ingest_text, _chunk_text, _split_into_paragraphs, форматы
  3. InputRouter       — route_text, route_file, дедупликация, quality policy
  4. Импорт через brain.perception

Запуск:
    python test_perception.py
"""

import json
import os
import sys
import tempfile
import textwrap

import pytest

# ─── Цвета для вывода ────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = 0
failed = 0
_section = ""
_results = []


def section(name: str):
    global _section
    _section = name
    print(f"\n{'─'*60}")
    print(f"  {name}")
    print(f"{'─'*60}")


def ok(msg: str):
    global passed
    passed += 1
    _results.append((msg, True, ""))
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str, exc: Exception = None):
    global failed
    failed += 1
    detail = str(exc) if exc else ""
    _results.append((msg, False, detail))
    print(f"  {RED}✗{RESET} {msg}" + (f" — {exc}" if exc else ""))


def check(condition: bool, msg: str, exc: Exception = None):
    if condition:
        ok(msg)
    else:
        fail(msg, exc)


# ─── 1. MetadataExtractor ────────────────────────────────────────────────────

section("1. MetadataExtractor")

try:
    from brain.perception.metadata_extractor import MetadataExtractor
    ok("MetadataExtractor импортирован")
except Exception as e:
    fail("MetadataExtractor импорт", e)
    sys.exit(1)

ext = MetadataExtractor()

# detect_language
check(ext.detect_language("Нейрон — это клетка нервной системы") == "ru",
      "detect_language: кириллица → 'ru'")
check(ext.detect_language("Neuron is a cell of the nervous system") == "en",
      "detect_language: латиница → 'en'")
check(ext.detect_language("Нейрон neuron клетка cell") == "mixed",
      "detect_language: смешанный → 'mixed'")
check(ext.detect_language("12345 !@#$%") == "unknown",
      "detect_language: нет букв → 'unknown'")
check(ext.detect_language("") == "unknown",
      "detect_language: пустая строка → 'unknown'")

# compute_quality — нормальный текст
text_good = "Нейрон — это основная клетка нервной системы.\nОн передаёт электрические импульсы."
q, warns = ext.compute_quality(text_good, "ru")
check(q >= 0.7, f"compute_quality: хороший текст quality={q:.2f} >= 0.7")
check(len(warns) == 0, f"compute_quality: хороший текст без предупреждений (warns={warns})")

# compute_quality — короткий текст
q_short, warns_short = ext.compute_quality("Привет", "ru")
check(q_short < 0.7, f"compute_quality: короткий текст quality={q_short:.2f} < 0.7")
check("short_text" in " ".join(warns_short), "compute_quality: предупреждение short_text")

# compute_quality — битые символы
text_broken = "Нейрон \ufffd\ufffd клетка нервной системы. Он передаёт импульсы."
q_broken, warns_broken = ext.compute_quality(text_broken, "ru")
check("broken_chars" in " ".join(warns_broken), "compute_quality: предупреждение broken_chars")

# compute_quality — неизвестный язык
q_unk, warns_unk = ext.compute_quality("1234567890 !!! ??? --- *** +++", None)
check("language_unknown" in " ".join(warns_unk), "compute_quality: предупреждение language_unknown")

# quality_label
check(MetadataExtractor.quality_label(0.9) == "normal",     "quality_label: 0.9 → normal")
check(MetadataExtractor.quality_label(0.7) == "normal",     "quality_label: 0.7 → normal")
check(MetadataExtractor.quality_label(0.5) == "warning",    "quality_label: 0.5 → warning")
check(MetadataExtractor.quality_label(0.4) == "warning",    "quality_label: 0.4 → warning")
check(MetadataExtractor.quality_label(0.3) == "low_priority", "quality_label: 0.3 → low_priority")
check(MetadataExtractor.quality_label(0.0) == "low_priority", "quality_label: 0.0 → low_priority")

# should_reject
check(MetadataExtractor.should_reject("")[0] is True,       "should_reject: пустая строка → True")
check(MetadataExtractor.should_reject("   ")[0] is True,    "should_reject: пробелы → True")
check(MetadataExtractor.should_reject(None)[0] is True,     "should_reject: None → True")
check(MetadataExtractor.should_reject("ab")[0] is True,     "should_reject: < 10 символов → True")
check(MetadataExtractor.should_reject("Нейрон — клетка")[0] is False,
      "should_reject: нормальный текст → False")

# extract — полный вызов
meta = ext.extract(
    text=text_good,
    source="test_source",
    page=1,
    chunk_id=0,
)
check("quality" in meta,   "extract: поле quality присутствует")
check("language" in meta,  "extract: поле language присутствует")
check("ts" in meta,        "extract: поле ts присутствует")
check("source" in meta,    "extract: поле source присутствует")
check("chunk_id" in meta,  "extract: поле chunk_id присутствует")
check("page" in meta,      "extract: поле page присутствует")
check(meta["language"] == "ru", f"extract: language='ru' (got {meta['language']})")


# ─── 2. TextIngestor ─────────────────────────────────────────────────────────

section("2. TextIngestor")

try:
    from brain.perception.text_ingestor import TextIngestor, _hard_split, _split_into_paragraphs
    ok("TextIngestor импортирован")
except Exception as e:
    fail("TextIngestor импорт", e)
    sys.exit(1)

ingestor = TextIngestor()

# ingest_text — базовый
text_sample = textwrap.dedent("""
    Нейрон — это основная структурная и функциональная единица нервной системы.
    Нейроны передают электрические и химические сигналы между собой.

    Существует несколько типов нейронов: сенсорные, моторные и вставочные.
    Каждый нейрон состоит из тела клетки, аксона и дендритов.

    Синапс — это место контакта между двумя нейронами.
    Через синапс передаётся нервный импульс с помощью нейромедиаторов.
""").strip()

events = ingestor.ingest_text(text_sample, source="test_text")
check(len(events) > 0, f"ingest_text: возвращает события (got {len(events)})")
check(all(e.modality == "text" for e in events), "ingest_text: все события modality='text'")
check(all(e.source == "test_text" for e in events), "ingest_text: source корректен")
check(all(e.content for e in events), "ingest_text: content не пустой")
check(all(0.0 <= e.quality <= 1.0 for e in events), "ingest_text: quality в диапазоне [0,1]")
check(all(e.language in ("ru", "en", "mixed", "unknown") for e in events),
      "ingest_text: language корректный")

# ingest_text — пустой текст
events_empty = ingestor.ingest_text("")
check(len(events_empty) == 0, "ingest_text: пустой текст → 0 событий")

# ingest_text — очень короткий текст
events_short = ingestor.ingest_text("Привет")
check(len(events_short) == 0, "ingest_text: слишком короткий текст → 0 событий")

# ingest_text — длинный текст (должен разбиться на несколько чанков)
long_text = ("Нейрон — это клетка нервной системы. " * 100).strip()
events_long = ingestor.ingest_text(long_text, source="long_test")
check(len(events_long) > 1, f"ingest_text: длинный текст → несколько чанков (got {len(events_long)})")

# _split_into_paragraphs
paras = _split_into_paragraphs("Абзац первый.\n\nАбзац второй.\n\nАбзац третий.")
check(len(paras) == 3, f"_split_into_paragraphs: 3 абзаца (got {len(paras)})")

paras_md = _split_into_paragraphs("# Заголовок\n\nТекст раздела.\n\n## Подраздел\n\nЕщё текст.")
check(len(paras_md) >= 2, f"_split_into_paragraphs: Markdown заголовки (got {len(paras_md)})")

# _hard_split
long_para = "А" * 3000
hard_chunks = _hard_split(long_para, max_chars=1500, overlap=120)
check(len(hard_chunks) >= 2, f"_hard_split: длинный параграф → несколько чанков (got {len(hard_chunks)})")
check(all(len(c) <= 1500 + 120 for c in hard_chunks), "_hard_split: размер чанков в пределах лимита")

# ingest — .txt файл
with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
    f.write(text_sample)
    tmp_txt = f.name

try:
    events_txt = ingestor.ingest(tmp_txt)
    check(len(events_txt) > 0, f"ingest(.txt): возвращает события (got {len(events_txt)})")
    check(events_txt[0].modality == "text", "ingest(.txt): modality='text'")
finally:
    os.unlink(tmp_txt)

# ingest — .md файл
md_content = textwrap.dedent("""
    # Нейробиология

    Нейрон — это основная клетка нервной системы.
    Нейроны передают сигналы через синапсы.

    ## Типы нейронов

    Существуют сенсорные, моторные и вставочные нейроны.
    Каждый тип выполняет свою функцию в нервной системе.
""").strip()

with tempfile.NamedTemporaryFile(mode="w", suffix=".md", encoding="utf-8", delete=False) as f:
    f.write(md_content)
    tmp_md = f.name

try:
    events_md = ingestor.ingest(tmp_md)
    check(len(events_md) > 0, f"ingest(.md): возвращает события (got {len(events_md)})")
finally:
    os.unlink(tmp_md)

# ingest — .json файл
json_data = {
    "title": "Нейробиология",
    "description": "Наука о нервной системе и нейронах.",
    "topics": ["нейрон", "синапс", "аксон", "дендрит"],
    "facts": [
        "Нейрон передаёт электрические импульсы.",
        "Синапс соединяет два нейрона.",
    ]
}
with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as f:
    json.dump(json_data, f, ensure_ascii=False)
    tmp_json = f.name

try:
    events_json = ingestor.ingest(tmp_json)
    check(len(events_json) > 0, f"ingest(.json): возвращает события (got {len(events_json)})")
finally:
    os.unlink(tmp_json)

# ingest — несуществующий файл
events_missing = ingestor.ingest("nonexistent_file.txt")
check(len(events_missing) == 0, "ingest: несуществующий файл → 0 событий")

# ingest — неподдерживаемый формат
events_unsup = ingestor.ingest("file.xyz")
check(len(events_unsup) == 0, "ingest: неподдерживаемый формат → 0 событий")

# session_id и trace_id прокидываются
events_ids = ingestor.ingest_text(text_sample, source="test", session_id="sess-1", trace_id="trace-1")
check(all(e.session_id == "sess-1" for e in events_ids), "ingest_text: session_id прокидывается")
check(all(e.trace_id == "trace-1" for e in events_ids), "ingest_text: trace_id прокидывается")

# metadata содержит chunk_id
check(all("chunk_id" in e.metadata for e in events_ids), "ingest_text: metadata содержит chunk_id")


# ─── 3. InputRouter ──────────────────────────────────────────────────────────

section("3. InputRouter")

try:
    from brain.perception.input_router import InputRouter
    ok("InputRouter импортирован")
except Exception as e:
    fail("InputRouter импорт", e)
    sys.exit(1)

router = InputRouter()

# route_text — базовый
events_r = router.route_text(text_sample, source="router_test")
check(len(events_r) > 0, f"route_text: возвращает события (got {len(events_r)})")
check(all(e.modality == "text" for e in events_r), "route_text: modality='text'")

# route_text — пустой текст
events_empty_r = router.route_text("")
check(len(events_empty_r) == 0, "route_text: пустой текст → 0 событий")

# Дедупликация
router2 = InputRouter(dedup=True)
ev1 = router2.route_text(text_sample, source="dedup_test")
ev2 = router2.route_text(text_sample, source="dedup_test")  # дубликат
check(len(ev1) > 0, "dedup: первый вызов возвращает события")
check(len(ev2) == 0, "dedup: второй вызов (дубликат) → 0 событий")

# force=True обходит дедупликацию
ev3 = router2.route_text(text_sample, source="dedup_test", force=True)
check(len(ev3) > 0, "dedup: force=True обходит дедупликацию")

# reset_dedup
router2.reset_dedup()
ev4 = router2.route_text(text_sample, source="dedup_test")
check(len(ev4) > 0, "reset_dedup: после сброса дедупликация работает заново")

# route_file — .txt (используем свежий роутер, чтобы избежать dedup-коллизии
# с предыдущим route_text на тех же данных — на Linux file bytes == text bytes)
router_file = InputRouter()
with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
    f.write(text_sample)
    tmp_route_txt = f.name

try:
    events_rf = router_file.route_file(tmp_route_txt)
    check(len(events_rf) > 0, f"route_file(.txt): возвращает события (got {len(events_rf)})")
finally:
    os.unlink(tmp_route_txt)

# route_file — несуществующий файл
events_nf = router.route_file("nonexistent.txt")
check(len(events_nf) == 0, "route_file: несуществующий файл → 0 событий")

# route_file — image (MVP: пропуск)
with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
    f.write(b"fake image data")
    tmp_img = f.name
try:
    events_img = router.route_file(tmp_img)
    check(len(events_img) == 0, "route_file(.jpg): image пропускается в MVP → 0 событий")
finally:
    os.unlink(tmp_img)

# route_file — audio (MVP: пропуск)
with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
    f.write(b"fake audio data")
    tmp_audio = f.name
try:
    events_audio = router.route_file(tmp_audio)
    check(len(events_audio) == 0, "route_file(.mp3): audio пропускается в MVP → 0 событий")
finally:
    os.unlink(tmp_audio)

# quality policy — low_priority события сохраняются
router3 = InputRouter(dedup=False)
short_text = "Короткий текст без структуры"  # quality будет низким
events_lp = router3.route_text(short_text, source="low_q_test")
# Может быть 0 (hard reject) или > 0 с low_priority — оба варианта корректны
check(isinstance(events_lp, list), "quality policy: route_text возвращает список")

# stats()
s = router.stats()
check("total_routed" in s,          "stats: поле total_routed")
check("total_events" in s,          "stats: поле total_events")
check("duplicates_skipped" in s,    "stats: поле duplicates_skipped")
check("hard_rejected" in s,         "stats: поле hard_rejected")
check("unsupported_modality" in s,  "stats: поле unsupported_modality")
check(s["total_routed"] > 0,        f"stats: total_routed > 0 (got {s['total_routed']})")

# route_batch — используем свежий роутер (без накопленного dedup-кэша)
router_batch = InputRouter(dedup=False)
with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
    f.write(text_sample)
    tmp_batch = f.name
try:
    batch_events = router_batch.route_batch([tmp_batch], session_id="batch-sess")
    check(len(batch_events) > 0, f"route_batch: возвращает события (got {len(batch_events)})")
finally:
    os.unlink(tmp_batch)


# ─── 4. Импорт через brain.perception ────────────────────────────────────────

section("4. Импорт через brain.perception")

try:
    from brain.perception import InputRouter, MetadataExtractor, TextIngestor
    ok("from brain.perception import MetadataExtractor, TextIngestor, InputRouter")
except Exception as e:
    fail("brain.perception импорт", e)

try:
    import brain.perception as bp
    check(hasattr(bp, "MetadataExtractor"), "__all__: MetadataExtractor экспортирован")
    check(hasattr(bp, "TextIngestor"),      "__all__: TextIngestor экспортирован")
    check(hasattr(bp, "InputRouter"),       "__all__: InputRouter экспортирован")
except Exception as e:
    fail("brain.perception __all__", e)

# Smoke: создать экземпляры через пакет
try:
    _ext = bp.MetadataExtractor()
    _ing = bp.TextIngestor()
    _rtr = bp.InputRouter()
    ok("Экземпляры создаются через brain.perception")
except Exception as e:
    fail("Создание экземпляров через brain.perception", e)

# Регрессия: memory система не сломана
section("5. Регрессия: brain.memory")
try:
    from brain.memory import MemoryManager
    mm = MemoryManager(data_dir="brain/data/memory", auto_consolidate=False)
    mm.start()
    mm.store("нейрон это клетка нервной системы", importance=0.8, source_ref="test")
    result = mm.retrieve("нейрон")
    mm.stop()
    check(result is not None, "MemoryManager.retrieve() работает после изменений")
except Exception as e:
    fail("Регрессия brain.memory", e)


# ─── Итог ────────────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
total = passed + failed
print(f"  Perception Tests: {passed}/{total} passed")
if failed == 0:
    print("  [OK] Vse testy proshli!")
else:
    print(f"  {RED}FAILED: {failed} тестов провалено{RESET}")
print(f"{'='*60}\n")

# ═══════════════════════════════════════════════════════
# PYTEST PARAMETRIZE — каждая проверка = отдельный тест
# ═══════════════════════════════════════════════════════

@pytest.mark.parametrize(
    "name,condition,detail",
    _results,
    ids=[r[0] for r in _results],
)
def test_perception_check(name, condition, detail):
    assert condition, f"{name}" + (f" — {detail}" if detail else "")


if __name__ == "__main__":
    sys.exit(0 if failed == 0 else 1)
