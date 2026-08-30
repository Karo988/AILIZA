"""Tests fuer scripts/scan_pfadnamen_auf_secrets.py.

Das Skript schliesst eine belegte gitleaks-Luecke: gitleaks prueft nur
Datei-INHALTE, keine Pfadnamen. Der in
`06_release/SECURITY_INCIDENT_2026-06-25.md` dokumentierte Vorfall war
genau dieser Fall.

Wie in tests/test_secret_scan_rules.py werden alle Testwerte erst zur
Laufzeit erzeugt und nur in Wegwerf-Repositories committet -- in dieser
Datei steht bewusst kein schluesselaehnliches Literal.
"""
from __future__ import annotations

import random
import string
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKRIPT = REPO_ROOT / "scripts" / "scan_pfadnamen_auf_secrets.py"


def _rand(n: int) -> str:
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(n))


def _synthetic_groq() -> str:
    return "gsk_" + _rand(52)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo(tmp_path: Path, dateien: dict[str, str], name: str = "wegwerf") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    for rel, inhalt in dateien.items():
        ziel = repo / rel
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(inhalt, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "synthetische Testdaten")
    return repo


def _scan(repo: Path, log_opts: str = "--all") -> subprocess.CompletedProcess:
    """Fuehrt das Skript gegen das Wegwerf-Repo aus.

    Das Skript liest seine Regeln aus der echten .gitleaks.toml des
    Projekts (REPO_ROOT), arbeitet aber im uebergebenen Arbeitsverzeichnis
    -- deshalb wird es hier mit cwd=repo aufgerufen und der Pfad zur
    Konfiguration bleibt der des Projekts.
    """
    return subprocess.run(
        [sys.executable, str(SKRIPT), "--log-opts=%s" % log_opts],
        cwd=repo, capture_output=True, text=True, timeout=120,
    )


def test_secret_im_dateinamen_wird_gefunden(tmp_path, monkeypatch):
    """Der Kernfall -- genau der reale Vorfall vom 25.06.2026."""
    schluessel = _synthetic_groq()
    repo = _repo(tmp_path, {".env%s" % schluessel: "PLACEHOLDER=nichts\n"})

    ergebnis = _scan(repo)
    assert ergebnis.returncode == 1, (
        "Ein Secret im Dateinamen muss zu Exit-Code 1 fuehren. Ausgabe:\n%s%s"
        % (ergebnis.stdout, ergebnis.stderr)
    )
    assert "ailiza-groq-api-key" in ergebnis.stdout


def test_gefundener_wert_erscheint_nie_in_der_ausgabe(tmp_path):
    """Datenschutzanforderung: der Wert darf nirgends stehen.

    Der Pfad IST hier der Fundort -- eine unredigierte Pfadausgabe waere
    das Geheimnis im Klartext, in einem fuer alle lesbaren CI-Protokoll.
    """
    schluessel = _synthetic_groq()
    repo = _repo(tmp_path, {".env%s" % schluessel: "PLACEHOLDER=nichts\n"})

    ergebnis = _scan(repo)
    gesamt = ergebnis.stdout + ergebnis.stderr

    assert schluessel not in gesamt, "Der vollstaendige Wert steht in der Ausgabe."
    # Auch kein aussagekraeftiges Teilstueck: 16 Zeichen genuegen bereits,
    # um einen Schluessel in einem Protokoll wiederzuerkennen.
    assert schluessel[4:20] not in gesamt, "Ein Teilstueck des Werts steht in der Ausgabe."
    assert "[REDIGIERT:" in gesamt, "Die Redaktionsmarkierung fehlt."


def test_sauberes_repo_meldet_keinen_fund(tmp_path):
    repo = _repo(tmp_path, {
        "apps/backend/main.py": "print('hallo')\n",
        "tests/test_x.py": "assert True\n",
    })
    ergebnis = _scan(repo)
    assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr
    assert "Kein Anbieter-Secret" in ergebnis.stdout


def test_spaeter_geloeschter_dateiname_wird_weiterhin_gefunden(tmp_path):
    """Umbenennen oder Loeschen entfernt den Namen nicht aus der Historie."""
    schluessel = _synthetic_groq()
    repo = _repo(tmp_path, {".env%s" % schluessel: "PLACEHOLDER=nichts\n"})
    _git(repo, "rm", "-q", ".env%s" % schluessel)
    _git(repo, "commit", "-qm", "Datei entfernt")

    assert not (repo / (".env%s" % schluessel)).exists()
    ergebnis = _scan(repo)
    assert ergebnis.returncode == 1, (
        "Ein geloeschter Dateiname steht weiter in der Historie und muss "
        "gefunden werden. Ausgabe:\n%s" % ergebnis.stdout
    )


def test_openrouter_muster_im_pfad_wird_gefunden(tmp_path):
    schluessel = "sk-or-v1-" + "".join(random.choice("0123456789abcdef") for _ in range(64))
    repo = _repo(tmp_path, {"config/%s.json" % schluessel: "{}\n"})
    ergebnis = _scan(repo)
    assert ergebnis.returncode == 1
    assert "ailiza-openrouter-api-key" in ergebnis.stdout


def test_regeln_stammen_aus_der_echten_konfiguration():
    """Eine zweite Musterliste im Skript wuerde unbemerkt abweichen.

    Zusaetzlich abgesichert: eine leere Regelmenge muss ein Fehler sein und
    darf nicht als "sauber" durchgehen.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import scan_pfadnamen_auf_secrets as skript

    regeln = skript.regeln_aus_config()
    assert "ailiza-groq-api-key" in regeln
    assert "ailiza-openrouter-api-key" in regeln
    # Die Entropie-Heuristik gehoert bewusst NICHT dazu -- auf Pfadnamen
    # angewandt erzeugt sie unbrauchbar viele Fehlalarme.
    assert "generic-api-key" not in regeln

    quelle = SKRIPT.read_text(encoding="utf-8")
    assert "tomllib" in quelle, (
        "Die Regeln muessen aus .gitleaks.toml gelesen werden, nicht im "
        "Skript dupliziert."
    )
