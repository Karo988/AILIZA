"""Sichtbarkeit von Wissensquellen -- Eigentuemer, Scope und Fachbereich.

Diese Schicht beantwortet genau eine Frage: WELCHE Wissensquellen darf
diese Person sehen? Sie ist bewusst von der Ablage (ingestion/search) und
von der Governance-Pipeline getrennt.

Zwei Regeln, die nie vermischt werden duerfen:

1. Die bisherigen Regeln (Eigentuemer, visibility_scope) bleiben
   unveraendert gueltig.
2. Ist eine Quelle einem Fachbereich zugeordnet, kommt die Bereichspruefung
   ZUSAETZLICH hinzu. Sie kann Zugriff nur entziehen, nie gewaehren.

Daraus folgt: eine bereichsgebundene Quelle, die einem anderen gehoert,
wird NICHT dadurch sichtbar, dass jemand im Bereich Leserechte hat. Und
eine eigene Quelle wird unsichtbar, sobald sie einem Bereich zugeordnet
ist, in dem man kein Leserecht hat -- das ist gewollt: die Zuordnung ist
eine bewusste Einstufung des Inhalts, nicht des Eigentuemers.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select

try:
    from .database import engine
    from .db_schema import knowledge_sources
    from .domains import evaluate_domain_permission
except ImportError:  # pragma: no cover - Fallback fuer flachen Import
    from database import engine  # type: ignore
    from db_schema import knowledge_sources  # type: ignore
    from domains import evaluate_domain_permission  # type: ignore

# Scopes, die ueber den Eigentuemer hinaus im Mandanten sichtbar sind.
# Bewusst als feste Liste: ein unbekannter Scope gilt als NICHT geteilt
# (fail-closed), statt versehentlich als "irgendwie oeffentlich".
_SHARED_SCOPES = ("company", "tenant", "shared")


def may_read_source(
    *, tenant_id: str, user_id: str, source: dict[str, Any],
) -> bool:
    """Darf user_id diese eine Quelle lesen?

    Reihenfolge ist bedeutsam: erst die Grundsichtbarkeit (Eigentuemer oder
    geteilter Scope), dann die Bereichseinschraenkung. Ein Vertauschen
    wuerde aus der Einschraenkung eine Freigabe machen."""
    if source.get("tenant_id") != tenant_id:
        return False

    owner = source.get("uploaded_by")
    scope = str(source.get("visibility_scope") or "private").strip().lower()
    base_visible = (owner == user_id) or (scope in _SHARED_SCOPES)
    if not base_visible:
        return False

    domain_code = source.get("domain_code")
    if not domain_code:
        return True

    return evaluate_domain_permission(
        tenant_id=tenant_id, user_id=user_id,
        domain_code=domain_code, action="content.read",
    ).allowed


def list_readable_sources(
    *, tenant_id: str, user_id: str, limit: int = 100,
) -> list[dict[str, Any]]:
    """Alle fuer user_id lesbaren Wissensquellen des Mandanten.

    Die Grundsichtbarkeit wird in SQL gefiltert (Tenant, Eigentuemer/Scope)
    -- fremde Datensaetze werden gar nicht erst geladen. Die
    Bereichspruefung erfolgt danach in Python, weil sie pro Bereich eine
    eigene Entscheidung ist; sie kann die Menge nur verkleinern."""
    query = (
        select(knowledge_sources)
        .where(knowledge_sources.c.tenant_id == tenant_id)
        .where(or_(
            knowledge_sources.c.uploaded_by == user_id,
            knowledge_sources.c.visibility_scope.in_(_SHARED_SCOPES),
        ))
        .order_by(knowledge_sources.c.created_at.desc())
        .limit(limit)
    )
    with engine.begin() as connection:
        rows = [dict(r) for r in connection.execute(query).mappings().all()]

    return [
        r for r in rows
        if may_read_source(tenant_id=tenant_id, user_id=user_id, source=r)
    ]


def serialize_source(source: dict[str, Any]) -> dict[str, Any]:
    """Nach aussen nur Metadaten -- niemals Speicherpfad, Inhaltshash oder
    Rohinhalt. Ein Speicherpfad waere ein Hinweis auf die Ablagestruktur,
    ein Inhaltshash erlaubt den Abgleich, ob ein bekanntes Dokument
    vorliegt."""
    return {
        "id": source.get("id"),
        "title": source.get("title"),
        "source_type": source.get("source_type"),
        "status": source.get("status"),
        "visibility_scope": source.get("visibility_scope"),
        "domain_code": source.get("domain_code"),
        "uploaded_by": source.get("uploaded_by"),
        "created_at": source.get("created_at"),
    }


def get_knowledge_source_for_tenant(source_id: int, tenant_id: str) -> dict[str, Any] | None:
    """Laedt eine Quelle NUR innerhalb des eigenen Mandanten.

    Der Tenant-Filter steht in der Abfrage, nicht in einer Pruefung danach:
    ein fremder Datensatz wird gar nicht erst geladen."""
    query = (
        select(knowledge_sources)
        .where(knowledge_sources.c.id == source_id)
        .where(knowledge_sources.c.tenant_id == tenant_id)
    )
    with engine.begin() as connection:
        row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def set_knowledge_source_domain(
    *, source_id: int, tenant_id: str, domain_code: str | None,
) -> None:
    """Setzt oder loest die Bereichsbindung. Der Tenant-Filter ist Teil des
    UPDATE-Statements -- eine fremde Quelle wird nicht getroffen, auch
    wenn die ID erraten wurde."""
    with engine.begin() as connection:
        connection.execute(
            knowledge_sources.update()
            .where(knowledge_sources.c.id == source_id)
            .where(knowledge_sources.c.tenant_id == tenant_id)
            .values(domain_code=domain_code)
        )
