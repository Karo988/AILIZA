"""
AILIZA Wissensdatenbank -- Block D0: Demo-/Nachschlagewerk-Ansicht
=====================================================================
Reine Anzeigelogik fuer die kleine Firmendatenbank-/Wissensdatenbank-Demo.
Keine Datenbankschreibzugriffe hier, keine neue Architektur -- nur wie
bestehende knowledge_sources-Zeilen (siehe apps/backend/database.py)
nutzerfreundlich dargestellt werden: Status -> Nutzbarkeits-Label,
Sortierung, und eine "oeffentliche" Sicht ohne interne/technische Felder
(storage_path, chunk_text, o.ae. werden NIE nach aussen gegeben).

Backend bleibt Quelle der Wahrheit: diese Funktionen lesen nur, was schon
in knowledge_sources steht -- kein Erfinden von Status oder Berechtigungen.
"""
from __future__ import annotations

from typing import Any

_USABILITY_LABELS = {
    "approved": "Nutzbar im Chat",
    "pending_review": "Wartet auf Prüfung",
    "blocked": "Blockiert",
    "deleted": "Nicht aktiv",
    "expired": "Nicht aktiv",
    "uploaded": "Wird noch geprüft",
}

_STATUS_EXPLANATIONS = {
    "approved": "Diese Quelle kann AILIZA für Antworten verwenden.",
    "pending_review": "Diese Quelle ist sichtbar, aber noch nicht im Chat nutzbar.",
    "blocked": "Diese Quelle wurde blockiert und wird nicht verwendet.",
    "deleted": "Diese Quelle ist nicht mehr aktiv.",
    "expired": "Diese Quelle ist abgelaufen und nicht mehr aktiv.",
    "uploaded": "Dieses Dokument wird noch geprüft, bevor es genutzt werden kann.",
}

# Sortier-Rang: approved zuerst, dann pending_review/uploaded (wartend),
# dann blocked/deleted/expired zuletzt.
_STATUS_SORT_RANK = {
    "approved": 0,
    "pending_review": 1,
    "uploaded": 1,
    "blocked": 2,
    "deleted": 2,
    "expired": 2,
}

# Genau die Felder, die die Demo-/Nachschlagewerk-Ansicht nach aussen gibt --
# NIE storage_path, chunk_text oder andere interne/technische Felder.
PUBLIC_SOURCE_FIELDS = {
    "source_id", "title", "original_filename", "category", "source_type",
    "status", "usability_label", "usable_in_chat", "status_explanation",
    "visibility_scope", "chunk_count", "created_at", "updated_at",
}


def usability_label_for_status(status: str) -> str:
    return _USABILITY_LABELS.get(status, "Nicht aktiv")


def status_explanation(status: str) -> str:
    return _STATUS_EXPLANATIONS.get(
        status, "Diese Quelle ist aktuell nicht im Chat nutzbar."
    )


def is_usable_in_chat(status: str) -> bool:
    return status == "approved"


def sort_sources_for_demo(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """approved zuerst, dann wartend (pending_review/uploaded), dann
    blocked/deleted/expired zuletzt -- innerhalb jeder Gruppe neueste zuerst.

    Zwei Sortierschritte: zuerst nach Datum absteigend (neueste zuerst),
    dann stabil nach Status-Rang gruppieren -- Python-sort ist stabil,
    daher bleibt die Datums-Reihenfolge innerhalb jeder Gruppe erhalten."""
    by_date = sorted(sources, key=lambda s: str(s.get("created_at") or ""), reverse=True)
    return sorted(by_date, key=lambda s: _STATUS_SORT_RANK.get(s.get("status"), 3))


def to_public_source_view(source: dict[str, Any]) -> dict[str, Any]:
    """Baut die oeffentliche Demo-Ansicht einer Wissensquelle -- enthaelt
    NIE storage_path, chunk_text oder andere interne Felder."""
    status = source.get("status", "")
    return {
        "source_id": source.get("id"),
        "title": source.get("title"),
        "original_filename": source.get("original_filename"),
        "category": source.get("category"),
        "source_type": source.get("source_type"),
        "status": status,
        "usability_label": usability_label_for_status(status),
        "usable_in_chat": is_usable_in_chat(status),
        "status_explanation": status_explanation(status),
        "visibility_scope": source.get("visibility_scope"),
        "chunk_count": source.get("chunk_count", 0),
        "created_at": source.get("created_at"),
        "updated_at": source.get("updated_at"),
    }
