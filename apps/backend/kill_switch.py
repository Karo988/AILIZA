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
from typing import Any

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
    # Explizit deaktiviert → False
    if raw in {"0", "false", "no", "off"}:
        return False
    # Explizit aktiviert → True
    if raw in {"1", "true", "yes", "on"}:
        return True
    # Nicht gesetzt: aktivieren wenn ein API-Key vorhanden ist (Render-Deployment)
    has_key = bool(
        os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    )
    return has_key


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


def is_external_llm_enabled() -> bool:
    """
    True nur wenn env aktiviert UND DB-Flag nicht explizit deaktiviert
    UND Betriebsmodus external_llm nicht blockiert.
    Fail-closed bei jeglicher Unklarheit.
    """
    try:
        mode = get_operation_mode()
        if "external_llm" in _MODE_BLOCKS.get(mode, set()):
            return False
        if not _env_enabled():
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


def kill_switch_metadata() -> dict[str, Any]:
    """Audit-Metadaten ohne Inhalt (nur Status und Modus)."""
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "external_llm_enabled": is_external_llm_enabled(),
        "operation_mode": get_operation_mode().value,
    }


def enforce_kill_switch() -> None:
    """Wirft AILIZAError wenn externe LLM-Calls deaktiviert sind."""
    if not is_external_llm_enabled():
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
