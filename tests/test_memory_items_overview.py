"""Persönliche-Gedächtnis-Übersicht: gezieltes Lesen/Korrigieren/Löschen
EINES einzelnen memory_item (bisher nur Alles-oder-nichts über
delete_own_account_data()).

Scope: apps/backend/database.py (update_memory_item, delete_memory_item),
apps/backend/main.py (GET/PATCH/DELETE /api/memory-items). Prüft vor allem
die Scope-/Owner-/Tenant-Trennung, die der memory-invariant-reviewer
verlangt: ein Nutzer darf nur eigenes, aktives user_memory ändern -- nie
company_memory, nie fremdes user_memory, nie über Mandantengrenzen hinweg.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.database import (
    metadata_obj, engine, init_db, create_user, upsert_user_settings,
    create_memory_suggestion, confirm_memory_suggestion,
    list_active_memory_items_for_user, get_memory_item,
    update_memory_item, delete_memory_item,
    MemoryValidationError,
)


def _confirmed_company_item(tenant_id: str = "default") -> dict:
    """Erzeugt einen aktiven company_memory-Eintrag ueber den regulaeren
    Vorschlag-/Freigabe-Pfad (braucht eine admin-Rolle), damit source_id
    und alle Pflichtfelder wie im echten Betrieb gesetzt sind."""
    s = create_memory_suggestion(
        user_id="admin-karo", tenant_id=tenant_id, suggested_scope="company_memory",
        suggested_title="Firmenwissen", suggested_content="DATEV wird genutzt.",
        suggested_purpose="Kontext", source_type="user_confirmation",
    )
    result = confirm_memory_suggestion(
        s["id"], confirmed_by="admin-karo", tenant_id=tenant_id, reviewer_role="admin",
    )
    return get_memory_item(result["memory_item_id"], tenant_id=tenant_id)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str, tenant_id: str = "default") -> None:
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")
    upsert_user_settings(user_id, tenant_id, speichermodus="immer_fragen")


def _confirmed_item(user_id: str, tenant_id: str = "default", *, title="Kurze Antworten",
                    content="Nutzer bevorzugt kurze Antworten.") -> dict:
    s = create_memory_suggestion(
        user_id=user_id, tenant_id=tenant_id, suggested_scope="user_memory",
        suggested_title=title, suggested_content=content,
        suggested_purpose="Antwortstil", source_type="user_confirmation",
    )
    result = confirm_memory_suggestion(s["id"], confirmed_by=user_id, tenant_id=tenant_id)
    return get_memory_item(result["memory_item_id"], tenant_id=tenant_id)


# ── Liste: nur eigenes, aktives user_memory ─────────────────────────────────

def test_list_only_own_active_user_memory():
    _make_user("alice")
    _make_user("bob")
    _confirmed_item("alice")
    _confirmed_item("bob")
    alice_items = list_active_memory_items_for_user("alice", "default")
    assert len(alice_items) == 1
    assert alice_items[0]["owner_user_id"] == "alice"


def test_list_excludes_company_memory():
    _make_user("alice")
    _make_user("admin-karo")
    _confirmed_company_item()
    assert list_active_memory_items_for_user("alice", "default") == []


# ── Korrektur: nur eigenes, aktives user_memory ─────────────────────────────

def test_update_own_item_succeeds():
    _make_user("alice")
    item = _confirmed_item("alice")
    updated = update_memory_item(
        item["id"], tenant_id="default", owner_user_id="alice", title="Neuer Titel",
    )
    assert updated["title"] == "Neuer Titel"
    assert updated["content"] == item["content"]  # nicht angegeben -> unveraendert


def test_update_foreign_item_rejected():
    _make_user("alice")
    _make_user("bob")
    item = _confirmed_item("alice")
    with pytest.raises(MemoryValidationError):
        update_memory_item(item["id"], tenant_id="default", owner_user_id="bob", title="Uebernommen")
    # unveraendert:
    unchanged = get_memory_item(item["id"], tenant_id="default")
    assert unchanged["title"] == item["title"]


def test_update_across_tenant_rejected():
    # user_id ist global eindeutig (siehe users-Tabelle) -- fuer den
    # Tenant-Grenzfall genuegt es, denselben Nutzer mit dem FALSCHEN
    # tenant_id-Parameter aufzurufen; der Eintrag selbst liegt in "default".
    _make_user("alice", tenant_id="default")
    item = _confirmed_item("alice", tenant_id="default")
    with pytest.raises(MemoryValidationError):
        update_memory_item(item["id"], tenant_id="other", owner_user_id="alice", title="x")


def test_update_company_memory_rejected():
    """Ein Nutzer darf company_memory NIE über diesen Pfad ändern -- auch
    nicht, wenn er zufällig die richtige item_id/tenant_id/owner_user_id-
    Kombination erraten könnte (owner_user_id ist bei company_memory NULL,
    kann also nie mit einem echten Nutzer übereinstimmen)."""
    _make_user("admin-karo")
    company_item = _confirmed_company_item()
    with pytest.raises(MemoryValidationError):
        update_memory_item(
            company_item["id"], tenant_id="default", owner_user_id="admin-karo", title="x",
        )


def test_update_secret_content_blocked():
    _make_user("alice")
    item = _confirmed_item("alice")
    with pytest.raises(MemoryValidationError):
        update_memory_item(
            item["id"], tenant_id="default", owner_user_id="alice",
            content="Mein API-Key ist sk-abcdefghijklmnopqrstuvwxyz123456",
        )
    unchanged = get_memory_item(item["id"], tenant_id="default")
    assert unchanged["content"] == item["content"]


def test_update_already_deleted_item_rejected():
    """Eine Korrektur darf einen geloeschten Eintrag nicht wieder aktivieren."""
    _make_user("alice")
    item = _confirmed_item("alice")
    delete_memory_item(item["id"], tenant_id="default", owner_user_id="alice")
    with pytest.raises(MemoryValidationError):
        update_memory_item(item["id"], tenant_id="default", owner_user_id="alice", title="wieder da?")


# ── Löschen: nur eigenes, aktives user_memory, nur soft-delete ─────────────

def test_delete_own_item_soft_deletes():
    _make_user("alice")
    item = _confirmed_item("alice")
    delete_memory_item(item["id"], tenant_id="default", owner_user_id="alice")
    deleted = get_memory_item(item["id"], tenant_id="default")
    assert deleted is not None  # kein Hard-Delete
    assert deleted["status"] == "deleted"
    assert list_active_memory_items_for_user("alice", "default") == []


def test_delete_foreign_item_rejected():
    _make_user("alice")
    _make_user("bob")
    item = _confirmed_item("alice")
    with pytest.raises(MemoryValidationError):
        delete_memory_item(item["id"], tenant_id="default", owner_user_id="bob")
    assert get_memory_item(item["id"], tenant_id="default")["status"] == "active"


def test_delete_across_tenant_rejected():
    _make_user("alice", tenant_id="default")
    item = _confirmed_item("alice", tenant_id="default")
    with pytest.raises(MemoryValidationError):
        delete_memory_item(item["id"], tenant_id="other", owner_user_id="alice")
    assert get_memory_item(item["id"], tenant_id="default")["status"] == "active"


def test_delete_company_memory_rejected():
    _make_user("admin-karo")
    company_item = _confirmed_company_item()
    with pytest.raises(MemoryValidationError):
        delete_memory_item(company_item["id"], tenant_id="default", owner_user_id="admin-karo")
    assert get_memory_item(company_item["id"], tenant_id="default")["status"] == "active"


def test_delete_already_deleted_item_rejected():
    """Ein zweiter Löschversuch meldet 'nicht gefunden', statt stillschweigend
    zu wiederholen -- konsistent mit rowcount==0 als einheitlichem Signal."""
    _make_user("alice")
    item = _confirmed_item("alice")
    delete_memory_item(item["id"], tenant_id="default", owner_user_id="alice")
    with pytest.raises(MemoryValidationError):
        delete_memory_item(item["id"], tenant_id="default", owner_user_id="alice")


def test_delete_nonexistent_item_rejected():
    _make_user("alice")
    with pytest.raises(MemoryValidationError):
        delete_memory_item(999999, tenant_id="default", owner_user_id="alice")
