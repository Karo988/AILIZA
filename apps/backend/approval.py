"""
AILIZA Approval-System
======================
Risikoabschätzung und Approval-Gate mit Rollenprüfung.

Risikolevel:
  low             — Auto-Approve (kein menschliches Eingreifen nötig)
  medium          — require_approval (jeder authorisierte Nutzer)
  high            — require_approval (erhöhte Rollen)
  safety_critical — require_approval (nur security_lead / operations_lead / owner)
  person_decision — require_approval (nur privacy / legal / owner) — DSGVO Art. 22

Rollenmatrix für Approval-Freigaben:
  safety_critical : security_lead, operations_lead, owner
  person_decision : privacy, legal, owner
  provider_avv    : admin, privacy, legal, owner
  memory_write    : admin, owner
  default/high    : admin, owner
  medium/low      : admin, manager, owner
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


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SAFETY_CRITICAL = "safety_critical"
    PERSON_DECISION = "person_decision"


# Rollen die für ein Approval-Gate freigeben dürfen
APPROVAL_ROLES: dict[str, list[str]] = {
    RiskLevel.SAFETY_CRITICAL.value: ["security_lead", "operations_lead", "owner"],
    RiskLevel.PERSON_DECISION.value: ["privacy", "legal", "owner"],
    "provider_avv":                  ["admin", "privacy", "legal", "owner"],
    "memory_write":                  ["admin", "owner"],
    RiskLevel.HIGH.value:            ["admin", "owner"],
    RiskLevel.MEDIUM.value:          ["admin", "manager", "owner"],
    RiskLevel.LOW.value:             ["admin", "manager", "user", "owner"],
}

# Timeout in Sekunden je Risikolevel (danach: Auto-Reject, nicht Auto-Approve)
APPROVAL_TIMEOUT_SECONDS: dict[str, int] = {
    RiskLevel.SAFETY_CRITICAL.value: 300,   # 5 Minuten
    RiskLevel.PERSON_DECISION.value: 600,   # 10 Minuten
    RiskLevel.HIGH.value:            1800,  # 30 Minuten
    RiskLevel.MEDIUM.value:          3600,  # 1 Stunde
    RiskLevel.LOW.value:             0,     # Auto (kein Timeout)
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
        return APPROVAL_ROLES.get(self.risk_level, APPROVAL_ROLES[RiskLevel.HIGH.value])

    def approval_timeout(self) -> int:
        return APPROVAL_TIMEOUT_SECONDS.get(self.risk_level, 1800)


def can_approve(risk_level: str, approver_role: str) -> bool:
    """Prueft ob eine Rolle einen Approval für das gegebene Risikolevel freigeben darf."""
    allowed = APPROVAL_ROLES.get(risk_level, APPROVAL_ROLES[RiskLevel.HIGH.value])
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
        return RiskResult(True, "URL host is missing", RiskLevel.HIGH.value, "fetch", "<no-url>")
    if host in TRUSTED_DOMAINS:
        return RiskResult(False, f"Trusted domain: {host}", RiskLevel.LOW.value, "fetch", "<url-host-only>")
    return RiskResult(True, f"Unknown domain: {host}", RiskLevel.MEDIUM.value, "fetch", "<url-host-only>")


def assess_search_risk(query: str) -> RiskResult:
    if _MASS_NOTIFY_PATTERNS.search(query):
        return RiskResult(
            True, "Mass notification detected — Safety-Critical gate required",
            RiskLevel.SAFETY_CRITICAL.value, "search", "<query-length-only>",
        )
    if _PERSON_DECISION_PATTERNS.search(query):
        return RiskResult(
            True, "Automated person decision detected — human approval required (DSGVO Art. 22)",
            RiskLevel.PERSON_DECISION.value, "search", "<query-length-only>",
        )
    if len(query) > COMPLEX_QUERY_THRESHOLD:
        return RiskResult(
            True, f"Complex query ({len(query)} characters)",
            RiskLevel.MEDIUM.value, "search", "<query-length-only>",
        )
    for pattern in RISKY_QUERY_PATTERNS:
        if pattern.search(query):
            return RiskResult(
                True, "Query contains potentially risky terms",
                RiskLevel.HIGH.value, "search", "<query-length-only>",
            )
    return RiskResult(False, "Query is low risk", RiskLevel.LOW.value, "search", "<query-length-only>")


def assess_risk(tool: str, params: dict[str, Any]) -> RiskResult:
    if tool == "fetch":
        return assess_fetch_risk(str(params.get("url", "")))
    if tool == "search":
        return assess_search_risk(str(params.get("query", "")))
    return RiskResult(True, f"Unknown tool: {tool}", RiskLevel.HIGH.value, tool, "<params-unknown>")
