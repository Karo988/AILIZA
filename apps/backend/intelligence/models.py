"""Reine Datenklassen fuer das Model-Intelligence-Routing.

Uebernommen aus dem gepruesten Referenz-Prototyp (HANDOFF_AILIZA.md,
ailiza_intelligence_control_plane.zip) und an die reale AILIZA-Persistenz
(apps.backend.db_schema.model_candidates) angepasst.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

Risk = Literal["low", "medium", "high", "critical"]
Status = Literal["candidate", "approved", "blocked", "retired"]


@dataclass(frozen=True)
class ModelCandidate:
    provider: str
    model_id: str
    modalities: frozenset[str]
    capabilities: frozenset[str]
    context_window: int
    regions: frozenset[str] = frozenset()
    status: Status = "candidate"
    quality_score: float = 0.0
    latency_score: float = 0.0
    cost_score: float = 0.0
    privacy_score: float = 0.0
    benchmark_version: str = "unbenchmarked"
    evidence_urls: tuple[str, ...] = ()
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_row(cls, row: dict) -> "ModelCandidate":
        """Baut ein ModelCandidate aus einer model_candidates-Datenbankzeile.
        Fehlende Scores (NULL = noch nicht benchmarkt) werden zu 0.0 --
        das ModelRouter-Scoring behandelt unbenchmarkte Kandidaten dadurch
        korrekt als niedrigstwertig, ohne dass ein fehlender Wert einen
        Fehler ausloest."""
        return cls(
            provider=row["provider"],
            model_id=row["model_id"],
            modalities=frozenset(row["modalities"] or []),
            capabilities=frozenset(row["capabilities"] or []),
            context_window=row["context_window"],
            regions=frozenset(row["regions"] or []),
            status=row["status"],
            quality_score=row["quality_score"] or 0.0,
            latency_score=row["latency_score"] or 0.0,
            cost_score=row["cost_score"] or 0.0,
            privacy_score=row["privacy_score"] or 0.0,
            benchmark_version=row["benchmark_version"],
            evidence_urls=tuple(row["evidence_urls"] or []),
            updated_at=row["updated_at"],
        )


@dataclass(frozen=True)
class RoutingRequest:
    modality: str
    task: str
    required_capabilities: frozenset[str] = frozenset()
    min_context_window: int = 0
    allowed_providers: frozenset[str] | None = None
    required_region: str | None = None
    local_only: bool = False
    data_risk: Risk = "low"
    weights: tuple[float, float, float, float] = (0.50, 0.15, 0.10, 0.25)  # quality, latency, cost, privacy


@dataclass(frozen=True)
class RoutingDecision:
    selected: str | None
    fallback: str | None
    score: float | None
    reason: str
    considered: tuple[str, ...]
    benchmark_version: str | None
