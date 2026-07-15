"""
B7 (P-C minimal): Startup-Erkennung nicht-produktionsreifer Module.

_check_non_production_modules() ist ein datei-basierter Scan (NICHT
import-basiert) ueber vier bekannte, tote Module (legal_hold.py,
policy_engine.py, retention.py, policies/pii_taxonomy.py), die sich per
Docstring-Marker selbst als "nicht produktionsreif" erklaeren. Warnt in
Dev/Staging, loggt ERROR + Audit-Eintrag in Production. Kein Startabbruch.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from apps.backend.main import (
    _NON_PRODUCTION_MARKER,
    _NON_PRODUCTION_MODULES,
    _check_non_production_modules,
)

BASE_DIR = Path(__file__).resolve().parents[1] / "apps" / "backend"


def test_all_four_modules_detected(monkeypatch):
    monkeypatch.delenv("AILIZA_ENV", raising=False)
    found = _check_non_production_modules()
    assert set(found) == set(_NON_PRODUCTION_MODULES)


def test_marker_present_in_all_four_files():
    for rel_path in _NON_PRODUCTION_MODULES:
        content = (BASE_DIR / rel_path).read_text(encoding="utf-8")
        assert _NON_PRODUCTION_MARKER in content, f"{rel_path} sollte den Marker tragen"


def test_production_env_writes_audit_entry(monkeypatch):
    monkeypatch.setenv("AILIZA_ENV", "production")
    calls = []
    import apps.backend.main as main_module
    monkeypatch.setattr(
        main_module, "write_audit_entry",
        lambda **kwargs: calls.append(kwargs),
    )
    found = main_module._check_non_production_modules()
    assert len(found) == 4
    audit_actions = [c["action"] for c in calls]
    assert audit_actions.count("startup.non_production_module_detected") == 4


def test_no_startup_abort_regardless_of_env(monkeypatch):
    """Kein Startabbruch — die Funktion darf niemals eine Exception werfen."""
    for env in ("production", "staging", "development", ""):
        monkeypatch.setenv("AILIZA_ENV", env)
        _check_non_production_modules()  # darf nicht raisen


def test_health_endpoint_unaffected(monkeypatch):
    """Kein Nebeneffekt auf /health — reiner Liveness-Check bleibt frei."""
    monkeypatch.delenv("AILIZA_BETA_ACCESS_CODE", raising=False)
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200


def test_marker_removed_stops_detection(monkeypatch, tmp_path):
    """Zusatztest: Wenn der Marker aus einer Datei entfernt wird (z.B. weil
    ein Modul spaeter produktionsreif erklaert wird), verschwindet die
    Warnung/der Audit-Eintrag fuer genau dieses Modul."""
    target_rel = "retention.py"
    original_path = BASE_DIR / target_rel
    backup_content = original_path.read_text(encoding="utf-8")
    try:
        cleaned = backup_content.replace(_NON_PRODUCTION_MARKER, "Produktionsreif. Zertifiziert.")
        original_path.write_text(cleaned, encoding="utf-8")

        monkeypatch.delenv("AILIZA_ENV", raising=False)
        found = _check_non_production_modules()
        assert target_rel not in found
        # Die anderen drei bleiben unveraendert erkannt
        assert set(found) == set(_NON_PRODUCTION_MODULES) - {target_rel}
    finally:
        original_path.write_text(backup_content, encoding="utf-8")
