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

from compliance_context import ComplianceContextManager


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
