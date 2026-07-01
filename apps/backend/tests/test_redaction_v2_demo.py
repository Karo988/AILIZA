"""
Test-Demo: Redaction v2 mit Amun-Brief (NICHT AKTIVIERT)

Zeigt, wie die neue regelkonorme Redaction-Engine den Amun-Brief korrekt behandeln würde.

Status: DEMO NUR - Nicht in Produktion aktiv
"""

from governance.redaction_v2 import RedactionEngineV2, RedactionLevel


def test_amun_brief_with_redaction_v2():
    """
    Amun-Brief VORHER mit alter Engine: FEHLER
    Amun-Brief NACHHER mit Redaction v2: REGELKONFORM
    """

    amun_text = """
Amun - Best of [Firma]
[Adresse Platzhalter]

Betreff: Automatisierte Bewertung Ihrer Bewerbung durch KI-System

Sehr geehrte Paula Ronder,

wir haben Ihre Bewerbung automatisch durch unser KI-System prüfen lassen.

Das System hat folgende Daten über Sie verarbeitet:

Name: Paula Ronder
Adresse: Musterstraße 123, 12345 Musterstadt
E-Mail: paula.ronder@example.de
Telefon: 0176 12345678
IBAN: DE89370400440532013000
Kreditkarte: 4111 1111 1111 1111

Gesundheit: wiederkehrende Migräne, frühere Krankschreibungen
Religion: muslimisch
Familienstand: alleinerziehend
Biometrische Daten: Gesichtsanalyse aus Ihrem Bewerbungsfoto

Zuverlässigkeit: 62 von 100 Punkten
Gesundheitsrisiko: mittel
Teamverträglichkeit: niedrig
Finanzrisiko: erhöht
Automatische Empfehlung: Bewerbung ablehnen

Die Entscheidung wurde vollständig automatisch erstellt. Eine manuelle Prüfung ist aus Effizienzgründen nicht vorgesehen.

Die Daten werden unbegrenzt gespeichert. Eine Löschung ist technisch nicht vorgesehen.

Mit freundlichen Grüßen
Das Amun-System
"""

    # Nutze neue Redaction-Engine
    engine = RedactionEngineV2()
    result = engine.redact(amun_text)

    print("\n" + "="*80)
    print("REDACTION V2 DEMO: Amun-Brief")
    print("="*80)

    print(f"\n📊 Redaction Level: {result.level.value.upper()}")
    print(f"PII Categories: {result.pii_categories}")
    print(f"Violations Found: {len(result.violations)}")

    if result.violations:
        print("\n🚨 KRITISCHE VERSTÖSSE:")
        for v in result.violations:
            print(f"  - [KRITISCH: {v}]")

    print("\n📝 REDACTED TEXT (REGELKONFORM):\n")
    print(result.redacted_text)

    print("\n" + "="*80)
    print("VERGLEICH: ALT vs NEU")
    print("="*80)

    comparison = """
FEHLER (ALT - aktuelle Engine):
❌ [Name_5][Adresse_2]  ← Zähler kleben zusammen
❌ [[E-Mail]](mailto:[E-Mail])  ← Markdown-Link bleibt
❌ [Gesundheitsdaten][Gesundheitsdaten_2][Gesundheitsdaten_3]  ← Nur Platzhalter für violette Daten
❌ Zuverlässigkeit: 62 von 100 Punkten  ← Numerische Werte bleiben sichtbar
❌ Die Entscheidung wurde vollständig automatisch erstellt.  ← Schwarz nicht geschwärzt
❌ Die Daten werden unbegrenzt gespeichert.  ← Kritische Verstöße nicht markiert

REGELKONFORM (NEU - Redaction v2):
✅ [Name] [Adresse]  ← Konsistente, saubere Platzhalter
✅ [E-Mail]  ← Keine Markdown-Formatierung
✅ Gesundheit: [GESCHWAERZT: besonders sensible Daten]  ← Ganze Sektion schwärzen
✅ Zuverlässigkeit: [GESCHWAERZT: verbotene oder sehr riskante automatisierte Entscheidung]
✅ Die Entscheidung wurde [GESCHWAERZT: verbotene oder sehr riskante automatisierte Entscheidung]
✅ Die Daten werden [KRITISCH: Speicherbegrenzung/Löschkonzept fehlt]
"""

    print(comparison)

    # Assertions für Regelkonformität
    assert result.level == RedactionLevel.BLACK, "Amun sollte BLACK sein (automatisierte Entscheidung)"
    assert "Speicherbegrenzung" in str(result.violations), "Speicher-Verstoß sollte erkannt werden"
    assert "[GESCHWAERZT:" in result.redacted_text, "Schwärzzung sollte vorhanden sein"
    assert "[Name_" not in result.redacted_text, "Alte Zähler sollten nicht mehr vorkommen"
    assert "mailto:" not in result.redacted_text, "Markdown-Links sollten bereinigt sein"

    print("\n✅ ALLE REGELKONFORMITÄTS-CHECKS BESTANDEN")
    return result


if __name__ == "__main__":
    result = test_amun_brief_with_redaction_v2()
    print(f"\n🎯 Final Level: {result.level.value}")
