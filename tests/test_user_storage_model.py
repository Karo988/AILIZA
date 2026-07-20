"""
Teilschritt 1: serverseitige Speicherung von Projekten/Chats.
Schwerpunkt: strikte Mandanten- UND Nutzertrennung. Kein Helper darf
je an fremde Datensaetze gelangen.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.database import (
    metadata_obj, engine, init_db,
    save_user_project, list_user_projects, delete_user_project,
    save_user_chat, list_user_chats, get_user_chat, delete_user_chat,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


# ── Projekte ──
def test_project_save_and_list():
    save_user_project("p1", "t1", "userA", name="Projekt A")
    rows = list_user_projects("t1", "userA")
    assert len(rows) == 1
    assert rows[0]["name"] == "Projekt A"


def test_project_upsert_updates_not_duplicates():
    save_user_project("p1", "t1", "userA", name="Alt")
    save_user_project("p1", "t1", "userA", name="Neu")
    rows = list_user_projects("t1", "userA")
    assert len(rows) == 1
    assert rows[0]["name"] == "Neu"


def test_project_user_isolation():
    save_user_project("p1", "t1", "userA", name="Gehoert A")
    # userB im selben Tenant darf A's Projekt NICHT sehen
    assert list_user_projects("t1", "userB") == []


def test_project_tenant_isolation():
    save_user_project("p1", "t1", "userA", name="Tenant1")
    # gleicher user_id-String, anderer Tenant -> kein Zugriff
    assert list_user_projects("t2", "userA") == []


def test_project_delete_only_own():
    save_user_project("p1", "t1", "userA", name="A")
    # userB versucht A's Projekt zu loeschen -> 0 Zeilen betroffen
    assert delete_user_project("p1", "t1", "userB") == 0
    assert len(list_user_projects("t1", "userA")) == 1
    # A loescht selbst -> 1 Zeile
    assert delete_user_project("p1", "t1", "userA") == 1
    assert list_user_projects("t1", "userA") == []


def test_project_upsert_cannot_hijack_foreign_id():
    # userA legt p1 an; userB "speichert" p1 -> darf A's Datensatz NICHT
    # ueberschreiben, sondern legt einen eigenen (getrennten) an.
    save_user_project("p1", "t1", "userA", name="A-Version")
    save_user_project("p1", "t1", "userB", name="B-Version")
    a = list_user_projects("t1", "userA")
    b = list_user_projects("t1", "userB")
    assert len(a) == 1 and a[0]["name"] == "A-Version"
    assert len(b) == 1 and b[0]["name"] == "B-Version"


# ── Chats ──
def test_chat_save_get_and_count():
    save_user_chat("c1", "t1", "userA", messages=[{"role": "user", "content": "hi"}])
    chat = get_user_chat("c1", "t1", "userA")
    assert chat is not None
    assert chat["message_count"] == 1
    assert chat["messages"][0]["content"] == "hi"


def test_chat_user_isolation():
    save_user_chat("c1", "t1", "userA", messages=[{"role": "user", "content": "geheim"}])
    assert get_user_chat("c1", "t1", "userB") is None
    assert list_user_chats("t1", "userB") == []


def test_chat_upsert_updates_not_duplicates():
    save_user_chat("c1", "t1", "userA", messages=[{"role": "user", "content": "a"}])
    save_user_chat("c1", "t1", "userA", messages=[{"role": "user", "content": "a"},
                                                  {"role": "ai", "content": "b"}])
    rows = list_user_chats("t1", "userA")
    assert len(rows) == 1
    assert rows[0]["message_count"] == 2


def test_chat_delete_only_own():
    save_user_chat("c1", "t1", "userA", messages=[])
    assert delete_user_chat("c1", "t1", "userB") == 0
    assert delete_user_chat("c1", "t1", "userA") == 1
    assert get_user_chat("c1", "t1", "userA") is None


def test_chat_filter_by_project():
    save_user_chat("c1", "t1", "userA", messages=[], project_id="proj1")
    save_user_chat("c2", "t1", "userA", messages=[], project_id="proj2")
    save_user_chat("c3", "t1", "userA", messages=[], project_id=None)
    only_proj1 = list_user_chats("t1", "userA", project_id="proj1")
    assert len(only_proj1) == 1
    assert only_proj1[0]["id"] == "c1"
    assert len(list_user_chats("t1", "userA")) == 3


def test_retention_column_present_but_null():
    save_user_chat("c1", "t1", "userA", messages=[])
    chat = get_user_chat("c1", "t1", "userA")
    # Retention-Spalte ist da, aber keine automatische Loeschung (bewusst None)
    assert "retention_until" in chat
    assert chat["retention_until"] is None
