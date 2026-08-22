"""Fünf Lücken aus dem Review der Betreiberin zu Commit 46aaf5b.

Jede davon war ein realer Weg, auf dem Inhalte an einem Kontrollpunkt
vorbeikamen. Die Tests halten die Korrekturen fest; jeder einzelne wurde
gegen den alten Zustand geprüft und wird dort rot.

  1. Such-Zusammenfassung ohne Governance-Kontext -> Anbieter-Gate blind
  2. Gesprächsverlauf ungeprüft an den Anbieter
  3. Dictionary-Schlüssel wurden nicht geprüft
  4. Rohdaten landeten vor der Governance in der Datenbank
  5. Freigabe-Fortsetzung ohne Bindung an Mandant und Eigentümerin
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest
from fastapi.testclient import TestClient

import apps.backend.agent_runtime as runtime_module
import apps.backend.main as main_module
from apps.backend.governance.payload_check import (
    pruefe_nutzlast,
    sichere_fassung_fuer_speicherung,
)

GEHEIM = "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
GESUNDHEIT = "Frau Müller wurde mit Diabetes Typ 2 diagnostiziert."


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


# ── 1. Such-Zusammenfassung bewertet den GESAMTEN Versandinhalt ──────────

def test_suchzusammenfassung_uebergibt_governance_kontext(client, monkeypatch):
    """Der Suchtext geht dem Anbieter mit -- also muss er die Anbieterwahl
    mitbestimmen. Ohne Kontext nahm der Orchestrator PUBLIC an."""
    gesehen = {}

    def _fake_generate(messages, context=None, **kw):
        gesehen["context"] = context
        return "Zusammenfassung."

    monkeypatch.setattr(main_module._orchestrator, "generate", _fake_generate)
    antwort, fehler = main_module._summarize_with_llm(
        "Was steht dazu im Netz?",
        GESUNDHEIT,
        context=main_module._leite_governance_kontext_ab(
            f"Was steht dazu im Netz?\n\n{GESUNDHEIT}",
        ),
    )
    assert antwort is not None
    assert gesehen["context"] is not None, (
        "Ohne Kontext prüft das Capability-Gate mit PUBLIC -- also blind"
    )


def test_suchzusammenfassung_kontext_beruecksichtigt_den_suchtext():
    """Kernpunkt: die Einstufung darf nicht nur aus der harmlosen Frage
    stammen, wenn die sensiblen Daten ausschliesslich im Suchergebnis stehen."""
    from apps.backend.governance.data_governance import DataClass

    nur_frage = main_module._leite_governance_kontext_ab("Was steht dazu im Netz?")
    mit_suchtext = main_module._leite_governance_kontext_ab(
        f"Was steht dazu im Netz?\n\n{GESUNDHEIT}",
    )
    assert nur_frage.data_classes == [DataClass.PUBLIC]
    assert mit_suchtext.data_classes != [DataClass.PUBLIC], (
        "Sensible Daten aus dem Suchergebnis blieben für die Anbieterwahl unsichtbar"
    )


def test_suchpfad_ruft_summarize_mit_kontext_auf(client, monkeypatch):
    """Verdrahtungsnachweis an der echten Route."""
    gesehen = {}

    def _fake_summarize(task, search_text, context=None):
        gesehen["context"] = context
        return "Zusammenfassung.", None

    class _RuntimeMitTreffer:
        def __init__(self, *a, **kw):
            pass

        def run(self, task):
            return {
                "status": "completed",
                "message": "",
                "steps": [{"step": 1, "tool": "search", "status": "completed"}],
                "results": [{"tool": "search", "result": {"text": "Treffer"}}],
            }

    monkeypatch.setattr(main_module, "AgentRuntime", _RuntimeMitTreffer)
    monkeypatch.setattr(main_module, "extract_agent_answer", lambda r: "Gefundener Text")
    monkeypatch.setattr(main_module, "_summarize_with_llm", _fake_summarize)

    aufgabe = "Suche Informationen zur Photosynthese"
    resp = client.post(
        "/agent/run",
        json={"task": aufgabe, "preview_id": _preview_id(client, aufgabe)},
    )
    assert resp.status_code == 200
    assert gesehen.get("context") is not None, (
        "Der Suchpfad rief die Zusammenfassung ohne Governance-Kontext auf"
    )


# ── 2. Gesprächsverlauf ──────────────────────────────────────────────────

def test_verlauf_wird_vor_dem_senden_geschwaerzt(monkeypatch):
    """Eine harmlose aktuelle Aufgabe darf keinen sensiblen Verlauf
    ungeprüft mit hinaustragen."""
    gesehen = {}

    def _fake_generate(messages, context=None, **kw):
        gesehen["messages"] = messages
        gesehen["ingress"] = kw.get("ingress_source")
        return "Antwort"

    monkeypatch.setattr(main_module._orchestrator, "generate", _fake_generate)
    main_module._ask_llm_directly(
        "Schreibe das freundlicher.",
        history=[{"role": "user", "content": GESUNDHEIT}],
    )
    versendet = json.dumps(gesehen["messages"], ensure_ascii=False)
    assert "Müller" not in versendet, (
        "Der Name aus dem Gesprächsverlauf ging ungeschwärzt an den Anbieter"
    )


def test_geheimnis_im_verlauf_erreicht_den_anbieter_nicht(monkeypatch):
    gesehen = {}

    def _fake_generate(messages, context=None, **kw):
        gesehen["messages"] = messages
        return "Antwort"

    monkeypatch.setattr(main_module._orchestrator, "generate", _fake_generate)
    main_module._ask_llm_directly(
        "Fasse das zusammen.",
        history=[{"role": "user", "content": f"Mein Schlüssel ist {GEHEIM}"}],
    )
    assert GEHEIM not in json.dumps(gesehen["messages"], ensure_ascii=False)


def test_verlauf_zaehlt_fuer_die_anbieterwahl(client, monkeypatch):
    """Art.-9-Daten im Verlauf muessen vor der Anbieterwahl pausieren."""
    gesehen = {}

    def _fake_ask(task, history=None, governance_context=None, **kw):
        gesehen["context"] = governance_context
        return "Antwort", None, []

    monkeypatch.setattr(main_module, "_ask_llm_directly", _fake_ask)
    aufgabe = "Bitte schreibe das freundlicher."
    resp = client.post(
        "/agent/run",
        json={
            "task": aufgabe,
            "preview_id": _preview_id(client, aufgabe),
            "history": [{"role": "user", "content": GESUNDHEIT}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "responsibility_handoff"
    assert body["activation_allowed"] is False
    assert gesehen == {}, "Providerpfad wurde trotz Art.-9-Daten im Verlauf erreicht"


def test_unbewertbare_verlaufsnachricht_wird_ausgelassen(monkeypatch):
    """Fail-closed: lieber ohne die Nachricht senden als ungeprüft."""
    import apps.backend.governance.payload_check as payload_check

    gesehen = {}

    def _fake_generate(messages, context=None, **kw):
        gesehen["messages"] = messages
        return "Antwort"

    def _kaputt(_text):
        raise RuntimeError("Scanner nicht verfügbar")

    monkeypatch.setattr(main_module._orchestrator, "generate", _fake_generate)
    monkeypatch.setattr(main_module, "strip_secrets_with_placeholder", _kaputt)
    main_module._ask_llm_directly(
        "Fasse zusammen.", history=[{"role": "user", "content": "Irgendein Verlauf"}],
    )
    assert "Irgendein Verlauf" not in json.dumps(gesehen["messages"], ensure_ascii=False)


# ── 3. Dictionary-Schlüssel ──────────────────────────────────────────────

def test_geheimnis_im_schluessel_wird_zurueckgehalten():
    ergebnis = pruefe_nutzlast({f"{GEHEIM}": "gefunden", "titel": "Bericht"})
    assert GEHEIM not in json.dumps(ergebnis, ensure_ascii=False)
    assert ergebnis["titel"] == "Bericht", "Der unbedenkliche Teil ging verloren"


def test_schluessel_wird_nicht_umbenannt_sondern_paar_entfaellt():
    """Ein umbenannter Schlüssel verändert die Bedeutung der Struktur still."""
    ergebnis = pruefe_nutzlast({f"{GEHEIM}": "gefunden"})
    assert ergebnis == {}


def test_problematischer_schluessel_in_verschachtelter_struktur():
    ergebnis = pruefe_nutzlast(
        {"aussen": {"innen": [{f"Bearer {'A' * 30}": "wert", "ok": 1}]}},
    )
    als_text = json.dumps(ergebnis, ensure_ascii=False)
    assert "Bearer" not in als_text
    assert '"ok": 1' in als_text


def test_streaming_ereignis_mit_geheimnis_im_schluessel():
    strom = [{"event": "tool_completed", "data": {"result": {GEHEIM: "gefunden"}}}]
    ausgabe = list(main_module._gepruefter_ereignisstrom(strom, tenant_id="default"))
    assert GEHEIM not in json.dumps(ausgabe, ensure_ascii=False)


def test_nicht_text_schluessel_bleiben_erhalten():
    ergebnis = pruefe_nutzlast({1: "eins", 2: "zwei"})
    assert ergebnis == {1: "eins", 2: "zwei"}


# ── 4. Nichts Ungeprüftes in die Datenbank ───────────────────────────────

def test_laufdatensatz_speichert_keine_rohen_zugangsdaten():
    """Speichern ist Verarbeitung: der Datensatz entstand bisher VOR dem
    Precheck und trug den Rohtext."""
    from apps.backend.database import get_agent_run

    laufzeit = runtime_module.AgentRuntime(tenant_id="default")
    laufzeit.create_run_record("run-test-1", f"Mein Schlüssel ist {GEHEIM}")
    gespeichert = get_agent_run("run-test-1")
    assert gespeichert is not None
    assert GEHEIM not in json.dumps(dict(gespeichert), ensure_ascii=False, default=str)


def test_ergebnis_wird_vor_dem_speichern_geprueft():
    from apps.backend.database import get_agent_run

    laufzeit = runtime_module.AgentRuntime(tenant_id="default")
    laufzeit.create_run_record("run-test-2", "harmlose Aufgabe")
    laufzeit.update_run_record(
        "run-test-2",
        status="completed",
        result={"results": [{"result": {"body": f"Key: {GEHEIM}"}}]},
    )
    gespeichert = get_agent_run("run-test-2")
    assert GEHEIM not in json.dumps(dict(gespeichert), ensure_ascii=False, default=str)


def test_speicherfassung_faellt_fail_closed_aus(monkeypatch):
    import apps.backend.governance.payload_check as payload_check

    def _kaputt(_text):
        raise RuntimeError("Scanner nicht verfügbar")

    monkeypatch.setattr(payload_check, "strip_secrets_with_placeholder", _kaputt)
    ergebnis = sichere_fassung_fuer_speicherung({"feld": "irgendetwas"})
    assert "irgendetwas" not in json.dumps(ergebnis, ensure_ascii=False)


# ── 5. Freigabe-Fortsetzung an Mandant und Eigentümerin gebunden ─────────

def _freigabe_anlegen(tenant_id: str, owner_user_id: str | None) -> int:
    from apps.backend.database import create_approval_request

    freigabe = create_approval_request(
        tool="search",
        input_params={"query": "beliebig"},
        risk_level="low",
        risk_reason="Test",
        tenant_id=tenant_id,
        owner_user_id=owner_user_id,
    )
    return freigabe["id"]


def test_fremder_mandant_kann_freigabe_nicht_fortsetzen(client, monkeypatch):
    """Kernnachweis: bisher genügte die Kenntnis der Nummer."""
    freigabe_id = _freigabe_anlegen("fremder-mandant", None)
    aufgerufen = {"ja": False}

    class _NieAufrufen:
        def __init__(self, *a, **kw):
            pass

        def continue_after_approval(self, approval_id):
            aufgerufen["ja"] = True
            return {"status": "completed", "message": "geheimes Ergebnis"}

    monkeypatch.setattr(main_module, "AgentRuntime", _NieAufrufen)
    resp = client.post(f"/agent/approvals/{freigabe_id}/continue")
    assert resp.status_code == 404
    assert not aufgerufen["ja"], "Ein fremder Vorgang wurde tatsächlich fortgesetzt"


def test_fremde_nutzerin_kann_freigabe_nicht_fortsetzen(client, monkeypatch):
    freigabe_id = _freigabe_anlegen("default", "nutzerin-a")
    aufgerufen = {"ja": False}

    class _NieAufrufen:
        def __init__(self, *a, **kw):
            pass

        def continue_after_approval(self, approval_id):
            aufgerufen["ja"] = True
            return {"status": "completed", "message": "geheimes Ergebnis"}

    monkeypatch.setattr(main_module, "AgentRuntime", _NieAufrufen)
    # Ohne Anmeldung: token ist None, die Freigabe gehört aber nutzerin-a
    resp = client.post(f"/agent/approvals/{freigabe_id}/continue")
    assert resp.status_code == 404
    assert not aufgerufen["ja"]


def test_streaming_fortsetzung_ist_ebenso_gebunden(client, monkeypatch):
    freigabe_id = _freigabe_anlegen("fremder-mandant", None)

    class _NieAufrufen:
        def __init__(self, *a, **kw):
            pass

        def stream_after_approval(self, approval_id):
            yield {"event": "run_completed", "data": {"message": "geheim"}}

    monkeypatch.setattr(main_module, "AgentRuntime", _NieAufrufen)
    for pfad in ("get", "post"):
        aufruf = getattr(client, pfad)
        resp = aufruf(f"/agent/approvals/{freigabe_id}/continue/stream")
        assert resp.status_code == 404, f"{pfad.upper()} war ungebunden"


def test_unbekannte_freigabe_gibt_dieselbe_antwort_wie_eine_fremde(client):
    """Sonst verrät der Unterschied, welche Nummern existieren."""
    fremd_id = _freigabe_anlegen("fremder-mandant", None)
    unbekannt = client.post("/agent/approvals/999999/continue")
    fremd = client.post(f"/agent/approvals/{fremd_id}/continue")
    assert unbekannt.status_code == fremd.status_code == 404
    assert unbekannt.json() == fremd.json()


def test_eigene_freigabe_bleibt_nutzbar(client, monkeypatch):
    """Die Härtung darf den Normalfall nicht kaputt machen."""
    freigabe_id = _freigabe_anlegen("default", None)

    class _Runtime:
        def __init__(self, *a, **kw):
            pass

        def continue_after_approval(self, approval_id):
            return {"status": "completed", "message": "Fertig."}

    monkeypatch.setattr(main_module, "AgentRuntime", _Runtime)
    resp = client.post(f"/agent/approvals/{freigabe_id}/continue")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Fertig."


# ── Nachbesserung aus dem zweiten Sicherheitsreview ──────────────────────

def test_geheimnis_in_tupel_schluessel_wird_zurueckgehalten():
    """Ein Tupel-Schlüssel kann selbst Zeichenketten enthalten -- die erste
    Fassung behandelte jeden Nicht-str-Schlüssel pauschal als unbedenklich."""
    ergebnis = pruefe_nutzlast({(GEHEIM,): "gefunden"})
    assert GEHEIM not in json.dumps(ergebnis, ensure_ascii=False)


def test_zeitkanal_existiert_vs_gehoert_anderem(client, monkeypatch):
    """Beide Ablehnungsfälle müssen denselben Audit-Schreibzugriff auslösen,
    sonst verrät die Antwortzeit, ob eine Nummer überhaupt vergeben ist."""
    schreibvorgaenge = []
    original = main_module.write_audit_entry

    def _zaehlend(**kw):
        if kw.get("action") == "approval.access_denied":
            schreibvorgaenge.append(kw.get("metadata", {}).get("reason"))
        return original(**kw)

    monkeypatch.setattr(main_module, "write_audit_entry", _zaehlend)

    fremd_id = _freigabe_anlegen("fremder-mandant", None)
    client.post(f"/agent/approvals/{fremd_id}/continue")
    client.post("/agent/approvals/999999/continue")

    assert schreibvorgaenge == ["tenant_mismatch", "not_found"], (
        f"Nicht symmetrisch: {schreibvorgaenge}"
    )


def test_geheimnis_in_frozenset_schluessel_wird_zurueckgehalten():
    """Dieselbe Lücke wie bei Tupel-Schlüsseln, für frozenset."""
    ergebnis = pruefe_nutzlast({frozenset({GEHEIM}): "gefunden"})
    assert GEHEIM not in json.dumps(ergebnis, ensure_ascii=False)
