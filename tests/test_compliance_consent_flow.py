"""
B2 (Betreiber-Freigabe 2026-07-11): Drei-Stufen-Modell statt Hartblock.

  Fall 1: keine sensiblen Daten        → direkt senden, kein Login noetig.
  Fall 2: Schwaerzung loest das Problem → Login noetig (Dokumentationspflicht).
  Fall 3: auch nach Schwaerzung nicht
          DSGVO-/EU-AI-Act-konform      → Login + explizite Einwilligung,
                                          Einwilligung wird dokumentiert und
                                          ist per task_sha256 an genau eine
                                          Anfrage gebunden.

B8b (Beta-Einschraenkung Bewerbung/Scoring) bleibt harte Sperre.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest

# Statusse, die eine Antwort VERHINDERN (Gates). Alles andere bedeutet:
# die Anfrage ist durch die Gates gekommen (LLM-Fehler in der Testumgebung
# wie "failed"/"local_only" zaehlen als durchgekommen).
GATE_STATUSES = {"login_required", "consent_required", "compliance_blocked", "blocked"}

BRIEF_PII = (
    "Bitte fasse diesen Brief zusammen: Mein Name ist Paula Ronder, ich leide "
    "an einer HIV-Infektion, bin Mitglied der Gewerkschaft ver.di, Religion "
    "roemisch-katholisch, IBAN DE89370400440532013000."
)

NONKONFORM = (
    "Formuliere eine Antwort an den Kunden: Wir gehen davon aus, dass Ihr "
    "Einverstaendnis vorliegt, und verarbeiten Ihre Daten ohne Einwilligung weiter."
)

HARMLOS = "Schreibe einen kurzen freundlichen Gruss."


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app, cookies={})


def _auth():
    from apps.backend.auth.jwt_handler import create_token
    return {"Authorization": f"Bearer {create_token('nutzer1', 'default', 'user')}"}


# ── Fall 1: harmlos, Gast ─────────────────────────────────────────────────────
def test_fall1_harmless_guest_passes_gates(client):
    resp = client.post("/agent/run", json={"task": HARMLOS})
    assert resp.status_code == 200
    assert resp.json().get("status") not in GATE_STATUSES


# ── Fall 2: PII → Login-Gate (Dokumentationspflicht) ─────────────────────────
def test_fall2_pii_guest_gets_login_required(client):
    resp = client.post("/agent/run", json={"task": BRIEF_PII})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "login_required"
    assert body["login_reason"] == "documentation"
    # Keine PII in der Antwort
    assert "Paula Ronder" not in str(body)
    assert "DE89370400440532013000" not in str(body)


def test_fall2_pii_logged_in_passes_gates(client):
    resp = client.post("/agent/run", json={"task": BRIEF_PII}, headers=_auth())
    assert resp.status_code == 200
    assert resp.json().get("status") not in GATE_STATUSES


# ── Fall 3: auch nach Schwaerzung nicht konform → Einwilligung ────────────────
def test_fall3_guest_gets_login_required_consent(client):
    resp = client.post("/agent/run", json={"task": NONKONFORM})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "login_required"
    assert body["login_reason"] == "consent"


def test_fall3_logged_in_gets_consent_required(client):
    resp = client.post("/agent/run", json={"task": NONKONFORM}, headers=_auth())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "consent_required"
    assert isinstance(body.get("approval_id"), int)
    assert "trotzdem senden" in body["message"].lower()


def test_fall3_consent_flow_completes(client):
    headers = _auth()
    body = client.post("/agent/run", json={"task": NONKONFORM}, headers=headers).json()
    approval_id = body["approval_id"]

    ok = client.post(f"/approvals/{approval_id}/approve", headers=headers)
    assert ok.status_code == 200

    resp = client.post(
        "/agent/run",
        json={"task": NONKONFORM, "consent_approval_id": approval_id},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json().get("status") not in GATE_STATUSES


def test_fall3_consent_bound_to_exact_task(client):
    """Eine erteilte Einwilligung gilt NUR fuer genau diese Anfrage (task_sha256)."""
    headers = _auth()
    body = client.post("/agent/run", json={"task": NONKONFORM}, headers=headers).json()
    approval_id = body["approval_id"]
    client.post(f"/approvals/{approval_id}/approve", headers=headers)

    resp = client.post(
        "/agent/run",
        json={"task": NONKONFORM + " Und noch etwas anderes.", "consent_approval_id": approval_id},
        headers=headers,
    )
    assert resp.json()["status"] == "consent_required"


def test_fall3_unapproved_consent_id_not_accepted(client):
    """Eine NICHT bestaetigte (pending) Freigabe-ID darf nicht durchlassen."""
    headers = _auth()
    body = client.post("/agent/run", json={"task": NONKONFORM}, headers=headers).json()
    approval_id = body["approval_id"]
    # KEIN approve — direkt versuchen
    resp = client.post(
        "/agent/run",
        json={"task": NONKONFORM, "consent_approval_id": approval_id},
        headers=headers,
    )
    assert resp.json()["status"] == "consent_required"


# ── B8b: Beta-Hochrisiko-Sperre bleibt hart ──────────────────────────────────
def test_beta_highrisk_block_still_hard(client, monkeypatch):
    monkeypatch.setenv("AILIZA_BETA_HIGHRISK_BLOCK", "true")
    resp = client.post(
        "/agent/run",
        json={"task": "Bewerte diesen Bewerber und triff eine Personalentscheidung."},
        headers=_auth(),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "compliance_blocked"


# ── Sicherheitsnetz: Klassifikator erkennt Art.-9-Daten, Engine schwaerzt
#    nicht → Voll-Schwaerzung, Rohdaten verlassen das System NIE ─────────────
def test_unredactable_health_data_never_leaves_in_clear():
    """
    Regressionsschutz fuer B2a-Korrektur: 'X leidet an einer HIV-Infektion'
    wird von classify() als special_category erkannt, von der Redaction-Engine
    aber nicht geschwaerzt. Das Sicherheitsnetz muss den gesamten Inhalt
    ersetzen — auch im Einwilligungs-Fall darf kein Klartext rausgehen.
    """
    from apps.backend.main import _governance_pre_check
    result = _governance_pre_check(
        "Fasse zusammen: Paula Ronder leidet an einer HIV-Infektion.",
        tenant_id="default",
    )
    assert result["decision"] != "block"
    task_out = result["task"]
    assert "HIV" not in task_out
    assert "Paula" not in task_out
    assert "GESCHWAERZT" in task_out


# ── Art.-44-48-Regel: "USA" ohne Wortgrenzen traf "zusammen" ─────────────────
def test_zusammenfassen_not_flagged_as_third_country_transfer():
    from apps.backend.compliance_auditor import evaluate_compliance
    report = evaluate_compliance("Fasse diesen Text bitte zusammen: Der Himmel ist blau.")
    articles = [v.article for v in report.violations]
    assert "Art. 44-48" not in articles


def test_real_usa_transfer_still_flagged():
    from apps.backend.compliance_auditor import evaluate_compliance
    report = evaluate_compliance(
        "Wir übermitteln die Kundendaten an unseren Dienstleister in den USA."
    )
    articles = [v.article for v in report.violations]
    assert "Art. 44-48" in articles


def test_fall1_summarize_request_guest_passes_gates(client):
    """Der haeufigste Anwendungsfall (harmlose Zusammenfassung) bleibt frei."""
    resp = client.post(
        "/agent/run",
        json={"task": "Fasse diesen Text bitte zusammen: Der Himmel ist blau und die Sonne scheint."},
    )
    assert resp.status_code == 200
    assert resp.json().get("status") not in GATE_STATUSES
