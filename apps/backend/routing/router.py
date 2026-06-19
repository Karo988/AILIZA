"""
AILIZA Routing & Token-Budget
=============================
Entscheidet, welche Verarbeitungsroute eine Anfrage nimmt und welches
Token-Budget gilt. Fail-safe: Bei Budget-Ueberschreitung Downgrade oder Abbruch.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

try:
    from ..governance.data_governance import DataClass
except ImportError:  # pragma: no cover
    from governance.data_governance import DataClass


class Route(str, Enum):
    SIMPLE = "simple"      # lokal, < 200ms
    STANDARD = "standard"  # kleines Modell, < 3s
    COMPLEX = "complex"    # grosses Modell, < 10s
    DOCUMENT = "document"  # async, chunking
    RISKY = "risky"        # approval + output-check


# Hard-Limits je Route (input/output)
ROUTE_LIMITS: dict[Route, tuple[int, int]] = {
    Route.SIMPLE: (200, 200),
    Route.STANDARD: (4000, 1000),
    Route.COMPLEX: (16000, 4000),
    Route.DOCUMENT: (100000, 8000),
    Route.RISKY: (8000, 2000),
}

MODEL_HINTS: dict[Route, str] = {
    Route.SIMPLE: "local",
    Route.STANDARD: "small",
    Route.COMPLEX: "large",
    Route.DOCUMENT: "large",
    Route.RISKY: "large",
}

_SENSITIVE_CLASSES = {
    DataClass.CREDENTIALS,
    DataClass.SPECIAL_CATEGORY,
    DataClass.HR,
    DataClass.LEGAL,
    DataClass.FINANCIAL,
    DataClass.SECURITY_SENSITIVE,
}


@dataclass
class RoutingDecision:
    route: Route
    model_hint: str
    max_input_tokens: int
    max_output_tokens: int
    reason: str


def estimate_tokens(text: str) -> int:
    """Einfache Schaetzung: Woerter * 1.3."""
    if not text:
        return 0
    return int(len(text.split()) * 1.3)


def route_request(
    task: str,
    data_classes: list[DataClass] | None = None,
    token_estimate: int | None = None,
    is_document: bool = False,
) -> RoutingDecision:
    data_classes = data_classes or [DataClass.PUBLIC]
    if token_estimate is None:
        token_estimate = estimate_tokens(task)

    if is_document:
        route, reason = Route.DOCUMENT, "Dateiupload erkannt"
    elif DataClass.CREDENTIALS in data_classes or DataClass.SPECIAL_CATEGORY in data_classes:
        route, reason = Route.RISKY, "Sensible Datenklasse (CREDENTIALS/SPECIAL_CATEGORY)"
    elif not task or not task.strip():
        route, reason = Route.SIMPLE, "Leere Eingabe"
    elif token_estimate > 4000 or sum(1 for dc in data_classes if dc in _SENSITIVE_CLASSES) >= 2:
        route, reason = Route.COMPLEX, "Hohe Token-Zahl oder mehrere sensitive Klassen"
    elif token_estimate <= 8:
        route, reason = Route.SIMPLE, "Sehr kurze Anfrage (Fast-Path-Kandidat)"
    else:
        route, reason = Route.STANDARD, "Standard-Anfrage"

    max_in, max_out = ROUTE_LIMITS[route]

    # Budget-Pruefung: Downgrade-Logik bei Ueberschreitung
    if token_estimate > max_in and route in {Route.STANDARD}:
        route = Route.COMPLEX
        max_in, max_out = ROUTE_LIMITS[route]
        reason += " | hochgestuft wegen Token-Budget"

    return RoutingDecision(
        route=route,
        model_hint=MODEL_HINTS[route],
        max_input_tokens=max_in,
        max_output_tokens=max_out,
        reason=reason,
    )
