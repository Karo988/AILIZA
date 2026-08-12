"""Sicherheitstests zu B-MEM-1, B-MEM-2 und B-MEM-3.

Diese Tests belegen die Behebung der drei praktisch reproduzierten Befunde:

B-MEM-1  Gesperrte Datenklassen (CREDENTIALS/SPECIAL_CATEGORY/HR/LEGAL)
         griffen nur in reflection_skill.store_fact(). create_memory_item(),
         create_memory_suggestion() und confirm_memory_suggestion() waren
         ungeschuetzt.
B-MEM-2  Direktzugriff ueber die ID war mandantenuebergreifend moeglich
         (lesen, Sichtbarkeit aendern, loeschen, ablehnen, bestaetigen).
B-MEM-3  Memory-Aktionen liefen nie durch evaluate_permission().

Jeder Test prueft eine Umgehungsmoeglichkeit, nicht nur den Gutfall.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

TENANT_A = "mandant-a"
TENANT_B = "mandant-b"


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _source(tenant_id: str) -> int:
    from apps.backend.database import create_memory_source
    return create_memory_source(tenant_id, "user_confirmation")["id"]


def _item(tenant_id: str, owner: str, *, title: str = "Titel",
          content: str = "Unverfaenglicher Inhalt") -> dict:
    from apps.backend.database import create_memory_item
    return create_memory_item(
        tenant_id, "user_memory", title, content,
        purpose="Test", source_id=_source(tenant_id),
        owner_user_id=owner, status="active",
    )


# ── B-MEM-1: gesperrte Datenklassen an ALLEN Schreibpfaden ────────────────

@pytest.mark.parametrize("data_class", ["credentials", "special_category", "hr", "legal"])
def test_blocked_class_rejected_on_create_memory_item(data_class):
    """Jede der vier gesperrten Klassen muss create_memory_item() abweisen --
    auch wenn der Klassifizierer den Text nicht selbst erkennt. Deshalb wird
    die Klasse hier ausdruecklich mitgegeben (declared_data_classes)."""
    from apps.backend.database import create_memory_item, MemoryValidationError

    with pytest.raises(MemoryValidationError) as exc:
        create_memory_item(
            TENANT_A, "user_memory", "Titel", "Inhalt",
            purpose="Test", source_id=_source(TENANT_A),
            owner_user_id="alice", status="active",
            declared_data_classes=[data_class],
        )
    assert data_class in str(exc.value)


def test_secret_content_rejected_on_create_memory_item():
    """Die bestehende Secret-Heuristik muss auch im Memory-Kern greifen --
    vorher schuetzte sie nur den Vorschlagspfad."""
    from apps.backend.database import create_memory_item, MemoryValidationError

    with pytest.raises(MemoryValidationError):
        create_memory_item(
            TENANT_A, "user_memory", "Zugang",
            "Das Passwort: sk-ant-api03-XXXXXXXXXXXX",
            purpose="Test", source_id=_source(TENANT_A),
            owner_user_id="alice", status="active",
        )


def test_blocked_class_suggestion_stores_no_raw_content():
    """Vorschlaege werden datensparsam blockiert statt zu werfen -- der
    Rohinhalt darf dabei niemals in der Datenbank landen."""
    from apps.backend.database import create_memory_suggestion

    geheim = "Das Passwort: sk-ant-api03-XXXXXXXXXXXX"
    s = create_memory_suggestion(
        user_id="alice", tenant_id=TENANT_A, suggested_scope="user_memory",
        suggested_title="Zugang", suggested_content=geheim,
        suggested_purpose="Test", source_type="user_confirmation",
    )
    assert s["status"] == "blocked"
    assert s["risk_level"] == "blocked"
    assert geheim not in (s["suggested_content"] or "")


def test_confirm_path_cannot_bypass_content_policy():
    """Der Bestaetigungspfad darf die Sperre nicht umgehen: ein Vorschlag mit
    gesperrtem Inhalt wird blockiert und ist damit nicht bestaetigbar."""
    from apps.backend.database import (
        create_memory_suggestion, confirm_memory_suggestion, MemoryValidationError,
    )

    s = create_memory_suggestion(
        user_id="alice", tenant_id=TENANT_A, suggested_scope="user_memory",
        suggested_title="Zugang", suggested_content="Das Passwort: sk-ant-api03-XXXX",
        suggested_purpose="Test", source_type="user_confirmation",
    )
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(s["id"], confirmed_by="alice", tenant_id=TENANT_A)


def test_harmless_content_still_passes():
    """Gegenprobe: die Sperre darf den Normalfall nicht blockieren."""
    from apps.backend.database import create_memory_item

    item = _item(TENANT_A, "alice", content="Der Kunde bevorzugt Rueckrufe am Vormittag.")
    assert item is not None and item["status"] == "active"


# ── B-MEM-2: Mandantentrennung ────────────────────────────────────────────

def test_foreign_tenant_item_not_readable_by_id():
    from apps.backend.database import get_memory_item

    fremd = _item(TENANT_B, "bob")
    assert get_memory_item(fremd["id"], tenant_id=TENANT_A) is None
    assert get_memory_item(fremd["id"], tenant_id=TENANT_B) is not None


def test_foreign_tenant_item_not_deletable():
    from apps.backend.database import (
        get_memory_item, mark_memory_item_deleted, MemoryValidationError,
    )

    fremd = _item(TENANT_B, "bob")
    with pytest.raises(MemoryValidationError):
        mark_memory_item_deleted(fremd["id"], tenant_id=TENANT_A)
    assert get_memory_item(fremd["id"], tenant_id=TENANT_B)["status"] == "active"


def test_foreign_tenant_visibility_not_changeable():
    from apps.backend.database import set_memory_visibility, MemoryValidationError

    fremd = _item(TENANT_B, "bob")
    with pytest.raises(MemoryValidationError):
        set_memory_visibility(fremd["id"], tenant_id=TENANT_A,
                              visibility_scope="organization",
                              allowed_org_id=TENANT_A)


def test_foreign_tenant_suggestion_not_confirmable_or_rejectable():
    from apps.backend.database import (
        create_memory_suggestion, confirm_memory_suggestion,
        reject_memory_suggestion, MemoryValidationError,
    )

    s = create_memory_suggestion(
        user_id="bob", tenant_id=TENANT_B, suggested_scope="user_memory",
        suggested_title="B-Wissen", suggested_content="Interna Mandant B",
        suggested_purpose="Test", source_type="user_confirmation",
    )
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(s["id"], confirmed_by="alice", tenant_id=TENANT_A)
    with pytest.raises(MemoryValidationError):
        reject_memory_suggestion(s["id"], reviewed_by="alice", tenant_id=TENANT_A)


def _legacy_zeile(owner="alice", inhalt="Altbestand"):
    """Legt eine mandantenlose Altzeile direkt an -- create_memory_item()
    verweigert das inzwischen bewusst (keine NEUEN Altdaten)."""
    from apps.backend.database import engine, memory_items
    from sqlalchemy import insert
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        r = conn.execute(insert(memory_items).values(
            tenant_id=None, scope="user_memory", owner_user_id=owner,
            title="Alt", content=inhalt, category=None, purpose="p",
            source_id=None, status="active", created_at=now, updated_at=now,
        ))
        return r.inserted_primary_key[0]


def test_no_new_tenantless_items_can_be_created():
    """Keine NEUEN mandantenlosen Zeilen: sie waeren sofort quarantaenisiert
    und damit fuer ihren Besitzer nicht mehr korrigier- oder loeschbar."""
    from apps.backend.database import create_memory_item, MemoryValidationError

    for leer in (None, "", "  "):
        with pytest.raises(MemoryValidationError):
            create_memory_item(
                leer, "user_memory", "Titel", "Inhalt",
                purpose="Test", source_id=_source(TENANT_A),
                owner_user_id="alice", status="active",
            )


def test_legacy_null_tenant_item_is_quarantined_everywhere():
    """B-MEM-4: Altdaten ohne Mandant sind aus ALLEN normalen Pfaden
    ausgenommen -- lesen, listen, exportieren, loeschen. Es wird nichts
    zugeordnet und nichts geloescht; der Bestand bleibt nachweisbar."""
    from apps.backend.database import (
        get_memory_item, list_active_memory_items_for_user, export_user_data,
        count_unassigned_memory_items,
    )

    alt_id = _legacy_zeile(owner="alice", inhalt="ALTBESTAND-GEHEIM")

    assert get_memory_item(alt_id, tenant_id=TENANT_A) is None
    assert get_memory_item(alt_id, tenant_id=TENANT_B) is None
    assert list_active_memory_items_for_user("alice", TENANT_A) == []
    assert list_active_memory_items_for_user("alice", TENANT_B) == []
    assert "ALTBESTAND-GEHEIM" not in str(export_user_data("alice", TENANT_A))

    bestand = count_unassigned_memory_items()
    assert bestand["anzahl"] == 1
    assert "alice" in bestand["betroffene_owner_user_ids"]


def test_account_deletion_does_not_touch_quarantined_items():
    """Keine automatische Loeschung des Altbestands -- auch nicht ueber die
    Kontoloeschung eines gleichnamigen Nutzers."""
    from apps.backend.database import (
        delete_own_account_data, count_unassigned_memory_items, create_user,
    )

    _legacy_zeile(owner="alice", inhalt="ALTBESTAND")
    create_user(user_id="alice", tenant_id=TENANT_B, role="user", hashed_password="h")
    delete_own_account_data("alice", TENANT_B)
    assert count_unassigned_memory_items()["anzahl"] == 1


def test_listing_does_not_leak_across_tenants():
    from apps.backend.database import (
        list_active_memory_items_for_user, list_active_memory_items_for_org,
        create_memory_item,
    )

    _item(TENANT_A, "alice", title="A-Wissen")
    _item(TENANT_B, "bob", title="B-Wissen")
    create_memory_item(
        TENANT_B, "company_memory", "B-Firma", "Firmenwissen B",
        purpose="Test", source_id=_source(TENANT_B), status="active",
    )

    titel_a = {i["title"] for i in list_active_memory_items_for_user("alice", TENANT_A)}
    assert titel_a == {"A-Wissen"}
    assert list_active_memory_items_for_user("alice", TENANT_B) == []
    assert {i["title"] for i in list_active_memory_items_for_org(TENANT_A)} == set()
    assert {i["title"] for i in list_active_memory_items_for_org(TENANT_B)} == {"B-Firma"}


# ── B-MEM-3: zentraler Permission-Evaluator ───────────────────────────────

def _actor(user_id: str, tenant_id: str, role: str = "user"):
    from apps.backend.auth.jwt_handler import TokenData
    return TokenData(user_id=user_id, tenant_id=tenant_id, role=role)


@pytest.mark.parametrize("action", [
    "MEMORY_ITEM_READ", "MEMORY_ITEM_DELETE", "MEMORY_VISIBILITY_UPDATE",
    "MEMORY_SUGGESTION_CONFIRM", "MEMORY_SUGGESTION_REJECT",
])
def test_owner_actions_denied_for_foreign_owner(action):
    from apps.backend import permissions

    result = permissions.evaluate_permission(
        action=getattr(permissions, action),
        actor=_actor("alice", TENANT_A),
        tenant_id=TENANT_A,
        resource_type="memory_item", resource_id="1",
        resource_owner_user_id="bob",
    )
    assert result.allowed is False


@pytest.mark.parametrize("action", [
    "MEMORY_ITEM_READ", "MEMORY_ITEM_DELETE", "MEMORY_VISIBILITY_UPDATE",
    "MEMORY_SUGGESTION_CONFIRM", "MEMORY_SUGGESTION_REJECT",
])
def test_owner_actions_allowed_for_own_resource(action):
    from apps.backend import permissions

    result = permissions.evaluate_permission(
        action=getattr(permissions, action),
        actor=_actor("alice", TENANT_A),
        tenant_id=TENANT_A,
        resource_type="memory_item", resource_id="1",
        resource_owner_user_id="alice",
    )
    assert result.allowed is True


def test_memory_action_denied_across_tenants():
    from apps.backend import permissions

    result = permissions.evaluate_permission(
        action=permissions.MEMORY_ITEM_READ,
        actor=_actor("alice", TENANT_A),
        tenant_id=TENANT_B,
        resource_type="memory_item", resource_id="1",
        resource_owner_user_id="alice",
    )
    assert result.allowed is False


def test_memory_action_denied_without_session():
    from apps.backend import permissions

    result = permissions.evaluate_permission(
        action=permissions.MEMORY_ITEM_READ,
        actor=None, tenant_id=TENANT_A,
        resource_type="memory_item", resource_id="1",
    )
    assert result.allowed is False
    assert result.reason_code == "NO_SESSION"


def test_memory_action_denied_for_unknown_role():
    from apps.backend import permissions

    result = permissions.evaluate_permission(
        action=permissions.MEMORY_ITEM_READ,
        actor=_actor("alice", TENANT_A, role="phantasierolle"),
        tenant_id=TENANT_A,
        resource_type="memory_item", resource_id="1",
        resource_owner_user_id="alice",
    )
    assert result.allowed is False
    assert result.reason_code == "UNKNOWN_ROLE"


def test_company_memory_action_requires_manager_role():
    """Ohne Eigentuemer (company_memory) entscheidet die Rolle."""
    from apps.backend import permissions

    als_user = permissions.evaluate_permission(
        action=permissions.MEMORY_ITEM_DELETE,
        actor=_actor("alice", TENANT_A, role="user"),
        tenant_id=TENANT_A, resource_type="memory_item", resource_id="1",
        resource_owner_user_id=None,
    )
    als_manager = permissions.evaluate_permission(
        action=permissions.MEMORY_ITEM_DELETE,
        actor=_actor("chef", TENANT_A, role="manager"),
        tenant_id=TENANT_A, resource_type="memory_item", resource_id="1",
        resource_owner_user_id=None,
    )
    assert als_user.allowed is False
    assert als_manager.allowed is True


def test_scope_transfer_is_always_denied():
    """Wissen darf nicht ohne ausdrueckliche Freigabe zwischen Ebenen wandern.
    Es gibt keinen freigegebenen Transferpfad -- auch nicht fuer Admins."""
    from apps.backend import permissions

    for rolle in ("user", "manager", "admin", "dsb"):
        result = permissions.evaluate_permission(
            action=permissions.MEMORY_SCOPE_TRANSFER,
            actor=_actor("alice", TENANT_A, role=rolle),
            tenant_id=TENANT_A, resource_type="memory_item", resource_id="1",
            resource_owner_user_id="alice",
        )
        assert result.allowed is False, f"Rolle {rolle} durfte transferieren"


def test_scope_transfer_denial_is_audited_without_content():
    from apps.backend import permissions
    from apps.backend.database import list_audit_entries

    permissions.evaluate_permission(
        action=permissions.MEMORY_SCOPE_TRANSFER,
        actor=_actor("alice", TENANT_A),
        tenant_id=TENANT_A, resource_type="memory_item", resource_id="42",
        resource_owner_user_id="alice",
    )
    treffer = [e for e in list_audit_entries(limit=20, tenant_id=TENANT_A)
               if e["action"] == "memory.scope_transfer_denied"]
    assert len(treffer) == 1
    md = treffer[0]["metadata"]
    assert md["resource_id"] == "42"
    for verboten in ("content", "prompt", "suggested_content", "secret"):
        assert verboten not in md


# ── Memory Scopes ─────────────────────────────────────────────────────────

def test_invalid_scope_rejected():
    from apps.backend.database import create_memory_item, MemoryValidationError

    for ungueltig in ("session", "personal", "project", "company", "help_glossary",
                      "learning_content", "beliebig"):
        with pytest.raises(MemoryValidationError):
            create_memory_item(
                TENANT_A, ungueltig, "Titel", "Inhalt",
                purpose="Test", source_id=_source(TENANT_A),
                owner_user_id="alice", status="active",
            )


# ── Befunde der unabhaengigen Gegenpruefung ───────────────────────────────
# Diese Tests decken acht Lücken ab, die eine zweite, unabhaengige Pruefung
# in der ERSTEN Fassung der Behebung gefunden hat.

def test_blocked_suggestion_also_discards_title_purpose_category():
    """Gegenpruefung 1 (HOCH): Nur der Inhalt wurde verworfen. Im Chat-Pfad
    ist der Titel der gekuerzte Rohprompt und enthielt denselben sensiblen
    Text."""
    from apps.backend.database import create_memory_suggestion

    geheim = "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI"
    s = create_memory_suggestion(
        user_id="alice", tenant_id=TENANT_A, suggested_scope="user_memory",
        suggested_title=f"Diagnose HIV-positiv {geheim}",
        suggested_content="harmlos",
        suggested_purpose=f"Zweck {geheim}",
        suggested_category=f"Kategorie {geheim}",
        source_type="user_confirmation",
    )
    assert s["status"] == "blocked"
    for feld in ("suggested_title", "suggested_content", "suggested_purpose",
                 "suggested_category"):
        assert geheim not in (s[feld] or ""), f"{feld} enthaelt noch das Geheimnis"
    assert "HIV" not in (s["suggested_title"] or "")


@pytest.mark.parametrize("leer", [None, "", "   "])
def test_empty_tenant_is_rejected_not_treated_as_null(leer):
    """Gegenpruefung 2 (HOCH): tenant_id=None wurde in SQL zu IS NULL und traf
    damit alle mandantenlosen Altdaten beliebiger Nutzer."""
    from apps.backend.database import (
        get_memory_item, mark_memory_item_deleted, reject_memory_suggestion,
        MemoryValidationError,
    )

    with pytest.raises(MemoryValidationError):
        get_memory_item(1, tenant_id=leer)
    with pytest.raises(MemoryValidationError):
        mark_memory_item_deleted(1, tenant_id=leer)
    with pytest.raises(MemoryValidationError):
        reject_memory_suggestion(1, reviewed_by="alice", tenant_id=leer)


def test_same_username_in_other_tenant_sees_nothing():
    """Gegenpruefung (HOCH): Derselbe user_id kann in mehreren Mandanten
    existieren. Weder ueber die ID noch ueber die Liste darf ein
    gleichnamiger Nutzer an mandantenlose Altdaten kommen."""
    from apps.backend.database import get_memory_item, list_active_memory_items_for_user

    alt_id = _legacy_zeile(owner="alice", inhalt="ALTDATEN-MANDANT-A")
    assert get_memory_item(alt_id, tenant_id=TENANT_A) is None
    assert get_memory_item(alt_id, tenant_id=TENANT_B) is None
    assert list_active_memory_items_for_user("alice", TENANT_B) == []


def test_purpose_and_category_go_through_content_policy():
    """Gegenpruefung 4 (MITTEL): purpose und category liefen an der Sperre
    vorbei und waren damit ein ungeprueter Schreibpfad."""
    from apps.backend.database import create_memory_item, MemoryValidationError

    for feld in ("purpose", "category"):
        kwargs = {
            "purpose": "Zweck", "category": None,
            "source_id": _source(TENANT_A), "owner_user_id": "alice",
            "status": "active",
        }
        kwargs[feld] = "Gesundheitsdaten: HIV-positiv, AWS_SECRET_ACCESS_KEY=AKIAXX"
        with pytest.raises(MemoryValidationError):
            create_memory_item(TENANT_A, "user_memory", "Titel", "Inhalt", **kwargs)


def test_foreign_user_in_same_tenant_cannot_confirm_suggestion():
    """Gegenpruefung 6 (MITTEL): Es wurde nur nach Mandant gefiltert, nicht
    nach Eigentuemer -- ein anderer Nutzer DESSELBEN Mandanten konnte einen
    fremden Vorschlag bestaetigen."""
    from apps.backend.database import (
        create_memory_suggestion, confirm_memory_suggestion,
        apply_confirmed_memory_suggestion, MemoryValidationError,
    )

    s = create_memory_suggestion(
        user_id="alice", tenant_id=TENANT_A, suggested_scope="user_memory",
        suggested_title="Alices Wissen", suggested_content="privat",
        suggested_purpose="Test", source_type="user_confirmation",
    )
    with pytest.raises(MemoryValidationError):
        confirm_memory_suggestion(s["id"], confirmed_by="mallory", tenant_id=TENANT_A)
    # Der oeffentliche Alias darf nicht schwaecher sein als das Original.
    with pytest.raises(MemoryValidationError):
        apply_confirmed_memory_suggestion(s["id"], confirmed_by="mallory",
                                          tenant_id=TENANT_A)
    # Der Eigentuemer selbst kann weiterhin bestaetigen.
    assert confirm_memory_suggestion(s["id"], confirmed_by="alice",
                                     tenant_id=TENANT_A)["memory_item_id"]


def test_manager_role_cannot_confirm_foreign_personal_suggestion():
    """Nachpruefung 5 (MITTEL): Die Rollen-Ausnahme galt pauschal und hob die
    Eigentuemerbindung auch fuer persoenliche Vorschlaege auf. Ein Manager
    konnte damit aus dem user_memory-Vorschlag eines fremden Nutzers einen
    Gedaechtniseintrag erzeugen."""
    from apps.backend.database import (
        create_memory_suggestion, confirm_memory_suggestion,
        apply_confirmed_memory_suggestion, MemoryValidationError,
    )

    s = create_memory_suggestion(
        user_id="alice", tenant_id=TENANT_A, suggested_scope="user_memory",
        suggested_title="Alices Privates", suggested_content="privat",
        suggested_purpose="Test", source_type="user_confirmation",
    )
    for rolle in ("manager", "admin"):
        with pytest.raises(MemoryValidationError):
            confirm_memory_suggestion(s["id"], confirmed_by="chef",
                                      reviewer_role=rolle, tenant_id=TENANT_A)
        with pytest.raises(MemoryValidationError):
            apply_confirmed_memory_suggestion(s["id"], confirmed_by="chef",
                                              reviewer_role=rolle, tenant_id=TENANT_A)


def test_manager_may_still_confirm_company_memory_of_others():
    """Gegenprobe: Fuer Firmenwissen ist genau das der Zweck der Rolle --
    company_memory hat keinen persoenlichen Eigentuemer."""
    from apps.backend.database import create_memory_suggestion, confirm_memory_suggestion

    s = create_memory_suggestion(
        user_id="alice", tenant_id=TENANT_A, suggested_scope="company_memory",
        suggested_title="Firmenregel", suggested_content="Rechnungen dienstags",
        suggested_purpose="Test", source_type="user_confirmation",
    )
    ergebnis = confirm_memory_suggestion(s["id"], confirmed_by="chef",
                                         reviewer_role="manager", tenant_id=TENANT_A)
    assert ergebnis["memory_item_id"]


def test_memory_item_create_is_not_a_blanket_allow():
    """Gegenpruefung 7 (NIEDRIG): MEMORY_ITEM_CREATE hatte Listen-Semantik und
    war damit fuer jede bekannte Rolle ohne Owner-Bezug erlaubt."""
    from apps.backend import permissions

    fremd = permissions.evaluate_permission(
        action=permissions.MEMORY_ITEM_CREATE,
        actor=_actor("alice", TENANT_A),
        tenant_id=TENANT_A, resource_type="memory_item", resource_id="neu",
        resource_owner_user_id="bob",
    )
    eigen = permissions.evaluate_permission(
        action=permissions.MEMORY_ITEM_CREATE,
        actor=_actor("alice", TENANT_A),
        tenant_id=TENANT_A, resource_type="memory_item", resource_id="neu",
        resource_owner_user_id="alice",
    )
    assert fremd.allowed is False
    assert eigen.allowed is True


def test_company_memory_must_not_have_owner():
    from apps.backend.database import create_memory_item, MemoryValidationError

    with pytest.raises(MemoryValidationError):
        create_memory_item(
            TENANT_A, "company_memory", "Titel", "Inhalt",
            purpose="Test", source_id=_source(TENANT_A),
            owner_user_id="alice", status="active",
        )


# ── Befunde der finalen Gegenprüfung ──────────────────────────────────────

def test_foreign_user_in_same_tenant_cannot_reject_or_block_suggestion():
    """Mittel 6: reject und blocked filterten nur nach Mandant, nicht nach
    Eigentuemer -- ein anderer Nutzer desselben Mandanten konnte fremde
    Vorschlaege ablehnen oder blockieren."""
    from apps.backend.database import (
        create_memory_suggestion, reject_memory_suggestion,
        mark_memory_suggestion_blocked, list_memory_suggestions_for_user,
        MemoryValidationError,
    )

    s = create_memory_suggestion(
        user_id="alice", tenant_id=TENANT_A, suggested_scope="user_memory",
        suggested_title="Alices Vorschlag", suggested_content="privat",
        suggested_purpose="Test", source_type="user_confirmation",
    )
    with pytest.raises(MemoryValidationError):
        reject_memory_suggestion(s["id"], reviewed_by="mallory", tenant_id=TENANT_A)
    with pytest.raises(MemoryValidationError):
        mark_memory_suggestion_blocked(s["id"], reviewed_by="mallory", tenant_id=TENANT_A)

    # Unveraendert offen -- und der Eigentuemer darf weiterhin.
    assert list_memory_suggestions_for_user("alice", TENANT_A)[0]["status"] == "open"
    reject_memory_suggestion(s["id"], reviewed_by="alice", tenant_id=TENANT_A)
    assert list_memory_suggestions_for_user("alice", TENANT_A, status=None)[0]["status"] == "rejected"


def test_foreign_user_in_same_tenant_cannot_change_visibility_or_delete():
    """Mittel 7: set_memory_visibility und mark_memory_item_deleted prueften
    nur den Mandanten -- ein anderer Nutzer desselben Mandanten konnte einen
    fremden persoenlichen Eintrag oeffentlich schalten oder loeschen."""
    from apps.backend.database import (
        set_memory_visibility, mark_memory_item_deleted, get_memory_item,
        MemoryValidationError,
    )

    fremd = _item(TENANT_A, "alice")
    with pytest.raises(MemoryValidationError):
        set_memory_visibility(fremd["id"], tenant_id=TENANT_A,
                              visibility_scope="public", owner_user_id="mallory")
    with pytest.raises(MemoryValidationError):
        mark_memory_item_deleted(fremd["id"], tenant_id=TENANT_A,
                                 owner_user_id="mallory")
    assert get_memory_item(fremd["id"], tenant_id=TENANT_A)["status"] == "active"

    # Der Eigentuemer selbst darf.
    mark_memory_item_deleted(fremd["id"], tenant_id=TENANT_A, owner_user_id="alice")
    assert get_memory_item(fremd["id"], tenant_id=TENANT_A)["status"] == "deleted"
