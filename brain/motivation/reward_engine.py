"""
brain/motivation/reward_engine.py — Движок вознаграждений (Stage M.1).

Биологический аналог: VTA (вентральная область покрышки) — источник дофамина.

Компоненты:
  - RewardType   — 6 типов вознаграждений (epistemic/accuracy/coherence/completion/efficiency/penalty)
  - REWARD_VALUES — словарь значений по типу
  - RewardSignal  — dataclass сигнала вознаграждения
  - RewardEngine  — вычисление сигнала + история + prediction_error

Формулы (BRAIN.md §17.2):
  prediction_error = actual_reward − expected_reward
  sliding_mean     = mean(last 100 signals)

Маппинг action → RewardType:
  "learn" / "store"          → EPISTEMIC  (+0.8)
  "answer" / "respond"       → ACCURACY   (+1.0)  [если не EFFICIENCY]
  "resolve" / "clarify"      → COHERENCE  (+0.6)
  "complete"                 → COMPLETION (+0.7)
  confidence>0.85 + fast<200 → EFFICIENCY (+0.3)  [приоритет над ACCURACY]
  "refuse" / corrected       → PENALTY    (−0.5)
  иначе                      → ACCURACY   (+1.0)  [default]
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Deque, Dict

from brain.core.contracts import CognitiveResult


# ---------------------------------------------------------------------------
# RewardType — типы вознаграждений
# ---------------------------------------------------------------------------

class RewardType(str, Enum):
    """Типы вознаграждений когнитивного мозга (BRAIN.md §15.1)."""
    EPISTEMIC  = "epistemic"   # Узнал новый факт, закрыл пробел
    ACCURACY   = "accuracy"    # Пользователь подтвердил ответ
    COHERENCE  = "coherence"   # Разрешил противоречие
    COMPLETION = "completion"  # Выполнил план/цель
    EFFICIENCY = "efficiency"  # Быстрый ответ с высокой уверенностью
    PENALTY    = "penalty"     # Пользователь исправил ошибку


# ---------------------------------------------------------------------------
# Значения вознаграждений
# ---------------------------------------------------------------------------

REWARD_VALUES: Dict[RewardType, float] = {
    RewardType.EPISTEMIC:  0.8,
    RewardType.ACCURACY:   1.0,
    RewardType.COHERENCE:  0.6,
    RewardType.COMPLETION: 0.7,
    RewardType.EFFICIENCY: 0.3,
    RewardType.PENALTY:   -0.5,
}

# Пороги для EFFICIENCY
_EFFICIENCY_CONFIDENCE_THRESHOLD: float = 0.85
_EFFICIENCY_ELAPSED_MS_THRESHOLD: float = 200.0

# Действия → RewardType (точное совпадение)
_ACTION_MAP: Dict[str, RewardType] = {
    "learn":    RewardType.EPISTEMIC,
    "store":    RewardType.EPISTEMIC,
    "resolve":  RewardType.COHERENCE,
    "clarify":  RewardType.COHERENCE,
    "complete": RewardType.COMPLETION,
    "refuse":   RewardType.PENALTY,
}


# ---------------------------------------------------------------------------
# RewardSignal — сигнал вознаграждения
# ---------------------------------------------------------------------------

@dataclass
class RewardSignal:
    """
    Сигнал вознаграждения от одного когнитивного цикла.

    Поля:
        type      — тип вознаграждения (RewardType)
        value     — числовое значение (из REWARD_VALUES)
        source    — источник (action name из CognitiveResult)
        cycle_id  — ID цикла
        timestamp — время создания (unix)
    """
    type: RewardType
    value: float
    source: str
    cycle_id: str
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# RewardEngine
# ---------------------------------------------------------------------------

class RewardEngine:
    """
    Движок вознаграждений — вычисляет RewardSignal по результату цикла.

    Биологический аналог: VTA (вентральная область покрышки).

    Параметры:
        history_size — размер скользящего окна истории (по умолчанию 100)

    Публичный API:
        compute(action_result)              → RewardSignal
        prediction_error(actual, expected)  → float
        sliding_mean()                      → float
    """

    def __init__(self, history_size: int = 100) -> None:
        self._history: Deque[RewardSignal] = deque(maxlen=history_size)

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def compute(self, action_result: CognitiveResult) -> RewardSignal:
        """
        Вычислить RewardSignal по результату когнитивного цикла.

        Маппинг action → RewardType:
          1. "refuse" → PENALTY
          2. "learn"/"store" → EPISTEMIC
          3. "resolve"/"clarify" → COHERENCE
          4. "complete" → COMPLETION
          5. confidence > 0.85 + elapsed_ms < 200 → EFFICIENCY
          6. "answer"/"respond" → ACCURACY
          7. иначе → ACCURACY (default)

        Args:
            action_result: результат когнитивного цикла

        Returns:
            RewardSignal с типом и значением вознаграждения
        """
        reward_type = self._classify(action_result)
        value = REWARD_VALUES[reward_type]

        signal = RewardSignal(
            type=reward_type,
            value=value,
            source=action_result.action,
            cycle_id=action_result.cycle_id,
        )
        self._history.append(signal)
        return signal

    def prediction_error(self, actual: float, expected: float) -> float:
        """
        Вычислить ошибку предсказания вознаграждения.

        Ключевой принцип (BRAIN.md §15.2):
        Дофамин выделяется не при получении награды, а при ошибке предсказания —
        разнице между ожидаемым и реальным результатом.

        Args:
            actual:   фактическое вознаграждение
            expected: ожидаемое вознаграждение

        Returns:
            actual − expected (положительное = лучше ожидаемого)
        """
        return actual - expected

    def sliding_mean(self) -> float:
        """
        Скользящее среднее по последним history_size сигналам.

        Returns:
            0.0 если история пуста, иначе среднее значение
        """
        if not self._history:
            return 0.0
        return sum(s.value for s in self._history) / len(self._history)

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _classify(self, result: CognitiveResult) -> RewardType:
        """
        Определить тип вознаграждения по результату цикла.

        Приоритет проверок:
          1. PENALTY  — "refuse" или metadata["corrected"]
          2. EPISTEMIC/COHERENCE/COMPLETION — по action из _ACTION_MAP
          3. EFFICIENCY — высокая уверенность + быстрый ответ
          4. ACCURACY — "answer"/"respond" или default
        """
        action = result.action.lower().strip()

        # 1. Штраф
        if action == "refuse" or result.metadata.get("corrected"):
            return RewardType.PENALTY

        # 2. Прямой маппинг из _ACTION_MAP
        if action in _ACTION_MAP:
            return _ACTION_MAP[action]

        # 3. Efficiency: высокая уверенность + быстрый ответ
        elapsed_ms = float(result.metadata.get("elapsed_ms", 9999))
        if (
            result.confidence >= _EFFICIENCY_CONFIDENCE_THRESHOLD
            and elapsed_ms < _EFFICIENCY_ELAPSED_MS_THRESHOLD
        ):
            return RewardType.EFFICIENCY

        # 4. Default: ACCURACY
        return RewardType.ACCURACY

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"RewardEngine("
            f"history={len(self._history)}/{self._history.maxlen} | "
            f"mean={self.sliding_mean():.3f})"
        )
