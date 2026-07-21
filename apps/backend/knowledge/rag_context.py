"""
AILIZA Wissensdatenbank -- Block C Phase C4: Interne Wissensquellen im Chat
=============================================================================
Best-effort Kontextaufbau aus freigegebenen knowledge_chunks fuer den Chat.
Kein RAG-Redesign, keine Websuche, keine UI, keine Vektordatenbank-
Erweiterung, keine Embeddings, kein Wissensgraph, kein Ruecksfrage-Popup.
Nutzt ausschliesslich
search_knowledge_chunks() (keine Parallel-Logik auf den Tabellen) und die
bestehende Governance-Klassifikation (classify() + check_data_target()).

Karo-Entscheidungen (2026-07-21, siehe docs/AGENT_HANDOFF_BLOCK_C1_ABGESCHLOSSEN.md):
- Kein Treffer -> normale Antwort, kein Standardhinweis. Nur bei expliziter
  Dokumentenfrage OHNE Treffer: woertlicher Hinweistext.
- Kontext-Limit: max. 3 Snippets, max. 800 Zeichen insgesamt.
- Jedes Snippet wird vor dem LLM-Kontext erneut klassifiziert
  (target=EXTERNAL_LLM) -- zusaetzlich zur Ingestion-Pruefung (C2), die nur
  gegen FILE_STORAGE geklassifiziert hat. Nicht erlaubte Snippets fallen
  einfach aus dem Kontext, der Chat laeuft normal weiter.
- Kein Rueckfrage-Popup: das LLM bleibt der normale Antwortweg.
- Backend bleibt Quelle der Wahrheit fuer die Quellenliste -- sie wird NIE
  aus dem Modelltext abgeleitet, nur aus dem eigenen tag_map.

Best-effort ueber die gesamte Kette: build_knowledge_context() wirft NIE
eine Exception. Jeder Fehler (Suche, Klassifikation, o.ae.) fuehrt zu einem
neutralen Kontext (kein Kontext, answer_mode="general_ai") -- der normale
Chat wird dadurch nie blockiert oder schlechter.
"""
from __future__ import annotations

import logging
import re
from typing import Any

try:
    from .search import search_knowledge_chunks, NOT_FOUND_MESSAGE
    from ..governance.data_governance import classify, DataTarget
    from ..governance.data_matrix import check_data_target, PolicyDecision
except ImportError:  # pragma: no cover
    from knowledge.search import search_knowledge_chunks, NOT_FOUND_MESSAGE  # type: ignore
    from governance.data_governance import classify, DataTarget  # type: ignore
    from governance.data_matrix import check_data_target, PolicyDecision  # type: ignore

logger = logging.getLogger(__name__)

MAX_CONTEXT_SNIPPETS = 3
MAX_CONTEXT_CHARS_TOTAL = 800

_CONTEXT_BLOCK_HEADER = "[Interne freigegebene Wissensquellen]"
_CONTEXT_BLOCK_FOOTER = "[/Interne freigegebene Wissensquellen]"
_CONTEXT_BLOCK_INSTRUCTION = (
    "Anweisung: Nutze diese Quellen nur, wenn sie zur Frage passen. "
    "Erfinde keine Quellen. Wenn die Quellen nicht ausreichen, antworte "
    "allgemein und sage nicht, dass es eine interne Quelle gibt. "
    "Verwende Quellen-Tags nur aus diesem Kontext."
)

# Einfache, feste Erkennung expliziter Dokumentenfragen -- KEIN LLM, nur
# dafuer relevant, ob bei leerem Suchergebnis der Hinweistext gezeigt wird.
_EXPLICIT_DOCUMENT_QUESTION_PATTERN = re.compile(
    r"\b(dokument\w*|quelle\w*|wissensdatenbank\w*|gespeicherte[nrs]?\s+unterlage\w*"
    r"|interne[nrs]?\s+wissen\w*)\b",
    re.IGNORECASE,
)

_ANSWER_MODE_USER_TEXT = {
    "internal_knowledge": "Antwort basiert auf: internes Wissen.",
    "internal_plus_general": "Antwort basiert auf: internes Wissen + allgemeine KI.",
    "general_ai": None,
    "no_internal_source": "Keine interne Quelle gefunden, allgemeine Antwort.",
    "blocked_sensitive": "Diese Information darf nicht extern verarbeitet werden.",
}


def _neutral_context(**overrides: Any) -> dict[str, Any]:
    base = {
        "context_block": None,
        "tag_map": {},
        "used_snippets": [],
        "answer_mode": "general_ai",
        "confidence": "medium",
        "status_message": None,
        "found_count": 0,
        "filtered_count": 0,
    }
    base.update(overrides)
    return base


def _is_explicit_document_question(text: str) -> bool:
    return bool(_EXPLICIT_DOCUMENT_QUESTION_PATTERN.search(text or ""))


def _allowed_for_external_llm(snippet_text: str) -> bool:
    """True, wenn das Snippet fuer einen externen LLM-Call erlaubt ist.

    Re-Klassifikation gegen DataTarget.EXTERNAL_LLM -- unabhaengig von der
    Ingestion-Pruefung (C2), die nur gegen DataTarget.FILE_STORAGE lief.
    FILE_STORAGE und EXTERNAL_LLM sind unterschiedliche Ziele mit
    unterschiedlichen Policy-Entscheidungen (siehe data_matrix.py)."""
    classification = classify(snippet_text)
    decision = check_data_target(
        data_classes=classification.data_classes,
        target=DataTarget.EXTERNAL_LLM,
        redaction_applied=False,
        approval_given=False,
        provider_profile_active=False,
    )
    return decision in (PolicyDecision.ALLOW, PolicyDecision.ALLOW_WITH_NOTICE)


def _select_snippets_within_budget(
    hits: list[dict[str, Any]],
    max_snippets: int = MAX_CONTEXT_SNIPPETS,
    max_chars: int = MAX_CONTEXT_CHARS_TOTAL,
) -> list[dict[str, Any]]:
    """Waehlt Treffer (bereits nach Relevanz sortiert) innerhalb des harten
    Kontext-Budgets aus. Ueberspringt zu grosse Snippets, statt komplett
    abzubrechen -- ein spaeterer, kleinerer Treffer kann noch passen."""
    selected: list[dict[str, Any]] = []
    total_chars = 0
    for hit in hits:
        if len(selected) >= max_snippets:
            break
        snippet = hit.get("snippet") or ""
        if total_chars + len(snippet) > max_chars:
            continue
        selected.append(hit)
        total_chars += len(snippet)
    return selected


def _format_context_block(selected: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    lines = [_CONTEXT_BLOCK_HEADER]
    tag_map: dict[str, Any] = {}
    for index, hit in enumerate(selected, start=1):
        tag = f"[Quelle {index}]"
        lines.append(f"{tag} Titel: {hit['title']}")
        lines.append(f"Auszug: {hit['snippet']}")
        tag_map[tag] = {
            "source_id": hit["source_id"],
            "chunk_id": hit["chunk_id"],
            "title": hit["title"],
            "source_type": hit.get("source_type"),
            "visibility_scope": hit.get("visibility_scope"),
        }
    lines.append(_CONTEXT_BLOCK_FOOTER)
    lines.append(_CONTEXT_BLOCK_INSTRUCTION)
    return "\n".join(lines), tag_map


def build_knowledge_context(*, tenant_id: str, requester_user_id: str, query: str,
                           requester_roles: list[str] | None = None,
                           project_id: str | None = None) -> dict[str, Any]:
    """Best-effort Kontextaufbau fuer den Chat. Wirft NIE eine Exception --
    jeder Fehler fuehrt zu einem neutralen Kontext ohne Nutzer-Impact."""
    try:
        if not tenant_id or not requester_user_id or not query or not query.strip():
            return _neutral_context()

        explicit_question = _is_explicit_document_question(query)

        try:
            search_result = search_knowledge_chunks(
                tenant_id=tenant_id, requester_user_id=requester_user_id, query=query,
                requester_roles=requester_roles, project_id=project_id,
                limit=MAX_CONTEXT_SNIPPETS * 3,
            )
        except Exception:  # noqa: BLE001 - best effort, Suche darf Chat nie blockieren
            logger.exception("Wissenssuche fehlgeschlagen (best effort, kein Nutzer-Impact).")
            return _neutral_context()

        hits = search_result.get("results", [])
        found_count = len(hits)

        if found_count == 0:
            if explicit_question:
                return _neutral_context(
                    answer_mode="no_internal_source", confidence="low",
                    status_message=NOT_FOUND_MESSAGE,
                )
            return _neutral_context()

        allowed_hits: list[dict[str, Any]] = []
        filtered_count = 0
        for hit in hits:
            try:
                if _allowed_for_external_llm(hit["snippet"]):
                    allowed_hits.append(hit)
                else:
                    filtered_count += 1
            except Exception:  # noqa: BLE001 - fail-closed: bei Klassifikationsfehler nicht senden
                logger.exception("Snippet-Reklassifikation fehlgeschlagen (fail-closed, Snippet verworfen).")
                filtered_count += 1

        if not allowed_hits:
            if explicit_question:
                return _neutral_context(
                    answer_mode="no_internal_source", confidence="low",
                    status_message=NOT_FOUND_MESSAGE,
                    found_count=found_count, filtered_count=filtered_count,
                )
            return _neutral_context(
                answer_mode="blocked_sensitive",
                found_count=found_count, filtered_count=filtered_count,
            )

        selected = _select_snippets_within_budget(allowed_hits)
        if not selected:
            # Alles zu gross fuers Budget -- wie "nichts brauchbares" behandeln.
            return _neutral_context(found_count=found_count, filtered_count=filtered_count)

        context_block, tag_map = _format_context_block(selected)
        return {
            "context_block": context_block,
            "tag_map": tag_map,
            "used_snippets": selected,
            "answer_mode": "internal_knowledge",
            "confidence": "high",
            "status_message": None,
            "found_count": found_count,
            "filtered_count": filtered_count,
        }
    except Exception:  # noqa: BLE001 - Sicherheitsnetz, darf nie nach aussen dringen
        logger.exception("Aufbau des Wissens-Kontexts fehlgeschlagen (best effort, kein Nutzer-Impact).")
        return _neutral_context()


def sanitize_answer_citations(answer_text: str, tag_map: dict[str, Any]) -> str:
    """Entfernt Quellen-Tags aus der sichtbaren Modell-Antwort, die nicht im
    tag_map vorkommen -- verhindert erfundene/halluzinierte Quellenverweise
    im fuer den Nutzer sichtbaren Text."""
    if not answer_text:
        return answer_text

    def _replace(match: "re.Match[str]") -> str:
        tag = match.group(0)
        return tag if tag in tag_map else ""

    return re.sub(r"\[Quelle\s+\d+\]", _replace, answer_text)


def build_sources_list(tag_map: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Backend-eigene Quellenliste -- wird NIE aus Modelltext abgeleitet.
    Enthaelt ausschliesslich Quellen, die tatsaechlich im finalen
    LLM-Kontext waren (siehe build_knowledge_context -> tag_map)."""
    if not tag_map:
        return None
    return [
        {
            "tag": tag,
            "title": meta["title"],
            "source_id": meta["source_id"],
            "chunk_id": meta["chunk_id"],
        }
        for tag, meta in tag_map.items()
    ]


def answer_mode_user_text(answer_mode: str) -> str | None:
    return _ANSWER_MODE_USER_TEXT.get(answer_mode)
