# AILIZA — AI Governance System

AILIZA ist ein Kontrollrahmen für den sicheren Einsatz externer KI-Anbieter (GPT, Claude, etc.) in regulierten Umgebungen. Kein eigenes Modell — Governance, Audit und Kontrolle.

**Stand:** 24.06.2026 | **Basis v1.0 Spec-ready** | Tech-ready: ausstehend

## Aktueller Teststatus

```
87/87 Tests grün
```

## Arbeitsregel

Vor jedem wichtigen technischen Schritt:
1. Erklären was gemacht wird und warum
2. Dateien nennen
3. Risiken nennen
4. Auf explizite Freigabe warten

## Dokumentation

| Ordner | Inhalt |
|--------|--------|
| `docs/00_masterplan/` | Baseline, Prinzipien, Gap-Liste |
| `docs/01_addendum/` | Korrekturen und Nachträge |
| `docs/02_workphases/` | Aktiver Arbeitsstand |
| `docs/03_specs/` | Technische Spezifikationen |
| `docs/04_schemas/` | JSON-Schemas |
| `docs/05_prompts/` | Prompt-Vorlagen für Folge-Sessions |
| `docs/06_release/` | Beta-Checkliste |

## Offene Komponenten

- Memory-Backend SQLite-Persistenz
- Kill-Switch-Persistenz
- BS-14–18 auf persistentem Backend schließen

---

---

## 🎯 Vision

AILIZA ist ein vollständig EU-konformer AI Agent, der:
- **DSGVO-konform** (Datenschutz by Design & by Default) operiert
- Den **EU AI Act** (in Kraft seit August 2024) vollständig erfüllt
- Alle Stärken eines modernen Agenten mitbringt (Tools, Memory, Multi-Turn)
- **Transparenz und menschliche Aufsicht** als Kernprinzipien hat

---

## 🏗️ Architektur

```
ailiza/
├── apps/
│   ├── backend/
│   │   ├── agent/          # Agent Core (inspiriert von Hermes)
│   │   ├── compliance/     # DSGVO + EU AI Act Layer
│   │   ├── gateway/        # API Gateway + Policy Engine
│   │   ├── audit/          # Audit Trail & Logging
│   │   ├── tools/          # Tool Registry
│   │   ├── routers/        # Approval- und Runtime-Routen
│   │   └── api/            # FastAPI Endpoints
│   ├── frontend/           # React Dashboard
│   ├── new-hire-portal/    # internes Onboarding-Portal
│   └── web/                # KI-Liza Dashboard-Prototyp
├── docs/                   # Dokumentation
├── examples/               # Beispiele
├── packages/               # Paket-/Modulplatzhalter
├── policies/               # EU AI Act & DSGVO Policies
├── tests/                  # Tests
└── scripts/                # Setup & Deploy Scripts
```

---

## ⚖️ EU AI Act Konformität

AILIZA ist als **Limited Risk AI System** klassifiziert (Art. 52 EU AI Act):

| Anforderung | Umsetzung |
|-------------|-----------|
| Transparenzpflicht | User-Benachrichtigung beim Start |
| Menschliche Aufsicht | Human-in-the-Loop bei kritischen Aktionen |
| Audit Trail | Vollständiges Logging aller Aktionen |
| Datenschutz | DSGVO Art. 25 (Privacy by Design) |
| Recht auf Erklärung | Erklärbare Entscheidungen (Art. 22 DSGVO) |
| Datensparsamkeit | Nur notwendige Daten werden gespeichert |

---

## 🔒 DSGVO Compliance

- **Art. 5** — Grundsätze der Verarbeitung
- **Art. 17** — Recht auf Löschung ("Recht auf Vergessenwerden")
- **Art. 20** — Recht auf Datenübertragbarkeit
- **Art. 25** — Datenschutz durch Technikgestaltung
- **Art. 35** — Datenschutz-Folgenabschätzung (DSFA)

---

## 🚀 Schnellstart

```bash
# Installation
pip install -r requirements.txt
pip install -r apps/backend/requirements.txt

# Konfiguration
cp .env.example .env

# Starten
python run_agent.py
```

---

## Runtime API

Der zusammengeführte KI-Liza-Backendstand ergänzt eine kontrollierte Runtime API:

- `POST /agent/run` startet einen Agentenlauf.
- `GET /agent/runs` listet Agentenläufe.
- `GET /agent/runs/{run_id}` zeigt den Status eines Laufs.
- `POST /agent/approvals/{approval_id}/continue` führt eine genehmigte Aktion fort.
- Stream-Endpunkte liefern Fortschritt, Approval-Wartezustand und Ergebnis per SSE.
- `POST /tools/search` und `POST /tools/fetch` laufen durch Gateway, Policy und Audit.

Agentenläufe sind bewusst kontrolliert: Policy-Prüfung, Risikobewertung,
Human Oversight und Audit Logging bleiben Teil jedes Tool-Aufrufs.

---

## New-Hire-Portal

Unter `apps/new-hire-portal` liegt ein Sites-kompatibles internes
Onboarding-Portal für neue Teammitglieder. Es enthält Checkliste, Rollenfokus,
Wochenplan, Ressourcen und Kontakte. Der lokale Checklistenfortschritt bleibt
gerätelokal und speichert keine personenbezogenen Onboarding-Daten im Backend.

---

## 📋 Status

- [x] Phase 1: Projektstruktur & Fundament
- [x] Phase 2: Agent Core
- [x] Phase 3: Compliance Layer
- [x] Gateway, Policy- und Approval-Runtime aus KI-Liza ergänzt
- [x] Interne Dashboard- und Portal-Prototypen ergänzt
- [ ] AILIZA- und KI-Liza-Backendmodule fachlich konsolidieren
- [ ] Frontend Dashboard final integrieren
