"""Block D0: Demo-/Nachschlagewerk-Ansicht -- reine Anzeigelogik.

Scope: Nutzbarkeits-Label je Status, Sortierung (approved zuerst, dann
pending_review, dann blocked/deleted/expired -- je Gruppe neueste zuerst),
Kategorie-Whitelist. Keine automatische Kategorisierung, keine
Datenbankschreibzugriffe in diesem Modul.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from apps.backend.knowledge.demo_view import (
    usability_label_for_status, status_explanation, sort_sources_for_demo,
    is_usable_in_chat, PUBLIC_SOURCE_FIELDS, to_public_source_view,
)


def _source(id_, status, created_at, **overrides):
    base = {
        "id": id_, "tenant_id": "default", "uploaded_by": "alice",
        "source_type": "txt", "title": f"Quelle {id_}", "original_filename": f"q{id_}.txt",
        "storage_path": f"/data/uploads/default/{id_}.txt", "content_hash": "abc",
        "mime_type": "text/plain", "status": status, "visibility_scope": "private",
        "category": None, "approved_by": None, "approved_at": None, "expires_at": None,
        "created_at": created_at, "updated_at": created_at, "chunk_count": 0,
    }
    base.update(overrides)
    return base


# -- Testgruppe 1: Nutzbarkeits-Label -----------------------------------------

def test_usability_label_approved():
    assert usability_label_for_status("approved") == "Nutzbar im Chat"


def test_usability_label_pending_review():
    assert usability_label_for_status("pending_review") == "Wartet auf Prüfung"


def test_usability_label_blocked():
    assert usability_label_for_status("blocked") == "Blockiert"


def test_usability_label_deleted_and_expired():
    assert usability_label_for_status("deleted") == "Nicht aktiv"
    assert usability_label_for_status("expired") == "Nicht aktiv"


def test_usability_label_uploaded_is_not_usable():
    # "uploaded" ist noch nicht geprueft/freigegeben -- fail-closed
    # Anzeige, kein "Nutzbar im Chat".
    assert usability_label_for_status("uploaded") != "Nutzbar im Chat"


def test_is_usable_in_chat_only_true_for_approved():
    assert is_usable_in_chat("approved") is True
    for status in ("pending_review", "blocked", "deleted", "expired", "uploaded"):
        assert is_usable_in_chat(status) is False


# -- Testgruppe 2: Status-Erklaerung (nutzerfreundlich, keine Technik) -------

def test_status_explanation_is_user_friendly():
    for status in ("approved", "pending_review", "blocked", "deleted", "expired", "uploaded"):
        text = status_explanation(status)
        assert text
        forbidden = ("traceback", "exception", "sql", "database", "regex")
        for token in forbidden:
            assert token not in text.lower()


# -- Testgruppe 3: Sortierung -------------------------------------------------

def test_sort_approved_first_then_pending_then_inactive():
    now = datetime.now(timezone.utc)
    sources = [
        _source(1, "blocked", now),
        _source(2, "approved", now),
        _source(3, "pending_review", now),
        _source(4, "deleted", now),
    ]
    ordered = sort_sources_for_demo(sources)
    assert [s["id"] for s in ordered] == [2, 3, 1, 4] or (
        ordered[0]["status"] == "approved" and ordered[1]["status"] == "pending_review"
    )
    assert ordered[0]["status"] == "approved"
    assert ordered[1]["status"] == "pending_review"
    assert ordered[-1]["status"] in ("blocked", "deleted", "expired")


def test_sort_newest_first_within_same_status_group():
    older = datetime.now(timezone.utc) - timedelta(days=5)
    newer = datetime.now(timezone.utc)
    sources = [
        _source(1, "approved", older),
        _source(2, "approved", newer),
    ]
    ordered = sort_sources_for_demo(sources)
    assert [s["id"] for s in ordered] == [2, 1]


# -- Testgruppe 4: Oeffentliche Ansicht -- keine verbotenen Felder -----------

def test_public_source_view_excludes_storage_path_and_chunk_text():
    source = _source(1, "approved", datetime.now(timezone.utc), chunk_count=3)
    view = to_public_source_view(source)
    assert "storage_path" not in view
    assert "chunk_text" not in view
    assert view["usable_in_chat"] is True
    assert view["usability_label"] == "Nutzbar im Chat"
    assert view["chunk_count"] == 3
    assert view["source_id"] == 1


def test_public_source_view_blocked_not_usable():
    source = _source(2, "blocked", datetime.now(timezone.utc))
    view = to_public_source_view(source)
    assert view["usable_in_chat"] is False
    assert view["usability_label"] == "Blockiert"


def test_public_source_view_includes_only_documented_fields():
    source = _source(3, "approved", datetime.now(timezone.utc))
    view = to_public_source_view(source)
    assert set(view.keys()) == PUBLIC_SOURCE_FIELDS


# -- Testgruppe 5: Kategorie-Whitelist (aus ingestion.py wiederverwendet) ----

def test_allowed_demo_categories_match_ingestion_module():
    from apps.backend.knowledge.ingestion import ALLOWED_DEMO_CATEGORIES
    assert "Allgemein" in ALLOWED_DEMO_CATEGORIES
    assert "Vertrag/Compliance" in ALLOWED_DEMO_CATEGORIES
    assert len(ALLOWED_DEMO_CATEGORIES) == 7
