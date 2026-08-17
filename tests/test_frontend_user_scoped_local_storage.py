"""Sicherheits-Hotfix: Chats/Projekte/lokale Daten sind an den Nutzer-Scope
gebunden (nicht mehr an einen globalen, ungebundenen localStorage-Schluessel).

Verlauf:
- PR #58 fuehrte scopedKey() ein, liess den anonymen Scope aber unter dem
  unveraenderten, unpraefigierten Alt-Schluessel weiterlaufen (z.B.
  "ailiza_chat_list" direkt). Dadurch blieben echte Alt-Daten (aus der Zeit
  vor jeder Scope-Trennung) im anonymen Modus automatisch sichtbar -- das hat
  der Render-Livetest bestaetigt (siehe tests/test_frontend_legacy_storage_quarantine.py
  fuer die Migrations-/Quarantaene-Tests zu diesem Hotfix).
- Dieser Hotfix ersetzt den anonymen Scope durch ein eigenes Praefix
  ("anon_"), ergaenzt den angemeldeten Scope um die tenant_id
  ("u_<user_id>_<tenant_id>_") und verschiebt echte Alt-Daten beim ersten
  Laden in einen gesperrten Quarantaene-Bereich statt sie automatisch zu
  laden.

Das eigentliche Verhalten (Isolation zwischen zwei echten, im Backend
registrierten Nutzern inkl. vorbereiteter Alt-Daten, ueber Login/Logout/
Reload hinweg) wurde zusaetzlich mit einem echten Chromium-Browser
(Playwright) end-to-end verifiziert -- das ist mit den hier verfuegbaren
Tools nicht automatisiert nachstellbar, daher dokumentieren diese Tests nur
die Code-Eigenschaften, die diese Isolation technisch tragen.
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


def test_scope_starts_anonymous_with_object_shape(served_index):
    assert 'let _scope={type:"anon"};' in served_index
    assert "function scopeSignature(s)" in served_index


def test_scoped_key_uses_anon_prefix_never_the_bare_legacy_name(served_index):
    start = served_index.index("function scopedKey(base)")
    end = served_index.index("const _LEGACY_STORAGE_BASES=", start)
    fn = served_index[start:end]
    assert '`anon_${base}`' in fn
    assert '`u_${_scope.userId}_${_scope.tenantId}_${base}`' in fn


def test_all_chat_and_project_keys_go_through_scoped_key(served_index):
    for literal in (
        '"ailiza_chat"', '"ailiza_chat_list"', '"ailiza_chat_meta"',
        '"ailiza_current_chat_id"', '"ailiza_active_project_id"',
        '"ailiza_projects"', '"ailiza_folders"', '"ailiza_tools"',
    ):
        for match in _find_all(served_index, literal):
            context = served_index[max(0, match - 250):match]
            assert ("scopedKey(" in context.splitlines()[-1] if context.splitlines() else False) \
                or "_LEGACY_STORAGE_BASES" in context or "legacy_quarantine_" in context \
                or 'key.startsWith("ailiza_chat_")' in context, (
                f"Unscoped Zugriff auf {literal} gefunden: ...{context[-200:]}"
            )


def test_project_chat_storage_key_is_scoped(served_index):
    assert "function getProjectChatStorageKey(chatId){return scopedKey(" in served_index


def test_logout_switches_to_anon_scope_before_awaiting_network(served_index):
    start = served_index.index("async function doLogout()")
    end = served_index.index("function showView(")
    fn = served_index[start:end]
    assert fn.index('applyScopeAndRerender({type:"anon"})') < fn.index("await fetch(")


def test_login_success_awaits_scope_switch_before_continuing(served_index):
    # PR A: doLogin() erhielt einen optionalen Parameter (isFreshRegistration),
    # um nach einer Registrierung eine andere Erfolgsmeldung zu zeigen --
    # Signatur-Text daher angepasst, die eigentliche Invariante (Scope-Wechsel
    # wird vor dem Fortfahren abgewartet) ist unveraendert.
    start = served_index.index("async function doLogin(")
    fn = served_index[start:start + 3000]
    assert "await refreshAuthButton();" in fn


def test_refresh_auth_button_applies_scope_for_logged_in_and_anon(served_index):
    """Der Nutzer-Scope entsteht NUR aus einem echten, nicht leeren Tenant.

    Frueher fiel refreshAuthButton() auf tenant_id="default" zurueck, wenn
    /auth/me keinen Mandanten lieferte -- damit landeten die Daten eines
    Kontos ohne belegten Mandanten im gemeinsamen "default"-Namensraum und
    waren fuer jedes andere Konto ohne Mandanten sichtbar. Der Scope wird
    jetzt fail-closed aufgebaut: ohne eindeutigen Tenant UND Benutzer bleibt
    der anonyme Scope aktiv.
    """
    start = served_index.index("async function refreshAuthButton()")
    end = served_index.index("async function doLogout()")
    fn = served_index[start:end]

    # 1. Kein hart codierter Default-Tenant-Rueckfall mehr (Kernregression).
    #    Kommentarzeilen werden entfernt, damit der Test echten Code prueft.
    code = "\n".join(
        line for line in fn.splitlines() if not line.strip().startswith("//")
    )
    assert 'me.tenant_id||"default"' not in code
    assert '"default"' not in code, "Kein Rueckfall auf einen Default-Mandanten im Auth-Pfad"

    # 2. Tenant und Benutzer werden aus /auth/me geprueft, nicht erfunden.
    assert "me.tenant_id" in fn and "me.user_id" in fn
    assert ".trim()" in fn, "Leerraum-only-Werte muessen verworfen werden"

    # 3. Fail-closed: fehlt einer der beiden Werte, bleibt der anonyme Scope.
    guard = fn[fn.index("_tid"):]
    assert 'if(!_tid||!_uid){' in guard
    anon_in_guard = guard[: guard.index("applyScopeAndRerender({type:\"user\"")]
    assert 'applyScopeAndRerender({type:"anon"})' in anon_in_guard, (
        "Ohne eindeutigen Mandanten muss der anonyme Scope aktiv bleiben"
    )

    # 4. Der Nutzer-Scope verwendet ausschliesslich die geprueften Werte.
    assert 'applyScopeAndRerender({type:"user",userId:_uid,tenantId:_tid})' in fn

    # 5. Der anonyme Pfad (abgemeldet/Fehler) bleibt erhalten.
    assert 'applyScopeAndRerender({type:"anon"})' in fn


def test_scoped_key_never_mixes_tenants(served_index):
    """scopedKey() bindet jeden Speicherschluessel an Benutzer UND Mandant.

    Damit koennen zwei Konten mit gleicher user_id in verschiedenen Tenants
    keine gemeinsamen localStorage-Eintraege sehen.
    """
    start = served_index.index("function scopedKey(base)")
    fn = served_index[start : start + 400]
    assert "_scope.userId" in fn and "_scope.tenantId" in fn, (
        "Der Schluessel muss Benutzer und Mandant enthalten"
    )
    assert "anon_" in fn, "Anonymer Scope braucht ein eigenes Praefix"
    assert '"default"' not in fn, "scopedKey() darf keinen Mandanten erfinden"


def test_apply_scope_resets_state_before_loading_new_scope(served_index):
    start = served_index.index("function applyScopeAndRerender(newScope)")
    end = served_index.index("function", start + 10)
    fn = served_index[start:end]
    assert fn.index("resetAppState()") < fn.index("reloadScopedState()")
    for call in ("renderChat()", "renderPrivacyMemory()", "renderRecent()", "renderProjects()",
                 "renderProjectList()", "renderFolders()", "renderTools()", "updateChatProjectLabel()"):
        assert call in fn


def test_reset_app_state_clears_draft_input_and_uses_fresh_objects(served_index):
    start = served_index.index("function resetAppState()")
    end = served_index.index("function applyScopeAndRerender(")
    fn = served_index[start:end]
    assert 'input.value=""' in fn
    assert "chatHistory=[];" in fn
    assert "projects=[];" in fn


def test_init_determines_auth_status_before_loading_and_rendering(served_index):
    start = served_index.index("async function init()")
    end = served_index.index("async function refreshAuthButton()")
    fn = served_index[start:end]
    assert fn.index("await refreshAuthButton();") < fn.index("loadActiveProjectFromStorage();")
    assert fn.index("migrateLegacyKeysToQuarantine();") < fn.index("await refreshAuthButton();")


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
