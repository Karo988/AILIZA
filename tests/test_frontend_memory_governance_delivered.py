"""AP-MEMGOV-UI-001 (v1.3): Prueft das tatsaechlich ausgelieferte Frontend.

apps/backend/main.py liefert fuer "/" (und andere Routen) FileResponse auf
apps/frontend/index.html aus -- ein statisches Vanilla-JS-Frontend. Die
Dateien unter apps/frontend/src/ (React/Vite) werden NICHT gebaut und NICHT
ausgeliefert. Ein reiner Quelltexttest gegen apps/frontend/src/ beweist also
nicht, dass Nutzer die Memory-Governance-Oberflaeche jemals sehen.

Dieser Test holt die Startseite ueber die echte FastAPI-App (TestClient,
denselben Pfad wie ein Browser) und prueft am ausgelieferten HTML/JS, dass:
- die Memory-Governance-Oberflaeche im ausgelieferten Markup enthalten ist,
- der ausgelieferte JavaScript-Code /memory/facts verwendet,
- die Loeschfunktion aus dem ausgelieferten Frontend heraus erreichbar ist
  (Button ruft die Loesch-Bestaetigung auf, die wiederum DELETE aufruft).
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


def test_served_index_is_the_static_frontend_not_the_react_scaffold(served_index):
    """Regressionsschutz: stellt sicher, dass der Test wirklich das Vanilla-JS-
    Frontend prueft (apps/frontend/index.html), nicht ein React-Bundle."""
    assert "id=\"app\"" not in served_index or "vite" not in served_index.lower()
    assert "MemorySettings.jsx" not in served_index


def test_served_index_contains_memory_governance_ui(served_index):
    assert 'id="memory-facts-card"' in served_index
    assert 'id="memory-facts-list"' in served_index
    assert "Mein persönliches Gedächtnis" in served_index
    assert "Unternehmenswissen" in served_index


def test_served_index_has_in_app_confirmation_dialog_not_window_confirm(served_index):
    assert 'id="memory-delete-modal"' in served_index
    assert "Erinnerung löschen?" in served_index
    assert "Unternehmenswissen und alle anderen Erinnerungen sind davon nicht betroffen" in served_index
    # Kein natives Browser-confirm() fuer die Memory-Loeschung mehr.
    delete_flow_start = served_index.index("function openMemoryDeleteModal")
    delete_flow_end = served_index.index("function confirmMemoryDelete")
    delete_flow = served_index[delete_flow_start:delete_flow_end]
    assert "window.confirm(" not in delete_flow
    assert "confirm(" not in delete_flow


def test_served_frontend_javascript_uses_memory_facts_endpoint(served_index):
    assert "`${API}/memory/facts`" in served_index
    assert 'method:"DELETE"' in served_index
    assert "async function loadMemoryFacts()" in served_index
    assert "async function confirmMemoryDelete()" in served_index


def test_delete_function_reachable_from_rendered_list_button(served_index):
    """Der Loesch-Button im gerenderten Fact-Eintrag muss tatsaechlich zur
    Loeschfunktion fuehren: Button -> Bestaetigungsdialog -> DELETE-Aufruf."""
    assert "onclick=\"openMemoryDeleteModal(${f.id})\"" in served_index
    assert 'onclick="confirmMemoryDelete()"' in served_index
    assert "openMemoryDeleteModal" in served_index
    assert "confirmMemoryDelete" in served_index


def test_served_frontend_shows_required_states(served_index):
    idx = served_index
    assert "Lädt…" in idx
    assert "AILIZA hat sich bisher nichts Persönliches über Sie gemerkt." in idx
    assert "konnten" in idx and "geladen werden" in idx  # Ladefehler-Text
    assert "Wird gelöscht…" in idx
    assert "wurde gelöscht" in idx  # Erfolgsmeldung
    assert "konnte nicht gelöscht werden" in idx  # Loeschfehler


def test_served_frontend_shows_no_technical_error_details_to_user(served_index):
    start = served_index.index("async function loadMemoryFacts()")
    end = served_index.index("async function confirmMemoryDelete()")
    memory_js = served_index[start:end]
    assert "Traceback" not in memory_js
    assert "stack" not in memory_js.lower()
