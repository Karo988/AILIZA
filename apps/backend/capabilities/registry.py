"""
Capability Registry fuer AILIZA
================================
Jede Faehigkeit des Agenten ist hier registriert mit:
- erlaubten Datenklassen
- Zielsystem (DataTarget)
- Freigabepflicht
- Risikostufe
- DSGVO-Zweckbindung

Vor jeder Skill-/Tool-/Memory-Aktion MUSS check_capability() aufgerufen werden.
Fail-closed: Unbekannte Capabilities werden blockiert.

DSGVO-Bezug: Art. 5 (Zweckbindung), Art. 25 (Privacy by Design).
EU AI Act: Art. 9 (Risikomanagement), Art. 13 (Transparenz).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    from ..governance.data_governance import DataClass, DataTarget, RISK_ORDER
    from ..governance.data_matrix import PolicyDecision
    from ..policy import PolicyContext, evaluate_policy
except ImportError:
    from governance.data_governance import DataClass, DataTarget, RISK_ORDER
    from governance.data_matrix import PolicyDecision
    from policy import PolicyContext, evaluate_policy


def _highest_class(data_classes: list[DataClass]) -> DataClass:
    """Gibt die strengste Datenklasse zurueck (RISK_ORDER, hoeher = strenger)."""
    if not data_classes:
        return DataClass.PUBLIC
    return max(data_classes, key=lambda c: RISK_ORDER.index(c))


class RiskLevel(str, Enum):
    LOW = "low"           # Kein externer Call, kein PII, lokal
    MEDIUM = "medium"     # Externer Call ODER PII, mit Redaktion
    HIGH = "high"         # Externer Call + PII, Freigabe empfohlen
    CRITICAL = "critical" # Schreiben, Senden, Memory mit sensiblen Daten


@dataclass
class Capability:
    capability_id: str
    name: str
    description: str
    target: DataTarget
    allowed_data_classes: list[DataClass]
    risk_level: RiskLevel
    requires_approval: bool
    external_call: bool
    gdpr_purpose: str          # Zweckbindung nach Art. 5 DSGVO
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


# ── Statische Capability-Definitionen ────────────────────────────────────────
# Jede neue Faehigkeit muss hier eingetragen werden, bevor sie genutzt werden darf.

_CAPABILITIES: dict[str, Capability] = {
    "web_search": Capability(
        capability_id="web_search",
        name="Web-Suche",
        description="Suche im Internet via Tavily. Kein PII im Query.",
        target=DataTarget.EXTERNAL_LLM,
        allowed_data_classes=[DataClass.PUBLIC, DataClass.INTERNAL],
        risk_level=RiskLevel.MEDIUM,
        requires_approval=False,
        external_call=True,
        gdpr_purpose="Informationsbeschaffung fuer Nutzeranfragen",
        tags=["search", "tavily", "external"],
    ),
    "web_fetch": Capability(
        capability_id="web_fetch",
        name="URL-Abruf",
        description="Laedt eine Webseite. Nur http/https, keine privaten IPs.",
        target=DataTarget.EXTERNAL_LLM,
        allowed_data_classes=[DataClass.PUBLIC, DataClass.INTERNAL],
        risk_level=RiskLevel.MEDIUM,
        requires_approval=False,
        external_call=True,
        gdpr_purpose="Inhaltsbeschaffung fuer Nutzeranfragen",
        tags=["fetch", "http", "external"],
    ),
    "llm_call": Capability(
        capability_id="llm_call",
        name="LLM-Aufruf",
        description="Sendet (redigierten) Prompt an externen Provider (Groq/Anthropic).",
        target=DataTarget.EXTERNAL_LLM,
        allowed_data_classes=[
            DataClass.PUBLIC, DataClass.INTERNAL, DataClass.CONFIDENTIAL,
            DataClass.PERSONAL_DATA,
        ],
        risk_level=RiskLevel.HIGH,
        requires_approval=False,
        external_call=True,
        gdpr_purpose="KI-gestuetzte Verarbeitung von Nutzeranfragen",
        tags=["llm", "groq", "anthropic", "external"],
    ),
    "memory_store": Capability(
        capability_id="memory_store",
        name="Langzeitgedaechtnis speichern",
        description="Speichert abstrahierte Lerninhalte in reflection_facts. Nur opt-in.",
        target=DataTarget.MEMORY,
        allowed_data_classes=[
            DataClass.PUBLIC, DataClass.INTERNAL,
        ],
        risk_level=RiskLevel.HIGH,
        requires_approval=True,
        external_call=False,
        gdpr_purpose="Verbesserung der Agentenqualitaet mit Nutzereinwilligung",
        tags=["memory", "reflection", "opt-in"],
    ),
    "memory_read": Capability(
        capability_id="memory_read",
        name="Langzeitgedaechtnis lesen",
        description="Liest gespeicherte Facts aus reflection_facts.",
        target=DataTarget.MEMORY,
        allowed_data_classes=[
            DataClass.PUBLIC, DataClass.INTERNAL, DataClass.CONFIDENTIAL,
        ],
        risk_level=RiskLevel.MEDIUM,
        requires_approval=False,
        external_call=False,
        gdpr_purpose="Kontextabruf fuer verbesserte Antwortqualitaet",
        tags=["memory", "reflection", "read"],
    ),
    "skill_propose": Capability(
        capability_id="skill_propose",
        name="Skill-Vorschlag erstellen",
        description="Agent schlaegt neuen Skill vor (abstrahiert, kein PII). Muss von Admin genehmigt werden.",
        target=DataTarget.MEMORY,
        allowed_data_classes=[DataClass.PUBLIC, DataClass.INTERNAL],
        risk_level=RiskLevel.HIGH,
        requires_approval=True,
        external_call=False,
        gdpr_purpose="Selbstoptimierung des Agenten mit menschlicher Kontrolle",
        tags=["skill", "learning", "approval-required"],
    ),
    "skill_execute": Capability(
        capability_id="skill_execute",
        name="Skill ausfuehren",
        description="Fuehrt einen vom Admin freigegebenen Skill aus.",
        target=DataTarget.RAM,
        allowed_data_classes=[
            DataClass.PUBLIC, DataClass.INTERNAL, DataClass.CONFIDENTIAL,
        ],
        risk_level=RiskLevel.MEDIUM,
        requires_approval=False,
        external_call=False,
        gdpr_purpose="Ausfuehren freigegebener Agentenaufgaben",
        tags=["skill", "execute"],
    ),
    "document_scan": Capability(
        capability_id="document_scan",
        name="Dokument scannen",
        description="Klassifiziert hochgeladene Dokumente vor der Verarbeitung.",
        target=DataTarget.RAM,
        allowed_data_classes=[
            DataClass.PUBLIC, DataClass.INTERNAL, DataClass.CONFIDENTIAL,
            DataClass.PERSONAL_DATA, DataClass.FINANCIAL, DataClass.HR, DataClass.LEGAL,
        ],
        risk_level=RiskLevel.MEDIUM,
        requires_approval=False,
        external_call=False,
        gdpr_purpose="Datenschutz-Vorpruefung vor Dokumentenverarbeitung",
        tags=["document", "classification", "local"],
    ),
    "audit_write": Capability(
        capability_id="audit_write",
        name="Audit-Log schreiben",
        description="Schreibt Ereignis in Audit-Log (kein Inhalt, kein PII).",
        target=DataTarget.AUDIT,
        allowed_data_classes=[DataClass.PUBLIC, DataClass.INTERNAL],
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        external_call=False,
        gdpr_purpose="Nachweisfuehrung und Compliance-Dokumentation",
        tags=["audit", "logging", "internal"],
    ),
    "messenger_receive": Capability(
        capability_id="messenger_receive",
        name="Messenger-Nachricht empfangen",
        description="Empfaengt Nachricht ueber Telegram. Nur nach Nutzer-Opt-in. Kein Inhalt in Logs.",
        target=DataTarget.RAM,
        allowed_data_classes=[DataClass.PUBLIC, DataClass.INTERNAL],
        risk_level=RiskLevel.MEDIUM,
        requires_approval=False,
        external_call=False,
        gdpr_purpose="Entgegennahme von Nutzeranfragen ueber Messenger-Kanal (nur mit Einwilligung)",
        tags=["messenger", "telegram", "receive"],
    ),
    "message_process": Capability(
        capability_id="message_process",
        name="Nachricht klassifizieren und redigieren",
        description="Klassifiziert Nutzerinput, blockiert sensible Kategorien, redigiert PII. Lokal, kein externer Call.",
        target=DataTarget.RAM,
        allowed_data_classes=[
            DataClass.PUBLIC, DataClass.INTERNAL, DataClass.CONFIDENTIAL,
            DataClass.PERSONAL_DATA,
        ],
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        external_call=False,
        gdpr_purpose="Datenschutz-Vorpruefung und Redaktion vor LLM-Verarbeitung",
        tags=["messenger", "classify", "redact", "local"],
    ),
    "messenger_send": Capability(
        capability_id="messenger_send",
        name="Messenger-Antwort senden",
        description="Sendet Antwort ueber Telegram/Slack/Discord an den Nutzer. Nur nach Opt-in und LLM-Verarbeitung.",
        target=DataTarget.EXTERNAL_LLM,
        allowed_data_classes=[DataClass.PUBLIC, DataClass.INTERNAL],
        risk_level=RiskLevel.CRITICAL,
        requires_approval=True,
        external_call=True,
        enabled=True,
        gdpr_purpose="Antwortlieferung ueber Messenger-Kanal (nur mit Einwilligung, Art. 6 Abs. 1 lit. a DSGVO)",
        tags=["messenger", "telegram", "slack", "send", "external"],
    ),
}


# ── Check-Funktion ─────────────────────────────────────────────────────────────
@dataclass
class CapabilityCheckResult:
    capability_id: str
    allowed: bool
    decision: PolicyDecision
    reason: str
    requires_approval: bool
    risk_level: str
    capability_enabled: bool
    context_summary: dict[str, Any] = field(default_factory=dict)


def check_capability(
    capability_id: str,
    data_classes: list[DataClass],
    tenant_id: str = "default",
    user_id: str | None = None,
    redaction_applied: bool = False,
    approval_given: bool = False,
    provider_profile_id: str | None = None,
) -> CapabilityCheckResult:
    """
    Prueft ob eine Capability fuer gegebene Datenklassen ausgefuehrt werden darf.
    Fail-closed: Unbekannte oder deaktivierte Capabilities → BLOCK.
    """
    cap = _CAPABILITIES.get(capability_id)

    if cap is None:
        return CapabilityCheckResult(
            capability_id=capability_id,
            allowed=False,
            decision=PolicyDecision.BLOCK,
            reason=f"Unbekannte Capability '{capability_id}' — nicht registriert.",
            requires_approval=True,
            risk_level=RiskLevel.CRITICAL.value,
            capability_enabled=False,
        )

    if not cap.enabled:
        return CapabilityCheckResult(
            capability_id=capability_id,
            allowed=False,
            decision=PolicyDecision.BLOCK,
            reason=f"Capability '{capability_id}' ist deaktiviert.",
            requires_approval=True,
            risk_level=cap.risk_level.value,
            capability_enabled=False,
        )

    # Strengste Datenklasse bestimmen — Mischfaelle (PUBLIC+CREDENTIALS) → CREDENTIALS
    highest = _highest_class(data_classes)

    # Datenklassen gegen erlaubte Liste pruefen
    forbidden = [dc for dc in data_classes if dc not in cap.allowed_data_classes]
    if forbidden:
        forbidden_names = [dc.value for dc in forbidden]
        return CapabilityCheckResult(
            capability_id=capability_id,
            allowed=False,
            decision=PolicyDecision.BLOCK,
            reason=f"Datenklassen nicht erlaubt fuer '{capability_id}': {', '.join(forbidden_names)}",
            requires_approval=True,
            risk_level=cap.risk_level.value,
            capability_enabled=True,
            context_summary={"forbidden_classes": forbidden_names},
        )

    # Policy Engine konsultieren — mit strengster Klasse als Leitklasse
    ctx = PolicyContext(
        tenant_id=tenant_id,
        user_id=user_id,
        purpose=cap.gdpr_purpose,
        target=cap.target,
        data_classes=data_classes,
        highest_risk_class=highest,
        redaction_applied=redaction_applied,
        approval_given=approval_given or (not cap.requires_approval),
        provider_profile_id=provider_profile_id,
    )
    result = evaluate_policy(ctx)

    # Freigabepflicht der Capability selbst berücksichtigen
    final_decision = result.decision
    if cap.requires_approval and not approval_given:
        if final_decision in {PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE}:
            final_decision = PolicyDecision.APPROVAL_REQUIRED

    allowed = final_decision in {PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE}

    return CapabilityCheckResult(
        capability_id=capability_id,
        allowed=allowed,
        decision=final_decision,
        reason=result.reason,
        requires_approval=cap.requires_approval,
        risk_level=cap.risk_level.value,
        capability_enabled=True,
        context_summary={
            **result.context_summary,
            "gdpr_purpose": cap.gdpr_purpose,
            "capability_name": cap.name,
            "external_call": cap.external_call,
        },
    )


def get_all_capabilities() -> list[dict[str, Any]]:
    """Gibt alle Capabilities als Dict-Liste zurueck (fuer Admin-Dashboard)."""
    return [
        {
            "capability_id": cap.capability_id,
            "name": cap.name,
            "description": cap.description,
            "target": cap.target.value,
            "allowed_data_classes": [dc.value for dc in cap.allowed_data_classes],
            "risk_level": cap.risk_level.value,
            "requires_approval": cap.requires_approval,
            "external_call": cap.external_call,
            "enabled": cap.enabled,
            "gdpr_purpose": cap.gdpr_purpose,
            "tags": cap.tags,
        }
        for cap in _CAPABILITIES.values()
    ]


def get_capability(capability_id: str) -> dict[str, Any] | None:
    cap = _CAPABILITIES.get(capability_id)
    if cap is None:
        return None
    return get_all_capabilities()[list(_CAPABILITIES.keys()).index(capability_id)]
