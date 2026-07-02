"""
Policy Engine: Smart data classification and escalation logic.

Implements 4-tier decision system:
  🟢 Green (allow)    → No secrets, no special categories, redactable
  🟡 Yellow (redacted) → Contains normal/sensitive data, can be redacted
  🟠 Orange (approval) → Contains special categories (Art. 9), needs approval
  🔴 Red (block)      → Contains secrets, never allow

Status: Bereit für kontrollierte Testumgebung und Governance-Review.
Nicht produktionsreif. Nicht zertifiziert.
"""

from dataclasses import dataclass
from typing import Optional
from policies.pii_taxonomy import PIITaxonomy


@dataclass
class PolicyDecision:
    """Result of policy check."""
    decision: str  # "allow" (green) | "redact" (yellow) | "approval_required" (orange) | "block" (red)
    risk_level: str  # "green" | "yellow" | "orange" | "red"
    detected_secrets: list[str]
    detected_special_categories: list[str]
    high_risk_contexts: list[tuple[str, str]] = None  # [(reason_code, label), ...]
    redacted_text: Optional[str] = None
    message: str = ""
    approval_request_id: Optional[str] = None
    reason_code: Optional[str] = None  # For audit: normalized code only

    def __post_init__(self):
        if self.high_risk_contexts is None:
            self.high_risk_contexts = []


class PolicyEngine:
    """Smart escalation: detects secrets, special categories, high-risk contexts."""

    # Data class decision matrix for third country transfers
    DATA_CLASS_THIRD_COUNTRY_DECISION = {
        "public": "allow_with_notice",
        "internal": "require_approval",
        "confidential": "block",
        "personal": "block",
        "sensitive": "block",
        "secret": "block",
    }

    @staticmethod
    def process_with_policy(
        task: str,
        user_id: str,
        redaction_fn=None,
        data_class: str = "personal",  # default to personal
    ) -> PolicyDecision:
        """
        Main policy check. Returns decision with escalation level.

        Args:
            task: User input text
            user_id: User ID for approval tracking
            redaction_fn: Optional function(text) -> redacted_text for safe redaction
            data_class: Data classification (public, internal, confidential, personal, sensitive, secret)

        Returns:
            PolicyDecision with decision, risk_level, detected categories
        """

        # 1. Check for secrets (always block immediately)
        secrets = PIITaxonomy.detect_secrets(task)
        if secrets:
            return PolicyDecision(
                decision="block",
                risk_level="red",
                detected_secrets=secrets,
                detected_special_categories=[],
                reason_code="SECRET_DETECTED",
                message="Geheimnisse erkannt: Anfrage kann nicht verarbeitet werden.",
            )

        # 2. Check for DSGVO Art. 9 special categories
        special_cats = PIITaxonomy.detect_special_categories(task)

        # 3. Check for high-risk contexts (HR+Health, Automated Decision, etc.)
        high_risk_contexts = PIITaxonomy.detect_high_risk_context(task, special_cats)

        # 4. Handle high-risk contexts
        if high_risk_contexts:
            # Extract reason codes for audit
            reason_codes = [rc for rc, _ in high_risk_contexts]

            # Special handling for third country unclear (data-class dependent)
            if "HIGH_RISK_THIRD_COUNTRY_UNCLEAR" in reason_codes:
                decision_type = PolicyEngine.DATA_CLASS_THIRD_COUNTRY_DECISION.get(data_class, "require_approval")
                if decision_type == "block":
                    return PolicyDecision(
                        decision="block",
                        risk_level="red",
                        detected_secrets=[],
                        detected_special_categories=special_cats,
                        high_risk_contexts=high_risk_contexts,
                        reason_code="HIGH_RISK_THIRD_COUNTRY_UNCLEAR",
                        message="Drittlandtransfer unklar: Datenklasse erfordert Blockade.",
                    )
                elif decision_type == "require_approval":
                    return PolicyDecision(
                        decision="approval_required",
                        risk_level="orange",
                        detected_secrets=[],
                        detected_special_categories=special_cats,
                        high_risk_contexts=high_risk_contexts,
                        reason_code="HIGH_RISK_THIRD_COUNTRY_UNCLEAR",
                        message="Drittlandtransfer unklar: Genehmigung erforderlich.",
                    )
                else:  # allow_with_notice
                    return PolicyDecision(
                        decision="allow",
                        risk_level="yellow",
                        detected_secrets=[],
                        detected_special_categories=special_cats,
                        high_risk_contexts=high_risk_contexts,
                        reason_code="HIGH_RISK_THIRD_COUNTRY_UNCLEAR_PUBLIC",
                        message="Drittlandtransfer unklar, aber öffentliche Daten: Hinweis erforderlich.",
                    )

            # All other high-risk contexts → block
            return PolicyDecision(
                decision="block",
                risk_level="red",
                detected_secrets=[],
                detected_special_categories=special_cats,
                high_risk_contexts=high_risk_contexts,
                reason_code=reason_codes[0] if reason_codes else "HIGH_RISK_CONTEXT",
                message=f"Hochrisiko erkannt: {high_risk_contexts[0][1]}",
            )

        # 5. Check for DSGVO Art. 9 special categories (approval required)
        if special_cats:
            return PolicyDecision(
                decision="approval_required",
                risk_level="orange",
                detected_secrets=[],
                detected_special_categories=special_cats,
                reason_code="SPECIAL_CATEGORY_DETECTED",
                message="Besondere Kategorien personenbezogener Daten erkannt: Genehmigung erforderlich.",
            )

        # 6. Try safe redaction
        if redaction_fn:
            try:
                redacted_text = redaction_fn(task)
                # If redaction was successful, return yellow (redacted)
                return PolicyDecision(
                    decision="redact",
                    risk_level="yellow",
                    detected_secrets=[],
                    detected_special_categories=[],
                    reason_code="REDACTED",
                    redacted_text=redacted_text,
                    message="Text redigiert. Sicher für Verarbeitung.",
                )
            except Exception as e:
                # Redaction failed, escalate to orange
                return PolicyDecision(
                    decision="approval_required",
                    risk_level="orange",
                    detected_secrets=[],
                    detected_special_categories=["redaction_failed"],
                    reason_code="REDACTION_FAILED",
                    message="Redaction-Validierung fehlgeschlagen: Genehmigung erforderlich.",
                )

        # 7. No special categories, no secrets, no high-risk → green
        return PolicyDecision(
            decision="allow",
            risk_level="green",
            detected_secrets=[],
            detected_special_categories=[],
            reason_code="SAFE",
            redacted_text=task,
            message="Keine sensiblen Daten erkannt: freigegeben.",
        )

    @staticmethod
    def block_with_policy_error(user_is_admin: bool, detected_categories: list[str],
                                 file_path: str = None, line_number: int = None,
                                 error_code: str = "policy_violation") -> str:
        """
        Generate appropriate error message based on user role.

        Admin sees technical details, regular user sees German-only message.
        """

        # Build category descriptions
        category_labels = [PIITaxonomy.get_category_label(cat) for cat in detected_categories]

        if user_is_admin:
            msg = f"Policy violation: {', '.join(category_labels)}"
            if file_path and line_number:
                msg += f" (detected in {file_path}:{line_number})"
            msg += f" [code: {error_code}]"
            return msg
        else:
            # German-only for non-admin
            return "Die Anfrage enthält geschützte Daten und kann nicht verarbeitet werden. Bitte kontaktieren Sie den Support."
