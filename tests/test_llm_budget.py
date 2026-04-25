"""Тесты общего LLM budget (U-A.3)."""

import tempfile

from brain.bridges.llm_bridge import MockProvider
from brain.bridges.llm_budget import LLMRateLimitConfig, LLMRateLimiter
from brain.cognition import CognitiveCore
from brain.memory import MemoryManager


def test_default_llm_calls_per_hour_is_20():
    limiter = LLMRateLimiter()

    assert limiter.config.llm_calls_per_hour == 20
    assert limiter.remaining(now=100.0) == 20


def test_allow_and_record_share_global_hourly_budget():
    limiter = LLMRateLimiter(LLMRateLimitConfig(llm_calls_per_hour=2))

    assert limiter.allow("ingestion", now=100.0)
    limiter.record("ingestion", now=100.0)
    assert limiter.allow("conflict_advice", now=101.0)
    limiter.record("conflict_advice", now=101.0)

    assert not limiter.allow("idle", now=102.0)
    assert limiter.remaining(now=102.0) == 0
    assert limiter.usage_by_purpose(now=102.0) == {
        "ingestion": 1,
        "conflict_advice": 1,
    }


def test_budget_recovers_after_window_expires():
    limiter = LLMRateLimiter(
        LLMRateLimitConfig(llm_calls_per_hour=1, window_seconds=10.0)
    )

    limiter.record("ingestion", now=100.0)
    assert not limiter.allow("idle", now=109.0)
    assert limiter.allow("idle", now=111.0)
    assert limiter.remaining(now=111.0) == 1


def test_pipeline_llm_enhance_skips_when_budget_exhausted():
    with tempfile.TemporaryDirectory() as tmp:
        mm = MemoryManager(data_dir=tmp, auto_consolidate=False)
        try:
            mm.store_fact("нейрон", "клетка нервной системы", source_ref="test#1")
            limiter = LLMRateLimiter(LLMRateLimitConfig(llm_calls_per_hour=0))
            core = CognitiveCore(
                memory_manager=mm,
                llm_provider=MockProvider("LLM answer"),
                llm_rate_limiter=limiter,
            )

            result = core.run("что такое нейрон?")

            assert result.metadata.get("llm_budget_exhausted") is True
            assert result.metadata.get("llm_enhanced") is False
            assert limiter.remaining() == 0
        finally:
            mm.stop(save=False)
