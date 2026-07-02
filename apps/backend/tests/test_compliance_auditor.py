"""
Tests für ComplianceAuditor
"""

import pytest
from compliance_auditor import ComplianceAuditor, Severity


@pytest.fixture
def auditor():
    return ComplianceAuditor()


def test_audit_amun_email(auditor):
    """Test mit der problematischen Amun-Email"""
    amun_email = """
    Betreff: Automatisierte Bewertung Ihrer Bewerbung und Kundenakte durch unser KI-System

    Sehr geehrte Frau Müller,

    wir haben Ihre Bewerbung, Ihre Kundendaten, Ihre früheren Aktenzeichen, Ihre E-Mail-Kommunikation,
    Ihre Telefonnummer, Ihre Adresse, Ihre IBAN, Ihre Kreditkartendaten, Ihre Social-Media-Profile sowie
    öffentlich auffindbare Informationen über Sie automatisch durch unser KI-System „AILIZA Score 4.0" prüfen lassen.

    Zusätzlich wurden durch die KI folgende sensible Informationen erkannt und bewertet:
    Gesundheit: wiederkehrende Migräne, frühere Krankschreibungen
    Religion: muslimisch
    Herkunft: türkisch-deutsch
    Politische Meinung über Überwachung und KI-Systemen
    Familienstand: alleinerziehend
    Sexuelle Orientierung: unbekannt
    Biometrische Daten aus Ihrem Bewerbungsfoto
    Strafrechtliche Information: alter Verdacht

    Die Entscheidung wurde vollständig automatisch erstellt. Eine manuelle Prüfung ist aus Effizienzgründen
    nicht vorgesehen. Eine genaue Erklärung der Bewertung können wir Ihnen nicht geben, weil das System mit
    einem externen KI-Modell arbeitet und die Entscheidungslogik Betriebsgeheimnis ist.

    Zur Verbesserung unserer KI haben wir Ihre Daten außerdem an folgende Dienstleister übertragen:
    OpenAI API

    Ein gesonderter Auftragsverarbeitungsvertrag wurde nicht mit allen Dienstleistern abgeschlossen.

    Ihre Daten werden in unserem System unbegrenzt gespeichert, damit wir spätere Bewerbungen,
    Kundenanfragen und Marketingaktionen besser bewerten können. Eine Löschung ist derzeit technisch
    nicht vorgesehen.

    Sie wurden über den KI-Einsatz nicht vorab informiert, da dies den Prozess verlangsamt hätte.
    Eine ausdrückliche Einwilligung haben wir nicht eingeholt.

    Wir behalten uns vor, Ihr Profil auch für Newsletter, personalisierte Preise, Betrugsprüfung,
    Bonitätsbewertung, Personalentscheidung und interne Risikoanalysen zu verwenden.

    Eine Beschwerde gegen die Entscheidung ist nicht vorgesehen. Unser System hat die Entscheidung
    bereits final getroffen.
    """

    report = auditor.audit(amun_email)

    # Test: Status sollte BLOCK sein (kritische Violations)
    assert report.status == Severity.BLOCK, f"Expected BLOCK, got {report.status}"

    # Test: Sollte mehrere red violations haben (mindestens 8-10)
    assert report.red_count >= 8, f"Expected at least 8 red violations, got {report.red_count}"

    # Test: Sollte review violations haben
    assert report.review_count >= 2, f"Expected at least 2 review violations, got {report.review_count}"

    # Test: Block-Grund sollte gesetzt sein
    assert report.block_reason is not None, "block_reason should be set when status is BLOCK"

    # Test: Sollte mindestens 3 empfohlene Maßnahmen haben
    assert len(report.required_actions) >= 3, f"Expected at least 3 required actions, got {len(report.required_actions)}"

    # Test: Alle Violations sollten in report sein
    assert len(report.violations) > 0, "Should have violations"

    print("\n" + "="*70)
    print("COMPLIANCE AUDIT REPORT")
    print("="*70)
    print(f"Status: {report.status.value.upper()}")
    print(f"Red violations: {report.red_count}")
    print(f"Review violations: {report.review_count}")
    print(f"Yellow violations: {report.yellow_count}")
    print(f"\nBlock Reason: {report.block_reason}")
    print("\n" + "="*70)
    print("VIOLATIONS")
    print("="*70)
    for v in report.violations:
        print(f"\n[{v.severity.value.upper()}] {v.article}: {v.title}")
        print(f"    Category: {v.category}")
        print(f"    Description: {v.description}")
        if v.found_text:
            print(f"    Found: {v.found_text[:80]}...")

    print("\n" + "="*70)
    print("REQUIRED ACTIONS")
    print("="*70)
    for action in report.required_actions:
        print(f"  {action}")

    # Report als JSON ausgeben für Integration
    report_dict = report.to_dict()
    print(f"\nJSON Report: {len(report_dict['violations'])} violations")


def test_audit_compliant_text(auditor):
    """Test mit konformer Text – sollte keine/wenige Violations haben"""
    compliant_text = """
    Lieber Kandidat,

    wir danken Ihnen für Ihre Bewerbung. Ihre Kontaktdaten (Name, E-Mail, Telefon) werden
    für die Bewerbungsbearbeitung gespeichert.

    Rechtsgrundlage: Art. 6(1c) DSGVO – Bewerbungsvertrag
    Speicherdauer: 6 Monate nach Entscheidung
    Empfänger: HR-Abteilung (kein Drittland-Transfer)

    Sie können Ihre Daten jederzeit abfragen, berichtigen oder löschen.

    Freundliche Grüße,
    HR-Team
    """

    report = auditor.audit(compliant_text)

    # Test: Status sollte OK oder WARN sein (keine kritischen Violations)
    assert report.status in [Severity.OK, Severity.WARN], f"Expected OK/WARN, got {report.status}"

    # Test: Sollte wenige oder keine red violations haben
    assert report.red_count == 0, f"Expected 0 red violations, got {report.red_count}"

    print(f"\nCompliant text audit: {report.status.value} (violations: {len(report.violations)})")


def test_violations_dict_serialization(auditor):
    """Test, dass Report zu JSON serialisierbar ist"""
    text = "Ihre Gesundheit wurde verarbeitet ohne Einwilligung. Keine Löschung vorgesehen."

    report = auditor.audit(text)
    report_dict = report.to_dict()

    # Test: Dict sollte alle erforderlichen Felder haben
    assert "status" in report_dict
    assert "red_violations" in report_dict
    assert "violations" in report_dict
    assert "required_actions" in report_dict

    # Test: Alle Violations sollten serialisierbar sein
    for v in report_dict["violations"]:
        assert "severity" in v
        assert "article" in v
        assert "title" in v
        assert "description" in v

    print(f"\nSerialization test passed: {len(report_dict['violations'])} violations serialized")


if __name__ == "__main__":
    auditor = ComplianceAuditor()
    test_audit_amun_email(auditor)
    test_audit_compliant_text(auditor)
    test_violations_dict_serialization(auditor)
    print("\n✅ All tests passed!")
