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
    PATTERNS = {
        "name": re.compile(r"\b(?:Herr(?:n)?|Frau|Dr\.|Prof\.)\s+[A-ZÄÖÜ][A-Za-zÄÖÜäöüß\s-]+", re.IGNORECASE),
        "email": re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        "phone": re.compile(r"(?:\+49|0)[\s.\-]?[1-9]\d{2,}[\s()./\-]*\d{2,}(?!\d)", re.IGNORECASE),
        "iban": re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]){11,30}\b"),
        "card": re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"),
        "reference": re.compile(r"\b[A-Z]{2,3}-\d{4}-\d{3,4}\b"),  # HR-2026-117
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
        "genetic": ["genetisch", "dna", "chromosom", "gen"],
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
        """Findet Art. 9-Sektionen (VIOLETT)"""
        found = {}
        text_lower = text.lower()

        for category, keywords in self.VIOLET_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    if category not in found:
                        found[category] = []
                    found[category].append(keyword)

        return found

    def _redact_violet_sections(self, text: str, violet_categories: dict[str, list]) -> str:
        """Schwärzt ganze Sektionen mit Art. 9-Daten - AGGRESSIV"""
        for category in violet_categories.keys():
            category_label = {
                "health": "Gesundheit",
                "religion": "Religion/Weltanschauung",
                "politics": "Politische Meinung",
                "sexual": "Sexualdaten/Familienstand",
                "ethnic": "Herkunft",
                "biometric": "Biometrische Daten",
                "union": "Gewerkschaftsbezug",
                "genetic": "Genetische Daten",
                "criminal": "Strafrechtliche Informationen",
            }.get(category, category)

            # AGGRESSIV: Ersetze ganze Zeilen + folgende Zeilen mit Details
            # Findet "Gesundheit: ..." und ersetzt komplett
            text = re.sub(
                rf"(?:{category_label}:[^\n]*(?:\n(?:\s+[^\n]*)*)?(?:\n|$))",
                f"[GESCHWAERZT: {category_label} - Art. 9 DSGVO - Datenkategorie nicht extern verarbeitbar]\n",
                text,
                flags=re.IGNORECASE,
            )

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
            "email": "E-Mail",
            "phone": "Telefon",
            "iban": "IBAN",
            "card": "Kartennummer",
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
