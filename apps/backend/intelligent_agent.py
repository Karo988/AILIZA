"""
AILIZA — Intelligenter Agent-Loop (Phase 1).
Ersetzt regelbasierte Tool-Auswahl durch echtes LLM-Reasoning.
Bestehende AgentRuntime bleibt unverändert.
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from .agent_runtime import AgentRuntime, PlannedToolCall, plan_tool_calls, build_step, summarize_tool_result, stream_event
    from .database import write_audit_entry
    from .llm_router import MultiLLMRouter
    from .security.input_sanitizer import sanitize as sanitize_input
    from .privacy.pseudonymizer import Pseudonymizer
    from .privacy import mapping_store
except ImportError:
    from agent_runtime import AgentRuntime, PlannedToolCall, plan_tool_calls, build_step, summarize_tool_result, stream_event
    from database import write_audit_entry
    from llm_router import MultiLLMRouter
    from security.input_sanitizer import sanitize as sanitize_input
    from privacy.pseudonymizer import Pseudonymizer
    from privacy import mapping_store


_TOOL_MANIFEST = """Du hast Zugriff auf folgende Tools:

1. search(query: str) — Sucht im Web nach aktuellen Informationen. Nutze dies wenn du aktuelle Daten brauchst.
2. fetch(url: str) — Lädt den Inhalt einer Webseite. Nutze dies wenn der Nutzer eine URL nennt.

Antworte mit einem JSON-Objekt:
{"tool": "search", "parameters": {"query": "..."}}
ODER
{"tool": "fetch", "parameters": {"url": "..."}}
ODER wenn kein Tool nötig:
{"tool": null, "direct_answer": "Deine direkte Antwort hier"}
"""

_SYSTEM_PROMPT = """Du bist AILIZA, ein intelligenter KI-Assistent für KMU-Mitarbeiter in Europa.

VERHALTEN:
- Antworte immer auf Deutsch, außer der Nutzer schreibt in einer anderen Sprache
- Bei einfachen Fragen: kurz und direkt (1-3 Sätze)
- Bei komplexen Aufgaben: strukturiert und vollständig
- Du bist ein KI-System (EU AI Act Art. 52) — sage das wenn gefragt

KANNST DU:
- E-Mails schreiben, überarbeiten, beantworten
- Texte zusammenfassen und analysieren
- Übersetzen (DE, EN, FR, ES, IT)
- Aktuelles aus dem Web recherchieren
- Rechnen und Daten analysieren
- Checklisten, Protokolle, Angebote erstellen

DARF NICHT:
- Kreditentscheidungen treffen
- Personalentscheidungen automatisiert treffen
- Medizinische Diagnosen stellen
- Sich als Mensch ausgeben
"""


class IntelligentAgentRuntime(AgentRuntime):
    """
    Erweitert AgentRuntime um echtes LLM-Reasoning.
    Alle bestehenden Tests laufen weiterhin gegen AgentRuntime.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._router = MultiLLMRouter()
        self._pseudonymizer = Pseudonymizer()
        self._provider = os.getenv("AILIZA_LLM_PROVIDER", "groq")
        self._model = os.getenv("AILIZA_LLM_MODEL", "llama-3.3-70b-versatile")

    def _external_enabled(self) -> bool:
        return os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "false").lower() == "true"

    def _get_api_key(self, session_id: str | None = None) -> str | None:
        if session_id:
            try:
                from security.key_manager import get_key_manager
                key = get_key_manager().get_key(session_id, self._provider)
                if key:
                    return key
            except ImportError:
                pass
        env_map = {
            "groq": "GROQ_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "mistral": "MISTRAL_API_KEY",
        }
        return os.getenv(env_map.get(self._provider, "GROQ_API_KEY"))

    def _plan_with_llm(
        self,
        task: str,
        api_key: str,
        user_rules: str = "",
    ) -> list[PlannedToolCall] | None:
        system = _SYSTEM_PROMPT
        if user_rules:
            system += f"\n\nNUTZER-PRÄFERENZEN:\n{user_rules}"
        system += f"\n\n{_TOOL_MANIFEST}"

        response = self._router.chat(
            message=task,
            provider=self._provider,
            model=self._model,
            api_key=api_key,
            system_prompt=system,
        )

        if response.error:
            return None

        try:
            text = response.text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text.strip())
            tool = data.get("tool")
            if tool is None:
                return []
            params = data.get("parameters", {})
            return [PlannedToolCall(tool=tool, parameters=params)]
        except (json.JSONDecodeError, KeyError):
            return None

    def _synthesize_with_llm(
        self,
        task: str,
        tool_results: list[dict],
        api_key: str,
        user_rules: str = "",
    ) -> str:
        context_parts = []
        for r in tool_results:
            summary = r.get("summary", {})
            if isinstance(summary, dict):
                top = summary.get("top_results", [])
                for item in top[:3]:
                    title = item.get("title", "")
                    content = item.get("content", "")
                    if content:
                        context_parts.append(f"**{title}**\n{content}" if title else content)
                text_preview = summary.get("text_preview", "")
                if text_preview:
                    context_parts.append(text_preview)

        if not context_parts:
            return ""

        context = "\n\n".join(context_parts[:5])
        synthesis_prompt = (
            f'Frage: "{task}"\n\n'
            f"Recherche-Ergebnisse:\n{context}\n\n"
            f"Formuliere eine klare, direkte Antwort auf Deutsch. "
            f"Fasse zusammen, liste nicht auf. Maximal 3 Absätze."
        )

        system = _SYSTEM_PROMPT
        if user_rules:
            system += f"\n\nNUTZER-PRÄFERENZEN:\n{user_rules}"

        response = self._router.chat(
            message=synthesis_prompt,
            provider=self._provider,
            model=self._model,
            api_key=api_key,
            system_prompt=system,
        )
        return response.text if not response.error else ""

    def _direct_llm_answer(
        self,
        task: str,
        api_key: str,
        conversation_history: list[dict] | None = None,
        user_rules: str = "",
    ) -> str:
        system = _SYSTEM_PROMPT
        if user_rules:
            system += f"\n\nNUTZER-PRÄFERENZEN:\n{user_rules}"

        response = self._router.chat(
            message=task,
            provider=self._provider,
            model=self._model,
            api_key=api_key,
            system_prompt=system,
            context=conversation_history or [],
        )
        return response.text if not response.error else ""

    def run(
        self,
        task: str,
        session_id: str | None = None,
        conversation_history: list[dict] | None = None,
        user_rules: str = "",
    ) -> dict[str, Any]:
        from uuid import uuid4

        # 1. Injection-Prüfung
        sanitize_result = sanitize_input(task)
        if sanitize_result.found_patterns:
            write_audit_entry("security.injection_attempt", {
                "patterns": sanitize_result.found_patterns,
                "is_high_risk": sanitize_result.is_high_risk,
            })

        # 2. Pseudonymisierung
        anon_result = self._pseudonymizer.anonymize(task)
        anon_task = anon_result.text
        pii_mapping = anon_result.mapping

        if pii_mapping and session_id:
            conv_id = str(uuid4())
            mapping_store.save(session_id, conv_id, pii_mapping)

        # 3. LLM-Modus oder Fallback
        if not self._external_enabled():
            result = super().run(anon_task)
            if pii_mapping:
                result["message"] = self._pseudonymizer.deanonymize(
                    result.get("message", ""), pii_mapping
                )
                result["ai_response"] = result["message"]
                result["pii_detected"] = self._pseudonymizer.get_consent_request(anon_result) if anon_result.has_pii else {}
            return result

        api_key = self._get_api_key(session_id)
        if not api_key:
            result = super().run(anon_task)
            result["warning"] = "Kein API-Key konfiguriert — Basis-Modus aktiv"
            return result

        # 4. Tool-Planung per LLM
        planned = self._plan_with_llm(anon_task, api_key, user_rules)

        if planned is None:
            planned = plan_tool_calls(anon_task)

        if not planned:
            answer = self._direct_llm_answer(anon_task, api_key, conversation_history, user_rules)
            answer = self._pseudonymizer.deanonymize(answer, pii_mapping)
            return {
                "status": "completed",
                "message": answer,
                "ai_response": answer,
                "steps": [],
                "results": [],
                "pii_detected": self._pseudonymizer.get_consent_request(anon_result) if anon_result.has_pii else {},
            }

        # 5. Tools ausführen
        run_id = str(uuid4())
        self.create_run_record(run_id, task)
        write_audit_entry("agent.run.intelligent", {
            "run_id": run_id,
            "planned_tools": [p.tool for p in planned],
            "pii_detected": list(anon_result.detected.keys()),
        })

        steps: list[dict] = []
        results: list[dict] = []

        for index, call in enumerate(planned, start=1):
            try:
                response = self.tool_executor(call.tool, call.parameters)
            except Exception as exc:
                self.update_run_record(run_id, status="failed", result={"detail": str(exc)})
                return {"status": "failed", "message": str(exc), "run_id": run_id}

            step = build_step(index, call, response)
            steps.append(step)

            if response.get("status") == "pending":
                return {
                    "run_id": run_id,
                    "status": "pending_approval",
                    "message": response.get("message", "Genehmigung erforderlich"),
                    "approval_id": response.get("approval_id"),
                    "steps": steps,
                }

            results.append({
                "tool": call.tool,
                "parameters": call.parameters,
                "summary": summarize_tool_result(call.tool, response.get("result")),
                "result": response.get("result"),
            })

        # 6. Synthese per LLM
        answer = self._synthesize_with_llm(anon_task, results, api_key, user_rules)
        if not answer:
            answer = self._direct_llm_answer(anon_task, api_key, conversation_history, user_rules)

        # 7. De-Pseudonymisierung
        answer = self._pseudonymizer.deanonymize(answer, pii_mapping)

        final = {
            "run_id": run_id,
            "status": "completed",
            "message": answer,
            "ai_response": answer,
            "steps": steps,
            "results": results,
            "pii_detected": self._pseudonymizer.get_consent_request(anon_result) if anon_result.has_pii else {},
        }
        self.update_run_record(run_id, status="completed", result=final)
        write_audit_entry("agent.run.completed", {"run_id": run_id, "intelligent": True})
        return final
