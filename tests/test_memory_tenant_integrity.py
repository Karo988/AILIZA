"""Knowledge Phase 1 -- Memory Tenant Integrity.

Zentrale Sicherheitsinvariante (siehe Auftrag): kein memory_item darf ohne
eindeutig bestimmten Tenant neu entstehen, und kein Tenant darf
Memory-Daten eines anderen Tenants lesen, veraendern, loeschen, freigeben
oder in ihrer Sichtbarkeit beeinflussen.

Diese Datei deckt ab (SQLite -- PostgreSQL-Aequivalente siehe
tests/test_memory_tenant_integrity_postgres.py, per pg_only-Marker
getrennt gehalten):
  - fail-closed Ablehnung fehlender/leerer/Whitespace-tenant_id
  - direkter DB-Insert mit tenant_id=NULL schlaegt fehl (DB-Constraint)
  - die 12 Cross-Tenant-/Owner-Negativtests aus dem Auftrag
  - Same-Owner-Identifier-Gegenprobe (Owner-ID ersetzt niemals Tenant-Grenze)
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest
from sqlalchemy.exc import IntegrityError

from apps.backend.database import (
    metadata_obj, engine, init_db, create_user,
    memory_items, memory_suggestions,
    create_memory_source, create_memory_item, get_memory_item,
    list_active_memory_items_for_user, list_active_memory_items_for_org,
    set_memory_visibility, mark_memory_item_deleted,
    create_memory_suggestion, list_memory_suggestions_for_user,
    confirm_memory_suggestion, reject_memory_suggestion,
    mark_memory_suggestion_blocked,
    MemoryValidationError,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _user(user_id: str, tenant_id: str = "default") -> None:
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")


def _source(tenant_id: str = "default") -> int:
    return create_memory_source(tenant_id=tenant_id, source_type="user_confirmation", reference="t")["id"]


def _personal_item(tenant_id: str, owner: str, title: str = "t") -> dict:
    return create_memory_item(
        tenant_id=tenant_id, scope="user_memory", title=title, content="c",
        purpose="p", source_id=_source(tenant_id), owner_user_id=owner, status="active",
    )


def _company_item(tenant_id: str, title: str = "t") -> dict:
    return create_memory_item(
        tenant_id=tenant_id, scope="company_memory", title=title, content="c",
        purpose="p", source_id=_source(tenant_id), status="active",
    )


def _suggestion(user_id: str, tenant_id: str, scope: str = "user_memory") -> dict:
    return create_memory_suggestion(
        user_id=user_id, tenant_id=tenant_id, suggested_scope=scope,
        suggested_title="s", suggested_content="c", suggested_purpose="p",
        source_type="user_confirmation",
    )


# ── Fail-closed: fehlende/leere/Whitespace tenant_id ────────────────────────

@pytest.mark.parametrize("bad_tenant", [None, "", "   "])
def test_create_memory_item_rejects_missing_tenant_user_memory(bad_tenant):
    """7-9: fehlende/leere/Whitespace tenant_id wird verweigert -- auch fuer
    user_memory (nicht nur company_memory, das war schon vorher geprueft)."""
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id=bad_tenant, scope="user_memory", title="t", content="c",
            purpose="p", owner_user_id="alice", status="suggested",
        )


@pytest.mark.parametrize("bad_tenant", [None, "", "   "])
def test_create_memory_item_rejects_missing_tenant_company_memory(bad_tenant):
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id=bad_tenant, scope="company_memory", title="t", content="c",
            purpose="p", status="suggested",
        )


@pytest.mark.parametrize("bad_tenant", [None, "", "   "])
def test_get_memory_item_rejects_missing_tenant(bad_tenant):
    _user("alice")
    item = _personal_item("default", "alice")
    with pytest.raises(MemoryValidationError):
        get_memory_item(item["id"], tenant_id=bad_tenant)


# ── Direkter DB-Beweis: tenant_id=NULL scheitert an der DB selbst ──────────

def test_direct_db_insert_with_null_tenant_fails_at_db_level():
    """Beweist, dass NICHT nur Python-/Service-Validierung (_require_tenant)
    einen fehlenden Tenant verhindert, sondern die Datenbank selbst --
    umgeht bewusst create_memory_item() und fuegt direkt per SQLAlchemy-Core
    ein, genau wie ein zukuenftiger, ungeprueft schreibender Codepfad es
    tun koennte."""
    from sqlalchemy import insert
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(insert(memory_items).values(
                tenant_id=None, scope="user_memory", owner_user_id="alice",
                title="t", content="c", purpose="p", source_id=None,
                status="active", created_at=now, updated_at=now,
            ))


# ── Die 12 Cross-Tenant-/Owner-Negativtests aus dem Auftrag ────────────────

def test_01_tenant_a_cannot_read_tenant_b_item_by_id():
    _user("alice", "tenant-a")
    item_b = _personal_item("tenant-b", "bob")
    assert get_memory_item(item_b["id"], tenant_id="tenant-a") is None


def test_02_tenant_a_cannot_read_tenant_b_item_via_listing():
    """Variante von "aendern": Listing ist der einzige generische Lesepfad
    fuer mehrere Items -- Tenant A darf darueber niemals Items von Tenant B
    sehen, unabhaengig vom Owner-Namen."""
    _user("alice", "tenant-a")
    _personal_item("tenant-b", "alice")  # gleicher Owner-Name, anderer Tenant
    assert list_active_memory_items_for_user("alice", "tenant-a") == []


def test_03_tenant_a_cannot_soft_delete_tenant_b_item():
    item_b = _personal_item("tenant-b", "bob")
    with pytest.raises(MemoryValidationError):
        mark_memory_item_deleted(item_b["id"], tenant_id="tenant-a")
    # Item bleibt bei Tenant B unveraendert vorhanden.
    assert get_memory_item(item_b["id"], tenant_id="tenant-b")["status"] == "active"


def test_04_tenant_a_cannot_change_visibility_of_tenant_b_item():
    item_b = _personal_item("tenant-b", "bob")
    with pytest.raises(MemoryValidationError):
        set_memory_visibility(item_b["id"], tenant_id="tenant-a", visibility_scope="organization")


def test_05_tenant_a_cannot_confirm_tenant_b_suggestion():
    s_b = _suggestion("bob", "tenant-b")
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(s_b["id"], confirmed_by="alice", tenant_id="tenant-a")


def test_06_tenant_a_cannot_reject_tenant_b_suggestion():
    s_b = _suggestion("bob", "tenant-b")
    with pytest.raises(MemoryValidationError):
        reject_memory_suggestion(s_b["id"], reviewed_by="alice", tenant_id="tenant-a")
    # Vorschlag bleibt bei Tenant B unveraendert (nicht "rejected").
    still = list_memory_suggestions_for_user("bob", "tenant-b", status=None)
    assert still[0]["status"] == "open"


def test_07_missing_tenant_id_rejected():
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id=None, scope="user_memory", title="t", content="c",
            purpose="p", owner_user_id="alice", status="suggested",
        )


def test_08_empty_tenant_id_rejected():
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id="", scope="user_memory", title="t", content="c",
            purpose="p", owner_user_id="alice", status="suggested",
        )


def test_09_whitespace_tenant_id_rejected():
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id="   ", scope="user_memory", title="t", content="c",
            purpose="p", owner_user_id="alice", status="suggested",
        )


def test_10a_foreign_owner_same_tenant_cannot_delete():
    """Owner-Isolation INNERHALB desselben Tenants (staerkste Luecke laut
    Subagent-C-Analyse): mallory darf Alice' persoenliches Item nicht
    loeschen, obwohl beide im selben Tenant sind."""
    item_alice = _personal_item("default", "alice")
    with pytest.raises(MemoryValidationError):
        mark_memory_item_deleted(item_alice["id"], tenant_id="default", owner_user_id="mallory")


def test_10b_foreign_owner_same_tenant_cannot_change_visibility():
    item_alice = _personal_item("default", "alice")
    with pytest.raises(MemoryValidationError):
        set_memory_visibility(
            item_alice["id"], tenant_id="default", owner_user_id="mallory",
            visibility_scope="organization",
        )


def test_10c_foreign_owner_same_tenant_cannot_confirm_suggestion():
    s_alice = _suggestion("alice", "default")
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(s_alice["id"], confirmed_by="mallory", tenant_id="default", user_id="mallory")


def test_10d_foreign_owner_same_tenant_cannot_reject_suggestion():
    s_alice = _suggestion("alice", "default")
    with pytest.raises(MemoryValidationError):
        reject_memory_suggestion(s_alice["id"], reviewed_by="mallory", tenant_id="default", user_id="mallory")


def test_10e_manager_role_cannot_confirm_foreign_personal_suggestion():
    """Eine Rollen-Ausnahme darf die Owner-Bindung bei persoenlichem Memory
    nicht aufheben -- auch ein Manager/Admin darf Alice' user_memory-
    Vorschlag nicht fuer sie bestaetigen."""
    s_alice = _suggestion("alice", "default")
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(
            s_alice["id"], confirmed_by="karo-admin", tenant_id="default",
            reviewer_role="admin", user_id="karo-admin",
        )


def test_11_valid_own_tenant_items_remain_usable():
    """Gegenprobe zu den Restriktionen oben: der eigene Tenant funktioniert
    weiterhin normal fuer alle gehaerteten Operationen."""
    item = _personal_item("default", "alice")
    assert get_memory_item(item["id"], tenant_id="default") is not None
    set_memory_visibility(item["id"], tenant_id="default", owner_user_id="alice", visibility_scope="private")
    mark_memory_item_deleted(item["id"], tenant_id="default", owner_user_id="alice")
    assert get_memory_item(item["id"], tenant_id="default")["status"] == "deleted"


def test_12_company_memory_of_correct_tenant_remains_usable_for_roles():
    """Firmenwissen des korrekten Tenants bleibt fuer berechtigte Rollen
    nutzbar -- Confirm durch Admin funktioniert weiterhin normal."""
    s = _suggestion("alice", "default", scope="company_memory")
    result = confirm_memory_suggestion(
        s["id"], confirmed_by="karo-admin", tenant_id="default", reviewer_role="admin",
    )
    item = get_memory_item(result["memory_item_id"], tenant_id="default")
    assert item["scope"] == "company_memory"
    assert item["status"] == "active"


# ── Same-Owner-Identifier-Gegenprobe (Auftrag Abschnitt 23) ────────────────

def test_same_owner_identifier_in_two_tenants_does_not_bypass_isolation():
    """Ein identischer owner_user_id-Wert ("alice") existiert unabhaengig in
    zwei verschiedenen Tenants -- der Owner-Identifier darf die
    Tenant-Grenze niemals ersetzen."""
    item_a = _personal_item("tenant-a", "alice", title="A-Geheimnis")
    item_b = _personal_item("tenant-b", "alice", title="B-Geheimnis")

    listing_a = list_active_memory_items_for_user("alice", "tenant-a")
    listing_b = list_active_memory_items_for_user("alice", "tenant-b")
    assert [i["title"] for i in listing_a] == ["A-Geheimnis"]
    assert [i["title"] for i in listing_b] == ["B-Geheimnis"]

    # Direkter ID-Zugriff ueber die falsche Tenant-Vermutung schlaegt fehl,
    # obwohl der Owner-Name identisch ist.
    assert get_memory_item(item_a["id"], tenant_id="tenant-b") is None
    assert get_memory_item(item_b["id"], tenant_id="tenant-a") is None

    # mark_memory_item_deleted mit falschem Tenant darf das jeweils andere
    # Item nicht treffen, selbst wenn der Owner-Name passt.
    with pytest.raises(MemoryValidationError):
        mark_memory_item_deleted(item_b["id"], tenant_id="tenant-a", owner_user_id="alice")
    assert get_memory_item(item_b["id"], tenant_id="tenant-b")["status"] == "active"


def test_confirm_memory_suggestion_does_not_blindly_trust_suggestion_tenant():
    """Regressionstest fuer den von Subagent A gefundenen kritischsten
    Befund: confirm_memory_suggestion() darf tenant_id NICHT mehr blind aus
    der (vorher ungefilterten) suggestion-Zeile uebernehmen, sondern muss
    selbst zuerst tenant-gefiltert laden."""
    s_b = _suggestion("bob", "tenant-b", scope="company_memory")
    with pytest.raises(MemoryValidationError, match="nicht gefunden"):
        confirm_memory_suggestion(s_b["id"], confirmed_by="mallory", tenant_id="tenant-a", reviewer_role="admin")
    # Kein memory_item in Tenant A entstanden.
    assert list_active_memory_items_for_org("tenant-a") == []


def test_mark_memory_suggestion_blocked_is_tenant_scoped():
    s_b = _suggestion("bob", "tenant-b")
    with pytest.raises(MemoryValidationError):
        mark_memory_suggestion_blocked(s_b["id"], tenant_id="tenant-a")
    still = list_memory_suggestions_for_user("bob", "tenant-b", status=None)
    assert still[0]["status"] == "open"
