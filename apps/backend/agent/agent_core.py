"""
AILIZA Agent Core
=================
Inspiriert von Hermes Agent Architecture.
Neu gebaut mit EU-Compliance (DSGVO + EU AI Act) von Grund auf.

EU AI Act Art. 52: Transparenzpflicht für KI-Systeme
DSGVO Art. 25: Datenschutz durch Technikgestaltung
"""

from __future__ import annotations

import uuid
import time
import logging
from typing import Any, Dict, List, Optional, Callable

from ..compliance.dsgvo import DSGVOCompliance
from ..compliance.eu_ai_act import EUAIActCompliance
from ..audit.audit_logger import AuditLogger

logger = logging.getLogger(__name__)


class AILIZAAgent:
    """
    AILIZA AI Agent — EU-konformer autonomer Agent.

    Kernprinzipien:
    - Transparenz: User wird immer informiert, dass er mit KI interagiert
    - Datensparsamkeit: Nur notwendige Daten werden verarbeitet
    - Menschliche Aufsicht: Kritische Aktionen erfordern Bestätigung
    - Audit Trail: Alle Aktionen werden protokolliert
    - Recht auf Löschung: User kann alle Daten jederzeit löschen
    """

    # EU AI Act: System-Identifikation (Art. 52 Abs. 1)
    SYSTEM_NAME = "AILIZA"
    SYSTEM_VERSION = "0.1.0"
    AI_DISCLOSURE = (
        "Sie interagieren mit AILIZA, einem KI-System. "
        "Dieses System unterliegt dem EU AI Act und der DSGVO."
    )

    def __init__(
        self,
        model: str = "",
        api_key: str = None,
        max_turns: int = 10,
        user_id: str = None,
        session_id: str = None,
        human_oversight: bool = True,
        data_retention_days: int = 90,
        stream_callback: Optional[Callable] = None,
    ):
        """
        Initialisiert den AILIZA Agent.

        Args:
            model: KI-Modell (z.B. anthropic/claude-sonnet-4-6)
            api_key: API Schlüssel
            max_turns: Maximale Anzahl an API-Aufrufen pro Konversation
            user_id: Pseudonymisierte User-ID (DSGVO Art. 4)
            session_id: Session-ID für Audit Trail
            human_oversight: Menschliche Aufsicht aktivieren (EU AI Act)
            data_retention_days: Aufbewahrungsfrist in Tagen (DSGVO)
            stream_callback: Callback für Streaming-Ausgabe
        """
        self.model = model
        self.api_key = api_key
        self.max_turns = max_turns
        self.stream_callback = stream_callback
        self.human_oversight = human_oversight

        # DSGVO: Pseudonymisierung (Art. 4 Nr. 5)
        self.user_id = user_id or self._generate_pseudonym()
        self.session_id = session_id or str(uuid.uuid4())

        # Compliance-Module
        self.dsgvo = DSGVOCompliance(
            user_id=self.user_id,
            retention_days=data_retention_days,
        )
        self.eu_ai_act = EUAIActCompliance(
            system_name=self.SYSTEM_NAME,
            version=self.SYSTEM_VERSION,
        )

        # Audit Logger (DSGVO Art. 30: Verzeichnis von Verarbeitungstätigkeiten)
        self.audit = AuditLogger(
            session_id=self.session_id,
            user_id=self.user_id,
        )

        # Konversationsverlauf
        self._messages: List[Dict[str, Any]] = []
        self._tool_registry: Dict[str, Callable] = {}

        logger.info(
            "AILIZA Agent gestartet | session=%s | user=%s",
            self.session_id,
            self.user_id,
        )

    # ── DSGVO: Pseudonymisierung ──────────────────────────────────────────

    @staticmethod
    def _generate_pseudonym() -> str:
        """Erzeugt eine pseudonymisierte User-ID (DSGVO Art. 4 Nr. 5)."""
        return f"user_{uuid.uuid4().hex[:12]}"

    # ── EU AI Act: Transparenz ────────────────────────────────────────────

    def get_ai_disclosure(self) -> str:
        """
        Gibt die KI-Offenlegungspflicht zurück (EU AI Act Art. 52 Abs. 1).
        Muss dem User beim ersten Kontakt angezeigt werden.
        """
        return self.AI_DISCLOSURE

    # ── Konversation ──────────────────────────────────────────────────────

    def chat(
        self,
        message: str,
        system_message: str = None,
    ) -> str:
        """
        Einfache Chat-Schnittstelle.

        Args:
            message: User-Nachricht
            system_message: Optionale System-Anweisung

        Returns:
            Antwort des Agenten
        """
        result = self.run_conversation(
            user_message=message,
            system_message=system_message,
        )
        return result["final_response"]

    def run_conversation(
        self,
        user_message: str,
        system_message: str = None,
        conversation_history: List[Dict[str, Any]] = None,
        task_id: str = None,
    ) -> Dict[str, Any]:
        """
        Führt eine vollständige Konversationsrunde durch.

        DSGVO Art. 5: Zweckbindung — Verarbeitung nur für definierten Zweck.
        EU AI Act: Audit Trail für alle Aktionen.
        """
        task_id = task_id or str(uuid.uuid4())
        start_time = time.time()

        # Audit: Konversation starten
        self.audit.log_conversation_start(
            task_id=task_id,
            user_message_hash=self.dsgvo.hash_content(user_message),
        )

        # DSGVO: Datensparsamkeit — nur notwendige Daten speichern
        messages = conversation_history or list(self._messages)
        messages.append({"role": "user", "content": user_message})

        try:
            response = self._run_agent_loop(
                messages=messages,
                system_message=system_message,
                task_id=task_id,
            )

            # Audit: Erfolgreiche Antwort
            self.audit.log_conversation_end(
                task_id=task_id,
                success=True,
                duration_ms=int((time.time() - start_time) * 1000),
            )

            return {
                "final_response": response,
                "session_id": self.session_id,
                "task_id": task_id,
                "user_id": self.user_id,
            }

        except Exception as e:
            self.audit.log_error(task_id=task_id, error=str(e))
            raise

    def _run_agent_loop(
        self,
        messages: List[Dict[str, Any]],
        system_message: str,
        task_id: str,
    ) -> str:
        """
        Haupt-Agent-Schleife.
        Delegiert an die konsolidierte Implementierung in conversation_loop.
        Externe LLM-Calls laufen ueber api_client -> (perspektivisch) Orchestrator.
        """
        from .conversation_loop import _agent_loop

        final_response, updated_messages = _agent_loop(
            agent=self,
            messages=messages,
            system_message=system_message,
            task_id=task_id,
            stream_callback=self.stream_callback,
        )
        self._messages = updated_messages
        return final_response

    # ── Tool Registry ─────────────────────────────────────────────────────

    def register_tool(self, name: str, func: Callable, requires_approval: bool = False) -> None:
        """
        Registriert ein Tool im Agent.

        Args:
            name: Tool-Name
            func: Tool-Funktion
            requires_approval: Ob menschliche Genehmigung erforderlich ist
                               (EU AI Act: Human-in-the-Loop)
        """
        self._tool_registry[name] = {
            "func": func,
            "requires_approval": requires_approval,
        }
        self.audit.log_tool_registered(tool_name=name, requires_approval=requires_approval)
        logger.info("Tool registriert: %s (approval=%s)", name, requires_approval)

    # ── DSGVO: Betroffenenrechte ──────────────────────────────────────────

    def delete_user_data(self) -> Dict[str, Any]:
        """
        Löscht alle Benutzerdaten (DSGVO Art. 17: Recht auf Löschung).
        """
        self._messages.clear()
        result = self.dsgvo.delete_all_user_data()
        self.audit.log_data_deletion(user_id=self.user_id)
        logger.info("Benutzerdaten gelöscht für user=%s", self.user_id)
        return result

    def export_user_data(self) -> Dict[str, Any]:
        """
        Exportiert alle Benutzerdaten (DSGVO Art. 20: Recht auf Datenübertragbarkeit).
        """
        return self.dsgvo.export_user_data(
            messages=self._messages,
            session_id=self.session_id,
        )

    def get_compliance_report(self) -> Dict[str, Any]:
        """
        Gibt einen Compliance-Bericht zurück (DSGVO + EU AI Act).
        """
        return {
            "dsgvo": self.dsgvo.get_status(),
            "eu_ai_act": self.eu_ai_act.get_status(),
            "audit_summary": self.audit.get_summary(),
        }
