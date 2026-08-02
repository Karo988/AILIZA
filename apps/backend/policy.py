from __future__ import annotations
import hashlib
import json
import re
from dataclasses import dataclass, field, replace
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


# ── RiskAssessment (deterministische Vorstufe vor evaluate_policy) ─────────
#
# HANDOFF (bewusst NICHT Teil dieses Pakets, siehe Auftrag "Phase-0-Entscheidung"):
# - verbindliche H1-H3-Schwellenwerte/-Matrix
# - Zuordnung der konzeptionellen DSGVO-Symbole (secret/forbidden) zum
#   tatsaechlichen DataClass-Modell (PUBLIC..SECURITY_SENSITIVE)
# - responsibility_handoff, local_only (existieren im Code nicht)
# - Owner-Override-AUSFUEHRUNG (dieses Paket bereitet nur additive
#   Metadaten-/Audit-Felder vor, siehe PolicyResultV2.override_* unten)
# - konkrete Ersatzpruefung bei H2/H3
#
# assess_risk() liefert deshalb in diesem Paket IMMER PolicyRiskLevel.UNKNOWN --
# mit einem Reason Code, der zwischen "Kontext unvollstaendig" und "Kontext
# vollstaendig, aber Matrix noch nicht bestaetigt" unterscheidet. Das trennt
# Signalerhebung (hier implementiert) von Risikostufenzuordnung (bewusst
# nicht implementiert) und vermeidet erratene H1-H3-Werte.

class PolicyRiskLevel(str, Enum):
    H1 = "H1"
    H2 = "H2"
    H3 = "H3"
    UNKNOWN = "unknown"


_ASSESSMENT_VERSION = "1.0"

# Minimal fuer eine Signalerhebung erforderliche Felder. Fehlen sie, ist der
# Kontext fuer eine Risikoanalyse unvollstaendig (RISK_CONTEXT_INCOMPLETE),
# unabhaengig von der (in diesem Paket ohnehin nicht getroffenen) H1-H3-Zuordnung.
_REQUIRED_SIGNAL_KEYS = ("action", "data_class")


@dataclass(frozen=True)
class RiskAssessment:
    """Bewertet ausschliesslich Risiko -- trifft NIE ALLOW/BLOCK/
    responsibility_handoff. Deterministisch, keine Netzwerk-/LLM-/Provider-
    Aufrufe, keine Rohinhalte oder PII in reason_codes/signals/fingerprint."""
    risk_level: PolicyRiskLevel
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    signals: dict[str, Any] = field(default_factory=dict)
    context_fingerprint: str = ""
    assessment_version: str = _ASSESSMENT_VERSION


def compute_context_fingerprint(context: "PolicyContext") -> str:
    """Stabiler SHA-256-Fingerprint des kanonischen Entscheidungszustands.

    Enthaelt bewusst KEINE Rohinhalte, Klartext-Namen oder E-Mailadressen --
    nur Aktion, Ressourcen-/Empfaenger-KENNUNG (falls als ID vorhanden),
    Datenklasse, Scope, Quellenversion, policy_version und
    assessment_version. Gleicher Zustand -> gleicher Fingerprint; eine
    Aenderung an einem dieser Felder -> anderer Fingerprint."""
    parameters = context.parameters or {}
    canonical = {
        "action": context.tool,
        "resource_id": parameters.get("resource_id"),
        "recipient_id": parameters.get("recipient_id"),
        "data_class": context.highest_risk_class.value if context.highest_risk_class else None,
        "scope": parameters.get("scope"),
        "source_version": parameters.get("source_version"),
        "policy_version": context.policy_version,
        "assessment_version": _ASSESSMENT_VERSION,
    }
    raw = json.dumps(canonical, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assess_risk(context: "PolicyContext") -> RiskAssessment:
    """Deterministische, seiteneffektfreie Risikosignal-Erhebung.

    Leitet Signale ausschliesslich aus dem uebergebenen, serverseitig
    aufgebauten PolicyContext ab -- keine Selbstauskuenfte, keine erratenen
    Werte. Liefert in diesem Ausbaupaket immer PolicyRiskLevel.UNKNOWN (siehe
    HANDOFF oben); der Reason Code zeigt, ob der Kontext dafuer vollstaendig
    war oder nicht."""
    fingerprint = compute_context_fingerprint(context)
    parameters = context.parameters or {}

    # PII-Schutz: signals ist eine sichtbare, potenziell geloggte/auditierte
    # Struktur -- deshalb NUR abgeleitete/kanonische Merkmale, NIE Rohwerte
    # aus context.parameters (koennten Namen, E-Mailadressen, Freitext o.ae.
    # enthalten). Roh-resource_id/recipient_id fliessen ausschliesslich in
    # compute_context_fingerprint() als SHA-256-Vorbild ein (Ausgabe ist ein
    # Hash, kein Klartext) -- nicht hierher.
    signals: dict[str, Any] = {
        "action": context.tool,
        "data_class": context.highest_risk_class.value if context.highest_risk_class else None,
        "target": context.target.value if context.target else None,
        "has_resource_id": bool(parameters.get("resource_id")),
        "has_recipient_id": bool(parameters.get("recipient_id")),
        "scope": parameters.get("scope"),
        "is_write_action": bool(parameters.get("write_effect")),
        "reversibility": parameters.get("reversibility"),
        "source_version": parameters.get("source_version"),
        "policy_version": context.policy_version,
        "parameter_count": len(parameters),
    }

    missing = [key for key in _REQUIRED_SIGNAL_KEYS if signals.get(key) is None]
    if missing:
        reason_codes = ("RISK_CONTEXT_INCOMPLETE",) + tuple(
            f"MISSING_SIGNAL_{key.upper()}" for key in missing
        )
        return RiskAssessment(
            risk_level=PolicyRiskLevel.UNKNOWN,
            reason_codes=reason_codes,
            signals=signals,
            context_fingerprint=fingerprint,
            assessment_version=_ASSESSMENT_VERSION,
        )

    return RiskAssessment(
        risk_level=PolicyRiskLevel.UNKNOWN,
        reason_codes=("RISK_MATRIX_NOT_CONFIRMED",),
        signals=signals,
        context_fingerprint=fingerprint,
        assessment_version=_ASSESSMENT_VERSION,
    )


def _ensure_risk_assessment(context: "PolicyContext") -> "PolicyContext":
    """Garantiert einen RiskAssessment-Versuch pro evaluate_policy-Aufruf.

    Bindet ein neues/aktualisiertes RiskAssessment an eine NEUE
    PolicyContext-Instanz (dataclasses.replace) -- kein stilles Mutieren
    eines bereits verwendeten Context-Objekts. Ein vorhandenes, zum
    aktuellen Fingerprint passendes RiskAssessment wird wiederverwendet."""
    fingerprint = compute_context_fingerprint(context)
    existing = context.risk_assessment
    if existing is not None and existing.context_fingerprint == fingerprint:
        return context
    try:
        assessment = assess_risk(context)
    except Exception:
        # Fehler der Risikoanalyse -> UNKNOWN, KEINE neue absolute Sperre
        # (die bestehende fail-closed-Behandlung echter Policy-Exceptions
        # bleibt unveraendert im aeusseren try/except von evaluate_policy).
        assessment = RiskAssessment(
            risk_level=PolicyRiskLevel.UNKNOWN,
            reason_codes=("RISK_ASSESSMENT_ERROR",),
            signals={},
            context_fingerprint=fingerprint,
            assessment_version=_ASSESSMENT_VERSION,
        )
    return replace(context, risk_assessment=assessment)


def _risk_result_fields(ra: "RiskAssessment | None") -> dict[str, Any]:
    if ra is None:
        return {}
    return {
        "reason_codes": list(ra.reason_codes),
        "risk_level": ra.risk_level.value,
        "context_fingerprint": ra.context_fingerprint,
        "assessment_version": ra.assessment_version,
    }


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
    risk_assessment: "RiskAssessment | None" = None


@dataclass
class PolicyResultV2:
    decision: "PolicyDecision"
    reason: str
    context_summary: dict = field(default_factory=dict)
    # ── Additive RiskAssessment-/Override-Felder (siehe HANDOFF oben) ──────
    # Bestehende Reason-Semantik (decision/reason/context_summary) bleibt
    # unveraendert; diese Felder ergaenzen, ersetzen nichts.
    reason_codes: list = field(default_factory=list)
    risk_level: str = PolicyRiskLevel.UNKNOWN.value
    context_fingerprint: str = ""
    assessment_version: str = _ASSESSMENT_VERSION
    # Owner-Override: in diesem Paket nur Metadaten-/Audit-Grundlage, KEINE
    # Ausfuehrung. evaluate_policy setzt diese Felder aktuell nicht aktiv --
    # sie stehen bereit, sobald der bestehende Freigabepfad dafuer geprueft ist.
    override_allowed: bool = False
    override_mode: str | None = None
    required_acknowledgements: list = field(default_factory=list)
    available_user_actions: list = field(default_factory=list)
    recovery_path: str | None = None

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
    """Governance-basierte Policy-Bewertung. Fail-closed bei Unklarheit.

    Garantiert fuer JEDEN Aufruf (auch bei fehlendem target) einen
    RiskAssessment-Versuch (_ensure_risk_assessment) -- erfasst damit sowohl
    den erreichbaren capabilities/registry.py-Pfad als auch core_api.py und
    etwaige weitere Aufrufer, ohne dass diese selbst etwas aendern muessen.
    RiskAssessment bewertet ausschliesslich Risiko; die Policy-Entscheidung
    selbst (ALLOW/BLOCK/...) bleibt unveraendert bei check_data_target."""
    try:
        context = _ensure_risk_assessment(context)
        ra = context.risk_assessment

        if context.target is None:
            return PolicyResultV2(
                PolicyDecision.BLOCK, "Kein Datenziel angegeben.",
                **_risk_result_fields(ra),
            )
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
            **_risk_result_fields(ra),
        )
    except Exception:
        return PolicyResultV2(PolicyDecision.BLOCK, "Fehler bei der Policy-Bewertung — fail-closed.")