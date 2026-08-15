"""Gateway-Approval-Persistenz: Tool-Parameter vor der Speicherung klassifizieren
(Foundation & Knowledge Kernel Phase 1, Freigabe der Betreiberin auf Basis
Commit 63d23f9).

Vorher: `request_approval_if_needed()` speicherte Tool-Parameter roh über
`input_params=parameters` in `approval_requests` -- ein Zugangsschlüssel in
einem Tool-Aufruf landete im Klartext in der Datenbank.

Jetzt: `prepare_for_approval_storage()` (governance/payload_check.py) klassifiziert
die Parameter vor jeder Persistenz:
  * operative Geschäftsdaten und gewöhnliche PII bleiben unverändert
    (kein Platzhaltersystem für Tool-Parameter -- eine Änderung würde
    später eine andere Aktion ausführen als die genehmigte);
  * ein Geheimnis führt zur sofortigen Ablehnung der Freigabeanfrage,
    nicht zur stillen Entfernung (kein Secret-Store im Repository
    vorhanden -- eine Platzhalter-Ausführung wäre ein stiller Fehlschlag
    mit vermeintlichem Erfolg);
  * eine besondere Kategorie (Art. 9/10 DSGVO) wird markiert und
    auditiert, aber nicht blockiert.

Diese Tests decken sowohl die reine Klassifikationsfunktion als auch ihre
Verdrahtung in `gateway/runtime_gateway.py` ab.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest
from fastapi import HTTPException

import apps.backend.gateway.runtime_gateway as rg
from apps.backend.governance.payload_check import prepare_for_approval_storage

GEHEIM = "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
GESUNDHEIT = "Patientin hat Diabetes Typ 2, Termin am 3. Mai."


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


# ── Reine Klassifikationsfunktion ────────────────────────────────────────

def test_operative_geschaeftsdaten_bleiben_unveraendert():
    """1. Normale operative Parameter bleiben nach Approval ausführbar --
    unveränderte Werte, sonst würde execute_approved_tool() später eine
    andere Aktion ausführen als die genehmigte."""
    parameter = {"query": "Rechnung Nr. 4711 an Kunde XY", "limit": 10}
    entscheidung = prepare_for_approval_storage(parameter)
    assert entscheidung.erlaubt is True
    assert entscheidung.parameter == parameter


def test_gewoehnliche_pii_wird_nicht_pauschal_zerstoert():
    """2. Keine Blanket-Redaction -- eine E-Mail-Adresse, die für die
    Ausführung gebraucht wird, bleibt erhalten."""
    parameter = {"to": "kunde@example.com", "subject": "Ihre Bestellung"}
    entscheidung = prepare_for_approval_storage(parameter)
    assert entscheidung.erlaubt is True
    assert entscheidung.parameter["to"] == "kunde@example.com"


def test_secret_wird_nicht_gespeichert():
    """3. Ein Secret erreicht approval_requests.input_params niemals --
    weder im Klartext noch als Platzhalter (das wäre eine stille
    Fehlausführung mit vermeintlichem Erfolg)."""
    entscheidung = prepare_for_approval_storage({"token": f"Bearer {GEHEIM}"})
    assert entscheidung.erlaubt is False
    assert entscheidung.ablehnungsgrund == "secret_detected"
    assert entscheidung.parameter == {}
    assert GEHEIM not in (entscheidung.nutzerhinweis or "")


def test_secret_im_verschachtelten_parameter_wird_erkannt():
    entscheidung = prepare_for_approval_storage(
        {"config": {"auth": {"api_key": GEHEIM}}}
    )
    assert entscheidung.erlaubt is False


def test_secret_als_dict_schluessel_wird_erkannt():
    entscheidung = prepare_for_approval_storage({GEHEIM: "wert"})
    assert entscheidung.erlaubt is False


def test_special_category_wird_markiert_aber_nicht_blockiert():
    """Besondere Kategorien sind nicht generell aus internen
    Geschäftsspeichern verboten -- aber die Persistenz muss kontrolliert,
    also sichtbar/auditiert erfolgen."""
    entscheidung = prepare_for_approval_storage({"notiz": GESUNDHEIT})
    assert entscheidung.erlaubt is True
    assert entscheidung.parameter["notiz"] == GESUNDHEIT
    assert entscheidung.special_category_erkannt is True


def test_normale_parameter_ohne_special_category_flag():
    entscheidung = prepare_for_approval_storage({"query": "Rechnung"})
    assert entscheidung.special_category_erkannt is False


def test_pruefung_faellt_fail_closed_aus(monkeypatch):
    import apps.backend.governance.payload_check as payload_check

    def _kaputt(_text):
        raise RuntimeError("Scanner nicht verfügbar")

    monkeypatch.setattr(payload_check, "strip_secrets_with_placeholder", _kaputt)
    entscheidung = prepare_for_approval_storage({"query": "irgendetwas"})
    assert entscheidung.erlaubt is False
    assert entscheidung.parameter == {}


# ── Verdrahtung in request_approval_if_needed() / guarded_tool_call() ───

def test_request_approval_lehnt_secret_ab_ohne_zu_speichern(monkeypatch):
    """Kernnachweis: kein approval_requests-Datensatz wird angelegt, wenn
    ein Geheimnis erkannt wird."""
    aufgerufen = {"create": False}

    def _fake_create(**kwargs):
        aufgerufen["create"] = True
        return {"id": 1, **kwargs}

    monkeypatch.setattr(rg, "write_audit_entry", lambda **kw: {})
    monkeypatch.setattr(rg, "create_approval_request", _fake_create)

    with pytest.raises(HTTPException) as exc:
        rg.request_approval_if_needed("custom_action", {"api_key": GEHEIM})

    assert exc.value.status_code == 422
    assert GEHEIM not in str(exc.value.detail)
    assert aufgerufen["create"] is False, (
        "Trotz erkanntem Geheimnis wurde ein Approval-Datensatz angelegt"
    )


def test_request_approval_speichert_operative_daten_normal(monkeypatch):
    """Regressionsschutz: die Härtung darf den Normalfall nicht kaputt machen."""
    gespeichert = {}

    def _fake_create(**kwargs):
        gespeichert.update(kwargs)
        return {"id": 7, **kwargs}

    monkeypatch.setattr(rg, "write_audit_entry", lambda **kw: {})
    monkeypatch.setattr(rg, "create_approval_request", _fake_create)

    ergebnis = rg.request_approval_if_needed(
        "custom_action", {"query": "Rechnung Nr. 4711"},
    )
    assert ergebnis["status"] == "pending"
    assert gespeichert["input_params"] == {"query": "Rechnung Nr. 4711"}


def test_audit_bei_ablehnung_enthaelt_kein_secret(monkeypatch):
    """9. Audit enthält keine rohen Tool-Parameter."""
    audit_eintraege = []

    monkeypatch.setattr(
        rg, "write_audit_entry",
        lambda **kw: audit_eintraege.append(kw) or {},
    )
    monkeypatch.setattr(rg, "create_approval_request", lambda **kw: {"id": 1, **kw})

    with pytest.raises(HTTPException):
        rg.request_approval_if_needed("custom_action", {"api_key": GEHEIM})

    als_text = json.dumps(audit_eintraege, ensure_ascii=False, default=str)
    assert GEHEIM not in als_text


def test_audit_markiert_special_category_ohne_inhalt(monkeypatch):
    audit_eintraege = []

    monkeypatch.setattr(
        rg, "write_audit_entry",
        lambda **kw: audit_eintraege.append(kw) or {},
    )
    monkeypatch.setattr(rg, "create_approval_request", lambda **kw: {"id": 1, **kw})

    rg.request_approval_if_needed("custom_action", {"notiz": GESUNDHEIT})

    requested = next(e for e in audit_eintraege if e["action"] == "approval.requested")
    assert requested["metadata"]["special_category_detected"] is True
    assert GESUNDHEIT not in json.dumps(audit_eintraege, ensure_ascii=False)


# ── execute_approved_tool() funktioniert weiterhin ───────────────────────

def test_execute_approved_tool_funktioniert_nach_freigabe(monkeypatch):
    """5. execute_approved_tool() funktioniert nach Freigabe weiterhin --
    für Parameter, die die Speicherprüfung bestanden haben."""
    monkeypatch.setattr(
        rg, "get_approval_request",
        lambda approval_id: {
            "id": approval_id,
            "status": "approved",
            "run_id": None,
            "tool": "custom_action",
            "input_params": {"query": "Rechnung Nr. 4711"},
            "risk_level": "medium",
        },
    )
    monkeypatch.setattr(rg, "write_audit_entry", lambda **kw: {})
    monkeypatch.setattr(rg, "execute_tool", lambda tool, params: {"ok": True})
    monkeypatch.setattr(rg, "check_tool_call", lambda tool, params: type(
        "Decision", (), {"allowed": True, "decision": type("D", (), {"value": "allow"})(), "reason": "", "tool": tool},
    )())

    ergebnis = rg.execute_approved_tool(1)
    assert ergebnis["status"] == "completed"
    assert ergebnis["result"] == {"ok": True}


# ── Tenant-/Owner-Bindung bleibt erhalten (Regressionsschutz) ────────────

def test_tenant_und_owner_bindung_unveraendert(monkeypatch):
    """7./8. Tenant-/Owner-Bindung bleibt erhalten: dieser Fix ändert die
    Tenant-/Owner-Semantik von create_approval_request() nicht -- weder
    zusätzlich einschränkend noch lockernd."""
    gesehen = {}

    def _fake_create(**kwargs):
        gesehen.update(kwargs)
        return {"id": 1, **kwargs}

    monkeypatch.setattr(rg, "write_audit_entry", lambda **kw: {})
    monkeypatch.setattr(rg, "create_approval_request", _fake_create)

    rg.request_approval_if_needed("custom_action", {"query": "Rechnung"})

    assert "tenant_id" not in gesehen, (
        "Diese Änderung fügt keine neue Tenant-Bindung hinzu -- das bleibt "
        "unverändert Aufgabe des Aufrufers/der DB-Funktion (Rest-Risiko, "
        "siehe Abschlussbericht)"
    )
    assert "owner_user_id" not in gesehen


# ── Gegenprobe: alter Zustand ──────────────────────────────────────────
# (dokumentiert als manuell durchgeführte Gegenprobe im Abschlussbericht;
# siehe dortige Beschreibung des Rollback-Tests)


def test_unbekannter_typ_wird_fail_closed_behandelt():
    """Sicherheitsreview-Fund: bytes und andere nicht behandelte Typen
    wurden zuvor stillschweigend als unauffällig durchgereicht."""
    entscheidung = prepare_for_approval_storage({"payload": b"\\x00\\x01raw-bytes"})
    assert entscheidung.erlaubt is False
    assert entscheidung.ablehnungsgrund == "check_failed"
