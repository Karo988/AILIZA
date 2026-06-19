"""
AILIZA Kill-Switch
==================
Globaler Notausschalter fuer externe LLM-Calls.

Prueft die Umgebungsvariable AILIZA_EXTERNAL_LLM_ENABLED sowie ein optionales
DB-Flag. Fail-closed: bei Unklarheit wird extern NICHT gesendet.

Es werden niemals Inhalte geloggt, nur Metadaten (Zeitpunkt, Status).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

try:
    from .errors import AILIZAError
except ImportError:  # pragma: no cover
    from errors import AILIZAError


def _env_enabled() -> bool:
    raw = os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


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
    True nur wenn env aktiviert UND DB-Flag nicht explizit deaktiviert.
    Fail-closed bei jeglicher Unklarheit.
    """
    try:
        if not _env_enabled():
            return False
        if _db_flag_enabled() is False:
            return False
        return True
    except Exception:
        return False


def kill_switch_metadata() -> dict[str, Any]:
    """Audit-Metadaten ohne Inhalt."""
    return {
        "kill_switch_checked_at": datetime.now(timezone.utc).isoformat(),
        "external_llm_enabled": is_external_llm_enabled(),
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
