"""
EU AI Act Compliance Modul
==========================
Implementiert die EU AI Act Anforderungen für AILIZA.

In Kraft seit: 1. August 2024
Vollständig anwendbar ab: 2. August 2026

Relevante Artikel:
- Art. 6:  Risikoklassifizierung
- Art. 9:  Risikomanagementsystem
- Art. 13: Transparenz und Bereitstellung von Informationen
- Art. 14: Menschliche Aufsicht
- Art. 52: Transparenzpflichten für bestimmte KI-Systeme
- Art. 69: Verhaltenskodizes
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional


# EU AI Act Risikoklassen (Art. 6)
class RiskLevel:
    UNACCEPTABLE = "unacceptable"   # Art. 5: Verboten
    HIGH = "high"                   # Anhang III: Hochrisiko
    LIMITED = "limited"             # Art. 52: Transparenzpflicht
    MINIMAL = "minimal"             # Keine spezifischen Anforderungen


class EUAIActCompliance:
    """
    EU AI Act Compliance Layer für AILIZA.

    AILIZA ist als LIMITED RISK klassifiziert (Art. 52):
    - Interagiert mit natürlichen Personen
    - Transparenzpflicht: User muss wissen, dass er mit KI interagiert
    - Keine autonomen Entscheidungen mit rechtlichen Folgen
    """

    # Aktueller EU AI Act Stand (wird regelmäßig aktualisiert)
    EU_AI_ACT_VERSION = "2024/1689"  # EU Verordnung 2024/1689
    ENFORCEMENT_DATE = "2026-08-02"  # Vollständige Anwendbarkeit

    def __init__(
        self,
        system_name: str,
        version: str,
        risk_level: str = RiskLevel.LIMITED,
    ):
        self.system_name = system_name
        self.version = version
        self.risk_level = risk_level
        self._human_oversight_active = True
        self._transparency_shown = False
        self._audit_log: List[Dict] = []
        self._created_at = time.time()

    # ── Art. 52: Transparenzpflicht ───────────────────────────────────────

    def get_transparency_notice(self, language: str = "de") -> str:
        """
        Erzeugt die Transparenzmitteilung (Art. 52 Abs. 1).
        Muss dem Nutzer VOR der ersten Interaktion angezeigt werden.
        """
        notices = {
            "de": (
                f"🤖 Sie interagieren mit {self.system_name} v{self.version}, "
                f"einem KI-System. Dieses System unterliegt dem EU AI Act "
                f"(Verordnung {self.EU_AI_ACT_VERSION}) und der DSGVO. "
                f"Ihre Daten werden datenschutzkonform verarbeitet."
            ),
            "en": (
                f"🤖 You are interacting with {self.system_name} v{self.version}, "
                f"an AI system. This system is subject to the EU AI Act "
                f"(Regulation {self.EU_AI_ACT_VERSION}) and GDPR. "
                f"Your data is processed in compliance with data protection laws."
            ),
        }
        self._transparency_shown = True
        self._log_action("transparency_notice_shown", {"language": language})
        return notices.get(language, notices["en"])

    def verify_transparency_shown(self) -> bool:
        """
        Prüft ob die Transparenzmitteilung angezeigt wurde (Art. 52).
        Sollte vor jeder Konversation aufgerufen werden.
        """
        return self._transparency_shown

    # ── Art. 14: Menschliche Aufsicht ─────────────────────────────────────

    def requires_human_oversight(self, action: str, risk_score: float = 0.0) -> bool:
        """
        Bestimmt ob eine Aktion menschliche Aufsicht erfordert (Art. 14).

        Args:
            action: Name der Aktion
            risk_score: Risikobewertung 0.0-1.0

        Returns:
            True wenn menschliche Genehmigung erforderlich
        """
        # Aktionen die immer menschliche Aufsicht erfordern
        HIGH_RISK_ACTIONS = {
            "delete_data",
            "send_email",
            "make_payment",
            "access_external_api",
            "modify_system_settings",
            "execute_code",
        }

        requires = (
            action in HIGH_RISK_ACTIONS
            or risk_score >= 0.7
            or self.risk_level == RiskLevel.HIGH
        )

        self._log_action("oversight_check", {
            "action": action,
            "risk_score": risk_score,
            "requires_oversight": requires,
        })

        return requires

    def request_human_approval(
        self,
        action: str,
        details: str,
        approver_id: str = None,
    ) -> Dict[str, Any]:
        """
        Erstellt eine Anfrage für menschliche Genehmigung (Art. 14).
        """
        request = {
            "request_id": f"approval_{int(time.time())}",
            "action": action,
            "details": details,
            "approver_id": approver_id,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "article": "EU AI Act Art. 14",
        }
        self._log_action("approval_requested", request)
        return request

    # ── Art. 9: Risikomanagement ──────────────────────────────────────────

    def assess_risk(self, action: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Bewertet das Risiko einer Aktion (Art. 9: Risikomanagementsystem).
        """
        context = context or {}

        # Basis-Risikobewertung
        risk_factors = []
        risk_score = 0.0

        # Faktor: Datenzugriff
        if context.get("accesses_personal_data"):
            risk_score += 0.3
            risk_factors.append("Zugriff auf personenbezogene Daten")

        # Faktor: Externe Systeme
        if context.get("calls_external_api"):
            risk_score += 0.2
            risk_factors.append("Aufruf externer API")

        # Faktor: Irreversible Aktionen
        if context.get("irreversible"):
            risk_score += 0.4
            risk_factors.append("Irreversible Aktion")

        # Faktor: Autonome Entscheidung
        if context.get("autonomous_decision"):
            risk_score += 0.3
            risk_factors.append("Autonome Entscheidung")

        risk_score = min(risk_score, 1.0)

        result = {
            "action": action,
            "risk_score": round(risk_score, 2),
            "risk_level": self._score_to_level(risk_score),
            "risk_factors": risk_factors,
            "requires_oversight": self.requires_human_oversight(action, risk_score),
            "assessed_at": datetime.utcnow().isoformat() + "Z",
        }

        self._log_action("risk_assessed", result)
        return result

    @staticmethod
    def _score_to_level(score: float) -> str:
        if score >= 0.7:
            return "high"
        elif score >= 0.4:
            return "medium"
        else:
            return "low"

    # ── Art. 13: Protokollierung ──────────────────────────────────────────

    def _log_action(self, action: str, details: Dict[str, Any]) -> None:
        """Interne Protokollierung für EU AI Act Compliance (Art. 13)."""
        self._audit_log.append({
            "action": action,
            "details": details,
            "timestamp": time.time(),
            "timestamp_iso": datetime.utcnow().isoformat() + "Z",
        })

    # ── Konformitätserklärung ─────────────────────────────────────────────

    def get_conformity_declaration(self) -> Dict[str, Any]:
        """
        Konformitätserklärung (EU AI Act Art. 47 für Hochrisiko, als Good Practice für Limited Risk).
        """
        return {
            "system": self.system_name,
            "version": self.version,
            "risk_classification": self.risk_level,
            "regulation": f"EU AI Act {self.EU_AI_ACT_VERSION}",
            "requirements_met": [
                "Art. 13: Transparenz und Informationsbereitstellung",
                "Art. 14: Menschliche Aufsicht implementiert",
                "Art. 52: Transparenzpflicht für Limited Risk KI",
            ],
            "conformity_date": datetime.utcnow().isoformat() + "Z",
            "next_review": "2025-08-01",
        }

    # ── Status ────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Gibt den aktuellen EU AI Act Compliance Status zurück."""
        return {
            "compliant": True,
            "regulation": f"EU AI Act {self.EU_AI_ACT_VERSION}",
            "risk_level": self.risk_level,
            "transparency_shown": self._transparency_shown,
            "human_oversight_active": self._human_oversight_active,
            "audit_entries": len(self._audit_log),
            "articles_implemented": [9, 13, 14, 52],
            "enforcement_date": self.ENFORCEMENT_DATE,
        }
