from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")


def _actor(user_id="owner", role="admin"):
    from apps.backend.auth.jwt_handler import TokenData
    return TokenData(user_id=user_id, tenant_id="default", role=role)


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import engine, init_db, metadata_obj
    metadata_obj.drop_all(engine)
    init_db()
    yield


def _create_admin_with_totp():
    from apps.backend.auth.totp import generate_secret, get_totp
    from apps.backend.database import confirm_totp_secret, create_user, upsert_totp_secret
    create_user("owner", "default", "admin", "unused-test-hash")
    secret = generate_secret()
    upsert_totp_secret("owner", "default", secret)
    assert confirm_totp_secret("owner")
    return get_totp(secret)


def _local_candidate(created_by="owner"):
    from apps.backend.database import create_model_candidate, engine, model_candidates
    from apps.backend.component_system import complete_evaluation, start_evaluation
    from sqlalchemy import select, update
    create_model_candidate(
        "local", "safe-local", modalities=["text"], capabilities=["chat"],
        context_window=8192, regions=["local"], created_by=created_by,
    )
    with engine.begin() as conn:
        candidate = dict(conn.execute(select(model_candidates)).mappings().one())
        conn.execute(update(model_candidates).where(model_candidates.c.id == candidate["id"])
                     .values(privacy_score=1.0, quality_score=1.0))
    run = start_evaluation(candidate_id=candidate["id"], benchmark_version="safe-local-v1",
                           data_kind="synthetic", created_by=created_by)
    complete_evaluation(evaluation_run_id=run["evaluation_run_id"],
                        metrics={"privacy_score": 1.0}, artifacts={"fixture": "synthetic"})
    with engine.begin() as conn:
        return dict(conn.execute(select(model_candidates)).mappings().one())


def test_solo_approval_requires_explicit_mode_and_totp():
    from apps.backend.component_system import (
        ComponentDecisionError, approve_component, configure_organization_mode,
    )
    from apps.backend.component_vocab import SOLO_COMPENSATED
    code = _create_admin_with_totp()
    candidate = _local_candidate()
    with pytest.raises(ComponentDecisionError):
        approve_component(
            candidate_id=candidate["id"], actor=_actor(), approval_mode=SOLO_COMPENSATED,
            approval_kind="full", task_package="invoice_drafts", purpose="draft invoices",
            allowed_data_classes=["public"], cost_limit=5.0,
            reason="Ausführlich geprüfte Modellfreigabe", totp_code=code,
        )
    configure_organization_mode(actor=_actor(), mode="single_person")
    approval = approve_component(
        candidate_id=candidate["id"], actor=_actor(), approval_mode=SOLO_COMPENSATED,
        approval_kind="full", task_package="invoice_drafts", purpose="draft invoices",
        allowed_data_classes=["public"], cost_limit=5.0,
        reason="Ausführlich geprüfte Modellfreigabe", totp_code=code,
    )
    assert approval["status"] == "approved"
    assert len(approval["approval_basis_hash"]) == 64


def test_candidate_change_invalidates_approval_and_activation():
    from apps.backend.component_system import (
        activate_component, approve_component, configure_organization_mode,
        refresh_candidate_integrity,
    )
    from apps.backend.component_vocab import SOLO_COMPENSATED
    from apps.backend.database import engine, model_candidates
    from apps.backend.db_schema import component_activations, component_approvals
    from sqlalchemy import select, update
    code = _create_admin_with_totp()
    configure_organization_mode(actor=_actor(), mode="single_person")
    candidate = _local_candidate()
    approval = approve_component(
        candidate_id=candidate["id"], actor=_actor(), approval_mode=SOLO_COMPENSATED,
        approval_kind="full", task_package="chat", purpose="safe local chat",
        allowed_data_classes=["public"], cost_limit=2.0,
        reason="Lokale Modellfreigabe mit Rückfall", totp_code=code,
    )
    activation = activate_component(approval_id=approval["id"], actor=_actor())
    from apps.backend.component_system import recommend_active_model
    from apps.backend.governance.data_governance import DataClass
    routed = recommend_active_model(
        tenant_id="default", task_package="chat", modality="text", task="chat",
        data_classes=[DataClass.PUBLIC], prompt_text="harmloser lokaler Text",
    )
    assert routed["provider"] == "local"
    assert routed["model"] == "safe-local"
    with engine.begin() as conn:
        conn.execute(update(model_candidates).where(
            model_candidates.c.id == candidate["id"]
        ).values(context_window=16384))
    result = refresh_candidate_integrity(candidate["id"])
    assert result["invalidated_count"] == 1
    with engine.begin() as conn:
        assert conn.execute(select(component_approvals.c.status)).scalar_one() == "approval_invalidated"
        assert conn.execute(select(component_activations.c.status)).scalar_one() == "approval_invalidated"


def test_budget_is_reserved_before_use_and_hard_limit_blocks():
    from apps.backend.component_system import (
        BudgetExceeded, reserve_budget, set_budget_policy, settle_budget,
    )
    now = datetime.now(timezone.utc)
    policy = set_budget_policy(
        actor=_actor(), task_package="chat", hard_limit=1.0,
        warning_threshold=0.8, period_start=now - timedelta(minutes=1),
        period_end=now + timedelta(days=30),
    )
    first = reserve_budget(tenant_id="default", task_package="chat", amount=0.7)
    with pytest.raises(BudgetExceeded):
        reserve_budget(tenant_id="default", task_package="chat", amount=0.4)
    settled = settle_budget(
        reservation_id=first["reservation_id"], actual_amount=0.5,
        provider="local", model="safe-local",
    )
    assert settled["status"] == "settled"
    second = reserve_budget(tenant_id="default", task_package="chat", amount=0.5)
    assert second["amount_reserved"] == 0.5


def test_evaluation_has_separate_run_and_artifact_identities():
    from apps.backend.component_system import complete_evaluation, start_evaluation
    candidate = _local_candidate(created_by="researcher")
    run = start_evaluation(
        candidate_id=candidate["id"], benchmark_version="invoice-v1",
        data_kind="synthetic", created_by="researcher",
    )
    completed = complete_evaluation(
        evaluation_run_id=run["evaluation_run_id"],
        metrics={"field_accuracy": 0.95}, artifacts={"fixture": "synthetic-1"},
    )
    assert completed["evaluation_run_id"] != completed["artifact_checksum"]
    assert len(completed["artifact_checksum"]) == 64


def test_board_eligibility_depends_on_data_context():
    from apps.backend.component_system import board_entries, complete_evaluation, start_evaluation
    from apps.backend.database import create_model_candidate, engine, model_candidates
    from sqlalchemy import select
    create_model_candidate(
        "openai", "contextual", modalities=["text"], capabilities=["chat"],
        context_window=1000, regions=["US"], created_by="researcher",
    )
    with engine.begin() as conn:
        candidate = dict(conn.execute(select(model_candidates)).mappings().one())
    run = start_evaluation(candidate_id=candidate["id"], benchmark_version="v1",
                           data_kind="synthetic", created_by="researcher")
    complete_evaluation(evaluation_run_id=run["evaluation_run_id"],
                        metrics={"quality": 1.0}, artifacts={"fixture": "synthetic"})
    public = board_entries(tenant_id="default", data_classes=["public"], task_package="chat")
    secret = board_entries(tenant_id="default", data_classes=["credentials"], task_package="chat")
    assert len(public["recommended"]) == 1
    assert len(secret["blocked"]) == 1
