"""
AILIZA Gate 8 — Local Device Protection (Sandbox-Gate)
=======================================================
AILIZA handelt autonom *innerhalb* definierter, geprüfter Arbeitsbereiche.
Änderungen an externen Programmen, Betriebssystem, Handy-Daten oder fremden
Dateien erfolgen nie ohne explizite, nachvollziehbare Freigabe.

Standardverhalten:
  - Lesen:    nur freigegebene Dateien (AILIZA_WORKSPACE_PATH)
  - Schreiben: nur im Workspace oder explizit gewähltem Zielordner
  - Löschen:  verboten (außer Wartungsmodus oder owner-Freigabe)
  - System:   keine Shell, keine Einstellungen, keine Programme

Env-Variablen:
  AILIZA_WORKSPACE_PATH   — Pfad des freigegebenen Arbeitsordners (kein Default — muss explizit gesetzt sein)
  AILIZA_MAINTENANCE_MODE — "1"/"true" erlaubt destruktive Aktionen im Workspace für Admins

Fail-closed bei:
  - AILIZA_WORKSPACE_PATH nicht gesetzt, leer oder Verzeichnis existiert nicht
  - Symlinks die aus dem Workspace nach außen zeigen
  - Unbekannte ActionClass
  - Ungültige/nicht auflösbare Pfade
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from .errors import AILIZAError
except ImportError:
    from errors import AILIZAError


class ActionClass(str, Enum):
    # Datei-Operationen
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    DELETE_FILE = "delete_file"
    MOVE_FILE = "move_file"

    # System / Programme
    INSTALL_APP = "install_app"
    UNINSTALL_APP = "uninstall_app"
    MODIFY_APP = "modify_app"
    EXECUTE_SHELL = "execute_shell"
    CHANGE_SETTINGS = "change_settings"
    MODIFY_AUTOSTART = "modify_autostart"
    MODIFY_REGISTRY = "modify_registry"
    CHANGE_PERMISSIONS = "change_permissions"
    MODIFY_SECURITY_SOFTWARE = "modify_security_software"

    # Mobile / Persönliche Daten
    ACCESS_CONTACTS = "access_contacts"
    ACCESS_PHOTOS = "access_photos"
    ACCESS_CALENDAR = "access_calendar"
    MODIFY_CALENDAR = "modify_calendar"
    SEND_MESSAGE = "send_message"
    READ_SENSITIVE_LOCAL_DATA = "read_sensitive_local_data"

    # Externe Apps
    REMOTE_CONTROL_APP = "remote_control_app"
    READ_EXTERNAL_APP = "read_external_app"


# Aktionen die IMMER geblockt werden — auch mit Approval nicht möglich
_ALWAYS_BLOCKED: frozenset[ActionClass] = frozenset({
    ActionClass.INSTALL_APP,
    ActionClass.UNINSTALL_APP,
    ActionClass.MODIFY_APP,
    ActionClass.MODIFY_AUTOSTART,
    ActionClass.MODIFY_REGISTRY,
    ActionClass.CHANGE_PERMISSIONS,
    ActionClass.MODIFY_SECURITY_SOFTWARE,
    ActionClass.REMOTE_CONTROL_APP,
})

# Aktionen die Owner-Approval benötigen (destruktiv oder systemkritisch)
_REQUIRE_OWNER_APPROVAL: frozenset[ActionClass] = frozenset({
    ActionClass.DELETE_FILE,
    ActionClass.MOVE_FILE,
    ActionClass.EXECUTE_SHELL,
    ActionClass.CHANGE_SETTINGS,
    ActionClass.READ_SENSITIVE_LOCAL_DATA,
})

# Aktionen die mindestens eine normale Approval benötigen
_REQUIRE_APPROVAL: frozenset[ActionClass] = frozenset({
    ActionClass.WRITE_FILE,
    ActionClass.ACCESS_CONTACTS,
    ActionClass.ACCESS_PHOTOS,
    ActionClass.ACCESS_CALENDAR,
    ActionClass.MODIFY_CALENDAR,
    ActionClass.SEND_MESSAGE,
    ActionClass.READ_EXTERNAL_APP,
})

# Im Workspace autonom erlaubte Aktionen
_WORKSPACE_AUTONOMOUS: frozenset[ActionClass] = frozenset({
    ActionClass.READ_FILE,
    ActionClass.WRITE_FILE,
})


# Sensitive Pfade außerhalb des Workspace die immer Owner-Approval benötigen,
# auch wenn sie zufällig im Workspace-Tree liegen könnten.
_SENSITIVE_PATH_FRAGMENTS: tuple[str, ...] = (
    ".ssh", ".gnupg", ".aws", ".config/google-chrome", ".config/chromium",
    ".mozilla", "Contacts", "Photos", "Downloads", "Documents",
    "Library/Application Support", "AppData", "NTUSER.DAT",
    "id_rsa", "id_ed25519", "id_ecdsa", ".pem", ".p12", ".pfx",
    "known_hosts", "authorized_keys",
)

# Shell-Befehle / Programme die bei execute_shell immer als hochriskant gelten
_HIGH_RISK_SHELL_TOKENS: tuple[str, ...] = (
    "rm ", "del ", "rmdir", "format ", "mkfs", "dd ", "shred",
    "curl ", "wget ", "pip install", "npm install -g", "gem install",
    "sudo ", "su ", "chmod ", "chown ", "passwd",
    "reg ", "regedit", "schtasks", "powershell", "cmd.exe",
    "crontab", "at ", "systemctl", "service ",
)


class WorkspaceError(Exception):
    """Workspace ist nicht korrekt konfiguriert — fail-closed."""


def _get_workspace() -> Path:
    """
    Gibt den konfigurierten Workspace zurück.
    Wirft WorkspaceError wenn AILIZA_WORKSPACE_PATH nicht gesetzt oder Verzeichnis fehlt.
    Kein Default — fail-closed bei fehlender Konfiguration.
    """
    raw = os.getenv("AILIZA_WORKSPACE_PATH", "").strip()
    if not raw:
        raise WorkspaceError(
            "AILIZA_WORKSPACE_PATH ist nicht gesetzt. "
            "Der Workspace muss explizit konfiguriert sein."
        )
    p = Path(raw).resolve()
    if not p.exists():
        raise WorkspaceError(
            f"AILIZA_WORKSPACE_PATH '{raw}' existiert nicht. "
            "Verzeichnis anlegen oder Pfad korrigieren."
        )
    if not p.is_dir():
        raise WorkspaceError(
            f"AILIZA_WORKSPACE_PATH '{raw}' ist kein Verzeichnis."
        )
    return p


def _is_maintenance_mode() -> bool:
    raw = os.getenv("AILIZA_MAINTENANCE_MODE", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_strict(target_path: str) -> Path | None:
    """
    Löst Symlinks vollständig auf (folgt der Symlink-Kette bis zum echten Ziel).
    Gibt None zurück wenn der Pfad nicht existiert und auch keine Basis-Auflösung möglich ist.
    Nutzt strict=False damit nicht-existente Pfade trotzdem normalisiert werden,
    aber folgt dabei keinen Symlinks nach außen.
    """
    try:
        p = Path(target_path)
        # resolve() folgt Symlinks — das ist beabsichtigt, um Symlink-Traversal zu erkennen
        return p.resolve()
    except Exception:
        return None


def _is_sensitive_path(resolved: Path) -> bool:
    path_str = str(resolved)
    return any(frag in path_str for frag in _SENSITIVE_PATH_FRAGMENTS)


def _is_in_workspace(target_path: str | None) -> bool:
    """
    True nur wenn der vollständig aufgelöste Pfad (inkl. Symlink-Ziel) innerhalb
    des Workspace liegt. Symlinks nach außen werden damit erkannt und geblockt.
    """
    if not target_path:
        return False
    try:
        workspace = _get_workspace()
    except WorkspaceError:
        return False
    resolved = _resolve_strict(target_path)
    if resolved is None:
        return False
    # Symlink-Schutz: resolved zeigt auf echtes Ziel, workspace ist ebenfalls resolved
    return resolved == workspace or workspace in resolved.parents


@dataclass(frozen=True)
class SandboxResult:
    allowed: bool
    action_class: str
    target: str
    reason: str
    requires_approval: bool = False
    requires_owner_approval: bool = False
    in_workspace: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action_class": self.action_class,
            "target": self.target,
            "reason": self.reason,
            "requires_approval": self.requires_approval,
            "requires_owner_approval": self.requires_owner_approval,
            "in_workspace": self.in_workspace,
        }


def assess_local_action(
    action_class: ActionClass | str,
    target_path: str | None = None,
) -> SandboxResult:
    """
    Prüft ob eine lokale Geräte-Aktion erlaubt ist.

    Rückgabe: SandboxResult mit allowed=False wenn geblockt,
              requires_owner_approval=True wenn Owner-Freigabe nötig,
              requires_approval=True wenn Nutzer-Freigabe nötig.
    """
    try:
        ac = ActionClass(action_class)
    except ValueError:
        return SandboxResult(
            allowed=False,
            action_class=str(action_class),
            target=target_path or "<unknown>",
            reason=f"Unbekannte Aktionsklasse '{action_class}' — fail-closed geblockt.",
        )

    # Defaults — werden für Nicht-Datei-Aktionen nicht überschrieben
    in_ws = False
    resolved = None
    target_label = target_path or "<unknown>"

    # Immer geblockt — keine Freigabe möglich (kein Workspace nötig)
    if ac in _ALWAYS_BLOCKED:
        return SandboxResult(
            allowed=False,
            action_class=ac.value,
            target=target_label,
            reason=f"Aktion '{ac.value}' ist permanent gesperrt (Device Protection Gate).",
            in_workspace=in_ws,
        )

    # Workspace-Konfiguration — nur für dateisystem-basierte Aktionen prüfen
    _FILE_ACTIONS = {
        ActionClass.READ_FILE, ActionClass.WRITE_FILE,
        ActionClass.DELETE_FILE, ActionClass.MOVE_FILE,
    }
    if ac in _FILE_ACTIONS:
        try:
            _get_workspace()
        except WorkspaceError as exc:
            return SandboxResult(
                allowed=False,
                action_class=ac.value,
                target=target_path or "<unknown>",
                reason=f"Workspace nicht konfiguriert — fail-closed: {exc}",
            )
        in_ws = _is_in_workspace(target_path)
        resolved = _resolve_strict(target_path) if target_path else None
        target_label = "<workspace>" if in_ws else (target_path or "<unknown>")

    # Sensitive Pfade immer Owner-Approval — unabhängig von Workspace-Status
    if resolved and _is_sensitive_path(resolved) and ac in _FILE_ACTIONS:
        return SandboxResult(
            allowed=False,
            action_class=ac.value,
            target=target_label,
            reason="Pfad enthält sensitive Daten (SSH-Keys, Browser-Profile, Credentials o.ä.) — Owner-Freigabe erforderlich.",
            requires_owner_approval=True,
            in_workspace=in_ws,
        )

    # Destruktive Aktionen: nur im Wartungsmodus und nur im Workspace
    if ac in _REQUIRE_OWNER_APPROVAL:
        # Shell-Befehl: hochriskante Token sofort identifizieren
        if ac == ActionClass.EXECUTE_SHELL and target_path:
            cmd_lower = target_path.lower()
            found = next((t for t in _HIGH_RISK_SHELL_TOKENS if t in cmd_lower), None)
            if found:
                return SandboxResult(
                    allowed=False,
                    action_class=ac.value,
                    target="<shell-command>",
                    reason=f"Shell-Befehl enthält hochriskantes Token '{found.strip()}' — permanent blockiert.",
                    in_workspace=in_ws,
                )
        if ac == ActionClass.DELETE_FILE and _is_maintenance_mode() and in_ws:
            return SandboxResult(
                allowed=True,
                action_class=ac.value,
                target=target_label,
                reason="Wartungsmodus aktiv — Löschen im Workspace erlaubt.",
                in_workspace=True,
            )
        return SandboxResult(
            allowed=False,
            action_class=ac.value,
            target=target_label,
            reason=f"Aktion '{ac.value}' erfordert explizite Owner-Freigabe.",
            requires_owner_approval=True,
            in_workspace=in_ws,
        )

    # Approval-pflichtige Aktionen
    if ac in _REQUIRE_APPROVAL:
        # Write im Workspace autonom erlaubt
        if ac == ActionClass.WRITE_FILE and in_ws:
            return SandboxResult(
                allowed=True,
                action_class=ac.value,
                target=target_label,
                reason="Schreiben im Workspace ist autonom erlaubt.",
                in_workspace=True,
            )
        # Write außerhalb Workspace → Owner-Approval
        if ac == ActionClass.WRITE_FILE and not in_ws:
            return SandboxResult(
                allowed=False,
                action_class=ac.value,
                target=target_label,
                reason="Schreiben außerhalb des Workspace erfordert Owner-Freigabe.",
                requires_owner_approval=True,
                in_workspace=False,
            )
        return SandboxResult(
            allowed=False,
            action_class=ac.value,
            target=target_label,
            reason=f"Aktion '{ac.value}' erfordert explizite Nutzer-Freigabe mit Vorschau.",
            requires_approval=True,
            in_workspace=in_ws,
        )

    # Lesen: nur im Workspace
    if ac == ActionClass.READ_FILE:
        if in_ws:
            return SandboxResult(
                allowed=True,
                action_class=ac.value,
                target=target_label,
                reason="Lesen im Workspace ist erlaubt.",
                in_workspace=True,
            )
        return SandboxResult(
            allowed=False,
            action_class=ac.value,
            target=target_label,
            reason="Lesen außerhalb des Workspace erfordert explizite Freigabe.",
            requires_approval=True,
            in_workspace=False,
        )

    return SandboxResult(
        allowed=False,
        action_class=ac.value,
        target=target_label,
        reason=f"Aktion '{ac.value}' ist nicht im erlaubten Standardverhalten.",
        in_workspace=in_ws,
    )


def enforce_sandbox(action_class: ActionClass | str, target_path: str | None = None) -> None:
    """Wirft AILIZAError wenn die lokale Aktion nicht erlaubt ist."""
    result = assess_local_action(action_class, target_path)
    if not result.allowed:
        raise AILIZAError(
            message_de=result.reason,
            code="sandbox_blocked",
            safe_alternatives=[
                "Aktion auf den freigegebenen AILIZA-Workspace beschränken",
                "Explizite Nutzerfreigabe einholen",
                "Administrator kontaktieren",
            ],
        )


def sandbox_status() -> dict[str, Any]:
    """Gibt Sandbox-Konfiguration zurück (für Admin-Endpoint)."""
    try:
        ws = str(_get_workspace())
        ws_ok = True
    except WorkspaceError as exc:
        ws = f"<nicht konfiguriert: {exc}>"
        ws_ok = False
    return {
        "workspace_path": ws,
        "workspace_configured": ws_ok,
        "maintenance_mode": _is_maintenance_mode(),
        "always_blocked": sorted(a.value for a in _ALWAYS_BLOCKED),
        "require_owner_approval": sorted(a.value for a in _REQUIRE_OWNER_APPROVAL),
        "require_approval": sorted(a.value for a in _REQUIRE_APPROVAL),
        "workspace_autonomous": sorted(a.value for a in _WORKSPACE_AUTONOMOUS),
    }


# ── SandboxApproval — Freigabe-Reuse-Schutz ──────────────────────────────────

@dataclass
class SandboxApproval:
    """
    Bindet eine Sandbox-Freigabe an genau eine Kombination aus:
    action_class, resolved_path, scope, approver_role und expires_at.

    Eine Freigabe für Datei A gilt nicht für Datei B (kein Approval-Reuse).
    Eine Freigabe für read_file gilt nicht für write_file auf demselben Pfad.
    """
    approval_id: str
    action_class: str
    resolved_path: str       # vollständig aufgelöster Pfad (nach resolve())
    scope: str               # z. B. "single_file", "workspace", "session"
    approver_role: str       # Rolle des Freigebers (z. B. "owner", "admin")
    approved_at: datetime
    expires_at: datetime
    used: bool = False

    @classmethod
    def create(
        cls,
        action_class: ActionClass | str,
        target_path: str,
        scope: str,
        approver_role: str,
        ttl_seconds: int = 300,
    ) -> "SandboxApproval":
        resolved = _resolve_strict(target_path)
        if resolved is None:
            raise ValueError(f"Pfad '{target_path}' konnte nicht aufgelöst werden.")
        now = datetime.now(timezone.utc)
        return cls(
            approval_id=str(uuid.uuid4()),
            action_class=str(action_class),
            resolved_path=str(resolved),
            scope=scope,
            approver_role=approver_role,
            approved_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )

    def is_valid_for(self, action_class: ActionClass | str, target_path: str) -> bool:
        """
        True nur wenn alle Dimensionen übereinstimmen und die Freigabe noch nicht
        abgelaufen oder bereits verwendet wurde.
        """
        if self.used:
            return False
        if datetime.now(timezone.utc) > self.expires_at:
            return False
        if str(action_class) != self.action_class:
            return False
        resolved = _resolve_strict(target_path)
        if resolved is None or str(resolved) != self.resolved_path:
            return False
        return True

    def consume(self) -> None:
        """Markiert die Freigabe als verbraucht (Einmalnutzung)."""
        object.__setattr__(self, "used", True) if hasattr(self, "__dataclass_fields__") else None
        self.used = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "action_class": self.action_class,
            "resolved_path": self.resolved_path,
            "scope": self.scope,
            "approver_role": self.approver_role,
            "approved_at": self.approved_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "used": self.used,
        }
