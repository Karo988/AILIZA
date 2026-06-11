# AILIZA — Projektübersicht

**Stand:** 09.06.2026  
**Version:** 0.3.0  
**Repository:** github.com/M-Imica/Ailiza

---

## 🎯 Vision

AILIZA ist ein vollständig EU-konformer KI-Assistent — einfach nutzbar für jeden, ohne technische Kenntnisse, sicher und DSGVO-konform.

---

## ✅ Was bisher gebaut wurde

### Phase 1 — Fundament & Compliance
| Datei | Inhalt |
|-------|--------|
| `apps/backend/compliance/dsgvo.py` | DSGVO Art. 5, 6, 17, 20, 25, 30, 35 |
| `apps/backend/compliance/eu_ai_act.py` | EU AI Act Art. 9, 13, 14, 52 |
| `apps/backend/audit/audit_logger.py` | Vollständiger Audit Trail |
| `policies/eu_compliance_policy.md` | Compliance Policy Dokument |

### Phase 2 — Agent Core + Tools
| Datei | Inhalt |
|-------|--------|
| `apps/backend/agent_runtime.py` | Haupt-Agent mit Streaming |
| `apps/backend/main.py` | FastAPI Backend |
| `apps/backend/gateway.py` | Tool-Ausführung + Human Oversight |
| `apps/backend/routers/approvals.py` | Genehmigungen-System |
| `apps/backend/database.py` | SQLite Datenbank |

### Phase 3 — Gateway + Dashboard
| Datei | Inhalt |
|-------|--------|
| `apps/frontend/index.html` | AILIZA Dashboard v5 |
| `apps/backend/groq_client.py` | Groq LLM Integration (kostenlos) |
| `railway.json` | Deployment-Konfiguration |
| `Procfile` | Server-Startbefehl |

### Super-Agent Skills (neu)
| Datei | Inhalt |
|-------|--------|
| `apps/backend/skills/router_skill.py` | Task-Router (kein LLM nötig) |
| `apps/backend/skills/guardrail_skill.py` | DSGVO + EU AI Act Filter |
| `apps/backend/skills/reflection_skill.py` | RAG Memory + Lernfähigkeit |
| `apps/backend/compliance/eurlex_connector.py` | EUR-Lex Delta-Checker |

---

## 🖥️ Dashboard Features

| Tab | Funktion |
|-----|---------|
| 💬 Chat | KI-Chat mit Verlauf, Modell wählbar |
| 📁 Projekte | Projekte erstellen und verwalten |
| ⚡ Skills | Web-Suche, DSGVO, EU AI Act, E-Mail, Risiko |
| 🛡 Status | Compliance, Genehmigungen, Runs |

### LLM-Auswahl im Dashboard
| Anbieter | Modelle | Key nötig | Kosten |
|----------|---------|-----------|--------|
| 🔍 Web-Suche | Tavily | Nein | Kostenlos |
| Groq | Llama 3, Mixtral | Ja (kostenlos) | Kostenlos |
| Anthropic | Claude Haiku/Sonnet | Ja | Günstig |
| OpenAI | GPT-4o, GPT-4o-mini | Ja | Mittel |
| Mistral | Mistral Small/Large | Ja | Günstig |

---

## ⚠️ Kritische EU AI Act Fristen

| Datum | Status | Beschreibung |
|-------|--------|-------------|
| 01.08.2024 | ✅ | EU AI Act tritt in Kraft |
| 02.02.2025 | ✅ | Verbotene KI-Praktiken anwendbar |
| 02.08.2025 | ✅ | Governance-Regeln anwendbar |
| **02.08.2026** | **⚠️ 54 Tage** | **VOLLSTÄNDIGE Anwendbarkeit** |
| 02.08.2027 | 🔜 | GPAI-Modelle müssen konform sein |

---

## ⚖️ EU-Konformität

### DSGVO Artikel
| Artikel | Beschreibung | Status |
|---------|-------------|--------|
| Art. 5 | Grundsätze der Verarbeitung | ✅ |
| Art. 6 | Rechtsgrundlage | ✅ |
| Art. 17 | Recht auf Löschung | ✅ |
| Art. 20 | Datenportabilität | ✅ |
| Art. 25 | Privacy by Design | ✅ |
| Art. 30 | Audit Trail | ✅ |
| Art. 35 | Datenschutz-Folgenabschätzung | ✅ |

### EU AI Act Artikel
| Artikel | Beschreibung | Status |
|---------|-------------|--------|
| Art. 9 | Risikomanagementsystem | ✅ |
| Art. 13 | Transparenz | ✅ |
| Art. 14 | Menschliche Aufsicht | ✅ |
| Art. 52 | Transparenzpflicht (Limited Risk) | ✅ |

**Risikoklasse:** Limited Risk (Art. 52 EU AI Act)

---

## 🚀 Schnellstart (lokal)

```powershell
# 1. Backend starten
cd C:\Ailiza
python -m uvicorn apps.backend.main:app --port 8001 --reload

# 2. Dashboard öffnen
# Browser: http://127.0.0.1:8001/dashboard

# 3. Oder BAT-Datei doppelklicken
# C:\Ailiza\start_ailiza.bat
```

---

## 🌐 Online Deployment (Railway.app)

```
1. railway.app → New Project → GitHub → M-Imica/Ailiza
2. Variables:
   GROQ_API_KEY = gsk_...
   ANTHROPIC_API_KEY = sk-ant-... (optional)
3. Deploy → Fertig!
```

**Ergebnis:** Jeder kann AILIZA per Link nutzen — kein Download, kein Python, kein eigener API-Key.

---

## 🛡️ Sicherheits-Stack

| Feature | Implementierung | Status |
|---------|----------------|--------|
| HTTPS | Railway automatisch | ✅ |
| Rate Limiting | 20 Anfragen/Min pro IP | ✅ |
| Input-Validierung | Pydantic | ✅ |
| PII-Erkennung | Guardrail Skill | ✅ |
| Audit-Logging | SQLite | ✅ |
| Human Oversight | Approvals-System | ✅ |
| EU-Server | Railway Frankfurt | 🔜 |

---

## 🔜 Nächste Schritte

1. **Groq API-Key** eintragen → AILIZA antwortet intelligent
2. **Railway Deployment** → Online für alle erreichbar
3. **Nutzer-Management** → Login, Rollen, Teams
4. **Mobile App** → PWA für Smartphone

---

## 📌 Git Historie

| Commit | Beschreibung |
|--------|-------------|
| aktuell | Dashboard v5 + LLM-Auswahl + Deployment |
| 6e562fe | docs: Projektübersicht hinzugefügt |
| c1f2839 | feat: Weekly Compliance Checker |
| 872257e | feat: Phase 2 - Agent Core + Tools |
| 0597048 | feat: Phase 1 - Fundament + Compliance |

---

## 🔑 Konfiguration (.env)

```env
# Pflicht für KI-Antworten (kostenlos)
GROQ_API_KEY=gsk_dein_key_hier

# Optional
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...
AILIZA_DATA_RETENTION_DAYS=90
AILIZA_HUMAN_OVERSIGHT=true
```

---

*AILIZA — EU AI Act Limited Risk · DSGVO konform · Stand 09.06.2026*
