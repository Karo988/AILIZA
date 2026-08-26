#!/usr/bin/env python3
"""Secret-Scan fuer DATEINAMEN -- schliesst eine belegte gitleaks-Luecke.

Warum es dieses Skript gibt
---------------------------
gitleaks prueft ausschliesslich Datei-INHALTE, keine Pfadnamen -- gemessen
am 26.08.2026 gegen 8.28.0, in beiden Modi (`git` und `dir`). Ein
Schluessel, der im Dateinamen steht, bleibt dort unentdeckt, unabhaengig
von jeder Regex.

Das ist kein theoretischer Fall: genau so entstand der in
`06_release/SECURITY_INCIDENT_2026-06-25.md` dokumentierte Vorfall -- der
Groq-Schluessel stand im Dateinamen, der Dateiinhalt war nur ein
Platzhalter. Ein reines Dokumentieren dieser Grenze schuetzt nicht.

Was geprueft wird
-----------------
Alle Pfadnamen, die im angegebenen Commit-Bereich jemals vorkamen
(hinzugefuegt, geaendert, umbenannt oder geloescht) -- nicht nur die des
aktuellen Dateistands. Ein spaeter geloeschter Dateiname steht weiterhin
dauerhaft in der Historie.

Die Muster stammen aus `.gitleaks.toml`, damit es genau eine Quelle fuer
die Anbieterregeln gibt. Eine zweite Musterliste hier wuerde frueher oder
spaeter von der ersten abweichen -- und zwar unbemerkt.

Datenschutz der Ausgabe
-----------------------
Der gefundene Wert wird NIEMALS ausgegeben, auch nicht gekuerzt
(Push-Sicherheitsregel, Abschnitt 2). Da der Wert hier Teil des Pfades
ist, wird der Pfad selbst redigiert: der Treffer wird durch
`[REDIGIERT:<n> Zeichen]` ersetzt. Gemeldet werden Regel-ID, redigierter
Pfad und Commit -- genug fuer die Behebung, ohne das Geheimnis erneut zu
verbreiten.

Aufruf
------
    python scripts/scan_pfadnamen_auf_secrets.py --log-opts "--all"
    python scripts/scan_pfadnamen_auf_secrets.py --log-opts "abc123..HEAD"

Exit-Codes: 0 = kein Fund, 1 = Fund, 2 = Ausfuehrungsfehler.
Aendert nie etwas -- reine Leseoperation.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / ".gitleaks.toml"

# Nur anbieterspezifische Regeln. Die Entropie-Heuristik "generic-api-key"
# ist auf Fliesstext ausgelegt und wuerde auf Pfadnamen (Hashes in
# Testdaten, lange Verzeichnisnamen) unbrauchbar viele Fehlalarme
# erzeugen. Anbieterregeln sind praezise und praktisch nie falsch-positiv.
_AUSGENOMMEN = {"generic-api-key"}


def regeln_aus_config(pfad: Path = CONFIG) -> dict[str, re.Pattern]:
    """Liest die Anbieterregeln aus .gitleaks.toml -- eine Quelle, nicht zwei."""
    with pfad.open("rb") as fh:
        daten = tomllib.load(fh)

    regeln: dict[str, re.Pattern] = {}
    for regel in daten.get("rules", []):
        rid = regel.get("id")
        muster = regel.get("regex")
        if not rid or not muster or rid in _AUSGENOMMEN:
            continue
        try:
            regeln[rid] = re.compile(muster)
        except re.error as exc:  # pragma: no cover - Konfigurationsfehler
            raise SystemExit(
                "Regex der Regel %s ist nicht uebersetzbar: %s" % (rid, exc)
            )

    if not regeln:
        # Fail-closed: eine leere Regelmenge wuerde immer "sauber" melden.
        raise SystemExit(
            "Keine anbieterspezifischen Regeln in %s gefunden. Ein Scan ohne "
            "Regeln waere ein stilles Gruen und ist deshalb ein Fehler." % pfad
        )
    return regeln


def _git(*args: str) -> str:
    # Bewusst OHNE festes cwd: geprueft wird das Repository, in dem das
    # Skript aufgerufen wird -- nicht immer dasjenige, in dem es liegt.
    # Ein hart auf REPO_ROOT gesetztes cwd liess einen frueheren Stand
    # dieses Skripts stets AILIZA selbst scannen; die zugehoerigen Tests
    # bestanden dadurch aus dem falschen Grund.
    ergebnis = subprocess.run(
        ["git", *args],
        capture_output=True, text=True, timeout=300,
    )
    if ergebnis.returncode != 0:
        raise SystemExit(
            "git %s fehlgeschlagen:\n%s" % (" ".join(args), ergebnis.stderr.strip())
        )
    return ergebnis.stdout


def pfade_im_bereich(log_opts: str) -> list[tuple[str, str]]:
    """(Commit, Pfad) fuer jeden im Bereich beruehrten Pfad.

    `--name-only` mit `--diff-filter=AMRD` erfasst auch umbenannte und
    geloeschte Dateien -- ein Dateiname, der nur kurz existierte, steht
    trotzdem dauerhaft in der Historie.
    """
    roh = _git("log", *log_opts.split(), "--pretty=format:%H", "--name-only",
               "--diff-filter=AMRD")
    treffer: list[tuple[str, str]] = []
    aktueller_commit = ""
    for zeile in roh.splitlines():
        zeile = zeile.strip()
        if not zeile:
            continue
        if re.fullmatch(r"[0-9a-f]{40}", zeile):
            aktueller_commit = zeile
            continue
        treffer.append((aktueller_commit, zeile))
    return treffer


def redigiere(pfad: str, treffer: re.Match) -> str:
    """Ersetzt den Treffer im Pfad -- der Wert darf nirgends erscheinen."""
    wert = treffer.group(0)
    return pfad.replace(wert, "[REDIGIERT:%d Zeichen]" % len(wert))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prueft Pfadnamen im Commit-Bereich auf Anbieter-Secrets.")
    parser.add_argument(
        "--config", default=str(CONFIG),
        help="Pfad zu .gitleaks.toml. Standard: die Konfiguration des "
             "Projekts, in dem dieses Skript liegt -- geprueft wird "
             "dagegen immer das Repository im aktuellen Verzeichnis.")
    parser.add_argument(
        "--log-opts", default="--all",
        help="An `git log` durchgereichter Bereich, z. B. \"--all\" oder "
             "\"basis..HEAD\". Standard: --all (fail-closed).")
    args = parser.parse_args()

    regeln = regeln_aus_config(Path(args.config))
    eintraege = pfade_im_bereich(args.log_opts)

    gesehen: set[tuple[str, str, str]] = set()
    funde: list[tuple[str, str, str]] = []
    for commit, pfad in eintraege:
        for rid, muster in regeln.items():
            treffer = muster.search(pfad)
            if not treffer:
                continue
            eintrag = (rid, redigiere(pfad, treffer), commit)
            if eintrag not in gesehen:
                gesehen.add(eintrag)
                funde.append(eintrag)

    geprueft = len({p for _, p in eintraege})
    print("Pfadnamen-Scan: %d Pfade im Bereich \"%s\" geprueft, %d Regeln aktiv (%s)."
          % (geprueft, args.log_opts, len(regeln), ", ".join(sorted(regeln))))

    if not funde:
        print("Kein Anbieter-Secret in einem Pfadnamen gefunden.")
        return 0

    print()
    print("SECRET IN PFADNAME GEFUNDEN -- %d Fund/Funde." % len(funde))
    print("Der Wert wird bewusst nicht ausgegeben.")
    for rid, pfad, commit in funde:
        print()
        print("  Regel:  %s" % rid)
        print("  Pfad:   %s" % pfad)
        print("  Commit: %s" % commit)
    print()
    print("Vorgehen: docs/AILIZA_PUSH_SICHERHEITSREGEL.md, Abschnitt 6.")
    print("Ein Schluessel im Pfadnamen ist genauso kompromittiert wie einer im")
    print("Dateiinhalt. Beim Anbieter zurueckziehen und neu ausstellen --")
    print("Umbenennen oder Loeschen ersetzt keine Rotation.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        print("Ausfuehrungsfehler: %s" % exc, file=sys.stderr)
        sys.exit(2)
