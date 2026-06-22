"""
AILIZA Gate 9 — Capability Risk Manifest
=========================================
Jede Capability bekommt ein maschinenlesbares Risikoprofil.

Regel: Keine Capability ohne fallback_id → kein Go (No-Fallback-No-Go).
Regel: Unbekannte Capability → fail-closed geblockt.
Regel: Provider ohne AVV + PERSONAL/SPECIAL_CATEGORY → geblockt.
Regel: Capability außerhalb freigegebener operation_mode-Grenzen → geblockt.

Profil-Felder:
  capability_id       — eindeutiger Bezeichner (z. B. "send_push_all")
  action_class        — ActionClass aus sandbox.py
  data_scope          — DataClass aus governance/data_governance.py
  device_scope        — "workspace", "local_system", "mobile", "external_api", "none"
  can_write           — schreibt Daten (Datei, DB, API)
  can_delete          — löscht Daten
  external_call       — kontaktiert externen Dienst (LLM, API, Messenger)
  risk_level          — RiskLevel aus approval.py
  requires_approval   — True wenn immer Approval nötig
  required_roles      — Mindest-Rollen für Approval-Freigabe
  fallback_id         — Pflichtfeld: was passiert wenn blockiert (None → No-Go)
  sop_reference       — Referenz auf schriftliche Betriebsanweisung
  provider_scope      — Liste erlaubter Provider-IDs (leer = kein externer Call erlaubt)
  avv_required        — True wenn AVV/DPA mit Provider Pflicht ist
  allowed_modes       — Betriebsmodi in denen die Capability aktiv ist
  beta_approved       — True wenn für interne Beta freigegeben
  notes               — Freier Text für Governance-Notizen
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from approval import RiskLevel
from governance.data_governance import DataClass
from kill_switch import OperationMode
from sandbox import ActionClass


# Provider-IDs die bereits einen bestätigten AVV haben
_AVV_CONFIRMED_PROVIDERS: frozenset[str] = frozenset()  # Beta: noch keine AVV bestätigt


@dataclass(frozen=True)
class CapabilityProfile:
    capability_id: str
    action_class: ActionClass
    data_scope: DataClass
    device_scope: str                          # "workspace"|"local_system"|"mobile"|"external_api"|"none"
    risk_level: str                            # RiskLevel-Wert
    fallback_id: str | None                   # None = No-Fallback-No-Go → immer geblockt
    can_write: bool = False
    can_delete: bool = False
    external_call: bool = False
    requires_approval: bool = False
    required_roles: tuple[str, ...] = field(default_factory=tuple)
    sop_reference: str = ""
    provider_scope: tuple[str, ...] = field(default_factory=tuple)
    avv_required: bool = False
    allowed_modes: tuple[str, ...] = field(default_factory=lambda: (OperationMode.NORMAL.value,))
    beta_approved: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "action_class": self.action_class.value,
            "data_scope": self.data_scope.value,
            "device_scope": self.device_scope,
            "risk_level": self.risk_level,
            "fallback_id": self.fallback_id,
            "can_write": self.can_write,
            "can_delete": self.can_delete,
            "external_call": self.external_call,
            "requires_approval": self.requires_approval,
            "required_roles": list(self.required_roles),
            "sop_reference": self.sop_reference,
            "provider_scope": list(self.provider_scope),
            "avv_required": self.avv_required,
            "allowed_modes": list(self.allowed_modes),
            "beta_approved": self.beta_approved,
            "notes": self.notes,
        }


# ── Capability-Registry ────────────────────────────────────────────────────────

CAPABILITY_REGISTRY: dict[str, CapabilityProfile] = {}


def _reg(profile: CapabilityProfile) -> CapabilityProfile:
    CAPABILITY_REGISTRY[profile.capability_id] = profile
    return profile


# ── Interne Beta — ✅ Freigegeben ──────────────────────────────────────────────

_reg(CapabilityProfile(
    capability_id="analyze_document",
    action_class=ActionClass.READ_FILE,
    data_scope=DataClass.PUBLIC,
    device_scope="workspace",
    risk_level=RiskLevel.LOW.value,
    fallback_id="manual_review",
    can_write=False,
    external_call=False,
    requires_approval=False,
    allowed_modes=(
        OperationMode.NORMAL.value,
        OperationMode.RESTRICTED.value,
        OperationMode.READ_ONLY.value,
        OperationMode.OFFLINE.value,
    ),
    beta_approved=True,
    notes="Nur freigegebene Workspace-Dateien. Keine Personendaten ohne needs_review.",
))

_reg(CapabilityProfile(
    capability_id="classify_data",
    action_class=ActionClass.READ_FILE,
    data_scope=DataClass.PUBLIC,
    device_scope="workspace",
    risk_level=RiskLevel.LOW.value,
    fallback_id="manual_classification",
    external_call=False,
    requires_approval=False,
    allowed_modes=(
        OperationMode.NORMAL.value,
        OperationMode.RESTRICTED.value,
        OperationMode.READ_ONLY.value,
        OperationMode.OFFLINE.value,
    ),
    beta_approved=True,
    notes="Governance-Klassifikation intern — kein externer Call.",
))

_reg(CapabilityProfile(
    capability_id="generate_report_workspace",
    action_class=ActionClass.WRITE_FILE,
    data_scope=DataClass.INTERNAL,
    device_scope="workspace",
    risk_level=RiskLevel.LOW.value,
    fallback_id="export_manual",
    can_write=True,
    external_call=False,
    requires_approval=False,
    allowed_modes=(
        OperationMode.NORMAL.value,
        OperationMode.RESTRICTED.value,
    ),
    beta_approved=True,
    notes="Schreiben nur in AILIZA_WORKSPACE_PATH.",
))

_reg(CapabilityProfile(
    capability_id="compliance_check",
    action_class=ActionClass.READ_FILE,
    data_scope=DataClass.INTERNAL,
    device_scope="workspace",
    risk_level=RiskLevel.LOW.value,
    fallback_id="manual_compliance_review",
    external_call=False,
    requires_approval=False,
    allowed_modes=(
        OperationMode.NORMAL.value,
        OperationMode.RESTRICTED.value,
        OperationMode.READ_ONLY.value,
        OperationMode.OFFLINE.value,
    ),
    beta_approved=True,
    notes="DSGVO/EU-AI-Act-Prüfung lokal — kein externer Call.",
))

_reg(CapabilityProfile(
    capability_id="summarize_document",
    action_class=ActionClass.READ_FILE,
    data_scope=DataClass.INTERNAL,
    device_scope="workspace",
    risk_level=RiskLevel.MEDIUM.value,
    fallback_id="manual_summary",
    external_call=True,
    requires_approval=True,
    required_roles=("admin", "manager", "owner"),
    provider_scope=(),          # Beta: kein externer LLM für INTERNAL ohne AVV
    avv_required=True,
    allowed_modes=(OperationMode.NORMAL.value,),
    beta_approved=False,
    notes="Externer LLM nur nach AVV-Abschluss freigeben. Beta: lokal oder manuell.",
))

# ── Externe Kommunikation — 🟡 Mit Approval ────────────────────────────────────

_reg(CapabilityProfile(
    capability_id="send_message_single",
    action_class=ActionClass.SEND_MESSAGE,
    data_scope=DataClass.PERSONAL_DATA,
    device_scope="external_api",
    risk_level=RiskLevel.HIGH.value,
    fallback_id="draft_for_manual_send",
    can_write=False,
    external_call=True,
    requires_approval=True,
    required_roles=("admin", "owner"),
    provider_scope=(),
    avv_required=True,
    allowed_modes=(OperationMode.NORMAL.value,),
    beta_approved=False,
    notes="Einzelnachricht mit Vorschau + expliziter Nutzerfreigabe. AVV nötig.",
))

_reg(CapabilityProfile(
    capability_id="send_push_all_visitors",
    action_class=ActionClass.SEND_MESSAGE,
    data_scope=DataClass.PERSONAL_DATA,
    device_scope="mobile",
    risk_level=RiskLevel.SAFETY_CRITICAL.value,
    fallback_id="send_message_single",
    can_write=False,
    external_call=True,
    requires_approval=True,
    required_roles=("security_lead", "operations_lead", "owner"),
    provider_scope=(),
    avv_required=True,
    allowed_modes=(OperationMode.NORMAL.value,),
    beta_approved=False,
    sop_reference="SOP-UC03-CrowdControl",
    notes="SAFETY_CRITICAL. Auto-Reject nach 300s Timeout. Kein Auto-Approve.",
))

# ── HR / Personalentscheidungen — 🔴 Nicht freigegeben ────────────────────────

_reg(CapabilityProfile(
    capability_id="hr_shift_assignment",
    action_class=ActionClass.WRITE_FILE,
    data_scope=DataClass.HR,
    device_scope="workspace",
    risk_level=RiskLevel.PERSON_DECISION.value,
    fallback_id="hr_shift_proposal",       # nur Vorschlag, kein Auto-Commit
    can_write=True,
    external_call=False,
    requires_approval=True,
    required_roles=("privacy", "legal", "owner"),
    avv_required=False,
    allowed_modes=(OperationMode.NORMAL.value,),
    beta_approved=False,
    sop_reference="SOP-UC02-HRDecision",
    notes="DSGVO Art. 22 / EU AI Act High-Risk. Nur Vorschlag — kein Auto-Commit.",
))

_reg(CapabilityProfile(
    capability_id="hr_shift_proposal",
    action_class=ActionClass.WRITE_FILE,
    data_scope=DataClass.HR,
    device_scope="workspace",
    risk_level=RiskLevel.HIGH.value,
    fallback_id="manual_hr_planning",
    can_write=True,
    external_call=False,
    requires_approval=True,
    required_roles=("admin", "owner"),
    avv_required=False,
    allowed_modes=(OperationMode.NORMAL.value,),
    beta_approved=False,
    sop_reference="SOP-UC02-HRDecision",
    notes="Schichtplan als Vorschlag — muss durch Mensch bestätigt werden.",
))

# ── Biometrie — 🔴 Permanent gesperrt ─────────────────────────────────────────

_reg(CapabilityProfile(
    capability_id="biometric_vip_recognition",
    action_class=ActionClass.ACCESS_PHOTOS,
    data_scope=DataClass.SPECIAL_CATEGORY,
    device_scope="local_system",
    risk_level=RiskLevel.SAFETY_CRITICAL.value,
    fallback_id=None,                       # No-Fallback-No-Go → permanent geblockt
    can_write=False,
    external_call=False,
    requires_approval=True,
    required_roles=("privacy", "legal", "owner"),
    avv_required=True,
    allowed_modes=(),                       # in keinem Modus erlaubt
    beta_approved=False,
    sop_reference="SOP-UC01-Biometric",
    notes="DSGVO Art. 9 / DSFA erforderlich. Ohne DPIA niemals freigeben. Beta: immer gesperrt.",
))

_reg(CapabilityProfile(
    capability_id="access_control_camera",
    action_class=ActionClass.ACCESS_PHOTOS,
    data_scope=DataClass.SPECIAL_CATEGORY,
    device_scope="local_system",
    risk_level=RiskLevel.SAFETY_CRITICAL.value,
    fallback_id=None,                       # No-Fallback-No-Go
    avv_required=True,
    allowed_modes=(),
    beta_approved=False,
    notes="Kamera-basierte Einlasskontrolle. Biometrie Art. 9 — DPIA Pflicht.",
))

# ── System-Agent — 🔴 Permanent gesperrt ──────────────────────────────────────

_reg(CapabilityProfile(
    capability_id="install_software",
    action_class=ActionClass.INSTALL_APP,
    data_scope=DataClass.PUBLIC,
    device_scope="local_system",
    risk_level=RiskLevel.SAFETY_CRITICAL.value,
    fallback_id=None,                       # No-Fallback-No-Go
    can_write=True,
    allowed_modes=(),
    beta_approved=False,
    notes="Permanent gesperrt. Gate 8: ALWAYS_BLOCKED.",
))

_reg(CapabilityProfile(
    capability_id="execute_shell_command",
    action_class=ActionClass.EXECUTE_SHELL,
    data_scope=DataClass.PUBLIC,
    device_scope="local_system",
    risk_level=RiskLevel.SAFETY_CRITICAL.value,
    fallback_id=None,                       # No-Fallback-No-Go
    can_write=True,
    can_delete=True,
    allowed_modes=(),
    beta_approved=False,
    notes="Permanent gesperrt. Shell mit Seiteneffekten außerhalb Gate 8 nicht erlaubt.",
))


# ── Manifest-Validierung & Enforcement ────────────────────────────────────────

@dataclass(frozen=True)
class ManifestCheckResult:
    allowed: bool
    capability_id: str
    reason: str
    risk_level: str
    fallback_id: str | None
    requires_approval: bool
    required_roles: list[str]
    beta_approved: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "capability_id": self.capability_id,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "fallback_id": self.fallback_id,
            "requires_approval": self.requires_approval,
            "required_roles": self.required_roles,
            "beta_approved": self.beta_approved,
        }


def check_capability(
    capability_id: str,
    current_mode: str | None = None,
    provider_id: str | None = None,
) -> ManifestCheckResult:
    """
    Prüft ob eine Capability im aktuellen Kontext ausgeführt werden darf.

    Fail-closed:
      - Unbekannte Capability → geblockt
      - fallback_id ist None → geblockt (No-Fallback-No-Go)
      - Betriebsmodus nicht in allowed_modes → geblockt
      - external_call + avv_required + Provider nicht in AVV-Liste → geblockt
    """
    profile = CAPABILITY_REGISTRY.get(capability_id)
    if profile is None:
        return ManifestCheckResult(
            allowed=False,
            capability_id=capability_id,
            reason=f"Unbekannte Capability '{capability_id}' — fail-closed geblockt.",
            risk_level=RiskLevel.HIGH.value,
            fallback_id=None,
            requires_approval=True,
            required_roles=["owner"],
            beta_approved=False,
        )

    # No-Fallback-No-Go
    if profile.fallback_id is None:
        return ManifestCheckResult(
            allowed=False,
            capability_id=capability_id,
            reason=f"Capability '{capability_id}' hat keinen Fallback — permanent gesperrt (No-Fallback-No-Go).",
            risk_level=profile.risk_level,
            fallback_id=None,
            requires_approval=True,
            required_roles=list(profile.required_roles),
            beta_approved=False,
        )

    # Betriebsmodus-Prüfung
    if current_mode and current_mode not in profile.allowed_modes:
        return ManifestCheckResult(
            allowed=False,
            capability_id=capability_id,
            reason=f"Capability '{capability_id}' ist im Modus '{current_mode}' nicht erlaubt.",
            risk_level=profile.risk_level,
            fallback_id=profile.fallback_id,
            requires_approval=profile.requires_approval,
            required_roles=list(profile.required_roles),
            beta_approved=profile.beta_approved,
        )

    # Keine allowed_modes = in keinem Modus erlaubt
    if not profile.allowed_modes:
        return ManifestCheckResult(
            allowed=False,
            capability_id=capability_id,
            reason=f"Capability '{capability_id}' ist in keinem Betriebsmodus erlaubt.",
            risk_level=profile.risk_level,
            fallback_id=profile.fallback_id,
            requires_approval=profile.requires_approval,
            required_roles=list(profile.required_roles),
            beta_approved=profile.beta_approved,
        )

    # AVV-Prüfung für externe Calls
    if profile.external_call and profile.avv_required:
        if provider_id not in _AVV_CONFIRMED_PROVIDERS:
            return ManifestCheckResult(
                allowed=False,
                capability_id=capability_id,
                reason=(
                    f"Capability '{capability_id}' erfordert AVV mit Provider '{provider_id}' — "
                    f"noch nicht bestätigt. Externer Call gesperrt."
                ),
                risk_level=profile.risk_level,
                fallback_id=profile.fallback_id,
                requires_approval=profile.requires_approval,
                required_roles=list(profile.required_roles),
                beta_approved=profile.beta_approved,
            )

    return ManifestCheckResult(
        allowed=True,
        capability_id=capability_id,
        reason="Capability freigegeben.",
        risk_level=profile.risk_level,
        fallback_id=profile.fallback_id,
        requires_approval=profile.requires_approval,
        required_roles=list(profile.required_roles),
        beta_approved=profile.beta_approved,
    )


def get_manifest_summary() -> dict[str, Any]:
    """Gibt Manifest-Übersicht zurück (für Admin-Endpoint und Beta-Report)."""
    all_caps = [p.to_dict() for p in CAPABILITY_REGISTRY.values()]
    beta_approved = [p for p in CAPABILITY_REGISTRY.values() if p.beta_approved]
    no_fallback = [p for p in CAPABILITY_REGISTRY.values() if p.fallback_id is None]
    return {
        "total_capabilities": len(CAPABILITY_REGISTRY),
        "beta_approved_count": len(beta_approved),
        "no_fallback_blocked_count": len(no_fallback),
        "beta_approved_ids": [p.capability_id for p in beta_approved],
        "no_fallback_blocked_ids": [p.capability_id for p in no_fallback],
        "avv_confirmed_providers": sorted(_AVV_CONFIRMED_PROVIDERS),
        "capabilities": all_caps,
    }
