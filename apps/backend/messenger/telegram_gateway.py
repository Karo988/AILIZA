"""
AILIZA Telegram-Gateway (Pilot)
================================
Empfaengt Telegram-Webhook-Events, prueft Nutzer-Opt-in, leitet an Agent weiter.

Sicherheits-Pflichten:
- Opt-in vor jeder Verarbeitung (DSGVO Art. 6, Art. 7)
- Datenschutzhinweis beim ersten Kontakt
- Capability-Check "messenger_send" vor jeder Antwort
- Rate-Limit pro chat_id
- Nur PUBLIC/INTERNAL-Daten erlaubt
- Tenant-Bindung: chat_id → tenant_id + user_id
- Audit-light: kein Nachrichteninhalt, nur HMAC-Pseudonym der chat_id
- Kein API-Key in Code — AILIZA_TELEGRAM_BOT_TOKEN in .env
- Webhook-HMAC: in Produktion Pflicht (AILIZA_TELEGRAM_WEBHOOK_SECRET)

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

# Rate-Limit: Max. Nachrichten pro chat_id pro Minute (in-memory, kein Redis noetig fuer MVP)
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
    "• Du kannst deine Einwilligung jederzeit widerrufen mit /widerrufen\n"
    "• Deine Daten werden auf Verlangen gelöscht mit /loeschen\n\n"
    "Tippe /accept um zuzustimmen und AILIZA zu nutzen.\n"
    "Tippe /ablehnen um die Verarbeitung abzulehnen."
)

_WILLKOMMEN = (
    "✅ Danke! Du kannst jetzt Fragen stellen.\n"
    "Beispiel: _Was ist der Unterschied zwischen GmbH und UG?_\n\n"
    "Befehle:\n"
    "/hilfe — Hilfe anzeigen\n"
    "/widerrufen — Einwilligung widerrufen (DSGVO Art. 7 Abs. 3)\n"
    "/loeschen — Deine Daten vollständig löschen\n"
    "/status — Dein Verbindungsstatus"
)


# ── Pseudonymisierung ─────────────────────────────────────────────────────────
def _pseudo_chat_id(chat_id: str) -> str:
    """
    HMAC-SHA256 mit serverseitigem Pepper (AILIZA_SECRET_KEY) statt plain SHA256.
    Ergebnis: 16-Zeichen-Pseudonym — nicht umkehrbar ohne Secret.
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


# ── Webhook-Signatur-Prüfung ──────────────────────────────────────────────────
def verify_telegram_signature(body: bytes, secret_token: str, x_telegram_token: str) -> bool:
    """
    Prueft X-Telegram-Bot-Api-Secret-Token Header (constant-time Vergleich).
    In Produktion MUSS AILIZA_TELEGRAM_WEBHOOK_SECRET gesetzt sein.
    Ohne Secret: nur fuer lokale Entwicklung akzeptabel.
    """
    if not secret_token:
        return True  # kein Secret konfiguriert — nur in Dev akzeptabel
    expected = hmac.new(secret_token.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, x_telegram_token or "")


def _require_webhook_secret_in_production() -> None:
    """Warnt wenn kein Webhook-Secret gesetzt (non-blocking — Operator muss bewusst entscheiden)."""
    import warnings
    env = os.getenv("AILIZA_ENV", "development").lower()
    if env in ("production", "staging") and not os.getenv("AILIZA_TELEGRAM_WEBHOOK_SECRET"):
        warnings.warn(
            "AILIZA_TELEGRAM_WEBHOOK_SECRET ist nicht gesetzt. "
            "In Produktion ist die Webhook-Signaturprüfung Pflicht (EU AI Act, DSGVO).",
            stacklevel=3,
        )


# ── Rate-Limit ────────────────────────────────────────────────────────────────
def _check_rate_limit(chat_id: str) -> bool:
    """True = erlaubt. False = Rate-Limit ueberschritten."""
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
    """DSGVO Art. 7 Abs. 3: Widerruf der Einwilligung — setzt opt_in auf 0, loescht keine Daten."""
    with engine.begin() as conn:
        conn.execute(
            update(messenger_bindings)
            .where(messenger_bindings.c.chat_id == chat_id)
            .values(opt_in_confirmed=0)
        )


def delete_binding(chat_id: str) -> None:
    """DSGVO-Loeschrecht (Art. 17): entfernt alle Bindungsdaten vollstaendig."""
    with engine.begin() as conn:
        conn.execute(
            sa_delete(messenger_bindings).where(messenger_bindings.c.chat_id == chat_id)
        )


# ── Hauptverarbeitungs-Pipeline ───────────────────────────────────────────────
def handle_update(update_data: dict[str, Any]) -> None:
    """
    Verarbeitet ein eingehendes Telegram-Update.
    Reihenfolge: Rate-Limit → Opt-in-Check → Datenschutz-Hinweis →
                 Capability-Check → Klassifikation → Redaktion → Agent → Antwort senden
    """
    _require_webhook_secret_in_production()

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

    # 2. Befehle
    if text == "/start":
        _handle_start(chat_id, username)
        return
    if text == "/accept":
        _handle_accept(chat_id)
        return
    if text in ("/ablehnen", "/loeschen"):
        _handle_delete(chat_id)
        return
    if text == "/widerrufen":
        _handle_revoke(chat_id)
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
            "/loeschen — Deine Daten vollständig löschen\n"
            "/status — Verbindungsstatus\n\n"
            "⚠️ Du interagierst mit einem KI-System (EU AI Act Art. 50).")
        return

    # 3. Opt-in prüfen
    binding = get_binding(chat_id)
    if binding is None or not binding.get("opt_in_confirmed"):
        send_message(chat_id,
            "Bitte stimme zuerst den Datenschutzhinweisen zu.\n"
            "Tippe /start um den Hinweis zu sehen.")
        return

    tenant_id = binding.get("tenant_id", DEFAULT_TENANT_ID)

    # 4. Capability-Check: messenger_send
    cap = check_capability(
        "messenger_send",
        data_classes=[DataClass.PUBLIC],
        tenant_id=tenant_id,
        approval_given=True,  # Opt-in des Nutzers = Genehmigung
    )
    if not cap.allowed:
        send_message(chat_id, "⛔ Dieser Dienst ist derzeit nicht verfügbar.")
        _audit("messenger.capability_blocked", chat_id, {"reason": cap.reason})
        return

    # 5. Klassifikation der Nutzereingabe (VOR LLM, Memory und Logs)
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

    # 6. Redaktion (zusätzliche Sicherheitsschicht, VOR LLM)
    redacted = redact(text, classification)
    safe_text = redacted.redacted_text

    # 7. Agent aufrufen
    answer = _run_agent(safe_text, tenant_id)

    # 8. Antwort senden (EU AI Act Art. 50: KI-Kennzeichnung Pflicht)
    send_message(chat_id, f"{answer}\n\n_🤖 KI-generierte Antwort — AILIZA (EU AI Act Art. 50)_")
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
    """DSGVO Art. 7 Abs. 3: Widerruf der Einwilligung — Daten bleiben, Verarbeitung stoppt."""
    binding = get_binding(chat_id)
    if binding is None:
        send_message(chat_id, "Keine aktive Verbindung gefunden. Tippe /start.")
        return
    revoke_opt_in(chat_id)
    send_message(chat_id,
        "✅ Deine Einwilligung wurde widerrufen (DSGVO Art. 7 Abs. 3).\n"
        "Ich verarbeite keine weiteren Nachrichten von dir.\n\n"
        "Tippe /loeschen um deine Daten vollständig zu entfernen.\n"
        "Tippe /accept um die Einwilligung erneut zu erteilen.")
    _audit("messenger.opt_in_revoked", chat_id)


def _handle_delete(chat_id: str) -> None:
    delete_binding(chat_id)
    send_message(chat_id,
        "✅ Deine Daten wurden gelöscht (DSGVO Art. 17).\n"
        "Du kannst jederzeit mit /start neu beginnen.")
    _audit("messenger.data_deleted", chat_id)


def _handle_status(chat_id: str) -> None:
    binding = get_binding(chat_id)
    if binding and binding.get("opt_in_confirmed"):
        send_message(chat_id, "✅ Verbunden und aktiv.")
    elif binding:
        send_message(chat_id, "⏸ Einwilligung widerrufen. Tippe /accept zum Reaktivieren.")
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

    # Externes LLM nur wenn aktiviert
    llm_enabled = os.getenv("AILIZA_EXTERNAL_LLM_ENABLED", "false").lower() == "true"
    if not llm_enabled:
        return "Externe KI ist derzeit deaktiviert. Für einfache Fragen stehe ich lokal zur Verfügung."

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
    """HMAC-Pseudonym statt plain SHA256 — serverseitiger Pepper aus AILIZA_SECRET_KEY."""
    try:
        write_audit_entry(
            action=action,
            metadata={"chat_pseudo": _pseudo_chat_id(chat_id), **(meta or {})},
        )
    except Exception:
        pass
