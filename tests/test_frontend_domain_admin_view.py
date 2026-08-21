"""Frontend: Bereichsverwaltung und die behobene Skills-Regression.

Geprueft wird, was strukturell nachweisbar ist: dass jede Ansicht ueber
einen Menuepunkt erreichbar ist, dass Nutzereingaben vor der Ausgabe
maskiert werden und dass der Menuepunkt nicht als Schutzmassnahme
missverstanden wird.

Bewusst NICHT geprueft: Aussehen und Klickverhalten -- dafuer ist ein
Browsertest zustaendig, nicht eine Textpruefung.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

INDEX = Path("apps/frontend/index.html").read_text(encoding="utf-8")


DOMAIN_FUNCTIONS = ("loadDomains", "domBootstrap", "domToggleMembers", "domAssign")


def _function_body(name: str) -> str:
    """Extrahiert den Rumpf einer JS-Funktion ueber Klammerzaehlung.

    Ein Fenster fester Groesse waere unbrauchbar: es liefe in den naechsten
    Funktionsrumpf hinein und wuerde dort Treffer melden, die mit der
    geprueften Funktion nichts zu tun haben."""
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


def _domain_code() -> str:
    return "\n".join(_function_body(fn) for fn in DOMAIN_FUNCTIONS)


def _views() -> set[str]:
    return set(re.findall(r'<div class="view" id="view-([a-z_-]+)"', INDEX))


def _nav_targets() -> set[str]:
    """Alle Ansichten, die ueber showView(...) aus dem Markup erreichbar sind."""
    return set(re.findall(r"showView\('([a-z_-]+)'", INDEX))


def test_every_view_is_reachable_from_navigation() -> None:
    """Regressionsschutz: 'view-skills' existierte, war aber nach einer
    Navigationsbereinigung ueber keinen Menuepunkt mehr erreichbar. Diese
    Pruefung faengt genau diesen Fall kuenftig ab -- fuer JEDE Ansicht,
    nicht nur fuer Skills."""
    unreachable = _views() - _nav_targets()
    assert not unreachable, (
        f"Ansichten ohne Weg dorthin: {sorted(unreachable)}. "
        "Jede Ansicht braucht einen Menuepunkt oder muss entfernt werden."
    )


def test_skills_view_is_reachable() -> None:
    assert "skills" in _nav_targets()


def test_domains_view_exists_and_is_reachable() -> None:
    assert "domains" in _views()
    assert "domains" in _nav_targets()


def test_domains_view_is_loaded_on_open() -> None:
    """Eine Ansicht ohne Ladeaufruf bliebe dauerhaft beim Platzhalter
    stehen -- genau dieser Fehler ist in diesem Projekt schon einmal
    aufgetreten (Kontextleiste wurde beim Start nie gerendert)."""
    assert 'if(name==="domains")loadDomains();' in INDEX


# ── Sicherheitsrelevante Eigenschaften ──────────────────────────────────────

def test_nav_entry_is_documented_as_convenience_not_protection() -> None:
    """Ein ausgeblendeter Menuepunkt schuetzt nichts -- die Pruefung liegt
    im Backend. Wenn dieser Hinweis verschwindet, koennte jemand spaeter
    annehmen, das Ausblenden sei die Zugriffskontrolle."""
    assert "keine Schutzmassnahme" in INDEX


def test_user_input_is_escaped_before_rendering() -> None:
    """Bereichs- und Nutzernamen landen in innerHTML. Ohne Maskierung
    waere ein Nutzername wie <img onerror=...> ausfuehrbar."""
    assert "function domEsc(" in INDEX
    # Die Maskierung muss die fuenf kritischen Zeichen abdecken.
    for ch in ("&amp;", "&lt;", "&gt;", "&quot;", "&#39;"):
        assert ch in INDEX, f"Maskierung fuer {ch} fehlt"


def test_domain_and_user_values_are_escaped_not_raw() -> None:
    """Jede Interpolation von Serverdaten in das Markup muss durch domEsc()
    laufen. Ein roher ${d.code} oder ${m.user_id} waere eine Luecke."""
    raw = re.findall(r"\$\{(?:d|m)\.[a-z_]+\}", _domain_code())
    assert not raw, f"Unmaskierte Interpolationen gefunden: {set(raw)}"


def test_no_token_is_read_from_local_storage_for_domain_calls() -> None:
    """Die Anmeldung laeuft ueber ein HttpOnly-Cookie. Ein zusaetzlich in
    localStorage abgelegtes Token waere fuer jedes Skript auf der Seite
    lesbar -- die Bereichsaufrufe duerfen darauf nicht zurueckfallen."""
    for fn in DOMAIN_FUNCTIONS:
        body = _function_body(fn)
        assert "localStorage" not in body, f"{fn} liest localStorage"
        assert 'credentials:"same-origin"' in body, f"{fn} sendet das Cookie nicht mit"


def test_reason_is_required_before_sending() -> None:
    """Begruendungspflicht ist eine Nachweispflicht, keine Formalie. Das
    Frontend darf einen leeren Grund nicht ans Backend durchreichen --
    auch wenn das Backend ihn ohnehin ablehnen wuerde."""
    assert "Ohne Begruendung wird nicht freigeschaltet." in INDEX
    assert "Ohne Begruendung wird nicht zugewiesen." in INDEX


def test_denied_access_shows_reason_not_empty_list() -> None:
    """403 muss als Verweigerung erkennbar sein. Eine stumme leere Liste
    waere von 'Bereich ist leer' nicht zu unterscheiden."""
    assert "Sie duerfen diesen Bereich nicht verwalten." in INDEX


@pytest.mark.parametrize("role", ["viewer", "contributor", "reviewer", "domain_manager"])
def test_all_four_v1_roles_are_selectable(role: str) -> None:
    """Fehlt eine Rolle in der Auswahl, waere sie ueber die Oberflaeche
    nicht vergebbar -- obwohl das Backend sie kennt."""
    assert f'"{role}"' in INDEX


def test_no_role_beyond_v1_is_offered() -> None:
    """Die Oberflaeche darf keine Rolle anbieten, die die Datenbank per
    CHECK-Constraint ablehnt -- das ergaebe einen unerklaerlichen Fehler."""
    roles = re.search(r"const DOM_ROLES=\[(.*?)\];", INDEX, re.S)
    assert roles is not None
    offered = set(re.findall(r'\["([a-z_]+)"', roles.group(1)))
    assert offered == {"viewer", "contributor", "reviewer", "domain_manager"}
