"""Tests fuer Dual-Gate PR-4: Stufe-3-Pruefer (flag-only) + Budget-Feinschliff
+ Statusphasen-Events + synthetischer Replay-Korpus.

Kern-Prinzip (Karo-Praezisierung): der Pruefer liefert NUR ein zusaetzliches
Diagnose-Flag, ueberschreibt NIE die deterministische Policy-Entscheidung.
Er wird ausschliesslich bei RED/BLACK-Signal-Uneinigkeit (kritische
Kategorie nur in Ingress ODER nur in Egress, nicht in beiden/keinem)
aufgerufen -- nie bei Komfort-/Wording-Treffern.

G3-konform: der Replay-Korpus verwendet ausschliesslich synthetische/
fiktive Daten, keine echten Namen/IBANs/Kontostaende/Produktionstexte.
"""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")

import pytest

from apps.backend.providers.gate_types import EgressOutcome, ProviderResult, Zweck
from apps.backend.providers.gated_client import (
    MAX_LLM_CALLS_PRO_ANFRAGE,
    MAX_TOTAL_CALLS_WITH_PRUEFER,
    GatedLLMClient,
)
from apps.backend.errors import AILIZAError


class _FakeProvider:
    provider_id = "fake"

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    def generate_with_meta(self, messages, context=None):
        self.calls += 1
        if not self._results:
            raise AssertionError("FakeProvider: keine weiteren Ergebnisse konfiguriert")
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


# ---------------------------------------------------------------------------
# T1: dritter Slot existiert nur fuer den Pruefer, nicht als beliebiger
# Zusatz-Retry
# ---------------------------------------------------------------------------

def test_budget_raised_to_three_with_escalation_slot():
    assert MAX_LLM_CALLS_PRO_ANFRAGE == 2  # Generate + Repair bleibt unveraendert
    assert MAX_TOTAL_CALLS_WITH_PRUEFER == 3  # 3. Slot exklusiv fuer Pruefer

    # Ohne kritische Signal-Uneinigkeit wird der 3. Slot NICHT genutzt, auch
    # wenn er theoretisch verfuegbar waere -- kein "freier" dritter Retry.
    provider = _FakeProvider([
        ProviderResult(text="Normale Antwort ohne PII.", stop_reason="end_turn"),
    ])
    client = GatedLLMClient()
    client.generate(
        provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
        ingress_source="Auch hier keine PII.",
    )
    assert provider.calls == 1


# ---------------------------------------------------------------------------
# T2: Pruefer wird NUR bei RED/BLACK-Uneinigkeit ausgeloest, nicht bei
# gelben/Komfort-Treffern
# ---------------------------------------------------------------------------

def test_pruefer_call_only_triggered_on_red_black_signal_disagreement():
    # Kritische Kategorie (IBAN) nur im Kandidaten, nicht im Ingress -> Uneinigkeit
    provider_critical = _FakeProvider([
        ProviderResult(text="Ihre IBAN DE89370400440532013000 wurde erfasst.", stop_reason="end_turn"),
        ProviderResult(text="UNCLEAR", stop_reason="end_turn"),  # Pruefer-Antwort
    ])
    client = GatedLLMClient()
    with pytest.raises(AILIZAError):
        client.generate(
            provider_critical, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
            ingress_source="Ganz ohne Finanzdaten im Ursprungstext.",
        )
    assert provider_critical.calls == 2  # Generate + Pruefer

    # Komfort-Kategorie (Name) nur im Kandidaten -> KEIN Pruefer-Call, auch
    # wenn die Regel selbst "enforce"/beide-Signale braucht (hier: nur 1
    # Signal, blockt also gar nicht -- und loest erst recht keinen Pruefer aus)
    provider_comfort = _FakeProvider([
        ProviderResult(text="Sehr geehrter Herr Mustermann, danke.", stop_reason="end_turn"),
    ])
    client2 = GatedLLMClient()
    text = client2.generate(
        provider_comfort, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
        ingress_source="Kein Namensbezug im Ursprungstext.",
    )
    assert provider_comfort.calls == 1
    assert "Mustermann" in text


# ---------------------------------------------------------------------------
# T3: Stimmen Ingress und Egress ueberein (beide oder keiner), wird der
# Pruefer uebersprungen
# ---------------------------------------------------------------------------

def test_pruefer_call_skipped_when_ingress_and_egress_agree():
    provider = _FakeProvider([
        ProviderResult(text="Ihre IBAN DE89370400440532013000 bleibt wie angegeben.", stop_reason="end_turn"),
    ])
    client = GatedLLMClient()
    with pytest.raises(AILIZAError):
        client.generate(
            provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
            ingress_source="Meine IBAN ist DE89370400440532013000.",
        )
    # Beide Signale vorhanden (Uebereinstimmung) -> kein Pruefer-Call, nur
    # der eigentliche Generate-Call.
    assert provider.calls == 1


# ---------------------------------------------------------------------------
# T4: Ein Pruefer-Call (Zweck.PRUEFER) loest NIE einen weiteren Pruefer-Call aus
# ---------------------------------------------------------------------------

def test_pruefer_zweck_does_not_recurse_into_another_pruefer_call():
    provider = _FakeProvider([
        ProviderResult(text="Ihre IBAN DE89370400440532013000 wurde erfasst.", stop_reason="end_turn"),
    ])
    client = GatedLLMClient()
    text = client.generate(
        provider, [{"role": "user", "content": "x"}], zweck=Zweck.PRUEFER,
        ingress_source="Ganz ohne Finanzdaten im Ursprungstext.",
    )
    assert text == "Ihre IBAN DE89370400440532013000 wurde erfasst."
    assert provider.calls == 1  # kein zusaetzlicher Pruefer-Call


# ---------------------------------------------------------------------------
# T5: Statusphasen-Hook bekommt geordnete Phasen-Codes
# ---------------------------------------------------------------------------

def test_status_phase_hook_receives_ordered_phase_events():
    provider = _FakeProvider([
        ProviderResult(text="", stop_reason="end_turn"),  # leer -> Repair
        ProviderResult(text="Zweiter Versuch: Antwort ohne PII.", stop_reason="end_turn"),
    ])
    phases: list[str] = []
    client = GatedLLMClient()
    client.generate(
        provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
        on_phase=phases.append,
    )
    assert phases == ["GENERATE", "REPAIR", "DELIVER"]
    # Nur Codes, keine Inhalte:
    assert all(isinstance(p, str) and len(p) < 20 for p in phases)


# ---------------------------------------------------------------------------
# T6: Ohne on_phase aendert sich das Verhalten nicht
# ---------------------------------------------------------------------------

def test_status_phase_hook_is_optional_no_behavior_change_without_it():
    provider = _FakeProvider([ProviderResult(text="Antwort ohne Hook.", stop_reason="end_turn")])
    client = GatedLLMClient()
    text = client.generate(provider, [{"role": "user", "content": "x"}])
    assert text == "Antwort ohne Hook."
    assert client.last_diagnostic.outcome == EgressOutcome.DELIVER.value


# ---------------------------------------------------------------------------
# T7: Synthetischer Replay-Korpus -- bekannte Musterfaelle liefern stabile
# Outcomes. Ausschliesslich fiktive Daten (G3), keine echten Produktionstexte.
# ---------------------------------------------------------------------------

_REPLAY_CORPUS = [
    # (Name, ingress, egress-Kandidat, erwartet_block)
    ("kritisch_nur_egress", "Kein Finanzbezug.", "Kartennummer 4111 1111 1111 1111 erfasst.", True),
    # Kritische Kategorie blockt bei JEDEM Signal (auch Uebereinstimmung) --
    # das ist die einzelsignal_genuegt-Regel aus PR-3, kein PR-4-Verhalten.
    ("kritisch_beide_uebereinstimmend_blockt_trotzdem", "IBAN DE00000000000000000000 vorhanden.", "IBAN DE00000000000000000000 bestaetigt.", True),
    ("komfort_nur_egress_kein_block", "Kein Namensbezug.", "Sehr geehrte Frau Beispielmann, danke.", False),
    ("refusal_wird_nie_ausgeliefert", "Testanfrage ohne PII.", "", False),  # Sonderfall unten simuliert
]


def test_replay_corpus_all_known_incidents_produce_stable_outcome():
    for name, ingress, egress_text, expect_block in _REPLAY_CORPUS:
        if name == "refusal_wird_nie_ausgeliefert":
            provider = _FakeProvider([
                ProviderResult(text="", stop_reason="refusal"),
                ProviderResult(text="", stop_reason="refusal"),
            ])
            client = GatedLLMClient()
            with pytest.raises(AILIZAError):
                client.generate(
                    provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
                    ingress_source=ingress,
                )
            continue

        provider = _FakeProvider([
            ProviderResult(text=egress_text, stop_reason="end_turn"),
            ProviderResult(text="UNCLEAR", stop_reason="end_turn"),  # falls Pruefer noetig
        ])
        client = GatedLLMClient()
        if expect_block:
            with pytest.raises(AILIZAError):
                client.generate(
                    provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
                    ingress_source=ingress,
                )
        else:
            text = client.generate(
                provider, [{"role": "user", "content": "x"}], zweck=Zweck.NUTZER_AUSGABE,
                ingress_source=ingress,
            )
            assert text == egress_text
