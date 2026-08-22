"""Gemeinsame, reihenfolgeunabhaengige Basis fuer Backend-Komponententests."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")


@pytest.fixture(autouse=True)
def ensure_backend_test_schema():
    """Repariert nur ein von einem vorherigen Test entferntes Testschema.

    Die Suite teilt in einzelnen Altmodulen absichtlich eine In-Memory-Engine.
    `create_all(checkfirst)` macht diese Module unabhaengig von der Reihenfolge,
    ohne vorhandene Testdaten zwischen Tests zu loeschen.
    """
    from apps.backend.database import init_db

    init_db()
