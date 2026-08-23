"""Sicherheitstests zu B3 und B4 (Modell-Router, PR #86).

Ausgangslage vor dieser Korrektur -- beide Umgehungen sind hier
reproduziert und werden jetzt abgewiesen:

B4  approve_model_candidate() akzeptierte einen FREI UEBERGEBENEN
    Rollen-String (`reviewer_role="admin"`). Er war durch keine Sitzung
    gedeckt; jeder Aufrufer konnte ihn setzen und ein Modell freigeben.
    approved_by war ebenfalls frei waehlbar -- eine Freigabe im fremden
    Namen war moeglich.

B3  recommend_model() erhielt die Datenklassen als OPTIONALE Liste
    (`data_classes=None`). Weglassen hob die Sperre vollstaendig auf; eine
    beliebige Liste konnte zudem eine harmlose Klassifikation vortaeuschen.

Kein Test hier prueft nur eine Signatur -- jeder fuehrt den frueher
erfolgreichen Missbrauch aus und erwartet die Abweisung.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

TENANT = "default"


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _actor(user_id="pruefer", tenant_id=TENANT, role="manager"):
    from apps.backend.auth.jwt_handler import TokenData
    return TokenData(user_id=user_id, tenant_id=tenant_id, role=role)


def _klass(*klassen):
    from apps.backend.governance.data_governance import ClassificationResult, DataClass
    return ClassificationResult(
        data_classes=[DataClass(k) for k in klassen] or [DataClass.PUBLIC]
    )


def _kandidat(name="m1", created_by="einbringer"):
    from apps.backend.database import create_model_candidate
    return create_model_candidate(
        "groq", name, modalities=["text"], capabilities=[], context_window=1000,
        created_by=created_by,
    )


def _freigeben(name="m1", actor=None, privacy=1.0):
    from apps.backend.database import approve_model_candidate
    return approve_model_candidate(
        "groq", name, actor=actor or _actor(),
        quality_score=1.0, latency_score=1.0, cost_score=1.0, privacy_score=privacy,
        benchmark_version="v1",
    )


# ── B4: Freigabe nur mit authentifiziertem Actor ──────────────────────────

def test_free_role_string_is_no_longer_accepted():
    """Der frueher genuegende Weg (`reviewer_role="admin"`) existiert nicht
    mehr -- die Funktion nimmt ihn nicht einmal entgegen."""
    from apps.backend.database import approve_model_candidate

    _kandidat()
    with pytest.raises(TypeError):
        approve_model_candidate(
            "groq", "m1", approved_by="hacker", reviewer_role="admin",
            quality_score=1.0, latency_score=1.0, cost_score=1.0, privacy_score=1.0,
            benchmark_version="v1",
        )


def test_missing_actor_is_denied():
    from apps.backend.database import approve_model_candidate, ModelApprovalDenied

    _kandidat()
    with pytest.raises(ModelApprovalDenied):
        approve_model_candidate(
            "groq", "m1", actor=None,
            quality_score=1.0, latency_score=1.0, cost_score=1.0, privacy_score=1.0,
            benchmark_version="v1",
        )


@pytest.mark.parametrize("rolle", ["user", "audit_viewer", "dsb", "phantasierolle", ""])
def test_insufficient_or_unknown_role_is_denied(rolle):
    """audit_viewer und dsb haben ausdruecklich keine Schreibrechte,
    unbekannte Rollen fallen auf Default Deny."""
    from apps.backend.database import ModelApprovalDenied

    _kandidat()
    with pytest.raises(ModelApprovalDenied):
        _freigeben(actor=_actor(role=rolle))


@pytest.mark.parametrize("rolle", ["manager", "admin"])
def test_authorized_roles_may_approve(rolle):
    _kandidat()
    ergebnis = _freigeben(actor=_actor(role=rolle))
    assert ergebnis["status"] == "approved"


def test_self_approval_is_denied():
    """Vier-Augen-Prinzip: wer den Kandidaten eingebracht hat, gibt ihn
    nicht selbst frei."""
    from apps.backend.database import ModelApprovalDenied

    _kandidat(created_by="chef")
    with pytest.raises(ModelApprovalDenied):
        _freigeben(actor=_actor(user_id="chef", role="manager"))
    # Eine andere berechtigte Person darf.
    assert _freigeben(actor=_actor(user_id="chefin", role="manager"))["status"] == "approved"


def test_approved_by_comes_from_actor_not_from_caller():
    """Eine Freigabe im fremden Namen ist ausgeschlossen -- approved_by wird
    aus dem Actor abgeleitet."""
    _kandidat()
    ergebnis = _freigeben(actor=_actor(user_id="echte-pruefer-id"))
    assert ergebnis["approved_by"] == "echte-pruefer-id"


def test_candidate_without_creator_is_rejected():
    """created_by ist Pflicht: ohne bekannten Urheber waere das
    Vier-Augen-Prinzip wirkungslos. Ein optionaler Wert wurde von keinem
    Aufrufer gesetzt und machte die Pruefung praktisch nie aktiv."""
    from apps.backend.database import create_model_candidate

    for leer in (None, "", "   "):
        with pytest.raises(ValueError):
            create_model_candidate(
                "groq", "ohne-urheber", modalities=["text"], capabilities=[],
                context_window=1000, created_by=leer,
            )


def test_denied_approval_is_audited_without_scores():
    from apps.backend.database import list_audit_entries, ModelApprovalDenied

    _kandidat()
    with pytest.raises(ModelApprovalDenied):
        _freigeben(actor=_actor(role="user"))
    treffer = [e for e in list_audit_entries(limit=20, tenant_id=TENANT)
               if e["action"] == "model.approval.denied"]
    assert treffer
    for verboten in ("prompt", "quality_score", "content"):
        assert verboten not in treffer[0]["metadata"]


# ── B3: Routing nur mit belegter Klassifikation ───────────────────────────

def test_missing_classification_blocks_routing():
    """Der frueher moegliche Weg -- Klassifikation einfach weglassen --
    fuehrt jetzt zu keiner Modellauswahl."""
    from apps.backend.database import recommend_model

    _kandidat(); _freigeben()
    ergebnis = recommend_model(TENANT, modality="text", task="chat")
    assert ergebnis["selected"] is None
    assert "klassifiziert" in ergebnis["reason"]


def test_caller_cannot_supply_own_classification():
    """Ein selbst gebautes ClassificationResult wird NICHT mehr entgegen-
    genommen. Frueher genuegte es, ein harmloses Ergebnis zu uebergeben,
    um HR-Daten durchzurouten -- der Typ allein ist kein Herkunftsnachweis,
    weil die Dataclass offen ist."""
    from apps.backend.database import recommend_model
    from apps.backend.governance.data_governance import ClassificationResult, DataClass

    _kandidat(); _freigeben()
    with pytest.raises(TypeError):
        recommend_model(TENANT, modality="text", task="chat",
                        classification=ClassificationResult(data_classes=[DataClass.PUBLIC]))


def test_forged_harmless_classification_cannot_route_sensitive_text():
    """Der eigentliche Missbrauch: sensibler Text + harmlose Klassifikation.
    Die Klassifikation entsteht jetzt intern, der Text wird erkannt."""
    from apps.backend.database import recommend_model

    _kandidat(); _freigeben()
    ergebnis = recommend_model(
        TENANT, modality="text", task="chat",
        prompt_text="Gehalt von Anna Meier: 78000 EUR, Abmahnung wegen Krankheit HIV-positiv.",
    )
    assert ergebnis["selected"] is None


def test_harmless_text_still_routes():
    from apps.backend.database import recommend_model

    _kandidat(); _freigeben()
    ergebnis = recommend_model(TENANT, modality="text", task="chat",
                               prompt_text="Wie formuliere ich eine hoefliche Absage?")
    assert ergebnis["selected"] == "groq:m1"


def test_free_text_task_is_rejected():
    """task war frueher freier Text und wurde woertlich in die Datenbank und
    ins Audit geschrieben -- damit liess sich ein Rohprompt persistieren."""
    from apps.backend.database import recommend_model

    _kandidat(); _freigeben()
    ergebnis = recommend_model(
        TENANT, modality="text",
        task="Mitarbeiterin Anna Meier, Gehalt 78000 EUR, HIV-positiv",
        prompt_text="harmlos",
    )
    assert ergebnis["selected"] is None
    assert "Aufgabenart" in ergebnis["reason"]


def test_prompt_text_is_never_persisted_or_audited():
    """Der Text darf klassifiziert, aber niemals gespeichert werden."""
    from apps.backend.database import (
        recommend_model, list_audit_entries, engine, routing_decisions,
    )
    from sqlalchemy import select as _select

    geheim = "Interne Preisliste Projekt Nordstern, Marge 42 Prozent"
    _kandidat(); _freigeben()
    recommend_model(TENANT, modality="text", task="chat", prompt_text=geheim)

    for e in list_audit_entries(limit=20, tenant_id=TENANT):
        assert geheim not in str(e)
    with engine.begin() as conn:
        zeilen = conn.execute(_select(routing_decisions)).mappings().all()
    assert zeilen
    for z in zeilen:
        assert geheim not in str(dict(z))


@pytest.mark.parametrize("klasse,text", [
    ("credentials", "Mein Passwort: hunter2geheim"),
    ("special_category", "Diagnose: HIV-positiv, Patientin Meier"),
    ("hr", "Gehalt von Hans Meier: 85000 EUR, Abmahnung"),
])
def test_each_blocked_class_prevents_routing(klasse, text):
    """LEGAL fehlt hier bewusst: classify() erkennt Strafverfahren derzeit
    NICHT als LEGAL (B-GOV-1, offen). Ein Test, der das Gegenteil behauptet,
    waere ein falscher Sicherheitsnachweis."""
    from apps.backend.database import recommend_model

    _kandidat(); _freigeben()
    ergebnis = recommend_model(TENANT, modality="text", task="chat", prompt_text=text)
    assert ergebnis["selected"] is None, f"{klasse} wurde nicht blockiert"
    assert "nicht extern geroutet" in ergebnis["reason"]


def test_legal_class_is_detected_and_blocked():
    """Art.-10-Daten werden als LEGAL erkannt und extern blockiert."""
    from apps.backend.database import recommend_model
    from apps.backend.governance.data_governance import DataClass, classify

    _kandidat(); _freigeben()
    prompt = (
        "SYNTHETISCH: Strafverfahren gegen Testperson A, "
        "Aktenzeichen 4 Ls 123/24, verurteilt wegen Diebstahl."
    )
    classification = classify(prompt)
    assert DataClass.LEGAL in classification.data_classes
    ergebnis = recommend_model(
        TENANT, modality="text", task="chat",
        prompt_text=prompt,
    )
    assert ergebnis["selected"] is None


def test_perfect_scores_cannot_override_hard_block():
    """Kein Score hebt eine gesperrte Datenklasse auf."""
    from apps.backend.database import recommend_model

    _kandidat(); _freigeben(privacy=1.0)
    ergebnis = recommend_model(TENANT, modality="text", task="chat",
                               prompt_text="Diagnose: HIV-positiv, Patientin Meier")
    assert ergebnis["selected"] is None


def test_local_only_does_not_bypass_block():
    from apps.backend.database import recommend_model

    _kandidat(); _freigeben()
    ergebnis = recommend_model(TENANT, modality="text", task="chat",
                               local_only=True, prompt_text="Gehalt von Hans Meier: 85000 EUR, Abmahnung wegen Krankheit")
    assert ergebnis["selected"] is None


def test_blocked_routing_audit_has_no_raw_content():
    from apps.backend.database import recommend_model, list_audit_entries

    _kandidat(); _freigeben()
    recommend_model(TENANT, modality="text", task="chat", prompt_text="Gehalt von Hans Meier: 85000 EUR, Abmahnung wegen Krankheit")
    treffer = [e for e in list_audit_entries(limit=20, tenant_id=TENANT)
               if e["action"] == "model.routing.blocked"]
    assert treffer
    md = treffer[0]["metadata"]
    for verboten in ("prompt", "content", "text", "raw"):
        assert verboten not in md


def test_router_calls_no_provider(monkeypatch):
    """Der Router bleibt Empfehlungsschicht -- er darf keinen Provider
    aufrufen. Ein echter Netzaufruf wuerde hier sofort auffallen."""
    import urllib.request
    from apps.backend.database import recommend_model

    def _verboten(*args, **kwargs):  # pragma: no cover - darf nie laufen
        raise AssertionError("Der Router hat einen externen Aufruf versucht.")

    monkeypatch.setattr(urllib.request, "urlopen", _verboten)
    _kandidat(); _freigeben()
    ergebnis = recommend_model(TENANT, modality="text", task="chat",
                               prompt_text="Wie formuliere ich eine hoefliche Absage?")
    assert ergebnis["selected"] == "groq:m1"


# ── Befunde der finalen Gegenprüfung ──────────────────────────────────────

@pytest.mark.parametrize("feld", ["modality", "data_risk"])
def test_free_text_in_neighbour_fields_is_rejected(feld):
    """Kritisch 1: task war gehaertet, die NACHBARSPALTEN nicht. modality und
    data_risk landen ebenfalls woertlich in routing_decisions und im Audit --
    damit liess sich ein Rohprompt persistieren."""
    from apps.backend.database import recommend_model

    _kandidat(); _freigeben()
    args = {"modality": "text", "task": "chat", "prompt_text": "harmlos"}
    args[feld] = "Patientin Meier, HIV-positiv, Passwort hunter2"
    ergebnis = recommend_model(TENANT, **args)
    assert ergebnis["selected"] is None


def test_real_api_key_is_blocked_even_if_classifier_misses_it():
    """Hoch 2: classify() stuft echte Schluessel als 'public' ein. Die
    vorhandene Secret-Heuristik erkennt sie und wird jetzt zusaetzlich
    ausgewertet."""
    from apps.backend.database import recommend_model

    _kandidat(); _freigeben()
    ergebnis = recommend_model(
        TENANT, modality="text", task="chat",
        prompt_text="Nimm diesen Schluessel: gsk_AbCdEfGhIjKlMnOpQrStUvWx1234",
    )
    assert ergebnis["selected"] is None


def test_caller_cannot_lower_risk_to_bypass_privacy_threshold():
    """Hoch 3: data_risk bestimmte der Aufrufer. Mit 'low' liess sich die
    Datenschutzschwelle umgehen, obwohl der Text personenbezogene Daten
    enthielt. Die Klassifikation hebt die Stufe jetzt an."""
    from apps.backend.database import recommend_model

    _kandidat(); _freigeben(privacy=0.5)
    ergebnis = recommend_model(
        TENANT, modality="text", task="chat", data_risk="low",
        prompt_text="Kundin Anna Meier, geboren 03.04.1985, wohnhaft Hauptstrasse 7, Telefon 0170 1234567.",
    )
    assert ergebnis["selected"] is None


@pytest.mark.parametrize("variante", ["Einbringer", " einbringer ", "EINBRINGER"])
def test_self_approval_cannot_be_bypassed_by_spelling(variante):
    """Mittel 4: Der Vergleich war ein reiner String-Vergleich -- eine andere
    Schreibweise genuegte fuer die Selbstfreigabe."""
    from apps.backend.database import ModelApprovalDenied

    _kandidat(created_by="einbringer")
    with pytest.raises(ModelApprovalDenied):
        _freigeben(actor=_actor(user_id=variante, role="manager"))


def test_unknown_creator_denies_approval_fail_closed():
    """Mittel 5: Fehlte created_by, wurde die Freigabe trotzdem erteilt und
    nur auditiert -- fail-open. Jetzt wird verweigert."""
    from apps.backend.database import (
        engine, model_candidates, ModelApprovalDenied, list_audit_entries,
    )
    from sqlalchemy import insert as _insert
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(_insert(model_candidates).values(
            provider="groq", model_id="altbestand", modalities=["text"],
            capabilities=[], context_window=1000, regions=[], status="candidate",
            benchmark_version="unbenchmarked", evidence_urls=[],
            created_by=None, created_at=now, updated_at=now,
        ))
    with pytest.raises(ModelApprovalDenied):
        _freigeben(name="altbestand")
    gruende = [e["metadata"].get("reason_code")
               for e in list_audit_entries(limit=20, tenant_id=TENANT)
               if e["action"] == "model.approval.denied"]
    assert "FOUR_EYES_NOT_VERIFIABLE" in gruende
