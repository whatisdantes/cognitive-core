"""Tests for brain/safety/source_trust.py"""
from __future__ import annotations

import os
import tempfile

import pytest

from brain.safety.source_trust import SourceTrustManager, SourceTrustScore


class TestSourceTrustScore:
    def test_fields(self):
        from datetime import datetime, timezone

        s = SourceTrustScore(
            source_id="s1",
            trust=0.7,
            verified=False,
            last_checked=datetime.now(timezone.utc),
        )
        assert s.source_id == "s1"
        assert s.trust == 0.7
        assert s.verified is False


class TestSourceTrustManagerBasic:
    def test_unknown_source_default_trust_05(self):
        mgr = SourceTrustManager()
        s = mgr.get_score("unknown")
        assert s.trust == 0.5
        assert s.verified is False

    def test_same_source_same_object(self):
        mgr = SourceTrustManager()
        assert mgr.get_score("src_a") is mgr.get_score("src_a")

    def test_update_trust_positive(self):
        mgr = SourceTrustManager()
        mgr.update_trust("src_a", delta=0.2)
        assert mgr.get_score("src_a").trust == pytest.approx(0.7, abs=0.01)

    def test_update_trust_negative(self):
        mgr = SourceTrustManager()
        mgr.update_trust("src_a", delta=-0.2)
        assert mgr.get_score("src_a").trust == pytest.approx(0.3, abs=0.01)

    def test_update_trust_clamp_max(self):
        mgr = SourceTrustManager()
        mgr.update_trust("src_a", delta=2.0)
        assert mgr.get_score("src_a").trust == 1.0

    def test_update_trust_clamp_min(self):
        mgr = SourceTrustManager()
        mgr.update_trust("src_a", delta=-2.0)
        assert mgr.get_score("src_a").trust == 0.0

    def test_verify_sets_verified_true(self):
        mgr = SourceTrustManager()
        mgr.verify("src_a")
        assert mgr.get_score("src_a").verified is True

    def test_verify_raises_trust_to_085(self):
        mgr = SourceTrustManager()
        # trust starts at 0.5, verify should raise it to at least 0.85
        mgr.verify("src_a")
        assert mgr.get_score("src_a").trust >= 0.85

    def test_verify_does_not_lower_high_trust(self):
        mgr = SourceTrustManager()
        mgr.update_trust("src_a", delta=0.5)  # trust = 1.0
        mgr.verify("src_a")
        assert mgr.get_score("src_a").trust == 1.0

    def test_unverify_sets_false(self):
        mgr = SourceTrustManager()
        mgr.verify("src_a")
        mgr.unverify("src_a")
        assert mgr.get_score("src_a").verified is False

    def test_is_trusted_above_threshold(self):
        mgr = SourceTrustManager()
        mgr.update_trust("src_a", delta=0.3)  # trust = 0.8
        assert mgr.is_trusted("src_a", threshold=0.5) is True

    def test_is_trusted_below_threshold(self):
        mgr = SourceTrustManager()
        mgr.update_trust("src_a", delta=-0.3)  # trust = 0.2
        assert mgr.is_trusted("src_a", threshold=0.5) is False

    def test_get_all_scores_returns_all(self):
        mgr = SourceTrustManager()
        mgr.get_score("src_a")
        mgr.get_score("src_b")
        mgr.get_score("src_c")
        ids = {s.source_id for s in mgr.get_all_scores()}
        assert {"src_a", "src_b", "src_c"} <= ids

    def test_last_checked_updated_on_update(self):
        from datetime import datetime, timezone

        mgr = SourceTrustManager()
        before = datetime.now(timezone.utc)
        mgr.update_trust("src_a", delta=0.1)
        assert mgr.get_score("src_a").last_checked >= before

    def test_is_trusted_blacklisted_returns_false(self):
        from brain.memory.source_memory import SourceMemory

        with tempfile.TemporaryDirectory() as tmp:
            sm = SourceMemory(
                data_path=os.path.join(tmp, "sources.json"),
                autosave_every=0,
            )
            sm.register("src_bad")
            sm.blacklist("src_bad", reason="test")
            mgr = SourceTrustManager(source_memory=sm)
            assert mgr.is_trusted("src_bad") is False
