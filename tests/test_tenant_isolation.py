from apps.backend import database


def setup_module(module):
    database.init_db()


def test_audit_tenant_isolation():
    database.write_audit_entry("x", {"k": "v"}, tenant_id="tenant_a")
    database.write_audit_entry("y", {"k": "v"}, tenant_id="tenant_b")
    a = database.list_audit_entries(tenant_id="tenant_a")
    b = database.list_audit_entries(tenant_id="tenant_b")
    assert all(r["tenant_id"] == "tenant_a" for r in a)
    assert all(r["tenant_id"] == "tenant_b" for r in b)
    assert not any(r["tenant_id"] == "tenant_b" for r in a)


def test_agent_runs_tenant_isolation():
    database.create_agent_run("run-a", "task", tenant_id="tenant_a")
    database.create_agent_run("run-b", "task", tenant_id="tenant_b")
    a = database.list_agent_runs(tenant_id="tenant_a")
    assert all(r["tenant_id"] == "tenant_a" for r in a)
    assert any(r["id"] == "run-a" for r in a)
    assert not any(r["id"] == "run-b" for r in a)
