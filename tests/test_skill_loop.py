"""
Tests fuer den kontrollierten Skill-Learning-Loop.
Prueft: Propose, Sanitierung, Capability-Checks, Approval-Flow, Audit, Loeschung.
"""
from __future__ import annotations

import os
import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _token(role: str = "user", tenant: str = "default") -> str:
    from apps.backend.auth.jwt_handler import create_token
    return create_token(f"{role}1", tenant, role)


# ── Sanitierung ───────────────────────────────────────────────────────────────
def test_sanitizer_strips_api_key():
    from apps.backend.skills.skill_store import _sanitize
    text = "Nutze sk-abc123XYZ789abcdef als Key"
    result = _sanitize(text)
    assert "sk-abc123" not in result
    assert "[ENTFERNT]" in result


def test_sanitizer_strips_email():
    from apps.backend.skills.skill_store import _sanitize
    result = _sanitize("Sende an user@example.com")
    assert "user@example.com" not in result


def test_sanitizer_limits_length():
    from apps.backend.skills.skill_store import _sanitize, _MAX_SKILL_CONTENT_CHARS
    long_text = "a" * (_MAX_SKILL_CONTENT_CHARS + 500)
    assert len(_sanitize(long_text)) <= _MAX_SKILL_CONTENT_CHARS


def test_sensitive_content_detection():
    from apps.backend.skills.skill_store import _contains_sensitive
    # Nach Sanitierung noch CREDENTIALS erkennbar → True
    # Leerer oder sauberer Text → False
    assert not _contains_sensitive("Wie suche ich nach Firmennamen in Deutschland?")


# ── Propose ───────────────────────────────────────────────────────────────────
def test_propose_public_skill_creates_pending():
    from apps.backend.skills.skill_store import propose_skill, list_skills
    from apps.backend.governance.data_governance import DataClass

    proposal = propose_skill(
        name="Web-Recherche",
        description="Suche und fasse zusammen",
        steps_summary="1. Suchbegriff bestimmen. 2. Suche ausfuehren. 3. Zusammenfassen.",
        gdpr_purpose="Informationsbeschaffung",
        data_classes=[DataClass.PUBLIC],
    )
    assert proposal.status == "pending"
    assert proposal.skill_id is not None

    pending = list_skills(status="pending")
    assert any(s["skill_id"] == proposal.skill_id for s in pending)


def test_propose_credentials_blocked():
    from apps.backend.skills.skill_store import propose_skill
    from apps.backend.governance.data_governance import DataClass
    from apps.backend.errors import AILIZAError

    with pytest.raises(AILIZAError):
        propose_skill(
            name="Geheimer Skill",
            description="Mit Credentials",
            steps_summary="Nutze API-Key sk-secret123abcdef fuer den Call.",
            gdpr_purpose="Test",
            data_classes=[DataClass.CREDENTIALS],
        )


def test_propose_with_pii_in_steps_gets_sanitized():
    from apps.backend.skills.skill_store import propose_skill, list_skills
    from apps.backend.governance.data_governance import DataClass

    proposal = propose_skill(
        name="E-Mail-Skill",
        description="Antwort senden",
        steps_summary="Recherchiere und antworte. Kontakt: nicht@example.com wird entfernt.",
        gdpr_purpose="Kundenkommunikation",
        data_classes=[DataClass.PUBLIC],
    )
    skills = list_skills(status="pending")
    stored = next(s for s in skills if s["skill_id"] == proposal.skill_id)
    assert "nicht@example.com" not in stored["steps_summary"]


# ── Approval-Flow ─────────────────────────────────────────────────────────────
def test_approve_skill_changes_status():
    from apps.backend.skills.skill_store import propose_skill, approve_skill, list_skills
    from apps.backend.governance.data_governance import DataClass

    proposal = propose_skill(
        name="Genehmigter Skill",
        description="Sicher",
        steps_summary="Suchbegriff -> Web-Suche -> Zusammenfassung -> Antwort.",
        gdpr_purpose="Informationsbeschaffung",
        data_classes=[DataClass.PUBLIC],
    )
    result = approve_skill(proposal.skill_id, approved_by="admin1")
    assert result["status"] == "approved"

    approved = list_skills(status="approved")
    assert any(s["skill_id"] == proposal.skill_id for s in approved)


def test_reject_skill_changes_status():
    from apps.backend.skills.skill_store import propose_skill, reject_skill, list_skills
    from apps.backend.governance.data_governance import DataClass

    proposal = propose_skill(
        name="Verworfener Skill",
        description="Nicht benoetigt",
        steps_summary="Schritt 1. Schritt 2. Schritt 3.",
        gdpr_purpose="Test",
        data_classes=[DataClass.PUBLIC],
    )
    result = reject_skill(proposal.skill_id, rejected_by="admin1", reason="Kein Bedarf")
    assert result["status"] == "rejected"


def test_approve_already_approved_fails():
    from apps.backend.skills.skill_store import propose_skill, approve_skill
    from apps.backend.governance.data_governance import DataClass
    from apps.backend.errors import AILIZAError

    proposal = propose_skill(
        name="Skill",
        description="Desc",
        steps_summary="Schritt 1. Schritt 2. Schritt 3.",
        gdpr_purpose="Test",
        data_classes=[DataClass.PUBLIC],
    )
    approve_skill(proposal.skill_id, approved_by="admin1")
    with pytest.raises(AILIZAError):
        approve_skill(proposal.skill_id, approved_by="admin1")


def test_delete_skill():
    from apps.backend.skills.skill_store import propose_skill, approve_skill, delete_skill, list_skills
    from apps.backend.governance.data_governance import DataClass

    proposal = propose_skill(
        name="Zu loeschender Skill",
        description="Desc",
        steps_summary="Schritt 1. Schritt 2.",
        gdpr_purpose="Test",
        data_classes=[DataClass.PUBLIC],
    )
    approve_skill(proposal.skill_id, approved_by="admin1")
    deleted = delete_skill(proposal.skill_id, tenant_id="default", deleted_by="admin1")
    assert deleted is True
    assert list_skills(status="approved") == []


# ── API-Endpoints ─────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from apps.backend.main import app
    from apps.backend.database import init_db
    init_db()
    return TestClient(app)


def test_propose_endpoint_requires_auth(client):
    resp = client.post("/skills/propose", json={
        "name": "Test", "description": "Desc",
        "steps_summary": "Step 1. Step 2. Step 3.",
        "gdpr_purpose": "Test",
    })
    assert resp.status_code == 401


def test_propose_endpoint_success(client):
    resp = client.post(
        "/skills/propose",
        json={
            "name": "Recherche-Skill",
            "description": "Web-Suche und Zusammenfassung",
            "steps_summary": "Suchbegriff bestimmen. Suche ausfuehren. Ergebnis zusammenfassen.",
            "gdpr_purpose": "Informationsbeschaffung fuer KMU",
            "data_classes": ["public"],
        },
        headers={"Authorization": f"Bearer {_token('user')}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["requires_approval"] is True


def test_admin_skills_requires_admin(client):
    resp = client.get("/admin/skills",
                      headers={"Authorization": f"Bearer {_token('user')}"})
    assert resp.status_code == 403


def test_full_skill_lifecycle_via_api(client):
    """Propose → list (pending) → approve → list (approved) → delete."""
    user_token = _token("user")
    admin_token = _token("admin")

    # Propose
    resp = client.post(
        "/skills/propose",
        json={
            "name": "Lifecycle-Skill",
            "description": "Vollstaendiger Test",
            "steps_summary": "Schritt eins. Schritt zwei. Schritt drei. Auswertung.",
            "gdpr_purpose": "Qualitaetsverbesserung",
            "data_classes": ["public"],
        },
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 201
    skill_id = resp.json()["skill_id"]

    # Admin sieht pending
    resp = client.get("/admin/skills?status=pending",
                      headers={"Authorization": f"Bearer {admin_token}"})
    ids = [s["skill_id"] for s in resp.json()]
    assert skill_id in ids

    # Approve
    resp = client.post(f"/admin/skills/{skill_id}/approve",
                       headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"

    # Approved Skills sichtbar
    resp = client.get("/skills", headers={"Authorization": f"Bearer {user_token}"})
    ids = [s["skill_id"] for s in resp.json()]
    assert skill_id in ids
    # steps_summary ist fuer normale Nutzer nicht sichtbar
    assert all("steps_summary" not in s for s in resp.json())

    # Delete
    resp = client.delete(f"/admin/skills/{skill_id}",
                         headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
