"""Selbsttests fuer den Secret-Scan (.gitleaks.toml + CI-Job "secret-scan").

Zweck: sicherstellen, dass der Scanner tatsaechlich findet, was er finden
soll -- und nicht stillschweigend "alles gut" meldet. Ohne diese Tests
koennte eine kaputte Regel oder eine zu breite Allowlist unbemerkt bleiben,
weil ein Scanner, der nichts findet, aeusserlich wie ein Scanner aussieht,
der nichts zu finden hat.

Alle Testwerte werden **erst zur Laufzeit** zusammengesetzt und
ausschliesslich in einem temporaeren Wegwerf-Repository committet. Es
steht bewusst kein schluesselaehnlicher Literalwert in dieser Datei --
sonst wuerde der Repository-Scan sich an seinen eigenen Testdaten
aufhaengen.

Die Tests werden uebersprungen, wenn gitleaks lokal nicht installiert ist
(Anleitung: docs/SECRET_SCAN_LOKAL.md). In der CI ist gitleaks im Job
"secret-scan" installiert; dort laufen sie verpflichtend mit.
"""
from __future__ import annotations

import json
import random
import shutil
import string
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / ".gitleaks.toml"

pytestmark = pytest.mark.skipif(
    shutil.which("gitleaks") is None,
    reason="gitleaks nicht installiert -- siehe docs/SECRET_SCAN_LOKAL.md",
)


def _rand(n: int, alphabet: str = string.ascii_letters + string.digits) -> str:
    return "".join(random.choice(alphabet) for _ in range(n))


def _synthetic_groq() -> str:
    """Groq-Format laut provider_registry.yaml: gsk_ + 52 Zeichen."""
    return "gsk_" + _rand(52)


def _synthetic_openrouter() -> str:
    return "sk-or-v1-" + _rand(64, "0123456789abcdef")


def _synthetic_github_pat() -> str:
    return "ghp_" + _rand(36)


def _synthetic_generic() -> str:
    """Hochentropisch, aber ohne Anbieter-Praefix."""
    return _rand(40)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "wegwerf"
    repo.mkdir()
    _git(repo, "init", "-q", ".")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    for rel, content in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "synthetische Testdaten")
    return repo


def _scan(repo: Path, log_opts: str = "--all -m") -> list[dict]:
    """Scannt das Wegwerf-Repo mit der echten AILIZA-Konfiguration.

    Der Standardwert enthaelt bewusst `-m` und NICHT `--no-merges` -- genau
    wie der CI-Job. Eine fruehere Fassung nutzte hier `--all --no-merges`;
    damit belegte der Merge-Test lediglich, dass ein ausdruecklich
    ausgeschlossener Merge nicht untersucht wird, und war als Nachweis
    wertlos.
    """
    report = repo / "report.json"
    subprocess.run(
        [
            "gitleaks", "git",
            "--config", str(CONFIG),
            "--log-opts", log_opts,
            "--redact",
            "--no-banner",
            "--report-format", "json",
            "--report-path", str(report),
            ".",
        ],
        cwd=repo,
        capture_output=True,
    )
    if not report.exists():
        return []
    raw = report.read_text(encoding="utf-8").strip()
    return json.loads(raw) if raw else []


def _rules_for(findings: list[dict], path: str) -> set[str]:
    return {f["RuleID"] for f in findings if f["File"] == path}


# ---------------------------------------------------------------------------
# 1. Anbieter-Schluessel in Produktivpfad -> muss gefunden werden
# ---------------------------------------------------------------------------

def test_groq_key_in_production_path_is_found(tmp_path):
    """Auch ohne schluesselaehnlichen Variablennamen.

    Die Heuristik generic-api-key wertet den Bezeichner-Kontext mit aus und
    faellt bei `wert = "gsk_..."` aus. Die eigene Groq-Regel greift am
    Format selbst und ist davon unabhaengig.
    """
    repo = _make_repo(tmp_path, {
        "apps/backend/prod.py": 'wert = "%s"\n' % _synthetic_groq(),
    })
    assert "ailiza-groq-api-key" in _rules_for(_scan(repo), "apps/backend/prod.py")


# ---------------------------------------------------------------------------
# 2. Anbieter-Schluessel in Testpfad -> muss trotz Allowlist gefunden werden
# ---------------------------------------------------------------------------

def test_groq_key_in_test_path_is_still_found(tmp_path):
    """Kernabsicherung: die generic-api-key-Allowlist fuer Testpfade darf
    anbieterspezifische Regeln NICHT mit abschalten."""
    repo = _make_repo(tmp_path, {
        "tests/test_beispiel.py": 'FAKE = "%s"\n' % _synthetic_groq(),
    })
    assert "ailiza-groq-api-key" in _rules_for(_scan(repo), "tests/test_beispiel.py")


def test_openrouter_key_in_test_path_is_still_found(tmp_path):
    repo = _make_repo(tmp_path, {
        "tests/test_beispiel.py": 'FAKE = "%s"\n' % _synthetic_openrouter(),
    })
    assert "ailiza-openrouter-api-key" in _rules_for(_scan(repo), "tests/test_beispiel.py")


def test_default_provider_rule_in_test_path_is_still_found(tmp_path):
    """Gegenprobe mit einer mitgelieferten Regel (github-pat)."""
    repo = _make_repo(tmp_path, {
        "tests/test_beispiel.py": 'TOKEN = "%s"\n' % _synthetic_github_pat(),
    })
    assert "github-pat" in _rules_for(_scan(repo), "tests/test_beispiel.py")


# ---------------------------------------------------------------------------
# 3. Allowlist wirkt -- aber nur dort, wo sie soll
# ---------------------------------------------------------------------------

def test_generic_heuristic_suppressed_in_test_path(tmp_path):
    repo = _make_repo(tmp_path, {
        "tests/test_beispiel.py": 'API_KEY = "%s"\n' % _synthetic_generic(),
    })
    assert _rules_for(_scan(repo), "tests/test_beispiel.py") == set()


def test_generic_heuristic_active_outside_test_paths(tmp_path):
    """Gegenprobe: ohne diesen Test koennte die Allowlist unbemerkt auf das
    ganze Repository ausgeweitet werden."""
    repo = _make_repo(tmp_path, {
        "apps/backend/prod.py": 'API_KEY = "%s"\n' % _synthetic_generic(),
    })
    assert "generic-api-key" in _rules_for(_scan(repo), "apps/backend/prod.py")


# ---------------------------------------------------------------------------
# 4. Historie statt Dateistand: hinzugefuegt und wieder geloescht
# ---------------------------------------------------------------------------

def test_secret_added_then_deleted_is_still_found(tmp_path):
    """Der eigentliche Grund fuer den Commit-Bereichs-Scan.

    Nach dem zweiten Commit steht der Schluessel in keiner Datei mehr --
    aber dauerhaft in der Historie. Ein Scan des Dateistands wuerde ihn
    verfehlen.
    """
    repo = _make_repo(tmp_path, {
        "apps/backend/prod.py": 'GROQ_API_KEY = "%s"\n' % _synthetic_groq(),
    })
    (repo / "apps" / "backend" / "prod.py").write_text("# entfernt\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "Schluessel wieder entfernt")

    assert "GROQ_API_KEY" not in (repo / "apps" / "backend" / "prod.py").read_text()
    findings = _scan(repo)
    assert any(f["RuleID"] == "ailiza-groq-api-key" for f in findings)


# ---------------------------------------------------------------------------
# 5. Merge-Aufloesung: nur der Dateistand-Scan findet sie
# ---------------------------------------------------------------------------

def _scan_dir(repo: Path) -> list[dict]:
    report = repo / "dir_report.json"
    subprocess.run(
        [
            "gitleaks", "dir",
            "--config", str(CONFIG),
            "--redact", "--no-banner",
            "--report-format", "json",
            "--report-path", str(report),
            ".",
        ],
        cwd=repo,
        capture_output=True,
    )
    if not report.exists():
        return []
    raw = report.read_text(encoding="utf-8").strip()
    return json.loads(raw) if raw else []


def _repo_mit_merge_secret(tmp_path: Path, name: str) -> Path:
    """Baut ein Repo, in dem ein Secret ERST bei der Konfliktaufloesung
    entsteht -- es steht damit in keinem der zusammengefuehrten Commits,
    sondern ausschliesslich im Merge-Commit selbst."""
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main", ".")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    datei = repo / "datei.py"
    datei.write_text("zeile\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "basis")

    _git(repo, "checkout", "-q", "-b", "feature")
    datei.write_text("feature-variante\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "feature")

    _git(repo, "checkout", "-q", "main")
    datei.write_text("main-variante\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "main")

    _git(repo, "checkout", "-q", "feature")
    subprocess.run(["git", "merge", "main", "-q"], cwd=repo, capture_output=True)
    datei.write_text('GROQ_API_KEY = "%s"\n' % _synthetic_groq(), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "merge aufgeloest")
    return repo


def test_merge_resolution_secret_requires_the_m_flag(tmp_path):
    """Kernabsicherung fuer das `-m` im CI-Job.

    `git log` zeigt fuer Merge-Commits ohne `-m` gar keinen Diff. Ein
    Secret, das erst bei der Konfliktaufloesung entsteht, ist damit
    unsichtbar -- auch bei `--all`. Erst `-m` macht es sichtbar.

    Dieser Test vergleicht die Varianten ausdruecklich gegeneinander.
    Eine fruehere Fassung rief nur den Standard `--all --no-merges` auf und
    belegte damit lediglich, dass ein ausgeschlossener Merge nicht
    untersucht wird -- als Nachweis wertlos.
    """
    repo = _repo_mit_merge_secret(tmp_path, "merge_m_flag")

    ohne_flag = {f["RuleID"] for f in _scan(repo, log_opts="--all")}
    ohne_merges = {f["RuleID"] for f in _scan(repo, log_opts="--all --no-merges")}
    mit_m = {f["RuleID"] for f in _scan(repo, log_opts="--all -m")}

    assert "ailiza-groq-api-key" in mit_m, (
        "Mit -m muss die Merge-Aufloesung geprueft werden -- genau darauf "
        "stuetzt sich der CI-Job."
    )
    assert "ailiza-groq-api-key" not in ohne_merges, (
        "Mit --no-merges darf der Merge nicht geprueft werden; sonst sagt "
        "der Vergleich in diesem Test nichts aus."
    )
    assert "ailiza-groq-api-key" not in ohne_flag, (
        "Ohne -m findet gitleaks Merge-Aufloesungen jetzt doch. Das waere "
        "eine gute Nachricht -- dann kann das -m im CI-Job neu bewertet "
        "werden. Bis dahin ist es noetig."
    )


def test_merge_secret_deleted_later_is_missed_without_the_m_flag(tmp_path):
    """Die Kombination, die BEIDE Scans einzeln verfehlen.

    Entsteht ein Secret bei einer Merge-Aufloesung und wird es in einem
    spaeteren Commit wieder geloescht, dann
      - sieht der Dateistand-Scan es nicht mehr (aus dem Baum entfernt) und
      - sieht der git-Modus es ohne `-m` ebenfalls nicht.
    Nur `-m` faengt diesen Fall. Ohne diesen Test koennte das `-m` im
    CI-Job spaeter als ueberfluessig entfernt werden.
    """
    repo = _repo_mit_merge_secret(tmp_path, "merge_dann_geloescht")
    (repo / "datei.py").write_text("# entfernt\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "secret wieder entfernt")

    assert "ailiza-groq-api-key" in {f["RuleID"] for f in _scan(repo, log_opts="--all -m")}, (
        "Mit -m muss dieser Fall gefunden werden -- er ist der einzige "
        "Schutz dagegen."
    )
    assert "ailiza-groq-api-key" not in {
        f["RuleID"] for f in _scan(repo, log_opts="--all --no-merges")
    }
    assert "ailiza-groq-api-key" not in {f["RuleID"] for f in _scan_dir(repo)}, (
        "Der Dateistand-Scan kann diesen Fall nicht abdecken -- das ist "
        "der Grund, warum beide Scans noetig sind."
    )


# ---------------------------------------------------------------------------
# 6. Bekannte Grenze: Secrets in DATEINAMEN
# ---------------------------------------------------------------------------

def test_known_limitation_secret_in_filename_is_not_detected(tmp_path):
    """Haelt eine reale, nicht behebbare Grenze sichtbar.

    gitleaks prueft ausschliesslich Datei-INHALTE, nicht Dateinamen --
    gemessen am 26.08.2026 gegen 8.28.0, in beiden Modi (`git` und `dir`).
    Ein Schluessel, der im Dateinamen steht, bleibt damit unentdeckt,
    unabhaengig von jeder Regex.

    Das ist kein theoretischer Fall: genau so ist der in
    `06_release/SECURITY_INCIDENT_2026-06-25.md` dokumentierte Vorfall
    entstanden -- der Schluessel stand im Dateinamen, der Dateiinhalt war
    nur ein Platzhalter.

    Dieser Test schlaegt bewusst NICHT fehl, solange die Grenze besteht.
    Faengt gitleaks eines Tages auch Dateinamen, wird er rot -- dann ist
    die Grenze aufgehoben und diese Dokumentation zu aktualisieren.
    """
    schluessel = _synthetic_groq()
    repo = _make_repo(tmp_path, {
        ".env%s" % schluessel: "PLACEHOLDER=nichts\n",
    })

    aus_historie = {f["RuleID"] for f in _scan(repo)}
    aus_dateistand = {f["RuleID"] for f in _scan_dir(repo)}

    assert "ailiza-groq-api-key" not in aus_historie, (
        "gitleaks findet Secrets in Dateinamen jetzt im git-Modus -- gute "
        "Nachricht. Grenze in .gitleaks.toml und in der Push-Regel "
        "entsprechend aktualisieren."
    )
    assert "ailiza-groq-api-key" not in aus_dateistand, (
        "gitleaks findet Secrets in Dateinamen jetzt im dir-Modus -- gute "
        "Nachricht. Grenze entsprechend aktualisieren."
    )

    # Gegenprobe: derselbe Schluessel IM INHALT wird sehr wohl gefunden.
    # Ohne sie koennte der Test auch dann bestehen, wenn die Groq-Regel
    # insgesamt kaputt waere.
    zweiter = tmp_path / "inhalt"
    zweiter.mkdir()
    repo2 = _make_repo(zweiter, {
        "apps/backend/x.py": 'KEY = "%s"\n' % schluessel,
    })
    assert "ailiza-groq-api-key" in {f["RuleID"] for f in _scan(repo2)}, (
        "Derselbe Schluessel muss im Dateiinhalt gefunden werden -- sonst "
        "sagt der Test oben nichts ueber Dateinamen aus."
    )


# ---------------------------------------------------------------------------
# 7. Konfiguration selbst
# ---------------------------------------------------------------------------

def test_allowlist_is_bound_to_a_single_rule(tmp_path):
    """Die Testpfad-Allowlist muss unter [[rules]] stehen, nicht global.

    Eine globale Allowlist wuerde SAEMTLICHE Regeln fuer den Pfad
    abschalten. `targetRules` als Einschraenkung wirkt in gitleaks 8.28.0
    nicht (gemessen am 26.08.2026) -- deshalb ist die Bindung an die
    Regel-ID der einzige tragfaehige Schnitt.
    """
    text = CONFIG.read_text(encoding="utf-8")
    assert "[[rules.allowlists]]" in text, "Allowlist muss regelgebunden sein"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert stripped != "[[allowlists]]", (
            "Globale Allowlist gefunden -- sie wuerde alle Regeln fuer den "
            "Pfad abschalten, auch die anbieterspezifischen."
        )


def test_every_used_provider_has_a_detection_rule():
    """Neuer Anbieter ohne Erkennungsregel soll hier auffallen.

    gitleaks 8.28.0 bringt Regeln fuer OpenAI und Anthropic mit, aber
    KEINE fuer Groq und KEINE fuer OpenRouter -- die zwei fehlenden sind
    deshalb in .gitleaks.toml selbst definiert.
    """
    registry = REPO_ROOT / "apps" / "backend" / "registry" / "provider_registry.yaml"
    config = CONFIG.read_text(encoding="utf-8")

    known = {
        "groq": "ailiza-groq-api-key",      # eigene Regel
        "openrouter": "ailiza-openrouter-api-key",  # eigene Regel
        "openai": None,                      # gitleaks-Standardregel
        "anthropic": None,                   # gitleaks-Standardregel
        "local": None,                       # kein externer Schluessel
    }

    text = registry.read_text(encoding="utf-8")
    in_providers = False
    found: list[str] = []
    for line in text.splitlines():
        if line.startswith("providers:"):
            in_providers = True
            continue
        if in_providers and line.startswith("  ") and line.strip().endswith(":") \
                and not line.startswith("    "):
            found.append(line.strip().rstrip(":"))

    unknown = [p for p in found if p not in known]
    assert not unknown, (
        "Neuer Provider ohne geklaerte Secret-Scan-Abdeckung: %s. Pruefen, ob "
        "gitleaks eine Regel mitbringt -- falls nicht, eigene Regel in "
        ".gitleaks.toml ergaenzen und hier eintragen." % unknown
    )

    for provider, own_rule in known.items():
        if own_rule is not None:
            assert own_rule in config, (
                "Eigene Regel %s fuer Provider %s fehlt in .gitleaks.toml"
                % (own_rule, provider)
            )
