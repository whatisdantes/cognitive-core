"""
safety — Безопасность и границы системы (Stage L).

Модули:
    audit_logger.py      — L.4: AuditEvent + AuditLogger (JSONL, rotation)
    source_trust.py      — L.1: SourceTrustScore + SourceTrustManager
    conflict_detector.py — L.2: Conflict + ConflictDetector (SemanticNode-level)
    boundary_guard.py    — L.3: GuardResult + BoundaryGuard (PII redaction, gates)
    policy_layer.py      — L.5: SafetyDecision + SafetyPolicyLayer (SF-1/2/3)

Зависимости: SourceMemory, SemanticNode, BrainLogger (NullObject pattern).
См. docs/layers/10_safety_boundaries.md
"""

from brain.safety.audit_logger import AUDIT_EVENTS, AuditEvent, AuditLogger
from brain.safety.boundary_guard import BoundaryGuard, GuardResult
from brain.safety.conflict_detector import Conflict, ConflictDetector
from brain.safety.policy_layer import SafetyDecision, SafetyPolicyLayer
from brain.safety.source_trust import SourceTrustManager, SourceTrustScore

__all__ = [
    # L.4
    "AuditEvent",
    "AuditLogger",
    "AUDIT_EVENTS",
    # L.1
    "SourceTrustScore",
    "SourceTrustManager",
    # L.2
    "Conflict",
    "ConflictDetector",
    # L.3
    "GuardResult",
    "BoundaryGuard",
    # L.5
    "SafetyDecision",
    "SafetyPolicyLayer",
]
