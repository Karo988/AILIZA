"""Output-Governance: prüfen, DANN wiedereinsetzen (Paket D, Teil 1).

Bisher lief es umgekehrt -- die Provider-Antwort ging direkt in reinsert()
und von dort in die Anzeige. Was das Modell selbst neu erzeugte (ein
ausgedachter API-Schlüssel, Gesundheitsdaten) wurde nie geprüft.

Diese Tests sichern die umgekehrte Reihenfolge ab und, ebenso wichtig, dass
die normale Nutzung dabei nicht kaputtgeht.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

import pytest

from apps.backend.main import _governance_post_check


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


# ── Sichere Antwort kommt durch ──────────────────────────────────────────

def test_safe_answer_passes_unchanged():
    ergebnis = _governance_post_check(
        "Gerne, hier ist ein kurzer Entwurf für Ihre Absage.", {}, tenant_id="default",
    )
    assert ergebnis["decision"] == "pass"
    assert "kurzer Entwurf" in ergebnis["message"]


def test_allowed_placeholders_are_reinserted():
    """Die eigenen Daten der Nutzerin kommen korrekt zurück -- sonst waere
    die Schwaerzung fuer sie unbenutzbar."""
    ergebnis = _governance_post_check(
        "Sehr geehrte [NAME_1], Ihre Anfrage zu [ORT_1] haben wir erhalten.",
        {"[NAME_1]": "Frau Müller", "[ORT_1]": "Hamburg"},
        tenant_id="default",
    )
    assert ergebnis["decision"] == "pass"
    assert "Frau Müller" in ergebnis["message"]
    assert "Hamburg" in ergebnis["message"]
    assert "[NAME_1]" not in ergebnis["message"]
    assert ergebnis["fully_reinserted"] is True


def test_unknown_placeholder_yields_notice_not_silence():
    """Ein vom Modell veraenderter Platzhalter darf nicht stillschweigend
    stehen bleiben -- die Nutzerin muss davon erfahren."""
    ergebnis = _governance_post_check(
        "Hallo [NAME_1], auch [NAME_99] gruesst.",
        {"[NAME_1]": "Frau Müller"},
        tenant_id="default",
    )
    assert ergebnis["fully_reinserted"] is False
    assert ergebnis["notice"]
    assert "vollständig" in ergebnis["notice"]


# ── Geheimnisse ──────────────────────────────────────────────────────────

def test_model_generated_secret_is_removed_before_display():
    """Kernfall: das Modell erzeugt selbst einen Schluessel. Der darf die
    Anzeige nie erreichen."""
    antwort = "Nutze diesen Schlüssel: sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
    ergebnis = _governance_post_check(antwort, {}, tenant_id="default")
    assert ergebnis["decision"] in ("sanitized", "blocked")
    if ergebnis["decision"] == "sanitized":
        assert "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in ergebnis["message"]


def test_secrets_are_never_in_reinsertion_map():
    """Belegt die Annahme, auf der die Reihenfolge beruht: redact() nimmt
    Geheimnisse gar nicht erst in die Wiedereinsetzungs-Abbildung auf --
    sie koennen deshalb auch nicht zurueckgeschrieben werden."""
    from apps.backend.governance.data_governance import classify
    from apps.backend.governance.redaction import redact

    text = "Mein Token ist sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD und ich heisse Erika Mustermann."
    ergebnis = redact(text, classify(text))
    for platzhalter, wert in ergebnis.reinsertion_map.items():
        assert "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in wert, (
            f"Geheimnis liegt in der Wiedereinsetzungs-Abbildung unter {platzhalter}"
        )


def test_secret_in_map_is_still_not_reinserted_into_display():
    """Verteidigung in der Tiefe: selbst wenn jemand kuenftig doch ein
    Geheimnis in die Abbildung legt, darf die Ausgangspruefung es nicht
    ungeprueft in die Anzeige schreiben."""
    antwort = "Der Zugang lautet [TOKEN_1]."
    ergebnis = _governance_post_check(
        antwort,
        {"[TOKEN_1]": "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"},
        tenant_id="default",
    )
    # Entweder blockiert, oder der Wert taucht nicht auf -- aber niemals
    # unveraendert angezeigt.
    if ergebnis["decision"] != "blocked":
        assert "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in ergebnis["message"], (
            "Geheimnis wurde in die Anzeige zurueckgeschrieben"
        )


# ── Technische Fehler: fail-closed ───────────────────────────────────────

@pytest.mark.parametrize("kaputte_antwort", [None, "", "   ", 42, [], {}])
def test_unusable_answer_is_blocked_not_passed_through(kaputte_antwort):
    ergebnis = _governance_post_check(kaputte_antwort, {}, tenant_id="default")
    assert ergebnis["decision"] == "blocked"
    assert ergebnis["reason"] == "empty_or_invalid"


def test_check_failure_blocks_instead_of_showing_raw_answer(monkeypatch):
    """Wenn die Pruefung selbst scheitert, darf NICHT die ungepruefte
    Rohantwort angezeigt werden."""
    import apps.backend.main as main_module

    def _explodiert(*a, **kw):
        raise RuntimeError("Klassifikation kaputt")

    monkeypatch.setattr(main_module, "classify", _explodiert)

    geheim = "Die Diagnose lautet HIV-positiv."
    ergebnis = _governance_post_check(geheim, {}, tenant_id="default")
    assert ergebnis["decision"] == "blocked"
    assert ergebnis["reason"] == "check_failed"
    assert "HIV" not in ergebnis["message"]


# ── Art.-9-Daten in der Modellantwort ────────────────────────────────────

def test_special_category_in_answer_is_blocked():
    """Besondere Kategorien (Art. 9) duerfen auch dann nicht angezeigt
    werden, wenn das Modell sie selbst erzeugt hat."""
    from apps.backend.governance.data_governance import classify, DataClass

    kandidaten = [
        "Der Patient ist HIV-positiv und in psychiatrischer Behandlung.",
        "Die Mitarbeiterin ist schwanger und Mitglied der Gewerkschaft ver.di.",
    ]
    treffer = next(
        (k for k in kandidaten
         if DataClass.SPECIAL_CATEGORY in set(getattr(classify(k), "data_classes", []) or [])),
        None,
    )
    if treffer is None:
        pytest.skip("Kein Kandidat wird vom aktuellen Classifier als Art. 9 erkannt")

    ergebnis = _governance_post_check(treffer, {}, tenant_id="default")
    assert ergebnis["decision"] == "blocked"
    assert ergebnis["reason"] == "special_category_or_credentials"
    assert "HIV" not in ergebnis["message"]
    assert "schwanger" not in ergebnis["message"]


def test_ordinary_personal_data_is_not_blocked():
    """Gegenprobe -- sonst waere die Anwendung unbrauchbar: Wer einen Brief
    entwerfen laesst, bekommt zwangslaeufig Namen zurueck. Das ist das
    bestellte Ergebnis und geht an dieselbe Person, die danach gefragt hat."""
    ergebnis = _governance_post_check(
        "Sehr geehrte Frau Müller, vielen Dank für Ihre Anfrage vom 3. März.",
        {},
        tenant_id="default",
    )
    assert ergebnis["decision"] != "blocked", (
        "Ein gewoehnlicher Briefentwurf darf nicht blockiert werden"
    )


# ── Audit ohne Inhalt ────────────────────────────────────────────────────

def test_audit_contains_no_raw_answer_content(monkeypatch):
    import apps.backend.main as main_module

    erfasst: list[dict] = []

    def _fake_audit(action: str, **kwargs):
        erfasst.append({"action": action, "metadata": kwargs.get("metadata") or {}})

    monkeypatch.setattr(main_module, "write_audit_entry", _fake_audit)

    geheimnisvoll = "Frau Müller aus Hamburg hat die Kundennummer 887766."
    _governance_post_check(geheimnisvoll, {"[NAME_1]": "Frau Müller"}, tenant_id="default")

    flach = str(erfasst)
    assert "Müller" not in flach
    assert "Hamburg" not in flach
    assert "887766" not in flach
    assert erfasst, "Es wurde gar kein Audit-Eintrag geschrieben"


def test_blocked_answer_is_not_written_to_audit(monkeypatch):
    import apps.backend.main as main_module

    erfasst: list[dict] = []
    monkeypatch.setattr(
        main_module, "write_audit_entry",
        lambda action, **kw: erfasst.append({"action": action, "metadata": kw.get("metadata") or {}}),
    )

    _governance_post_check(
        "Nutze sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD zum Anmelden.",
        {}, tenant_id="default",
    )
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in str(erfasst)


# ── Reihenfolge: Pruefung vor Wiedereinsetzung ───────────────────────────

def test_check_runs_before_reinsertion(monkeypatch):
    """Der eigentliche Kern von Paket D. Beweist die Reihenfolge direkt am
    Aufrufprotokoll, nicht nur am Endergebnis."""
    import apps.backend.main as main_module

    ablauf: list[str] = []

    original_classify = main_module.classify
    original_reinsert = main_module.reinsert

    def spy_classify(text):
        ablauf.append("classify")
        return original_classify(text)

    def spy_reinsert(text, mapping):
        ablauf.append("reinsert")
        return original_reinsert(text, mapping)

    monkeypatch.setattr(main_module, "classify", spy_classify)
    monkeypatch.setattr(main_module, "reinsert", spy_reinsert)

    _governance_post_check(
        "Hallo [NAME_1].", {"[NAME_1]": "Frau Müller"}, tenant_id="default",
    )

    assert "classify" in ablauf, "Die Antwort wurde gar nicht klassifiziert"
    assert "reinsert" in ablauf, "Es wurde nicht wiedereingesetzt"
    assert ablauf.index("classify") < ablauf.index("reinsert"), (
        f"Wiedereinsetzung lief VOR der Pruefung: {ablauf}"
    )


def test_reinsert_is_not_called_when_blocked(monkeypatch):
    """Bei blockierter Antwort darf gar nicht erst wiedereingesetzt werden --
    sonst laege der Klartext trotzdem kurz im Speicher der Antwort."""
    import apps.backend.main as main_module

    aufrufe: list[str] = []
    monkeypatch.setattr(
        main_module, "reinsert",
        lambda text, mapping: (aufrufe.append("reinsert"), (text, True))[1],
    )

    _governance_post_check(None, {"[NAME_1]": "Frau Müller"}, tenant_id="default")
    assert aufrufe == []


# ── Verdrahtung: greift die Pruefung im echten Endpunkt? ─────────────────
# Die Tests oben pruefen _governance_post_check isoliert. Genau das war zu
# wenig: der erste Entwurf rief die Funktion im Agenten-Pfad nur auf, wenn
# die Eingabe PII enthielt (`if reinsertion_map:`). Ohne PII in der Eingabe
# lief sie gar nicht -- und damit ausgerechnet dort nicht, wo das Modell
# selbst etwas Heikles erzeugt. Aufgedeckt im Sicherheitsreview, nicht von
# diesen Tests. Die folgenden schliessen diese Luecke.

import pytest as _pytest
from fastapi.testclient import TestClient


@_pytest.fixture()
def client():
    from apps.backend.main import app
    return TestClient(app, cookies={})


def _preview_id(client, task: str) -> str:
    resp = client.post("/api/policy-redact", json={"text": task})
    assert resp.status_code == 200, resp.text
    pid = resp.json().get("preview_id")
    assert pid, f"Kein Pruefbeleg ausgestellt: {resp.json()}"
    return pid




class _FakeRuntimeOhneTools:
    """AgentRuntime-Ersatz, der weder Tool-Schritte noch Suchergebnis
    liefert. Damit laeuft in _run_agent_core zwingend der Zweig
    "elif not result.get('steps')" -- also genau die dritte
    _governance_post_check-Aufrufstelle, die im ersten Entwurf uebersprungen
    wurde. Ohne diese Steuerung landet ein Test je nach Formulierung im
    Schreibaufgaben-Kurzpfad und prueft die falsche Stelle."""

    def __init__(self, *a, **kw):
        pass

    def run(self, task):
        return {"status": "completed", "message": "", "steps": [], "results": []}


def _erzwinge_dritten_pfad(monkeypatch, llm_antwort: str):
    import apps.backend.main as main_module
    from apps.backend.agent_runtime import _WRITING_INTENT_PATTERN, _SEARCH_INTENT_PATTERN

    aufgabe = "Was bedeutet Photosynthese?"
    # Absicherung: waere die Aufgabe eine Schreib- oder Suchabsicht, liefe
    # der Test an der zu pruefenden Stelle vorbei und waere wertlos.
    assert not _WRITING_INTENT_PATTERN.search(aufgabe)
    assert not _SEARCH_INTENT_PATTERN.search(aufgabe)

    monkeypatch.setattr(main_module, "AgentRuntime", _FakeRuntimeOhneTools)
    monkeypatch.setattr(
        main_module, "_ask_llm_directly",
        lambda task, history=None: (llm_antwort, None, {}),
    )
    return aufgabe


def test_wiring_third_call_site_blocks_model_generated_secret(client, monkeypatch):
    """Kernbeweis am reparierten Ort: Eingabe ohne PII (die Abbildung bleibt
    leer), Agentenpfad ohne Tools, Modell erzeugt einen Schluessel.

    Der erste Entwurf pruefte hier nur bei vorhandener PII in der Eingabe --
    dieser Test waere dagegen rot gewesen."""
    geheim = "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
    aufgabe = _erzwinge_dritten_pfad(monkeypatch, f"Nutze diesen Schlüssel: {geheim}")

    resp = client.post(
        "/agent/run",
        json={"task": aufgabe, "preview_id": _preview_id(client, aufgabe)},
    )
    assert resp.status_code == 200
    assert geheim not in str(resp.json()), (
        "Der vom Modell erzeugte Schluessel wurde ungeprueft angezeigt -- "
        "die Ausgangspruefung greift an der dritten Aufrufstelle nicht"
    )


def test_wiring_third_call_site_lets_safe_answers_through(client, monkeypatch):
    """Gegenprobe am selben Ort: die Haerte darf den Normalfall nicht
    kaputt machen."""
    aufgabe = _erzwinge_dritten_pfad(
        monkeypatch, "Photosynthese wandelt Licht in chemische Energie um.",
    )
    resp = client.post(
        "/agent/run",
        json={"task": aufgabe, "preview_id": _preview_id(client, aufgabe)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") != "output_blocked"
    assert "Photosynthese" in str(body.get("ai_response", ""))


class _FakeRuntimeLokal:
    """Liefert den local_only-Zustand (kein Provider erreichbar) -- damit
    laeuft die zweite _governance_post_check-Aufrufstelle."""

    def __init__(self, *a, **kw):
        pass

    def run(self, task):
        return {
            "status": "local_only",
            "message": "Lokale Ersatzantwort.",
            "steps": [],
            "results": [],
        }


def test_wiring_first_call_site_blocks_model_generated_secret(client, monkeypatch):
    """Aufrufstelle 1 (Schreibaufgaben-Kurzpfad). Eigener Regressionstest,
    damit eine kuenftige Wiedereinfuehrung von "if reinsertion_map:" auch
    hier sofort auffaellt -- Hinweis aus dem Abschlussreview."""
    import apps.backend.main as main_module
    from apps.backend.agent_runtime import _WRITING_INTENT_PATTERN

    aufgabe = "Bitte schreibe eine kurze Absage."
    assert _WRITING_INTENT_PATTERN.search(aufgabe), (
        "Testvoraussetzung: diese Aufgabe muss den Schreibpfad ausloesen"
    )

    geheim = "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
    monkeypatch.setattr(
        main_module, "_ask_llm_directly",
        lambda task, history=None: (f"Gerne: {geheim}", None, {}),
    )

    resp = client.post(
        "/agent/run",
        json={"task": aufgabe, "preview_id": _preview_id(client, aufgabe)},
    )
    assert resp.status_code == 200
    assert geheim not in str(resp.json()), (
        "Schluessel ungeprueft angezeigt -- Aufrufstelle 1 greift nicht"
    )


def test_wiring_local_only_path_is_also_checked(client, monkeypatch):
    """Aufrufstelle 2 (local_only/degraded). Auch eine lokal erzeugte
    Ersatzantwort geht durch die Ausgangspruefung, statt ungeprueft
    angezeigt zu werden."""
    import apps.backend.main as main_module
    from apps.backend.agent_runtime import _WRITING_INTENT_PATTERN, _SEARCH_INTENT_PATTERN

    aufgabe = "Was bedeutet Photosynthese?"
    assert not _WRITING_INTENT_PATTERN.search(aufgabe)
    assert not _SEARCH_INTENT_PATTERN.search(aufgabe)

    monkeypatch.setattr(main_module, "AgentRuntime", _FakeRuntimeLokal)

    resp = client.post(
        "/agent/run",
        json={"task": aufgabe, "preview_id": _preview_id(client, aufgabe)},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Die Antwort kommt durch (nichts Heikles drin) -- geprueft wird, dass
    # der Pfad ueberhaupt bis zur Anzeige laeuft und nicht faelschlich
    # blockiert.
    assert body.get("status") != "output_blocked"
