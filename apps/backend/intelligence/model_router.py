"""Deterministischer Modell-Router.

Waehlt niemals einen Provider frei -- routet ausschliesslich unter
Kandidaten mit status="approved". Identisch zur geprueften
Referenzimplementierung (HANDOFF_AILIZA.md), unveraendert uebernommen.
"""
from __future__ import annotations

from .models import ModelCandidate, RoutingRequest, RoutingDecision


class ModelRouter:
    """Deterministic router. It never approves providers; it only routes
    among approved candidates."""

    def __init__(self, models: list[ModelCandidate]):
        self.models = list(models)

    def _eligible(self, m: ModelCandidate, r: RoutingRequest) -> bool:
        if m.status != "approved":
            return False
        if r.modality not in m.modalities:
            return False
        if not r.required_capabilities.issubset(m.capabilities):
            return False
        if m.context_window < r.min_context_window:
            return False
        if r.allowed_providers is not None and m.provider not in r.allowed_providers:
            return False
        if r.required_region and r.required_region not in m.regions:
            return False
        if r.local_only and m.provider != "local":
            return False
        if r.data_risk in {"high", "critical"} and m.privacy_score < 0.8:
            return False
        return True

    def route(self, request: RoutingRequest) -> RoutingDecision:
        eligible = [m for m in self.models if self._eligible(m, request)]
        considered = tuple(f"{m.provider}:{m.model_id}" for m in eligible)
        if not eligible:
            return RoutingDecision(None, None, None, "Kein freigegebenes Modell erfüllt alle harten Anforderungen.", considered, None)
        qw, lw, cw, pw = request.weights

        def score(m: ModelCandidate) -> float:
            return qw * m.quality_score + lw * m.latency_score + cw * m.cost_score + pw * m.privacy_score

        ranked = sorted(eligible, key=lambda m: (score(m), m.privacy_score, m.quality_score, m.model_id), reverse=True)
        top = ranked[0]
        fb = ranked[1] if len(ranked) > 1 else None
        return RoutingDecision(
            f"{top.provider}:{top.model_id}",
            f"{fb.provider}:{fb.model_id}" if fb else None,
            round(score(top), 4),
            "Auswahl nur aus freigegebenen Modellen nach Fähigkeiten, Datenschutz und Benchmark-Scores.",
            considered,
            top.benchmark_version,
        )
