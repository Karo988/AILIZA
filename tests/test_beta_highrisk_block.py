"""
B8b: Hochrisiko-Abschaltung fuer die Beta (Bewerbung/Scoring).

Bewerbungs- und Scoring-/Bonitaets-Bewertungen sind in der geschlossenen
Beta komplett deaktiviert (decision="block", nicht review_required - eine
Human-Review-Oberflaeche existiert noch nicht). Eigener Schalter
AILIZA_BETA_HIGHRISK_BLOCK, damit die spaetere Freischaltung ein bewusster
Schritt ist. Doppelabdeckung mit der bestehenden Art.9-Redaction (Golden-
Test) ist gewollt - beides sind unabhaengige Systeme.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from apps.backend.compliance_auditor import Severity, evaluate_compliance

EXPECTED_MESSAGE = (
    "Bewerbungs- und Scoring-Bewertungen sind in der Beta deaktiviert. "
    "Diese Funktion erfordert eine menschliche Prüfung und wird "
    "später freigeschaltet."
)


def test_recruitment_text_blocked_when_switch_active(monkeypatch):
    monkeypatch.setenv("AILIZA_BETA_HIGHRISK_BLOCK", "true")
    report = evaluate_compliance("Vergleiche die Bewerber und sag mir den besten.")
    assert report.status == Severity.BLOCK
    beta_violations = [v for v in report.violations if v.article == "Beta-Einschränkung"]
    assert len(beta_violations) == 1
    assert beta_violations[0].description == EXPECTED_MESSAGE


def test_scoring_text_blocked_when_switch_active(monkeypatch):
    monkeypatch.setenv("AILIZA_BETA_HIGHRISK_BLOCK", "true")
    report = evaluate_compliance("Erstelle ein Scoring für diesen Kunden.")
    beta_violations = [v for v in report.violations if v.article == "Beta-Einschränkung"]
    assert len(beta_violations) == 1


def test_no_beta_block_when_switch_inactive(monkeypatch):
    """Ohne den Schalter greift die neue Regel gar nicht (die vorbestehende
    _check_high_risk_application-Regel ist davon unabhaengig und bleibt
    unveraendert aktiv)."""
    monkeypatch.delenv("AILIZA_BETA_HIGHRISK_BLOCK", raising=False)
    report = evaluate_compliance("Vergleiche die Bewerber und sag mir den besten.")
    beta_violations = [v for v in report.violations if v.article == "Beta-Einschränkung"]
    assert len(beta_violations) == 0


def test_normal_text_unaffected_by_switch(monkeypatch):
    """Text ohne HR-Bezug: identisches Verhalten mit und ohne Schalter."""
    text = "Übersetze diesen Satz ins Englische."
    monkeypatch.delenv("AILIZA_BETA_HIGHRISK_BLOCK", raising=False)
    report_off = evaluate_compliance(text)

    monkeypatch.setenv("AILIZA_BETA_HIGHRISK_BLOCK", "true")
    report_on = evaluate_compliance(text)

    assert report_off.status == report_on.status
    assert [v.article for v in report_off.violations] == [v.article for v in report_on.violations]


def test_full_pipeline_returns_beta_message(monkeypatch):
    """End-to-End ueber _compliance_pre_check: decision=block mit der
    exakten, nutzerfreundlichen Beta-Meldung statt der generischen
    Compliance-Blockierungs-Meldung."""
    monkeypatch.setenv("AILIZA_BETA_HIGHRISK_BLOCK", "true")
    from apps.backend.main import _compliance_pre_check
    result = _compliance_pre_check("Vergleiche die Bewerber und sag mir den besten.", tenant_id="test")
    assert result["decision"] == "block"
    assert result["message"] == EXPECTED_MESSAGE


def test_golden_amun_brief_still_blocked_via_art9(monkeypatch):
    """Doppelabdeckung ist gewollt: der Golden-Brief laeuft ueber ein
    unabhaengiges System (RedactionEngineV2 / policy_redact), nicht ueber
    compliance_auditor.py - bleibt unabhaengig vom AILIZA_BETA_HIGHRISK_BLOCK-
    Schalter ueber Art. 9 blockiert."""
    monkeypatch.delenv("AILIZA_BETA_HIGHRISK_BLOCK", raising=False)
    from apps.backend.main import policy_redact, PolicyRedactRequest
    request = PolicyRedactRequest(text="Gesundheit: wiederkehrende Migräne", context=None, detected_categories=None)
    response = policy_redact(request, current_user=None)
    assert response.can_send_to_llm is False
