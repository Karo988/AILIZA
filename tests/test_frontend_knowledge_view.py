"""Frontend: Unternehmenswissen-Ansicht.

Der wichtigste Punkt dieser Datei ist eine Abgrenzung: Das Frontend darf
die Sichtbarkeit NICHT selbst entscheiden. Wuerde es die Serverantwort
nachfiltern, waeren die Daten bereits uebertragen -- eine Anzeige-
entscheidung ist keine Zugriffskontrolle.
"""
from __future__ import annotations

import re
from pathlib import Path

INDEX = Path("apps/frontend/index.html").read_text(encoding="utf-8")

KNOWLEDGE_FUNCTIONS = ("loadKnowledge", "knSetDomain")


def _function_body(name: str) -> str:
    start = INDEX.index(f"function {name}(")
    open_brace = INDEX.index("{", start)
    depth = 0
    for i in range(open_brace, len(INDEX)):
        if INDEX[i] == "{":
            depth += 1
        elif INDEX[i] == "}":
            depth -= 1
            if depth == 0:
                return INDEX[start:i + 1]
    raise AssertionError(f"Funktionsende von {name} nicht gefunden")


def test_view_exists_and_is_reachable() -> None:
    assert '<div class="view" id="view-knowledge">' in INDEX
    assert "showView('knowledge'" in INDEX


def test_view_is_loaded_on_open() -> None:
    assert 'if(name==="knowledge")loadKnowledge();' in INDEX


def test_frontend_does_not_filter_visibility_itself() -> None:
    """Kein Nachfiltern der Serverantwort. Die Liste zeigt genau das, was
    der Server geliefert hat -- eine zusaetzliche Filterung im Browser
    waere Fassade, weil die Daten dann schon uebertragen waeren."""
    body = _function_body("loadKnowledge")
    for verboten in (".filter(", "domain_code===", "domain_code =="):
        assert verboten not in body, (
            f"loadKnowledge enthaelt {verboten!r} -- Sichtbarkeit gehoert "
            "ausschliesslich auf den Server"
        )


def test_no_local_storage_token_for_knowledge_calls() -> None:
    for fn in KNOWLEDGE_FUNCTIONS:
        body = _function_body(fn)
        assert "localStorage" not in body, f"{fn} liest localStorage"
        assert 'credentials:"same-origin"' in body, f"{fn} sendet das Cookie nicht mit"


def test_server_values_are_escaped() -> None:
    """Titel und Nutzernamen stammen aus Uploads und landen in innerHTML."""
    assert "function knEsc(" in INDEX
    raw = re.findall(r"\$\{s\.[a-z_]+\}", _function_body("loadKnowledge"))
    assert not raw, f"Unmaskierte Interpolationen: {set(raw)}"


def test_source_id_is_coerced_to_number() -> None:
    """Die ID geht in eine URL und in einen onclick-Handler. Ohne
    Zahlkonvertierung koennte ein manipulierter Wert dort Code einschleusen."""
    body = _function_body("loadKnowledge")
    assert "Number(s.id)" in body
    assert "Number(sourceId)" in _function_body("knSetDomain")


def test_restricting_effect_is_explained_to_the_user() -> None:
    """Eine Bereichszuordnung nimmt anderen den Zugriff. Wer das nicht
    weiss, ordnet versehentlich zu und wundert sich, warum Kolleginnen
    das Dokument nicht mehr finden."""
    assert "schraenkt ein" in INDEX


def test_reason_is_required_before_sending() -> None:
    assert "Ohne Begruendung wird nichts geaendert." in INDEX


def test_unbound_sources_are_marked_as_such() -> None:
    """'kein Bereich' muss sichtbar sein -- sonst waere nicht erkennbar,
    ob ein Dokument ungeschuetzt oder nur nicht eingestuft ist."""
    assert "kein Bereich" in INDEX


def test_empty_list_message_does_not_claim_there_is_nothing() -> None:
    """Wichtige Unterscheidung: Es kann Dokumente geben, die diese Person
    nicht sehen darf. 'Keine Dokumente vorhanden' waere eine falsche
    Aussage ueber den Datenbestand."""
    assert "die Sie sehen dürfen" in INDEX
