"""
M0: Quarantaene des technischen Memory-Prototyp-Routers
(apps/backend/routers/memory.py + apps/backend/memory/).

Ausgangslage (Phase-1-Diagnose): der Router ist im aktuellen main NICHT
registriert und es wurde kein interner Aufrufer gefunden. Sein
urspruenglicher Import `from ..auth import require_admin` war fehlerhaft
(kein solches Symbol im auth-Package, nur in der separaten, veralteten
Datei apps/backend/auth.py) und haette bei einer Einbindung sofort einen
ImportError ausgeloest.

Diese Tests pruefen NICHT die fachliche Funktion des Prototyps (die ist
bewusst nicht Teil dieses PRs), sondern ausschliesslich:
  1. dass die produktive App keine /memory-Routen exponiert,
  2. dass der Router-Modul-Import ohne ImportError funktioniert (kein
     Bezug mehr auf das nicht existierende require_admin-Symbol),
  3. dass eine isolierte Einbindung des Routers per Fail-Closed-Guard
     JEDEN Zugriff verweigert -- unabhaengig von Credentials/Rolle,
  4. dass kein Bezug zum alten API-Key-Auth-Modul (apps/backend/auth.py)
     mehr besteht.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")


def test_production_app_has_no_memory_routes():
    from apps.backend.main import app
    memory_paths = [r.path for r in app.routes if getattr(r, "path", "").startswith("/memory")]
    assert memory_paths == [], f"Unerwartete /memory-Routen in der produktiven App: {memory_paths}"


def test_memory_router_module_imports_without_error():
    """Der urspruengliche Import `from ..auth import require_admin` waere
    bei Einbindung fehlgeschlagen (require_admin existiert nicht im
    auth-Package). Nach der Quarantaene muss der Modul-Import sauber
    funktionieren."""
    import importlib
    module = importlib.import_module("apps.backend.routers.memory")
    assert hasattr(module, "router")
    assert hasattr(module, "_quarantine_guard")


def test_memory_router_does_not_reference_legacy_api_key_auth_module():
    """Der Modul-Docstring darf den historischen Fehler ERWAEHNEN
    (Dokumentation), aber im tatsaechlichen Code (nicht im Docstring)
    darf kein Import/Aufruf von require_admin/require_operator/dem
    auth.py-Modul mehr vorkommen."""
    import ast
    import inspect
    from apps.backend.routers import memory as memory_router_module
    source = inspect.getsource(memory_router_module)
    tree = ast.parse(source)
    # Modul-Docstring (erstes Statement, falls ein Constant-String) entfernen
    body = tree.body[1:] if (tree.body and isinstance(tree.body[0], ast.Expr)
                              and isinstance(tree.body[0].value, ast.Constant)) else tree.body
    code_only = ast.unparse(ast.Module(body=body, type_ignores=[]))
    assert "require_admin" not in code_only
    assert "require_operator" not in code_only
    assert "from ..auth import" not in code_only


def test_isolated_router_denies_all_endpoints_by_default():
    """Selbst bei einer (hier bewusst isolierten, nicht-produktiven)
    Einbindung in eine frische FastAPI-Testapp muessen ALLE Endpunkte des
    Prototyp-Routers mit 503 (Fail-Closed) antworten -- unabhaengig von
    Credentials, Methode oder Payload."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from apps.backend.routers.memory import router as memory_prototype_router

    isolated_app = FastAPI()
    isolated_app.include_router(memory_prototype_router)
    client = TestClient(isolated_app)

    future_iso = "2099-01-01T00:00:00+00:00"
    create_payload = {
        "purpose": "task", "content_hash": "abc123", "visibility": "user",
        "role_required": "admin", "retention_until": future_iso, "sensitive": True,
    }

    responses = [
        client.post("/memory", json=create_payload),
        client.post("/memory", json=create_payload, headers={"Authorization": "Bearer faketoken"}),
        client.get("/memory"),
        client.get("/memory/some-id"),
        client.delete("/memory/some-id"),
        client.post("/memory/purge"),
        client.post("/memory/purge", headers={"Authorization": "Bearer faketoken"}),
        client.post("/memory/purge", headers={"X-API-Key": "irgendein-key"}),
    ]
    for r in responses:
        assert r.status_code == 503, f"Erwartet 503 (Fail-Closed), war {r.status_code}: {r.text}"


def test_technical_memory_package_distinct_from_business_memory_core():
    """Abgrenzung: apps/backend/memory/ (technischer Hash-only-Prototyp)
    darf nicht mit dem fachlichen Memory-Kern (memory_items/
    memory_sources/memory_visibility/memory_suggestions in database.py)
    vermischt werden -- unterschiedliche Module, unterschiedliche
    Datenhaltung."""
    from apps.backend.memory.models import MemoryEntry
    from apps.backend.database import memory_items
    assert MemoryEntry is not memory_items
    # Der technische Prototyp speichert nur Hash + Metadaten, nie Rohinhalt.
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(MemoryEntry)}
    assert "content_hash" in field_names
    assert "content" not in field_names
