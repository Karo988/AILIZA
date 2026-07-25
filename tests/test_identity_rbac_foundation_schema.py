"""PR 1 (Identitaets-/RBAC-Grundlage): Grundlagenschema und kontrollierte
Legacy-Migration.

Reines Schema: owner_user_id auf agent_runs/approval_requests, plus die
neuen Tabellen user_specialist_roles und case_assignments. KEINE
Permission-Evaluator-Logik, KEINE Endpunkt-Anbindung, KEINE automatische
Zuordnung historischer Datensaetze -- das folgt in spaeteren, separaten PRs.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.database import (
    CaseAssignmentValidationError,
    SpecialistRoleValidationError,
    create_agent_run,
    create_approval_request,
    create_case_assignment,
    create_specialist_role_assignment,
    create_user,
    engine,
    get_agent_run,
    get_approval_request,
    init_db,
    list_active_case_assignments,
    list_active_specialist_roles,
    metadata_obj,
    revoke_case_assignment,
    revoke_specialist_role_assignment,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str, tenant_id: str = "default") -> None:
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")


# ── Testgruppe 1: Migration (Schema-Ebene) ──────────────────────────────────

def test_fresh_database_has_owner_user_id_columns():
    from apps.backend.database import agent_runs, approval_requests
    assert "owner_user_id" in agent_runs.c
    assert "owner_user_id" in approval_requests.c


def test_migration_can_run_repeatedly_without_error():
    init_db()
    init_db()
    init_db()  # idempotent, kein Fehler


def test_new_tables_exist():
    assert "user_specialist_roles" in metadata_obj.tables
    assert "case_assignments" in metadata_obj.tables


# ── Testgruppe 2: Historische Datensaetze bleiben ohne Owner ────────────────

def test_agent_run_without_explicit_owner_stays_null():
    """create_agent_run() bekommt in PR 1 bewusst noch keinen owner_user_id-
    Parameter (Verdrahtung folgt in einem spaeteren PR) -- die Spalte muss
    trotzdem in der DB als NULL vorliegen, nicht fehlen."""
    create_agent_run(run_id="run-legacy-1", task="alte Aufgabe")
    assert get_agent_run("run-legacy-1")["owner_user_id"] is None


def test_approval_request_without_explicit_owner_stays_null():
    entry = create_approval_request(
        tool="llm_call", input_params={}, risk_level="high", risk_reason="Test",
    )
    assert get_approval_request(entry["id"])["owner_user_id"] is None


def test_no_user_receives_historical_records_automatically():
    """Kein Nutzer erhaelt automatisch historische Datensaetze -- es gibt
    keine Funktion, die owner_user_id nachtraeglich rateweise befuellt."""
    import apps.backend.database as db_module
    forbidden = ("backfill_owner", "assign_legacy_owner", "guess_owner", "auto_assign_owner")
    for name in forbidden:
        assert not hasattr(db_module, name), f"Verbotene Backfill-Funktion gefunden: {name}"


# ── Testgruppe 3: Fachrollen-Zuweisung ───────────────────────────────────────

def test_specialist_role_assignment_can_be_created():
    _make_user("alice")
    _make_user("admin1")
    entry = create_specialist_role_assignment(
        user_id="alice", tenant_id="default", specialist_role="DATENSCHUTZBEAUFTRAGTER",
        assigned_by_user_id="admin1", assignment_reason="Neue DSB-Bestellung 2026",
    )
    assert entry["id"] is not None
    assert entry["is_active"] == 1
    assert entry["revoked_at"] is None


def test_duplicate_active_specialist_role_is_rejected():
    _make_user("alice")
    _make_user("admin1")
    create_specialist_role_assignment(
        user_id="alice", tenant_id="default", specialist_role="RECHTSVERANTWORTLICHER",
        assigned_by_user_id="admin1", assignment_reason="Erstbestellung",
    )
    with pytest.raises(SpecialistRoleValidationError):
        create_specialist_role_assignment(
            user_id="alice", tenant_id="default", specialist_role="RECHTSVERANTWORTLICHER",
            assigned_by_user_id="admin1", assignment_reason="Doppelte Bestellung",
        )


def test_specialist_role_can_be_revoked_without_deleting_record():
    _make_user("alice")
    _make_user("admin1")
    entry = create_specialist_role_assignment(
        user_id="alice", tenant_id="default", specialist_role="BETRIEBSVERANTWORTLICHER",
        assigned_by_user_id="admin1", assignment_reason="Bestellung",
    )
    revoked = revoke_specialist_role_assignment(entry["id"], revoked_by_user_id="admin1")
    assert revoked is not None
    assert revoked["revoked_at"] is not None
    assert revoked["revoked_by_user_id"] == "admin1"
    assert revoked["is_active"] == 0
    # Datensatz existiert weiterhin (kein DELETE):
    assert list_active_specialist_roles("alice", "default") == []


def test_revoked_specialist_role_frees_up_reassignment():
    """Nach Widerruf kann dieselbe Fachrolle erneut vergeben werden --
    beweist, dass der Unique-Index nur AKTIVE Zuweisungen erfasst."""
    _make_user("alice")
    _make_user("admin1")
    entry = create_specialist_role_assignment(
        user_id="alice", tenant_id="default", specialist_role="INFORMATIONSSICHERHEITSBEAUFTRAGTER",
        assigned_by_user_id="admin1", assignment_reason="Erstbestellung",
    )
    revoke_specialist_role_assignment(entry["id"], revoked_by_user_id="admin1")
    second = create_specialist_role_assignment(
        user_id="alice", tenant_id="default", specialist_role="INFORMATIONSSICHERHEITSBEAUFTRAGTER",
        assigned_by_user_id="admin1", assignment_reason="Neubestellung nach Widerruf",
    )
    assert second["id"] != entry["id"]
    assert len(list_active_specialist_roles("alice", "default")) == 1


def test_specialist_role_requires_assignment_reason():
    _make_user("alice")
    _make_user("admin1")
    with pytest.raises(SpecialistRoleValidationError):
        create_specialist_role_assignment(
            user_id="alice", tenant_id="default", specialist_role="RECHTSVERANTWORTLICHER",
            assigned_by_user_id="admin1", assignment_reason="",
        )


def test_specialist_role_rejects_unknown_role_value():
    _make_user("alice")
    _make_user("admin1")
    with pytest.raises(SpecialistRoleValidationError):
        create_specialist_role_assignment(
            user_id="alice", tenant_id="default", specialist_role="SUPERADMIN",
            assigned_by_user_id="admin1", assignment_reason="Test",
        )


# ── Testgruppe 4: Gezielte Vorgangszuteilung ─────────────────────────────────

def test_case_can_be_assigned():
    _make_user("teamlead1")
    _make_user("admin1")
    entry = create_case_assignment(
        case_type="APPROVAL", case_id="42", tenant_id="default",
        assigned_to_user_id="teamlead1", assigned_by_user_id="admin1",
        assignment_reason="Zustaendigkeit Projekt AILIZA",
    )
    assert entry["id"] is not None
    assert entry["revoked_at"] is None


def test_duplicate_active_case_assignment_is_rejected():
    _make_user("teamlead1")
    _make_user("admin1")
    create_case_assignment(
        case_type="APPROVAL", case_id="42", tenant_id="default",
        assigned_to_user_id="teamlead1", assigned_by_user_id="admin1",
        assignment_reason="Erstzuweisung",
    )
    with pytest.raises(CaseAssignmentValidationError):
        create_case_assignment(
            case_type="APPROVAL", case_id="42", tenant_id="default",
            assigned_to_user_id="teamlead1", assigned_by_user_id="admin1",
            assignment_reason="Doppelte Zuweisung",
        )


def test_cross_tenant_case_assignment_is_rejected():
    _make_user("teamlead1", tenant_id="tenant-a")
    _make_user("admin_b", tenant_id="tenant-b")
    with pytest.raises(CaseAssignmentValidationError):
        create_case_assignment(
            case_type="APPROVAL", case_id="99", tenant_id="tenant-b",
            assigned_to_user_id="teamlead1",  # gehoert zu tenant-a, nicht tenant-b
            assigned_by_user_id="admin_b",
            assignment_reason="Fehlversuch ueber Tenant-Grenze",
        )


def test_case_assignment_can_be_revoked_without_deleting_record():
    _make_user("teamlead1")
    _make_user("admin1")
    entry = create_case_assignment(
        case_type="AGENT_RUN", case_id="run-1", tenant_id="default",
        assigned_to_user_id="teamlead1", assigned_by_user_id="admin1",
        assignment_reason="Zuweisung",
    )
    revoked = revoke_case_assignment(entry["id"], revoked_by_user_id="admin1")
    assert revoked["revoked_at"] is not None
    assert list_active_case_assignments("teamlead1", "default") == []


def test_case_assignment_requires_reason():
    _make_user("teamlead1")
    _make_user("admin1")
    with pytest.raises(CaseAssignmentValidationError):
        create_case_assignment(
            case_type="APPROVAL", case_id="1", tenant_id="default",
            assigned_to_user_id="teamlead1", assigned_by_user_id="admin1",
            assignment_reason="   ",
        )


def test_case_assignment_rejects_unknown_case_type():
    _make_user("teamlead1")
    _make_user("admin1")
    with pytest.raises(CaseAssignmentValidationError):
        create_case_assignment(
            case_type="PROJECT", case_id="1", tenant_id="default",
            assigned_to_user_id="teamlead1", assigned_by_user_id="admin1",
            assignment_reason="noch nicht erlaubt in PR 1",
        )


# ── Testgruppe 5: Bestandskonten ohne E-Mail bleiben unangetastet ───────────

def test_existing_users_without_email_field_remain_valid():
    """PR 1 fuehrt bewusst KEIN E-Mail-Feld ein (eigener Folge-PR, siehe
    Abschlussbericht) -- bestehende Nutzer bleiben unveraendert nutzbar."""
    _make_user("bestandsnutzer")
    from apps.backend.database import get_user
    user = get_user("bestandsnutzer")
    assert user is not None
    assert "email" not in user
    assert "primary_email" not in user
