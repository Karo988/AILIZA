"""AP-MEMGOV-UI-001: statische Frontend-Pruefungen fuer MemorySettings.

Das Frontend definiert aktuell keinen eigenen Test-Runner. Diese Tests halten
die geforderten UI-Verhalten als gleichwertige Repo-Pruefung fest.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps" / "frontend" / "src" / "components" / "MemorySettings.jsx"
APP = ROOT / "apps" / "frontend" / "src" / "App.jsx"


def _component() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_memory_settings_is_bound_into_settings_page():
    app = APP.read_text(encoding="utf-8")
    assert 'import MemorySettings from "./components/MemorySettings"' in app
    assert "<MemorySettings />" in app


def test_memory_settings_uses_api_fetch_and_real_endpoints_only():
    source = _component()
    assert 'import { apiFetch } from "../api"' in source
    assert 'apiFetch("/memory/facts")' in source
    assert 'apiFetch(`/memory/facts/${fact.id}`, { method: "DELETE" })' in source
    assert "Beispiel" not in source
    assert "mock" not in source.lower()


def test_memory_settings_has_loading_state():
    source = _component()
    assert "Memory-Facts werden geladen" in source
    assert "disabled={loading}" in source


def test_memory_settings_renders_successful_fact_fields():
    source = _component()
    for field in ("fact.title", "fact.content", "fact.scope", "fact.purpose", "fact.category", "fact.status", "fact.created_at"):
        assert field in source


def test_memory_settings_has_empty_state():
    source = _component()
    assert "Es sind keine gespeicherten Erinnerungen vorhanden." in source
    assert "facts.length === 0" in source


def test_memory_settings_requires_delete_confirmation():
    source = _component()
    assert "window.confirm" in source
    assert "Diese Erinnerung wirklich loeschen?" in source


def test_memory_settings_shows_delete_loading_state_and_refreshes_after_success():
    source = _component()
    assert "setDeletingId(fact.id)" in source
    assert "Loesche ..." in source
    assert "await loadFacts()" in source


def test_memory_settings_handles_load_errors():
    source = _component()
    assert "Memory-Facts konnten nicht geladen werden." in source
    assert "setError" in source


def test_memory_settings_handles_delete_errors():
    source = _component()
    assert "Die Erinnerung konnte nicht geloescht werden." in source
    assert "finally" in source
    assert "setDeletingId(null)" in source


def test_memory_settings_imports_responsive_styles():
    source = _component()
    css = ROOT / "apps" / "frontend" / "src" / "components" / "MemorySettings.css"
    assert 'import "./MemorySettings.css"' in source
    styles = css.read_text(encoding="utf-8")
    assert "@media" in styles
    assert "max-width: 640px" in styles
