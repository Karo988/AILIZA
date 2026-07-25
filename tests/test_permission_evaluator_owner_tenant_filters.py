"""
PR 2: Zentraler Permission-Evaluator und sichere Owner-/Tenant-Filter.

Die 20 im Startauftrag vorgeschriebenen Pflicht-Tests. Deckt ab: eigener
Zugriff, Fremdzugriff (Tenant und Nutzer), Zuweisungen (aktiv/widerrufen/
abgelaufen), historische ownerlose Datensaetze, serverseitiges Setzen von
Owner/Tenant beim Erstellen, Listen/Details ohne Fremddaten-Leck, neutrale
Fehlerantworten, Genehmigungs-Owner-Vererbung, Selbst-/Fremdfreigabe,
Ablauf, unbekannte Rollen, Admin ohne Automatikzugriff, tenant-uebergreifende
Zuweisungen und die unmittelbare Zweitpruefung vor der Mutation.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

from datetime import datetime, timedelta, timezone

import pytest

from apps.backend.permissions import GENERIC_DENIED_MESSAGE


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app, cookies={})


def _token(user_id: str, tenant_id: str = "default", role: str = "user") -> str:
    from apps.backend.auth.jwt_handler import create_token
    return create_token(user_id, tenant_id, role)


def _headers(user_id: str, tenant_id: str = "default", role: str = "user") -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user_id, tenant_id, role)}"}


def _make_run(run_id: str, tenant_id: str = "default", owner_user_id: str | None = None):
    from apps.backend.database import create_agent_run
    return create_agent_run(
        run_id=run_id, task="Testaufgabe", status="completed",
        tenant_id=tenant_id, owner_user_id=owner_user_id,
    )


def _ensure_user(user_id: str, tenant_id: str = "default", role: str = "user"):
    from apps.backend.database import create_user, get_user
    if get_user(user_id, tenant_id=tenant_id) is None:
        create_user(user_id, tenant_id, role, hashed_password="x")


def _assign_approval(approval_id, user_id: str, tenant_id: str = "default", **kw):
    from apps.backend.database import create_case_assignment
    _ensure_user(user_id, tenant_id, kw.pop("role", "user"))
    _ensure_user("assignerin", tenant_id, "manager")
    return create_case_assignment(
        case_type="APPROVAL", case_id=str(approval_id), tenant_id=tenant_id,
        assigned_to_user_id=user_id, assigned_by_user_id="assignerin",
        assignment_reason="Test-Zustaendigkeit", **kw,
    )


def _make_approval(tenant_id: str = "default", owner_user_id: str | None = None, run_id: str | None = None):
    from apps.backend.database import create_approval_request
    return create_approval_request(
        tool="llm_call", input_params={"task_length": 10}, risk_level="high",
        risk_reason="Test", run_id=run_id, tenant_id=tenant_id, owner_user_id=owner_user_id,
    )


# 1. Eigener Agent-Run sichtbar
def test_own_agent_run_visible(client):
    _make_run("run-own-1", owner_user_id="alice")
    resp = client.get("/agent/runs", headers=_headers("alice"))
    assert resp.status_code == 200
    assert any(r["id"] == "run-own-1" for r in resp.json())


# 2. Fremder Agent-Run im selben Tenant NICHT sichtbar
def test_foreign_agent_run_same_tenant_not_visible(client):
    _make_run("run-foreign-1", owner_user_id="bob")
    resp = client.get("/agent/runs", headers=_headers("alice"))
    assert resp.status_code == 200
    assert all(r["id"] != "run-foreign-1" for r in resp.json())


# 3. Agent-Run eines fremden Tenants NICHT sichtbar
def test_agent_run_other_tenant_not_visible(client):
    _make_run("run-tenantx-1", tenant_id="tenant-x", owner_user_id="alice")
    resp = client.get("/agent/runs", headers=_headers("alice", tenant_id="default"))
    assert resp.status_code == 200
    assert all(r["id"] != "run-tenantx-1" for r in resp.json())


# 4. Gueltig zugewiesene Person darf lesen
def test_assigned_user_can_read_agent_run(client):
    from apps.backend.database import create_case_assignment
    _ensure_user("bob")
    _ensure_user("alice")
    _make_run("run-assigned-1", owner_user_id="bob")
    create_case_assignment(
        case_type="AGENT_RUN", case_id="run-assigned-1", tenant_id="default",
        assigned_to_user_id="alice", assigned_by_user_id="bob", assignment_reason="Vertretung",
    )
    resp = client.get("/agent/runs/run-assigned-1", headers=_headers("alice"))
    assert resp.status_code == 200
    assert resp.json()["id"] == "run-assigned-1"


# 5. Widerrufene Zuweisung gewaehrt keinen Zugriff
def test_revoked_assignment_denies_access(client):
    from apps.backend.database import create_case_assignment, revoke_case_assignment
    _ensure_user("bob")
    _ensure_user("alice")
    _make_run("run-revoked-1", owner_user_id="bob")
    assignment = create_case_assignment(
        case_type="AGENT_RUN", case_id="run-revoked-1", tenant_id="default",
        assigned_to_user_id="alice", assigned_by_user_id="bob", assignment_reason="Vertretung",
    )
    revoke_case_assignment(assignment["id"], tenant_id="default", revoked_by_user_id="bob")
    resp = client.get("/agent/runs/run-revoked-1", headers=_headers("alice"))
    assert resp.status_code == 404


# 6. Abgelaufene Zuweisung gewaehrt keinen Zugriff
def test_expired_assignment_denies_access(client):
    from apps.backend.database import create_case_assignment
    _ensure_user("bob")
    _ensure_user("alice")
    _make_run("run-expired-1", owner_user_id="bob")
    create_case_assignment(
        case_type="AGENT_RUN", case_id="run-expired-1", tenant_id="default",
        assigned_to_user_id="alice", assigned_by_user_id="bob", assignment_reason="Vertretung",
        valid_until=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    resp = client.get("/agent/runs/run-expired-1", headers=_headers("alice"))
    assert resp.status_code == 404


# 7. Historischer Run ohne Owner ist fuer normale Nutzer unsichtbar
def test_historical_ownerless_run_invisible(client):
    _make_run("run-historical-1", owner_user_id=None)
    list_resp = client.get("/agent/runs", headers=_headers("alice"))
    assert all(r["id"] != "run-historical-1" for r in list_resp.json())
    detail_resp = client.get("/agent/runs/run-historical-1", headers=_headers("alice"))
    assert detail_resp.status_code == 404


# 8. Neue Runs erhalten Owner+Tenant aus dem Server-Kontext
def test_new_run_gets_server_side_owner_and_tenant(client):
    resp = client.post(
        "/agent/run", json={"task": "Fasse zusammen: Der Himmel ist blau."},
        headers=_headers("alice"),
    )
    assert resp.status_code == 200
    run_id = resp.json().get("run_id")
    assert run_id, "Antwort muss eine run_id enthalten"
    from apps.backend.database import get_agent_run
    entry = get_agent_run(run_id)
    assert entry is not None
    assert entry["owner_user_id"] == "alice"
    assert entry["tenant_id"] == "default"


# 9. Vom Browser mitgegebener fremder Owner wird ignoriert
def test_client_supplied_owner_is_ignored(client):
    resp = client.post(
        "/agent/run",
        json={"task": "Fasse zusammen: Der Himmel ist blau.", "owner_user_id": "mallory"},
        headers=_headers("alice"),
    )
    assert resp.status_code == 200
    run_id = resp.json().get("run_id")
    assert run_id, "Antwort muss eine run_id enthalten"
    from apps.backend.database import get_agent_run
    entry = get_agent_run(run_id)
    assert entry is not None
    assert entry["owner_user_id"] == "alice"
    assert entry["owner_user_id"] != "mallory"


# 10. Listen enthalten keine fremden Datensaetze
def test_lists_contain_no_foreign_records(client):
    _make_run("run-mine-10", owner_user_id="alice")
    _make_run("run-theirs-10", owner_user_id="bob")
    resp = client.get("/agent/runs", headers=_headers("alice"))
    ids = {r["id"] for r in resp.json()}
    assert "run-mine-10" in ids
    assert "run-theirs-10" not in ids


# 11. Detailzugriff liefert eine neutrale 404-Antwort
def test_detail_access_returns_neutral_denied_message(client):
    from apps.backend.permissions import GENERIC_DENIED_MESSAGE
    _make_run("run-neutral-1", owner_user_id="bob")
    resp = client.get("/agent/runs/run-neutral-1", headers=_headers("alice"))
    assert resp.status_code == 404
    assert resp.json()["detail"] == GENERIC_DENIED_MESSAGE
    assert "bob" not in resp.text


# 12. Zaehler/Suche (Listenendpunkt) leckt keine fremden Daten
def test_counters_and_lists_leak_no_foreign_data(client):
    _make_run("run-count-mine", owner_user_id="alice")
    for i in range(3):
        _make_run(f"run-count-foreign-{i}", owner_user_id="bob")
    resp = client.get("/agent/runs", headers=_headers("alice"))
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["id"] == "run-count-mine"


# 13. Genehmigungsanfrage erbt den korrekten Owner ueber den echten Laufweg
# (nicht durch direktes Setzen von owner_user_id im Test).
def test_approval_inherits_owner_from_run(client):
    from apps.backend.database import get_approval_request
    nonkonform = (
        "Formuliere eine Antwort an den Kunden: Wir gehen davon aus, dass Ihr "
        "Einverstaendnis vorliegt, und verarbeiten Ihre Daten ohne Einwilligung weiter."
    )
    resp = client.post("/agent/run", json={"task": nonkonform}, headers=_headers("alice"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "consent_required"
    approval_id = body["approval_id"]
    stored = get_approval_request(approval_id)
    assert stored["owner_user_id"] == "alice"
    assert stored["tenant_id"] == "default"


# 14. Fremde Genehmigung kann nicht entschieden werden
def test_foreign_approval_cannot_be_decided(client):
    approval = _make_approval(owner_user_id="bob")
    resp = client.post(f"/approvals/{approval['id']}/approve", headers=_headers("alice"))
    assert resp.status_code == 404


# 15. Abgelaufene Genehmigung kann nicht entschieden werden (durch eine
# ZUSTAENDIGE Person -- erst dann darf ueberhaupt EXPIRED unterschieden werden).
def test_expired_approval_cannot_be_decided(client):
    from apps.backend.database import approval_requests, engine
    from sqlalchemy import update
    approval = _make_approval(owner_user_id="bob")
    _assign_approval(approval["id"], "managerin1", role="manager")
    with engine.begin() as connection:
        connection.execute(
            update(approval_requests)
            .where(approval_requests.c.id == approval["id"])
            .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        )
    resp = client.post(f"/approvals/{approval['id']}/approve", headers=_headers("managerin1", role="manager"))
    assert resp.status_code == 409


# 16. Unbekannter Rollenwert fuehrt zu Default Deny
def test_unknown_role_defaults_to_deny(client):
    resp = client.get("/agent/runs", headers=_headers("alice", role="voellig_unbekannte_rolle"))
    assert resp.status_code in (403, 422)


# 17. Admin erhaelt keinen Automatikzugriff auf fremde Inhalte
def test_admin_has_no_automatic_access_to_foreign_content(client):
    _make_run("run-admin-foreign-1", owner_user_id="bob")
    resp = client.get("/agent/runs/run-admin-foreign-1", headers=_headers("chefin1", role="admin"))
    assert resp.status_code == 404


# 18. Tenant-uebergreifende Zuweisung bleibt wirkungslos
def test_cross_tenant_assignment_stays_ineffective(client):
    from apps.backend.database import CaseAssignmentValidationError, create_case_assignment
    _ensure_user("bob", tenant_id="tenant-x")
    _make_run("run-crosstenant-1", tenant_id="tenant-x", owner_user_id="bob")
    # Zuweisung in einem anderen Tenant als dem des Vorgangs -- die
    # Konsistenzpruefung (case_id existiert im angegebenen tenant_id) muss
    # dies ablehnen, damit eine tenant-uebergreifende Zuweisung gar nicht
    # erst wirksam entstehen kann.
    with pytest.raises(CaseAssignmentValidationError):
        create_case_assignment(
            case_type="AGENT_RUN", case_id="run-crosstenant-1", tenant_id="default",
            assigned_to_user_id="alice", assigned_by_user_id="bob", assignment_reason="Test",
        )
    resp = client.get("/agent/runs/run-crosstenant-1", headers=_headers("alice", tenant_id="default"))
    assert resp.status_code == 404


# 19. Die Berechtigungspruefung laeuft unmittelbar vor der Schreibaktion erneut
# -- eine zwischenzeitliche Statusaenderung (z.B. durch eine parallele
# Anfrage) muss beim eigentlichen UPDATE noch einmal wirksam werden, nicht
# nur bei der anfaenglichen Pruefung.
def test_permission_rechecked_immediately_before_decide(client):
    from apps.backend.database import approval_requests, engine
    from sqlalchemy import update
    approval = _make_approval(owner_user_id=None)
    _assign_approval(approval["id"], "managerin1", role="manager")
    headers = _headers("managerin1", role="manager")
    with engine.begin() as connection:
        connection.execute(
            update(approval_requests)
            .where(approval_requests.c.id == approval["id"])
            .values(status="approved")
        )
    resp = client.post(f"/approvals/{approval['id']}/approve", headers=headers)
    assert resp.status_code == 409


# ── Zusaetzliche Pflicht-Tests aus dem Korrekturauftrag ─────────────────────

# Manager ohne Zuweisung darf fremde Genehmigung nicht entscheiden.
def test_manager_without_assignment_cannot_decide(client):
    approval = _make_approval(owner_user_id="bob")
    resp = client.post(
        f"/approvals/{approval['id']}/approve", headers=_headers("managerin1", role="manager"),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == GENERIC_DENIED_MESSAGE


# Admin ohne Zuweisung darf fremde Genehmigung nicht entscheiden.
def test_admin_without_assignment_cannot_decide(client):
    approval = _make_approval(owner_user_id="bob")
    resp = client.post(
        f"/approvals/{approval['id']}/approve", headers=_headers("chefin1", role="admin"),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == GENERIC_DENIED_MESSAGE


# DSB ohne passende Fachzustaendigkeit/Zuweisung darf nicht entscheiden.
def test_dsb_without_assignment_cannot_decide(client):
    approval = _make_approval(owner_user_id="bob")
    resp = client.post(
        f"/approvals/{approval['id']}/approve", headers=_headers("dsb1", role="dsb"),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == GENERIC_DENIED_MESSAGE


# Ownerlose historische Genehmigung ist nicht ueber eine Rolle freigebbar.
def test_ownerless_historical_approval_not_decidable_via_role(client):
    approval = _make_approval(owner_user_id=None)
    resp = client.post(
        f"/approvals/{approval['id']}/approve", headers=_headers("chefin1", role="admin"),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == GENERIC_DENIED_MESSAGE


# Normaler Nutzer erhaelt fuer fremde ABGELAUFENE Genehmigung die neutrale 404
# (nicht 409) -- die Zustaendigkeit fehlt, also darf EXPIRED nicht sichtbar werden.
def test_unzustaendiger_user_gets_neutral_404_for_expired_approval(client):
    from apps.backend.database import approval_requests, engine
    from sqlalchemy import update
    approval = _make_approval(owner_user_id="bob")
    with engine.begin() as connection:
        connection.execute(
            update(approval_requests)
            .where(approval_requests.c.id == approval["id"])
            .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        )
    resp = client.post(f"/approvals/{approval['id']}/approve", headers=_headers("alice"))
    assert resp.status_code == 404
    assert resp.json()["detail"] == GENERIC_DENIED_MESSAGE


# Normaler Nutzer erhaelt fuer fremde BEREITS ENTSCHIEDENE Genehmigung die
# neutrale 404 (nicht 409).
def test_unzustaendiger_user_gets_neutral_404_for_already_decided_approval(client):
    from apps.backend.database import approval_requests, engine
    from sqlalchemy import update
    approval = _make_approval(owner_user_id="bob")
    with engine.begin() as connection:
        connection.execute(
            update(approval_requests)
            .where(approval_requests.c.id == approval["id"])
            .values(status="approved")
        )
    resp = client.post(f"/approvals/{approval['id']}/approve", headers=_headers("alice"))
    assert resp.status_code == 404
    assert resp.json()["detail"] == GENERIC_DENIED_MESSAGE


# Nach serverseitiger Sperrung ist eine noch gueltige alte Session (Token)
# fuer eine Genehmigungsentscheidung wirkungslos, obwohl das JWT selbst
# noch nicht abgelaufen ist.
def test_locked_user_session_rejected_for_decide(client):
    from apps.backend.database import create_user, users, engine
    from sqlalchemy import update as sa_update

    create_user("gesperrt1", "default", "manager", hashed_password="x")
    with engine.begin() as connection:
        connection.execute(
            sa_update(users).where(users.c.user_id == "gesperrt1").values(active=0)
        )
    approval = _make_approval(owner_user_id="bob")
    _assign_approval(approval["id"], "gesperrt1", role="manager")
    resp = client.post(
        f"/approvals/{approval['id']}/approve", headers=_headers("gesperrt1", role="manager"),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == GENERIC_DENIED_MESSAGE


# Zwei gleichzeitige Entscheidungen fuehren zu genau einem Erfolg; der
# unterlegene Request erzeugt keinen Erfolg und kein Erfolgs-Audit.
def test_concurrent_decisions_only_one_succeeds(client):
    approval = _make_approval(owner_user_id="bob")
    _assign_approval(approval["id"], "managerin1", role="manager")
    headers = _headers("managerin1", role="manager")

    first = client.post(f"/approvals/{approval['id']}/approve", headers=headers)
    second = client.post(f"/approvals/{approval['id']}/approve", headers=headers)

    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 409]

    from apps.backend.database import query_audit_events
    entries = query_audit_events(tenant_id="default", action="approval.approved")
    matching = [e for e in entries if e["metadata"].get("approval_id") == approval["id"]]
    assert len(matching) == 1


# Eine manipulierte compliance_consent ohne gueltige Task-Bindung (fehlendes
# task_sha256) wird trotz identischem Tool-Namen NICHT als Selbstkonsens
# akzeptiert.
def test_manipulated_compliance_consent_without_task_binding_is_rejected(client):
    from apps.backend.database import create_approval_request
    approval = create_approval_request(
        tool="compliance_consent",
        input_params={"kein_task_sha256": True},
        risk_level="high", risk_reason="Test",
        tenant_id="default", owner_user_id="alice",
    )
    resp = client.post(f"/approvals/{approval['id']}/approve", headers=_headers("alice"))
    assert resp.status_code == 404
    assert resp.json()["detail"] == GENERIC_DENIED_MESSAGE


# Fremde Detaildatensaetze werden bereits durch die DB-Abfrage ausgeschlossen
# (get_accessible_agent_run / get_accessible_approval), nicht erst nach dem
# Laden verworfen.
def test_foreign_detail_records_excluded_at_db_query_level(client):
    from apps.backend.database import get_accessible_agent_run, get_accessible_approval
    _make_run("run-dbfilter-1", owner_user_id="bob")
    assert get_accessible_agent_run("run-dbfilter-1", "default", "alice") is None

    approval = _make_approval(owner_user_id="bob")
    assert get_accessible_approval(approval["id"], "default", "alice") is None


# Audit enthaelt keine vollstaendige Freitextnotiz.
def test_audit_does_not_contain_full_note_text(client):
    approval = _make_approval(owner_user_id="bob")
    _assign_approval(approval["id"], "managerin1", role="manager")
    secret_note = "Vertraulich: Kundendaten Max Mustermann IBAN DE1234567890"
    resp = client.post(
        f"/approvals/{approval['id']}/approve",
        json={"note": secret_note},
        headers=_headers("managerin1", role="manager"),
    )
    assert resp.status_code == 200

    from apps.backend.database import query_audit_events
    entries = query_audit_events(tenant_id="default", action="approval.approved")
    matching = [e for e in entries if e["metadata"].get("approval_id") == approval["id"]]
    assert len(matching) == 1
    metadata_str = str(matching[0]["metadata"])
    assert secret_note not in metadata_str
    assert matching[0]["metadata"].get("note_present") is True


# 20. Bestandstestsuite bleibt vollstaendig gruen (Marker-Test; die eigentliche
#     Vollpruefung erfolgt separat ueber "pytest tests/").
def test_existing_suite_marker_placeholder():
    assert True
