"""Sicherheits-Hotfix: Chats/Projekte/Ordner/Tools sind an den Nutzer-Scope
gebunden (nicht mehr an einen globalen, ungebundenen localStorage-Schluessel).

Vorher blieben Chats und Projekte nach dem Abmelden weiterhin sichtbar und
ein anderer Nutzer auf demselben Browser sah die Daten des vorherigen Nutzers,
weil alle localStorage-Schluessel (ailiza_chat, ailiza_chat_list,
ailiza_projects, ...) global und nutzerunabhaengig waren.

Das eigentliche Verhalten (Isolation zwischen zwei echten, im Backend
registrierten Nutzern, ueber Login/Logout/Reload hinweg) wurde zusaetzlich
mit einem echten Chromium-Browser (Playwright) end-to-end verifiziert -- das
ist mit den hier verfuegbaren Tools nicht automatisiert nachstellbar, daher
dokumentieren diese Tests nur die Code-Eigenschaften, die diese Isolation
technisch tragen: scopedKey() wird fuer jeden betroffenen Schluessel benutzt,
und Login/Logout loesen tatsaechlich einen Scope-Wechsel aus.
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


def test_scoped_key_helper_exists_and_binds_to_active_scope(served_index):
    assert "function scopedKey(base)" in served_index
    assert 'let _scope="anon";' in served_index


def test_all_chat_and_project_keys_go_through_scoped_key(served_index):
    # Kein direkter, unscoped Zugriff mehr auf diese Schluessel ausserhalb der
    # scopedKey()-Definition/Initialisierung selbst.
    for literal in (
        '"ailiza_chat"', '"ailiza_chat_list"', '"ailiza_chat_meta"',
        '"ailiza_current_chat_id"', '"ailiza_active_project_id"',
        '"ailiza_projects"', '"ailiza_folders"', '"ailiza_tools"',
    ):
        for match in _find_all(served_index, literal):
            line_start = served_index.rfind("\n", 0, match) + 1
            line_end = served_index.find("\n", match)
            line = served_index[line_start:line_end]
            assert "scopedKey(" in line or "function scopedKey" in line or "function reloadScopedState" in line, (
                f"Unscoped Zugriff auf {literal} gefunden: {line.strip()[:200]}"
            )


def test_project_chat_storage_key_is_scoped(served_index):
    assert "function getProjectChatStorageKey(chatId){return scopedKey(" in served_index


def test_logout_switches_to_anon_scope_before_awaiting_network(served_index):
    start = served_index.index("async function doLogout()")
    end = served_index.index("function showView(")
    fn = served_index[start:end]
    assert fn.index('applyScopeAndRerender("anon")') < fn.index("await fetch(")


def test_login_success_awaits_scope_switch_before_continuing(served_index):
    start = served_index.index("async function doLogin()")
    end = served_index.index("async function doLogout()") if served_index.index("async function doLogout()") > start else len(served_index)
    fn = served_index[start:start + 3000]
    assert "await refreshAuthButton();" in fn


def test_refresh_auth_button_applies_scope_for_logged_in_and_anon(served_index):
    start = served_index.index("async function refreshAuthButton()")
    end = served_index.index("async function doLogout()")
    fn = served_index[start:end]
    assert 'applyScopeAndRerender(me.user_id||"unknown")' in fn
    assert 'applyScopeAndRerender("anon")' in fn


def test_apply_scope_clears_draft_and_rerenders_everything(served_index):
    start = served_index.index("function applyScopeAndRerender(newScope)")
    end = served_index.index("function", start + 10)
    fn = served_index[start:end]
    assert 'document.getElementById("chat-input").value=""' in fn
    for call in ("reloadScopedState()", "renderChat()", "renderPrivacyMemory()", "renderRecent()", "renderProjects()", "renderProjectList()", "renderFolders()", "renderTools()", "updateChatProjectLabel()"):
        assert call in fn


def test_delete_my_data_removes_scoped_keys_not_hardcoded_globals(served_index):
    start = served_index.index("async function deleteMyData()")
    end = served_index.index("forEach(k=>localStorage.removeItem(k))", start)
    fn = served_index[start:end]
    assert 'scopedKey("ailiza_chat")' in fn
    assert 'scopedKey("ailiza_projects")' in fn


def _find_all(haystack: str, needle: str) -> list[int]:
    positions = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx == -1:
            break
        positions.append(idx)
        start = idx + 1
    return positions
