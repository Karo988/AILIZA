"""
DSGVO Art. 30 — Verzeichnis von Verarbeitungstätigkeiten.
Niemals Klartextwerte speichern — nur Typen und Anzahl.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from ..database import record_processing, list_processing_records, get_engine
except ImportError:
    from database import record_processing, list_processing_records, get_engine

from sqlalchemy import text


class ProcessingRegistry:
    """Art. 30 Verarbeitungsverzeichnis."""

    def record(
        self,
        user_id: str,
        conversation_id: str,
        message_id: int | None,
        pii_mapping: dict,
        legal_basis: str = "Art. 6 Abs. 1b",
        purpose: str = "Aufgabenerfüllung durch KI-Assistenten",
        recipients: list[str] | None = None,
        retention_days: int = 90,
        consent_given: bool = False,
    ) -> int:
        pii_types: list[str] = []
        for placeholder in pii_mapping:
            ptype = placeholder.strip("[]").rsplit("_", 1)[0]
            if ptype not in pii_types:
                pii_types.append(ptype)

        return record_processing(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            pii_types=pii_types,
            pii_count=len(pii_mapping),
            legal_basis=legal_basis,
            purpose=purpose,
            recipients=recipients or ["AILIZA-Intern (pseudonymisiert)"],
            retention_days=retention_days,
            consent_given=consent_given,
        )

    def export_for_user(self, user_id: str) -> dict[str, Any]:
        """Art. 15 Auskunftsrecht — alle Verarbeitungen eines Nutzers."""
        records = list_processing_records(user_id=user_id)
        return {
            "user_id": user_id,
            "total": len(records),
            "records": records,
            "exported_at": datetime.utcnow().isoformat(),
        }

    def export_full(self) -> dict[str, Any]:
        """Art. 30 Vollständiges Verzeichnis für Datenschutzbeauftragten."""
        records = list_processing_records()
        return {
            "total": len(records),
            "records": records,
            "exported_at": datetime.utcnow().isoformat(),
            "controller": "AILIZA-Betreiber",
            "dpo_note": "Verarbeitungsverzeichnis gemäß Art. 30 DSGVO",
        }

    def acknowledge(self, record_id: int) -> bool:
        try:
            engine = get_engine()
            with engine.begin() as c:
                result = c.execute(
                    text(
                        "UPDATE processing_records SET acknowledged_by_user=1, documented_at=:now "
                        "WHERE id=:id"
                    ),
                    {"now": datetime.utcnow().isoformat(), "id": record_id},
                )
                return result.rowcount > 0
        except Exception:
            return False
