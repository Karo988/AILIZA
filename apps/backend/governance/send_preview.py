"""
Prüfbeleg für den verbindlichen Versand-Vorcheck ("Lupe").
=============================================================================
Kerninvariante:

    Kein externer Anbieter erhaelt Nutzinhalt, der nicht exakt in der zuletzt
    gueltigen, fuer diesen Nutzer, Mandanten, Zweck und Zielweg geprueften
    Versandvorschau stand.

Bisher waren Vorschau (/api/policy-redact) und Versand (/agent/run) zwei
voneinander unabhaengige Redaction-Laeufe: es gab keine Garantie, dass der
Text, den die Nutzerin geprueft und ggf. bearbeitet hat, derselbe ist, der
tatsaechlich hinausgeht. Dieses Modul stellt genau diese Bindung her.

Ein Pruefbeleg bindet:
  - user_id + tenant_id  (wer)
  - sha256 des geprueften Textes (was -- exakt, nicht "aehnlich")
  - purpose/route (wozu und wohin)

Er ist kurzlebig (TTL) und genau EINMAL verbrauchbar.

BETRIEBSGRENZE (bewusst dokumentiert, nicht verschwiegen):
Der Zustand liegt prozesslokal im RAM. Bei mehreren Worker-Prozessen oder
Instanzen wuerde ein in Prozess A ausgestellter Beleg in Prozess B nicht
gefunden -- der Versand bricht dann sicher ab (fail-closed), es entsteht
KEINE Sicherheitsluecke, aber eine Fehlbedienung. Das ist mit der bestehenden
Betriebsvorgabe vereinbar: render.yaml betreibt den Dienst bewusst mit genau
einem Worker, weil Genehmigungssperren und die Audit-Hash-Kette ebenfalls nur
prozessinterne Locks sind. Eine mehrprozessfaehige Variante braeuchte
gemeinsamen Speicher (neue Infrastruktur) und ist bewusst NICHT Teil dieses
Pakets.

Nach einem Prozessneustart sind alle Belege weg -- der naechste Versand
schlaegt fehl und die Nutzerin prueft erneut. Das ist der gewollte sichere
Abbruch, kein Raten.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
import unicodedata
from dataclasses import dataclass

# Ein Beleg ist absichtlich kurzlebig: er soll den unmittelbaren
# "geprueft -> gesendet"-Vorgang abdecken, nicht eine ganze Sitzung.
DEFAULT_TTL_SECONDS = 300

# Obergrenze gegen unbegrenztes Wachstum des Speichers, falls sehr viele
# Belege ausgestellt und nie verbraucht werden (z.B. Nutzerin prueft
# wiederholt, sendet aber nie). Aeltester Beleg faellt zuerst heraus.
MAX_ENTRIES = 10_000


class PreviewRejected(Exception):
    """Pruefbeleg ungueltig -- Versand muss abbrechen (fail-closed).

    `reason` ist ein maschinenlesbarer Kurzcode fuer das Audit (enthaelt
    niemals Inhalt), `message_de` ist der verstaendliche deutsche Text fuer
    die Nutzerin.
    """

    def __init__(self, reason: str, message_de: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.message_de = message_de


@dataclass(frozen=True)
class _Entry:
    user_id: str
    tenant_id: str
    text_hash: str
    purpose: str
    expires_at: float


def normalize_text(text: str) -> str:
    """Kanonische Form fuer den Hash-Vergleich.

    Nur soweit normalisieren, dass technisch bedeutungsgleiche Varianten
    nicht faelschlich als Manipulation gelten -- aber NICHT so weit, dass
    inhaltliche Aenderungen durchrutschen:
      - Unicode NFC (aus 'e + Kombinationsakzent' wird 'é'; der Browser
        sendet je nach Plattform unterschiedliche Formen desselben Zeichens)
      - CRLF/CR -> LF (Zeilenenden unterscheiden sich je Betriebssystem)

    Bewusst NICHT normalisiert: Gross-/Kleinschreibung, Leerzeichenfolgen,
    fuehrende/abschliessende Leerzeichen. Wer ein Wort aendert oder ein
    Leerzeichen einfuegt, hat den Text geaendert -- das MUSS die Pruefung
    ungueltig machen.
    """
    normalized = unicodedata.normalize("NFC", text)
    return normalized.replace("\r\n", "\n").replace("\r", "\n")


def hash_text(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


class SendPreviewStore:
    """Prozesslokaler Speicher fuer Pruefbelege mit atomarem Verbrauch.

    Der Verbrauch laeuft komplett innerhalb eines Locks: pruefen und
    entfernen sind eine untrennbare Operation. Ein "erst lesen, dann
    loeschen" ohne Lock waere angreifbar -- zwei gleichzeitige Requests
    koennten denselben Beleg beide als gueltig sehen und doppelt senden.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS, max_entries: int = MAX_ENTRIES) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._entries: dict[str, _Entry] = {}

    def issue(self, *, user_id: str | None, tenant_id: str, checked_text: str, purpose: str) -> str:
        """Stellt einen Beleg fuer exakt diesen geprueften Text aus."""
        preview_id = secrets.token_urlsafe(32)
        entry = _Entry(
            # Anonyme Nutzung ist erlaubt (die Vorschau verlangt keinen Login);
            # der Beleg bindet dann an den festen Pseudo-Wert, damit ein
            # angemeldeter Nutzer keinen anonymen Beleg uebernehmen kann.
            user_id=user_id or "__anonymous__",
            tenant_id=tenant_id,
            text_hash=hash_text(checked_text),
            purpose=purpose,
            expires_at=time.monotonic() + self._ttl,
        )
        with self._lock:
            self._evict_expired_locked()
            if len(self._entries) >= self._max_entries:
                oldest = min(self._entries, key=lambda key: self._entries[key].expires_at)
                del self._entries[oldest]
            self._entries[preview_id] = entry
        return preview_id

    def consume(
        self, *, preview_id: str | None, user_id: str | None, tenant_id: str, text: str, purpose: str
    ) -> None:
        """Prueft und verbraucht den Beleg. Wirft PreviewRejected, sonst nichts.

        Reihenfolge ist Absicht: Ein abgelaufener oder unbekannter Beleg wird
        in JEDEM Fall entfernt, bevor irgendeine inhaltliche Pruefung
        stattfindet -- ein fehlgeschlagener Versuch darf einen Beleg nicht
        fuer einen zweiten Versuch am Leben lassen.
        """
        if not preview_id:
            raise PreviewRejected(
                "missing",
                "Diese Nachricht wurde noch nicht geprüft. Bitte zuerst die Prüfung (Lupe) ausführen.",
            )

        with self._lock:
            self._evict_expired_locked()
            entry = self._entries.pop(preview_id, None)

        if entry is None:
            raise PreviewRejected(
                "unknown_or_expired",
                "Die Prüfung ist abgelaufen oder wurde bereits verwendet. Bitte erneut prüfen.",
            )

        expected_user = user_id or "__anonymous__"
        if not hmac.compare_digest(entry.user_id, expected_user):
            raise PreviewRejected(
                "user_mismatch",
                "Die Prüfung gehört zu einer anderen Anmeldung. Bitte erneut prüfen.",
            )

        if not hmac.compare_digest(entry.tenant_id, tenant_id):
            raise PreviewRejected(
                "tenant_mismatch",
                "Die Prüfung gehört zu einem anderen Mandanten. Bitte erneut prüfen.",
            )

        if not hmac.compare_digest(entry.purpose, purpose):
            raise PreviewRejected(
                "purpose_mismatch",
                "Die Prüfung gilt für einen anderen Zweck. Bitte erneut prüfen.",
            )

        if not hmac.compare_digest(entry.text_hash, hash_text(text)):
            raise PreviewRejected(
                "text_mismatch",
                "Der Text wurde nach der Prüfung verändert. Bitte erneut prüfen.",
            )

    def _evict_expired_locked(self) -> None:
        now = time.monotonic()
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            del self._entries[key]

    # Nur fuer Tests: erlaubt deterministisches Leeren zwischen Testfaellen.
    def _reset_for_tests(self) -> None:
        with self._lock:
            self._entries.clear()


send_preview_store = SendPreviewStore()
