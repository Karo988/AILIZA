# ADR: Provider-Orchestrator statt Direktcall

## Status
Angenommen (2026-06-19).

## Kontext
Der Prototyp rief Groq direkt aus `main.py` (`/agent/run`) via `urllib.request`.
Das umging Kill-Switch, Data Governance, Policy-Gateway und Redaction und machte
Compliance (DSGVO / EU AI Act) nicht durchsetzbar.

## Entscheidung
Alle externen LLM-Calls laufen ausschliesslich ueber `ProviderOrchestrator`.
`main.py` enthaelt keinen direkten Provider-Code mehr (per Test `test_no_direct_groq`
abgesichert). Der Orchestrator erzwingt der Reihe nach:
Kill-Switch -> ProviderProfile-Pruefung -> Provider-Auswahl -> `generate()` ->
Performance-/Cost-Logging.

## Konsequenzen
- Positiv: Einheitlicher, fail-closed Pfad; Provider austauschbar (Groq/Anthropic);
  zentrale Stelle fuer Kill-Switch, Logging und Kostenkontrolle.
- Positiv: Fehlende API-Keys fuehren zu verstaendlicher deutscher Meldung statt Crash.
- Negativ: Zusaetzliche Abstraktionsschicht; Streaming im MVP teils gechunkt.

## Alternativen
- Direktcall (verworfen: nicht compliant, nicht testbar).
- Nur Gateway ohne Orchestrator (verworfen: keine Provider-Abstraktion, kein zentrales Cost-Logging).
