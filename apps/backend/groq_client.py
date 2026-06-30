"""
AILIZA — Groq Client mit Compliance Context
Jede Anfrage bekommt automatisch den richtigen DSGVO + EU AI Act Kontext.
"""

import os
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

try:
    from compliance_context import ComplianceContextManager
except ImportError:
    from apps.backend.compliance_context import ComplianceContextManager


@dataclass
class ChatResponse:
    text: str
    model: str
    tokens_used: int = 0
    compliance_summary: dict = None
    error: Optional[str] = None


class GroqClientWithCompliance:
    """
    Groq API Client mit automatischem Compliance-Kontext.
    Jede Anfrage bekommt die relevanten DSGVO + EU AI Act Regeln.
    """

    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    MODELS = {
        "llama-3.3-70b-versatile": "Llama 3.3 70B (Beste Qualität)",
        "llama3-8b-8192": "Llama 3 8B (Schnellste)",
        "mixtral-8x7b-32768": "Mixtral 8x7B (Langer Kontext)",
        "gemma-7b-it": "Gemma 7B (Leichtgewichtig)",
    }

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.compliance_mgr = ComplianceContextManager()

    def chat(
        self,
        message: str,
        model: str = "llama-3.3-70b-versatile",
        context: list = None,
        additional_rules: list = None,
    ) -> ChatResponse:
        """
        Sendet eine Nachricht an Groq mit automatischem Compliance-Kontext.
        """
        if not self.api_key:
            return ChatResponse(
                text="Kein Groq API-Key konfiguriert.",
                model=model,
                error="no_api_key"
            )

        # ── Compliance-Kontext automatisch aufbauen ──────────────────────────
        system_prompt, compliance = self.compliance_mgr.build_system_prompt(
            user_message=message,
            conversation_context=context or [],
            additional_rules=additional_rules or [],
        )

        # ── Nachrichten aufbauen ─────────────────────────────────────────────
        messages = [{"role": "system", "content": system_prompt}]

        # Kontext hinzufügen (max. 10 Nachrichten — Token-Sparsamkeit)
        for m in (context or [])[-10:]:
            role = m.get("role", "user")
            if role == "ai":
                role = "assistant"
            messages.append({"role": role, "content": m.get("content", "")})

        messages.append({"role": "user", "content": message})

        # ── API-Aufruf ───────────────────────────────────────────────────────
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7,
        }).encode()

        req = urllib.request.Request(
            self.API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())

            text = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", 0)

            return ChatResponse(
                text=text,
                model=model,
                tokens_used=tokens,
                compliance_summary=self.compliance_mgr.get_compliance_summary(compliance),
            )

        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            return ChatResponse(
                text=f"Fehler: {e.code} — {error_body[:200]}",
                model=model,
                error=str(e.code)
            )
        except Exception as e:
            return ChatResponse(
                text=f"Verbindungsfehler: {str(e)}",
                model=model,
                error=str(e)
            )

    def is_configured(self) -> bool:
        return bool(self.api_key)


def run_groq_diagnosis() -> dict:
    """Beweisbasierte Groq-Diagnose — ausgelagert aus main.py (kein api.groq.com in main)."""
    import hashlib
    import json as _json
    from uuid import uuid4

    GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
    GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

    rid = uuid4().hex[:8]
    out: dict = {"request_id": rid}

    raw_key = os.getenv("GROQ_API_KEY", "")
    groq_key_present = bool(raw_key)
    groq_key_prefix = raw_key[:4] if raw_key else "(not set)"
    groq_key_fingerprint = hashlib.sha256(raw_key.encode()).hexdigest()[:12] if raw_key else "(no key)"
    groq_model_env = os.getenv("GROQ_MODEL", "(not set)")
    groq_model_effective = os.getenv("GROQ_MODEL", "") or "llama-3.1-8b-instant"

    try:
        try:
            from kill_switch import is_external_llm_enabled as _ille
        except ImportError:
            from .kill_switch import is_external_llm_enabled as _ille  # type: ignore[no-redef]
        ext_allowed = _ille()
    except Exception:
        ext_allowed = False

    out["env"] = {
        "groq_key_present": groq_key_present,
        "groq_key_prefix": groq_key_prefix,
        "groq_key_fingerprint": groq_key_fingerprint,
        "groq_model_env": groq_model_env,
        "groq_model_effective": groq_model_effective,
        "external_llm_allowed": ext_allowed,
    }

    if not groq_key_present:
        out["diagnosis"] = "groq_key_invalid"
        out["next_action_de"] = (
            "GROQ_API_KEY ist nicht gesetzt. Key im Groq-Dashboard erstellen "
            "und in Render-Umgebungsvariablen eintragen."
        )
        return out

    _HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {raw_key}"}

    # Models API
    models_api_ok = False
    models_status = None
    accessible_model_ids: list = []
    target_in_models = False
    models_error_sanitized = ""

    try:
        req = urllib.request.Request(GROQ_MODELS_URL, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            models_status = resp.getcode()
            data = _json.loads(resp.read())
            accessible_model_ids = [m["id"] for m in data.get("data", []) if isinstance(m, dict) and "id" in m]
            models_api_ok = True
            target_in_models = groq_model_effective in accessible_model_ids
    except urllib.error.HTTPError as exc:
        models_status = exc.code
        models_error_sanitized = f"HTTP {exc.code} — {exc.reason}"
    except urllib.error.URLError as exc:
        models_error_sanitized = f"Netzwerkfehler: {type(exc.reason).__name__}"
    except Exception as exc:
        models_error_sanitized = f"Unerwarteter Fehler: {type(exc).__name__}"

    out["models_api"] = {
        "models_api_status_code": models_status,
        "models_api_ok": models_api_ok,
        "accessible_model_ids": accessible_model_ids,
        "target_model_in_accessible_models": target_in_models,
        "models_api_error_sanitized": models_error_sanitized or None,
    }

    if not models_api_ok and models_status == 401:
        out["diagnosis"] = "groq_key_invalid"
        out["next_action_de"] = "Der API-Key ist ungültig (HTTP 401). Neuen Key erstellen."
        return out
    if not models_api_ok and models_status == 403:
        out["models_api_403_warning"] = "Models API 403: Chat Completions wird trotzdem getestet."

    # Chat Test
    _TEST_MESSAGES = [{"role": "user", "content": "Reply exactly: AILIZA_GROQ_OK"}]
    _TEST_PAYLOAD = _json.dumps({
        "model": groq_model_effective, "messages": _TEST_MESSAGES,
        "max_tokens": 20, "temperature": 0,
    }).encode()

    print(
        f"AILIZA GROQ DIAG | request_id={rid} "
        f"url={GROQ_CHAT_URL} model={groq_model_effective} "
        f"authorization_header_set=True content_type_set=True max_tokens=20 messages_count=1",
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
        req = urllib.request.Request(GROQ_CHAT_URL, data=_TEST_PAYLOAD, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            chat_status = resp.getcode()
            data = _json.loads(resp.read())
            response_text = (data.get("choices", [{}])[0].get("message", {}).get("content", ""))[:50]
            chat_ok = True
            raw_error_category = "ok"
    except urllib.error.HTTPError as exc:
        chat_status = exc.code
        try:
            body = _json.loads(exc.read())
            err_obj = body.get("error", {})
            groq_error_code_raw = err_obj.get("code", "")
            groq_error_type_raw = err_obj.get("type", "")
            groq_error_msg_sanitized = str(err_obj.get("message", exc.reason or ""))[:120]
        except Exception:
            groq_error_msg_sanitized = f"HTTP {exc.code} {exc.reason}"
        raw_error_category = {401: "unauthorized_key", 403: "forbidden_model_or_project",
                               404: "model_not_found", 429: "rate_limited", 400: "bad_request"}.get(exc.code, "unknown")
    except urllib.error.URLError as exc:
        groq_error_msg_sanitized = f"Netzwerkfehler: {type(exc.reason).__name__}"
        raw_error_category = "network_error"
    except Exception as exc:
        groq_error_msg_sanitized = f"Unerwarteter Fehler: {type(exc).__name__}"

    out["chat_test"] = {
        "chat_status_code": chat_status, "chat_ok": chat_ok,
        "response_text_if_ok": response_text if chat_ok else None,
        "groq_error_code": groq_error_code_raw or None,
        "groq_error_type": groq_error_type_raw or None,
        "groq_error_message_sanitized": groq_error_msg_sanitized or None,
        "raw_error_category": raw_error_category,
    }

    # Diagnose
    diagnosis = "unknown"
    next_action_de = "Keine eindeutige Diagnose — bitte alle Felder oben manuell prüfen."
    if models_api_ok and target_in_models and chat_ok:
        diagnosis = "groq_ok"
        next_action_de = "Groq funktioniert korrekt."
    elif not models_api_ok and models_status == 403 and chat_ok:
        diagnosis = "groq_ok_but_routing_issue"
        next_action_de = ("Chat OK, Models API 403. Problem liegt im AILIZA-Provider-Stack. "
                          "AILIZA-Logs für 'AILIZA LLM FAILED' prüfen.")
    elif not models_api_ok and models_status == 403 and not chat_ok:
        diagnosis = "groq_key_not_authorized_for_project"
        next_action_de = (f"403 an Models und Chat API. Neuen Key im aktiven Groq-Projekt erstellen. "
                          f"groq_key_prefix={groq_key_prefix}")
    elif models_api_ok and not target_in_models:
        diagnosis = "groq_model_not_allowed_for_key"
        next_action_de = f"Modell '{groq_model_effective}' nicht in accessible_model_ids."
    elif models_api_ok and target_in_models and not chat_ok:
        if raw_error_category == "forbidden_model_or_project":
            diagnosis = "groq_model_permission_ui_saved_but_api_still_forbidden"
            next_action_de = (f"Modell '{groq_model_effective}' in Liste, aber Chat-Completion 403. "
                              "Billing-Status prüfen oder Support-Ticket an Groq.")
        elif raw_error_category == "rate_limited":
            diagnosis = "groq_rate_limited"
            next_action_de = "Rate-Limit (429). Groq-Dashboard → Usage prüfen."
        elif raw_error_category == "unauthorized_key":
            diagnosis = "groq_key_invalid"
            next_action_de = "Chat-Completion 401. Key neu erstellen."
        elif raw_error_category == "bad_request":
            diagnosis = "groq_request_format_bug"
            next_action_de = ("Groq gibt 400 Bad Request. Request-Format in "
                              "apps/backend/providers/groq_provider.py prüfen.")
    elif raw_error_category == "rate_limited":
        diagnosis = "groq_rate_limited"
        next_action_de = "Rate-Limit (429). Groq-Dashboard → Usage prüfen."
    elif raw_error_category == "bad_request":
        diagnosis = "groq_request_format_bug"
        next_action_de = "400 Bad Request. Request-Format in groq_provider.py prüfen."
    elif raw_error_category == "unauthorized_key":
        diagnosis = "groq_key_invalid"
        next_action_de = "Chat-Completion 401. Key neu erstellen."

    if chat_ok:
        out["note"] = (
            "Direkter Groq-Chat-Test erfolgreich. "
            "Falls AILIZA-Routing trotzdem 403 zeigt, liegt das an internem Stack. "
            "Prüfe: AILIZA_EXTERNAL_LLM_ENABLED, Kill-Switch, Capability 'llm_call'."
        )

    out["diagnosis"] = diagnosis
    out["next_action_de"] = next_action_de
    out["security_note"] = (
        "Kein API-Key im Response. Nur erste 4 Zeichen + SHA256-Fingerprint."
    )
    return out
