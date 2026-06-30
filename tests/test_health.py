"""
Health-Check Endpunkt Tests
============================
Prueft dass GET /api/health und GET /health erreichbar sind
und die erwartete Antwort liefern.
Render Health Check Path: /api/health → muss 200 zurueckgeben.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from fastapi.testclient import TestClient
from apps.backend.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_api_health_returns_200():
    """GET /api/health muss 200 zurueckgeben — Render Health Check."""
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_api_health_response_body():
    """Antwort muss status=ok, service=ailiza-backend, api=online enthalten."""
    resp = client.get("/api/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "ailiza-backend"
    assert data["api"] == "online"


def test_health_returns_200():
    """GET /health muss ebenfalls 200 zurueckgeben."""
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_and_api_health_same_response():
    """/health und /api/health geben identische Antwort."""
    r1 = client.get("/health").json()
    r2 = client.get("/api/health").json()
    assert r1 == r2
