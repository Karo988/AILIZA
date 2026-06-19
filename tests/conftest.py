import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Use an isolated in-memory DB for tests.
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
