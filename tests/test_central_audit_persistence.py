"""Arbeitspaket 1: AuditLogger (agent/agent_core.py, agent/tool_executor.py)
schreibt jetzt dauerhaft in die zentrale audit_logs-Hash-Chain, statt in eine
zweite, standardmaessig flüchtige sqlite3-Datenbank (":memory:").

Scope: apps/backend/audit/audit_logger.py. Keine zweite Audit-Datenbank,
keine Aenderung der bestehenden Hash-Chain-Logik in database.py/audit/vault.py.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.audit.audit_logger import AuditLogger
from apps.backend.audit.vault import verify_audit_chain
from apps.backend.database import engine, init_db, metadata_obj, query_audit_events


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


# ── 1. Speicherung bleibt nach neuer Verbindung erhalten ─────────────────────

def test_events_persist_across_new_connection():
    logger = AuditLogger(session_id="sess-persist", user_id="alice")
    logger.log_conversation_start(task_id="t1", user_message_hash="h1")

    # Neue, unabhaengige Verbindung/Abfrage -- kein In-Prozess-Cache, der
    # den Nachweis verfaelschen koennte.
    with engine.connect() as fresh_connection:
        rows = fresh_connection.exec_driver_sql(
            "SELECT action FROM audit_logs WHERE action = 'agent.conversation_start'"
        ).fetchall()
    assert len(rows) == 1


# ── 2. Hash-Chain ist gueltig ────────────────────────────────────────────────

def test_hash_chain_remains_valid_after_agent_events():
    logger = AuditLogger(session_id="sess-chain", user_id="alice")
    logger.log_conversation_start(task_id="t1", user_message_hash="h1")
    logger.log_tool_call(tool_name="web_search", task_id="t1", approved=True)
    logger.log_conversation_end(task_id="t1", success=True, duration_ms=120)

    result = verify_audit_chain()
    assert result["ok"] is True
    assert result["checked"] >= 3


# ── 3. Agent-Ereignisse landen genau einmal in audit_logs ────────────────────

def test_each_agent_event_creates_exactly_one_audit_entry():
    logger = AuditLogger(session_id="sess-once", user_id="alice")
    logger.log_tool_registered(tool_name="web_search", requires_approval=False)

    rows = query_audit_events(action="agent.tool_registered", limit=100)
    matching = [r for r in rows if r["metadata"].get("session_id") == "sess-once"]
    assert len(matching) == 1


def test_no_second_audit_database_file_created(tmp_path, monkeypatch):
    """AuditLogger darf keine eigene zweite sqlite3-Datei mehr anlegen --
    reiner Import-/Attribut-Nachweis: die Klasse haelt keine eigene
    Connection/kein eigenes db_path-Attribut mehr."""
    logger = AuditLogger(session_id="sess-nodb", user_id="alice")
    assert not hasattr(logger, "_conn")
    assert not hasattr(logger, "_db_path")


# ── 4. Fehler fuehren nicht zu unbemerktem Audit-Verlust ─────────────────────

def test_write_failure_is_not_silently_swallowed(monkeypatch, caplog):
    import apps.backend.audit.audit_logger as audit_logger_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("simulierter Audit-Schreibfehler")

    monkeypatch.setattr("apps.backend.database.write_audit_entry", _boom)

    logger = AuditLogger(session_id="sess-fail", user_id="alice")
    with caplog.at_level("ERROR"):
        with pytest.raises(RuntimeError):
            logger.log_error(task_id="t1", error="etwas ging schief")

    assert any("AUDIT-SCHREIBFEHLER" in rec.message for rec in caplog.records)
    # Kein Eintrag wurde faelschlich als erfolgreich gezaehlt:
    assert logger._entry_count == 0


# ── 5. Sanitisierung: keine sensiblen Rohdaten zusaetzlich gespeichert ───────

def test_blocked_metadata_keys_are_stripped():
    logger = AuditLogger(session_id="sess-safe", user_id="alice")
    logger._log("tool_call", {
        "tool_name": "web_search",
        "prompt": "geheimer Nutzertext",
        "credentials": "sk-should-not-appear",
    })
    rows = query_audit_events(action="agent.tool_call", limit=10)
    matching = [r for r in rows if r["metadata"].get("session_id") == "sess-safe"]
    assert len(matching) == 1
    metadata = matching[0]["metadata"]
    assert "prompt" not in metadata
    assert "credentials" not in metadata
    assert metadata.get("tool_name") == "web_search"


# ── 6. Bestehende Aufrufer (tool_executor.py) bleiben kompatibel ─────────────

def test_tool_executor_call_signatures_still_work():
    """Reiner Signaturnachweis fuer die in tool_executor.py verwendeten
    Aufrufe -- kein Verhalten des Tool-Executors selbst getestet."""
    logger = AuditLogger(session_id="sess-exec", user_id="alice")
    logger.log_tool_call(tool_name="fetch", task_id="t1", approved=False)
    logger.log_human_oversight(action="fetch", decision="denied")
    rows = query_audit_events(tenant_id="default", limit=100)
    matching = [r for r in rows if r["metadata"].get("session_id") == "sess-exec"]
    assert len(matching) == 2


# ── 7. delete_user_audit_data(): keine direkte Loeschung aus der Hash-Chain ──

def test_delete_user_audit_data_has_original_signature():
    import inspect
    sig = inspect.signature(AuditLogger.delete_user_audit_data)
    params = list(sig.parameters)
    assert params == ["self", "user_id"]


def test_delete_user_audit_data_raises_without_confirmed_process():
    from apps.backend.audit.audit_logger import AuditChainDeletionNotAllowed

    logger = AuditLogger(session_id="sess-del", user_id="alice")
    with pytest.raises(AuditChainDeletionNotAllowed):
        logger.delete_user_audit_data(user_id="bob")


def test_delete_user_audit_data_does_not_touch_audit_logs():
    from apps.backend.audit.audit_logger import AuditChainDeletionNotAllowed

    logger = AuditLogger(session_id="sess-del2", user_id="alice")
    logger.log_conversation_start(task_id="t1", user_message_hash="h1")

    with engine.connect() as conn:
        before = conn.exec_driver_sql("SELECT COUNT(*) FROM audit_logs").scalar()

    with pytest.raises(AuditChainDeletionNotAllowed):
        logger.delete_user_audit_data(user_id="alice")

    with engine.connect() as conn:
        after = conn.exec_driver_sql("SELECT COUNT(*) FROM audit_logs").scalar()
    assert before == after

    result = verify_audit_chain()
    assert result["ok"] is True


# ── 8. Rekursive Sanitisierung verschachtelter sensibler Schluessel ──────────

def test_nested_blocked_keys_are_stripped_recursively():
    logger = AuditLogger(session_id="sess-nested", user_id="alice")
    logger._log("tool_call", {
        "tool_name": "web_search",
        "context": {
            "nested": {
                "prompt": "sollte verschwinden",
                "credentials": "sollte auch verschwinden",
                "harmless": "bleibt erhalten",
            },
        },
        "items": [
            {"password": "sollte verschwinden"},
            {"harmless_item": "bleibt erhalten"},
        ],
    })
    rows = query_audit_events(action="agent.tool_call", limit=10)
    matching = [r for r in rows if r["metadata"].get("session_id") == "sess-nested"]
    assert len(matching) == 1
    metadata = matching[0]["metadata"]

    nested = metadata["context"]["nested"]
    assert "prompt" not in nested
    assert "credentials" not in nested
    assert nested.get("harmless") == "bleibt erhalten"

    items = metadata["items"]
    assert "password" not in items[0]
    assert items[1].get("harmless_item") == "bleibt erhalten"
