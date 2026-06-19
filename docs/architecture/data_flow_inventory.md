# Datenflussinventar (AILIZA)

Welche Daten fliessen wohin, warum, und mit welcher Aufbewahrung (Retention).

## Eingehende Daten
| Quelle | Datenart | Erste Station |
|--------|----------|---------------|
| HTTP `/agent/run` | Freitext-Aufgabe | RAM, Klassifikation |
| HTTP `/documents/scan` | Datei (Whitelist) | RAM, Scan, keine Persistenz im MVP |
| HTTP `/feedback` | Rating + optionaler Grund | `feedback`-Tabelle |

## Verarbeitungspipeline (externe Calls)
1. **Kill-Switch** (`kill_switch.py`) — kein Inhalt, nur Status-Metadaten.
2. **Data Governance** (`governance/data_governance.py`) — Klassifikation im RAM, kein LLM.
3. **Policy-Gateway** (`policy.evaluate_policy`) — Entscheidung anhand Datenziel-Matrix.
4. **Redaction** (`governance/redaction.py`) — Secrets entfernt, PII -> Platzhalter; Mapping nur fluechtig im RAM.
5. **Provider-Orchestrator** (`providers/orchestrator.py`) — einziger externer Call-Pfad.

## Ziele (DataTarget) und Regeln
- `EXTERNAL_LLM`: PERSONAL_DATA nur nach Redaction/Approval + aktivem ProviderProfile; CREDENTIALS/SPECIAL_CATEGORY blockiert.
- `MEMORY`/`VECTOR_DB`: SPECIAL_CATEGORY blockiert; PERSONAL_DATA approval-pflichtig.
- `AUDIT`: nur Metadaten, niemals Inhalte/Prompts/Secrets.

## Persistenz und Retention
| Tabelle | Inhalt | Retention (`expires_at`) |
|---------|--------|--------------------------|
| `audit_logs` | Aktionsmetadaten | — (gem. DSGVO Art. 30) |
| `security_logs` | incident_type, severity | 365 Tage |
| `performance_logs` | latency, route, provider, error_type | 90 Tage |
| `cost_logs` | tokens, provider, model, cost_estimate | 365 Tage |
| `reflection_facts` | freigegebene Fakten (Opt-in) | 90 Tage (TTL) |
| `agent_runs` | Aufgabe + Ergebnis | projektabhaengig |

## Grundsatz
Keine Prompts, keine Antworten, keine Secrets in irgendeinem Log. Alle Queries
sind `tenant_id`-gefiltert.
