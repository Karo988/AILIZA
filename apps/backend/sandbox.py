"""
AILIZA Gate 8 — Local Device Protection (Sandbox-Gate)
=======================================================
AILIZA handelt autonom *innerhalb* definierter, geprüfter Arbeitsbereiche.
Änderungen an externen Programmen, Betriebssystem, Handy-Daten oder fremden
Dateien erfolgen nie ohne explizite, nachvollziehbare Freigabe.

Standardverhalten ohne authentisierten Workspace-Broker:
  - Dateioperationen: fail-closed mit ``responsibility_handoff``
  - Löschen/Verschieben: ebenfalls Handoff; keine In-Process-Ausnahme
  - System:   keine Shell, keine Einstellungen, keine Programme

Env-Variablen:
  AILIZA_WORKSPACE_PATH   — nur ein Pfadkandidat; ohne Broker kein Vertrauensnachweis
  AILIZA_MAINTENANCE_MODE — "1"/"true" erlaubt destruktive Aktionen im Workspace für Admins

Fail-closed bei:
  - Authentisierter Workspace-Broker nicht verfuegbar
  - Symlinks die aus dem Workspace nach außen zeigen
  - Unbekannte ActionClass
  - Ungültige/nicht auflösbare Pfade
"""
from __future__ import annotations

import os
import sys
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
    APPEND_FILE = "append_file"
    LIST_DIRECTORY = "list_directory"
    COPY_FILE = "copy_file"
    DELETE_FILE = "delete_file"
    MOVE_FILE = "move_file"
    RENAME_FILE = "rename_file"

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
    ActionClass.APPEND_FILE,
    ActionClass.LIST_DIRECTORY,
})

_FILE_ACTIONS: frozenset[ActionClass] = frozenset({
    ActionClass.READ_FILE,
    ActionClass.WRITE_FILE,
    ActionClass.APPEND_FILE,
    ActionClass.LIST_DIRECTORY,
    ActionClass.COPY_FILE,
    ActionClass.DELETE_FILE,
    ActionClass.MOVE_FILE,
    ActionClass.RENAME_FILE,
})

_WORKSPACE_BROKER_HANDOFF_REASON = (
    "Autonome Workspace-Dateioperation ist deaktiviert: Es ist kein "
    "authentisierter Workspace-Broker verfuegbar. Die Verantwortung wird "
    "an die kontrollierte Broker-Einrichtung durch einen Administrator uebergeben."
)


# Sensitive Pfade außerhalb des Workspace die immer Owner-Approval benötigen,
# auch wenn sie zufällig im Workspace-Tree liegen könnten.
_SENSITIVE_PATH_FRAGMENTS: tuple[str, ...] = (
    ".ssh", ".gnupg", ".aws", ".config/google-chrome", ".config/chromium",
    "AppData/Local/Google/Chrome/User Data",
    "AppData/Local/Microsoft/Edge/User Data",
    "AppData/Roaming/Mozilla/Firefox/Profiles",
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


def _is_unc_path(path: Path) -> bool:
    """Netzwerkpfade sind keine lokal kontrollierte autonome Grenze."""
    return str(path).startswith("\\\\") or str(path.anchor).startswith("\\\\")


def _default_workspace_path(
    *,
    platform_name: str | None = None,
    home: Path | None = None,
) -> Path:
    """Berechnet nur den kanonischen Pfad; die Funktion vertraut ihm nicht."""
    platform_name = platform_name or sys.platform
    home = home or Path.home()
    if platform_name.startswith("win") or platform_name == "cygwin":
        raw_base = os.getenv("LOCALAPPDATA", "").strip()
        if not raw_base:
            raise WorkspaceError("LOCALAPPDATA ist fuer den Standard-Workspace nicht gesetzt.")
        return Path(raw_base) / "AILIZA" / "Workspace"
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / "AILIZA" / "Workspace"
    base = Path(os.getenv("XDG_DATA_HOME", "").strip() or (home / ".local" / "share"))
    return base / "ailiza" / "workspace"


def _authenticated_workspace_broker_available() -> bool:
    """Bewusste Sperre bis zum getrennten, OS-isolierten Security-PR."""
    return False


def initialize_managed_workspace(base_dir: str | Path | None = None) -> Path:
    """Kein In-Process-Einrichtungsweg: nur der kuenftige Broker darf anlegen."""
    del base_dir
    raise WorkspaceError(_WORKSPACE_BROKER_HANDOFF_REASON)


def initialize_custom_workspace(parent_dir: str | Path) -> Path:
    """Benutzerdefinierte Workspaces bleiben bis zum Broker-PR deaktiviert."""
    del parent_dir
    raise WorkspaceError(_WORKSPACE_BROKER_HANDOFF_REASON)


def _get_workspace() -> Path:
    """Ohne authentisierten Broker existiert kein vertrauenswuerdiger Workspace."""
    raise WorkspaceError(_WORKSPACE_BROKER_HANDOFF_REASON)


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


def _is_canonical_macos_standard_workspace(
    resolved: Path,
    *,
    platform_name: str | None = None,
    home: Path | None = None,
) -> bool:
    """Pfad-Ausnahme, aber ausdruecklich kein Kontroll- oder Vertrauensnachweis."""
    platform_name = platform_name or sys.platform
    if platform_name != "darwin":
        return False
    return resolved == _default_workspace_path(
        platform_name="darwin",
        home=home or Path.home(),
    )


def _is_forbidden_workspace_root(
    resolved: Path,
    *,
    platform_name: str | None = None,
    home: Path | None = None,
) -> bool:
    """Reject protected roots without banning every dedicated child folder.

    Broad user folders (for example AppData or Documents) are unsafe when
    selected as the workspace itself.  A dedicated child such as
    ``AppData/Local/Temp/.../ailiza_workspace`` remains usable, while actual
    credential/profile paths stay forbidden at every depth.
    """
    if _is_canonical_macos_standard_workspace(
        resolved,
        platform_name=platform_name,
        home=home,
    ):
        return False
    parts = tuple(part.casefold() for part in resolved.parts)
    parts = tuple(part.casefold() for part in resolved.parts)
    if not parts:
        return True
    # Muss nach der exakten macOS-Standardpfad-Ausnahme stehen:
    # Nur dieser Pfad wurde dort bereits als zulässiger Kandidat klassifiziert.
    if (platform_name or sys.platform) == "darwin":
        application_support_parts = ("library", "application support")
        if any(
            parts[index:index + 2] == application_support_parts
            for index in range(len(parts) - 1)
        ):
            return True

    if not parts:
        return True
    broad_roots = {"appdata", "contacts", "photos", "downloads", "documents"}
    if parts[-1] in broad_roots:
        return True
    protected_parts = {
        ".ssh", ".gnupg", ".aws", ".mozilla", "ntuser.dat",
        "id_rsa", "id_ed25519", "id_ecdsa", "known_hosts", "authorized_keys",
    }
    if any(part in protected_parts for part in parts):
        return True
    protected_sequences = {
        (".config", "google-chrome"), (".config", "chromium"),
        ("library", "application support"),
        ("appdata", "local", "google", "chrome", "user data"),
        ("appdata", "local", "microsoft", "edge", "user data"),
        ("appdata", "roaming", "mozilla", "firefox", "profiles"),
    }
    for sequence in protected_sequences:
        width = len(sequence)
        if any(parts[index:index + width] == sequence
               for index in range(len(parts) - width + 1)):
            return True
    return parts[-1].endswith((".pem", ".p12", ".pfx"))


def _is_sensitive_path(resolved: Path, trusted_workspace: Path | None = None) -> bool:
    # Plattformneutral vergleichen: Windows verwendet Backslashes und seine
    # Pfade sind nicht case-sensitiv. Die Schutzliste ist in POSIX-Form
    # definiert und muss auf beiden Plattformen gleich fail-closed greifen.
    # Liegt das konfigurierte Workspace selbst z.B. unter Windows-AppData,
    # ist dieser Elternpfad bereits bewusst als Grenze freigegeben. Geprueft
    # wird dann nur noch der relative Zielpfad innerhalb des Workspace. Ein
    # per Symlink nach aussen aufgeloestes Ziel ist nicht relativ und wird
    # weiterhin anhand seines vollstaendigen Pfads bewertet.
    path_to_check = resolved
    if trusted_workspace is not None:
        try:
            path_to_check = resolved.relative_to(trusted_workspace)
        except ValueError:
            pass
    parts = tuple(part.casefold() for part in path_to_check.parts)
    certificate_suffixes = {".pem", ".p12", ".pfx"}
    for raw_fragment in _SENSITIVE_PATH_FRAGMENTS:
        fragment_parts = tuple(
            part.casefold() for part in raw_fragment.replace("\\", "/").split("/") if part
        )
        if len(fragment_parts) == 1:
            fragment = fragment_parts[0]
            if fragment in certificate_suffixes:
                if parts and parts[-1].endswith(fragment):
                    return True
            elif fragment in parts:
                return True
            continue
        width = len(fragment_parts)
        if any(parts[index:index + width] == fragment_parts
               for index in range(len(parts) - width + 1)):
            return True
    return False


@dataclass(frozen=True)
class SandboxResult:
    allowed: bool
    action_class: str
    target: str
    reason: str
    requires_approval: bool = False
    requires_owner_approval: bool = False
    in_workspace: bool = False
    responsibility_handoff: bool = False

    @property
    def decision(self) -> str:
        if self.responsibility_handoff:
            return "responsibility_handoff"
        if self.allowed:
            return "allow"
        if self.requires_approval or self.requires_owner_approval:
            return "approval_required"
        return "block"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "action_class": self.action_class,
            "target": self.target,
            "reason": self.reason,
            "requires_approval": self.requires_approval,
            "requires_owner_approval": self.requires_owner_approval,
            "in_workspace": self.in_workspace,
            "decision": self.decision,
            "responsibility_handoff": self.responsibility_handoff,
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

    target_label = target_path or "<unknown>"

    # Immer geblockt — keine Freigabe möglich (kein Workspace nötig)
    if ac in _ALWAYS_BLOCKED:
        return SandboxResult(
            allowed=False,
            action_class=ac.value,
            target=target_label,
            reason=f"Aktion '{ac.value}' ist permanent gesperrt (Device Protection Gate).",
        )

    # Ohne OS-isolierten, authentisierten Broker darf keine Workspace-Dateiaktion
    # bis zur Pfadauflösung oder Dateiberührung gelangen. Eine Umgebungsvariable,
    # ein Verzeichnisname oder eine JSON-Datei sind ausdrücklich kein Ersatz.
    if ac in _FILE_ACTIONS:
        return SandboxResult(
            allowed=False,
            action_class=ac.value,
            target=target_label,
            reason=_WORKSPACE_BROKER_HANDOFF_REASON,
            responsibility_handoff=True,
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
                )
        return SandboxResult(
            allowed=False,
            action_class=ac.value,
            target=target_label,
            reason=f"Aktion '{ac.value}' erfordert explizite Owner-Freigabe.",
            requires_owner_approval=True,
        )

    # Approval-pflichtige Aktionen
    if ac in _REQUIRE_APPROVAL:
        return SandboxResult(
            allowed=False,
            action_class=ac.value,
            target=target_label,
            reason=f"Aktion '{ac.value}' erfordert explizite Nutzer-Freigabe mit Vorschau.",
            requires_approval=True,
        )

    return SandboxResult(
        allowed=False,
        action_class=ac.value,
        target=target_label,
        reason=f"Aktion '{ac.value}' ist nicht im erlaubten Standardverhalten.",
    )


def enforce_sandbox(action_class: ActionClass | str, target_path: str | None = None) -> None:
    """Wirft AILIZAError wenn die lokale Aktion nicht erlaubt ist."""
    result = assess_local_action(action_class, target_path)
    if not result.allowed:
        if result.responsibility_handoff:
            alternatives = [
                "Workspace-Dateiaktion an den authentisierten Broker uebergeben",
                "Administrator mit der kontrollierten Broker-Einrichtung beauftragen",
                "Nicht-dateibasierte AILIZA-Funktion verwenden",
            ]
        else:
            alternatives = [
                "Aktion auf einen zulässigen Umfang beschränken",
                "Explizite Nutzerfreigabe einholen",
                "Administrator kontaktieren",
            ]
        raise AILIZAError(
            message_de=result.reason,
            code="responsibility_handoff" if result.responsibility_handoff else "sandbox_blocked",
            safe_alternatives=alternatives,
        )


def sandbox_status() -> dict[str, Any]:
    """Gibt Sandbox-Konfiguration zurück (für Admin-Endpoint)."""
    configured = os.getenv("AILIZA_WORKSPACE_PATH", "").strip()
    try:
        candidate = configured or str(_default_workspace_path())
    except WorkspaceError as exc:
        candidate = f"<nicht bestimmbar: {exc}>"
    return {
        "workspace_path_candidate": candidate,
        "workspace_configured": False,
        "authenticated_broker_available": _authenticated_workspace_broker_available(),
        "decision": "responsibility_handoff",
        "reason": _WORKSPACE_BROKER_HANDOFF_REASON,
        "maintenance_mode": _is_maintenance_mode(),
        "always_blocked": sorted(a.value for a in _ALWAYS_BLOCKED),
        "require_owner_approval": sorted(a.value for a in _REQUIRE_OWNER_APPROVAL),
        "require_approval": sorted(a.value for a in _REQUIRE_APPROVAL),
        "workspace_autonomous": [],
        "workspace_autonomous_requested": sorted(a.value for a in _WORKSPACE_AUTONOMOUS),
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
        if datetime.now(timezone.utc) >= self.expires_at:
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
