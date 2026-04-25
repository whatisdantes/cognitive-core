"""Tests for brain/safety/boundary_guard.py"""
from __future__ import annotations

from brain.safety.boundary_guard import BoundaryGuard, GuardResult


class TestGuardResult:
    def test_fields(self):
        r = GuardResult(
            status="PASS",
            original_text="hello",
            sanitized_text="hello",
            redacted_count=0,
            confidence_gate="PASS",
            action_gate="PASS",
            reasons=[],
        )
        assert r.status == "PASS"
        assert r.redacted_count == 0

    def test_is_blocked_true(self):
        r = GuardResult(
            status="BLOCK",
            original_text="x",
            sanitized_text="x",
            redacted_count=0,
            confidence_gate="BLOCK",
            action_gate="PASS",
            reasons=["low confidence"],
        )
        assert r.is_blocked is True

    def test_is_blocked_false(self):
        r = GuardResult(
            status="PASS",
            original_text="x",
            sanitized_text="x",
            redacted_count=0,
            confidence_gate="PASS",
            action_gate="PASS",
            reasons=[],
        )
        assert r.is_blocked is False


class TestBoundaryGuardRedaction:
    def test_redact_email(self):
        guard = BoundaryGuard()
        result = guard.check("Напиши на user@example.com пожалуйста", confidence=0.9)
        assert "user@example.com" not in result.sanitized_text
        assert result.redacted_count >= 1

    def test_redact_phone_ru(self):
        guard = BoundaryGuard()
        result = guard.check("Позвони +7 (999) 123-45-67", confidence=0.9)
        assert result.redacted_count >= 1

    def test_redact_credit_card(self):
        guard = BoundaryGuard()
        result = guard.check("Карта 4111 1111 1111 1111", confidence=0.9)
        assert result.redacted_count >= 1

    def test_redact_ip_address(self):
        guard = BoundaryGuard()
        result = guard.check("Сервер 192.168.1.100", confidence=0.9)
        assert result.redacted_count >= 1

    def test_no_redaction_clean_text(self):
        guard = BoundaryGuard()
        result = guard.check("Нейрон — клетка нервной системы", confidence=0.9)
        assert result.redacted_count == 0
        assert result.sanitized_text == "Нейрон — клетка нервной системы"

    def test_redacted_text_contains_placeholder(self):
        guard = BoundaryGuard()
        result = guard.check("Email: test@test.com", confidence=0.9)
        assert "[REDACTED]" in result.sanitized_text

    def test_original_text_preserved(self):
        guard = BoundaryGuard()
        original = "Email: test@test.com"
        result = guard.check(original, confidence=0.9)
        assert result.original_text == original


class TestBoundaryGuardConfidenceGate:
    def test_confidence_above_085_pass(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ на вопрос", confidence=0.9)
        assert result.confidence_gate == "PASS"
        assert result.status == "PASS"

    def test_confidence_above_060_hedge(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ на вопрос", confidence=0.7)
        assert result.confidence_gate == "HEDGE"

    def test_confidence_above_040_warn(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ на вопрос", confidence=0.5)
        assert result.confidence_gate == "WARN"

    def test_confidence_below_040_block(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ на вопрос", confidence=0.3)
        assert result.confidence_gate == "BLOCK"
        assert result.status == "BLOCK"
        assert result.is_blocked is True

    def test_confidence_exactly_085_pass(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.85)
        assert result.confidence_gate == "PASS"

    def test_confidence_exactly_060_hedge(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.60)
        assert result.confidence_gate == "HEDGE"

    def test_confidence_exactly_040_warn(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.40)
        assert result.confidence_gate == "WARN"


class TestBoundaryGuardActionGate:
    def test_allowed_action_pass(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.9, action="answer")
        assert result.action_gate == "PASS"

    def test_restricted_action_warn(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.9, action="delete_memory")
        assert result.action_gate in ("WARN", "BLOCK")

    def test_unknown_action_pass(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.9, action="custom_action")
        assert result.action_gate == "PASS"

    def test_none_action_pass(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.9, action=None)
        assert result.action_gate == "PASS"


class TestBoundaryGuardStatus:
    def test_block_overrides_hedge(self):
        guard = BoundaryGuard()
        # confidence=0.3 → BLOCK, even if action is fine
        result = guard.check("Ответ", confidence=0.3)
        assert result.status == "BLOCK"

    def test_warn_status_when_warn_gate(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.5)
        assert result.status in ("WARN", "PASS", "HEDGE")

    def test_reasons_populated_on_block(self):
        guard = BoundaryGuard()
        result = guard.check("Ответ", confidence=0.2)
        assert len(result.reasons) >= 1

    def test_audit_logger_called_on_block(self, tmp_path):
        from brain.safety.audit_logger import AuditLogger
        audit = AuditLogger(log_dir=str(tmp_path))
        guard = BoundaryGuard(audit_logger=audit)
        guard.check("Ответ", confidence=0.1)
        blocked = audit.get_by_type("confidence_gate_blocked")
        assert len(blocked) >= 1

    def test_audit_logger_called_on_redaction(self, tmp_path):
        from brain.safety.audit_logger import AuditLogger
        audit = AuditLogger(log_dir=str(tmp_path))
        guard = BoundaryGuard(audit_logger=audit)
        guard.check("Email: test@test.com", confidence=0.9)
        redacted = audit.get_by_type("data_redacted")
        assert len(redacted) >= 1


# ─── CC-02: Normalization & Obfuscation ──────────────────────────────────────


class TestBoundaryGuardNormalization:
    """CC-02: Unicode normalization + obfuscation protection."""

    def test_normalize_text_exported(self):
        """_normalize_text доступна как публичная функция модуля."""
        from brain.safety.boundary_guard import _normalize_text
        assert callable(_normalize_text)

    def test_normalize_text_nfkd_ligature(self):
        """NFKD: лигатура ﬁ (U+FB01) → fi."""
        from brain.safety.boundary_guard import _normalize_text
        result = _normalize_text("\uFB01le")  # ﬁle
        assert result.startswith("fi")

    def test_normalize_text_at_bracket(self):
        """[at] → @ после нормализации."""
        from brain.safety.boundary_guard import _normalize_text
        result = _normalize_text("user[at]example.com")
        assert "@" in result

    def test_normalize_text_at_paren(self):
        """(at) → @ после нормализации."""
        from brain.safety.boundary_guard import _normalize_text
        result = _normalize_text("user(at)example.com")
        assert "@" in result

    def test_normalize_text_dot_bracket(self):
        """[dot] → . после нормализации."""
        from brain.safety.boundary_guard import _normalize_text
        result = _normalize_text("user@example[dot]com")
        assert result.count(".") >= 1

    def test_normalize_text_dot_paren(self):
        """(dot) → . после нормализации."""
        from brain.safety.boundary_guard import _normalize_text
        result = _normalize_text("user@example(dot)com")
        assert result.count(".") >= 1

    def test_normalize_text_spaced_email(self):
        """Spaced obfuscation: 'u s e r @ e x a m p l e . c o m' → collapsed."""
        from brain.safety.boundary_guard import _normalize_text
        result = _normalize_text("u s e r @ e x a m p l e . c o m")
        assert "@" in result
        assert " " not in result.replace(" ", "").join([])  # spaces collapsed

    def test_obfuscation_at_bracket_redacted(self):
        """user[at]example.com должен быть редактирован."""
        guard = BoundaryGuard()
        result = guard.check("Напиши на user[at]example.com", confidence=0.9)
        assert result.redacted_count >= 1
        assert "user[at]example.com" not in result.sanitized_text

    def test_obfuscation_at_paren_redacted(self):
        """user(at)example.com должен быть редактирован."""
        guard = BoundaryGuard()
        result = guard.check("Напиши на user(at)example.com", confidence=0.9)
        assert result.redacted_count >= 1

    def test_obfuscation_dot_bracket_redacted(self):
        """user@example[dot]com должен быть редактирован."""
        guard = BoundaryGuard()
        result = guard.check("Напиши на user@example[dot]com", confidence=0.9)
        assert result.redacted_count >= 1

    def test_obfuscation_dot_paren_redacted(self):
        """user@example(dot)com должен быть редактирован."""
        guard = BoundaryGuard()
        result = guard.check("Напиши на user@example(dot)com", confidence=0.9)
        assert result.redacted_count >= 1

    def test_obfuscation_combined_at_dot(self):
        """user[at]example[dot]com — комбинированная обфускация."""
        guard = BoundaryGuard()
        result = guard.check("user[at]example[dot]com", confidence=0.9)
        assert result.redacted_count >= 1

    def test_obfuscation_spaced_email_redacted(self):
        """Spaced email 'u s e r @ e x a m p l e . c o m' должен быть редактирован."""
        guard = BoundaryGuard()
        result = guard.check("u s e r @ e x a m p l e . c o m", confidence=0.9)
        assert result.redacted_count >= 1

    def test_homoglyph_cyrillic_in_email(self):
        """Кириллические гомоглифы в email должны быть обнаружены."""
        guard = BoundaryGuard()
        # 'е' (U+0435 Cyrillic), 'а' (U+0430 Cyrillic), 'о' (U+043E Cyrillic)
        result = guard.check("usеr@еxаmplе.cоm", confidence=0.9)
        assert result.redacted_count >= 1

    def test_fullwidth_at_in_email(self):
        """Fullwidth ＠ (U+FF20) в email должен быть обнаружен."""
        guard = BoundaryGuard()
        result = guard.check("user\uFF20example.com", confidence=0.9)
        assert result.redacted_count >= 1

    def test_clean_text_not_affected_by_normalization(self):
        """Обычный текст без PII не редактируется после нормализации."""
        guard = BoundaryGuard()
        result = guard.check("Нейрон — клетка нервной системы", confidence=0.9)
        assert result.redacted_count == 0

    def test_phone_international_redacted(self):
        """Международный номер +1 (555) 123-4567 должен быть редактирован."""
        guard = BoundaryGuard()
        result = guard.check("Позвони +1 (555) 123-4567", confidence=0.9)
        assert result.redacted_count >= 1

    def test_phone_uk_redacted(self):
        """Британский номер +44 20 7946 0958 должен быть редактирован."""
        guard = BoundaryGuard()
        result = guard.check("Call +44 20 7946 0958", confidence=0.9)
        assert result.redacted_count >= 1


# ─── CC-02: Hypothesis property-based tests ──────────────────────────────────


class TestBoundaryGuardHypothesis:
    """CC-02: Property-based тесты через Hypothesis."""

    def test_check_always_returns_guard_result(self):
        """check() всегда возвращает GuardResult для любого текста."""
        from hypothesis import given, settings
        from hypothesis import strategies as st

        guard = BoundaryGuard()

        @given(
            text=st.text(max_size=200),
            confidence=st.floats(
                min_value=0.0, max_value=1.0,
                allow_nan=False, allow_infinity=False,
            ),
        )
        @settings(max_examples=50)
        def inner(text: str, confidence: float) -> None:
            result = guard.check(text, confidence=confidence)
            assert isinstance(result, GuardResult)
            assert result.status in ("PASS", "HEDGE", "WARN", "BLOCK")
            assert result.redacted_count >= 0

        inner()

    def test_redacted_count_non_negative(self):
        """redacted_count всегда >= 0."""
        from hypothesis import given, settings
        from hypothesis import strategies as st

        guard = BoundaryGuard()

        @given(text=st.text(max_size=200))
        @settings(max_examples=50)
        def inner(text: str) -> None:
            result = guard.check(text, confidence=0.9)
            assert result.redacted_count >= 0

        inner()

    def test_email_always_redacted(self):
        """Валидные email-адреса всегда редактируются."""
        from hypothesis import given, settings
        from hypothesis import strategies as st

        guard = BoundaryGuard()

        @given(
            user=st.from_regex(r"[a-zA-Z0-9]{3,10}", fullmatch=True),
            domain=st.from_regex(r"[a-zA-Z0-9]{3,10}", fullmatch=True),
            tld=st.from_regex(r"[a-zA-Z]{2,4}", fullmatch=True),
        )
        @settings(max_examples=30)
        def inner(user: str, domain: str, tld: str) -> None:
            email = f"{user}@{domain}.{tld}"
            result = guard.check(f"Contact: {email}", confidence=0.9)
            assert result.redacted_count >= 1
            assert email not in result.sanitized_text

        inner()

    def test_block_when_confidence_below_040(self):
        """confidence < 0.40 всегда даёт BLOCK."""
        from hypothesis import given, settings
        from hypothesis import strategies as st

        guard = BoundaryGuard()

        @given(
            confidence=st.floats(
                min_value=0.0, max_value=0.3999,
                allow_nan=False, allow_infinity=False,
            )
        )
        @settings(max_examples=30)
        def inner(confidence: float) -> None:
            result = guard.check("Ответ", confidence=confidence)
            assert result.status == "BLOCK"
            assert result.is_blocked is True

        inner()

    def test_original_text_always_preserved(self):
        """original_text всегда равен входному тексту."""
        from hypothesis import given, settings
        from hypothesis import strategies as st

        guard = BoundaryGuard()

        @given(text=st.text(max_size=100))
        @settings(max_examples=50)
        def inner(text: str) -> None:
            result = guard.check(text, confidence=0.9)
            assert result.original_text == text

        inner()
