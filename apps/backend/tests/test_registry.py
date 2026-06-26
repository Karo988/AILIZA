"""
Tests für AILIZA Provider & Tool Registry.

Regeln die getestet werden:
- Unbekannter Provider → wird nicht genutzt
- Neuer Provider bleibt pending (admin_approved=False blockiert)
- Sensible Daten blockieren ungeeignete Provider
- public_data darf günstige Provider nutzen
- Human approval erforderlich bei sensitiven Aufgaben
- Pending-Change wird gespeichert, nie direkt aktiviert
- Validierung schlägt an bei fehlenden Pflicht-Einträgen
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ── Fixture: isolierte Test-Registry ──────────────────────────────────────────

@pytest.fixture()
def registry(tmp_path):
    """Lädt die echte Registry aus dem Projektverzeichnis."""
    import importlib
    import apps.backend.registry.registry_loader as rl
    # Reset Singleton für saubere Tests
    rl._registry = None
    reg = rl.load_registry()
    yield reg
    rl._registry = None


# ── 1. Provider-Grundregeln ────────────────────────────────────────────────────

class TestProviderRegistry:

    def test_known_providers_loaded(self, registry):
        assert "groq" in registry.providers
        assert "openai" in registry.providers
        assert "local" in registry.providers
        assert "openrouter" in registry.providers

    def test_groq_is_usable(self, registry):
        assert registry.get_provider("groq").is_usable()

    def test_openai_is_usable(self, registry):
        assert registry.get_provider("openai").is_usable()

    def test_local_is_usable(self, registry):
        assert registry.get_provider("local").is_usable()

    def test_openrouter_not_usable(self, registry):
        """OpenRouter ist admin_approved=false — darf nicht genutzt werden."""
        entry = registry.get_provider("openrouter")
        assert not entry.is_usable(), "OpenRouter muss blockiert sein bis Admin-Freigabe"

    def test_unknown_provider_returns_none(self, registry):
        """Unbekannter Provider → get_provider gibt None zurück."""
        assert registry.get_provider("some_new_chinese_provider") is None

    def test_usable_providers_excludes_unapproved(self, registry):
        usable_ids = {p.provider_id for p in registry.get_usable_providers()}
        assert "openrouter" not in usable_ids

    def test_local_allows_all_data_classes(self, registry):
        local = registry.get_provider("local")
        for dc in ["public", "internal", "personal_data", "credentials", "special_category", "hr", "legal"]:
            assert local.allows_data(dc), f"local muss {dc} erlauben"

    def test_groq_forbids_credentials(self, registry):
        assert not registry.get_provider("groq").allows_data("credentials")

    def test_groq_forbids_special_category(self, registry):
        assert not registry.get_provider("groq").allows_data("special_category")

    def test_groq_allows_personal_data(self, registry):
        """Nach Redaktion muss Groq personal_data akzeptieren."""
        assert registry.get_provider("groq").allows_data("personal_data")

    def test_openai_allows_hr(self, registry):
        assert registry.get_provider("openai").allows_data("hr")

    def test_groq_failover_before_openai(self, registry):
        groq = registry.get_provider("groq")
        openai = registry.get_provider("openai")
        assert groq.failover_priority < openai.failover_priority

    def test_provider_blocks_reason_for_unapproved(self, registry):
        """OpenRouter gibt einen verständlichen Grund zurück warum er blockiert ist."""
        entry = registry.get_provider("openrouter")
        reason = entry.blocks_reason()
        assert reason is not None
        assert "Admin" in reason or "Freigabe" in reason or "deaktiviert" in reason


# ── 2. Neuer Provider bleibt pending ──────────────────────────────────────────

class TestNewProviderStaysPending:

    def test_provider_with_admin_approved_false_not_usable(self):
        from apps.backend.registry.registry_loader import ProviderEntry
        new_provider = ProviderEntry(
            provider_id="shiny_new_provider",
            type="text_llm",
            enabled=True,           # enabled=True, aber...
            admin_approved=False,   # ...noch nicht freigegeben
            region="us",
            transfer_basis="scc",
            avv_signed=False,
            allowed_data=["public"],
            forbidden_data=[],
            default_model="model-x",
            fallback_models=[],
            failover_priority=5,
            health_status="unknown",
            logs_prompts=False,
            used_for_training=False,
        )
        assert not new_provider.is_usable()
        reason = new_provider.blocks_reason()
        assert reason is not None

    def test_add_pending_change_does_not_activate_provider(self, tmp_path, monkeypatch):
        """add_pending_change darf Provider NICHT aktivieren — nur Vorschlag speichern."""
        import apps.backend.registry.registry_loader as rl
        health_file = tmp_path / "provider_health.json"
        health_file.write_text(json.dumps({"pending_changes": []}))
        monkeypatch.setattr(rl, "_REGISTRY_DIR", tmp_path)
        # Auch provider_registry.yaml + routing + tools anlegen (leer reicht für diesen Test)
        (tmp_path / "provider_registry.yaml").write_text("providers: {}")
        (tmp_path / "tool_registry.yaml").write_text("tools: {}")
        (tmp_path / "routing_rules.yaml").write_text("rules: {}")

        change = rl.add_pending_change(
            change_type="new_provider",
            target="budget_provider",
            proposed_value={"enabled": True, "admin_approved": False},
            reason="Günstiger Anbieter gefunden",
            created_by="watch_agent",
        )

        assert change.status == "pending"

        # Registry neu laden — Provider darf NICHT aktiv sein
        rl._registry = None
        reg = rl.load_registry()
        assert reg.get_provider("budget_provider") is None  # nicht in Registry

        # Aber in pending_changes
        assert any(c.target == "budget_provider" for c in reg.pending_changes)

    def test_pending_change_written_to_file(self, tmp_path, monkeypatch):
        import apps.backend.registry.registry_loader as rl
        health_file = tmp_path / "provider_health.json"
        health_file.write_text(json.dumps({"pending_changes": []}))
        monkeypatch.setattr(rl, "_REGISTRY_DIR", tmp_path)

        rl.add_pending_change(
            change_type="provider_health",
            target="groq",
            proposed_value={"health_status": "degraded"},
            reason="3 consecutive 503 errors",
            created_by="watch_agent",
        )

        data = json.loads(health_file.read_text())
        assert len(data["pending_changes"]) == 1
        assert data["pending_changes"][0]["target"] == "groq"
        assert data["pending_changes"][0]["status"] == "pending"
        assert data["pending_changes"][0]["created_by"] == "watch_agent"


# ── 3. Daten-Klassen-Regeln ────────────────────────────────────────────────────

class TestDataClassRules:

    def test_credentials_blocked_for_all_external_providers(self, registry):
        for pid, entry in registry.providers.items():
            if entry.region != "local":
                assert not entry.allows_data("credentials"), (
                    f"Provider '{pid}' darf niemals credentials erhalten"
                )

    def test_special_category_blocked_for_external(self, registry):
        for pid, entry in registry.providers.items():
            if entry.region != "local":
                assert not entry.allows_data("special_category"), (
                    f"Provider '{pid}' darf niemals special_category erhalten"
                )

    def test_public_data_allowed_for_approved_providers(self, registry):
        for entry in registry.get_usable_providers():
            assert entry.allows_data("public"), (
                f"Jeder aktive Provider muss public_data verarbeiten können"
            )


# ── 4. Tool-Registry ──────────────────────────────────────────────────────────

class TestToolRegistry:

    def test_tavily_is_usable(self, registry):
        assert registry.get_tool("tavily_search").is_usable()

    def test_canva_not_usable(self, registry):
        """Canva ist nicht freigegeben — darf nicht genutzt werden."""
        canva = registry.get_tool("canva")
        assert not canva.is_usable()

    def test_canva_forbids_personal_data(self, registry):
        assert not registry.get_tool("canva").allows_data("personal_data")

    def test_local_chart_engine_allows_personal_data(self, registry):
        assert registry.get_tool("local_chart_engine").allows_data("personal_data")

    def test_tavily_forbids_personal_data(self, registry):
        assert not registry.get_tool("tavily_search").allows_data("personal_data")

    def test_usable_tools_excludes_canva(self, registry):
        usable_ids = {t.tool_id for t in registry.get_usable_tools()}
        assert "canva" not in usable_ids


# ── 5. Routing-Regeln ─────────────────────────────────────────────────────────

class TestRoutingRules:

    def test_writing_task_no_web_search(self, registry):
        rule = registry.get_routing_rule("writing_task")
        assert not rule.web_search

    def test_research_task_web_search_true(self, registry):
        rule = registry.get_routing_rule("research_task")
        assert rule.web_search

    def test_sensitive_hr_task_requires_human_review(self, registry):
        rule = registry.get_routing_rule("sensitive_hr_task")
        assert rule.human_review
        assert rule.draft_only

    def test_fallback_to_general_task(self, registry):
        """Unbekannte Aufgaben fallen auf general_task zurück."""
        rule = registry.get_routing_rule("totally_unknown_task_type")
        assert rule is not None
        assert rule.rule_id == "general_task"

    def test_hr_preferred_providers_include_local(self, registry):
        rule = registry.get_routing_rule("sensitive_hr_task")
        assert "local" in rule.preferred_providers


# ── 6. Validierung ────────────────────────────────────────────────────────────

class TestRegistryValidation:

    def test_valid_registry_no_warnings(self, registry):
        from apps.backend.registry.registry_loader import validate_registry
        warnings = validate_registry(registry)
        # Keine kritischen Fehler — Warnungen über AVV sind okay
        critical = [w for w in warnings if "fehlt" in w and "Pflicht" in w]
        assert not critical, f"Kritische Validierungsfehler: {critical}"

    def test_missing_required_provider_creates_warning(self):
        from apps.backend.registry.registry_loader import Registry, validate_registry
        reg = Registry()  # leer
        warnings = validate_registry(reg)
        assert any("groq" in w for w in warnings)
        assert any("openai" in w for w in warnings)
        assert any("local" in w for w in warnings)

    def test_enabled_without_approved_creates_warning(self):
        from apps.backend.registry.registry_loader import Registry, ProviderEntry, validate_registry
        entry = ProviderEntry(
            provider_id="sneaky",
            type="text_llm",
            enabled=True,
            admin_approved=False,   # Konflikt!
            region="us", transfer_basis="scc", avv_signed=False,
            allowed_data=["public"], forbidden_data=[],
            default_model="m", fallback_models=[],
            failover_priority=5, health_status="ok",
            logs_prompts=False, used_for_training=False,
        )
        reg = Registry(providers={"sneaky": entry})
        warnings = validate_registry(reg)
        assert any("sneaky" in w and "admin_approved" in w for w in warnings)
