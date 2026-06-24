"""
AILIZA Kill-Switch & Restricted-Modus
======================================
EU AI Act Art. 14: Menschliche Aufsicht — System muss stoppbar sein
EU AI Act Art. 9:  Risikomanagementsystem

Vier Ebenen in Prioritätsreihenfolge:
  GLOBAL    → gesamtes System gestoppt (höchste Priorität)
  PROVIDER  → einzelner LLM-Anbieter deaktiviert
  MODULE    → einzelnes Modul deaktiviert (memory, approvals, search, ...)
  CAPABILITY → einzelne Fähigkeit blockiert (fetch, file_write, ...)

Logik: Eine einzige Traversierung — sobald eine Ebene blockiert, stoppt die Prüfung.
Das System kennt zwei Betriebsmodi:
  NORMAL      → alle nicht explizit blockierten Aktionen erlaubt
  RESTRICTED  → nur explizit freigegebene Aktionen erlaubt (Whitelist-Modus)
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Optional, Set


class OperationMode(str):
    NORMAL = "normal"
    RESTRICTED = "restricted"


class KillSwitchLevel(IntEnum):
    """Priorität: niedrigere Zahl = höhere Priorität."""
    GLOBAL = 0
    PROVIDER = 1
    MODULE = 2
    CAPABILITY = 3


@dataclass
class KillSwitchState:
    global_halt: bool = False
    halted_providers: Set[str] = field(default_factory=set)
    halted_modules: Set[str] = field(default_factory=set)
    halted_capabilities: Set[str] = field(default_factory=set)
    mode: str = OperationMode.NORMAL
    last_changed_at: Optional[datetime] = None
    last_changed_by: str = "system"


@dataclass
class KillSwitchResult:
    blocked: bool
    level: Optional[KillSwitchLevel]
    reason: str

    @property
    def allowed(self) -> bool:
        return not self.blocked


class KillSwitch:
    """
    Zentraler Kill-Switch mit vier Ebenen und zwei Betriebsmodi.

    Thread-sicher. Alle Zustandsänderungen werden intern geloggt.
    Für persistente Speicherung ist ein Storage-Backend einzuhängen (später).
    """

    def __init__(self) -> None:
        self._state = KillSwitchState()
        self._lock = threading.Lock()
        self._change_log: list[dict] = []  # In-Memory-Log für diese Session

    # ── Traversierung ─────────────────────────────────────────────────────

    def check(
        self,
        provider: Optional[str] = None,
        module: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> KillSwitchResult:
        """
        Prüft alle vier Ebenen in Prioritätsreihenfolge.
        Gibt beim ersten Match zurück — keine vollständige Traversierung nötig.
        """
        with self._lock:
            state = self._state

        # Ebene 0: GLOBAL
        if state.global_halt:
            return KillSwitchResult(True, KillSwitchLevel.GLOBAL, "System global gestoppt")

        # Ebene 1: PROVIDER
        if provider and provider.lower() in state.halted_providers:
            return KillSwitchResult(True, KillSwitchLevel.PROVIDER, f"Provider gesperrt: {provider}")

        # Ebene 2: MODULE
        if module and module.lower() in state.halted_modules:
            return KillSwitchResult(True, KillSwitchLevel.MODULE, f"Modul gesperrt: {module}")

        # Ebene 3: CAPABILITY
        if capability and capability.lower() in state.halted_capabilities:
            return KillSwitchResult(True, KillSwitchLevel.CAPABILITY, f"Capability gesperrt: {capability}")

        return KillSwitchResult(False, None, "OK")

    def is_restricted_mode(self) -> bool:
        with self._lock:
            return self._state.mode == OperationMode.RESTRICTED

    # ── GLOBAL ────────────────────────────────────────────────────────────

    def halt_global(self, actor: str = "operator") -> None:
        """Stoppt das gesamte System (EU AI Act Art. 14)."""
        self._apply(actor, lambda s: setattr(s, "global_halt", True), "GLOBAL_HALT")

    def resume_global(self, actor: str = "operator") -> None:
        self._apply(actor, lambda s: setattr(s, "global_halt", False), "GLOBAL_RESUME")

    # ── PROVIDER ──────────────────────────────────────────────────────────

    def halt_provider(self, provider: str, actor: str = "operator") -> None:
        self._apply(actor, lambda s: s.halted_providers.add(provider.lower()), f"PROVIDER_HALT:{provider}")

    def resume_provider(self, provider: str, actor: str = "operator") -> None:
        self._apply(actor, lambda s: s.halted_providers.discard(provider.lower()), f"PROVIDER_RESUME:{provider}")

    # ── MODULE ────────────────────────────────────────────────────────────

    def halt_module(self, module: str, actor: str = "operator") -> None:
        self._apply(actor, lambda s: s.halted_modules.add(module.lower()), f"MODULE_HALT:{module}")

    def resume_module(self, module: str, actor: str = "operator") -> None:
        self._apply(actor, lambda s: s.halted_modules.discard(module.lower()), f"MODULE_RESUME:{module}")

    # ── CAPABILITY ────────────────────────────────────────────────────────

    def halt_capability(self, capability: str, actor: str = "operator") -> None:
        self._apply(actor, lambda s: s.halted_capabilities.add(capability.lower()), f"CAPABILITY_HALT:{capability}")

    def resume_capability(self, capability: str, actor: str = "operator") -> None:
        self._apply(actor, lambda s: s.halted_capabilities.discard(capability.lower()), f"CAPABILITY_RESUME:{capability}")

    # ── MODUS ─────────────────────────────────────────────────────────────

    def set_restricted(self, actor: str = "operator") -> None:
        self._apply(actor, lambda s: setattr(s, "mode", OperationMode.RESTRICTED), "MODE_RESTRICTED")

    def set_normal(self, actor: str = "operator") -> None:
        self._apply(actor, lambda s: setattr(s, "mode", OperationMode.NORMAL), "MODE_NORMAL")

    # ── Status ────────────────────────────────────────────────────────────

    def status(self) -> dict:
        with self._lock:
            s = self._state
            return {
                "global_halt": s.global_halt,
                "mode": s.mode,
                "halted_providers": sorted(s.halted_providers),
                "halted_modules": sorted(s.halted_modules),
                "halted_capabilities": sorted(s.halted_capabilities),
                "last_changed_at": s.last_changed_at.isoformat() if s.last_changed_at else None,
                "last_changed_by": s.last_changed_by,
                "change_log_entries": len(self._change_log),
            }

    def change_log(self) -> list[dict]:
        with self._lock:
            return list(self._change_log)

    # ── Intern ────────────────────────────────────────────────────────────

    def _apply(self, actor: str, mutation, event: str) -> None:
        with self._lock:
            mutation(self._state)
            self._state.last_changed_at = datetime.now(timezone.utc)
            self._state.last_changed_by = actor
            self._change_log.append({
                "event": event,
                "actor": actor,
                "timestamp": self._state.last_changed_at.isoformat(),
            })


# Singleton — wird von gateway.py importiert
_kill_switch = KillSwitch()


def get_kill_switch() -> KillSwitch:
    return _kill_switch
