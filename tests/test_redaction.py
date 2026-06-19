from apps.backend.governance.redaction import redact
from apps.backend.governance.data_governance import classify


def test_secret_removed():
    r = redact("token=supersecretvalue123 here", classify("token=supersecretvalue123"))
    assert "supersecretvalue123" not in r.redacted_text
    assert "[SECRET_REMOVED]" in r.redacted_text
    assert r.secrets_blocked >= 1


def test_email_replaced():
    r = redact("write to a.b@example.com now", None)
    assert "a.b@example.com" not in r.redacted_text
    assert "[EMAIL_1]" in r.redacted_text
    assert r.pii_replaced >= 1


def test_iban_replaced():
    r = redact("IBAN DE12345678901234567890 ok", None)
    assert "DE12345678901234567890" not in r.redacted_text
    assert "[IBAN_1]" in r.redacted_text


def test_mapping_has_no_original_value():
    r = redact("mail x@y.de", None)
    for placeholder, type_label in r.replacements.items():
        assert "@" not in type_label
        assert type_label in {"email", "iban", "phone", "card", "ip"}


def test_redaction_applied_flag():
    assert redact("nothing sensitive", None).redaction_applied is False
    assert redact("mail a@b.de", None).redaction_applied is True
