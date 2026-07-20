"""Mini-PR 2: Memory-Kernschema (memory_items, memory_sources, memory_visibility).

Scope (siehe docs/DATABASE_MEMORY_GOVERNANCE_V1.md, Mini-PR 2):
Nur die Datenstruktur fuer sichtbares, kontrolliertes Gedaechtnis. Keine
automatische Erkennung, keine memory_suggestions, keine UI, keine
pgvector-Suche, kein Wissensgraph, kein RAG.

Leitprinzip:
users = technische Stammdaten
user_settings = Arbeitsweise
memory_items = sichtbares, bewusst verwendbares Wissen
memory_sources = Herkunft/Quelle
memory_visibility = wer darf es sehen/nutzen
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.database import (
    metadata_obj, engine, init_db, create_user,
    memory_items, memory_sources, memory_visibility,
    create_memory_source, create_memory_item, get_memory_item,
    list_active_memory_items_for_user, list_active_memory_items_for_org,
    set_memory_visibility, mark_memory_item_deleted,
    MemoryValidationError,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str = "alice", tenant_id: str = "default") -> None:
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")


def _confirmation_source(tenant_id: str = "default") -> int:
    return create_memory_source(
        tenant_id=tenant_id, source_type="user_confirmation",
        reference="chat-123", source_title="Nutzerbestaetigung im Chat",
    )["id"]


# ── Testgruppe 1: Migration ──────────────────────────────────────────────────

def test_tables_are_created():
    for table in (memory_items, memory_sources, memory_visibility):
        assert table.name in metadata_obj.tables


def test_required_fields_present():
    item_cols = {c.name for c in memory_items.columns}
    for f in ("scope", "title", "content", "purpose", "status", "source_id"):
        assert f in item_cols
    source_cols = {c.name for c in memory_sources.columns}
    assert "source_type" in source_cols
    vis_cols = {c.name for c in memory_visibility.columns}
    assert "visibility_scope" in vis_cols


def test_foreign_keys_point_to_correct_tables():
    fk_targets = {fk.column.table.name for col in memory_items.columns for fk in col.foreign_keys}
    assert "memory_sources" in fk_targets
    fk_targets_vis = {fk.column.table.name for col in memory_visibility.columns for fk in col.foreign_keys}
    assert "memory_items" in fk_targets_vis


# ── Testgruppe 2: memory_items-Regeln ────────────────────────────────────────

def test_invalid_scope_is_rejected():
    _make_user("alice")
    source_id = _confirmation_source()
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id="default", scope="irgendwas", title="x", content="y",
            purpose="Testzweck", source_id=source_id, owner_user_id="alice",
        )


def test_active_item_without_source_is_rejected():
    _make_user("alice")
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id="default", scope="user_memory", title="x", content="y",
            purpose="Testzweck", source_id=None, owner_user_id="alice",
            status="active",
        )


def test_active_item_without_purpose_is_rejected():
    _make_user("alice")
    source_id = _confirmation_source()
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id="default", scope="user_memory", title="x", content="y",
            purpose=None, source_id=source_id, owner_user_id="alice",
            status="active",
        )


def test_active_item_gets_default_visibility():
    _make_user("alice")
    source_id = _confirmation_source()
    item = create_memory_item(
        tenant_id="default", scope="user_memory", title="Kurze Antworten",
        content="Nutzer bevorzugt kurze Antworten.", purpose="Antwortstil anpassen",
        source_id=source_id, owner_user_id="alice", status="active",
    )
    with engine.begin() as conn:
        from sqlalchemy import select
        row = conn.execute(
            select(memory_visibility).where(memory_visibility.c.memory_item_id == item["id"])
        ).mappings().first()
    assert row is not None
    assert row["visibility_scope"] == "private"


# ── Testgruppe 3: Firmenwissen vs. Nutzergedaechtnis ─────────────────────────

def test_user_memory_requires_owner():
    source_id = _confirmation_source()
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id="default", scope="user_memory", title="x", content="y",
            purpose="Testzweck", source_id=source_id, owner_user_id=None,
            status="active",
        )


def test_company_memory_requires_tenant():
    source_id = _confirmation_source()
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id=None, scope="company_memory", title="x", content="y",
            purpose="Testzweck", source_id=source_id, owner_user_id=None,
            status="active",
        )


def test_company_memory_not_auto_visible_to_external():
    source_id = _confirmation_source()
    item = create_memory_item(
        tenant_id="default", scope="company_memory", title="DATEV",
        content="Firma nutzt DATEV.", purpose="Buchhaltungs-Kontext",
        source_id=source_id, owner_user_id=None, status="active",
    )
    with engine.begin() as conn:
        from sqlalchemy import select
        row = conn.execute(
            select(memory_visibility).where(memory_visibility.c.memory_item_id == item["id"])
        ).mappings().first()
    assert row["visibility_scope"] != "external_limited"
    assert row["visibility_scope"] == "organization"


# ── Testgruppe 4: Sichtbarkeit / Zugriff ─────────────────────────────────────

def test_user_a_sees_own_memory_user_b_does_not():
    _make_user("alice")
    _make_user("bob")
    source_id = _confirmation_source()
    create_memory_item(
        tenant_id="default", scope="user_memory", title="Alice-Praeferenz",
        content="Alice mag kurze Antworten.", purpose="Antwortstil",
        source_id=source_id, owner_user_id="alice", status="active",
    )
    alice_items = list_active_memory_items_for_user("alice", "default")
    bob_items = list_active_memory_items_for_user("bob", "default")
    assert len(alice_items) == 1
    assert len(bob_items) == 0


def test_organization_visibility_bound_to_tenant():
    source_a = _confirmation_source(tenant_id="tenant_a")
    create_memory_item(
        tenant_id="tenant_a", scope="company_memory", title="Firmenwissen A",
        content="Firma A nutzt DATEV.", purpose="Kontext",
        source_id=source_a, owner_user_id=None, status="active",
    )
    items_a = list_active_memory_items_for_org("tenant_a")
    items_b = list_active_memory_items_for_org("tenant_b")
    assert len(items_a) == 1
    assert len(items_b) == 0


def test_external_limited_requires_explicit_visibility_call():
    _make_user("alice")
    source_id = _confirmation_source()
    item = create_memory_item(
        tenant_id="default", scope="company_memory", title="Externes Wissen",
        content="Kunde Z braucht Rechnung als PDF.", purpose="Kundenkontext",
        source_id=source_id, owner_user_id=None, status="active",
    )
    # Default ist "organization", nicht "external_limited" (Test 3 oben deckt das
    # bereits ab). Hier: explizites Setzen ist moeglich und ueberschreibt Default.
    set_memory_visibility(item["id"], visibility_scope="external_limited",
                          allowed_user_ids=["kunde_z_kontakt"])
    with engine.begin() as conn:
        from sqlalchemy import select
        row = conn.execute(
            select(memory_visibility).where(memory_visibility.c.memory_item_id == item["id"])
        ).mappings().first()
    assert row["visibility_scope"] == "external_limited"
    assert row["allowed_user_ids"] == ["kunde_z_kontakt"]


# ── Testgruppe 5: Status / Nutzung ───────────────────────────────────────────

def test_all_valid_status_values_accepted_structurally():
    # "suggested" existiert nur als Statuswert (keine Vorschlagslogik in
    # dieser PR) -- Pflichtfelder (source/purpose) gelten nur fuer "active".
    _make_user("alice")
    for status in ("suggested", "confirmed", "active", "outdated", "deleted"):
        source_id = _confirmation_source() if status != "suggested" else None
        item = create_memory_item(
            tenant_id="default", scope="user_memory", title=f"Item {status}",
            content="Inhalt", purpose="Testzweck" if status != "suggested" else None,
            source_id=source_id, owner_user_id="alice", status=status,
        )
        assert item["status"] == status


def test_deleted_and_outdated_excluded_from_active_listing():
    _make_user("alice")
    source_id = _confirmation_source()
    active_item = create_memory_item(
        tenant_id="default", scope="user_memory", title="Aktiv",
        content="x", purpose="Testzweck", source_id=source_id,
        owner_user_id="alice", status="active",
    )
    deleted_item = create_memory_item(
        tenant_id="default", scope="user_memory", title="Geloescht",
        content="y", purpose="Testzweck", source_id=source_id,
        owner_user_id="alice", status="active",
    )
    mark_memory_item_deleted(deleted_item["id"])
    result = list_active_memory_items_for_user("alice", "default")
    ids = {r["id"] for r in result}
    assert active_item["id"] in ids
    assert deleted_item["id"] not in ids


def test_expires_at_can_be_set_and_excludes_from_active_listing():
    from datetime import datetime, timedelta, timezone

    _make_user("alice")
    source_id = _confirmation_source()
    past = datetime.now(timezone.utc) - timedelta(days=1)
    expired_item = create_memory_item(
        tenant_id="default", scope="user_memory", title="Abgelaufen",
        content="x", purpose="Testzweck", source_id=source_id,
        owner_user_id="alice", status="active", expires_at=past,
    )
    result = list_active_memory_items_for_user("alice", "default")
    ids = {r["id"] for r in result}
    assert expired_item["id"] not in ids


def test_get_memory_item_returns_item():
    _make_user("alice")
    source_id = _confirmation_source()
    item = create_memory_item(
        tenant_id="default", scope="user_memory", title="Test",
        content="Inhalt", purpose="Testzweck", source_id=source_id,
        owner_user_id="alice", status="active",
    )
    fetched = get_memory_item(item["id"])
    assert fetched["title"] == "Test"


# ── Testgruppe 6: Keine Roh-Chats ────────────────────────────────────────────

def test_no_automatic_chat_to_memory_path_exists():
    # Strukturelle Pruefung: kein Aufruf von save_user_chat() oder
    # aehnlichem loest automatisch create_memory_item() aus. Es gibt keinen
    # automatischen Pfad in dieser PR -- memory_items wird ausschliesslich
    # explizit ueber die Helper-Funktionen befuellt.
    import inspect
    from apps.backend import database as db_module

    save_chat_src = inspect.getsource(db_module.save_user_chat)
    assert "create_memory_item" not in save_chat_src
    assert "memory_items" not in save_chat_src
