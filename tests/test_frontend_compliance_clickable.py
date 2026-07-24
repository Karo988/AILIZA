"""AP2: Compliance-Seite wirklich bedienbar machen.

Vorher wirkten die Compliance-Kennzahlen und -Karten wie Schaltflaechen,
hatten aber keine erkennbare Aktion. Diese Tests pruefen das tatsaechlich
ausgelieferte Frontend (TestClient GET "/") -- nicht eine ungenutzte Datei.

Bewusste Einschraenkung dieser Runde: "Agent-Runs" und "Genehmigungen"
zeigen ehrlich "noch nicht verfuegbar" statt echter Detaildaten, weil
agent_runs/approval_requests im Backend noch keine user_id-Trennung haben
(separates Sicherheits-Arbeitspaket). Compliance-Erklaerung und EU-AI-Act-
Frist verwenden echte, bereits vorhandene Daten (keine erfundenen Werte).
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient

from apps.backend.main import app


@pytest.fixture()
def served_index() -> str:
    client = TestClient(app)
    response = client.get("/", headers={"accept": "text/html"})
    assert response.status_code == 200
    return response.text


def test_metrics_and_compliance_card_are_clickable(served_index):
    assert 'onclick="openAgentRunsInfo()"' in served_index
    assert 'onclick="openApprovalsInfo()"' in served_index
    assert 'onclick="openComplianceInfo()"' in served_index
    assert 'onclick="openAiActDeadlineInfo()"' in served_index


def test_agent_run_rows_are_clickable(served_index):
    assert 'onclick="openAgentRunsInfo()" title="Details ansehen"' in served_index


def test_shared_info_modal_exists(served_index):
    assert 'id="info-modal"' in served_index
    assert 'id="info-modal-title"' in served_index
    assert 'id="info-modal-body"' in served_index


def test_approvals_uses_the_exact_not_available_wording(served_index):
    assert "Genehmigungsübersicht ist noch nicht verfügbar." in served_index


def test_agent_runs_honestly_explains_missing_user_separation(served_index):
    assert "aus Datenschutzgründen aktuell nicht verfügbar" in served_index
    assert "nicht pro Nutzer/-in getrennt gespeichert" in served_index
    assert "eigenen Arbeitspaket nachgerüstet" in served_index


def test_compliance_detail_distinguishes_proven_from_documented_only(served_index):
    start = served_index.index("function openComplianceInfo()")
    end = served_index.index("function openAiActDeadlineInfo()")
    fn = served_index[start:end]
    assert "technisch geprüft" in fn
    assert "technisch noch nicht vollständig nachgewiesen" in fn
    assert "02.08.2026" in fn


def test_ai_act_deadline_uses_real_existing_date_not_fabricated(served_index):
    start = served_index.index("function openAiActDeadlineInfo()")
    end = served_index.index("function openApprovalsInfo()")
    fn = served_index[start:end]
    assert 'new Date("2026-08-02")' in fn
    assert "nicht strukturiert im System nachverfolgt" in fn


def test_no_raw_agent_run_or_approval_payload_leaked_in_info_dialogs(served_index):
    start = served_index.index("function openInfoModal(")
    end = served_index.index("function openAgentRunsInfo()") + len("function openAgentRunsInfo()")
    block = served_index[start:end]
    assert "input_params" not in block
    assert "pending_approval_id" not in block
