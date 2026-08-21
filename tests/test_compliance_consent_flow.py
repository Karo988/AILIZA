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
# preview_invalid gehoert seit dem verpflichtenden Pruefbeleg-Gate dazu --
# ohne diesen Eintrag wuerde "not in GATE_STATUSES" faelschlich als Erfolg
# durchgehen, obwohl der Versand tatsaechlich am fehlenden Beleg scheiterte.
GATE_STATUSES = {"login_required", "consent_required", "compliance_blocked", "blocked", "preview_invalid"}


def _preview_id(client, task: str, headers: dict) -> str:
    """Einwilligung UND Pruefbeleg sind seit der Nachbesserung beide Pflicht
    fuer den externen Versand (Fall 3) -- eine erteilte Einwilligung allein
    beweist nicht mehr, dass der gesendete Text unveraendert blieb."""
    resp = client.post("/api/policy-redact", json={"text": task}, headers=headers)
    assert resp.status_code == 200, resp.text
    preview_id = resp.json().get("preview_id")
    assert preview_id, f"Kein Pruefbeleg fuer Testtext ausgestellt: {resp.json()}"
    return preview_id

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
    from apps.backend.database import create_user, get_user
    # PR 2 Nachbesserung: eine Genehmigungsentscheidung (auch die eigene
    # compliance_consent) verlangt seit der Haertung IMMER einen aktuellen,
    # aktiven users-Datensatz (kein Token-Rollen-Fallback mehr, Default Deny
    # ohne Datensatz) -- in einer echten Session existiert dieser Datensatz
    # durch die Registrierung, hier muss er fuer den Test explizit angelegt
    # werden.
    if get_user("nutzer1", tenant_id="default") is None:
        create_user("nutzer1", "default", "user", hashed_password="x")
    return {"Authorization": f"Bearer {create_token('nutzer1', 'default', 'user')}"}


# ── Fall 1: harmlos, Gast ─────────────────────────────────────────────────────
def test_fall1_harmless_guest_passes_gates(client):
    resp = client.post(
        "/agent/run",
        json={"task": HARMLOS, "preview_id": _preview_id(client, HARMLOS, {})},
    )
    assert resp.status_code == 200
    assert resp.json().get("status") not in GATE_STATUSES


# ── Fall 2: Art.-9-Daten → echte Pause vor jedem Versand ─────────────────────
def test_fall2_art9_guest_goes_to_handoff(client):
    resp = client.post("/agent/run", json={"task": BRIEF_PII})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "responsibility_handoff"
    assert body["login_required"] is True
    assert body["activation_allowed"] is False
    # Keine PII in der Antwort
    assert "Paula Ronder" not in str(body)
    assert "DE89370400440532013000" not in str(body)


def test_fall2_art9_logged_in_stays_paused_without_confirmations(client):
    headers = _auth()
    resp = client.post(
        "/agent/run",
        json={"task": BRIEF_PII, "preview_id": _preview_id(client, BRIEF_PII, headers)},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "responsibility_handoff"
    assert body["login_required"] is False
    assert body["activation_allowed"] is False
    assert isinstance(body.get("approval_id"), int)


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
        json={
            "task": NONKONFORM,
            "consent_approval_id": approval_id,
            "preview_id": _preview_id(client, NONKONFORM, headers),
        },
        headers=headers,
    )
    assert resp.status_code == 200
    status = resp.json().get("status")
    assert status not in GATE_STATUSES, (
        f"Erwartet: durchgekommen (Einwilligung + Beleg gueltig), tatsaechlich: {status!r}"
    )


def test_fall3_consent_without_preview_id_still_rejected(client):
    """Regressionsschutz fuer die Nachbesserung: eine erteilte Einwilligung
    allein darf NICHT mehr genuegen -- ohne Pruefbeleg muss der Versand
    trotz gueltiger consent_approval_id abgelehnt werden."""
    headers = _auth()
    body = client.post("/agent/run", json={"task": NONKONFORM}, headers=headers).json()
    approval_id = body["approval_id"]
    client.post(f"/approvals/{approval_id}/approve", headers=headers)

    resp = client.post(
        "/agent/run",
        json={"task": NONKONFORM, "consent_approval_id": approval_id},
        headers=headers,
    )
    assert resp.json()["status"] == "preview_invalid"


def test_fall3_missing_preview_id_does_not_burn_the_consent(client):
    """Sicherheitsreview-Fund: preview_id fehlt -> die Einwilligung darf NICHT
    bereits verbraucht werden (sonst gaebe es eine dokumentierte Zustimmung
    ohne jeden Versand). Die Einwilligung muss danach noch gueltig sein und
    mit einem Beleg tatsaechlich durchgehen."""
    headers = _auth()
    body = client.post("/agent/run", json={"task": NONKONFORM}, headers=headers).json()
    approval_id = body["approval_id"]
    client.post(f"/approvals/{approval_id}/approve", headers=headers)

    # Erster Versuch ohne Beleg -- muss abgelehnt werden, OHNE die Einwilligung
    # zu verbrauchen.
    first = client.post(
        "/agent/run",
        json={"task": NONKONFORM, "consent_approval_id": approval_id},
        headers=headers,
    )
    assert first.json()["status"] == "preview_invalid"

    # Zweiter Versuch, jetzt MIT Beleg, DERSELBEN approval_id -- muss noch
    # funktionieren. Wuerde der erste Versuch die Einwilligung bereits
    # verbraucht haben, schluege dieser hier fehl.
    second = client.post(
        "/agent/run",
        json={
            "task": NONKONFORM,
            "consent_approval_id": approval_id,
            "preview_id": _preview_id(client, NONKONFORM, headers),
        },
        headers=headers,
    )
    assert second.json().get("status") not in GATE_STATUSES, (
        f"Einwilligung wurde vermutlich beim ersten (fehlgeschlagenen) Versuch "
        f"verbraucht: {second.json()}"
    )


def test_fall3_consent_bound_to_exact_task(client):
    """Eine erteilte Einwilligung gilt NUR fuer genau diese Anfrage (task_sha256)."""
    headers = _auth()
    body = client.post("/agent/run", json={"task": NONKONFORM}, headers=headers).json()
    approval_id = body["approval_id"]
    client.post(f"/approvals/{approval_id}/approve", headers=headers)

    resp = client.post(
        "/agent/run",
        json={
            "task": NONKONFORM + " Und noch etwas anderes.",
            "consent_approval_id": approval_id,
            "preview_id": _preview_id(client, NONKONFORM + " Und noch etwas anderes.", headers),
        },
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
        json={
            "task": NONKONFORM,
            "consent_approval_id": approval_id,
            "preview_id": _preview_id(client, NONKONFORM, headers),
        },
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


# ── Sicherheitsnetz: sensible Fachbegriffe (HIV, Religion, ...) verlassen
#    das System nie im Klartext, auch bei gezielter (nicht Voll-)Schwaerzung ─
def test_unredactable_health_data_is_paused_before_redaction_or_send():
    """
    Regressionsschutz fuer B2a: Der Fachbegriff selbst (hier "HIV-Infektion")
    muss immer geschwaerzt werden.

    BEKANNTE GRENZE (dokumentiert, kein falscher Sicherheitsanspruch): Ein
    Name OHNE jedes Einleitungswort ("Paula Ronder leidet an...") wird aktuell
    NICHT erkannt — weder von classify() noch von der Redaction-Engine, die
    beide auf Kontextmuster wie "mein Name ist X", "Frau X" oder eine
    Gruss-Signatur angewiesen sind. Im echten Testbrief (Anrede + "mein Name
    ist" + Signatur) greifen diese Muster und der Name wird zuverlaessig
    entfernt (siehe test_fall2_pii_guest_gets_login_required). Diese
    Restluecke (kontextlose Nameneinbettung) ist ein bekannter Punkt fuer den
    naechsten Haertungsschritt, kein stillschweigend akzeptiertes Risiko.
    """
    from apps.backend.main import _governance_pre_check
    result = _governance_pre_check(
        "Fasse zusammen: Paula Ronder leidet an einer HIV-Infektion.",
        tenant_id="default",
    )
    assert result["decision"] == "responsibility_handoff"
    assert result["activation_allowed"] is False
    assert "task" not in result
    assert "HIV" not in str(result)


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
    task = "Fasse diesen Text bitte zusammen: Der Himmel ist blau und die Sonne scheint."
    resp = client.post(
        "/agent/run",
        json={"task": task, "preview_id": _preview_id(client, task, {})},
    )
    assert resp.status_code == 200
    assert resp.json().get("status") not in GATE_STATUSES


# ── "geboren am X" ist die haeufigste Alltagsformulierung (nicht nur
#    "Geburtsdatum:") — wurde vorher NICHT erkannt (Karo-Fund 2026-07-11) ────
def test_geboren_am_birthdate_redacted():
    from apps.backend.governance.redaction_v2 import RedactionEngineV2
    r = RedactionEngineV2().redact("Herr Mustermann, geboren am 03.04.1985, meldet sich.")
    assert "03.04.1985" not in r.redacted_text
    assert "[Geburtsdatum]" in r.redacted_text
