"""Fachliche vier Memory-Scopes auf die zwei bestehenden Speicher abbilden."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryScopeRoute:
    scope: str
    store: str
    owner_required: bool
    project_required: bool
    visible_to_tenant: bool


_ROUTES = {
    "session": MemoryScopeRoute("session", "user_memory", True, False, False),
    "personal": MemoryScopeRoute("personal", "user_memory", True, False, False),
    "project": MemoryScopeRoute("project", "company_memory", False, True, False),
    "company": MemoryScopeRoute("company", "company_memory", False, False, True),
}


def route_memory_scope(scope: str, *, owner_user_id: str | None = None,
                       project_id: str | None = None) -> MemoryScopeRoute:
    try:
        route = _ROUTES[scope]
    except KeyError as exc:
        raise ValueError("Unbekannter Memory-Scope; Speicherung wird verweigert.") from exc
    if route.owner_required and not owner_user_id:
        raise ValueError("Dieser Memory-Scope benötigt eine Nutzerzuordnung.")
    if route.project_required and not project_id:
        raise ValueError("Der Projekt-Scope benötigt eine Projektzuordnung.")
    return route
