from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse

class Decision(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"

@dataclass
class PolicyResult:
    decision: Decision
    reason: str
    tool: str
    input_summary: str
    metadata: dict = field(default_factory=dict)

    @property
    def allowed(self):
        return self.decision == Decision.ALLOWED

ALLOWED_SCHEMAS = {"http", "https"}
BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254"}
BLOCKED_HOST_PATTERNS = [
    re.compile(r"^10\.\d+\.\d+\.\d+$"),
    re.compile(r"^172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+$"),
    re.compile(r"^192\.168\.\d+\.\d+$"),
    re.compile(r"\.internal$"),
    re.compile(r"\.local$"),
]
BLOCKED_QUERY_PATTERNS = [
    re.compile(r"\b(password|passwd|secret|api[_\s]?key|private[_\s]?key)\b", re.I),
]
MAX_QUERY_LENGTH = 500
MAX_URL_LENGTH = 2048


def check_fetch(url: str) -> PolicyResult:
    if len(url) > MAX_URL_LENGTH:
        return PolicyResult(Decision.BLOCKED, "URL zu lang", "fetch", url[:80])
    try:
        parsed = urlparse(url)
    except Exception:
        return PolicyResult(Decision.BLOCKED, "URL ungueltig", "fetch", url[:80])
    if parsed.scheme.lower() not in ALLOWED_SCHEMAS:
        return PolicyResult(Decision.BLOCKED, "Schema nicht erlaubt", "fetch", url[:80])
    host = parsed.hostname or ""
    if host.lower() in BLOCKED_HOSTS:
        return PolicyResult(Decision.BLOCKED, "Host gesperrt", "fetch", url[:80])
    for p in BLOCKED_HOST_PATTERNS:
        if p.search(host):
            return PolicyResult(Decision.BLOCKED, "Privater IP-Bereich", "fetch", url[:80])
    return PolicyResult(Decision.ALLOWED, "OK", "fetch", url[:80], {"url": url})


def check_search(query: str) -> PolicyResult:
    if len(query) > MAX_QUERY_LENGTH:
        return PolicyResult(Decision.BLOCKED, "Query zu lang", "search", query[:80])
    for p in BLOCKED_QUERY_PATTERNS:
        if p.search(query):
            return PolicyResult(Decision.BLOCKED, "Sensible Begriffe", "search", query[:80])
    return PolicyResult(Decision.ALLOWED, "OK", "search", query[:80], {"query": query})


def check_tool_call(tool: str, params: dict) -> PolicyResult:
    if tool == "fetch":
        return check_fetch(params.get("url", ""))
    elif tool == "search":
        return check_search(params.get("query", ""))
    return PolicyResult(Decision.BLOCKED, f"Unbekanntes Tool: {tool}", tool, str(params)[:80])


# ── Erweitertes Policy-Gateway (governance-basiert) ─────────────────────────

try:
    from .governance.data_governance import DataClass, DataTarget
    from .governance.data_matrix import PolicyDecision, check_data_target
except ImportError:  # pragma: no cover
    from governance.data_governance import DataClass, DataTarget
    from governance.data_matrix import PolicyDecision, check_data_target


@dataclass
class PolicyContext:
    tenant_id: str = "default"
    user_id: str | None = None
    purpose: str = ""
    target: "DataTarget" = None  # type: ignore
    data_classes: list = field(default_factory=list)
    highest_risk_class: "DataClass" = None  # type: ignore
    provider_profile_id: str | None = None
    redaction_applied: bool = False
    approval_id: int | None = None
    approval_given: bool = False
    policy_version: str = "1.0"
    tool: str | None = None
    parameters: dict = field(default_factory=dict)


@dataclass
class PolicyResultV2:
    decision: "PolicyDecision"
    reason: str
    context_summary: dict = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision in {PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE}


_REASONS = {
    PolicyDecision.ALLOW: "Verarbeitung zulaessig.",
    PolicyDecision.ALLOW_WITH_NOTICE: "Verarbeitung zulaessig (mit Hinweis/Protokollierung).",
    PolicyDecision.REDACT_REQUIRED: "Anonymisierung erforderlich, bevor extern verarbeitet wird.",
    PolicyDecision.APPROVAL_REQUIRED: "Freigabe durch einen Administrator erforderlich.",
    PolicyDecision.BLOCK: "Verarbeitung dieser Datenklasse am gewuenschten Ziel ist untersagt.",
}


def evaluate_policy(context: PolicyContext) -> PolicyResultV2:
    """Governance-basierte Policy-Bewertung. Fail-closed bei Unklarheit."""
    try:
        if context.target is None:
            return PolicyResultV2(PolicyDecision.BLOCK, "Kein Datenziel angegeben.")
        provider_active = context.provider_profile_id is not None
        decision = check_data_target(
            data_classes=list(context.data_classes),
            target=context.target,
            redaction_applied=context.redaction_applied,
            approval_given=context.approval_given,
            provider_profile_active=provider_active,
        )
        return PolicyResultV2(
            decision=decision,
            reason=_REASONS.get(decision, "Unklar — blockiert."),
            context_summary={
                "tenant_id": context.tenant_id,
                "target": context.target.value if context.target else None,
                "data_classes": [c.value for c in context.data_classes],
                "redaction_applied": context.redaction_applied,
                "approval_given": context.approval_given,
                "provider_profile_active": provider_active,
                "policy_version": context.policy_version,
            },
        )
    except Exception:
        return PolicyResultV2(PolicyDecision.BLOCK, "Fehler bei der Policy-Bewertung — fail-closed.")