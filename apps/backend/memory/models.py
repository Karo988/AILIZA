from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid

class MemoryPurpose(str, Enum):
    TASK = "task"
    SESSION = "session"
    AUDIT = "audit"
    CONSENT = "consent"

class VisibilityLevel(str, Enum):
    USER = "user"
    OPERATOR = "operator"
    SYSTEM = "system"

@dataclass
class MemoryEntry:
    purpose: MemoryPurpose
    content_hash: str
    visibility: VisibilityLevel
    role_required: str
    retention_until: datetime
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    deactivated_at: Optional[datetime] = None
    sensitive: bool = True

    def __post_init__(self):
        # Nur Timezone-Check — keine Business-Logik hier
        if self.retention_until.tzinfo is None:
            raise ValueError("retention_until muss timezone-aware sein")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at muss timezone-aware sein")

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.retention_until

    def deactivate(self) -> None:
        self.deactivated_at = datetime.now(timezone.utc)

    def is_active(self) -> bool:
        return self.deactivated_at is None
