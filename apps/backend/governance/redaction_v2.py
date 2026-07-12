"""
AILIZA Redaction v2 – Regelkonform mit 4-Tier Klassifikation

Implementiert die AILIZA-Permanent-Rule:
- GRÜN: Keine Redaction
- GELB: [Platzhalter] für normale PII
- ORANGE: [Platzhalter] für normale PII + ORANGE-Flag für Approval-Gate
- ROT: Blockade + [Platzhalter] für kritische Daten + [KRITISCH: ...] für Verstöße
- VIOLETT: [GESCHWAERZT: besonders sensible Daten] für Art. 9-Kategorien
- SCHWARZ: [GESCHWAERZT: verbotene/sehr riskante automatisierte Entscheidung]

Status: REGELKONFORM mit GDD-Richtlinie + DSGVO
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RedactionLevel(Enum):
    """Redaction-Stufen nach neuer AILIZA-Regel"""
    GREEN = "green"        # Keine Redaction
    YELLOW = "yellow"      # [Platzhalter]
    ORANGE = "orange"      # [Platzhalter] + approval_required
    RED = "red"            # Blockade, aber [Platzhalter] wenn minimal
    VIOLET = "violet"      # [GESCHWAERZT: besonders sensible Daten]
    BLACK = "black"        # [GESCHWAERZT: verbotene/sehr riskante automatisierte Entscheidung]
    CRITICAL = "critical"  # [KRITISCH: ...]


@dataclass
class RedactionResult:
    """Ergebnis der Redaction"""
    redacted_text: str
    level: RedactionLevel
    replacements: dict[str, str] = field(default_factory=dict)  # [Placeholder] → "type"
    reinsertion_map: dict[str, str] = field(default_factory=dict)  # [Placeholder] → original
    violations: list[str] = field(default_factory=list)  # CRITICAL violations
    pii_categories: set[str] = field(default_factory=set)
    secrets_blocked: int = 0
    pii_replaced: int = 0


class RedactionEngineV2:
    """Neue Redaction-Engine mit regelkonformer Ausgabe"""

    # Pattern für verschiedene PII-Typen (vereinfacht)
    # Reihenfolge ist wichtig: strukturierte/spezifische Muster (IBAN, Karte) VOR
    # loseren Mustern (Telefon), sonst kann Telefon mitten in eine IBAN matchen
    # und sie nur teilweise zerstoeren (Incident 2026-07, Amun-Brief).
    # WICHTIG: Ausschliesslich [ \t] oder woertliches Leerzeichen statt \s
    # verwenden, wenn "gleiche Zeile" gemeint ist. \s matcht auch \n — in
    # einer Zeichenklasse oder Wiederholung ohne Obergrenze kann das ueber
    # Zeilen-/Absatzgrenzen hinweg "fressen" und dabei benachbarte, bereits
    # geschwaerzte Abschnitte oder Folgezeilen mit zerstoeren/verschlucken
    # (Incident 2026-07, Amun-Brief: sowohl bei Telefon/IBAN-Kollision als
    # auch bei Violett-Sektionen und Namensfeldern beobachtet).
    PATTERNS = {
        "name": re.compile(
            # (?i:...) nur um die Anrede — der Name selbst MUSS grossgeschrieben
            # sein (case-sensitiv), sonst frisst IGNORECASE beliebigen
            # kleingeschriebenen Folgetext als vermeintlich "weiteres Namenswort"
            # (gleiche Fehlerklasse wie bei "reference", Incident 2026-07).
            r"\b(?i:Herr(?:n)?|Frau|Dr\.|Prof\.)[ \t]+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+"
            r"(?:[ \t]+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)*",
        ),
        "name_field": re.compile(
            r"(?i:Name|Ansprechpartner|Antragsteller|Bewerber(?:in)?|Kunde|Kundin)[ \t]*:[ \t]*"
            r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+(?:[ \t]+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)*",
        ),
        "name_standalone_line": re.compile(
            r"^[A-ZÄÖÜ][a-zäöüß\-]+[ \t]+[A-ZÄÖÜ][a-zäöüß\-]+$", re.MULTILINE,
        ),
        # "mein Name ist Paula Ronder" — haeufigste Selbstauskunfts-Formulierung
        # in Briefen/E-Mails, wurde bisher von keinem Muster erfasst (nur
        # "Name:" mit Doppelpunkt und Titel-Anreden wie "Frau X").
        "name_self_intro": re.compile(
            r"(?i:mein(?:e)?|unser(?:e)?)[ \t]+Name[ \t]+ist[ \t]+"
            r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+(?:[ \t]+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)*",
        ),
        # Name in der Grussformel-Signatur ("Mit freundlichen Gruessen, X Y").
        # Gr(üe|ü|ue)ß(en)? deckt auch ASCII-Ersatzschreibung ohne Umlaut-
        # Tastatur ab ("Gruessen" statt "Grüßen").
        "name_signature": re.compile(
            r"(?i:Mit[ \t]+freundlichen[ \t]+Gr(?:ü|ue)(?:ß|ss)en"
            r"|Mit[ \t]+besten[ \t]+Gr(?:ü|ue)(?:ß|ss)en"
            r"|Viele[ \t]+Gr(?:ü|ue)(?:ß|ss)e\b"
            r"|Beste[ \t]+Gr(?:ü|ue)(?:ß|ss)e\b)[,]?[ \t]*"
            r"[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+(?:[ \t]+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)*",
        ),
        "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        # "geboren am X" ist die haeufigste Alltagsformulierung in Briefen/
        # E-Mails und wurde bisher NICHT erkannt (nur "Geburtsdatum:"/"geb.").
        "birthdate": re.compile(
            r"\b(?:Geburtsdatum|geb\.|geboren[ \t]+am)[ \t]*:?[ \t]*\d{1,2}\.\d{1,2}\.\d{2,4}",
            re.IGNORECASE,
        ),
        "iban": re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b"),
        "bic": re.compile(r"\bBIC[ \t]*:?[ \t]*[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b", re.IGNORECASE),
        "card": re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"),
        # Amtliche Ausweis-/ID-Nummern (Karo-Fund 2026-07-11, erweiterter
        # Amun-Testbrief): Personalausweis, Reisepass, Steuer-ID, Sozial-
        # versicherung, Fuehrerschein, Krankenversicherung. Label-basiert,
        # da die Nummernformate je Dokumenttyp variieren.
        "official_id": re.compile(
            r"(?i:Personalausweisnummer|Reisepassnummer|Steueridentifikationsnummer"
            r"|Steuer-?ID|Sozialversicherungsnummer|Führerscheinnummer"
            r"|Krankenversicherungsnummer)[ \t]*:?[ \t]*[\w \-]{4,25}",
        ),
        # Zugangsdaten/Geheimnisse (DSGVO/CLAUDE.md-Kategorie "secret" ⚫ —
        # nie ausgeben). Label-basiert: die Werte selbst haben kein
        # einheitliches Format (Woerter, Zahlen, Base32-Schluessel, ...).
        #
        # Karo-Fund 2026-07-12: "Antwort" ist ein sehr allgemeines deutsches
        # Wort (= "Reply") und matchte mit optionalem Doppelpunkt (":?")
        # beliebigen Fliesstext ("Antwort-Mail an ...") — dabei wurden
        # bereits redigierte Platzhalter ([E-Mail], [Name]) erneut mit
        # eingeschlossen und so eine verschachtelte Platzhalter-Situation
        # erzeugt. Betreiber-Entscheidung (Option 1): "Antwort" bleibt im
        # Muster (schuetzt weiterhin z.B. "Antwort: Lucky" bei Sicherheits-
        # fragen), aber der Doppelpunkt ist jetzt fuer ALLE Schluesselwoerter
        # PFLICHT (":" statt ":?") -- "Antwort-Mail" (kein Doppelpunkt)
        # matcht dadurch nicht mehr, "Antwort: Lucky" weiterhin.
        "credential": re.compile(
            r"(?i:Benutzername|Passwort|WLAN-Passwort|PIN|Sicherheitsfrage|Antwort"
            r"|Wiederherstellungscode|Zwei-Faktor-Authentifizierungsschlüssel)"
            r"[ \t]*:[ \t]*[^\n]{1,60}",
        ),
        # Technische Kennungen mit Standort-/Identifizierungsbezug.
        "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "gps_coords": re.compile(r"\b-?\d{1,3}\.\d{3,6},[ \t]*-?\d{1,3}\.\d{3,6}\b"),
        "device_id": re.compile(
            r"(?i:Gerätekennung|Geräte-ID|Device-ID|Browser-Fingerprint)[ \t]*:?[ \t]*[\w\-]{4,30}",
        ),
        # Finanzielle Detailangaben — label-basiert, Wert bis Zeilenende.
        "financial_detail": re.compile(
            r"(?i:Monatliches Nettoeinkommen|Monatliche Mietkosten|Laufender Ratenkredit"
            r"|Dispositionskredit|Aktueller Kontostand|Bonitätsscore"
            r"|SCHUFA-ähnliche Risikoeinstufung)[ \t]*:?[ \t]*[^\n]{1,60}",
        ),
        # SCHUFA/Bonität auch als freistehende Erwaehnung erkennen (nicht nur
        # in der exakten Label-Zeile oben) — Karo-Fund 2026-07-11.
        "financial_keyword": re.compile(r"\b(?:schufa|bonität(?:sscore)?)[\wäöüÄÖÜß\-]*", re.IGNORECASE),
        # Kartenpruefnummer/Gueltigkeitsdatum (getrennt von der Kartennummer
        # selbst, damit CVV nicht zufaellig als 3-4-stellige "Kartennummer"
        # durchrutscht oder umgekehrt zerstoert wird).
        "card_cvv": re.compile(r"(?i:Kartenprüfnummer|CVV|CVC)[ \t]*:?[ \t]*\d{3,4}"),
        "card_expiry": re.compile(r"(?i:Gültig bis)[ \t]*:?[ \t]*\d{1,2}[ \t]*/[ \t]*\d{2,4}"),
        # Kinderdaten (DSGVO Art. 8 — eigene, striktere Rechtsgrundlage fuer
        # Daten Minderjaehriger, unabhaengig von der sonstigen Kategorie).
        "child_field": re.compile(
            r"(?i:Schule des Kindes|Schulweg|Kindergarten|Name des Kindes"
            r"|Geburtsdatum des Kindes)[ \t]*:?[ \t]*[^\n]{1,60}",
        ),
        "address": re.compile(
            # Kein IGNORECASE: Strassenname ist im Deutschen konventionell
            # grossgeschrieben — case-sensitiv verhindert Ueberdehnung auf
            # zufaellige kleingeschriebene Wortteile wie "unterwegs" (enthaelt
            # "weg" als Teilstring). Nicht-gieriges *? vor dem Suffix, damit
            # die Suffix-Gruppe zuverlaessig genau an der richtigen Stelle
            # matcht statt sich auf Backtracking zu verlassen.
            r"\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]*?(?:stra(?:ße|sse)|gasse|weg|platz|allee|ring|damm|ufer)"
            r"[ \t]+\d+[a-z]?(?:/\d+[a-z]?)?",
        ),
        "postal_city": re.compile(
            r"\b\d{5}[ \t]+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+(?:[ \t]+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+){0,3}",
        ),
        "reference": re.compile(
            # (?i:...) beschraenkt Gross-/Kleinschreibungs-Toleranz auf die
            # Schluesselwoerter — die Nummer selbst MUSS mit Grossbuchstabe/
            # Ziffer beginnen (case-sensitiv), sonst matcht z.B. "Bestellung"
            # + IGNORECASE das "en" in "Bestellungen" als vermeintliche
            # Nummer (Incident 2026-07, Amun-Brief).
            r"(?i:Rechnung(?:s(?:nummer)?)?|Rechnungs-?Nr\.?|Kundennummer|Kunden-?Nr\.?"
            r"|Auftrag(?:s(?:nummer)?)?|Auftrags-?Nr\.?|Bestellung(?:s(?:nummer)?)?|Bestell-?Nr\.?"
            r"|Aktenzeichen|Az\.?|Vertrag(?:s(?:nummer)?)?|Vertrags-?Nr\.?|Fall(?:nummer)?|Fall-?Nr\.?"
            r"|Ticket-?(?:Nr\.?|Nummer)?|Bewerbung(?:s(?:nummer)?)?|Bewerbungs-?Nr\.?)"
            r"[ \t]*[:\-#]?[ \t]*[A-Z0-9][\w\-/]{1,19}"
            r"|\b[A-Z]{2,3}-\d{4}-\d{3,4}\b",  # HR-2026-117 (auch ohne Label)
        ),
        "phone": re.compile(r"(?:\+49|0)[ \t.\-]?[1-9]\d{2,}[ \t()./\-]*\d{2,}(?!\d)", re.IGNORECASE),
        "secret_openai": re.compile(r"\bsk-[\w\-]{15,}\b"),
        "secret_groq": re.compile(r"\bgsk_[\w\-]{15,}\b"),
        "secret_jwt": re.compile(r"\beyJ[\w\-\.]+\b"),
        "secret_bearer": re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b"),
    }

    # Art. 9-Kategorien (VIOLETT)
    VIOLET_KEYWORDS = {
        "health": [
            "diagnose", "migräne", "kopfschmerz", "krankheit", "gesundheit",
            "krankschreibung", "hiv", "aids", "infektion", "erkrankung",
            "behinderung", "depression", "krebs", "diabetes",
            # Karo-Fund 2026-07-11, erweiterter Amun-Testbrief:
            "depressiv", "angststörung", "burnout", "burn-out", "allergie",
            "schwanger", "fehlgeburt", "therapeutisch", "psychotherap",
            "medikament", "blutdruck", "body-mass-index", "bmi",
            "krankenversicherungsnummer",
        ],
        "religion": ["religion", "muslimisch", "christlich", "buddhistische", "jüdisch", "atheist", "katholisch", "evangelisch"],
        "politics": ["politische", "wahlbezirk", "spd", "cdu", "grüne", "linke", "afd", "fdp"],
        "sexual": ["homosexuell", "lesbisch", "schwul", "bisexuell", "queer", "sexuelle"],
        "ethnic": ["herkunft", "ethni", "rasse", "abstammung", "nationalität"],
        "biometric": ["fingerabdruck", "gesichtserkennung", "biometrisch", "gesichtsanalyse"],
        # "gewerkschaft" statt "gewerkschafts": das Grundwort ("Mitglied der
        # Gewerkschaft ver.di") ist haeufiger als die zusammengesetzte Form
        # und wurde vorher NICHT erkannt (\bgewerkschafts matcht "Gewerkschaft"
        # nicht, da das "s" fehlt).
        "union": ["gewerkschaft", "tarifvertrag", "betriebsrat"],
        "genetic": ["genetisch", "dna", "chromosom", "genom"],
        "criminal": ["strafrechtlich", "verurteilung", "strafregister"],
    }

    # Schwarz-Indikatoren (automatisierte Entscheidungen)
    BLACK_KEYWORDS = {
        "triggers": ["automatisierte entscheidung", "automatische empfehlung", "automatisch", "vollständig automatisch", "keine manuelle prüfung"],
        "impacts": ["ablehnen", "kündigen", "nicht einstellen", "vorkasse", "score", "risiko", "bonität"],
    }

    # KRITISCH-Marker (DSGVO-Verstöße)
    CRITICAL_MARKERS = {
        "storage": ["unbegrenzt gespeichert", "speicherung ohne frist", "löschung nicht vorgesehen"],
        "consent": ["ohne einwilligung", "ohne zustimmung", "ohne consent"],
        "dpa": ["kein dpa", "kein avv", "auftragsverarbeitungsvertrag", "provider nicht geprüft"],
        "transparency": ["ohne hinweis", "keine benachrichtigung", "transparenz nicht gewährleistet"],
    }

    def __init__(self):
        self.seen_placeholders: dict[str, str] = {}  # Cache für konsistente Platzhalter
        self.reinsertion_map: dict[str, str] = {}
        self.replacements: dict[str, str] = {}
        self.violations: list[str] = []

    def redact(self, text: str, detected_categories: Optional[set[str]] = None) -> RedactionResult:
        """
        Hauptmethode: Redact nach 4-Tier-Regel

        Priorität:
        1. BLACK: [GESCHWAERZT: automatisierte Entscheidung]
        2. VIOLET: [GESCHWAERZT: besonders sensible Daten]
        3. Secrets: entfernen (nicht redact)
        4. Normale PII: [Placeholder]
        5. CRITICAL: [KRITISCH: ...]
        """
        self.seen_placeholders = {}
        self.reinsertion_map = {}
        self.replacements = {}
        self.violations = []

        result_text = text
        result_level = RedactionLevel.GREEN
        pii_categories = set()

        # 1. Prüfe auf SCHWARZ (automatisierte Entscheidungen)
        if self._has_black_indicators(text):
            result_text = self._redact_black(result_text)
            result_level = RedactionLevel.BLACK

        # 2. Prüfe auf VIOLETT (Art. 9-Kategorien)
        violet_found = self._find_violet_sections(result_text)
        if violet_found:
            result_text = self._redact_violet_sections(result_text, violet_found)
            result_level = RedactionLevel.VIOLET if result_level == RedactionLevel.GREEN else result_level
            pii_categories.update(violet_found.keys())

        # 3. Entferne Secrets (komplett)
        result_text = self._remove_secrets(result_text)

        # 4. Redact normale PII
        result_text, pii_count = self._redact_normal_pii(result_text)
        if pii_count > 0:
            if result_level == RedactionLevel.GREEN:
                result_level = RedactionLevel.YELLOW

        # 5. Prüfe auf KRITISCH (DSGVO-Verstöße)
        critical_found = self._find_critical_violations(text)
        if critical_found:
            self.violations.extend(critical_found)
            if result_level == RedactionLevel.GREEN:
                result_level = RedactionLevel.CRITICAL

        return RedactionResult(
            redacted_text=result_text,
            level=result_level,
            replacements=self.replacements,
            reinsertion_map=self.reinsertion_map,
            violations=self.violations,
            pii_categories=pii_categories,
        )

    def _has_black_indicators(self, text: str) -> bool:
        """Prüft auf automatisierte Entscheidungen (SCHWARZ)"""
        text_lower = text.lower()

        # Muss BEIDE haben: Trigger UND Impact
        has_trigger = any(kw in text_lower for kw in self.BLACK_KEYWORDS["triggers"])
        has_impact = any(kw in text_lower for kw in self.BLACK_KEYWORDS["impacts"])

        return has_trigger and has_impact

    def _redact_black(self, text: str) -> str:
        """Geschwärzt: automatisierte Entscheidung"""
        # Ersetze ganze Sätze/Absätze mit automatisierten Entscheidungen
        text = re.sub(
            r"(?:Automatische Empfehlung|Automatisierte Entscheidung|Bewertung):[^\n]*(?:\n|$)",
            "[GESCHWAERZT: verbotene oder sehr riskante automatisierte Entscheidung]\n",
            text,
            flags=re.IGNORECASE,
        )
        return text

    def _find_violet_sections(self, text: str) -> dict[str, list[str]]:
        """
        Findet Art. 9-Sektionen (VIOLETT).

        Nutzt Wortgrenzen (\\b) statt naiver Teilstring-Suche — sonst matchen
        kurze/generische Schluesselwoerter (z.B. ehemals "gen") versehentlich
        innerhalb unverwandter Woerter (z.B. "Bestellun-gen", "fol-gen-de").
        """
        found = {}

        for category, keywords in self.VIOLET_KEYWORDS.items():
            for keyword in keywords:
                if re.search(rf"\b{re.escape(keyword)}", text, re.IGNORECASE):
                    if category not in found:
                        found[category] = []
                    found[category].append(keyword)

        return found

    _VIOLET_CATEGORY_LABELS = {
        "health": "Gesundheit",
        "religion": "Religion/Weltanschauung",
        "politics": "Politische Meinung",
        "sexual": "Sexualdaten/Familienstand",
        "ethnic": "Herkunft",
        "biometric": "Biometrische Daten",
        "union": "Gewerkschaftsbezug",
        "genetic": "Genetische Daten",
        "criminal": "Strafrechtliche Informationen",
    }

    # Rechtsgrundlage je Kategorie: Art. 9 DSGVO (besondere Kategorien) vs.
    # Art. 10 DSGVO (strafrechtliche Verurteilungen/Straftaten — eigene,
    # striktere Rechtsgrundlage, KEINE Art.-9-Kategorie). Fehlklassifizierung
    # als Art. 9 wurde in einer externen Compliance-Pruefung bemaengelt.
    _VIOLET_CATEGORY_ARTICLE = {
        "criminal": "Art. 10 DSGVO",
    }
    _DEFAULT_VIOLET_ARTICLE = "Art. 9 DSGVO"

    def _redact_violet_sections(self, text: str, violet_categories: dict[str, list]) -> str:
        """
        Schwärzt NUR die konkreten Art.-9-Begriffe/Wörter selbst — nicht die
        ganze Zeile oder den ganzen Brief.

        Betreiber-Freigabe 2026-07-11: Eine fruehere Version ersetzte die
        komplette Zeile, die ein Schluesselwort enthielt (Incident: bei
        einem einzigen durchgehenden Absatz ohne Zeilenumbrueche war "die
        Zeile" der GESAMTE Brief — der Rest der Anfrage, z.B. das eigentliche
        Anliegen, ging mit verloren und konnte nicht mehr zusammengefasst
        werden). Jetzt: nur die tatsaechlich erkannten Woerter werden durch
        einen kompakten Inline-Platzhalter ersetzt, der Rest des Textes
        bleibt unveraendert erhalten und ist weiter verarbeitbar.
        """
        for category, matched_keywords in violet_categories.items():
            category_label = self._VIOLET_CATEGORY_LABELS.get(category, category)
            article = self._VIOLET_CATEGORY_ARTICLE.get(category, self._DEFAULT_VIOLET_ARTICLE)
            # Karo-Fund 2026-07-11 (erweiterter Amun-Testbrief): "Diagnose:
            # depressive Episode" schwaerzte bisher nur das Wort "Diagnose"
            # — die eigentliche Diagnose dahinter blieb im Klartext. Wenn dem
            # Schluesselwort direkt ": <Wert>" folgt (Label-Zeile), wird der
            # Wert bis Zeilenende MIT geschwaerzt, nicht nur das Label-Wort.
            kw_pattern = re.compile(
                r"\b(?:" + "|".join(re.escape(kw) for kw in set(matched_keywords)) + r")"
                r"[\wäöüÄÖÜß-]*(?:[ \t]*:[ \t]*[^\n]{1,80})?",
                re.IGNORECASE,
            )
            placeholder = f"[GESCHWAERZT: {category_label} - {article}]"
            text = kw_pattern.sub(placeholder, text)

        return text

    def _remove_secrets(self, text: str) -> str:
        """Entfernt Secrets komplett (keine Redaction)"""
        for secret_type, pattern in self.PATTERNS.items():
            if "secret" in secret_type:
                text = pattern.sub("", text)
        return text

    def _redact_normal_pii(self, text: str) -> tuple[str, int]:
        """Redact normale PII mit normalisierten Platzhaltern - gibt (modifizierter_text, count) zurück"""
        count = 0

        for pii_type, pattern in self.PATTERNS.items():
            if "secret" in pii_type:
                continue  # Skip secrets

            def replacer(match):
                nonlocal count
                original = match.group()

                # Konsistenter Platzhalter (Cache)
                if original in self.seen_placeholders:
                    return self.seen_placeholders[original]

                # Normalisierter Platzhalter (KEINE Zähler!)
                type_label = self._normalize_label(pii_type)
                placeholder = f"[{type_label}]"

                # Falls Platzhalter schon existiert (z.B. mehrere E-Mails), Cache verwenden
                if placeholder in self.replacements:
                    # Platzhalter schon in Verwendung, trotzdem verwenden aber unterscheiden
                    pass

                self.seen_placeholders[original] = placeholder
                self.replacements[placeholder] = pii_type
                self.reinsertion_map[placeholder] = original
                count += 1

                return placeholder

            text = pattern.sub(replacer, text)

        return text, count

    def _normalize_label(self, pii_type: str) -> str:
        """Normalisiert PII-Typ zu Platzhalter-Label (ohne Zähler)"""
        labels = {
            "name": "Name",
            "name_field": "Name",
            "name_standalone_line": "Name",
            "name_self_intro": "Name",
            "name_signature": "Name",
            "email": "E-Mail",
            "birthdate": "Geburtsdatum",
            "phone": "Telefon",
            "iban": "IBAN",
            "bic": "BIC",
            "card": "Kartennummer",
            "address": "Adresse",
            "postal_city": "Ort",
            "reference": "Referenznummer",
            "official_id": "Ausweisnummer",
            "credential": "Zugangsdaten",
            "ip_address": "IP-Adresse",
            "gps_coords": "Standort",
            "device_id": "Gerätekennung",
            "financial_detail": "Finanzangabe",
            "financial_keyword": "Finanzangabe",
            "card_cvv": "Kartenprüfnummer",
            "card_expiry": "Kartengültigkeit",
            "child_field": "Kinderdaten (Art. 8 DSGVO)",
        }
        return labels.get(pii_type, pii_type.title())

    def _find_critical_violations(self, text: str) -> list[str]:
        """Findet DSGVO-Verstöße (KRITISCH)"""
        violations = []
        text_lower = text.lower()

        for violation_type, markers in self.CRITICAL_MARKERS.items():
            for marker in markers:
                if marker in text_lower:
                    label = {
                        "storage": "Speicherbegrenzung/Löschkonzept fehlt",
                        "consent": "Einwilligung/Rechtsgrundlage unklar",
                        "dpa": "Externe KI-/Dienstleisterübermittlung - Providerprüfung erforderlich",
                        "transparency": "Transparenz und Betroffenenrechte unklar",
                    }.get(violation_type, violation_type)

                    violations.append(label)
                    break

        return violations


def apply_redaction_v2(text: str, detected_categories: Optional[set[str]] = None) -> RedactionResult:
    """Convenience function"""
    engine = RedactionEngineV2()
    return engine.redact(text, detected_categories)
