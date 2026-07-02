"""
Fallback-Transparenz bei Provider-Failover (Freigabe Stufe 1, E3-Zusatzpatch)
================================================================================
Bei Provider-Wechsel durch Failover muss der tatsaechlich genutzte Provider
+ Modell in Response-Metadaten UND im Audit-Trail sichtbar sein
(failover_from, failover_to) — kein stiller Wechsel.

Akzeptanz: simulierter Ausfall des ersten Providers → Orchestrator-Attribute
und Audit zeigen den tatsaechlich genutzten Anbieter.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "true")
os.environ.setdefault("AILIZA_TEST_MODE", "true")

from apps.backend.errors import AILIZAError
from apps.backend.providers.orchestrator import ProviderOrchestrator


class _FailProvider:
    def __init__(self, pid: str):
        self.provider_id = pid
        self.model = f"model-{pid}"
    def count_tokens(self, text): return 1
    def estimate_cost(self, i, o): return 0.0
    def generate(self, messages, context=None):
        raise AILIZAError.from_code("provider_forbidden", safe_alternatives=[f"{self.provider_id}: HTTP 403"])


class _OKProvider:
    def __init__(self, pid: str, answer: str = "OK"):
        self.provider_id = pid
        self.model = f"model-{pid}"
        self._answer = answer
    def count_tokens(self, text): return 1
    def estimate_cost(self, i, o): return 0.0
    def generate(self, messages, context=None):
        return self._answer


def test_no_failover_attrs_reflect_first_success(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    orch = ProviderOrchestrator(providers={"groq": _OKProvider("groq")})
    result = orch.generate([{"role": "user", "content": "hi"}])
    assert result == "OK"
    assert orch.last_provider_id == "groq"
    assert orch.last_failover_occurred is False
    assert orch.last_failover_from == []


def test_failover_attrs_show_actual_provider_used(monkeypatch):
    """Erster Provider (groq) faellt aus (simulierter 403) → openai uebernimmt.
    Orchestrator-Attribute muessen den TATSAECHLICH genutzten Provider zeigen,
    nicht den urspruenglich bevorzugten."""
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AILIZA_PROVIDER_ORDER", "groq,openai")

    orch = ProviderOrchestrator(providers={
        "groq": _FailProvider("groq"),
        "openai": _OKProvider("openai", answer="Antwort von OpenAI"),
    })
    result = orch.generate([{"role": "user", "content": "hi"}])

    assert result == "Antwort von OpenAI"
    assert orch.last_provider_id == "openai"
    assert orch.last_model == "model-openai"
    assert orch.last_failover_occurred is True
    assert "groq" in orch.last_failover_from


def test_failover_writes_audit_entry(monkeypatch):
    """Bei Failover wird ein Audit-Eintrag 'provider.failover' mit
    failover_from/failover_to geschrieben — kein stiller Wechsel."""
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AILIZA_PROVIDER_ORDER", "groq,openai")

    recorded = []

    def _fake_write_audit_entry(action, metadata=None, tenant_id="default"):
        recorded.append((action, metadata, tenant_id))
        return {"id": 1}

    import apps.backend.database as db
    monkeypatch.setattr(db, "write_audit_entry", _fake_write_audit_entry)

    orch = ProviderOrchestrator(providers={
        "groq": _FailProvider("groq"),
        "openai": _OKProvider("openai", answer="Antwort von OpenAI"),
    })
    orch.generate([{"role": "user", "content": "hi"}])

    failover_entries = [r for r in recorded if r[0] == "provider.failover"]
    assert len(failover_entries) == 1
    _, metadata, _ = failover_entries[0]
    assert metadata["failover_from"] == ["groq"]
    assert metadata["failover_to"] == "openai"
    assert metadata["model"] == "model-openai"
