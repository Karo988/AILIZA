import os
import sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Use an isolated in-memory DB for tests.
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

# database.py legt Tabellen nicht mehr automatisch beim Import an (siehe
# apps/backend/db_schema.py-Docstring) -- der Datenbankstart erfolgt sonst
# explizit beim Anwendungsstart (FastAPI-Lifespan in main.py). Fuer die
# Testsuite uebernimmt diese Stelle die Rolle des Anwendungsstarts, damit
# bestehende Tests, die apps.backend.database direkt importieren (ohne
# main.py zu importieren), unveraendert funktionieren.
import apps.backend.database as _db  # noqa: E402
_db.init_db()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Rate-Limit-Speicher vor jedem Test leeren — verhindert 429 zwischen Test-Modulen."""
    from apps.backend.main import _limiter
    _limiter._storage.reset()
    yield
