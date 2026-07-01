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
    redacted_text: Optional[str] = None
    message: str = ""
    approval_request_id: Optional[str] = None


class PolicyEngine:
    """Smart escalation: detects secrets, special categories, attempts safe redaction."""

    @staticmethod
    def process_with_policy(task: str, user_id: str, redaction_fn=None) -> PolicyDecision:
        """
        Main policy check. Returns decision with escalation level.

        Args:
            task: User input text
            user_id: User ID for approval tracking
            redaction_fn: Optional function(text) -> redacted_text for safe redaction

        Returns:
            PolicyDecision with decision, risk_level, detected categories
        """

        # 1. Check for secrets (always block)
        secrets = PIITaxonomy.detect_secrets(task)
        if secrets:
            return PolicyDecision(
                decision="block",
                risk_level="red",
                detected_secrets=secrets,
                detected_special_categories=[],
                message="Secrets detected: task cannot be processed.",
            )

        # 2. Check for DSGVO Art. 9 special categories (approval required)
        special_cats = PIITaxonomy.detect_special_categories(task)
        if special_cats:
            return PolicyDecision(
                decision="approval_required",
                risk_level="orange",
                detected_secrets=[],
                detected_special_categories=special_cats,
                message="Special categories (Art. 9 DSGVO) detected: approval required.",
            )

        # 3. Try safe redaction
        if redaction_fn:
            try:
                redacted_text = redaction_fn(task)
                # If redaction was successful, return yellow (redacted)
                return PolicyDecision(
                    decision="redact",
                    risk_level="yellow",
                    detected_secrets=[],
                    detected_special_categories=[],
                    redacted_text=redacted_text,
                    message="Text redacted. Safe for processing.",
                )
            except Exception as e:
                # Redaction failed, escalate to orange
                return PolicyDecision(
                    decision="approval_required",
                    risk_level="orange",
                    detected_secrets=[],
                    detected_special_categories=["redaction_failed"],
                    message=f"Redaction validation failed: approval required.",
                )

        # 4. No special categories, no secrets → green
        return PolicyDecision(
            decision="allow",
            risk_level="green",
            detected_secrets=[],
            detected_special_categories=[],
            redacted_text=task,
            message="No sensitive data detected: approved.",
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
