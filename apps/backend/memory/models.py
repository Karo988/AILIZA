"""
AILIZA Memory Models
====================
DSGVO Art. 5: Zweckbindung, Datensparsamkeit, Speicherbegrenzung
DSGVO Art. 25: Privacy by Design — sensitiv ist der Default, nicht die Ausnahme

BS-14: Zweckbindung je Memory-Eintrag (purpose + retention_until Pflichtfelder)
BS-15: Sichtbarkeit/Rolle (visibility + role_required)
BS-16: Aufbewahrungsfrist (retention_until, is_expired)
BS-17: Lösch-/Deaktivierungslogik (deactivate, Soft-delete via deactivated_at)
BS-18: Keine Vollspeicherung sensibler Inhalte als Default (sensitive=True, content_hash statt Klartext)
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class MemoryPurpose(str, Enum):
    TASK = "TASK"           # Aufgaben-Kontext, endet mit Session
    SESSION = "SESSION"     # Sitzungs-Kontext, kurzlebig
    AUDIT = "AUDIT"         # Audit-Referenz, nur Metadaten
    CONSENT = "CONSENT"     # Einwilligungs-Nachweis, langlebig


class VisibilityLevel(str, Enum):
    USER = "USER"           # Nur der betreffende Nutzer
    OPERATOR = "OPERATOR"   # Operator + Nutzer
    SYSTEM = "SYSTEM"       # Nur System-intern, niemals nach außen


@dataclass
class MemoryEntry:
    """
    Minimale, zweckgebundene Memory-Einheit.

    Invarianten:
    - content_hash enthält niemals Klartext sensitiver Inhalte
    - sensitive=True ist der Default — Opt-out, nicht Opt-in (BS-18)
    - retention_until ist Pflicht — kein ewiges Speichern (BS-16)
    - deactivate() ist der einzige Löschpfad — kein Hard-delete ohne Audit (BS-17)
    """

    purpose: MemoryPurpose
    content_hash: str           # SHA-256 des Inhalts — niemals Klartext sensitiv
    visibility: VisibilityLevel
    role_required: str          # z.B. "user", "operator", "admin"
    retention_until: datetime   # Pflicht — kein ewiges Speichern

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    deactivated_at: Optional[datetime] = None
    sensitive: bool = True      # Default: sensitiv (BS-18)

    def __post_init__(self) -> None:
        if self.retention_until.tzinfo is None:
            raise ValueError("retention_until muss timezone-aware sein (UTC)")
        if self.created_at > self.retention_until:
            raise ValueError("retention_until muss in der Zukunft liegen")

    # ── Zustands-Abfragen ─────────────────────────────────────────────────

    def is_active(self) -> bool:
        return self.deactivated_at is None

    def is_expired(self) -> bool:
        """True wenn Aufbewahrungsfrist abgelaufen (BS-16)."""
        return datetime.now(timezone.utc) > self.retention_until

    def is_accessible_by(self, role: str) -> bool:
        """Prüft ob Rolle ausreichend für Sichtbarkeit (BS-15)."""
        if not self.is_active():
            return False
        hierarchy = {
            VisibilityLevel.USER: {"user", "operator", "admin"},
            VisibilityLevel.OPERATOR: {"operator", "admin"},
            VisibilityLevel.SYSTEM: {"admin"},
        }
        return role in hierarchy.get(self.visibility, set())

    # ── Mutation ──────────────────────────────────────────────────────────

    def deactivate(self) -> None:
        """Soft-delete — kein Hard-delete ohne separaten Audit-Eintrag (BS-17)."""
        if self.deactivated_at is not None:
            return
        self.deactivated_at = datetime.now(timezone.utc)

    # ── Hilfsfunktion ─────────────────────────────────────────────────────

    @staticmethod
    def hash_content(content: str) -> str:
        """SHA-256 Hash eines Inhalts — niemals den Originalinhalt speichern."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
