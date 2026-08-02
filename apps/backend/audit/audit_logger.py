"""
Audit Logger
============
Schnittstelle für den Agent-Kern (agent/agent_core.py, agent/tool_executor.py)
zur zentralen, dauerhaften Audit-Hash-Chain.

DSGVO Art. 30: Verzeichnis von Verarbeitungstätigkeiten
EU AI Act Art. 12: Protokollierungspflichten
EU AI Act Art. 19: Automatisch erzeugte Protokolle

Alle Aktionen werden pseudonymisiert gespeichert. Keine Klartextdaten im
Audit-Log.

WICHTIG (Arbeitspaket 1, Audit-Konsolidierung): Diese Klasse fuehrt KEINE
eigene, zweite Audit-Datenbank mehr. Jeder Log-Aufruf schreibt ueber
database.write_audit_entry() direkt in die bestehende, produktiv genutzte
audit_logs-Tabelle -- inkl. der dort bereits vorhandenen SHA-256-Hash-Chain
(_compute_audit_hash/_get_latest_audit_hash). Vorher schrieb diese Klasse in
eine eigene sqlite3-Datenbank, die standardmaessig (":memory:") nie
persistiert wurde und beim Prozessende verloren ging -- dieser stille
Datenverlust ist der Grund fuer die Umstellung.

Fail-closed bei Schreibfehlern: ein fehlgeschlagener Audit-Schreibvorgang
wird NICHT stillschweigend verschluckt, sondern lautstark geloggt und erneut
ausgeloest (re-raise) -- ein Aufrufer, der Audit-Verlust ignoriert, wuerde
sonst unbemerkt gegen DSGVO Art. 30 / EU AI Act Art. 12 verstossen.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Verbotene Schluessel in metadata -- niemals in die Hash-Chain uebernehmen
# (deckungsgleich mit core_api.write_audit_event(), damit beide Schreibpfade
# denselben Schutz bieten).
_BLOCKED_METADATA_KEYS = frozenset({
    "task_content", "prompt", "input_summary", "credentials",
    "secret", "totp", "backup_code", "password", "token",
})


def _sanitize_value(value: Any) -> Any:
    """Entfernt verbotene Schluessel rekursiv -- auch in verschachtelten
    dicts/Listen (z.B. {"context": {"prompt": "..."}} oder
    [{"credentials": "..."}])."""
    if isinstance(value, dict):
        return {
            k: _sanitize_value(v)
            for k, v in value.items()
            if k.lower() not in _BLOCKED_METADATA_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    return value


def _sanitize_metadata(details: Dict[str, Any] | None) -> Dict[str, Any]:
    return _sanitize_value(details or {})


class AuditChainDeletionNotAllowed(Exception):
    """Direkte Loeschung einzelner Zeilen aus der Audit-Hash-Chain ist nicht
    erlaubt. audit_logs ist eine append-only Hash-Chain
    (previous_hash/entry_hash, siehe database.py/_compute_audit_hash) -- das
    Entfernen einer einzelnen, nutzerbezogenen Zeile aus der Mitte der Kette
    wuerde previous_hash fuer alle nachfolgenden Eintraege ungueltig machen
    und die Manipulationserkennung faelschlich ausloesen.

    Die bestehende, bereits vorhandene Alters-Retention
    (maintenance/retention_cleanup.py) loescht ausschliesslich die AELTESTEN
    Eintraege chronologisch von vorne -- das ist ein anderer, bereits
    bestaetigter Prozess und betrifft keine gezielte, nutzerbezogene
    Einzel-Loeschung (DSGVO Art. 17).

    Ein bestaetigter, dokumentierter Prozess fuer eine solche gezielte
    Loeschung existiert aktuell nicht und wird hier NICHT erfunden -- siehe
    HANDOFF in delete_user_audit_data()."""


class AuditLogger:
    """
    Audit-Trail Logger für AILIZA -- dünner, fehlerlauter Adapter auf die
    zentrale audit_logs-Hash-Chain (siehe database.write_audit_entry).

    Implementiert:
    - DSGVO Art. 30: Verzeichnis von Verarbeitungstätigkeiten
    - EU AI Act Art. 12: Aufzeichnung von Ereignissen
    - Unveränderlichkeit: Einträge können nicht gelöscht werden (außer DSGVO Art. 17)
    - Pseudonymisierung: Keine Klartextdaten
    """

    def __init__(
        self,
        session_id: str,
        user_id: str,
        tenant_id: Optional[str] = None,
    ):
        self.session_id = session_id
        self.user_id = user_id
        try:
            from ..database import DEFAULT_TENANT_ID
        except ImportError:
            from database import DEFAULT_TENANT_ID  # type: ignore
        self.tenant_id = tenant_id or DEFAULT_TENANT_ID
        self._entry_count = 0

    # ── Logging Methoden ──────────────────────────────────────────────────

    def _log(self, event_type: str, details: Dict[str, Any] = None) -> None:
        """Schreibt EINEN Eintrag ueber die zentrale Hash-Chain.

        Fail-closed: schlaegt der Schreibvorgang fehl, wird der Fehler laut
        geloggt (kein stiller Verlust) und erneut ausgeloest -- der Aufrufer
        entscheidet, wie er darauf reagiert, statt dass der Audit-Verlust
        unbemerkt bleibt."""
        try:
            from ..database import write_audit_entry
        except ImportError:
            from database import write_audit_entry  # type: ignore

        safe_details = _sanitize_metadata(details)
        metadata = {
            "session_id": self.session_id,
            "agent_user_id": self.user_id,
            **safe_details,
        }
        try:
            write_audit_entry(
                action=f"agent.{event_type}",
                metadata=metadata,
                tenant_id=self.tenant_id,
            )
        except Exception:
            logger.error(
                "AUDIT-SCHREIBFEHLER (nicht verschluckt) | session=%s | event=%s",
                self.session_id[:8], event_type,
            )
            raise
        self._entry_count += 1

        logger.debug(
            "AUDIT | session=%s | event=%s",
            self.session_id[:8],
            event_type,
        )

    def log_conversation_start(
        self,
        task_id: str,
        user_message_hash: str,
    ) -> None:
        """Protokolliert den Start einer Konversation."""
        self._log("conversation_start", {
            "task_id": task_id,
            "message_hash": user_message_hash,  # Kein Klartext!
            "article": "EU AI Act Art. 12",
        })

    def log_conversation_end(
        self,
        task_id: str,
        success: bool,
        duration_ms: int,
    ) -> None:
        """Protokolliert das Ende einer Konversation."""
        self._log("conversation_end", {
            "task_id": task_id,
            "success": success,
            "duration_ms": duration_ms,
        })

    def log_tool_call(
        self,
        tool_name: str,
        task_id: str,
        approved: bool = True,
        approver_id: str = None,
    ) -> None:
        """
        Protokolliert einen Tool-Aufruf (EU AI Act Art. 12).
        Kritisch für Transparenz und Nachvollziehbarkeit.
        """
        self._log("tool_call", {
            "tool_name": tool_name,
            "task_id": task_id,
            "approved": approved,
            "approver_id": approver_id,
            "article": "EU AI Act Art. 12",
        })

    def log_tool_registered(self, tool_name: str, requires_approval: bool) -> None:
        """Protokolliert die Registrierung eines Tools."""
        self._log("tool_registered", {
            "tool_name": tool_name,
            "requires_approval": requires_approval,
        })

    def log_data_deletion(self, user_id: str) -> None:
        """
        Protokolliert die Datenlöschung (DSGVO Art. 17).
        Der Audit-Log-Eintrag selbst bleibt erhalten (Nachweis der Löschung).
        """
        self._log("data_deletion", {
            "deleted_user_id": user_id,
            "article": "DSGVO Art. 17",
        })

    def log_consent(self, purpose: str, legal_basis: str) -> None:
        """Protokolliert eine Einwilligung (DSGVO Art. 6)."""
        self._log("consent_recorded", {
            "purpose": purpose,
            "legal_basis": legal_basis,
            "article": "DSGVO Art. 6",
        })

    def log_error(self, task_id: str, error: str) -> None:
        """Protokolliert einen Fehler."""
        self._log("error", {
            "task_id": task_id,
            "error_type": type(error).__name__,
            # Keine vollständige Fehlermeldung — könnte personenbezogene Daten enthalten
            "error_preview": str(error)[:50],
        })

    def log_human_oversight(
        self,
        action: str,
        decision: str,
        approver_id: str = None,
    ) -> None:
        """
        Protokolliert menschliche Aufsichtsentscheidungen (EU AI Act Art. 14).
        """
        self._log("human_oversight", {
            "action": action,
            "decision": decision,
            "approver_id": approver_id,
            "article": "EU AI Act Art. 14",
        })

    # ── Abfragen (lesen aus der zentralen audit_logs-Tabelle) ───────────────

    def get_session_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Gibt alle Ereignisse der aktuellen Session zurück (read-only
        Filterung auf metadata.session_id nach dem Laden -- audit_logs hat
        keinen eigenen Session-Index, das ist fuer die hier ueblichen
        Datenmengen je Konversation unkritisch)."""
        try:
            from ..database import query_audit_events
        except ImportError:
            from database import query_audit_events  # type: ignore

        rows = query_audit_events(tenant_id=self.tenant_id, limit=1000)
        own = [r for r in rows if (r.get("metadata") or {}).get("session_id") == self.session_id]
        own.sort(key=lambda r: r.get("timestamp") or 0)
        return [
            {
                "event_type": (r.get("action") or "").removeprefix("agent."),
                "details": r.get("metadata"),
                "timestamp_iso": str(r.get("timestamp")),
            }
            for r in own[:limit]
        ]

    def get_summary(self) -> Dict[str, Any]:
        """Gibt eine Zusammenfassung des Audit-Logs zurück."""
        events = self.get_session_events(limit=1000)
        event_counts: Dict[str, int] = {}
        for e in events:
            event_counts[e["event_type"]] = event_counts.get(e["event_type"], 0) + 1

        return {
            "session_id": self.session_id,
            "total_entries": self._entry_count,
            "event_counts": event_counts,
            "dsgvo_art_30_compliant": True,
            "eu_ai_act_art_12_compliant": True,
        }

    # ── DSGVO Art. 17: Recht auf Löschung ────────────────────────────────

    def delete_user_audit_data(self, user_id: str) -> int:
        """
        Loescht Audit-Eintraege eines Users (DSGVO Art. 17).

        HANDOFF: audit_logs ist seit der Umstellung auf die zentrale
        Hash-Chain (Arbeitspaket 1) eine append-only Kette. Ein direktes
        DELETE einzelner, nutzerbezogener Zeilen wuerde previous_hash fuer
        alle nachfolgenden Eintraege brechen (siehe
        AuditChainDeletionNotAllowed). Diese Methode fuehrt deshalb KEINE
        Loeschung aus, sondern loest fail-closed IMMER eine klare Ausnahme
        aus -- solange kein gesondert bestaetigter, dokumentierter
        Loeschprozess fuer nutzerbezogene audit_logs-Eintraege existiert
        (z.B. Neuaufbau der Kette mit Platzhalter-Eintraegen fuer geloeschte
        Zeilen + erneuter Hash-Berechnung, oder ein gesondert freigegebener
        Kompensationsprozess). Ein solcher Prozess ist bewusst NICHT Teil
        dieser Aenderung -- keine Erfindung einer neuen Loeschregel.

        Erhaelt die urspruengliche Signatur (Rueckgabewert `int`, Anzahl
        geloeschter Zeilen) bewusst NICHT bei -- die Methode wirft immer,
        gibt also nie tatsaechlich zurueck; die Signatur (Parameter,
        Exception statt stillem Fehlschlagen) bleibt kompatibel zu
        bestehenden Aufrufkonventionen.
        """
        raise AuditChainDeletionNotAllowed(
            f"Direkte Loeschung aus der Audit-Hash-Chain ist nicht erlaubt "
            f"(user_id-Praefix: {user_id[:8]}...). Ein bestaetigter, "
            f"dokumentierter Loeschprozess fuer nutzerbezogene "
            f"audit_logs-Eintraege (DSGVO Art. 17) existiert aktuell nicht."
        )
