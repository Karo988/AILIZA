from __future__ import annotations

import os
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException

try:
    from .classifier import classify, InputRiskLevel
    from .redactor import redact
    from .database import (
        create_agent_run,
        create_approval_request,
        get_approval_request,
        link_approval_to_run,
        update_agent_run,
        write_audit_entry,
    )
    from .gateway import execute_approved_tool, guarded_tool_call
except ImportError:
    from classifier import classify, InputRiskLevel
    from redactor import redact
    from database import (
        create_agent_run,
        create_approval_request,
        get_approval_request,
        link_approval_to_run,
        update_agent_run,
        write_audit_entry,
    )
    from gateway import execute_approved_tool, guarded_tool_call


ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]
ApprovedToolExecutor = Callable[[int], dict[str, Any]]
AuditWriter = Callable[[str, dict[str, Any] | None], dict[str, Any]]

URL_PATTERN = re.compile(r"https?://[^\s<>\")]+")
_UNSET = object()

_MISSING_PROVIDER_DETAILS: frozenset[str] = frozenset({
    "TAVILY_API_KEY is not configured",
    "tavily-python is not installed",
    "OPENAI_API_KEY is not configured",
    "GROQ_API_KEY is not configured",
    "ANTHROPIC_API_KEY is not configured",
    "External LLM calls are disabled",
})

_RESEARCH_KEYWORDS: frozenset[str] = frozenset({
    "recherch", "such", "aktuell", "neuest", "news", "preis", "wetter",
    "kurse", "börse", "ergebnis", "statistik", "studie", "bericht",
    "was ist", "wer ist", "wie viel", "wie hoch", "wann", "wo ist",
})


def _is_missing_provider_error(exc: HTTPException) -> bool:
    return isinstance(exc.detail, str) and any(
        marker in exc.detail for marker in _MISSING_PROVIDER_DETAILS
    )


def _is_research_task(task: str) -> bool:
    lower = task.lower()
    return any(kw in lower for kw in _RESEARCH_KEYWORDS)


def _build_local_response(run_id: str, task: str) -> dict[str, Any]:
    """Erzeugt eine nutzerfreundliche Antwort wenn kein externer Provider verfügbar ist."""
    if _is_research_task(task):
        message = (
            "Für diese Rechercheanfrage benötige ich eine Internetverbindung, "
            "die aktuell nicht konfiguriert ist.\n\n"
            "Sobald ein Websuche-Dienst (z.B. Tavily) eingerichtet ist, "
            "kann ich diese Frage beantworten.\n\n"
            f'Rechercheplan fuer: "{task}"\n'
            "1. Aktuelle Quellen zum Thema suchen\n"
            "2. Ergebnisse zusammenfassen und auf Relevanz prüfen\n"
            "3. Antwort strukturiert aufbereiten\n\n"
            "Bitte wende dich an deinen Administrator, um die Websuche zu aktivieren."
        )
    else:
        message = (
            "AILIZA läuft im lokalen Modus — externe Dienste sind aktuell nicht konfiguriert. "
            "Einfache Fragen, Dokumentenanalyse und Compliance-Prüfungen stehen weiterhin zur Verfügung."
        )
    return {
        "run_id": run_id,
        "status": "local_only",
        "mode": "degraded",
        "message": message,
        "ai_response": message,
        "steps": [],
        "results": [],
        "notice": "Externe Dienste nicht verfügbar. Kein Datenverlust — AILIZA arbeitet lokal weiter.",
    }


@dataclass(frozen=True)
class PlannedToolCall:
    tool: str
    parameters: dict[str, Any]


class AgentRuntime:
    def __init__(
        self,
        tool_executor: ToolExecutor = guarded_tool_call,
        approved_tool_executor: ApprovedToolExecutor = execute_approved_tool,
        audit_writer: AuditWriter = write_audit_entry,
        persist_runs: bool = True,
    ) -> None:
        self.tool_executor = tool_executor
        self.approved_tool_executor = approved_tool_executor
        self.audit_writer = audit_writer
        self.persist_runs = persist_runs

    def create_run_record(self, run_id: str, task: str, streaming: bool = False) -> None:
        if self.persist_runs:
            create_agent_run(run_id, task, run_metadata={"streaming": streaming})

    def update_run_record(
        self,
        run_id: str | None,
        *,
        status: str | None = None,
        pending_approval_id: int | None | object = _UNSET,
        result: dict[str, Any] | None | object = _UNSET,
    ) -> None:
        if not self.persist_runs or not run_id:
            return

        kwargs: dict[str, Any] = {}
        if status is not None:
            kwargs["status"] = status
        if pending_approval_id is not _UNSET:
            kwargs["pending_approval_id"] = pending_approval_id
        if result is not _UNSET:
            kwargs["result"] = result
        if kwargs:
            update_agent_run(run_id, **kwargs)

    def link_approval_record(self, approval_id: int | None, run_id: str) -> None:
        if self.persist_runs and approval_id is not None:
            link_approval_to_run(approval_id, run_id)

    def _precheck(self, task: str, run_id: str) -> dict[str, Any] | None:
        """
        classify → redact → decide.

        Governance-Grundregel:
        - BLOCKED: nur bei echten Rechtsverstößen (EU AI Act Art. 5) — stoppt den Flow.
        - HIGH: Approval-Request anlegen, Flow läuft weiter — Ergebnis als Entwurf.
        - MEDIUM/PII: redact, dann weiter.
        - LOW: direkt weiter.

        Gibt None zurück wenn Flow normal weiterläuft.
        Gibt Dict zurück nur wenn BLOCKED.
        Seiteneffekte: self._redacted_task, self._draft_approval_id, self._is_draft.
        """
        classification = classify(task)
        self.audit_writer(
            "agent.input.classified",
            {
                "run_id": run_id,
                "risk_level": classification.risk_level.value,
                "pii_detected": classification.pii_detected,
                "requires_approval": classification.requires_approval,
                "blocked": classification.blocked,
                "categories": classification.detected_categories,
            },
        )

        if classification.blocked:
            self.update_run_record(
                run_id,
                status="blocked",
                result={"reason": classification.reason, "user_message": classification.user_message},
            )
            self.audit_writer("agent.input.blocked", {"run_id": run_id, "reason": classification.reason})
            return {
                "run_id": run_id,
                "status": "blocked",
                "message": classification.user_message,
                "reason": classification.reason,
            }

        self._draft_approval_id: int | None = None
        self._is_draft: bool = classification.requires_approval

        if classification.requires_approval:
            if self.persist_runs:
                approval = create_approval_request(
                    tool="agent_input",
                    input_params={"task": task[:500], "risk_categories": classification.detected_categories},
                    risk_level=classification.risk_level.value,
                    risk_reason=classification.reason,
                )
                self._draft_approval_id = approval["id"]
            self.link_approval_record(self._draft_approval_id, run_id)
            self.audit_writer(
                "agent.input.draft_prepared",
                {
                    "run_id": run_id,
                    "approval_id": self._draft_approval_id,
                    "reason": classification.reason,
                    "note": "Flow läuft weiter — Ergebnis gilt als Entwurf bis zur Freigabe",
                },
            )

        if classification.pii_detected:
            redaction = redact(task)
            self._redacted_task = redaction.redacted_text
            self.audit_writer(
                "agent.input.redacted",
                {"run_id": run_id, "redacted_count": redaction.redacted_count, "categories": redaction.redacted_categories},
            )
        else:
            self._redacted_task = task

        return None

    def run(self, task: str) -> dict[str, Any]:
        run_id = str(uuid4())
        self._redacted_task: str = task
        self.create_run_record(run_id, task)
        self.audit_writer("agent.run.started", {"run_id": run_id})

        early_result = self._precheck(task, run_id)
        if early_result is not None:
            return early_result

        plan = plan_tool_calls(self._redacted_task)

        steps: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        for index, call in enumerate(plan, start=1):
            self.audit_writer(
                "agent.tool.planned",
                {
                    "run_id": run_id,
                    "step": index,
                    "tool": call.tool,
                    "parameters": {k: f"<{type(v).__name__}:{len(str(v))}>" for k, v in call.parameters.items()},
                },
            )

            try:
                response = self.tool_executor(call.tool, call.parameters)
            except HTTPException as exc:
                if _is_missing_provider_error(exc):
                    local_result = _build_local_response(run_id, task)
                    self.update_run_record(run_id, status="local_only", result=local_result)
                    self.audit_writer(
                        "agent.degraded_missing_provider",
                        {
                            "run_id": run_id,
                            "tool": call.tool,
                            "mode": "local_only",
                            "reason": "provider_not_configured",
                        },
                    )
                    print(
                        f"AILIZA LOCAL_ONLY DECISION | reason=missing_provider "
                        f"source=tool_executor tool={call.tool} "
                        f"detail={getattr(exc, 'detail', str(exc))!r}",
                        flush=True,
                    )
                    return local_result
                status = "blocked" if exc.status_code == 403 else "failed"
                self.update_run_record(
                    run_id,
                    status=status,
                    result={"status_code": exc.status_code, "detail": exc.detail},
                )
                raise

            step = build_step(index, call, response)
            steps.append(step)

            if response.get("status") == "pending":
                approval_id = response.get("approval_id")
                self.link_approval_record(approval_id, run_id)
                self.update_run_record(
                    run_id,
                    status="pending_approval",
                    pending_approval_id=approval_id,
                    result={
                        "message": response.get("message", "Approval required"),
                        "steps": steps,
                        "next_action": "approve_or_reject",
                    },
                )
                self.audit_writer(
                    "agent.run.pending_approval",
                    {
                        "run_id": run_id,
                        "approval_id": approval_id,
                        "tool": call.tool,
                        "parameters": {k: f"<{type(v).__name__}:{len(str(v))}>" for k, v in call.parameters.items()},
                    },
                )
                return {
                    "run_id": run_id,
                    "status": "pending_approval",
                    "message": response.get("message", "Approval required"),
                    "approval_id": approval_id,
                    "risk_level": response.get("risk_level"),
                    "steps": steps,
                    "next_action": "approve_or_reject",
                }

            results.append(
                {
                    "tool": call.tool,
                    "parameters": call.parameters,
                    "summary": summarize_tool_result(call.tool, response.get("result")),
                    "result": response.get("result"),
                }
            )

        is_draft = getattr(self, "_is_draft", False)
        draft_approval_id = getattr(self, "_draft_approval_id", None)
        final_status = "draft" if is_draft else "completed"
        final_response = {
            "run_id": run_id,
            "status": final_status,
            "message": "Entwurf — wartet auf menschliche Freigabe" if is_draft else "Agent run completed",
            "draft": is_draft,
            "approval_id": draft_approval_id if is_draft else None,
            "steps": steps,
            "results": results,
        }
        self.update_run_record(run_id, status=final_status, pending_approval_id=draft_approval_id if is_draft else None, result=final_response)
        event = "agent.run.draft" if is_draft else "agent.run.completed"
        tools_used = [r.get("tool") for r in results]
        providers_used = list({r.get("result", {}).get("provider") for r in results if r.get("result", {}).get("provider")})
        models_used = list({r.get("result", {}).get("model") for r in results if r.get("result", {}).get("model")})
        self.audit_writer(event, {
            "run_id": run_id,
            "steps": len(steps),
            "approval_id": draft_approval_id,
            "decision_type": final_status,
            "web_search_used": "search" in tools_used,
            "redaction_used": bool(getattr(self, "_redacted_task", task) != task),
            "provider": providers_used[0] if len(providers_used) == 1 else (providers_used or None),
            "model": models_used[0] if len(models_used) == 1 else (models_used or None),
        })
        return final_response

    def continue_after_approval(self, approval_id: int) -> dict[str, Any]:
        approval = get_approval_request(approval_id) if self.persist_runs else None
        run_id = str(approval.get("run_id") if approval and approval.get("run_id") else uuid4())
        if self.persist_runs and approval and not approval.get("run_id"):
            self.create_run_record(run_id, f"Continue approval #{approval_id}")
        self.audit_writer("agent.resume.started", {"run_id": run_id, "approval_id": approval_id})
        try:
            response = self.approved_tool_executor(approval_id)
        except HTTPException as exc:
            status = "rejected" if approval and approval.get("status") == "rejected" else "blocked"
            if exc.status_code >= 500:
                status = "failed"
            self.update_run_record(
                run_id,
                status=status,
                result={"approval_id": approval_id, "status_code": exc.status_code, "detail": exc.detail},
            )
            raise

        call = PlannedToolCall(
            tool=str(response.get("tool", "")),
            parameters=dict(response.get("parameters", {})),
        )
        step = build_step(1, call, response)

        if response.get("status") == "pending":
            self.update_run_record(
                run_id,
                status="pending_approval",
                pending_approval_id=approval_id,
                result={"message": response.get("message", "Approval is still pending"), "steps": [step]},
            )
            self.audit_writer(
                "agent.resume.pending_approval",
                {"run_id": run_id, "approval_id": approval_id},
            )
            return {
                "run_id": run_id,
                "status": "pending_approval",
                "message": response.get("message", "Approval is still pending"),
                "approval_id": approval_id,
                "risk_level": response.get("risk_level"),
                "steps": [step],
                "next_action": "approve_or_reject",
            }

        result = response.get("result")
        final_response = {
            "run_id": run_id,
            "status": "completed",
            "message": "Approved tool call executed",
            "approval_id": approval_id,
            "steps": [step],
            "results": [
                {
                    "tool": call.tool,
                    "parameters": call.parameters,
                    "summary": summarize_tool_result(call.tool, result),
                    "result": result,
                }
            ],
        }
        self.update_run_record(run_id, status="completed", pending_approval_id=None, result=final_response)
        self.audit_writer(
            "agent.resume.completed",
            {"run_id": run_id, "approval_id": approval_id, "tool": call.tool},
        )
        return final_response

    def stream(
        self,
        task: str,
        wait_for_approval: bool = False,
        approval_poll_interval: float = 1.0,
        approval_timeout: float = 300.0,
    ) -> Iterator[dict[str, Any]]:
        run_id = str(uuid4())
        plan = plan_tool_calls(task)
        self.create_run_record(run_id, task, streaming=True)
        self.audit_writer(
            "agent.run.started",
            {"run_id": run_id, "planned_steps": len(plan), "streaming": True},
        )
        yield stream_event(
            "run_started",
            {"run_id": run_id, "status": "running", "task": task, "planned_steps": len(plan)},
        )

        steps: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        for index, call in enumerate(plan, start=1):
            self.audit_writer(
                "agent.tool.planned",
                {
                    "run_id": run_id,
                    "step": index,
                    "tool": call.tool,
                    "parameters": {k: f"<{type(v).__name__}:{len(str(v))}>" for k, v in call.parameters.items()},
                    "streaming": True,
                },
            )
            yield stream_event(
                "tool_planned",
                {
                    "run_id": run_id,
                    "step": index,
                    "tool": call.tool,
                    "parameters": call.parameters,
                },
            )
            yield stream_event(
                "tool_started",
                {
                    "run_id": run_id,
                    "step": index,
                    "tool": call.tool,
                    "parameters": call.parameters,
                },
            )

            try:
                response = self.tool_executor(call.tool, call.parameters)
            except HTTPException as exc:
                if _is_missing_provider_error(exc):
                    local_result = _build_local_response(run_id, task)
                    self.update_run_record(run_id, status="local_only", result=local_result)
                    self.audit_writer(
                        "agent.degraded_missing_provider",
                        {
                            "run_id": run_id,
                            "tool": call.tool,
                            "mode": "local_only",
                            "reason": "provider_not_configured",
                            "streaming": True,
                        },
                    )
                    yield stream_event("local_only", local_result)
                    return
                status = "blocked" if exc.status_code == 403 else "failed"
                event_name = "blocked" if exc.status_code == 403 else "error"
                self.update_run_record(
                    run_id,
                    status=status,
                    result={"status_code": exc.status_code, "detail": exc.detail},
                )
                self.audit_writer(
                    f"agent.run.{status}",
                    {
                        "run_id": run_id,
                        "step": index,
                        "tool": call.tool,
                        "parameters": {k: f"<{type(v).__name__}:{len(str(v))}>" for k, v in call.parameters.items()},
                        "status_code": exc.status_code,
                    },
                )
                yield stream_event(
                    event_name,
                    {
                        "run_id": run_id,
                        "status": status,
                        "step": index,
                        "tool": call.tool,
                        "status_code": exc.status_code,
                        "detail": exc.detail,
                    },
                )
                return
            except Exception as exc:
                self.update_run_record(run_id, status="failed", result={"detail": str(exc)})
                self.audit_writer(
                    "agent.run.failed",
                    {
                        "run_id": run_id,
                        "step": index,
                        "tool": call.tool,
                        "parameters": call.parameters,
                        "detail": str(exc),
                    },
                )
                yield stream_event(
                    "error",
                    {
                        "run_id": run_id,
                        "status": "failed",
                        "step": index,
                        "tool": call.tool,
                        "detail": str(exc),
                    },
                )
                return

            step = build_step(index, call, response)
            steps.append(step)

            if response.get("status") == "pending":
                approval_id = response.get("approval_id")
                self.link_approval_record(approval_id, run_id)
                self.update_run_record(
                    run_id,
                    status="pending_approval",
                    pending_approval_id=approval_id,
                    result={
                        "message": response.get("message", "Approval required"),
                        "steps": steps,
                        "next_action": "approve_or_reject",
                    },
                )
                self.audit_writer(
                    "agent.run.pending_approval",
                    {
                        "run_id": run_id,
                        "approval_id": approval_id,
                        "tool": call.tool,
                        "parameters": {k: f"<{type(v).__name__}:{len(str(v))}>" for k, v in call.parameters.items()},
                        "streaming": True,
                    },
                )
                yield stream_event(
                    "approval_required",
                    {
                        "run_id": run_id,
                        "status": "pending_approval",
                        "message": response.get("message", "Approval required"),
                        "approval_id": approval_id,
                        "risk_level": response.get("risk_level"),
                        "steps": steps,
                        "next_action": "approve_or_reject",
                    },
                )
                if not wait_for_approval:
                    return

                if approval_id is None:
                    self.update_run_record(run_id, status="failed", result={"detail": "Approval id is missing"})
                    yield stream_event(
                        "error",
                        {"run_id": run_id, "status": "failed", "detail": "Approval id is missing"},
                    )
                    return

                deadline = time.monotonic() + approval_timeout
                poll_interval = max(0.1, approval_poll_interval)
                yield stream_event(
                    "approval_waiting",
                    {
                        "run_id": run_id,
                        "status": "pending_approval",
                        "approval_id": approval_id,
                        "timeout_seconds": approval_timeout,
                    },
                )

                while True:
                    approval = get_approval_request(int(approval_id))
                    if approval is None:
                        self.update_run_record(
                            run_id,
                            status="failed",
                            result={"approval_id": approval_id, "detail": "Approval request not found"},
                        )
                        yield stream_event(
                            "error",
                            {
                                "run_id": run_id,
                                "status": "failed",
                                "approval_id": approval_id,
                                "detail": "Approval request not found",
                            },
                        )
                        return

                    if approval["status"] == "pending":
                        if time.monotonic() >= deadline:
                            yield stream_event(
                                "approval_timeout",
                                {
                                    "run_id": run_id,
                                    "status": "pending_approval",
                                    "approval_id": approval_id,
                                },
                            )
                            return

                        time.sleep(poll_interval)
                        yield stream_event(
                            "approval_waiting",
                            {
                                "run_id": run_id,
                                "status": "pending_approval",
                                "approval_id": approval_id,
                            },
                        )
                        continue

                    if approval["status"] == "rejected":
                        final_response = {
                            "run_id": run_id,
                            "status": "rejected",
                            "message": "Approval was rejected",
                            "approval_id": approval_id,
                            "steps": steps,
                        }
                        self.update_run_record(run_id, status="rejected", result=final_response)
                        self.audit_writer(
                            "agent.run.rejected",
                            {"run_id": run_id, "approval_id": approval_id, "streaming": True},
                        )
                        yield stream_event("approval_rejected", final_response)
                        return

                    if approval["status"] != "approved":
                        final_response = {
                            "run_id": run_id,
                            "status": "blocked",
                            "approval_id": approval_id,
                            "detail": f"Unsupported approval status: {approval['status']}",
                        }
                        self.update_run_record(run_id, status="blocked", result=final_response)
                        yield stream_event("blocked", final_response)
                        return

                    self.update_run_record(run_id, status="running")
                    yield stream_event(
                        "approval_granted",
                        {"run_id": run_id, "status": "running", "approval_id": approval_id},
                    )
                    try:
                        response = self.approved_tool_executor(int(approval_id))
                    except HTTPException as exc:
                        status = "blocked" if exc.status_code == 403 else "failed"
                        event_name = "blocked" if exc.status_code == 403 else "error"
                        self.update_run_record(
                            run_id,
                            status=status,
                            result={
                                "approval_id": approval_id,
                                "status_code": exc.status_code,
                                "detail": exc.detail,
                            },
                        )
                        yield stream_event(
                            event_name,
                            {
                                "run_id": run_id,
                                "status": status,
                                "approval_id": approval_id,
                                "status_code": exc.status_code,
                                "detail": exc.detail,
                            },
                        )
                        return
                    except Exception as exc:
                        self.update_run_record(
                            run_id,
                            status="failed",
                            result={"approval_id": approval_id, "detail": str(exc)},
                        )
                        yield stream_event(
                            "error",
                            {
                                "run_id": run_id,
                                "status": "failed",
                                "approval_id": approval_id,
                                "detail": str(exc),
                            },
                        )
                        return

                    step = build_step(index, call, response)
                    steps[-1] = step
                    break

            result = response.get("result")
            result_entry = {
                "tool": call.tool,
                "parameters": call.parameters,
                "summary": summarize_tool_result(call.tool, result),
                "result": result,
            }
            results.append(result_entry)
            yield stream_event(
                "tool_completed",
                {
                    "run_id": run_id,
                    "step": index,
                    "tool": call.tool,
                    "parameters": call.parameters,
                    "summary": result_entry["summary"],
                },
            )

        final_response = {
            "run_id": run_id,
            "status": "completed",
            "message": "Agent run completed",
            "steps": steps,
            "results": results,
        }
        self.update_run_record(run_id, status="completed", pending_approval_id=None, result=final_response)
        self.audit_writer("agent.run.completed", {"run_id": run_id, "steps": len(steps), "streaming": True})
        yield stream_event("run_completed", final_response)

    def stream_after_approval(self, approval_id: int) -> Iterator[dict[str, Any]]:
        approval = get_approval_request(approval_id) if self.persist_runs else None
        run_id = str(approval.get("run_id") if approval and approval.get("run_id") else uuid4())
        if self.persist_runs and approval and not approval.get("run_id"):
            self.create_run_record(run_id, f"Continue approval #{approval_id}", streaming=True)
        self.audit_writer(
            "agent.resume.started",
            {"run_id": run_id, "approval_id": approval_id, "streaming": True},
        )
        yield stream_event(
            "resume_started",
            {"run_id": run_id, "status": "running", "approval_id": approval_id},
        )

        try:
            response = self.approved_tool_executor(approval_id)
        except HTTPException as exc:
            status = "rejected" if approval and approval.get("status") == "rejected" else "blocked"
            if exc.status_code >= 500:
                status = "failed"
            event_name = "approval_rejected" if status == "rejected" else "blocked"
            if status == "failed":
                event_name = "error"
            self.update_run_record(
                run_id,
                status=status,
                result={"approval_id": approval_id, "status_code": exc.status_code, "detail": exc.detail},
            )
            self.audit_writer(
                "agent.resume.blocked",
                {
                    "run_id": run_id,
                    "approval_id": approval_id,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                },
            )
            yield stream_event(
                event_name,
                {
                    "run_id": run_id,
                    "status": status,
                    "approval_id": approval_id,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                },
            )
            return
        except Exception as exc:
            self.update_run_record(run_id, status="failed", result={"approval_id": approval_id, "detail": str(exc)})
            self.audit_writer(
                "agent.resume.failed",
                {"run_id": run_id, "approval_id": approval_id, "detail": str(exc)},
            )
            yield stream_event(
                "error",
                {
                    "run_id": run_id,
                    "status": "failed",
                    "approval_id": approval_id,
                    "detail": str(exc),
                },
            )
            return

        call = PlannedToolCall(
            tool=str(response.get("tool", "")),
            parameters=dict(response.get("parameters", {})),
        )
        step = build_step(1, call, response)

        if response.get("status") == "pending":
            self.update_run_record(
                run_id,
                status="pending_approval",
                pending_approval_id=approval_id,
                result={"message": response.get("message", "Approval is still pending"), "steps": [step]},
            )
            self.audit_writer(
                "agent.resume.pending_approval",
                {"run_id": run_id, "approval_id": approval_id, "streaming": True},
            )
            yield stream_event(
                "approval_pending",
                {
                    "run_id": run_id,
                    "status": "pending_approval",
                    "message": response.get("message", "Approval is still pending"),
                    "approval_id": approval_id,
                    "risk_level": response.get("risk_level"),
                    "steps": [step],
                    "next_action": "approve_or_reject",
                },
            )
            return

        result = response.get("result")
        summary = summarize_tool_result(call.tool, result)
        yield stream_event(
            "tool_completed",
            {
                "run_id": run_id,
                "approval_id": approval_id,
                "step": 1,
                "tool": call.tool,
                "parameters": call.parameters,
                "summary": summary,
            },
        )
        final_response = {
            "run_id": run_id,
            "status": "completed",
            "message": "Approved tool call executed",
            "approval_id": approval_id,
            "steps": [step],
            "results": [
                {
                    "tool": call.tool,
                    "parameters": call.parameters,
                    "summary": summary,
                    "result": result,
                }
            ],
        }
        self.update_run_record(run_id, status="completed", pending_approval_id=None, result=final_response)
        self.audit_writer(
            "agent.resume.completed",
            {"run_id": run_id, "approval_id": approval_id, "tool": call.tool, "streaming": True},
        )
        yield stream_event("resume_completed", final_response)


def plan_tool_calls(task: str) -> list[PlannedToolCall]:
    urls = [clean_url(match.group(0)) for match in URL_PATTERN.finditer(task)]
    if urls:
        return [PlannedToolCall("fetch", {"url": url}) for url in urls]

    return [PlannedToolCall("search", {"query": task.strip()})]


def clean_url(url: str) -> str:
    return url.rstrip(".,;:")


def stream_event(event: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"event": event, "data": data}


def build_step(index: int, call: PlannedToolCall, response: dict[str, Any]) -> dict[str, Any]:
    status = response.get("status", "completed")
    step: dict[str, Any] = {
        "step": index,
        "tool": call.tool,
        "parameters": call.parameters,
        "status": "pending_approval" if status == "pending" else status,
    }
    if status == "pending":
        step["approval_id"] = response.get("approval_id")
        step["risk_level"] = response.get("risk_level")
        step["message"] = response.get("message")
    else:
        step["summary"] = summarize_tool_result(call.tool, response.get("result"))
    return step


def summarize_tool_result(tool_name: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"type": type(result).__name__}

    if tool_name == "fetch":
        text = str(result.get("text", ""))
        return {
            "title": result.get("title", ""),
            "text_preview": text[:500],
            "text_length": len(text),
        }

    if tool_name == "search":
        raw_results = result.get("results")
        if isinstance(raw_results, list):
            return {
                "result_count": len(raw_results),
                "top_results": [
                    {
                        "title": item.get("title"),
                        "url": item.get("url"),
                        "content": str(item.get("content", ""))[:240],
                    }
                    for item in raw_results[:5]
                    if isinstance(item, dict)
                ],
            }

    return {"keys": sorted(str(key) for key in result.keys())}
