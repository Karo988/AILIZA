"""Tests fuer Dual-Gate PR-3: Spiegel-Linting + asymmetrische Schwellen +
Freigabe-Cockpit (minimal: pro-Kategorie enforce/shadow-Flag).

Scope: keine Provider-Aenderungen, kein Frontend, kein echter Stufe-3-
Pruefer -- nur das deterministische Zweitsignal auf Ingress UND Egress,
plus die Entscheidung, ob eine Kategorie ueberhaupt blocken darf.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

from apps.backend.governance.mirror_lint import (
    MirrorLintFinding,
    rule_mode,
    run_mirror_lint,
)
from apps.backend.governance.redaction_v2 import RedactionEngineV2


# ---------------------------------------------------------------------------
# T1: Spiegel-Linting laeuft getrennt auf Ingress und Egress
# ---------------------------------------------------------------------------

def test_mirror_lint_runs_on_ingress_and_egress_separately():
    ingress = "Meine IBAN ist DE89370400440532013000, bitte pruefen."
    egress = "Ihre Anfrage wurde erfasst, kein IBAN-Bezug im Entwurf."
    findings = run_mirror_lint(ingress, egress)
    iban_finding = next(f for f in findings if f.category == "iban")
    assert iban_finding.in_ingress is True
    assert iban_finding.in_egress is False
    assert iban_finding.signal_count == 1


# ---------------------------------------------------------------------------
# T2: Generator-risk_flags sind nur tertiaer -- should_block ignoriert sie
# ---------------------------------------------------------------------------

def test_generator_risk_flags_are_tertiary_not_decisive():
    ingress = "Kein Treffer hier."
    egress = "Auch hier kein Treffer."
    findings = run_mirror_lint(ingress, egress, generator_flagged_categories={"iban"})
    # "iban" taucht in keinem der beiden Texte auf -> kein Finding, obwohl
    # der Generator es (fiktiv) markiert hat. Das Generator-Signal allein
    # erzeugt NIE ein Finding.
    assert all(f.category != "iban" for f in findings)


# ---------------------------------------------------------------------------
# T3: Kritische Kategorie blockt auf ein einzelnes Signal
# ---------------------------------------------------------------------------

def test_critical_category_blocks_on_single_signal():
    finding = MirrorLintFinding(category="iban", in_ingress=False, in_egress=True)
    assert finding.signal_count == 1
    assert finding.should_block is True
    assert rule_mode("iban") == "enforce"
    assert finding.is_blocking is True


# ---------------------------------------------------------------------------
# T4: Komfort-Regel (aber enforce) braucht beide Signale
# ---------------------------------------------------------------------------

def test_comfort_rule_requires_both_signals_to_block():
    assert rule_mode("reference") == "enforce"
    only_egress = MirrorLintFinding(category="reference", in_ingress=False, in_egress=True)
    assert only_egress.should_block is False
    assert only_egress.is_blocking is False

    both = MirrorLintFinding(category="reference", in_ingress=True, in_egress=True)
    assert both.should_block is True
    assert both.is_blocking is True


# ---------------------------------------------------------------------------
# T5: Shadow-Regel erkennt, blockt aber nie
# ---------------------------------------------------------------------------

def test_shadow_mode_rule_logs_but_never_blocks():
    assert rule_mode("name") == "shadow"
    finding = MirrorLintFinding(category="name", in_ingress=True, in_egress=True)
    assert finding.should_block is True  # Schwelle erreicht (Komfort, beide Signale)
    assert finding.is_blocking is False  # aber Shadow-Modus blockt nie


# ---------------------------------------------------------------------------
# T6: Enforce-Regel kann tatsaechlich blocken
# ---------------------------------------------------------------------------

def test_enforce_mode_rule_can_block():
    finding = MirrorLintFinding(category="credential", in_ingress=True, in_egress=False)
    assert rule_mode("credential") == "enforce"
    assert finding.is_blocking is True

    # Unbekannte/neue Kategorie: fail-closed -> shadow, blockt nie
    assert rule_mode("irgendeine_zukuenftige_kategorie") == "shadow"


# ---------------------------------------------------------------------------
# T7: Mirror-Linting dupliziert die Redaction-Muster NICHT, sondern nutzt sie
# ---------------------------------------------------------------------------

def test_reuses_redaction_v2_patterns_not_duplicated():
    from apps.backend.governance import mirror_lint

    assert mirror_lint._PATTERNS is RedactionEngineV2.PATTERNS
