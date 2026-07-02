"""
PII-freies Exception-Logging im Request-Pfad (Freigabe Stufe 1, P-G)
======================================================================
main.py:2812 (Fundstelle F11 im Code-Review) loggte die rohe Exception-
Message (str(e)) im Request-Pfad von /api/policy-redact — und gab sie
zusaetzlich im admin_only-Feld der API-Antwort zurueck. Falls die
Redaction-Engine selbst mit dem verarbeiteten Nutzertext in der
Fehlermeldung wirft, waere das ein PII-Leak in Logs und Response.

main.py laesst sich in dieser Umgebung nicht direkt importieren
(vorbestehender, unabhaengiger 'classifier'-Modulpfad-Fehler in
agent_runtime.py — siehe Baseline-Testlaeufe). Diese Tests pruefen daher
den Quellcode direkt (Grep-Akzeptanz), analog zum bereits etablierten
Muster in P-E (test_test_mode_has_no_request_parameter_path).
"""
from __future__ import annotations

import re
from pathlib import Path

_MAIN_PY = Path(__file__).resolve().parents[1] / "main.py"


def _policy_redact_exception_block() -> str:
    src = _MAIN_PY.read_text(encoding="utf-8")
    start = src.index("def policy_redact(")
    # Block endet vor dem naechsten Top-Level 'app.mount' (naechster Abschnitt)
    end = src.index('app.mount("/static"', start)
    return src[start:end]


def test_no_raw_exception_message_logged():
    block = _policy_redact_exception_block()
    # Kein logger.*(f"...{e}") oder logger.*(f"...{exc}") — nur Typ/Korrelations-ID
    assert not re.search(r'logger\.\w+\(f".*\{e\}', block)
    assert not re.search(r'logger\.\w+\(f".*\{exc\}', block)


def test_no_str_e_in_admin_response():
    block = _policy_redact_exception_block()
    # admin_only durfte frueher "error": str(e) enthalten — das API-Antwortfeld
    # darf die Rohmeldung nicht mehr direkt exponieren. Kommentarzeilen, die
    # den String "str(e)" nur erwaehnen, sind erlaubt — nur echter Code zaehlt.
    code_lines = [ln for ln in block.splitlines() if not ln.strip().startswith("#")]
    code_only = "\n".join(code_lines)
    assert '"error": str(e)' not in code_only
    assert re.search(r"(?<!#\s)\bstr\(e\)", code_only) is None


def test_exception_logging_uses_type_and_correlation_id():
    block = _policy_redact_exception_block()
    assert "type(e).__name__" in block
    assert "correlation_id" in block
