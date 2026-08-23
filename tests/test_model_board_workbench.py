from pathlib import Path

import pytest

from apps.backend.evaluation.benchmark_suite import SYNTHETIC_CASES
from apps.backend.memory_scope_adapter import route_memory_scope
from apps.backend.model_radar import ingest_model_candidate


def test_synthetic_benchmark_contains_no_real_customer_data() -> None:
    assert SYNTHETIC_CASES
    assert all("@" not in case["input"] for case in SYNTHETIC_CASES)


def test_memory_scope_adapter_is_fail_closed() -> None:
    assert route_memory_scope("personal", owner_user_id="u1").store == "user_memory"
    assert route_memory_scope("project", project_id="p1").store == "company_memory"
    with pytest.raises(ValueError):
        route_memory_scope("project")
    with pytest.raises(ValueError):
        route_memory_scope("invented")


def test_radar_requires_official_https_evidence() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        ingest_model_candidate(discovery={
            "provider": "local", "model_id": "x", "official_url": "http://example.com",
            "official_content": "x", "modalities": ["text"],
            "capabilities": ["classification"], "context_window": 1000,
        }, actor_user_id="admin")
