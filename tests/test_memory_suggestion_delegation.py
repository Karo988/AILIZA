"""M2b: Delegation eines einzelnen company_memory-Vorschlags an genau einen
Mitarbeiter desselben Tenants. Baut auf der M2-Haertung (siehe
test_memory_suggestions.py) auf -- user_memory bleibt NIEMALS delegierbar."""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.database import (
    metadata_obj, engine, init_db, create_user,
    create_memory_suggestion, confirm_memory_suggestion, reject_memory_suggestion,
    get_memory_item, list_memory_suggestions_for_user,
    create_memory_suggestion_delegation, revoke_memory_suggestion_delegation,
    list_delegated_memory_suggestions_for_user,
    MemoryValidationError,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_company_suggestion(user_id="alice", tenant_id="default"):
    create_user(user_id=user_id, tenant_id=tenant_id, role="user", hashed_password="hash")
    return create_memory_suggestion(
        user_id=user_id, tenant_id=tenant_id, suggested_scope="company_memory",
        suggested_title="DATEV", suggested_content="Firma nutzt DATEV.",
        suggested_purpose="Kontext", source_type="user_confirmation",
    )


def test_admin_can_delegate_company_memory_to_employee():
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    delegation = create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    assert delegation["status"] == "active"
    listed = list_delegated_memory_suggestions_for_user("bob", "default")
    assert len(listed) == 1
    assert listed[0]["suggestion_id"] == s["id"]


def test_manager_can_delegate_company_memory():
    create_user(user_id="mgr1", tenant_id="default", role="manager", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    delegation = create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="mgr1", delegated_to_user_id="bob",
    )
    assert delegation["status"] == "active"


def test_normal_user_cannot_delegate():
    create_user(user_id="notadmin", tenant_id="default", role="user", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    with pytest.raises(MemoryValidationError):
        create_memory_suggestion_delegation(
            s["id"], tenant_id="default", delegated_by_user_id="notadmin", delegated_to_user_id="bob",
        )


def test_user_memory_can_never_be_delegated():
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="alice", tenant_id="default", role="user", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Privat", suggested_content="Alice' private Notiz.",
        suggested_purpose="Kontext", source_type="user_confirmation",
    )
    with pytest.raises(MemoryValidationError):
        create_memory_suggestion_delegation(
            s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
        )


def test_delegated_employee_can_confirm_exactly_that_suggestion():
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    result = confirm_memory_suggestion(s["id"], confirmed_by="bob", tenant_id="default")
    item = get_memory_item(result["memory_item_id"])
    assert item["scope"] == "company_memory"
    assert item["status"] == "active"


def test_delegated_employee_can_reject():
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    reject_memory_suggestion(s["id"], reviewed_by="bob", tenant_id="default")
    updated = [x for x in list_memory_suggestions_for_user("alice", "default", status=None)
               if x["id"] == s["id"]][0]
    assert updated["status"] == "rejected"


def test_employee_cannot_confirm_other_suggestion_without_delegation():
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s1 = _make_company_suggestion(user_id="alice")
    s2 = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="company_memory",
        suggested_title="Zweiter Vorschlag", suggested_content="anderer Inhalt",
        suggested_purpose="Kontext", source_type="user_confirmation",
    )
    create_memory_suggestion_delegation(
        s1["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    # bob darf nur s1 bestaetigen, nicht s2 (keine Delegation dafuer, keine Admin-Rolle).
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(s2["id"], confirmed_by="bob", tenant_id="default")


def test_employee_cannot_redelegate():
    """Delegierte duerfen selbst keine weitere Delegation vergeben (keine
    Admin/Manager-Rolle -> create_memory_suggestion_delegation lehnt ab)."""
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    create_user(user_id="carol", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    with pytest.raises(MemoryValidationError):
        create_memory_suggestion_delegation(
            s["id"], tenant_id="default", delegated_by_user_id="bob", delegated_to_user_id="carol",
        )


def test_revoked_delegation_is_immediately_unusable():
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    delegation = create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    ok = revoke_memory_suggestion_delegation(
        delegation["id"], tenant_id="default", revoking_user_id="admin1",
    )
    assert ok is True
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(s["id"], confirmed_by="bob", tenant_id="default")


def test_double_revoke_is_safe_and_returns_false():
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    delegation = create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    assert revoke_memory_suggestion_delegation(delegation["id"], tenant_id="default", revoking_user_id="admin1") is True
    assert revoke_memory_suggestion_delegation(delegation["id"], tenant_id="default", revoking_user_id="admin1") is False


def test_two_active_delegations_for_same_suggestion_are_impossible():
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    create_user(user_id="carol", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    with pytest.raises(MemoryValidationError):
        create_memory_suggestion_delegation(
            s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="carol",
        )


def test_foreign_and_nonexistent_delegation_target_yield_identical_error():
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    with pytest.raises(MemoryValidationError):
        create_memory_suggestion_delegation(
            999999, tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
        )
    with pytest.raises(MemoryValidationError):
        create_memory_suggestion_delegation(
            s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="does-not-exist",
        )


def test_delegation_completed_after_successful_confirm_no_double_use():
    create_user(user_id="admin1", tenant_id="default", role="admin", hashed_password="hash")
    create_user(user_id="bob", tenant_id="default", role="user", hashed_password="hash")
    s = _make_company_suggestion()
    create_memory_suggestion_delegation(
        s["id"], tenant_id="default", delegated_by_user_id="admin1", delegated_to_user_id="bob",
    )
    confirm_memory_suggestion(s["id"], confirmed_by="bob", tenant_id="default")
    # Vorschlag ist jetzt "confirmed" -- ein zweiter Versuch (egal ob durch
    # bob oder jemand anderen) muss scheitern, Status-Filter greift zuerst.
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(s["id"], confirmed_by="bob", tenant_id="default")
