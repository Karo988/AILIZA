"""
Kill-Switch Tests — Vier Ebenen + Betriebsmodi
EU AI Act Art. 14: Menschliche Aufsicht / Stoppbarkeit
"""

import pytest
from apps.backend.kill_switch import KillSwitch, KillSwitchLevel, OperationMode


@pytest.fixture
def ks():
    return KillSwitch()


# ── GLOBAL ────────────────────────────────────────────────────────────────────

class TestGlobalHalt:
    def test_global_halt_blockiert_alles(self, ks):
        ks.halt_global("operator")
        result = ks.check(provider="groq", module="memory", capability="fetch")
        assert result.blocked
        assert result.level == KillSwitchLevel.GLOBAL

    def test_resume_gibt_system_frei(self, ks):
        ks.halt_global()
        ks.resume_global()
        assert ks.check().allowed

    def test_global_hat_hoechste_prioritaet(self, ks):
        ks.halt_global()
        ks.halt_capability("fetch")
        result = ks.check(capability="fetch")
        assert result.level == KillSwitchLevel.GLOBAL


# ── PROVIDER ──────────────────────────────────────────────────────────────────

class TestProviderHalt:
    def test_provider_halt_blockiert_nur_diesen_provider(self, ks):
        ks.halt_provider("groq")
        assert ks.check(provider="groq").blocked
        assert ks.check(provider="openai").allowed

    def test_provider_case_insensitive(self, ks):
        ks.halt_provider("Groq")
        assert ks.check(provider="GROQ").blocked

    def test_resume_provider(self, ks):
        ks.halt_provider("groq")
        ks.resume_provider("groq")
        assert ks.check(provider="groq").allowed


# ── MODULE ────────────────────────────────────────────────────────────────────

class TestModuleHalt:
    def test_modul_halt_blockiert_nur_dieses_modul(self, ks):
        ks.halt_module("memory")
        assert ks.check(module="memory").blocked
        assert ks.check(module="approvals").allowed

    def test_provider_blockiert_vor_modul(self, ks):
        ks.halt_provider("groq")
        ks.halt_module("memory")
        result = ks.check(provider="groq", module="memory")
        assert result.level == KillSwitchLevel.PROVIDER


# ── CAPABILITY ────────────────────────────────────────────────────────────────

class TestCapabilityHalt:
    def test_capability_halt_blockiert_nur_diese_capability(self, ks):
        ks.halt_capability("fetch")
        assert ks.check(capability="fetch").blocked
        assert ks.check(capability="search").allowed

    def test_modul_blockiert_vor_capability(self, ks):
        ks.halt_module("tools")
        ks.halt_capability("fetch")
        result = ks.check(module="tools", capability="fetch")
        assert result.level == KillSwitchLevel.MODULE


# ── BETRIEBSMODUS ─────────────────────────────────────────────────────────────

class TestOperationMode:
    def test_default_ist_normal(self, ks):
        assert not ks.is_restricted_mode()

    def test_restricted_modus_setzbar(self, ks):
        ks.set_restricted()
        assert ks.is_restricted_mode()

    def test_zurueck_zu_normal(self, ks):
        ks.set_restricted()
        ks.set_normal()
        assert not ks.is_restricted_mode()


# ── CHANGE LOG ────────────────────────────────────────────────────────────────

class TestChangeLog:
    def test_aenderungen_werden_protokolliert(self, ks):
        ks.halt_global(actor="admin")
        ks.resume_global(actor="admin")
        log = ks.change_log()
        assert len(log) == 2
        assert log[0]["event"] == "GLOBAL_HALT"
        assert log[0]["actor"] == "admin"

    def test_status_liefert_aktuellen_zustand(self, ks):
        ks.halt_provider("groq")
        ks.halt_capability("fetch")
        s = ks.status()
        assert "groq" in s["halted_providers"]
        assert "fetch" in s["halted_capabilities"]
        assert s["global_halt"] is False
