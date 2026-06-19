from apps.backend import database


def setup_module(module):
    database.init_db()


def test_performance_log_has_no_content():
    database.write_performance_log(latency_ms=120, route="standard", provider="mock",
                                   error_type=None, tenant_id="default")
    rows = database.list_performance_logs(tenant_id="default")
    assert rows
    row = rows[0]
    # Es darf keine Prompt-/Antwort-/Secret-Spalte existieren.
    for forbidden in ("prompt", "content", "answer", "response", "secret"):
        assert forbidden not in row


def test_security_log_records_only_metadata():
    database.write_security_log(incident_type="blocked_credentials", severity="high",
                                tenant_id="default")
    # Tabelle hat nur Metadaten-Spalten.
    cols = {c.name for c in database.security_logs.columns}
    assert "content" not in cols
    assert "prompt" not in cols


def test_cost_log_no_content():
    database.write_cost_log(tokens_in=10, tokens_out=5, provider="mock", model="m",
                            tenant_id="default", use_case="test", cost_estimate=0.001)
    cols = {c.name for c in database.cost_logs.columns}
    assert "content" not in cols and "prompt" not in cols
