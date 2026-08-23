"""responsibility_handoff (AILIZA-Kern, siehe policies/governance/ai-act-use-case-classification.md
UC09 Buchhaltung, UC10 HR/Personal).

Scope: PolicyDecision.RESPONSIBILITY_HANDOFF wird ausschliesslich in
policy.evaluate_policy() VOR check_data_target() entschieden, gesteuert
durch PolicyContext.responsibility_domain (nur von Capability-Entwicklern
setzbar, nie aus Nutzereingabe abgeleitet). Feste Domain-Sperrliste
(accounting, hr) -- keine Freitext-/KI-Erkennung, keine H1-H3-Matrix.

Bewusst NICHT Teil dieses Pakets: echte Buchhaltungs-/HR-Capabilities
(responsibility_domain bleibt bei allen bestehenden Capabilities None)."""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.capabilities.registry import (
    Capability, RiskLevel, _CAPABILITIES, check_capability, get_all_capabilities,
)
from apps.backend.governance.data_governance import DataClass, DataTarget
from apps.backend.governance.data_matrix import PolicyDecision, check_data_target
from apps.backend.policy import PolicyContext, evaluate_policy


def _complete_context(**overrides) -> PolicyContext:
    defaults = dict(
        target=DataTarget.MEMORY,
        data_classes=[DataClass.PUBLIC],
        highest_risk_class=DataClass.PUBLIC,
        tool="some.action",
    )
    defaults.update(overrides)
    return PolicyContext(**defaults)


# ── 1. accounting/hr fuehren zum Handoff ─────────────────────────────────────

def test_accounting_domain_triggers_responsibility_handoff():
    ctx = _complete_context(responsibility_domain="accounting")
    result = evaluate_policy(ctx)
    assert result.decision == PolicyDecision.RESPONSIBILITY_HANDOFF
    assert not result.allowed
    assert "Steuerberatung" in result.reason


def test_hr_domain_triggers_responsibility_handoff():
    ctx = _complete_context(responsibility_domain="hr")
    result = evaluate_policy(ctx)
    assert result.decision == PolicyDecision.RESPONSIBILITY_HANDOFF
    assert not result.allowed
    assert "Personalbereich" in result.reason


def test_handoff_message_is_returned_as_recovery_path():
    ctx = _complete_context(responsibility_domain="accounting")
    result = evaluate_policy(ctx)
    assert result.recovery_path == result.reason


def test_handoff_ignores_data_class_and_target():
    """Handoff greift unabhaengig von Datenklasse/Ziel -- wird VOR
    check_data_target ausgewertet."""
    ctx = _complete_context(
        responsibility_domain="accounting",
        target=DataTarget.EXTERNAL_LLM,
        data_classes=[DataClass.CREDENTIALS],
        highest_risk_class=DataClass.CREDENTIALS,
    )
    result = evaluate_policy(ctx)
    assert result.decision == PolicyDecision.RESPONSIBILITY_HANDOFF


# ── 2. Allgemeine Funktionen bleiben unveraendert ────────────────────────────

def test_general_functions_unaffected_no_domain_set():
    ctx = _complete_context()
    result = evaluate_policy(ctx)
    assert result.decision != PolicyDecision.RESPONSIBILITY_HANDOFF
    assert result.allowed


def test_existing_capabilities_have_no_responsibility_domain():
    """Bestaetigt Auftrag Punkt 13: keine Capability mit gesetztem
    responsibility_domain -- alle bestehenden Funktionen bleiben unberuehrt."""
    caps = get_all_capabilities()
    assert caps, "mindestens eine Capability muss registriert sein"
    for cap_id, cap in _CAPABILITIES.items():
        assert cap.responsibility_domain is None, (
            f"Capability {cap_id} hat unerwartet responsibility_domain gesetzt"
        )


def test_check_capability_path_unaffected_for_existing_capabilities():
    caps = get_all_capabilities()
    cap_id = caps[0]["capability_id"]
    result = check_capability(cap_id, data_classes=[DataClass.PUBLIC], tenant_id="default", user_id="alice")
    assert result.decision != PolicyDecision.RESPONSIBILITY_HANDOFF


def test_check_capability_passes_through_responsibility_domain(monkeypatch):
    """Simuliert eine zukuenftige Fachanwendungs-Capability (ohne sie
    dauerhaft anzulegen) und prueft, dass check_capability() das Feld
    korrekt an evaluate_policy() durchreicht."""
    fake_cap = Capability(
        capability_id="_test_accounting_probe",
        name="Testsonde Buchhaltung",
        description="Nur fuer diesen Test",
        target=DataTarget.MEMORY,
        allowed_data_classes=[DataClass.PUBLIC],
        risk_level=RiskLevel.HIGH,
        requires_approval=False,
        external_call=False,
        gdpr_purpose="Test",
        responsibility_domain="accounting",
    )
    monkeypatch.setitem(_CAPABILITIES, "_test_accounting_probe", fake_cap)
    result = check_capability("_test_accounting_probe", data_classes=[DataClass.PUBLIC],
                               tenant_id="default", user_id="alice")
    assert result.decision == PolicyDecision.RESPONSIBILITY_HANDOFF
    assert not result.allowed


def test_capability_without_approval_requirement_does_not_invent_approval(monkeypatch):
    """Capability metadata is not evidence that a human approved a request."""
    import apps.backend.capabilities.registry as registry_mod

    observed = {}

    def capture_policy(context):
        observed["approval_given"] = context.approval_given
        return type("Result", (), {
            "decision": PolicyDecision.ALLOW,
            "reason": "test",
            "allowed": True,
            "risk_level": "low",
            "requires_owner_approval": False,
            "context_summary": {},
        })()

    fake_cap = Capability(
        capability_id="_test_no_approval_evidence",
        name="Testsonde ohne Freigabepflicht",
        description="Nur fuer diesen Test",
        target=DataTarget.RAM,
        allowed_data_classes=[DataClass.PUBLIC],
        risk_level=RiskLevel.LOW,
        requires_approval=False,
        external_call=False,
        gdpr_purpose="Test",
    )
    monkeypatch.setitem(_CAPABILITIES, fake_cap.capability_id, fake_cap)
    monkeypatch.setattr(registry_mod, "evaluate_policy", capture_policy)

    result = check_capability(
        fake_cap.capability_id, data_classes=[DataClass.PUBLIC],
        tenant_id="default", user_id="alice", approval_given=False,
    )

    assert result.allowed
    assert observed["approval_given"] is False


# ── 3. Unbekannte Domain wird fail-closed blockiert ──────────────────────────

def test_unknown_domain_is_blocked_not_handed_off():
    ctx = _complete_context(responsibility_domain="legal_unknown_domain")
    result = evaluate_policy(ctx)
    assert result.decision == PolicyDecision.BLOCK
    assert not result.allowed


def test_typo_in_domain_status_is_blocked_not_approved(monkeypatch):
    """Fail-closed-Kernanforderung: nur der EXAKTE Status "approved" darf
    zur normalen Pruefung durchfallen. Ein Tippfehler wie "aproved" darf
    NIEMALS stillschweigend als Freigabe wirken."""
    import apps.backend.policy as policy_mod
    monkeypatch.setitem(policy_mod._RESPONSIBILITY_DOMAIN_STATUS, "accounting", "aproved")
    ctx = _complete_context(responsibility_domain="accounting")
    result = evaluate_policy(ctx)
    assert result.decision == PolicyDecision.BLOCK
    assert not result.allowed
    assert result.decision != PolicyDecision.RESPONSIBILITY_HANDOFF


def test_arbitrary_unrecognized_status_value_is_blocked(monkeypatch):
    import apps.backend.policy as policy_mod
    monkeypatch.setitem(policy_mod._RESPONSIBILITY_DOMAIN_STATUS, "hr", "provisionally_ok")
    ctx = _complete_context(responsibility_domain="hr")
    result = evaluate_policy(ctx)
    assert result.decision == PolicyDecision.BLOCK
    assert not result.allowed


def test_exact_approved_status_falls_through_to_normal_evaluation(monkeypatch):
    """Gegenprobe: nur der exakte String "approved" schaltet die normale
    Pruefung frei -- Nachweis, dass der Mechanismus ueberhaupt korrekt
    funktioniert (nicht permanent alles blockiert)."""
    import apps.backend.policy as policy_mod
    monkeypatch.setitem(policy_mod._RESPONSIBILITY_DOMAIN_STATUS, "accounting", "approved")
    ctx = _complete_context(responsibility_domain="accounting")
    result = evaluate_policy(ctx)
    assert result.decision != PolicyDecision.RESPONSIBILITY_HANDOFF
    assert result.decision != PolicyDecision.BLOCK or result.reason != (
        "Unbekannter oder ungueltiger Domain-Status — fail-closed blockiert."
    )
    assert result.allowed


def test_unknown_domain_does_not_guess_a_handoff_message():
    ctx = _complete_context(responsibility_domain="finance_unconfirmed")
    result = evaluate_policy(ctx)
    assert "Fachbereich" in result.reason
    assert "Steuerberatung" not in result.reason
    assert "Personalbereich" not in result.reason


# ── 4. Meldungen enthalten keine Nutzereingaben (PII-Schutz) ─────────────────

def test_handoff_message_contains_no_user_supplied_values():
    ctx = _complete_context(
        responsibility_domain="accounting",
        tool="delete-alle-daten-von-erika-musterfrau",
        user_id="erika.musterfrau@example.com",
        parameters={"resource_id": "vertrauliches-projekt-x", "note": "Erika Musterfrau"},
    )
    result = evaluate_policy(ctx)
    assert "erika" not in result.reason.lower()
    assert "musterfrau" not in result.reason.lower()
    assert "vertrauliches-projekt-x" not in result.reason
    # Meldung ist Wort-fuer-Wort eine der beiden festen, vorab definierten Texte:
    from apps.backend.policy import _RESPONSIBILITY_HANDOFF_MESSAGES
    assert result.reason in _RESPONSIBILITY_HANDOFF_MESSAGES.values()


def test_handoff_messages_are_fixed_not_dynamically_generated():
    """Zwei verschiedene Aufrufe mit gleicher Domain aber unterschiedlichen
    Parametern liefern EXAKT dieselbe Meldung -- kein Freitext-Zusammenbau."""
    ctx1 = _complete_context(responsibility_domain="hr", tool="action_a",
                              parameters={"resource_id": "x"})
    ctx2 = _complete_context(responsibility_domain="hr", tool="action_b",
                              parameters={"resource_id": "y", "recipient_id": "z"})
    r1 = evaluate_policy(ctx1)
    r2 = evaluate_policy(ctx2)
    assert r1.reason == r2.reason


# ── 5. Kill-Switch bleibt vorrangig (unabhaengige Pipelinestufe) ─────────────

def test_evaluate_policy_never_imports_or_calls_kill_switch():
    """Struktureller Nachweis: evaluate_policy() (inkl. der neuen
    responsibility_domain-Pruefung) importiert/ruft den Kill-Switch nicht --
    die Pipelinereihenfolge Kill-Switch -> Data Governance ->
    Policy-Gateway bleibt unveraendert, der Kill-Switch wird nicht
    umgangen oder dupliziert. Prueft echte Import-/Aufrufmuster, nicht
    Erwaehnungen in Kommentaren/Docstrings."""
    import apps.backend.policy as policy_mod
    import inspect
    source = inspect.getsource(policy_mod)
    forbidden_patterns = (
        "import kill_switch", "from .kill_switch", "from kill_switch",
        "check_kill_switch(", "enforce_kill_switch(",
    )
    for pattern in forbidden_patterns:
        assert pattern not in source, f"unerwarteter Kill-Switch-Bezug: {pattern}"


def test_kill_switch_module_unmodified_still_blocks_when_disabled():
    """Regressionsschutz: der eigentliche Kill-Switch-Mechanismus
    (unabhaengig von responsibility_handoff) funktioniert unveraendert."""
    from apps.backend.kill_switch import check_kill_switch
    import os as _os
    old = _os.environ.get("AILIZA_EXTERNAL_LLM_ENABLED")
    _os.environ["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    try:
        result = check_kill_switch("global", "external_llm")
        assert result["allowed"] is False
    finally:
        if old is None:
            _os.environ.pop("AILIZA_EXTERNAL_LLM_ENABLED", None)
        else:
            _os.environ["AILIZA_EXTERNAL_LLM_ENABLED"] = old


def test_active_kill_switch_blocks_before_responsibility_domain_is_reached():
    """Echter Ablauf-Test entlang der dokumentierten Pipelinereihenfolge
    (Kill-Switch -> Data Governance -> Policy-Gateway): ein aktiver
    Kill-Switch muss die Ausfuehrung stoppen, BEVOR die
    responsibility_domain-Pruefung ueberhaupt erreicht wird -- unabhaengig
    davon, ob die betroffene Capability eine handoff-pflichtige Domain hat.
    Simuliert einen korrekten Aufrufer, der die Pipelinereihenfolge
    einhaelt (erst Kill-Switch, dann erst bei Erlaubnis die Capability)."""
    from apps.backend.kill_switch import check_kill_switch
    import os as _os

    fake_cap = Capability(
        capability_id="_test_kill_switch_accounting_probe",
        name="Testsonde Kill-Switch + Buchhaltung",
        description="Nur fuer diesen Test",
        target=DataTarget.MEMORY,
        allowed_data_classes=[DataClass.PUBLIC],
        risk_level=RiskLevel.HIGH,
        requires_approval=False,
        external_call=True,
        gdpr_purpose="Test",
        responsibility_domain="accounting",
    )

    capability_calls: list[str] = []

    def _correct_pipeline_caller(kill_switch_scope: str, kill_switch_name: str, capability_id: str) -> str:
        """Simuliert einen Aufrufer, der die dokumentierte Reihenfolge
        einhaelt: Kill-Switch zuerst, Capability/Policy-Gateway nur bei
        Freigabe."""
        ks_result = check_kill_switch(kill_switch_scope, kill_switch_name)
        if not ks_result["allowed"]:
            return "kill_switch_blocked"
        capability_calls.append(capability_id)
        result = check_capability(capability_id, data_classes=[DataClass.PUBLIC],
                                   tenant_id="default", user_id="alice")
        return result.decision.value

    old = _os.environ.get("AILIZA_EXTERNAL_LLM_ENABLED")
    _os.environ["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
    try:
        outcome = _correct_pipeline_caller("global", "external_llm", "_test_kill_switch_accounting_probe")
        assert outcome == "kill_switch_blocked"
        assert capability_calls == [], (
            "Capability/responsibility_domain-Pruefung darf bei aktivem "
            "Kill-Switch nicht erreicht werden"
        )
    finally:
        if old is None:
            _os.environ.pop("AILIZA_EXTERNAL_LLM_ENABLED", None)
        else:
            _os.environ["AILIZA_EXTERNAL_LLM_ENABLED"] = old

    # Gegenprobe: Kill-Switch wieder aktiv (Standard in Tests) -- jetzt WIRD
    # die Capability erreicht und liefert weiterhin korrekt RESPONSIBILITY_HANDOFF.
    _os.environ["AILIZA_EXTERNAL_LLM_ENABLED"] = "true"
    try:
        import apps.backend.capabilities.registry as registry_mod
        registry_mod._CAPABILITIES["_test_kill_switch_accounting_probe"] = fake_cap
        try:
            outcome = _correct_pipeline_caller("global", "external_llm", "_test_kill_switch_accounting_probe")
            assert outcome == "responsibility_handoff"
            assert capability_calls == ["_test_kill_switch_accounting_probe"]
        finally:
            del registry_mod._CAPABILITIES["_test_kill_switch_accounting_probe"]
    finally:
        if old is None:
            _os.environ.pop("AILIZA_EXTERNAL_LLM_ENABLED", None)
        else:
            _os.environ["AILIZA_EXTERNAL_LLM_ENABLED"] = old


# ── 6. Bestehendes Governance-Vokabular bleibt sonst unveraendert ────────────

def test_only_responsibility_handoff_added_to_policy_decision():
    expected = {
        "allow", "allow_with_notice", "redact_required", "approval_required",
        "block", "responsibility_handoff",
    }
    actual = {d.value for d in PolicyDecision}
    assert actual == expected


def test_check_data_target_never_returns_responsibility_handoff():
    """check_data_target() (data_matrix.py) selbst entscheidet
    responsibility_handoff NIE -- nur evaluate_policy() tut das, vorgelagert."""
    for target in DataTarget:
        for dc in DataClass:
            decision = check_data_target(
                data_classes=[dc], target=target,
                redaction_applied=False, approval_given=False,
                provider_profile_active=False,
            )
            assert decision != PolicyDecision.RESPONSIBILITY_HANDOFF
