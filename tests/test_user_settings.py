"""Mini-PR 1: Nutzerprofil minimal halten, user_settings trennen.

Scope (siehe docs/DATABASE_MEMORY_GOVERNANCE_V1.md, Mini-PR 1):
users bleibt technisch/klein, aenderbare Arbeits-/Bedienpraeferenzen kommen
in eine eigene Tabelle user_settings. Kein Gedaechtnis, keine memory_items
in dieser PR.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from apps.backend.database import (
    metadata_obj, engine, init_db, users, user_settings,
    create_user, get_user_settings, upsert_user_settings,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str = "alice") -> None:
    create_user(user_id=user_id, tenant_id="default", role="user", hashed_password="hash")


# ── Testgruppe 1: Migration/Tabelle ──────────────────────────────────────────

def test_table_is_created_with_user_id_and_timestamps():
    cols = {c.name for c in user_settings.columns}
    assert "user_id" in cols
    assert "created_at" in cols
    assert "updated_at" in cols


def test_only_one_settings_row_per_user():
    from datetime import datetime, timezone

    _make_user("alice")
    upsert_user_settings("alice", "default")
    now = datetime.now(timezone.utc)
    # Zweiter direkter Insert fuer denselben (user_id, tenant_id) verletzt unique.
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(insert(user_settings).values(
                user_id="alice", tenant_id="default",
                antwortlaenge="normal", ton="freundlich", sprache=None,
                ausgabeformat=None, ui_prefs={}, benachrichtigungen={},
                aktives_merken=0, sichtbare_zusammenfassungen_erlaubt=0,
                erinnerungs_vorschlaege_erlaubt=1, speichermodus="immer_fragen",
                created_at=now, updated_at=now,
            ))


def test_upsert_updates_not_duplicates():
    _make_user("alice")
    upsert_user_settings("alice", "default", ton="sachlich")
    upsert_user_settings("alice", "default", ton="formell")
    result = get_user_settings("alice", "default")
    assert result["ton"] == "formell"


def test_no_physical_user_deletion_documented_as_noop():
    # Karo-Projekt loescht Nutzer nicht physisch (nur users.active=0/1,
    # keine delete_user()-Funktion im gesamten database.py). Spec-Fall
    # "dokumentierter No-op" fuer Loesch-/Aufbewahrungslogik: user_settings
    # bleibt bestehen, solange der User-Datensatz selbst nicht geloescht
    # wird -- das ist bewusst kein Bug dieser PR, sondern bestehendes
    # Projektverhalten. Cascade-Delete wird erst relevant, sobald eine
    # physische User-Loeschung eingefuehrt wird (nicht Teil von Mini-PR 1).
    import inspect
    from apps.backend import database as db_module

    assert "delete_user" not in {n for n, _ in inspect.getmembers(db_module, inspect.isfunction)}


# ── Testgruppe 2: Defaults ───────────────────────────────────────────────────

def test_defaults_on_first_read_without_explicit_save():
    _make_user("alice")
    result = get_user_settings("alice", "default")
    assert result is None  # kein Datensatz ohne expliziten upsert -- kein heimliches Anlegen


def test_defaults_on_upsert_without_values():
    _make_user("alice")
    result = upsert_user_settings("alice", "default")
    assert result["antwortlaenge"] == "normal"
    assert result["ton"] == "freundlich"
    assert result["aktives_merken"] is False
    assert result["sichtbare_zusammenfassungen_erlaubt"] is False
    assert result["erinnerungs_vorschlaege_erlaubt"] is True
    assert result["speichermodus"] == "immer_fragen"


def test_json_fields_default_to_empty_dict():
    _make_user("alice")
    result = upsert_user_settings("alice", "default")
    assert result["ui_prefs"] == {}
    assert result["benachrichtigungen"] == {}


# ── Testgruppe 3: users bleibt minimal ───────────────────────────────────────

def test_users_table_has_no_work_preference_columns():
    forbidden = {
        "antwortlaenge", "ton", "ausgabeformat", "ui_prefs", "benachrichtigungen",
        "aktives_merken", "sichtbare_zusammenfassungen_erlaubt",
        "erinnerungs_vorschlaege_erlaubt",
    }
    cols = {c.name for c in users.columns}
    assert forbidden.isdisjoint(cols)


def test_existing_user_functions_still_work():
    import bcrypt

    hashed = bcrypt.hashpw(b"echtes-passwort", bcrypt.gensalt()).decode()
    create_user(user_id="alice", tenant_id="default", role="user", hashed_password=hashed)
    from apps.backend.database import authenticate_user, get_user
    assert authenticate_user("alice", "falsches-passwort", "default") is None
    assert authenticate_user("alice", "echtes-passwort", "default") is not None
    assert get_user("alice", "default")["role"] == "user"


# ── Testgruppe: Isolation (Mandant/Nutzer) ───────────────────────────────────

def test_settings_isolated_per_user():
    # users.user_id ist alleiniger Primaerschluessel (global eindeutig,
    # nicht (user_id, tenant_id)) -- Isolation testen wir daher zwischen
    # zwei verschiedenen Nutzern, nicht demselben user_id in zwei Mandanten.
    _make_user("alice")
    _make_user("bob")
    upsert_user_settings("alice", "default", ton="sachlich")
    upsert_user_settings("bob", "default", ton="formell")
    assert get_user_settings("alice", "default")["ton"] == "sachlich"
    assert get_user_settings("bob", "default")["ton"] == "formell"


def test_no_sensitive_content_fields_present():
    # Kein Feld fuer Projektwissen/Kundendaten/Gedaechtnis in dieser Tabelle.
    cols = {c.name for c in user_settings.columns}
    forbidden = {"projektwissen", "kundendaten", "gedaechtnis", "chat_zusammenfassung"}
    assert forbidden.isdisjoint(cols)


# ── Testgruppe 5: API ─────────────────────────────────────────────────────

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    return TestClient(app, raise_server_exceptions=True)


def _auth(user_id: str, tenant_id: str = "default"):
    from apps.backend.auth import create_token
    token = create_token(user_id=user_id, tenant_id=tenant_id, role="user")
    return {"Authorization": f"Bearer {token}"}


def test_settings_require_auth(client):
    assert client.get("/api/user-settings").status_code == 401
    assert client.patch("/api/user-settings", json={"ton": "sachlich"}).status_code == 401


def test_get_settings_returns_defaults_without_prior_save(client):
    h = _auth("alice")
    r = client.get("/api/user-settings", headers=h)
    assert r.status_code == 200
    assert r.json()["ton"] == "freundlich"
    assert r.json()["speichermodus"] == "immer_fragen"


def test_patch_settings_updates_own_settings(client):
    h = _auth("alice")
    r = client.patch("/api/user-settings", json={"ton": "sachlich", "antwortlaenge": "kurz"}, headers=h)
    assert r.status_code == 200
    assert r.json()["ton"] == "sachlich"
    assert r.json()["antwortlaenge"] == "kurz"


def test_patch_settings_rejects_unknown_fields(client):
    h = _auth("alice")
    r = client.patch("/api/user-settings", json={"unbekanntes_feld": "x"}, headers=h)
    assert r.status_code == 422


def test_settings_are_per_user_not_shared(client):
    h_alice, h_bob = _auth("alice"), _auth("bob")
    client.patch("/api/user-settings", json={"ton": "sachlich"}, headers=h_alice)
    client.patch("/api/user-settings", json={"ton": "formell"}, headers=h_bob)
    assert client.get("/api/user-settings", headers=h_alice).json()["ton"] == "sachlich"
    assert client.get("/api/user-settings", headers=h_bob).json()["ton"] == "formell"


def test_settings_response_does_not_mix_with_user_stammdaten(client):
    h = _auth("alice")
    r = client.get("/api/user-settings", headers=h)
    body = r.json()
    assert "hashed_password" not in body
    assert "role" not in body
