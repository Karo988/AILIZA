"""
AILIZA Skill-Store
==================
Kontrollierter Skill-Learning-Loop.

Ablauf (PFLICHT):
  1. skill_propose()  → capability check "skill_propose" → sanitize → DB pending
  2. Admin sieht Vorschau in /admin/skills
  3. Admin genehmigt oder verwirft
  4. Bei Genehmigung: capability check "memory_store" → persist as approved
  5. Audit-light nach jedem Schritt (kein Inhalt, kein PII)

DSGVO: Art. 5 (Zweckbindung, Datenminimierung), Art. 25 (Privacy by Design).
EU AI Act: Art. 9 (Risikomanagement), Art. 13 (Transparenz), Art. 14 (Menschliche Aufsicht).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from ..governance.data_governance import DataClass, classify
    from ..governance.redaction import redact
    from ..capabilities.registry import check_capability
    from ..database import engine, skills as skills_table, write_audit_entry, DEFAULT_TENANT_ID
    from ..errors import AILIZAError
except ImportError:
    from governance.data_governance import DataClass, classify
    from governance.redaction import redact
    from capabilities.registry import check_capability
    from database import engine, skills as skills_table, write_audit_entry, DEFAULT_TENANT_ID
    from errors import AILIZAError

from sqlalchemy import insert, select, update


# ── Sanitizer: kein PII, keine Secrets, keine Vollkonversationen ──────────────
_STRIP_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),                              # API-Keys
    re.compile(r"\bgsk_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),  # E-Mail
    re.compile(r"(?:(?:\+49|0049)[\s\-/]?|\b0)(?:\d[\s\-/]?){6,14}\d"),   # Telefon
    re.compile(r"\bDE\d{20}\b"),                                            # IBAN
    re.compile(r"\b(password|passwd|token|api[_-]?key|secret)\s*[=:]\s*\S+", re.I),
]

_MAX_SKILL_CONTENT_CHARS = 2000


def _sanitize(text: str) -> str:
    """Entfernt PII und Secrets. Kuerzt auf Max-Laenge. Fail-closed."""
    try:
        for pat in _STRIP_PATTERNS:
            text = pat.sub("[ENTFERNT]", text)
        # Redaktion via Governance-Layer
        classification = classify(text)
        redacted = redact(text, classification)
        text = redacted.redacted_text
        return text[:_MAX_SKILL_CONTENT_CHARS]
    except Exception:
        return "[Inhalt konnte nicht bereinigt werden]"


def _contains_sensitive(text: str) -> bool:
    """True wenn nach Sanitierung noch sensible Daten erkennbar."""
    classification = classify(text)
    return classification.highest_risk_class in {
        DataClass.CREDENTIALS, DataClass.SPECIAL_CATEGORY,
        DataClass.HR, DataClass.LEGAL,
    }


# ── Datenklasse fuer Skill-Vorschlag ─────────────────────────────────────────
@dataclass
class SkillProposal:
    skill_id: str
    name: str
    description: str
    steps_summary: str       # Abstrahiertes Vorgehen — KEIN Vollinhalt
    source_run_id: str | None
    data_classes: list[str]
    risk_level: str
    gdpr_purpose: str
    tenant_id: str
    proposed_by: str | None
    status: str              # pending / approved / rejected
    created_at: datetime
    approved_at: datetime | None = None
    approved_by: str | None = None
    rejection_reason: str | None = None


# ── Propose: Schritt 1 ────────────────────────────────────────────────────────
def propose_skill(
    name: str,
    description: str,
    steps_summary: str,
    gdpr_purpose: str,
    data_classes: list[DataClass],
    tenant_id: str = DEFAULT_TENANT_ID,
    user_id: str | None = None,
    source_run_id: str | None = None,
) -> SkillProposal:
    """
    Schlaegt einen neuen Skill vor. Speichert NICHT direkt.
    Capability-Check, Sanitierung, Sensitivitaetspruefung — dann pending.
    """
    # 1. Capability-Check: darf skill_propose ausgefuehrt werden?
    cap_result = check_capability(
        "skill_propose", data_classes=data_classes,
        tenant_id=tenant_id, user_id=user_id, approval_given=False,
    )
    if not cap_result.allowed and cap_result.decision.value != "approval_required":
        _audit("skill.propose.blocked", tenant_id, {
            "reason": cap_result.reason, "risk_level": cap_result.risk_level,
        })
        raise AILIZAError.from_code("policy_blocked")

    # 2. Sanitierung — kein PII, keine Secrets
    clean_name = _sanitize(name)[:128]
    clean_desc = _sanitize(description)[:512]
    clean_steps = _sanitize(steps_summary)

    # 3. Residual-Sensitivitaetspruefung nach Sanitierung
    if _contains_sensitive(clean_steps):
        _audit("skill.propose.sensitivity_fail", tenant_id, {"risk": "residual_sensitive_content"})
        raise AILIZAError(
            "Der Skill-Vorschlag enthält nach der Bereinigung noch sensible Daten und kann nicht gespeichert werden.",
            "policy_blocked",
        )

    # 4. In DB speichern als "pending" — KEIN memory_store-Check hier, nur Vorschlag
    skill_id = str(uuid.uuid4())
    dc_values = [dc.value for dc in data_classes]
    risk = cap_result.risk_level

    with engine.begin() as conn:
        conn.execute(insert(skills_table).values(
            skill_id=skill_id,
            tenant_id=tenant_id,
            name=clean_name,
            description=clean_desc,
            steps_summary=clean_steps,
            data_classes=dc_values,
            risk_level=risk,
            gdpr_purpose=gdpr_purpose[:256],
            source_run_id=source_run_id,
            proposed_by=user_id,
            status="pending",
            created_at=datetime.now(timezone.utc),
        ))

    _audit("skill.propose.created", tenant_id, {
        "skill_id": skill_id, "risk_level": risk,
        "data_classes": dc_values, "requires_approval": True,
    })

    return SkillProposal(
        skill_id=skill_id, name=clean_name, description=clean_desc,
        steps_summary=clean_steps, source_run_id=source_run_id,
        data_classes=dc_values, risk_level=risk,
        gdpr_purpose=gdpr_purpose, tenant_id=tenant_id,
        proposed_by=user_id, status="pending",
        created_at=datetime.now(timezone.utc),
    )


# ── Approve: Schritt 3+4 ──────────────────────────────────────────────────────
def approve_skill(
    skill_id: str,
    approved_by: str,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    """
    Admin genehmigt einen Skill-Vorschlag.
    Laueft durch memory_store capability-check bevor persistiert wird.
    """
    row = _get_skill(skill_id, tenant_id)
    if row is None:
        raise AILIZAError("Skill-Vorschlag nicht gefunden.", "internal_error")
    if row["status"] != "pending":
        raise AILIZAError(f"Skill ist bereits '{row['status']}'.", "internal_error")

    # memory_store Capability-Check mit den Datenklassen des Skills
    dc_list = [DataClass(dc) for dc in (row["data_classes"] or [])]
    cap_result = check_capability(
        "memory_store", data_classes=dc_list,
        tenant_id=tenant_id, user_id=approved_by,
        approval_given=True,  # Admin genehmigt explizit
    )
    if not cap_result.allowed:
        _audit("skill.approve.blocked", tenant_id, {
            "skill_id": skill_id, "reason": cap_result.reason,
        })
        raise AILIZAError.from_code("policy_blocked")

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            update(skills_table)
            .where(skills_table.c.skill_id == skill_id)
            .where(skills_table.c.tenant_id == tenant_id)
            .values(status="approved", approved_by=approved_by, approved_at=now)
        )

    _audit("skill.approve.granted", tenant_id, {
        "skill_id": skill_id, "approved_by": approved_by,
        "risk_level": row["risk_level"],
    })
    return {**row, "status": "approved", "approved_by": approved_by, "approved_at": now.isoformat()}


def reject_skill(
    skill_id: str,
    rejected_by: str,
    reason: str,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    """Admin verwirft einen Skill-Vorschlag."""
    row = _get_skill(skill_id, tenant_id)
    if row is None:
        raise AILIZAError("Skill-Vorschlag nicht gefunden.", "internal_error")

    with engine.begin() as conn:
        conn.execute(
            update(skills_table)
            .where(skills_table.c.skill_id == skill_id)
            .where(skills_table.c.tenant_id == tenant_id)
            .values(status="rejected", rejection_reason=_sanitize(reason)[:512])
        )

    _audit("skill.reject", tenant_id, {
        "skill_id": skill_id, "rejected_by": rejected_by,
    })
    return {**row, "status": "rejected"}


# ── Lesen ─────────────────────────────────────────────────────────────────────
def list_skills(
    tenant_id: str = DEFAULT_TENANT_ID,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = select(skills_table).where(skills_table.c.tenant_id == tenant_id).limit(limit)
    if status:
        query = query.where(skills_table.c.status == status)
    with engine.begin() as conn:
        return [dict(r) for r in conn.execute(query).mappings().all()]


def _get_skill(skill_id: str, tenant_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(skills_table)
            .where(skills_table.c.skill_id == skill_id)
            .where(skills_table.c.tenant_id == tenant_id)
        ).mappings().first()
    return dict(row) if row else None


def delete_skill(skill_id: str, tenant_id: str, deleted_by: str) -> bool:
    """Loescht einen Skill (auch genehmigte). DSGVO-Loeschrecht."""
    with engine.begin() as conn:
        from sqlalchemy import delete as sa_delete
        result = conn.execute(
            sa_delete(skills_table)
            .where(skills_table.c.skill_id == skill_id)
            .where(skills_table.c.tenant_id == tenant_id)
        )
    deleted = result.rowcount > 0
    if deleted:
        _audit("skill.deleted", tenant_id, {"skill_id": skill_id, "deleted_by": deleted_by})
    return deleted


# ── Audit-Light ───────────────────────────────────────────────────────────────
def _audit(action: str, tenant_id: str, meta: dict[str, Any]) -> None:
    """Schreibt Audit-Eintrag ohne Inhalte — nur Entscheidung, IDs, Risiko."""
    try:
        write_audit_entry(action=action, metadata=meta, tenant_id=tenant_id)
    except Exception:
        pass
