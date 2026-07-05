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
    """
    Sendet Anfragen an verschiedene LLM-Anbieter.
    API-Key wird pro Anfrage übergeben — kein fester Key in .env nötig.
    """

    PROVIDERS = {
        "anthropic": {
            "name": "Anthropic Claude",
            "models": [
                "claude-sonnet-4-6",
                "claude-haiku-4-5",
                "claude-opus-4-6",
            ],
            "url": "https://api.anthropic.com/v1/messages",
        },
        "openai": {
            "name": "OpenAI",
            "models": [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-3.5-turbo",
            ],
            "url": "https://api.openai.com/v1/chat/completions",
        },
        "mistral": {
            "name": "Mistral AI",
            "models": [
                "mistral-large-latest",
                "mistral-small-latest",
                "open-mistral-7b",
            ],
            "url": "https://api.mistral.ai/v1/chat/completions",
        },
        "groq": {
            "name": "Groq",
            "models": [
                "llama-3.3-70b-versatile",
                "llama3-8b-8192",
                "mixtral-8x7b-32768",
            ],
            "url": "https://api.groq.com/openai/v1/chat/completions",
        },
    }

    def chat(
        self,
        message: str,
        provider: str,
        model: str,
        api_key: str,
        system_prompt: str = "Du bist AILIZA, ein agentische KI-Assistent für KMU-Mitarbeiter in Europa.

ANTWORT-STIL:
- Einfache Fragen (Datum, Übersetzung, kurze Info): 1-2 Sätze, direkt und klar
- Komplexe Fragen (Analyse, Strategie, DSGVO): ausführlich, strukturiert mit Schritten
- Niemals rohe Suchergebnisse ausgeben — immer die Antwort direkt formulieren
- Sprache: Deutsch, es sei denn der Nutzer schreibt anders

AUTONOMES HANDELN:
- Aufgaben selbständig erledigen ohne nachzufragen wenn die Anfrage klar ist
- Bei unklaren Aufgaben: einmal kurz nachfragen, dann sofort ausführen
- Web-Suche automatisch nutzen wenn aktuelle Informationen nötig sind
- Ergebnisse zusammenfassen, nicht auflisten

PERSÖNLICHE DATEN (DSGVO-konform):
- Namen, Firma, Rolle und Präferenzen des Nutzers im Chat merken
- Diese Daten in Antworten personalisiert einsetzen (z.B. "Guten Tag Frau Müller")
- Keine Weitergabe an Dritte (DSGVO Art. 5)
- Auf Anfrage alles löschen (DSGVO Art. 17)

COMPLIANCE (Non-Negotiable):
- Kennzeichne dich bei jeder Antwort als KI-System (EU AI Act Art. 50)
- Bei Hochrisiko-Anfragen (Kredit, Kündigung, Diagnose): menschliche Überprüfung empfehlen
- DSGVO-Hinweise nur wenn wirklich relevant — nicht bei jeder Antwort

KANN AILIZA:
- E-Mails schreiben, überarbeiten, beantworten
- Dokumente zusammenfassen und analysieren
- Übersetzen (DE, EN, FR, ES, IT)
- Web-Suche und aktuelle Informationen zusammenfassen
- Checklisten, Protokolle, Angebote erstellen
- DSGVO-Schnellcheck für KMU-Situationen
- Termine und Aufgaben strukturieren

DARF AILIZA NICHT:
- Kreditentscheidungen treffen
- Personalentscheidungen automatisiert treffen
- Medizinische Diagnosen stellen
- Sich als Mensch ausgeben.",
        context: list = None,
    ) -> LLMResponse:
        """Sendet eine Nachricht an den gewählten LLM-Anbieter."""

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
        """Gibt alle verfügbaren Anbieter und Modelle zurück."""
        return {
            pid: {
                "name": p["name"],
                "models": p["models"],
            }
            for pid, p in self.PROVIDERS.items()
        }
