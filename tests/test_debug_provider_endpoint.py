from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

os.environ.setdefault("AILIZA_ENV", "development")
os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")

from apps.backend import main as main_module


ROOT = Path(__file__).resolve().parents[1]


def _debug_provider_route_registered(env_name: str) -> bool:
    env = os.environ.copy()
    env.update(
        {
            "AILIZA_ENV": env_name,
            "AILIZA_SECRET_KEY": "test-secret-key-minimum-32-chars-ok",
            "AILIZA_DATABASE_URL": "sqlite:///:memory:",
            "AILIZA_EXTERNAL_LLM_ENABLED": "false",
            "PYTHONPATH": str(ROOT),
        }
    )
    code = """
import json
from apps.backend.main import app
print(json.dumps(any(getattr(route, "path", "") == "/api/debug/provider-test" for route in app.routes)))
"""
    output = subprocess.check_output(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
    )
    return bool(json.loads(output.strip().splitlines()[-1]))


def test_provider_debug_endpoint_respects_kill_switch_before_provider_calls(monkeypatch):
    calls: list[str] = []

    class FakeProvider:
        model = "fake-model"

        def generate(self, messages):  # pragma: no cover - failure path only
            calls.append("generate")
            return "AILIZA_PROVIDER_OK"

    monkeypatch.setenv("AILIZA_ENV", "development")
    monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "false")
    monkeypatch.delenv("AILIZA_BETA_ACCESS_CODE", raising=False)
    monkeypatch.setattr(main_module._orchestrator, "providers", {"fake": FakeProvider()})

    client = TestClient(main_module.app, raise_server_exceptions=False)
    response = client.get("/api/debug/provider-test")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked"
    assert data["final_status"] == "blocked"
    assert data["error"]["code"] == "kill_switch_active"
    assert data["provider_attempts_in_order"] == []
    assert data["providers"] == {}
    assert calls == []


def test_provider_debug_endpoint_not_registered_in_production():
    assert _debug_provider_route_registered("production") is False


def test_provider_debug_endpoint_remains_registered_in_staging():
    assert _debug_provider_route_registered("staging") is True
