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
    "invalid_api_key": "Der API-Schluessel ist ungueltig. Bitte pruefen Sie die Konfiguration.",
    "provider_forbidden": "Der Anbieter verweigert den Zugriff. Bitte pruefen Sie die Berechtigungen.",
    "model_not_found": "Das angeforderte KI-Modell ist nicht verfuegbar.",
    "model_not_allowed": "Das KI-Modell ist in Ihrem aktuellen Anbieter-Plan nicht freigeschaltet. Bitte GROQ_MODEL anpassen oder einen Administrator kontaktieren.",
    "rate_limited": "Der KI-Anbieter ist momentan ausgelastet. Bitte versuchen Sie es spaeter erneut.",
    "provider_unavailable": "Der KI-Anbieter ist momentan nicht erreichbar. Bitte versuchen Sie es spaeter erneut.",
    "provider_error": "Der KI-Anbieter hat einen unbekannten Fehler gemeldet. Bitte versuchen Sie es spaeter erneut.",
    "all_providers_failed": "Kein KI-Anbieter konnte erfolgreich antworten. Bitte versuchen Sie es spaeter erneut.",
    "registry_provider_not_found": "Dieser KI-Anbieter ist in AILIZA nicht registriert und kann nicht genutzt werden.",
    "registry_provider_disabled": "Dieser KI-Anbieter ist in AILIZA deaktiviert. Bitte einen Administrator kontaktieren.",
    "registry_provider_not_approved": "Dieser Anbieter ist in AILIZA noch nicht freigegeben. Admin-Freigabe erforderlich.",
    "registry_data_class_not_allowed": "Fuer diese Datenklasse ist kein freigegebener Anbieter verfuegbar.",
    "registry_unavailable": "Die Anbieter-Registry konnte nicht geladen werden. Externe Calls sind deaktiviert.",
    "data_class_blocked": "Diese Datenklasse darf nicht extern verarbeitet werden. Sie koennen die Daten anonymisieren oder lokal bearbeiten.",
    "redaction_required": "Diese Anfrage muss vor der externen Verarbeitung anonymisiert werden.",
    "document_blocked": "Dieses Dokument kann aus Sicherheitsgruenden nicht verarbeitet werden.",
    "internal_error": "Es ist ein interner Fehler aufgetreten. Bitte versuchen Sie es spaeter erneut.",
    "policy_blocked": "Diese Aktion ist aufgrund der Datenschutz-Richtlinien nicht erlaubt. Bitte pruefen Sie die Datenklassen oder beantragen Sie eine Freigabe.",
    "capability_disabled": "Diese Faehigkeit ist derzeit deaktiviert. Bitte wenden Sie sich an einen Administrator.",
    "capability_unknown": "Unbekannte Faehigkeit. Die Aktion kann nicht ausgefuehrt werden.",
    "totp_required": "Bitte geben Sie Ihren TOTP-Code aus der Authenticator-App ein.",
    "totp_invalid": "Der TOTP-Code ist ungueltig oder abgelaufen. Bitte versuchen Sie es erneut.",
    "totp_not_configured": "Fuer Ihren Account ist kein TOTP konfiguriert. Bitte richten Sie die Zwei-Faktor-Authentifizierung ein.",
    "totp_already_confirmed": "TOTP ist bereits eingerichtet. Loeschen Sie das bestehende Setup, bevor Sie ein neues erstellen.",
    "totp_pending_invalid": "Der Zwei-Schritt-Login-Token ist ungueltig oder abgelaufen. Bitte melden Sie sich erneut an.",
    "sandbox_blocked": "Diese Aktion ist außerhalb des erlaubten AILIZA-Arbeitsbereichs nicht gestattet. Bitte beschränken Sie die Aktion auf den freigegebenen Workspace oder holen Sie eine explizite Freigabe ein.",
}


# Admin-sichtbare Diagnose-Hinweise je Fehlercode.
# Provider-NEUTRAL: kein "Groq:" / "OpenAI:"-Prefix hier.
# Provider-spezifische Hinweise kommen aus den Provider-Adaptern (safe_alternatives).
# Nur für /api/debug/* und interne Logs — niemals direkt zum Nutzer.
# Kein API-Key, kein Secret, keine PII.
ADMIN_HINTS: dict[str, str] = {
    "provider_forbidden": (
        "HTTP 403: Provider verweigert Zugriff auf das konfigurierte Modell. "
        "Häufige Ursachen: Modell nicht im Plan, Projekt-Einschränkung, Account-Sperre. "
        "Sanitisierter Provider-Hinweis steht in 'error_sanitized' des jeweiligen Providers."
    ),
    "no_api_key": (
        "API-Key fehlt oder nicht gesetzt. "
        "Prüfe die Render-Umgebungsvariablen für den betroffenen Provider."
    ),
    "invalid_api_key": (
        "API-Key vorhanden aber ungültig (HTTP 401). "
        "Key im Provider-Dashboard erneuern und in Render aktualisieren."
    ),
    "rate_limited": (
        "Rate-Limit oder Quota erschöpft (HTTP 429). "
        "Provider-Plan oder Billing im jeweiligen Dashboard prüfen. "
        "Sanitisierter Hinweis steht in 'error_sanitized' des jeweiligen Providers."
    ),
    "provider_unavailable": (
        "Provider nicht erreichbar (Netzwerkfehler oder HTTP 5xx). "
        "Temporärer Ausfall — Failover zum nächsten Provider wird versucht."
    ),
    "all_providers_failed": (
        "Alle konfigurierten Provider haben fehlgeschlagen. "
        "Einzelursachen je Provider stehen in 'provider_errors'. "
        "Prüfe /api/debug/provider-test für Live-Diagnose."
    ),
    "model_not_found": (
        "Das konfigurierte Modell existiert nicht (HTTP 404). "
        "Modell-Env-Variable des betroffenen Providers prüfen."
    ),
    "kill_switch_active": (
        "Kill-Switch aktiv — AILIZA_EXTERNAL_LLM_ENABLED=false oder "
        "Gate-10-Integritätsprüfung fehlgeschlagen. "
        "Prüfe /api/debug/llm-status für Details."
    ),
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
