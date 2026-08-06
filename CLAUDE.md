# AILIZA — Projektkontext fuer Claude Code

## AILIZA Vision & Anforderungen

**AILIZA** = DSGVO + EU AI Act konformer KI-Assistant fuer alle KMUs
- Nutzerfreundlich, aber mit maximaler Datensicherheit
- Multi-LLM Support: ChatGPT, Anthropic, Groq, Mistral + Chinesische LLMs (DeepSeek, Qwen) mit Punktesystem
- **Zertifizierungsreife erforderlich** (DSGVO-Konformität ist Voraussetzung, nicht Feature)
- Backend: FastAPI + SQLAlchemy (SQLite). Jeder externe LLM-Call laeuft durch eine mehrstufige Governance-Pipeline.

## KRITISCHE ANFORDERUNGEN

⚠️ **NICHTS ohne Genehmigung aendern!** Vor jeder Code-Aenderung: ERST erklaeren WAS und WARUM, dann auf OK warten.

✅ **Governance ist zentral** — jede PII, die unredaktiert rausgeht, ist ein Zertifizierungs-Fehler.

✅ **Alle 5 DSGVO-Kategorien muessen redaktiert werden:** secret (⚫) > forbidden (🔴) > confidential (🟠) > high (🟡) > normal (🟢)

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

**GRUNDREGEL: Erst fragen, dann programmieren.**
- Vor jeder Code-Aenderung: ERKLAEREN WAS und WARUM wird geaendert.
- Dann auf OK/Bestaetigung WARTEN.
- Erst DANACH: Aenderung durchfuehren, committen, pushen.
- Keine Aktion ohne explizite Rueckmeldung der Nutzerin.
- NIEMALS ohne Genehmigung aendern!

**Wichtig fuer Zertifizierung:**
- Jede Redaction-Rule muss korrekt sein (keine False Positives/Negatives)
- DSGVO-Kategorien sind nicht verhandelbar (Art. 5, 6, 9, 10)
- Governance-Pipeline darf nicht umgangen werden
- Audit-Logs muessen lueckenlos sein

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

## Zugangs- und Tier-Konzept (Roadmap)
Jeder kann AILIZA kostenlos ausprobieren. Ab ~20 Anfragen oder bei DSGVO-relevanten Daten
ist eine kostenlose Registrierung erforderlich (Art. 6 DSGVO — Einwilligung mit Identifikation).

| Tier    | Login | Anfragen  | Modelle                        |
|---------|-------|-----------|--------------------------------|
| Anonym  | Nein  | ~20/Tag   | Einfach (Groq/Llama)           |
| Free    | Ja    | Mehr      | Einfache Modelle               |
| Pro     | Ja    | Viel mehr | + Anthropic / GPT              |
| Enterprise | Ja | Unbegrenzt | Alle inkl. DeepSeek, Qwen   |

Admin-Endpoints (/admin/*) bleiben immer passwortgeschuetzt (nur Betreiberin).
Chat-Endpoints sind aktuell offen (kein Token noetig) — Tier-Logik kommt spaeter.

## Mandanten
`DEFAULT_TENANT_ID = AILIZA_DEFAULT_TENANT_ID` (Default `default`). Alle Logs/Runs/Facts
sind tenant-gefiltert.

## Model-Strategie fuer Claude Code Sessions

⚠️ **PFLICHT:** Claude muss in JEDER Antwort explizit mitteilen, welches Modell
fuer die anstehende Aufgabe empfohlen wird (auch wenn unveraendert zum
aktuellen) — nicht nur bei Modellwechseln. Kurzer Satz reicht, z.B.
"Empfehlung: Sonnet 5 (Bugfixing)." Karo stellt das Modell manuell um.

**Standard: Sonnet 5**
- Iterative Entwicklung (Pattern-Fixes, Tests, Debugging)
- Governance-Code (Policy, Redaction)
- Bugfixing & Refactoring
- Gutes Preis-Leistungs-Verhaeltnis bei langen Sessions

**Opus 4.8:** Nur fuer
- Grosse Architektur-Entscheidungen (z.B. Pipeline neu designen)
- DSGVO/EU AI Act Compliance-Fragen (Art. 9 Kategorisierung, etc.)
- Code-Reviews vor Meilensteinen
- Komplexe Sicherheits-Analysen

**Haiku:** Nur fuer triviale Aufgaben (Syntax, Formatierung, Status-Checks)

## Promptregeln fuer Opus 5 Sessions

Diese Regeln gelten, sobald Opus 5 fuer eine Aufgabe verwendet wird.
Sie ersetzen nicht die allgemeinen Arbeitsregeln — sie ergaenzen sie.

### Regel 1 — Ganze Aufgabe auf einmal geben
**Was tun:** Vollstaendige Spezifikation und alle Schritte von Anfang an in einen Prompt.
Opus 5 profitiert von langen, zusammenhaengenden Aufgaben und liefert fertige Ergebnisse.
**Was vermeiden:** Haepchenweise vorgehen (erst Recherche, dann Struktur, dann Text).
Keine Zwischenergebnisse abfragen, wenn das Ziel klar ist.
**Prompt-Baustein:** "Erstelle ein vollstaendiges [Ergebnis] inklusive [Teil A], [Teil B] und [Teil C] in einem Durchgang."

### Regel 2 — Aufgabenrahmen definieren
**Was tun:** Klaren Rahmen setzen, was NICHT Teil der Aufgabe ist.
Kleine Entscheidungen selbststaendig treffen lassen — Rueckfragen nur bei echten Weggabelungen.
**Was vermeiden:** Unklare Grenzen, die zu ungewollter Aufgabenerweiterung fuehren.
Haepchenschleifen durch zu viele Rueckfragen.
**Prompt-Baustein:** "Bleib beim bestellten Umfang. Kleinere Entscheidungen triffst du selbst; frag nur bei grundlegend unterschiedlichen Lesarten nach."

### Regel 3 — Laenge getrennt steuern
**Was tun:** Laenge fuer Chat-Antwort und eigentliches Dokument separat kalibrieren.
Genaue Vorgaben zu Zeilenanzahl oder Modulen machen.
**Was vermeiden:** Fuelltext, wiederholte Zusammenfassungen, Standardfloskeln,
ungefilterte Chat-Zusammenfassungen des Inhalts.
**Prompt-Baustein:** "Halte das Dokument inhaltlich vollstaendig ohne Fuelltext.
Antworte im Chat danach nur in maximal drei kurzen Stichpunkten."

### Regel 4 — Kontrollsaetze loeschen
**Was tun:** Qualitaetskriterien definieren, aber dem Modell vertrauen.
Bei Textpruefungen alles melden lassen und spaeter selbst filtern.
**Was vermeiden:** Saetze wie "Pruefe deine Antwort doppelt", "Verifikationsschritt einbauen"
oder "Melde nur schwere Fehler". Kein unnötiges Token-Limit-Verbrauchen durch Ueberprüfung der Ueberpruefung.
**Prompt-Baustein:** [Kein Baustein — diese Saetze ersatzlos streichen]

### Regel 5 — Subagenten begrenzen
**Was tun:** Delegation nur bei grossen, unabhaengigen Arbeitspaketen erlauben.
Explizite Grenzen fuer Subagenten in Projektanweisungen setzen.
**Was vermeiden:** Subagenten zur Kontrolle der eigenen Arbeit einsetzen.
Delegation von Kleinstaufgaben.
**Prompt-Baustein:** "Delegiere nur bei grossen, unabhaengigen Arbeitspaketen.
Nutze keine Subagenten, um deine eigene Arbeit zu kontrollieren."
