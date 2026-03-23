"""
test_logging.py — Тесты Этапа C: Logging & Observability.

Тестирует:
  1. BrainLogger  (7 тестов) — запись, уровни, категории, индексация, потокобезопасность
  2. DigestGenerator (8 тестов) — форматирование циклов, сессий, файлы
  3. TraceBuilder (8 тестов) — накопление шагов, reconstruct, human-readable, from_logger
  4. Импорт через __init__.py (2 теста)

Ожидаемый результат: 25/25 тестов
"""

import os
import tempfile
import threading
import unittest
from pathlib import Path

from brain.logging.brain_logger import BrainLogger
from brain.logging.digest_generator import CycleInfo, DigestGenerator
from brain.logging.trace_builder import TraceBuilder
from brain.core.contracts import TraceRef, TraceStep


# ===========================================================================
# 1. BrainLogger
# ===========================================================================

class TestBrainLogger(unittest.TestCase):
    """7 тестов BrainLogger."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.logger = BrainLogger(log_dir=str(self.temp_dir), echo_stdout=False)

    def tearDown(self):
        self.logger.close()
        for path in self.temp_dir.rglob("*"):
            if path.is_file():
                try:
                    path.unlink()
                except Exception:
                    pass
        try:
            self.temp_dir.rmdir()
        except Exception:
            pass

    # ------------------------------------------------------------------
    def test_basic_logging(self):
        """Базовая запись события и проверка полей."""
        self.logger.info(
            "planner", "goal_created",
            session_id="sess_01", cycle_id="cycle_1", trace_id="t-001",
            state={"goal": "answer_question"},
            latency_ms=2.3,
        )
        events = self.logger.get_events("t-001")
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["module"], "planner")
        self.assertEqual(ev["event"], "goal_created")
        self.assertEqual(ev["session_id"], "sess_01")
        self.assertEqual(ev["cycle_id"], "cycle_1")
        self.assertEqual(ev["trace_id"], "t-001")
        self.assertEqual(ev["state"], {"goal": "answer_question"})
        self.assertAlmostEqual(ev["latency_ms"], 2.3, places=2)
        self.assertIn("ts", ev)
        self.assertEqual(ev["level"], "INFO")

    # ------------------------------------------------------------------
    def test_level_shortcuts(self):
        """Все 5 shortcut-методов записывают правильный level."""
        self.logger.debug("m", "ev_debug", trace_id="td")
        self.logger.info("m", "ev_info", trace_id="ti")
        self.logger.warn("m", "ev_warn", trace_id="tw")
        self.logger.error("m", "ev_error", trace_id="te")
        self.logger.critical("m", "ev_critical", trace_id="tc")
        for tid, expected_level in [
            ("td", "DEBUG"), ("ti", "INFO"), ("tw", "WARN"),
            ("te", "ERROR"), ("tc", "CRITICAL"),
        ]:
            evs = self.logger.get_events(tid)
            self.assertEqual(len(evs), 1, f"trace_id={tid}")
            self.assertEqual(evs[0]["level"], expected_level)

    # ------------------------------------------------------------------
    def test_min_level_filtering(self):
        """min_level=WARN отфильтровывает DEBUG и INFO."""
        logger_warn = BrainLogger(
            log_dir=str(self.temp_dir), min_level="WARN", echo_stdout=False
        )
        logger_warn.debug("m", "ev_debug", trace_id="td2")
        logger_warn.info("m", "ev_info", trace_id="ti2")
        logger_warn.warn("m", "ev_warn", trace_id="tw2")
        logger_warn.error("m", "ev_error", trace_id="te2")
        logger_warn.close()
        self.assertEqual(len(logger_warn.get_events("td2")), 0)
        self.assertEqual(len(logger_warn.get_events("ti2")), 0)
        self.assertEqual(len(logger_warn.get_events("tw2")), 1)
        self.assertEqual(len(logger_warn.get_events("te2")), 1)

    # ------------------------------------------------------------------
    def test_category_files_created(self):
        """Категорийные файлы создаются при записи соответствующих событий."""
        self.logger.info("planner", "goal_created", trace_id="t1")
        self.logger.info("memory", "fact_stored", trace_id="t2")
        self.logger.info("perception", "text_ingested", trace_id="t3")
        self.logger.info("safety", "audit_flag", trace_id="t4")
        self.logger.flush()
        self.assertTrue((self.temp_dir / "brain.jsonl").exists())
        self.assertTrue((self.temp_dir / "cognitive.jsonl").exists())
        self.assertTrue((self.temp_dir / "memory.jsonl").exists())
        self.assertTrue((self.temp_dir / "perception.jsonl").exists())
        self.assertTrue((self.temp_dir / "safety_audit.jsonl").exists())

    # ------------------------------------------------------------------
    def test_session_index(self):
        """Индексация по session_id."""
        self.logger.info("m", "ev1", session_id="sess_A", trace_id="t1")
        self.logger.info("m", "ev2", session_id="sess_B", trace_id="t2")
        self.logger.info("m", "ev3", session_id="sess_A", trace_id="t3")
        sess_a = self.logger.get_session("sess_A")
        sess_b = self.logger.get_session("sess_B")
        self.assertEqual(len(sess_a), 2)
        self.assertEqual(len(sess_b), 1)
        self.assertEqual(sess_a[0]["trace_id"], "t1")
        self.assertEqual(sess_a[1]["trace_id"], "t3")

    # ------------------------------------------------------------------
    def test_get_recent_with_level_filter(self):
        """get_recent() возвращает последние N событий с фильтром по уровню."""
        self.logger.debug("m", "ev_debug", trace_id="r1")
        self.logger.info("m", "ev_info", trace_id="r2")
        self.logger.warn("m", "ev_warn", trace_id="r3")
        recent = self.logger.get_recent(10, min_level="INFO")
        levels = [e["level"] for e in recent]
        self.assertNotIn("DEBUG", levels)
        self.assertIn("INFO", levels)
        self.assertIn("WARN", levels)

    # ------------------------------------------------------------------
    def test_thread_safety(self):
        """10 потоков пишут параллельно — все события сохраняются."""
        results = []

        def writer(tid: int):
            self.logger.info(
                f"thread_{tid}", f"event_{tid}",
                session_id=f"sess_{tid}", trace_id=f"thr_{tid}",
                latency_ms=float(tid),
            )
            results.append(tid)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 10)
        for i in range(10):
            evs = self.logger.get_events(f"thr_{i}")
            self.assertEqual(len(evs), 1, f"thread {i}: expected 1 event")
            self.assertEqual(evs[0]["event"], f"event_{i}")


# ===========================================================================
# 2. DigestGenerator
# ===========================================================================

class TestDigestGenerator(unittest.TestCase):
    """8 тестов DigestGenerator."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.gen = DigestGenerator(str(self.temp_dir))

    def tearDown(self):
        for path in self.temp_dir.rglob("*"):
            if path.is_file():
                try:
                    path.unlink()
                except Exception:
                    pass
        try:
            self.temp_dir.rmdir()
        except Exception:
            pass

    # ------------------------------------------------------------------
    def test_cycle_digest_contains_key_fields(self):
        """Дайджест цикла содержит все ключевые поля."""
        info = CycleInfo(
            cycle_id="cycle_42",
            session_id="sess_01",
            trace_id="t-001",
            goal="answer_question('Что такое нейрон?')",
            input_text="Что такое нейрон?",
            input_modality="text",
            input_source="user_input",
            memory_used=["semantic:нейрон (conf=0.87)", "episodic:ep_001"],
            sources_used=["user_input (trust=0.80)"],
            reasoning_chain=["нейрон", "→", "клетка", "→", "нервная система"],
            reasoning_type="associative",
            confidence=0.78,
            action="respond_hedged",
            response_preview="Вероятно, нейрон — это основная клетка нервной системы",
            duration_ms=142.0,
            cpu_pct=45.0,
            ram_gb=3.8,
            learning_updates=["association(нейрон↔клетка) += 0.01"],
        )
        text = self.gen.format_cycle(info)
        self.assertIn("cycle_42", text)
        self.assertIn("sess_01", text)
        self.assertIn("answer_question", text)
        self.assertIn("нейрон", text)
        self.assertIn("0.78", text)
        self.assertIn("respond_hedged", text)
        self.assertIn("142", text)
        self.assertIn("associative", text)

    # ------------------------------------------------------------------
    def test_confidence_labels(self):
        """Метки уверенности: high/medium/low/very low."""
        from brain.logging.digest_generator import _confidence_label
        self.assertEqual(_confidence_label(0.90), "high")
        self.assertEqual(_confidence_label(0.70), "medium")
        self.assertEqual(_confidence_label(0.40), "low")
        self.assertEqual(_confidence_label(0.10), "very low")

    # ------------------------------------------------------------------
    def test_cycle_digest_writes_to_day_file(self):
        """generate_cycle_digest() записывает в файл дня."""
        info = CycleInfo(cycle_id="c1", session_id="s1", goal="test_goal")
        self.gen.generate_cycle_digest(info)
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_file = self.temp_dir / f"{today}.txt"
        self.assertTrue(day_file.exists())
        content = day_file.read_text(encoding="utf-8")
        self.assertIn("c1", content)
        self.assertIn("test_goal", content)

    # ------------------------------------------------------------------
    def test_session_digest_aggregates_cycles(self):
        """Дайджест сессии содержит агрегированные метрики."""
        cycles = [
            CycleInfo(cycle_id=f"c{i}", session_id="sess_X",
                      confidence=0.7 + i * 0.05, duration_ms=100.0 + i * 10,
                      action="respond")
            for i in range(3)
        ]
        text = self.gen.generate_session_digest("sess_X", cycles)
        self.assertIn("sess_X", text)
        self.assertIn("Total cycles:   3", text)
        self.assertIn("Avg confidence", text)
        self.assertIn("Avg cycle time", text)

    # ------------------------------------------------------------------
    def test_session_digest_writes_file(self):
        """generate_session_digest() создаёт файл session_<id>.txt."""
        cycles = [CycleInfo(cycle_id="c1", session_id="sess_Y")]
        self.gen.generate_session_digest("sess_Y", cycles)
        session_file = self.temp_dir / "session_sess_Y.txt"
        self.assertTrue(session_file.exists())

    # ------------------------------------------------------------------
    def test_empty_cycle_info(self):
        """Пустой CycleInfo не вызывает исключений."""
        info = CycleInfo()
        text = self.gen.format_cycle(info)
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)

    # ------------------------------------------------------------------
    def test_contradiction_shown(self):
        """Противоречие отображается в дайджесте."""
        info = CycleInfo(
            cycle_id="c_contr",
            contradiction="нейрон=клетка vs нейрон=орган",
        )
        text = self.gen.format_cycle(info)
        self.assertIn("нейрон=клетка", text)

    # ------------------------------------------------------------------
    def test_no_contradiction_shows_none(self):
        """Если противоречий нет — показывается 'none'."""
        info = CycleInfo(cycle_id="c_ok", contradiction="")
        text = self.gen.format_cycle(info)
        self.assertIn("none", text)


# ===========================================================================
# 3. TraceBuilder
# ===========================================================================

class TestTraceBuilder(unittest.TestCase):
    """8 тестов TraceBuilder."""

    def setUp(self):
        self.builder = TraceBuilder()

    # ------------------------------------------------------------------
    def test_start_and_finish_trace(self):
        """start_trace + finish_trace возвращает TraceChain."""
        self.builder.start_trace("t-001", session_id="sess_01", cycle_id="c1")
        chain = self.builder.finish_trace("t-001")
        self.assertIsNotNone(chain)
        self.assertEqual(chain.trace_id, "t-001")
        self.assertEqual(chain.session_id, "sess_01")
        self.assertEqual(chain.cycle_id, "c1")

    # ------------------------------------------------------------------
    def test_add_steps(self):
        """Шаги добавляются и сохраняются в TraceChain."""
        self.builder.start_trace("t-002")
        self.builder.add_step("t-002", module="planner", action="goal_created",
                               confidence=1.0, details={"goal": "answer"})
        self.builder.add_step("t-002", module="reasoner", action="reasoning_completed",
                               confidence=0.78)
        chain = self.builder.finish_trace("t-002")
        self.assertEqual(len(chain.steps), 2)
        self.assertEqual(chain.steps[0].module, "planner")
        self.assertEqual(chain.steps[0].action, "goal_created")
        self.assertAlmostEqual(chain.steps[0].confidence, 1.0)
        self.assertEqual(chain.steps[1].module, "reasoner")

    # ------------------------------------------------------------------
    def test_add_refs(self):
        """Ссылки на входы, память и выходы сохраняются."""
        self.builder.start_trace("t-003")
        self.builder.add_input_ref("t-003", ref_type="user_input", ref_id="msg_3")
        self.builder.add_memory_ref("t-003", ref_type="semantic", ref_id="нейрон",
                                    note="conf=0.87")
        self.builder.add_output_ref("t-003", ref_type="response", ref_id="out_001")
        chain = self.builder.finish_trace("t-003")
        # input_refs включает и memory_refs (объединяются в _TraceAccumulator.build)
        ref_ids = [r.ref_id for r in chain.input_refs]
        self.assertIn("msg_3", ref_ids)
        self.assertIn("нейрон", ref_ids)
        out_ids = [r.ref_id for r in chain.output_refs]
        self.assertIn("out_001", out_ids)

    # ------------------------------------------------------------------
    def test_reconstruct_active_trace(self):
        """reconstruct() работает для активного (незавершённого) trace."""
        self.builder.start_trace("t-004")
        self.builder.add_step("t-004", module="m", action="step1")
        chain = self.builder.reconstruct("t-004")
        self.assertIsNotNone(chain)
        self.assertEqual(len(chain.steps), 1)
        # trace остаётся активным
        self.assertIn("t-004", self.builder.active_traces())

    # ------------------------------------------------------------------
    def test_reconstruct_completed_trace(self):
        """reconstruct() работает для завершённого trace из кэша."""
        self.builder.start_trace("t-005")
        self.builder.add_step("t-005", module="m", action="step1")
        self.builder.finish_trace("t-005")
        # После finish — не в active
        self.assertNotIn("t-005", self.builder.active_traces())
        # Но reconstruct из кэша работает
        chain = self.builder.reconstruct("t-005")
        self.assertIsNotNone(chain)
        self.assertEqual(chain.trace_id, "t-005")

    # ------------------------------------------------------------------
    def test_human_readable_output(self):
        """to_human_readable() содержит ключевые поля."""
        self.builder.start_trace("t-006", session_id="sess_01", cycle_id="c6")
        self.builder.add_input_ref("t-006", ref_type="user_input", ref_id="msg_1")
        self.builder.add_step("t-006", module="planner", action="goal_created",
                               confidence=1.0)
        self.builder.add_step("t-006", module="reasoner", action="reasoning_completed",
                               confidence=0.78,
                               details={"decision": {"action": "respond_hedged"}})
        self.builder.add_output_ref("t-006", ref_type="response", ref_id="out_006",
                                    note="confidence=0.78")
        self.builder.set_summary("t-006", "Ответ на вопрос о нейроне")
        chain = self.builder.finish_trace("t-006")
        text = self.builder.to_human_readable(chain)
        self.assertIn("t-006", text)
        self.assertIn("sess_01", text)
        self.assertIn("planner", text)
        self.assertIn("reasoner", text)
        self.assertIn("msg_1", text)
        self.assertIn("out_006", text)
        self.assertIn("Ответ на вопрос о нейроне", text)

    # ------------------------------------------------------------------
    def test_reconstruct_from_logger(self):
        """reconstruct_from_logger() восстанавливает trace из событий BrainLogger."""
        temp_dir = Path(tempfile.mkdtemp())
        logger = BrainLogger(log_dir=str(temp_dir), echo_stdout=False)
        try:
            logger.info("planner", "goal_created",
                        trace_id="t-007", session_id="sess_07", cycle_id="c7",
                        state={"goal": "answer_question"},
                        input_ref=["user_input:msg_7"])
            logger.info("reasoner", "reasoning_completed",
                        trace_id="t-007", session_id="sess_07", cycle_id="c7",
                        decision={"action": "respond", "confidence": 0.82},
                        memory_refs=["semantic:нейрон"])
            chain = self.builder.reconstruct_from_logger("t-007", logger)
            self.assertIsNotNone(chain)
            self.assertEqual(chain.trace_id, "t-007")
            self.assertEqual(chain.session_id, "sess_07")
            self.assertEqual(len(chain.steps), 2)
            self.assertEqual(chain.steps[0].module, "planner")
            self.assertEqual(chain.steps[1].module, "reasoner")
            # Проверяем ссылки
            ref_ids = [r.ref_id for r in chain.input_refs]
            self.assertIn("user_input:msg_7", ref_ids)
            self.assertIn("semantic:нейрон", ref_ids)
        finally:
            logger.close()
            for path in temp_dir.rglob("*"):
                if path.is_file():
                    try:
                        path.unlink()
                    except Exception:
                        pass
            try:
                temp_dir.rmdir()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def test_auto_create_trace_on_add_step(self):
        """add_step() без start_trace автоматически создаёт trace."""
        self.builder.add_step("t-auto", module="m", action="auto_step")
        chain = self.builder.reconstruct("t-auto")
        self.assertIsNotNone(chain)
        self.assertEqual(len(chain.steps), 1)
        self.assertEqual(chain.steps[0].action, "auto_step")


# ===========================================================================
# 4. Импорт через __init__.py
# ===========================================================================

class TestLoggingImports(unittest.TestCase):
    """2 теста импорта через brain.logging."""

    def test_import_all_classes(self):
        """Все 4 класса импортируются из brain.logging."""
        from brain.logging import BrainLogger, DigestGenerator, CycleInfo, TraceBuilder
        self.assertTrue(callable(BrainLogger))
        self.assertTrue(callable(DigestGenerator))
        self.assertTrue(callable(CycleInfo))
        self.assertTrue(callable(TraceBuilder))

    def test_all_exports(self):
        """__all__ содержит все публичные классы."""
        import brain.logging as logging_pkg
        self.assertIn("BrainLogger", logging_pkg.__all__)
        self.assertIn("DigestGenerator", logging_pkg.__all__)
        self.assertIn("CycleInfo", logging_pkg.__all__)
        self.assertIn("TraceBuilder", logging_pkg.__all__)


# ===========================================================================
# Runner
# ===========================================================================

def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestBrainLogger,
        TestDigestGenerator,
        TestTraceBuilder,
        TestLoggingImports,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    passed = total - failed

    print(f"\n{'='*50}")
    print(f"  Logging Tests: {passed}/{total} passed")
    if failed == 0:
        print("  [OK] Vse testy proshli!")
    else:
        print(f"  [FAIL] {failed} testov provalilis'")
    print(f"{'='*50}")

    return result


if __name__ == "__main__":
    run_tests()
