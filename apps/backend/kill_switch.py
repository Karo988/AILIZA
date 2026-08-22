"""
AILIZA Kill-Switch und Betriebsmodus-Steuerung
===============================================
Globaler Notausschalter fuer externe LLM-Calls und Betriebsmodus.

Betriebsmodi (AILIZA_OPERATION_MODE):
  normal          — Vollbetrieb, alle Funktionen aktiv
  restricted      — Keine Schreibaktionen, keine Massennachrichten, kein Memory
  read_only       — Nur Lesezugriffe und öffentliche Inhalte
  offline         — Kein externer Call, nur lokale Verarbeitung
  kill_switch_active — Alle externen Calls und Schreibaktionen gesperrt

Fail-closed: bei Unklarheit wird extern NICHT gesendet.
Audit-Metadaten: nur run_id, status, mode, timestamp — kein Inhalt.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - fehlende Abhaengigkeit sperrt fail-closed
    yaml = None  # type: ignore[assignment]

try:
    from .errors import AILIZAError
except ImportError:
    from errors import AILIZAError


class OperationMode(str, Enum):
    NORMAL = "normal"
    RESTRICTED = "restricted"
    READ_ONLY = "read_only"
    OFFLINE = "offline"
    KILL_SWITCH_ACTIVE = "kill_switch_active"


_KILL_SWITCH_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "kill_switch.yaml"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


# Verbotene Aktionen je Modus (alles was nicht explizit erlaubt ist → blockiert)
_MODE_BLOCKS: dict[OperationMode, set[str]] = {
    OperationMode.NORMAL: set(),
    OperationMode.RESTRICTED: {"write", "send_message", "memory_store", "mass_notify"},
    OperationMode.READ_ONLY: {"write", "send_message", "memory_store", "mass_notify", "external_llm"},
    OperationMode.OFFLINE: {"external_llm", "send_message", "mass_notify", "fetch"},
    OperationMode.KILL_SWITCH_ACTIVE: {"external_llm", "write", "send_message", "memory_store", "mass_notify", "fetch"},
}


def get_operation_mode() -> OperationMode:
    raw = os.getenv("AILIZA_OPERATION_MODE", "normal").strip().lower()
    try:
        return OperationMode(raw)
    except ValueError:
        return OperationMode.KILL_SWITCH_ACTIVE  # Fail-closed bei unbekanntem Modus


def _env_enabled() -> bool:
    raw = os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "").strip().lower()
    if raw in _FALSE_VALUES:
        return False
    if raw in _TRUE_VALUES:
        return True
    # Fehlend oder unbekannt ist niemals eine Freigabe. Ein vorhandener API-Key
    # darf den administrativen Schalter nicht implizit einschalten.
    return False


def _load_kill_switch_config() -> dict[str, Any] | None:
    """Liest die Schalterdatei bei jeder Entscheidung neu.

    Fehlend, unlesbar, syntaktisch ungueltig oder strukturell unvollstaendig
    ergibt None und damit eine Sperre. Kein Cache: Laufzeitaenderungen greifen
    vor dem naechsten externen Aufruf.
    """
    if yaml is None:
        return None
    try:
        raw = yaml.safe_load(_KILL_SWITCH_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _yaml_external_enabled(provider_id: str | None = None) -> bool:
    config = _load_kill_switch_config()
    if config is None:
        return False
    try:
        if config["global"]["enabled"] is not True:
            return False
        if config["capabilities"]["external_calls"]["enabled"] is not True:
            return False
        if provider_id is not None:
            if config["providers"][provider_id]["enabled"] is not True:
                return False
        return True
    except (KeyError, TypeError):
        return False


def _db_flag_enabled() -> bool | None:
    """Optionales DB-Flag. Gibt None zurueck wenn nicht verfuegbar/gesetzt."""
    try:
        from .database import get_kill_switch_flag  # type: ignore
    except Exception:
        try:
            from database import get_kill_switch_flag  # type: ignore
        except Exception:
            return None
    try:
        return get_kill_switch_flag()
    except Exception:
        return None


def is_external_llm_enabled(provider_id: str | None = None) -> bool:
    """
    True nur bei explizit positivem Env- und YAML-Schalter, nicht sperrendem
    Betriebsmodus und nicht explizit deaktiviertem DB-Flag.
    Fail-closed bei jeglicher Unklarheit.
    """
    try:
        mode = get_operation_mode()
        if "external_llm" in _MODE_BLOCKS.get(mode, set()):
            return False
        if not _env_enabled():
            return False
        if not _yaml_external_enabled(provider_id):
            return False
        if _db_flag_enabled() is False:
            return False
        return True
    except Exception:
        return False


def is_action_allowed(action: str) -> bool:
    """
    Prueft ob eine Aktion im aktuellen Betriebsmodus erlaubt ist.
    Fail-closed: bei Fehler wird blockiert.
    """
    try:
        mode = get_operation_mode()
        return action not in _MODE_BLOCKS.get(mode, {"external_llm", "write", "send_message"})
    except Exception:
        return False


def is_test_mode() -> bool:
    """
    True nur wenn AILIZA_TEST_MODE serverseitig gesetzt ist (Env oder DB-Flag).
    Wird NIEMALS aus Request-Parametern, Headern oder Client-Payload gelesen —
    nur aus Server-Konfiguration. Fail-closed: bei Unklarheit False.
    """
    raw = os.getenv("AILIZA_TEST_MODE", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_production_env() -> bool:
    """True wenn AILIZA_ENV=production gesetzt ist (Server-Konfiguration)."""
    raw = os.getenv("AILIZA_ENV", "").strip().lower()
    return raw == "production"


def enforce_test_mode_not_in_production() -> None:
    """
    Startup-Guard: Verweigert den Start, wenn AILIZA_TEST_MODE=true UND
    AILIZA_ENV=production gleichzeitig gesetzt sind. Setzt technisch durch,
    dass der Testmodus (und damit die AVV-Ausnahme in provider_profiles.py)
    nie in einer produktiv markierten Umgebung aktiv sein kann.
    """
    if is_test_mode() and is_production_env():
        raise RuntimeError(
            "AILIZA_TEST_MODE=true ist zusammen mit AILIZA_ENV=production nicht "
            "zulaessig. Testmodus darf niemals in einer produktiven Umgebung "
            "aktiv sein (Freigabe Stufe 1, P-A, Haertung 1). Start abgebrochen."
        )


def kill_switch_metadata() -> dict[str, Any]:
    """Audit-Metadaten ohne Inhalt (nur Status und Modus)."""
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "external_llm_enabled": is_external_llm_enabled(),
        "operation_mode": get_operation_mode().value,
    }


def enforce_kill_switch(provider_id: str | None = None) -> None:
    """Wirft AILIZAError wenn externe LLM-Calls deaktiviert sind."""
    if not is_external_llm_enabled(provider_id):
        raise AILIZAError.from_code(
            "kill_switch_active",
            safe_alternatives=[
                "Lokale Bearbeitung der Anfrage",
                "Administrator kontaktieren",
            ],
        )


def enforce_action_allowed(action: str) -> None:
    """Wirft AILIZAError wenn Aktion im aktuellen Betriebsmodus nicht erlaubt ist."""
    if not is_action_allowed(action):
        mode = get_operation_mode()
        raise AILIZAError.from_code(
            "kill_switch_active",
            safe_alternatives=[f"Aktion '{action}' ist im Modus '{mode.value}' nicht erlaubt."],
        )


# ── Granularer Kill-Switch-Check (Provider / Modul / Capability) ──────────────

def check_kill_switch(scope: str, name: str) -> dict[str, Any]:
    """
    Prueft Kill-Switch-Status fuer einen bestimmten Scope.

    scope: "provider" | "module" | "capability" | "global"
    name:  Provider-ID, Modul-Name oder Capability-ID

    Gibt {allowed: bool, scope, name, reason, mode} zurueck.
    Fail-closed: bei Fehler immer allowed=False.
    """
    try:
        mode = get_operation_mode()
        mode_blocks = _MODE_BLOCKS.get(mode, set())

        if scope == "global":
            allowed = "external_llm" not in mode_blocks and is_external_llm_enabled()
            reason = "Kill-Switch aktiv" if not allowed else "ok"
            return {"allowed": allowed, "scope": scope, "name": name,
                    "reason": reason, "mode": mode.value}

        if scope == "provider":
            # Provider-spezifischer Kill-Switch: Admin-disabled-Flag aus provider_profiles
            try:
                from .providers.provider_profiles import get_profile
            except ImportError:
                from providers.provider_profiles import get_profile
            profile = get_profile(name)
            if profile is None:
                return {"allowed": False, "scope": scope, "name": name,
                        "reason": f"Unbekannter Provider '{name}'", "mode": mode.value}
            if profile.admin_disabled:
                return {"allowed": False, "scope": scope, "name": name,
                        "reason": f"Provider '{name}' durch Admin-Kill-Switch deaktiviert",
                        "mode": mode.value}
            if not profile.active:
                return {"allowed": False, "scope": scope, "name": name,
                        "reason": f"Provider '{name}' ist inaktiv",
                        "mode": mode.value}
            if not is_external_llm_enabled(name):
                return {"allowed": False, "scope": scope, "name": name,
                        "reason": f"Provider '{name}' ist nicht vollstaendig freigeschaltet",
                        "mode": mode.value}
            # Globaler Modus blockiert externe Calls?
            if "external_llm" in mode_blocks:
                return {"allowed": False, "scope": scope, "name": name,
                        "reason": f"Modus '{mode.value}' blockiert externe Provider-Calls",
                        "mode": mode.value}
            return {"allowed": True, "scope": scope, "name": name,
                    "reason": "ok", "mode": mode.value}

        if scope == "capability":
            try:
                from .capabilities.registry import _CAPABILITIES
            except ImportError:
                from capabilities.registry import _CAPABILITIES
            cap = _CAPABILITIES.get(name)
            if cap is None:
                return {"allowed": False, "scope": scope, "name": name,
                        "reason": f"Unbekannte Capability '{name}'", "mode": mode.value}
            if not cap.enabled:
                return {"allowed": False, "scope": scope, "name": name,
                        "reason": f"Capability '{name}' ist deaktiviert",
                        "mode": mode.value}
            if cap.can_send_external and "external_llm" in mode_blocks:
                return {"allowed": False, "scope": scope, "name": name,
                        "reason": f"Modus '{mode.value}' blockiert externe Capability-Calls",
                        "mode": mode.value}
            return {"allowed": True, "scope": scope, "name": name,
                    "reason": "ok", "mode": mode.value}

        if scope == "module":
            # Modul-Kill-Switch über action_allowed (Modul-Name entspricht Aktionsname)
            allowed = is_action_allowed(name)
            return {"allowed": allowed, "scope": scope, "name": name,
                    "reason": "ok" if allowed else f"Modul '{name}' im Modus '{mode.value}' blockiert",
                    "mode": mode.value}

        # Unbekannter Scope → fail-closed
        return {"allowed": False, "scope": scope, "name": name,
                "reason": f"Unbekannter Scope '{scope}' — fail-closed", "mode": mode.value}

    except Exception as exc:
        return {"allowed": False, "scope": scope, "name": name,
                "reason": f"Kill-Switch-Prüfung fehlgeschlagen — fail-closed: {type(exc).__name__}",
                "mode": "unknown"}
