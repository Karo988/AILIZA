"""Hotfix: Legacy-Storage-Isolation -- echte Alt-Daten aus der Zeit vor jeder
Scope-Trennung duerfen nie automatisch geladen werden (weder anonym noch
einem angemeldeten Nutzer zugeschlagen), aber auch nie geloescht werden.

Prueft das tatsaechlich ausgelieferte Frontend (TestClient GET "/").
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient

from apps.backend.main import app


@pytest.fixture()
def served_index() -> str:
    client = TestClient(app)
    response = client.get("/", headers={"accept": "text/html"})
    assert response.status_code == 200
    return response.text


def test_legacy_bases_list_covers_all_known_legacy_keys(served_index):
    start = served_index.index('const _LEGACY_STORAGE_BASES=')
    end = served_index.index("];", start)
    literal = served_index[start:end]
    for base in ("ailiza_chat", "ailiza_chat_list", "ailiza_chat_meta",
                 "ailiza_current_chat_id", "ailiza_active_project_id",
                 "ailiza_projects", "ailiza_folders", "ailiza_tools"):
        assert f'"{base}"' in literal


def test_legacy_per_chat_message_keys_are_detected_dynamically(served_index):
    start = served_index.index("function _isLegacyPerChatMessageKey(key)")
    end = served_index.index("}", start)
    fn = served_index[start:end]
    assert 'key.startsWith("ailiza_chat_")' in fn
    assert 'key!=="ailiza_chat_list"' in fn
    assert 'key!=="ailiza_chat_meta"' in fn


def test_migration_moves_to_quarantine_prefix_and_never_deletes_value(served_index):
    start = served_index.index("function migrateLegacyKeysToQuarantine()")
    end = served_index.index("function hasUnclaimedLegacyQuarantine()")
    fn = served_index[start:end]
    assert '"legacy_quarantine_"+key' in fn
    # Wert wird VOR dem Entfernen des Alt-Schluessels in die Quarantaene kopiert.
    assert fn.index("localStorage.setItem(quarantineKey") < fn.index("localStorage.removeItem(key)")
    # Idempotenz-Schutz: ueberschreibt eine bereits bestehende Quarantaene nicht.
    assert 'localStorage.getItem(quarantineKey)===null' in fn


def test_migration_never_calls_a_delete_of_quarantine_itself(served_index):
    start = served_index.index("function migrateLegacyKeysToQuarantine()")
    end = served_index.index("function hasUnclaimedLegacyQuarantine()")
    fn = served_index[start:end]
    assert "localStorage.removeItem(quarantineKey)" not in fn


def test_restore_requires_explicit_confirmation_and_can_be_declined(served_index):
    start = served_index.index("function offerLegacyQuarantineRestoreIfNeeded()")
    end = served_index.index("function applyScopeAndRerender(")
    fn = served_index[start:end]
    assert "confirm(" in fn
    assert 'localStorage.setItem("legacy_quarantine_status","dismissed")' in fn
    assert 'localStorage.setItem("legacy_quarantine_status","claimed")' in fn
    # Bei Ablehnung: kein removeItem auf legacy_quarantine_* Schluessel -> nichts geloescht.
    decline_branch_start = fn.index("if(!ok)")
    decline_branch = fn[decline_branch_start:decline_branch_start + 100]
    assert "removeItem" not in decline_branch


def test_restore_writes_into_the_currently_active_scope_via_scoped_key(served_index):
    start = served_index.index("function offerLegacyQuarantineRestoreIfNeeded()")
    end = served_index.index("function applyScopeAndRerender(")
    fn = served_index[start:end]
    assert "localStorage.setItem(scopedKey(originalBase)" in fn


def test_migration_runs_once_at_startup_before_auth_check(served_index):
    start = served_index.index("async function init()")
    end = served_index.index("async function refreshAuthButton()")
    fn = served_index[start:end]
    assert fn.index("migrateLegacyKeysToQuarantine();") < fn.index("await refreshAuthButton();")
