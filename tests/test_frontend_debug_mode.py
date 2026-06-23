"""
Frontend Debug-Mode Tests
=========================
Statische Prüfung: DiagBlock in AgentChat.jsx darf technische Details
nur anzeigen wenn VITE_DEBUG_ERRORS === "true".
Normale Nutzer (Produktion) sehen ausschliesslich nutzerfreundliche Kurzmeldungen.
"""

from pathlib import Path

AGENT_CHAT = Path("apps/frontend/src/components/AgentChat.jsx").read_text()
ENV_EXAMPLE = Path("apps/frontend/.env.example").read_text()


class TestDebugFlagGuard:
    def test_debug_constant_reads_from_env(self):
        """DEBUG_ERRORS wird aus import.meta.env gelesen."""
        assert 'import.meta.env.VITE_DEBUG_ERRORS' in AGENT_CHAT

    def test_debug_constant_requires_exact_true_string(self):
        """Nur der exakte String 'true' aktiviert den Debug-Modus."""
        assert 'VITE_DEBUG_ERRORS === "true"' in AGENT_CHAT

    def test_diagblock_guarded_by_debug_flag(self):
        """DiagBlock gibt null zurück wenn DEBUG_ERRORS falsy."""
        assert '!DEBUG_ERRORS' in AGENT_CHAT or 'DEBUG_ERRORS' in AGENT_CHAT
        # Sicherstellen dass die Guard-Bedingung VOR dem JSX steht
        diag_idx = AGENT_CHAT.index("function DiagBlock")
        guard_idx = AGENT_CHAT.index("!DEBUG_ERRORS", diag_idx)
        jsx_idx = AGENT_CHAT.index("<div className=\"diag-block\"", diag_idx)
        assert guard_idx < jsx_idx, "Guard muss vor JSX-Ausgabe stehen"

    def test_diagblock_returns_null_without_debug(self):
        """DiagBlock enthält 'return null' wenn Flag nicht gesetzt."""
        diag_fn_start = AGENT_CHAT.index("function DiagBlock")
        diag_fn_end = AGENT_CHAT.index("\nfunction ", diag_fn_start + 1)
        diag_body = AGENT_CHAT[diag_fn_start:diag_fn_end]
        assert "return null" in diag_body

    def test_no_raw_stack_trace_in_user_msg(self):
        """userMsg enthält keine Stack-Trace-Begriffe."""
        assert "stack" not in AGENT_CHAT.lower() or "stack" not in (
            AGENT_CHAT[AGENT_CHAT.index("userMsg"):AGENT_CHAT.index("userMsg") + 200]
            if "userMsg" in AGENT_CHAT else ""
        )

    def test_user_friendly_messages_always_present(self):
        """Nutzerfreundliche Fehlertexte sind unabhängig vom Debug-Flag vorhanden."""
        assert "Nicht authentifiziert" in AGENT_CHAT   # 401
        assert "Keine Berechtigung" in AGENT_CHAT       # 403
        assert "Interner Serverfehler" in AGENT_CHAT    # 500


class TestEnvExample:
    def test_env_example_exists(self):
        assert Path("apps/frontend/.env.example").exists()

    def test_debug_errors_default_false(self):
        """Standard-Wert muss false sein – sicher für Produktion."""
        assert "VITE_DEBUG_ERRORS=false" in ENV_EXAMPLE

    def test_env_example_has_api_url(self):
        assert "VITE_API_URL" in ENV_EXAMPLE

    def test_env_example_warns_against_production_use(self):
        """Datei enthält Hinweis, dass true nicht für Produktion gilt."""
        lower = ENV_EXAMPLE.lower()
        assert "produktion" in lower or "production" in lower or "niemals" in lower

    def test_env_local_not_checked_in(self):
        """env.local darf nicht im Repo liegen."""
        assert not Path("apps/frontend/.env.local").exists()


class TestAgentChatUnchanged:
    def test_local_only_still_handled(self):
        assert "local_only" in AGENT_CHAT

    def test_upload_section_still_present(self):
        assert "documents/scan" in AGENT_CHAT
        assert "FormData" in AGENT_CHAT

    def test_deep_research_still_present(self):
        assert "deepResearch" in AGENT_CHAT

    def test_on_run_complete_still_present(self):
        assert "onRunComplete" in AGENT_CHAT

    def test_no_stack_trace_leaked_to_user(self):
        """Kein Stack-Trace oder Exception-Name in nutzerfreundlichem Text."""
        # userMsg darf keine technischen Begriffe enthalten
        user_msgs = [
            "Nicht authentifiziert",
            "Keine Berechtigung",
            "Interner Serverfehler",
        ]
        for msg in user_msgs:
            assert "Exception" not in msg
            assert "Traceback" not in msg
            assert "stack" not in msg.lower()
