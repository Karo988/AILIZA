"""
Kill-Switch Tests — 4 Ebenen + YAML-Config
EU AI Act Art. 14: System muss jederzeit stoppbar sein
"""

import pytest
from pathlib import Path
from apps.backend.kill_switch import KillSwitch, KillSwitchLevel

CONFIG_PATH = Path("config/kill_switch.yaml")


@pytest.fixture
def ks():
    return KillSwitch()


# ── GLOBAL ────────────────────────────────────────────────────────────────────

class TestGlobal:
    def test_default_ist_erlaubt(self, ks):
        assert ks.is_allowed() is True

    def test_halt_global_blockiert_alles(self, ks):
        ks.halt_global()
        assert ks.is_allowed() is False
        assert ks.is_allowed(provider="claude") is False
        assert ks.is_allowed(module="memory") is False
        assert ks.is_allowed(capability="fetch") is False

    def test_resume_global_gibt_frei(self, ks):
        ks.halt_global()
        ks.resume_global()
        assert ks.is_allowed() is True


# ── PROVIDER ──────────────────────────────────────────────────────────────────

class TestProvider:
    def test_halt_provider_blockiert_nur_diesen(self, ks):
        ks.halt_provider("claude")
        assert ks.is_allowed(provider="claude") is False
        assert ks.is_allowed(provider="openai") is True

    def test_resume_provider(self, ks):
        ks.halt_provider("claude")
        ks.resume(provider="claude")
        assert ks.is_allowed(provider="claude") is True

    def test_unbekannter_provider_standardmaessig_erlaubt(self, ks):
        assert ks.is_allowed(provider="unbekannt") is True


# ── MODULE ────────────────────────────────────────────────────────────────────

class TestModule:
    def test_halt_module_blockiert_nur_dieses(self, ks):
        ks.halt_module("memory")
        assert ks.is_allowed(module="memory") is False
        assert ks.is_allowed(module="audit") is True

    def test_resume_module(self, ks):
        ks.halt_module("memory")
        ks.resume(module="memory")
        assert ks.is_allowed(module="memory") is True

    def test_global_blockiert_vor_module(self, ks):
        ks.halt_global()
        assert ks.is_allowed(module="memory") is False


# ── CAPABILITY ────────────────────────────────────────────────────────────────

class TestCapability:
    def test_halt_capability_blockiert_nur_diese(self, ks):
        ks.halt_capability("data_export")
        assert ks.is_allowed(capability="data_export") is False
        assert ks.is_allowed(capability="external_calls") is True

    def test_resume_capability(self, ks):
        ks.halt_capability("data_export")
        ks.resume(capability="data_export")
        assert ks.is_allowed(capability="data_export") is True

    def test_provider_blockiert_vor_capability(self, ks):
        ks.halt_provider("claude")
        assert ks.is_allowed(provider="claude", capability="data_export") is False


# ── YAML-CONFIG ───────────────────────────────────────────────────────────────

class TestLoadFromConfig:
    def test_load_from_config_global_enabled(self):
        ks = KillSwitch.load_from_config(CONFIG_PATH)
        assert ks.is_allowed() is True

    def test_load_from_config_provider_present(self):
        ks = KillSwitch.load_from_config(CONFIG_PATH)
        assert ks.is_allowed(provider="claude") is True

    def test_load_from_config_unknown_provider_defaults_true(self):
        ks = KillSwitch.load_from_config(CONFIG_PATH)
        assert ks.is_allowed(provider="unknown_provider") is True

    def test_load_from_config_halt_persists_in_memory(self):
        ks = KillSwitch.load_from_config(CONFIG_PATH)
        ks.halt_provider("claude")
        assert ks.is_allowed(provider="claude") is False
