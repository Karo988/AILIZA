"""
Erweiterter Golden-Test (Karo-Fund 2026-07-11): Der Live-Test auf Staging mit
einem deutlich umfangreicheren Testbrief (Ausweisnummern, Zugangsdaten,
Finanzdetails, technische Kennungen, gelabelte Gesundheitsangaben) deckte
mehrere PII-Kategorien auf, die der urspruengliche Golden-Test
(test_golden_amun_brief.py, 10 Datenfelder) nicht prueft. Dieser Test
erweitert die Abdeckung entsprechend permanent.

BEKANNTE GRENZE (bewusst dokumentiert, kein Vollstaendigkeitsanspruch):
Diese Engine arbeitet regex-/label-basiert. Sie erkennt bekannte Label-
Muster ("Diagnose:", "PIN:", ...) und feste Formate (IBAN, IP-Adresse, ...)
zuverlaessig, aber KEINE frei formulierten Saetze ohne erkennbares Muster
(z.B. "Verdacht auf Angststoerung" ohne Label). Fuer echte Vollstaendigkeit
braucht es eine NER-Schicht (im Projekt-Backlog als Nach-Beta-Punkt
dokumentiert) — bis dahin traegt dieser Golden-Test die Kernabdeckung.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

from apps.backend.governance.redaction_v2 import RedactionEngineV2

BRIEF = """Amun – Best of Orient GmbH
Musterstraße 18
18119 Rostock

An:
Paula Ronder
Musterstraße 5
18055 Rostock

**Identitätsdaten**

* Vollständiger Name: Paula Ronder
* Geburtsdatum: 14.03.1988
* Personalausweisnummer: L01X00T47
* Reisepassnummer: C4F8X9210
* Steueridentifikationsnummer: 12 345 678 901
* Sozialversicherungsnummer: 14 150388 R 123
* Führerscheinnummer: ROD880214P001

**Kontakt- und Standortdaten**

* Wohnanschrift: Hafenstraße 44, 18057 Rostock
* E-Mail-Adresse: paula.ronder@example.com
* Private Telefonnummer: 0176 45678912
* Aktueller GPS-Standort: 54.0924, 12.0991
* IP-Adresse: 192.0.2.45
* Gerätekennung: DEVICE-PR-8821

**Bank-, Zahlungs- und Finanzdaten**

* IBAN: DE89 3704 0044 0532 0130 00
* BIC: COBADEFFXXX
* Kreditkartennummer: 4111 1111 1111 1111
* Monatliches Nettoeinkommen: 2.480,00 Euro
* Aktueller Kontostand: minus 1.340,00 Euro
* Bonitätsscore: 71 von 100

**Zugangsdaten und Sicherheitsinformationen**

* Benutzername: paularonder88
* Passwort: Sommer2026!
* PIN: 4821
* Sicherheitsfrage: Name des ersten Haustieres
* Antwort: Lucky
* Wiederherstellungscode: 8821-4412-9011
* Zwei-Faktor-Authentifizierungsschlüssel: JBSWY3DPEHPK3PXP
* WLAN-Passwort: Hafen44WLAN!

**Gesundheitsdaten**

* Diagnose: depressive Episode
* Krankenversicherungsnummer: A123456789
* Hausarzt: Dr. Müller

Mit freundlichen Grüßen, Paula Ronder"""

FORBIDDEN = [
    "Paula Ronder", "14.03.1988", "L01X00T47", "C4F8X9210",
    "12 345 678 901", "14 150388 R 123", "ROD880214P001",
    "Hafenstraße 44", "paula.ronder@example.com", "0176 45678912",
    "54.0924, 12.0991", "192.0.2.45", "DEVICE-PR-8821",
    "DE89 3704 0044 0532 0130 00", "COBADEFFXXX", "4111 1111 1111 1111",
    "2.480,00", "minus 1.340,00", "71 von 100",
    "paularonder88", "Sommer2026!", "4821", "Lucky", "8821-4412-9011",
    "JBSWY3DPEHPK3PXP", "Hafen44WLAN!", "depressive Episode",
    "A123456789", "Dr. Müller",
]


def test_expanded_amun_brief_no_pii_leaks():
    result = RedactionEngineV2().redact(BRIEF)
    for forbidden in FORBIDDEN:
        assert forbidden not in result.redacted_text, (
            f"Golden-Test-Regression: {forbidden!r} ist weiterhin im redigierten Text enthalten."
        )


def test_expanded_amun_brief_still_summarizable():
    """Betreiber-Anforderung 2026-07-11: gezielte Schwaerzung darf den Rest
    des Dokuments nicht mit weglöschen — der Brief muss noch bearbeitbar sein."""
    result = RedactionEngineV2().redact(BRIEF)
    assert "Amun" in result.redacted_text
    assert "Identitätsdaten" in result.redacted_text
    assert "Bank-, Zahlungs- und Finanzdaten" in result.redacted_text
