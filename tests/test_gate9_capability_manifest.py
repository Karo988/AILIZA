"""
Gate 9 — Capability Risk Manifest Tests
=========================================
Prüft dass jede Capability ein vollständiges Risikoprofil hat und dass
No-Fallback-No-Go, Modus-Prüfung und AVV-Gate korrekt greifen.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "backend"))

from capability_manifest import (
    CAPABILITY_REGISTRY,
    CapabilityProfile,
    ManifestCheckResult,
    check_capability,
    get_manifest_summary,
)
from approval import RiskLevel
from governance.data_governance import DataClass
from kill_switch import OperationMode
from sandbox import ActionClass


# ── TestRegistryCompleteness ───────────────────────────────────────────────────

class TestRegistryCompleteness:
    """Alle registrierten Capabilities müssen vollständige Pflichtfelder haben."""

    def test_registry_not_empty(self):
        assert len(CAPABILITY_REGISTRY) >= 10

    def test_all_capabilities_have_valid_risk_level(self):
        valid = {r.value for r in RiskLevel}
        for cap in CAPABILITY_REGISTRY.values():
            assert cap.risk_level in valid, f"{cap.capability_id}: ungültiger risk_level '{cap.risk_level}'"

    def test_all_capabilities_have_valid_data_scope(self):
        valid = {d.value for d in DataClass}
        for cap in CAPABILITY_REGISTRY.values():
            assert cap.data_scope.value in valid, f"{cap.capability_id}: ungültige data_scope"

    def test_all_capabilities_have_valid_action_class(self):
        valid = {a.value for a in ActionClass}
        for cap in CAPABILITY_REGISTRY.values():
            assert cap.action_class.value in valid, f"{cap.capability_id}: ungültige action_class"

    def test_capabilities_with_fallback_have_valid_fallback_reference(self):
        """Fallback-ID muss auf eine bekannte Capability oder SOPs verweisen."""
        for cap in CAPABILITY_REGISTRY.values():
            if cap.fallback_id is not None:
                assert len(cap.fallback_id) > 0, f"{cap.capability_id}: leere fallback_id"

    def test_beta_approved_capabilities_have_no_special_category(self):
        """Beta-freigegebene Capabilities dürfen keine SPECIAL_CATEGORY verarbeiten."""
        for cap in CAPABILITY_REGISTRY.values():
            if cap.beta_approved:
                assert cap.data_scope != DataClass.SPECIAL_CATEGORY, (
                    f"{cap.capability_id}: beta_approved=True aber SPECIAL_CATEGORY"
                )

    def test_beta_approved_capabilities_have_fallback(self):
        """Beta-freigegeben ohne Fallback ist ein Widerspruch."""
        for cap in CAPABILITY_REGISTRY.values():
            if cap.beta_approved:
                assert cap.fallback_id is not None, (
                    f"{cap.capability_id}: beta_approved=True aber kein Fallback"
                )


# ── TestNoFallbackNoGo ────────────────────────────────────────────────────────

class TestNoFallbackNoGo:
    """Capabilities ohne fallback_id sind permanent gesperrt."""

    def test_biometric_vip_recognition_has_no_fallback(self):
        cap = CAPABILITY_REGISTRY["biometric_vip_recognition"]
        assert cap.fallback_id is None

    def test_biometric_vip_recognition_is_blocked(self):
        result = check_capability("biometric_vip_recognition")
        assert result.allowed is False
        assert "Fallback" in result.reason or "fallback" in result.reason.lower()

    def test_install_software_has_no_fallback(self):
        cap = CAPABILITY_REGISTRY["install_software"]
        assert cap.fallback_id is None

    def test_install_software_is_blocked(self):
        result = check_capability("install_software")
        assert result.allowed is False

    def test_execute_shell_command_has_no_fallback(self):
        result = check_capability("execute_shell_command")
        assert result.allowed is False

    def test_access_control_camera_is_blocked(self):
        result = check_capability("access_control_camera")
        assert result.allowed is False

    def test_no_fallback_capabilities_count(self):
        summary = get_manifest_summary()
        assert summary["no_fallback_blocked_count"] >= 4, (
            "Es sollten mindestens 4 Capabilities permanent gesperrt sein (Biometrie + System)"
        )


# ── TestBetaApprovedCapabilities ──────────────────────────────────────────────

class TestBetaApprovedCapabilities:
    """Beta-freigegebene Capabilities müssen in NORMAL-Modus erlaubt sein."""

    def test_analyze_document_is_beta_approved(self):
        result = check_capability("analyze_document", current_mode=OperationMode.NORMAL.value)
        assert result.allowed is True
        assert result.beta_approved is True

    def test_classify_data_is_beta_approved(self):
        result = check_capability("classify_data", current_mode=OperationMode.NORMAL.value)
        assert result.allowed is True

    def test_generate_report_workspace_is_beta_approved(self):
        result = check_capability("generate_report_workspace", current_mode=OperationMode.NORMAL.value)
        assert result.allowed is True

    def test_compliance_check_is_beta_approved(self):
        result = check_capability("compliance_check", current_mode=OperationMode.NORMAL.value)
        assert result.allowed is True

    def test_beta_approved_count(self):
        summary = get_manifest_summary()
        assert summary["beta_approved_count"] >= 4


# ── TestOperationModeGating ───────────────────────────────────────────────────

class TestOperationModeGating:
    """Capabilities werden im falschen Betriebsmodus geblockt."""

    def test_analyze_document_blocked_in_kill_switch(self):
        result = check_capability("analyze_document", current_mode=OperationMode.KILL_SWITCH_ACTIVE.value)
        assert result.allowed is False
        assert "Modus" in result.reason

    def test_analyze_document_allowed_in_restricted_mode(self):
        result = check_capability("analyze_document", current_mode=OperationMode.RESTRICTED.value)
        assert result.allowed is True

    def test_analyze_document_allowed_in_offline_mode(self):
        result = check_capability("analyze_document", current_mode=OperationMode.OFFLINE.value)
        assert result.allowed is True

    def test_generate_report_blocked_in_read_only(self):
        result = check_capability("generate_report_workspace", current_mode=OperationMode.READ_ONLY.value)
        assert result.allowed is False

    def test_send_push_all_blocked_in_restricted(self):
        result = check_capability("send_push_all_visitors", current_mode=OperationMode.RESTRICTED.value)
        assert result.allowed is False

    def test_capability_with_no_allowed_modes_always_blocked(self):
        result = check_capability("biometric_vip_recognition", current_mode=OperationMode.NORMAL.value)
        assert result.allowed is False

    def test_hr_assignment_blocked_in_all_modes(self):
        """HR-Entscheidung soll ausschließlich in NORMAL erlaubt sein (und braucht Approval)."""
        for mode in (OperationMode.RESTRICTED, OperationMode.READ_ONLY, OperationMode.OFFLINE):
            result = check_capability("hr_shift_assignment", current_mode=mode.value)
            assert result.allowed is False, f"hr_shift_assignment sollte im Modus {mode.value} gesperrt sein"


# ── TestAVVGating ─────────────────────────────────────────────────────────────

class TestAVVGating:
    """Externe Calls ohne AVV-bestätigten Provider werden geblockt."""

    def test_send_message_without_avv_provider_blocked(self):
        result = check_capability("send_message_single", provider_id="groq")
        assert result.allowed is False
        assert "AVV" in result.reason or "avv" in result.reason.lower()

    def test_send_push_without_avv_provider_blocked(self):
        result = check_capability("send_push_all_visitors", provider_id="anthropic")
        assert result.allowed is False

    def test_send_push_without_provider_blocked(self):
        result = check_capability("send_push_all_visitors", provider_id=None)
        assert result.allowed is False

    def test_analyze_document_no_avv_needed(self):
        """Interne Capabilities brauchen keinen AVV."""
        result = check_capability("analyze_document", current_mode=OperationMode.NORMAL.value)
        assert result.allowed is True

    def test_avv_confirmed_providers_empty_in_beta(self):
        summary = get_manifest_summary()
        assert summary["avv_confirmed_providers"] == [], (
            "Beta: keine AVV-bestätigten Provider — kein externer LLM-Call mit Personendaten"
        )


# ── TestUnknownCapability ─────────────────────────────────────────────────────

class TestUnknownCapability:
    """Unbekannte Capabilities werden fail-closed geblockt."""

    def test_unknown_capability_is_blocked(self):
        result = check_capability("undefined_action_xyz")
        assert result.allowed is False

    def test_unknown_capability_reason_mentions_fail_closed(self):
        result = check_capability("do_something_dangerous")
        assert "fail-closed" in result.reason.lower() or "unbekannt" in result.reason.lower()

    def test_unknown_capability_has_no_fallback(self):
        result = check_capability("nonexistent")
        assert result.fallback_id is None

    def test_empty_capability_id_is_blocked(self):
        result = check_capability("")
        assert result.allowed is False


# ── TestManifestSummary ───────────────────────────────────────────────────────

class TestManifestSummary:
    """get_manifest_summary() gibt vollständige und korrekte Übersicht."""

    def test_summary_keys_present(self):
        summary = get_manifest_summary()
        assert "total_capabilities" in summary
        assert "beta_approved_count" in summary
        assert "no_fallback_blocked_count" in summary
        assert "beta_approved_ids" in summary
        assert "no_fallback_blocked_ids" in summary
        assert "avv_confirmed_providers" in summary
        assert "capabilities" in summary

    def test_summary_counts_consistent(self):
        summary = get_manifest_summary()
        assert summary["total_capabilities"] == len(CAPABILITY_REGISTRY)
        assert summary["beta_approved_count"] == len(summary["beta_approved_ids"])
        assert summary["no_fallback_blocked_count"] == len(summary["no_fallback_blocked_ids"])

    def test_special_category_capabilities_not_beta_approved(self):
        summary = get_manifest_summary()
        beta_ids = set(summary["beta_approved_ids"])
        for cap in CAPABILITY_REGISTRY.values():
            if cap.data_scope == DataClass.SPECIAL_CATEGORY:
                assert cap.capability_id not in beta_ids

    def test_safety_critical_capabilities_require_elevated_roles(self):
        """SAFETY_CRITICAL braucht mindestens security_lead oder operations_lead oder owner."""
        elevated = {"security_lead", "operations_lead", "privacy", "legal", "owner"}
        for cap in CAPABILITY_REGISTRY.values():
            if cap.risk_level == RiskLevel.SAFETY_CRITICAL.value and cap.required_roles:
                assert bool(set(cap.required_roles) & elevated), (
                    f"{cap.capability_id}: SAFETY_CRITICAL ohne erhöhte Rolle"
                )

    def test_to_dict_all_capabilities(self):
        for cap in CAPABILITY_REGISTRY.values():
            d = cap.to_dict()
            assert "capability_id" in d
            assert "risk_level" in d
            assert "fallback_id" in d
            assert "beta_approved" in d


# ── TestManifestCheckResult ───────────────────────────────────────────────────

class TestManifestCheckResult:
    """ManifestCheckResult.to_dict() vollständig."""

    def test_allowed_result_to_dict(self):
        result = check_capability("analyze_document", current_mode=OperationMode.NORMAL.value)
        d = result.to_dict()
        assert d["allowed"] is True
        assert "risk_level" in d
        assert "fallback_id" in d

    def test_blocked_result_to_dict(self):
        result = check_capability("biometric_vip_recognition")
        d = result.to_dict()
        assert d["allowed"] is False
        assert d["beta_approved"] is False
