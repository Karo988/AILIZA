"""
Karo-Fund 2026-07-12: Ein alter, nirgends mehr registrierter Service Worker
(Cache "ailiza-v1") blieb bei jedem Nutzer aktiv installiert und zeigte bei
Netzwerkausfaellen (z.B. Render-Free-Tier-Aufwachzeit) eine wochenalte
gecachte Version der Seite -- inkl. laengst entfernter, DSGVO-inkorrekter
Inhalte (falsche "Art. 52"-Referenz, altes Login-Overlay). Dieser Test
sichert ab, dass /sw.js auf Root-Scope liegt (sonst kann der neue Worker
den alten root-scope-registrierten Worker nicht ersetzen) und sich selbst
deregistriert statt Inhalte zu cachen.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from fastapi.testclient import TestClient

from apps.backend.main import app

client = TestClient(app)


def test_sw_js_reachable_at_root_scope():
    resp = client.get("/sw.js")
    assert resp.status_code == 200


def test_sw_js_self_unregisters_and_clears_caches():
    text = client.get("/sw.js").text
    assert "unregister" in text
    assert "caches.delete" in text or "caches.keys" in text


def test_sw_js_never_caches_content():
    """Der neue Worker darf KEINEN Offline-/Content-Cache mehr aufbauen."""
    text = client.get("/sw.js").text
    assert "caches.open" not in text
    assert "caches.addAll" not in text


def test_sw_js_not_browser_cached():
    resp = client.get("/sw.js")
    cache_control = resp.headers.get("cache-control", "")
    assert "no-cache" in cache_control or "no-store" in cache_control
