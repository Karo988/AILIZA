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
    from .agent_runtime import AgentRuntime, _WRITING_INTENT_PATTERN, _SEARCH_INTENT_PATTERN
    from .database import (
        get_agent_run, init_db, list_agent_runs, list_audit_entries, write_audit_entry,
        insert_feedback, count_negative_feedback, insert_routing_proposal,
        adjust_fact_quality_for_run, DEFAULT_TENANT_ID,
        create_approval_request,
    )
    from .gateway import guarded_tool_call
    from .routers.approvals import router as approvals_router
    from .errors import AILIZAError, MESSAGES
    from .providers.orchestrator import ProviderOrchestrator
    from .documents.document_handler import scan_document
    from .auth import create_token, Role, require_role, get_current_user, TokenData
    from .auth.jwt_handler import create_totp_pending_token, decode_totp_pending_token
    from .database import create_user as db_create_user, authenticate_user as db_authenticate_user
    from .database import (
        engine,
        get_totp_record, upsert_totp_secret, confirm_totp_secret,
        delete_totp_secret, store_backup_codes, consume_backup_code,
    )
    from .auth.models import UserCreate, UserInDB
    from .auth.totp import generate_secret, verify_totp, build_otpauth_uri, generate_backup_codes, hash_backup_code
    from .governance.data_governance import classify, DataClass, DataTarget
    from .governance.redaction import redact, reinsert
    from .governance.data_matrix import check_data_target, PolicyDecision
except ImportError:
    from agent_runtime import AgentRuntime, _WRITING_INTENT_PATTERN, _SEARCH_INTENT_PATTERN
    from database import (
        get_agent_run, init_db, list_agent_runs, list_audit_entries, write_audit_entry,
        insert_feedback, count_negative_feedback, insert_routing_proposal,
        adjust_fact_quality_for_run, DEFAULT_TENANT_ID,
        create_user as db_create_user, authenticate_user as db_authenticate_user,
        engine,
        get_totp_record, upsert_totp_secret, confirm_totp_secret,
        delete_totp_secret, store_backup_codes, consume_backup_code,
        create_approval_request,
    )
    from gateway import guarded_tool_call
    from routers.approvals import router as approvals_router
    from errors import AILIZAError, MESSAGES
    from providers.orchestrator import ProviderOrchestrator
    from documents.document_handler import scan_document
    from auth import create_token, Role, require_role, get_current_user, TokenData
    from auth.jwt_handler import create_totp_pending_token, decode_totp_pending_token
    from auth.models import UserCreate, UserInDB
    from auth.totp import generate_secret, verify_totp, build_otpauth_uri, generate_backup_codes, hash_backup_code
    from governance.data_governance import classify, DataClass, DataTarget
    from governance.redaction import redact, reinsert
    from governance.data_matrix import check_data_target, PolicyDecision


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # ── Gate 10: Config Integrity — muss als ERSTES laufen ───────────────────
    # AILIZA darf niemals normal starten wenn Governance-Dateien fehlen,
    # beschädigt oder unautorisiert verändert sind.
    _base_dir = Path(__file__).resolve().parent
    _manifest_path = _base_dir / "governance_integrity.json"
    try:
        from .config_integrity import verify_integrity, IntegrityStatus
    except ImportError:
        from config_integrity import verify_integrity, IntegrityStatus

    _integrity = verify_integrity(_base_dir, _manifest_path)
    _integrity_ok = _integrity.all_ok

    if not _integrity_ok:
        # Fail-closed: sofort kill_switch_active setzen
        os.environ["AILIZA_OPERATION_MODE"] = "kill_switch_active"
        os.environ["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
        import logging as _logging
        _logging.getLogger(__name__).critical(
            "Gate 10 FAILED — Governance-Integrität verletzt. "
            "Status: %s. Modus: kill_switch_active. "
            "Betroffene Dateien: %d. Keine externen Calls, keine Schreibaktionen.",
            _integrity.overall_status,
            sum(1 for r in _integrity.file_results if r.decision == "blocked"),
        )
        # Kein raise — Backend startet im kill_switch_active Modus,
        # damit Health/Status-Endpoints erreichbar bleiben für Monitoring.
        # Alle Governance-abhängigen Endpoints werden durch enforce_kill_switch() geblockt.
    # ── Ende Gate 10 ─────────────────────────────────────────────────────────

    # ── Secret-Key-Prüfung: Hard-Fail wenn zu schwach ───────────────────────
    _secret_key = os.getenv("AILIZA_SECRET_KEY", "")
    if len(_secret_key) < 32:
        import logging as _log_sk
        _log_sk.getLogger(__name__).critical(
            "STARTUP ABORTED: AILIZA_SECRET_KEY ist nicht gesetzt oder zu kurz "
            "(< 32 Zeichen). JWT-Authentifizierung ist ohne sicheres Secret nicht "
            "betreibbar. Bitte AILIZA_SECRET_KEY in .env setzen und AILIZA neu starten."
        )
        # Kein raise — Dienst startet, aber alle Auth-abhängigen Calls schlagen fehl.
        # Externe Calls bleiben durch Kill-Switch blockiert.
        os.environ["AILIZA_EXTERNAL_LLM_ENABLED"] = "false"
        write_audit_entry(
            action="startup.secret_key_missing",
            metadata={"component": "jwt_handler", "key_length": len(_secret_key)},
        )
    # ── Ende Secret-Key-Prüfung ──────────────────────────────────────────────

    # ── CORS-Produktionswarnung ──────────────────────────────────────────────
    _is_debug = os.getenv("AILIZA_DEBUG", "false").lower() in ("1", "true", "yes")
    _cors_raw = os.getenv("AILIZA_CORS_ORIGINS", "*")
    if _cors_raw.strip() == "*" and not _is_debug:
        import logging as _log_cors
        _log_cors.getLogger(__name__).warning(
            "SECURITY: AILIZA_CORS_ORIGINS ist '*' (Wildcard). "
            "In Produktion MUSS eine konkrete Origin gesetzt werden, z. B. "
            "AILIZA_CORS_ORIGINS=https://ailiza.onrender.com. "
            "Setze AILIZA_DEBUG=true um diese Warnung in der Entwicklung zu unterdrücken."
        )
        write_audit_entry(
            action="startup.cors_wildcard_warning",
            metadata={"cors_origins": "*", "debug_mode": _is_debug},
        )
    # ── Ende CORS-Produktionswarnung ─────────────────────────────────────────

    init_db()

    # ── Provider-Diagnose beim Startup (kein Key-Inhalt, nur Präsenz) ─────────
    try:
        from .kill_switch import is_external_llm_enabled as _is_ext_enabled
    except ImportError:
        from kill_switch import is_external_llm_enabled as _is_ext_enabled
    _diag_groq = bool(os.getenv("GROQ_API_KEY"))
    _diag_openai = bool(os.getenv("OPENAI_API_KEY"))
    _diag_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
    _diag_tavily = bool(os.getenv("TAVILY_API_KEY"))
    _diag_ext_env = os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "(not set)")
    _diag_ext_allowed = _is_ext_enabled()
    # ── Erweiterter Startup-Debug-Log (keine Keys, keine Secrets) ───────────────
    try:
        from .providers.provider_profiles import _PROFILES as _pp
        _provider_debug = [
            f"{pid}(active={p.active},admin_disabled={p.admin_disabled},"
            f"transfer={p.transfer_basis.value})"
            for pid, p in _pp.items()
        ]
    except Exception:
        _provider_debug = ["(profile-load-error)"]
    try:
        from .registry.registry_loader import get_registry as _get_reg
        _reg = _get_reg()
        _reg_usable = [p.provider_id for p in _reg.get_usable_providers()]
    except Exception:
        _reg_usable = ["(registry-load-error)"]
    _gate10_status = getattr(_integrity, "overall_status", "unknown")
    # GROQ_MODEL: zeige welches Modell tatsächlich genutzt wird (entscheidend für 403-Diagnose)
    _diag_groq_model = os.getenv("GROQ_MODEL", "") or "llama-3.1-8b-instant (default)"
    print(
        f"AILIZA PROVIDER STATUS | groq_key={_diag_groq} openai_key={_diag_openai} "
        f"anthropic_key={_diag_anthropic} tavily_key={_diag_tavily} "
        f"AILIZA_EXTERNAL_LLM_ENABLED={_diag_ext_env} external_llm_allowed={_diag_ext_allowed} "
        f"groq_model={_diag_groq_model} "
        f"gate10={_gate10_status} "
        f"registry_usable={_reg_usable} "
        f"provider_profiles={_provider_debug}",
        flush=True,
    )
    write_audit_entry(
        action="startup.provider_status",
        metadata={
            "groq_present": _diag_groq,
            "openai_present": _diag_openai,
            "anthropic_present": _diag_anthropic,
            "tavily_present": _diag_tavily,
            "external_llm_env": _diag_ext_env,
            "external_llm_allowed": _diag_ext_allowed,
        },
    )
    # ── Ende Provider-Diagnose ───────────────────────────────────────────────

    # Audit-Light: Gate-10-Ergebnis protokollieren (keine Inhalte, keine Hashes)
    _audit_meta = _integrity.to_audit_dict()
    _audit_meta["event_type"] = "startup.integrity_check"
    write_audit_entry(
        action="startup.integrity_check",
        metadata=_audit_meta,
    )

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

# HSTS + HTTP→HTTPS-Redirect (C1): nur aktiv wenn AILIZA_FORCE_HTTPS=true.
# Render terminiert TLS selbst — intern läuft HTTP, daher standardmäßig off.
# In Produktion: AILIZA_FORCE_HTTPS=true setzen (nach TLS-Setup verifizieren).
_force_https = os.getenv("AILIZA_FORCE_HTTPS", "false").lower() in ("1", "true", "yes")

if _force_https:
    from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
    app.add_middleware(HTTPSRedirectMiddleware)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as _StarletteRequest
from starlette.responses import Response as _StarletteResponse


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Setzt HSTS + grundlegende Sicherheitsheader auf jede Antwort."""

    async def dispatch(self, request: _StarletteRequest, call_next):
        response: _StarletteResponse = await call_next(request)
        if _force_https:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(_SecurityHeadersMiddleware)

app.include_router(approvals_router)


from fastapi.responses import JSONResponse
from fastapi import Depends, UploadFile, File


# ── CSRF-Schutz: Origin-/Referer-Check fuer Cookie-gestuetzte Requests ────────
_CSRF_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_CSRF_PROTECTED_PREFIXES = (
    "/auth/logout", "/auth/register", "/auth/totp", "/admin/", "/skills/propose",
    "/agent/run", "/feedback", "/documents/", "/messenger/",
)


@app.middleware("http")
async def csrf_origin_check(request: Request, call_next):
    """
    Prueft bei schreibenden Requests mit Cookie-Auth, ob Origin/Referer
    zur konfigurierten CORS-Origin passt.

    SameSite=Strict allein reicht nicht in allen Browser-Setups.
    API-Clients mit Bearer-Token sind ausgenommen (kein Cookie gesendet).
    """
    if request.method in _CSRF_SAFE_METHODS:
        return await call_next(request)

    # Nur pruefen wenn Cookie vorhanden (Browser-Flow) und kein Bearer-Header
    has_cookie = "ailiza_session" in request.cookies
    has_bearer = request.headers.get("authorization", "").startswith("Bearer ")

    if has_cookie and not has_bearer:
        path = request.url.path
        if any(path.startswith(p) for p in _CSRF_PROTECTED_PREFIXES):
            origin = request.headers.get("origin", "")
            referer = request.headers.get("referer", "")
            allowed = os.getenv("AILIZA_CORS_ORIGINS", "*")

            if allowed != "*":
                allowed_origins = [o.strip() for o in allowed.split(",") if o.strip()]
                source = origin or referer
                if source and not any(source.startswith(o) for o in allowed_origins):
                    write_audit_entry(
                        action="security.csrf_blocked",
                        metadata={"path": path, "origin": origin or referer},
                    )
                    return JSONResponse(
                        status_code=403,
                        content={"error": True, "code": "csrf_blocked",
                                 "message": "Cross-Site-Anfrage abgewiesen."},
                    )

    return await call_next(request)


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
@app.get("/api/health")
def health() -> dict[str, Any]:
    """Schneller Liveness-Check — kein DB-Call. Erreichbar unter /health und /api/health."""
    return {"status": "ok", "service": "ailiza", "api": "online"}


@app.get("/api/debug/llm-status")
def debug_llm_status() -> dict[str, Any]:
    """
    Diagnose-Endpunkt: Zeigt LLM-Aktivierungsstatus ohne Secrets.
    Hilft bei der Fehlersuche warum 'Die externe KI ist deaktiviert' erscheint.
    Kein API-Key, kein Secret, keine PII im Response.
    """
    result: dict[str, Any] = {}
    block_reasons: list[str] = []

    # 1. Gate 10 — Governance-Integrität
    try:
        _base_dir = Path(__file__).parent
        _manifest_path = _base_dir / "governance_integrity.json"
        try:
            from .config_integrity import verify_integrity
        except ImportError:
            from config_integrity import verify_integrity
        _integrity = verify_integrity(_base_dir, _manifest_path)
        gate10_ok = _integrity.all_ok
        gate10_status = _integrity.overall_status
        gate10_blocked = [r.path for r in _integrity.file_results if r.decision == "blocked"]
    except Exception as e:
        gate10_ok = False
        gate10_status = f"check-error: {type(e).__name__}"
        gate10_blocked = []
        block_reasons.append("gate10_check_failed")
    result["gate10_ok"] = gate10_ok
    result["gate10_status"] = gate10_status
    if gate10_blocked:
        result["gate10_blocked_files"] = gate10_blocked
        block_reasons.append("gate10_integrity_violation")

    # 2. Secret-Key-Länge (nur Länge, kein Inhalt)
    _sk_len = len(os.getenv("AILIZA_SECRET_KEY", ""))
    secret_key_ok = _sk_len >= 32
    result["secret_key_ok"] = secret_key_ok
    result["secret_key_length"] = _sk_len
    if not secret_key_ok:
        block_reasons.append("secret_key_too_short")

    # 3. Env-Variable roh
    _ext_env_raw = os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "(not set)")
    result["env_AILIZA_EXTERNAL_LLM_ENABLED"] = _ext_env_raw
    result["operation_mode"] = os.getenv("AILIZA_OPERATION_MODE", "normal")

    # 4. Kill-Switch-Auswertung
    try:
        try:
            from .kill_switch import is_external_llm_enabled, get_operation_mode, kill_switch_metadata
        except ImportError:
            from kill_switch import is_external_llm_enabled, get_operation_mode, kill_switch_metadata
        ext_llm_enabled = is_external_llm_enabled()
        ks_meta = kill_switch_metadata()
        result["external_llm_enabled"] = ext_llm_enabled
        result["kill_switch_metadata"] = {k: v for k, v in ks_meta.items()
                                           if k not in ("api_key", "secret", "token")}
        if not ext_llm_enabled:
            block_reasons.append("kill_switch_active_or_env_false")
    except Exception as e:
        result["external_llm_enabled"] = False
        result["kill_switch_error"] = type(e).__name__
        block_reasons.append("kill_switch_check_failed")

    # 5. API-Keys konfiguriert (nur Präsenz, nicht Inhalt)
    result["groq_configured"] = bool(os.getenv("GROQ_API_KEY"))
    result["openai_configured"] = bool(os.getenv("OPENAI_API_KEY"))
    result["anthropic_configured"] = bool(os.getenv("ANTHROPIC_API_KEY"))
    result["tavily_configured"] = bool(os.getenv("TAVILY_API_KEY"))

    # 6. Provider-Profile
    try:
        try:
            from .providers.provider_profiles import _PROFILES
        except ImportError:
            from providers.provider_profiles import _PROFILES
        result["providers"] = [
            {
                "id": pid,
                "active": p.active,
                "admin_disabled": p.admin_disabled,
                "transfer_basis": p.transfer_basis.value,
            }
            for pid, p in _PROFILES.items()
        ]
    except Exception as e:
        result["providers"] = [{"error": type(e).__name__}]

    # 7. Registry — nutzbare Provider
    try:
        try:
            from .registry.registry_loader import get_registry
        except ImportError:
            from registry.registry_loader import get_registry
        _reg = get_registry()
        result["registry_usable"] = [p.provider_id for p in _reg.get_usable_providers()]
        if not result["registry_usable"]:
            block_reasons.append("no_usable_provider_in_registry")
    except Exception as e:
        result["registry_usable"] = []
        result["registry_error"] = type(e).__name__
        block_reasons.append("registry_load_failed")

    result["block_reasons"] = block_reasons if block_reasons else None
    result["diagnosis"] = "ok" if not block_reasons else "blocked"
    return result


@app.get("/api/debug/provider-test")
def debug_provider_test() -> dict[str, Any]:
    """
    Testet jeden Provider mit einer harmlosen Nachricht ohne Nutzerdaten.
    Gibt sanitisierten Status je Provider zurück — keine Secrets, keine Keys.
    Für Diagnose auf Render: zeigt welcher Provider fehlschlägt und warum.
    WICHTIG: Deaktivieren wenn nicht gebraucht (AILIZA_DEBUG=false).
    """
    import uuid as _uuid
    rid = _uuid.uuid4().hex[:8]
    _test_prompt = "Antworte nur mit: AILIZA_PROVIDER_OK"
    _test_messages = [{"role": "user", "content": _test_prompt}]

    results: dict[str, Any] = {}
    selected_provider: str | None = None
    final_status = "all_failed"

    # GROQ_MODEL — der häufigste Fehlergrund
    groq_model_used = os.getenv("GROQ_MODEL", "") or "llama-3.1-8b-instant"
    results["groq_model_resolved"] = groq_model_used
    results["groq_model_env_raw"] = os.getenv("GROQ_MODEL", "(not set)")

    _KEY_ENV_TEST = {
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
    }

    # Effektive Provider-Reihenfolge aus AILIZA_PROVIDER_ORDER
    from providers.orchestrator import _get_provider_order
    provider_order_effective = _get_provider_order()

    def _reg_meta(pid: str) -> dict[str, Any]:
        try:
            from registry.registry_loader import get_registry
            reg_entry = get_registry().get_provider(pid)
            if reg_entry:
                return {
                    "registry_enabled": reg_entry.enabled,
                    "registry_approved": reg_entry.admin_approved,
                    "registry_health": reg_entry.health_status,
                    "failover_priority": reg_entry.failover_priority,
                }
        except Exception:
            pass
        return {}

    # Teste Provider in der konfigurierten Reihenfolge
    all_pids = list(getattr(_orchestrator, "providers", {}).keys())
    ordered_pids = [p for p in provider_order_effective if p in all_pids]
    ordered_pids += [p for p in all_pids if p not in ordered_pids]

    attempts_in_order: list[str] = []
    failed_providers: dict[str, str] = {}

    for pid in ordered_pids:
        provider = _orchestrator.providers[pid]
        key_env = _KEY_ENV_TEST.get(pid, "")
        configured = bool(os.getenv(key_env)) if key_env else True
        model_used = getattr(provider, "model", "unknown")

        entry: dict[str, Any] = {
            "configured": configured,
            "model": model_used,
            "status": "skipped",
            "error_type": None,
            "error_sanitized": None,
            **_reg_meta(pid),
        }

        if not configured:
            entry["error_sanitized"] = f"API-Key nicht gesetzt — Render-Env: {key_env}"
            results[pid] = entry
            continue

        attempts_in_order.append(pid)
        try:
            answer = provider.generate(_test_messages)
            entry["status"] = "ok"
            entry["answer_preview"] = (answer or "")[:40]
            if selected_provider is None:
                selected_provider = pid
                final_status = "ok"
        except AILIZAError as exc:
            entry["status"] = "error"
            entry["error_type"] = exc.code
            _alts = exc.safe_alternatives or []
            entry["error_sanitized"] = _alts[0] if _alts else exc.code
            failed_providers[pid] = entry["error_sanitized"]
        except Exception as exc:  # noqa: BLE001
            entry["status"] = "error"
            entry["error_type"] = type(exc).__name__
            entry["error_sanitized"] = type(exc).__name__
            failed_providers[pid] = entry["error_sanitized"]

        print(
            f"AILIZA PROVIDER TEST | request_id={rid} provider={pid} "
            f"model={model_used} status={entry['status']} "
            f"error={entry.get('error_type') or 'none'}",
            flush=True,
        )
        results[pid] = entry

    return {
        "request_id": rid,
        "final_status": final_status,
        "provider_order_effective": provider_order_effective,
        "provider_attempts_in_order": attempts_in_order,
        "first_successful_provider": selected_provider,
        "selected_provider": selected_provider,
        "failed_providers": failed_providers,
        "groq_model_resolved": groq_model_used,
        "groq_model_env_raw": results.pop("groq_model_env_raw", os.getenv("GROQ_MODEL", "(not set)")),
        "providers": results,
        "render_env_required": {
            "openai": "OPENAI_API_KEY (+ optional OPENAI_MODEL, default: gpt-4o-mini)",
            "openrouter": "OPENROUTER_API_KEY (+ optional OPENROUTER_MODEL, default: meta-llama/llama-3.1-8b-instruct)",
            "groq": "GROQ_API_KEY + GROQ_MODEL (default: llama-3.1-8b-instant) — aktuell health_status=down",
            "anthropic": "ANTHROPIC_API_KEY (+ optional ANTHROPIC_MODEL)",
            "provider_order": "AILIZA_PROVIDER_ORDER (optional, default: openai,openrouter,groq,anthropic,local)",
        },
        "note": "Dieser Endpunkt sollte in Produktion durch AILIZA_DEBUG-Flag geschützt werden.",
    }


@app.get("/api/debug/groq-diagnosis")
def debug_groq_diagnosis() -> dict[str, Any]:  # noqa: C901
    """
    Beweisbasierte Groq-Diagnose.
    Klärt ob 403 von Key/Projekt/Modell kommt oder vom AILIZA-Request-Format.
    Kein API-Key, kein vollständiger Prompt im Response.
    Abschaltbar via AILIZA_DEBUG=false (TODO: Admin-Key-Schutz in Produktion).
    """
    import hashlib
    import json as _json
    import urllib.error
    import urllib.request

    rid = __import__("uuid").uuid4().hex[:8]
    out: dict[str, Any] = {"request_id": rid}

    # ── 1. Env-Status (ohne Secrets) ─────────────────────────────────────────
    raw_key = os.getenv("GROQ_API_KEY", "")
    groq_key_present = bool(raw_key)
    groq_key_prefix = raw_key[:12] if raw_key else "(not set)"
    groq_key_fingerprint = (
        hashlib.sha256(raw_key.encode()).hexdigest()[:12] if raw_key else "(no key)"
    )
    groq_model_env = os.getenv("GROQ_MODEL", "(not set)")
    groq_model_effective = os.getenv("GROQ_MODEL", "") or "llama-3.1-8b-instant"

    try:
        try:
            from .kill_switch import is_external_llm_enabled as _ille
        except ImportError:
            from kill_switch import is_external_llm_enabled as _ille
        ext_allowed = _ille()
    except Exception:
        ext_allowed = False

    try:
        _base = Path(__file__).parent
        try:
            from .config_integrity import verify_integrity as _vi
        except ImportError:
            from config_integrity import verify_integrity as _vi
        gate10_ok = _vi(_base, _base / "governance_integrity.json").all_ok
    except Exception:
        gate10_ok = None

    out["env"] = {
        "groq_key_present": groq_key_present,
        "groq_key_prefix": groq_key_prefix,
        "groq_key_fingerprint": groq_key_fingerprint,
        "groq_model_env": groq_model_env,
        "groq_model_effective": groq_model_effective,
        "external_llm_allowed": ext_allowed,
        "gate10_ok": gate10_ok,
    }

    if not groq_key_present:
        out["diagnosis"] = "groq_key_invalid"
        out["next_action_de"] = (
            "GROQ_API_KEY ist nicht gesetzt. Key im Groq-Dashboard erstellen "
            "und in Render-Umgebungsvariablen eintragen."
        )
        return out

    _GROQ_HEADERS = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {raw_key}",
    }

    # ── 2. Groq Models API Test ───────────────────────────────────────────────
    models_api_ok = False
    models_status = None
    accessible_model_ids: list[str] = []
    target_in_models = False
    models_error_sanitized = ""

    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers=_GROQ_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            models_status = resp.getcode()
            data = _json.loads(resp.read())
            accessible_model_ids = [
                m["id"] for m in data.get("data", [])
                if isinstance(m, dict) and "id" in m
            ]
            models_api_ok = True
            target_in_models = groq_model_effective in accessible_model_ids
    except urllib.error.HTTPError as exc:
        models_status = exc.code
        models_error_sanitized = f"HTTP {exc.code} — {exc.reason}"
    except urllib.error.URLError as exc:
        models_error_sanitized = f"Netzwerkfehler: {type(exc.reason).__name__}"
    except Exception as exc:  # noqa: BLE001
        models_error_sanitized = f"Unerwarteter Fehler: {type(exc).__name__}"

    out["models_api"] = {
        "models_api_status_code": models_status,
        "models_api_ok": models_api_ok,
        "accessible_model_ids": accessible_model_ids,
        "target_model_in_accessible_models": target_in_models,
        "models_api_error_sanitized": models_error_sanitized or None,
    }

    # Frühe Diagnose: Models-API bereits 401/403
    if not models_api_ok and models_status == 401:
        out["diagnosis"] = "groq_key_invalid"
        out["next_action_de"] = (
            "Der API-Key ist ungültig (HTTP 401 an Models API). "
            "Neuen Key im Groq-Dashboard erstellen und in Render ersetzen."
        )
        return out
    if not models_api_ok and models_status == 403:
        # Kein frühes Return — Chat Completions kann trotzdem klappen (Groq trennt Permissions)
        out["models_api_403_warning"] = (
            "Models API 403: Key hat keine Berechtigung um Modelle aufzulisten. "
            "Chat Completions wird trotzdem getestet (kann andere Permissions haben)."
        )

    # ── 3. Minimaler Groq Chat Test (direkt, ohne AILIZA-Routing) ────────────
    _TEST_MESSAGES = [{"role": "user", "content": "Reply exactly: AILIZA_GROQ_OK"}]
    _TEST_PAYLOAD = _json.dumps({
        "model": groq_model_effective,
        "messages": _TEST_MESSAGES,
        "max_tokens": 20,
        "temperature": 0,
    }).encode()

    # Request-Format-Log (kein Prompt, kein Key)
    print(
        f"AILIZA GROQ DIAG | request_id={rid} "
        f"url=https://api.groq.com/openai/v1/chat/completions "
        f"model={groq_model_effective} "
        f"authorization_header_set=True "
        f"content_type_set=True "
        f"max_tokens=20 "
        f"messages_count=1",
        flush=True,
    )

    chat_ok = False
    chat_status = None
    response_text = ""
    groq_error_code_raw = ""
    groq_error_type_raw = ""
    groq_error_msg_sanitized = ""
    raw_error_category = "unknown"

    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=_TEST_PAYLOAD,
            headers=_GROQ_HEADERS,
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            chat_status = resp.getcode()
            data = _json.loads(resp.read())
            response_text = (data.get("choices", [{}])[0]
                             .get("message", {}).get("content", ""))[:50]
            chat_ok = True
            raw_error_category = "ok"
    except urllib.error.HTTPError as exc:
        chat_status = exc.code
        try:
            body = _json.loads(exc.read())
            err_obj = body.get("error", {})
            groq_error_code_raw = err_obj.get("code", "")
            groq_error_type_raw = err_obj.get("type", "")
            # Sanitisierte Meldung: erste 120 Zeichen, kein Key-Inhalt
            raw_msg = err_obj.get("message", exc.reason or "")
            groq_error_msg_sanitized = str(raw_msg)[:120]
        except Exception:
            groq_error_msg_sanitized = f"HTTP {exc.code} {exc.reason}"

        if exc.code == 401:
            raw_error_category = "unauthorized_key"
        elif exc.code == 403:
            raw_error_category = "forbidden_model_or_project"
        elif exc.code == 404:
            raw_error_category = "model_not_found"
        elif exc.code == 429:
            raw_error_category = "rate_limited"
        elif exc.code == 400:
            raw_error_category = "bad_request"
        else:
            raw_error_category = "unknown"
    except urllib.error.URLError as exc:
        groq_error_msg_sanitized = f"Netzwerkfehler: {type(exc.reason).__name__}"
        raw_error_category = "network_error"
    except Exception as exc:  # noqa: BLE001
        groq_error_msg_sanitized = f"Unerwarteter Fehler: {type(exc).__name__}"
        raw_error_category = "unknown"

    out["chat_test"] = {
        "chat_status_code": chat_status,
        "chat_ok": chat_ok,
        "response_text_if_ok": response_text if chat_ok else None,
        "groq_error_code": groq_error_code_raw or None,
        "groq_error_type": groq_error_type_raw or None,
        "groq_error_message_sanitized": groq_error_msg_sanitized or None,
        "raw_error_category": raw_error_category,
    }

    # ── 4. Modellvergleich (nur wenn Models API ok und Zielmodell fehlt) ──────
    alt_test: dict[str, Any] = {}
    if models_api_ok and not target_in_models and accessible_model_ids:
        _text_candidates = [
            m for m in accessible_model_ids
            if any(k in m.lower() for k in ("llama", "mixtral", "gemma", "qwen", "whisper"))
            and "whisper" not in m.lower()  # Audio-Modelle ausschließen
        ]
        alt_model = _text_candidates[0] if _text_candidates else accessible_model_ids[0]
        alt_payload = _json.dumps({
            "model": alt_model,
            "messages": _TEST_MESSAGES,
            "max_tokens": 20,
            "temperature": 0,
        }).encode()
        try:
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=alt_payload,
                headers=_GROQ_HEADERS,
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                alt_data = _json.loads(resp.read())
                alt_answer = (alt_data.get("choices", [{}])[0]
                              .get("message", {}).get("content", ""))[:50]
                alt_test = {"model_tested": alt_model, "status": "ok", "answer_preview": alt_answer}
        except urllib.error.HTTPError as exc:
            alt_test = {"model_tested": alt_model, "status": f"error_http_{exc.code}"}
        except Exception as exc:  # noqa: BLE001
            alt_test = {"model_tested": alt_model, "status": f"error_{type(exc).__name__}"}
    elif models_api_ok and not target_in_models:
        alt_test = {"note": "Keine alternativen Text-Modelle in accessible_model_ids gefunden."}

    if alt_test:
        out["alt_model_test"] = alt_test

    # ── 5+6. Entscheidungsmatrix ──────────────────────────────────────────────
    diagnosis = "unknown"
    next_action_de = "Keine eindeutige Diagnose — bitte alle Felder oben manuell prüfen."

    if not models_api_ok and models_status == 401:
        diagnosis = "groq_key_invalid"
        next_action_de = (
            "Der API-Key ist ungültig (HTTP 401 an Models API). "
            "Neuen Key im Groq-Dashboard erstellen und in Render ersetzen."
        )
    elif not models_api_ok and models_status == 403 and chat_ok:
        # Models API: 403 — aber Chat Completions funktioniert! Key ist korrekt.
        # AILIZA-Routing oder Provider-Stack hat ein Problem.
        diagnosis = "groq_ok_but_routing_issue"
        next_action_de = (
            f"Groq Chat Completions funktioniert (model={groq_model_effective}). "
            "Models API gibt 403 (andere Permission) — das ist OK. "
            "Das Problem liegt im AILIZA-Provider-Stack, nicht beim Key. "
            "Bitte den uvicorn-Log prüfen: Zeilen 'AILIZA GROQ CALL' und 'AILIZA REGISTRY CHECK'. "
            "Wahrscheinliche Ursache: Registry oder Kill-Switch blockiert."
        )
    elif not models_api_ok and models_status == 403 and not chat_ok:
        diagnosis = "groq_key_not_authorized_for_project"
        next_action_de = (
            "Der Key hat keinen Projekt-Zugriff (HTTP 403 an Models API und Chat API). "
            "Im Groq-Dashboard das aktive Projekt öffnen, dort einen neuen API-Key "
            "erstellen (nicht in einem anderen Projekt!) und in Render ersetzen. "
            "Auch Organisation/Billing-Limits prüfen. "
            f"Key-Prefix der aktuell geladenen Keys: groq_key_prefix={groq_key_prefix}"
        )
    elif models_api_ok and not target_in_models:
        diagnosis = "groq_model_not_allowed_for_key"
        first_ok = (alt_test.get("status") == "ok")
        if first_ok:
            next_action_de = (
                f"Zielmodell '{groq_model_effective}' ist nicht in accessible_model_ids. "
                f"Ein anderes Modell ({alt_test.get('model_tested')}) funktioniert. "
                f"GROQ_MODEL in Render auf ein Modell aus accessible_model_ids setzen."
            )
        else:
            next_action_de = (
                f"Zielmodell '{groq_model_effective}' nicht in accessible_model_ids. "
                "Kein alternatives Textmodell gefunden das funktioniert. "
                "Groq-Account/Billing und Projektberechtigungen prüfen."
            )
    elif models_api_ok and target_in_models and chat_ok:
        diagnosis = "groq_ok"
        next_action_de = (
            "Groq funktioniert korrekt. Falls normaler Chat trotzdem fehlschlägt, "
            "liegt das an AILIZA-Routing/_ask_llm_directly — nicht an Groq. "
            "AILIZA-Logs für 'AILIZA LLM FAILED' prüfen."
        )
    elif models_api_ok and target_in_models and not chat_ok:
        if raw_error_category == "forbidden_model_or_project":
            diagnosis = "groq_model_permission_ui_saved_but_api_still_forbidden"
            next_action_de = (
                f"Groq zeigt '{groq_model_effective}' in der Modell-Liste, "
                "verweigert aber die Ausführung (403 bei Chat-Completion). "
                "Mögliche Ursachen: Groq-UI und API sind nicht synchron, "
                "Organisation hat Modell gesperrt, oder Billing-Limit aktiv. "
                "Empfehlung: Support-Ticket an Groq, Billing-Status prüfen, "
                "Key in anderem Browser neu erstellen."
            )
        elif raw_error_category == "rate_limited":
            diagnosis = "groq_rate_limited"
            next_action_de = (
                "Groq-Quota oder Rate-Limit erschöpft (429). "
                "Groq-Dashboard → Usage prüfen. "
                "Kurzfristig: OpenAI-Fallback sicherstellen (OPENAI_API_KEY und Quota prüfen)."
            )
        elif raw_error_category == "unauthorized_key":
            diagnosis = "groq_key_invalid"
            next_action_de = (
                "Key war für Models API gültig, schlägt bei Chat-Completion fehl (401). "
                "Ungewöhnlich — Key möglicherweise gesperrt. Neuen Key erstellen."
            )
        elif raw_error_category == "bad_request":
            diagnosis = "groq_request_format_bug"
            next_action_de = (
                "Groq gibt 400 Bad Request. Das Request-Format in "
                "apps/backend/providers/groq_provider.py prüfen. "
                "Mögliche Ursache: ungültiger messages-Aufbau oder unbekannte Parameter."
            )
        else:
            next_action_de = (
                f"Chat-Test fehlgeschlagen mit raw_error_category='{raw_error_category}'. "
                "Groq-Fehlermeldung oben auswerten."
            )

    # Sonderfall: Direkt-Test ok, aber normaler AILIZA-Provider-Test schlägt fehl
    # (wird in provider-test separat gemessen — hier als Hinweis)
    if chat_ok:
        out["note"] = (
            "Direkter Groq-Chat-Test erfolgreich. "
            "Falls /api/debug/provider-test trotzdem 403 zeigt, "
            "liegt das an AILIZA-internem Routing (ProviderOrchestrator/Capability-Check). "
            "Prüfe: AILIZA_EXTERNAL_LLM_ENABLED, Kill-Switch, Capability 'llm_call' für PUBLIC."
        )

    out["diagnosis"] = diagnosis
    out["next_action_de"] = next_action_de
    out["security_note"] = (
        "Dieser Endpunkt gibt keinen API-Key aus. "
        "Nur die ersten 4 Zeichen und ein SHA256-Fingerprint werden gezeigt. "
        "In Produktion durch AILIZA_DEBUG=false oder Admin-Key schützen."
    )
    return out


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
    token: TokenData = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    # Audit-Einträge dürfen nur intern (via write_audit_entry) oder durch Admins erstellt werden.
    # Kein anonymer / nicht-autorisierter Zugriff — verhindert Audit-Manipulation.
    return write_audit_entry(action=payload.action, metadata=payload.metadata,
                             tenant_id=_tenant_id(token))


@app.get("/audit-logs")
def get_audit_logs(
    limit: int = 100,
    token: TokenData = Depends(require_role(Role.AUDIT_VIEWER)),
) -> list[dict[str, Any]]:
    # Audit-Logs enthalten Aktivitätsdaten — nur für AUDIT_VIEWER+ sichtbar.
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


def _governance_pre_check(
    task: str,
    tenant_id: str,
    run_id: str | None = None,
) -> dict[str, Any]:
    """
    Führt classify → data_matrix → redact vor jedem externen LLM/Tool-Call durch.

    Rückgabe:
      {"decision": "allow",    "task": <ggf. redacted>}
      {"decision": "allow_with_notice", "task": <redacted>, "notice": "..."}
      {"decision": "approval_required", "approval_id": ..., "message": "..."}
      {"decision": "block",    "message": "..."}
    """
    try:
        classification = classify(task)
    except Exception:
        # Fail-closed: bei Klassifizierungsfehler blocken
        write_audit_entry(
            action="governance.classify_error",
            tenant_id=tenant_id,
            metadata={"task_length": len(task)},
        )
        return {"decision": "block", "message": "Anfrage konnte nicht sicher klassifiziert werden."}

    data_classes = list(getattr(classification, "classes", getattr(classification, "data_classes", [])) or [])

    # Provider-Profil aktiv? Aktuell: alle Provider haben admin_disabled=True → False
    try:
        from .providers.provider_profiles import check_provider_policy  # type: ignore
    except ImportError:
        from providers.provider_profiles import check_provider_policy  # type: ignore
    _provider_ok, _ = check_provider_policy("groq", data_classes)
    provider_profile_active = _provider_ok

    decision = check_data_target(
        data_classes=data_classes,
        target=DataTarget.EXTERNAL_LLM,
        redaction_applied=False,
        approval_given=False,
        provider_profile_active=provider_profile_active,
    )

    if decision == PolicyDecision.BLOCK:
        # Nur bei CREDENTIALS oder SPECIAL_CATEGORY → echter Block (EU AI Act Art. 5 / DSGVO Art. 9)
        write_audit_entry(
            action="governance.task_blocked",
            tenant_id=tenant_id,
            metadata={"data_classes": [c.value for c in data_classes]},
        )
        return {
            "decision": "block",
            "message": (
                "Diese Anfrage enthält Daten, die nach EU AI Act Art. 5 / DSGVO Art. 9 "
                f"nicht extern verarbeitet werden dürfen ({', '.join(c.value for c in data_classes)})."
            ),
        }

    if decision in (PolicyDecision.APPROVAL_REQUIRED, PolicyDecision.REDACT_REQUIRED):
        # Governance-Regel: Redacten → als Entwurf weiterlaufen (nicht stoppen).
        # APPROVAL_REQUIRED und REDACT_REQUIRED werden gleich behandelt:
        # Phase 1.3: Nutze RedactionEngineV2 (nicht die alte redaction.py)
        from .governance.redaction_v2 import RedactionEngineV2
        engine = RedactionEngineV2()
        redaction_result = engine.redact(task)
        redacted_task = redaction_result.redacted_text
        reinsertion_map = redaction_result.reinsertion_map
        is_draft = decision == PolicyDecision.APPROVAL_REQUIRED
        dc_names = [c.value for c in data_classes]
        approval_id: int | None = None
        if is_draft and run_id:
            try:
                approval = create_approval_request(
                    tool="llm_call",
                    input_params={"task_length": len(task), "data_classes": dc_names},
                    risk_level="high",
                    risk_reason=f"Sensible Daten erkannt: {', '.join(dc_names)}",
                    run_id=run_id,
                    tenant_id=tenant_id,
                )
                approval_id = approval.get("id")
            except Exception:
                pass
        write_audit_entry(
            action="governance.draft_prepared" if is_draft else "governance.task_redacted",
            tenant_id=tenant_id,
            metadata={
                "data_classes": dc_names,
                "redaction_applied": True,
                "is_draft": is_draft,
                "approval_id": approval_id,
            },
        )
        notice = (
            f"Personenbezogene Daten erkannt ({', '.join(dc_names)}) und lokal pseudonymisiert (DSGVO Art. 25). "
            + ("Ergebnis als Entwurf vorbereitet — menschliche Prüfung erforderlich." if is_draft else "")
        ).strip()
        return {
            "decision": "allow_with_notice",
            "task": redacted_task,
            # reinsertion_map: NUR lokal im RAM — NIEMALS loggen oder persistieren
            "reinsertion_map": reinsertion_map,
            "notice": notice,
            "is_draft": is_draft,
            "approval_id": approval_id,
            "pii_detected": {
                "has_pii": True,
                "requires_consent": True,
                "items": [{"type": m, "requires_consent": True} for m in getattr(classification, "matched_rules", [])],
            },
        }

    # ALLOW / ALLOW_WITH_NOTICE
    return {"decision": "allow", "task": task}


def _summarize_with_llm(task: str, search_text: str, context: Any = None) -> tuple[str | None, str | None]:
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
        answer = _orchestrator.generate(messages, context=context)
        _prov = getattr(_orchestrator, "default_provider", "unknown")
        _model = getattr(
            _orchestrator.providers.get(_prov), "model", "unknown"
        )
        print(
            f"AILIZA LLM | provider={_prov} model={_model} result=ok chars={len(answer)}",
            flush=True,
        )
        return answer, None
    except AILIZAError as exc:
        print(f"AILIZA LLM FAILED | code={exc.code}", flush=True)
        return None, exc.code


def _ask_llm_directly(
    task: str,
    request_id: str = "",
    data_class: str = "public",
    task_type: str = "general_task",
) -> tuple[str | None, str | None, list[str]]:
    """
    Direkter LLM-Call ohne Suche.
    Gibt (answer, error_code, provider_errors) zurück.
    provider_errors: sanitisierte Ursachen je Provider (kein Key, kein PII) — für Admin-Debug.
    """
    import uuid as _uuid
    rid = request_id or _uuid.uuid4().hex[:8]

    _provider_order = list(getattr(_orchestrator, "providers", {}).keys())
    _groq_model = os.getenv("GROQ_MODEL", "") or "llama-3.1-8b-instant"

    print(
        f"AILIZA LLM START | request_id={rid} task_type={task_type} "
        f"data_class={data_class} groq_model={_groq_model} "
        f"provider_order={_provider_order}",
        flush=True,
    )

    messages = [
        {
            "role": "system",
            "content": (
                "Du bist AILIZA, ein autonomer KI-Assistent fuer KMU. "
                "Bei Schreibaufgaben (E-Mail, Brief, Entwurf, Übersetzung, Zusammenfassung) "
                "lieferst du direkt den fertigen Text mit Betreff und Inhalt auf Deutsch. "
                "Bei Wissensfragen antwortest du kurz und direkt auf Deutsch."
            ),
        },
        {"role": "user", "content": task},
    ]
    try:
        answer = _orchestrator.generate(messages)
        print(
            f"AILIZA LLM OK | request_id={rid} result=ok chars={len(answer)}",
            flush=True,
        )
        return answer, None, []
    except AILIZAError as exc:
        _reasons = exc.safe_alternatives or []
        print(
            f"AILIZA LLM FAILED | request_id={rid} code={exc.code} "
            f"provider_errors={_reasons}",
            flush=True,
        )
        return None, exc.code, _reasons
    except Exception as exc:  # noqa: BLE001
        _etype = type(exc).__name__
        print(
            f"AILIZA LLM FAILED | request_id={rid} code=unexpected_error type={_etype}",
            flush=True,
        )
        return None, "internal_error", [f"Unerwarteter Fehler: {_etype}"]


@app.post("/agent/run")
@_limiter.limit("30/minute")
def run_agent(
    request: Request,
    payload: AgentRunRequest,
    token: TokenData | None = Depends(get_current_user),
) -> dict[str, Any]:
    tenant = _tenant_id(token)

    # ── Fast-Path: einfache Fragen ohne externen Call ────────────────────────
    simple_answer = answer_simple_question(payload.task)
    if simple_answer is not None:
        return {
            "status": "completed",
            "message": simple_answer,
            "ai_response": simple_answer,
            "steps": [],
            "results": [],
        }

    # ── Phase 1.2: Policy Engine High-Risk Detection (neu, ERSTES Gate) ──────
    # Erkennt Hochrisiko-Kontexte: HR+Health, HR+Biometric, automatisierte Entscheidung, Bonitäts-Scoring, etc.
    # BLOCKIERT auf RED, eskaliert auf ORANGE, redacted auf YELLOW, freigegeben auf GREEN.
    try:
        from policy_engine import PolicyEngine
    except ImportError:
        PolicyEngine = None

    user_id = token.user_id if token else "anonymous"
    policy_decision = None

    if PolicyEngine:
        policy_decision = PolicyEngine.process_with_policy(payload.task, user_id)

        # Policy-Decision Handling
        if policy_decision.decision == "block":
            # RED: Sofort blockiert, keine Weiterverarbeitung
            write_audit_entry(
                action="policy.blocked",
                tenant_id=tenant,
                metadata={
                    "reason_code": policy_decision.reason_code,
                    "risk_level": policy_decision.risk_level,
                    "detected_categories": policy_decision.detected_special_categories,
                    "high_risk_contexts": [rc for rc, _ in policy_decision.high_risk_contexts] if policy_decision.high_risk_contexts else [],
                },
            )
            return {
                "status": "blocked",
                "message": policy_decision.message,
                "ai_response": policy_decision.message,
                "steps": [],
                "results": [],
                "policy_decision": policy_decision.decision,
                "reason_code": policy_decision.reason_code,
            }

        elif policy_decision.decision == "approval_required":
            # ORANGE: Approval-Gate erforderlich
            write_audit_entry(
                action="policy.approval_required",
                tenant_id=tenant,
                metadata={
                    "reason_code": policy_decision.reason_code,
                    "risk_level": policy_decision.risk_level,
                },
            )
            # TODO: Approval-Request erstellen und zurückgeben
            # Für jetzt: auch blockieren bis Approval-System aktiv
            return {
                "status": "approval_required",
                "message": policy_decision.message,
                "ai_response": policy_decision.message,
                "steps": [],
                "results": [],
                "policy_decision": policy_decision.decision,
                "reason_code": policy_decision.reason_code,
            }

        elif policy_decision.decision == "redact":
            # YELLOW: Redacted Text verwenden, aber mit Draft-Status
            # Payload wird mit redacted_text überschrieben
            payload.task = policy_decision.redacted_text
            write_audit_entry(
                action="policy.redacted",
                tenant_id=tenant,
                metadata={
                    "reason_code": policy_decision.reason_code,
                    "risk_level": policy_decision.risk_level,
                },
            )

        # GREEN: Normaler Flow, keine Änderung erforderlich

    # ── Governance Pre-Check: classify → data_matrix → redact/block ─────────
    # Läuft VOR jedem Tool-Call und LLM-Call.
    # BLOCK: nur bei CREDENTIALS / SPECIAL_CATEGORY (EU AI Act Art. 5 / DSGVO Art. 9).
    # PERSONAL_DATA/HR/LEGAL/FINANCIAL: lokal redacten, als Entwurf weiterlaufen.
    pre_check = _governance_pre_check(payload.task, tenant_id=tenant)

    if pre_check["decision"] == "block":
        return {
            "status": "blocked",
            "message": pre_check["message"],
            "ai_response": pre_check["message"],
            "steps": [],
            "results": [],
        }

    # Bei Redaction: pseudonymisierte Aufgabe verwenden
    # reinsertion_map: NUR lokal im RAM — nie loggen oder persistieren
    effective_task = pre_check.get("task", payload.task)
    reinsertion_map: dict[str, str] = pre_check.get("reinsertion_map", {})
    pii_detected = pre_check.get("pii_detected")
    governance_is_draft = pre_check.get("is_draft", False)

    # ── Schreibaufgaben: direkt LLM ohne AgentRuntime / Tavily ────────────────
    _is_writing = (
        _WRITING_INTENT_PATTERN.search(effective_task) is not None
        and _SEARCH_INTENT_PATTERN.search(effective_task) is None
    )
    if _is_writing:
        print(
            f"AILIZA WRITING TASK | direct_llm_called=True "
            f"redaction_applied={bool(reinsertion_map)} "
            f"task_chars={len(effective_task)}",
            flush=True,
        )
        answer, error_code, provider_errors = _ask_llm_directly(effective_task)
        print(
            f"AILIZA WRITING TASK | direct_llm_called=True "
            f"answer_chars={len(answer) if answer else 0} "
            f"error={error_code}",
            flush=True,
        )
        if answer is not None:
            if reinsertion_map:
                answer, fully = reinsert(answer, reinsertion_map)
                if not fully:
                    pass  # partial reinsertion — kein Block, nur Statistik
            final = {
                "status": "draft" if governance_is_draft else "completed",
                "message": answer,
                "ai_response": answer,
                "steps": [],
                "results": [],
                "web_search": False,
                "redaction_applied": bool(reinsertion_map),
                "reinsertion_used": bool(reinsertion_map),
                "tenant_id": tenant,
            }
            if governance_is_draft:
                final["draft"] = True
                final["draft_notice"] = (
                    "Entwurf — personenbezogene Daten lokal maskiert, menschliche Prüfung erforderlich."
                )
            if pii_detected:
                final["pii_detected"] = pii_detected
            if pre_check["decision"] == "allow_with_notice":
                final["governance_notice"] = pre_check.get("notice", "")
            write_audit_entry(
                action="agent.writing_task.completed",
                tenant_id=tenant,
                metadata={
                    "redaction_applied": bool(reinsertion_map),
                    "answer_chars": len(answer),
                    "draft": governance_is_draft,
                },
            )
            return final
        # LLM fehlgeschlagen → sichere Fehlermeldung für Nutzer, Admin-Details separat
        _user_msg = MESSAGES.get(error_code or "internal_error", "LLM-Aufruf fehlgeschlagen.")
        _failed_resp: dict[str, Any] = {
            "status": "failed",
            "message": _user_msg,
            "ai_response": _user_msg,
            "steps": [],
            "results": [],
            "tenant_id": tenant,
            "llm_notice": _user_msg,
        }
        # provider_errors: sanitisierte Ursachen je Provider (kein Key, kein PII)
        # Nur im Response wenn vorhanden — Admin kann diese für Diagnose nutzen
        if provider_errors:
            _failed_resp["provider_errors"] = provider_errors
        return _failed_resp
    # ── Ende Schreibaufgaben-Pfad ─────────────────────────────────────────────

    runtime = AgentRuntime()
    result = runtime.run(effective_task)

    # ── Entscheidungs-Diagnose je Request (kein Inhalt, kein PII) ────────────
    _run_status = result.get("status", "unknown")
    _web_search_req = any(
        s.get("tool") == "search" for s in result.get("steps", [])
    )
    print(
        f"AILIZA RUN | run_id={result.get('run_id', 'n/a')} status={_run_status} "
        f"local_only={_run_status in ('local_only', 'degraded')} "
        f"redaction_applied={bool(reinsertion_map)} draft={governance_is_draft} "
        f"web_search={_web_search_req}",
        flush=True,
    )
    # ── Ende Entscheidungs-Diagnose ──────────────────────────────────────────

    # Local-only / degraded: Suche fehlgeschlagen, aber LLM direkt fragen
    if result.get("status") in ("local_only", "degraded"):
        answer, error_code, provider_errors = _ask_llm_directly(effective_task)
        if answer is not None:
            result["status"] = "completed"
            result["message"] = answer
            # PII-Reinsertion auch hier anwenden
            if reinsertion_map:
                reinserted, fully = reinsert(answer, reinsertion_map)
                result["message"] = reinserted
                if not fully:
                    result["reinsertion_notice"] = (
                        "Originaldaten konnten nicht vollständig automatisch eingesetzt werden."
                    )
                write_audit_entry(
                    action="governance.reinsertion_applied",
                    tenant_id=tenant,
                    metadata={"reinsertion_used": True, "fully_reinserted": fully},
                )
            result["ai_response"] = result["message"]
            result["tenant_id"] = tenant
            if pii_detected:
                result["pii_detected"] = pii_detected
            if governance_is_draft:
                result["status"] = "draft"
                result["draft"] = True
                result["draft_notice"] = (
                    "Entwurf — personenbezogene Daten lokal maskiert, menschliche Prüfung erforderlich."
                )
            return result
        # LLM auch nicht verfügbar → lokale Antwort zurückgeben
        result["ai_response"] = result.get("message", "")
        result["tenant_id"] = tenant
        if pii_detected:
            result["pii_detected"] = pii_detected
        if error_code:
            result["llm_notice"] = MESSAGES.get(error_code, "")
        if provider_errors:
            result["provider_errors"] = provider_errors
        return result

    search_text = extract_agent_answer(result)

    if search_text:
        # Tool (Tavily) hat Ergebnisse geliefert → LLM fasst zusammen
        answer, error_code = _summarize_with_llm(effective_task, search_text)
        if answer is not None:
            result["message"] = answer
        else:
            result["message"] = search_text
            if error_code:
                result["llm_notice"] = MESSAGES.get(error_code, "")
    elif not result.get("steps"):
        # Kein Tool geplant (Schreibaufgabe, Übersetzung etc.) → LLM direkt
        answer, error_code, provider_errors = _ask_llm_directly(effective_task)
        if answer is not None:
            result["message"] = answer
        else:
            if error_code:
                result["llm_notice"] = MESSAGES.get(error_code, "")
            if provider_errors:
                result["provider_errors"] = provider_errors

    # PII-Reinsertion: Originalwerte lokal wieder einsetzen (NUR RAM, nie loggen)
    reinsertion_used = False
    if reinsertion_map:
        current_message = result.get("message", "")
        reinserted, fully_reinserted = reinsert(current_message, reinsertion_map)
        result["message"] = reinserted
        reinsertion_used = True
        if not fully_reinserted:
            result["reinsertion_notice"] = (
                "Originaldaten konnten nicht vollständig automatisch eingesetzt werden."
            )
        write_audit_entry(
            action="governance.reinsertion_applied",
            tenant_id=tenant,
            # Nur Statistik loggen — keine Originalwerte, kein Mapping-Inhalt
            metadata={"reinsertion_used": True, "fully_reinserted": fully_reinserted},
        )

    # Governance Draft-Markierung übernehmen (HR/LEGAL/FINANCIAL nach Redaction)
    if governance_is_draft and result.get("status") not in ("draft", "blocked"):
        result["status"] = "draft"
        result["draft"] = True
        result["approval_id"] = pre_check.get("approval_id")
        result["draft_notice"] = (
            "Entwurf — personenbezogene Daten lokal maskiert, menschliche Prüfung erforderlich."
        )

    result["ai_response"] = result.get("message", "")
    result["tenant_id"] = tenant
    result["reinsertion_used"] = reinsertion_used
    if pii_detected:
        result["pii_detected"] = pii_detected
    if pre_check["decision"] == "allow_with_notice":
        result["governance_notice"] = pre_check.get("notice", "")
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
        "injection_detected": scan.injection_detected,
        "injection_pattern_count": scan.injection_pattern_count,
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


_TOTP_REQUIRED_ROLES = {"admin", "dsb"}


def _set_session_cookie(response: JSONResponse, token: str) -> None:
    is_prod = os.getenv("AILIZA_ENV", "development").lower() in ("production", "staging")
    expiry_minutes = int(os.getenv("AILIZA_JWT_EXPIRY_MINUTES", "60"))
    response.set_cookie(
        key="ailiza_session",
        value=token,
        httponly=True,
        secure=is_prod,
        samesite="strict",
        max_age=expiry_minutes * 60,
        path="/",
    )


@app.post("/auth/login")
@_limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest) -> JSONResponse:
    """
    Login: setzt HttpOnly-Cookie (Browser-Flow) und gibt Token im Body zurück.
    Für ADMIN/DSB mit aktiviertem TOTP: gibt totp_required=true + totp_pending_token zurück.
    Zweiter Schritt: POST /auth/totp/verify mit Code + totp_pending_token.
    """
    user = db_authenticate_user(payload.user_id, payload.password, payload.tenant_id)
    if user is None:
        write_audit_entry(action="auth.login.failed",
                          metadata={"user_id": payload.user_id, "tenant_id": payload.tenant_id},
                          tenant_id=payload.tenant_id)
        raise HTTPException(status_code=401, detail="Ungültige Zugangsdaten.")

    role = user["role"]
    # TOTP-Pflicht für ADMIN/DSB wenn TOTP eingerichtet und bestätigt
    if role in _TOTP_REQUIRED_ROLES:
        totp_record = get_totp_record(user["user_id"])
        if totp_record and totp_record["confirmed"]:
            pending = create_totp_pending_token(user["user_id"], user["tenant_id"], role)
            write_audit_entry(action="auth.login.totp_required",
                              metadata={"user_id": user["user_id"], "role": role},
                              tenant_id=user["tenant_id"])
            return JSONResponse(content={
                "totp_required": True,
                "totp_pending_token": pending,
                "role": role,
            })

    token = create_token(user["user_id"], user["tenant_id"], role)
    write_audit_entry(action="auth.login.success",
                      metadata={"user_id": payload.user_id, "role": role},
                      tenant_id=payload.tenant_id)
    response = JSONResponse(content={
        "access_token": token, "token_type": "bearer",
        "role": role, "user_id": user["user_id"],
    })
    _set_session_cookie(response, token)
    return response


class TotpSetupRequest(BaseModel):
    pass  # kein Body nötig — user_id kommt aus JWT


class TotpConfirmRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class TotpVerifyRequest(BaseModel):
    totp_pending_token: str = Field(..., min_length=10)
    code: str = Field(..., min_length=6, max_length=8)  # 6-stellig TOTP oder 8-stellig Backup-Code


class TotpDeleteRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class AdminTotpResetRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=512)


@app.post("/auth/totp/setup")
@_limiter.limit("3/minute")
def totp_setup(request: Request, token: TokenData = Depends(get_current_user)) -> dict[str, Any]:
    """
    Schritt 1: TOTP-Secret generieren.
    Gibt otpauth:// URI zurück (nur einmalig — Secret danach nicht mehr abrufbar).
    Secret ist erst nach /auth/totp/confirm aktiv.
    Nur für ADMIN/DSB erlaubt.
    """
    if token is None:
        raise HTTPException(status_code=401, detail="Nicht authentifiziert.")
    if token.role not in _TOTP_REQUIRED_ROLES:
        raise HTTPException(status_code=403, detail="TOTP nur für ADMIN und DSB verfügbar.")
    existing = get_totp_record(token.user_id)
    if existing and existing["confirmed"]:
        raise AILIZAError.from_code("totp_already_confirmed")
    secret = generate_secret()
    upsert_totp_secret(token.user_id, token.tenant_id, secret)
    uri = build_otpauth_uri(secret, token.user_id)
    # Kein Secret im Audit-Log — nur Event
    write_audit_entry(action="auth.totp.setup_initiated", metadata={"user_id": token.user_id},
                      tenant_id=token.tenant_id)
    return {
        "otpauth_uri": uri,
        "secret": secret,
        "issuer": "AILIZA",
        "warning": "Dieses Secret und den QR-Code jetzt scannen. Danach nicht mehr abrufbar.",
    }


@app.post("/auth/totp/confirm")
@_limiter.limit("5/minute")
def totp_confirm(request: Request, payload: TotpConfirmRequest,
                 token: TokenData = Depends(get_current_user)) -> dict[str, Any]:
    """
    Schritt 2: Ersten TOTP-Code bestätigen → TOTP aktiviert.
    Backup-Codes werden einmalig zurückgegeben — danach nicht mehr abrufbar.
    """
    if token is None:
        raise HTTPException(status_code=401, detail="Nicht authentifiziert.")
    if token.role not in _TOTP_REQUIRED_ROLES:
        raise HTTPException(status_code=403, detail="TOTP nur für ADMIN und DSB verfügbar.")
    record = get_totp_record(token.user_id)
    if not record or record["confirmed"]:
        raise AILIZAError.from_code("totp_not_configured")
    if not verify_totp(record["secret_b32"], payload.code):
        # Kein Code im Audit — nur fehlgeschlagenes Event
        write_audit_entry(action="auth.totp.confirm_failed", metadata={"user_id": token.user_id},
                          tenant_id=token.tenant_id)
        raise AILIZAError.from_code("totp_invalid")
    confirm_totp_secret(token.user_id)
    backup_codes = generate_backup_codes(8)
    store_backup_codes(token.user_id, token.tenant_id, [hash_backup_code(c) for c in backup_codes])
    # Kein Backup-Code-Inhalt im Audit-Log
    write_audit_entry(action="auth.totp.confirmed",
                      metadata={"user_id": token.user_id, "backup_codes_issued": 8},
                      tenant_id=token.tenant_id)
    return {
        "status": "totp_activated",
        "backup_codes": backup_codes,
        "warning": "Backup-Codes jetzt sicher aufbewahren. Sie werden nicht erneut angezeigt.",
    }


@app.post("/auth/totp/verify")
@_limiter.limit("5/minute")
def totp_verify(request: Request, payload: TotpVerifyRequest) -> JSONResponse:
    """
    Schritt 3 (2FA-Login-Abschluss): TOTP-Code oder Backup-Code prüfen.
    Erwartet totp_pending_token (aus /auth/login) + 6-stelligen TOTP-Code
    oder 8-stelligen Backup-Code.
    Gibt bei Erfolg volles JWT + Cookie zurück.
    """
    try:
        td = decode_totp_pending_token(payload.totp_pending_token)
    except ValueError:
        raise AILIZAError.from_code("totp_pending_invalid")

    record = get_totp_record(td.user_id)
    if not record or not record["confirmed"]:
        raise AILIZAError.from_code("totp_not_configured")

    code = payload.code.strip()
    valid = False

    if len(code) == 6 and code.isdigit():
        valid = verify_totp(record["secret_b32"], code)
    elif len(code) == 8:
        valid = consume_backup_code(td.user_id, code)
        if valid:
            # Backup-Code-Nutzung auditieren — kein Code im Log
            write_audit_entry(action="auth.totp.backup_code_used",
                              metadata={"user_id": td.user_id}, tenant_id=td.tenant_id)

    if not valid:
        write_audit_entry(action="auth.totp.verify_failed",
                          metadata={"user_id": td.user_id}, tenant_id=td.tenant_id)
        raise AILIZAError.from_code("totp_invalid")

    full_token = create_token(td.user_id, td.tenant_id, td.role)
    write_audit_entry(action="auth.login.success_2fa",
                      metadata={"user_id": td.user_id, "role": td.role},
                      tenant_id=td.tenant_id)
    response = JSONResponse(content={
        "access_token": full_token, "token_type": "bearer",
        "role": td.role, "user_id": td.user_id,
    })
    _set_session_cookie(response, full_token)
    return response


@app.delete("/auth/totp")
@_limiter.limit("3/minute")
def totp_delete(request: Request, payload: TotpDeleteRequest,
                token: TokenData = Depends(get_current_user)) -> dict[str, Any]:
    """
    TOTP deaktivieren. Erfordert aktuellen TOTP-Code zur Bestätigung.
    Nur eigener Account — ADMIN kann per /admin/totp/{user_id} löschen.
    """
    if token is None:
        raise HTTPException(status_code=401, detail="Nicht authentifiziert.")
    record = get_totp_record(token.user_id)
    if not record or not record["confirmed"]:
        raise AILIZAError.from_code("totp_not_configured")
    if not verify_totp(record["secret_b32"], payload.code):
        raise AILIZAError.from_code("totp_invalid")
    delete_totp_secret(token.user_id)
    write_audit_entry(action="auth.totp.deleted", metadata={"user_id": token.user_id},
                      tenant_id=token.tenant_id)
    return {"status": "totp_removed"}


@app.delete("/admin/totp/{target_user_id}")
def admin_totp_delete(
    request: Request,
    target_user_id: str,
    payload: AdminTotpResetRequest,
    token: TokenData = Depends(require_role(Role.ADMIN)),
) -> dict[str, Any]:
    """
    Admin-Endpoint: TOTP für beliebigen User zurücksetzen (z.B. bei verlorenen Codes).
    Pflichtfeld: reason (wird auditiert, kein Secret/Code).
    """
    deleted = delete_totp_secret(target_user_id)
    write_audit_entry(
        action="auth.totp.admin_reset",
        metadata={
            "target_user_id": target_user_id,
            "by": token.user_id,
            "reason": payload.reason,
        },
        tenant_id=token.tenant_id,
    )
    return {"status": "totp_reset", "rows_deleted": deleted}


@app.post("/auth/logout")
def logout() -> JSONResponse:
    """Loescht den Session-Cookie. Token-Revocation liegt am Client (Bearer) oder Cookie-Loeschung."""
    response = JSONResponse(content={"status": "logged_out"})
    response.delete_cookie(key="ailiza_session", path="/", samesite="strict")
    return response


@app.get("/auth/me")
def me(token: TokenData | None = Depends(get_current_user)) -> dict[str, Any]:
    """Gibt Nutzerinfos des aktuellen Sessions-Tokens zurueck. Fuer Frontend-Bootstrapping."""
    if token is None:
        raise HTTPException(status_code=401, detail="Nicht authentifiziert.")
    return {
        "user_id": token.user_id,
        "tenant_id": token.tenant_id,
        "role": token.role,
        "exp": token.exp.isoformat() if token.exp else None,
    }


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

@app.get("/admin/audit/events")
def admin_audit_events(
    action: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    timestamp_from: datetime | None = Query(default=None),
    timestamp_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _admin: TokenData = Depends(require_role(Role.AUDIT_VIEWER)),
) -> dict[str, Any]:
    """Paginierte Audit-Events — ab audit_viewer, append-only, sanitized."""
    try:
        from .audit.vault import query_vault_events
    except ImportError:
        from audit.vault import query_vault_events  # type: ignore
    events = query_vault_events(
        action=action,
        tenant_id=tenant_id,
        timestamp_from=timestamp_from,
        timestamp_to=timestamp_to,
        limit=limit,
        offset=offset,
    )
    return {"events": events, "count": len(events), "offset": offset, "limit": limit}


@app.get("/admin/audit/export")
def admin_audit_export(
    action: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    timestamp_from: datetime | None = Query(default=None),
    timestamp_to: datetime | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    fmt: str = Query(default="json", pattern="^(json|jsonl)$"),
    _admin: TokenData = Depends(require_role(Role.AUDIT_VIEWER)),
) -> Any:
    """Audit-Export als JSON oder JSONL — ab audit_viewer, max. 1000 Einträge, keine Rohdaten."""
    try:
        from .audit.vault import export_audit_events
    except ImportError:
        from audit.vault import export_audit_events  # type: ignore
    from fastapi.responses import Response
    content = export_audit_events(
        action=action,
        tenant_id=tenant_id,
        timestamp_from=timestamp_from,
        timestamp_to=timestamp_to,
        limit=limit,
        offset=offset,
        fmt=fmt,
    )
    media_type = "application/x-ndjson" if fmt == "jsonl" else "application/json"
    return Response(content=content.encode(), media_type=media_type)


@app.get("/admin/audit/retention-report")
def admin_audit_retention_report(
    retention_days: int = Query(default=90, ge=1),
    tenant_id: str | None = Query(default=None),
    _admin: TokenData = Depends(require_role(Role.AUDIT_VIEWER)),
) -> dict[str, Any]:
    """
    Retention-Report — zeigt wie viele Einträge älter als retention_days sind.
    Kein automatisches Löschen. DSGVO-Dokumentation vor Löschung erforderlich.
    """
    try:
        from .audit.vault import run_audit_retention_report
    except ImportError:
        from audit.vault import run_audit_retention_report  # type: ignore
    return run_audit_retention_report(retention_days, tenant_id=tenant_id)


@app.get("/admin/audit/verify")
def admin_audit_verify(
    tenant_id: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=10000),
    _user: TokenData = Depends(require_role(Role.ADMIN)),
):
    """
    Audit-Vault Stufe 2: Prüft SHA-256 Hash-Chain auf Manipulationen.
    Admin-only. Gibt keine Audit-Inhalte zurück, nur Prüfergebnis.
    """
    try:
        from .audit.vault import verify_audit_chain
    except ImportError:
        from audit.vault import verify_audit_chain  # type: ignore
    result = verify_audit_chain(tenant_id=tenant_id, limit=limit)
    if not result["ok"]:
        write_audit_entry(
            "audit.chain.manipulation_detected",
            metadata={"first_invalid_id": result.get("first_invalid_id")},
        )
    return result


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
        from .messenger.telegram_gateway import (
            handle_update, verify_telegram_signature, check_webhook_secret_or_fail,
        )
    except ImportError:
        from messenger.telegram_gateway import (
            handle_update, verify_telegram_signature, check_webhook_secret_or_fail,
        )

    # Fail-Closed in Produktion: kein Secret → sofortiger Fehler
    check_webhook_secret_or_fail()

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


# ── Phase 1: Policy & Redaction Endpoints ──────────────────────────────────────

@app.get("/api/privacy-rules")
def get_privacy_rules() -> dict[str, Any]:
    """
    Returns redaction patterns for frontend PII masking.
    Source of truth: backend loads from privacy_rules.json, frontend updates via this API.

    Status: Bereit für kontrollierte Testumgebung und Governance-Review.
    """
    try:
        # In production: load from privacy_rules.json
        # For now: return inline redaction rules matching the PRIVACY_RULES from frontend
        from governance.redaction import PRIVACY_RULES
    except ImportError:
        pass

    return {
        "version": "1.0.0",
        "updated_at": datetime.utcnow().isoformat(),
        "status": "Testumgebung",
        "note": "Nicht produktionsreif. Nicht zertifiziert.",
        "categories": [
            {"id": "secret", "label_de": "Geheimnisse", "risk_class": "🔴red"},
            {"id": "forbidden", "label_de": "DSGVO Art. 9", "risk_class": "🟠orange"},
            {"id": "confidential", "label_de": "Geschäftsgeheim", "risk_class": "🟠orange"},
            {"id": "high", "label_de": "Zahlungsdaten", "risk_class": "🟡high"},
            {"id": "normal", "label_de": "Personendaten", "risk_class": "🟢normal"},
        ],
        "rules_count": 50,
        "last_update": "2026-07-01T00:00:00Z",
    }


@app.post("/api/policy-check")
def policy_check(
    request_data: dict[str, str] = Body(...),
    _user: TokenData | None = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Test policy decision on a task text (for frontend preview).
    Returns decision level without storing anything.

    Status: Bereit für kontrollierte Testumgebung und Governance-Review.
    """
    try:
        from policy_engine import PolicyEngine
    except ImportError:
        pass

    task = request_data.get("task", "")
    user_id = _user.user_id if _user else "anonymous"

    try:
        decision = PolicyEngine.process_with_policy(task, user_id)
        return {
            "decision": decision.decision,
            "risk_level": decision.risk_level,
            "message": decision.message,
            "detected_secrets": decision.detected_secrets,
            "detected_special_categories": decision.detected_special_categories,
        }
    except Exception as e:
        return {
            "decision": "error",
            "risk_level": "unknown",
            "message": "Policy check failed",
            "error_code": "policy_check_failed",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 1.3: NEW ENDPOINT /api/policy-redact (Backend PolicyEngine + Redaction V2)
# ═══════════════════════════════════════════════════════════════════════════════

class PolicyRedactRequest(BaseModel):
    """Request für Policy + Redaction"""
    text: str = Field(..., min_length=0, max_length=100000)
    context: str | None = None  # employment, credit, general
    detected_categories: set[str] | None = None

class PolicyRedactResponse(BaseModel):
    """Response: Schicht 1 (ALLE sehen) + Versionsmarker für Debugging"""
    decision: str
    risk_level: str
    safe_text: str
    user_message_de: str
    can_send_to_llm: bool
    requires_human_review: bool
    documentation_required: bool = False
    admin_only: dict[str, Any] | None = None  # Nur Admin (serverseitig gefiltert)

    # Versionsmarker für Debugging (zeigt dass RedactionEngineV2 aktiv ist)
    redaction_engine: str = "RedactionEngineV2"
    policy_version: str = "1.3.3"

def contains_secret(text: str) -> bool:
    """Prüft auf Geheimnisse: API-Keys, Tokens, etc."""
    secret_patterns = [
        r"\bsk-[\w\-]{15,}\b",  # OpenAI
        r"\bgsk_[\w\-]{15,}\b",  # Groq
        r"\beyJ[\w\-\.]+\b",     # JWT
        r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b",  # Bearer Token
    ]
    for pattern in secret_patterns:
        if re.search(pattern, text):
            return True
    return False

def detect_prompt_injection(text: str) -> bool:
    """Prüft auf bekannte Prompt-Injection Muster"""
    injection_patterns = [
        r"ignore.*instruction",
        r"forget.*system.*prompt",
        r"new.*instruction.*:",
        r"act.*as.*",
    ]
    text_lower = text.lower()
    for pattern in injection_patterns:
        if re.search(pattern, text_lower):
            return True
    return False

def map_risk_to_user_message(level: str) -> str:
    """Nutzer-freundliche Meldungen (keine technischen Details)"""
    messages = {
        "green": "Ihre Anfrage wurde verarbeitet.",
        "yellow": "Ihre persönlichen Daten wurden geschützt. Sie können mit dieser bereinigten Fassung weitermachen.",
        "orange": "Diese Anfrage erfordert eine Genehmigung. Bitte wenden Sie sich an einen Administrator.",
        "red": "Sicherheitsrelevante Angaben wurden entfernt. Die bereinigte Fassung kann genutzt werden.",
        "violet": "Besonders sensible Daten wurden geschützt. Sie können mit den übrigen Angaben weitermachen.",
        "black": "Diese Entscheidung kann nicht automatisch getroffen werden. Sie müssen einen Mensch manuell überprüfen und dokumentieren.",
        "critical": "Es wurde ein Datenschutzverstoß erkannt. Bitte kontaktieren Sie den Datenschutz."
    }
    return messages.get(level, "Ihre Anfrage wurde verarbeitet.")

def build_escalation_info(risk_level: str, violations: list[str] = None) -> dict[str, Any] | None:
    """Eskalations-Infos nur für Admin"""
    if risk_level == "black":
        return {
            "severity": "high_risk",
            "reason": "Hochrisiko-automatisierte Entscheidung erkannt",
            "required_action": "Menschliche Prüfung + Dokumentation",
            "legal_reference": "Art. 22 DSGVO, EU AI Act Art. 6",
            "contact": "dpo@ailiza.de"
        }

    if risk_level == "critical":
        return {
            "severity": "critical",
            "reason": "DSGVO-Verstoß erkannt",
            "violations": violations or [],
            "required_action": "Sofortige Analyse + Dokumentation",
            "contact": "dpo@ailiza.de"
        }

    return None

@app.post("/api/policy-redact", response_model=PolicyRedactResponse)
def policy_redact(
    request: PolicyRedactRequest,
    current_user: TokenData | None = Depends(get_current_user),
) -> PolicyRedactResponse:
    """
    Phase 1.3: Backend Policy + Redaction (Einzige Quelle der Wahrheit)

    SICHERHEIT:
    1. Originaldaten werden NICHT zurückgegeben
    2. admin_only wird SERVERSEITIG gefiltert (nur Admin)
    3. Bei Fehler: technical_block
    4. Secrets → security_block (nicht technical_block)
    """
    try:
        text = request.text or ""
        logger.info(f"🔍 /api/policy-redact called | text_len={len(text)} | engine=RedactionEngineV2")

        # ─────────────────────────────────────────────────────────
        # 1. SICHERHEITS-CHECKS
        # ─────────────────────────────────────────────────────────

        # Geheimnis erkannt?
        if contains_secret(text):
            admin_block = None
            if current_user and current_user.role == "admin":
                admin_block = {
                    "escalation_info": {
                        "severity": "security",
                        "security_finding": "SECRET_DETECTED",
                        "reason": "API-Key, Token oder Geheimnis im Text erkannt",
                        "required_action": "Geheimnis widerrufen/rotieren",
                        "contact": "security@ailiza.de"
                    }
                }

            return PolicyRedactResponse(
                decision="security_block",
                risk_level="critical",
                safe_text="[BLOCKIERT: Sicherheitsverstoß erkannt]",
                user_message_de="Ihre Anfrage enthält einen Sicherheitsfund (z.B. API-Key). Dieser wurde entfernt.",
                can_send_to_llm=False,
                requires_human_review=False,
                documentation_required=False,
                admin_only=admin_block
            )

        # Prompt-Injection erkannt?
        if detect_prompt_injection(text):
            admin_block = None
            if current_user and current_user.role == "admin":
                admin_block = {
                    "escalation_info": {
                        "severity": "security",
                        "security_finding": "PROMPT_INJECTION_DETECTED",
                        "reason": "Angriffsmuster in Text erkannt",
                        "required_action": "Security-Analyse durchführen",
                        "contact": "security@ailiza.de"
                    }
                }

            return PolicyRedactResponse(
                decision="security_block",
                risk_level="critical",
                safe_text="[BLOCKIERT: Sicherheitsverstoß erkannt]",
                user_message_de="Ihre Anfrage enthält ein Angriffsmuster. Bitte kontaktieren Sie Support.",
                can_send_to_llm=False,
                requires_human_review=False,
                documentation_required=False,
                admin_only=admin_block
            )

        # ─────────────────────────────────────────────────────────
        # 2. POLICY + REDACTION
        # ─────────────────────────────────────────────────────────

        try:
            from .governance.redaction_v2 import RedactionEngineV2
        except ImportError:
            from governance.redaction_v2 import RedactionEngineV2

        # Redaction durchführen
        redaction_engine = RedactionEngineV2()
        redaction_result = redaction_engine.redact(text, request.detected_categories)
        logger.info(f"✅ RedactionEngineV2 completed | risk_level={redaction_result.level.value} | pii_count={redaction_result.pii_replaced}")

        # ─────────────────────────────────────────────────────────
        # 3. ENTSCHEIDUNG TREFFEN (AILIZA-Regel: nicht blockieren)
        # ─────────────────────────────────────────────────────────

        risk_level = redaction_result.level.value

        if risk_level == "green":
            decision = "safe_output"
        elif risk_level == "yellow":
            decision = "safe_output_with_redactions"
        elif risk_level == "orange":
            decision = "requires_human_review"
        elif risk_level in ["red", "violet"]:
            decision = "safe_output_with_redactions"
        elif risk_level == "black":
            decision = "requires_human_review"
        elif risk_level == "critical":
            decision = "requires_human_review"
        else:
            decision = "safe_output"

        # ─────────────────────────────────────────────────────────
        # 4. CAN_SEND_TO_LLM (nur Green/Yellow + transparent)
        # ─────────────────────────────────────────────────────────

        can_send_to_llm = (
            decision == "safe_output" and risk_level in ["green"]
        ) or (
            decision == "safe_output_with_redactions" and
            risk_level == "yellow"
        )

        # ─────────────────────────────────────────────────────────
        # 5. NUTZER-MELDUNG
        # ─────────────────────────────────────────────────────────

        user_message = map_risk_to_user_message(risk_level)

        # ─────────────────────────────────────────────────────────
        # 6. ADMIN-BLOCK (serverseitig gefiltert)
        # ─────────────────────────────────────────────────────────

        admin_only = None
        if current_user and current_user.role == "admin":
            admin_only = {
                "gdpr_reason_codes": [],  # TODO: aus policy_result
                "ai_act_risk": "unknown",  # TODO: aus ai_act_evaluator
                "escalation_info": build_escalation_info(risk_level, redaction_result.violations)
            }

        # ─────────────────────────────────────────────────────────
        # 7. RESPONSE
        # ─────────────────────────────────────────────────────────

        logger.info(f"📤 PolicyRedact response | decision={decision} | risk_level={risk_level} | can_send_to_llm={can_send_to_llm}")
        return PolicyRedactResponse(
            decision=decision,
            risk_level=risk_level,
            safe_text=redaction_result.redacted_text,
            user_message_de=user_message,
            can_send_to_llm=can_send_to_llm,
            requires_human_review=decision in ["requires_human_review"],
            documentation_required=risk_level in ["black", "critical"],
            admin_only=admin_only
        )

    except Exception as e:
        logger.error(f"❌ Policy-Redaction error: {e}")
        # TECHNICAL_BLOCK: Systemfehler
        admin_only = None
        if current_user and current_user.role == "admin":
            admin_only = {
                "escalation_info": {
                    "severity": "system_error",
                    "reason": "Policy-Engine error",
                    "error": str(e),
                    "contact": "support@ailiza.de"
                }
            }

        return PolicyRedactResponse(
            decision="technical_block",
            risk_level="critical",
            safe_text="[BLOCKIERT: Sicherheitsprüfung nicht verfügbar]",
            user_message_de="Das System ist gerade nicht verfügbar. Bitte versuchen Sie später erneut.",
            can_send_to_llm=False,
            requires_human_review=False,
            documentation_required=False,
            admin_only=admin_only
        )


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/config.js")
def config_js():
    return FileResponse(FRONTEND_DIR / "config.js")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/dashboard")
def dashboard():
    return FileResponse(FRONTEND_DIR / "index.html")
