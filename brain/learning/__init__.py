"""
learning — Система обучения (онлайн + replay + self-supervised).

Модули:
    online_learner.py       — обновление знаний из новых входных данных в реальном времени
    replay_engine.py        — периодическое воспроизведение эпизодов для закрепления
    self_supervised.py      — самообучение на основе предсказаний и ошибок
    hypothesis_validator.py — проверка гипотез через накопленный опыт
    forgetting_manager.py   — управляемое забывание (кривая Эббингауза)

TODO (Stage I): Реализовать систему обучения.
    - OnlineLearner: обновление весов/знаний после каждого взаимодействия
    - ReplayEngine: периодическое воспроизведение эпизодов из EpisodicMemory
    - SelfSupervisedLearner: согласованность text ↔ image ↔ audio предсказаний
    - HypothesisValidator: проверка гипотез через накопленный опыт
    - ForgettingManager: управляемое забывание (кривая Эббингауза, spaced repetition)
    Зависимости: MemoryManager (Stage A), HypothesisEngine (Stage F), EpisodicMemory
    См. docs/layers/06_learning_loop.md
"""
