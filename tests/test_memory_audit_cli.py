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


def test_clean_db_exits_zero_and_reports_no_violations(tmp_path):
    db_path = tmp_path / "clean.db"
    result = _run_script(f"sqlite:///{db_path}")
    assert result.returncode == 0, result.stderr
    assert "Keine Invarianten-Verletzungen" in result.stdout


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
    result = _run_script(f"sqlite:///{db_path}", ["--summary-only", "--json"])
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
    env = dict(os.environ)
    env["AILIZA_SECRET_KEY"] = "test-secret-key-minimum-32-chars-ok"
    env["AILIZA_DATABASE_URL"] = f"sqlite:///{tmp_path / 'cwd_test.db'}"
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


def test_workflow_installs_cryptography_dependency():
    """Regressionsschutz: database.py braucht transitiv 'cryptography'
    (governance/field_crypto.py) -- muss in der Minimal-Installation des
    Produktions-Audit-Workflows enthalten sein, sonst schlaegt der Import
    fehl, bevor ueberhaupt eine DB-Verbindung versucht wird."""
    workflow = REPO_ROOT / ".github" / "workflows" / "memory-audit-manual.yml"
    content = workflow.read_text(encoding="utf-8")
    assert "cryptography" in content
