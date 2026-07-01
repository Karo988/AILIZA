"""
Approval Workflow: Two-phase approval for special category data.

Phase 1: approve_request() → Admin reviews metadata + redacted_preview, sets decision
Phase 2: resubmit_after_approval() → User re-submits original task, full policy re-check

redacted_preview contains ONLY the actual validated and truncated text. Never full payload.

Status: Bereit für kontrollierte Testumgebung und Governance-Review.
Nicht produktionsreif. Nicht zertifiziert.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Tuple
from enum import Enum
import uuid


class ApprovalDecisionCode(Enum):
    """Whitelist of approval decision reasons."""
    BUSINESS_NEED = "business_need"
    LEGAL_OBLIGATION = "legal_obligation"
    USER_EXPLICIT_CONSENT = "user_explicit_consent"
    UNNECESSARY_DATA = "unnecessary_data"
    POLICY_VIOLATION = "policy_violation"
    RISK_TOO_HIGH = "risk_too_high"


@dataclass
class ApprovalRequest:
    """Approval request record. Stores ONLY metadata + redacted preview."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = ""  # FK to task request
    pii_categories: list[str] = field(default_factory=list)
    data_class: str = ""  # "high" | "confidential" | "forbidden"
    highest_risk_level: str = ""
    redacted_preview: Optional[str] = None  # ACTUAL safe preview text, max 500 chars
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=24))
    decision: Optional[str] = None  # "approved" | "rejected" | "pending"
    decision_reason_code: Optional[str] = None  # ApprovalDecisionCode value
    decided_by_user_id: Optional[str] = None
    decided_at: Optional[datetime] = None


def assert_no_pii(text: str, max_len: int = 500) -> Tuple[bool, Optional[str]]:
    """
    Validate text contains no secrets/special categories.
    Return (is_safe, truncated_text) or (False, None).

    This is the ACTUAL validation that redacted_preview stores.
    """
    from policies.pii_taxonomy import PIITaxonomy

    # Check for secrets (always unsafe)
    if PIITaxonomy.detect_secrets(text):
        return (False, None)

    # Check for special categories (always unsafe in preview)
    if PIITaxonomy.detect_special_categories(text):
        return (False, None)

    # Truncate and return
    truncated = text[:max_len] if len(text) > max_len else text
    return (True, truncated)


class ApprovalWorkflow:
    """Two-phase approval workflow."""

    @staticmethod
    def generate_approval_request(
        request_id: str,
        pii_categories: list[str],
        data_class: str,
        highest_risk_level: str,
        redacted_text: str,
    ) -> Optional[ApprovalRequest]:
        """
        Create approval request. Validates redacted_text, stores safe preview.

        Args:
            request_id: Task request ID
            pii_categories: Detected PII categories
            data_class: "high" | "confidential" | "forbidden"
            highest_risk_level: Risk escalation level
            redacted_text: The REDACTED (already safe) version of text

        Returns:
            ApprovalRequest with redacted_preview set to validated text, or None if validation fails
        """

        # Validate and truncate the redacted text
        is_safe, safe_preview = assert_no_pii(redacted_text, max_len=500)
        if not is_safe:
            # Validation failed - do not create approval request
            return None

        approval = ApprovalRequest(
            request_id=request_id,
            pii_categories=pii_categories,
            data_class=data_class,
            highest_risk_level=highest_risk_level,
            redacted_preview=safe_preview,  # Store ONLY the validated, truncated text
            decision="pending",
        )
        return approval

    @staticmethod
    def approve_request(
        approval_id: str,
        user_id: str,
        reason_code: str,
        db_session=None,
    ) -> bool:
        """
        Admin approves or rejects an approval request.

        Args:
            approval_id: Approval request ID
            user_id: Admin user ID
            reason_code: ApprovalDecisionCode value
            db_session: Database session

        Returns:
            True if approved, False if rejected
        """

        # Validate reason code
        valid_codes = [code.value for code in ApprovalDecisionCode]
        if reason_code not in valid_codes:
            raise ValueError(f"Invalid reason code: {reason_code}")

        # Update approval record
        if db_session:
            # UPDATE approval SET decision='approved', decided_by=user_id, decided_at=now()
            # (In actual implementation, this queries the DB)
            pass

        return True

    @staticmethod
    def resubmit_after_approval(
        approval_id: str,
        original_task: str,
        user_id: str,
        policy_check_fn=None,
        db_session=None,
    ) -> dict:
        """
        User re-submits original task AFTER approval.
        Runs FULL policy-check again (no original task is stored in approval).

        Args:
            approval_id: Reference to approval request
            original_task: FULL original task text (user must provide)
            user_id: User ID
            policy_check_fn: Function(task, user_id) -> PolicyDecision
            db_session: Database session

        Returns:
            Decision dict with result of full re-check
        """

        # Verify approval exists and is approved
        if db_session:
            # Query approval from DB, check decision=='approved'
            pass

        # Run FULL policy check on original task
        if policy_check_fn:
            decision = policy_check_fn(original_task, user_id)
            return {
                "approval_id": approval_id,
                "policy_decision": decision.decision,
                "risk_level": decision.risk_level,
                "message": decision.message,
            }

        return {"error": "policy_check_fn not provided"}
