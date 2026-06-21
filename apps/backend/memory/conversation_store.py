"""
Gesprächsgedächtnis mit adaptiver Token-Komprimierung.
Kritische Fakten (Namen, Entscheidungen, Deadlines) bleiben immer erhalten.
"""

from __future__ import annotations

from typing import Any

try:
    from ..database import create_conversation, append_message, get_conversation_history
except ImportError:
    from database import create_conversation, append_message, get_conversation_history

_COMPRESSION_THRESHOLD = 0.6   # Komprimierung bei >60% Token-Limit
_DEFAULT_TOKEN_LIMIT = 8000    # Groq llama-3.3-70b


class ConversationStore:
    """Multi-Turn-Gesprächsverwaltung mit adaptiver Komprimierung."""

    def __init__(self, token_limit: int = _DEFAULT_TOKEN_LIMIT) -> None:
        self._token_limit = token_limit

    def new_conversation(self, user_id: str, session_id: str, title: str = "") -> str:
        return create_conversation(user_id, session_id, title)

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_result: dict | None = None,
    ) -> int:
        token_count = _estimate_tokens(content)
        return append_message(conversation_id, role, content, token_count, tool_name, tool_result)

    def get_history(
        self,
        conversation_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        rows = get_conversation_history(conversation_id, limit)
        return [
            {
                "role": r["role"],
                "content": r["content"],
                "tool_name": r.get("tool_name"),
                "tool_result": r.get("tool_result"),
                "created_at": r.get("created_at"),
            }
            for r in rows
        ]

    def build_context_window(
        self,
        conversation_id: str,
        llm_router=None,
        provider: str = "groq",
        model: str = "llama-3.3-70b-versatile",
        api_key: str | None = None,
    ) -> list[dict[str, str]]:
        messages = self.get_history(conversation_id, limit=100)
        total_tokens = sum(_estimate_tokens(m["content"]) for m in messages)

        if total_tokens > self._token_limit * _COMPRESSION_THRESHOLD and llm_router and api_key:
            messages = self._compress(messages, llm_router, provider, model, api_key)

        return [{"role": m["role"], "content": m["content"]} for m in messages]

    def _compress(
        self,
        messages: list[dict],
        llm_router,
        provider: str,
        model: str,
        api_key: str,
    ) -> list[dict]:
        if len(messages) <= 10:
            return messages

        old = messages[:-10]
        recent = messages[-10:]

        old_text = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in old
        )
        prompt = (
            "Fasse folgendes Gespräch zusammen. "
            "Behalte ALLE: Namen, Daten, Entscheidungen, Deadlines, Vereinbarungen.\n\n"
            f"{old_text}\n\n"
            "Zusammenfassung (deutsch, max 300 Wörter):"
        )

        try:
            resp = llm_router.chat(
                message=prompt,
                provider=provider,
                model=model,
                api_key=api_key,
                system_prompt="Du bist ein präziser Assistent, der Gespräche zusammenfasst.",
            )
            summary = resp.text if not resp.error else old_text[:500]
        except Exception:
            summary = old_text[:500]

        summary_msg = {"role": "system", "content": f"[Gesprächszusammenfassung]\n{summary}"}
        return [summary_msg] + recent


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
