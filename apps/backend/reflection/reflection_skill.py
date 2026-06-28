"""
AILIZA Memory & Reflection MVP
=============================
Speichert und liefert Fakten unter strenger Governance.

Rechtsgrundlage je Mandant und Use Case pruefen; Produkt-Opt-in ist nicht
automatisch eine DSGVO-Einwilligung.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

try:
    from ..governance.data_governance import DataClass, classify
    from ..database import (
        insert_reflection_fact,
        query_reflection_facts,
        delete_reflection_fact,
        delete_reflection_facts_for_tenant,
        DEFAULT_TENANT_ID,
    )
except ImportError:  # pragma: no cover
    from governance.data_governance import DataClass, classify
    from database import (
        insert_reflection_fact,
        query_reflection_facts,
        delete_reflection_fact,
        delete_reflection_facts_for_tenant,
        DEFAULT_TENANT_ID,
    )


# Datenklassen, die niemals gespeichert werden duerfen.
_BLOCKED_CLASSES = {
    DataClass.CREDENTIALS,
    DataClass.SPECIAL_CATEGORY,
    DataClass.HR,
    DataClass.LEGAL,
}


def store_fact(tenant_id: str, content: str, data_classes: list[DataClass] | None = None,
               purpose: str = "", opt_in: bool = False, user_id: str | None = None,
               ttl_days: int = 90, source: str | None = None) -> dict:
    """
    Speichert einen Fakt. Prueft zuerst classify(); blockiert
    CREDENTIALS/SPECIAL_CATEGORY/HR/LEGAL immer.
    """
    classification = classify(content)
    effective_classes = set(data_classes or []) | set(classification.data_classes)

    if effective_classes & _BLOCKED_CLASSES:
        return {
            "stored": False,
            "reason": "Datenklasse darf nicht gespeichert werden (CREDENTIALS/SPECIAL_CATEGORY/HR/LEGAL).",
            "blocked_classes": [c.value for c in (effective_classes & _BLOCKED_CLASSES)],
        }

    now = datetime.now(timezone.utc)
    fact_id = str(uuid.uuid4())
    insert_reflection_fact({
        "id": fact_id,
        "tenant_id": tenant_id or DEFAULT_TENANT_ID,
        "user_id": user_id,
        "data_classes": [c.value for c in effective_classes],
        "content": content,
        "quality_score": 1.0,
        "opt_in_confirmed": 1 if opt_in else 0,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=ttl_days)).isoformat(),
        "source": source,
        "purpose": purpose,
        "pii_cleared": 0 if DataClass.PERSONAL_DATA in effective_classes else 1,
    })
    return {"stored": True, "fact_id": fact_id}


def retrieve_facts(tenant_id: str, purpose: str, provider_profile_active: bool,
                   max_facts: int = 5, opt_in_confirmed: bool = False) -> list[dict]:
    """
    7-Bedingungen-Policy: Fakten werden nur zurueckgegeben, wenn ALLE erfuellt sind:
      1. tenant_id gesetzt
      2. purpose gesetzt
      3. ProviderProfile aktiv (falls extern genutzt)
      4. Fakt nicht abgelaufen
      5. Fakt enthaelt keine blockierte Datenklasse
      6. PII ist geklaert (pii_cleared) ODER Opt-in bestaetigt
      7. quality_score > 0
    """
    if not tenant_id or not purpose or not provider_profile_active:
        return []

    now = datetime.now(timezone.utc).isoformat()
    raw = query_reflection_facts(tenant_id=tenant_id, purpose=purpose, limit=max_facts * 3)

    results = []
    for fact in raw:
        classes = set(fact.get("data_classes") or [])
        if fact.get("expires_at", "") < now:  # Bedingung 4
            continue
        if classes & {c.value for c in _BLOCKED_CLASSES}:  # Bedingung 5
            continue
        if not (fact.get("pii_cleared") or fact.get("opt_in_confirmed") or opt_in_confirmed):  # Bedingung 6
            continue
        if (fact.get("quality_score") or 0) <= 0:  # Bedingung 7
            continue
        results.append(fact)
        if len(results) >= max_facts:
            break
    return results


def delete_fact(fact_id: str) -> int:
    return delete_reflection_fact(fact_id)


def delete_tenant_facts(tenant_id: str) -> int:
    return delete_reflection_facts_for_tenant(tenant_id)
