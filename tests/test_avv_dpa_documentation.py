"""
AVV/DPA-Dokumentation der kommerziellen Provider (Betreiber-Entscheidung,
2026-07-06): Anthropic und OpenAI gelten als "AVV/DPA vorhanden", weil der
AVV/DPA ueber kommerzielle Vertragsbedingungen bzw. den Online-DPA-Prozess
des jeweiligen Anbieters wirksam eingebunden wird.

WICHTIG: "AVV vorhanden" heisst nicht "keine Pruefung noetig". Es heisst nur,
dass die Vertragsgrundlage dokumentiert ist. Drittlandtransfer (SCC/TIA)
bleibt ein eigener Pruefpunkt (siehe transfer_review_required).

Diese Tests sichern NUR die technische Umsetzung ab (Feld-Werte, Policy-
Verhalten) — sie sind kein Ersatz fuer die juristische Pruefung.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from apps.backend.governance.data_governance import DataClass
from apps.backend.providers.provider_profiles import check_provider_policy, get_profile


def test_anthropic_avv_documented():
    profile = get_profile("anthropic")
    assert profile is not None
    assert profile.avv_signed is True
    assert profile.avv_status == "documented"
    assert profile.avv_basis == "commercial_terms_or_online_dpa"
    assert profile.avv_checked_at == "2026-07-06"
    assert profile.avv_source_url  # nicht leer
    assert profile.transfer_review_required is True


def test_openai_avv_documented():
    profile = get_profile("openai")
    assert profile is not None
    assert profile.avv_signed is True
    assert profile.avv_status == "documented"
    assert profile.avv_basis == "commercial_terms_or_online_dpa"
    assert profile.avv_checked_at == "2026-07-06"
    assert profile.avv_source_url  # nicht leer
    assert profile.transfer_review_required is True


def test_groq_avv_unaffected():
    """Regressionsschutz: Groq ist NICHT Teil dieser Betreiber-Entscheidung
    und bleibt unveraendert nicht dokumentiert."""
    profile = get_profile("groq")
    assert profile is not None
    assert profile.avv_signed is False
    assert profile.avv_status == "not_documented"


def test_anthropic_personal_data_allowed_without_test_mode(monkeypatch):
    """Mit dokumentiertem AVV darf Anthropic PERSONAL_DATA routen — ganz
    ohne Testmodus-Ausnahme (die Ausnahme war vorher der einzige Weg)."""
    monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
    allowed, reason = check_provider_policy("anthropic", [DataClass.PERSONAL_DATA])
    assert allowed
    assert reason == "ok"  # NICHT die Testmodus-Ausnahme — echter AVV-Weg


def test_openai_personal_data_allowed_without_test_mode(monkeypatch):
    monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
    allowed, reason = check_provider_policy("openai", [DataClass.PERSONAL_DATA])
    assert allowed
    assert reason == "ok"


def test_groq_personal_data_still_blocked_without_avv(monkeypatch):
    """Regressionsschutz: Provider OHNE dokumentierten AVV bleiben fuer
    PERSONAL_DATA blockiert — die Aenderung darf die AVV-Pruefung an sich
    nicht aufweichen, nur fuer die zwei genannten Provider den Status setzen."""
    monkeypatch.delenv("AILIZA_TEST_MODE", raising=False)
    allowed, _ = check_provider_policy("groq", [DataClass.PERSONAL_DATA])
    assert not allowed


def test_anthropic_special_category_still_blocked():
    """Der dokumentierte AVV lockert NICHT die Datenklassen-Erlaubnisliste —
    SPECIAL_CATEGORY ist fuer Anthropic weiterhin nicht in
    allowed_data_classes und bleibt blockiert."""
    allowed, _ = check_provider_policy("anthropic", [DataClass.SPECIAL_CATEGORY])
    assert not allowed


def test_openai_special_category_still_blocked():
    allowed, _ = check_provider_policy("openai", [DataClass.SPECIAL_CATEGORY])
    assert not allowed


def test_unknown_or_unconfigured_provider_still_blocked():
    """Regressionsschutz: kostenlose/unbekannte Consumer-Accounts duerfen
    durch diese Aenderung nicht versehentlich als AVV-abgedeckt gelten."""
    allowed, reason = check_provider_policy("nonexistent_consumer_account", [DataClass.PUBLIC])
    assert not allowed
