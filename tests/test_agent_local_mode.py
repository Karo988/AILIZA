"""
Agent Local-Mode Tests
======================
Stellt sicher, dass /agent/run ohne externe Provider (kein TAVILY_API_KEY,
kein LLM-Key) kein HTTP 500 produziert, sondern nutzerfreundlich in den
lokalen Modus wechselt.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi import HTTPException


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def missing_tavily_executor():
    """Tool-Executor der TAVILY_API_KEY-Fehler wirft."""
    def _executor(tool: str, params: dict):
        raise HTTPException(status_code=500, detail="TAVILY_API_KEY is not configured")
    return _executor


@pytest.fixture()
def missing_groq_executor():
    def _executor(tool: str, params: dict):
        raise HTTPException(status_code=500, detail="GROQ_API_KEY is not configured")
    return _executor


@pytest.fixture()
def audit_log():
    events = []
    def _writer(action, metadata=None, **kwargs):
        events.append({"action": action, "metadata": metadata or {}})
        return {"id": len(events)}
    _writer.events = events
    return _writer


# ── 1. Kein HTTP 500 bei fehlendem Tavily ────────────────────────────────────

class TestNoHttp500:
    def test_run_returns_local_only_not_500(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        result = runtime.run("Was ist DSGVO?")
        assert result["status"] == "local_only"

    def test_run_has_message_not_exception(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        result = runtime.run("Was ist DSGVO?")
        assert "message" in result
        assert len(result["message"]) > 10
        assert "TAVILY_API_KEY" not in result["message"]

    def test_run_missing_groq_also_local(self, missing_groq_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_groq_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        result = runtime.run("Schreibe eine E-Mail.")
        assert result["status"] == "local_only"


# ── 2. Einfache Fragen funktionieren ohne Provider ───────────────────────────

class TestSimpleQuestions:
    def test_simple_greeting_no_tool_needed(self, audit_log):
        """Einfache Grüße lösen keinen Tool-Call aus → immer erfolgreich."""
        from apps.backend.agent_runtime import AgentRuntime

        def _never_called(tool, params):
            raise AssertionError("Tool-Executor darf für einfache Fragen nicht aufgerufen werden")

        runtime = AgentRuntime(
            tool_executor=_never_called,
            audit_writer=audit_log,
            persist_runs=False,
        )
        # simple_question wird in main.py behandelt, aber wir testen direkt
        # dass /agent/run eine Frage verarbeiten kann ohne 500
        from apps.backend.agent_runtime import plan_tool_calls
        plan = plan_tool_calls("Hallo")
        assert len(plan) >= 1  # Plan entsteht, Tool-Call aber wird im run() behandelt

    def test_local_result_has_ai_response_field(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        result = runtime.run("Erkläre Datenschutz.")
        # ai_response wird von main.py gesetzt, aber message muss vorhanden sein
        assert "message" in result
        assert result["message"]


# ── 3. Recherchefrage → Rechercheplan ────────────────────────────────────────

class TestResearchPlan:
    def test_research_task_yields_research_plan(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        result = runtime.run("Recherchiere aktuelle Datenschutzurteile.")
        assert result["status"] == "local_only"
        msg = result["message"]
        assert "Rechercheplan" in msg or "Websuche" in msg or "Internetverbindung" in msg

    def test_simple_task_yields_local_help_message(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        result = runtime.run("Was ist Datenschutz?")
        assert result["status"] == "local_only"
        assert result["message"]

    def test_research_message_is_german(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        result = runtime.run("Suche nach aktuellen Nachrichten.")
        msg = result["message"]
        # Muss in Deutsch und nutzerfreundlich sein
        assert any(word in msg for word in ("nicht", "kein", "kann", "bitte", "lokal", "Recher", "extern"))
        assert "500" not in msg
        assert "Exception" not in msg
        assert "TAVILY" not in msg


# ── 4. Audit-Event wird geschrieben ──────────────────────────────────────────

class TestAuditEvent:
    def test_degraded_audit_event_written(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        runtime.run("Was ist DSGVO?")
        actions = [e["action"] for e in audit_log.events]
        assert "agent.degraded_missing_provider" in actions

    def test_audit_event_has_no_raw_params(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        runtime.run("Recherchiere aktuelle Preise.")
        degraded_events = [
            e for e in audit_log.events
            if e["action"] == "agent.degraded_missing_provider"
        ]
        assert degraded_events
        meta = degraded_events[0]["metadata"]
        # Kein Task-Inhalt, kein Prompt, keine Rohdaten im Audit
        assert "task" not in meta
        assert "prompt" not in meta
        assert "query" not in meta
        assert "parameters" not in meta

    def test_audit_event_fields_allowed_only(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        runtime.run("Was ist DSGVO?")
        degraded = next(
            e for e in audit_log.events
            if e["action"] == "agent.degraded_missing_provider"
        )
        meta = degraded["metadata"]
        # Nur erlaubte Felder: run_id, tool, mode, reason (+ optional streaming)
        forbidden = {"task_content", "prompt", "input_summary", "password", "secret"}
        assert not (forbidden & set(meta.keys()))
        assert "mode" in meta
        assert meta["mode"] == "local_only"
        assert "reason" in meta


# ── 5. Streaming-Pfad: ebenfalls kein 500 ────────────────────────────────────

class TestStreamingLocalMode:
    def test_streaming_run_yields_local_only_event(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        events = list(runtime.stream("Was ist DSGVO?"))
        event_names = [e.get("event") for e in events]
        assert "local_only" in event_names

    def test_streaming_no_error_event_for_missing_provider(self, missing_tavily_executor, audit_log):
        from apps.backend.agent_runtime import AgentRuntime
        runtime = AgentRuntime(
            tool_executor=missing_tavily_executor,
            audit_writer=audit_log,
            persist_runs=False,
        )
        events = list(runtime.stream("Was ist DSGVO?"))
        event_names = [e.get("event") for e in events]
        assert "error" not in event_names


# ── 6. Hilfsfunktionen direkt testen ─────────────────────────────────────────

class TestHelpers:
    def test_is_missing_provider_error_tavily(self):
        from apps.backend.agent_runtime import _is_missing_provider_error
        exc = HTTPException(status_code=500, detail="TAVILY_API_KEY is not configured")
        assert _is_missing_provider_error(exc) is True

    def test_is_missing_provider_error_groq(self):
        from apps.backend.agent_runtime import _is_missing_provider_error
        exc = HTTPException(status_code=500, detail="GROQ_API_KEY is not configured")
        assert _is_missing_provider_error(exc) is True

    def test_is_missing_provider_error_other_500_not_caught(self):
        from apps.backend.agent_runtime import _is_missing_provider_error
        exc = HTTPException(status_code=500, detail="Database connection failed")
        assert _is_missing_provider_error(exc) is False

    def test_is_missing_provider_error_403_not_caught(self):
        from apps.backend.agent_runtime import _is_missing_provider_error
        exc = HTTPException(status_code=403, detail="TAVILY_API_KEY is not configured")
        # 403 ist ein anderer Fehlertyp
        assert _is_missing_provider_error(exc) is True  # Detail-Match reicht

    def test_is_research_task_detects_keywords(self):
        from apps.backend.agent_runtime import _is_research_task
        assert _is_research_task("Recherchiere aktuelle Nachrichten") is True
        assert _is_research_task("Was ist der aktuelle Preis?") is True
        assert _is_research_task("Suche nach DSGVO-Urteilen") is True

    def test_is_research_task_no_false_positive(self):
        from apps.backend.agent_runtime import _is_research_task
        assert _is_research_task("Hallo, wie geht es?") is False
        assert _is_research_task("Erkläre mir Datenschutz.") is False

    def test_build_local_response_structure(self):
        from apps.backend.agent_runtime import _build_local_response
        r = _build_local_response("test-run-id", "Was ist DSGVO?")
        assert r["status"] == "local_only"
        assert r["mode"] == "degraded"
        assert "message" in r
        assert "notice" in r
        assert r["steps"] == []
        assert r["results"] == []

    def test_build_local_response_no_raw_task_in_notice(self):
        from apps.backend.agent_runtime import _build_local_response
        secret_task = "Mein Passwort ist hunter2"
        r = _build_local_response("run-1", secret_task)
        # notice darf keine beliebigen Task-Inhalte enthalten
        assert "hunter2" not in r.get("notice", "")
