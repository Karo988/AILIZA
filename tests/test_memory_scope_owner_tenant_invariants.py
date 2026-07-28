"""
M1: Scope-, Owner- und Tenant-Invarianten fuer den fachlichen Memory-Kern
(memory_items/memory_sources/memory_visibility/memory_suggestions).

Verbindliche Zielregeln:
  user_memory:    scope=="user_memory", owner_user_id PFLICHT
  company_memory: scope=="company_memory", tenant_id PFLICHT, owner_user_id MUSS NULL sein

Diese Tests decken KEINE Migration von Bestandsdaten ab (Freigabe der
Nutzerin: "keine bekannten Bestandsdaten" -- additiv, idempotent,
fail-safe implementiert). Sie pruefen:
  - Validierungsregeln (_validate_memory_item)
  - Sichtbarkeit fuer den Owner vs. fremde Nutzer/Tenants
  - Uebergangsregel fuer Legacy-user_memory mit tenant_id=NULL
  - Export/Loeschung beruecksichtigen ausschliesslich user_memory
  - der rein lesende Audit-/Repair-Report (audit_memory_scope_invariants)
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_source(tenant_id="default"):
    from apps.backend.database import create_memory_source
    return create_memory_source(tenant_id, "user_confirmation", reference="test")["id"]


# ── Validierung (_validate_memory_item) ─────────────────────────────────────

def test_user_memory_without_owner_rejected():
    from apps.backend.database import create_memory_item, MemoryValidationError
    source_id = _make_source()
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id="default", scope="user_memory", title="t", content="c",
            purpose="p", source_id=source_id, status="active", owner_user_id=None,
        )


def test_company_memory_without_tenant_rejected():
    from apps.backend.database import create_memory_item, MemoryValidationError
    source_id = _make_source()
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id=None, scope="company_memory", title="t", content="c",
            purpose="p", source_id=source_id, status="active",
        )


def test_company_memory_with_owner_rejected():
    """M1-Neuerung: company_memory darf keinen owner_user_id haben."""
    from apps.backend.database import create_memory_item, MemoryValidationError
    source_id = _make_source()
    with pytest.raises(MemoryValidationError):
        create_memory_item(
            tenant_id="default", scope="company_memory", title="t", content="c",
            purpose="p", source_id=source_id, status="active", owner_user_id="alice",
        )


def test_valid_user_memory_accepted():
    from apps.backend.database import create_memory_item
    source_id = _make_source()
    item = create_memory_item(
        tenant_id="default", scope="user_memory", title="t", content="c",
        purpose="p", source_id=source_id, status="active", owner_user_id="alice",
    )
    assert item["id"]


def test_valid_company_memory_accepted():
    from apps.backend.database import create_memory_item
    source_id = _make_source()
    item = create_memory_item(
        tenant_id="default", scope="company_memory", title="t", content="c",
        purpose="p", source_id=source_id, status="active",
    )
    assert item["id"]


# ── Legacy-Uebergang: user_memory mit tenant_id=NULL ────────────────────────

def test_user_memory_with_null_tenant_is_listable_for_owner():
    """Legacy-user_memory ohne Tenant (aus Zeit vor Tenant-Pflicht) muss
    weiterhin fuer den Owner sichtbar sein, unabhaengig vom angefragten
    Tenant."""
    from apps.backend.database import engine, memory_items
    from sqlalchemy import insert
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(insert(memory_items).values(
            tenant_id=None, scope="user_memory", owner_user_id="legacy_alice",
            title="alt", content="alt-inhalt", category=None, purpose="p",
            source_id=None, status="active", created_at=now, updated_at=now,
        ))
    from apps.backend.database import list_active_memory_items_for_user
    items = list_active_memory_items_for_user("legacy_alice", "default")
    assert len(items) == 1
    assert items[0]["tenant_id"] is None


def test_legacy_user_memory_with_tenant_remains_findable():
    """user_memory MIT gesetztem Tenant (regulaerer Fall) bleibt selbstverstaendlich
    weiterhin auffindbar -- Regressionsschutz gegen eine zu enge Uebergangsregel."""
    from apps.backend.database import create_memory_item, list_active_memory_items_for_user
    source_id = _make_source()
    create_memory_item(
        tenant_id="default", scope="user_memory", title="t", content="c",
        purpose="p", source_id=source_id, status="active", owner_user_id="bob",
    )
    items = list_active_memory_items_for_user("bob", "default")
    assert len(items) == 1


def test_null_tenant_user_memory_not_visible_to_other_users():
    from apps.backend.database import engine, memory_items, list_active_memory_items_for_user
    from sqlalchemy import insert
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(insert(memory_items).values(
            tenant_id=None, scope="user_memory", owner_user_id="legacy_alice",
            title="alt", content="alt-inhalt", purpose="p", source_id=None,
            status="active", created_at=now, updated_at=now,
        ))
    assert list_active_memory_items_for_user("mallory", "default") == []


# ── Fremder Tenant erhaelt kein company_memory ──────────────────────────────

def test_company_memory_not_visible_to_foreign_tenant():
    from apps.backend.database import create_memory_item, list_active_memory_items_for_org
    source_id = _make_source(tenant_id="tenant-a")
    create_memory_item(
        tenant_id="tenant-a", scope="company_memory", title="t", content="c",
        purpose="p", source_id=source_id, status="active",
    )
    assert list_active_memory_items_for_org("tenant-b") == []
    assert len(list_active_memory_items_for_org("tenant-a")) == 1


def test_list_for_user_never_returns_company_memory():
    """Expliziter scope-Filter (M1): list_active_memory_items_for_user()
    darf niemals company_memory zurueckgeben, auch wenn (hypothetisch)
    tenant_id uebereinstimmt."""
    from apps.backend.database import create_memory_item, list_active_memory_items_for_user
    source_id = _make_source()
    create_memory_item(
        tenant_id="default", scope="company_memory", title="t", content="c",
        purpose="p", source_id=source_id, status="active",
    )
    assert list_active_memory_items_for_user("alice", "default") == []


# ── Export/Loeschung: nur user_memory, nie company_memory ───────────────────

def test_export_user_data_contains_only_user_memory():
    from apps.backend.database import create_memory_item, export_user_data, create_user
    import bcrypt
    create_user("alice", "default", "user", bcrypt.hashpw(b"CorrectHorse123!", bcrypt.gensalt()).decode())
    source_id = _make_source()
    create_memory_item(
        tenant_id="default", scope="user_memory", title="privat", content="c",
        purpose="p", source_id=source_id, status="active", owner_user_id="alice",
    )
    create_memory_item(
        tenant_id="default", scope="company_memory", title="firma", content="c",
        purpose="p", source_id=source_id, status="active",
    )
    export = export_user_data("alice", "default")
    titles = [i["title"] for i in export["memory_items"]]
    assert titles == ["privat"]


def test_delete_own_account_data_removes_only_user_memory():
    from apps.backend.database import (
        create_memory_item, delete_own_account_data, create_user,
        list_active_memory_items_for_user, list_active_memory_items_for_org,
    )
    import bcrypt
    create_user("alice", "default", "user", bcrypt.hashpw(b"CorrectHorse123!", bcrypt.gensalt()).decode())
    source_id = _make_source()
    create_memory_item(
        tenant_id="default", scope="user_memory", title="privat", content="c",
        purpose="p", source_id=source_id, status="active", owner_user_id="alice",
    )
    create_memory_item(
        tenant_id="default", scope="company_memory", title="firma", content="c",
        purpose="p", source_id=source_id, status="active",
    )
    delete_own_account_data("alice", "default")
    assert list_active_memory_items_for_user("alice", "default") == []
    assert len(list_active_memory_items_for_org("default")) == 1


def test_delete_own_account_data_removes_legacy_null_tenant_user_memory():
    from apps.backend.database import (
        engine, memory_items, delete_own_account_data, create_user,
        list_active_memory_items_for_user,
    )
    from sqlalchemy import insert
    from datetime import datetime, timezone
    import bcrypt
    create_user("legacy_alice", "default", "user", bcrypt.hashpw(b"CorrectHorse123!", bcrypt.gensalt()).decode())
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(insert(memory_items).values(
            tenant_id=None, scope="user_memory", owner_user_id="legacy_alice",
            title="alt", content="c", purpose="p", source_id=None,
            status="active", created_at=now, updated_at=now,
        ))
    delete_own_account_data("legacy_alice", "default")
    assert list_active_memory_items_for_user("legacy_alice", "default") == []


# ── Audit-/Repair-Report (rein lesend) ──────────────────────────────────────

def test_audit_report_clean_state_no_violations():
    from apps.backend.database import audit_memory_scope_invariants, create_memory_item
    source_id = _make_source()
    create_memory_item(
        tenant_id="default", scope="user_memory", title="t", content="c",
        purpose="p", source_id=source_id, status="active", owner_user_id="alice",
    )
    report = audit_memory_scope_invariants()
    assert report["has_violations"] is False
    assert report["violations"]["user_memory_missing_owner"] == []
    assert report["violations"]["company_memory_missing_tenant"] == []
    assert report["violations"]["company_memory_with_owner"] == []


def test_audit_report_flags_legacy_null_tenant_as_info_not_violation():
    from apps.backend.database import engine, memory_items, audit_memory_scope_invariants
    from sqlalchemy import insert
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(insert(memory_items).values(
            tenant_id=None, scope="user_memory", owner_user_id="legacy_alice",
            title="alt", content="c", purpose="p", source_id=None,
            status="active", created_at=now, updated_at=now,
        ))
    report = audit_memory_scope_invariants()
    assert report["has_violations"] is False
    assert len(report["info_only"]["legacy_user_memory_null_tenant"]) == 1


def test_audit_report_detects_invariant_violation_bypassing_validation():
    """Simuliert einen Bestandsdatensatz, der die Invariante verletzt
    (z.B. durch direktes SQL vor dieser Haertung entstanden) -- der Report
    muss ihn finden, OHNE ihn zu veraendern."""
    from apps.backend.database import engine, memory_items, audit_memory_scope_invariants
    from sqlalchemy import insert
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(insert(memory_items).values(
            tenant_id="default", scope="company_memory", owner_user_id="sollte_leer_sein",
            title="invalid", content="c", purpose="p", source_id=None,
            status="active", created_at=now, updated_at=now,
        ))
    report = audit_memory_scope_invariants()
    assert report["has_violations"] is True
    assert len(report["violations"]["company_memory_with_owner"]) == 1
    # Rein lesend: der fehlerhafte Datensatz existiert unveraendert weiter.
    from apps.backend.database import list_active_memory_items_for_org
    assert len(list_active_memory_items_for_org("default")) == 1
