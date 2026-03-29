"""
learning — Система обучения (онлайн + replay + gap detection).

Реализованные модули (Этап I):
    online_learner.py           — OnlineLearner: обновление памяти после каждого цикла
                                  (Хеббовское обучение, confirm/deny фактов, source trust)
    knowledge_gap_detector.py   — KnowledgeGapDetector: фиксация пробелов в знаниях
                                  (MISSING / WEAK / OUTDATED, дедупликация)
    replay_engine.py            — ReplayEngine: воспроизведение эпизодов в idle-режиме
                                  (4 стратегии, stale pruning, CPU-aware)

Запланированные модули (Этап J+):
    self_supervised.py      — самообучение на основе предсказаний и ошибок
    hypothesis_validator.py — проверка гипотез через накопленный опыт
    forgetting_manager.py   — управляемое забывание (кривая Эббингауза, spaced repetition)

Интеграция (Этап J):
    - OnlineLearner вызывается из CognitivePipeline.step_post_cycle()
    - ReplayEngine вызывается из idle hook / CLI --autonomous
    - KnowledgeGapDetector вызывается после каждого retrieve()

Зависимости: MemoryManager, CognitiveResult, ContractMixin
См. docs/layers/06_learning_loop.md
"""

from .knowledge_gap_detector import (
    GapSeverity,
    GapType,
    KnowledgeGap,
    KnowledgeGapDetector,
)
from .online_learner import (
    OnlineLearner,
    OnlineLearningUpdate,
)
from .replay_engine import (
    ReplayEngine,
    ReplaySession,
    ReplayStrategy,
)

__all__ = [
    # online_learner (I.1)
    "OnlineLearner",
    "OnlineLearningUpdate",
    # knowledge_gap_detector (I.2)
    "GapSeverity",
    "GapType",
    "KnowledgeGap",
    "KnowledgeGapDetector",
    # replay_engine (I.3)
    "ReplayStrategy",
    "ReplaySession",
    "ReplayEngine",
]
