"""
AILIZA Data Governance — Klassifikation
=======================================
Pattern-basierte Datenklassifikation. KEIN LLM beteiligt.

Fail-closed: Bei jeder Exception wird CREDENTIALS + needs_review=True
zurueckgegeben, damit im Zweifel nicht extern gesendet wird.

Klassifikationsstufen (RISK_ORDER, niedrig → hoch):
  PUBLIC < INTERNAL < CONFIDENTIAL < INTELLECTUAL_PROPERTY
  < PERSONAL_DATA < FINANCIAL < HR < LEGAL
  < SECURITY_SENSITIVE < SPECIAL_CATEGORY < CREDENTIALS

Sonderflags:
  requires_human_decision: True bei HR-Kontext oder Personenentscheidungen
                           (DSGVO Art. 22, EU AI Act)
  needs_review:            True bei CREDENTIALS, SPECIAL_CATEGORY
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class DataClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    PERSONAL_DATA = "personal_data"
    SPECIAL_CATEGORY = "special_category"
    CREDENTIALS = "credentials"
    FINANCIAL = "financial"
    HR = "hr"
    LEGAL = "legal"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    SECURITY_SENSITIVE = "security_sensitive"
    # SYNTHETIC/DEMO: NIEMALS von classify() aus Text vergeben — nur von
    # vertrauenswuerdigem Testcode explizit gesetzt (z.B. Fixture-Daten ohne
    # Personenbezug). Dient der AVV-Testmodus-Ausnahme in provider_profiles.py
    # (Freigabe Stufe 1, P-A).
    SYNTHETIC = "synthetic"
    DEMO = "demo"


class DataTarget(str, Enum):
    RAM = "ram"
    SESSION = "session"
    AUDIT = "audit"
    FILE_STORAGE = "file_storage"
    MEMORY = "memory"
    VECTOR_DB = "vector_db"
    EXTERNAL_LLM = "external_llm"
    CRM = "crm"
    EMAIL = "email"
    ADMIN_UI = "admin_ui"


# Reihenfolge von niedrig nach hoch. Strengste (hoechste) Klasse gewinnt.
RISK_ORDER: list[DataClass] = [
    DataClass.SYNTHETIC,
    DataClass.DEMO,
    DataClass.PUBLIC,
    DataClass.INTERNAL,
    DataClass.CONFIDENTIAL,
    DataClass.INTELLECTUAL_PROPERTY,
    DataClass.PERSONAL_DATA,
    DataClass.FINANCIAL,
    DataClass.HR,
    DataClass.LEGAL,
    DataClass.SECURITY_SENSITIVE,
    DataClass.SPECIAL_CATEGORY,
    DataClass.CREDENTIALS,
]


@dataclass
class ClassificationResult:
    data_classes: list[DataClass] = field(default_factory=list)
    highest_risk_class: DataClass = DataClass.PUBLIC
    confidence: float = 1.0
    matched_rules: list[str] = field(default_factory=list)
    needs_review: bool = False
    requires_human_decision: bool = False  # DSGVO Art. 22 / EU AI Act


# ── Secrets / Credentials ────────────────────────────────────────────────────
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("api_key_openai", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("api_key_groq", re.compile(r"\bgsk_[A-Za-z0-9]{16,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z._\-]{20,}\b")),
    ("github_token", re.compile(r"\bghp_[A-Za-z0-9]{16,}\b")),
    ("secret_assignment", re.compile(r"\b(password|passwd|token|api[_-]?key|secret)\s*[=:]\s*\S+", re.I)),
    # Deutsche Zugangsdaten-Schluesselwoerter im Fliesstext (Karo-Fund
    # 2026-07-11, erweiterter Amun-Testbrief): "Passwort: Sommer2026!" wurde
    # von der Klassifikation bisher nicht als secret erkannt, da nur
    # englische Code-Stil-Schluesselwoerter geprueft wurden.
    ("secret_assignment_de", re.compile(
        r"\b(Passwort|Kennwort|WLAN-Passwort|PIN|Sicherheitsfrage|Antwort"
        r"|Wiederherstellungscode|Zugangscode|Zwei-Faktor-Authentifizierungsschlüssel)"
        r"\s*[=:]\s*\S+", re.I,
    )),
]

# ── Kontakt / Identifikatoren (DSGVO Art. 4 Nr. 1) ──────────────────────────
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"(?:(?:\+49|0049)[\s\-/]?|\b0)(?:\d[\s\-/]?){6,14}\d")
_IBAN_PATTERN = re.compile(r"\bDE\d{20}\b")
_CARD_PATTERN = re.compile(r"\b(?:\d[ \-]?){13,16}\b")
_IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

_PERSONAL_ID_PATTERN = re.compile(
    r"\b(Vorname|Nachname|Geburtsdatum|Geburtsort|Personalausweis|Reisepass"
    r"|Sozialversicherungsnummer|Steuer-?ID|Kundennummer|Mitarbeiternummer"
    r"|Ticket-?(?:ID|Nummer)|Ausweis-?(?:ID|Nummer)"
    r"|first\s+name|last\s+name|date\s+of\s+birth|passport|national\s+id"
    r"|customer\s+(?:id|number)|employee\s+(?:id|number)|social\s+security"
    r"|ticket\s+(?:id|number)|attendee\s+id)\b",
    re.I,
)

# ── Biometrie + Zugangssteuerung (DSGVO Art. 9, immer SPECIAL_CATEGORY) ─────
_BIOMETRIC_PATTERN = re.compile(
    r"\b(Fingerabdruck|Gesichtserkennung|Gesichtsscan|Retina|Iris-?scan|DNA|Erbgut"
    r"|Kamera-?erkennung|VIP-?Erkennung|biometrisch|Einlass-?System|Zugangskontrolle\s+per\s+Kamera"
    r"|fingerprint|face\s+(?:recognition|scan|id)|retina|iris\s+scan|biometric"
    r"|facial\s+recognition|access\s+control\s+(?:camera|biometric)"
    r"|vip\s+(?:access|entry|recognition))\b",
    re.I,
)

# ── DSGVO Art. 9 — Besondere Kategorien ──────────────────────────────────────
_SPECIAL_CATEGORY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("biometric", _BIOMETRIC_PATTERN),
    ("health_diagnosis", re.compile(
        r"\b(Diagnose|Krankheit|Symptom|Behandlung|Medikament|Patient|Arzt|Therapie"
        r"|Krankenakte|Befund|HIV|AIDS|Krebs|Diabetes|Epilepsie|Depression|Schizophrenie"
        r"|Metformin|Insulin|Chemotherapie|psychisch|psychiatrisch|Behinderung|Sanitäts"
        r"|diagnosis|disease|symptom|treatment|medication|patient|physician|therapy"
        r"|medical\s+record|cancer|epilepsy|disability|prescription|hospitali[zs]ation"
        r"|first\s+aid|medical\s+emergency|health\s+data)\b", re.I,
    )),
    ("political", re.compile(
        r"\b(Parteimitgliedschaft|politische\s+(?:Meinung|Ansicht|Überzeugung)"
        r"|Gewerkschaft|Weltanschauung|party\s+membership|political\s+(?:opinion|view)"
        r"|trade\s+union|union\s+membership)\b", re.I,
    )),
    ("religious", re.compile(
        r"\b(Religion|Religionszugehörigkeit|Konfession|Glaube|Glaubensbekenntnis"
        r"|Kirchenmitglied|Muslim|Christ|Jude|Buddhist|Hindu|Atheist"
        r"|religious\s+(?:belief|affiliation)|denomination|faith|church\s+member)\b", re.I,
    )),
    ("ethnic_origin", re.compile(
        r"\b(ethnische\s+Herkunft|Rasse|Hautfarbe|Volkszugehörigkeit"
        r"|ethnic\s+origin|racial\s+origin|nationality\s+data)\b", re.I,
    )),
    ("sexual_orientation", re.compile(
        r"\b(sexuelle\s+Orientierung|Geschlechtsidentität|transgender|nicht-?binär"
        r"|sexual\s+orientation|gender\s+identity|non-?binary)\b", re.I,
    )),
    ("criminal", re.compile(
        r"\b(Vorstrafe|Strafakte|strafrechtliche\s+Verurteilung|Strafregister"
        r"|criminal\s+record|conviction|criminal\s+history)\b", re.I,
    )),
]

# ── Referenznummern (Kundennummer, Rechnungsnummer, Aktenzeichen — Identifier) ─
_REFERENCE_NUMBER_PATTERN = re.compile(
    r"(?:Rechnung(?:s(?:nummer)?)?|Rechnungs-?Nr\.?"
    r"|Kundennummer|Kunden-?Nr\.?"
    r"|Auftrag(?:s(?:nummer)?)?|Auftrags-?Nr\.?"
    r"|Bestellung(?:s(?:nummer)?)?|Bestell-?Nr\.?"
    r"|Aktenzeichen|Az\.?"
    r"|Vertrag(?:s(?:nummer)?)?|Vertrags-?Nr\.?"
    r"|Fall(?:nummer)?|Fall-?Nr\.?"
    r"|Ticket-?(?:Nr\.?|Nummer)?)"
    r"\s*[:\-#]?\s*\d[\w\-/]{1,19}",
    re.I | re.UNICODE,
)

# ── Personennamen (DSGVO Art. 4 Nr. 1 — natürliche Person identifizierbar) ────
# Keyword-getriggert: Titel/Rolle gefolgt von Vorname + Nachname
_PERSON_NAME_PATTERN = re.compile(
    r"(?:Herr(?:n|en)?|Frau|Hr\.|Fr\."
    r"|Mitarbeiter(?:in)?|Kollege|Kollegin"
    r"|Bewerber(?:in)?|Kandidat(?:in)?"
    r"|Arbeitnehmer(?:in)?|Angestellte[rn]?"
    r"|Vorgesetzte[rn]?|Auszubildende[rn]?|Praktikant(?:in)?)"
    r"\s+"
    r"([A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜ][a-zäöüß\-]+)+)",
    re.UNICODE,
)

# ── HR / Personalplanung (DSGVO Art. 22, EU AI Act — requires_human_decision) ─
_HR_PATTERN = re.compile(
    r"\b(Mitarbeitereinsatz|Personalplanung|Schichtplan|Dienstplan|Personalentscheidung"
    r"|Leistungsbewertung|Bewerberdaten|Bewerber|Kündigung|Abmahnung|abgemahnt|abmahnen"
    r"|Beurteilung|Gehaltsabrechnung|Lohnabrechnung|Personalakte|Urlaubsantrag\s+genehmigen"
    r"|Entlassung|Versetzung|Disziplinar(?:verfahren|maßnahme|maßnahmen)?"
    r"|staff\s+(?:assignment|scheduling|decision)|shift\s+plan|workforce\s+planning"
    r"|performance\s+(?:review|evaluation)|employee\s+(?:record|file|evaluation)"
    r"|termination|disciplinary|payroll|leave\s+approval)\b",
    re.I,
)

# ── Personenentscheidungs-Kontext (DSGVO Art. 22) ────────────────────────────
_PERSON_DECISION_PATTERN = re.compile(
    r"\b(einteilen|zuweisen|ablehnen|abweisen|blockieren|sperren|bewerten|bewilligen"
    r"|assign|deny\s+access|block\s+(?:person|user|entry)|evaluate\s+(?:person|candidate)"
    r"|reject\s+(?:person|candidate|entry)|automated\s+decision)\b",
    re.I,
)

# ── CSV / Event-Log-Struktur (strukturierte Personendaten, mind. INTERNAL) ───
_TABULAR_PERSONAL_PATTERN = re.compile(
    r"(?:Name|Vorname|Nachname|Geburtsdatum|Ausweis|Ticket-?ID|E-?Mail|Telefon"
    r"|firstname|lastname|birthdate|passport|ticket_id|email|phone)"
    r"[\s,;|]+\w",
    re.I,
)


def classify(text: str) -> ClassificationResult:
    """Klassifiziert einen Text pattern-basiert. Fail-closed bei Fehler."""
    try:
        if text is None:
            text = ""
        matched: list[str] = []
        classes: set[DataClass] = set()
        requires_human_decision = False

        # ── Credentials ──────────────────────────────────────────────────────
        for name, pattern in _SECRET_PATTERNS:
            if pattern.search(text):
                matched.append(name)
                classes.add(DataClass.CREDENTIALS)

        # ── Kontaktdaten / Identifikatoren ───────────────────────────────────
        if _EMAIL_PATTERN.search(text):
            matched.append("email")
            classes.add(DataClass.PERSONAL_DATA)
        if _PHONE_PATTERN.search(text):
            matched.append("phone")
            classes.add(DataClass.PERSONAL_DATA)
        if _IP_PATTERN.search(text):
            matched.append("ip_address")
            classes.add(DataClass.PERSONAL_DATA)
        if _PERSONAL_ID_PATTERN.search(text):
            matched.append("personal_identifier")
            classes.add(DataClass.PERSONAL_DATA)

        # ── Personennamen (DSGVO Art. 4 Nr. 1) ───────────────────────────────
        if _PERSON_NAME_PATTERN.search(text):
            matched.append("person_name")
            classes.add(DataClass.PERSONAL_DATA)

        # ── Referenznummern (Kunden-/Rechnungs-/Auftragsnummer — Identifier) ─
        if _REFERENCE_NUMBER_PATTERN.search(text):
            matched.append("reference_number")
            classes.add(DataClass.PERSONAL_DATA)

        # ── Tabellarische Personendaten (CSV / Event-Log) ────────────────────
        if _TABULAR_PERSONAL_PATTERN.search(text):
            matched.append("tabular_personal_data")
            classes.add(DataClass.PERSONAL_DATA)

        # ── DSGVO Art. 9 — Besondere Kategorien (inkl. Biometrie) ────────────
        for rule_name, pattern in _SPECIAL_CATEGORY_PATTERNS:
            if pattern.search(text):
                matched.append(rule_name)
                classes.add(DataClass.SPECIAL_CATEGORY)
                if rule_name == "biometric":
                    requires_human_decision = True

        # ── HR / Personalentscheidungen (DSGVO Art. 22) ──────────────────────
        if _HR_PATTERN.search(text):
            matched.append("hr_context")
            classes.add(DataClass.HR)
            requires_human_decision = True

        # Kombination: Personenbezug + Entscheidungsverb → Art.-22-Pflicht
        if _PERSON_DECISION_PATTERN.search(text) and (
            DataClass.PERSONAL_DATA in classes
            or DataClass.HR in classes
            or DataClass.SPECIAL_CATEGORY in classes
        ):
            matched.append("person_decision_context")
            requires_human_decision = True

        # ── Finanzdaten ───────────────────────────────────────────────────────
        if _IBAN_PATTERN.search(text):
            matched.append("iban")
            classes.add(DataClass.FINANCIAL)
        if _CARD_PATTERN.search(text) and not _IBAN_PATTERN.search(text):
            digits = re.sub(r"\D", "", _CARD_PATTERN.search(text).group())
            if 13 <= len(digits) <= 16:
                matched.append("credit_card")
                classes.add(DataClass.FINANCIAL)

        if not classes:
            classes.add(DataClass.PUBLIC)

        ordered = sorted(classes, key=lambda c: RISK_ORDER.index(c))
        highest = ordered[-1]
        needs_review = highest in {DataClass.CREDENTIALS, DataClass.SPECIAL_CATEGORY} or requires_human_decision

        return ClassificationResult(
            data_classes=ordered,
            highest_risk_class=highest,
            confidence=0.9 if matched else 0.6,
            matched_rules=matched,
            needs_review=needs_review,
            requires_human_decision=requires_human_decision,
        )
    except Exception:
        return ClassificationResult(
            data_classes=[DataClass.CREDENTIALS],
            highest_risk_class=DataClass.CREDENTIALS,
            confidence=0.0,
            matched_rules=["classification_error"],
            needs_review=True,
            requires_human_decision=False,
        )
