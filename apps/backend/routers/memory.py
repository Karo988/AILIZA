from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from ..memory import MemoryEntry, MemoryPurpose, VisibilityLevel
from ..memory.sqlite_store import SqliteMemoryStore

router = APIRouter(prefix="/memory", tags=["memory"])

_store: SqliteMemoryStore | None = None


def get_store() -> SqliteMemoryStore:
    global _store
    if _store is None:
        _store = SqliteMemoryStore()
    return _store


class MemoryEntryCreate(BaseModel):
    purpose: MemoryPurpose
    content_hash: str
    visibility: VisibilityLevel
    role_required: str
    retention_until: datetime
    sensitive: bool = True

    @field_validator("retention_until")
    @classmethod
    def must_be_future(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= datetime.now(timezone.utc):
            raise ValueError("retention_until muss in der Zukunft liegen")
        return v


def serialize_entry(entry: MemoryEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "purpose": entry.purpose.value,
        "content_hash": entry.content_hash,
        "visibility": entry.visibility.value,
        "role_required": entry.role_required,
        "retention_until": entry.retention_until.isoformat(),
        "created_at": entry.created_at.isoformat(),
        "deactivated_at": entry.deactivated_at.isoformat() if entry.deactivated_at else None,
        "sensitive": entry.sensitive,
    }


@router.post("", status_code=201)
def create_entry(payload: MemoryEntryCreate) -> dict[str, Any]:
    entry = MemoryEntry(
        purpose=payload.purpose,
        content_hash=payload.content_hash,
        visibility=payload.visibility,
        role_required=payload.role_required,
        retention_until=payload.retention_until,
        sensitive=payload.sensitive,
    )
    get_store().add(entry)
    return serialize_entry(entry)


@router.get("")
def list_entries() -> list[dict[str, Any]]:
    return [serialize_entry(e) for e in get_store().list_active()]


@router.get("/{entry_id}")
def get_entry(entry_id: str) -> dict[str, Any]:
    entry = get_store().get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return serialize_entry(entry)


@router.delete("/{entry_id}", status_code=200)
def deactivate_entry(entry_id: str) -> dict[str, Any]:
    ok = get_store().deactivate(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory entry not found or already deactivated")
    return {"id": entry_id, "status": "deactivated"}


@router.post("/purge", status_code=200)
def purge_expired() -> dict[str, Any]:
    count = get_store().purge_expired()
    return {"purged": count}
