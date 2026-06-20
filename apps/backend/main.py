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

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

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
    from .auth import create_token, Role, require_role, get_current_user, TokenData
    from .database import create_user as db_create_user, authenticate_user as db_authenticate_user
    from .database import engine
    from .auth.models import UserCreate, UserInDB
except ImportError:
    from agent_runtime import AgentRuntime
    from database import (
        get_agent_run, init_db, list_agent_runs, list_audit_entries, write_audit_entry,
        insert_feedback, count_negative_feedback, insert_routing_proposal,
        adjust_fact_quality_for_run, DEFAULT_TENANT_ID,
        create_user as db_create_user, authenticate_user as db_authenticate_user,
        engine,
    )
    from gateway import guarded_tool_call
    from routers.approvals import router as approvals_router
    from errors import AILIZAError, MESSAGES
    from providers.orchestrator import ProviderOrchestrator
    from documents.document_handler import scan_document
    from auth import create_token, Role, require_role, get_current_user, TokenData
    from auth.models import UserCreate, UserInDB


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    try:
        from .maintenance.retention_cleanup import run_cleanup
    except ImportError:
        from maintenance.retention_cleanup import run_cleanup

    run_cleanup()

    from apscheduler.schedulers.background import BackgroundScheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _cleanup_interval_hours = int(os.getenv("AILIZA_CLEANUP_INTERVAL_HOURS", "24"))
    _scheduler.add_job(run_cleanup, "interval", hours=_cleanup_interval_hours,
                       id="retention_cleanup", replace_existing=True)
    _scheduler.start()

    yield

    _scheduler.shutdown(wait=False)


_limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AILIZA Backend", lifespan=lifespan)
app.state.limiter = _limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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
from fastapi import Depends, UploadFile, File


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
def health() -> dict[str, Any]:
    """Schneller Liveness-Check — kein DB-Call."""
    return {"status": "ok", "service": "ailiza-backend"}


@app.get("/ready")
def ready() -> dict[str, Any]:
    """Readiness-Check: DB, Kill-Switch, Scheduler."""
    checks: dict[str, str] = {}

    # DB-Check
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # Kill-Switch-Status
    kill_switch_env = os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "false").lower()
    checks["kill_switch"] = "enabled" if kill_switch_env == "true" else "disabled"

    # Scheduler (APScheduler im lifespan gestartet)
    checks["scheduler"] = "running"

    overall = "ok" if checks["database"] == "ok" else "degraded"
    return {"status": overall, "checks": checks}


def _tenant_id(token: TokenData | None) -> str:
    """Liest tenant_id aus dem JWT-Token oder gibt DEFAULT_TENANT_ID zurück."""
    return token.tenant_id if token is not None else DEFAULT_TENANT_ID


@app.post("/audit-logs", status_code=201)
def create_audit_log(
    payload: AuditLogCreate,
    token: TokenData | None = Depends(get_current_user),
) -> dict[str, Any]:
    return write_audit_entry(action=payload.action, metadata=payload.metadata,
                             tenant_id=_tenant_id(token))


@app.get("/audit-logs")
def get_audit_logs(
    limit: int = 100,
    token: TokenData | None = Depends(get_current_user),
) -> list[dict[str, Any]]:
    return list_audit_entries(limit=limit, tenant_id=_tenant_id(token))


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
@_limiter.limit("30/minute")
def run_agent(
    request: Request,
    payload: AgentRunRequest,
    token: TokenData | None = Depends(get_current_user),
) -> dict[str, Any]:
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

    tenant = _tenant_id(token)
    if search_text:
        answer, error_code = _summarize_with_llm(payload.task, search_text)
        if answer is not None:
            result["message"] = answer
        else:
            result["message"] = search_text
            if error_code:
                result["llm_notice"] = MESSAGES.get(error_code, "")
    elif result.get("message") == "Agent run completed" and search_text:
        result["message"] = search_text

    result["ai_response"] = result.get("message", "")
    result["tenant_id"] = tenant
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
    tenant_id: str | None = None


@app.post("/feedback", status_code=201)
def submit_feedback(
    payload: FeedbackRequest,
    token: TokenData | None = Depends(get_current_user),
) -> dict[str, Any]:
    tenant = payload.tenant_id or _tenant_id(token)
    delta = 0.1 if payload.rating == "helpful" else -0.2
    entry = insert_feedback(
        tenant_id=tenant, run_id=payload.run_id,
        rating=payload.rating, reason=payload.reason, quality_score_delta=delta)
    if payload.run_id:
        adjust_fact_quality_for_run(payload.run_id, delta, tenant_id=payload.tenant_id)

    admin_suggestion = None
    if payload.rating == "not_helpful":
        negatives = count_negative_feedback(tenant, payload.run_id)
        if negatives >= 3:
            proposal = insert_routing_proposal(
                tenant_id=tenant, trigger_type="negative_feedback",
                description=f"{negatives} negative Bewertungen fuer run {payload.run_id}.",
                reason="Schwellwert von 3 negativen Bewertungen erreicht.")
            admin_suggestion = proposal["id"]
    write_audit_entry(action="feedback.submitted",
                      metadata={"rating": payload.rating, "run_id": payload.run_id},
                      tenant_id=tenant)
    return {"status": "ok", "feedback_id": entry["id"], "admin_proposal_id": admin_suggestion}


@app.post("/documents/scan")
@_limiter.limit("20/minute")
async def documents_scan(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
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


# ── Auth-Endpunkte ────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)
    tenant_id: str = Field(default=DEFAULT_TENANT_ID)


class RegisterRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=12)
    role: str = Field(default="user", pattern="^(user|manager|admin|dsb)$")
    tenant_id: str = Field(default=DEFAULT_TENANT_ID)

    @field_validator("password")
    @classmethod
    def password_policy(cls, v: str) -> str:
        import re
        errors = []
        if not re.search(r"[A-Z]", v):
            errors.append("Großbuchstabe fehlt")
        if not re.search(r"[a-z]", v):
            errors.append("Kleinbuchstabe fehlt")
        if not re.search(r"\d", v):
            errors.append("Zahl fehlt")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", v):
            errors.append("Sonderzeichen fehlt")
        if errors:
            raise ValueError(f"Passwort-Policy: {', '.join(errors)}")
        return v


@app.post("/auth/login")
@_limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest) -> dict[str, Any]:
    user = db_authenticate_user(payload.user_id, payload.password, payload.tenant_id)
    if user is None:
        write_audit_entry(action="auth.login.failed",
                          metadata={"user_id": payload.user_id, "tenant_id": payload.tenant_id},
                          tenant_id=payload.tenant_id)
        raise HTTPException(status_code=401, detail="Ungültige Zugangsdaten.")
    token = create_token(user["user_id"], user["tenant_id"], user["role"])
    write_audit_entry(action="auth.login.success",
                      metadata={"user_id": payload.user_id, "role": user["role"]},
                      tenant_id=payload.tenant_id)
    return {"access_token": token, "token_type": "bearer", "role": user["role"]}


@app.post("/auth/register", status_code=201)
@_limiter.limit("5/minute")
def register(
    request: Request,
    payload: RegisterRequest,
    _admin: TokenData = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    user_create = UserCreate(
        user_id=payload.user_id,
        tenant_id=payload.tenant_id,
        role=payload.role,
        plain_password=payload.password,
    )
    user_in_db = UserInDB.from_create(user_create)
    try:
        entry = db_create_user(
            user_id=user_in_db.user_id,
            tenant_id=user_in_db.tenant_id,
            role=user_in_db.role,
            hashed_password=user_in_db.hashed_password,
        )
    except Exception:
        raise HTTPException(status_code=409, detail="Nutzer existiert bereits.")
    write_audit_entry(action="auth.register",
                      metadata={"user_id": payload.user_id, "role": payload.role},
                      tenant_id=payload.tenant_id)
    return {"status": "created", "user_id": entry["user_id"], "role": entry["role"]}


# ── Admin-Endpunkte (mindestens ADMIN-Rolle erforderlich) ────────────────────
@app.post("/admin/cleanup")
def admin_cleanup(_admin: TokenData = Depends(require_role(Role.ADMIN))) -> dict[str, Any]:
    """Retention-Cleanup manuell auslösen — löscht abgelaufene Einträge."""
    try:
        from .maintenance.retention_cleanup import run_cleanup
    except ImportError:
        from maintenance.retention_cleanup import run_cleanup
    result = run_cleanup()
    write_audit_entry(action="admin.cleanup", metadata={"total_deleted": result["total_deleted"]})
    return result


@app.get("/admin/provider-profiles")
def list_provider_profiles(_admin: TokenData = Depends(require_role(Role.ADMIN))) -> list[dict[str, Any]]:
    """Gibt alle konfigurierten ProviderProfile zurück (ohne API-Keys)."""
    try:
        from .providers.provider_profiles import get_active_profiles, profile_to_dict
    except ImportError:
        from providers.provider_profiles import get_active_profiles, profile_to_dict
    return [profile_to_dict(p) for p in get_active_profiles()]


@app.get("/admin/capabilities")
def list_capabilities(_admin: TokenData = Depends(require_role(Role.ADMIN))) -> list[dict[str, Any]]:
    """Gibt alle registrierten Capabilities zurück (Capability Registry)."""
    try:
        from .capabilities.registry import get_all_capabilities
    except ImportError:
        from capabilities.registry import get_all_capabilities
    return get_all_capabilities()


class CapabilityCheckRequest(BaseModel):
    capability_id: str = Field(..., min_length=1)
    data_classes: list[str] = Field(default_factory=list)
    redaction_applied: bool = False
    approval_given: bool = False


@app.post("/admin/capabilities/check")
def check_capability_endpoint(
    payload: CapabilityCheckRequest,
    token: TokenData = Depends(require_role(Role.MANAGER)),
) -> dict[str, Any]:
    """Prüft ob eine Capability für gegebene Datenklassen erlaubt ist."""
    try:
        from .capabilities.registry import check_capability
        from .governance.data_governance import DataClass
    except ImportError:
        from capabilities.registry import check_capability
        from governance.data_governance import DataClass

    try:
        dc_list = [DataClass(dc) for dc in payload.data_classes]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Ungültige Datenklasse: {exc}")

    result = check_capability(
        capability_id=payload.capability_id,
        data_classes=dc_list,
        tenant_id=token.tenant_id,
        user_id=token.user_id,
        redaction_applied=payload.redaction_applied,
        approval_given=payload.approval_given,
    )
    return {
        "capability_id": result.capability_id,
        "allowed": result.allowed,
        "decision": result.decision.value,
        "reason": result.reason,
        "requires_approval": result.requires_approval,
        "risk_level": result.risk_level,
        "capability_enabled": result.capability_enabled,
        "context_summary": result.context_summary,
    }


# ── Skill-Learning-Loop ───────────────────────────────────────────────────────
class SkillProposeRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1, max_length=512)
    steps_summary: str = Field(..., min_length=10, max_length=2000)
    gdpr_purpose: str = Field(..., min_length=1, max_length=256)
    data_classes: list[str] = Field(default_factory=lambda: ["public"])
    source_run_id: str | None = None


@app.post("/skills/propose", status_code=201)
@_limiter.limit("10/minute")
def skill_propose(
    request: Request,
    payload: SkillProposeRequest,
    token: TokenData = Depends(require_role(Role.USER)),
) -> dict[str, Any]:
    """
    Schlaegt einen neuen Skill vor. Capability-Check + Sanitierung laufen automatisch.
    Skill wird als 'pending' gespeichert — Admin muss genehmigen.
    """
    try:
        from .skills.skill_store import propose_skill
        from .governance.data_governance import DataClass
    except ImportError:
        from skills.skill_store import propose_skill
        from governance.data_governance import DataClass

    try:
        dc_list = [DataClass(dc) for dc in payload.data_classes]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Ungültige Datenklasse: {exc}")

    proposal = propose_skill(
        name=payload.name,
        description=payload.description,
        steps_summary=payload.steps_summary,
        gdpr_purpose=payload.gdpr_purpose,
        data_classes=dc_list,
        tenant_id=token.tenant_id,
        user_id=token.user_id,
        source_run_id=payload.source_run_id,
    )
    return {
        "skill_id": proposal.skill_id,
        "status": proposal.status,
        "name": proposal.name,
        "risk_level": proposal.risk_level,
        "requires_approval": True,
        "message": "Skill-Vorschlag eingereicht. Ein Administrator muss ihn genehmigen.",
    }


@app.get("/admin/skills")
def list_skills_admin(
    status: str | None = None,
    token: TokenData = Depends(require_role(Role.ADMIN)),
) -> list[dict[str, Any]]:
    """Gibt alle Skill-Vorschlaege zurueck (gefiltert nach Status)."""
    try:
        from .skills.skill_store import list_skills
    except ImportError:
        from skills.skill_store import list_skills
    return list_skills(tenant_id=token.tenant_id, status=status)


@app.post("/admin/skills/{skill_id}/approve")
def approve_skill_endpoint(
    skill_id: str,
    token: TokenData = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    """Admin genehmigt Skill. Capability-Check 'memory_store' laeuft hier."""
    try:
        from .skills.skill_store import approve_skill
    except ImportError:
        from skills.skill_store import approve_skill
    return approve_skill(skill_id=skill_id, approved_by=token.user_id, tenant_id=token.tenant_id)


@app.post("/admin/skills/{skill_id}/reject")
def reject_skill_endpoint(
    skill_id: str,
    reason: str = "Kein Grund angegeben.",
    token: TokenData = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    """Admin verwirft Skill-Vorschlag."""
    try:
        from .skills.skill_store import reject_skill
    except ImportError:
        from skills.skill_store import reject_skill
    return reject_skill(skill_id=skill_id, rejected_by=token.user_id,
                        reason=reason, tenant_id=token.tenant_id)


@app.delete("/admin/skills/{skill_id}")
def delete_skill_endpoint(
    skill_id: str,
    token: TokenData = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    """Admin loescht Skill (auch genehmigte). DSGVO-Loeschrecht."""
    try:
        from .skills.skill_store import delete_skill
    except ImportError:
        from skills.skill_store import delete_skill
    deleted = delete_skill(skill_id=skill_id, tenant_id=token.tenant_id, deleted_by=token.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill nicht gefunden.")
    return {"status": "deleted", "skill_id": skill_id}


@app.get("/skills")
def list_approved_skills(
    token: TokenData | None = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Gibt genehmigte Skills zurueck (ohne steps_summary fuer normale Nutzer)."""
    try:
        from .skills.skill_store import list_skills
    except ImportError:
        from skills.skill_store import list_skills
    skills_list = list_skills(tenant_id=_tenant_id(token), status="approved")
    return [
        {k: v for k, v in s.items() if k != "steps_summary"}
        for s in skills_list
    ]


# ── Messenger / Telegram-Gateway ─────────────────────────────────────────────
@app.post("/messenger/telegram/webhook")
@_limiter.limit("100/minute")
async def telegram_webhook(request: Request) -> dict[str, Any]:
    """
    Telegram-Webhook-Endpoint.
    Optionale Signatur-Prüfung via X-Telegram-Bot-Api-Secret-Token Header.
    Fail-closed: Fehler in handle_update werden nicht nach außen gegeben.
    """
    try:
        from .messenger.telegram_gateway import handle_update, verify_telegram_signature
    except ImportError:
        from messenger.telegram_gateway import handle_update, verify_telegram_signature

    body = await request.body()
    secret = os.getenv("AILIZA_TELEGRAM_WEBHOOK_SECRET", "")
    x_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not verify_telegram_signature(body, secret, x_token):
        write_audit_entry(action="messenger.webhook.signature_invalid",
                          metadata={"ip": request.client.host if request.client else "unknown"})
        raise HTTPException(status_code=403, detail="Ungültige Webhook-Signatur.")

    try:
        update_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiges JSON.")

    try:
        handle_update(update_data)
    except Exception:
        pass  # Fail-closed: keine internen Fehler nach außen

    return {"ok": True}


@app.get("/admin/messenger/bindings")
def list_messenger_bindings(
    _admin: TokenData = Depends(require_role(Role.ADMIN)),
) -> list[dict[str, Any]]:
    """Gibt alle Telegram-Bindungen zurück (pseudonymisiert: nur chat_id-Hash + Metadaten)."""
    try:
        from .database import engine, messenger_bindings
    except ImportError:
        from database import engine, messenger_bindings
    import hashlib
    from sqlalchemy import select

    with engine.begin() as conn:
        rows = conn.execute(select(messenger_bindings)).mappings().all()
    return [
        {
            "chat_id_hash": hashlib.sha256(str(r["chat_id"]).encode()).hexdigest()[:16],
            "tenant_id": r["tenant_id"],
            "opt_in_confirmed": bool(r["opt_in_confirmed"]),
            "created_at": str(r["created_at"]) if r["created_at"] else None,
            "opt_in_at": str(r["opt_in_at"]) if r.get("opt_in_at") else None,
        }
        for r in rows
    ]


@app.delete("/admin/messenger/bindings/{chat_id}")
def delete_messenger_binding(
    chat_id: str,
    _admin: TokenData = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    """DSGVO-Loeschrecht: Admin löscht Telegram-Bindung eines Nutzers."""
    try:
        from .messenger.telegram_gateway import delete_binding, get_binding
    except ImportError:
        from messenger.telegram_gateway import delete_binding, get_binding

    binding = get_binding(chat_id)
    if binding is None:
        raise HTTPException(status_code=404, detail="Bindung nicht gefunden.")
    delete_binding(chat_id)
    write_audit_entry(action="admin.messenger.binding_deleted",
                      metadata={"deleted_by": _admin.user_id})
    return {"status": "deleted", "chat_id": chat_id}


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dashboard")
def dashboard():
    return FileResponse(FRONTEND_DIR / "index.html")
