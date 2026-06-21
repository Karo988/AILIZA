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
        get_or_create_user_profile, update_user_profile, complete_onboarding, delete_user_data,
        create_conversation, append_message, get_conversation_history, list_conversations,
        record_processing, list_processing_records, add_learned_rule, get_active_rules,
        update_rule_confidence, deactivate_rule, record_feedback,
    )
    from .gateway import guarded_tool_call
    from .routers.approvals import router as approvals_router
    from .intelligent_agent import IntelligentAgentRuntime
    from .security.key_manager import get_key_manager
    from .compliance.processing_registry import ProcessingRegistry
    from .agents.registry import get_registry
    import apps.backend.agents.accounting  # noqa: F401
except ImportError:
    from agent_runtime import AgentRuntime
    from database import (
        get_agent_run, init_db, list_agent_runs, list_audit_entries, write_audit_entry,
        get_or_create_user_profile, update_user_profile, complete_onboarding, delete_user_data,
        create_conversation, append_message, get_conversation_history, list_conversations,
        record_processing, list_processing_records, add_learned_rule, get_active_rules,
        update_rule_confidence, deactivate_rule, record_feedback,
    )
    from gateway import guarded_tool_call
    from routers.approvals import router as approvals_router
    from intelligent_agent import IntelligentAgentRuntime
    from security.key_manager import get_key_manager
    from compliance.processing_registry import ProcessingRegistry
    from agents.registry import get_registry
    import agents.accounting  # noqa: F401


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
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(approvals_router)


# ── Pydantic-Modelle ──────────────────────────────────────────────────────────────

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

class OnboardingRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)
    company: str = Field(default="", max_length=200)
    language: str = Field(default="de", max_length=10)

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: str = Field(default="default")
    conversation_id: str | None = None
    session_id: str | None = None

class FeedbackRequest(BaseModel):
    message_id: int
    user_id: str = Field(default="default")
    rating: int = Field(..., ge=1, le=5)
    correction: str = Field(default="")
    tool_name: str = Field(default="")

class KeyStoreRequest(BaseModel):
    session_id: str
    provider: str = Field(default="groq")
    api_key: str = Field(..., min_length=1)

class RuleRequest(BaseModel):
    rule_text: str = Field(..., min_length=1)
    source: str = Field(default="explicit")
    confidence: int = Field(default=80, ge=0, le=100)


# ── Basis-Endpunkte ────────────────────────────────────────────────────────────

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
        encode_sse(events), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

def encode_sse(events: Iterable[dict[str, Any]]):
    for event in events:
        data = json.dumps(event.get("data", {}), ensure_ascii=True, default=str)
        yield f"event: {event.get('event', 'message')}\ndata: {data}\n\n"

def serialize_agent_run(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"], "created_at": entry["created_at"], "updated_at": entry["updated_at"],
        "task": entry["task"], "status": entry["status"],
        "pending_approval_id": entry["pending_approval_id"],
        "result": entry["result"], "metadata": entry["run_metadata"],
    }


# ── Tools ───────────────────────────────────────────────────────────────────

@app.post("/tools/search")
def search_tools(
    query: str | None = Query(default=None, min_length=1),
    payload: ToolSearchRequest | None = Body(default=None),
) -> dict[str, Any]:
    search_query = query or (payload.query if payload else None)
    if search_query is None:
        raise HTTPException(status_code=422, detail="query is required")
    write_audit_entry(action="tools.search", metadata={"query": search_query})
    response = guarded_tool_call("search", {"query": search_query})
    return response["result"] if response.get("status") == "completed" else response

@app.post("/tools/fetch")
def fetch_tool(
    url: str | None = Query(default=None, min_length=1),
    payload: ToolFetchRequest | None = Body(default=None),
) -> dict[str, Any]:
    fetch_url = url or (payload.url if payload else None)
    if fetch_url is None:
        raise HTTPException(status_code=422, detail="url is required")
    write_audit_entry(action="tools.fetch", metadata={"url": fetch_url})
    response = guarded_tool_call("fetch", {"url": fetch_url})
    return response["result"] if response.get("status") == "completed" else response


# ── Einfache Fragen ohne LLM ──────────────────────────────────────────────

def answer_simple_question(task: str) -> str | None:
    text = " ".join(task.lower().strip().replace("?", "").split())
    now = datetime.now()
    if not text:
        return None
    if any(p in text for p in ("welchen tag haben wir heute", "welcher tag ist heute", "welches datum", "datum heute", "heutiges datum")):
        return now.strftime("%d.%m.%Y")
    if "wochentag" in text:
        return ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"][now.weekday()]
    if "uhrzeit" in text or "wie sp" in text:
        return now.strftime("%H:%M Uhr")
    if "welches jahr" in text or "jahr haben wir" in text:
        return str(now.year)
    if "welcher monat" in text or "monat haben wir" in text:
        return ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"][now.month-1]
    if text in {"hallo","hi","hey","guten tag","guten morgen","guten abend"}:
        return "Hallo!"
    if text in {"danke","dankeschoen","dankeschoen","vielen dank"}:
        return "Gern."
    if "wer bist du" in text or "wie heißt du" in text:
        return "Ich bin AILIZA."
    if "was kannst du" in text:
        return "Ich helfe bei E-Mails, Recherche, Übersetzungen und Zusammenfassungen."
    expr = text
    for p in ("was ist", "rechne", "berechne"):
        if expr.startswith(p + " "):
            expr = expr[len(p):].strip()
            break
    expr = expr.replace("plus","+").replace("minus","-").replace("mal","*").replace("geteilt durch","/")
    if re.fullmatch(r"[0-9+\-*/()., ]+", expr) and re.search(r"[+\-*/]", expr):
        try:
            v = eval(expr.replace(",","."), {"__builtins__": {}}, {})
            return str(int(v) if isinstance(v, float) and v.is_integer() else v)
        except Exception:
            return None
    return None


def extract_agent_answer(result: dict[str, Any]) -> str:
    parts: list[str] = []
    for step in result.get("results", []):
        if not isinstance(step, dict):
            continue
        for key in ("result", "summary"):
            data = step.get(key)
            if not isinstance(data, dict):
                continue
            s = data.get("summary")
            if isinstance(s, str) and s.strip():
                parts.append(s.strip())
            for top in (data.get("top_results") or [])[:3]:
                if isinstance(top, dict):
                    title = str(top.get("title") or "").strip()
                    content = str(top.get("content") or "").strip()
                    line = f"{title}: {content}" if title else content
                    if line.strip():
                        parts.append(line.strip())
    return "\n".join(parts).strip()


# ── Agent Run ───────────────────────────────────────────────────────────────

@app.post("/agent/run")
def run_agent(payload: AgentRunRequest) -> dict[str, Any]:
    import urllib.request, json as _json
    simple_answer = answer_simple_question(payload.task)
    if simple_answer is not None:
        return {"status": "completed", "message": simple_answer, "ai_response": simple_answer, "steps": [], "results": []}

    external_enabled = os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "false").lower() == "true"
    if external_enabled:
        runtime: AgentRuntime = IntelligentAgentRuntime()
        return runtime.run(payload.task)  # type: ignore[attr-defined]

    runtime_base = AgentRuntime()
    result = runtime_base.run(payload.task)
    search_text = extract_agent_answer(result)
    api_key = os.getenv("GROQ_API_KEY")
    if search_text and api_key:
        sys_prompt = "Du bist AILIZA. Antworte kurz und direkt auf Deutsch."
        user_msg = f'Frage: "{payload.task}"\n\nSuchergebnis:\n{search_text}\n\nFormuliere eine kurze direkte Antwort.'
        for model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
            try:
                req = urllib.request.Request(
                    "https://api.groq.com/openai/v1/chat/completions",
                    data=_json.dumps({"model": model, "messages": [{"role":"system","content":sys_prompt},{"role":"user","content":user_msg}], "max_tokens": 600, "temperature": 0.3}).encode(),
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                )
                with urllib.request.urlopen(req, timeout=20) as r:
                    result["message"] = _json.loads(r.read())["choices"][0]["message"]["content"]
                    break
            except Exception:
                pass
        else:
            result["message"] = search_text
    elif result.get("message") == "Agent run completed" and search_text:
        result["message"] = search_text
    result["ai_response"] = result.get("message", "")
    return result

@app.get("/agent/runs")
def get_agent_runs(status: str | None = None, limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    return [serialize_agent_run(e) for e in list_agent_runs(status=status, limit=limit)]

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
    return sse_response(AgentRuntime().stream(task, wait_for_approval=wait_for_approval,
        approval_poll_interval=approval_poll_interval, approval_timeout=approval_timeout))

@app.post("/agent/run/stream")
def stream_agent_run_post(
    payload: AgentRunRequest,
    wait_for_approval: bool = Query(default=False),
    approval_poll_interval: float = Query(default=1.0, ge=0.1, le=30.0),
    approval_timeout: float = Query(default=300.0, ge=1.0, le=3600.0),
) -> StreamingResponse:
    return sse_response(AgentRuntime().stream(payload.task, wait_for_approval=wait_for_approval,
        approval_poll_interval=approval_poll_interval, approval_timeout=approval_timeout))

@app.post("/agent/approvals/{approval_id}/continue")
def continue_agent_after_approval(approval_id: int) -> dict[str, Any]:
    return AgentRuntime().continue_after_approval(approval_id)

@app.get("/agent/approvals/{approval_id}/continue/stream")
def stream_agent_after_approval(approval_id: int) -> StreamingResponse:
    return sse_response(AgentRuntime().stream_after_approval(approval_id))

@app.post("/agent/approvals/{approval_id}/continue/stream")
def stream_agent_after_approval_post(approval_id: int) -> StreamingResponse:
    return sse_response(AgentRuntime().stream_after_approval(approval_id))


# ── Nutzerprofile & Onboarding ──────────────────────────────────────────────

@app.get("/users/{user_id}/profile")
def get_profile(user_id: str) -> dict[str, Any]:
    return get_or_create_user_profile(user_id)

@app.post("/users/{user_id}/onboarding")
def finish_onboarding(user_id: str, payload: OnboardingRequest) -> dict[str, Any]:
    update_user_profile(user_id, display_name=payload.display_name, company=payload.company, language=payload.language)
    complete_onboarding(user_id)
    return {"status": "ok", "user_id": user_id}

@app.delete("/users/{user_id}")
def delete_user(user_id: str) -> dict[str, Any]:
    counts = delete_user_data(user_id)
    write_audit_entry("dsgvo.art17.delete", {"user_id": user_id, "deleted": counts})
    return {"status": "deleted", "counts": counts}

@app.get("/users/{user_id}/export")
def export_user(user_id: str) -> dict[str, Any]:
    return {"profile": get_or_create_user_profile(user_id), "learned_rules": get_active_rules(user_id)}


# ── Multi-Turn Chat ────────────────────────────────────────────────────────

@app.post("/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    conv_id = payload.conversation_id or create_conversation(payload.user_id, payload.session_id or "")
    msg_id = append_message(conv_id, "user", payload.message, max(1, len(payload.message)//4))
    external_enabled = os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "false").lower() == "true"
    history = get_conversation_history(conv_id, limit=20)
    context = [{"role": m["role"], "content": m["content"]} for m in history[:-1]]
    if external_enabled:
        result = IntelligentAgentRuntime().run(payload.message, session_id=payload.session_id, conversation_history=context)
    else:
        result = AgentRuntime().run(payload.message)
    answer = result.get("ai_response") or result.get("message", "")
    ai_msg_id = append_message(conv_id, "assistant", answer, max(1, len(answer)//4))
    return {"conversation_id": conv_id, "message_id": ai_msg_id, "response": answer,
            "pii_detected": result.get("pii_detected", {}), "status": result.get("status", "completed")}

@app.get("/chat/{conversation_id}/history")
def get_history(conversation_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return get_conversation_history(conversation_id, limit=limit)

@app.get("/users/{user_id}/conversations")
def get_conversations(user_id: str) -> list[dict[str, Any]]:
    return list_conversations(user_id)


# ── DSGVO Art. 30 ───────────────────────────────────────────────────────────────

_processing_registry = ProcessingRegistry()

@app.get("/compliance/processing-records")
def get_processing_records(user_id: str | None = None) -> dict[str, Any]:
    return _processing_registry.export_for_user(user_id) if user_id else _processing_registry.export_full()

@app.get("/users/{user_id}/processing-records")
def get_user_processing_records(user_id: str) -> dict[str, Any]:
    return _processing_registry.export_for_user(user_id)

@app.post("/compliance/processing-records/{record_id}/acknowledge")
def acknowledge_processing(record_id: int) -> dict[str, Any]:
    ok = _processing_registry.acknowledge(record_id)
    return {"status": "ok" if ok else "not_found"}


# ── Feedback & Lernregeln ───────────────────────────────────────────────────

@app.post("/feedback")
def add_feedback(payload: FeedbackRequest) -> dict[str, Any]:
    rec_id = record_feedback(message_id=payload.message_id, user_id=payload.user_id,
        rating=payload.rating, correction=payload.correction,
        tool_name=payload.tool_name, was_helpful=payload.rating >= 4)
    if payload.correction:
        add_learned_rule(user_id=payload.user_id, rule_text=f"Nutzerkorrektur: {payload.correction[:300]}",
                         source="correction", confidence=70)
    return {"status": "ok", "id": rec_id}

@app.get("/users/{user_id}/rules")
def get_rules(user_id: str) -> list[dict[str, Any]]:
    return get_active_rules(user_id)

@app.post("/users/{user_id}/rules")
def add_rule(user_id: str, payload: RuleRequest) -> dict[str, Any]:
    rule_id = add_learned_rule(user_id=user_id, rule_text=payload.rule_text,
                               source=payload.source, confidence=payload.confidence)
    return {"status": "ok", "id": rule_id}

@app.delete("/users/{user_id}/rules/{rule_id}")
def delete_rule(user_id: str, rule_id: int) -> dict[str, Any]:
    deactivate_rule(rule_id)
    return {"status": "ok"}


# ── Key-Management ────────────────────────────────────────────────────────────

@app.post("/keys/store")
def store_key(payload: KeyStoreRequest) -> dict[str, Any]:
    token = get_key_manager().store_key(session_id=payload.session_id, provider=payload.provider, api_key=payload.api_key)
    write_audit_entry("keys.stored", {"session_id": payload.session_id, "provider": payload.provider})
    return {"status": "ok", "key_token": token}

@app.delete("/keys/{session_id}")
def revoke_session_keys(session_id: str) -> dict[str, Any]:
    get_key_manager().revoke_session(session_id)
    write_audit_entry("keys.revoked", {"session_id": session_id})
    return {"status": "ok"}


# ── Sub-Agenten ──────────────────────────────────────────────────────────────

@app.get("/agents")
def list_agents() -> list[dict[str, Any]]:
    return get_registry().list_agents()


# ── Frontend ───────────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/dashboard")
def dashboard():
    return FileResponse(FRONTEND_DIR / "index.html")
