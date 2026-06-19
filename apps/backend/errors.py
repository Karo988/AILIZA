"""
AILIZA Fehler-Definitionen
==========================
Verstaendliche deutsche Fehlermeldungen. Niemals Stack-Traces zum Client.
"""
from __future__ import annotations

from typing import Any


MESSAGES: dict[str, str] = {
    "kill_switch_active": "Die externe KI ist derzeit deaktiviert. Sie koennen Ihre Anfrage lokal bearbeiten oder einen Administrator kontaktieren.",
    "credentials_blocked": "Ihre Anfrage enthaelt moegliche Zugangsdaten oder API-Schluessel. Diese werden aus Sicherheitsgruenden nicht weitergeleitet.",
    "approval_required": "Fuer diese Aktion ist eine Freigabe erforderlich. Bitte wenden Sie sich an einen Administrator oder nutzen Sie die anonymisierte Version.",
    "provider_not_configured": "Kein KI-Anbieter ist fuer diesen Vorgang konfiguriert. Bitte pruefen Sie die Systemeinstellungen.",
    "budget_exceeded": "Das Token-Budget fuer diese Anfrage wurde ueberschritten. Bitte kuerzen Sie Ihre Eingabe oder waehlen Sie eine einfachere Aufgabe.",
    "no_api_key": "Der API-Schluessel fuer den KI-Anbieter fehlt. Bitte pruefen Sie die Konfiguration.",
    "data_class_blocked": "Diese Datenklasse darf nicht extern verarbeitet werden. Sie koennen die Daten anonymisieren oder lokal bearbeiten.",
    "redaction_required": "Diese Anfrage muss vor der externen Verarbeitung anonymisiert werden.",
    "document_blocked": "Dieses Dokument kann aus Sicherheitsgruenden nicht verarbeitet werden.",
    "internal_error": "Es ist ein interner Fehler aufgetreten. Bitte versuchen Sie es spaeter erneut.",
}


class AILIZAError(Exception):
    """Basis-Exception mit deutscher Meldung, Code und sicheren Alternativen."""

    def __init__(
        self,
        message_de: str,
        code: str,
        safe_alternatives: list[str] | None = None,
    ) -> None:
        super().__init__(message_de)
        self.message_de = message_de
        self.code = code
        self.safe_alternatives = safe_alternatives or []

    @classmethod
    def from_code(cls, code: str, safe_alternatives: list[str] | None = None) -> "AILIZAError":
        return cls(MESSAGES.get(code, MESSAGES["internal_error"]), code, safe_alternatives)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": True,
            "code": self.code,
            "message": self.message_de,
            "safe_alternatives": self.safe_alternatives,
        }
