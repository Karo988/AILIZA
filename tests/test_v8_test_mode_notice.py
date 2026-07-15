"""
V-8 (Freigabe Stufe 1, P-A): Jede Antwort im Testmodus muss sichtbar
Provider + Modell + einen Testmodus-Hinweis tragen — nicht nur bei der
AVV-Testausnahme, sondern bei JEDER Antwort waehrend AILIZA_TEST_MODE=true.

Diese Tests pruefen die serverseitige Helferfunktion _test_mode_fields()
direkt (main.py), die an allen drei Rueckgabepunkten von /agent/run
(Schreibaufgaben-Erfolg, lokaler Fallback, Haupt-/Standardpfad) genutzt
wird, um die strukturierten Felder test_mode/provider/model anzuhaengen.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from apps.backend.main import _test_mode_fields


def test_test_mode_fields_present_when_test_mode_active(monkeypatch):
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")
    fields = _test_mode_fields("groq", "llama-3.3-70b-versatile")
    assert fields is not None
    assert fields["test_mode"] is True
    assert fields["provider"] == "groq"
    assert fields["model"] == "llama-3.3-70b-versatile"


def test_test_mode_fields_fallback_when_provider_model_unknown(monkeypatch):
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")
    fields = _test_mode_fields(None, None)
    assert fields is not None
    assert fields["provider"] == "unbekannt"
    assert fields["model"] == "unbekannt"


def test_test_mode_fields_absent_in_normal_operation(monkeypatch):
    monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
    fields = _test_mode_fields("groq", "llama-3.3-70b-versatile")
    assert fields is None
