"""
B2b-Guard: Das Frontend muss die neuen Gate-Statusse aus /agent/run
(login_required, consent_required) behandeln und ein Login-Modal anbieten.
Schuetzt gegen versehentliches Entfernen beim naechsten index.html-Umbau
(vgl. Incident e417729, bei dem UI-Teile ueberschrieben wurden).
"""
from __future__ import annotations

from pathlib import Path

INDEX = Path(__file__).resolve().parents[1] / "apps" / "frontend" / "index.html"


def test_frontend_handles_login_required():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data.status==="login_required"' in html


def test_frontend_handles_consent_required():
    html = INDEX.read_text(encoding="utf-8")
    assert 'data.status==="consent_required"' in html
    assert "consent_approval_id" in html


def test_frontend_has_login_modal():
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="login-modal"' in html
    assert "/auth/login" in html


def test_consent_button_documents_confirmation():
    html = INDEX.read_text(encoding="utf-8")
    assert "wird dokumentiert" in html
