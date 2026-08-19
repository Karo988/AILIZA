"""Stufe B: Anwendungslogik der Bereichsrechte.

Prueft bootstrap_domain(), die Standard-Rechteprofile, den Schutz des
letzten domain_manager und evaluate_domain_permission() gegen eine echte
(migrierte) SQLite-Datenbank -- keine Mocks der Datenbankschicht, weil
genau das Zusammenspiel von Migration und Anwendungslogik geprueft werden
soll.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "apps" / "backend"


_SWAPPED_MODULE_NAMES = (
    "database", "db_schema", "domains",
    "apps.backend.database", "apps.backend.db_schema", "apps.backend.domains",
)


@pytest.fixture()
def domains_module(tmp_path, monkeypatch):
    """ACHTUNG Testisolation: dieses Modul importiert apps.backend.database/
    db_schema/domains NEU gegen eine temporaere SQLite-Datei, damit
    bootstrap_domain() gegen eine ECHT migrierte Datenbank laeuft (nicht
    gegen das gemeinsame :memory:-Testschema aus conftest.py, das die
    Migrationsdaten -- die 13 festen Bereichscodes -- nicht enthaelt).

    Ohne Teardown wuerden diese ausgetauschten Module fuer den Rest des
    Pytest-Prozesses aktiv bleiben und JEDEN anderen Test, der
    apps.backend.database (direkt oder ueber main.py-Importe) neu
    anfordert, gegen die laengst geloeschte tmp-Datei laufen lassen --
    das hat genau das beim vollen Suite-Lauf beobachtete flaechendeckende
    Auth-/DB-Fehlerbild verursacht. Deshalb: Original-Modulobjekte vor dem
    Tausch sichern und nach dem Test exakt wiederherstellen."""
    db_path = tmp_path / "domains.sqlite"
    monkeypatch.setenv("AILIZA_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND, env=dict(os.environ), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

    import apps.backend as _backend_pkg

    _saved_sys_modules = {name: sys.modules.get(name) for name in _SWAPPED_MODULE_NAMES}
    _saved_pkg_attrs = {
        attr: getattr(_backend_pkg, attr) for attr in ("database", "db_schema", "domains")
        if hasattr(_backend_pkg, attr)
    }

    for name in _SWAPPED_MODULE_NAMES:
        sys.modules.pop(name, None)
    # sys.modules.pop() allein genuegt nicht: das Elternpaket haelt die
    # importierten Submodule zusaetzlich als eigene Attribute. "from
    # apps.backend import domains" wuerde sonst ueber genau dieses
    # Attribut auf das ALTE (bereits entfernte) Modul zugreifen, ohne
    # neu zu importieren -- der neue AILIZA_DATABASE_URL-Wert wuerde nie
    # wirksam. Attribute muessen deshalb explizit entfernt werden.
    for attr in ("database", "db_schema", "domains"):
        if hasattr(_backend_pkg, attr):
            delattr(_backend_pkg, attr)

    import importlib
    domains_module = importlib.import_module("apps.backend.domains")

    try:
        yield domains_module
    finally:
        for name in _SWAPPED_MODULE_NAMES:
            sys.modules.pop(name, None)
        for name, mod in _saved_sys_modules.items():
            if mod is not None:
                sys.modules[name] = mod
        for attr in ("database", "db_schema", "domains"):
            if hasattr(_backend_pkg, attr):
                delattr(_backend_pkg, attr)
        for attr, mod in _saved_pkg_attrs.items():
            setattr(_backend_pkg, attr, mod)


def test_bootstrap_activates_domain_and_seeds_permissions(domains_module):
    result = domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="accounting", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    assert result["status"] == "enabled"

    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="mgr1", domain_code="accounting", action="membership.manage",
    )
    assert decision.allowed is True


def test_bootstrap_seeds_all_default_role_actions(domains_module):
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="hr", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    from sqlalchemy import select
    from apps.backend.db_schema import domain_role_permissions
    with domains_module.engine.begin() as con:
        rows = con.execute(
            select(domain_role_permissions.c.role_in_domain, domain_role_permissions.c.action)
            .where(domain_role_permissions.c.tenant_id == "t1")
        ).all()
    seeded = {(r[0], r[1]) for r in rows}
    for role, actions in domains_module.DEFAULT_ROLE_ACTIONS.items():
        for action in actions:
            assert (role, action) in seeded


def test_bootstrap_is_idempotent(domains_module):
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="hr", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="hr", enabled_by="admin1",
        reason="Zweiter Aufruf", first_manager_user_id="mgr1",
    )
    memberships = domains_module.list_my_domain_memberships(tenant_id="t1", user_id="mgr1")
    managers = [m for m in memberships if m["code"] == "hr" and m["role_in_domain"] == "domain_manager"]
    assert len(managers) == 1


def test_bootstrap_without_reason_is_rejected(domains_module):
    with pytest.raises(domains_module.DomainBootstrapError):
        domains_module.bootstrap_domain(
            tenant_id="t1", domain_code="hr", enabled_by="admin1",
            reason="", first_manager_user_id="mgr1",
        )


def test_bootstrap_without_first_manager_is_rejected(domains_module):
    with pytest.raises(domains_module.DomainBootstrapError):
        domains_module.bootstrap_domain(
            tenant_id="t1", domain_code="hr", enabled_by="admin1",
            reason="Erstinbetriebnahme", first_manager_user_id="",
        )


def test_last_domain_manager_cannot_be_revoked(domains_module):
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="legal", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    from sqlalchemy import select
    from apps.backend.db_schema import user_domain_memberships
    with domains_module.engine.begin() as con:
        membership_id = con.execute(
            select(user_domain_memberships.c.id)
            .where(user_domain_memberships.c.user_id == "mgr1")
        ).first()[0]

    with pytest.raises(domains_module.LastDomainManagerError):
        domains_module.revoke_membership(
            tenant_id="t1", membership_id=membership_id, revoked_by="admin1",
            revocation_reason="Testversuch",
        )


def test_second_manager_allows_revoking_the_first(domains_module):
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="legal", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    from sqlalchemy import select
    from apps.backend.db_schema import business_domains, user_domain_memberships
    with domains_module.engine.begin() as con:
        domain_id = con.execute(
            select(business_domains.c.id).where(business_domains.c.code == "legal")
        ).first()[0]
        con.execute(
            user_domain_memberships.insert().values(
                tenant_id="t1", domain_id=domain_id, user_id="mgr2",
                role_in_domain="domain_manager", valid_from=domains_module._now(),
                assigned_by="admin1", assignment_reason="Zweite Person", is_active=1, version=1,
            )
        )
        membership_id = con.execute(
            select(user_domain_memberships.c.id)
            .where(user_domain_memberships.c.user_id == "mgr1")
        ).first()[0]

    result = domains_module.revoke_membership(
        tenant_id="t1", membership_id=membership_id, revoked_by="admin1",
        revocation_reason="Rollenwechsel",
    )
    assert result["status"] == "revoked"


def test_revoke_without_reason_is_rejected(domains_module):
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="legal", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    with pytest.raises(domains_module.LastDomainManagerError):
        domains_module.revoke_membership(
            tenant_id="t1", membership_id=1, revoked_by="admin1", revocation_reason="",
        )


def test_evaluator_denies_without_domain_activation(domains_module):
    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="mgr1", domain_code="accounting", action="content.read",
    )
    assert decision.allowed is False
    assert decision.reason_code == "DOMAIN_NOT_ENABLED"


def test_evaluator_denies_unknown_domain(domains_module):
    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="mgr1", domain_code="does_not_exist", action="content.read",
    )
    assert decision.allowed is False
    assert decision.reason_code == "UNKNOWN_DOMAIN"


def test_evaluator_denies_without_membership(domains_module):
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="accounting", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="stranger", domain_code="accounting", action="content.read",
    )
    assert decision.allowed is False
    assert decision.reason_code == "NO_MEMBERSHIP"


def test_evaluator_denies_action_not_in_role_profile(domains_module):
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="accounting", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    from sqlalchemy import select
    from apps.backend.db_schema import business_domains, user_domain_memberships
    with domains_module.engine.begin() as con:
        domain_id = con.execute(
            select(business_domains.c.id).where(business_domains.c.code == "accounting")
        ).first()[0]
        con.execute(
            user_domain_memberships.insert().values(
                tenant_id="t1", domain_id=domain_id, user_id="viewer1",
                role_in_domain="viewer", valid_from=domains_module._now(),
                assigned_by="admin1", assignment_reason="Testmitgliedschaft", is_active=1, version=1,
            )
        )
    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="viewer1", domain_code="accounting", action="membership.manage",
    )
    assert decision.allowed is False
    assert decision.reason_code == "ACTION_NOT_PERMITTED"


def test_evaluator_denies_expired_membership(domains_module):
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="accounting", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    from datetime import timedelta
    from sqlalchemy import select
    from apps.backend.db_schema import business_domains, user_domain_memberships
    with domains_module.engine.begin() as con:
        domain_id = con.execute(
            select(business_domains.c.id).where(business_domains.c.code == "accounting")
        ).first()[0]
        past = domains_module._now() - timedelta(days=1)
        con.execute(
            user_domain_memberships.insert().values(
                tenant_id="t1", domain_id=domain_id, user_id="expired1",
                role_in_domain="viewer", valid_from=past - timedelta(days=10),
                valid_until=past, assigned_by="admin1", assignment_reason="Befristet",
                is_active=1, version=1,
            )
        )
    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="expired1", domain_code="accounting", action="content.read",
    )
    assert decision.allowed is False
    assert decision.reason_code == "MEMBERSHIP_EXPIRED"


def test_evaluator_denies_cross_tenant_membership(domains_module):
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="accounting", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    decision = domains_module.evaluate_domain_permission(
        tenant_id="t2", user_id="mgr1", domain_code="accounting", action="content.read",
    )
    assert decision.allowed is False
    assert decision.reason_code == "DOMAIN_NOT_ENABLED"


def test_evaluator_rejects_unknown_action(domains_module):
    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="mgr1", domain_code="accounting", action="content.destroy",
    )
    assert decision.allowed is False
    assert decision.reason_code == "UNKNOWN_ACTION"


# ── Rollen-Rechte-Matrix ────────────────────────────────────────────────────
# Vollstaendige Abdeckung der V1-Bereichsrollen gegen alle 8 Aktionen: fuer
# JEDE Rolle wird sowohl geprueft, was sie darf, als auch was sie NICHT darf.
# Eine reine Positivpruefung wuerde eine zu weit gefasste Rechtevergabe nicht
# auffallen lassen -- genau die waere aber der sicherheitsrelevante Fehler.

_ROLE_MATRIX = {
    "viewer": {"domain.view", "content.read"},
    "contributor": {"domain.view", "content.read", "content.create", "content.update"},
    "reviewer": {"domain.view", "content.read", "content.create", "content.update",
                 "content.approve", "content.export"},
    "domain_manager": {"domain.view", "content.read", "content.create", "content.update",
                       "content.approve", "content.export", "action.execute",
                       "membership.manage"},
}


def _add_member(domains_module, tenant_id, domain_code, user_id, role):
    from sqlalchemy import select
    from apps.backend.db_schema import business_domains, user_domain_memberships
    with domains_module.engine.begin() as con:
        domain_id = con.execute(
            select(business_domains.c.id).where(business_domains.c.code == domain_code)
        ).first()[0]
        con.execute(
            user_domain_memberships.insert().values(
                tenant_id=tenant_id, domain_id=domain_id, user_id=user_id,
                role_in_domain=role, valid_from=domains_module._now(),
                assigned_by="admin1", assignment_reason="Testmitgliedschaft",
                is_active=1, version=1,
            )
        )


@pytest.mark.parametrize("role", sorted(_ROLE_MATRIX))
@pytest.mark.parametrize("action", sorted(
    {a for allowed in _ROLE_MATRIX.values() for a in allowed}
))
def test_role_permission_matrix(domains_module, role, action):
    """Jede V1-Rolle gegen jede Aktion -- erlaubt UND verweigert."""
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="accounting", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="seed_mgr",
    )
    user_id = f"u_{role}"
    if role != "domain_manager":
        _add_member(domains_module, "t1", "accounting", user_id, role)
    else:
        user_id = "seed_mgr"  # vom Bootstrap bereits als domain_manager angelegt

    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id=user_id, domain_code="accounting", action=action,
    )
    expected = action in _ROLE_MATRIX[role]
    assert decision.allowed is expected, (
        f"Rolle {role!r} und Aktion {action!r}: erwartet allowed={expected}, "
        f"erhalten {decision.allowed} ({decision.reason_code})"
    )
    if not expected:
        assert decision.reason_code == "ACTION_NOT_PERMITTED"


def test_domain_manager_rights_do_not_leak_into_other_domain(domains_module):
    """Bereichsbindung: domain_manager in einem Bereich hat in einem ZWEITEN
    freigeschalteten Bereich desselben Mandanten keinerlei Rechte. Ohne diese
    Pruefung koennte eine fehlende domain_id-Bedingung unbemerkt bleiben."""
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="accounting", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr_acc",
    )
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="hr", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr_hr",
    )
    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="mgr_acc", domain_code="hr", action="membership.manage",
    )
    assert decision.allowed is False
    assert decision.reason_code == "NO_MEMBERSHIP"


def test_evaluator_denies_when_domain_disabled_for_tenant(domains_module):
    """Fail-closed bei nachtraeglich deaktiviertem Bereich: eine bestehende
    aktive Mitgliedschaft darf den Zugriff NICHT am Mandanten-Schalter
    vorbei erhalten."""
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="accounting", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    assert domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="mgr1", domain_code="accounting", action="content.read",
    ).allowed is True

    from apps.backend.db_schema import tenant_business_domains
    with domains_module.engine.begin() as con:
        con.execute(
            tenant_business_domains.update()
            .where(tenant_business_domains.c.tenant_id == "t1")
            .values(is_enabled=0)
        )

    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="mgr1", domain_code="accounting", action="content.read",
    )
    assert decision.allowed is False
    assert decision.reason_code == "DOMAIN_NOT_ENABLED"


def test_evaluator_denies_revoked_membership(domains_module):
    """Ein Widerruf muss sofort wirken -- die Zeile bleibt als Nachweis
    erhalten, darf aber keinen Zugriff mehr gewaehren."""
    domains_module.bootstrap_domain(
        tenant_id="t1", domain_code="accounting", enabled_by="admin1",
        reason="Erstinbetriebnahme", first_manager_user_id="mgr1",
    )
    _add_member(domains_module, "t1", "accounting", "contrib1", "contributor")
    assert domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="contrib1", domain_code="accounting", action="content.create",
    ).allowed is True

    from sqlalchemy import select
    from apps.backend.db_schema import user_domain_memberships
    with domains_module.engine.begin() as con:
        membership_id = con.execute(
            select(user_domain_memberships.c.id)
            .where(user_domain_memberships.c.user_id == "contrib1")
        ).first()[0]
    domains_module.revoke_membership(
        tenant_id="t1", membership_id=membership_id, revoked_by="admin1",
        revocation_reason="Rollenwechsel",
    )

    decision = domains_module.evaluate_domain_permission(
        tenant_id="t1", user_id="contrib1", domain_code="accounting", action="content.create",
    )
    assert decision.allowed is False
    assert decision.reason_code == "NO_MEMBERSHIP"
