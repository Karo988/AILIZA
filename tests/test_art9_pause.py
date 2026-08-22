"""Sicherheitsregressionen fuer die nicht-aktivierende Art.-9-Pause."""
from __future__ import annotations

import hashlib
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

from fastapi import Request, Response
from pydantic import ValidationError

from apps.backend import main
from apps.backend.art9_transfer_registry import (
    Art6LegalBasis, Art9Exception, Art9PurposeId, Art9RecipientId,
    PURPOSE_REGISTRY, RECIPIENT_REGISTRY,
)
from apps.backend.routers.approvals import serialize_approval


# Vollstaendig synthetische, namenlose Sicherheits-Fixture; kein realer Fall.
_ART9_TEXT = "Die Patientin ist HIV-positiv und erhaelt eine Chemotherapie."


def _complete_context() -> main.Art9TransferContext:
    return main.Art9TransferContext(
        purpose="treatment_summary",
        recipient="clinic_partner_01",
        art6_legal_basis="art6_1_b",
        art9_exception="art9_2_h",
        provider_id="openai",
    )


def test_complete_art9_context_creates_pause_without_activation(monkeypatch):
    captured: dict = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return {"id": 901}

    monkeypatch.setattr(main, "create_approval_request", fake_create)
    monkeypatch.setattr(main, "write_audit_entry", lambda **kwargs: None)
    binding = main._art9_payload_binding(_ART9_TEXT, None)

    result = main._governance_pre_check(
        _ART9_TEXT,
        tenant_id="tenant-a",
        owner_user_id="user-a",
        art9_transfer=_complete_context(),
        payload_binding=binding,
    )

    assert result["decision"] == "approval_required"
    assert result["status"] == "art9_paused"
    assert result["approval_id"] == 901
    assert result["activation_allowed"] is False
    assert result["missing_fields"] == []
    assert result["invalid_fields"] == []
    assert captured["tool"] == "art9_external_transfer_pause"
    assert captured["owner_user_id"] == "user-a"
    assert captured["tenant_id"] == "tenant-a"
    assert captured["required_approver_roles"] == ["admin", "privacy"]
    params = captured["input_params"]
    assert params["payload_sha256"] == hashlib.sha256(binding.encode("utf-8")).hexdigest()
    assert params["activation_stage"] == "pause_only"
    assert params["activation_allowed"] is False
    assert _ART9_TEXT not in repr(params)


def test_missing_art9_confirmations_go_to_responsibility_handoff(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        main,
        "create_approval_request",
        lambda **kwargs: captured.update(kwargs) or {"id": 902},
    )
    monkeypatch.setattr(main, "write_audit_entry", lambda **kwargs: None)

    result = main._governance_pre_check(
        _ART9_TEXT,
        tenant_id="tenant-a",
        owner_user_id="user-a",
        art9_transfer=main.Art9TransferContext(purpose="treatment_summary"),
        payload_binding=main._art9_payload_binding(_ART9_TEXT, None),
    )

    assert result["decision"] == "responsibility_handoff"
    assert result["activation_allowed"] is False
    assert set(result["missing_fields"]) == {
        "recipient", "art6_legal_basis", "art9_exception", "provider_id",
    }
    assert captured["tool"] == "art9_responsibility_handoff"


def test_invalid_legal_codes_stay_in_handoff(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        main,
        "create_approval_request",
        lambda **kwargs: captured.update(kwargs) or {"id": 903},
    )
    monkeypatch.setattr(main, "write_audit_entry", lambda **kwargs: None)
    invalid_values = _complete_context().model_dump(mode="json")
    invalid_values.update({"art6_legal_basis": "unknown", "art9_exception": "unknown"})
    context = SimpleNamespace(model_dump=lambda mode=None: invalid_values)

    result = main._governance_pre_check(
        _ART9_TEXT,
        tenant_id="tenant-a",
        owner_user_id="user-a",
        art9_transfer=context,
        payload_binding=main._art9_payload_binding(_ART9_TEXT, None),
    )

    assert result["decision"] == "responsibility_handoff"
    assert set(result["invalid_fields"]) == {"art6_legal_basis", "art9_exception"}
    assert captured["input_params"]["activation_allowed"] is False


@pytest.mark.parametrize("field,value", [
    ("purpose", "free text purpose"),
    ("recipient", "unknown_recipient"),
    ("art6_legal_basis", "contract"),
    ("art9_exception", "healthcare"),
    ("provider_id", "custom-provider"),
])
def test_transfer_context_rejects_unregistered_or_free_text_codes(field, value):
    values = _complete_context().model_dump(mode="json")
    values[field] = value
    with pytest.raises(ValidationError):
        main.Art9TransferContext(**values)


def test_every_purpose_and_recipient_enum_is_pre_registered():
    assert set(PURPOSE_REGISTRY) == set(Art9PurposeId)
    assert set(RECIPIENT_REGISTRY) == set(Art9RecipientId)


def test_legal_codes_are_exactly_the_closed_dsgvo_enumerations():
    assert {item.value for item in Art6LegalBasis} == {
        f"art6_1_{letter}" for letter in "abcdef"
    }
    assert {item.value for item in Art9Exception} == {
        f"art9_2_{letter}" for letter in "abcdefghij"
    }


def test_approval_serialization_resolves_explanations_without_storing_them():
    params = {
        "payload_sha256": "a" * 64,
        "purpose": "treatment_summary",
        "recipient": "clinic_partner_01",
        "art6_legal_basis": "art6_1_b",
        "art9_exception": "art9_2_h",
        "provider_id": "openai",
        "activation_allowed": False,
    }
    entry = {
        "id": 12, "created_at": "2026-08-21T00:00:00Z", "run_id": None,
        "tool": "art9_external_transfer_pause", "input_params": params,
        "risk_level": "safety_critical", "risk_reason": "pause",
        "status": "pending", "resolved_at": None, "note": "",
    }

    serialized = serialize_approval(entry)

    assert "explanation" not in repr(params).lower()
    assert serialized["identifier_details"]["purpose"]["explanation_de"]
    recipient = serialized["identifier_details"]["recipient"]
    assert recipient["explanation_de"]
    assert recipient["avv_required"] is True
    assert recipient["avv_status"] == "not_verified"


def test_anonymous_art9_request_is_paused_without_orphan_approval(monkeypatch):
    monkeypatch.setattr(
        main,
        "create_approval_request",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("orphan approval")),
    )
    monkeypatch.setattr(main, "write_audit_entry", lambda **kwargs: None)

    result = main._governance_pre_check(
        _ART9_TEXT,
        tenant_id="default",
        owner_user_id=None,
        art9_transfer=_complete_context(),
        payload_binding=main._art9_payload_binding(_ART9_TEXT, None),
    )

    assert result["decision"] == "responsibility_handoff"
    assert result["login_required"] is True
    assert result["approval_id"] is None
    assert result["activation_allowed"] is False


def test_history_is_part_of_payload_hash_and_art9_detection(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        main,
        "create_approval_request",
        lambda **kwargs: captured.update(kwargs) or {"id": 904},
    )
    monkeypatch.setattr(main, "write_audit_entry", lambda **kwargs: None)
    binding = main._art9_payload_binding(
        "Bitte fasse den Verlauf zusammen.",
        [{"role": "user", "content": _ART9_TEXT}],
    )

    result = main._governance_pre_check(
        "Bitte fasse den Verlauf zusammen.",
        tenant_id="tenant-a",
        owner_user_id="user-a",
        art9_transfer=_complete_context(),
        payload_binding=binding,
    )

    assert result["status"] == "art9_paused"
    assert captured["input_params"]["payload_sha256"] == hashlib.sha256(binding.encode("utf-8")).hexdigest()


def test_agent_core_returns_before_any_provider_call(monkeypatch):
    monkeypatch.setattr(main, "create_approval_request", lambda **kwargs: {"id": 905})
    monkeypatch.setattr(main, "write_audit_entry", lambda **kwargs: None)
    monkeypatch.setattr(
        main._orchestrator,
        "generate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider called")),
    )
    monkeypatch.setattr(
        main.AgentRuntime,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("runtime called")),
    )
    scope = {
        "type": "http", "method": "POST", "path": "/agent/run",
        "headers": [], "query_string": b"", "client": ("127.0.0.1", 1),
        "server": ("test", 80), "scheme": "http",
    }
    token = SimpleNamespace(user_id="user-a", tenant_id="tenant-a")
    payload = main.AgentRunRequest(task=_ART9_TEXT, art9_transfer=_complete_context())

    result = main._run_agent_core(Request(scope), payload, token, Response())

    assert result["status"] == "art9_paused"
    assert result["activation_allowed"] is False
    assert result["steps"] == []
