"""
brain/motivation — Система вознаграждения и мотивации (Stage M).

Биологический аналог: VTA (вентральная тегментальная область) + прилежащее ядро.

Публичные экспорты:
  RewardType       — перечисление типов вознаграждений (M.1)
  REWARD_VALUES    — словарь значений вознаграждений по типу (M.1)
  RewardSignal     — dataclass сигнала вознаграждения (M.1)
  RewardEngine     — движок вычисления вознаграждений (M.1)
  MotivationState  — dataclass состояния мотивации (M.2)
  MotivationEngine — движок мотивации с EMA-аккумулятором (M.2)
  CuriosityEngine  — движок любопытства (M.3)
  IdleDispatcher   — диспетчер фоновой idle-работы (U-D)
"""

from brain.motivation.curiosity_engine import CuriosityEngine
from brain.motivation.idle_dispatcher import (
    IdleCandidate,
    IdleDispatcher,
    IdleDispatcherConfig,
    IdleDispatchResult,
)
from brain.motivation.motivation_engine import MotivationEngine, MotivationState
from brain.motivation.reward_engine import REWARD_VALUES, RewardEngine, RewardSignal, RewardType

__all__ = [
    # M.1 — RewardEngine
    "RewardType",
    "REWARD_VALUES",
    "RewardSignal",
    "RewardEngine",
    # M.2 — MotivationEngine
    "MotivationState",
    "MotivationEngine",
    # M.3 — CuriosityEngine
    "CuriosityEngine",
    # U-D — IdleDispatcher
    "IdleCandidate",
    "IdleDispatcherConfig",
    "IdleDispatchResult",
    "IdleDispatcher",
]
