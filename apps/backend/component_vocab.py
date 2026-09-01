"""Canonical vocabulary for governed AILIZA components.

This module intentionally contains constants and transition data only.  It is
the shared contract for persistence, policy and user interfaces; it performs
no authorization and no database access.
"""
from __future__ import annotations


# Integrity and evidence identifiers.
CANDIDATE_OBJECT_HASH = "candidate_object_hash"
PROVIDER_PROFILE_VERSION = "provider_profile_version"
PROVIDER_PROFILE_HASH = "provider_profile_hash"
APPROVAL_BASIS_HASH = "approval_basis_hash"
EVALUATION_RUN_ID = "evaluation_run_id"
ARTIFACT_CHECKSUM = "artifact_checksum"
BENCHMARK_VERSION = "benchmark_version"


# Explicit permissions.  Roles may be mapped to these permissions, but their
# numeric ordering must never imply one of these capabilities.
COMPONENT_VIEW = "component.view"
COMPONENT_EVALUATE = "component.evaluate"
COMPONENT_TRIAL_APPROVE = "component.trial_approve"
COMPONENT_FULL_APPROVE = "component.full_approve"
COMPONENT_ACTIVATE = "component.activate"
COMPONENT_DISABLE = "component.disable"
PROVIDER_REVIEW = "provider.review"
PROVIDER_APPROVE = "provider.approve"
PRIVACY_REVIEW = "privacy.review"
BUDGET_CHANGE = "budget.change"
AUDIT_READ = "audit.read"

COMPONENT_PERMISSIONS = frozenset({
    COMPONENT_VIEW,
    COMPONENT_EVALUATE,
    COMPONENT_TRIAL_APPROVE,
    COMPONENT_FULL_APPROVE,
    COMPONENT_ACTIVATE,
    COMPONENT_DISABLE,
    PROVIDER_REVIEW,
    PROVIDER_APPROVE,
    PRIVACY_REVIEW,
    BUDGET_CHANGE,
    AUDIT_READ,
})

DUAL_CONTROL = "dual_control"
SOLO_COMPENSATED = "solo_compensated"
RESPONSIBILITY_HANDOFF = "responsibility_handoff"
APPROVAL_MODES = frozenset({
    DUAL_CONTROL,
    SOLO_COMPENSATED,
    RESPONSIBILITY_HANDOFF,
})


DISCOVERED = "discovered"
PROFILED = "profiled"
CANDIDATE = "candidate"
BENCHMARKED = "benchmarked"
RECOMMENDED = "recommended"
TRIAL_REQUESTED = "trial_requested"
TRIAL_APPROVED = "trial_approved"
TRIAL_RUNNING = "trial_running"
TRIAL_EVALUATED = "trial_evaluated"
APPROVAL_REQUESTED = "approval_requested"
APPROVED = "approved"
ACTIVE = "active"
DEGRADED = "degraded"
DEPRECATED = "deprecated"
RETIRED = "retired"
ARCHIVED = "archived"
PURGE_ELIGIBLE = "purge_eligible"
PURGED = "purged"

REJECTED = "rejected"
BLOCKED = "blocked"
QUARANTINED = "quarantined"
TRIAL_REVOKED = "trial_revoked"
TRIAL_EXPIRED = "trial_expired"
APPROVAL_EXPIRED = "approval_expired"
APPROVAL_INVALIDATED = "approval_invalidated"
REPLACEMENT_REQUIRED = "replacement_required"
DISABLED = "disabled"

COMPONENT_STATES = (
    DISCOVERED,
    PROFILED,
    CANDIDATE,
    BENCHMARKED,
    RECOMMENDED,
    TRIAL_REQUESTED,
    TRIAL_APPROVED,
    TRIAL_RUNNING,
    TRIAL_EVALUATED,
    APPROVAL_REQUESTED,
    APPROVED,
    ACTIVE,
    DEGRADED,
    DEPRECATED,
    RETIRED,
    ARCHIVED,
    PURGE_ELIGIBLE,
    PURGED,
    REJECTED,
    BLOCKED,
    QUARANTINED,
    TRIAL_REVOKED,
    TRIAL_EXPIRED,
    APPROVAL_EXPIRED,
    APPROVAL_INVALIDATED,
    REPLACEMENT_REQUIRED,
    DISABLED,
)


# State transitions are deliberately explicit.  Recovery from a side state
# always returns to a reviewable state, never directly to ACTIVE.
ALLOWED_COMPONENT_TRANSITIONS = frozenset({
    (DISCOVERED, PROFILED),
    (PROFILED, CANDIDATE),
    (CANDIDATE, BENCHMARKED),
    (BENCHMARKED, RECOMMENDED),
    (RECOMMENDED, TRIAL_REQUESTED),
    (TRIAL_REQUESTED, TRIAL_APPROVED),
    (TRIAL_APPROVED, TRIAL_RUNNING),
    (TRIAL_RUNNING, TRIAL_EVALUATED),
    (TRIAL_EVALUATED, APPROVAL_REQUESTED),
    (APPROVAL_REQUESTED, APPROVED),
    (APPROVED, ACTIVE),
    (ACTIVE, DEGRADED),
    (DEGRADED, ACTIVE),
    (ACTIVE, DEPRECATED),
    (DEGRADED, DEPRECATED),
    (DEPRECATED, RETIRED),
    (RETIRED, ARCHIVED),
    (ARCHIVED, PURGE_ELIGIBLE),
    (PURGE_ELIGIBLE, PURGED),
    (DISCOVERED, REJECTED),
    (PROFILED, REJECTED),
    (CANDIDATE, REJECTED),
    (BENCHMARKED, REJECTED),
    (RECOMMENDED, REJECTED),
    (TRIAL_REQUESTED, REJECTED),
    (APPROVAL_REQUESTED, REJECTED),
    (DISCOVERED, BLOCKED),
    (PROFILED, BLOCKED),
    (CANDIDATE, BLOCKED),
    (BENCHMARKED, BLOCKED),
    (RECOMMENDED, BLOCKED),
    (ACTIVE, BLOCKED),
    (DISCOVERED, QUARANTINED),
    (PROFILED, QUARANTINED),
    (CANDIDATE, QUARANTINED),
    (TRIAL_RUNNING, QUARANTINED),
    (TRIAL_APPROVED, TRIAL_REVOKED),
    (TRIAL_RUNNING, TRIAL_REVOKED),
    (TRIAL_APPROVED, TRIAL_EXPIRED),
    (TRIAL_RUNNING, TRIAL_EXPIRED),
    (APPROVED, APPROVAL_EXPIRED),
    (ACTIVE, APPROVAL_EXPIRED),
    (APPROVED, APPROVAL_INVALIDATED),
    (ACTIVE, APPROVAL_INVALIDATED),
    (DEGRADED, APPROVAL_INVALIDATED),
    (ACTIVE, REPLACEMENT_REQUIRED),
    (DEGRADED, REPLACEMENT_REQUIRED),
    (APPROVED, DISABLED),
    (ACTIVE, DISABLED),
    (DEGRADED, DISABLED),
    (REPLACEMENT_REQUIRED, DISABLED),
    (BLOCKED, CANDIDATE),
    (QUARANTINED, CANDIDATE),
    (TRIAL_REVOKED, TRIAL_REQUESTED),
    (TRIAL_EXPIRED, TRIAL_REQUESTED),
    (APPROVAL_EXPIRED, APPROVAL_REQUESTED),
    (APPROVAL_INVALIDATED, CANDIDATE),
    (REPLACEMENT_REQUIRED, DEPRECATED),
    (DISABLED, APPROVED),
})


SESSION_SCOPE = "session"
PERSONAL_SCOPE = "personal"
PROJECT_SCOPE = "project"
COMPANY_SCOPE = "company"
MEMORY_SCOPES = frozenset({
    SESSION_SCOPE,
    PERSONAL_SCOPE,
    PROJECT_SCOPE,
    COMPANY_SCOPE,
})
