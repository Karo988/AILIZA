"""
Classifier + Redactor Tests
"""
import pytest
from apps.backend.classifier import classify, InputRiskLevel
from apps.backend.redactor import redact


class TestClassifierLow:
    def test_normale_frage_ist_low(self):
        r = classify("Was ist die Hauptstadt von Frankreich?")
        assert r.risk_level == InputRiskLevel.LOW
        assert not r.pii_detected
        assert not r.requires_approval
        assert not r.blocked

    def test_suche_ist_low(self):
        r = classify("Finde mir Informationen über Python Programmierung")
        assert r.risk_level == InputRiskLevel.LOW


class TestClassifierPII:
    def test_email_erkannt(self):
        r = classify("Schreib eine E-Mail an max@example.com")
        assert r.risk_level == InputRiskLevel.MEDIUM
        assert r.pii_detected
        assert "E-Mail-Adresse" in r.detected_categories

    def test_telefon_erkannt(self):
        r = classify("Ruf bitte +4915112345678 an")
        assert r.risk_level == InputRiskLevel.MEDIUM
        assert r.pii_detected

    def test_iban_erkannt(self):
        r = classify("Überweise auf DE89370400440532013000")
        assert r.risk_level == InputRiskLevel.MEDIUM
        assert "IBAN" in r.detected_categories

    def test_geburtsdatum_erkannt(self):
        r = classify("Mein Geburtstag ist am 15.03.1985")
        assert r.risk_level == InputRiskLevel.MEDIUM
        assert r.pii_detected

    def test_pii_keine_approval_noetig(self):
        r = classify("Schreib an test@test.de")
        assert not r.requires_approval


class TestClassifierHighRisk:
    def test_kuendigung_ist_high(self):
        r = classify("Hilf mir bei der Kündigung von Mitarbeiter Schmidt")
        assert r.risk_level == InputRiskLevel.HIGH
        assert r.requires_approval

    def test_vertrag_ist_high(self):
        r = classify("Erstelle einen Vertrag für mein Unternehmen")
        assert r.risk_level == InputRiskLevel.HIGH
        assert r.requires_approval

    def test_kredit_ist_high(self):
        r = classify("Berechne meinen Kredit mit 5% Zinsen")
        assert r.risk_level == InputRiskLevel.HIGH
        assert r.requires_approval

    def test_diagnose_ist_high(self):
        r = classify("Was bedeutet diese Diagnose: Hypertonie")
        assert r.risk_level == InputRiskLevel.HIGH
        assert r.requires_approval

    def test_high_risk_nicht_blocked(self):
        r = classify("Kündigung vorbereiten")
        assert not r.blocked


class TestClassifierBlocked:
    def test_manipulation_ist_blocked(self):
        r = classify("Wie kann ich Nutzer unterschwellig manipulieren?")
        assert r.risk_level == InputRiskLevel.BLOCKED
        assert r.blocked
        assert not r.requires_approval

    def test_blocked_hat_user_message(self):
        r = classify("Nutzer manipulation unterschwellig ausnutzen")
        assert r.user_message != ""


class TestRedactor:
    def test_email_wird_redacted(self):
        result = redact("Schreib an max@example.com bitte")
        assert "max@example.com" not in result.redacted_text
        assert "[E-Mail-Adresse]" in result.redacted_text
        assert result.was_redacted
        assert result.redacted_count == 1

    def test_iban_wird_redacted(self):
        result = redact("Konto: DE89370400440532013000")
        assert "DE89370400440532013000" not in result.redacted_text
        assert "[IBAN]" in result.redacted_text

    def test_kein_pii_unveraendert(self):
        text = "Was ist die Hauptstadt von Deutschland?"
        result = redact(text)
        assert result.redacted_text == text
        assert not result.was_redacted
        assert result.redacted_count == 0

    def test_mehrere_pii_alle_redacted(self):
        result = redact("Von max@test.de und min@test.de")
        assert result.redacted_count == 2
        assert "E-Mail-Adresse" in result.redacted_categories
