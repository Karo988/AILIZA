"""
AILIZA Approval-System
======================
Risikoabschätzung (RiskResult) und die vorgesehene Rollenmatrix je
Risikolevel (APPROVAL_ROLES). Diese Matrix wird als required_approver_roles
in jeder Genehmigungsanfrage gespeichert (siehe database.create_approval_request).

⚠️ WICHTIG (seit PR 2, Vier-Augen-Prinzip): Der Eintrag "owner" in dieser
Matrix wird von der tatsaechlichen Freigabepruefung
(permissions.decide_approval / decide_approval_atomic) IMMER ignoriert.
Eine Person darf ihre EIGENE Genehmigung nicht selbst entscheiden -- die
einzige Ausnahme ist die separat streng geprüfte compliance_consent (B2:
Einwilligung zum Versand der eigenen, vorher geflaggten Nachricht, keine
Freigabe einer fremden Entscheidung). can_approve() unten ist eine reine,
von der eigentlichen Autorisierung UNABHAENGIGE Hilfsfunktion auf dieser
Rohmatrix (u.a. fuer Altlasten-Tests) -- sie wird von der produktiven
Freigabepruefung NICHT mehr aufgerufen und darf nicht dafuer verwendet
werden, "owner" als gueltigen Freigabepfad zu behandeln.

Risikolevel:
  low             — Auto-Approve (kein menschliches Eingreifen nötig)
  medium          — require_approval (jeder authorisierte Nutzer)
  high            — require_approval (erhöhte Rollen)
  safety_critical — require_approval (nur security_lead / operations_lead)
  person_decision — require_approval (nur privacy / legal) — DSGVO Art. 22

Rollenmatrix für Approval-Freigaben (roh, siehe Warnung oben zu "owner"):
  safety_critical : security_lead, operations_lead, (owner -- ignoriert)
  person_decision : privacy, legal, (owner -- ignoriert)
  provider_avv    : admin, privacy, legal, (owner -- ignoriert)
  memory_write    : admin, (owner -- ignoriert)
  default/high    : admin, (owner -- ignoriert)
  medium/low      : admin, manager, (owner -- ignoriert)
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlparse


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO = "auto"
    # PR 2 Nachbesserung: Endzustand fuer eine bereits genutzte
    # compliance_consent -- eine Einwilligung darf nur EINMAL zum Versand
    # der zugehoerigen Anfrage fuehren (siehe database.consume_compliance_consent).
    CONSUMED = "consumed"


class ApprovalRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SAFETY_CRITICAL = "safety_critical"
    PERSON_DECISION = "person_decision"


# Rollen die für ein Approval-Gate freigeben dürfen
APPROVAL_ROLES: dict[str, list[str]] = {
    ApprovalRiskLevel.SAFETY_CRITICAL.value: ["security_lead", "operations_lead", "owner"],
    ApprovalRiskLevel.PERSON_DECISION.value: ["privacy", "legal", "owner"],
    "provider_avv":                  ["admin", "privacy", "legal", "owner"],
    "memory_write":                  ["admin", "owner"],
    ApprovalRiskLevel.HIGH.value:            ["admin", "owner"],
    ApprovalRiskLevel.MEDIUM.value:          ["admin", "manager", "owner"],
    ApprovalRiskLevel.LOW.value:             ["admin", "manager", "user", "owner"],
}

# Timeout in Sekunden je Risikolevel (danach: Auto-Reject, nicht Auto-Approve)
APPROVAL_TIMEOUT_SECONDS: dict[str, int] = {
    ApprovalRiskLevel.SAFETY_CRITICAL.value: 300,   # 5 Minuten
    ApprovalRiskLevel.PERSON_DECISION.value: 600,   # 10 Minuten
    ApprovalRiskLevel.HIGH.value:            1800,  # 30 Minuten
    ApprovalRiskLevel.MEDIUM.value:          3600,  # 1 Stunde
    ApprovalRiskLevel.LOW.value:             0,     # Auto (kein Timeout)
}


@dataclass(frozen=True)
class RiskResult:
    risky: bool
    reason: str
    risk_level: str
    tool: str
    input_summary: str      # NIEMALS im Audit loggen — nur intern für Risikoentscheid

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def required_approver_roles(self) -> list[str]:
        return APPROVAL_ROLES.get(self.risk_level, APPROVAL_ROLES[ApprovalRiskLevel.HIGH.value])

    def approval_timeout(self) -> int:
        return APPROVAL_TIMEOUT_SECONDS.get(self.risk_level, 1800)


def can_approve(risk_level: str, approver_role: str) -> bool:
    """LEGACY/Hilfsfunktion auf der rohen Rollenmatrix -- prueft NUR, ob eine
    Rollen-BEZEICHNUNG in APPROVAL_ROLES fuer das Risikolevel vorkommt.
    KEINE tatsaechliche Autorisierungspruefung und wird von der produktiven
    Freigabepruefung (permissions.decide_approval) NICHT verwendet.
    Insbesondere behandelt diese Funktion "owner" weiterhin als Treffer,
    obwohl decide_approval() eine Selbstfreigabe (ausser der streng
    geprüften compliance_consent-Ausnahme) grundsaetzlich verweigert -- das
    ist bewusst so belassen, um bestehende Altlasten-Tests dieser reinen
    Matrix-Hilfsfunktion nicht zu veraendern."""
    allowed = APPROVAL_ROLES.get(risk_level, APPROVAL_ROLES[ApprovalRiskLevel.HIGH.value])
    return approver_role in allowed


TRUSTED_DOMAINS: set[str] = {
    "wikipedia.org",
    "www.wikipedia.org",
    "github.com",
    "raw.githubusercontent.com",
    "docs.python.org",
    "pypi.org",
    "stackoverflow.com",
    "arxiv.org",
    "news.ycombinator.com",
}

COMPLEX_QUERY_THRESHOLD = 120

RISKY_QUERY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(hack|exploit|vulnerability|CVE-\d+|bypass|injection)\b", re.I),
    re.compile(r"\b(credit.?card|ssn|social.?security|bank.?account)\b", re.I),
    re.compile(r"\b(darkweb|dark.?net|tor.?browser)\b", re.I),
]

# Crowd-Control / Massennachricht — Safety-Critical
_MASS_NOTIFY_PATTERNS = re.compile(
    r"\b(alle\s+Besucher|alle\s+Teilnehmer|alle\s+Gäste|Massennachricht"
    r"|all\s+(?:visitors|attendees|guests)|mass\s+(?:notify|message|push)"
    r"|broadcast\s+to\s+all|push\s+notification\s+(?:to\s+all|\d{4,}))\b",
    re.I,
)

# Personenentscheidungs-Kontext
_PERSON_DECISION_PATTERNS = re.compile(
    r"\b(Personalentscheidung|Mitarbeiterbewertung|Kündigung|Personalplanung"
    r"|automated\s+(?:decision|evaluation)|staff\s+(?:decision|evaluation)"
    r"|employee\s+termination|performance\s+decision)\b",
    re.I,
)


def assess_fetch_risk(url: str) -> RiskResult:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return RiskResult(True, "URL host is missing", ApprovalRiskLevel.HIGH.value, "fetch", "<no-url>")
    if host in TRUSTED_DOMAINS:
        return RiskResult(False, f"Trusted domain: {host}", ApprovalRiskLevel.LOW.value, "fetch", "<url-host-only>")
    return RiskResult(True, f"Unknown domain: {host}", ApprovalRiskLevel.MEDIUM.value, "fetch", "<url-host-only>")


def assess_search_risk(query: str) -> RiskResult:
    if _MASS_NOTIFY_PATTERNS.search(query):
        return RiskResult(
            True, "Mass notification detected — Safety-Critical gate required",
            ApprovalRiskLevel.SAFETY_CRITICAL.value, "search", "<query-length-only>",
        )
    if _PERSON_DECISION_PATTERNS.search(query):
        return RiskResult(
            True, "Automated person decision detected — human approval required (DSGVO Art. 22)",
            ApprovalRiskLevel.PERSON_DECISION.value, "search", "<query-length-only>",
        )
    if len(query) > COMPLEX_QUERY_THRESHOLD:
        return RiskResult(
            True, f"Complex query ({len(query)} characters)",
            ApprovalRiskLevel.MEDIUM.value, "search", "<query-length-only>",
        )
    for pattern in RISKY_QUERY_PATTERNS:
        if pattern.search(query):
            return RiskResult(
                True, "Query contains potentially risky terms",
                ApprovalRiskLevel.HIGH.value, "search", "<query-length-only>",
            )
    return RiskResult(False, "Query is low risk", ApprovalRiskLevel.LOW.value, "search", "<query-length-only>")


def assess_tool_risk(tool: str, params: dict[str, Any]) -> RiskResult:
    if tool == "fetch":
        return assess_fetch_risk(str(params.get("url", "")))
    if tool == "search":
        return assess_search_risk(str(params.get("query", "")))
    return RiskResult(True, f"Unknown tool: {tool}", ApprovalRiskLevel.HIGH.value, tool, "<params-unknown>")


# ── Approval Preview (kein Execute) ──────────────────────────────────────────

@dataclass
class ApprovalPreview:
    """
    Vorschau einer geplanten Aktion OHNE Ausführung.
    Enthält alle Informationen die ein Mensch zur Freigabe braucht.
    KEINE Secrets, KEIN vollständiger Input, KEIN Stack-Trace.
    """
    action: str                    # Was soll passieren
    target_system: str             # Wo soll es passieren
    data_class: str                # Welche Datenklasse ist betroffen
    risk_level: str                # Risikoeinschätzung
    reason: str                    # Warum braucht es eine Freigabe
    safe_alternative: str          # Was passiert bei Ablehnung
    required_role: str             # Wer darf freigeben
    capability_id: str | None      # Welche Capability ist betroffen
    provider_id: str | None        # Welcher Provider wird genutzt
    approval_timeout_seconds: int  # Wie lange ist die Freigabe gültig
    preview_only: bool = True      # Sicherheitsfeld: darf NICHT ausgeführt werden


def create_approval_preview(
    action: str,
    tool: str,
    params: dict[str, Any],
    data_class: str = "unknown",
    capability_id: str | None = None,
    provider_id: str | None = None,
    safe_alternative: str = "Aktion abbrechen oder lokal verarbeiten",
) -> ApprovalPreview:
    """
    Erstellt eine Approval-Vorschau ohne die Aktion auszuführen.
    Darf nur an den Nutzer/Admin gezeigt werden — nie ausführen.
    """
    risk = assess_tool_risk(tool, params)
    required_role = APPROVAL_ROLES.get(risk.risk_level, APPROVAL_ROLES[ApprovalRiskLevel.HIGH.value])
    role_str = ", ".join(required_role)

    target = "extern"
    if tool == "fetch":
        host = ""
        try:
            from urllib.parse import urlparse
            host = urlparse(str(params.get("url", ""))).hostname or "unbekannt"
        except Exception:
            host = "unbekannt"
        target = f"URL-Abruf: {host}"
    elif tool == "search":
        target = "Web-Suche (Tavily)"
    elif tool == "llm_call":
        target = f"LLM-Provider: {provider_id or 'unbekannt'}"

    return ApprovalPreview(
        action=action,
        target_system=target,
        data_class=data_class,
        risk_level=risk.risk_level,
        reason=risk.reason,
        safe_alternative=safe_alternative,
        required_role=role_str,
        capability_id=capability_id,
        provider_id=provider_id,
        approval_timeout_seconds=risk.approval_timeout(),
        preview_only=True,
    )
