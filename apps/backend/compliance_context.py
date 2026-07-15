"""
AILIZA — Compliance Context Manager
Fügt automatisch relevante DSGVO + EU AI Act Artikel
in jeden Chat-Kontext ein.
Läuft unsichtbar im Hintergrund — keine Token-Verschwendung.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ComplianceContext:
    """Compliance-Kontext der bei jeder Anfrage mitläuft."""
    dsgvo_articles: list = field(default_factory=list)
    eu_ai_act_articles: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    risk_level: str = "low"
    requires_transparency: bool = True
    requires_human_oversight: bool = False


# ── Vollständige Compliance-Datenbank ───────────────────────────────────────

DSGVO_ARTICLES = {
    "art_5": {
        "title": "Art. 5 DSGVO — Grundsätze",
        "short": "Zweckbindung, Datensparsamkeit, Richtigkeit, Speicherbegrenzung",
        "keywords": ["daten", "speichern", "verarbeiten", "nutzen", "sammeln"],
        "rule": "Daten nur für festgelegte Zwecke verarbeiten. Keine unnötige Speicherung."
    },
    "art_6": {
        "title": "Art. 6 DSGVO — Rechtmäßigkeit",
        "short": "Verarbeitung nur mit Rechtsgrundlage (Einwilligung, Vertrag, etc.)",
        "keywords": ["einwilligung", "erlaubnis", "zustimmung", "verarbeitung"],
        "rule": "Jede Datenverarbeitung braucht eine Rechtsgrundlage."
    },
    "art_13": {
        "title": "Art. 13 DSGVO — Informationspflicht",
        "short": "Betroffene müssen über Datenverarbeitung informiert werden",
        "keywords": ["information", "transparenz", "mitteilen", "betroffene"],
        "rule": "Nutzer müssen wissen welche Daten wie verarbeitet werden."
    },
    "art_17": {
        "title": "Art. 17 DSGVO — Recht auf Löschung",
        "short": "Betroffene können Löschung ihrer Daten verlangen",
        "keywords": ["löschen", "entfernen", "vergessen", "löschung"],
        "rule": "Auf Anfrage müssen alle personenbezogenen Daten gelöscht werden."
    },
    "art_20": {
        "title": "Art. 20 DSGVO — Datenportabilität",
        "short": "Betroffene können ihre Daten in maschinenlesbarem Format erhalten",
        "keywords": ["export", "portabilität", "übertragen", "herausgabe"],
        "rule": "Daten müssen auf Anfrage exportierbar sein."
    },
    "art_25": {
        "title": "Art. 25 DSGVO — Privacy by Design",
        "short": "Datenschutz muss von Anfang an eingebaut sein",
        "keywords": ["design", "entwicklung", "system", "technisch"],
        "rule": "Datenschutz ist kein Nachgedanke — er muss eingebaut sein."
    },
    "art_30": {
        "title": "Art. 30 DSGVO — Verzeichnis der Verarbeitungstätigkeiten",
        "short": "Alle Datenverarbeitungen müssen dokumentiert werden",
        "keywords": ["dokumentation", "verzeichnis", "protokoll", "audit"],
        "rule": "Jede Verarbeitung muss im Verzeichnis eingetragen sein."
    },
    "art_35": {
        "title": "Art. 35 DSGVO — Datenschutz-Folgenabschätzung",
        "short": "Bei hohem Risiko muss eine DSFA durchgeführt werden",
        "keywords": ["risiko", "folgenabschätzung", "dsfa", "hochrisiko"],
        "rule": "Vor risikoreichen Verarbeitungen muss eine DSFA durchgeführt werden."
    },
}

EU_AI_ACT_ARTICLES = {
    "art_5": {
        "title": "Art. 5 EU AI Act — Verbotene Praktiken",
        "short": "Manipulation, Social Scoring, biometrische Massenüberwachung verboten",
        "keywords": ["manipulation", "täuschung", "social scoring", "überwachung"],
        "rule": "Diese KI-Praktiken sind in der EU verboten."
    },
    "art_9": {
        "title": "Art. 9 EU AI Act — Risikomanagement",
        "short": "Hochrisiko-KI braucht ein Risikomanagementsystem",
        "keywords": ["risiko", "management", "hochrisiko", "bewertung"],
        "rule": "Risiken müssen systematisch identifiziert und gemindert werden."
    },
    "art_13": {
        "title": "Art. 13 EU AI Act — Transparenz",
        "short": "KI-Systeme müssen transparent und erklärbar sein",
        "keywords": ["transparenz", "erklärbar", "nachvollziehbar", "dokumentation"],
        "rule": "Nutzer müssen verstehen wie das KI-System Entscheidungen trifft."
    },
    "art_14": {
        "title": "Art. 14 EU AI Act — Menschliche Aufsicht",
        "short": "Menschen müssen KI-Entscheidungen überwachen und korrigieren können",
        "keywords": ["aufsicht", "kontrolle", "überwachen", "eingriff", "human oversight"],
        "rule": "Ein Mensch muss KI-Entscheidungen jederzeit stoppen können."
    },
    "art_50": {
        "title": "Art. 50 EU AI Act — Transparenzpflicht",
        "short": "KI-Systeme müssen sich als KI kennzeichnen",
        "keywords": ["kennzeichnung", "offenlegung", "ki-system", "chatbot"],
        "rule": "AILIZA muss sich immer als KI-System kennzeichnen."
    },
    "art_6": {
        "title": "Art. 6 + Anhang III EU AI Act — Hochrisiko-KI",
        "short": "Bestimmte KI-Anwendungen gelten als Hochrisiko",
        "keywords": ["kredit", "einstellung", "bildung", "strafverfolgung", "medizin"],
        "rule": "Hochrisiko-KI braucht besondere Anforderungen und Zertifizierung."
    },
}

# ── Compliance Context Manager ───────────────────────────────────────────────

class ComplianceContextManager:
    """
    Analysiert jede Anfrage und fügt relevante
    DSGVO + EU AI Act Artikel automatisch in den Kontext ein.
    """

    # Immer aktive Basis-Regeln (in jedem Chat)
    BASE_SYSTEM_PROMPT = """Du bist AILIZA, ein EU-konformer KI-Assistent.

PFLICHTREGELN (immer aktiv):
1. Kennzeichne dich immer als KI-System [EU AI Act Art. 50]
2. Verarbeite keine unnötigen personenbezogenen Daten [DSGVO Art. 5]
3. Sei transparent über deine Funktionsweise [EU AI Act Art. 13]
4. Weise auf menschliche Aufsicht hin wenn nötig [EU AI Act Art. 14]
5. Antworte auf Deutsch, präzise und hilfreich

RISIKOKLASSE: Limited Risk (Art. 50 EU AI Act)
FRIST: 02.08.2026 — Vollständige EU AI Act Anwendbarkeit"""

    def build_system_prompt(
        self,
        user_message: str,
        conversation_context: list = None,
        additional_rules: list = None,
    ) -> tuple[str, ComplianceContext]:
        """
        Analysiert die Anfrage und baut einen compliance-konformen System-Prompt.
        Gibt den Prompt + den Compliance-Kontext zurück.
        """
        compliance = self._analyze_message(user_message, conversation_context or [])
        prompt = self._build_prompt(compliance, additional_rules or [])
        return prompt, compliance

    def _analyze_message(self, message: str, context: list) -> ComplianceContext:
        """Analysiert Nachricht und Kontext auf relevante Compliance-Aspekte."""
        text = message.lower()
        ctx_text = " ".join(m.get("content", "") for m in context).lower()
        combined = text + " " + ctx_text

        compliance = ComplianceContext()

        # DSGVO-Artikel prüfen
        for art_id, article in DSGVO_ARTICLES.items():
            if any(kw in combined for kw in article["keywords"]):
                compliance.dsgvo_articles.append(art_id)

        # EU AI Act Artikel prüfen
        for art_id, article in EU_AI_ACT_ARTICLES.items():
            if any(kw in combined for kw in article["keywords"]):
                compliance.eu_ai_act_articles.append(art_id)

        # Risiko-Level bestimmen
        high_risk_keywords = [
            "kredit", "kreditentscheidung", "einstellung", "kündigung",
            "medizinische diagnose", "strafverfolgung", "asyl", "bildungsbewertung"
        ]
        if any(kw in combined for kw in high_risk_keywords):
            compliance.risk_level = "high"
            compliance.requires_human_oversight = True
            if "art_6" not in compliance.eu_ai_act_articles:
                compliance.eu_ai_act_articles.append("art_6")
            compliance.warnings.append(
                "⚠️ Mögliche Hochrisiko-Anwendung erkannt (EU AI Act Art. 6, Anhang III)"
            )

        # PII erkannt?
        pii_patterns = [
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b",
            r"\bDE\d{2}[\s]?\d{4}",
        ]
        if any(re.search(p, message) for p in pii_patterns):
            if "art_5" not in compliance.dsgvo_articles:
                compliance.dsgvo_articles.append("art_5")
            compliance.warnings.append(
                "⚠️ Personenbezogene Daten erkannt — werden minimal verarbeitet [DSGVO Art. 5]"
            )

        # Immer Art. 50 aktiv
        if "art_50" not in compliance.eu_ai_act_articles:
            compliance.eu_ai_act_articles.append("art_50")

        return compliance

    def _build_prompt(self, compliance: ComplianceContext, additional_rules: list) -> str:
        """Baut den vollständigen System-Prompt mit Compliance-Kontext."""
        parts = [self.BASE_SYSTEM_PROMPT]

        # Relevante DSGVO-Artikel
        if compliance.dsgvo_articles:
            parts.append("\nAKTIVE DSGVO-REGELN FÜR DIESE ANFRAGE:")
            for art_id in compliance.dsgvo_articles:
                if art_id in DSGVO_ARTICLES:
                    a = DSGVO_ARTICLES[art_id]
                    parts.append(f"• {a['title']}: {a['rule']}")

        # Relevante EU AI Act Artikel
        if compliance.eu_ai_act_articles:
            parts.append("\nAKTIVE EU AI ACT REGELN FÜR DIESE ANFRAGE:")
            for art_id in compliance.eu_ai_act_articles:
                if art_id in EU_AI_ACT_ARTICLES:
                    a = EU_AI_ACT_ARTICLES[art_id]
                    parts.append(f"• {a['title']}: {a['rule']}")

        # Warnungen
        if compliance.warnings:
            parts.append("\nHINWEISE:")
            for w in compliance.warnings:
                parts.append(f"• {w}")

        # Hochrisiko
        if compliance.risk_level == "high":
            parts.append(
                "\n⚠️ HOCHRISIKO: Diese Anfrage betrifft eine Hochrisiko-Anwendung. "
                "Weise den Nutzer auf menschliche Aufsicht hin [EU AI Act Art. 14]."
            )

        # Zusätzliche Regeln
        if additional_rules:
            parts.append("\nWEITERE REGELN:")
            for rule in additional_rules:
                parts.append(f"• {rule}")

        # Am Ende immer Transparenzhinweis
        parts.append(
            "\nANTWORT-FORMAT: Antworte hilfreich und präzise. "
            "Bei sensiblen Themen: kurzen Compliance-Hinweis am Ende einfügen. "
            "Kennzeichne dich bei Bedarf als KI-System (AILIZA)."
        )

        return "\n".join(parts)

    def get_compliance_summary(self, compliance: ComplianceContext) -> dict:
        """Gibt eine Zusammenfassung des Compliance-Kontexts zurück."""
        return {
            "dsgvo_articles": [
                DSGVO_ARTICLES[a]["title"]
                for a in compliance.dsgvo_articles
                if a in DSGVO_ARTICLES
            ],
            "eu_ai_act_articles": [
                EU_AI_ACT_ARTICLES[a]["title"]
                for a in compliance.eu_ai_act_articles
                if a in EU_AI_ACT_ARTICLES
            ],
            "risk_level": compliance.risk_level,
            "warnings": compliance.warnings,
            "requires_human_oversight": compliance.requires_human_oversight,
        }
