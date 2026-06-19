"""
Nutzer-Modelle fuer AILIZA Auth
================================
Passwort-Hashing via bcrypt (direkt, ohne passlib).
Keine Klartextpasswoerter — weder speichern noch loggen.
"""
from __future__ import annotations

from dataclasses import dataclass

try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    _BCRYPT_AVAILABLE = False


@dataclass
class UserCreate:
    user_id: str
    tenant_id: str
    role: str          # "user" | "manager" | "admin" | "dsb"
    plain_password: str


@dataclass
class UserInDB:
    user_id: str
    tenant_id: str
    role: str
    hashed_password: str

    @classmethod
    def from_create(cls, user: UserCreate) -> "UserInDB":
        if not _BCRYPT_AVAILABLE:
            raise RuntimeError("bcrypt nicht installiert.")
        hashed = bcrypt.hashpw(user.plain_password.encode(), bcrypt.gensalt())
        return cls(
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            role=user.role,
            hashed_password=hashed.decode(),
        )

    def verify_password(self, plain: str) -> bool:
        if not _BCRYPT_AVAILABLE:
            return False
        return bcrypt.checkpw(plain.encode(), self.hashed_password.encode())
