"""
Legal Hold: Preservation of audit logs with reason code and technical details.

Stores only whitelisted technical details (no free-form text).
Details are copied to clean dict, not modified in-place.

Status (Stand 2026-07-06): Bereit für kontrollierte Testumgebung und
Governance-Review. Nicht produktionsreif. Nicht zertifiziert.

Blocker:
- Keine echte Datenbankanbindung: set_legal_hold() beschreibt das noetige
  SQL nur als Kommentar (# SQL: INSERT INTO legal_holds ...), fuehrt es
  nie aus.
- Keine legal_holds-Tabelle in database.py vorhanden.
- Keine Tests.
- Nirgends in main.py eingebunden (totes Modul).

Aktives Gegenstueck: KEINES. Diese Funktion (Legal Hold auf Audit-Logs)
existiert derzeit nicht produktiv im System.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LegalHoldReasonCode(Enum):
    """Whitelist of legal hold reason codes."""
    INCIDENT_INVESTIGATION = "incident_investigation"
    LITIGATION_RISK = "litigation_risk"
    REGULATORY_REQUEST = "regulatory_request"
    DATA_BREACH = "data_breach"
    COMPLIANCE_AUDIT = "compliance_audit"


# Allowed fields in technical_details
ALLOWED_TECHNICAL_FIELDS = {
    "incident_id",
    "policy_version",
    "source_module",
    "severity",
    "affected_systems",
}


@dataclass
class LegalHold:
    """Record of a legal hold on an audit log."""
    log_id: str
    reason_code: str
    hold_until: datetime
    held_by_user_id: str
    technical_details: dict = None
    created_at: datetime = None

    def __post_init__(self):
        if self.technical_details is None:
            self.technical_details = {}
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class LegalHoldManager:
    """Manage legal holds on audit logs."""

    @staticmethod
    def validate_reason_code(reason_code: str) -> bool:
        """Check if reason code is in whitelist."""

        valid_codes = [code.value for code in LegalHoldReasonCode]
        return reason_code in valid_codes

    @staticmethod
    def validate_hold_until(hold_until: datetime) -> bool:
        """Check if hold_until is in the future."""

        return hold_until > datetime.utcnow()

    @staticmethod
    def sanitize_technical_details(technical_details: dict) -> dict:
        """
        Create clean copy of technical_details with only allowed fields.

        IMPORTANT: Use copy-based cleaning, never modify original dict during iteration.

        Args:
            technical_details: Raw technical details dict

        Returns:
            Cleaned dict with only whitelisted fields
        """

        clean_details = {}

        # Iterate original, only add allowed fields to clean copy
        for key, value in technical_details.items():
            if key in ALLOWED_TECHNICAL_FIELDS:
                clean_details[key] = value

        return clean_details

    @staticmethod
    def set_legal_hold(
        log_id: str,
        reason_code: str,
        hold_until: datetime,
        user_id: str,
        technical_details: Optional[dict] = None,
        db_session=None,
    ) -> LegalHold:
        """
        Set legal hold on an audit log.

        Args:
            log_id: Audit log ID
            reason_code: LegalHoldReasonCode value
            hold_until: Hold until this datetime (must be future)
            user_id: User ID who set the hold
            technical_details: Optional technical metadata (will be sanitized)
            db_session: Database session

        Returns:
            LegalHold record

        Raises:
            ValueError if reason_code or hold_until invalid
        """

        # Validate reason code
        if not LegalHoldManager.validate_reason_code(reason_code):
            raise ValueError(f"Invalid reason code: {reason_code}")

        # Validate hold_until
        if not LegalHoldManager.validate_hold_until(hold_until):
            raise ValueError("hold_until must be a future date")

        # Sanitize technical details
        if technical_details is None:
            technical_details = {}

        clean_details = LegalHoldManager.sanitize_technical_details(technical_details)

        # Create legal hold record
        hold = LegalHold(
            log_id=log_id,
            reason_code=reason_code,
            hold_until=hold_until,
            held_by_user_id=user_id,
            technical_details=clean_details,
        )

        # Persist to DB if session provided
        if db_session:
            try:
                # SQL: INSERT INTO legal_holds (log_id, reason_code, hold_until, held_by_user_id, technical_details)
                # VALUES (...) RETURNING *
                logger.info(
                    f"Legal hold set on log {log_id} by {user_id} "
                    f"with reason {reason_code} until {hold_until}"
                )
            except Exception as e:
                logger.error(f"Failed to persist legal hold: {e}")
                raise

        return hold

    @staticmethod
    def check_legal_hold(log_id: str, db_session=None) -> bool:
        """
        Check if log is currently under legal hold.

        Args:
            log_id: Audit log ID
            db_session: Database session

        Returns:
            True if under active legal hold, False otherwise
        """

        if db_session:
            # SQL: SELECT * FROM legal_holds WHERE log_id = ? AND hold_until > NOW()
            pass

        return False

    @staticmethod
    def release_legal_hold(log_id: str, db_session=None) -> bool:
        """
        Release expired legal hold.

        Args:
            log_id: Audit log ID
            db_session: Database session

        Returns:
            True if hold was released
        """

        if db_session:
            # SQL: UPDATE legal_holds SET hold_until = NOW() WHERE log_id = ?
            logger.info(f"Legal hold released on log {log_id}")

        return True
