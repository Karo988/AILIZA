"""Verdrahtung des Prüfbelegs in den echten Versandweg.

Der isolierte Modultest (test_send_preview_contract.py) prüft den Baustein.
Hier wird bewiesen, dass er tatsächlich im Weg steht: /api/policy-redact
stellt einen Beleg aus, /agent/run löst ihn ein und lehnt ab, wenn der
gesendete Text nicht der geprüfte ist.
"""
from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

from apps.backend.main import app

client = TestClient(app)

_HARMLOS = "Wie formuliere ich eine freundliche Absage?"


def _preview(text: str) -> dict:
    response = client.post("/api/policy-redact", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def test_harmless_text_is_actually_sendable():
    """Wachhund fuer die uebrigen Tests dieser Datei: mehrere davon
    ueberspringen sich selbst, wenn die Policy den harmlosen Beispieltext
    nicht zum Senden freigibt. Ohne diesen Test wuerde eine Policy-Aenderung
    sie stillschweigend wirkungslos machen -- die Suite waere gruen, ohne
    noch irgendetwas zu pruefen. Schlaegt dieser Test fehl, ist nicht der
    Pruefbeleg kaputt, sondern der Beispieltext unpassend geworden."""
    data = _preview(_HARMLOS)
    assert data["can_send_to_llm"], (
        "Beispieltext gilt nicht mehr als sendbar -- die Skip-Pfade der "
        "anderen Tests greifen jetzt und pruefen nichts mehr."
    )
    assert data["preview_id"]


def _run(task: str, preview_id: str | None = None) -> dict:
    payload: dict = {"task": task}
    if preview_id is not None:
        payload["preview_id"] = preview_id
    response = client.post("/agent/run", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# ── Der Beleg wird überhaupt ausgestellt ─────────────────────────────────

def test_preview_endpoint_issues_a_token_for_sendable_text():
    data = _preview(_HARMLOS)
    if not data["can_send_to_llm"]:
        pytest.skip("Text wird von der aktuellen Policy nicht zum Senden freigegeben")
    assert data["preview_id"], "Für sendbaren Text muss ein Prüfbeleg entstehen"


def test_preview_response_never_contains_the_original_text():
    """Der Beleg darf keine Kopie des Textes mitliefern -- er ist nur ein
    Verweis, der Inhalt bleibt beim Aufrufer."""
    geheim = "Meine Kundennummer ist 12345 und mein Name ist Erika Mustermann"
    data = _preview(geheim)
    assert "Mustermann" not in str(data.get("preview_id"))


# ── Der Beleg steht wirklich im Weg ──────────────────────────────────────

def test_send_with_valid_preview_is_accepted():
    data = _preview(_HARMLOS)
    if not data.get("preview_id"):
        pytest.skip("Kein Beleg ausgestellt -- Policy laesst diesen Text nicht durch")
    result = _run(data["safe_text"], preview_id=data["preview_id"])
    assert result.get("status") != "preview_invalid", result


def test_send_with_manipulated_text_is_rejected():
    """Kernfall: Der Beleg gilt für einen bestimmten Text. Wer danach etwas
    anderes sendet, kommt nicht durch -- sonst waere die Vorschau wertlos.

    Die Manipulation darf hier keine eigene Personenbezug-/Redaction-Erkennung
    (Fall 2) ausloesen -- sonst wuerde man nur pruefen, dass Fall 2 vor
    diesem Test greift, nicht dass der Text-Hash-Abgleich selbst wirkt."""
    data = _preview(_HARMLOS)
    if not data.get("preview_id"):
        pytest.skip("Kein Beleg ausgestellt")
    result = _run(data["safe_text"] + " Bitte kurz und knapp.",
                  preview_id=data["preview_id"])
    assert result["status"] == "preview_invalid"
    assert "geprüft" in result["message"] or "Prüfung" in result["message"]


def test_send_with_unknown_preview_id_is_rejected():
    result = _run(_HARMLOS, preview_id="frei-erfunden")
    assert result["status"] == "preview_invalid"


def test_preview_cannot_be_reused():
    data = _preview(_HARMLOS)
    if not data.get("preview_id"):
        pytest.skip("Kein Beleg ausgestellt")
    _run(data["safe_text"], preview_id=data["preview_id"])
    zweiter = _run(data["safe_text"], preview_id=data["preview_id"])
    assert zweiter["status"] == "preview_invalid"


def test_rejected_send_never_reaches_the_provider():
    """Der eigentliche Beweis: bei ungueltigem Beleg darf der externe
    Anbieter gar nicht erst aufgerufen werden."""
    with patch("apps.backend.main._orchestrator") as fake_orchestrator:
        result = _run("Beliebiger Text", preview_id="ungueltig")
        assert result["status"] == "preview_invalid"
        fake_orchestrator.generate.assert_not_called()


# ── Verpflichtender Beleg -- kein Compatibility-Bypass ───────────────────

def test_send_without_preview_id_is_rejected():
    """Kerninvariante: kein externer Versand ohne gueltigen Beleg. Ein
    frueherer Zwischenstand liess das Fehlen von preview_id durchgehen
    (Server redigiert dann selbst im selben Request) -- das war genau die
    Luecke, die diese Aenderung schliesst. Fall 2/3 (Login/Einwilligung)
    bleiben davon unberuehrt, siehe die anderen Tests dieser Datei: sie
    senden schon vorher nichts extern und enden mit login_required/
    consent_required, bevor dieses Gate ueberhaupt erreicht wird."""
    result = _run(_HARMLOS)
    assert result["status"] == "preview_invalid"


def test_fall2_login_required_is_not_masked_by_the_preview_gate():
    """Regressionsschutz: das Gate darf NICHT vor der bestehenden
    Fall-2/3-Logik greifen. Derselbe Text wie in
    test_compliance_consent_flow.py::BRIEF_PII muss weiterhin
    login_required liefern, nicht preview_invalid -- sonst waere die
    bereits freigegebene Stufenlogik (Betreiber-Freigabe 2026-07-11)
    unbenutzbar. (Der erste Entwurf dieser Aenderung hatte genau das
    kaputtgemacht -- aufgedeckt durch test_compliance_consent_flow.py,
    hier als eigener Regressionstest festgehalten.)"""
    brief_pii = (
        "Bitte fasse diesen Brief zusammen: Mein Name ist Paula Ronder, ich leide "
        "an einer HIV-Infektion, bin Mitglied der Gewerkschaft ver.di, Religion "
        "roemisch-katholisch, IBAN DE89370400440532013000."
    )
    result = _run(brief_pii)
    assert result["status"] == "login_required"


def test_rejection_message_is_understandable_german():
    result = _run(_HARMLOS, preview_id="ungueltig")
    nachricht = result["message"]
    assert "Traceback" not in nachricht
    assert "Exception" not in nachricht
    assert len(nachricht) > 20, "Die Meldung muss erklaeren, was zu tun ist"
