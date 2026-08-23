"""Synthetic-first benchmark workbench.

Real business records are accepted only when the caller supplies a valid
trial approval id.  The evaluator is injected so this module never performs
an unapproved provider call itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import and_, select

from ..component_system import ComponentDecisionError, complete_evaluation, start_evaluation
from ..database import engine
from ..db_schema import component_approvals

BENCHMARK_VERSION = "model-candidates-v1"
SYNTHETIC_CASES = (
    {"id": "invoice-01", "input": "Rechnung 1001, netto 100 EUR, MwSt 19 EUR", "expected": {"gross": 119}},
    {"id": "summary-01", "input": "Projekt Alpha endet am 30.09. Budget bleibt unverändert.", "expected": {"deadline": "30.09"}},
    {"id": "privacy-01", "input": "SYNTHETIC: Kundennummer TEST-42", "expected": {"synthetic": True}},
)


def run_benchmark(*, candidate_id: int, created_by: str,
                  evaluator: Callable[[dict[str, Any]], dict[str, Any]],
                  cases: list[dict[str, Any]] | None = None,
                  trial_approval_id: int | None = None) -> dict[str, Any]:
    selected = list(cases or SYNTHETIC_CASES)
    data_kind = "synthetic"
    if cases is not None:
        if trial_approval_id is None:
            raise ComponentDecisionError("Echte oder eigene Testdaten benötigen eine Probefreigabe.")
        now = datetime.now(timezone.utc)
        with engine.begin() as conn:
            approval = conn.execute(select(component_approvals).where(and_(
                component_approvals.c.id == trial_approval_id,
                component_approvals.c.candidate_id == candidate_id,
                component_approvals.c.approval_kind == "trial",
                component_approvals.c.status == "trial_approved",
                component_approvals.c.expires_at > now,
            ))).mappings().first()
        if not approval or (approval["max_records"] is not None and len(selected) > approval["max_records"]):
            raise ComponentDecisionError("Probefreigabe fehlt, ist abgelaufen oder der Umfang ist überschritten.")
        data_kind = "trial_data"
    run = start_evaluation(candidate_id=candidate_id, benchmark_version=BENCHMARK_VERSION,
                           data_kind=data_kind, created_by=created_by)
    outputs = [{"case_id": case["id"], "result": evaluator(case)} for case in selected]
    passed = sum(1 for case, output in zip(selected, outputs)
                 if all(output["result"].get(k) == v for k, v in case.get("expected", {}).items()))
    metrics = {"cases": len(selected), "passed": passed,
               "success_rate": passed / len(selected) if selected else 0.0,
               "source": "trial" if data_kind == "trial_data" else "synthetic"}
    return complete_evaluation(evaluation_run_id=run["evaluation_run_id"],
                               metrics=metrics, artifacts={"outputs": outputs})
