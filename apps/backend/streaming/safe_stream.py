"""
AILIZA sicheres Streaming
========================
Token-Streaming fuer einfache Faelle, Satz-/Absatzpufferung fuer sensible
Routen/Datenklassen, optionale Output-Guardrail.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator

try:
    from ..routing.router import Route
    from ..governance.data_governance import DataClass
except ImportError:  # pragma: no cover
    from routing.router import Route
    from governance.data_governance import DataClass


SENSITIVE_ROUTES = {Route.RISKY}
BUFFERED_CLASSES = {
    DataClass.HR,
    DataClass.LEGAL,
    DataClass.FINANCIAL,
    DataClass.SPECIAL_CATEGORY,
    DataClass.CREDENTIALS,
}

_SAFE_BLOCK_MESSAGE = "[Antwort aus Sicherheitsgruenden abgebrochen.]"
_SENTENCE_ENDINGS = (".", "!", "?", "\n")


def should_buffer(route: Route, data_classes: list[DataClass]) -> bool:
    if route in SENSITIVE_ROUTES:
        return True
    return any(dc in BUFFERED_CLASSES for dc in (data_classes or []))


def safe_stream(generator: Iterator[str], route: Route, data_classes: list[DataClass],
                output_guardrail: Callable[[str], bool] | None = None) -> Iterator[str]:
    buffer_mode = should_buffer(route, data_classes)

    if not buffer_mode:
        for token in generator:
            if output_guardrail is not None and not output_guardrail(token):
                yield _SAFE_BLOCK_MESSAGE
                return
            yield token
        return

    # Gepufferter Modus: nach Satz-/Absatzende pruefen und ausgeben
    buf = ""
    for token in generator:
        buf += token
        if any(buf.rstrip().endswith(end) for end in _SENTENCE_ENDINGS):
            if output_guardrail is not None and not output_guardrail(buf):
                yield _SAFE_BLOCK_MESSAGE
                return
            yield buf
            buf = ""
    if buf:
        if output_guardrail is not None and not output_guardrail(buf):
            yield _SAFE_BLOCK_MESSAGE
            return
        yield buf
