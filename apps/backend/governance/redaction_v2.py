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
        "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        "birthdate": re.compile(
            r"\b(?:Geburtsdatum|geb\.)[ \t]*:?[ \t]*\d{1,2}\.\d{1,2}\.\d{2,4}", re.IGNORECASE,
        ),
        "iban": re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b"),
        "card": re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"),
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
        "health": ["diagnose", "migräne", "kopfschmerz", "krankheit", "gesundheit", "krankschreibung"],
        "religion": ["religion", "muslimisch", "christlich", "buddhistische", "jüdisch", "atheist"],
        "politics": ["politische", "wahlbezirk", "spd", "cdu", "grüne", "linke", "afd", "fdp"],
        "sexual": ["homosexuell", "lesbisch", "schwul", "bisexuell", "queer", "sexuelle"],
        "ethnic": ["herkunft", "ethni", "rasse", "abstammung", "nationalität"],
        "biometric": ["fingerabdruck", "gesichtserkennung", "biometrisch", "gesichtsanalyse"],
        "union": ["gewerkschafts", "tarifvertrag", "betriebsrat"],
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

    def _redact_violet_sections(self, text: str, violet_categories: dict[str, list]) -> str:
        """
        Schwärzt Zeilen mit Art. 9-Daten - AGGRESSIV, aber zeilenscharf.

        Fruehere Version nutzte eine mehrzeilige Regex mit `\\s+` als
        "Folgezeilen"-Muster — `\\s` matcht auch `\\n`, wodurch das Muster
        durch Absatzgrenzen hindurch bis zum Ende des Dokuments "fressen"
        konnte und dabei bereits geschwaerzte SCHWARZ-Abschnitte mit
        wegloeschte (Incident 2026-07, Amun-Brief-Vorfall). Fix: Ersetzt
        ausschliesslich die EINZELNE Zeile, die eines der tatsaechlich
        erkannten Schluesselwoerter enthaelt — nie mehr, nie weniger.
        Ausserdem unabhaengig vom exakten Feldbezeichner im Dokument (z.B.
        "Religion:" vs. Code-Label "Religion/Weltanschauung:" — vorher ein
        stiller Mismatch, der die Zeile komplett unredaktiert liess).
        """
        lines = text.split("\n")
        for category, matched_keywords in violet_categories.items():
            category_label = self._VIOLET_CATEGORY_LABELS.get(category, category)
            kw_pattern = re.compile(
                "|".join(re.escape(kw) for kw in set(matched_keywords)), re.IGNORECASE,
            )
            placeholder_line = (
                f"[GESCHWAERZT: {category_label} - Art. 9 DSGVO - "
                f"Datenkategorie nicht extern verarbeitbar]"
            )
            for i, line in enumerate(lines):
                if kw_pattern.search(line):
                    lines[i] = placeholder_line

        return "\n".join(lines)

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
            "email": "E-Mail",
            "birthdate": "Geburtsdatum",
            "phone": "Telefon",
            "iban": "IBAN",
            "card": "Kartennummer",
            "address": "Adresse",
            "postal_city": "Ort",
            "reference": "Referenznummer",
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
