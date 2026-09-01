# AILIZA v1.0 — lokal abgenommener Kandidat

EU-konformer autonomer KI-Agent für KMU.
Backend: FastAPI + SQLAlchemy (SQLite). Governance-Pipeline: Kill-Switch → Data Governance → Policy-Gateway → Redaction → Provider-Orchestrator.

---

## Aktueller Stand

AILIZA ist lokal im fail-closed Modus start- und testfaehig. Die lokale
technische Abnahme und der genaue Nachweis stehen in
`docs/AILIZA_ABLAUFPLAN_2026-08-20.md`. Eine Produktionsfreigabe ist damit
nicht verbunden.

Fuer neue Agenten-Arbeiten (Codex und Claude Code) gelten als kompakter
Einstieg:

- [`docs/AILIZA_HANDOFF_ENTWICKLUNG.md`](docs/AILIZA_HANDOFF_ENTWICKLUNG.md) — einziges Entwicklungs-Handoff
- [`docs/AILIZA_HANDOFF_ANWENDER.md`](docs/AILIZA_HANDOFF_ANWENDER.md) — kontrolliert lernendes Anwendergedaechtnis
- [`AGENTS.md`](AGENTS.md) — verbindliche Repository-Anweisungen fuer Codex
- [`CLAUDE.md`](CLAUDE.md) — verbindliche Repository-Anweisungen fuer Claude Code
- [`05_prompts/CODEX_TOKEN_KONTEXT_STATUS_PROMPT.md`](05_prompts/CODEX_TOKEN_KONTEXT_STATUS_PROMPT.md) — Modell-/Kontext-/Nutzungsregeln fuer Codex
- [`05_prompts/CLAUDE_TOKEN_KONTEXT_STATUS_PROMPT.md`](05_prompts/CLAUDE_TOKEN_KONTEXT_STATUS_PROMPT.md) — Modell-/Kontext-/Nutzungsregeln fuer Claude Code
- [`docs/LINKS.md`](docs/LINKS.md) — geprüfte Einstiege, Betrieb und historische Dokumente
- [`docs/SCHEMA_KONFLIKTBERICHT.md`](docs/SCHEMA_KONFLIKTBERICHT.md) — verbindlicher technischer Schema-Stand
- [`docs/PRODUKTIONSFREIGABE_CHECKLISTE.md`](docs/PRODUKTIONSFREIGABE_CHECKLISTE.md) — Phasen 5–6 mit Nachweisen und Owner-Feldern

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
- [x] Capability-Registry (`check_capability()`, 12 Capabilities, fail-closed)
- [x] Tool-Gateway (`guarded_tool_call()`)
- [x] Audit-Vault Stufe 1 (append-only, sanitized, paginiert)
- [x] Audit-Vault Stufe 2 (SHA-256 Hash-Chain, `verify_audit_chain()`)
- [x] Memory-Governance (Opt-in, CREDENTIALS/SPECIAL_CATEGORY/HR/LEGAL blockiert)
- [x] Fachlicher Memory-Kern (`user_memory`/`company_memory`, Scope-/Owner-/Tenant-Invarianten gehärtet, PR #64–#67)
- [x] Bestands-Audit für Memory-Invarianten (`audit_memory_scope_cli.py`, manueller GitHub-Actions-Workflow)
- [x] Dokument-Scan vor Upload
- [x] Startup Secret-Key-Check
- [x] Governance-Dokumentation (TOM-Katalog, Provider-DPA, AI-Act-Klassifikation, Incident-Response, Review-Plan)
- [x] Frontend: Datei-Upload, Deep Research, DiagBlock (nur `VITE_DEBUG_ERRORS=true`)
- [x] Alembic als verbindliche Schema-Autoritaet beim persistenten App-Start
- [x] Verschluesseltes SQLite-Backup mit Verify und geprueftem Restore
- [x] Reproduzierbarer Python-3.12-Stand (`requirements-lock-py312.txt`)

---

## Offene Bausteine

- [ ] Produktions-Bestandsprüfung der Memory-Invarianten ausführen (Workflow „Memory-Scope-Audit" manuell auslösen) — Voraussetzung, bevor die Anbindung des Memory-Kerns an den zentralen Permission-Evaluator (`apps/backend/permissions.py`) beginnt
- [ ] Memory-Governance UI (`GET /memory/facts`, `DELETE /memory/facts/{id}`)
- [x] Freigabe-UI (`GET /approvals`, serverseitig tenant-/owner-/zuweisungsgefiltert)
- [ ] Fehlende Audit-Events: `provider.blocked`, `capability.blocked`, `memory.stored` (`approval.approved`/`approval.rejected` existieren bereits in `routers/approvals.py`; ob der Name auf `approval.granted` vereinheitlicht wird, ist offen — siehe `docs/AILIZA_HANDOFF_ENTWICKLUNG.md`, Abschnitt 4)
- [x] CORS in der Render-Vorlage auf eine explizite HTTPS-Origin begrenzt; Live-Nachweis bleibt Produktions-Gate
- [ ] Externes Backupziel, Zeitplan, Alarmierung und verantwortliche Person festlegen
- [ ] Render-TLS/HTTP→HTTPS und HSTS am Live-System nachweisen (Konfiguration vorbereitet)

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
- Externe Provider fuer echte Kundendaten ohne aktuellen, organisationsbezogenen
  AVV/DPA- und Transfernachweis. Die technischen `ProviderProfile`-Werte sind
  nur eine Betreiber-Konfiguration und ersetzen keinen Vertragsnachweis.

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
├── intelligence/        — Modell-Empfehlung, routet nur freigegebene Modelle
├── audit/               — Audit-Vault (Stufe 1 + 2)
├── auth/                — JWT, RBAC
├── reflection/          — Memory & Reflection (Opt-in, Governance)
├── memory/              — technischer Prototyp, QUARANTÄNE (nicht der Memory-Kern)
├── documents/           — Dokument-Scan vor Upload
└── streaming/           — gepuffertes Streaming
apps/frontend/           — React/Vite Dashboard
policies/governance/     — TOM-Katalog, Provider-DPA, AI-Act, Incident, Review
docs/                    — v1.0-Blaupause und weitere Dokumente
```

Der fachliche **Memory-Kern** sind die Tabellen `memory_items`,
`memory_sources`, `memory_visibility` und `memory_suggestions` in
`apps/backend/db_schema.py` — **nicht** der Ordner `apps/backend/memory/`.

Governance-relevante Module im Detail:
[`docs/architecture/module_overview.md`](docs/architecture/module_overview.md)

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

```powershell
.\install.bat verified
.\start_ailiza.bat
.\.venv\Scripts\python.exe -m pytest tests apps/backend/tests -q
```

Vollstaendige lokale Betriebsanleitung: [`LOCAL_DEV.md`](LOCAL_DEV.md).
