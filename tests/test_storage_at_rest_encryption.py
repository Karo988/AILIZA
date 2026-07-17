"""Verschlüsselung at rest, Teilschritt 2: Verdrahtung + Migration.

Prueft, dass Projekt-/Chat-Inhalte in der DB tatsaechlich verschluesselt
liegen (nicht nur die API-Schicht), dass Alt-Klartext weiterhin lesbar
bleibt, und dass die Migration bestehender Datensaetze idempotent ist
(mehrfacher Lauf aendert nichts und beschaedigt keine Daten).
"""
import datetime
import os

import pytest
from sqlalchemy import insert, select

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from apps.backend.database import (
    engine, metadata_obj, init_db, user_projects, user_chats,
    save_user_project, list_user_projects, save_user_chat, get_user_chat,
    migrate_encrypt_existing_records,
)


@pytest.fixture(autouse=True)
def _fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def test_project_stored_encrypted_in_db_but_readable_via_api():
    save_user_project("p1", "default", "karo", name="Angebot Q3", description="Kunde Max Mustermann")
    with engine.begin() as c:
        raw = c.execute(select(user_projects.c.name, user_projects.c.description)).mappings().first()
    assert raw["name"].startswith("enc:v1:")
    assert "Angebot" not in raw["name"]
    api = list_user_projects("default", "karo")[0]
    assert api["name"] == "Angebot Q3"
    assert api["description"] == "Kunde Max Mustermann"


def test_chat_messages_stored_encrypted_in_db_but_readable_via_api():
    save_user_chat("c1", "default", "karo", messages=[{"role": "user", "content": "Hallo Max"}], title="Mein Chat")
    with engine.begin() as c:
        raw = c.execute(select(user_chats.c.title, user_chats.c.messages)).mappings().first()
    assert raw["title"].startswith("enc:v1:")
    assert isinstance(raw["messages"], str) and raw["messages"].startswith("enc:v1:")
    api = get_user_chat("c1", "default", "karo")
    assert api["title"] == "Mein Chat"
    assert api["messages"] == [{"role": "user", "content": "Hallo Max"}]


def test_legacy_plaintext_readable_before_and_after_migration():
    now = datetime.datetime.now(datetime.timezone.utc)
    with engine.begin() as c:
        c.execute(insert(user_projects).values(
            id="legacy1", tenant_id="default", user_id="karo",
            name="Alt-Projekt Klartext", description="alte Beschreibung",
            priority=None, chat_id=None, files=None,
            created_at=now, updated_at=now, retention_until=None, version=1))
    before = next(p for p in list_user_projects("default", "karo") if p["id"] == "legacy1")
    assert before["name"] == "Alt-Projekt Klartext"

    migrate_encrypt_existing_records()

    with engine.begin() as c:
        raw = c.execute(select(user_projects.c.name).where(user_projects.c.id == "legacy1")).scalar()
    assert raw.startswith("enc:v1:")
    after = next(p for p in list_user_projects("default", "karo") if p["id"] == "legacy1")
    assert after["name"] == "Alt-Projekt Klartext"


def test_migration_is_idempotent():
    save_user_project("p1", "default", "karo", name="X", description="Y")
    save_user_chat("c1", "default", "karo", messages=[{"role": "user", "content": "Hallo"}], title="T")
    first = migrate_encrypt_existing_records()
    assert first == {"projects": 0, "chats": 0}  # bereits beim Schreiben verschluesselt
    second = migrate_encrypt_existing_records()
    assert second == {"projects": 0, "chats": 0}
    # Daten nach zwei Migrationslaeufen weiterhin unbeschaedigt lesbar
    assert get_user_chat("c1", "default", "karo")["messages"] == [{"role": "user", "content": "Hallo"}]
