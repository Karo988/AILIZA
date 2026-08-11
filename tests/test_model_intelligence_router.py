"""Tests für Paket A: Model-Intelligence-Persistenz + Router
(apps/backend/intelligence/, apps/backend/database.py: create_model_candidate,
approve_model_candidate, list_model_candidates, recommend_model).

Kernkriterium: niemals wird ein nicht freigegebenes Modell empfohlen; ein
neu angelegter Kandidat ist niemals sofort waehlbar; Freigabe erfordert
explizite Scores und approved_by.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "apps" / "backend"


@pytest.fixture(autouse=True)
def fresh_db():
    from apps.backend.database import init_db, metadata_obj, engine
    metadata_obj.drop_all(engine)
    init_db()
    yield


def test_new_candidate_starts_unapproved_and_is_not_recommended():
    from apps.backend.database import create_model_candidate, recommend_model

    create_model_candidate(
        "groq", "llama-test", modalities=["text"], capabilities=["chat"], context_window=8000,
    )
    result = recommend_model("default", modality="text", task="chat")
    assert result["selected"] is None
    assert "llama-test" not in " ".join(result["considered"])


def test_approved_candidate_is_recommended():
    from apps.backend.database import create_model_candidate, approve_model_candidate, recommend_model

    create_model_candidate(
        "groq", "llama-test", modalities=["text"], capabilities=["chat"], context_window=8000,
    )
    approved = approve_model_candidate(
        "groq", "llama-test", approved_by="admin1",
        quality_score=0.8, latency_score=0.7, cost_score=0.9, privacy_score=0.75,
        benchmark_version="2026-08-bench-1",
    )
    assert approved is not None
    assert approved["status"] == "approved"

    result = recommend_model("default", modality="text", task="chat", required_capabilities=["chat"])
    assert result["selected"] == "groq:llama-test"
    assert result["benchmark_version"] == "2026-08-bench-1"


def test_high_risk_data_requires_privacy_score_above_threshold():
    from apps.backend.database import create_model_candidate, approve_model_candidate, recommend_model

    create_model_candidate(
        "groq", "low-privacy", modalities=["text"], capabilities=[], context_window=8000,
    )
    approve_model_candidate(
        "groq", "low-privacy", approved_by="admin1",
        quality_score=1.0, latency_score=1.0, cost_score=1.0, privacy_score=0.5,
        benchmark_version="v1",
    )
    result = recommend_model("default", modality="text", task="chat", data_risk="high")
    assert result["selected"] is None


def test_approve_unknown_candidate_returns_none_no_silent_create():
    from apps.backend.database import approve_model_candidate

    result = approve_model_candidate(
        "unknown", "ghost", approved_by="admin1",
        quality_score=1.0, latency_score=1.0, cost_score=1.0, privacy_score=1.0,
        benchmark_version="v1",
    )
    assert result is None


def test_duplicate_provider_model_rejected():
    import sqlalchemy.exc
    from apps.backend.database import create_model_candidate

    create_model_candidate("groq", "dup", modalities=["text"], capabilities=[], context_window=1000)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        create_model_candidate("groq", "dup", modalities=["text"], capabilities=[], context_window=1000)


def test_recommend_model_writes_audit_entry_without_prompt_content():
    from apps.backend.database import create_model_candidate, approve_model_candidate, recommend_model, list_audit_entries

    create_model_candidate("groq", "audited", modalities=["text"], capabilities=[], context_window=1000)
    approve_model_candidate(
        "groq", "audited", approved_by="admin1",
        quality_score=1.0, latency_score=1.0, cost_score=1.0, privacy_score=1.0,
        benchmark_version="v1",
    )
    recommend_model("default", modality="text", task="chat")

    entries = list_audit_entries(limit=10, tenant_id="default")
    matching = [e for e in entries if e["action"] == "model.routing.recommended"]
    assert len(matching) == 1
    assert matching[0]["metadata"]["selected"] == "groq:audited"
    assert "prompt" not in matching[0]["metadata"]


def test_recommend_model_persists_routing_decision():
    from apps.backend.database import (
        create_model_candidate, approve_model_candidate, recommend_model, engine, routing_decisions,
    )
    from sqlalchemy import select

    create_model_candidate("groq", "logged", modalities=["text"], capabilities=[], context_window=1000)
    approve_model_candidate(
        "groq", "logged", approved_by="admin1",
        quality_score=1.0, latency_score=1.0, cost_score=1.0, privacy_score=1.0,
        benchmark_version="v1",
    )
    recommend_model("tenant-x", modality="text", task="chat")

    with engine.begin() as conn:
        rows = conn.execute(
            select(routing_decisions).where(routing_decisions.c.tenant_id == "tenant-x")
        ).mappings().all()
    assert len(rows) == 1
    assert rows[0]["selected"] == "groq:logged"


def test_list_model_candidates_filters_by_status():
    from apps.backend.database import create_model_candidate, approve_model_candidate, list_model_candidates

    create_model_candidate("groq", "c1", modalities=["text"], capabilities=[], context_window=1000)
    create_model_candidate("groq", "c2", modalities=["text"], capabilities=[], context_window=1000)
    approve_model_candidate(
        "groq", "c1", approved_by="admin1",
        quality_score=1.0, latency_score=1.0, cost_score=1.0, privacy_score=1.0,
        benchmark_version="v1",
    )
    approved = list_model_candidates(status="approved")
    candidates = list_model_candidates(status="candidate")
    assert {r["model_id"] for r in approved} == {"c1"}
    assert {r["model_id"] for r in candidates} == {"c2"}


def test_migration_creates_tables_on_fresh_and_existing_database(tmp_path):
    db_path = tmp_path / "existing.sqlite"
    db_url = f"sqlite:///{db_path}"
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = db_url

    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "d8f4c6a91b27"],
        cwd=BACKEND_DIR, env=env, check=True, capture_output=True, text=True, timeout=60,
    )

    from sqlalchemy import create_engine
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO audit_logs (timestamp, action, metadata, tenant_id, previous_hash, entry_hash) "
            "VALUES ('2026-01-01T00:00:00+00:00', 'test.action', '{}', 'default', '00', '11')"
        )
    engine.dispose()

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND_DIR, env=env, check=True, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(db_url)
    with engine.begin() as conn:
        tables = {row[0] for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).all()}
        assert "model_candidates" in tables
        assert "routing_decisions" in tables
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM audit_logs").scalar() == 1
    engine.dispose()


def test_migration_downgrade_removes_tables_without_data_loss(tmp_path):
    db_path = tmp_path / "downgrade.sqlite"
    db_url = f"sqlite:///{db_path}"
    env = os.environ.copy()
    env["AILIZA_DATABASE_URL"] = db_url

    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND_DIR, env=env, check=True, capture_output=True, text=True, timeout=60,
    )
    from sqlalchemy import create_engine
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO audit_logs (timestamp, action, metadata, tenant_id, previous_hash, entry_hash) "
            "VALUES ('2026-01-01T00:00:00+00:00', 'test.action', '{}', 'default', '00', '11')"
        )
    engine.dispose()

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "downgrade", "d8f4c6a91b27"],
        cwd=BACKEND_DIR, env=env, check=True, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr

    engine = create_engine(db_url)
    with engine.begin() as conn:
        tables = {row[0] for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).all()}
        assert "model_candidates" not in tables
        assert "routing_decisions" not in tables
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM audit_logs").scalar() == 1
    engine.dispose()
