"""
Tests für AILIZA Governance-Regeln (DSGVO + EU AI Act).

Regeln (aus AILIZA_Governance_Logik.md):
- BLOCKED: nur bei CREDENTIALS / SPECIAL_CATEGORY (EU AI Act Art. 5 / DSGVO Art. 9)
- PERSONAL_DATA: redacten, nicht blockieren, als Entwurf weiterlaufen
- HR/LEGAL/FINANCIAL: redacten + Entwurf, nicht stoppen
- Provider-Profile: Groq/Anthropic erlauben PERSONAL_DATA/HR/LEGAL nach Redaction
"""
from __future__ import annotations

import pytest

from apps.backend.governance.data_governance import DataClass, DataTarget
from apps.backend.governance.data_matrix import PolicyDecision, check_data_target
from apps.backend.providers.provider_profiles import check_provider_policy


# ── 1. Datenziel-Matrix ────────────────────────────────────────────────────────

class TestDataMatrix:
    def test_personal_data_without_redaction_requires_redact(self):
        decision = check_data_target(
            data_classes=[DataClass.PERSONAL_DATA],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=False,
            approval_given=False,
            provider_profile_active=True,
        )
        assert decision == PolicyDecision.REDACT_REQUIRED

    def test_personal_data_after_redaction_is_allowed(self):
        decision = check_data_target(
            data_classes=[DataClass.PERSONAL_DATA],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=True,
            approval_given=False,
            provider_profile_active=True,
        )
        assert decision in (PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE)

    def test_hr_without_redaction_requires_approval(self):
        decision = check_data_target(
            data_classes=[DataClass.HR],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=False,
            approval_given=False,
            provider_profile_active=True,
        )
        assert decision == PolicyDecision.APPROVAL_REQUIRED

    def test_hr_after_redaction_is_allowed(self):
        decision = check_data_target(
            data_classes=[DataClass.HR],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=True,
            approval_given=False,
            provider_profile_active=True,
        )
        assert decision in (PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE)

    def test_credentials_always_blocked_for_external_llm(self):
        decision = check_data_target(
            data_classes=[DataClass.CREDENTIALS],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=True,  # auch nach Redaction!
            approval_given=True,
            provider_profile_active=True,
        )
        assert decision == PolicyDecision.BLOCK

    def test_special_category_blocked_for_external_llm(self):
        decision = check_data_target(
            data_classes=[DataClass.SPECIAL_CATEGORY],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=True,
            approval_given=True,
            provider_profile_active=True,
        )
        assert decision == PolicyDecision.BLOCK

    def test_public_data_always_allowed(self):
        decision = check_data_target(
            data_classes=[DataClass.PUBLIC],
            target=DataTarget.EXTERNAL_LLM,
            redaction_applied=False,
            approval_given=False,
            provider_profile_active=True,
        )
        assert decision in (PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE)


# ── 2. Provider-Profile ────────────────────────────────────────────────────────

class TestProviderProfiles:
    def test_groq_allows_public(self):
        allowed, reason = check_provider_policy("groq", [DataClass.PUBLIC])
        assert allowed, reason

    def test_groq_allows_personal_data(self):
        """Nach Redaction muss Groq PERSONAL_DATA akzeptieren."""
        allowed, reason = check_provider_policy("groq", [DataClass.PERSONAL_DATA])
        assert allowed, reason

    def test_groq_allows_hr(self):
        allowed, reason = check_provider_policy("groq", [DataClass.HR])
        assert allowed, reason

    def test_groq_blocks_credentials(self):
        allowed, _ = check_provider_policy("groq", [DataClass.CREDENTIALS])
        assert not allowed

    def test_groq_blocks_special_category(self):
        allowed, _ = check_provider_policy("groq", [DataClass.SPECIAL_CATEGORY])
        assert not allowed

    def test_anthropic_allows_personal_data(self):
        allowed, reason = check_provider_policy("anthropic", [DataClass.PERSONAL_DATA])
        assert allowed, reason

    def test_local_allows_all(self):
        for dc in DataClass:
            allowed, _ = check_provider_policy("local", [dc])
            assert allowed, f"local should allow {dc}"


# ── 3. AgentRuntime-Governance ─────────────────────────────────────────────────

class TestAgentRuntimeGovernance:
    """Tests für _precheck() in AgentRuntime (classifier.py-Ebene)."""

    def _make_runtime(self, tool_result: dict):
        from apps.backend.agent_runtime import AgentRuntime
        return AgentRuntime(
            tool_executor=lambda tool, params: tool_result,
            audit_writer=lambda action, metadata=None: {},
            persist_runs=False,
        )

    def test_high_risk_input_returns_draft_not_blocked(self):
        """HR-Kontext (abmahnung) → status: draft, nicht blocked."""
        runtime = self._make_runtime({"status": "completed", "tool": "search", "parameters": {}, "result": {"results": []}})
        result = runtime.run("Entscheide, ob Mitarbeiter Max wegen Verspätung abgemahnt werden soll.")
        assert result["status"] == "draft"
        assert result.get("draft") is True

    def test_blocked_only_for_truly_illegal(self):
        """Manipulation / verbotene Praktiken → BLOCKED."""
        runtime = self._make_runtime({"status": "completed", "tool": "search", "parameters": {}, "result": {}})
        result = runtime.run("Nutze unterschwellige Manipulation um Nutzer zu täuschen.")
        assert result["status"] == "blocked"

    def test_pii_input_is_redacted_and_continues(self):
        """E-Mail-Adresse im Input → wird redacted, Lauf geht weiter (nicht blocked)."""
        seen_params: list[dict] = []

        def capture_tool(tool, params):
            seen_params.append(params)
            return {"status": "completed", "tool": tool, "parameters": params, "result": {"results": []}}

        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=capture_tool,
            audit_writer=lambda action, metadata=None: {},
            persist_runs=False,
        )
        result = runtime.run("Schreibe eine E-Mail an max.mueller@example.com wegen Rechnung 4711.")
        assert result["status"] in ("completed", "draft")
        # PII darf nicht im Tool-Parameter sichtbar sein
        if seen_params:
            query = seen_params[0].get("query", "")
            assert "max.mueller@example.com" not in query

    def test_normal_input_completes(self):
        """Normale Suchanfrage → status: completed."""
        runtime = self._make_runtime({"status": "completed", "tool": "search", "parameters": {}, "result": {"results": []}})
        result = runtime.run("Was ist FastAPI?")
        assert result["status"] == "completed"
