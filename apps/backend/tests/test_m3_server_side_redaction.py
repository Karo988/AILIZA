"""
M3 — Client-Behauptung "schon geschwaerzt" darf Server-Redaction nie umgehen
================================================================================
Merge-Auftrag Stufe 1×main, M3. main hatte unabhaengig eine Funktion
_is_redacted(text) eingefuehrt, die nur prueft, ob IRGENDWO eckige Klammern
im Text vorkommen, und bei True redaction_applied=True setzte — ohne dass der
Server tatsaechlich redaktiert hatte. Ein Client konnte also z.B.
"[x] Herr Max Mustermann, Diagnose: Krebs" senden und der Server haette die
echte PII unredaktiert durchgelassen, weil die blosse Anwesenheit von "[x]"
als Redaction-Beweis akzeptiert wurde.

Fix: _governance_pre_check() setzt redaction_applied bei der Erstentscheidung
IMMER auf False. Redaction passiert ausschliesslich serverseitig via
RedactionEngineV2, nie basierend auf einer Client-Behauptung.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from apps.backend.main import _governance_pre_check


def test_bracket_claim_does_not_bypass_server_redaction():
    """Text enthaelt literale eckige Klammern (Client-'Beweis' fuer Redaction)
    UND echte, unredaktierte PII. Der Server darf das NICHT als bereits
    geschwaerzt akzeptieren — er muss selbst klassifizieren und redaktieren."""
    task = "[bereits anonymisiert] Herr Max Mustermann, Diagnose: Krebs, Tel: 0151 23456789"

    result = _governance_pre_check(task, tenant_id="test-tenant")

    # Darf NICHT "allow" mit unveraendertem, PII-haltigem Text sein.
    if result["decision"] in ("allow_with_notice",):
        returned_task = result.get("task", "")
        assert "Max Mustermann" not in returned_task, (
            "M3-Regression: Client-Klammern haben Server-Redaction umgangen — "
            "echter Name wurde unredaktiert durchgelassen."
        )
        assert "0151" not in returned_task, (
            "M3-Regression: Client-Klammern haben Server-Redaction umgangen — "
            "echte Telefonnummer wurde unredaktiert durchgelassen."
        )
    else:
        # block / approval_required sind ebenfalls akzeptable, sichere Ergebnisse
        assert result["decision"] in ("block", "approval_required")


def test_plain_pii_without_bracket_claim_still_redacted():
    """Kontrollfall: PII ohne jede Klammer-Behauptung wird wie erwartet
    server-seitig behandelt (Regressionsschutz fuer den Normalfall)."""
    task = "Herr Max Mustermann, Tel: 0151 23456789"

    result = _governance_pre_check(task, tenant_id="test-tenant")

    if result["decision"] == "allow_with_notice":
        returned_task = result.get("task", "")
        assert "Max Mustermann" not in returned_task
        assert "0151" not in returned_task
