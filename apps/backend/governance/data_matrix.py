"""
AILIZA Datenziel-Matrix
=======================
Entscheidet, ob eine Datenklasse an ein Ziel weitergegeben werden darf.
Fail-closed: Unklarheit fuehrt zu BLOCK.
"""
from __future__ import annotations

from enum import Enum

from .data_governance import DataClass, DataTarget


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    ALLOW_WITH_NOTICE = "allow_with_notice"
    REDACT_REQUIRED = "redact_required"
    APPROVAL_REQUIRED = "approval_required"
    BLOCK = "block"


_PERSISTENT_TARGETS = {
    DataTarget.MEMORY,
    DataTarget.VECTOR_DB,
    DataTarget.FILE_STORAGE,
}
_EXTERNAL_TARGETS = {
    DataTarget.EXTERNAL_LLM,
    DataTarget.CRM,
    DataTarget.EMAIL,
}


def _decide_single(
    data_class: DataClass,
    target: DataTarget,
    redaction_applied: bool,
    approval_given: bool,
    provider_profile_active: bool,
) -> PolicyDecision:
    # CREDENTIALS: immer BLOCK, ausser RAM zur Erkennung
    if data_class == DataClass.CREDENTIALS:
        return PolicyDecision.ALLOW if target == DataTarget.RAM else PolicyDecision.BLOCK

    # SPECIAL_CATEGORY: BLOCK fuer EXTERNAL_LLM, MEMORY, VECTOR_DB
    if data_class == DataClass.SPECIAL_CATEGORY:
        if target in {DataTarget.EXTERNAL_LLM, DataTarget.MEMORY, DataTarget.VECTOR_DB}:
            return PolicyDecision.BLOCK
        if target in _EXTERNAL_TARGETS:
            return PolicyDecision.APPROVAL_REQUIRED if approval_given else PolicyDecision.APPROVAL_REQUIRED
        return PolicyDecision.ALLOW_WITH_NOTICE

    # SECURITY_SENSITIVE: extern nur nach Approval
    if data_class == DataClass.SECURITY_SENSITIVE:
        if target in _EXTERNAL_TARGETS or target in _PERSISTENT_TARGETS:
            return PolicyDecision.APPROVAL_REQUIRED if not approval_given else PolicyDecision.ALLOW_WITH_NOTICE
        return PolicyDecision.ALLOW

    # PERSONAL_DATA: EXTERNAL_LLM nur nach Redaction oder Approval + ProviderProfile
    if data_class == DataClass.PERSONAL_DATA:
        if target == DataTarget.EXTERNAL_LLM:
            if not provider_profile_active:
                return PolicyDecision.BLOCK
            if redaction_applied:
                return PolicyDecision.ALLOW_WITH_NOTICE
            if approval_given:
                return PolicyDecision.ALLOW_WITH_NOTICE
            return PolicyDecision.REDACT_REQUIRED
        if target in _PERSISTENT_TARGETS:
            return PolicyDecision.APPROVAL_REQUIRED if not approval_given else PolicyDecision.ALLOW_WITH_NOTICE
        return PolicyDecision.ALLOW

    # HR / LEGAL / FINANCIAL: sensibel, extern nur mit Approval
    if data_class in {DataClass.HR, DataClass.LEGAL, DataClass.FINANCIAL}:
        if target in _EXTERNAL_TARGETS:
            if not provider_profile_active:
                return PolicyDecision.BLOCK
            if redaction_applied:
                return PolicyDecision.ALLOW_WITH_NOTICE
            return PolicyDecision.APPROVAL_REQUIRED if not approval_given else PolicyDecision.ALLOW_WITH_NOTICE
        if target in _PERSISTENT_TARGETS:
            return PolicyDecision.APPROVAL_REQUIRED if not approval_given else PolicyDecision.ALLOW_WITH_NOTICE
        return PolicyDecision.ALLOW

    # CONFIDENTIAL / INTERNAL / INTELLECTUAL_PROPERTY
    if data_class in {DataClass.CONFIDENTIAL, DataClass.INTELLECTUAL_PROPERTY}:
        if target == DataTarget.EXTERNAL_LLM:
            if not provider_profile_active:
                return PolicyDecision.BLOCK
            return PolicyDecision.ALLOW_WITH_NOTICE
        return PolicyDecision.ALLOW

    if data_class == DataClass.INTERNAL:
        if target in _EXTERNAL_TARGETS and not provider_profile_active:
            return PolicyDecision.ALLOW_WITH_NOTICE
        return PolicyDecision.ALLOW

    # PUBLIC
    if data_class == DataClass.PUBLIC:
        if target == DataTarget.EXTERNAL_LLM:
            return PolicyDecision.ALLOW if provider_profile_active else PolicyDecision.ALLOW_WITH_NOTICE
        return PolicyDecision.ALLOW

    # Unbekannt -> fail-closed
    return PolicyDecision.BLOCK


# Reihenfolge der Strenge (hoechste gewinnt)
_DECISION_SEVERITY = {
    PolicyDecision.ALLOW: 0,
    PolicyDecision.ALLOW_WITH_NOTICE: 1,
    PolicyDecision.REDACT_REQUIRED: 2,
    PolicyDecision.APPROVAL_REQUIRED: 3,
    PolicyDecision.BLOCK: 4,
}


def check_data_target(
    data_classes: list[DataClass],
    target: DataTarget,
    redaction_applied: bool,
    approval_given: bool,
    provider_profile_active: bool,
) -> PolicyDecision:
    """Strengste Einzelentscheidung ueber alle Datenklassen gewinnt."""
    try:
        if not data_classes:
            data_classes = [DataClass.PUBLIC]
        decisions = [
            _decide_single(dc, target, redaction_applied, approval_given, provider_profile_active)
            for dc in data_classes
        ]
        return max(decisions, key=lambda d: _DECISION_SEVERITY[d])
    except Exception:
        return PolicyDecision.BLOCK
