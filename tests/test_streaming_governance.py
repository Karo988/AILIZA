"""Governance für Streaming, strukturierte Nutzlasten und Anbieter-Kontext
(Paket D, Teil 2).

Geprüft wird der Inhalt, nicht der Transportweg. Ein Zugangsschlüssel in
einem Tool-Ergebnisfeld ist derselbe Vorfall wie derselbe Schlüssel im
Antworttext -- er darf nicht deshalb durchgehen, weil er über SSE kommt
oder in einem Dictionary steckt.

Die Tests belegen vier Invarianten:
  1. Kein Streaming ohne gültigen Prüfbeleg (serverseitig, nicht im Browser).
  2. Kein Aufgabentext in einer URL.
  3. Kein ungeprüftes Streaming-Ereignis verlässt den Server.
  4. Der Anbieter-Aufruf kennt die echte Datenklasse statt "public".
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

import apps.backend.main as main_module
from apps.backend.main import (
    _erlaubte_reinsertion_map,
    _gepruefte_antwort,
    _gepruefter_ereignisstrom,
    _leite_governance_kontext_ab,
    _pruefe_nutzlast,
)

GEHEIM = "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def client():
    from apps.backend.main import app
    return TestClient(app, cookies={})


def _preview_id(client, task: str) -> str:
    resp = client.post("/api/policy-redact", json={"text": task})
    assert resp.status_code == 200, resp.text
    pid = resp.json().get("preview_id")
    assert pid, f"Kein Prüfbeleg ausgestellt: {resp.json()}"
    return pid


def _sse_ereignisse(text: str) -> list[dict]:
    """Zerlegt eine SSE-Antwort in (event, data)-Paare."""
    ereignisse = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        name, daten = None, None
        for zeile in block.splitlines():
            if zeile.startswith("event: "):
                name = zeile[len("event: "):]
            elif zeile.startswith("data: "):
                daten = json.loads(zeile[len("data: "):])
        ereignisse.append({"event": name, "data": daten})
    return ereignisse


# ── Testklasse 5: Prüfbeleg-Gate für Streaming ───────────────────────────

def test_streaming_ohne_pruefbeleg_wird_abgelehnt(client, monkeypatch):
    """Kernnachweis: ohne Beleg wird kein Anbieter kontaktiert."""
    aufgerufen = {"ja": False}

    class _NieAufrufen:
        def __init__(self, *a, **kw):
            pass

        def stream(self, *a, **kw):
            aufgerufen["ja"] = True
            yield {"event": "run_completed", "data": {"message": "sollte nie kommen"}}

    monkeypatch.setattr(main_module, "AgentRuntime", _NieAufrufen)
    resp = client.post("/agent/run/stream", json={"task": "Was ist Photosynthese?"})

    assert resp.status_code == 200
    ereignisse = _sse_ereignisse(resp.text)
    assert ereignisse[0]["event"] == "preview_invalid"
    assert not aufgerufen["ja"], (
        "Ohne gültigen Prüfbeleg wurde trotzdem ein Agentenlauf gestartet"
    )


def test_streaming_mit_gefaelschtem_beleg_wird_abgelehnt(client):
    resp = client.post(
        "/agent/run/stream",
        json={"task": "Was ist Photosynthese?", "preview_id": "erfunden-1234"},
    )
    assert resp.status_code == 200
    assert _sse_ereignisse(resp.text)[0]["event"] == "preview_invalid"


def test_beleg_fuer_andere_aufgabe_wird_abgelehnt(client):
    """Ein Beleg darf nicht auf einen beliebigen anderen Text übertragbar sein."""
    beleg = _preview_id(client, "Harmlose Frage zur Photosynthese.")
    resp = client.post(
        "/agent/run/stream",
        json={"task": "Ganz andere Aufgabe mit anderem Inhalt.", "preview_id": beleg},
    )
    assert _sse_ereignisse(resp.text)[0]["event"] == "preview_invalid"


def test_beleg_ist_nur_einmal_verwendbar(client, monkeypatch):
    class _Leer:
        def __init__(self, *a, **kw):
            pass

        def stream(self, *a, **kw):
            yield {"event": "run_completed", "data": {"message": "fertig"}}

    monkeypatch.setattr(main_module, "AgentRuntime", _Leer)
    aufgabe = "Was ist Photosynthese?"
    beleg = _preview_id(client, aufgabe)

    erste = client.post("/agent/run/stream", json={"task": aufgabe, "preview_id": beleg})
    assert _sse_ereignisse(erste.text)[0]["event"] != "preview_invalid"

    zweite = client.post("/agent/run/stream", json={"task": aufgabe, "preview_id": beleg})
    assert _sse_ereignisse(zweite.text)[0]["event"] == "preview_invalid", (
        "Derselbe Beleg war ein zweites Mal verwendbar"
    )


# ── Kein Aufgabentext in einer URL ───────────────────────────────────────

def test_get_streaming_route_existiert_nicht_mehr(client):
    """Der Aufgabentext darf nicht über ?task=... transportiert werden --
    er landet sonst in Zugriffsprotokollen, Verlauf und Referrer."""
    resp = client.get("/agent/run/stream", params={"task": "Frau Müller hat Diabetes"})
    assert resp.status_code == 405, (
        f"GET-Route mit Aufgabentext in der URL ist noch erreichbar ({resp.status_code})"
    )


def test_keine_route_nimmt_aufgabentext_als_query_parameter():
    """Gegenprobe über alle registrierten Routen, damit die Lücke nicht an
    anderer Stelle wieder aufgeht."""
    from apps.backend.main import app

    treffer = []
    for route in app.routes:
        methoden = getattr(route, "methods", set()) or set()
        if "GET" not in methoden:
            continue
        abhaengigkeiten = getattr(getattr(route, "dependant", None), "query_params", [])
        for param in abhaengigkeiten:
            if param.name in {"task", "text", "prompt", "message"}:
                treffer.append(f"{route.path}?{param.name}")
    assert not treffer, f"Nutzdaten als Query-Parameter: {treffer}"


# ── Testklasse 4: Ausgangsprüfung je Streaming-Ereignis ──────────────────

def test_tool_completed_secret_wird_nicht_gesendet():
    """Ein Schlüssel aus einem abgerufenen Webinhalt darf die Anzeige nicht
    erreichen -- auch nicht über ein Tool-Ergebnisfeld."""
    strom = [{
        "event": "tool_completed",
        "data": {"tool": "search", "summary": f"Gefunden: {GEHEIM}"},
    }]
    ausgabe = list(_gepruefter_ereignisstrom(strom, tenant_id="default"))
    assert GEHEIM not in json.dumps(ausgabe, ensure_ascii=False)


def test_run_completed_secret_in_verschachtelter_struktur():
    strom = [{
        "event": "run_completed",
        "data": {
            "run_id": "abc",
            "results": [{"tool": "fetch", "result": {"body": f"Key: {GEHEIM}"}}],
        },
    }]
    ausgabe = list(_gepruefter_ereignisstrom(strom, tenant_id="default"))
    assert GEHEIM not in json.dumps(ausgabe, ensure_ascii=False)


def test_harmlose_ereignisse_kommen_unveraendert_durch():
    """Die Härtung darf den Normalfall nicht kaputt machen."""
    strom = [
        {"event": "run_started", "data": {"run_id": "abc", "planned_steps": 2}},
        {"event": "run_completed", "data": {"message": "Photosynthese erklärt."}},
    ]
    ausgabe = list(_gepruefter_ereignisstrom(strom, tenant_id="default"))
    assert ausgabe[0]["data"]["planned_steps"] == 2
    assert ausgabe[1]["data"]["message"] == "Photosynthese erklärt."


def test_stream_bricht_fail_closed_ab_wenn_pruefung_scheitert(monkeypatch):
    """Scanner-Ausfall: nichts Ungeprüftes darf noch hinausgehen."""
    def _kaputt(_text):
        raise RuntimeError("Scanner nicht verfügbar")

    monkeypatch.setattr(main_module, "strip_secrets_with_placeholder", _kaputt)
    strom = [
        {"event": "run_completed", "data": {"message": "irgendetwas"}},
        {"event": "danach", "data": {"message": "darf nicht mehr kommen"}},
    ]
    ausgabe = list(_gepruefter_ereignisstrom(strom, tenant_id="default"))
    assert ausgabe[-1]["event"] == "output_blocked"
    assert "darf nicht mehr kommen" not in json.dumps(ausgabe, ensure_ascii=False)


def test_stream_route_prueft_die_ereignisse_wirklich(client, monkeypatch):
    """Verdrahtungsnachweis: nicht nur die Funktion, sondern die echte Route."""
    class _RuntimeMitSecret:
        def __init__(self, *a, **kw):
            pass

        def stream(self, *a, **kw):
            yield {"event": "tool_completed", "data": {"summary": f"Key: {GEHEIM}"}}

    monkeypatch.setattr(main_module, "AgentRuntime", _RuntimeMitSecret)
    aufgabe = "Was ist Photosynthese?"
    resp = client.post(
        "/agent/run/stream",
        json={"task": aufgabe, "preview_id": _preview_id(client, aufgabe)},
    )
    assert resp.status_code == 200
    ereignisse = _sse_ereignisse(resp.text)
    # Ohne diese Zusicherung wäre der Test wertlos: würde der Beleg abgelehnt,
    # käme nur "preview_invalid" zurück und die Schlüssel-Prüfung unten wäre
    # trivial erfüllt, ohne dass die Ereignisprüfung je gelaufen ist.
    assert [e["event"] for e in ereignisse] == ["tool_completed"], (
        f"Der Strom lief nicht wie erwartet: {[e['event'] for e in ereignisse]}"
    )
    assert GEHEIM not in resp.text, (
        "Der Schlüssel wurde ungeprüft über die Streaming-Route gesendet"
    )


# ── §17: sichere Teilweiterarbeit statt Vollsperre ───────────────────────

def test_nur_das_betroffene_feld_wird_zurueckgehalten():
    zaehler: dict[str, int] = {}
    ergebnis = _pruefe_nutzlast(
        {
            "titel": "Quartalsbericht",
            "zugang": f"Key: {GEHEIM}",
            "seiten": 12,
            "autor": "Redaktion",
        },
        {},
        zaehler,
    )
    assert GEHEIM not in json.dumps(ergebnis, ensure_ascii=False)
    assert ergebnis["titel"] == "Quartalsbericht"
    assert ergebnis["seiten"] == 12
    assert ergebnis["autor"] == "Redaktion"


def test_strukturtypen_bleiben_erhalten():
    zaehler: dict[str, int] = {}
    eingabe = {"liste": ["a", "b"], "leer": None, "wahr": True, "zahl": 1.5}
    ergebnis = _pruefe_nutzlast(eingabe, {}, zaehler)
    assert ergebnis == eingabe


def test_unbekannter_typ_wird_fail_closed_ersetzt():
    class Exotisch:
        def __str__(self):
            return GEHEIM

    zaehler: dict[str, int] = {}
    ergebnis = _pruefe_nutzlast({"feld": Exotisch()}, {}, zaehler)
    assert ergebnis["feld"] != GEHEIM
    assert zaehler["gesperrte_felder"] == 1


def test_zu_grosse_nutzlast_wird_abgelehnt_statt_durchgereicht():
    zaehler: dict[str, int] = {}
    riesig = ["x"] * (main_module._MAX_NUTZLAST_KNOTEN + 5)
    with pytest.raises(ValueError):
        _pruefe_nutzlast(riesig, {}, zaehler)


def test_tiefe_verschachtelung_wird_abgelehnt():
    zaehler: dict[str, int] = {}
    tief: dict = {"a": "ende"}
    for _ in range(main_module._MAX_NUTZLAST_TIEFE + 5):
        tief = {"a": tief}
    with pytest.raises(ValueError):
        _pruefe_nutzlast(tief, {}, zaehler)


def test_unicode_und_html_bleiben_unversehrt():
    zaehler: dict[str, int] = {}
    text = "<p>Grüße aus Zürich — 日本語 😀</p>"
    assert _pruefe_nutzlast(text, {}, zaehler) == text


# ── Reinsertion in strukturierten Nutzlasten ─────────────────────────────

def test_platzhalter_werden_auch_in_feldern_eingesetzt():
    zaehler: dict[str, int] = {}
    ergebnis = _pruefe_nutzlast(
        {"anrede": "Sehr geehrte [NAME_1]"}, {"[NAME_1]": "Frau Müller"}, zaehler,
    )
    assert ergebnis["anrede"] == "Sehr geehrte Frau Müller"


def test_geheimnis_wird_nicht_ueber_die_abbildung_wieder_eingesetzt():
    """Sonst wäre die Entfernung wirkungslos."""
    erlaubt, zurueckgehalten = _erlaubte_reinsertion_map({"[X_1]": GEHEIM, "[N_1]": "Müller"})
    assert "[X_1]" not in erlaubt
    assert erlaubt["[N_1]"] == "Müller"
    assert zurueckgehalten == 1


# ── Testklasse 6: Fortsetzung nach Freigabe ──────────────────────────────

def test_fortsetzung_nach_freigabe_wird_ebenfalls_geprueft(client, monkeypatch):
    """Die Freigabe einer Aktion ist keine Freigabe späterer Inhalte."""
    class _RuntimeFortsetzung:
        def __init__(self, *a, **kw):
            pass

        def continue_after_approval(self, approval_id):
            return {
                "status": "completed",
                "message": "Fertig.",
                "results": [{"result": {"token": GEHEIM}}],
            }

    monkeypatch.setattr(main_module, "AgentRuntime", _RuntimeFortsetzung)
    resp = client.post("/agent/approvals/1/continue")
    assert resp.status_code == 200
    assert GEHEIM not in resp.text


def test_fortsetzung_streaming_wird_ebenfalls_geprueft(client, monkeypatch):
    class _RuntimeFortsetzungStream:
        def __init__(self, *a, **kw):
            pass

        def stream_after_approval(self, approval_id):
            yield {"event": "run_completed", "data": {"message": f"Key: {GEHEIM}"}}

    monkeypatch.setattr(main_module, "AgentRuntime", _RuntimeFortsetzungStream)
    resp = client.post("/agent/approvals/1/continue/stream")
    assert resp.status_code == 200
    assert GEHEIM not in resp.text


def test_gepruefte_antwort_faellt_fail_closed_aus(monkeypatch):
    def _kaputt(_text):
        raise RuntimeError("Scanner nicht verfügbar")

    monkeypatch.setattr(main_module, "strip_secrets_with_placeholder", _kaputt)
    ergebnis = _gepruefte_antwort({"message": "irgendetwas"}, tenant_id="default")
    assert ergebnis["status"] == "output_blocked"
    assert "irgendetwas" not in json.dumps(ergebnis, ensure_ascii=False)


# ── Testklasse 7: echter Governance-Kontext für den Anbieter ─────────────

def test_kontext_meldet_echte_datenklasse_statt_public():
    kontext = _leite_governance_kontext_ab(
        "Frau Müller, Diabetes Typ 2, Termin am 3. Mai.", tenant_id="default",
    )
    from apps.backend.governance.data_governance import DataClass

    assert kontext.data_classes != [DataClass.PUBLIC], (
        "Sensibler Text wurde dem Anbieter-Gate als PUBLIC gemeldet"
    )


def test_kontext_faellt_bei_klassifikationsfehler_auf_strengste_klasse(monkeypatch):
    """"Unbekannt" wird nach schlimmstem Fall behandelt, nicht nach bequemstem."""
    def _kaputt(_text):
        raise RuntimeError("Klassifikation nicht verfügbar")

    monkeypatch.setattr(main_module, "classify", _kaputt)
    from apps.backend.governance.data_governance import DataClass

    kontext = _leite_governance_kontext_ab("beliebiger Text")
    assert DataClass.SPECIAL_CATEGORY in kontext.data_classes


def test_orchestrator_bekommt_den_kontext_wirklich(monkeypatch):
    """Verdrahtungsnachweis: ohne diesen Test wäre nur belegt, dass die
    Struktur existiert -- nicht, dass sie beim Gate ankommt."""
    gesehen = {}

    def _fake_generate(messages, context=None, **kw):
        gesehen["context"] = context
        return "Antwort"

    monkeypatch.setattr(main_module._orchestrator, "generate", _fake_generate)
    main_module._ask_llm_directly("Frau Müller hat Diabetes Typ 2.")

    from apps.backend.governance.data_governance import DataClass

    assert gesehen["context"] is not None, (
        "Der Orchestrator erhielt keinen Kontext -- das Capability-Gate prüft "
        "dann mit PUBLIC und redaction_applied=False, also blind"
    )
    assert gesehen["context"].data_classes != [DataClass.PUBLIC]


def test_redaction_status_wird_wahrheitsgemaess_uebergeben(monkeypatch):
    gesehen = {}

    def _fake_generate(messages, context=None, **kw):
        gesehen["context"] = context
        return "Antwort"

    monkeypatch.setattr(main_module._orchestrator, "generate", _fake_generate)
    kontext = _leite_governance_kontext_ab(
        "Frau Müller", tenant_id="t1", redaction_applied=True,
    )
    main_module._ask_llm_directly("Sehr geehrte [NAME_1]", governance_context=kontext)

    assert gesehen["context"].redaction_applied is True
    assert gesehen["context"].tenant_id == "t1"


# ── Audit ohne Rohinhalt ─────────────────────────────────────────────────

def test_audit_enthaelt_keine_nutzdaten(monkeypatch):
    eintraege = []
    monkeypatch.setattr(
        main_module, "write_audit_entry",
        lambda **kw: eintraege.append(kw),
    )
    strom = [{"event": "run_completed", "data": {"message": f"Key: {GEHEIM}"}}]
    list(_gepruefter_ereignisstrom(strom, tenant_id="default"))

    assert eintraege, "Governance-Entscheidung wurde nicht auditiert"
    als_text = json.dumps(eintraege, ensure_ascii=False, default=str)
    assert GEHEIM not in als_text
    assert "run_completed" not in als_text or "message" not in als_text


# ── Tool-Endpunkte: Fremdmaterial ist am schutzbedürftigsten ─────────────

def test_tools_fetch_prueft_abgerufenen_webinhalt(client, monkeypatch):
    """Ein Schlüssel auf einer abgerufenen Seite darf nicht ungeprüft
    zurückkommen -- derselbe Schlüssel im Antworttext würde entfernt."""
    monkeypatch.setattr(
        main_module, "guarded_tool_call",
        lambda tool, params: {
            "status": "completed",
            "result": {"url": "https://example.test", "text": f"Key: {GEHEIM}"},
        },
    )
    resp = client.post("/tools/fetch", json={"url": "https://example.test"})
    assert resp.status_code == 200
    assert GEHEIM not in resp.text


def test_tools_search_prueft_suchtreffer(client, monkeypatch):
    monkeypatch.setattr(
        main_module, "guarded_tool_call",
        lambda tool, params: {
            "status": "completed",
            "result": {"results": [{"title": "Treffer", "snippet": f"Key: {GEHEIM}"}]},
        },
    )
    resp = client.post("/tools/search", json={"query": "beliebige Suche"})
    assert resp.status_code == 200
    assert GEHEIM not in resp.text


def test_gepruefte_antwort_gibt_nie_das_ungepruefte_original_zurueck():
    """Regressionsschutz: bei einer Nutzlast, die kein Dictionary ist, gab ein
    früherer Entwurf das ungeprüfte Original zurück."""
    ergebnis = _gepruefte_antwort([{"feld": f"Key: {GEHEIM}"}], tenant_id="default")
    assert GEHEIM not in json.dumps(ergebnis, ensure_ascii=False)
