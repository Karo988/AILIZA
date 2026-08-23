"""Governed model-component lifecycle, evidence, approvals and budgets.

The module is deliberately server-side.  UI code may display its decisions
but may not recreate eligibility or approval logic.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, insert, or_, select, update

from .auth.jwt_handler import TokenData
from .auth.totp import verify_totp
from .component_integrity import (
    approval_basis_hash, candidate_hash, provider_profile_hash, sha256_canonical,
)
from .component_vocab import (
    APPROVAL_INVALIDATED, APPROVED, ACTIVE, BLOCKED, DUAL_CONTROL,
    RECOMMENDED, SOLO_COMPENSATED, TRIAL_APPROVED,
)
from .database import (
    _insert_audit_entry_on_connection, _sql_write_lock, engine,
)
from .db_schema import (
    budget_policies, budget_reservations, component_activations,
    component_approvals, component_evidence, cost_events, evaluation_runs,
    model_candidates, tenant_governance_settings, users,
    totp_secrets,
)
from .governance.data_governance import DataClass
from .providers.provider_profiles import check_provider_policy, get_profile


POLICY_VERSION = "component-policy-v1"


class ComponentDecisionError(RuntimeError):
    pass


class BudgetExceeded(ComponentDecisionError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _candidate_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": row["provider"], "model_id": row["model_id"],
        "modalities": row["modalities"], "capabilities": row["capabilities"],
        "context_window": row["context_window"], "regions": row["regions"],
        "benchmark_version": row["benchmark_version"],
        "evidence_urls": row["evidence_urls"],
    }


def configure_organization_mode(*, actor: TokenData, mode: str) -> dict[str, Any]:
    if actor.role != "admin":
        raise ComponentDecisionError("Nur ADMIN darf den Organisationsmodus konfigurieren.")
    if mode not in {"single_person", "multi_person"}:
        raise ValueError("organization_mode muss single_person oder multi_person sein.")
    now = _now()
    with _sql_write_lock, engine.begin() as conn:
        existing = conn.execute(select(tenant_governance_settings).where(
            tenant_governance_settings.c.tenant_id == actor.tenant_id
        )).mappings().first()
        if existing:
            conn.execute(update(tenant_governance_settings).where(
                tenant_governance_settings.c.tenant_id == actor.tenant_id
            ).values(organization_mode=mode, configured_by=actor.user_id, updated_at=now))
        else:
            conn.execute(insert(tenant_governance_settings).values(
                tenant_id=actor.tenant_id, organization_mode=mode,
                configured_by=actor.user_id, configured_at=now, updated_at=now,
            ))
        _insert_audit_entry_on_connection(conn, "tenant.organization_mode.changed", {
            "organization_mode": mode,
        }, actor.tenant_id)
    return {"tenant_id": actor.tenant_id, "organization_mode": mode}


def refresh_candidate_integrity(candidate_id: int) -> dict[str, Any]:
    """Recompute hashes and invalidate approvals if an approval basis changed."""
    now = _now()
    with _sql_write_lock, engine.begin() as conn:
        row = conn.execute(select(model_candidates).where(
            model_candidates.c.id == candidate_id
        )).mappings().first()
        if not row:
            raise ComponentDecisionError("Kandidat nicht gefunden.")
        current = candidate_hash(_candidate_values(dict(row)))
        changed = bool(row["candidate_object_hash"] and row["candidate_object_hash"] != current)
        conn.execute(update(model_candidates).where(model_candidates.c.id == candidate_id).values(
            candidate_object_hash=current,
        ))
        invalidated = 0
        if changed:
            affected_tenants = conn.execute(select(component_approvals.c.tenant_id).where(and_(
                component_approvals.c.candidate_id == candidate_id,
                component_approvals.c.status.in_([APPROVED, TRIAL_APPROVED]),
            )).distinct()).scalars().all()
            result = conn.execute(update(component_approvals).where(and_(
                component_approvals.c.candidate_id == candidate_id,
                component_approvals.c.status.in_([APPROVED, TRIAL_APPROVED]),
            )).values(
                status=APPROVAL_INVALIDATED, invalidated_at=now,
                invalidated_reason="candidate_object_hash_changed",
            ))
            invalidated = result.rowcount
            conn.execute(update(component_activations).where(and_(
                component_activations.c.candidate_id == candidate_id,
                component_activations.c.status == ACTIVE,
            )).values(status=APPROVAL_INVALIDATED, disabled_at=now,
                      disable_reason="candidate_object_hash_changed"))
            for tenant_id in affected_tenants:
                _insert_audit_entry_on_connection(conn, "component.approval.invalidated", {
                    "candidate_id": candidate_id, "reason_code": "CANDIDATE_HASH_CHANGED",
                    "invalidated_count": invalidated,
                }, tenant_id)
    return {"candidate_id": candidate_id, "candidate_object_hash": current,
            "changed": changed, "invalidated_count": invalidated}


def add_evidence(*, candidate_id: int, source_url: str, source_type: str,
                 source_content: str, observed_at: datetime | None = None,
                 valid_until: datetime | None = None,
                 review_status: str = "unreviewed") -> dict[str, Any]:
    if source_type not in {"official", "contract", "benchmark", "operator"}:
        raise ValueError("Unbekannter Evidenztyp.")
    checksum = sha256_canonical({"url": source_url, "content": source_content})
    values = dict(candidate_id=candidate_id, source_url=source_url,
                  source_type=source_type, source_checksum=checksum,
                  observed_at=observed_at or _now(), valid_until=valid_until,
                  review_status=review_status)
    with engine.begin() as conn:
        result = conn.execute(insert(component_evidence).values(**values))
    return {"id": result.inserted_primary_key[0], **values}


def start_evaluation(*, candidate_id: int, benchmark_version: str,
                     data_kind: str, created_by: str) -> dict[str, Any]:
    if data_kind not in {"synthetic", "approved_fixture", "trial_data"}:
        raise ValueError("Unzulässige Bewertungsdatenart.")
    with engine.begin() as conn:
        candidate = conn.execute(select(model_candidates).where(
            model_candidates.c.id == candidate_id
        )).mappings().first()
        if not candidate:
            raise ComponentDecisionError("Kandidat nicht gefunden.")
        run_id = str(uuid.uuid4())
        values = dict(
            evaluation_run_id=run_id, candidate_id=candidate_id,
            candidate_object_hash=candidate["candidate_object_hash"],
            provider_profile_hash=candidate["provider_profile_hash"],
            benchmark_version=benchmark_version, data_kind=data_kind,
            status="running", metrics={}, artifact_checksum=None,
            started_at=_now(), completed_at=None, created_by=created_by,
        )
        conn.execute(insert(evaluation_runs).values(**values))
    return values


def complete_evaluation(*, evaluation_run_id: str, metrics: dict[str, Any],
                        artifacts: dict[str, Any]) -> dict[str, Any]:
    checksum = sha256_canonical(artifacts)
    now = _now()
    with _sql_write_lock, engine.begin() as conn:
        run = conn.execute(select(evaluation_runs).where(
            evaluation_runs.c.evaluation_run_id == evaluation_run_id
        )).mappings().first()
        if not run or run["status"] != "running":
            raise ComponentDecisionError("Bewertungslauf ist nicht offen.")
        candidate = conn.execute(select(model_candidates).where(
            model_candidates.c.id == run["candidate_id"]
        )).mappings().one()
        updated_values = dict(candidate)
        updated_values["benchmark_version"] = run["benchmark_version"]
        updated_hash = candidate_hash(_candidate_values(updated_values))
        conn.execute(update(evaluation_runs).where(
            evaluation_runs.c.evaluation_run_id == evaluation_run_id
        ).values(status="completed", metrics=metrics,
                 candidate_object_hash=updated_hash,
                 artifact_checksum=checksum, completed_at=now))
        conn.execute(update(model_candidates).where(
            model_candidates.c.id == run["candidate_id"]
        ).values(status=RECOMMENDED, benchmark_version=run["benchmark_version"],
                 candidate_object_hash=updated_hash, updated_at=now))
        _insert_audit_entry_on_connection(conn, "evaluation.completed", {
            "evaluation_run_id": evaluation_run_id,
            "candidate_id": run["candidate_id"],
            "artifact_checksum": checksum,
        }, "default")
    return {"evaluation_run_id": evaluation_run_id, "status": "completed",
            "metrics": metrics, "artifact_checksum": checksum}


def _validate_solo(conn: Any, *, actor: TokenData, candidate: dict[str, Any],
                   totp_code: str | None, reason: str, task_package: str,
                   cost_limit: float, approval_kind: str) -> None:
    setting = conn.execute(select(tenant_governance_settings).where(
        tenant_governance_settings.c.tenant_id == actor.tenant_id
    )).mappings().first()
    if not setting or setting["organization_mode"] != "single_person":
        raise ComponentDecisionError("Solo-Freigabe ist für diesen Mandanten nicht konfiguriert.")
    admin_count = conn.execute(select(func.count()).select_from(users).where(and_(
        users.c.tenant_id == actor.tenant_id, users.c.role == "admin", users.c.active == 1,
    ))).scalar_one()
    if admin_count != 1 or actor.role != "admin":
        raise ComponentDecisionError("Solo-Freigabe verlangt genau einen aktiven ADMIN.")
    record = conn.execute(select(totp_secrets).where(and_(
        totp_secrets.c.user_id == actor.user_id,
        totp_secrets.c.tenant_id == actor.tenant_id,
    ))).mappings().first()
    if (not record or record.get("tenant_id") != actor.tenant_id
            or not record.get("confirmed") or not totp_code
            or not verify_totp(record["secret_b32"], totp_code)):
        raise ComponentDecisionError("Gültige TOTP-Bestätigung erforderlich.")
    if len(reason.strip()) < 20:
        raise ComponentDecisionError("Begründung muss mindestens 20 Zeichen enthalten.")
    if not task_package.strip() or cost_limit <= 0:
        raise ComponentDecisionError("Aufgabenpaket und positives Kostenlimit sind Pflicht.")
    if candidate.get("privacy_score") is None or float(candidate["privacy_score"]) < 0.8:
        raise ComponentDecisionError("Solo-Freigabe verlangt einen belegten privacy_score von mindestens 0,8.")
    completed_run = conn.execute(select(func.count()).select_from(evaluation_runs).where(and_(
        evaluation_runs.c.candidate_id == candidate["id"],
        evaluation_runs.c.status == "completed",
        evaluation_runs.c.candidate_object_hash == candidate["candidate_object_hash"],
    ))).scalar_one()
    if completed_run < 1:
        raise ComponentDecisionError("Solo-Freigabe verlangt einen abgeschlossenen Bewertungslauf.")
    if candidate["provider"] != "local" and approval_kind == "full":
        if _now() - _aware(candidate["created_at"]) < timedelta(hours=24):
            raise ComponentDecisionError("Externe Erstfreigabe erfordert 24 Stunden Abkühlfrist.")


def approve_component(*, candidate_id: int, actor: TokenData,
                      approval_mode: str, approval_kind: str,
                      task_package: str, purpose: str,
                      allowed_data_classes: list[str], cost_limit: float,
                      reason: str, totp_code: str | None = None,
                      max_records: int | None = None,
                      validity_days: int | None = None) -> dict[str, Any]:
    if approval_mode not in {DUAL_CONTROL, SOLO_COMPENSATED}:
        raise ComponentDecisionError("Dieser Freigabemodus kann nicht aktivieren.")
    if approval_kind not in {"trial", "full"}:
        raise ValueError("approval_kind muss trial oder full sein.")
    if actor.role not in {"manager", "admin"}:
        raise ComponentDecisionError("Keine Modellfreigabeberechtigung.")
    if not purpose.strip() or cost_limit <= 0:
        raise ComponentDecisionError("Zweck und positives Kostenlimit sind Pflicht.")
    now = _now()
    duration = validity_days if validity_days is not None else (14 if approval_kind == "trial" else 90)
    if duration < 1 or duration > 90:
        raise ValueError("Freigabe darf höchstens 90 Tage gelten.")
    with _sql_write_lock, engine.begin() as conn:
        candidate = conn.execute(select(model_candidates).where(
            model_candidates.c.id == candidate_id
        )).mappings().first()
        if not candidate:
            raise ComponentDecisionError("Kandidat nicht gefunden.")
        expected_hash = candidate_hash(_candidate_values(dict(candidate)))
        if candidate["candidate_object_hash"] != expected_hash:
            raise ComponentDecisionError("Kandidat wurde nach der Profilierung verändert.")
        profile = get_profile(candidate["provider"])
        if not profile or not candidate["provider_profile_hash"]:
            raise ComponentDecisionError("Versioniertes Anbieterprofil fehlt.")
        try:
            requested_classes = [DataClass(value) for value in allowed_data_classes]
        except ValueError as exc:
            raise ComponentDecisionError("Unbekannte Datenklasse in der Freigabe.") from exc
        provider_allowed, provider_reason = check_provider_policy(
            candidate["provider"], requested_classes, "kmu_assistant",
        )
        if not provider_allowed:
            raise ComponentDecisionError(f"Anbieterprofil sperrt diese Daten: {provider_reason}")
        if approval_mode == SOLO_COMPENSATED:
            _validate_solo(conn, actor=actor, candidate=dict(candidate),
                           totp_code=totp_code, reason=reason,
                           task_package=task_package, cost_limit=cost_limit,
                           approval_kind=approval_kind)
        else:
            if str(candidate["created_by"]).strip().casefold() == actor.user_id.strip().casefold():
                raise ComponentDecisionError("Dual-Control erlaubt keine Selbstfreigabe.")
        basis_hash = approval_basis_hash(
            candidate_object_hash=expected_hash,
            provider_profile_hash_value=candidate["provider_profile_hash"],
            provider_profile_version=candidate["provider_profile_version"],
            task_package=task_package, purpose=purpose,
            allowed_data_classes=allowed_data_classes, cost_limit=cost_limit,
            policy_version=POLICY_VERSION,
        )
        status = TRIAL_APPROVED if approval_kind == "trial" else APPROVED
        values = dict(
            candidate_id=candidate_id, tenant_id=actor.tenant_id,
            approval_mode=approval_mode, approval_kind=approval_kind, status=status,
            candidate_object_hash=expected_hash,
            provider_profile_version=candidate["provider_profile_version"],
            provider_profile_hash=candidate["provider_profile_hash"],
            approval_basis_hash=basis_hash, task_package=task_package,
            purpose=purpose, allowed_data_classes=allowed_data_classes,
            max_records=max_records, cost_limit=cost_limit,
            approver_user_id=actor.user_id, reason=reason.strip(),
            approved_at=now, expires_at=now + timedelta(days=duration),
            invalidated_at=None, invalidated_reason=None,
        )
        result = conn.execute(insert(component_approvals).values(**values))
        approval_id = result.inserted_primary_key[0]
        if approval_kind == "full":
            conn.execute(update(model_candidates).where(
                model_candidates.c.id == candidate_id
            ).values(status=APPROVED, approved_by=actor.user_id,
                     approved_at=now, updated_at=now))
        action = ("model.approval.solo_compensated"
                  if approval_mode == SOLO_COMPENSATED else "model.approval.dual_control")
        _insert_audit_entry_on_connection(conn, action, {
            "approval_id": approval_id, "candidate_id": candidate_id,
            "approval_kind": approval_kind, "task_package": task_package,
            "approval_basis_hash": basis_hash,
        }, actor.tenant_id)
    return {"id": approval_id, **values}


def set_budget_policy(*, actor: TokenData, task_package: str, hard_limit: float,
                      warning_threshold: float, period_start: datetime,
                      period_end: datetime, currency: str = "EUR") -> dict[str, Any]:
    if actor.role != "admin":
        raise ComponentDecisionError("Nur ADMIN darf Budgetregeln ändern.")
    if hard_limit <= 0 or not 0 <= warning_threshold <= hard_limit:
        raise ValueError("Ungültige Budgetgrenzen.")
    if period_end <= period_start:
        raise ValueError("Budgetzeitraum ist ungültig.")
    now = _now()
    values = dict(tenant_id=actor.tenant_id, task_package=task_package,
                  currency=currency, hard_limit=hard_limit,
                  warning_threshold=warning_threshold,
                  period_start=period_start, period_end=period_end,
                  created_by=actor.user_id, created_at=now, updated_at=now)
    with _sql_write_lock, engine.begin() as conn:
        result = conn.execute(insert(budget_policies).values(**values))
        policy_id = result.inserted_primary_key[0]
        _insert_audit_entry_on_connection(conn, "budget.policy.created", {
            "policy_id": policy_id, "task_package": task_package,
            "hard_limit": hard_limit, "currency": currency,
        }, actor.tenant_id)
    return {"id": policy_id, **values}


def reserve_budget(*, tenant_id: str, task_package: str, amount: float) -> dict[str, Any]:
    if amount <= 0:
        raise ValueError("Reservierungsbetrag muss positiv sein.")
    now = _now()
    with _sql_write_lock, engine.begin() as conn:
        policy = conn.execute(select(budget_policies).where(and_(
            budget_policies.c.tenant_id == tenant_id,
            budget_policies.c.task_package == task_package,
            budget_policies.c.period_start <= now,
            budget_policies.c.period_end > now,
        )).order_by(budget_policies.c.period_start.desc())).mappings().first()
        if not policy:
            raise BudgetExceeded("Keine aktive Budgetregel; Provideraufruf gesperrt.")
        used = conn.execute(select(func.coalesce(func.sum(
            func.coalesce(budget_reservations.c.amount_actual,
                          budget_reservations.c.amount_reserved)
        ), 0.0)).where(and_(
            budget_reservations.c.policy_id == policy["id"],
            budget_reservations.c.status.in_(["reserved", "settled"]),
        ))).scalar_one()
        if float(used) + amount > float(policy["hard_limit"]):
            raise BudgetExceeded("Kostenmaximum erreicht; Provideraufruf gesperrt.")
        reservation_id = str(uuid.uuid4())
        conn.execute(insert(budget_reservations).values(
            reservation_id=reservation_id, policy_id=policy["id"],
            tenant_id=tenant_id, task_package=task_package,
            amount_reserved=amount, amount_actual=None, status="reserved",
            created_at=now, settled_at=None,
        ))
        conn.execute(insert(cost_events).values(
            reservation_id=reservation_id, tenant_id=tenant_id,
            task_package=task_package, provider=None, model=None,
            event_type="reserved", amount=amount, created_at=now,
        ))
    return {"reservation_id": reservation_id, "amount_reserved": amount,
            "currency": policy["currency"]}


def settle_budget(*, reservation_id: str, actual_amount: float,
                  provider: str | None, model: str | None,
                  failed: bool = False) -> dict[str, Any]:
    if actual_amount < 0:
        raise ValueError("Tatsächliche Kosten dürfen nicht negativ sein.")
    now = _now()
    with _sql_write_lock, engine.begin() as conn:
        row = conn.execute(select(budget_reservations).where(
            budget_reservations.c.reservation_id == reservation_id
        )).mappings().first()
        if not row or row["status"] != "reserved":
            raise ComponentDecisionError("Reservierung fehlt oder wurde bereits abgeschlossen.")
        effective = 0.0 if failed else actual_amount
        if effective > row["amount_reserved"]:
            raise BudgetExceeded("Tatsächliche Kosten überschreiten die Reservierung.")
        status = "released" if failed else "settled"
        conn.execute(update(budget_reservations).where(
            budget_reservations.c.reservation_id == reservation_id
        ).values(amount_actual=effective, status=status, settled_at=now))
        conn.execute(insert(cost_events).values(
            reservation_id=reservation_id, tenant_id=row["tenant_id"],
            task_package=row["task_package"], provider=provider, model=model,
            event_type=status, amount=effective, created_at=now,
        ))
    return {"reservation_id": reservation_id, "status": status,
            "amount_actual": effective}


def activate_component(*, approval_id: int, actor: TokenData,
                       fallback_candidate_id: int | None = None) -> dict[str, Any]:
    if actor.role != "admin":
        raise ComponentDecisionError("Nur ADMIN darf Bausteine aktivieren.")
    now = _now()
    with _sql_write_lock, engine.begin() as conn:
        approval = conn.execute(select(component_approvals).where(and_(
            component_approvals.c.id == approval_id,
            component_approvals.c.tenant_id == actor.tenant_id,
        ))).mappings().first()
        if not approval or approval["status"] != APPROVED or _aware(approval["expires_at"]) <= now:
            raise ComponentDecisionError("Keine gültige Vollfreigabe.")
        candidate = conn.execute(select(model_candidates).where(
            model_candidates.c.id == approval["candidate_id"]
        )).mappings().first()
        if not candidate or candidate["candidate_object_hash"] != approval["candidate_object_hash"]:
            raise ComponentDecisionError("Freigabegrundlage hat sich geändert.")
        live_profile = get_profile(candidate["provider"])
        if (not live_profile
                or live_profile.profile_version != approval["provider_profile_version"]
                or provider_profile_hash(live_profile) != approval["provider_profile_hash"]):
            raise ComponentDecisionError("Das Anbieterprofil hat sich seit der Freigabe geändert.")
        current_basis = approval_basis_hash(
            candidate_object_hash=approval["candidate_object_hash"],
            provider_profile_hash_value=approval["provider_profile_hash"],
            provider_profile_version=approval["provider_profile_version"],
            task_package=approval["task_package"], purpose=approval["purpose"],
            allowed_data_classes=approval["allowed_data_classes"],
            cost_limit=approval["cost_limit"], policy_version=POLICY_VERSION,
        )
        if current_basis != approval["approval_basis_hash"]:
            raise ComponentDecisionError("Der Freigabevertrag ist nicht mehr unverändert.")
        values = dict(
            approval_id=approval_id, candidate_id=approval["candidate_id"],
            tenant_id=actor.tenant_id, task_package=approval["task_package"],
            status=ACTIVE, fallback_candidate_id=fallback_candidate_id,
            activated_by=actor.user_id, activated_at=now,
            disabled_at=None, disable_reason=None,
        )
        result = conn.execute(insert(component_activations).values(**values))
        activation_id = result.inserted_primary_key[0]
        _insert_audit_entry_on_connection(conn, "component.activated", {
            "activation_id": activation_id, "approval_id": approval_id,
            "candidate_id": approval["candidate_id"],
            "task_package": approval["task_package"],
        }, actor.tenant_id)
    return {"id": activation_id, **values}


def disable_component(*, activation_id: int, actor: TokenData,
                      reason: str) -> dict[str, Any]:
    if actor.role != "admin" or len(reason.strip()) < 10:
        raise ComponentDecisionError("ADMIN und eine nachvollziehbare Begründung sind erforderlich.")
    now = _now()
    with _sql_write_lock, engine.begin() as conn:
        row = conn.execute(select(component_activations).where(and_(
            component_activations.c.id == activation_id,
            component_activations.c.tenant_id == actor.tenant_id,
            component_activations.c.status == ACTIVE,
        ))).mappings().first()
        if not row:
            raise ComponentDecisionError("Aktivierung nicht gefunden.")
        conn.execute(update(component_activations).where(
            component_activations.c.id == activation_id
        ).values(status="disabled", disabled_at=now, disable_reason=reason.strip()))
        _insert_audit_entry_on_connection(conn, "component.disabled", {
            "activation_id": activation_id, "candidate_id": row["candidate_id"],
            "fallback_candidate_id": row["fallback_candidate_id"],
            "reason": reason.strip(),
        }, actor.tenant_id)
    return {"id": activation_id, "status": "disabled",
            "fallback_candidate_id": row["fallback_candidate_id"]}


def board_entries(*, tenant_id: str, data_classes: list[str],
                  task_package: str, use_case: str = "kmu_assistant") -> dict[str, list[dict[str, Any]]]:
    now = _now()
    classes: list[DataClass] = []
    for value in data_classes:
        try:
            classes.append(DataClass(value))
        except ValueError:
            classes.append(DataClass.CREDENTIALS)  # fail closed
    with engine.begin() as conn:
        candidates = conn.execute(select(model_candidates)).mappings().all()
        approvals = conn.execute(select(component_approvals).where(and_(
            component_approvals.c.tenant_id == tenant_id,
            component_approvals.c.expires_at > now,
        ))).mappings().all()
        activations = conn.execute(select(component_activations).where(and_(
            component_activations.c.tenant_id == tenant_id,
            component_activations.c.status == ACTIVE,
        ))).mappings().all()
    approval_by_candidate = {a["candidate_id"]: a for a in approvals}
    active_by_candidate = {a["candidate_id"]: a for a in activations}
    result = {"recommended": [], "active": [], "blocked": []}
    for row in candidates:
        allowed, reason = check_provider_policy(row["provider"], classes, use_case)
        item = {
            "candidate_id": row["id"], "provider": row["provider"],
            "model_id": row["model_id"], "candidate_status": row["status"],
            "task_package": task_package, "data_classes": data_classes,
            "eligibility": "eligible" if allowed else "blocked",
            "reason": reason,
            "approval_status": approval_by_candidate.get(row["id"], {}).get("status"),
            "active": row["id"] in active_by_candidate,
            "benchmark_version": row["benchmark_version"],
        }
        if not allowed:
            result["blocked"].append(item)
        elif item["active"]:
            result["active"].append(item)
        elif row["status"] in {RECOMMENDED, APPROVED, "benchmarked"}:
            result["recommended"].append(item)
    return result


def recommend_active_model(*, tenant_id: str, task_package: str,
                           modality: str, task: str,
                           data_classes: list[DataClass], prompt_text: str,
                           required_capabilities: list[str] | None = None,
                           min_context_window: int = 0,
                           required_region: str | None = None,
                           local_only: bool = False,
                           use_case: str = "kmu_assistant") -> dict[str, Any]:
    """Route only among active, hash-valid approval contracts for a task."""
    from .intelligence.model_router import ModelRouter
    from .intelligence.models import ModelCandidate, RoutingRequest

    if not prompt_text.strip():
        raise ComponentDecisionError("Klassifizierbarer Text ist für Routing erforderlich.")
    now = _now()
    with engine.begin() as conn:
        rows = conn.execute(
            select(model_candidates, component_activations.c.id.label("activation_id"),
                   component_approvals.c.expires_at,
                   component_approvals.c.candidate_object_hash.label("approved_candidate_hash"),
                   component_approvals.c.provider_profile_hash.label("approved_provider_hash"),
                   component_approvals.c.allowed_data_classes)
            .select_from(component_activations
                .join(component_approvals, component_activations.c.approval_id == component_approvals.c.id)
                .join(model_candidates, component_activations.c.candidate_id == model_candidates.c.id))
            .where(and_(
                component_activations.c.tenant_id == tenant_id,
                component_activations.c.task_package == task_package,
                component_activations.c.status == ACTIVE,
                component_approvals.c.status == APPROVED,
                component_approvals.c.expires_at > now,
            ))
        ).mappings().all()
    eligible_rows: list[dict[str, Any]] = []
    required_dc = {dc.value for dc in data_classes}
    for row in rows:
        if row["candidate_object_hash"] != row["approved_candidate_hash"]:
            continue
        if row["provider_profile_hash"] != row["approved_provider_hash"]:
            continue
        if not required_dc.issubset(set(row["allowed_data_classes"] or [])):
            continue
        provider_ok, _reason = check_provider_policy(row["provider"], data_classes, use_case)
        if not provider_ok:
            continue
        candidate = dict(row)
        candidate["status"] = APPROVED  # activation + valid contract is the authority
        eligible_rows.append(candidate)
    candidates = [ModelCandidate.from_row(row) for row in eligible_rows]
    request = RoutingRequest(
        modality=modality, task=task,
        required_capabilities=frozenset(required_capabilities or []),
        min_context_window=min_context_window, allowed_providers=None,
        required_region=required_region, local_only=local_only,
        data_risk="high" if required_dc & {
            "personal_data", "financial", "security_sensitive",
            "intellectual_property", "hr", "legal", "special_category",
        } else "low",
    )
    decision = ModelRouter(candidates).route(request)
    if not decision.selected:
        raise ComponentDecisionError(decision.reason)
    provider, model = decision.selected.split(":", 1)
    return {
        "provider": provider, "model": model,
        "fallback": decision.fallback, "score": decision.score,
        "reason": decision.reason, "considered": decision.considered,
    }
