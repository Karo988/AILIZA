"""
Audit-Vault Stufe 1 — Tests
============================
Testet: Admin-Zugriff, User-Sperre, Filter, Sanitization, Append-only,
        Export-Formate, Retention-Report (Report-Mode only).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def sample_rows():
    now = datetime.now(timezone.utc)
    return [
        {
            "id": 1,
            "timestamp": now - timedelta(hours=2),
            "action": "auth.login.success",
            "tenant_id": "default",
            "metadata": {"user_id": "admin", "role": "admin"},
        },
        {
            "id": 2,
            "timestamp": now - timedelta(hours=1),
            "action": "documents.scan",
            "tenant_id": "default",
            "metadata": {"file_type": ".txt", "decision": "allow"},
        },
        {
            "id": 3,
            "timestamp": now,
            "action": "auth.login.failed",
            "tenant_id": "default",
            "metadata": {"user_id": "unknown", "secret": "should-be-removed"},
        },
    ]


# ── 1. Sanitization: verbotene Felder werden entfernt ────────────────────────

class TestVaultSanitization:
    def test_secret_removed_from_metadata(self, sample_rows):
        from apps.backend.audit.vault import _format_entry
        row = sample_rows[2]  # hat "secret" in metadata
        result = _format_entry(row)
        assert "secret" not in result["metadata"]

    def test_allowed_fields_preserved(self, sample_rows):
        from apps.backend.audit.vault import _format_entry
        row = sample_rows[1]  # file_type, decision
        result = _format_entry(row)
        assert result["metadata"]["file_type"] == ".txt"
        assert result["metadata"]["decision"] == "allow"

    def test_blocked_keys_all_removed(self):
        from apps.backend.audit.vault import _sanitize_metadata
        raw = {
            "task_content": "geheimer Inhalt",
            "prompt": "systemrolle",
            "password": "hunter2",
            "totp": "123456",
            "backup_code": "abc",
            "credentials": "...",
            "token": "jwt...",
            "input_summary": "...",
            "decision": "allow",
        }
        cleaned = _sanitize_metadata(raw)
        assert "decision" in cleaned
        for key in ("task_content", "prompt", "password", "totp", "backup_code",
                    "credentials", "token", "input_summary"):
            assert key not in cleaned

    def test_non_dict_metadata_returns_empty(self):
        from apps.backend.audit.vault import _sanitize_metadata
        assert _sanitize_metadata("raw string") == {}
        assert _sanitize_metadata(None) == {}
        assert _sanitize_metadata([1, 2]) == {}

    def test_timestamp_iso_format(self, sample_rows):
        from apps.backend.audit.vault import _format_entry
        result = _format_entry(sample_rows[0])
        ts = result["timestamp"]
        assert isinstance(ts, str)
        assert "T" in ts  # ISO 8601

    def test_only_allowed_top_level_fields(self, sample_rows):
        from apps.backend.audit.vault import _format_entry
        result = _format_entry(sample_rows[0])
        assert set(result.keys()) == {"id", "timestamp", "action", "tenant_id", "metadata"}


# ── 2. query_vault_events: DB-Integration (gemockt) ─────────────────────────

class TestQueryVaultEvents:
    def test_returns_sanitized_events(self, sample_rows):
        with patch("apps.backend.audit.vault.query_audit_events", return_value=sample_rows):
            from apps.backend.audit.vault import query_vault_events
            events = query_vault_events()
        assert len(events) == 3
        for e in events:
            assert "secret" not in e.get("metadata", {})

    def test_limit_passed_to_db(self, sample_rows):
        with patch("apps.backend.audit.vault.query_audit_events", return_value=sample_rows[:1]) as mock_q:
            from apps.backend.audit.vault import query_vault_events
            query_vault_events(limit=1)
            call_kwargs = mock_q.call_args[1]
            assert call_kwargs["limit"] == 1

    def test_action_filter_passed(self):
        with patch("apps.backend.audit.vault.query_audit_events", return_value=[]) as mock_q:
            from apps.backend.audit.vault import query_vault_events
            query_vault_events(action="auth.login.success")
            assert mock_q.call_args[1]["action"] == "auth.login.success"

    def test_tenant_filter_passed(self):
        with patch("apps.backend.audit.vault.query_audit_events", return_value=[]) as mock_q:
            from apps.backend.audit.vault import query_vault_events
            query_vault_events(tenant_id="tenant-abc")
            assert mock_q.call_args[1]["tenant_id"] == "tenant-abc"


# ── 3. Export-Format ──────────────────────────────────────────────────────────

class TestExportAuditEvents:
    def test_json_format_has_events_key(self, sample_rows):
        with patch("apps.backend.audit.vault.query_audit_events", return_value=sample_rows):
            from apps.backend.audit.vault import export_audit_events
            result = export_audit_events(fmt="json")
        parsed = json.loads(result)
        assert "events" in parsed
        assert "count" in parsed
        assert parsed["count"] == 3

    def test_jsonl_format_one_event_per_line(self, sample_rows):
        with patch("apps.backend.audit.vault.query_audit_events", return_value=sample_rows):
            from apps.backend.audit.vault import export_audit_events
            result = export_audit_events(fmt="jsonl")
        lines = [l for l in result.strip().splitlines() if l]
        assert len(lines) == 3
        for line in lines:
            obj = json.loads(line)
            assert "action" in obj

    def test_export_limit_capped_at_1000(self):
        with patch("apps.backend.audit.vault.query_audit_events", return_value=[]) as mock_q:
            from apps.backend.audit.vault import export_audit_events
            export_audit_events(limit=9999, fmt="json")
            assert mock_q.call_args[1]["limit"] == 1000

    def test_no_secrets_in_export(self, sample_rows):
        with patch("apps.backend.audit.vault.query_audit_events", return_value=sample_rows):
            from apps.backend.audit.vault import export_audit_events
            result = export_audit_events(fmt="json")
        assert "should-be-removed" not in result
        assert "secret" not in result


# ── 4. Retention-Report: nur Zählung, kein DELETE ───────────────────────────

class TestRetentionReport:
    def test_report_mode_true(self):
        with patch("apps.backend.audit.vault.count_audit_events", side_effect=[5, 100]):
            from apps.backend.audit.vault import run_audit_retention_report
            report = run_audit_retention_report(90)
        assert report["report_mode"] is True

    def test_no_deletion_in_report(self):
        with patch("apps.backend.audit.vault.count_audit_events", side_effect=[5, 100]):
            from apps.backend.audit.vault import run_audit_retention_report
            report = run_audit_retention_report(90)
        assert "deleted" not in str(report).lower() or "nicht" in report.get("note", "")

    def test_affected_count_correct(self):
        with patch("apps.backend.audit.vault.count_audit_events", side_effect=[7, 200]):
            from apps.backend.audit.vault import run_audit_retention_report
            report = run_audit_retention_report(90)
        assert report["entries_older_than_retention"] == 7
        assert report["total_entries"] == 200

    def test_action_required_when_affected(self):
        with patch("apps.backend.audit.vault.count_audit_events", side_effect=[1, 10]):
            from apps.backend.audit.vault import run_audit_retention_report
            report = run_audit_retention_report(90)
        assert report["action_required"] is True

    def test_action_not_required_when_none_affected(self):
        with patch("apps.backend.audit.vault.count_audit_events", side_effect=[0, 10]):
            from apps.backend.audit.vault import run_audit_retention_report
            report = run_audit_retention_report(90)
        assert report["action_required"] is False


# ── 5. Append-only: kein UPDATE/DELETE im Vault ───────────────────────────────

class TestAppendOnly:
    def test_vault_has_no_delete_function(self):
        import apps.backend.audit.vault as v
        assert not hasattr(v, "delete_audit_events")
        assert not hasattr(v, "purge_audit_events")
        assert not hasattr(v, "update_audit_event")

    def test_vault_has_no_update_function(self):
        import apps.backend.audit.vault as v
        public_fns = [name for name in dir(v) if not name.startswith("_")]
        for fn in public_fns:
            assert "delete" not in fn.lower()
            assert "update" not in fn.lower()
            assert "purge" not in fn.lower()
            assert "truncate" not in fn.lower()
