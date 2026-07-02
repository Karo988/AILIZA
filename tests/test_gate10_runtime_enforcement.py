"""
Gate 10 Runtime Enforcement Tests
===================================
Prüft dass Gate 10 beim Backend-Start verbindlich aktiv ist und
bei defekter Governance-Konfiguration niemals normaler Betrieb möglich ist.
"""
from __future__ import annotations

import json
import os
import sys
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "backend"))

BACKEND = Path(__file__).parent.parent / "apps" / "backend"


# ── Fixtures ──────────────────────────────────────────────────────────────────

from config_integrity import (
    GOVERNANCE_FILES_RELATIVE,
    INTEGRITY_MANIFEST_FILENAME,
    IntegrityStatus,
    IntegrityViolationError,
    generate_integrity_manifest,
    verify_integrity,
    enforce_integrity,
)
from kill_switch import is_external_llm_enabled, is_action_allowed, get_operation_mode, OperationMode


@pytest.fixture
def clean_env(monkeypatch):
    """Stellt sicher dass Env-Variablen sauber sind."""
    monkeypatch.delenv("AILIZA_OPERATION_MODE", raising=False)
    monkeypatch.delenv("AILIZA_EXTERNAL_LLM_ENABLED", raising=False)
    yield


@pytest.fixture
def governance_dir(tmp_path):
    """Kopiert echte Governance-Dateien in tmp-Verzeichnis."""
    (tmp_path / "governance").mkdir()
    for rel in GOVERNANCE_FILES_RELATIVE:
        src = BACKEND / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return tmp_path


@pytest.fixture
def valid_manifest_path(governance_dir):
    m = governance_dir / INTEGRITY_MANIFEST_FILENAME
    generate_integrity_manifest(governance_dir, m)
    return m


# ── TestLifespanIntegrity ─────────────────────────────────────────────────────

class TestLifespanIntegrity:
    """verify_integrity() korrekt mit echten Dateien aus dem Projekt."""

    def test_real_files_pass_integrity(self, tmp_path):
        m = tmp_path / INTEGRITY_MANIFEST_FILENAME
        generate_integrity_manifest(BACKEND, m)
        result = verify_integrity(BACKEND, m)
        assert result.all_ok is True
        assert result.overall_status == IntegrityStatus.OK.value

    def test_real_files_recommend_normal_mode(self, tmp_path):
        m = tmp_path / INTEGRITY_MANIFEST_FILENAME
        generate_integrity_manifest(BACKEND, m)
        result = verify_integrity(BACKEND, m)
        assert result.recommended_mode == "normal"

    def test_real_manifest_present_in_repo(self):
        m = BACKEND / INTEGRITY_MANIFEST_FILENAME
        assert m.exists(), "governance_integrity.json fehlt im Repository"

    def test_real_manifest_verifies_current_files(self):
        m = BACKEND / INTEGRITY_MANIFEST_FILENAME
        result = verify_integrity(BACKEND, m)
        assert result.all_ok is True, (
            f"Committed manifest stimmt nicht mit aktuellen Dateien überein! "
            f"Status: {result.overall_status}. "
            f"Bitte 'generate_integrity_manifest()' erneut ausführen und einchecken."
        )


# ── TestStartupBlockedOnMissingFile ──────────────────────────────────────────

class TestStartupBlockedOnMissingFile:
    """Fehlende Governance-Datei → kill_switch_active, kein normaler Start."""

    def test_missing_approval_py_blocks_integrity(self, governance_dir, valid_manifest_path):
        (governance_dir / "approval.py").unlink()
        result = verify_integrity(governance_dir, valid_manifest_path)
        assert result.all_ok is False
        assert result.recommended_mode == "kill_switch_active"

    def test_missing_kill_switch_blocks_integrity(self, governance_dir, valid_manifest_path):
        (governance_dir / "kill_switch.py").unlink()
        result = verify_integrity(governance_dir, valid_manifest_path)
        assert result.all_ok is False

    def test_missing_sandbox_blocks_integrity(self, governance_dir, valid_manifest_path):
        (governance_dir / "sandbox.py").unlink()
        result = verify_integrity(governance_dir, valid_manifest_path)
        assert result.all_ok is False

    def test_missing_capability_manifest_blocks_integrity(self, governance_dir, valid_manifest_path):
        (governance_dir / "capability_manifest.py").unlink()
        result = verify_integrity(governance_dir, valid_manifest_path)
        assert result.all_ok is False

    def test_missing_data_governance_blocks_integrity(self, governance_dir, valid_manifest_path):
        (governance_dir / "governance" / "data_governance.py").unlink()
        result = verify_integrity(governance_dir, valid_manifest_path)
        assert result.all_ok is False

    def test_missing_file_enforce_raises(self, governance_dir, valid_manifest_path):
        (governance_dir / "policy.py").unlink()
        with pytest.raises(IntegrityViolationError) as exc_info:
            enforce_integrity(governance_dir, valid_manifest_path)
        msg = str(exc_info.value)
        assert "blockiert" in msg.lower() or "blocked" in msg.lower() or "verletzt" in msg.lower()


# ── TestStartupBlockedOnHashMismatch ─────────────────────────────────────────

class TestStartupBlockedOnHashMismatch:
    """Geänderte Governance-Datei → kill_switch_active, kein normaler Start."""

    def test_modified_approval_py_blocks_start(self, governance_dir, valid_manifest_path):
        (governance_dir / "approval.py").write_text(
            "# TAMPERED\nAPPROVAL_ROLES = {}\nAPPROVAL_TIMEOUT_SECONDS = {}\n",
            encoding="utf-8",
        )
        result = verify_integrity(governance_dir, valid_manifest_path)
        assert result.all_ok is False
        assert result.recommended_mode == "kill_switch_active"

    def test_modified_kill_switch_blocks_start(self, governance_dir, valid_manifest_path):
        original = (governance_dir / "kill_switch.py").read_text()
        (governance_dir / "kill_switch.py").write_text(
            original + "\n# unauthorized change\n", encoding="utf-8"
        )
        result = verify_integrity(governance_dir, valid_manifest_path)
        assert result.all_ok is False

    def test_modified_sandbox_blocks_start(self, governance_dir, valid_manifest_path):
        (governance_dir / "sandbox.py").write_text(
            "# Sandbox bypassed\n_ALWAYS_BLOCKED = frozenset()\n",
            encoding="utf-8",
        )
        result = verify_integrity(governance_dir, valid_manifest_path)
        assert result.all_ok is False

    def test_modified_redaction_blocks_start(self, governance_dir, valid_manifest_path):
        (governance_dir / "governance" / "redaction.py").write_text(
            "# Redaction disabled\ndef redact(text, cls): return text\n",
            encoding="utf-8",
        )
        result = verify_integrity(governance_dir, valid_manifest_path)
        assert result.all_ok is False

    def test_mismatch_status_is_hash_mismatch(self, governance_dir, valid_manifest_path):
        (governance_dir / "approval.py").write_text("# changed\n", encoding="utf-8")
        result = verify_integrity(governance_dir, valid_manifest_path)
        mismatch = [r for r in result.file_results if r.status == IntegrityStatus.HASH_MISMATCH.value]
        assert len(mismatch) >= 1

    def test_mismatch_enforce_raises(self, governance_dir, valid_manifest_path):
        (governance_dir / "capability_manifest.py").write_text(
            "# No-Fallback-No-Go removed\n", encoding="utf-8"
        )
        with pytest.raises(IntegrityViolationError):
            enforce_integrity(governance_dir, valid_manifest_path)


# ── TestStartupBlockedOnManifestIssues ───────────────────────────────────────

class TestStartupBlockedOnManifestIssues:
    """Fehlendes oder korruptes Manifest → kein normaler Start."""

    def test_missing_manifest_blocks_start(self, governance_dir):
        result = verify_integrity(governance_dir, governance_dir / "nope.json")
        assert result.all_ok is False
        assert result.recommended_mode == "kill_switch_active"

    def test_empty_manifest_blocks_start(self, governance_dir):
        m = governance_dir / INTEGRITY_MANIFEST_FILENAME
        m.write_text(json.dumps({"manifest_version": "1.0", "governance_files": {}}))
        result = verify_integrity(governance_dir, m)
        assert result.all_ok is False
        assert result.overall_status == IntegrityStatus.EMPTY_MANIFEST.value

    def test_corrupt_manifest_blocks_start(self, governance_dir):
        m = governance_dir / INTEGRITY_MANIFEST_FILENAME
        m.write_text("not json at all {{{{")
        result = verify_integrity(governance_dir, m)
        assert result.all_ok is False
        assert result.overall_status == IntegrityStatus.INTEGRITY_ERROR.value

    def test_missing_manifest_enforce_raises(self, governance_dir):
        with pytest.raises(IntegrityViolationError):
            enforce_integrity(governance_dir, governance_dir / "missing.json")

    def test_corrupt_manifest_enforce_raises(self, governance_dir):
        m = governance_dir / INTEGRITY_MANIFEST_FILENAME
        m.write_text("{broken")
        with pytest.raises(IntegrityViolationError):
            enforce_integrity(governance_dir, m)


# ── TestKillSwitchAfterIntegrityFailure ───────────────────────────────────────

class TestKillSwitchAfterIntegrityFailure:
    """
    Simuliert was lifespan() tut: bei Integrity-Fehler → Env auf kill_switch_active setzen.
    Dann prüfen dass Kill-Switch und alle Aktionen korrekt geblockt sind.
    """

    def _simulate_integrity_failure(self, monkeypatch):
        """Setzt Env wie lifespan() es bei Integrity-Fehler tut."""
        monkeypatch.setenv("AILIZA_OPERATION_MODE", "kill_switch_active")
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "false")

    def test_kill_switch_active_after_integrity_failure(self, monkeypatch):
        self._simulate_integrity_failure(monkeypatch)
        assert get_operation_mode() == OperationMode.KILL_SWITCH_ACTIVE

    def test_external_llm_disabled_after_integrity_failure(self, monkeypatch):
        self._simulate_integrity_failure(monkeypatch)
        assert is_external_llm_enabled() is False

    def test_write_blocked_after_integrity_failure(self, monkeypatch):
        self._simulate_integrity_failure(monkeypatch)
        assert is_action_allowed("write") is False

    def test_send_message_blocked_after_integrity_failure(self, monkeypatch):
        self._simulate_integrity_failure(monkeypatch)
        assert is_action_allowed("send_message") is False

    def test_memory_store_blocked_after_integrity_failure(self, monkeypatch):
        self._simulate_integrity_failure(monkeypatch)
        assert is_action_allowed("memory_store") is False

    def test_fetch_blocked_after_integrity_failure(self, monkeypatch):
        self._simulate_integrity_failure(monkeypatch)
        assert is_action_allowed("fetch") is False

    def test_mass_notify_blocked_after_integrity_failure(self, monkeypatch):
        self._simulate_integrity_failure(monkeypatch)
        assert is_action_allowed("mass_notify") is False


# ── TestSandboxSmokeTest ──────────────────────────────────────────────────────

class TestSandboxSmokeTest:
    """
    Smoke-Test mit synthetischen Daten und Workspace-Aktionen.
    Keine echten Kundendaten, keine Biometrie, keine Massennachrichten.
    """

    from sandbox import assess_local_action, ActionClass

    def test_read_file_in_workspace_allowed(self, tmp_path, monkeypatch):
        from sandbox import assess_local_action, ActionClass
        ws = tmp_path / "ailiza_workspace"
        ws.mkdir()
        monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(ws))
        f = ws / "synthetic_report.txt"
        f.write_text("Synthetische Testdaten: Kunde A, Auftrag 42")
        result = assess_local_action(ActionClass.READ_FILE, str(f))
        assert result.allowed is True

    def test_write_report_in_workspace_allowed(self, tmp_path, monkeypatch):
        from sandbox import assess_local_action, ActionClass
        ws = tmp_path / "ailiza_workspace"
        ws.mkdir()
        monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(ws))
        result = assess_local_action(ActionClass.WRITE_FILE, str(ws / "compliance_report.pdf"))
        assert result.allowed is True

    def test_delete_outside_workspace_blocked(self, tmp_path, monkeypatch):
        from sandbox import assess_local_action, ActionClass
        ws = tmp_path / "ailiza_workspace"
        ws.mkdir()
        monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(ws))
        external = tmp_path / "important_data" / "contracts.pdf"
        external.parent.mkdir()
        external.write_text("data")
        result = assess_local_action(ActionClass.DELETE_FILE, str(external))
        assert result.allowed is False

    def test_shell_command_always_blocked(self, tmp_path, monkeypatch):
        from sandbox import assess_local_action, ActionClass
        ws = tmp_path / "ailiza_workspace"
        ws.mkdir()
        monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(ws))
        result = assess_local_action(ActionClass.EXECUTE_SHELL, "rm -rf /tmp")
        assert result.allowed is False

    def test_biometric_access_always_blocked(self, tmp_path, monkeypatch):
        from sandbox import assess_local_action, ActionClass
        ws = tmp_path / "ailiza_workspace"
        ws.mkdir()
        monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(ws))
        result = assess_local_action(ActionClass.ACCESS_PHOTOS, "/dev/camera")
        assert result.allowed is False

    def test_mass_notify_not_allowed_in_capability_manifest(self):
        from capability_manifest import check_capability
        from kill_switch import OperationMode
        # SAFETY_CRITICAL: send_push_all_visitors blocked ohne AVV
        result = check_capability(
            "send_push_all_visitors",
            current_mode=OperationMode.NORMAL.value,
            provider_id=None,
        )
        assert result.allowed is False


# ── TestAuditCleanlinessRuntime ───────────────────────────────────────────────

class TestAuditCleanlinessRuntime:
    """Audit-Einträge bei Integrity-Check enthalten keine Governance-Inhalte."""

    def test_audit_dict_no_file_contents(self, governance_dir, valid_manifest_path):
        result = verify_integrity(governance_dir, valid_manifest_path)
        audit = result.to_audit_dict()
        audit_str = json.dumps(audit)
        assert "APPROVAL_ROLES" not in audit_str
        assert "_ALWAYS_BLOCKED" not in audit_str
        assert "_BLOCK_CLASSES" not in audit_str
        assert "sha256" not in audit_str.lower()

    def test_file_result_audit_no_hash_values(self, governance_dir, valid_manifest_path):
        result = verify_integrity(governance_dir, valid_manifest_path)
        for fr in result.file_results:
            audit = fr.to_audit_dict()
            assert "hash" not in str(audit).lower() or audit.get("expected_hash_present") is not None
            # expected_hash_present ist bool, kein Wert — das ist erlaubt
            assert len([k for k in audit if "hash_value" in k]) == 0

    def test_audit_dict_required_keys_only(self, governance_dir, valid_manifest_path):
        result = verify_integrity(governance_dir, valid_manifest_path)
        audit = result.to_audit_dict()
        allowed_keys = {
            "overall_status", "all_ok", "recommended_mode",
            "unknown_files_count", "file_count", "blocked_count", "checked_at",
        }
        assert set(audit.keys()).issubset(allowed_keys), (
            f"Unerlaubte Keys im Audit: {set(audit.keys()) - allowed_keys}"
        )

    def test_mismatch_audit_no_file_content(self, governance_dir, valid_manifest_path):
        (governance_dir / "approval.py").write_text(
            "SECRET='leaked-credential'\nAPPROVAL_ROLES={}\n", encoding="utf-8"
        )
        result = verify_integrity(governance_dir, valid_manifest_path)
        for fr in result.file_results:
            audit_str = json.dumps(fr.to_audit_dict())
            assert "leaked-credential" not in audit_str
            assert "SECRET" not in audit_str
