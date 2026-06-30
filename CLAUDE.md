# AILIZA — Projektkontext fuer Claude Code

AILIZA ist ein EU-konformer (DSGVO + EU AI Act) autonomer KI-Agent fuer KMU.
Backend: FastAPI + SQLAlchemy (SQLite). Jeder externe LLM-Call laeuft durch eine
mehrstufige Governance-Pipeline.

## Startbefehle
```bash
cd apps/backend && uvicorn main:app --port 8001
```

## Testbefehle
```bash
pytest tests/                 # neue konsolidierte Tests
pytest apps/backend/tests/    # Bestands-Tests
```

## Arbeitsregeln (IMMER einhalten)
- Vor jeder Aenderung: erst erklaeren WAS geaendert wird und WARUM — dann auf Bestaetigung warten.
- Nie sofort committen oder pushen. Erst fragen, Aenderung zeigen, dann ausfuehren.
- Keine Aktion ohne Rueckmeldung der Nutzerin.

## Sicherheitsregeln (NIEMALS verletzen)
- Keine echten API-Keys in Code oder Logs.
- Keine PII, Secrets oder vollstaendigen Prompts in Logs.
- Externe LLM-Calls NIE direkt aus `main.py` — immer ueber den Provider-Orchestrator.
- Jeder externe Call durchlaeuft: Kill-Switch -> Data Governance -> Policy-Gateway
  -> Redaction -> Provider-Orchestrator.
- Fail-closed: bei Unklarheit nicht extern senden.
- Verstaendliche deutsche Fehlermeldungen, kein Stack-Trace zum Client.

## Architekturuebersicht
- `apps/backend/main.py` — HTTP/API-Orchestrierung, Fast-Path, Exception-Handler.
- `apps/backend/kill_switch.py` — globaler Notausschalter (`AILIZA_EXTERNAL_LLM_ENABLED`).
- `apps/backend/governance/` — Datenklassifikation, Datenziel-Matrix, Redaction.
- `apps/backend/policy.py` — `evaluate_policy(PolicyContext)` + Legacy `check_tool_call`.
- `apps/backend/providers/` — `LLMProvider`-Interface, Groq/Anthropic-Adapter, Orchestrator.
- `apps/backend/routing/router.py` — Token-Budget und Routing (SIMPLE..RISKY).
- `apps/backend/audit/` — getrennte Security-/Performance-/Cost-Logs (ohne Inhalt).
- `apps/backend/reflection/` — Memory & Reflection (strenge Governance, Opt-in).
- `apps/backend/documents/` — Dokumenten-Scan vor Upload.
- `apps/backend/streaming/safe_stream.py` — gepuffertes Streaming fuer sensible Routen.
- `apps/backend/database.py` — alle Tabellen, tenant_id-gefiltert, Retention-Felder.

## Pipeline-Reihenfolge fuer externe Calls
1. Kill-Switch (`enforce_kill_switch`)
2. Data Governance (`classify`)
3. Policy-Gateway (`evaluate_policy`)
4. Redaction (`redact`)
5. Provider-Orchestrator (`ProviderOrchestrator.generate`)

## Mandanten
`DEFAULT_TENANT_ID = AILIZA_DEFAULT_TENANT_ID` (Default `default`). Alle Logs/Runs/Facts
sind tenant-gefiltert.
