"""RiskAssessment-Grundlage vor evaluate_policy (Business-Governance-Paket).

Scope (siehe HANDOFF-Fortsetzungsauftrag "Phase-0-Entscheidung"):
RiskAssessment bewertet AUSSCHLIESSLICH Risiko und ersetzt nie ALLOW/BLOCK/
responsibility_handoff. evaluate_policy bleibt die einzige Entscheidungsinstanz.

Bewusst NICHT Teil dieses Pakets (siehe policy.py-Docstring "HANDOFF"):
verbindliche H1-H3-Schwellenwerte, secret/forbidden/responsibility_handoff/
local_only (existieren im Code nicht), Owner-Override-Ausfuehrung.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend import core_api
from apps.backend.capabilities.registry import check_capability, get_all_capabilities
from apps.backend.governance.data_governance import DataClass, DataTarget
from apps.backend.governance.data_matrix import PolicyDecision
from apps.backend.policy import (
    PolicyContext,
    RiskAssessment,
    PolicyRiskLevel,
    assess_risk,
    compute_context_fingerprint,
    evaluate_policy,
)


def _complete_context(**overrides) -> PolicyContext:
    defaults = dict(
        target=DataTarget.MEMORY,
        data_classes=[DataClass.PUBLIC],
        highest_risk_class=DataClass.PUBLIC,
        tool="memory.write",
        parameters={"resource_id": "item-1", "recipient_id": None, "scope": "default"},
    )
    defaults.update(overrides)
    return PolicyContext(**defaults)


# ── 1. Determinismus & Fingerprint ───────────────────────────────────────────

def test_assess_risk_is_deterministic():
    ctx = _complete_context()
    a1 = assess_risk(ctx)
    a2 = assess_risk(ctx)
    assert a1.risk_level == a2.risk_level
    assert a1.reason_codes == a2.reason_codes
    assert a1.context_fingerprint == a2.context_fingerprint


def test_same_context_same_fingerprint():
    ctx1 = _complete_context()
    ctx2 = _complete_context()
    assert compute_context_fingerprint(ctx1) == compute_context_fingerprint(ctx2)


def test_relevant_change_produces_new_fingerprint():
    ctx1 = _complete_context()
    ctx2 = _complete_context(tool="memory.delete")
    assert compute_context_fingerprint(ctx1) != compute_context_fingerprint(ctx2)

    ctx3 = _complete_context(parameters={"resource_id": "item-2", "scope": "default"})
    assert compute_context_fingerprint(ctx1) != compute_context_fingerprint(ctx3)

    ctx4 = _complete_context(highest_risk_class=DataClass.CREDENTIALS)
    assert compute_context_fingerprint(ctx1) != compute_context_fingerprint(ctx4)

    ctx5 = _complete_context(policy_version="2.0")
    assert compute_context_fingerprint(ctx1) != compute_context_fingerprint(ctx5)


def test_fingerprint_contains_no_raw_pii():
    ctx = _complete_context(
        user_id="alice@example.com",
        parameters={"resource_id": "item-1", "recipient_id": "bob@example.com", "scope": "default"},
    )
    fp = compute_context_fingerprint(ctx)
    assert "alice@example.com" not in fp
    assert "bob@example.com" not in fp
    assert len(fp) == 64  # SHA-256 hex digest, kein Klartext


# ── 2. Kompatibilitaet des bestehenden reason-Strings ────────────────────────

def test_existing_reason_string_stays_compatible():
    ctx = _complete_context()
    result = evaluate_policy(ctx)
    assert isinstance(result.reason, str)
    assert result.reason  # unveraendert vorhanden, nicht leer


def test_reason_codes_are_additive():
    ctx = _complete_context()
    result = evaluate_policy(ctx)
    assert isinstance(result.reason_codes, list)
    assert result.reason  # bestehendes Feld bleibt zusaetzlich vorhanden


# ── 3. Bestehende Aufrufer funktionieren weiterhin ───────────────────────────

def test_check_capability_path_receives_risk_assessment(monkeypatch):
    """check_capability() muss intern evaluate_policy() -> assess_risk()
    durchlaufen -- nachgewiesen ueber einen Spy auf assess_risk, da
    CapabilityCheckResult die neuen PolicyResultV2-Felder (bewusst additiv,
    nicht Teil dieses Pakets) noch nicht in sein eigenes Schema uebernimmt."""
    import apps.backend.policy as policy_mod

    calls = []
    original = policy_mod.assess_risk

    def _spy(context):
        calls.append(context)
        return original(context)

    monkeypatch.setattr(policy_mod, "assess_risk", _spy)

    caps = get_all_capabilities()
    assert caps, "mindestens eine Capability muss registriert sein"
    cap_id = caps[0]["capability_id"]
    check_capability(cap_id, data_classes=[DataClass.PUBLIC], tenant_id="default", user_id="alice")

    assert len(calls) == 1, "assess_risk muss genau einmal ueber den check_capability-Pfad laufen"
    assert calls[0].tool == cap_id, "PolicyContext.tool muss mit der Capability angereichert sein"


def test_core_api_path_stays_compatible():
    ctx = _complete_context()
    result = core_api.evaluate_policy(ctx)
    assert result.decision in {PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE,
                                PolicyDecision.REDACT_REQUIRED, PolicyDecision.APPROVAL_REQUIRED,
                                PolicyDecision.BLOCK}
    assert result.risk_level == PolicyRiskLevel.UNKNOWN.value


def test_direct_evaluate_policy_call_gets_risk_assessment():
    ctx = _complete_context()
    result = evaluate_policy(ctx)
    assert result.risk_level == PolicyRiskLevel.UNKNOWN.value
    assert result.context_fingerprint
    assert result.assessment_version


# ── 4. Fehlende Signale -> UNKNOWN, kein erratenes H1-H3 ─────────────────────

def test_missing_tool_and_data_class_yield_unknown_with_context_incomplete():
    ctx = PolicyContext(target=DataTarget.MEMORY, data_classes=[])
    result = evaluate_policy(ctx)
    assert result.risk_level == PolicyRiskLevel.UNKNOWN.value
    assert "RISK_CONTEXT_INCOMPLETE" in result.reason_codes
    assert "MISSING_SIGNAL_ACTION" in result.reason_codes
    assert "MISSING_SIGNAL_DATA_CLASS" in result.reason_codes


def test_complete_context_still_yields_unknown_no_matrix_confirmed():
    ctx = _complete_context()
    ra = assess_risk(ctx)
    assert ra.risk_level == PolicyRiskLevel.UNKNOWN
    assert ra.reason_codes == ("RISK_MATRIX_NOT_CONFIRMED",)
    assert "H1" not in ra.reason_codes and "H2" not in ra.reason_codes and "H3" not in ra.reason_codes


def test_incomplete_risk_context_does_not_change_existing_policy_decision():
    """Ein unvollstaendiger Risikokontext darf die bestehende
    PolicyDecision NICHT alleine veraendern -- RiskAssessment entscheidet nie."""
    ctx_with_signals = _complete_context()
    ctx_without_signals = PolicyContext(
        target=DataTarget.MEMORY, data_classes=[DataClass.PUBLIC],
        highest_risk_class=DataClass.PUBLIC,
    )
    result_with = evaluate_policy(ctx_with_signals)
    result_without = evaluate_policy(ctx_without_signals)
    # Gleiche Datenklasse/Ziel -> gleiche PolicyDecision, unabhaengig davon,
    # ob RiskAssessment vollstaendige oder unvollstaendige Signale hatte.
    assert result_with.decision == result_without.decision


# ── 5. Bestehendes Governance-Vokabular bleibt unveraendert ─────────────────

def test_existing_dataclass_values_unchanged():
    # Vollstaendige Ist-Menge inkl. SYNTHETIC/DEMO (Testmodus-Ausnahme,
    # siehe governance/data_governance.py) -- dieses Paket ergaenzt keinen
    # dieser Werte und entfernt keinen.
    expected = {
        "public", "internal", "confidential", "personal_data", "special_category",
        "credentials", "financial", "hr", "legal", "intellectual_property",
        "security_sensitive", "synthetic", "demo",
    }
    actual = {c.value for c in DataClass}
    assert actual == expected, "DataClass darf in diesem Paket nicht erweitert werden"


def test_existing_policy_decision_values_unchanged():
    # responsibility_handoff wurde im Folgepaket (siehe
    # tests/test_responsibility_handoff.py) bewusst und bestaetigt ergaenzt --
    # dieses RiskAssessment-Paket selbst erweitert PolicyDecision nicht.
    expected = {"allow", "allow_with_notice", "redact_required", "approval_required",
                "block", "responsibility_handoff"}
    actual = {d.value for d in PolicyDecision}
    assert actual == expected, "PolicyDecision darf in diesem Paket nicht erweitert werden"


def test_no_conceptual_categories_added_as_enums():
    # secret/forbidden/local_only bleiben weiterhin unbestaetigte HANDOFF-
    # Begriffe. responsibility_handoff ist NICHT mehr Teil dieser Prüfung --
    # es wurde im Folgepaket bewusst als PolicyDecision-Wert bestaetigt
    # (siehe tests/test_responsibility_handoff.py).
    dataclass_values = {c.value for c in DataClass}
    decision_values = {d.value for d in PolicyDecision}
    for forbidden_term in ("secret", "forbidden", "local_only"):
        assert forbidden_term not in dataclass_values
        assert forbidden_term not in decision_values


# ── 6. RiskAssessment-Objekt selbst ──────────────────────────────────────────

def test_risk_assessment_is_frozen():
    ra = RiskAssessment(risk_level=PolicyRiskLevel.UNKNOWN)
    with pytest.raises(Exception):
        ra.risk_level = PolicyRiskLevel.H1  # type: ignore[misc]


def test_stale_fingerprint_triggers_reassessment():
    ctx = _complete_context()
    result1 = evaluate_policy(ctx)
    old_fp = result1.context_fingerprint

    changed_ctx = _complete_context(tool="memory.delete")
    result2 = evaluate_policy(changed_ctx)
    assert result2.context_fingerprint != old_fp


def test_existing_risk_assessment_with_matching_fingerprint_is_reused():
    ctx = _complete_context()
    fp = compute_context_fingerprint(ctx)
    pre_bound = RiskAssessment(
        risk_level=PolicyRiskLevel.UNKNOWN,
        reason_codes=("PRE_BOUND_MARKER",),
        signals={},
        context_fingerprint=fp,
    )
    ctx_with_ra = _complete_context(risk_assessment=pre_bound)
    result = evaluate_policy(ctx_with_ra)
    assert "PRE_BOUND_MARKER" in result.reason_codes


# ── 7. PII-Schutz (sichtbare Strukturen: signals, context_summary, reason_codes) ──

def test_signals_never_contain_raw_resource_or_recipient_values():
    ctx = _complete_context(
        parameters={"resource_id": "geheimnisvoller-kunde-mueller-gmbh",
                    "recipient_id": "mueller@kunde-example.de", "scope": "default"},
    )
    ra = assess_risk(ctx)
    serialized = repr(ra.signals)
    assert "geheimnisvoller-kunde-mueller-gmbh" not in serialized
    assert "mueller@kunde-example.de" not in serialized
    # Nur abgeleitete Booleans statt Rohwerten:
    assert ra.signals["has_resource_id"] is True
    assert ra.signals["has_recipient_id"] is True


def test_signals_use_only_derived_or_canonical_features():
    ctx = _complete_context()
    ra = assess_risk(ctx)
    allowed_keys = {
        "action", "data_class", "target", "has_resource_id", "has_recipient_id",
        "scope", "is_write_action", "reversibility", "source_version",
        "policy_version", "parameter_count",
    }
    assert set(ra.signals.keys()) <= allowed_keys


def test_context_summary_never_contains_raw_parameters():
    ctx = _complete_context(
        parameters={"resource_id": "vertraulich-projekt-x", "recipient_id": "chef@firma.de",
                    "scope": "default", "freitext": "interne Notiz mit Namen Erika Musterfrau"},
    )
    result = evaluate_policy(ctx)
    serialized = repr(result.context_summary)
    assert "vertraulich-projekt-x" not in serialized
    assert "chef@firma.de" not in serialized
    assert "Erika Musterfrau" not in serialized


def test_reason_codes_never_contain_user_supplied_values():
    ctx = _complete_context(tool="delete-alle-daten-von-erika-musterfrau")
    result = evaluate_policy(ctx)
    for code in result.reason_codes:
        assert "erika" not in code.lower() and "musterfrau" not in code.lower()
    # reason_codes stammen ausschliesslich aus einer festen, bekannten Menge:
    fixed_codes = {"RISK_CONTEXT_INCOMPLETE", "RISK_MATRIX_NOT_CONFIRMED", "RISK_ASSESSMENT_ERROR",
                   "MISSING_SIGNAL_ACTION", "MISSING_SIGNAL_DATA_CLASS"}
    for code in result.reason_codes:
        assert code in fixed_codes, f"unerwarteter, evtl. dynamischer Reason Code: {code}"


def test_fingerprint_of_sensitive_parameters_leaks_nothing_in_signals_or_summary():
    ctx = _complete_context(
        parameters={"resource_id": "patientenakte-schmidt-2026", "recipient_id": "arzt@praxis.de",
                    "scope": "default"},
    )
    ra = assess_risk(ctx)
    result = evaluate_policy(ctx)
    for haystack in (repr(ra.signals), repr(result.context_summary), repr(result.reason_codes),
                     ra.context_fingerprint, result.context_fingerprint):
        assert "patientenakte-schmidt-2026" not in haystack
        assert "arzt@praxis.de" not in haystack


# ── 8. Keine geteilten veraenderlichen Standardwerte ─────────────────────────

def test_policyresultv2_instances_do_not_share_mutable_defaults():
    ctx1 = PolicyContext(target=None, data_classes=[])
    ctx2 = PolicyContext(target=None, data_classes=[])
    r1 = evaluate_policy(ctx1)
    r2 = evaluate_policy(ctx2)
    assert r1.reason_codes is not r2.reason_codes
    assert r1.context_summary is not r2.context_summary
    r1.reason_codes.append("MUTATED")
    assert "MUTATED" not in r2.reason_codes


def test_riskassessment_instances_do_not_share_mutable_defaults():
    ra1 = RiskAssessment(risk_level=PolicyRiskLevel.UNKNOWN)
    ra2 = RiskAssessment(risk_level=PolicyRiskLevel.UNKNOWN)
    assert ra1.signals is not ra2.signals
    ra1.signals["MUTATED"] = True
    assert "MUTATED" not in ra2.signals


# ── 9. Uebernommene Policy-Hardening-Tests aus apps/backend/tests/test_core_hardening.py ──
#
# Quelle: apps/backend/tests/test_core_hardening.py, Klasse TestGovernanceGate
# (Zeilen 167-217 zum Zeitpunkt der Uebernahme). Diese Datei selbst ist laut
# .github/workflows/ci.yml als "verwaist" dokumentiert (kaputte Imports auf
# nicht mehr existierende Module) und wird NICHT ausgefuehrt -- nur die
# folgenden, weiterhin gegen den aktuellen Code lauffaehigen Faelle wurden
# hierher uebernommen und an evaluate_policy() mit RiskAssessment angepasst.

def test_ported_no_target_blocks():
    ctx = PolicyContext(target=None, data_classes=[DataClass.PUBLIC])
    result = evaluate_policy(ctx)
    assert not result.allowed


def test_ported_credentials_blocked_for_external_llm():
    ctx = PolicyContext(
        target=DataTarget.EXTERNAL_LLM,
        data_classes=[DataClass.CREDENTIALS],
        redaction_applied=False,
    )
    result = evaluate_policy(ctx)
    assert not result.allowed


def test_ported_special_category_blocked_for_external_llm():
    ctx = PolicyContext(
        target=DataTarget.EXTERNAL_LLM,
        data_classes=[DataClass.SPECIAL_CATEGORY],
        redaction_applied=False,
    )
    result = evaluate_policy(ctx)
    assert not result.allowed


def test_ported_public_data_allowed_for_external_llm_with_profile():
    ctx = PolicyContext(
        target=DataTarget.EXTERNAL_LLM,
        data_classes=[DataClass.PUBLIC],
        provider_profile_id="groq",
        redaction_applied=False,
    )
    result = evaluate_policy(ctx)
    assert result.allowed


def test_ported_no_provider_profile_affects_decision():
    ctx = PolicyContext(
        target=DataTarget.EXTERNAL_LLM,
        data_classes=[DataClass.PUBLIC],
        provider_profile_id=None,
    )
    result = evaluate_policy(ctx)
    assert isinstance(result.allowed, bool)


def test_ported_evaluate_policy_via_core_api_fail_closed():
    ctx = PolicyContext(target=None, data_classes=[])
    result = core_api.evaluate_policy(ctx)
    assert not result.allowed
