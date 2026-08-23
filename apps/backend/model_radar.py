"""Small, model-only development radar with evidence-first ingestion."""
from __future__ import annotations

from typing import Any

from .component_system import add_evidence
from .database import create_model_candidate


def ingest_model_candidate(*, discovery: dict[str, Any], actor_user_id: str) -> dict[str, Any]:
    required = {"provider", "model_id", "official_url", "official_content",
                "modalities", "capabilities", "context_window"}
    missing = sorted(required - discovery.keys())
    if missing:
        raise ValueError(f"Unvollständiger Radar-Fund: {', '.join(missing)}")
    if not str(discovery["official_url"]).startswith("https://"):
        raise ValueError("Radar-Evidenz muss auf eine HTTPS-Quelle verweisen.")
    candidate = create_model_candidate(
        discovery["provider"], discovery["model_id"],
        modalities=list(discovery["modalities"]),
        capabilities=list(discovery["capabilities"]),
        context_window=int(discovery["context_window"]),
        regions=list(discovery.get("regions", [])),
        evidence_urls=[discovery["official_url"]], created_by=actor_user_id,
    )
    from sqlalchemy import and_, select
    from .database import engine
    from .db_schema import model_candidates
    with engine.begin() as conn:
        candidate_id = conn.execute(select(model_candidates.c.id).where(and_(
            model_candidates.c.provider == discovery["provider"],
            model_candidates.c.model_id == discovery["model_id"],
        ))).scalar_one()
    evidence = add_evidence(candidate_id=candidate_id,
                            source_url=discovery["official_url"], source_type="official",
                            source_content=discovery["official_content"])
    return {"candidate_id": candidate_id, "candidate": candidate, "evidence": evidence,
            "status": "candidate", "auto_approved": False}
