"""
AILIZA — Multi-LLM Router
Unterstützt: Anthropic, OpenAI, Mistral, Groq
API-Keys werden pro Request übergeben — kein fester Key nötig.
"""

import os
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    tokens_used: int = 0
    error: Optional[str] = None


class MultiLLMRouter:
    PROVIDERS = {
        "anthropic": {
            "name": "Anthropic Claude",
            "models": ["claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-6"],
            "url": "https://api.anthropic.com/v1/messages",
        },
        "openai": {
            "name": "OpenAI",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
            "url": "https://api.openai.com/v1/chat/completions",
        },
        "mistral": {
            "name": "Mistral AI",
            "models": ["mistral-large-latest", "mistral-small-latest", "open-mistral-7b"],
            "url": "https://api.mistral.ai/v1/chat/completions",
        },
        "groq": {
            "name": "Groq",
            "models": ["llama-3.3-70b-versatile", "llama3-8b-8192", "mixtral-8x7b-32768"],
            "url": "https://api.groq.com/openai/v1/chat/completions",
        },
    }

    @staticmethod
    def _external_llm_enabled() -> bool:
        return os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "false").lower() == "true"

    def chat(
        self,
        message: str,
        provider: str,
        model: str,
        api_key: str,
        system_prompt: str = "Du bist AILIZA, ein agentische KI-Assistent für KMU-Mitarbeiter in Europa.",
        context: list = None,
    ) -> LLMResponse:
        if not self._external_llm_enabled():
            return LLMResponse(
                text="Externe LLM-Aufrufe sind deaktiviert (AILIZA_EXTERNAL_LLM_ENABLED=false).",
                model=model,
                provider=provider,
                error="external_llm_disabled",
            )

        if provider not in self.PROVIDERS:
            return LLMResponse(
                text=f"Unbekannter Anbieter: {provider}",
                model=model, provider=provider,
                error="unknown_provider"
            )

        try:
            if provider == "anthropic":
                return self._call_anthropic(message, model, api_key, system_prompt, context or [])
            else:
                return self._call_openai_compatible(message, model, api_key, system_prompt, context or [], provider)
        except Exception as e:
            return LLMResponse(
                text=f"Fehler bei {provider}: {str(e)}",
                model=model, provider=provider,
                error=str(e)
            )

    def _call_anthropic(self, message, model, api_key, system_prompt, context):
        messages = []
        for m in context[-10:]:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": message})

        payload = json.dumps({
            "model": model,
            "max_tokens": 1024,
            "system": system_prompt,
            "messages": messages,
        }).encode()

        req = urllib.request.Request(
            self.PROVIDERS["anthropic"]["url"],
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        text = data["content"][0]["text"]
        tokens = data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
        return LLMResponse(text=text, model=model, provider="anthropic", tokens_used=tokens)

    def _call_openai_compatible(self, message, model, api_key, system_prompt, context, provider):
        messages = [{"role": "system", "content": system_prompt}]
        for m in context[-10:]:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": message})

        payload = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": 1024,
        }).encode()

        req = urllib.request.Request(
            self.PROVIDERS[provider]["url"],
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        text = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return LLMResponse(text=text, model=model, provider=provider, tokens_used=tokens)

    def get_providers_list(self) -> dict:
        return {
            pid: {"name": p["name"], "models": p["models"]}
            for pid, p in self.PROVIDERS.items()
        }
