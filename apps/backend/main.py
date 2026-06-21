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
    from .database import get_agent_run, init_db, list_agent_runs, list_audit_entries, write_audit_entry
    from .gateway import guarded_tool_call
    from .routers.approvals import router as approvals_router
except ImportError:
    from agent_runtime import AgentRuntime
    from database import get_agent_run, init_db, list_agent_runs, list_audit_entries, write_audit_entry
    from gateway import guarded_tool_call
    from routers.approvals import router as approvals_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="AILIZA Backend", lifespan=lifespan)
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("AILIZA_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(approvals_router)


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
    if any(phrase in text for phrase in ("welchen tag haben wir heute", "welcher tag ist heute", "was ist heute fuer ein tag", "was ist heute fuer ein tag", "welches datum", "datum heute", "heutiges datum")):
        return now.strftime("%d.%m.%Y")
    if "wochentag" in text:
        weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        return weekdays[now.weekday()]
    if "uhrzeit" in text or "wie spaet" in text or "wie spaet" in text:
        return now.strftime("%H:%M Uhr")
    if "welches jahr" in text or "jahr haben wir" in text:
        return str(now.year)
    if "welcher monat" in text or "monat haben wir" in text:
        months = ["Januar", "Februar", "Maerz", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
        return months[now.month - 1]
    if text in {"hallo", "hi", "hey", "guten tag", "guten morgen", "guten abend"}:
        return "Hallo!"
    if text in {"danke", "dankeschoen", "dankeschoen", "vielen dank"}:
        return "Gern."
    if "wer bist du" in text or "wie heisst du" in text or "wie heisst du" in text:
        return "Ich bin AILIZA."
    if "was kannst du" in text:
        return "Ich helfe bei E-Mails, Recherche, Uebersetzungen und Zusammenfassungen."

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

@app.post("/agent/run")
def run_agent(payload: AgentRunRequest) -> dict[str, Any]:
    import os, urllib.request, json as _json
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

    external_enabled = os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "false").lower() == "true"
    api_key = os.getenv("GROQ_API_KEY")
    if search_text and api_key and external_enabled:
        sys_prompt = "Du bist AILIZA, ein autonomer KI-Assistent fuer KMU. Antworte kurz und direkt auf Deutsch. Bei einfachen Fragen 1-2 Saetze. Keine Auflistung."
        user_msg = f'Frage: "{payload.task}"\n\nSuchergebnis:\n{search_text}\n\nFormuliere eine kurze direkte Antwort.'
        last_error = None
        for model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
            try:
                req_data = _json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 600,
                    "temperature": 0.3,
                }).encode()
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=req_data,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                )
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = _json.loads(r.read())
                    result["message"] = data["choices"][0]["message"]["content"]
                    result["model"] = model
                    last_error = None
                    break
            except Exception as e:
                last_error = e
        else:
            result["message"] = search_text
            result["llm_error"] = str(last_error) if last_error else "Groq request failed"
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


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/dashboard")
def dashboard():
    return FileResponse(FRONTEND_DIR / "index.html")
