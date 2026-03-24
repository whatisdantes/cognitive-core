"""
safety — Безопасность и границы системы.

Модули:
    source_trust.py     — оценка надёжности источников информации
    conflict_detector.py — обнаружение конфликтов между фактами и источниками
    boundary_guard.py   — ограничения на действия и выводы системы
    audit_logger.py     — аудит-лог всех решений с высоким риском

TODO (Stage L): Реализовать систему безопасности.
    - SourceTrust: оценка надёжности источников (расширение SourceMemory trust scores)
    - ConflictDetector: обнаружение конфликтов между фактами из разных источников
    - BoundaryGuard: ограничения на действия системы (запрещённые темы, лимиты)
    - AuditLogger: аудит-лог всех решений с высоким риском (JSONL, immutable)
    Зависимости: SourceMemory (Stage A), ContradictionDetector (Stage F+), BrainLogger (Stage C)
    См. docs/layers/10_safety_boundaries.md
"""
