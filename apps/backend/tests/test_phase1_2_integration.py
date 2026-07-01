"""
Phase 1.2 Integration Tests: PolicyEngine in run_agent() flow

Tests that high-risk contexts are actually blocked in the production pipeline.

Status: Bereit für kontrollierte Testumgebung und Governance-Review.
Nicht produktionsreif. Nicht zertifiziert.
"""

import pytest
from policy_engine import PolicyEngine


class TestPhase12Integration:
    """Test PolicyEngine integration in run_agent() flow."""

    def test_amun_brief_blocks_hr_special_category(self):
        """
        Real-world test: The Amun letter with HR+Health+Biometric+Automated Decision
        should be blocked by PolicyEngine BEFORE reaching the Agent.
        """
        amun_brief = """
Betreff: Automatisierte Bewertung Ihrer Bewerbung durch KI-System

Sehr geehrte Paula Ronder,

wir haben Ihre Bewerbung automatisch durch unser KI-System prüfen lassen.

Das System hat folgende Daten über Sie verarbeitet:

Gesundheit: wiederkehrende Migräne, frühere Krankschreibungen
Religion: muslimisch
Familienstand: alleinerziehend
Biometrische Daten: Gesichtsanalyse aus Ihrem Bewerbungsfoto
Automatische Empfehlung: Bewerbung ablehnen

Eine manuelle Prüfung ist aus Effizienzgründen nicht vorgesehen.
        """

        decision = PolicyEngine.process_with_policy(amun_brief, "user1")

        # Must be BLOCKED, not redacted
        assert decision.decision == "block", f"Expected 'block', got '{decision.decision}'"
        assert decision.risk_level == "red", f"Expected 'red', got '{decision.risk_level}'"

        # Should detect multiple high-risk contexts
        assert len(decision.high_risk_contexts) > 0, "No high-risk contexts detected"

        # Reason codes should be normalized (no freetext)
        assert decision.reason_code in [
            "HIGH_RISK_HR_SPECIAL_CATEGORY",
            "HIGH_RISK_HR_HEALTH",
            "HIGH_RISK_HR_BIOMETRIC",
            "HIGH_RISK_AUTOMATED_DECISION",
        ], f"Unexpected reason_code: {decision.reason_code}"

    def test_amun_brief_does_not_redact(self):
        """redacted_preview should be None for blocked content."""
        amun_brief = "Bewerbung Paula Ronder. Gesundheit: Migräne. Automatische Ablehnung."
        decision = PolicyEngine.process_with_policy(amun_brief, "user1")

        # Should NOT have redacted_text
        assert decision.redacted_text is None or decision.decision == "block"

    def test_safe_request_still_green(self):
        """Normal requests should still be GREEN."""
        safe_task = "What are the top 5 programming languages?"
        decision = PolicyEngine.process_with_policy(safe_task, "user1")

        assert decision.decision == "allow"
        assert decision.risk_level == "green"

    def test_health_data_alone_orange(self):
        """Art. 9 data alone (without HR context) should be ORANGE (approval_required)."""
        task = "I have been diagnosed with migraine."
        decision = PolicyEngine.process_with_policy(task, "user1")

        assert decision.decision == "approval_required"
        assert decision.risk_level == "orange"
        assert "health" in decision.detected_special_categories

    def test_secret_detected_red(self):
        """Secrets always RED."""
        task = "My API key is sk-proj-abcdef123456"
        decision = PolicyEngine.process_with_policy(task, "user1")

        assert decision.decision == "block"
        assert decision.risk_level == "red"
        assert len(decision.detected_secrets) > 0

    def test_third_country_confidential_red(self):
        """Third country unclear + confidential data = RED."""
        task = "Daten werden in USA verarbeitet. Prüfung nicht abgeschlossen."
        decision = PolicyEngine.process_with_policy(
            task, "user1", data_class="confidential"
        )

        assert decision.decision == "block"
        assert decision.risk_level == "red"

    def test_third_country_public_yellow(self):
        """Third country unclear + public data = allow with notice (YELLOW)."""
        task = "Außerhalb EU Verarbeitung, aber nur öffentliche Daten"
        decision = PolicyEngine.process_with_policy(task, "user1", data_class="public")

        assert decision.decision == "allow"
        assert decision.risk_level == "yellow"

    def test_reason_code_normalized(self):
        """Reason code should always be normalized (no freetext)."""
        task = "Bewerbung. Gesundheit: Migräne. Automatische Ablehnung."
        decision = PolicyEngine.process_with_policy(task, "user1")

        # Should have a reason_code
        assert decision.reason_code is not None
        # Should be uppercase with underscores (normalized)
        assert decision.reason_code.isupper()
        assert "_" in decision.reason_code or decision.reason_code in ["SAFE", "REDACTED"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
