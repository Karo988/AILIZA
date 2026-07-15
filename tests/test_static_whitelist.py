"""
Phase 3e / B3: Static-Whitelist-Guard.

Sichert die Whitelist aus B2 strukturell ab, in BEIDE Richtungen:
- Ein nicht freigegebener Pfad darf NIE erreichbar sein (auch nicht bei
  neuen Dateitypen, die spaeter in apps/frontend/ landen).
- Ein freigegebener Pfad muss weiterhin erreichbar sein (rot, falls er
  aus main.py verschwindet, ohne dass hier jemand die Whitelist anpasst).
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from fastapi.testclient import TestClient

from apps.backend.main import app

client = TestClient(app)

WHITELISTED_PATHS = [
    "/",
    "/static/index.html",
    "/static/icon.svg",
    "/static/manifest.json",
    "/static/public/favicon.svg",
    "/static/public/icons.svg",
]

# Stichproben verschiedener Dateitypen, die NICHT mehr ausgeliefert werden duerfen.
NOT_WHITELISTED_PATHS = [
    "/static/sw.js",
    "/static/config.js",
    "/static/package.json",
    "/static/package-lock.json",
    "/static/README.md",
    "/static/.env.example",
    "/static/vite.config.js",
    "/static/eslint.config.js",
    "/static/src/App.jsx",
    "/static/src/api.js",
    "/static/src/api/ailizaClient.js",
    "/static/src/components/OnboardingWizard.jsx",
    "/static/src/assets/hero.png",
    "/static/assets/.gitkeep",
    "/static/components/.gitkeep",
    "/static/pages/.gitkeep",
    "/static/styles/.gitkeep",
    "/static/AILIZA_Dashboard.html",  # bereits in Phase 3e Schritt 1 entfernt
    "/static/AILIZA_Dashboard_v2.html",
]


def test_whitelisted_paths_return_200():
    for path in WHITELISTED_PATHS:
        response = client.get(path)
        assert response.status_code == 200, f"{path} sollte erreichbar sein (200), war {response.status_code}"


def test_not_whitelisted_paths_return_404():
    for path in NOT_WHITELISTED_PATHS:
        response = client.get(path)
        assert response.status_code == 404, f"{path} sollte NICHT erreichbar sein (404), war {response.status_code}"
