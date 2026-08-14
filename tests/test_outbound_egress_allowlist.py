"""Wachhund: neue externe Ausgänge dürfen nicht unbemerkt entstehen.

Hintergrund: Das Chat-Schutzgate (Prüfbeleg, siehe governance/send_preview.py)
wirkt nur dort, wo es tatsächlich verdrahtet ist. Ein neuer, direkt
programmierter Netzwerkaufruf an anderer Stelle würde es umgehen, ohne dass
jemand es merkt -- genau so sind die bisherigen Lücken entstanden
(AgentRuntime.stream ohne classify/redact, Telegram-Antwort ohne
Ausgangsprüfung).

Dieser Test findet Egress-Stellen über den Syntaxbaum (AST), nicht über eine
Textsuche: eine Textsuche würde an Kommentaren, Strings und Umbenennungen
scheitern und wäre als Sicherheitsnachweis wertlos. Gefundene Stellen werden
gegen eine ausdrückliche Allowlist geprüft. Kommt eine neue hinzu, schlägt
dieser Test fehl -- mit dem Hinweis, was zu tun ist.

Bekannte Grenzen -- bewusst benannt, damit dieser Test nicht für mehr
gehalten wird, als er leistet:

  * Er beweist NICHT, dass die erlaubten Ausgänge korrekt abgesichert sind.
    Er stellt nur sicher, dass keine neuen unbemerkt dazukommen.
  * Er erkennt Aufrufe anhand ihrer Form im Syntaxbaum. Dynamisch gebaute
    Aufrufe (``getattr(requests, "post")(...)``, ``functools.partial``,
    ein über ``importlib`` geladenes Modul) rutschen durch. Gegen
    versehentliche Neuzugänge -- der eigentliche Zweck -- hilft er; gegen
    jemanden, der den Ausgang absichtlich verschleiert, nicht.
  * Er prüft nur ``apps/backend``. Ein Egress aus einem anderen Verzeichnis
    fällt hier nicht auf.
"""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "apps" / "backend"

# HTTP-Verben, die über einem Netzwerk-Modul einen Aufruf nach außen bedeuten.
_HTTP_VERBS = {"get", "post", "put", "patch", "delete", "request", "send"}

# Netzwerk-Bibliotheken. Import-Aliasse werden pro Datei aufgeloest (siehe
# _collect_import_aliases) -- ohne das waere der Wachhund blind gegenueber
# "import requests as http_requests", genau wie im Telegram-Gateway.
_NET_LIBS = {"requests", "httpx", "urllib", "urllib3", "aiohttp"}

# Direkte Aufrufnamen, die unabhaengig vom Modulpraefix Egress bedeuten.
_DIRECT_EGRESS_NAMES = {"urlopen"}

# Aufrufe von Anbieter-SDKs, die intern selbst eine Verbindung oeffnen --
# hier taucht kein requests/httpx im Code auf, der Egress ist aber real.
# Als (vorletztes, letztes) Attributpaar, z.B. client.messages.create().
_SDK_EGRESS_PAIRS = {
    ("messages", "create"),      # anthropic
    ("messages", "stream"),      # anthropic (Streaming)
    ("completions", "create"),   # openai chat.completions.create
    ("chat", "completions"),     # defensiv
}

# Ausdrücklich erlaubte Egress-Module. Jeder Eintrag ist eine bewusste
# Entscheidung und in der Statusdatei bzw. im jeweiligen Modul begründet.
_ALLOWLIST: dict[str, str] = {
    "providers/groq_provider.py":
        "Provider-Adapter. Erreichbar nur über ProviderOrchestrator -> GatedLLMClient.",
    "providers/openai_provider.py":
        "Provider-Adapter, wie groq_provider.",
    "providers/anthropic_provider.py":
        "Provider-Adapter, wie groq_provider.",
    "providers/openrouter_provider.py":
        "Provider-Adapter. Praktisch nicht erreichbar (Orchestrator ruft nur "
        "generate_with_meta, das diese Klasse nicht hat) -- bleibt gelistet, "
        "damit eine spätere Aktivierung hier auffällt.",
    "tools/runtime_tools.py":
        "Websuche (Tavily) und URL-Abruf. Laufen über guarded_tool_call "
        "(Policy/Approval), aber NICHT über den Prüfbeleg -- offener Punkt, "
        "siehe docs/AILIZA_IMPLEMENTATION_STATUS.md.",
    "messenger/telegram_gateway.py":
        "Antwortversand an api.telegram.org. Der externe Anbieter-Aufruf ist "
        "hier fail-closed entfernt (Paket C); hinaus geht nur noch lokal "
        "erzeugter Text oder eine feste Hinweismeldung.",
    "groq_client.py":
        "Verwaistes Alt-Modul (GroqClientWithCompliance ohne Aufrufer) plus "
        "Diagnose-Endpunkt mit festem Testprompt, kein Nutzinhalt.",
    "tools.py":
        "Schattenmodul: wird vom gleichnamigen Package tools/ verdeckt und "
        "nie importiert. Gelistet, damit ein versehentliches Reaktivieren "
        "auffällt.",
    "agent/api_client.py":
        "Quarantänisierter Agent-Prototyp ohne FastAPI-Route.",
}


def _relpath(path: Path) -> str:
    return path.relative_to(BACKEND).as_posix()


def _collect_import_aliases(tree: ast.AST) -> set[str]:
    """Namen, unter denen in DIESER Datei eine Netzwerkbibliothek erreichbar
    ist -- inklusive Aliassen. "import requests as http_requests" macht
    http_requests zu einem Netzwerknamen; ohne diese Aufloesung waere der
    Wachhund genau dort blind, wo jemand die Herkunft verschleiert (bewusst
    oder aus Stilgruenden, wie im Telegram-Gateway)."""
    names: set[str] = set(_NET_LIBS)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _NET_LIBS and alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            for alias in node.names:
                if root in _NET_LIBS or alias.name in _NET_LIBS:
                    names.add(alias.asname or alias.name)
    return names


def _is_egress_call(node: ast.Call, net_names: set[str]) -> bool:
    func = node.func

    if isinstance(func, ast.Name):
        return func.id in _DIRECT_EGRESS_NAMES

    if not isinstance(func, ast.Attribute):
        return False

    if func.attr in _DIRECT_EGRESS_NAMES:
        return True

    base = func.value

    # SDK-Muster: client.messages.create(...) / chat.completions.create(...)
    if isinstance(base, ast.Attribute) and (base.attr, func.attr) in _SDK_EGRESS_PAIRS:
        return True

    if func.attr not in _HTTP_VERBS:
        return False

    # requests.post(...) bzw. http_requests.post(...) nach Alias-Aufloesung
    if isinstance(base, ast.Name) and base.id in net_names:
        return True
    # self._session.get(...) / mod.requests.post(...)
    if isinstance(base, ast.Attribute) and (
        base.attr in net_names or base.attr.lower() in {"session", "client"}
    ):
        return True
    return False


def _find_egress_modules() -> dict[str, list[int]]:
    """Alle Module mit Netzwerkausgang. Wirft, wenn eine Datei nicht
    auswertbar ist -- eine ungelesene Datei ist eine ungepruefte Datei.

    Das ist bewusst fail-closed: eine frueherer Fassung fing SyntaxError ab
    und uebersprang die Datei still. Dadurch war apps/backend/agent/api_client.py
    (UTF-8-BOM am Dateianfang -> ast.parse scheitert) fuer den Wachhund
    unsichtbar, obwohl es einen echten Anbieter-Aufruf enthaelt. Ein
    Sicherheitstest, der bei unlesbaren Dateien einfach gruen bleibt, sichert
    genau die Faelle nicht ab, in denen etwas ungewoehnlich ist.
    """
    found: dict[str, list[int]] = {}
    nicht_auswertbar: list[str] = []
    for py in sorted(BACKEND.rglob("*.py")):
        rel = _relpath(py)
        if rel.startswith("tests/") or "/tests/" in rel:
            continue
        # utf-8-sig: entfernt ein etwaiges BOM, das ast.parse sonst als
        # "invalid non-printable character U+FEFF" ablehnen wuerde.
        try:
            quelltext = py.read_text(encoding="utf-8-sig")
            tree = ast.parse(quelltext)
        except (SyntaxError, UnicodeDecodeError) as exc:
            nicht_auswertbar.append(f"{rel}: {type(exc).__name__}: {exc}")
            continue
        net_names = _collect_import_aliases(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_egress_call(node, net_names):
                found.setdefault(rel, []).append(node.lineno)

    if nicht_auswertbar:
        raise AssertionError(
            "Der Egress-Wachhund konnte Dateien nicht auswerten und damit nicht "
            "pruefen:\n" + "\n".join(f"  {e}" for e in nicht_auswertbar)
            + "\n\nDiese Dateien sind fuer den Wachhund blind -- sie koennten "
              "einen ungesicherten externen Ausgang enthalten. Bitte die Datei "
              "reparieren (haeufigste Ursache: UTF-8-BOM oder Syntaxfehler)."
        )
    return found


def test_no_unlisted_outbound_egress():
    """Kein neuer Netzwerkausgang ohne bewusste Entscheidung."""
    found = _find_egress_modules()
    unlisted = {mod: lines for mod, lines in found.items() if mod not in _ALLOWLIST}
    assert not unlisted, (
        "Neuer externer Ausgang gefunden, der nicht in der Allowlist steht:\n"
        + "\n".join(f"  apps/backend/{m} (Zeilen {ls})" for m, ls in sorted(unlisted.items()))
        + "\n\nDas ist kein Formfehler: ein direkter Netzwerkaufruf umgeht das "
          "Chat-Schutzgate (Prüfbeleg), wenn er nicht daran angebunden ist.\n"
          "Zu tun: (1) den Aufruf an den geprüften Versandweg anbinden ODER "
          "(2) begründen, warum er ohne Nutzinhalt auskommt, und ihn mit "
          "dieser Begründung in _ALLOWLIST eintragen."
    )


def test_allowlist_has_no_stale_entries():
    """Gegenprobe: eine Allowlist, die längst entfernte Module auflistet,
    wiegt in falscher Sicherheit und verdeckt echte Neuzugänge."""
    found = _find_egress_modules()
    stale = [mod for mod in _ALLOWLIST if mod not in found]
    assert not stale, (
        "Allowlist nennt Module ohne (noch) vorhandenen Egress: "
        + ", ".join(sorted(stale))
        + " -- bitte Eintrag entfernen."
    )


def test_every_allowlist_entry_has_a_reason():
    """Ein leerer Grund waere eine stillschweigende Freigabe."""
    for mod, reason in _ALLOWLIST.items():
        assert reason and len(reason) > 20, f"Allowlist-Eintrag ohne echte Begruendung: {mod}"


def test_watchdog_actually_detects_a_new_egress(tmp_path, monkeypatch):
    """Selbsttest: erkennt der Wachhund einen neu hinzugefuegten Aufruf
    ueberhaupt? Ohne diesen Nachweis koennte er dauerhaft gruen sein, weil
    seine Erkennung kaputt ist -- und niemand wuerde es merken."""
    fake_backend = tmp_path / "backend"
    (fake_backend / "sub").mkdir(parents=True)
    (fake_backend / "sub" / "neuer_ausgang.py").write_text(
        "import requests\n\n\ndef leck(text):\n    return requests.post('https://example.invalid', data=text)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.BACKEND", fake_backend)

    found = _find_egress_modules()
    assert "sub/neuer_ausgang.py" in found, (
        "Der Wachhund erkennt einen offensichtlichen neuen Egress nicht -- "
        "seine Erkennungslogik ist defekt."
    )


def test_watchdog_detects_aliased_network_import(tmp_path, monkeypatch):
    """Ein umbenannter Import darf den Wachhund nicht blind machen.
    Genau dieser Fall existiert real: messenger/telegram_gateway.py nutzt
    "import requests as http_requests"."""
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir(parents=True)
    (fake_backend / "getarnt.py").write_text(
        "import requests as http_requests\n\n\n"
        "def leck(text):\n    return http_requests.post('https://example.invalid', json=text)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.BACKEND", fake_backend)
    assert "getarnt.py" in _find_egress_modules()


def test_watchdog_detects_sdk_call_without_http_library(tmp_path, monkeypatch):
    """Anbieter-SDKs oeffnen die Verbindung selbst -- im Code steht kein
    requests/httpx. Ohne diese Erkennung waeren alle Anthropic-/OpenAI-
    Aufrufe unsichtbar."""
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir(parents=True)
    (fake_backend / "sdk.py").write_text(
        "def frage(client, msgs):\n    return client.messages.create(messages=msgs)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.BACKEND", fake_backend)
    assert "sdk.py" in _find_egress_modules()


def test_watchdog_fails_loudly_on_unparsable_file(tmp_path, monkeypatch):
    """Fail-closed: eine nicht auswertbare Datei muss den Wachhund
    fehlschlagen lassen, nicht still uebersprungen werden. Eine fruehere
    Fassung uebersprang sie -- dadurch war eine Datei mit UTF-8-BOM und
    echtem Anbieter-Aufruf unsichtbar."""
    import pytest as _pytest

    fake_backend = tmp_path / "backend"
    fake_backend.mkdir(parents=True)
    (fake_backend / "kaputt.py").write_text(
        "def unvollstaendig(:\n    pass\n", encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.BACKEND", fake_backend)

    with _pytest.raises(AssertionError, match="nicht auswerten"):
        _find_egress_modules()


def test_watchdog_handles_byte_order_mark(tmp_path, monkeypatch):
    """Ein BOM am Dateianfang darf die Auswertung nicht verhindern --
    reale Fundstelle: apps/backend/agent/api_client.py."""
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir(parents=True)
    (fake_backend / "mit_bom.py").write_bytes(
        b"\xef\xbb\xbf" + b"import requests\n\n\ndef f():\n    return requests.get('https://x.invalid')\n"
    )
    monkeypatch.setattr(f"{__name__}.BACKEND", fake_backend)
    assert "mit_bom.py" in _find_egress_modules()


def test_watchdog_ignores_lookalike_calls(tmp_path, monkeypatch):
    """Gegenprobe zum Selbsttest: harmlose .get()-Aufrufe auf Dictionaries
    duerfen NICHT als Netzwerkausgang gelten -- sonst waere der Wachhund vor
    lauter Fehlalarmen unbrauchbar und wuerde abgeschaltet."""
    fake_backend = tmp_path / "backend"
    fake_backend.mkdir(parents=True)
    (fake_backend / "harmlos.py").write_text(
        "def f(d, payload):\n"
        "    a = d.get('key')\n"
        "    b = payload.get('anderes', 1)\n"
        "    return a, b\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(f"{__name__}.BACKEND", fake_backend)

    assert _find_egress_modules() == {}
