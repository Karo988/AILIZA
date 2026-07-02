"""
Tests fuer Provider-Governance: ProviderProfile, Policy-Check, OpenRouter-Gate.
Prueft: Fail-Closed, Datenklassen-Blockierung, Use-Case-Check,
        Admin-Kill-Switch, Transfer-Basis, OpenRouter deaktiviert.
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")


# ── check_provider_policy ─────────────────────────────────────────────────────
def test_unknown_provider_blocked():
    from apps.backend.providers.provider_profiles import check_provider_policy
    from apps.backend.governance.data_governance import DataClass
    allowed, reason = check_provider_policy("nonexistent", [DataClass.PUBLIC])
    assert not allowed
    assert "nicht registriert" in reason.lower() or "unbekannt" in reason.lower()


def test_groq_public_allowed():
    from apps.backend.providers.provider_profiles import check_provider_policy
    from apps.backend.governance.data_governance import DataClass
    allowed, reason = check_provider_policy("groq", [DataClass.PUBLIC])
    assert allowed
    assert reason == "ok"


def test_groq_internal_allowed():
    from apps.backend.providers.provider_profiles import check_provider_policy
    from apps.backend.governance.data_governance import DataClass
    allowed, _ = check_provider_policy("groq", [DataClass.INTERNAL])
    assert allowed


def test_groq_confidential_blocked():
    from apps.backend.providers.provider_profiles import check_provider_policy
    from apps.backend.governance.data_governance import DataClass
    allowed, reason = check_provider_policy("groq", [DataClass.CONFIDENTIAL])
    assert not allowed
    assert "confidential" in reason.lower() or "nicht erlaubt" in reason.lower()


def test_groq_credentials_blocked():
    from apps.backend.providers.provider_profiles import check_provider_policy
    from apps.backend.governance.data_governance import DataClass
    allowed, _ = check_provider_policy("groq", [DataClass.CREDENTIALS])
    assert not allowed


def test_groq_personal_data_blocked():
    from apps.backend.providers.provider_profiles import check_provider_policy
    from apps.backend.governance.data_governance import DataClass
    allowed, _ = check_provider_policy("groq", [DataClass.PERSONAL_DATA])
    assert not allowed


def test_anthropic_public_allowed():
    from apps.backend.providers.provider_profiles import check_provider_policy
    from apps.backend.governance.data_governance import DataClass
    allowed, _ = check_provider_policy("anthropic", [DataClass.PUBLIC])
    assert allowed


# ── OpenRouter: standardmaessig inaktiv / admin_disabled ─────────────────────
def test_openrouter_blocked_by_default():
    from apps.backend.providers.provider_profiles import check_provider_policy
    from apps.backend.governance.data_governance import DataClass
    allowed, reason = check_provider_policy("openrouter", [DataClass.PUBLIC])
    assert not allowed


def test_openrouter_profile_admin_disabled():
    from apps.backend.providers.provider_profiles import get_profile
    profile = get_profile("openrouter")
    assert profile is not None
    assert profile.admin_disabled is True
    assert profile.active is False


def test_openrouter_not_in_active_profiles():
    from apps.backend.providers.provider_profiles import get_active_profiles
    ids = [p.provider_id for p in get_active_profiles()]
    assert "openrouter" not in ids


def test_openrouter_only_allows_public():
    from apps.backend.providers.provider_profiles import get_profile
    from apps.backend.governance.data_governance import DataClass
    profile = get_profile("openrouter")
    assert DataClass.PUBLIC in profile.allowed_data_classes
    assert DataClass.INTERNAL not in profile.allowed_data_classes
    assert DataClass.CONFIDENTIAL not in profile.allowed_data_classes


def test_openrouter_logs_prompts_flagged():
    from apps.backend.providers.provider_profiles import get_profile
    profile = get_profile("openrouter")
    assert profile.logs_prompts is True  # bekanntes Risiko dokumentiert


# ── Transfer-Basis ────────────────────────────────────────────────────────────
def test_local_provider_eu_internal():
    from apps.backend.providers.provider_profiles import get_profile
    from apps.backend.providers.provider_profiles import TransferBasis
    profile = get_profile("local")
    assert profile.transfer_basis == TransferBasis.EU_INTERNAL


def test_groq_transfer_basis_scc():
    from apps.backend.providers.provider_profiles import get_profile
    from apps.backend.providers.provider_profiles import TransferBasis
    profile = get_profile("groq")
    assert profile.transfer_basis == TransferBasis.SCC


def test_provider_with_none_transfer_basis_blocked():
    from apps.backend.providers.provider_profiles import (
        ProviderProfile, TransferBasis, check_provider_policy, _PROFILES,
    )
    from apps.backend.governance.data_governance import DataClass
    # Temporaer einen Provider mit NONE-Transfer-Basis einsetzen
    fake = ProviderProfile(
        provider_id="fake_no_transfer",
        name="Fake",
        region="XX",
        transfer_basis=TransferBasis.NONE,
        avv_signed=False,
        allowed_data_classes=[DataClass.PUBLIC],
        allowed_use_cases=["all"],
        logs_prompts=True,
        used_for_training=True,
        active=True,
        profile_version="0.0.1",
    )
    _PROFILES["fake_no_transfer"] = fake
    try:
        allowed, reason = check_provider_policy("fake_no_transfer", [DataClass.PUBLIC])
        assert not allowed
        assert "transfer" in reason.lower() or "art. 44" in reason.lower()
    finally:
        del _PROFILES["fake_no_transfer"]


# ── Use-Case-Check ────────────────────────────────────────────────────────────
def test_use_case_allowed():
    from apps.backend.providers.provider_profiles import check_provider_policy
    from apps.backend.governance.data_governance import DataClass
    allowed, _ = check_provider_policy("groq", [DataClass.PUBLIC], use_case="kmu_assistant")
    assert allowed


def test_use_case_not_allowed():
    from apps.backend.providers.provider_profiles import check_provider_policy
    from apps.backend.governance.data_governance import DataClass
    allowed, reason = check_provider_policy("groq", [DataClass.PUBLIC], use_case="financial_trading")
    assert not allowed
    assert "use case" in reason.lower()


# ── Failover-Prioritaet ───────────────────────────────────────────────────────
def test_local_has_highest_priority():
    from apps.backend.providers.provider_profiles import get_profile
    local = get_profile("local")
    groq = get_profile("groq")
    anthropic = get_profile("anthropic")
    assert local.failover_priority < groq.failover_priority
    assert groq.failover_priority < anthropic.failover_priority


# ── Orchestrator blockiert inaktiven Provider ─────────────────────────────────
def test_orchestrator_blocks_openrouter(monkeypatch):
    from apps.backend.errors import AILIZAError
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
    from apps.backend.providers.orchestrator import ProviderOrchestrator
    from apps.backend.providers.openrouter_provider import OpenRouterProvider

    orch = ProviderOrchestrator(providers={
        "openrouter": OpenRouterProvider(),
    }, default_provider="openrouter")

    with pytest.raises(AILIZAError):
        orch.generate(
            [{"role": "user", "content": "test"}],
            provider_id="openrouter",
        )


# ── Admin-Endpunkt gibt Transfer-Basis zurueck ─────────────────────────────────
def test_profile_to_dict_includes_transfer_basis():
    from apps.backend.providers.provider_profiles import get_profile, profile_to_dict
    d = profile_to_dict(get_profile("groq"))
    assert "transfer_basis" in d
    assert d["transfer_basis"] == "scc"
    assert "logs_prompts" in d
    assert "used_for_training" in d
    assert "allowed_use_cases" in d
