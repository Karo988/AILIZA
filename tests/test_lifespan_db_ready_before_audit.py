"""Regressionstest fuer CI-Run 30787567646 (PR #76): der FastAPI-Lifespan
in main.py rief write_audit_entry() (Secret-Key-/CORS-Warnungen) auf, BEVOR
init_db() lief. Solange database.py die Tabellen automatisch beim
Modulimport anlegte, blieb das unsichtbar. Seit der Trennung von
Schema-Import und Datenbankstart (apps/backend/db_schema.py) legt der
reine Import keine Tabellen mehr an -- der erste write_audit_entry()-Aufruf
scheiterte dadurch mit "no such table: audit_logs" und der Dienst startete
nicht (frontend-e2e-Job in der CI schlug fehl).

WICHTIG: Dieser Test muss als eigener SUBPROZESS laufen, nicht im
Testprozess selbst -- tests/conftest.py ruft init_db() beim Sammeln aller
Tests bereits eigenhaendig auf (Ersatz fuer den Anwendungsstart in der
Testsuite), was genau diesen Fehler in-process maskieren wuerde: die
geteilte In-Memory-Engine haette die Tabellen dann laengst, unabhaengig
von der tatsaechlichen Reihenfolge im Lifespan. Der Subprozess startet
komplett frisch, ohne conftest.py -- exakt wie der uvicorn-Prozess in der
CI."""
from __future__ import annotations

import os
import subprocess
import sys

REPO_ROOT_ENV = {
    "AILIZA_DATABASE_URL": "sqlite:///:memory:",
    "AILIZA_EXTERNAL_LLM_ENABLED": "false",
    "AILIZA_DEFAULT_TENANT_ID": "default",
    "AILIZA_SECRET_KEY": "ci-e2e-secret-key-not-for-production-32ch",
    "AILIZA_LOG_HMAC_KEY": "ci-e2e-log-hmac-key-not-for-production-32ch",
    # Bewusst NICHT gesetzt: AILIZA_CORS_ORIGINS/AILIZA_DEBUG -- der
    # CORS-Wildcard-Warnpfad (write_audit_entry) muss wie in der CI ueber
    # den Default "*" ausgeloest werden, ohne Debug-Unterdrueckung.
}

_SCRIPT = (
    "import asyncio\n"
    "from apps.backend.main import app\n"
    "async def _run():\n"
    "    async with app.router.lifespan_context(app):\n"
    "        pass\n"
    "asyncio.run(_run())\n"
    "print('LIFESPAN_OK')\n"
)


def test_lifespan_completes_in_fresh_subprocess_against_in_memory_database():
    env = {**os.environ, **REPO_ROOT_ENV}
    env.pop("AILIZA_CORS_ORIGINS", None)
    env.pop("AILIZA_DEBUG", None)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        cwd=repo_root, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "LIFESPAN_OK" in result.stdout
    assert "no such table" not in (result.stdout + result.stderr)
