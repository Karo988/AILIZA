"""AgentRuntime: clarification_required darf den Lauf nicht abbrechen
(Foundation & Knowledge Kernel Phase 1, Betreiber-Freigabe "Variante 2").

Vorher: JEDE HTTPException aus dem Tool-Executor (Policy-Block, Secret,
aber auch die neue "nicht bewertbar"-Ablehnung aus
governance/payload_check.py) führte in AgentRuntime.run()/stream() dazu,
dass der komplette Lauf als "failed"/"blocked" beendet und die Exception
erneut geworfen wurde -- auch wenn eigentlich nur Information für eine
sichere Entscheidung fehlte.

Jetzt: `_is_clarification_required_error()` erkennt GENAU den einen,
maschinenlesbar signalisierten Fall (`exc.detail == {"reason":
"clarification_required", ...}`) und lässt den Lauf mit Status
"clarification_required" enden, statt ihn abzubrechen. Alle anderen
HTTPExceptions (Secret, Policy, generische Fehler) verhalten sich
unverändert wie zuvor.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest
from fastapi import HTTPException

from apps.backend.agent_runtime import AgentRuntime, _is_clarification_required_error

_CLARIFICATION_EXC = HTTPException(
    status_code=422,
    detail={
        "reason": "clarification_required",
        "message": "Ich kann die Aufgabe weiterbearbeiten, brauche für diesen "
        "Schritt aber noch eine Angabe: ist das Ziel intern oder extern?",
    },
)


def _laufzeit(tool_executor) -> AgentRuntime:
    return AgentRuntime(
        tool_executor=tool_executor,
        audit_writer=lambda action, metadata=None: None,
        persist_runs=False,
    )


# ── _is_clarification_required_error(): kein generischer 422-Fang ───────

def test_erkennt_nur_das_strukturierte_signal():
    """7. Andere 422-Fehler werden NICHT versehentlich zu Clarification."""
    assert _is_clarification_required_error(_CLARIFICATION_EXC) is True
    assert _is_clarification_required_error(
        HTTPException(422, detail="Irgendein anderer Fehlertext")
    ) is False
    assert _is_clarification_required_error(
        HTTPException(422, detail={"reason": "secret_detected", "message": "x"})
    ) is False
    assert _is_clarification_required_error(
        HTTPException(403, detail="Policy verletzt")
    ) is False


# ── run(): clarification_required bricht den Lauf nicht ab ──────────────

def test_run_clarification_required_wird_nicht_zu_failed():
    """2. AgentRuntime behandelt diesen Fall NICHT als 'failed'."""
    def fake_executor(tool, parameters):
        raise _CLARIFICATION_EXC

    ergebnis = _laufzeit(fake_executor).run("Suche etwas Bestimmtes")
    assert ergebnis["status"] != "failed"


def test_run_clarification_required_wird_nicht_zu_blocked():
    """3. AgentRuntime behandelt diesen Fall NICHT als 'blocked'."""
    def fake_executor(tool, parameters):
        raise _CLARIFICATION_EXC

    ergebnis = _laufzeit(fake_executor).run("Suche etwas Bestimmtes")
    assert ergebnis["status"] != "blocked"
    assert ergebnis["status"] == "clarification_required"


def test_run_liefert_konkrete_rueckfrage():
    """4. Nutzer erhält eine konkrete Rückfrage / nächsten Schritt --
    nicht nur eine Abbruchmeldung."""
    def fake_executor(tool, parameters):
        raise _CLARIFICATION_EXC

    ergebnis = _laufzeit(fake_executor).run("Suche etwas Bestimmtes")
    assert "intern oder extern" in ergebnis["message"]


def test_run_wirft_keine_exception_bei_clarification():
    """5. Run bleibt fortsetzbar -- run() gibt normal zurück, statt eine
    Exception zu werfen, die main.py als 4xx an die Nutzerin durchreicht
    und die Aufgabe damit beendet."""
    def fake_executor(tool, parameters):
        raise _CLARIFICATION_EXC

    # Wirft NICHT -- im Gegensatz zu jeder anderen HTTPException.
    ergebnis = _laufzeit(fake_executor).run("Suche etwas Bestimmtes")
    assert ergebnis is not None


def test_run_behaelt_bereits_erzeugte_schritte():
    """6. Bereits erzeugter sicherer Zustand wird nicht verworfen: der
    erste von zwei URLs wird erfolgreich verarbeitet, bevor die zweite
    eine Rückfrage auslöst -- das erste Ergebnis bleibt erhalten."""
    aufrufe = {"n": 0}

    def fake_executor(tool, parameters):
        aufrufe["n"] += 1
        if aufrufe["n"] == 1:
            return {"status": "completed", "tool": tool, "parameters": parameters, "result": {"ok": True}}
        raise _CLARIFICATION_EXC

    aufgabe = "Bitte prüfe https://erste-quelle.test und https://zweite-quelle.test"
    ergebnis = _laufzeit(fake_executor).run(aufgabe)
    assert ergebnis["status"] == "clarification_required"
    assert len(ergebnis["steps"]) == 1, (
        "Der bereits erfolgreich verarbeitete erste Schritt wurde verworfen"
    )


def test_run_secret_block_bleibt_unveraendert_blockierend():
    """8. Secret-/Credential-Block bleibt unverändert -- eine als Secret
    signalisierte Ablehnung (kein clarification_required-detail) muss den
    Lauf weiterhin abbrechen, wie vor dieser Änderung."""
    def fake_executor(tool, parameters):
        raise HTTPException(
            status_code=422,
            detail="Diese Aktion kann nicht zur Freigabe gespeichert werden, "
            "weil die Parameter Zugangsdaten enthalten.",
        )

    with pytest.raises(HTTPException) as exc:
        _laufzeit(fake_executor).run("Suche etwas Bestimmtes")
    assert exc.value.status_code == 422


def test_run_policy_block_bleibt_unveraendert_blockierend():
    def fake_executor(tool, parameters):
        raise HTTPException(status_code=403, detail="Policy verletzt")

    with pytest.raises(HTTPException) as exc:
        _laufzeit(fake_executor).run("Suche etwas Bestimmtes")
    assert exc.value.status_code == 403


def test_run_missing_provider_sonderfall_bleibt_unveraendert():
    """9. Bestehender Missing-Provider-Sonderfall bleibt unverändert."""
    def fake_executor(tool, parameters):
        raise HTTPException(status_code=503, detail="TAVILY_API_KEY is not configured")

    ergebnis = _laufzeit(fake_executor).run("Suche etwas Bestimmtes")
    assert ergebnis["status"] == "local_only"


# ── stream(): derselbe Kontrollfluss ─────────────────────────────────────

def test_stream_clarification_required_bricht_nicht_ab():
    def fake_executor(tool, parameters):
        raise _CLARIFICATION_EXC

    laufzeit = _laufzeit(fake_executor)
    ereignisse = list(laufzeit.stream("Suche etwas Bestimmtes"))
    namen = [e["event"] for e in ereignisse]
    assert "clarification_required" in namen
    letztes = next(e for e in ereignisse if e["event"] == "clarification_required")
    assert letztes["data"]["status"] == "clarification_required"


def test_stream_secret_block_bleibt_unveraendert():
    def fake_executor(tool, parameters):
        raise HTTPException(status_code=422, detail="Secret erkannt.")

    laufzeit = _laufzeit(fake_executor)
    ereignisse = list(laufzeit.stream("Suche etwas Bestimmtes"))
    namen = [e["event"] for e in ereignisse]
    assert "clarification_required" not in namen
    assert "error" in namen or "blocked" in namen
