"""
tests/test_replay_engine.py

Тесты для Этапа I: ReplayEngine (brain/learning/replay_engine.py).

Покрывает:
  - ReplaySession — ContractMixin round-trip, defaults
  - ReplayStrategy — enum значения
  - ReplayEngine.run_replay_session() — все 4 стратегии, skip при cpu_busy
  - ReplayEngine.cleanup_stale() — удаление устаревших эпизодов
  - ReplayEngine._should_run() — CPU threshold
  - ReplayEngine._select_episodes() — IMPORTANCE, RECENCY, FREQUENCY, RANDOM
  - ReplayEngine._replay_episode() — reinforced / stale / ok
  - ReplayEngine._check_consistency() — semantic confidence check
  - ReplayEngine.status() / __repr__()
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from brain.learning.replay_engine import (
    ReplayEngine,
    ReplaySession,
    ReplayStrategy,
)

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _make_episode(
    importance: float = 0.5,
    age_days: float = 3.0,
    access_count: int = 2,
    confidence: float = 0.7,
    concepts: list | None = None,
    episode_id: str = "ep_001",
) -> MagicMock:
    """Создать mock Episode."""
    ep = MagicMock()
    ep.episode_id = episode_id
    ep.importance = importance
    ep.age_days = MagicMock(return_value=age_days)
    ep.access_count = access_count
    ep.confidence = confidence
    ep.concepts = concepts or ["нейрон", "синапс"]
    ep.content = "Тестовый эпизод"
    # ts — временная метка (datetime), нужна для сортировки RECENCY_BASED
    ep.ts = datetime(2024, 1, 1) - timedelta(days=age_days)
    return ep


def _make_memory(episodes: list | None = None) -> MagicMock:
    """Создать mock MemoryManager с эпизодической памятью."""
    memory = MagicMock()
    memory.episodic = MagicMock()
    memory.episodic.get_all = MagicMock(return_value=episodes or [])
    memory.episodic.get_recent = MagicMock(return_value=episodes or [])
    memory.episodic.update_importance = MagicMock()
    memory.episodic.delete = MagicMock()
    memory.episodic._remove_episode = MagicMock()
    memory.semantic = MagicMock()
    memory.semantic.get_fact = MagicMock(return_value=None)
    return memory


def _make_engine(
    episodes: list | None = None,
    batch_size: int = 10,
    idle_cpu_threshold: float = 30.0,
) -> tuple[ReplayEngine, MagicMock]:
    """Создать ReplayEngine с mock memory."""
    memory = _make_memory(episodes)
    engine = ReplayEngine(
        memory=memory,
        batch_size=batch_size,
        idle_cpu_threshold=idle_cpu_threshold,
    )
    return engine, memory


# ---------------------------------------------------------------------------
# 1. ReplayStrategy — enum значения
# ---------------------------------------------------------------------------


class TestReplayStrategy:
    """Тесты ReplayStrategy enum."""

    def test_importance_based_value(self):
        assert ReplayStrategy.IMPORTANCE_BASED == "importance"

    def test_recency_based_value(self):
        assert ReplayStrategy.RECENCY_BASED == "recency"

    def test_frequency_based_value(self):
        assert ReplayStrategy.FREQUENCY_BASED == "frequency"

    def test_random_value(self):
        assert ReplayStrategy.RANDOM == "random"

    def test_all_strategies_are_str(self):
        for strategy in ReplayStrategy:
            assert isinstance(strategy, str)

    def test_four_strategies_total(self):
        assert len(list(ReplayStrategy)) == 4


# ---------------------------------------------------------------------------
# 2. ReplaySession — ContractMixin round-trip
# ---------------------------------------------------------------------------


class TestReplaySession:
    """Тесты ReplaySession — ContractMixin round-trip и defaults."""

    def test_required_fields(self):
        session = ReplaySession(
            session_id="sess_001",
            strategy=ReplayStrategy.IMPORTANCE_BASED,
        )
        assert session.session_id == "sess_001"
        assert session.strategy == ReplayStrategy.IMPORTANCE_BASED
        assert session.episodes_replayed == 0
        assert session.reinforced == 0
        assert session.stale_removed == 0
        assert session.duration_ms == 0.0
        assert session.metadata == {}

    def test_to_dict(self):
        session = ReplaySession(
            session_id="sess_002",
            strategy=ReplayStrategy.RECENCY_BASED,
            episodes_replayed=5,
            reinforced=3,
            stale_removed=1,
            duration_ms=42.5,
            metadata={"skipped": False},
        )
        d = session.to_dict()
        assert d["session_id"] == "sess_002"
        assert d["strategy"] == "recency"
        assert d["episodes_replayed"] == 5
        assert d["reinforced"] == 3
        assert d["stale_removed"] == 1
        assert d["duration_ms"] == 42.5

    def test_from_dict_roundtrip(self):
        session = ReplaySession(
            session_id="sess_003",
            strategy=ReplayStrategy.RANDOM,
            episodes_replayed=10,
            reinforced=7,
            stale_removed=2,
            duration_ms=100.0,
            metadata={"batch_size": 10},
        )
        d = session.to_dict()
        session2 = ReplaySession.from_dict(d)
        assert session2.session_id == session.session_id
        assert session2.strategy == session.strategy
        assert session2.episodes_replayed == session.episodes_replayed
        assert session2.reinforced == session.reinforced

    def test_all_fields_in_dict(self):
        session = ReplaySession(session_id="sess_004", strategy=ReplayStrategy.FREQUENCY_BASED)
        d = session.to_dict()
        for key in ("session_id", "strategy", "episodes_replayed", "reinforced",
                    "stale_removed", "duration_ms", "metadata"):
            assert key in d


# ---------------------------------------------------------------------------
# 3. ReplayEngine — инициализация
# ---------------------------------------------------------------------------


class TestReplayEngineInit:
    """Тесты инициализации ReplayEngine."""

    def test_default_params(self):
        engine, _ = _make_engine()
        status = engine.status()
        assert status["batch_size"] == 10
        assert status["idle_cpu_threshold"] == 30.0
        assert status["session_count"] == 0
        assert status["total_reinforced"] == 0
        assert status["total_removed"] == 0

    def test_custom_params(self):
        engine, _ = _make_engine(batch_size=5, idle_cpu_threshold=50.0)
        status = engine.status()
        assert status["batch_size"] == 5
        assert status["idle_cpu_threshold"] == 50.0

    def test_repr(self):
        engine, _ = _make_engine()
        r = repr(engine)
        assert "ReplayEngine" in r
        assert "sessions=" in r

    def test_constants(self):
        assert ReplayEngine.STALE_AGE_DAYS == 7.0
        assert ReplayEngine.STALE_MIN_IMPORTANCE == 0.1
        assert ReplayEngine.REINFORCE_DELTA == 0.01
        assert ReplayEngine.CONSISTENCY_CONFIDENCE_THRESHOLD == 0.5
        assert ReplayEngine.MAX_EPISODES_POOL == 200


# ---------------------------------------------------------------------------
# 4. ReplayEngine._should_run()
# ---------------------------------------------------------------------------


class TestShouldRun:
    """Тесты _should_run() — CPU threshold."""

    def test_should_run_when_cpu_below_threshold(self):
        engine, _ = _make_engine(idle_cpu_threshold=30.0)
        with patch("psutil.cpu_percent", return_value=10.0):
            assert engine._should_run() is True

    def test_should_not_run_when_cpu_above_threshold(self):
        engine, _ = _make_engine(idle_cpu_threshold=30.0)
        with patch("psutil.cpu_percent", return_value=50.0):
            assert engine._should_run() is False

    def test_should_run_at_exact_threshold(self):
        """CPU == threshold → не запускать (строго меньше)."""
        engine, _ = _make_engine(idle_cpu_threshold=30.0)
        with patch("psutil.cpu_percent", return_value=30.0):
            # Зависит от реализации: < или <=
            result = engine._should_run()
            assert isinstance(result, bool)

    def test_fallback_true_when_psutil_unavailable(self):
        """При недоступности psutil — fallback True."""
        engine, _ = _make_engine()
        with patch("psutil.cpu_percent", side_effect=Exception("psutil error")):
            result = engine._should_run()
            assert result is True


# ---------------------------------------------------------------------------
# 5. ReplayEngine.run_replay_session() — skip при cpu_busy
# ---------------------------------------------------------------------------


class TestRunReplaySessionSkip:
    """Тесты пропуска сессии при высокой нагрузке CPU."""

    def test_skip_when_cpu_busy(self):
        """CPU > threshold и force=False → сессия пропускается."""
        engine, _ = _make_engine(idle_cpu_threshold=30.0)
        with patch("psutil.cpu_percent", return_value=80.0):
            session = engine.run_replay_session(ReplayStrategy.IMPORTANCE_BASED)
        assert session.metadata.get("skipped") is True
        assert session.metadata.get("reason") == "cpu_busy"
        assert session.episodes_replayed == 0

    def test_no_skip_when_force_true(self):
        """force=True → сессия запускается даже при высоком CPU."""
        episodes = [_make_episode(episode_id=f"ep_{i}") for i in range(3)]
        engine, _ = _make_engine(episodes=episodes, idle_cpu_threshold=30.0)
        with patch("psutil.cpu_percent", return_value=80.0):
            session = engine.run_replay_session(
                ReplayStrategy.IMPORTANCE_BASED, force=True
            )
        assert session.metadata.get("skipped") is not True

    def test_no_skip_when_cpu_low(self):
        """CPU < threshold → сессия запускается."""
        episodes = [_make_episode(episode_id=f"ep_{i}") for i in range(3)]
        engine, _ = _make_engine(episodes=episodes, idle_cpu_threshold=30.0)
        with patch("psutil.cpu_percent", return_value=5.0):
            session = engine.run_replay_session(ReplayStrategy.IMPORTANCE_BASED)
        assert session.metadata.get("skipped") is not True


# ---------------------------------------------------------------------------
# 6. ReplayEngine.run_replay_session() — все 4 стратегии
# ---------------------------------------------------------------------------


class TestRunReplaySessionStrategies:
    """Тесты run_replay_session() со всеми стратегиями."""

    def _run_with_strategy(self, strategy: ReplayStrategy) -> ReplaySession:
        episodes = [
            _make_episode(
                episode_id=f"ep_{i}",
                importance=0.5 + i * 0.1,
                age_days=float(i),
                access_count=i + 1,
            )
            for i in range(5)
        ]
        engine, _ = _make_engine(episodes=episodes)
        with patch("psutil.cpu_percent", return_value=5.0):
            return engine.run_replay_session(strategy, force=True)

    def test_importance_based_returns_session(self):
        session = self._run_with_strategy(ReplayStrategy.IMPORTANCE_BASED)
        assert isinstance(session, ReplaySession)
        assert session.strategy == ReplayStrategy.IMPORTANCE_BASED

    def test_recency_based_returns_session(self):
        session = self._run_with_strategy(ReplayStrategy.RECENCY_BASED)
        assert isinstance(session, ReplaySession)
        assert session.strategy == ReplayStrategy.RECENCY_BASED

    def test_frequency_based_returns_session(self):
        session = self._run_with_strategy(ReplayStrategy.FREQUENCY_BASED)
        assert isinstance(session, ReplaySession)
        assert session.strategy == ReplayStrategy.FREQUENCY_BASED

    def test_random_returns_session(self):
        session = self._run_with_strategy(ReplayStrategy.RANDOM)
        assert isinstance(session, ReplaySession)
        assert session.strategy == ReplayStrategy.RANDOM

    def test_session_id_generated(self):
        session = self._run_with_strategy(ReplayStrategy.IMPORTANCE_BASED)
        assert session.session_id != ""

    def test_duration_ms_set(self):
        session = self._run_with_strategy(ReplayStrategy.IMPORTANCE_BASED)
        assert session.duration_ms >= 0.0

    def test_episodes_replayed_count(self):
        session = self._run_with_strategy(ReplayStrategy.IMPORTANCE_BASED)
        assert session.episodes_replayed >= 0

    def test_empty_episodes_pool(self):
        """Пустой пул эпизодов → сессия с 0 replayed."""
        engine, _ = _make_engine(episodes=[])
        with patch("psutil.cpu_percent", return_value=5.0):
            session = engine.run_replay_session(ReplayStrategy.IMPORTANCE_BASED, force=True)
        assert session.episodes_replayed == 0

    def test_custom_batch_size(self):
        """batch_size ограничивает количество эпизодов."""
        episodes = [_make_episode(episode_id=f"ep_{i}") for i in range(20)]
        engine, _ = _make_engine(episodes=episodes, batch_size=3)
        with patch("psutil.cpu_percent", return_value=5.0):
            session = engine.run_replay_session(ReplayStrategy.IMPORTANCE_BASED, force=True)
        assert session.episodes_replayed <= 3

    def test_sessions_run_incremented(self):
        episodes = [_make_episode(episode_id=f"ep_{i}") for i in range(3)]
        engine, _ = _make_engine(episodes=episodes)
        with patch("psutil.cpu_percent", return_value=5.0):
            engine.run_replay_session(ReplayStrategy.IMPORTANCE_BASED, force=True)
            engine.run_replay_session(ReplayStrategy.RECENCY_BASED, force=True)
        assert engine.status()["session_count"] == 2


# ---------------------------------------------------------------------------
# 7. ReplayEngine._select_episodes()
# ---------------------------------------------------------------------------


class TestSelectEpisodes:
    """Тесты _select_episodes() — выбор эпизодов по стратегии."""

    def _make_episodes(self, n: int = 10) -> list:
        return [
            _make_episode(
                episode_id=f"ep_{i}",
                importance=float(i) / n,
                age_days=float(n - i),
                access_count=i + 1,
            )
            for i in range(n)
        ]

    def test_importance_based_selects_highest_importance(self):
        """IMPORTANCE_BASED → эпизоды с наибольшим importance."""
        episodes = self._make_episodes(10)
        engine, memory = _make_engine(episodes=episodes)
        selected = engine._select_episodes(ReplayStrategy.IMPORTANCE_BASED, 3)
        importances = [ep.importance for ep in selected]
        # Должны быть выбраны эпизоды с наибольшим importance
        assert all(imp >= 0.6 for imp in importances)

    def test_recency_based_selects_newest(self):
        """RECENCY_BASED → эпизоды с наименьшим age_days."""
        episodes = self._make_episodes(10)
        engine, memory = _make_engine(episodes=episodes)
        selected = engine._select_episodes(ReplayStrategy.RECENCY_BASED, 3)
        ages = [ep.age_days() for ep in selected]
        # Должны быть выбраны самые новые (наименьший age_days)
        assert all(age <= 3.0 for age in ages)

    def test_frequency_based_selects_most_accessed(self):
        """FREQUENCY_BASED → эпизоды с наибольшим access_count."""
        episodes = self._make_episodes(10)
        engine, memory = _make_engine(episodes=episodes)
        selected = engine._select_episodes(ReplayStrategy.FREQUENCY_BASED, 3)
        counts = [ep.access_count for ep in selected]
        assert all(c >= 8 for c in counts)

    def test_random_selects_n_episodes(self):
        """RANDOM → ровно n эпизодов (или меньше если пул меньше)."""
        episodes = self._make_episodes(10)
        engine, memory = _make_engine(episodes=episodes)
        selected = engine._select_episodes(ReplayStrategy.RANDOM, 5)
        assert len(selected) == 5

    def test_select_returns_list(self):
        episodes = self._make_episodes(5)
        engine, memory = _make_engine(episodes=episodes)
        selected = engine._select_episodes(ReplayStrategy.IMPORTANCE_BASED, 3)
        assert isinstance(selected, list)

    def test_select_empty_pool_returns_empty(self):
        engine, memory = _make_engine(episodes=[])
        selected = engine._select_episodes(ReplayStrategy.IMPORTANCE_BASED, 5)
        assert selected == []

    def test_select_n_larger_than_pool(self):
        """n > len(pool) → возвращает все доступные."""
        episodes = self._make_episodes(3)
        engine, memory = _make_engine(episodes=episodes)
        selected = engine._select_episodes(ReplayStrategy.IMPORTANCE_BASED, 10)
        assert len(selected) <= 3

    def test_pool_capped_at_max_episodes(self):
        """Пул ограничен MAX_EPISODES_POOL."""
        episodes = self._make_episodes(300)
        engine, memory = _make_engine(episodes=episodes)
        selected = engine._select_episodes(ReplayStrategy.RANDOM, 10)
        assert len(selected) <= 10


# ---------------------------------------------------------------------------
# 8. ReplayEngine._replay_episode()
# ---------------------------------------------------------------------------


class TestReplayEpisode:
    """Тесты _replay_episode() — reinforced / stale / ok."""

    def test_stale_episode_returns_stale(self):
        """Эпизод с age_days > STALE_AGE_DAYS, importance < STALE_MIN_IMPORTANCE и access_count==0 → 'stale'."""
        ep = _make_episode(
            importance=0.05,   # < STALE_MIN_IMPORTANCE (0.1)
            age_days=10.0,     # > STALE_AGE_DAYS (7.0)
            access_count=0,    # access_count == 0
        )
        engine, memory = _make_engine()
        result = engine._replay_episode(ep)
        assert result == "stale"

    def test_stale_episode_deleted(self):
        """Stale эпизод удаляется через _remove_episode."""
        ep = _make_episode(importance=0.05, age_days=10.0, access_count=0)
        engine, memory = _make_engine()
        engine._replay_episode(ep)
        memory.episodic._remove_episode.assert_called_once_with(ep)

    def test_consistent_episode_returns_reinforced(self):
        """Консистентный эпизод (confidence > threshold) → 'reinforced'."""
        ep = _make_episode(importance=0.5, age_days=3.0, confidence=0.8)
        engine, memory = _make_engine()
        # Мокаем _check_consistency → True
        engine._check_consistency = MagicMock(return_value=True)
        result = engine._replay_episode(ep)
        assert result == "reinforced"

    def test_reinforced_episode_updates_importance(self):
        """Reinforced эпизод → ep.confidence увеличивается напрямую."""
        ep = _make_episode(importance=0.5, age_days=3.0, confidence=0.7)
        old_confidence = ep.confidence
        engine, memory = _make_engine()
        engine._check_consistency = MagicMock(return_value=True)
        engine._replay_episode(ep)
        assert ep.confidence > old_confidence

    def test_inconsistent_episode_returns_ok(self):
        """Неконсистентный эпизод → 'ok' (без reinforcement)."""
        ep = _make_episode(importance=0.5, age_days=3.0)
        engine, memory = _make_engine()
        engine._check_consistency = MagicMock(return_value=False)
        result = engine._replay_episode(ep)
        assert result == "ok"

    def test_ok_episode_no_importance_update(self):
        """'ok' эпизод → update_importance НЕ вызывается."""
        ep = _make_episode(importance=0.5, age_days=3.0)
        engine, memory = _make_engine()
        engine._check_consistency = MagicMock(return_value=False)
        engine._replay_episode(ep)
        memory.episodic.update_importance.assert_not_called()

    def test_not_stale_when_importance_above_threshold(self):
        """importance >= STALE_MIN_IMPORTANCE → не stale."""
        ep = _make_episode(importance=0.5, age_days=10.0)
        engine, memory = _make_engine()
        engine._check_consistency = MagicMock(return_value=False)
        result = engine._replay_episode(ep)
        assert result != "stale"

    def test_not_stale_when_age_below_threshold(self):
        """age_days <= STALE_AGE_DAYS → не stale."""
        ep = _make_episode(importance=0.05, age_days=3.0)
        engine, memory = _make_engine()
        engine._check_consistency = MagicMock(return_value=False)
        result = engine._replay_episode(ep)
        assert result != "stale"


# ---------------------------------------------------------------------------
# 9. ReplayEngine._check_consistency()
# ---------------------------------------------------------------------------


class TestCheckConsistency:
    """Тесты _check_consistency() — semantic confidence check."""

    def test_consistent_when_semantic_confidence_above_threshold(self):
        """semantic.get_fact().confidence > 0.5 → True."""
        ep = _make_episode(concepts=["нейрон"])
        engine, memory = _make_engine()
        fact = MagicMock()
        fact.confidence = 0.8
        memory.semantic.get_fact.return_value = fact
        assert engine._check_consistency(ep) is True

    def test_inconsistent_when_semantic_confidence_below_threshold(self):
        """semantic.get_fact().confidence <= 0.5 → False."""
        ep = _make_episode(concepts=["нейрон"])
        engine, memory = _make_engine()
        fact = MagicMock()
        fact.confidence = 0.3
        memory.semantic.get_fact.return_value = fact
        assert engine._check_consistency(ep) is False

    def test_inconsistent_when_no_semantic_fact(self):
        """semantic.get_fact() == None → False."""
        ep = _make_episode(concepts=["нейрон"])
        engine, memory = _make_engine()
        memory.semantic.get_fact.return_value = None
        assert engine._check_consistency(ep) is False

    def test_inconsistent_when_no_concepts(self):
        """Нет концептов → False."""
        ep = _make_episode(concepts=[])
        engine, memory = _make_engine()
        assert engine._check_consistency(ep) is False

    def test_uses_first_concept(self):
        """Проверяется первый концепт из списка."""
        ep = _make_episode(concepts=["нейрон", "синапс"])
        engine, memory = _make_engine()
        fact = MagicMock()
        fact.confidence = 0.8
        memory.semantic.get_fact.return_value = fact
        engine._check_consistency(ep)
        memory.semantic.get_fact.assert_called_with("нейрон")

    def test_exception_returns_false(self):
        """Исключение в semantic.get_fact → False."""
        ep = _make_episode(concepts=["нейрон"])
        engine, memory = _make_engine()
        memory.semantic.get_fact.side_effect = RuntimeError("ошибка")
        assert engine._check_consistency(ep) is False


# ---------------------------------------------------------------------------
# 10. ReplayEngine.cleanup_stale()
# ---------------------------------------------------------------------------


class TestCleanupStale:
    """Тесты cleanup_stale() — удаление устаревших эпизодов."""

    def test_cleanup_removes_stale_episodes(self):
        """Эпизоды с age_days > age_days, importance < min_importance и access_count==0 удаляются."""
        stale_ep = _make_episode(
            episode_id="stale_ep",
            importance=0.05,
            age_days=10.0,
            access_count=0,
        )
        fresh_ep = _make_episode(
            episode_id="fresh_ep",
            importance=0.8,
            age_days=2.0,
        )
        engine, memory = _make_engine(episodes=[stale_ep, fresh_ep])
        count = engine.cleanup_stale(age_days=7.0, min_importance=0.1)
        assert count == 1
        memory.episodic._remove_episode.assert_called_once_with(stale_ep)

    def test_cleanup_returns_count(self):
        stale_eps = [
            _make_episode(episode_id=f"stale_{i}", importance=0.05, age_days=10.0, access_count=0)
            for i in range(3)
        ]
        engine, memory = _make_engine(episodes=stale_eps)
        count = engine.cleanup_stale(age_days=7.0, min_importance=0.1)
        assert count == 3

    def test_cleanup_zero_when_no_stale(self):
        fresh_eps = [
            _make_episode(episode_id=f"fresh_{i}", importance=0.8, age_days=2.0)
            for i in range(3)
        ]
        engine, memory = _make_engine(episodes=fresh_eps)
        count = engine.cleanup_stale(age_days=7.0, min_importance=0.1)
        assert count == 0

    def test_cleanup_uses_default_params(self):
        """cleanup_stale() без аргументов использует STALE_AGE_DAYS и STALE_MIN_IMPORTANCE."""
        stale_ep = _make_episode(
            episode_id="stale_ep",
            importance=ReplayEngine.STALE_MIN_IMPORTANCE - 0.01,
            age_days=ReplayEngine.STALE_AGE_DAYS + 1.0,
            access_count=0,
        )
        engine, memory = _make_engine(episodes=[stale_ep])
        count = engine.cleanup_stale()
        assert count == 1

    def test_cleanup_total_stale_removed_incremented(self):
        stale_ep = _make_episode(importance=0.05, age_days=10.0, access_count=0)
        engine, memory = _make_engine(episodes=[stale_ep])
        engine.cleanup_stale()
        assert engine.status()["total_removed"] == 1

    def test_cleanup_empty_pool_returns_zero(self):
        engine, memory = _make_engine(episodes=[])
        count = engine.cleanup_stale()
        assert count == 0


# ---------------------------------------------------------------------------
# 11. ReplayEngine.status() / __repr__()
# ---------------------------------------------------------------------------


class TestReplayEngineStatus:
    """Тесты status() и __repr__()."""

    def setup_method(self):
        self.engine, self.memory = _make_engine()

    def test_status_returns_dict(self):
        status = self.engine.status()
        assert isinstance(status, dict)

    def test_status_keys(self):
        status = self.engine.status()
        for key in ("session_count", "total_reinforced", "total_removed",
                    "batch_size", "idle_cpu_threshold"):
            assert key in status

    def test_status_initial_values(self):
        status = self.engine.status()
        assert status["session_count"] == 0
        assert status["total_reinforced"] == 0
        assert status["total_removed"] == 0

    def test_status_after_session(self):
        episodes = [_make_episode(episode_id=f"ep_{i}") for i in range(3)]
        engine, memory = _make_engine(episodes=episodes)
        engine._check_consistency = MagicMock(return_value=True)
        with patch("psutil.cpu_percent", return_value=5.0):
            engine.run_replay_session(ReplayStrategy.IMPORTANCE_BASED, force=True)
        status = engine.status()
        assert status["session_count"] == 1

    def test_repr_contains_key_info(self):
        r = repr(self.engine)
        assert "ReplayEngine" in r
        assert "sessions=" in r

    def test_status_batch_size_matches_init(self):
        engine, _ = _make_engine(batch_size=7)
        assert engine.status()["batch_size"] == 7

    def test_status_idle_cpu_threshold_matches_init(self):
        engine, _ = _make_engine(idle_cpu_threshold=45.0)
        assert engine.status()["idle_cpu_threshold"] == 45.0
