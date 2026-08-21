"""Bereichsverwaltung: Zuweisung, Uebersicht und Mitgliederliste.

Diese Endpunkte sind die erste Stelle, an der evaluate_domain_permission()
eine echte Zugriffsentscheidung traegt -- bis hierhin existierte der
Evaluator, steuerte aber nichts. Entsprechend wird hier beides geprueft:
dass ein Berechtigter durchkommt UND dass ein Unberechtigter es nicht tut.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apps.backend.auth.jwt_handler import create_token
from apps.backend.database import engine
from apps.backend.db_schema import business_domains
from apps.backend.main import app

BASE = "domadmin"


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _seed_domains():
    """Die Testdatenbank entsteht ueber create_all(), nicht ueber Alembic --
    die Bereichscodes aus der Migration fehlen deshalb und werden hier
    gesetzt."""
    now = datetime.now(timezone.utc)
    with engine.begin() as con:
        for code, name in (("accounting", "Buchhaltung"), ("hr", "Personal")):
            exists = con.execute(
                business_domains.select().where(business_domains.c.code == code)
            ).first()
            if exists is None:
                con.execute(
                    business_domains.insert().values(
                        code=code, name=name, sensitivity_level="confidential",
                        is_system_domain=1, created_at=now, updated_at=now,
                    )
                )
    yield


def _bootstrap(client, tenant, manager="mgr", domain="accounting"):
    admin = create_token("adm", tenant, "admin")
    r = client.post(
        f"/domains/bootstrap",
        json={"domain_code": domain, "reason": "Testfreigabe",
              "first_manager_user_id": manager},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 200, r.text
    return admin


# ── Uebersicht ──────────────────────────────────────────────────────────────

def test_domain_list_requires_login(client):
    assert client.get("/domains").status_code == 401


def test_domain_list_shows_not_enabled_domains_too(client):
    """Ein Bereich ohne Freischaltzeile muss sichtbar sein -- sonst waeren
    genau die Bereiche unsichtbar, die man freischalten koennte."""
    tenant = BASE + "-list"
    token = create_token("u", tenant, "user")
    rows = client.get("/domains", headers={"Authorization": f"Bearer {token}"}).json()
    codes = {r["code"] for r in rows}
    assert "accounting" in codes and "hr" in codes
    assert all(r["is_enabled"] is False for r in rows), "ohne Bootstrap nichts freigeschaltet"


def test_domain_list_reflects_enablement(client):
    tenant = BASE + "-list2"
    _bootstrap(client, tenant)
    token = create_token("u", tenant, "user")
    rows = client.get("/domains", headers={"Authorization": f"Bearer {token}"}).json()
    by_code = {r["code"]: r for r in rows}
    assert by_code["accounting"]["is_enabled"] is True
    assert by_code["hr"]["is_enabled"] is False


def test_domain_list_is_tenant_scoped(client):
    """Die Freischaltung eines Mandanten darf in einem anderen nicht
    erscheinen."""
    _bootstrap(client, BASE + "-t1")
    other = create_token("u", BASE + "-t2", "user")
    rows = client.get("/domains", headers={"Authorization": f"Bearer {other}"}).json()
    by_code = {r["code"]: r for r in rows}
    assert by_code["accounting"]["is_enabled"] is False


# ── Mitgliederliste ─────────────────────────────────────────────────────────

def test_members_visible_for_admin(client):
    tenant = BASE + "-mem1"
    admin = _bootstrap(client, tenant, manager="mgr1")
    r = client.get("/domains/accounting/members",
                   headers={"Authorization": f"Bearer {admin}"})
    assert r.status_code == 200
    assert {m["user_id"] for m in r.json()} == {"mgr1"}


def test_members_visible_for_domain_manager(client):
    """Der domain_manager verwaltet seinen Bereich -- ohne globale
    Admin-Rolle. Das ist der Beleg, dass der Evaluator wirklich entscheidet."""
    tenant = BASE + "-mem2"
    _bootstrap(client, tenant, manager="mgr2")
    mgr = create_token("mgr2", tenant, "user")   # global nur 'user'
    r = client.get("/domains/accounting/members",
                   headers={"Authorization": f"Bearer {mgr}"})
    assert r.status_code == 200, r.text
    assert {m["user_id"] for m in r.json()} == {"mgr2"}


def test_members_denied_for_stranger(client):
    """403, nicht leere Liste: eine leere Liste waere von 'Bereich ist leer'
    nicht zu unterscheiden."""
    tenant = BASE + "-mem3"
    _bootstrap(client, tenant, manager="mgr3")
    stranger = create_token("fremd", tenant, "user")
    r = client.get("/domains/accounting/members",
                   headers={"Authorization": f"Bearer {stranger}"})
    assert r.status_code == 403


def test_members_denied_for_manager_of_other_domain(client):
    """Bereichsbindung: wer hr verwaltet, sieht accounting nicht."""
    tenant = BASE + "-mem4"
    _bootstrap(client, tenant, manager="hrmgr", domain="hr")
    _bootstrap(client, tenant, manager="accmgr", domain="accounting")
    hrmgr = create_token("hrmgr", tenant, "user")
    r = client.get("/domains/accounting/members",
                   headers={"Authorization": f"Bearer {hrmgr}"})
    assert r.status_code == 403


# ── Zuweisung ───────────────────────────────────────────────────────────────

def test_admin_can_assign_member(client):
    tenant = BASE + "-as1"
    admin = _bootstrap(client, tenant, manager="mgr")
    r = client.post(
        "/domains/accounting/members",
        json={"user_id": "neu1", "role_in_domain": "viewer",
              "assignment_reason": "Neue Kollegin Buchhaltung"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 200, r.text
    members = client.get("/domains/accounting/members",
                         headers={"Authorization": f"Bearer {admin}"}).json()
    assert {m["user_id"] for m in members} == {"mgr", "neu1"}


def test_domain_manager_can_assign_in_own_domain(client):
    tenant = BASE + "-as2"
    _bootstrap(client, tenant, manager="mgr")
    mgr = create_token("mgr", tenant, "user")
    r = client.post(
        "/domains/accounting/members",
        json={"user_id": "neu2", "role_in_domain": "contributor",
              "assignment_reason": "Unterstuetzung Monatsabschluss"},
        headers={"Authorization": f"Bearer {mgr}"},
    )
    assert r.status_code == 200, r.text


def test_stranger_cannot_assign(client):
    tenant = BASE + "-as3"
    _bootstrap(client, tenant, manager="mgr")
    stranger = create_token("fremd", tenant, "user")
    r = client.post(
        "/domains/accounting/members",
        json={"user_id": "ich_selbst", "role_in_domain": "domain_manager",
              "assignment_reason": "Selbstbedienung"},
        headers={"Authorization": f"Bearer {stranger}"},
    )
    assert r.status_code == 403


def test_assign_requires_reason(client):
    tenant = BASE + "-as4"
    admin = _bootstrap(client, tenant, manager="mgr")
    r = client.post(
        "/domains/accounting/members",
        json={"user_id": "neu", "role_in_domain": "viewer", "assignment_reason": "  "},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 400


def test_assign_rejects_unknown_role(client):
    tenant = BASE + "-as5"
    admin = _bootstrap(client, tenant, manager="mgr")
    r = client.post(
        "/domains/accounting/members",
        json={"user_id": "neu", "role_in_domain": "superuser",
              "assignment_reason": "Rollenschmuggel"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 400


def test_assign_rejects_not_enabled_domain(client):
    """Rechte auf Vorrat: eine Mitgliedschaft in einem nicht
    freigeschalteten Bereich waere bei spaeterer Freischaltung sofort
    wirksam, ohne dass jemand sie in dem Moment gepruefet haette."""
    tenant = BASE + "-as6"
    admin = _bootstrap(client, tenant, manager="mgr")   # nur accounting
    r = client.post(
        "/domains/hr/members",
        json={"user_id": "neu", "role_in_domain": "viewer",
              "assignment_reason": "Vorratsrecht"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 400


def test_assign_rejects_duplicate_active_membership(client):
    tenant = BASE + "-as7"
    admin = _bootstrap(client, tenant, manager="mgr")
    r = client.post(
        "/domains/accounting/members",
        json={"user_id": "mgr", "role_in_domain": "viewer",
              "assignment_reason": "Zweitrolle"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert r.status_code == 400
    assert "bereits" in r.json()["detail"]


def test_assigned_member_gains_exactly_the_role_rights(client):
    """Eine frisch zugewiesene viewer-Rolle darf lesen, aber nicht
    verwalten -- sonst waere die Zuweisung eine Rechteausweitung."""
    tenant = BASE + "-as8"
    admin = _bootstrap(client, tenant, manager="mgr")
    client.post(
        "/domains/accounting/members",
        json={"user_id": "leser", "role_in_domain": "viewer",
              "assignment_reason": "Nur Leserecht"},
        headers={"Authorization": f"Bearer {admin}"},
    )
    leser = create_token("leser", tenant, "user")
    # viewer hat kein membership.manage -> Mitgliederliste bleibt gesperrt
    assert client.get("/domains/accounting/members",
                      headers={"Authorization": f"Bearer {leser}"}).status_code == 403

    from apps.backend.domains import evaluate_domain_permission
    assert evaluate_domain_permission(
        tenant_id=tenant, user_id="leser",
        domain_code="accounting", action="content.read").allowed is True
    assert evaluate_domain_permission(
        tenant_id=tenant, user_id="leser",
        domain_code="accounting", action="membership.manage").allowed is False
