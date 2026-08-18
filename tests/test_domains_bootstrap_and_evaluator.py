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


@pytest.fixture()
def domains_module(tmp_path, monkeypatch):
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
    for mod in ("database", "db_schema", "domains", "apps.backend.database",
                "apps.backend.db_schema", "apps.backend.domains"):
        sys.modules.pop(mod, None)
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
    return domains_module


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
