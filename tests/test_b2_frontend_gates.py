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


def test_send_message_has_no_native_confirm_gate():
    """
    Karo-Fund 2026-07-12: sendMessage() hatte einen aelteren, parallelen
    Vorab-Check mit nativen confirm()/alert()-Popups (haesslich, kein
    einheitliches Gate, widerspricht "kein Frust"/"ohne akustisches
    Signal"). /agent/run (B2) ist jetzt die einzige Gate-Quelle.
    """
    html = INDEX.read_text(encoding="utf-8")
    send_message_start = html.index("async function sendMessage()")
    send_message_end = html.index("\n}", send_message_start)
    send_message_body = html[send_message_start:send_message_end]
    assert "confirm(" not in send_message_body
    assert "alert(" not in send_message_body


def test_topbar_has_persistent_auth_button():
    """Karo-Wunsch 2026-07-12: dauerhaft sichtbarer Anmelde-Button oben
    rechts, nicht nur reaktiv im Gate-Fluss."""
    html = INDEX.read_text(encoding="utf-8")
    assert 'id="topbar-auth-btn"' in html
    assert "/auth/me" in html
    assert "refreshAuthButton" in html
