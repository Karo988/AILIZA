"""
Phase 3e, Schritt 1: Legacy-Dashboards entfernt.

AILIZA_Dashboard.html und AILIZA_Dashboard_v2.html (v0.4-Altlast, nirgends
verlinkt, aber ueber /static/ technisch erreichbar) wurden entfernt.
Dieser Test stellt sicher, dass die alten Pfade sauber 404 liefern
(nicht 200 - Datei waere noch da; nicht 500 - Server-Fehler beim Mount).
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from fastapi.testclient import TestClient

from apps.backend.main import app

client = TestClient(app)


def test_legacy_dashboard_v1_returns_404():
    response = client.get("/static/AILIZA_Dashboard.html")
    assert response.status_code == 404


def test_legacy_dashboard_v2_returns_404():
    response = client.get("/static/AILIZA_Dashboard_v2.html")
    assert response.status_code == 404
