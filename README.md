# AILIZA v1.0 Beta Ready

EU-konformer autonomer KI-Agent für KMU.
Backend: FastAPI + SQLAlchemy (SQLite). Governance-Pipeline: Kill-Switch → Data Governance → Policy-Gateway → Redaction → Provider-Orchestrator.

---

## Aktueller Stand

AILIZA befindet sich in der v1.0 Beta-Ready-Phase.
Alle abgeschlossenen Artefakte sind in diesem Repository versioniert.

---

## Eingefrorene Basis

| Datei | Inhalt |
|---|---|
| `00_masterplan/AILIZA_v1_Beta_Ready_Masterplan.md` | Vollständige v1.0-Blaupause (10 Artefakte) |
| `01_addendum/AILIZA_v1_Beta_Ready_Addendum_01.md` | Korrekturen und Ergänzungen zur Basis |

---

## Aktueller Arbeits-Prompt

`02_workphases/AILIZA_v1_Beta_Ready_Workphase_01_v1.2.md`

---

## Fertige Bausteine

- [x] RBAC: USER / AUDIT_VIEWER / MANAGER / ADMIN / DSB
- [x] JWT Auth (Bearer + HttpOnly Cookie)
- [x] Kill-Switch (`AILIZA_EXTERNAL_LLM_ENABLED`)
- [x] Governance-Pipeline (Klassifikation → Policy → Redaction → Orchestrator)
- [x] Provider-Profil-System (`ProviderProfile`, `avv_signed`, `transfer_basis`)
- [x] Capability-Registry (`check_capability()`, 11 Capabilities, fail-closed)
- [x] Tool-Gateway (`guarded_tool_call()`)
- [x] Audit-Vault Stufe 1 (append-only, sanitized, paginiert)
- [x] Audit-Vault Stufe 2 (SHA-256 Hash-Chain, `verify_audit_chain()`)
- [x] Memory-Governance (Opt-in, CREDENTIALS/SPECIAL_CATEGORY/HR/LEGAL blockiert)
- [x] Dokument-Scan vor Upload
- [x] Startup Secret-Key-Check
- [x] Governance-Dokumentation (TOM-Katalog, Provider-DPA, AI-Act-Klassifikation, Incident-Response, Review-Plan)
- [x] Frontend: Datei-Upload, Deep Research, DiagBlock (nur `VITE_DEBUG_ERRORS=true`)

---

## Offene Bausteine

- [ ] Memory-Governance UI (`GET /memory/facts`, `DELETE /memory/facts/{id}`)
- [ ] Freigabe-UI (`GET /admin/approvals` Frontend-Seite)
- [ ] Fehlende Audit-Events (`provider.blocked`, `capability.blocked`, `memory.stored`, `memory.deleted`, `approval.granted`, `approval.rejected`)
- [ ] CORS Wildcard → explizite Origins (vor Produktion)
- [ ] Backup-Strategie (SQLite Cron-Backup)
- [ ] TLS-Terminierung (vor Produktion)

---

## Dauerhafte Sperren

Die folgenden Module und Aktionen sind **permanent gesperrt** bis zur expliziten Freigabe durch Admin mit Dokumentation:

- Autonome HR-Entscheidungen
- Autonome Buchhaltungsentscheidungen
- Automatische Vertragsfreigaben
- Gesundheitsdaten
- Tools ohne AVV/DPA
- Tools mit Training auf Kundendaten
- Tools ohne Löschkonzept
- Unkontrollierte Websuche
- Alle Provider (Groq, Anthropic, Tavily) — je kein AVV unterzeichnet

---

## Repo-Struktur (Dokumentation)

```
00_masterplan/   — eingefrorene Basisdokumente
01_addendum/     — Korrekturen und Ergänzungen
02_workphases/   — versionierte Arbeits-Prompts (v1.0, v1.1, v1.2 …)
03_specs/        — Einzelspezifikationen pro Baustein
04_schemas/      — JSON-Schemas für Datenmodelle
05_prompts/      — aktuelle und nächste Agenten-Prompts
06_release/      — Beta-Ready-Checkliste und Release Notes
archive/         — ältere Versionen
```

---

## Code-Struktur

```
apps/backend/
├── main.py              — HTTP/API-Orchestrierung
├── kill_switch.py       — globaler Notausschalter
├── database.py          — alle Tabellen, tenant-gefiltert
├── policy.py            — evaluate_policy(PolicyContext)
├── governance/          — Klassifikation, Datenziel-Matrix, Redaction
├── providers/           — LLMProvider-Interface, Groq/Anthropic, Orchestrator
├── routing/             — Token-Budget, Routing (SIMPLE..RISKY)
├── audit/               — Audit-Vault (Stufe 1 + 2)
├── auth/                — JWT, RBAC
├── reflection/          — Memory & Reflection (Opt-in, Governance)
├── documents/           — Dokument-Scan vor Upload
└── streaming/           — gepuffertes Streaming
apps/frontend/           — React/Vite Dashboard
policies/governance/     — TOM-Katalog, Provider-DPA, AI-Act, Incident, Review
docs/                    — v1.0-Blaupause und weitere Dokumente
```

---

## Arbeitsregel

```
Chat    = Arbeitsraum
GitHub  = freigegebener Stand

Alles, was fertig ist, kommt nach GitHub.
Alles, was noch diskutiert wird, bleibt im Chat.
Alles, was umgesetzt werden soll, bekommt eine eigene Datei.
```

---

## Startbefehle

```bash
cd apps/backend && uvicorn main:app --port 8001
python3 -m pytest tests/ apps/backend/tests/ -q
```
