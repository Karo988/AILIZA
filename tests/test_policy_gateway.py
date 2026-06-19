from apps.backend.policy import evaluate_policy, PolicyContext
from apps.backend.governance.data_governance import DataClass, DataTarget
from apps.backend.governance.data_matrix import PolicyDecision


def _ctx(**kw):
    return PolicyContext(**kw)


def test_allow_public():
    r = evaluate_policy(_ctx(target=DataTarget.EXTERNAL_LLM,
                             data_classes=[DataClass.PUBLIC],
                             provider_profile_id="profile-eu"))
    assert r.decision == PolicyDecision.ALLOW
    assert r.allowed


def test_block_credentials():
    r = evaluate_policy(_ctx(target=DataTarget.EXTERNAL_LLM,
                             data_classes=[DataClass.CREDENTIALS],
                             provider_profile_id="profile-eu"))
    assert r.decision == PolicyDecision.BLOCK
    assert not r.allowed


def test_redact_required():
    r = evaluate_policy(_ctx(target=DataTarget.EXTERNAL_LLM,
                             data_classes=[DataClass.PERSONAL_DATA],
                             provider_profile_id="profile-eu"))
    assert r.decision == PolicyDecision.REDACT_REQUIRED


def test_approval_required():
    r = evaluate_policy(_ctx(target=DataTarget.EXTERNAL_LLM,
                             data_classes=[DataClass.HR],
                             provider_profile_id="profile-eu"))
    assert r.decision == PolicyDecision.APPROVAL_REQUIRED


def test_fail_closed_no_target():
    r = evaluate_policy(_ctx(data_classes=[DataClass.PUBLIC]))
    assert r.decision == PolicyDecision.BLOCK
