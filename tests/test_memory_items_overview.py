"""Persoenliche-Gedaechtnis-Uebersicht (update_memory_item/delete_memory_item):
eigene, aktive user_memory-Eintraege korrigieren/loeschen. company_memory und
fremde Eintraege sind durch das WHERE-Muster in der Datenschicht selbst
ausgeschlossen, nicht nur per Konvention (siehe reject_memory_suggestion())."""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.database import (
    metadata_obj, engine, init_db, create_user, upsert_user_settings,
    create_memory_suggestion, confirm_memory_suggestion, get_memory_item,
    list_active_memory_items_for_user, update_memory_item, delete_memory_item,
    MemoryValidationError,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str = "alice") -> None:
    create_user(user_id=user_id, tenant_id="default", role="user", hashed_password="hash")
    upsert_user_settings(user_id, "default", speichermodus="immer_fragen")


def _confirmed_user_memory_item(user_id: str = "alice", tenant_id: str = "default",
                                title: str = "Kurze Antworten",
                                content: str = "Nutzer bevorzugt kurze Antworten.") -> int:
    s = create_memory_suggestion(
        user_id=user_id, tenant_id=tenant_id, suggested_scope="user_memory",
        suggested_title=title, suggested_content=content,
        suggested_purpose="Antwortstil", source_type="user_confirmation",
    )
    result = confirm_memory_suggestion(s["id"], confirmed_by=user_id, tenant_id=tenant_id)
    return result["memory_item_id"]


def test_own_list_shows_confirmed_item():
    _make_user("alice")
    item_id = _confirmed_user_memory_item("alice")
    items = list_active_memory_items_for_user("alice", "default")
    assert len(items) == 1
    assert items[0]["id"] == item_id


def test_foreign_user_sees_nothing():
    _make_user("alice")
    _make_user("bob")
    _confirmed_user_memory_item("alice")
    assert list_active_memory_items_for_user("bob", "default") == []


def test_update_changes_title_content_category():
    _make_user("alice")
    item_id = _confirmed_user_memory_item("alice")
    update_memory_item(item_id, tenant_id="default", owner_user_id="alice",
                       title="Neuer Titel", content="Neuer Inhalt", category="stil")
    item = get_memory_item(item_id, tenant_id="default")
    assert item["title"] == "Neuer Titel"
    assert item["content"] == "Neuer Inhalt"
    assert item["category"] == "stil"


def test_update_foreign_item_raises_not_found():
    _make_user("alice")
    _make_user("bob")
    item_id = _confirmed_user_memory_item("alice")
    with pytest.raises(MemoryValidationError):
        update_memory_item(item_id, tenant_id="default", owner_user_id="bob", title="x")


def test_update_blocks_secret_content():
    _make_user("alice")
    item_id = _confirmed_user_memory_item("alice")
    with pytest.raises(MemoryValidationError):
        update_memory_item(item_id, tenant_id="default", owner_user_id="alice",
                           content="Mein API Key ist sk-abcdefghijklmnop123456")
    # Urspruenglicher Inhalt bleibt unveraendert -- kein Teilschreiben vor dem Check.
    item = get_memory_item(item_id, tenant_id="default")
    assert "sk-abcdefghijklmnop123456" not in item["content"]


def test_delete_soft_deletes_and_hides_from_list():
    _make_user("alice")
    item_id = _confirmed_user_memory_item("alice")
    delete_memory_item(item_id, tenant_id="default", owner_user_id="alice")
    assert list_active_memory_items_for_user("alice", "default") == []
    item = get_memory_item(item_id, tenant_id="default")
    assert item["status"] == "deleted"


def test_delete_foreign_item_raises_not_found():
    _make_user("alice")
    _make_user("bob")
    item_id = _confirmed_user_memory_item("alice")
    with pytest.raises(MemoryValidationError):
        delete_memory_item(item_id, tenant_id="default", owner_user_id="bob")


def test_company_memory_not_reachable_via_user_endpoints():
    _make_user("alice")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="company_memory",
        suggested_title="DATEV", suggested_content="Firma nutzt DATEV.",
        suggested_purpose="Kontext", source_type="user_confirmation",
    )
    result = confirm_memory_suggestion(s["id"], confirmed_by="karo-admin", tenant_id="default", reviewer_role="admin")
    item_id = result["memory_item_id"]
    with pytest.raises(MemoryValidationError):
        update_memory_item(item_id, tenant_id="default", owner_user_id="alice", title="x")
    with pytest.raises(MemoryValidationError):
        delete_memory_item(item_id, tenant_id="default", owner_user_id="alice")
    assert item_id not in {i["id"] for i in list_active_memory_items_for_user("alice", "default")}
