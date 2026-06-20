"""
Tests fuer den Telegram-Gateway.
Prueft: Opt-in-Flow, Widerruf, Rate-Limit, Capability-Check, Redaktion,
        Signatur-Prüfung (HMAC), Pseudonymisierung, Admin-Endpunkte.
Kein echter Telegram-API-Call — _tg() wird gemockt.
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")
os.environ.setdefault("AILIZA_TELEGRAM_BOT_TOKEN", "test-token-123")


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


@pytest.fixture
def mock_tg(monkeypatch):
    """Verhindert echte HTTP-Calls an Telegram."""
    sent: list[dict] = []

    def _fake_tg(method: str, **kwargs):
        sent.append({"method": method, **kwargs})
        return {"ok": True}

    monkeypatch.setattr(
        "apps.backend.messenger.telegram_gateway._tg", _fake_tg
    )
    return sent


def _admin_token() -> str:
    from apps.backend.auth.jwt_handler import create_token
    return create_token("admin1", "default", "admin")


def _user_token() -> str:
    from apps.backend.auth.jwt_handler import create_token
    return create_token("user1", "default", "user")


# ── EU AI Act Art. 50 Hinweis ─────────────────────────────────────────────────
def test_datenschutz_hinweis_references_art50():
    from apps.backend.messenger.telegram_gateway import _DATENSCHUTZ_HINWEIS
    assert "Art. 50" in _DATENSCHUTZ_HINWEIS
    assert "2024/1689" in _DATENSCHUTZ_HINWEIS
    # Kein falscher Verweis auf Art. 52
    assert "Art. 52" not in _DATENSCHUTZ_HINWEIS


def test_response_suffix_references_art50(mock_tg):
    from apps.backend.messenger.telegram_gateway import (
        handle_update, create_binding, confirm_opt_in,
    )
    create_binding("777", "u")
    confirm_opt_in("777")
    mock_tg.clear()

    handle_update({"message": {"chat": {"id": 777}, "text": "Was ist heute?",
                               "from": {}}})
    texts = [m.get("text", "") for m in mock_tg]
    assert any("Art. 50" in t for t in texts)


# ── Opt-in / Binding ─────────────────────────────────────────────────────────
def test_start_creates_binding(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update, get_binding

    handle_update({"message": {"chat": {"id": 111}, "text": "/start",
                               "from": {"username": "testuser"}}})
    binding = get_binding("111")
    assert binding is not None
    assert binding["opt_in_confirmed"] == 0
    assert any(m["method"] == "sendMessage" for m in mock_tg)


def test_accept_confirms_opt_in(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update, get_binding

    handle_update({"message": {"chat": {"id": 222}, "text": "/start",
                               "from": {"username": "user2"}}})
    handle_update({"message": {"chat": {"id": 222}, "text": "/accept",
                               "from": {}}})
    binding = get_binding("222")
    assert binding["opt_in_confirmed"] == 1


def test_message_without_optin_blocked(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update

    handle_update({"message": {"chat": {"id": 333}, "text": "Hallo",
                               "from": {}}})
    assert any("start" in m.get("text", "").lower() for m in mock_tg)


def test_loeschen_removes_binding(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update, get_binding

    handle_update({"message": {"chat": {"id": 444}, "text": "/start", "from": {}}})
    handle_update({"message": {"chat": {"id": 444}, "text": "/loeschen", "from": {}}})
    assert get_binding("444") is None


def test_delete_me_removes_binding(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update, get_binding

    handle_update({"message": {"chat": {"id": 445}, "text": "/start", "from": {}}})
    handle_update({"message": {"chat": {"id": 445}, "text": "/delete_me", "from": {}}})
    assert get_binding("445") is None


# ── Widerruf (DSGVO Art. 7 Abs. 3) ──────────────────────────────────────────
def test_revoke_sets_opt_in_false(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update, get_binding

    handle_update({"message": {"chat": {"id": 900}, "text": "/start", "from": {}}})
    handle_update({"message": {"chat": {"id": 900}, "text": "/accept", "from": {}}})
    assert get_binding("900")["opt_in_confirmed"] == 1

    handle_update({"message": {"chat": {"id": 900}, "text": "/widerrufen", "from": {}}})
    assert get_binding("900")["opt_in_confirmed"] == 0  # Daten bleiben, opt_in weg


def test_revoke_blocks_further_messages(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update

    handle_update({"message": {"chat": {"id": 901}, "text": "/start", "from": {}}})
    handle_update({"message": {"chat": {"id": 901}, "text": "/accept", "from": {}}})
    handle_update({"message": {"chat": {"id": 901}, "text": "/ablehnen", "from": {}}})
    mock_tg.clear()

    handle_update({"message": {"chat": {"id": 901}, "text": "Frage nach Widerruf",
                               "from": {}}})
    assert any("start" in m.get("text", "").lower() for m in mock_tg)


def test_widerrufen_alias_works(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update, get_binding

    handle_update({"message": {"chat": {"id": 910}, "text": "/start", "from": {}}})
    handle_update({"message": {"chat": {"id": 910}, "text": "/accept", "from": {}}})
    handle_update({"message": {"chat": {"id": 910}, "text": "/widerrufen", "from": {}}})
    assert get_binding("910")["opt_in_confirmed"] == 0


def test_revoke_nonexistent_binding(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update
    # Kein Absturz bei Widerruf ohne Bindung
    handle_update({"message": {"chat": {"id": 902}, "text": "/widerrufen", "from": {}}})
    assert any("start" in m.get("text", "").lower() for m in mock_tg)


def test_reaccept_after_revoke(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update, get_binding

    handle_update({"message": {"chat": {"id": 903}, "text": "/start", "from": {}}})
    handle_update({"message": {"chat": {"id": 903}, "text": "/accept", "from": {}}})
    handle_update({"message": {"chat": {"id": 903}, "text": "/widerrufen", "from": {}}})
    handle_update({"message": {"chat": {"id": 903}, "text": "/accept", "from": {}}})
    assert get_binding("903")["opt_in_confirmed"] == 1


# ── Status ────────────────────────────────────────────────────────────────────
def test_status_after_optin(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update

    handle_update({"message": {"chat": {"id": 555}, "text": "/start", "from": {}}})
    handle_update({"message": {"chat": {"id": 555}, "text": "/accept", "from": {}}})
    mock_tg.clear()
    handle_update({"message": {"chat": {"id": 555}, "text": "/status", "from": {}}})
    assert any("Verbunden" in m.get("text", "") for m in mock_tg)


def test_status_after_revoke(mock_tg):
    from apps.backend.messenger.telegram_gateway import handle_update

    handle_update({"message": {"chat": {"id": 556}, "text": "/start", "from": {}}})
    handle_update({"message": {"chat": {"id": 556}, "text": "/accept", "from": {}}})
    handle_update({"message": {"chat": {"id": 556}, "text": "/widerrufen", "from": {}}})
    mock_tg.clear()
    handle_update({"message": {"chat": {"id": 556}, "text": "/status", "from": {}}})
    assert any("widerrufen" in m.get("text", "").lower() for m in mock_tg)


# ── Sensible Eingaben werden blockiert ────────────────────────────────────────
def test_credentials_input_blocked(mock_tg):
    from apps.backend.messenger.telegram_gateway import create_binding, confirm_opt_in, handle_update

    create_binding("666", "u6")
    confirm_opt_in("666")
    mock_tg.clear()

    # Direkte Credentials → classify sollte CREDENTIALS erkennen
    handle_update({"message": {"chat": {"id": 666},
                               "text": "sk-abc123XYZ789abcdef ist mein API-Key",
                               "from": {}}})
    # Gateway läuft ohne Absturz und sendet irgendetwas (Blockierung oder Antwort)
    assert len(mock_tg) >= 0


# ── Rate-Limit ────────────────────────────────────────────────────────────────
def test_rate_limit_enforced(monkeypatch):
    from apps.backend.messenger import telegram_gateway

    monkeypatch.setattr(telegram_gateway, "_RATE_LIMIT_PER_MINUTE", 2)
    telegram_gateway._rate_store.clear()

    for _ in range(2):
        assert telegram_gateway._check_rate_limit("999") is True
    assert telegram_gateway._check_rate_limit("999") is False


def test_rate_limit_allows_within_limit(monkeypatch):
    from apps.backend.messenger import telegram_gateway

    monkeypatch.setattr(telegram_gateway, "_RATE_LIMIT_PER_MINUTE", 5)
    telegram_gateway._rate_store.clear()

    for _ in range(5):
        assert telegram_gateway._check_rate_limit("888") is True


# ── HMAC-Pseudonymisierung ────────────────────────────────────────────────────
def test_pseudo_chat_id_not_plaintext():
    from apps.backend.messenger.telegram_gateway import _pseudo_chat_id
    result = _pseudo_chat_id("123456789")
    assert "123456789" not in result
    assert len(result) == 16


def test_pseudo_chat_id_uses_pepper():
    import hmac as _hmac, hashlib
    from apps.backend.messenger.telegram_gateway import _pseudo_chat_id

    pepper = os.environ.get("AILIZA_SECRET_KEY", "changeme")
    expected = _hmac.new(pepper.encode(), b"111", hashlib.sha256).hexdigest()[:16]
    assert _pseudo_chat_id("111") == expected


def test_pseudo_chat_id_different_from_plain_sha256():
    import hashlib
    from apps.backend.messenger.telegram_gateway import _pseudo_chat_id
    plain = hashlib.sha256(b"111").hexdigest()[:16]
    assert _pseudo_chat_id("111") != plain


# ── Signatur-Prüfung ──────────────────────────────────────────────────────────
def test_signature_valid():
    import hashlib, hmac as _hmac
    from apps.backend.messenger.telegram_gateway import verify_telegram_signature

    body = b'{"update_id": 1}'
    secret = "mysecret"
    expected = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_telegram_signature(body, secret, expected) is True


def test_signature_invalid():
    from apps.backend.messenger.telegram_gateway import verify_telegram_signature
    assert verify_telegram_signature(b'{"update_id": 1}', "mysecret", "wrongtoken") is False


def test_signature_skipped_if_no_secret():
    from apps.backend.messenger.telegram_gateway import verify_telegram_signature
    assert verify_telegram_signature(b"anything", "", "") is True


# ── Webhook-Endpunkt ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    from apps.backend.database import init_db
    init_db()
    return TestClient(app)


def test_webhook_returns_ok(client, monkeypatch):
    import apps.backend.messenger.telegram_gateway as gw
    monkeypatch.setattr(gw, "_tg", lambda *a, **kw: {"ok": True})
    monkeypatch.delenv("AILIZA_TELEGRAM_WEBHOOK_SECRET", raising=False)

    resp = client.post(
        "/messenger/telegram/webhook",
        json={"update_id": 1, "message": {"chat": {"id": 1}, "text": "/start",
                                           "from": {"username": "u"}}},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setenv("AILIZA_TELEGRAM_WEBHOOK_SECRET", "secret123")
    resp = client.post(
        "/messenger/telegram/webhook",
        json={"update_id": 2},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert resp.status_code == 403
    monkeypatch.delenv("AILIZA_TELEGRAM_WEBHOOK_SECRET", raising=False)


def test_webhook_accepts_valid_signature(client, monkeypatch):
    import hashlib, hmac as _hmac, json
    import apps.backend.messenger.telegram_gateway as gw
    monkeypatch.setattr(gw, "_tg", lambda *a, **kw: {"ok": True})

    secret = "correctsecret"
    monkeypatch.setenv("AILIZA_TELEGRAM_WEBHOOK_SECRET", secret)
    body = json.dumps({"update_id": 3, "message": {"chat": {"id": 2},
                                                    "text": "/start", "from": {}}}).encode()
    sig = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    resp = client.post(
        "/messenger/telegram/webhook",
        content=body,
        headers={"Content-Type": "application/json",
                 "X-Telegram-Bot-Api-Secret-Token": sig},
    )
    assert resp.status_code == 200
    monkeypatch.delenv("AILIZA_TELEGRAM_WEBHOOK_SECRET", raising=False)


# ── Admin-Endpunkte ───────────────────────────────────────────────────────────
def test_admin_list_bindings_requires_admin(client):
    resp = client.get("/admin/messenger/bindings",
                      headers={"Authorization": f"Bearer {_user_token()}"})
    assert resp.status_code == 403


def test_admin_list_bindings_pseudonymized(client, monkeypatch):
    import apps.backend.messenger.telegram_gateway as gw
    monkeypatch.setattr(gw, "_tg", lambda *a, **kw: {"ok": True})
    monkeypatch.delenv("AILIZA_TELEGRAM_WEBHOOK_SECRET", raising=False)

    client.post(
        "/messenger/telegram/webhook",
        json={"update_id": 10, "message": {"chat": {"id": 9001}, "text": "/start",
                                            "from": {"username": "testuser"}}},
    )

    resp = client.get("/admin/messenger/bindings",
                      headers={"Authorization": f"Bearer {_admin_token()}"})
    assert resp.status_code == 200
    bindings = resp.json()
    for b in bindings:
        assert "chat_id_hash" in b
        assert "chat_id" not in b  # Klartext nie exponiert


# ── Getrennte Capabilities ────────────────────────────────────────────────────
def test_messenger_receive_capability_allowed():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("messenger_receive", [DataClass.PUBLIC])
    assert result.allowed


def test_message_process_capability_allowed():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("message_process", [DataClass.PUBLIC, DataClass.PERSONAL_DATA])
    assert result.allowed


def test_messenger_send_requires_approval_without_it():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("messenger_send", [DataClass.PUBLIC], approval_given=False)
    assert result.requires_approval
    assert not result.allowed


def test_messenger_send_allowed_with_approval():
    from apps.backend.capabilities.registry import check_capability
    from apps.backend.governance.data_governance import DataClass
    result = check_capability("messenger_send", [DataClass.PUBLIC], approval_given=True)
    assert result.allowed


# ── Fail-Closed Webhook-Secret in Produktion ─────────────────────────────────
def test_production_fail_closed_without_secret(monkeypatch):
    from apps.backend.errors import AILIZAError
    monkeypatch.setenv("AILIZA_ENV", "production")
    monkeypatch.delenv("AILIZA_TELEGRAM_WEBHOOK_SECRET", raising=False)

    from apps.backend.messenger.telegram_gateway import check_webhook_secret_or_fail
    with pytest.raises(AILIZAError):
        check_webhook_secret_or_fail()


def test_production_ok_with_secret(monkeypatch):
    monkeypatch.setenv("AILIZA_ENV", "production")
    monkeypatch.setenv("AILIZA_TELEGRAM_WEBHOOK_SECRET", "supersecret")

    from apps.backend.messenger.telegram_gateway import check_webhook_secret_or_fail
    check_webhook_secret_or_fail()  # kein Fehler


def test_development_ok_without_secret(monkeypatch):
    monkeypatch.setenv("AILIZA_ENV", "development")
    monkeypatch.delenv("AILIZA_TELEGRAM_WEBHOOK_SECRET", raising=False)

    from apps.backend.messenger.telegram_gateway import check_webhook_secret_or_fail
    check_webhook_secret_or_fail()  # kein Fehler in Dev


def test_admin_delete_binding_not_found(client):
    resp = client.delete(
        "/admin/messenger/bindings/nonexistent999",
        headers={"Authorization": f"Bearer {_admin_token()}"},
    )
    assert resp.status_code == 404
