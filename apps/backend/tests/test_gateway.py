import pytest
from fastapi import HTTPException

from apps.backend import gateway
from apps.backend.gateway import runtime_gateway


def test_guarded_tool_call_executes_low_risk_tool(monkeypatch) -> None:
    events = []

    monkeypatch.setattr(runtime_gateway, "write_audit_entry", lambda action, metadata=None: events.append(action) or {})
    monkeypatch.setattr(runtime_gateway, "execute_tool", lambda tool, parameters: {"results": []})

    response = gateway.guarded_tool_call("search", {"query": "FastAPI audit logging"})

    assert response["status"] == "completed"
    assert response["result"] == {"results": []}
    assert "policy.decision" in events
    assert "approval.auto" in events
    assert "tools.executed" in events


def test_guarded_tool_call_returns_pending_before_execution(monkeypatch) -> None:
    called = False

    def execute_tool(_tool: str, _parameters: dict) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(runtime_gateway, "write_audit_entry", lambda action, metadata=None: {})
    monkeypatch.setattr(runtime_gateway, "create_approval_request", lambda **kwargs: {"id": 42, **kwargs})
    monkeypatch.setattr(runtime_gateway, "execute_tool", execute_tool)

    response = gateway.guarded_tool_call("fetch", {"url": "https://unknown-example.test"})

    assert response["status"] == "pending"
    assert response["approval_id"] == 42
    assert called is False


def test_guarded_tool_call_blocks_policy_violation_before_execution(monkeypatch) -> None:
    called = False

    def execute_tool(_tool: str, _parameters: dict) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(runtime_gateway, "write_audit_entry", lambda action, metadata=None: {})
    monkeypatch.setattr(runtime_gateway, "execute_tool", execute_tool)

    with pytest.raises(HTTPException) as exc:
        gateway.guarded_tool_call("fetch", {"url": "http://127.0.0.1/admin"})

    assert exc.value.status_code == 403
    assert called is False


def test_execute_approved_tool_waits_for_pending_approval(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_gateway,
        "get_approval_request",
        lambda approval_id: {
            "id": approval_id,
            "status": "pending",
            "run_id": None,
            "tool": "fetch",
            "input_params": {"url": "https://unknown-example.test"},
            "risk_level": "medium",
        },
    )

    response = gateway.execute_approved_tool(5)

    assert response["status"] == "pending"
    assert response["approval_id"] == 5


def test_execute_approved_tool_runs_approved_request(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_gateway,
        "get_approval_request",
        lambda approval_id: {
            "id": approval_id,
            "status": "approved",
            "run_id": None,
            "tool": "fetch",
            "input_params": {"url": "https://github.com/openai/codex"},
            "risk_level": "medium",
        },
    )
    monkeypatch.setattr(runtime_gateway, "write_audit_entry", lambda action, metadata=None: {})
    monkeypatch.setattr(runtime_gateway, "execute_tool", lambda tool, parameters: {"title": "Codex", "text": ""})

    response = gateway.execute_approved_tool(5)

    assert response["status"] == "completed"
    assert response["approval_id"] == 5
    assert response["result"]["title"] == "Codex"


def test_execute_approved_tool_rejects_unknown_status(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime_gateway,
        "get_approval_request",
        lambda approval_id: {
            "id": approval_id,
            "status": "expired",
            "run_id": None,
            "tool": "fetch",
            "input_params": {"url": "https://github.com/openai/codex"},
            "risk_level": "medium",
        },
    )

    with pytest.raises(HTTPException) as exc:
        gateway.execute_approved_tool(5)

    assert exc.value.status_code == 409
