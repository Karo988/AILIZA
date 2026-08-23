from apps.backend.governance.data_governance import DataClass, DataTarget
from apps.backend.governance.data_matrix import check_data_target, PolicyDecision


def test_credentials_always_block_external():
    d = check_data_target([DataClass.CREDENTIALS], DataTarget.EXTERNAL_LLM, False, False, True)
    assert d == PolicyDecision.BLOCK


def test_credentials_allowed_in_ram():
    d = check_data_target([DataClass.CREDENTIALS], DataTarget.RAM, False, False, True)
    assert d == PolicyDecision.ALLOW


def test_special_category_block_external():
    d = check_data_target([DataClass.SPECIAL_CATEGORY], DataTarget.EXTERNAL_LLM, True, True, True)
    assert d == PolicyDecision.BLOCK


def test_special_category_has_no_ordinary_approval_activation_path():
    """A normal approval must never turn an Art.-9 decision into ALLOW."""
    for target in DataTarget:
        without_approval = check_data_target(
            [DataClass.SPECIAL_CATEGORY], target, False, False, True,
        )
        with_approval = check_data_target(
            [DataClass.SPECIAL_CATEGORY], target, False, True, True,
        )
        assert with_approval == without_approval, target
        if target in {DataTarget.EXTERNAL_LLM, DataTarget.CRM, DataTarget.EMAIL}:
            assert with_approval not in {
                PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE,
            }, target


def test_personal_data_redact_required():
    d = check_data_target([DataClass.PERSONAL_DATA], DataTarget.EXTERNAL_LLM, False, False, True)
    assert d == PolicyDecision.REDACT_REQUIRED


def test_personal_data_allow_after_redaction():
    d = check_data_target([DataClass.PERSONAL_DATA], DataTarget.EXTERNAL_LLM, True, False, True)
    assert d == PolicyDecision.ALLOW_WITH_NOTICE


def test_personal_data_block_without_profile():
    d = check_data_target([DataClass.PERSONAL_DATA], DataTarget.EXTERNAL_LLM, False, False, False)
    assert d == PolicyDecision.BLOCK


def test_hr_approval_required():
    d = check_data_target([DataClass.HR], DataTarget.EXTERNAL_LLM, False, False, True)
    assert d == PolicyDecision.APPROVAL_REQUIRED


def test_public_allow_with_profile():
    d = check_data_target([DataClass.PUBLIC], DataTarget.EXTERNAL_LLM, False, False, True)
    assert d == PolicyDecision.ALLOW


def test_strictest_wins():
    d = check_data_target(
        [DataClass.PUBLIC, DataClass.CREDENTIALS], DataTarget.EXTERNAL_LLM, True, True, True)
    assert d == PolicyDecision.BLOCK
