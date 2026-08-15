"""
CLI-Entrypoint fuer den Produktions-Audit der Memory-Scope-/Owner-/Tenant-
Invarianten (apps/backend/audit_memory_scope_cli.py).

Prueft NUR das Script selbst (Exit-Codes, Text-/JSON-Ausgabe, kein
Datenschreibzugriff) -- die inhaltliche Korrektheit der zugrundeliegenden
audit_memory_scope_invariants()-Funktion ist bereits in
tests/test_memory_scope_owner_tenant_invariants.py abgedeckt.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "apps" / "backend" / "audit_memory_scope_cli.py"


def _run_script(db_url: str, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(extra_args or [])],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=30,
    )


def test_script_exists_and_is_python():
    assert SCRIPT.exists()
    assert SCRIPT.read_text(encoding="utf-8").startswith('"""')


def _init_schema_only(db_url: str) -> None:
    """Legt das Schema separat vom CLI-Aufruf an -- das Audit selbst darf
    das seit der Read-only-Haertung nicht mehr tun (siehe
    test_script_never_calls_init_db_or_creates_schema)."""
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    setup = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.database import init_db
init_db()
"""
    subprocess.run([sys.executable, "-c", setup], env=env, capture_output=True, text=True, check=True, timeout=30)


def test_clean_db_exits_zero_and_reports_no_violations(tmp_path):
    db_path = tmp_path / "clean.db"
    db_url = f"sqlite:///{db_path}"
    _init_schema_only(db_url)
    result = _run_script(db_url)
    assert result.returncode == 0, result.stderr
    assert "Keine Invarianten-Verletzungen" in result.stdout


def test_missing_database_file_does_not_create_it(tmp_path):
    """Gate 1: eine nicht existierende Datenbankdatei darf durch das Audit
    NICHT angelegt werden. Eine gewoehnliche SQLite-Verbindung (auch eine
    rein lesende `inspect()`-Anfrage ueber die Standard-Engine) legt eine
    fehlende Datei beim Verbindungsaufbau selbst an -- das war die
    tatsaechliche Ursache des urspruenglichen Schreibpotenzials, auch nach
    Entfernen von init_db() aus dem Auditpfad. Der Dateisystem-Check muss
    JEDER Verbindung vorausgehen."""
    db_path = tmp_path / "ghost.db"
    db_url = f"sqlite:///{db_path}"
    assert not db_path.exists()

    result = _run_script(db_url)

    assert result.returncode == 2, result.stdout
    assert "Datenbankdatei nicht gefunden" in result.stderr
    assert not db_path.exists(), (
        "Das Audit hat trotz fehlender Datenbank eine Datei angelegt"
    )


def test_missing_schema_exits_two_without_creating_it(tmp_path):
    """Kernverhalten der Read-only-Haertung: eine (existierende, aber
    leere) Datenbank ohne memory_items/memory_visibility darf NICHT
    repariert werden -- das Audit muss verstaendlich abbrechen, statt das
    Schema selbst anzulegen."""
    db_path = tmp_path / "no_schema.db"
    db_url = f"sqlite:///{db_path}"
    # Datei existiert (leer, ohne Schema) -- unterscheidet diesen Fall
    # bewusst von test_missing_database_file_does_not_create_it oben.
    db_path.touch()

    result = _run_script(db_url)
    assert result.returncode == 2, result.stdout
    assert "Tabelle(n) fehlen" in result.stderr
    assert "memory_items" in result.stderr
    # Beweis, dass das Audit selbst nichts angelegt hat: eine frische
    # Verbindung sieht weiterhin keine memory_items-Tabelle.
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    check = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from sqlalchemy import create_engine, inspect
eng = create_engine({db_url!r})
assert not inspect(eng).has_table("memory_items"), "Audit hat trotz Read-only-Fix Schema angelegt"
print("OK")
"""
    check_result = subprocess.run(
        [sys.executable, "-c", check], env=env, capture_output=True, text=True, timeout=30,
    )
    assert check_result.returncode == 0, check_result.stderr
    assert "OK" in check_result.stdout


def test_violation_exits_one_and_lists_violation_in_text_output(tmp_path):
    db_path = tmp_path / "violation.db"
    db_url = f"sqlite:///{db_path}"
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    setup = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.database import init_db, engine, memory_items
from sqlalchemy import insert
from datetime import datetime, timezone
init_db()
now = datetime.now(timezone.utc)
with engine.begin() as conn:
    conn.execute(insert(memory_items).values(
        tenant_id="default", scope="company_memory", owner_user_id="sollte_leer_sein",
        title="invalid", content="c", purpose="p", source_id=None,
        status="active", created_at=now, updated_at=now,
    ))
"""
    subprocess.run([sys.executable, "-c", setup], env=env, capture_output=True, text=True, check=True, timeout=30)

    result = _run_script(db_url)
    assert result.returncode == 1, result.stderr
    assert "INVARIANTEN VERLETZT" in result.stdout
    assert "company_memory_with_owner" in result.stdout


def test_violation_json_output_is_valid_and_machine_readable(tmp_path):
    db_path = tmp_path / "violation_json.db"
    db_url = f"sqlite:///{db_path}"
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    setup = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.database import init_db, engine, memory_items
from sqlalchemy import insert
from datetime import datetime, timezone
init_db()
now = datetime.now(timezone.utc)
with engine.begin() as conn:
    conn.execute(insert(memory_items).values(
        tenant_id=None, scope="company_memory", owner_user_id=None,
        title="invalid", content="c", purpose="p", source_id=None,
        status="active", created_at=now, updated_at=now,
    ))
"""
    subprocess.run([sys.executable, "-c", setup], env=env, capture_output=True, text=True, check=True, timeout=30)

    result = _run_script(db_url, ["--json"])
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["has_violations"] is True
    assert len(report["violations"]["company_memory_missing_tenant"]) == 1


def test_script_never_mutates_data_even_on_violation(tmp_path):
    """End-to-End-Beweis (nicht nur Code-Lesung): zweimaliger Aufruf des
    Scripts liefert denselben Bericht -- kein Reparatur-/Nebeneffekt."""
    db_path = tmp_path / "idempotent.db"
    db_url = f"sqlite:///{db_path}"
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    setup = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.database import init_db, engine, memory_items
from sqlalchemy import insert
from datetime import datetime, timezone
init_db()
now = datetime.now(timezone.utc)
with engine.begin() as conn:
    conn.execute(insert(memory_items).values(
        tenant_id="default", scope="company_memory", owner_user_id="x",
        title="invalid", content="c", purpose="p", source_id=None,
        status="active", created_at=now, updated_at=now,
    ))
"""
    subprocess.run([sys.executable, "-c", setup], env=env, capture_output=True, text=True, check=True, timeout=30)

    first = _run_script(db_url, ["--json"])
    second = _run_script(db_url, ["--json"])
    first_report = json.loads(first.stdout)
    second_report = json.loads(second.stdout)
    assert first_report["total_memory_items"] == second_report["total_memory_items"] == 1
    assert first_report["violations"] == second_report["violations"]


def test_unreachable_database_exits_two():
    """Fehler beim Ausfuehren (z.B. ungueltige/nicht erreichbare
    Datenbank-URL) -> Exit-Code 2, nicht 0 oder 1 (unterscheidbar von
    'kein Problem' / 'Verletzung gefunden')."""
    result = _run_script("postgresql+psycopg://user:pass@nonexistent-host-xyz.invalid:5432/db")
    assert result.returncode == 2


# ── --summary-only: keine internen ID-Listen in oeffentlich einsehbaren Logs ─

def test_summary_only_json_omits_id_lists(tmp_path):
    db_path = tmp_path / "summary_violation.db"
    db_url = f"sqlite:///{db_path}"
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    setup = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.database import init_db, engine, memory_items
from sqlalchemy import insert
from datetime import datetime, timezone
init_db()
now = datetime.now(timezone.utc)
with engine.begin() as conn:
    conn.execute(insert(memory_items).values(
        tenant_id="default", scope="company_memory", owner_user_id="sollte_leer_sein",
        title="invalid", content="c", purpose="p", source_id=None,
        status="active", created_at=now, updated_at=now,
    ))
"""
    subprocess.run([sys.executable, "-c", setup], env=env, capture_output=True, text=True, check=True, timeout=30)

    result = _run_script(db_url, ["--json", "--summary-only"])
    assert result.returncode == 1, result.stderr
    report = json.loads(result.stdout)
    assert report["has_violations"] is True
    # Zaehlwert bleibt erhalten ...
    assert report["violations"]["company_memory_with_owner"] == 1
    # ... aber KEINE ID-Liste -- der Wert ist ein Integer, keine Liste.
    assert isinstance(report["violations"]["company_memory_with_owner"], int)
    # Auch als Rohtext darf keine erkennbare ID-Listen-Klammer auftauchen
    # (Regressionsschutz: stellt sicher, dass niemand versehentlich doch
    # eine Liste serialisiert).
    assert "[1]" not in result.stdout


def test_summary_only_text_output_has_no_id_list_suffix(tmp_path):
    db_path = tmp_path / "summary_violation_text.db"
    db_url = f"sqlite:///{db_path}"
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    setup = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.database import init_db, engine, memory_items
from sqlalchemy import insert
from datetime import datetime, timezone
init_db()
now = datetime.now(timezone.utc)
with engine.begin() as conn:
    conn.execute(insert(memory_items).values(
        tenant_id="default", scope="company_memory", owner_user_id="sollte_leer_sein",
        title="invalid", content="c", purpose="p", source_id=None,
        status="active", created_at=now, updated_at=now,
    ))
"""
    subprocess.run([sys.executable, "-c", setup], env=env, capture_output=True, text=True, check=True, timeout=30)

    result = _run_script(db_url, ["--summary-only"])
    assert result.returncode == 1, result.stderr
    assert "company_memory_with_owner: 1 Treffer" in result.stdout
    assert "--" not in result.stdout.split("company_memory_with_owner")[1].split("\n")[0]


def test_summary_only_clean_db_still_exits_zero(tmp_path):
    db_path = tmp_path / "summary_clean.db"
    db_url = f"sqlite:///{db_path}"
    _init_schema_only(db_url)
    result = _run_script(db_url, ["--summary-only", "--json"])
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["has_violations"] is False


# ── Regression: Produktions-Audit-Run #1 (Workflow-Run 30626472529, Exit 2) ─
# Ursache: database.py importiert transitiv "cryptography"
# (governance/field_crypto.py). Fehlte dieses Paket in der Minimal-
# Installation des Workflows, warf "from database import ..." ein
# ImportError -- der damalige Fallback "from apps.backend.database import
# ..." schlug ZUSAETZLICH fehl, weil das Repo-Root beim direkten
# Skriptaufruf nicht automatisch in sys.path liegt (nur das Skript-
# Verzeichnis selbst). Das erzeugte die irrefuehrende Meldung
# "ModuleNotFoundError: No module named 'apps'" statt des eigentlichen
# Fehlers. Fix: Repo-Root wird jetzt explizit ueber __file__ (nicht cwd)
# in sys.path eingefuegt + "cryptography" in der Workflow-Installation
# ergaenzt.

def test_script_works_regardless_of_caller_cwd(tmp_path):
    """Der Importpfad darf nicht vom Arbeitsverzeichnis des Aufrufers
    abhaengen -- nur vom tatsaechlichen Speicherort des Skripts. Simuliert
    exakt den Fall, der im Produktions-Workflow (Run 30626472529) zum
    irrefuehrenden 'No module named apps'-Fehler fuehrte."""
    db_url = f"sqlite:///{tmp_path / 'cwd_test.db'}"
    _init_schema_only(db_url)
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    other_cwd = tmp_path / "not_the_repo_root"
    other_cwd.mkdir()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--summary-only", "--json"],
        cwd=other_cwd, env=env, capture_output=True, text=True, timeout=30,
    )
    assert "No module named 'apps'" not in result.stderr
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["has_violations"] is False


# ── Gate 1: dedizierte Read-only-SQLite-Verbindung (mode=ro + query_only) ────

def test_readonly_connection_rejects_a_deliberate_write(tmp_path):
    """Gegenprobe/Schutztest: beweist nicht nur, dass der Audit-Code selbst
    keine schreibende Anweisung absetzt (das leistet
    test_audit_run_issues_no_write_sql_statements unten), sondern dass ein
    Schreibversuch UEBER DIESELBE Read-only-Verbindung, die das Audit
    verwendet, technisch abgewiesen wird -- unabhaengig davon, ob der
    Audit-Code selbst fehlerfrei ist. Zwei unabhaengige Schranken:
    URI mode=ro UND PRAGMA query_only."""
    db_path = tmp_path / "protected.db"
    db_url = f"sqlite:///{db_path}"
    _init_schema_only(db_url)

    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    script = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.audit_memory_scope_cli import _open_readonly_sqlite_engine
from apps.backend.database import memory_items
from sqlalchemy import insert
from sqlalchemy.exc import OperationalError
from datetime import datetime, timezone

ro_engine = _open_readonly_sqlite_engine({str(db_path)!r})
now = datetime.now(timezone.utc)
try:
    with ro_engine.connect() as conn:
        conn.execute(insert(memory_items).values(
            tenant_id="default", scope="company_memory", owner_user_id=None,
            title="t", content="c", purpose="p", source_id=None,
            status="active", created_at=now, updated_at=now,
        ))
        conn.commit()
    print("SCHREIBVERSUCH_ERFOLGREICH")
except OperationalError as exc:
    print(f"SCHREIBVERSUCH_ABGEWIESEN: {{exc}}")
finally:
    ro_engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, cwd=REPO_ROOT,
        capture_output=True, text=True, timeout=30,
    )
    assert "SCHREIBVERSUCH_ABGEWIESEN" in result.stdout, (
        f"Read-only-Schutz hat einen Schreibversuch NICHT abgewiesen: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "readonly" in result.stdout.lower() or "read-only" in result.stdout.lower()


def test_readonly_engine_uses_separate_connection_from_app_engine(tmp_path):
    """Regressionsschutz: die dedizierte Read-only-Engine darf die
    schreibfaehige, anwendungsweite `engine` aus database.py nicht
    ersetzen oder beeinflussen -- nur ein zusaetzlicher, unabhaengiger
    Verbindungsweg fuer den Audit-Lauf."""
    db_path = tmp_path / "separate.db"
    db_url = f"sqlite:///{db_path}"
    _init_schema_only(db_url)

    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    script = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.audit_memory_scope_cli import _open_readonly_sqlite_engine
from apps.backend.database import engine as app_engine
ro_engine = _open_readonly_sqlite_engine({str(db_path)!r})
assert ro_engine is not app_engine
assert ro_engine.url != app_engine.url
ro_engine.dispose()
print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, cwd=REPO_ROOT,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# ── Gate 1A: technischer Beweis auf SQL-Anweisungsebene, nicht nur Endzustand ─

_WRITE_KEYWORDS = ("CREATE", "ALTER", "DROP", "INSERT", "UPDATE", "DELETE", "REPLACE", "VACUUM", "ATTACH", "DETACH")


def test_script_never_calls_init_db_or_creates_schema():
    """Statischer Beleg: das CLI darf init_db() (create_all/ensure_sqlite_schema)
    nicht mehr aufrufen -- das war die Ursache der urspruenglichen
    Read-only-Verletzung. Prueft nur ausfuehrbaren Code, keine Kommentare/
    Docstrings (die duerfen den Namen zur Erklaerung erwaehnen)."""
    content = SCRIPT.read_text(encoding="utf-8")
    code_lines = [
        line for line in content.splitlines()
        if not line.strip().startswith("#") and '"""' not in line
    ]
    code_only = "\n".join(code_lines)
    assert "init_db(" not in code_only
    assert "import init_db" not in code_only


def test_audit_run_issues_no_write_sql_statements(tmp_path):
    """Beweist die tatsaechlich abgesetzten SQL-Anweisungen, nicht nur den
    Endzustand der Datenbank: audit_memory_scope_invariants() darf niemals
    CREATE/ALTER/DROP/INSERT/UPDATE/DELETE ausloesen, auch nicht bei bereits
    vorhandenem Schema mit Verletzungen. Laeuft bewusst als eigener
    Subprozess (wie alle anderen Tests dieser Datei) -- ein reload() des
    Datenbankmoduls im Testprozess wuerde die globale Engine verseuchen und
    andere Tests in derselben pytest-Session zum Scheitern bringen."""
    db_path = tmp_path / "sql_proof.db"
    db_url = f"sqlite:///{db_path}"
    _init_schema_only(db_url)

    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"

    script = f"""
import sys, json
sys.path.insert(0, {str(REPO_ROOT)!r})
from datetime import datetime, timezone
from sqlalchemy import event, insert
from apps.backend.database import engine, memory_items, audit_memory_scope_invariants

now = datetime.now(timezone.utc)
with engine.begin() as conn:
    conn.execute(insert(memory_items).values(
        tenant_id="default", scope="company_memory", owner_user_id="sollte_leer_sein",
        title="invalid", content="c", purpose="p", source_id=None,
        status="active", created_at=now, updated_at=now,
    ))

statements = []

def _capture(conn, cursor, statement, parameters, context, executemany):
    statements.append(statement)

event.listen(engine, "before_cursor_execute", _capture)
try:
    audit_memory_scope_invariants()
finally:
    event.remove(engine, "before_cursor_execute", _capture)

print("STATEMENTS_JSON_START")
print(json.dumps(statements))
print("STATEMENTS_JSON_END")
"""
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, cwd=REPO_ROOT,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    stdout = result.stdout
    payload = stdout.split("STATEMENTS_JSON_START\n", 1)[1].split("\nSTATEMENTS_JSON_END", 1)[0]
    statements = json.loads(payload)

    assert statements, "Es wurden gar keine SQL-Anweisungen erfasst -- Test greift nicht"
    for stmt in statements:
        upper = stmt.strip().upper()
        for keyword in _WRITE_KEYWORDS:
            assert not upper.startswith(keyword), f"Schreibende Anweisung entdeckt: {stmt!r}"


def test_audit_via_readonly_connection_issues_no_write_sql_statements(tmp_path):
    """Wie test_audit_run_issues_no_write_sql_statements oben, aber ueber
    GENAU die dedizierte Read-only-Verbindung, die das CLI tatsaechlich
    fuer den Audit-Lauf verwendet (nicht die schreibfaehige App-Engine)."""
    db_path = tmp_path / "sql_proof_ro.db"
    db_url = f"sqlite:///{db_path}"
    _init_schema_only(db_url)

    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"

    setup = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.database import init_db, engine, memory_items
from sqlalchemy import insert
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
with engine.begin() as conn:
    conn.execute(insert(memory_items).values(
        tenant_id="default", scope="company_memory", owner_user_id="sollte_leer_sein",
        title="invalid", content="c", purpose="p", source_id=None,
        status="active", created_at=now, updated_at=now,
    ))
"""
    subprocess.run([sys.executable, "-c", setup], env=env, capture_output=True, text=True, check=True, timeout=30)

    script = f"""
import sys, json
sys.path.insert(0, {str(REPO_ROOT)!r})
from sqlalchemy import event
from apps.backend.audit_memory_scope_cli import _open_readonly_sqlite_engine
from apps.backend.database import audit_memory_scope_invariants

ro_engine = _open_readonly_sqlite_engine({str(db_path)!r})
statements = []

def _capture(conn, cursor, statement, parameters, context, executemany):
    statements.append(statement)

event.listen(ro_engine, "before_cursor_execute", _capture)
try:
    with ro_engine.connect() as conn:
        audit_memory_scope_invariants(conn=conn)
finally:
    event.remove(ro_engine, "before_cursor_execute", _capture)
    ro_engine.dispose()

print("STATEMENTS_JSON_START")
print(json.dumps(statements))
print("STATEMENTS_JSON_END")
"""
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, cwd=REPO_ROOT,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = result.stdout.split("STATEMENTS_JSON_START\n", 1)[1].split("\nSTATEMENTS_JSON_END", 1)[0]
    statements = json.loads(payload)

    assert statements, "Es wurden gar keine SQL-Anweisungen erfasst -- Test greift nicht"
    for stmt in statements:
        upper = stmt.strip().upper()
        for keyword in _WRITE_KEYWORDS:
            assert not upper.startswith(keyword), f"Schreibende Anweisung entdeckt: {stmt!r}"


def test_output_contains_no_raw_secret_or_content(tmp_path):
    """Anforderung 8: die Audit-Ausgabe darf niemals Rohinhalte (title/
    content/purpose) oder darin enthaltene Test-Secrets ausgeben -- nur
    Zaehlwerte, technische IDs und die fuer die Diagnose zwingend
    benoetigten owner_user_id/tenant_id-Werte."""
    GEHEIM = "sk-test-audit-secret-nicht-echt-24680"
    db_path = tmp_path / "secret_content.db"
    db_url = f"sqlite:///{db_path}"
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    setup = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.database import init_db, engine, memory_items
from sqlalchemy import insert
from datetime import datetime, timezone
init_db()
now = datetime.now(timezone.utc)
with engine.begin() as conn:
    conn.execute(insert(memory_items).values(
        tenant_id="default", scope="company_memory", owner_user_id="sollte_leer_sein",
        title="Zugangsdaten", content="api_key={GEHEIM!r}", purpose="Geheimnisverwaltung",
        source_id=None, status="active", created_at=now, updated_at=now,
    ))
"""
    subprocess.run([sys.executable, "-c", setup], env=env, capture_output=True, text=True, check=True, timeout=30)

    for extra_args in ([], ["--json"], ["--summary-only", "--json"]):
        result = _run_script(db_url, extra_args)
        assert GEHEIM not in result.stdout
        assert GEHEIM not in result.stderr
        assert "Zugangsdaten" not in result.stdout
        assert "Geheimnisverwaltung" not in result.stdout


# ── Gate 1 Phase 3: PostgreSQL Read-only-Schranke (separat, nicht in CI) ────
#
# Diese Tests laufen NUR, wenn AILIZA_TEST_POSTGRES_ADMIN_URL gesetzt ist --
# eine Verbindung mit CREATEDB-Recht auf eine LOKALE/ISOLIERTE Testinstanz,
# NIEMALS Render/Neon. Ohne diese Variable werden sie uebersprungen (auch
# in CI, wo kein PostgreSQL-Service konfiguriert ist) -- bewusst getrennt
# vom Standard-Testlauf, wie von Karo verlangt ("PostgreSQL-Testumgebung
# getrennt pruefen").

import contextlib

_PG_ADMIN_URL = os.environ.get("AILIZA_TEST_POSTGRES_ADMIN_URL")

pg_only = pytest.mark.skipif(
    not _PG_ADMIN_URL,
    reason="AILIZA_TEST_POSTGRES_ADMIN_URL nicht gesetzt -- PostgreSQL-Tests "
    "laufen nur explizit gegen eine lokale/isolierte Testinstanz.",
)


@contextlib.contextmanager
def _fresh_postgres_database(name: str):
    """Legt ueber die Admin-URL eine frische, isolierte Testdatenbank an
    und loescht sie danach wieder -- niemals Render/Neon, ausschliesslich
    die in AILIZA_TEST_POSTGRES_ADMIN_URL konfigurierte lokale Instanz."""
    import psycopg
    from urllib.parse import urlsplit, urlunsplit

    admin = psycopg.connect(_PG_ADMIN_URL.replace("postgresql+psycopg://", "postgresql://"))
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}"')
            cur.execute(f'CREATE DATABASE "{name}"')
        parts = urlsplit(_PG_ADMIN_URL)
        db_url = urlunsplit(parts._replace(path=f"/{name}"))
        try:
            yield db_url
        finally:
            with admin.cursor() as cur:
                cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        admin.close()


def _pg_init_schema(db_url: str) -> None:
    """Erzeugt das Testschema AUSSCHLIESSLICH ueber `alembic upgrade head`
    -- kein Ersatzweg. Render/Neon wird in der Praxis ausschliesslich per
    Migration aufgesetzt, nie per `init_db()`/`create_all()`; ein Fallback
    auf die SQLAlchemy-Metadata-Variante wuerde bei einem echten Alembic-
    Fehler (z.B. einer defekten Migration) stillschweigend ein anderes,
    nicht repraesentatives Schema erzeugen und den eigentlichen Fehler
    verdecken, statt den Test fehlschlagen zu lassen. Scheitert Alembic,
    schlaegt dieser Aufruf deshalb sofort fehl (AssertionError) -- kein
    automatischer Rueckfall auf init_db()/create_all()/
    ensure_sqlite_schema().

    Die Fehlermeldung enthaelt bewusst NICHT die volle stderr-Ausgabe
    (koennte die Datenbank-URL/Zugangsdaten aus der Alembic-Log-Ausgabe
    enthalten), sondern nur den Exit-Code und die letzten Codezeilen."""
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = db_url
    env["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"

    alembic_result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT / "apps" / "backend", env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert alembic_result.returncode == 0, (
        f"alembic upgrade head fehlgeschlagen (Exit {alembic_result.returncode}) "
        "-- kein Fallback auf init_db(). Siehe CI-Logausgabe von "
        "'alembic upgrade head' fuer Details (dort ggf. Verbindungsdetails "
        "sichtbar, deshalb hier nicht wiederholt)."
    )


@pg_only
def test_postgres_readonly_connection_rejects_a_deliberate_write():
    """Gegenprobe/Schutztest fuer PostgreSQL, analog zum SQLite-Pendant
    oben: ein Schreibversuch UEBER DIESELBE Read-only-Verbindung, die das
    Audit fuer PostgreSQL verwendet, muss serverseitig abgewiesen werden."""
    with _fresh_postgres_database("ailiza_audit_cli_test_ro") as db_url:
        _pg_init_schema(db_url)
        env = dict(os.environ)
        env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
        env["AILIZA_DATABASE_URL"] = db_url
        script = f"""
import sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from apps.backend.audit_memory_scope_cli import _open_readonly_postgres_engine
from apps.backend.database import memory_items
from sqlalchemy import insert
from sqlalchemy.exc import DBAPIError
from datetime import datetime, timezone

ro_engine = _open_readonly_postgres_engine({db_url!r})
now = datetime.now(timezone.utc)
try:
    with ro_engine.connect() as conn:
        conn.execute(insert(memory_items).values(
            tenant_id="default", scope="company_memory", owner_user_id=None,
            title="t", content="c", purpose="p", source_id=None,
            status="active", created_at=now, updated_at=now,
        ))
        conn.commit()
    print("SCHREIBVERSUCH_ERFOLGREICH")
except DBAPIError as exc:
    print(f"SCHREIBVERSUCH_ABGEWIESEN: {{exc}}")
finally:
    ro_engine.dispose()
"""
        result = subprocess.run(
            [sys.executable, "-c", script], env=env, cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=30,
        )
        assert "SCHREIBVERSUCH_ABGEWIESEN" in result.stdout, (
            f"Postgres-Read-only-Schutz hat einen Schreibversuch NICHT abgewiesen: "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "read-only" in result.stdout.lower() or "readonly" in result.stdout.lower()


@pg_only
def test_postgres_audit_clean_db_exits_zero():
    with _fresh_postgres_database("ailiza_audit_cli_test_clean") as db_url:
        _pg_init_schema(db_url)
        result = _run_script(db_url)
        assert result.returncode == 0, result.stderr
        assert "Keine Invarianten-Verletzungen" in result.stdout


@pg_only
def test_postgres_audit_missing_schema_exits_two():
    with _fresh_postgres_database("ailiza_audit_cli_test_noschema") as db_url:
        result = _run_script(db_url)
        assert result.returncode == 2, result.stdout
        assert "Tabelle(n) fehlen" in result.stderr


def test_workflow_installs_cryptography_dependency():
    """Regressionsschutz: database.py braucht transitiv 'cryptography'
    (governance/field_crypto.py) -- muss in der Minimal-Installation des
    Produktions-Audit-Workflows enthalten sein, sonst schlaegt der Import
    fehl, bevor ueberhaupt eine DB-Verbindung versucht wird."""
    workflow = REPO_ROOT / ".github" / "workflows" / "memory-audit-manual.yml"
    content = workflow.read_text(encoding="utf-8")
    assert "cryptography" in content
