import os
import sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Use an isolated in-memory DB for tests.
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Rate-Limit-Speicher vor jedem Test leeren — verhindert 429 zwischen Test-Modulen."""
    from apps.backend.main import _limiter
    _limiter._storage.reset()
    yield
