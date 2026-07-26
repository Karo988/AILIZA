"""
ACHTUNG — nicht-produktiver technischer Prototyp (Quarantäne, M0)
===================================================================
Dieser Router ist im aktuellen `main` NICHT registriert (kein
`app.include_router(...)`-Aufruf in `apps/backend/main.py`) und es wurde
kein interner Aufrufer gefunden. Er gehört zu `apps/backend/memory/`
(`MemoryEntry`/`MemoryStore`/`SqliteMemoryStore`) -- einem eigenständigen,
technischen Hash-only-Speicher (eigene SQLite-Datei, siehe
`apps/backend/memory/sqlite_store.py`) für Zwecke wie Session-/Audit-
Merkmale. Er ist NICHT identisch mit dem fachlichen Memory-Kern
(`memory_items`/`memory_sources`/`memory_visibility`/`memory_suggestions`
in `apps/backend/database.py`, ueber `apps/backend/permissions.py`
abgesichert) und darf mit diesem nicht vermischt werden.

Ursprünglicher Fehler (vor diesem Commit): `from ..auth import
require_admin` importierte aus einem nicht mehr existierenden Symbol --
`apps/backend/auth/__init__.py` (Package) exportiert kein `require_admin`;
dieses Symbol existiert nur in der separaten, veralteten Datei
`apps/backend/auth.py` (altes Operator/API-Key-Schema), die vom
gleichnamigen Package verdeckt wird und nicht Teil des aktuellen RBAC-/
Permission-Systems ist. Ein Import von dort waere schlicht falsch
gewesen -- dieser Router bekommt daher KEIN eigenes zweites
Auth-/API-Key-System, sondern eine dedizierte Fail-Closed-Sperre (siehe
unten), bis (falls je gewuenscht) eine bewusste Integrations-Entscheidung
getroffen wird.

Fail-Closed-Quarantäne (M0):
  Jeder Endpunkt haengt zusaetzlich von `_quarantine_guard()` ab, die
  IMMER 503 wirft -- unabhaengig von Credentials, Rolle oder Tenant.
  Selbst wenn dieser Router versehentlich registriert würde (z.B. durch
  ein zukünftiges `include_router()` ohne Rücksprache), sind KEINE
  nutzbaren Endpunkte erreichbar. Das ist bewusst strenger als eine reine
  Admin-Prüfung, da für dieses Prototyp-Modul keine Rollen-/Tenant-Logik
  definiert oder geprüft wurde -- Default Deny statt stillschweigender
  Wiederverwendung von Produktions-Rollenlogik, die hier nicht passt.

  Vor einer produktiven Nutzung (Registrierung in main.py) waere
  mindestens noetig: echte Authentifizierung ueber
  `apps.backend.auth.require_role`/`evaluate_permission`, Abgrenzung der
  hier verwendeten Konzepte (`MemoryPurpose`, `VisibilityLevel`) vom
  fachlichen Memory-Kern, und eine bewusste Entscheidung, ob dieses
  Modul ueberhaupt weiterbetrieben oder entfernt wird (siehe HANDOFF im
  PR-Beschreibungstext). Bis dahin bleibt dieser Router unregistriert
  und quarantänisiert.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from ..memory import MemoryEntry, MemoryPurpose, VisibilityLevel
from ..memory.sqlite_store import SqliteMemoryStore

router = APIRouter(prefix="/memory", tags=["memory-prototype-quarantined"])

_store: SqliteMemoryStore | None = None


def _quarantine_guard() -> None:
    """Fail-closed: dieser technische Prototyp ist grundsaetzlich nicht
    produktiv nutzbar. Weder Rolle noch Tenant noch Owner werden hier
    geprueft -- ausschliesslich bedingungslose Ablehnung, unabhaengig
    davon, ob/wie dieser Router eingebunden wird."""
    raise HTTPException(
        status_code=503,
        detail=(
            "Dieser technische Memory-Prototyp ist nicht fuer produktiven "
            "Zugriff freigegeben (Quarantaene, siehe Moduldokumentation)."
        ),
    )


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


class MemoryEntryResponse(BaseModel):
    id: str
    purpose: MemoryPurpose
    content_hash: str
    visibility: VisibilityLevel
    role_required: str
    retention_until: datetime
    created_at: datetime
    deactivated_at: Optional[datetime]
    sensitive: bool


class DeactivateResponse(BaseModel):
    id: str
    status: str


class PurgeResponse(BaseModel):
    purged: int


def _to_response(entry: MemoryEntry) -> MemoryEntryResponse:
    return MemoryEntryResponse(
        id=entry.id,
        purpose=entry.purpose,
        content_hash=entry.content_hash,
        visibility=entry.visibility,
        role_required=entry.role_required,
        retention_until=entry.retention_until,
        created_at=entry.created_at,
        deactivated_at=entry.deactivated_at,
        sensitive=entry.sensitive,
    )


@router.post("", status_code=201, response_model=MemoryEntryResponse)
def create_entry(payload: MemoryEntryCreate, _guard: None = Depends(_quarantine_guard)) -> MemoryEntryResponse:
    entry = MemoryEntry(
        purpose=payload.purpose,
        content_hash=payload.content_hash,
        visibility=payload.visibility,
        role_required=payload.role_required,
        retention_until=payload.retention_until,
        sensitive=payload.sensitive,
    )
    get_store().add(entry)
    return _to_response(entry)


@router.get("", response_model=list[MemoryEntryResponse])
def list_entries(_guard: None = Depends(_quarantine_guard)) -> list[MemoryEntryResponse]:
    return [_to_response(e) for e in get_store().list_active()]


@router.get("/{entry_id}", response_model=MemoryEntryResponse)
def get_entry(entry_id: str, _guard: None = Depends(_quarantine_guard)) -> MemoryEntryResponse:
    entry = get_store().get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Memory entry not found")
    return _to_response(entry)


@router.delete("/{entry_id}", status_code=200, response_model=DeactivateResponse)
def deactivate_entry(entry_id: str, _guard: None = Depends(_quarantine_guard)) -> DeactivateResponse:
    ok = get_store().deactivate(entry_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory entry not found or already deactivated")
    return DeactivateResponse(id=entry_id, status="deactivated")


@router.post("/purge", status_code=200, response_model=PurgeResponse)
def purge_expired(_guard: None = Depends(_quarantine_guard)) -> PurgeResponse:
    count = get_store().purge_expired()
    return PurgeResponse(purged=count)
