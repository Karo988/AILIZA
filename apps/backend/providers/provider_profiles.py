"""
AILIZA ProviderProfile-Register
================================
Jeder externe LLM-Provider braucht ein ProviderProfile, bevor er genutzt werden darf.
Profile definieren: erlaubte Datenklassen, erlaubte Use Cases, Region, AVV-Status,
Logging-/Training-Verwendung, Transferbasis (DSGVO Art. 46), Failover-Reihenfolge
und einen Admin-Kill-Switch.

Policy-Check laeuft im Orchestrator VOR jedem Provider-Call.
Fail-closed: unbekannter oder inaktiver Provider → BLOCK.

DSGVO Art. 28: Auftragsverarbeitung erfordert AVV.
DSGVO Art. 44–46: Drittlandtransfer nur mit geeigneter Garantie.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    from ..governance.data_governance import DataClass
except ImportError:
    from governance.data_governance import DataClass


class TransferBasis(str, Enum):
    """DSGVO Art. 44–46 Transferbasis fuer Drittlandtransfers."""
    EU_INTERNAL = "eu_internal"              # kein Transfer — EU/EWR
    ADEQUACY_DECISION = "adequacy_decision"  # Art. 45
    SCC = "scc"                              # Art. 46 Abs. 2 lit. c (Standard-Vertragsklauseln)
    BINDING_RULES = "binding_rules"          # Art. 47 (BCR)
    NONE = "none"                            # Kein Transfermechanismus — BLOCK


@dataclass
class ProviderProfile:
    provider_id: str
    name: str
    region: str
    transfer_basis: TransferBasis       # DSGVO Art. 44-46 Grundlage
    avv_signed: bool                    # Auftragsverarbeitungsvertrag (Art. 28)
    allowed_data_classes: list[DataClass]
    allowed_use_cases: list[str]        # z.B. ["kmu_assistant", "summarization"]
    logs_prompts: bool                  # Speichert der Provider Prompts?
    used_for_training: bool             # Werden Daten fuer Training verwendet?
    active: bool
    profile_version: str
    failover_priority: int = 99         # Niedrigere Zahl = hoehere Prioritaet im Failover
    admin_disabled: bool = False        # Admin-Kill-Switch fuer diesen Provider
    notes: str = ""
    tags: list[str] = field(default_factory=list)

    def allows(self, data_class: DataClass) -> bool:
        return (
            self.active
            and not self.admin_disabled
            and data_class in self.allowed_data_classes
            and self.transfer_basis != TransferBasis.NONE
        )

    def allows_use_case(self, use_case: str) -> bool:
        return use_case in self.allowed_use_cases or "all" in self.allowed_use_cases


# ── Provider-Register ─────────────────────────────────────────────────────────
_PROFILES: dict[str, ProviderProfile] = {
    "groq": ProviderProfile(
        provider_id="groq",
        name="Groq Cloud",
        region="US",
        transfer_basis=TransferBasis.SCC,
        avv_signed=False,               # ⚠ DPA noch zu unterzeichnen
        allowed_data_classes=[
            DataClass.PUBLIC, DataClass.INTERNAL, DataClass.CONFIDENTIAL,
            # Nach Redaction erlaubt — data_matrix prüft redaction_applied=True
            DataClass.PERSONAL_DATA, DataClass.FINANCIAL, DataClass.HR, DataClass.LEGAL,
        ],
        allowed_use_cases=["kmu_assistant", "summarization", "classification"],
        logs_prompts=False,
        used_for_training=False,
        active=True,
        profile_version="1.2.0",
        failover_priority=1,
        notes="US-Provider, SCC. Nach Redaction erlaubt für PERSONAL_DATA/HR/LEGAL/FINANCIAL. "
              "AVV/DPA noch zu unterzeichnen. data_matrix kontrolliert redaction_applied-Gate.",
        tags=["llm", "groq", "us", "scc"],
    ),
    "anthropic": ProviderProfile(
        provider_id="anthropic",
        name="Anthropic",
        region="US",
        transfer_basis=TransferBasis.SCC,
        avv_signed=False,               # ⚠ Commercial API Terms prüfen
        allowed_data_classes=[
            DataClass.PUBLIC, DataClass.INTERNAL, DataClass.CONFIDENTIAL,
            DataClass.PERSONAL_DATA, DataClass.FINANCIAL, DataClass.HR, DataClass.LEGAL,
        ],
        allowed_use_cases=["kmu_assistant", "summarization", "code_assist", "classification"],
        logs_prompts=False,
        used_for_training=False,
        active=True,
        profile_version="1.2.0",
        failover_priority=2,
        notes="US-Provider, SCC. Nach Redaction erlaubt für PERSONAL_DATA/HR/LEGAL/FINANCIAL. "
              "AVV/DPA noch zu unterzeichnen.",
        tags=["llm", "anthropic", "us", "scc"],
    ),
    "openrouter": ProviderProfile(
        provider_id="openrouter",
        name="OpenRouter",
        region="US",
        transfer_basis=TransferBasis.SCC,
        avv_signed=False,               # ⚠ Kein bekannter AVV verfügbar (Stand 2026-06)
        allowed_data_classes=[DataClass.PUBLIC],  # Nur PUBLIC — Aggregator mit unklarer Subverarbeiter-Kette
        allowed_use_cases=["kmu_assistant"],
        logs_prompts=True,              # ⚠ OpenRouter kann Requests loggen (Policy prüfen)
        used_for_training=False,
        active=False,                   # Standardmaessig inaktiv bis AVV + Subverarbeiter-Pruefung
        profile_version="1.1.0",
        failover_priority=3,            # Dritter Fallback — nur wenn explizit aktiviert
        admin_disabled=True,            # Expliziter Admin-Kill-Switch
        notes="Aggregator-API: unterlagert wechselnde Sub-Provider (OpenAI, Mistral, Meta etc.). "
              "Subverarbeiter-Kette ungeklaert → DSGVO Art. 28 Abs. 4 nicht abgedeckt. "
              "Nur PUBLIC. Aktivierung erfordert: AVV, Subverarbeiter-Liste, Admin-Freigabe.",
        tags=["llm", "openrouter", "us", "aggregator", "disabled"],
    ),
    "local": ProviderProfile(
        provider_id="local",
        name="Lokal (Fast-Path)",
        region="local",
        transfer_basis=TransferBasis.EU_INTERNAL,
        avv_signed=True,
        allowed_data_classes=list(DataClass),
        allowed_use_cases=["all"],
        logs_prompts=False,
        used_for_training=False,
        active=True,
        profile_version="1.1.0",
        failover_priority=0,            # Hoechste Prioritaet — immer zuerst versuchen
        notes="Lokale Verarbeitung, kein externer Datenabfluss. Kein AVV erforderlich.",
        tags=["local", "fast-path", "eu"],
    ),
}


# ── Governance-Check ──────────────────────────────────────────────────────────
def check_provider_policy(
    provider_id: str,
    data_classes: list[DataClass],
    use_case: str = "kmu_assistant",
) -> tuple[bool, str]:
    """
    Prueft ob ein Provider fuer gegebene Datenklassen und Use Case zugelassen ist.
    Gibt (allowed: bool, reason: str) zurueck.
    Fail-closed: unbekannt oder inaktiv → (False, reason).
    """
    profile = _PROFILES.get(provider_id)
    if profile is None:
        return False, f"Unbekannter Provider '{provider_id}' — nicht registriert."
    if not profile.active:
        return False, f"Provider '{provider_id}' ist deaktiviert."
    if profile.admin_disabled:
        return False, f"Provider '{provider_id}' ist durch Admin-Kill-Switch gesperrt."
    if profile.transfer_basis == TransferBasis.NONE:
        return False, f"Provider '{provider_id}': kein Drittland-Transfermechanismus (DSGVO Art. 44)."
    if not profile.allows_use_case(use_case):
        return False, f"Provider '{provider_id}': Use Case '{use_case}' nicht freigegeben."
    forbidden = [dc for dc in data_classes if dc not in profile.allowed_data_classes]
    if forbidden:
        names = [dc.value for dc in forbidden]
        return False, (f"Provider '{provider_id}': Datenklassen nicht erlaubt: "
                       f"{', '.join(names)}. Kein AVV oder Transfer-Basis fehlt.")
    return True, "ok"


def get_profile(provider_id: str) -> ProviderProfile | None:
    return _PROFILES.get(provider_id)


def get_active_profiles() -> list[ProviderProfile]:
    return [p for p in _PROFILES.values() if p.active and not p.admin_disabled]


def is_data_class_allowed(provider_id: str, data_class: DataClass) -> bool:
    profile = get_profile(provider_id)
    if profile is None:
        return False
    return profile.allows(data_class)


def profile_to_dict(profile: ProviderProfile) -> dict[str, Any]:
    return {
        "provider_id": profile.provider_id,
        "name": profile.name,
        "region": profile.region,
        "transfer_basis": profile.transfer_basis.value,
        "avv_signed": profile.avv_signed,
        "allowed_data_classes": [c.value for c in profile.allowed_data_classes],
        "allowed_use_cases": profile.allowed_use_cases,
        "logs_prompts": profile.logs_prompts,
        "used_for_training": profile.used_for_training,
        "active": profile.active,
        "admin_disabled": profile.admin_disabled,
        "failover_priority": profile.failover_priority,
        "profile_version": profile.profile_version,
        "notes": profile.notes,
        "tags": profile.tags,
    }
