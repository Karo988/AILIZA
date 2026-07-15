"""
Regressionsschutz nach Phase 3d: EU AI Act Art. 52 wurde als falsche
Artikel-Referenz identifiziert (Transparenzpflicht liegt in Art. 50).
Diese Tests verifizieren die Laufzeit-Strings, die tatsaechlich an das
LLM oder an den Nutzer gehen — nicht bloss Kommentare/Doku.

Vorbild: tests/test_telegram_gateway.py pruefte dies bereits fuer den
Telegram-Kanal; hier wird derselbe Schutz fuer die uebrigen Kanaele
(Web-Chat-Backend) ergaenzt. test_telegram_gateway.py selbst bleibt
unveraendert.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

from apps.backend.compliance_context import ComplianceContextManager, EU_AI_ACT_ARTICLES
from apps.backend.compliance.eu_ai_act import EUAIActCompliance
from apps.backend.agent.agent_core import AILIZAAgent


def test_base_system_prompt_references_article_50_not_52():
    prompt = ComplianceContextManager.BASE_SYSTEM_PROMPT
    assert "Art. 52" not in prompt
    assert "Art. 50" in prompt


def test_compliance_context_article_key_renamed():
    assert "art_52" not in EU_AI_ACT_ARTICLES
    assert "art_50" in EU_AI_ACT_ARTICLES
    assert "Art. 52" not in EU_AI_ACT_ARTICLES["art_50"]["title"]
    assert "Art. 50" in EU_AI_ACT_ARTICLES["art_50"]["title"]


def test_transparency_notice_has_no_wrong_article():
    compliance = EUAIActCompliance(system_name="AILIZA", version="0.5")
    notice_de = compliance.get_transparency_notice("de")
    notice_en = compliance.get_transparency_notice("en")
    assert "Art. 52" not in notice_de
    assert "Art. 52" not in notice_en


def test_agent_ai_disclosure_has_no_wrong_article():
    agent = AILIZAAgent()
    assert "Art. 52" not in agent.get_ai_disclosure()
