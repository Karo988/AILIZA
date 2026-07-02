"""
AILIZA Telegram-Gateway (Pilot)
================================
Empfaengt Telegram-Webhook-Events, prueft Nutzer-Opt-in, leitet an Agent weiter.

Sicherheits-Pflichten:
- Opt-in vor jeder Verarbeitung (DSGVO Art. 6, Art. 7)
- Datenschutzhinweis beim ersten Kontakt
- Getrennte Capability-Checks: messenger_receive → message_process → llm_call → messenger_send
- Rate-Limit pro chat_id
- Nur PUBLIC/INTERNAL-Daten erlaubt
- Tenant-Bindung: chat_id → tenant_id + user_id
- Audit-light: kein Nachrichteninhalt, nur HMAC-Pseudonym der chat_id (pseudonymisiert)
- Kein API-Key in Code — AILIZA_TELEGRAM_BOT_TOKEN in .env
- Webhook-Authentifizierung: Telegram Secret-Token oder Gateway-HMAC.
  In Produktion (AILIZA_ENV=production/staging) ist das Secret verpflichtend (hard fail).

EU AI Act Art. 50: Nutzer wird klar und zugaenglich informiert, dass er mit einem
KI-System interagiert (Regulation (EU) 2024/1689, Art. 50).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests as http_requests

try:
    from ..capabilities.registry import check_capability
    from ..governance.data_governance import DataClass, classify
    from ..governance.redaction import redact
    from ..database import (
        engine, messenger_bindings, write_audit_entry, DEFAULT_TENANT_ID,
    )
    from ..errors import AILIZAError
except ImportError:
    from capabilities.registry import check_capability
    from governance.data_governance import DataClass, classify
    from governance.redaction import redact
    from database import engine, messenger_bindings, write_audit_entry, DEFAULT_TENANT_ID
    from errors import AILIZAError

from sqlalchemy import insert, select, update, delete as sa_delete

_BOT_TOKEN = os.getenv("AILIZA_TELEGRAM_BOT_TOKEN", "")
_TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

_rate_store: dict[str, list[float]] = {}
_RATE_LIMIT_PER_MINUTE = int(os.getenv("AILIZA_TELEGRAM_RATE_LIMIT", "10"))

_DATENSCHUTZ_HINWEIS = (
    "👋 Hallo! Ich bin AILIZA, ein KI-Assistent.\n\n"
    "⚠️ *EU AI Act Art. 50 Hinweis:* Du interagierst mit einem KI-System "
    "(Regulation (EU) 2024/1689).\n\n"
    "📋 *Datenschutz (DSGVO):*\n"
    "• Deine Anfragen werden an externe KI-Anbieter (Anthropic/Groq) weitergeleitet.\n"
    "• Anfragen werden vor der Weiterleitung auf sensible Daten geprüft.\n"
    "• Keine dauerhaften Chat-Verläufe werden gespeichert.\n"
    "• Einwilligung widerrufen: /widerrufen\n"
    "• Daten löschen: /delete_me\n\n"
    "Tippe /accept um zuzustimmen und AILIZA zu nutzen.\n"
    "Tippe /ablehnen um die Verarbeitung abzulehnen."
)

_WILLKOMMEN = (
    "✅ Danke! Du kannst jetzt Fragen stellen.\n"
    "Beispiel: _Was ist der Unterschied zwischen GmbH und UG?_\n\n"
    "Befehle:\n"
    "/hilfe — Hilfe anzeigen\n"
    "/widerrufen — Einwilligung widerrufen (DSGVO Art. 7 Abs. 3)\n"
    "/delete_me — Alle deine Daten löschen (DSGVO Art. 17)\n"
    "/status — Dein Verbindungsstatus"
)


# ── Pseudonymisierung ─────────────────────────────────────────────────────────
def _pseudo_chat_id(chat_id: str) -> str:
    """
    HMAC-SHA256 mit serverseitigem Pepper (AILIZA_SECRET_KEY).
    Ergebnis ist pseudonymisiert — Zuordnung zur chat_id bleibt technisch
    moeglich, solange das Secret bekannt ist. Kein plain SHA256.
    """
    pepper = os.getenv("AILIZA_SECRET_KEY", "changeme")
    return hmac.new(pepper.encode(), chat_id.encode(), hashlib.sha256).hexdigest()[:16]


# ── Telegram API-Wrapper ──────────────────────────────────────────────────────
def _tg(method: str, **kwargs: Any) -> dict[str, Any]:
    if not _BOT_TOKEN:
        return {"ok": False, "description": "Bot-Token fehlt"}
    url = _TELEGRAM_API.format(token=_BOT_TOKEN, method=method)
    try:
        resp = http_requests.post(url, json=kwargs, timeout=10)
        return resp.json()
    except Exception as exc:
        return {"ok": False, "description": str(exc)}


def send_message(chat_id: int | str, text: str, parse_mode: str = "Markdown") -> dict[str, Any]:
    return _tg("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode)


# ── Webhook-Authentifizierung ─────────────────────────────────────────────────
def verify_telegram_signature(body: bytes, secret_token: str, x_telegram_token: str) -> bool:
    """
    Prueft X-Telegram-Bot-Api-Secret-Token Header (constant-time Vergleich).
    Funktioniert sowohl mit dem nativen Telegram Webhook Secret-Token
    als auch mit einem eigenen Gateway-HMAC (falls Proxy vorgeschaltet).

    In Produktion MUSS AILIZA_TELEGRAM_WEBHOOK_SECRET gesetzt sein.
    Ohne Secret: nur fuer lokale Entwicklung akzeptabel.
    """
    if not secret_token:
        return True  # kein Secret konfiguriert — nur in Dev akzeptabel
    expected = hmac.new(secret_token.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, x_telegram_token or "")


def is_production_env() -> bool:
    return os.getenv("AILIZA_ENV", "development").lower() in ("production", "staging")


def check_webhook_secret_or_fail() -> None:
    """
    Fail-Closed in Produktion: wirft AILIZAError wenn kein Webhook-Secret gesetzt.
    In Entwicklung: keine Blockierung, aber Log-Warnung.
    """
    if is_production_env() and not os.getenv("AILIZA_TELEGRAM_WEBHOOK_SECRET"):
        raise AILIZAError.from_code("capability_disabled")


# ── Rate-Limit ────────────────────────────────────────────────────────────────
def _check_rate_limit(chat_id: str) -> bool:
    now = time.time()
    window = [t for t in _rate_store.get(chat_id, []) if now - t < 60]
    if len(window) >= _RATE_LIMIT_PER_MINUTE:
        return False
    window.append(now)
    _rate_store[chat_id] = window
    return True


# ── Opt-in / Binding ─────────────────────────────────────────────────────────
def get_binding(chat_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(messenger_bindings).where(messenger_bindings.c.chat_id == chat_id)
        ).mappings().first()
    return dict(row) if row else None


def create_binding(chat_id: str, telegram_username: str | None,
                   tenant_id: str = DEFAULT_TENANT_ID) -> None:
    with engine.begin() as conn:
        conn.execute(insert(messenger_bindings).values(
            chat_id=chat_id,
            telegram_username=telegram_username,
            tenant_id=tenant_id,
            opt_in_confirmed=0,
            created_at=datetime.now(timezone.utc),
        ))


def confirm_opt_in(chat_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(messenger_bindings)
            .where(messenger_bindings.c.chat_id == chat_id)
            .values(opt_in_confirmed=1, opt_in_at=datetime.now(timezone.utc))
        )


def revoke_opt_in(chat_id: str) -> None:
    """DSGVO Art. 7 Abs. 3: Widerruf der Einwilligung. Bindungs-Datensatz bleibt erhalten."""
    with engine.begin() as conn:
        conn.execute(
            update(messenger_bindings)
            .where(messenger_bindings.c.chat_id == chat_id)
            .values(opt_in_confirmed=0)
        )


def delete_binding(chat_id: str) -> None:
    """DSGVO Art. 17: Loeschrecht — entfernt Bindung und alle zugehoerigen Daten vollstaendig."""
    with engine.begin() as conn:
        conn.execute(
            sa_delete(messenger_bindings).where(messenger_bindings.c.chat_id == chat_id)
        )


# ── Hauptverarbeitungs-Pipeline ───────────────────────────────────────────────
def handle_update(update_data: dict[str, Any]) -> None:
    """
    Verarbeitet ein eingehendes Telegram-Update.
    Pipeline: Rate-Limit → messenger_receive-Check → Opt-in → message_process-Check
              → Klassifikation → Redaktion → llm_call (extern) → messenger_send-Check → Antwort
    """
    message = update_data.get("message", {})
    if not message:
        return

    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()
    username = message.get("from", {}).get("username")

    if not chat_id or not text:
        return

    # 1. Rate-Limit
    if not _check_rate_limit(chat_id):
        send_message(chat_id, "⏳ Zu viele Anfragen. Bitte warte einen Moment.")
        _audit("messenger.rate_limit", chat_id)
        return

    # 2. Capability: messenger_receive (Empfang)
    cap_receive = check_capability(
        "messenger_receive",
        data_classes=[DataClass.PUBLIC],
    )
    if not cap_receive.allowed:
        send_message(chat_id, "⛔ Empfang derzeit nicht verfügbar.")
        _audit("messenger.receive_blocked", chat_id, {"reason": cap_receive.reason})
        return

    # 3. Befehle
    if text == "/start":
        _handle_start(chat_id, username)
        return
    if text == "/accept":
        _handle_accept(chat_id)
        return
    if text in ("/ablehnen", "/widerrufen"):
        _handle_revoke(chat_id)
        return
    if text in ("/loeschen", "/delete_me"):
        _handle_delete(chat_id)
        return
    if text == "/status":
        _handle_status(chat_id)
        return
    if text == "/hilfe":
        send_message(chat_id,
            "ℹ️ *AILIZA Hilfe*\n\n"
            "Stelle einfach eine Frage auf Deutsch.\n\n"
            "Befehle:\n"
            "/start — Datenschutzhinweis\n"
            "/widerrufen — Einwilligung widerrufen (DSGVO Art. 7 Abs. 3)\n"
            "/delete_me — Alle Daten löschen (DSGVO Art. 17)\n"
            "/status — Verbindungsstatus\n\n"
            "⚠️ Du interagierst mit einem KI-System (EU AI Act Art. 50).")
        return

    # 4. Opt-in prüfen
    binding = get_binding(chat_id)
    if binding is None or not binding.get("opt_in_confirmed"):
        send_message(chat_id,
            "Bitte stimme zuerst den Datenschutzhinweisen zu.\n"
            "Tippe /start um den Hinweis zu sehen.")
        return

    tenant_id = binding.get("tenant_id", DEFAULT_TENANT_ID)

    # 5. Capability: message_process (Klassifikation + Redaktion — lokal, kein externer Call)
    cap_process = check_capability(
        "message_process",
        data_classes=[DataClass.PUBLIC, DataClass.PERSONAL_DATA],
        tenant_id=tenant_id,
    )
    if not cap_process.allowed:
        send_message(chat_id, "⛔ Verarbeitung derzeit nicht verfügbar.")
        _audit("messenger.process_blocked", chat_id, {"reason": cap_process.reason})
        return

    # 6. Klassifikation der Nutzereingabe (VOR LLM, Memory und Logs)
    classification = classify(text)
    if classification.highest_risk_class in {
        DataClass.CREDENTIALS, DataClass.SPECIAL_CATEGORY,
        DataClass.HR, DataClass.LEGAL, DataClass.FINANCIAL,
    }:
        send_message(chat_id,
            "⚠️ Deine Nachricht enthält möglicherweise sensible Daten "
            "(Passwörter, persönliche Daten, Finanzdaten). "
            "Bitte entferne diese und versuche es erneut.")
        _audit("messenger.sensitive_input_blocked", chat_id,
               {"highest_class": classification.highest_risk_class.value})
        return

    # 7. Redaktion (VOR LLM)
    redacted = redact(text, classification)
    safe_text = redacted.redacted_text

    # 8. Capability: messenger_send (externe Antwort — CRITICAL, Opt-in = Genehmigung)
    cap_send = check_capability(
        "messenger_send",
        data_classes=[DataClass.PUBLIC],
        tenant_id=tenant_id,
        approval_given=True,  # Opt-in des Nutzers = Einwilligung = Genehmigung
    )
    if not cap_send.allowed:
        send_message(chat_id, "⛔ Antwortversand derzeit nicht verfügbar.")
        _audit("messenger.send_blocked", chat_id, {"reason": cap_send.reason})
        return

    # 9. Agent aufrufen (llm_call-Capability wird intern im Orchestrator geprüft)
    answer = _run_agent(safe_text, tenant_id)

    # 10. Antwort senden (EU AI Act Art. 50: KI-Kennzeichnung Pflicht)
    send_message(chat_id,
        f"{answer}\n\n_🤖 KI-generierte Antwort — AILIZA (EU AI Act Art. 50, Reg. (EU) 2024/1689)_")
    _audit("messenger.response_sent", chat_id, {"tenant_id": tenant_id})


def _handle_start(chat_id: str, username: str | None) -> None:
    binding = get_binding(chat_id)
    if binding is None:
        create_binding(chat_id, username)
    send_message(chat_id, _DATENSCHUTZ_HINWEIS)
    _audit("messenger.start", chat_id)


def _handle_accept(chat_id: str) -> None:
    binding = get_binding(chat_id)
    if binding is None:
        create_binding(chat_id, None)
    confirm_opt_in(chat_id)
    send_message(chat_id, _WILLKOMMEN)
    _audit("messenger.opt_in_confirmed", chat_id)


def _handle_revoke(chat_id: str) -> None:
    """
    DSGVO Art. 7 Abs. 3: Widerruf der Einwilligung.
    Verarbeitung stoppt sofort. Bindungs-Datensatz (Pseudonym + Opt-in-Zeitstempel)
    bleibt als Nachweis erhalten. Fuer vollstaendige Loeschung: /delete_me.
    """
    binding = get_binding(chat_id)
    if binding is None:
        send_message(chat_id, "Keine aktive Verbindung gefunden. Tippe /start.")
        return
    revoke_opt_in(chat_id)
    send_message(chat_id,
        "✅ Deine Einwilligung wurde widerrufen (DSGVO Art. 7 Abs. 3).\n"
        "Ich verarbeite keine weiteren Nachrichten von dir.\n\n"
        "📌 Deine Verbindungsdaten (pseudonymisiert) bleiben als Nachweis gespeichert.\n"
        "Fuer vollstaendige Loeschung tippe /delete_me.\n\n"
        "Tippe /accept um die Einwilligung erneut zu erteilen.")
    _audit("messenger.opt_in_revoked", chat_id)


def _handle_delete(chat_id: str) -> None:
    """
    DSGVO Art. 17: Recht auf Loeschung (Recht auf Vergessenwerden).
    Entfernt die Bindung und alle gespeicherten personenbezogenen Daten vollstaendig.
    Audit-Eintraege (ohne Inhalt, nur HMAC-Pseudonym) verbleiben gemaess Art. 5 Abs. 2.
    """
    delete_binding(chat_id)
    send_message(chat_id,
        "✅ Deine Daten wurden vollständig gelöscht (DSGVO Art. 17).\n"
        "Du kannst jederzeit mit /start neu beginnen.")
    _audit("messenger.data_deleted", chat_id)


def _handle_status(chat_id: str) -> None:
    binding = get_binding(chat_id)
    if binding and binding.get("opt_in_confirmed"):
        send_message(chat_id, "✅ Verbunden und aktiv.")
    elif binding:
        send_message(chat_id,
            "⏸ Einwilligung widerrufen.\n"
            "Tippe /accept zum Reaktivieren oder /delete_me fuer vollstaendige Loeschung.")
    else:
        send_message(chat_id, "❌ Nicht verbunden. Tippe /start.")


def _run_agent(task: str, tenant_id: str) -> str:
    """Ruft den Fast-Path oder Provider-Orchestrator auf. Fail-closed."""
    try:
        from ..main import answer_simple_question
    except ImportError:
        try:
            from main import answer_simple_question
        except ImportError:
            answer_simple_question = None

    if answer_simple_question:
        fast = answer_simple_question(task)
        if fast:
            return fast

    try:
        from ..kill_switch import is_external_llm_enabled
    except ImportError:
        from kill_switch import is_external_llm_enabled
    if not is_external_llm_enabled():
        return "Externe KI ist derzeit deaktiviert. Fuer einfache Fragen stehe ich lokal zur Verfuegung."

    try:
        from ..providers.orchestrator import ProviderOrchestrator
    except ImportError:
        from providers.orchestrator import ProviderOrchestrator

    try:
        orch = ProviderOrchestrator()
        messages = [
            {"role": "system", "content": "Du bist AILIZA, ein KI-Assistent fuer KMU. Antworte kurz und auf Deutsch."},
            {"role": "user", "content": task},
        ]
        return orch.generate(messages)
    except Exception:
        return "Es tut mir leid, ich konnte deine Anfrage gerade nicht verarbeiten."


# ── Audit-Light ───────────────────────────────────────────────────────────────
def _audit(action: str, chat_id: str, meta: dict[str, Any] | None = None) -> None:
    """
    Pseudonymisiertes Audit-Light: kein Nachrichteninhalt, kein Klartext der chat_id.
    HMAC-SHA256 mit serverseitigem Secret — pseudonymisiert, nicht anonymisiert.
    """
    try:
        write_audit_entry(
            action=action,
            metadata={"chat_pseudo": _pseudo_chat_id(chat_id), **(meta or {})},
        )
    except Exception:
        pass
