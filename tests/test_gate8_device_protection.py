"""
Gate 8 — Local Device Protection Tests
=======================================
Sicherstellt dass AILIZA standardmäßig nicht auf Gerätedaten, Programme
oder Systemeinstellungen außerhalb des Workspace zugreifen kann.

Akzeptanztests aus dem Gate-8-Spezifikationsdokument:
  - agent_cannot_delete_files_outside_workspace
  - agent_cannot_modify_installed_programs
  - agent_cannot_change_system_settings
  - agent_cannot_access_phone_contacts_without_scope
  - agent_cannot_send_messages_without_preview_and_approval
  - shell_command_requires_policy_gate
  - destructive_local_action_is_blocked_by_default
  - workspace_write_allowed_but_external_write_requires_approval
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "backend"))

from sandbox import (
    ActionClass,
    SandboxResult,
    assess_local_action,
    enforce_sandbox,
    sandbox_status,
    _get_workspace,
    _ALWAYS_BLOCKED,
    _REQUIRE_OWNER_APPROVAL,
    _REQUIRE_APPROVAL,
)
from errors import AILIZAError


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def workspace_dir(tmp_path, monkeypatch):
    ws = tmp_path / "ailiza_workspace"
    ws.mkdir()
    monkeypatch.setenv("AILIZA_WORKSPACE_PATH", str(ws))
    return ws


@pytest.fixture
def external_path(tmp_path):
    ext = tmp_path / "other_folder" / "file.txt"
    ext.parent.mkdir(parents=True)
    ext.write_text("external")
    return str(ext)


# ── TestAlwaysBlockedActions ───────────────────────────────────────────────────

class TestAlwaysBlockedActions:
    """Aktionen die IMMER gesperrt sind — keine Freigabe möglich."""

    def test_agent_cannot_modify_installed_programs(self, workspace_dir):
        result = assess_local_action(ActionClass.MODIFY_APP, str(workspace_dir / "app"))
        assert result.allowed is False
        assert result.requires_approval is False
        assert result.requires_owner_approval is False
        assert "permanent" in result.reason.lower() or "gesperrt" in result.reason.lower()

    def test_install_app_always_blocked(self):
        result = assess_local_action(ActionClass.INSTALL_APP, "/usr/local/bin/tool")
        assert result.allowed is False

    def test_uninstall_app_always_blocked(self):
        result = assess_local_action(ActionClass.UNINSTALL_APP)
        assert result.allowed is False

    def test_modify_autostart_always_blocked(self):
        result = assess_local_action(ActionClass.MODIFY_AUTOSTART)
        assert result.allowed is False

    def test_modify_registry_always_blocked(self):
        result = assess_local_action(ActionClass.MODIFY_REGISTRY)
        assert result.allowed is False

    def test_modify_security_software_always_blocked(self):
        result = assess_local_action(ActionClass.MODIFY_SECURITY_SOFTWARE)
        assert result.allowed is False

    def test_remote_control_app_always_blocked(self):
        result = assess_local_action(ActionClass.REMOTE_CONTROL_APP)
        assert result.allowed is False

    def test_always_blocked_set_completeness(self):
        """ALWAYS_BLOCKED muss die sicherheitskritischen Klassen enthalten."""
        critical = {
            ActionClass.INSTALL_APP, ActionClass.UNINSTALL_APP, ActionClass.MODIFY_APP,
            ActionClass.MODIFY_REGISTRY, ActionClass.MODIFY_SECURITY_SOFTWARE,
            ActionClass.REMOTE_CONTROL_APP,
        }
        assert critical.issubset(_ALWAYS_BLOCKED)


# ── TestDestructiveActionsRequireOwnerApproval ─────────────────────────────────

class TestDestructiveActionsRequireOwnerApproval:
    """Destruktive Aktionen benötigen Owner-Freigabe."""

    def test_agent_cannot_delete_files_outside_workspace(self, workspace_dir, external_path):
        result = assess_local_action(ActionClass.DELETE_FILE, external_path)
        assert result.allowed is False
        assert result.requires_owner_approval is True

    def test_destructive_local_action_is_blocked_by_default(self, workspace_dir):
        ws_file = str(workspace_dir / "report.txt")
        result = assess_local_action(ActionClass.DELETE_FILE, ws_file)
        assert result.allowed is False
        assert result.requires_owner_approval is True

    def test_delete_in_workspace_allowed_in_maintenance_mode(self, workspace_dir, monkeypatch):
        monkeypatch.setenv("AILIZA_MAINTENANCE_MODE", "true")
        ws_file = str(workspace_dir / "old_log.txt")
        result = assess_local_action(ActionClass.DELETE_FILE, ws_file)
        assert result.allowed is True
        assert result.in_workspace is True

    def test_delete_outside_workspace_blocked_even_in_maintenance_mode(self, workspace_dir, external_path, monkeypatch):
        monkeypatch.setenv("AILIZA_MAINTENANCE_MODE", "true")
        result = assess_local_action(ActionClass.DELETE_FILE, external_path)
        assert result.allowed is False

    def test_agent_cannot_change_system_settings(self):
        result = assess_local_action(ActionClass.CHANGE_SETTINGS, "/etc/hosts")
        assert result.allowed is False
        assert result.requires_owner_approval is True

    def test_shell_command_requires_policy_gate(self):
        result = assess_local_action(ActionClass.EXECUTE_SHELL, "rm -rf /tmp/data")
        assert result.allowed is False
        assert result.requires_owner_approval is True

    def test_move_file_requires_owner_approval(self, workspace_dir, external_path):
        result = assess_local_action(ActionClass.MOVE_FILE, external_path)
        assert result.allowed is False
        assert result.requires_owner_approval is True


# ── TestApprovalRequiredActions ─────────────────────────────────────────────

class TestApprovalRequiredActions:
    """Aktionen die Nutzer-Freigabe mit Vorschau benötigen."""

    def test_agent_cannot_access_phone_contacts_without_scope(self):
        result = assess_local_action(ActionClass.ACCESS_CONTACTS)
        assert result.allowed is False
        assert result.requires_approval is True

    def test_agent_cannot_send_messages_without_preview_and_approval(self):
        result = assess_local_action(ActionClass.SEND_MESSAGE)
        assert result.allowed is False
        assert result.requires_approval is True

    def test_access_photos_requires_approval(self):
        result = assess_local_action(ActionClass.ACCESS_PHOTOS)
        assert result.allowed is False
        assert result.requires_approval is True

    def test_modify_calendar_requires_approval(self):
        result = assess_local_action(ActionClass.MODIFY_CALENDAR)
        assert result.allowed is False
        assert result.requires_approval is True

    def test_read_external_app_requires_approval(self):
        result = assess_local_action(ActionClass.READ_EXTERNAL_APP)
        assert result.allowed is False
        assert result.requires_approval is True

    def test_read_sensitive_local_data_requires_owner_approval(self):
        result = assess_local_action(ActionClass.READ_SENSITIVE_LOCAL_DATA)
        assert result.allowed is False
        assert result.requires_owner_approval is True


# ── TestWorkspaceBoundary ─────────────────────────────────────────────────────

class TestWorkspaceBoundary:
    """Workspace-Grenze: innerhalb erlaubt, außerhalb geblockt."""

    def test_workspace_write_allowed(self, workspace_dir):
        ws_file = str(workspace_dir / "output.txt")
        result = assess_local_action(ActionClass.WRITE_FILE, ws_file)
        assert result.allowed is True
        assert result.in_workspace is True

    def test_workspace_read_allowed(self, workspace_dir):
        ws_file = str(workspace_dir / "input.csv")
        result = assess_local_action(ActionClass.READ_FILE, ws_file)
        assert result.allowed is True
        assert result.in_workspace is True

    def test_workspace_write_allowed_but_external_write_requires_approval(self, workspace_dir, external_path):
        ws_result = assess_local_action(ActionClass.WRITE_FILE, str(workspace_dir / "out.txt"))
        ext_result = assess_local_action(ActionClass.WRITE_FILE, external_path)
        assert ws_result.allowed is True
        assert ext_result.allowed is False
        assert ext_result.requires_owner_approval is True

    def test_read_outside_workspace_requires_approval(self, external_path):
        result = assess_local_action(ActionClass.READ_FILE, external_path)
        assert result.allowed is False
        assert result.requires_approval is True

    def test_subdirectory_in_workspace_allowed(self, workspace_dir):
        subdir = workspace_dir / "reports" / "2024"
        subdir.mkdir(parents=True)
        result = assess_local_action(ActionClass.WRITE_FILE, str(subdir / "report.pdf"))
        assert result.allowed is True
        assert result.in_workspace is True

    def test_path_traversal_outside_workspace_blocked(self, workspace_dir):
        traversal = str(workspace_dir / ".." / "etc" / "passwd")
        result = assess_local_action(ActionClass.READ_FILE, traversal)
        assert result.allowed is False


# ── TestEnforceSandbox ────────────────────────────────────────────────────────

class TestEnforceSandbox:
    """enforce_sandbox() wirft AILIZAError bei geblockter Aktion."""

    def test_enforce_raises_on_blocked_action(self):
        with pytest.raises(AILIZAError) as exc_info:
            enforce_sandbox(ActionClass.INSTALL_APP)
        assert exc_info.value.code == "sandbox_blocked"
        assert "Device Protection" in exc_info.value.message_de or "permanent" in exc_info.value.message_de

    def test_enforce_does_not_raise_for_workspace_write(self, workspace_dir):
        ws_file = str(workspace_dir / "safe.txt")
        enforce_sandbox(ActionClass.WRITE_FILE, ws_file)  # kein Raise

    def test_enforce_raises_for_external_write(self, external_path):
        with pytest.raises(AILIZAError) as exc_info:
            enforce_sandbox(ActionClass.WRITE_FILE, external_path)
        assert exc_info.value.code == "sandbox_blocked"

    def test_enforce_raises_for_shell_command(self):
        with pytest.raises(AILIZAError):
            enforce_sandbox(ActionClass.EXECUTE_SHELL, "sudo rm -rf /")

    def test_unknown_action_class_is_fail_closed(self):
        result = assess_local_action("unknown_action_xyz")
        assert result.allowed is False
        assert "fail-closed" in result.reason.lower() or "unbekannt" in result.reason.lower()


# ── TestSandboxStatus ────────────────────────────────────────────────────────

class TestSandboxStatus:
    """sandbox_status() gibt vollständige Konfiguration zurück."""

    def test_sandbox_status_keys(self, workspace_dir):
        status = sandbox_status()
        assert "workspace_path" in status
        assert "maintenance_mode" in status
        assert "always_blocked" in status
        assert "require_owner_approval" in status
        assert "require_approval" in status
        assert "workspace_autonomous" in status

    def test_sandbox_status_always_blocked_non_empty(self):
        status = sandbox_status()
        assert len(status["always_blocked"]) >= 7

    def test_sandbox_status_maintenance_mode_default_false(self, monkeypatch):
        monkeypatch.delenv("AILIZA_MAINTENANCE_MODE", raising=False)
        status = sandbox_status()
        assert status["maintenance_mode"] is False
