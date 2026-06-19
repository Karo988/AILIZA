from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

import json
import os
import re
from datetime import datetime
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

try:
    from .agent_runtime import AgentRuntime
    from .database import (
        get_agent_run, init_db, list_agent_runs, list_audit_entries, write_audit_entry,
        insert_feedback, count_negative_feedback, insert_routing_proposal,
        adjust_fact_quality_for_run, DEFAULT_TENANT_ID,
    )
    from .gateway import guarded_tool_call
    from .routers.approvals import router as approvals_router
    from .errors import AILIZAError, MESSAGES
    from .providers.orchestrator import ProviderOrchestrator
    from .documents.document_handler import scan_document
except ImportError:
    from agent_runtime import AgentRuntime
    from database import (
        get_agent_run, init_db, list_agent_runs, list_audit_entries, write_audit_entry,
        insert_feedback, count_negative_feedback, insert_routing_proposal,
        adjust_fact_quality_for_run, DEFAULT_TENANT_ID,
    )
    from gateway import guarded_tool_call
    from routers.approvals import router as approvals_router
    from errors import AILIZAError, MESSAGES
    from providers.orchestrator import ProviderOrchestrator
    from documents.document_handler import scan_document


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    try:
        from .maintenance.retention_cleanup import run_cleanup
    except ImportError:
        from maintenance.retention_cleanup import run_cleanup
    run_cleanup()
    yield


app = FastAPI(title="AILIZA Backend", lifespan=lifespan)
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"

# CORS: in Produktion über AILIZA_CORS_ORIGINS einschränken (kommasepariert).
# Default bleibt "*" für lokale Entwicklung — nie in Produktion so lassen.
_raw_origins = os.getenv("AILIZA_CORS_ORIGINS", "*")
_cors_origins: list[str] | str = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins != "*"
    else ["*"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(approvals_router)


from fastapi.responses import JSONResponse
from fastapi import Request, UploadFile, File


@app.exception_handler(AILIZAError)
async def ailiza_error_handler(_request: Request, exc: AILIZAError) -> JSONResponse:
    # Niemals Stack-Trace zum Client. Nur saubere deutsche Meldung.
    return JSONResponse(status_code=400, content=exc.to_dict())


@app.exception_handler(Exception)
async def generic_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "code": "internal_error",
            "message": MESSAGES["internal_error"],
            "safe_alternatives": [],
        },
    )


class AuditLogCreate(BaseModel):
    action: str = Field(..., min_length=1, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)


class ToolFetchRequest(BaseModel):
    url: str = Field(..., min_length=1)


class AgentRunRequest(BaseModel):
    task: str = Field(..., min_length=1)

    @field_validator("task")
    @classmethod
    def validate_task(cls, value: str) -> str:
        task = value.strip()
        if not task:
            raise ValueError("task is required")
        return task


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/audit-logs", status_code=201)
def create_audit_log(payload: AuditLogCreate) -> dict[str, Any]:
    return write_audit_entry(action=payload.action, metadata=payload.metadata)


@app.get("/audit-logs")
def get_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    return list_audit_entries(limit=limit)


def sse_response(events: Iterable[dict[str, Any]]) -> StreamingResponse:
    return StreamingResponse(
        encode_sse(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def encode_sse(events: Iterable[dict[str, Any]]):
    for event in events:
        event_name = str(event.get("event", "message"))
        data = json.dumps(event.get("data", {}), ensure_ascii=True, default=str)
        yield f"event: {event_name}\ndata: {data}\n\n"


def serialize_agent_run(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "created_at": entry["created_at"],
        "updated_at": entry["updated_at"],
        "task": entry["task"],
        "status": entry["status"],
        "pending_approval_id": entry["pending_approval_id"],
        "result": entry["result"],
        "metadata": entry["run_metadata"],
    }


@app.post("/tools/search")
def search_tools(
    query: str | None = Query(default=None, min_length=1),
    payload: ToolSearchRequest | None = Body(default=None),
) -> dict[str, Any]:
    search_query = query or (payload.query if payload else None)
    if search_query is None:
        raise HTTPException(status_code=422, detail="query is required")
    write_audit_entry(action="tools.search", metadata={"query": search_query})
    parameters = {"query": search_query}
    response = guarded_tool_call("search", parameters)
    if response.get("status") == "completed":
        return response["result"]
    return response


@app.post("/tools/fetch")
def fetch_tool(
    url: str | None = Query(default=None, min_length=1),
    payload: ToolFetchRequest | None = Body(default=None),
) -> dict[str, Any]:
    fetch_url = url or (payload.url if payload else None)
    if fetch_url is None:
        raise HTTPException(status_code=422, detail="url is required")
    write_audit_entry(action="tools.fetch", metadata={"url": fetch_url})
    parameters = {"url": fetch_url}
    response = guarded_tool_call("fetch", parameters)
    if response.get("status") == "completed":
        return response["result"]
    return response


def answer_simple_question(task: str) -> str | None:
    text = " ".join(task.lower().strip().replace("?", "").split())
    now = datetime.now()

    if not text:
        return None
    if any(phrase in text for phrase in ("welchen tag haben wir heute", "welcher tag ist heute", "was ist heute fuer ein tag", "was ist heute für ein tag", "welches datum", "datum heute", "heutiges datum")):
        return now.strftime("%d.%m.%Y")
    if "wochentag" in text:
        weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        return weekdays[now.weekday()]
    if "uhrzeit" in text or "wie spaet" in text or "wie spät" in text:
        return now.strftime("%H:%M Uhr")
    if "welches jahr" in text or "jahr haben wir" in text:
        return str(now.year)
    if "welcher monat" in text or "monat haben wir" in text:
        months = ["Januar", "Februar", "Maerz", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
        return months[now.month - 1]
    if text in {"hallo", "hi", "hey", "guten tag", "guten morgen", "guten abend"}:
        return "Hallo!"
    if text in {"danke", "dankeschoen", "dankeschön", "vielen dank"}:
        return "Gern."
    if "wer bist du" in text or "wie heisst du" in text or "wie heißt du" in text:
        return "Ich bin AILIZA."
    if "was kannst du" in text:
        return "Ich helfe bei E-Mails, Recherche, Übersetzungen und Zusammenfassungen."

    expression = text
    for prefix in ("was ist", "rechne", "berechne"):
        if expression.startswith(prefix + " "):
            expression = expression[len(prefix):].strip()
            break
    expression = expression.replace("plus", "+").replace("minus", "-").replace("mal", "*").replace("geteilt durch", "/")
    if re.fullmatch(r"[0-9+\-*/()., ]+", expression) and re.search(r"[+\-*/]", expression):
        try:
            value = eval(expression.replace(",", "."), {"__builtins__": {}}, {})
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            return str(value)
        except Exception:
            return None

    return None

def extract_agent_answer(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return ""

    parts: list[str] = []
    for step in result.get("results", []):
        if not isinstance(step, dict):
            continue
        for key in ("result", "summary"):
            data = step.get(key)
            if not isinstance(data, dict):
                continue
            summary = data.get("summary")
            if isinstance(summary, str) and summary.strip():
                parts.append(summary.strip())
            top_results = data.get("top_results")
            if isinstance(top_results, list):
                for top in top_results[:3]:
                    if isinstance(top, dict):
                        title = str(top.get("title") or "").strip()
                        content = str(top.get("content") or "").strip()
                        line = f"{title}: {content}" if title else content
                        if line.strip():
                            parts.append(line.strip())

    return "\n".join(parts).strip()
_orchestrator = ProviderOrchestrator()


def _summarize_with_llm(task: str, search_text: str) -> tuple[str | None, str | None]:
    """
    Fasst ein Suchergebnis ueber den Provider-Orchestrator zusammen.
    Kein direkter Provider-Call hier. Kill-Switch/Governance liegen im Orchestrator.
    Gibt (antwort, fehler_code) zurueck.
    """
    sys_prompt = (
        "Du bist AILIZA, ein autonomer KI-Assistent fuer KMU. Antworte kurz und direkt "
        "auf Deutsch. Bei einfachen Fragen 1-2 Saetze. Keine Auflistung."
    )
    user_msg = (
        f'Frage: "{task}"\n\nSuchergebnis:\n{search_text}\n\n'
        "Formuliere eine kurze direkte Antwort."
    )
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_msg},
    ]
    try:
        answer = _orchestrator.generate(messages, context=None)
        return answer, None
    except AILIZAError as exc:
        return None, exc.code


@app.post("/agent/run")
def run_agent(payload: AgentRunRequest) -> dict[str, Any]:
    simple_answer = answer_simple_question(payload.task)
    if simple_answer is not None:
        return {
            "status": "completed",
            "message": simple_answer,
            "ai_response": simple_answer,
            "steps": [],
            "results": [],
        }

    runtime = AgentRuntime()
    result = runtime.run(payload.task)

    search_text = extract_agent_answer(result)

    if search_text:
        answer, error_code = _summarize_with_llm(payload.task, search_text)
        if answer is not None:
            result["message"] = answer
        else:
            # Fail-closed: lokal vorhandenes Suchergebnis als Antwort verwenden.
            result["message"] = search_text
            if error_code:
                result["llm_notice"] = MESSAGES.get(error_code, "")
    elif result.get("message") == "Agent run completed" and search_text:
        result["message"] = search_text

    result["ai_response"] = result.get("message", "")
    return result
@app.get("/agent/runs")
def get_agent_runs(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return [serialize_agent_run(entry) for entry in list_agent_runs(status=status, limit=limit)]


@app.get("/agent/runs/{run_id}")
def get_agent_run_status(run_id: str) -> dict[str, Any]:
    entry = get_agent_run(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return serialize_agent_run(entry)


@app.get("/agent/run/stream")
def stream_agent_run(
    task: str = Query(..., min_length=1),
    wait_for_approval: bool = Query(default=False),
    approval_poll_interval: float = Query(default=1.0, ge=0.1, le=30.0),
    approval_timeout: float = Query(default=300.0, ge=1.0, le=3600.0),
) -> StreamingResponse:
    task = task.strip()
    if not task:
        raise HTTPException(status_code=422, detail="task is required")
    runtime = AgentRuntime()
    return sse_response(
        runtime.stream(
            task,
            wait_for_approval=wait_for_approval,
            approval_poll_interval=approval_poll_interval,
            approval_timeout=approval_timeout,
        )
    )


@app.post("/agent/run/stream")
def stream_agent_run_post(
    payload: AgentRunRequest,
    wait_for_approval: bool = Query(default=False),
    approval_poll_interval: float = Query(default=1.0, ge=0.1, le=30.0),
    approval_timeout: float = Query(default=300.0, ge=1.0, le=3600.0),
) -> StreamingResponse:
    runtime = AgentRuntime()
    return sse_response(
        runtime.stream(
            payload.task,
            wait_for_approval=wait_for_approval,
            approval_poll_interval=approval_poll_interval,
            approval_timeout=approval_timeout,
        )
    )


@app.post("/agent/approvals/{approval_id}/continue")
def continue_agent_after_approval(approval_id: int) -> dict[str, Any]:
    runtime = AgentRuntime()
    return runtime.continue_after_approval(approval_id)


@app.get("/agent/approvals/{approval_id}/continue/stream")
def stream_agent_after_approval(approval_id: int) -> StreamingResponse:
    runtime = AgentRuntime()
    return sse_response(runtime.stream_after_approval(approval_id))


@app.post("/agent/approvals/{approval_id}/continue/stream")
def stream_agent_after_approval_post(approval_id: int) -> StreamingResponse:
    runtime = AgentRuntime()
    return sse_response(runtime.stream_after_approval(approval_id))


class FeedbackRequest(BaseModel):
    run_id: str | None = None
    rating: str = Field(..., pattern="^(helpful|not_helpful)$")
    reason: str | None = None
    tenant_id: str = Field(default=DEFAULT_TENANT_ID)


@app.post("/feedback", status_code=201)
def submit_feedback(payload: FeedbackRequest) -> dict[str, Any]:
    delta = 0.1 if payload.rating == "helpful" else -0.2
    entry = insert_feedback(
        tenant_id=payload.tenant_id, run_id=payload.run_id,
        rating=payload.rating, reason=payload.reason, quality_score_delta=delta)
    if payload.run_id:
        adjust_fact_quality_for_run(payload.run_id, delta, tenant_id=payload.tenant_id)

    admin_suggestion = None
    if payload.rating == "not_helpful":
        negatives = count_negative_feedback(payload.tenant_id, payload.run_id)
        # Ab 3 negativen Ratings: Admin-Vorschlag erzeugen (keine automatische Aenderung).
        if negatives >= 3:
            proposal = insert_routing_proposal(
                tenant_id=payload.tenant_id, trigger_type="negative_feedback",
                description=f"{negatives} negative Bewertungen fuer run {payload.run_id}.",
                reason="Schwellwert von 3 negativen Bewertungen erreicht.")
            admin_suggestion = proposal["id"]
    write_audit_entry(action="feedback.submitted",
                      metadata={"rating": payload.rating, "run_id": payload.run_id},
                      tenant_id=payload.tenant_id)
    return {"status": "ok", "feedback_id": entry["id"], "admin_proposal_id": admin_suggestion}


@app.post("/documents/scan")
async def documents_scan(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    scan = scan_document(file.filename or "", content)
    write_audit_entry(action="documents.scan",
                      metadata={"file_type": scan.file_type, "decision": scan.decision,
                                "size_bytes": scan.size_bytes})
    return {
        "allowed": scan.allowed,
        "file_type": scan.file_type,
        "size_bytes": scan.size_bytes,
        "decision": scan.decision,
        "reason": scan.reason,
        "expires_at": scan.expires_at,
        "data_classes": [c.value for c in scan.classification.data_classes],
        "highest_risk_class": scan.classification.highest_risk_class.value,
        "needs_review": scan.classification.needs_review,
    }


@app.post("/admin/cleanup")
def admin_cleanup() -> dict[str, Any]:
    """Retention-Cleanup manuell auslösen — löscht abgelaufene Einträge."""
    try:
        from .maintenance.retention_cleanup import run_cleanup
    except ImportError:
        from maintenance.retention_cleanup import run_cleanup
    result = run_cleanup()
    write_audit_entry(action="admin.cleanup", metadata={"total_deleted": result["total_deleted"]})
    return result


@app.get("/admin/provider-profiles")
def list_provider_profiles() -> list[dict[str, Any]]:
    """Gibt alle konfigurierten ProviderProfile zurück (ohne API-Keys)."""
    try:
        from .providers.provider_profiles import get_active_profiles, profile_to_dict
    except ImportError:
        from providers.provider_profiles import get_active_profiles, profile_to_dict
    return [profile_to_dict(p) for p in get_active_profiles()]


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dashboard")
def dashboard():
    return FileResponse(FRONTEND_DIR / "index.html")
