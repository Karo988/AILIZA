"""
AILIZA Groq Provider
====================
Adapter fuer die Groq OpenAI-kompatible API.
Externe Calls erfolgen ausschliesslich ueber den Orchestrator.

Modell-Auswahl:
  GROQ_MODEL env var hat Vorrang vor dem Konstruktor-Default.
  Default: llama-3.1-8b-instant (kostenlos, breite Verfügbarkeit)
  Alternatives Modell: llama-3.3-70b-versatile (nur bestimmte Pläne)

Model-Fallback bei 403:
  Wenn ein nicht-default Modell HTTP 403 erhält, wird automatisch
  llama-3.1-8b-instant als Free-Tier-Fallback versucht.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

try:
    from .base import LLMProvider
    from ..errors import AILIZAError
except ImportError:  # pragma: no cover
    from providers.base import LLMProvider
    from errors import AILIZAError


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Sicherer Default: llama-3.1-8b-instant ist im kostenlosen Plan verfügbar.
# llama-3.3-70b-versatile erfordert einen bezahlten Plan → 403 wenn nicht freigeschaltet.
_DEFAULT_MODEL = "llama-3.1-8b-instant"


def _resolve_model(requested: str) -> str:
    """GROQ_MODEL env var hat Vorrang. Danach Konstruktor-Argument."""
    return os.getenv("GROQ_MODEL", "") or requested


def _map_groq_http_error(status: int, model: str) -> tuple[str, str]:
    """
    Gibt (error_code, admin_detail) zurück.
    admin_detail ist sanitisiert — kein Key, kein PII.
    403-Hinweis ist kontextabhängig: wenn model == _DEFAULT_MODEL, kein zirkulärer Fix-Vorschlag.
    """
    if status == 401:
        return "no_api_key", "Groq: Ungültiger API-Key (HTTP 401) — GROQ_API_KEY in Render prüfen"
    if status == 403:
        if model == _DEFAULT_MODEL:
            # Free-Tier-Modell schlägt fehl → kein "setze dieses Modell"-Fix, da es schon gesetzt ist
            detail = (
                f"Groq verweigert Zugriff auf '{model}' (HTTP 403). "
                "Mögliche Ursachen: Groq-Projekt hat dieses Modell nicht freigeschaltet, "
                "API-Key fehlt Projekt-Berechtigung oder Account-Sperre. "
                "Bitte Groq-Dashboard → API Keys → Projekt-Berechtigungen prüfen."
            )
        else:
            detail = (
                f"Groq verweigert Zugriff auf '{model}' (HTTP 403). "
                "Modell nicht im aktuellen Groq-Plan verfügbar. "
                "Fix: GROQ_MODEL=llama-3.1-8b-instant in Render setzen (kostenloser Plan)."
            )
        return "provider_forbidden", detail
    if status == 404:
        return "model_not_found", f"Groq: Modell '{model}' nicht gefunden (HTTP 404)"
    if status == 429:
        return "rate_limited", "Groq: Rate-Limit oder Quota erschöpft (HTTP 429) — Groq-Dashboard prüfen"
    if status >= 500:
        return "provider_unavailable", f"Groq: Server-Fehler (HTTP {status}) — temporär nicht erreichbar"
    return "provider_error", f"Groq: Unbekannter HTTP-Fehler (HTTP {status})"


def _call_groq_once(api_key: str, model: str, messages: list[dict[str, Any]]) -> str:
    """
    Einzelner HTTP-Call gegen die Groq-API.
    Wirft AILIZAError mit sanitisiertem admin_detail in safe_alternatives.
    """
    print(f"AILIZA GROQ CALL | model={model}", flush=True)
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": 1000,
        "temperature": 0.3,
    }).encode()
    req = urllib.request.Request(
        GROQ_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            result = data["choices"][0]["message"]["content"]
            print(f"AILIZA GROQ RESULT | result=ok chars={len(result)} model={model}", flush=True)
            return result
    except urllib.error.HTTPError as exc:
        status = exc.code
        code, detail = _map_groq_http_error(status, model)
        print(f"AILIZA GROQ HTTP ERROR | status={status} code={code} model={model}", flush=True)
        raise AILIZAError.from_code(code, safe_alternatives=[detail]) from exc
    except urllib.error.URLError as exc:
        detail = f"Groq: Netzwerkfehler — Provider nicht erreichbar"
        print(f"AILIZA GROQ URL ERROR | reason={type(exc.reason).__name__} model={model}", flush=True)
        raise AILIZAError.from_code("provider_unavailable", safe_alternatives=[detail]) from exc
    except Exception as exc:  # noqa: BLE001
        detail = f"Groq: Unerwarteter Fehler ({type(exc).__name__})"
        print(f"AILIZA GROQ ERROR | type={type(exc).__name__} model={model}", flush=True)
        raise AILIZAError.from_code("provider_error", safe_alternatives=[detail]) from exc


class GroqProvider(LLMProvider):
    provider_region = "US"
    provider_profile_version = "1.0"
    provider_id = "groq"

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self.model = _resolve_model(model)

    def _api_key(self) -> str:
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise AILIZAError.from_code(
                "no_api_key",
                safe_alternatives=["Groq: GROQ_API_KEY nicht gesetzt — in Render-Env prüfen"],
            )
        return key

    @property
    def max_context_tokens(self) -> int:
        return 32768

    @property
    def supports_json_mode(self) -> bool:
        # OpenAI-kompatibler response_format={"type":"json_object"} -- nicht
        # bei allen Groq-Modellen garantiert, daher weiterhin Pfad B mit
        # lokaler Validierung (PR-2), nicht Pfad A.
        return True

    def estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        return round((tokens_in * 0.00000059) + (tokens_out * 0.00000079), 8)

    def generate(self, messages: list[dict[str, Any]], context: Any = None) -> str:
        api_key = self._api_key()
        try:
            return _call_groq_once(api_key, self.model, messages)
        except AILIZAError as exc:
            # Bei 403 (Modell nicht im Plan): automatisch Free-Tier-Fallback versuchen
            if exc.code == "provider_forbidden" and self.model != _DEFAULT_MODEL:
                print(
                    f"AILIZA GROQ FALLBACK | original_model={self.model} "
                    f"fallback_model={_DEFAULT_MODEL} reason=403_model_not_in_plan",
                    flush=True,
                )
                try:
                    return _call_groq_once(api_key, _DEFAULT_MODEL, messages)
                except AILIZAError as fallback_exc:
                    # Fallback auch fehlgeschlagen — ursprünglichen Fehler UND Fallback-Fehler melden
                    combined = (exc.safe_alternatives or []) + (fallback_exc.safe_alternatives or [])
                    raise AILIZAError.from_code(
                        fallback_exc.code,
                        safe_alternatives=combined,
                    ) from fallback_exc
            raise

    def stream(self, messages: list[dict[str, Any]], context: Any = None) -> Iterator[str]:
        yield self.generate(messages, context)
