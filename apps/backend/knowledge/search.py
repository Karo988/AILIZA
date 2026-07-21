"""
AILIZA Wissensdatenbank -- Block C Phase C3: Lokale Suche
==========================================================
Einfache, autarke Keyword-Suche ueber freigegebene knowledge_chunks.
Kein RAG, keine Antwortgenerierung, keine Vektordatenbank-Erweiterung,
keine Embeddings, kein Wissensgraph, keine externen Dienste -- reine
lokale Substring-Relevanz auf bereits gespeicherten Chunks (SQLite-kompatibel).

Nur Quellen mit status="approved" werden durchsucht. blocked/deleted/
pending_review/expired werden nie zurueckgegeben. tenant_id ist eine
harte Grenze (kein Treffer ueber Mandantengrenzen hinweg). Sichtbarkeit
wird ueber knowledge_source_permissions geprueft -- ohne Berechtigungs-
eintrag gilt fail-closed: nur die hochladende Person sieht die Quelle.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

try:
    from ..database import engine, knowledge_sources, knowledge_chunks, knowledge_source_permissions
except ImportError:  # pragma: no cover
    from database import engine, knowledge_sources, knowledge_chunks, knowledge_source_permissions  # type: ignore


class KnowledgeSearchError(ValueError):
    """Nutzerseitig verstaendlicher Suchfehler (fehlende Pflichtangaben)."""


NOT_FOUND_MESSAGE = "Ich habe in freigegebenen Quellen nichts Passendes gefunden."

_DEFAULT_LIMIT = 10
_SNIPPET_WINDOW = 160


def _split_terms(query: str) -> list[str]:
    return [t.lower() for t in query.split() if t.strip()]


def _score_chunk(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(lowered.count(term) for term in terms)


def _make_snippet(text: str, terms: list[str], window: int = _SNIPPET_WINDOW) -> str:
    lowered = text.lower()
    pos = -1
    for term in terms:
        idx = lowered.find(term)
        if idx != -1:
            pos = idx
            break
    if pos == -1:
        pos = 0
    start = max(0, pos - window // 2)
    end = min(len(text), start + window)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def _is_source_visible(source: dict[str, Any], permission: dict[str, Any] | None, *,
                       requester_user_id: str, requester_roles: list[str],
                       project_id: str | None) -> bool:
    if permission is None:
        # Kein Berechtigungseintrag -- fail-closed: nur die hochladende Person sieht es.
        return requester_user_id == source["uploaded_by"]

    scope = permission["visibility_scope"]
    if scope == "private":
        return requester_user_id in (source["uploaded_by"], permission.get("created_by"))
    if scope == "project":
        return project_id is not None and project_id == permission.get("project_id")
    if scope in ("team", "organization"):
        # Mandantengrenze ist bereits vor dem Aufruf dieser Funktion durchgesetzt.
        return True
    if scope == "external_limited":
        allowed_users = permission.get("allowed_user_ids") or []
        allowed_roles = permission.get("allowed_roles") or []
        if requester_user_id in allowed_users:
            return True
        return any(role in allowed_roles for role in requester_roles)
    # Unbekannter Scope -> fail-closed blockieren.
    return False


def search_knowledge_chunks(*, tenant_id: str, requester_user_id: str, query: str,
                            requester_roles: list[str] | None = None,
                            project_id: str | None = None,
                            limit: int = _DEFAULT_LIMIT) -> dict[str, Any]:
    """Lokale Keyword-Suche ueber freigegebene knowledge_chunks.

    Gibt {"results": [...], "message": str|None} zurueck. "message" ist nur
    gesetzt, wenn nichts gefunden wurde (freundlicher Hinweistext ohne
    technische Details).
    """
    if not tenant_id:
        raise KnowledgeSearchError("Tenant fehlt.")
    if not requester_user_id:
        raise KnowledgeSearchError("Anfragende Person fehlt.")

    terms = _split_terms(query)
    if not terms:
        raise KnowledgeSearchError("Suchanfrage darf nicht leer sein.")

    roles = requester_roles or []
    results: list[dict[str, Any]] = []

    with engine.begin() as conn:
        sources = conn.execute(
            select(knowledge_sources)
            .where(knowledge_sources.c.tenant_id == tenant_id)
            .where(knowledge_sources.c.status == "approved")
        ).mappings().all()

        for source in sources:
            permission_row = conn.execute(
                select(knowledge_source_permissions)
                .where(knowledge_source_permissions.c.source_id == source["id"])
            ).mappings().first()
            permission = dict(permission_row) if permission_row else None

            if not _is_source_visible(
                dict(source), permission, requester_user_id=requester_user_id,
                requester_roles=roles, project_id=project_id,
            ):
                continue

            chunk_rows = conn.execute(
                select(knowledge_chunks)
                .where(knowledge_chunks.c.source_id == source["id"])
                .where(knowledge_chunks.c.status == "active")
                .order_by(knowledge_chunks.c.chunk_index)
            ).mappings().all()

            for chunk in chunk_rows:
                score = _score_chunk(chunk["chunk_text"], terms)
                if score <= 0:
                    continue
                results.append({
                    "source_id": source["id"],
                    "chunk_id": chunk["id"],
                    "title": source["title"],
                    "snippet": _make_snippet(chunk["chunk_text"], terms),
                    "score": score,
                    "source_type": source["source_type"],
                    "visibility_scope": (permission or {}).get(
                        "visibility_scope", source["visibility_scope"]),
                    "status": source["status"],
                })

    results.sort(key=lambda r: (-r["score"], r["source_id"], r["chunk_id"]))
    results = results[:limit]

    return {
        "results": results,
        "message": None if results else NOT_FOUND_MESSAGE,
    }
