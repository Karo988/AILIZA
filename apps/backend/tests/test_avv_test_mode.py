"""
AVV-Gate + Testmodus-Ausnahme (Freigabe Stufe 1, P-A)
=======================================================
Deckt die Akzeptanztests aus AILIZA_FREIGABE_STUFE1.md ab:

| Fall                                                        | Erwartung        |
|---------------------------------------------------------------|------------------|
| avv_signed=False + PERSONAL                                  | blockiert        |
| avv_signed=False + HR                                        | blockiert        |
| avv_signed=False + SYNTHETIC + test_mode=true                 | erlaubt          |
| avv_signed=False + SYNTHETIC + test_mode=false                | blockiert        |
| avv_signed=False + SYNTHETIC + test_mode=true, PII erkannt     | blockiert        |
| test_mode=true per Request-Parameter gesendet                 | wirkungslos      |
| AILIZA_TEST_MODE=true + AILIZA_ENV=production                 | Start abgebrochen|
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.governance.data_governance import DataClass
from apps.backend.providers.provider_profiles import check_provider_policy
from apps.backend.kill_switch import enforce_test_mode_not_in_production


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Sauberer Ausgangszustand fuer jeden Test — kein Leck aus anderen Tests.
    monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
    monkeypatch.delenv("AILIZA_ENV", raising=False)
    yield


def test_avv_missing_personal_data_blocked(monkeypatch):
    monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
    allowed, reason = check_provider_policy("groq", [DataClass.PERSONAL_DATA])
    assert allowed is False
    assert "AVV" in reason or "avv" in reason.lower()


def test_avv_missing_hr_blocked(monkeypatch):
    monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
    allowed, reason = check_provider_policy("groq", [DataClass.HR])
    assert allowed is False


def test_avv_missing_synthetic_test_mode_true_allowed(monkeypatch):
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")
    allowed, reason = check_provider_policy("groq", [DataClass.SYNTHETIC])
    assert allowed is True
    assert reason == "ok:no_avv_test_exception"


def test_avv_missing_synthetic_test_mode_false_blocked(monkeypatch):
    monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
    allowed, reason = check_provider_policy("groq", [DataClass.SYNTHETIC])
    assert allowed is False


def test_avv_missing_demo_test_mode_true_allowed(monkeypatch):
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")
    allowed, reason = check_provider_policy("groq", [DataClass.DEMO])
    assert allowed is True


def test_avv_missing_public_test_mode_true_allowed(monkeypatch):
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")
    allowed, reason = check_provider_policy("groq", [DataClass.PUBLIC])
    assert allowed is True


def test_avv_test_mode_true_but_pii_detected_blocked(monkeypatch):
    """Haertung 2: Testmodus greift nur wenn AUSSCHLIESSLICH exempte Klassen
    vorliegen. Wird PERSONAL_DATA mitklassifiziert (z.B. weil der Text trotz
    'Testmodus'-Deklaration echte PII enthaelt), bleibt es blockiert."""
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")
    allowed, reason = check_provider_policy(
        "groq", [DataClass.SYNTHETIC, DataClass.PERSONAL_DATA]
    )
    assert allowed is False


def test_test_mode_has_no_request_parameter_path():
    """Haertung 1: check_provider_policy hat keinen test_mode-Parameter, der
    von einem Aufrufer (z.B. aus einem Request-Body) gesetzt werden koennte.
    test_mode wird ausschliesslich intern ueber is_test_mode() (Env) geloest."""
    import inspect
    sig = inspect.signature(check_provider_policy)
    assert "test_mode" not in sig.parameters


def test_env_test_mode_true_in_production_blocks_startup(monkeypatch):
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")
    monkeypatch.setenv("AILIZA_ENV", "production")
    with pytest.raises(RuntimeError):
        enforce_test_mode_not_in_production()


def test_env_test_mode_true_without_production_env_ok(monkeypatch):
    monkeypatch.setenv("AILIZA_TEST_MODE", "true")
    monkeypatch.delenv("AILIZA_ENV", raising=False)
    enforce_test_mode_not_in_production()  # darf nicht werfen


def test_env_test_mode_false_in_production_ok(monkeypatch):
    monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
    monkeypatch.setenv("AILIZA_ENV", "production")
    enforce_test_mode_not_in_production()  # darf nicht werfen


def test_local_provider_unaffected_by_avv_gate(monkeypatch):
    """local hat avv_signed=True — Gate greift gar nicht erst."""
    monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
    allowed, reason = check_provider_policy("local", [DataClass.PERSONAL_DATA])
    assert allowed is True
    assert reason == "ok"
