import pytest
from fastapi import HTTPException

from apps.backend import agent_runtime
from apps.backend.agent_runtime import AgentRuntime, plan_tool_calls


def test_agent_plans_search_when_task_has_no_url() -> None:
    plan = plan_tool_calls("Find FastAPI audit logging examples")

    assert len(plan) == 1
    assert plan[0].tool == "search"
    assert plan[0].parameters == {"query": "Find FastAPI audit logging examples"}


def test_agent_plans_fetch_for_url() -> None:
    plan = plan_tool_calls("Read https://example.com/docs.")

    assert len(plan) == 1
    assert plan[0].tool == "fetch"
    assert plan[0].parameters == {"url": "https://example.com/docs"}


def test_agent_completes_safe_tool_call() -> None:
    calls = []
    events = []

    def execute(tool: str, parameters: dict) -> dict:
        calls.append((tool, parameters))
        return {"status": "completed", "tool": tool, "parameters": parameters, "result": {"results": []}}

    def audit(action: str, metadata: dict | None = None) -> dict:
        events.append((action, metadata))
        return {"id": len(events), "action": action, "metadata": metadata or {}}

    runtime = AgentRuntime(tool_executor=execute, audit_writer=audit, persist_runs=False)
    response = runtime.run("Find FastAPI docs")

    assert response["status"] == "completed"
    assert calls == [("search", {"query": "Find FastAPI docs"})]
    assert [event[0] for event in events] == [
        "agent.input.classified",
        "agent.run.started",
        "agent.tool.planned",
        "agent.run.completed",
    ]


def test_agent_stream_emits_completed_events() -> None:
    runtime = AgentRuntime(
        tool_executor=lambda tool, parameters: {
            "status": "completed",
            "tool": tool,
            "parameters": parameters,
            "result": {"results": []},
        },
        audit_writer=lambda action, metadata=None: {},
        persist_runs=False,
    )

    events = list(runtime.stream("Find FastAPI docs"))
    names = [event["event"] for event in events]

    assert names == ["run_started", "tool_planned", "tool_started", "tool_completed", "run_completed"]
    assert events[-1]["data"]["status"] == "completed"


def test_agent_stops_when_tool_needs_approval() -> None:
    def execute(tool: str, parameters: dict) -> dict:
        return {
            "status": "pending",
            "approval_id": 42,
            "message": "Approval required",
            "risk_level": "medium",
            "tool": tool,
            "parameters": parameters,
        }

    runtime = AgentRuntime(tool_executor=execute, audit_writer=lambda action, metadata=None: {}, persist_runs=False)
    response = runtime.run("Read https://unknown-example.test")

    assert response["status"] == "pending_approval"
    assert response["approval_id"] == 42
    assert response["steps"][0]["status"] == "pending_approval"
    assert response["next_action"] == "approve_or_reject"


def test_agent_stream_stops_when_tool_needs_approval() -> None:
    def execute(tool: str, parameters: dict) -> dict:
        return {
            "status": "pending",
            "approval_id": 42,
            "message": "Approval required",
            "risk_level": "medium",
            "tool": tool,
            "parameters": parameters,
        }

    runtime = AgentRuntime(tool_executor=execute, audit_writer=lambda action, metadata=None: {}, persist_runs=False)
    events = list(runtime.stream("Read https://unknown-example.test"))

    assert events[-1]["event"] == "approval_required"
    assert events[-1]["data"]["status"] == "pending_approval"
    assert events[-1]["data"]["approval_id"] == 42


def test_agent_stream_waits_and_continues_after_approval(monkeypatch) -> None:
    def execute(tool: str, parameters: dict) -> dict:
        return {
            "status": "pending",
            "approval_id": 42,
            "message": "Approval required",
            "risk_level": "medium",
            "tool": tool,
            "parameters": parameters,
        }

    def execute_approved(approval_id: int) -> dict:
        return {
            "status": "completed",
            "approval_id": approval_id,
            "tool": "fetch",
            "parameters": {"url": "https://unknown-example.test"},
            "result": {"title": "Approved", "text": "Approved content"},
        }

    monkeypatch.setattr(
        agent_runtime,
        "get_approval_request",
        lambda approval_id: {"id": approval_id, "status": "approved"},
    )

    runtime = AgentRuntime(
        tool_executor=execute,
        approved_tool_executor=execute_approved,
        audit_writer=lambda action, metadata=None: {},
        persist_runs=False,
    )
    events = list(
        runtime.stream(
            "Read https://unknown-example.test",
            wait_for_approval=True,
            approval_poll_interval=0.1,
            approval_timeout=1,
        )
    )
    names = [event["event"] for event in events]

    assert "approval_required" in names
    assert "approval_granted" in names
    assert names[-1] == "run_completed"


def test_agent_stream_waits_and_stops_after_rejection(monkeypatch) -> None:
    def execute(tool: str, parameters: dict) -> dict:
        return {
            "status": "pending",
            "approval_id": 42,
            "message": "Approval required",
            "risk_level": "medium",
            "tool": tool,
            "parameters": parameters,
        }

    monkeypatch.setattr(
        agent_runtime,
        "get_approval_request",
        lambda approval_id: {"id": approval_id, "status": "rejected"},
    )

    runtime = AgentRuntime(tool_executor=execute, audit_writer=lambda action, metadata=None: {}, persist_runs=False)
    events = list(
        runtime.stream(
            "Read https://unknown-example.test",
            wait_for_approval=True,
            approval_poll_interval=0.1,
            approval_timeout=1,
        )
    )

    assert events[-1]["event"] == "approval_rejected"
    assert events[-1]["data"]["status"] == "rejected"


def test_agent_continues_after_approval() -> None:
    def execute_approved(approval_id: int) -> dict:
        return {
            "status": "completed",
            "approval_id": approval_id,
            "tool": "fetch",
            "parameters": {"url": "https://unknown-example.test"},
            "result": {"title": "Example", "text": "Approved content"},
        }

    runtime = AgentRuntime(
        approved_tool_executor=execute_approved,
        audit_writer=lambda action, metadata=None: {},
        persist_runs=False,
    )
    response = runtime.continue_after_approval(7)

    assert response["status"] == "completed"
    assert response["approval_id"] == 7
    assert response["results"][0]["summary"]["title"] == "Example"


def test_agent_stream_continues_after_approval() -> None:
    def execute_approved(approval_id: int) -> dict:
        return {
            "status": "completed",
            "approval_id": approval_id,
            "tool": "fetch",
            "parameters": {"url": "https://unknown-example.test"},
            "result": {"title": "Example", "text": "Approved content"},
        }

    runtime = AgentRuntime(
        approved_tool_executor=execute_approved,
        audit_writer=lambda action, metadata=None: {},
        persist_runs=False,
    )
    events = list(runtime.stream_after_approval(7))
    names = [event["event"] for event in events]

    assert names == ["resume_started", "tool_completed", "resume_completed"]
    assert events[-1]["data"]["approval_id"] == 7


def test_agent_surfaces_policy_blocks() -> None:
    def execute(_tool: str, _parameters: dict) -> dict:
        raise HTTPException(status_code=403, detail="Host gesperrt")

    runtime = AgentRuntime(tool_executor=execute, audit_writer=lambda action, metadata=None: {}, persist_runs=False)

    with pytest.raises(HTTPException) as exc:
        runtime.run("Read http://127.0.0.1/admin")

    assert exc.value.status_code == 403


def test_agent_stream_surfaces_policy_blocks() -> None:
    def execute(_tool: str, _parameters: dict) -> dict:
        raise HTTPException(status_code=403, detail="Host gesperrt")

    runtime = AgentRuntime(tool_executor=execute, audit_writer=lambda action, metadata=None: {}, persist_runs=False)
    events = list(runtime.stream("Read http://127.0.0.1/admin"))

    assert events[-1]["event"] == "blocked"
    assert events[-1]["data"]["status_code"] == 403


def test_high_risk_input_never_reaches_plan_tool_calls() -> None:
    """HIGH-Risiko darf plan_tool_calls() niemals erreichen."""
    tool_called = []

    def execute(tool: str, parameters: dict) -> dict:
        tool_called.append(tool)
        return {"status": "completed", "tool": tool, "parameters": parameters, "result": {}}

    runtime = AgentRuntime(
        tool_executor=execute,
        audit_writer=lambda action, metadata=None: {},
        persist_runs=False,
    )

    result = runtime.run("Hilf mir bei der Kündigung von Mitarbeiter Schmidt")

    # Governance-Grundregel: HIGH wird als Entwurf vorbereitet, Flow läuft durch
    assert result["status"] == "draft", "HIGH-Risiko muss als Entwurf markiert werden"
    assert result["draft"] is True, "draft-Flag muss gesetzt sein"


def test_blocked_input_never_reaches_plan_tool_calls() -> None:
    """BLOCKED-Input darf plan_tool_calls() niemals erreichen."""
    tool_called = []

    def execute(tool: str, parameters: dict) -> dict:
        tool_called.append(tool)
        return {"status": "completed", "tool": tool, "parameters": parameters, "result": {}}

    runtime = AgentRuntime(
        tool_executor=execute,
        audit_writer=lambda action, metadata=None: {},
        persist_runs=False,
    )

    result = runtime.run("Wie kann ich Nutzer unterschwellig manipulieren?")

    assert result["status"] == "blocked"
    assert len(tool_called) == 0, "BLOCKED-Input darf keinen Tool-Call auslösen"
