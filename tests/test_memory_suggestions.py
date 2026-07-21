"""Mini-PR 3: Kontrolliertes sichtbares Lernen (memory_suggestions).

Scope (siehe docs/DATABASE_MEMORY_GOVERNANCE_V1.md, Mini-PR 3):
Vorschlaege statt heimliches Lernen. Erkannte Information -> Entscheidung ->
Vorschlag/temporaer/verwerfen/blockieren. Nur bestaetigte Vorschlaege werden
zu memory_items. Keine UI, kein pgvector, kein Wissensgraph, keine freie
LLM-Extraktion.

WICHTIG (gestapelte PR): baut auf claude/memory-core-schema (PR #44) auf.
Nicht mergen, bevor PR #44 gemergt ist.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest

from apps.backend.database import (
    metadata_obj, engine, init_db, create_user, upsert_user_settings,
    memory_suggestions, memory_items, memory_visibility,
    decide_memory_storage, create_memory_suggestion,
    list_memory_suggestions_for_user, confirm_memory_suggestion,
    reject_memory_suggestion, get_memory_item,
    MemoryValidationError,
)


@pytest.fixture(autouse=True)
def fresh_db():
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _make_user(user_id: str = "alice", speichermodus: str = "immer_fragen") -> None:
    create_user(user_id=user_id, tenant_id="default", role="user", hashed_password="hash")
    upsert_user_settings(user_id, "default", speichermodus=speichermodus)


# ── Testgruppe 1: Migration ──────────────────────────────────────────────────

def test_suggestions_table_created_with_required_fields():
    cols = {c.name for c in memory_suggestions.columns}
    for f in ("user_id", "tenant_id", "suggested_scope", "suggested_title",
              "suggested_content", "suggested_purpose", "source_type", "status",
              "risk_level", "requires_admin_approval", "created_at", "expires_at"):
        assert f in cols, f"Feld fehlt: {f}"


def test_invalid_status_rejected():
    _make_user("alice")
    with pytest.raises(MemoryValidationError):
        create_memory_suggestion(
            user_id="alice", tenant_id="default", suggested_scope="user_memory",
            suggested_title="x", suggested_content="y", suggested_purpose="z",
            source_type="user_confirmation", status="irgendwas",
        )


def test_invalid_risk_level_rejected():
    _make_user("alice")
    with pytest.raises(MemoryValidationError):
        create_memory_suggestion(
            user_id="alice", tenant_id="default", suggested_scope="user_memory",
            suggested_title="x", suggested_content="y", suggested_purpose="z",
            source_type="user_confirmation", risk_level="extrem",
        )


# ── Testgruppe 2: Speichermodi ───────────────────────────────────────────────

def test_nie_automatisch_creates_no_automatic_suggestion():
    _make_user("alice", speichermodus="nie_automatisch")
    decision = decide_memory_storage(
        user_id="alice", tenant_id="default",
        info_kind="user_knowledge", reusable=True, has_source=True,
        user_initiated=False,
    )
    assert decision == "temporary_only"


def test_nie_automatisch_allows_explicit_user_action():
    _make_user("alice", speichermodus="nie_automatisch")
    decision = decide_memory_storage(
        user_id="alice", tenant_id="default",
        info_kind="user_knowledge", reusable=True, has_source=True,
        user_initiated=True,  # Nutzer hat explizit "merken" ausgeloest
    )
    assert decision == "create_user_memory_suggestion"


def test_immer_fragen_creates_suggestion_not_direct_item():
    _make_user("alice", speichermodus="immer_fragen")
    decision = decide_memory_storage(
        user_id="alice", tenant_id="default",
        info_kind="user_knowledge", reusable=True, has_source=True,
    )
    assert decision == "create_user_memory_suggestion"
    # Und: die Entscheidung selbst legt NIE direkt ein memory_item an.
    from sqlalchemy import select
    with engine.begin() as conn:
        rows = conn.execute(select(memory_items)).mappings().all()
    assert len(rows) == 0


def test_projektbezogen_fragen_requires_project():
    _make_user("alice", speichermodus="projektbezogen_fragen")
    without_project = decide_memory_storage(
        user_id="alice", tenant_id="default",
        info_kind="user_knowledge", reusable=True, has_source=True,
        project_id=None,
    )
    with_project = decide_memory_storage(
        user_id="alice", tenant_id="default",
        info_kind="user_knowledge", reusable=True, has_source=True,
        project_id="proj-1",
    )
    assert without_project == "temporary_only"
    assert with_project == "create_user_memory_suggestion"


# ── Testgruppe 3: Datenschutz/Blockierung ────────────────────────────────────

def test_secrets_are_blocked():
    _make_user("alice")
    for text in ("Mein API Key ist sk-abcdefghijklmnop123456",
                 "Passwort: geheim123",
                 "Token: eyJhbGciOiJIUzI1NiJ9.abc.def"):
        decision = decide_memory_storage(
            user_id="alice", tenant_id="default",
            info_kind="user_knowledge", reusable=True, has_source=True,
            content=text,
        )
        assert decision == "block_sensitive", f"Nicht blockiert: {text[:20]}"


def test_sensitive_categories_never_stored():
    _make_user("alice")
    decision = decide_memory_storage(
        user_id="alice", tenant_id="default",
        info_kind="sensitive", reusable=True, has_source=True,
    )
    assert decision in ("block_sensitive", "temporary_only")


def test_settings_info_routed_to_settings_not_memory():
    _make_user("alice")
    decision = decide_memory_storage(
        user_id="alice", tenant_id="default",
        info_kind="setting", reusable=True, has_source=True,
    )
    assert decision == "store_as_setting"


def test_non_reusable_info_discarded():
    _make_user("alice")
    decision = decide_memory_storage(
        user_id="alice", tenant_id="default",
        info_kind="user_knowledge", reusable=False, has_source=True,
    )
    assert decision in ("discard", "temporary_only")


def test_no_source_means_no_permanent_storage():
    _make_user("alice")
    decision = decide_memory_storage(
        user_id="alice", tenant_id="default",
        info_kind="user_knowledge", reusable=True, has_source=False,
    )
    assert decision in ("discard", "temporary_only")


def test_blocked_suggestion_stores_no_raw_content():
    _make_user("alice")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Blockiert", suggested_content="sk-geheimerkey12345678",
        suggested_purpose="Test", source_type="user_confirmation",
        status="blocked", risk_level="blocked",
    )
    assert "sk-geheimerkey" not in (s["suggested_content"] or "")


# ── Testgruppe 4: Suggestions ────────────────────────────────────────────────

def test_user_memory_suggestion_defaults():
    _make_user("alice")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Compliance-Hinweise", suggested_content="Nutzer moechte Compliance-Hinweise immer sehen.",
        suggested_purpose="Antwortverhalten anpassen", source_type="user_confirmation",
    )
    assert s["status"] == "open"
    assert s["risk_level"] == "low"
    assert s["requires_admin_approval"] is False


def test_company_memory_suggestion_requires_admin():
    _make_user("alice")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="company_memory",
        suggested_title="DATEV", suggested_content="Unsere Firma nutzt DATEV.",
        suggested_purpose="Buchhaltungs-Kontext", source_type="user_confirmation",
    )
    assert s["requires_admin_approval"] is True
    assert s["status"] == "needs_admin_approval"


def test_suggestion_without_purpose_rejected():
    _make_user("alice")
    with pytest.raises(MemoryValidationError):
        create_memory_suggestion(
            user_id="alice", tenant_id="default", suggested_scope="user_memory",
            suggested_title="x", suggested_content="y", suggested_purpose=None,
            source_type="user_confirmation",
        )


def test_suggestion_without_source_type_rejected():
    _make_user("alice")
    with pytest.raises(MemoryValidationError):
        create_memory_suggestion(
            user_id="alice", tenant_id="default", suggested_scope="user_memory",
            suggested_title="x", suggested_content="y", suggested_purpose="z",
            source_type=None,
        )


def test_list_suggestions_only_own():
    _make_user("alice")
    _make_user("bob")
    create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Alice-Vorschlag", suggested_content="x",
        suggested_purpose="z", source_type="user_confirmation",
    )
    assert len(list_memory_suggestions_for_user("alice", "default")) == 1
    assert len(list_memory_suggestions_for_user("bob", "default")) == 0


# ── Testgruppe 5: Bestaetigen/Ablehnen ───────────────────────────────────────

def test_confirm_creates_source_item_and_visibility():
    from sqlalchemy import select

    _make_user("alice")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Kurze Antworten", suggested_content="Nutzer bevorzugt kurze Antworten.",
        suggested_purpose="Antwortstil", source_type="user_confirmation",
    )
    result = confirm_memory_suggestion(s["id"], confirmed_by="alice")
    item = get_memory_item(result["memory_item_id"])
    assert item is not None
    assert item["status"] == "active"
    assert item["source_id"] is not None
    with engine.begin() as conn:
        vis = conn.execute(
            select(memory_visibility).where(memory_visibility.c.memory_item_id == item["id"])
        ).mappings().first()
    assert vis["visibility_scope"] == "private"
    # Suggestion selbst ist jetzt confirmed:
    updated = [x for x in list_memory_suggestions_for_user("alice", "default", status=None)
               if x["id"] == s["id"]][0]
    assert updated["status"] == "confirmed"


def test_reject_creates_no_item():
    from sqlalchemy import select

    _make_user("alice")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="Abgelehnt", suggested_content="x",
        suggested_purpose="z", source_type="user_confirmation",
    )
    reject_memory_suggestion(s["id"], reviewed_by="alice")
    with engine.begin() as conn:
        rows = conn.execute(select(memory_items)).mappings().all()
    assert len(rows) == 0
    updated = [x for x in list_memory_suggestions_for_user("alice", "default", status=None)
               if x["id"] == s["id"]][0]
    assert updated["status"] == "rejected"


def test_company_memory_needs_admin_before_confirm():
    _make_user("alice")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="company_memory",
        suggested_title="DATEV", suggested_content="Firma nutzt DATEV.",
        suggested_purpose="Kontext", source_type="user_confirmation",
    )
    # Ohne Admin-Rolle: Bestaetigung schlaegt fehl.
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(s["id"], confirmed_by="alice", reviewer_role="user")
    # Mit Admin-Rolle: klappt und erzeugt memory_item.
    result = confirm_memory_suggestion(s["id"], confirmed_by="karo-admin", reviewer_role="admin")
    item = get_memory_item(result["memory_item_id"])
    assert item["scope"] == "company_memory"
    assert item["status"] == "active"


def test_confirm_rejected_suggestion_fails():
    _make_user("alice")
    s = create_memory_suggestion(
        user_id="alice", tenant_id="default", suggested_scope="user_memory",
        suggested_title="x", suggested_content="y",
        suggested_purpose="z", source_type="user_confirmation",
    )
    reject_memory_suggestion(s["id"], reviewed_by="alice")
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(s["id"], confirmed_by="alice")
