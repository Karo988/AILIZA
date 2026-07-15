"""
Phase 3e / B4: config.js-Fix Guard.

Verhindert die Fehlerklasse strukturell: das aktiv ausgelieferte Frontend
(apps/frontend/index.html) darf KEINE absolute onrender.com-API-Basis-URL
mehr enthalten. Frueher fuehrte window.AILIZA_API-Fallback auf eine feste
Production-URL dazu, dass Staging (ailiza-1.onrender.com) heimlich
Production (ailiza.onrender.com) ansprach statt sein eigenes Backend.

Same-Origin-Nachweis: main.py liefert index.html selbst aus (app.get("/")),
Frontend und Backend laufen im selben Prozess/Service - relative Pfade
("/api/...", "/health", ...) gehen daher immer zum eigenen Service.
"""
from __future__ import annotations

from pathlib import Path

INDEX_HTML = Path(__file__).resolve().parents[1] / "apps" / "frontend" / "index.html"


def test_no_onrender_url_in_active_frontend():
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert "onrender.com" not in content, (
        "index.html darf keine absolute onrender.com-URL mehr enthalten "
        "(z.B. als API-Basis-URL-Fallback)."
    )


def test_config_js_file_removed():
    config_js = Path(__file__).resolve().parents[1] / "apps" / "frontend" / "config.js"
    assert not config_js.exists(), "config.js sollte entfernt sein (git rm)."


def test_config_js_not_referenced_in_index_html():
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert "config.js" not in content
