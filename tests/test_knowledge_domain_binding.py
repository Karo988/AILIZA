"""Wissensquellen: Bereichsbindung schraenkt ein, erweitert nie.

Die gefaehrlichste denkbare Fehlfunktion ist nicht "zu wenig sichtbar",
sondern "zu viel": wenn ein Leserecht im Bereich ein fremdes, privates
Dokument sichtbar machen wuerde. Genau darauf zielt der Grossteil dieser
Tests.

Der zweite Schwerpunkt sind Bestandsdaten: eine Quelle ohne
Bereichsbindung muss sich exakt wie vor der Migration verhalten -- sonst
waere die Einfuehrung der Bindung eine stille Sichtbarkeitsaenderung.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from apps.backend.auth.jwt_handler import create_token
from apps.backend.database import engine
from apps.backend.db_schema import business_domains, knowledge_sources
from apps.backend.knowledge_access import may_read_source
from apps.backend.main import app

BASE = "kdbind"


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _seed_domains():
    now = datetime.now(timezone.utc)
    with engine.begin() as con:
        for code, name in (("accounting", "Buchhaltung"), ("hr", "Personal")):
            if con.execute(
                business_domains.select().where(business_domains.c.code == code)
            ).first() is None:
                con.execute(business_domains.insert().values(
                    code=code, name=name, sensitivity_level="confidential",
                    is_system_domain=1, created_at=now, updated_at=now,
                ))
    yield


def _add_source(tenant, owner, *, scope="private", domain=None, title="Dok"):
    now = datetime.now(timezone.utc)
    with engine.begin() as con:
        r = con.execute(knowledge_sources.insert().values(
            tenant_id=tenant, uploaded_by=owner, source_type="upload",
            title=title, status="ready", visibility_scope=scope,
            domain_code=domain, created_at=now, updated_at=now,
        ))
        return r.inserted_primary_key[0]


def _src(tenant, owner, scope="private", domain=None):
    return {"tenant_id": tenant, "uploaded_by": owner,
            "visibility_scope": scope, "domain_code": domain}


def _bootstrap(client, tenant, manager, domain="accounting"):
    admin = create_token("adm", tenant, "admin")
    r = client.post("/domains/bootstrap",
                    json={"domain_code": domain, "reason": "Testfreigabe",
                          "first_manager_user_id": manager},
                    headers={"Authorization": f"Bearer {admin}"})
    assert r.status_code == 200, r.text
    return admin


# ── Bestandsdaten: ohne Bindung aendert sich nichts ─────────────────────────

def test_unbound_source_stays_visible_to_owner():
    assert may_read_source(tenant_id="t", user_id="a",
                           source=_src("t", "a")) is True


def test_unbound_private_source_stays_hidden_from_others():
    assert may_read_source(tenant_id="t", user_id="b",
                           source=_src("t", "a")) is False


def test_unbound_shared_source_stays_visible_in_tenant():
    assert may_read_source(tenant_id="t", user_id="b",
                           source=_src("t", "a", scope="company")) is True


def test_unknown_scope_is_treated_as_private():
    """Fail-closed: ein unbekannter Scope darf nicht versehentlich als
    'irgendwie geteilt' gelten."""
    assert may_read_source(tenant_id="t", user_id="b",
                           source=_src("t", "a", scope="voellig_neu")) is False


def test_foreign_tenant_is_never_visible():
    assert may_read_source(tenant_id="t1", user_id="a",
                           source=_src("t2", "a", scope="company")) is False


# ── Kernregel: Bindung schraenkt ein, erweitert NIE ─────────────────────────

def test_domain_right_does_not_open_foreign_private_source(client):
    """DER wichtigste Test: ein Leserecht im Bereich darf ein fremdes,
    privates Dokument NICHT sichtbar machen. Waere die Reihenfolge in
    may_read_source() vertauscht, wuerde genau das passieren."""
    tenant = BASE + "-x1"
    _bootstrap(client, tenant, "mgr")
    # mgr hat als domain_manager content.read in accounting -- das Dokument
    # gehoert aber jemand anderem und ist privat.
    src = _src(tenant, "fremd", scope="private", domain="accounting")
    assert may_read_source(tenant_id=tenant, user_id="mgr", source=src) is False


def test_binding_hides_shared_source_from_non_member(client):
    """Eine geteilte Quelle wird durch die Bindung enger, nicht weiter."""
    tenant = BASE + "-x2"
    _bootstrap(client, tenant, "mgr")
    shared_bound = _src(tenant, "mgr", scope="company", domain="accounting")
    # mgr ist Mitglied -> sichtbar
    assert may_read_source(tenant_id=tenant, user_id="mgr", source=shared_bound) is True
    # aussenstehende Person im selben Mandanten -> jetzt NICHT mehr
    assert may_read_source(tenant_id=tenant, user_id="fremd", source=shared_bound) is False


def test_binding_hides_own_source_without_domain_right(client):
    """Auch die eigene Quelle wird unsichtbar, wenn sie einem Bereich
    zugeordnet ist, in dem man kein Leserecht hat. Die Zuordnung stuft den
    INHALT ein, nicht den Eigentuemer."""
    tenant = BASE + "-x3"
    _bootstrap(client, tenant, "mgr", domain="accounting")
    own_bound = _src(tenant, "eigentuemer", scope="private", domain="accounting")
    assert may_read_source(tenant_id=tenant, user_id="eigentuemer",
                           source=own_bound) is False


def test_binding_to_not_enabled_domain_hides_everything(client):
    """Ein Bereich, der im Mandanten nicht freigeschaltet ist, gewaehrt
    niemandem Leserecht -- also bleibt die Quelle fuer alle unsichtbar."""
    tenant = BASE + "-x4"
    src = _src(tenant, "a", scope="company", domain="hr")
    assert may_read_source(tenant_id=tenant, user_id="a", source=src) is False


# ── Listen-Endpunkt ────────────────────────────────────────────────────────

def test_list_requires_login(client):
    assert client.get("/knowledge").status_code == 401


def test_list_shows_own_unbound_source(client):
    tenant = BASE + "-l1"
    _add_source(tenant, "u1", title="Meine Notiz")
    tok = create_token("u1", tenant, "user")
    rows = client.get("/knowledge", headers={"Authorization": f"Bearer {tok}"}).json()
    assert {r["title"] for r in rows} == {"Meine Notiz"}


def test_list_hides_foreign_private_source(client):
    tenant = BASE + "-l2"
    _add_source(tenant, "u1", title="Fremd")
    tok = create_token("u2", tenant, "user")
    rows = client.get("/knowledge", headers={"Authorization": f"Bearer {tok}"}).json()
    assert rows == []


def test_list_hides_bound_source_from_non_member(client):
    tenant = BASE + "-l3"
    _bootstrap(client, tenant, "mgr")
    _add_source(tenant, "mgr", scope="company", domain="accounting", title="Buchhaltung")
    _add_source(tenant, "mgr", scope="company", title="Allgemein")

    mgr = create_token("mgr", tenant, "user")
    seen_mgr = {r["title"] for r in client.get(
        "/knowledge", headers={"Authorization": f"Bearer {mgr}"}).json()}
    assert seen_mgr == {"Buchhaltung", "Allgemein"}

    fremd = create_token("fremd", tenant, "user")
    seen_fremd = {r["title"] for r in client.get(
        "/knowledge", headers={"Authorization": f"Bearer {fremd}"}).json()}
    assert seen_fremd == {"Allgemein"}, "Bereichsgebundenes darf nicht erscheinen"


def test_list_never_exposes_storage_path_or_hash(client):
    """Speicherpfad und Inhaltshash duerfen den Server nie verlassen."""
    tenant = BASE + "-l4"
    _add_source(tenant, "u1")
    tok = create_token("u1", tenant, "user")
    rows = client.get("/knowledge", headers={"Authorization": f"Bearer {tok}"}).json()
    assert rows
    for r in rows:
        assert "storage_path" not in r
        assert "content_hash" not in r


def test_list_is_tenant_scoped(client):
    _add_source(BASE + "-t1", "u1", scope="company", title="Mandant1")
    tok = create_token("u1", BASE + "-t2", "user")
    rows = client.get("/knowledge", headers={"Authorization": f"Bearer {tok}"}).json()
    assert all(r["title"] != "Mandant1" for r in rows)


# ── Zuordnung aendern ──────────────────────────────────────────────────────

def test_bind_requires_reason(client):
    tenant = BASE + "-b1"
    _bootstrap(client, tenant, "mgr")
    sid = _add_source(tenant, "mgr")
    tok = create_token("mgr", tenant, "user")
    r = client.post(f"/knowledge/{sid}/domain",
                    json={"domain_code": "accounting", "reason": " "},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400


def test_bind_requires_update_right_in_target_domain(client):
    """Ohne content.update im Zielbereich koennte man Inhalte in einen
    Bereich schieben, in dem man selbst nichts zu sagen hat."""
    tenant = BASE + "-b2"
    _bootstrap(client, tenant, "mgr")
    sid = _add_source(tenant, "fremder_nutzer", scope="company")
    outsider = create_token("fremder_nutzer", tenant, "user")
    r = client.post(f"/knowledge/{sid}/domain",
                    json={"domain_code": "accounting", "reason": "Verschieben"},
                    headers={"Authorization": f"Bearer {outsider}"})
    assert r.status_code == 403


def test_bind_succeeds_for_domain_member(client):
    tenant = BASE + "-b3"
    _bootstrap(client, tenant, "mgr")
    sid = _add_source(tenant, "mgr")
    tok = create_token("mgr", tenant, "user")
    r = client.post(f"/knowledge/{sid}/domain",
                    json={"domain_code": "accounting", "reason": "Gehoert zur Buchhaltung"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    assert r.json()["domain_code"] == "accounting"


def test_unbind_requires_update_right_in_current_domain(client):
    """Das Aufloesen einer Bindung ERWEITERT die Sichtbarkeit -- deshalb
    braucht es das Recht im bisherigen Bereich, nicht nur Lesezugriff."""
    tenant = BASE + "-b4"
    _bootstrap(client, tenant, "mgr")
    sid = _add_source(tenant, "mgr", scope="company", domain="accounting")
    # viewer darf lesen, aber nicht aendern.
    # Die Mitgliedschaft wird direkt gesetzt statt ueber den
    # Zuweisungs-Endpunkt: dieser Branch zweigt von main ab, der Endpunkt
    # liegt in einem anderen, noch offenen Paket. Der Test soll die
    # Bereichsbindung pruefen, nicht die Zuweisung.
    from apps.backend.db_schema import user_domain_memberships
    with engine.begin() as con:
        did = con.execute(
            business_domains.select().where(business_domains.c.code == "accounting")
        ).first().id
        con.execute(user_domain_memberships.insert().values(
            tenant_id=tenant, domain_id=did, user_id="leser",
            role_in_domain="viewer", valid_from=datetime.now(timezone.utc),
            assigned_by="adm", assignment_reason="Nur Leserecht",
            is_active=1, version=1,
        ))
    leser = create_token("leser", tenant, "user")
    r = client.post(f"/knowledge/{sid}/domain",
                    json={"domain_code": None, "reason": "Freigeben fuer alle"},
                    headers={"Authorization": f"Bearer {leser}"})
    assert r.status_code == 403


def test_bind_unknown_source_returns_404(client):
    tenant = BASE + "-b5"
    tok = create_token("u", tenant, "user")
    r = client.post("/knowledge/999999/domain",
                    json={"domain_code": "accounting", "reason": "Testgrund"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 404


def test_bind_foreign_private_source_returns_404(client):
    """404, nicht 403: sonst waere die Existenz eines fremden Dokuments
    ueber unterschiedliche Antworten erkennbar."""
    tenant = BASE + "-b6"
    sid = _add_source(tenant, "eigentuemer")
    fremd = create_token("fremd", tenant, "user")
    r = client.post(f"/knowledge/{sid}/domain",
                    json={"domain_code": "accounting", "reason": "Neugier"},
                    headers={"Authorization": f"Bearer {fremd}"})
    assert r.status_code == 404
