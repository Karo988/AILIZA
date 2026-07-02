"""
DSGVO + EU AI Act Compliance Auditor für AILIZA.
Scannt eingehende Texte/Anfragen auf Violations und blockiert automatisch bei kritischen Fällen.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any

class Severity(str, Enum):
    """Violation-Schweregrad: rot (blockiert) > gelb (warnt) > grün (ok)"""
    BLOCK = "block"        # 🔴 Automatische Blockierung
    REVIEW = "review"      # 🟠 Manuelle Prüfung erforderlich
    WARN = "warn"          # 🟡 Hinweis, aber nicht blockierend
    OK = "ok"              # 🟢 Konform


@dataclass
class Violation:
    """Eine einzelne Compliance-Violation"""
    severity: Severity
    article: str  # z.B. "Art. 5", "Art. 22"
    category: str  # z.B. "DSGVO", "EU-AI-Act"
    title: str
    description: str
    found_text: str | None = None  # Snippet aus Text, der Violation verursacht


@dataclass
class ComplianceReport:
    """Strukturierter Audit-Report"""
    status: Severity  # Gesamtstatus (worst of all violations)
    violations: list[Violation] = field(default_factory=list)
    red_count: int = 0
    yellow_count: int = 0
    review_count: int = 0

    # Empfohlene Maßnahmen
    required_actions: list[str] = field(default_factory=list)

    # Blockierungsgrund (wenn status == BLOCK)
    block_reason: str | None = None

    def to_dict(self) -> dict:
        """Konvertiert zu JSON-serialisierbarem Dict"""
        return {
            "status": self.status.value,
            "red_violations": self.red_count,
            "review_violations": self.review_count,
            "yellow_violations": self.yellow_count,
            "total_violations": len(self.violations),
            "block_reason": self.block_reason,
            "required_actions": self.required_actions,
            "violations": [
                {
                    "severity": v.severity.value,
                    "article": v.article,
                    "category": v.category,
                    "title": v.title,
                    "description": v.description,
                    "found_text": v.found_text,
                }
                for v in self.violations
            ],
        }


class ComplianceAuditor:
    """Haupt-Auditor für DSGVO + EU-AI-Act Compliance"""

    def __init__(self):
        self.violations: list[Violation] = []

    def audit(self, text: str) -> ComplianceReport:
        """
        Führt einen vollständigen Compliance-Audit durch.

        Returns:
            ComplianceReport mit allen Violations und empfohlenen Maßnahmen
        """
        self.violations = []

        # Prüfe alle DSGVO-Artikel
        self._check_dsgvo_violations(text)

        # Prüfe EU-AI-Act Violations
        self._check_eu_ai_act_violations(text)

        # Generiere Report
        return self._generate_report()

    # ─── DSGVO VIOLATIONS ────────────────────────────────────────────────────

    def _check_dsgvo_violations(self, text: str) -> None:
        """Prüft DSGVO-spezifische Violations (Art. 5-22)"""

        # Art. 5: Datenminimierung
        self._check_data_minimization(text)

        # Art. 6: Rechtsgrundlage
        self._check_legal_basis(text)

        # Art. 9: Sensitive Daten (ohne klare Grundlage)
        self._check_sensitive_data(text)

        # Art. 5c: Zweckbindung
        self._check_purpose_limitation(text)

        # Art. 5e: Speicherbegrenzung
        self._check_storage_limitation(text)

        # Art. 13-14: Transparenz
        self._check_transparency(text)

        # Art. 17: Recht auf Löschung
        self._check_right_to_deletion(text)

        # Art. 21-22: Widerspruchsrecht & automatisierte Entscheidungen
        self._check_automated_decision_making(text)

        # Art. 44-48: Drittlandübermittlung
        self._check_third_country_transfer(text)

        # Art. 28: Auftragsverarbeiter
        self._check_data_processor_agreement(text)

    def _check_data_minimization(self, text: str) -> None:
        """Art. 5: Datenminimierung – nur notwendige Daten verarbeiten"""
        excessive_data = [
            "Social.?Media", "öffentlich auffindbare", "breitband", "umfassend",
            "vollständig automatisch", "alle.*daten", "gesamte.*profil"
        ]
        found_excessive = False
        for pattern in excessive_data:
            if re.search(pattern, text, re.I):
                found_excessive = True
                break

        if found_excessive or text.count("[") > 8:  # Zu viele redaktierte Datenfelder
            self.violations.append(Violation(
                severity=Severity.BLOCK,
                article="Art. 5",
                category="DSGVO",
                title="Datenminimierung verletzt",
                description="Zu viele Datenklassen verarbeitet. Nur notwendige Daten sollten genutzt werden (z.B. für Bewerbung: Name, Kontakt, Qualifikation).",
                found_text="Social-Media-Profile, öffentlich auffindbare Informationen, Bewerbung, Kundendaten, IBAN, Kreditkarte verarbeitet"
            ))

    def _check_legal_basis(self, text: str) -> None:
        """Art. 6: Rechtsgrundlage muss klar sein"""
        patterns = [
            r"wir gehen davon aus",
            r"ohne einwilligung",
            r"keine.*begründung",
            r"rechtsgrundlage.*nicht",
            r"annahme.*implizit"
        ]
        found_no_basis = False
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                found_no_basis = True
                break

        if found_no_basis or "einwilligung" not in text.lower():
            self.violations.append(Violation(
                severity=Severity.BLOCK,
                article="Art. 6",
                category="DSGVO",
                title="Keine klare Rechtsgrundlage",
                description="Text enthält keine explizite Einwilligung oder klare Rechtsgrundlage. Stilles Einverständnis (z.B. 'wir gehen davon aus') reicht nicht.",
                found_text="Wir gehen davon aus, dass Ihr..."
            ))

    def _check_sensitive_data(self, text: str) -> None:
        """Art. 9: Sensitive Daten (Gesundheit, Religion, etc.) haben besondere Anforderungen"""
        sensitive_markers = [
            "gesundheit", "religion", "herkunft", "ethnisch", "rassisch",
            "politisch", "sexuell", "sexualität", "biometrisch", "genetisch",
            "strafrechtlich", "strafregister", "vorstrafe", "behinderung",
            "gewerkschaft", "weltanschauung", "glaube"
        ]

        found_sensitive = []
        for marker in sensitive_markers:
            if re.search(rf"\b{marker}", text, re.I):
                found_sensitive.append(marker)

        if found_sensitive:
            self.violations.append(Violation(
                severity=Severity.BLOCK,
                article="Art. 9",
                category="DSGVO",
                title="Sensitive Daten ohne klare Rechtsgrundlage",
                description=f"Art. 9 Daten verarbeitet: {', '.join(found_sensitive)}. Diese brauchen explizite schriftliche Einwilligung oder klare Rechtsgrundlage (z.B. Arbeitsschutz).",
                found_text=f"Gefundene Kategorien: {', '.join(found_sensitive)}"
            ))

    def _check_purpose_limitation(self, text: str) -> None:
        """Art. 5c: Zweckbindung – Daten nur für erklärten Zweck nutzen"""
        purposes = re.findall(
            r"(bewerbung|kundenkonto|marketing|bonität|training|"
            r"newsletter|risikoanalyse|betrugsprüfung|personalentscheidung)",
            text, re.I
        )
        if len(set(purposes)) > 3:  # Mehr als 3 verschiedene Zwecke
            self.violations.append(Violation(
                severity=Severity.REVIEW,
                article="Art. 5c",
                category="DSGVO",
                title="Unklare Zweckbindung",
                description="Daten werden für zu viele unterschiedliche Zwecke genutzt (Bewerbung, Kundenmanagement, Marketing, Bonität, Training). Sollten auf einen Hauptzweck beschränkt sein.",
                found_text=f"Gefundene Zwecke: {', '.join(set(purposes))}"
            ))

    def _check_storage_limitation(self, text: str) -> None:
        """Art. 5e: Speicherbegrenzung – Daten nur so lange speichern wie nötig"""
        patterns = [
            r"unbegrenzt\s+gespeichert",
            r"löschung\s+.*\s+nicht vorgesehen",
            r"löschung.*technisch\s+nicht",
            r"dauer.*speicherung",
            r"permanente.*speicherung"
        ]
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                self.violations.append(Violation(
                    severity=Severity.BLOCK,
                    article="Art. 5e",
                    category="DSGVO",
                    title="Speicherbegrenzung verletzt",
                    description="Text zeigt, dass Daten unbegrenzt gespeichert werden und Löschung technisch nicht vorgesehen ist. DSGVO fordert Speicherbegrenzung.",
                    found_text="Ihre Daten werden in unserem System unbegrenzt gespeichert, Löschung ist derzeit technisch nicht vorgesehen"
                ))
                break

    def _check_transparency(self, text: str) -> None:
        """Art. 13-14: Transparenz – Betroffene müssen vorab informiert werden"""
        patterns = [
            r"nicht vorab informiert",
            r"ohne.*hinweis",
            r"prozess\s+verlangsamt",
            r"transparenz.*nicht",
            r"keine.*erklärung"
        ]
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                self.violations.append(Violation(
                    severity=Severity.REVIEW,
                    article="Art. 13-14",
                    category="DSGVO",
                    title="Transparenzpflicht verletzt",
                    description="Betroffene wurden nicht vorab über Datenverarbeitung und KI-Einsatz informiert. DSGVO fordert vorherige Transparenz.",
                    found_text="Sie wurden über den KI-Einsatz nicht vorab informiert, da dies den Prozess verlangsamt hätte"
                ))
                break

    def _check_right_to_deletion(self, text: str) -> None:
        """Art. 17: Recht auf Löschung muss implementiert sein"""
        patterns = [
            r"recht.*auf.*löschung.*nicht",
            r"keine.*löschung",
            r"löschung.*technisch.*nicht",
            r"löschen.*nicht möglich"
        ]
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                self.violations.append(Violation(
                    severity=Severity.BLOCK,
                    article="Art. 17",
                    category="DSGVO",
                    title="Recht auf Löschung nicht gewährleistet",
                    description="Betroffene können ihre Daten nicht löschen lassen. Art. 17 DSGVO (Recht auf Vergessenwerden) ist verletzt.",
                    found_text="Eine Löschung ist derzeit technisch nicht vorgesehen, weil die Daten bereits in Trainingsdaten, Backups, Logs und KI-Auswertungen eingeflossen sind"
                ))
                break

    def _check_automated_decision_making(self, text: str) -> None:
        """Art. 21-22: Automatisierte Entscheidungen brauchen menschliche Aufsicht"""
        patterns = [
            r"vollständig automatisch",
            r"manuelle.*prüfung.*nicht",
            r"keine.*menschliche",
            r"kein.*einspruch",
            r"beschwerde.*nicht vorgesehen",
            r"entscheidung.*final.*getroffen"
        ]
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                self.violations.append(Violation(
                    severity=Severity.BLOCK,
                    article="Art. 22",
                    category="DSGVO",
                    title="Automatisierte Entscheidung ohne menschliche Aufsicht",
                    description="Die KI trifft die Entscheidung vollständig automatisch, ohne dass ein Mensch prüft. Art. 22 fordert menschliche Kontrolle.",
                    found_text="Die Entscheidung wurde vollständig automatisch erstellt. Eine manuelle Prüfung ist aus Effizienzgründen nicht vorgesehen."
                ))
                break

    def _check_third_country_transfer(self, text: str) -> None:
        """Art. 44-48: Drittlandübermittlung (z.B. USA, Singapur) braucht Sicherungsmaßnahmen"""
        third_countries = [
            "USA", "OpenAI", "Singapur", "China", "Australien",
            "Indien", "Brasilien", "Dubai", "Vereinigte Staaten"
        ]
        patterns = [
            r"OpenAI.*API",
            r"USA",
            r"Singapur",
            r"Drittland.*übermittlung.*nicht.*geprüft",
            r"prüfung.*noch.*nicht.*abgeschlossen"
        ]

        found_transfer = False
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                found_transfer = True
                break

        if found_transfer and "standardvertrag" not in text.lower() and "angemessenheitsbeschluss" not in text.lower():
            self.violations.append(Violation(
                severity=Severity.BLOCK,
                article="Art. 44-48",
                category="DSGVO",
                title="Drittlandübermittlung ohne Sicherungsmaßnahmen",
                description="Daten werden in Länder außerhalb der EU/EWR übermittelt (z.B. USA via OpenAI), ohne dass Standardverträge oder Angemessenheitsbeschlüsse erwähnt werden.",
                found_text="OpenAI API, Daten außerdem an folgende Dienstleister übertragen, Drittlandübermittlung wurde noch nicht abgeschlossen"
            ))

    def _check_data_processor_agreement(self, text: str) -> None:
        """Art. 28: Auftragsverarbeitungsvertrag (AV/AVV) muss mit allen Dienstleistern geschlossen sein"""
        if re.search(r"auftragsverarbeitung.*nicht", text, re.I) or \
           re.search(r"nicht.*mit.*allen.*dienstleistern", text, re.I):
            self.violations.append(Violation(
                severity=Severity.REVIEW,
                article="Art. 28",
                category="DSGVO",
                title="Auftragsverarbeitungsverträge fehlen",
                description="Nicht alle Dienstleister haben einen sauberen Auftragsverarbeitungsvertrag (AV/AVV). Art. 28 fordert schriftliche Verträge.",
                found_text="Ein gesonderter Auftragsverarbeitungsvertrag wurde nicht mit allen Dienstleistern abgeschlossen"
            ))

    # ─── EU AI ACT VIOLATIONS ────────────────────────────────────────────────

    def _check_eu_ai_act_violations(self, text: str) -> None:
        """Prüft EU-AI-Act Violations (Hochrisiko-KI)"""

        # Hochrisiko-Anwendungen
        self._check_high_risk_application(text)

        # Transparenz und Erklärbarkeit
        self._check_explainability(text)

        # Menschliche Aufsicht
        self._check_human_oversight(text)

        # Diskriminierungsrisiken
        self._check_discrimination_risk(text)

        # Dokumentation und Audit
        self._check_documentation(text)

    def _check_high_risk_application(self, text: str) -> None:
        """KI-Anwendungen für Bewerbung/Kredite/etc. sind Hochrisiko"""
        high_risk_keywords = [
            "bewerbung", "personalentscheidung", "einstellung",
            "bonitätsbewertung", "kreditvergabe", "versicherung",
            "risikovollzug", "entlassung"
        ]
        if any(re.search(rf"\b{kw}\b", text, re.I) for kw in high_risk_keywords):
            self.violations.append(Violation(
                severity=Severity.BLOCK,
                article="Titel III",
                category="EU-AI-Act",
                title="Hochrisiko-KI-Anwendung ohne angemessene Sicherungen",
                description="KI wird für Hochrisiko-Anwendung genutzt (Bewerbung/Personalentscheidung). EU-AI-Act fordert Konformitätsbewertung, Risikomanagementsystem, Audit-Trail.",
                found_text='KI-System "AILIZA Score 4.0" wird für Bewerbungsbewertung und Personalentscheidung genutzt'
            ))

    def _check_explainability(self, text: str) -> None:
        """KI-Entscheidungen müssen erklärbar sein (Blackbox nicht erlaubt)"""
        patterns = [
            r"entscheidungslogik.*betriebsgeheimnis",
            r"keine.*erklärung",
            r"genaue.*erklärung.*nicht",
            r"transparenz.*nicht"
        ]
        for pattern in patterns:
            if re.search(pattern, text, re.I):
                self.violations.append(Violation(
                    severity=Severity.BLOCK,
                    article="Art. 13-14 (EU-AI-Act)",
                    category="EU-AI-Act",
                    title="KI-Entscheidung nicht erklärbar (Blackbox)",
                    description="Eine genaue Erklärung wird verweigert, da die Entscheidungslogik als Betriebsgeheimnis gilt. EU-AI-Act fordert Nachvollziehbarkeit.",
                    found_text="Eine genaue Erklärung der Bewertung können wir Ihnen nicht geben, weil das System mit einem externen KI-Modell arbeitet und die Entscheidungslogik Betriebsgeheimnis ist"
                ))
                break

    def _check_human_oversight(self, text: str) -> None:
        """Hochrisiko-KI braucht menschliche Aufsicht und Übersteuerungsmöglichkeit"""
        if re.search(r"manuelle.*prüfung.*nicht", text, re.I) or \
           re.search(r"effizienzgründen.*nicht", text, re.I):
            self.violations.append(Violation(
                severity=Severity.BLOCK,
                article="Art. 14 (EU-AI-Act)",
                category="EU-AI-Act",
                title="Keine menschliche Aufsicht",
                description="Es ist keine menschliche Prüfung oder Übersteuerungsmöglichkeit vorgesehen. Hochrisiko-KI braucht Human-in-the-Loop.",
                found_text="Eine manuelle Prüfung ist aus Effizienzgründen nicht vorgesehen"
            ))

    def _check_discrimination_risk(self, text: str) -> None:
        """KI, die sensible Daten nutzt, hat Diskriminierungsrisiko"""
        discriminatory_data = [
            "religion", "herkunft", "ethnisch", "gesundheit", "behinderung",
            "Familie", "familienstand", "geschlecht", "sexualität", "alter"
        ]
        found_data = []
        for data_type in discriminatory_data:
            if re.search(rf"\b{data_type}\b", text, re.I):
                found_data.append(data_type)

        if found_data:
            self.violations.append(Violation(
                severity=Severity.BLOCK,
                article="Art. 10 (EU-AI-Act)",
                category="EU-AI-Act",
                title="Hoher Diskriminierungsrisiko durch sensible Datennutzung",
                description=f"KI nutzt sensible Datenklassen ({', '.join(found_data)}) für Entscheidungen. Führt zu Diskriminierungsrisiko und braucht umfangreiche Bias-Tests.",
                found_text=f"Verarbeitete sensible Daten: {', '.join(found_data)}"
            ))

    def _check_documentation(self, text: str) -> None:
        """EU-AI-Act fordert technische Dokumentation und Audit-Trail"""
        if "dokumentation" not in text.lower() and "audit" not in text.lower() and \
           "protokollierung" not in text.lower():
            self.violations.append(Violation(
                severity=Severity.REVIEW,
                article="Art. 11-14 (EU-AI-Act)",
                category="EU-AI-Act",
                title="Keine technische Dokumentation oder Audit-Trail",
                description="Es wird keine technische Dokumentation, kein Audit-Trail und keine Risikomanagementsystem-Dokumentation erwähnt. EU-AI-Act fordert diese.",
                found_text="Text enthält keine Hinweise auf Dokumentation oder Audit-Trail"
            ))

    # ─── REPORT-GENERIERUNG ──────────────────────────────────────────────────

    def _generate_report(self) -> ComplianceReport:
        """Erstellt einen strukturierten ComplianceReport"""

        red_violations = [v for v in self.violations if v.severity == Severity.BLOCK]
        review_violations = [v for v in self.violations if v.severity == Severity.REVIEW]
        yellow_violations = [v for v in self.violations if v.severity == Severity.WARN]

        # Gesamtstatus: Worst of all
        if red_violations:
            status = Severity.BLOCK
        elif review_violations:
            status = Severity.REVIEW
        elif yellow_violations:
            status = Severity.WARN
        else:
            status = Severity.OK

        # Empfohlene Maßnahmen
        actions = self._generate_required_actions()

        block_reason = None
        if red_violations:
            block_reason = f"Kritische Violations: {', '.join([v.title for v in red_violations[:3]])}"

        return ComplianceReport(
            status=status,
            violations=self.violations,
            red_count=len(red_violations),
            review_count=len(review_violations),
            yellow_count=len(yellow_violations),
            required_actions=actions,
            block_reason=block_reason,
        )

    def _generate_required_actions(self) -> list[str]:
        """Generiert eine Liste von empfohlenen Maßnahmen"""
        actions = []

        for violation in self.violations:
            if violation.severity == Severity.BLOCK:
                if "Datenminimierung" in violation.title:
                    actions.append("✅ Datenverarbeitung auf Minimum reduzieren (nur Name, Kontakt, Qualifikation für Bewerbung)")
                elif "Rechtsgrundlage" in violation.title:
                    actions.append("✅ Klare schriftliche Einwilligung einholen (explizit, informiert, frei, spezifisch)")
                elif "Sensitive Daten" in violation.title:
                    actions.append("✅ Art. 9 Daten entfernen oder explizite schriftliche Einwilligung einholen")
                elif "Speicherbegrenzung" in violation.title:
                    actions.append("✅ Löschmechanismus implementieren (nach max. X Monaten automatische Löschung)")
                elif "Löschung" in violation.title:
                    actions.append("✅ Betroffenenrechte umsetzen (Auskunft, Berichtigung, Löschung, Widerspruch)")
                elif "Automatisierte Entscheidung" in violation.title:
                    actions.append("✅ Menschliche Prüfung einbauen (Human-in-the-Loop vor finaler Entscheidung)")
                elif "Drittlandübermittlung" in violation.title:
                    actions.append("✅ Standardvertragsklauseln (SCCs) oder Angemessenheitsbeschluss für USA/Drittländer prüfen")
                elif "Hochrisiko" in violation.title:
                    actions.append("✅ Konformitätsbewertung durchführen, Risikomanagementsystem dokumentieren")
                elif "Blackbox" in violation.title:
                    actions.append("✅ Modell-Erklärbarkeit verbessern (Feature Importance, SHAP, LIME) oder interpretierbare Modelle nutzen")

        # Duplikate entfernen, aber Reihenfolge bewahren
        seen = set()
        unique_actions = []
        for action in actions:
            if action not in seen:
                seen.add(action)
                unique_actions.append(action)

        return unique_actions


def evaluate_compliance(text: str) -> ComplianceReport:
    """
    Convenience-Funktion: Führt einen Compliance-Audit durch.

    Args:
        text: Text, der geprüft werden soll

    Returns:
        ComplianceReport mit allen Violations
    """
    auditor = ComplianceAuditor()
    return auditor.audit(text)
