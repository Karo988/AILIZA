"""
Golden-Test: Incident-Testbrief "Paula Ronder" (Amun-Brief)
================================================================================
Hotfix nach Live-Incident (2026-07): Ein vollstaendiger, realistischer Brief
mit Art.-9-Daten, automatisierter Entscheidung und diversen PII-Typen ging auf
der Live-Instanz komplett unredaktiert an die KI. Wurzelursachen (mehrere,
unabhaengige Regex-Bugs in governance/redaction_v2.py):

1. `\\s` in Zeichenklassen/Wiederholungen matcht auch `\\n` — mehrzeilige
   Muster (Violett-Sektionen, Namensfelder, Postleitzahl+Ort) konnten dadurch
   ueber Absatzgrenzen hinweg "fressen" und dabei benachbarte, bereits
   redaktierte Abschnitte (inkl. der SCHWARZ-Redaction der automatisierten
   Entscheidung) mit zerstoeren.
2. `re.IGNORECASE` auf ganze Patterns angewendet, die intern eine
   Grossschreibungs-Anforderung als Abgrenzungskriterium nutzen (z.B.
   "Nummer MUSS mit Grossbuchstabe beginnen"), hob dieses Kriterium auf und
   fuehrte zu Ueberdehnung (z.B. "Bestellungen" faelschlich als
   Referenznummer erkannt).
3. Violett-Kategorien wurden ueber einen hart codierten Anzeige-Namen
   ("Religion/Weltanschauung:") gegen die Zeile gematcht statt gegen die
   tatsaechlich erkannten Schluesselwoerter — bei abweichendem Feldnamen im
   Dokument (z.B. nur "Religion:") blieb die Zeile komplett unredaktiert.
4. Das Schluesselwort "gen" (Kategorie "genetic") war als Teilstring viel zu
   kurz und matchte in normalen Woertern wie "Bestellun-gen", "fol-gen-de".
5. Fehlende Muster: Geburtsdatum, Strassenadresse, PLZ+Ort, "Name:"-Feldlabel,
   alleinstehende Namenszeile im Adressblock waren serverseitig ueberhaupt
   nicht abgedeckt.

Akzeptanz (Betreiber-Vorgabe): Im safe_text darf KEINER der zehn
Klartext-Strings mehr vorkommen. Alle acht Art.-9-Kategorien muessen als
kritische Redaction (violet/black) erkannt werden.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from apps.backend.main import policy_redact, PolicyRedactRequest

AMUN_BRIEF = """Amun – Best of Orient GmbH
Musterstraße 18
18119 Rostock-Warnemünde

An:
Paula Ronder
Hafenstraße 44
18057 Rostock

Rostock, 01.07.2026

Betreff: Automatisierte Bewertung Ihrer Bewerbung und Kundenakte durch unser KI-System

Sehr geehrte Frau Ronder,

wir haben Ihre Bewerbung, Ihre Kundendaten, Ihre früheren Bestellungen, Ihre E-Mail-Kommunikation, Ihre Telefonnummer, Ihre Adresse, Ihre IBAN, Ihre Kreditkartendaten, Ihre Social-Media-Profile sowie öffentlich auffindbare Informationen über Sie automatisch durch unser KI-System "AILIZA Score 4.0" prüfen lassen.

Das System hat folgende Daten über Sie verarbeitet:

Name: Paula Ronder
Geburtsdatum: 14.03.1988
Adresse: Hafenstraße 44, 18057 Rostock
E-Mail: paula.ronder@example.de
Telefon: 0176 45678912
IBAN: DE89 3704 0044 0532 0130 00
Kreditkarte: 4111 1111 1111 1111, gültig bis 12/29
Kundennummer: AMUN-44821
Bewerbungsnummer: HR-2026-117

Zusätzlich wurden durch die KI folgende sensible Informationen erkannt und bewertet:

Gesundheit: wiederkehrende Migräne, frühere Krankschreibungen, mögliche Stressbelastung
Religion: muslimisch
Herkunft: türkisch-deutsch
Politische Meinung: kritisch gegenüber Überwachung und KI-Systemen
Familienstand: alleinerziehend
Sexuelle Orientierung: unbekannt, aber durch KI als "prüfungsrelevant" markiert
Biometrische Daten: Gesichtsanalyse aus Ihrem Bewerbungsfoto
Strafrechtliche Information: alter Verdacht aus einer Online-Suche, nicht geprüft
Gewerkschaftsbezug: mögliche Mitgliedschaft aufgrund öffentlicher Likes in sozialen Netzwerken

Unser KI-System hat daraus einen Risiko- und Vertrauensscore berechnet:

Zuverlässigkeit: 62 von 100 Punkten
Automatische Empfehlung: Bewerbung ablehnen
"""

FORBIDDEN_STRINGS = [
    "Paula Ronder",
    "Hafenstraße 44",
    "18057",
    "14.03.1988",
    "paula.ronder@",
    "0176 45678912",
    "DE89 3704 0044 0532 0130 00",
    "4111 1111 1111 1111",
    "AMUN-44821",
    "HR-2026-117",
]


def _run_policy_redact(text: str):
    request = PolicyRedactRequest(text=text, context=None, detected_categories=None)
    return policy_redact(request, current_user=None)


def test_golden_amun_brief_no_pii_leaks():
    response = _run_policy_redact(AMUN_BRIEF)
    for forbidden in FORBIDDEN_STRINGS:
        assert forbidden not in response.safe_text, (
            f"Golden-Test-Regression: {forbidden!r} ist weiterhin im safe_text enthalten."
        )


def test_golden_amun_brief_art9_categories_critical():
    response = _run_policy_redact(AMUN_BRIEF)
    # Alle acht Art.-9-Kategorien muessen als [GESCHWAERZT: ...] markiert sein.
    for label in [
        "Gesundheit", "Religion", "Herkunft", "Politische Meinung",
        "Sexualdaten", "Biometrische Daten", "Strafrechtliche Informationen",
        "Gewerkschaftsbezug",
    ]:
        assert f"[GESCHWAERZT: {label}" in response.safe_text, (
            f"Art.-9-Kategorie {label!r} wurde nicht als kritische Violation redaktiert."
        )
    # Risk-Level muss die hoechste erkannte Kategorie widerspiegeln (SCHWARZ
    # wegen automatisierter Entscheidung uebersteuert Violett in der Prioritaet).
    assert response.risk_level in ("black", "violet")
    assert response.can_send_to_llm is False


def test_golden_amun_brief_automated_decision_preserved():
    """Die SCHWARZ-Redaction der automatisierten Entscheidung darf nicht durch
    nachfolgende Violett-Redaction ueberschrieben/geloescht werden."""
    response = _run_policy_redact(AMUN_BRIEF)
    assert "[GESCHWAERZT: verbotene" in response.safe_text
    assert "Automatische Empfehlung: Bewerbung ablehnen" not in response.safe_text
