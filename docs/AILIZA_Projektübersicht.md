# AILIZA — Projektübersicht

**Stand:** 08.06.2026  
**Version:** 0.1.0, zusammengeführt mit aktuellem KI-Liza-Stand  
**Repository:** github.com/M-Imica/Ailiza

---

## Ziel

AILIZA ist ein EU-konformer AI Agent für kontrollierte Autonomie. Das Projekt
verbindet Agent Core, Tool-Calling, Policy Enforcement, Human Oversight,
Audit Logging, DSGVO-Konformität und EU AI Act Compliance.

Der Ordner `C:\Ailiza` enthält jetzt zusätzlich den aktuellen KI-Liza-Stand aus
`C:\ki-liza`, ohne bestehende AILIZA-Dateien zu überschreiben.

---

## Was bisher gebaut wurde

### Phase 1 — Fundament und Compliance Layer

| Datei | Inhalt |
|-------|--------|
| `apps/backend/compliance/dsgvo.py` | DSGVO Art. 5, 6, 17, 20, 25, 30, 35 |
| `apps/backend/compliance/eu_ai_act.py` | EU AI Act Art. 9, 13, 14, 52 |
| `apps/backend/audit/audit_logger.py` | Vollständiger Audit Trail |
| `policies/eu_compliance_policy.md` | Compliance Policy Dokument |
| `requirements.txt` | AILIZA-Abhängigkeiten |
| `.env.example` | Konfigurationsvorlage |

### Phase 2 — Agent Core und Tool-Calling

| Datei | Inhalt |
|-------|--------|
| `apps/backend/agent/agent_core.py` | Haupt-Agent, inspiriert von Hermes |
| `apps/backend/agent/conversation_loop.py` | Agent-Schleife mit Tool-Calling |
| `apps/backend/agent/api_client.py` | Anthropic- und OpenAI-Kommunikation |
| `apps/backend/agent/tool_executor.py` | Tool-Ausführung mit Human Oversight |
| `apps/backend/tools/standard_tools.py` | Standard-Toolset |

### KI-Liza Runtime und Gateway

| Datei | Inhalt |
|-------|--------|
| `apps/backend/main.py` | FastAPI-Einstieg für Runtime und Approval-Flows |
| `apps/backend/gateway.py` | Policy-, Risiko- und Approval-Gateway |
| `apps/backend/agent_runtime.py` | Kontrollierter Agentenlauf mit Statusmodell |
| `apps/backend/approval.py` | Approval-Status und Fortsetzung genehmigter Aktionen |
| `apps/backend/policy.py` | Policy-Regeln vor Tool-Ausführung |
| `apps/backend/database.py` | Persistenz für Runs, Approvals und Auditdaten |
| `apps/backend/routers/approvals.py` | Approval-Endpunkte |
| `apps/backend/tests/` | Tests für Runtime, Gateway, Policy und Approval |

### Frontend und Portal

| Pfad | Inhalt |
|------|--------|
| `apps/frontend/` | bestehendes AILIZA React Dashboard |
| `apps/web/dashboard.html` | KI-Liza Dashboard-Prototyp |
| `apps/new-hire-portal/` | Sites-kompatibles New-Hire-Portal |

---

## Verfügbare Tools

| Tool | Beschreibung | Genehmigung |
|------|--------------|-------------|
| `get_current_time` | Aktuelle Uhrzeit | Nein |
| `read_file` | Datei lesen | Nein |
| `write_file` | Datei schreiben | Ja |
| `list_directory` | Verzeichnis auflisten | Nein |
| `calculate` | Mathematische Berechnungen | Nein |
| `read_pdf` | PDF-Text extrahieren | Nein |
| `read_image` | OCR für Bilder/Screenshots | Nein |

---

## EU-Konformität

### DSGVO

- **Art. 5** — Grundsätze der Verarbeitung
- **Art. 6** — Rechtsgrundlage
- **Art. 17** — Recht auf Löschung
- **Art. 20** — Datenübertragbarkeit
- **Art. 25** — Privacy by Design
- **Art. 30** — Audit Trail
- **Art. 35** — Datenschutz-Folgenabschätzung

### EU AI Act

- **Art. 9** — Risikomanagementsystem
- **Art. 13** — Transparenz
- **Art. 14** — Menschliche Aufsicht
- **Art. 50** — Transparenzpflicht bei Limited Risk

### Risikoklasse

**Limited Risk** nach Art. 50 EU AI Act. Transparenzpflicht, Audit Trail und
menschliche Aufsicht sind zentrale Produktprinzipien.

---

## Weekly Compliance Checker

AILIZA enthält einen wöchentlichen Compliance-Abgleich mit offiziellen Quellen:

- EU AI Act: https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng
- EU AI Office: https://digital-strategy.ec.europa.eu/en/policies/ai-office
- DSGVO: https://eur-lex.europa.eu/eli/reg/2016/679/oj
- EDPB: https://edpb.europa.eu
- EDPS: https://edps.europa.eu

Kritische Fristen:

- 01.08.2024 — EU AI Act tritt in Kraft
- 02.02.2025 — Verbotene KI-Praktiken anwendbar
- 02.08.2025 — Governance-Regeln anwendbar
- 02.08.2026 — vollständige Anwendbarkeit
- 02.08.2027 — GPAI-Modelle müssen konform sein

---

## Projektstruktur

```text
C:\Ailiza\
├── apps/
│   ├── backend/
│   │   ├── agent/
│   │   ├── audit/
│   │   ├── compliance/
│   │   ├── gateway/
│   │   ├── routers/
│   │   ├── tools/
│   │   ├── api/
│   │   ├── agent_runtime.py
│   │   ├── approval.py
│   │   ├── database.py
│   │   ├── gateway.py
│   │   ├── main.py
│   │   └── policy.py
│   ├── frontend/
│   ├── new-hire-portal/
│   └── web/
├── docs/
├── examples/
├── packages/
├── policies/
├── scripts/
├── tests/
├── AILIZA_HERMES_PLAN.md
├── requirements.txt
├── requirements_phase3.txt
└── run_agent.py
```

---

## Schnellstart

```powershell
cd C:\Ailiza
copy .env.example .env
pip install -r requirements.txt
pip install -r apps/backend/requirements.txt
py run_agent.py --demo
```

Backend-Runtime aus KI-Liza:

```powershell
cd C:\Ailiza
pip install -r apps/backend/requirements.txt
uvicorn apps.backend.main:app --reload
```

New-Hire-Portal:

```powershell
cd C:\Ailiza\apps\new-hire-portal
npm install
npm run build
```

---

## Nächste Phasen

- AILIZA-Agent-Core und KI-Liza-Runtime fachlich konsolidieren.
- Doppelte Tool- und Gateway-Konzepte vereinheitlichen.
- Frontend Dashboard und internes New-Hire-Portal sauber verlinken.
- Tests für den zusammengeführten Zielstand ausführen und fehlende Abdeckung ergänzen.
- Deployment-/Hosting-Entscheidung für Dashboard und Portal treffen.
