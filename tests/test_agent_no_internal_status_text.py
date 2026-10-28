"""Die Oberflaeche darf nie den internen Status "Agent run completed" als
Antwort zeigen. Fall aus der lokalen Abnahme 2026-10-28: Wetterfrage, Suche
ohne Ergebnis, externe KI ausgeschaltet."""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

from fastapi.testclient import TestClient

from apps.backend import main


class _FakeRuntime:
    def __init__(self, *args, **kwargs):
        pass

    def run(self, task):
        # Suche war geplant, lieferte aber nichts (z. B. Websuche nicht eingerichtet).
        return {
            "run_id": "test-run",
            "status": "completed",
            "message": "Agent run completed",
            "steps": [{"tool": "search", "status": "completed"}],
            "results": [],
        }


def _post(monkeypatch, llm_result):
    monkeypatch.setattr(main, "AgentRuntime", _FakeRuntime)
    monkeypatch.setattr(main, "_ask_llm_directly", lambda *a, **k: llm_result)
    # Echter Ablauf wie in der Oberflaeche: erst Sicherheitspruefung (🔍),
    # dann Senden mit dem ausgestellten Beleg.
    client = TestClient(main.app, cookies={})
    preview = client.post(
        "/api/policy-redact", json={"text": "wie ist das wetter in Hurghada?"},
    ).json()
    assert preview.get("preview_id"), preview
    return client.post(
        "/agent/run",
        json={"task": preview["safe_text"], "preview_id": preview["preview_id"]},
    )


def test_ohne_ki_kommt_verstaendliche_meldung_statt_statustext(monkeypatch):
    response = _post(monkeypatch, (None, "kill_switch_active", []))
    assert response.status_code == 200
    body = response.json()
    assert body["ai_response"] != "Agent run completed"
    assert "externe KI ist derzeit deaktiviert" in body["ai_response"]
    assert "Websuche" in body["ai_response"]


def test_suche_ohne_treffer_fragt_ki_ueber_pipeline(monkeypatch):
    response = _post(monkeypatch, ("Antwort der KI", None, []))
    assert response.status_code == 200
    assert response.json()["ai_response"] == "Antwort der KI"


def test_meldung_ohne_fehlercode_ist_deutsch_und_ohne_statustext():
    text = main._keine_antwort_meldung(None, suche_geplant=False)
    assert "Agent run completed" not in text
    assert "keine KI erreichbar" in text
