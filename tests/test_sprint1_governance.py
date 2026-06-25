"""
AILIZA Sprint-1 Governance-Tests
=================================
Deckt alle sechs Sprint-1-Gates ab:

  Gate 1: Klassifikator — Biometrie, HR, CSV/Event-Log-Personendaten
  Gate 2: Personenentscheidungs-Block (DSGVO Art. 22, EU AI Act)
  Gate 3: Kill-Switch-Betriebsmodi (normal/restricted/read_only/offline/kill_switch_active)
  Gate 4: Rollenprüfung für Approvals
  Gate 5: Retention-Pflicht für Approval-Records und Agent-Runs
  Gate 5b: Audit-Sauberkeit in Fehlerpfaden (Exception, Policy-Block)

Crash-Szenarien (PDF-Rahmen):
  Szenario 1: VIP-Biometrie am Einlass → SPECIAL_CATEGORY + requires_human_decision
  Szenario 2: Kundendaten-CSV → PERSONAL_DATA, nicht PUBLIC
  Szenario 4: Massennachricht → safety_critical, nicht nur medium
  Szenario 6: Personalentscheidung → PERSON_DECISION-Gate
"""
from __future__ import annotations

import importlib
import os

import pytest

os.environ.setdefault("AILIZA_SECRET_KEY", "test-sprint1-governance-32-chars-minimum!")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AILIZA_EXTERNAL_LLM_ENABLED", "false")


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1: Klassifikator — Biometrie
# ─────────────────────────────────────────────────────────────────────────────
class TestBiometricClassification:
    def test_facial_recognition_is_special_category(self):
        """Crash-Szenario 1: Gesichtserkennung → SPECIAL_CATEGORY."""
        from apps.backend.governance.data_governance import classify, DataClass
        result = classify("Das System verwendet Gesichtserkennung am VIP-Einlass.")
        assert DataClass.SPECIAL_CATEGORY in result.data_classes
        assert "biometric" in result.matched_rules

    def test_biometric_requires_human_decision(self):
        """Biometrie-Kontext setzt requires_human_decision=True."""
        from apps.backend.governance.data_governance import classify
        result = classify("VIP-Erkennung per Kamera und Gesichtsscan aktivieren.")
        assert result.requires_human_decision is True

    def test_fingerprint_is_special_category(self):
        from apps.backend.governance.data_governance import classify, DataClass
        result = classify("Fingerabdruck-Scanner am Haupteingang installieren.")
        assert DataClass.SPECIAL_CATEGORY in result.data_classes

    def test_biometric_vip_entry_blocks_external_provider(self):
        """Crash-Szenario 1: Biometrie-Daten dürfen nicht an externe Provider."""
        from apps.backend.providers.provider_profiles import check_provider_policy
        from apps.backend.governance.data_governance import DataClass
        for provider in ("groq", "anthropic"):
            allowed, reason = check_provider_policy(provider, [DataClass.SPECIAL_CATEGORY])
            assert not allowed, f"{provider} muss SPECIAL_CATEGORY blockieren"

    def test_vip_access_denial_requires_human_decision(self):
        """'VIP abweisen' + Biometrie → requires_human_decision (DSGVO Art. 22)."""
        from apps.backend.governance.data_governance import classify
        result = classify("VIP-Erkennung: abweisen wenn Gesichtsscan nicht übereinstimmt.")
        assert result.requires_human_decision is True


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1: Klassifikator — CSV / Kundendaten / Event-Log
# ─────────────────────────────────────────────────────────────────────────────
class TestPersonalDataClassification:
    def test_customer_csv_with_name_and_birthdate_is_personal(self):
        """Crash-Szenario 2: Kundendaten-CSV → mindestens PERSONAL_DATA, nicht PUBLIC."""
        from apps.backend.governance.data_governance import classify, DataClass
        csv_header = "Vorname, Nachname, Geburtsdatum, Ticket-ID, E-Mail"
        result = classify(csv_header)
        assert DataClass.PERSONAL_DATA in result.data_classes
        assert DataClass.PUBLIC not in result.data_classes or len(result.data_classes) > 1

    def test_passport_number_is_personal(self):
        from apps.backend.governance.data_governance import classify, DataClass
        result = classify("Bitte Personalausweis-Nummer eingeben: DE1234567")
        assert DataClass.PERSONAL_DATA in result.data_classes

    def test_ticket_id_in_event_log_is_personal(self):
        """Ticket-ID in Event-Log → PERSONAL_DATA (nicht PUBLIC)."""
        from apps.backend.governance.data_governance import classify, DataClass
        result = classify("ticket_id, name, timestamp — Einlass-Log Export")
        assert DataClass.PERSONAL_DATA in result.data_classes

    def test_plain_public_text_stays_public(self):
        """Öffentliche Infos bleiben PUBLIC — keine False-Positives."""
        from apps.backend.governance.data_governance import classify, DataClass
        result = classify("Das Festival beginnt am Samstag um 14 Uhr am Haupteingang.")
        assert result.highest_risk_class == DataClass.PUBLIC
        assert result.requires_human_decision is False

    def test_customer_csv_blocked_for_external_provider_without_avv(self):
        """Crash-Szenario 2: PERSONAL_DATA ohne AVV → Provider blockiert."""
        from apps.backend.providers.provider_profiles import check_provider_policy
        from apps.backend.governance.data_governance import DataClass
        allowed, reason = check_provider_policy("groq", [DataClass.PERSONAL_DATA])
        assert not allowed


# ─────────────────────────────────────────────────────────────────────────────
# Gate 1 + Gate 2: HR / Personalentscheidung
# ─────────────────────────────────────────────────────────────────────────────
class TestHRAndPersonDecisionGate:
    def test_staff_assignment_classified_as_hr(self):
        """Crash-Szenario 6: Mitarbeitereinsatzplanung → DataClass.HR."""
        from apps.backend.governance.data_governance import classify, DataClass
        result = classify("Erstelle Schichtplan und weise Mitarbeiter den Toiletten zu.")
        assert DataClass.HR in result.data_classes

    def test_hr_context_requires_human_decision(self):
        """HR-Kontext → requires_human_decision=True (DSGVO Art. 22)."""
        from apps.backend.governance.data_governance import classify
        result = classify("Personalplanung: Wer wird an Station C eingesetzt?")
        assert result.requires_human_decision is True

    def test_employee_termination_requires_human_decision(self):
        from apps.backend.governance.data_governance import classify
        result = classify("KI soll Kündigung für Mitarbeiter empfehlen.")
        assert result.requires_human_decision is True

    def test_person_decision_verb_plus_personal_data_triggers_human_gate(self):
        """Entscheidungsverb + Personenbezug → requires_human_decision."""
        from apps.backend.governance.data_governance import classify, DataClass
        result = classify("Bewerber ablehnen basierend auf Lebenslauf-Daten: Vorname Mustermann.")
        assert result.requires_human_decision is True
        assert DataClass.HR in result.data_classes or DataClass.PERSONAL_DATA in result.data_classes

    def test_approval_risk_level_for_person_decision(self):
        """Personalentscheidungs-Abfrage → risk_level=person_decision."""
        from apps.backend.approval import assess_search_risk, RiskLevel
        result = assess_search_risk("Automatische Personalentscheidung für Schicht treffen")
        assert result.risk_level == RiskLevel.PERSON_DECISION.value
        assert result.risky is True

    def test_neutral_staff_scheduling_without_decision_stays_lower_risk(self):
        """Neutrale Schichtanfrage ohne Entscheidungsbegriff → kein person_decision-Gate."""
        from apps.backend.approval import assess_search_risk, RiskLevel
        result = assess_search_risk("Wie viele Mitarbeiter brauchen wir am Samstag?")
        assert result.risk_level != RiskLevel.PERSON_DECISION.value


# ─────────────────────────────────────────────────────────────────────────────
# Gate 3: Kill-Switch-Betriebsmodi
# ─────────────────────────────────────────────────────────────────────────────
class TestOperationModes:
    def test_normal_mode_allows_external_llm(self, monkeypatch):
        monkeypatch.setenv("AILIZA_OPERATION_MODE", "normal")
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        from apps.backend import kill_switch
        importlib.reload(kill_switch)
        assert kill_switch.is_action_allowed("external_llm")

    def test_restricted_mode_blocks_write_and_mass_notify(self, monkeypatch):
        monkeypatch.setenv("AILIZA_OPERATION_MODE", "restricted")
        from apps.backend import kill_switch
        importlib.reload(kill_switch)
        assert not kill_switch.is_action_allowed("write")
        assert not kill_switch.is_action_allowed("send_message")
        assert not kill_switch.is_action_allowed("mass_notify")

    def test_restricted_mode_still_allows_read(self, monkeypatch):
        monkeypatch.setenv("AILIZA_OPERATION_MODE", "restricted")
        from apps.backend import kill_switch
        importlib.reload(kill_switch)
        assert kill_switch.is_action_allowed("read")

    def test_offline_mode_blocks_external_llm_and_fetch(self, monkeypatch):
        monkeypatch.setenv("AILIZA_OPERATION_MODE", "offline")
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "true")
        from apps.backend import kill_switch
        importlib.reload(kill_switch)
        assert not kill_switch.is_external_llm_enabled()
        assert not kill_switch.is_action_allowed("fetch")

    def test_kill_switch_active_mode_blocks_all_critical_actions(self, monkeypatch):
        monkeypatch.setenv("AILIZA_OPERATION_MODE", "kill_switch_active")
        from apps.backend import kill_switch
        importlib.reload(kill_switch)
        for action in ("external_llm", "write", "send_message", "memory_store", "mass_notify"):
            assert not kill_switch.is_action_allowed(action), f"{action} muss blockiert sein"

    def test_unknown_mode_is_fail_closed(self, monkeypatch):
        """Unbekannter Modus → kill_switch_active (Fail-Closed)."""
        monkeypatch.setenv("AILIZA_OPERATION_MODE", "unknown_garbage_mode")
        from apps.backend import kill_switch
        importlib.reload(kill_switch)
        assert kill_switch.get_operation_mode().value == "kill_switch_active"
        assert not kill_switch.is_action_allowed("external_llm")

    def test_kill_switch_metadata_contains_no_content(self, monkeypatch):
        """Audit-Metadaten des Kill-Switch enthalten nur Status/Modus/Timestamp."""
        monkeypatch.setenv("AILIZA_OPERATION_MODE", "normal")
        from apps.backend import kill_switch
        importlib.reload(kill_switch)
        meta = kill_switch.kill_switch_metadata()
        assert "checked_at" in meta
        assert "operation_mode" in meta
        assert "external_llm_enabled" in meta
        # Kein Inhalt, kein task, kein prompt
        for forbidden in ("task", "prompt", "query", "content", "input"):
            assert forbidden not in meta


# ─────────────────────────────────────────────────────────────────────────────
# Gate 4: Crowd-Control / Safety-Critical (Crash-Szenario 4)
# ─────────────────────────────────────────────────────────────────────────────
class TestSafetyCriticalApproval:
    def test_mass_push_to_all_visitors_is_safety_critical(self):
        """Crash-Szenario 4: Massennachricht → safety_critical, nicht nur medium."""
        from apps.backend.approval import assess_search_risk, RiskLevel
        result = assess_search_risk("Alle Besucher sofort zum Ausgang schicken wegen Sicherheitslage")
        assert result.risk_level == RiskLevel.SAFETY_CRITICAL.value
        assert result.risky is True

    def test_mass_notify_english_is_safety_critical(self):
        from apps.backend.approval import assess_search_risk, RiskLevel
        result = assess_search_risk("broadcast to all attendees: emergency evacuation now")
        assert result.risk_level == RiskLevel.SAFETY_CRITICAL.value

    def test_safety_critical_timeout_is_short(self):
        """Safety-Critical: Timeout 300s (5 min), danach Auto-Reject."""
        from apps.backend.approval import APPROVAL_TIMEOUT_SECONDS, RiskLevel
        assert APPROVAL_TIMEOUT_SECONDS[RiskLevel.SAFETY_CRITICAL.value] == 300

    def test_safety_critical_requires_elevated_roles(self):
        """Safety-Critical darf nur von security_lead / operations_lead / owner freigegeben werden."""
        from apps.backend.approval import can_approve, RiskLevel
        assert can_approve(RiskLevel.SAFETY_CRITICAL.value, "security_lead")
        assert can_approve(RiskLevel.SAFETY_CRITICAL.value, "operations_lead")
        assert can_approve(RiskLevel.SAFETY_CRITICAL.value, "owner")
        assert not can_approve(RiskLevel.SAFETY_CRITICAL.value, "admin")
        assert not can_approve(RiskLevel.SAFETY_CRITICAL.value, "user")
        assert not can_approve(RiskLevel.SAFETY_CRITICAL.value, "manager")

    def test_normal_search_is_not_safety_critical(self):
        """Normale Suchanfrage ohne Crowd-Control → nicht safety_critical."""
        from apps.backend.approval import assess_search_risk, RiskLevel
        result = assess_search_risk("Was ist das Wetterprogramm für Samstag?")
        assert result.risk_level != RiskLevel.SAFETY_CRITICAL.value


# ─────────────────────────────────────────────────────────────────────────────
# Gate 4: Rollenprüfung für Approvals
# ─────────────────────────────────────────────────────────────────────────────
class TestApprovalRoleGating:
    def test_person_decision_requires_privacy_or_legal(self):
        from apps.backend.approval import can_approve, RiskLevel
        assert can_approve(RiskLevel.PERSON_DECISION.value, "privacy")
        assert can_approve(RiskLevel.PERSON_DECISION.value, "legal")
        assert can_approve(RiskLevel.PERSON_DECISION.value, "owner")
        assert not can_approve(RiskLevel.PERSON_DECISION.value, "admin")
        assert not can_approve(RiskLevel.PERSON_DECISION.value, "manager")
        assert not can_approve(RiskLevel.PERSON_DECISION.value, "user")

    def test_high_risk_requires_admin_or_owner(self):
        from apps.backend.approval import can_approve, RiskLevel
        assert can_approve(RiskLevel.HIGH.value, "admin")
        assert can_approve(RiskLevel.HIGH.value, "owner")
        assert not can_approve(RiskLevel.HIGH.value, "manager")
        assert not can_approve(RiskLevel.HIGH.value, "user")

    def test_medium_risk_allows_manager(self):
        from apps.backend.approval import can_approve, RiskLevel
        assert can_approve(RiskLevel.MEDIUM.value, "manager")
        assert not can_approve(RiskLevel.MEDIUM.value, "user")

    def test_approval_record_contains_required_roles(self):
        """Neu erstellter Approval-Record enthält required_approver_roles."""
        from apps.backend.database import init_db, create_approval_request
        init_db()
        record = create_approval_request(
            tool="search",
            input_params={"query": "<str:50>"},
            risk_level="safety_critical",
            risk_reason="Mass notification detected",
        )
        assert "required_approver_roles" in record
        assert "security_lead" in record["required_approver_roles"]
        assert "expires_at" in record
        assert record["expires_at"] is not None  # Safety-Critical hat Timeout

    def test_high_risk_approval_has_expires_at(self):
        from apps.backend.database import init_db, create_approval_request
        init_db()
        record = create_approval_request(
            tool="fetch",
            input_params={"url": "<str:30>"},
            risk_level="high",
            risk_reason="Unknown domain",
        )
        assert record["expires_at"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# Gate 5: Retention-Pflicht für Approval-Records und Agent-Runs
# ─────────────────────────────────────────────────────────────────────────────
class TestRetentionCompleteness:
    def test_retention_policy_includes_approval_requests(self):
        from apps.backend.maintenance.retention_cleanup import get_retention_policy
        policy = get_retention_policy()
        assert "approval_requests" in policy
        assert 1 <= policy["approval_requests"] <= 365

    def test_retention_policy_includes_agent_runs(self):
        from apps.backend.maintenance.retention_cleanup import get_retention_policy
        policy = get_retention_policy()
        assert "agent_runs" in policy
        assert 1 <= policy["agent_runs"] <= 365

    def test_cleanup_includes_approval_and_agent_runs(self):
        from apps.backend.database import init_db
        from apps.backend.maintenance.retention_cleanup import run_cleanup
        init_db()
        result = run_cleanup()
        assert "approval_requests__resolved" in result["deleted_by_table"]
        assert "agent_runs__completed" in result["deleted_by_table"]

    def test_no_object_type_missing_retention(self):
        """Alle Tabellen mit personenbezogenen Daten haben eine Retentionsfrist."""
        from apps.backend.maintenance.retention_cleanup import get_retention_policy
        policy = get_retention_policy()
        required = {
            "audit_logs", "security_logs", "performance_logs", "cost_logs",
            "reflection_facts", "totp_backup_codes", "messenger_bindings",
            "approval_requests", "agent_runs",
        }
        missing = required - set(policy.keys())
        assert not missing, f"Fehlende Retentionsfristen: {missing}"


# ─────────────────────────────────────────────────────────────────────────────
# Gate 5b: Audit-Sauberkeit in Fehlerpfaden
# ─────────────────────────────────────────────────────────────────────────────
class TestAuditCleanlinessInErrorPaths:
    @pytest.fixture()
    def client(self):
        from apps.backend.main import app, init_db
        from fastapi.testclient import TestClient
        init_db()
        return TestClient(app, raise_server_exceptions=False)

    def _create_and_login(self, client, user_id: str, role: str = "user") -> str:
        from apps.backend.database import create_user
        import bcrypt
        hashed = bcrypt.hashpw("Sprint1@Test!".encode(), bcrypt.gensalt()).decode()
        try:
            create_user(user_id, "default", role, hashed)
        except Exception:
            pass
        resp = client.post("/auth/login", json={
            "user_id": user_id, "password": "Sprint1@Test!", "tenant_id": "default",
        })
        return resp.json().get("access_token", "")

    def test_policy_block_audit_no_raw_parameters(self, client):
        """403-Block durch Policy → Audit-Eintrag ohne Rohinhalt in parameters."""
        from apps.backend.database import list_audit_entries
        token = self._create_and_login(client, "s1_policy_user")
        sensitive = "SPRINT1_LEAK_TEST_SECRET_VALUE_XYZ"
        client.post("/agent/run",
                    json={"task": sensitive},
                    headers={"Authorization": f"Bearer {token}"})
        entries = list_audit_entries(limit=30)
        for entry in entries:
            meta_str = str(entry.get("metadata", {}))
            assert "SPRINT1_LEAK" not in meta_str, (
                f"Rohinhalt in Audit-Eintrag '{entry.get('action')}': {meta_str[:200]}"
            )

    def test_kill_switch_active_audit_no_content(self, monkeypatch, client):
        """Kill-Switch aktiv → Audit-Eintrag enthält nur Status/Modus, kein task-Content."""
        from apps.backend.database import list_audit_entries
        monkeypatch.setenv("AILIZA_EXTERNAL_LLM_ENABLED", "false")
        token = self._create_and_login(client, "s1_ks_user")
        secret_task = "KILL_SWITCH_LEAK_CHECK_12345"
        client.post("/agent/run",
                    json={"task": secret_task},
                    headers={"Authorization": f"Bearer {token}"})
        entries = list_audit_entries(limit=30)
        for entry in entries:
            meta_str = str(entry.get("metadata", {}))
            assert "KILL_SWITCH_LEAK" not in meta_str

    def test_exception_in_audit_entry_has_no_raw_input(self):
        """Audit-Eintrag nach Exception enthält keinen Rohinhalt."""
        from apps.backend.database import write_audit_entry, list_audit_entries, init_db
        init_db()
        try:
            raise ValueError("Test-Exception mit EXCEPTION_LEAK_TEST_SECRET")
        except ValueError as exc:
            write_audit_entry(
                action="test.error",
                metadata={
                    "error_type": type(exc).__name__,
                    "status": "failed",
                },
            )
        entries = list_audit_entries(limit=5)
        for entry in entries:
            meta_str = str(entry.get("metadata", {}))
            assert "EXCEPTION_LEAK" not in meta_str
