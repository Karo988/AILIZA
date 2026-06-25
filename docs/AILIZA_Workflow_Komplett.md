# AILIZA — Vollständiger Workflow

Stand: 2026-06-19 | Version 2.0 — integriert aus allen bisherigen Sessions

---

## Zielbild

AILIZA verarbeitet jede Anfrage so:

> schnell, verständlich, datensparsam, nachvollziehbar, mandantensicher,
> mit klarer Freigabe bei Risiko und ohne ungeprüften externen Datenabfluss.

Jede Anfrage wird vor Ausgabe an vier Kriterien gemessen:

1. Datenminimierung eingehalten?
2. Zweck klar und dokumentiert?
3. Freigabe vorhanden (wenn nötig)?
4. Nachweis erzeugbar?

Sprachregelung: „Freigabe" oder „Nutzerbestätigung" statt „Einwilligung".
DSGVO-Einwilligung (Art. 6 Abs. 1 lit. a) ist ein eigenständiger Rechtsbegriff und nicht automatisch die passende Rechtsgrundlage.

---

## Gesamtarchitektur — Datenfluss

```
Anfrage-Eingang
      │
      ▼
[1] Sofortprüfung (Mandant, Auth, Rate-Limit, Kill-Switch)
      │
      ▼
[2] Data Governance Layer (Klassifikation, PII, Secret, Lineage)
      │
      ▼
[3] Policy-Gateway (erlauben / hinweisen / anonymisieren / Freigabe / blockieren)
      │
      ├──[blockiert]──► Klare Begründung + sichere Alternative
      │
      ▼
[4] Token-Budget + Routing (Simple / Standard / Komplex / Dokument / Riskant)
      │
      ├──[Simple]──► Fast-Path lokal → Antwort → Anzeige
      │
      ▼
[5] Provider-Orchestrator (Adapter-Auswahl nach Policy + Budget)
      │
      ▼
[6] Redaction & Prompt-Building (PII ersetzen, Secrets entfernen, Memory-Policy)
      │
      ▼
[7] Modell / Tool-Aufruf (Groq / lokal / Tool-Chain)
      │
      ▼
[8] Output-Guardrail (bei Riskant: gepuffert prüfen)
      │
      ▼
[9] Antwort-Erzeugung (Streaming / gepuffert / Fortschritt)
      │
      ▼
[10] Logging (Audit / Security / Performance / Cost — kein Inhalt)
      │
      ▼
[11] Nutzeranzeige (Risikoampel, Verarbeitungsort, Freigabestatus, Quelle)
      │
      ▼
[12] Feedback-Loop (optional: ✓/✗, quality_score, Admin-Vorschlag)
```

Parallele Threads (laufen nicht sequenziell, sondern gleichzeitig wo möglich):
- Memory-Retrieval-Check (vor Schritt 6)
- Kostenschätzung (vor Schritt 5)
- Lineage-Metadaten (parallel zu Schritt 2)

---

## Stufe 1 — Anfrage-Eingang

### Input-Quellen

- Chat-Eingabe (Text, Sprache)
- Datei-Upload (PDF, DOCX, XLSX, Bilder)
- Memory (interne Fakten-Datenbank, mandantenisoliert)
- Tool-Ergebnis (Kalender, CRM, Websuche, Notion, API)
- Webhook / Automatisierung
- Admin-Trigger

### Sofortprüfung (synchron, vor allem anderen)

| Prüfung | Fehler-Reaktion |
|---|---|
| Mandant vorhanden und aktiv? | 401 Unauthorized |
| Nutzer authentifiziert? | 401 Unauthorized |
| Rate-Limit eingehalten? | 429 Too Many Requests + deutsche Meldung |
| Dateigröße/Promptgröße erlaubt? | 413 Payload Too Large |
| Externe KI grundsätzlich aktiviert? | Lokale Verarbeitung oder Blockade |
| Kill-Switch aktiv? | Sofortiger Stopp aller LLM-Aufrufe |

**Wichtig:** Fast-Path darf erst starten, wenn die Sofortprüfung bestanden ist und keine sensiblen Muster erkannt wurden. Auch lokale Verarbeitung ist DSGVO-relevant.

---

## Stufe 2 — Data Governance Layer

Läuft vor jeder Policy- oder Modellentscheidung. Erzeugt Lineage-Metadaten für jeden Datenfluss.

### Klassifikationsebenen (Multi-Label — ein Objekt kann mehrere Klassen haben)

| Klasse | Beispiele | Strengste Regel gewinnt |
|---|---|---|
| PUBLIC | Allgemeinwissen, Hilfetexte | Überall verarbeitbar |
| INTERNAL | Interne Prozesse, Vorlagen | Nur mandantenintern |
| CONFIDENTIAL | Verträge, Finanzdaten, Strategie | Nur lokal oder geprüfter EU-Provider |
| PERSONAL_DATA | Name, E-Mail, Adresse | DSGVO-Prüfung, Zweckbindung |
| SENSITIVE_PERSONAL | Gesundheit, Religion, Biometrie | Art. 9 DSGVO, Sonderprüfung |
| SECRET | API-Keys, Passwörter, Tokens | Immer blockieren, niemals extern |
| LEGAL | Vertragsklauseln, Rechtsstreitigkeiten | Anwaltsprivileg prüfen |
| HR | Personalakten, Gehälter, Bewerbungen | Strenge Zweckbindung |
| CRITICAL | Notfallpläne, Sicherheitskonzepte | Nur lokal |

### Prüfungen

- Multi-Label-Datenklassifikation (Pattern-basiert, lokal, kein externer LLM)
- Secret-Erkennung (Regex: API-Keys, Tokens, Passwörter)
- PII-Erkennung (Name, E-Mail, IBAN, Telefon, Adresse)
- Datenquelle + Mandant + Zweck dokumentieren
- Zielsystem bestimmen: RAM / Session / Audit / File Storage / Memory / Vector DB / External LLM / CRM / E-Mail / Admin UI
- Retention-Klasse zuweisen
- Externe Verarbeitung erlaubt? (aus ProviderProfile + Mandanten-Config)
- Lineage-Metadaten erzeugen (Pflicht für jede Verarbeitungsstufe)

### Datenfluss-Matrix (Zielsystem-basiert)

| Datenklasse | RAM/Session | Audit-Log | File Storage | Memory | External LLM | CRM/E-Mail |
|---|---|---|---|---|---|---|
| PUBLIC | ✓ | Meta only | ✓ | ✓ | ✓ | ✓ |
| INTERNAL | ✓ | Meta only | ✓ | ✓ | Mandant-Policy | Eingeschränkt |
| CONFIDENTIAL | ✓ | Meta only | Verschlüsselt | Opt-in | EU-Provider only | Nein |
| PERSONAL_DATA | Minimiert | Meta only | Verschlüsselt | Opt-in + Zweck | Redacted | Zweckgebunden |
| SENSITIVE_PERSONAL | Minimiert | Meta only | Verschlüsselt | Nein | Nein | Nein |
| SECRET | Nein | Incident only | Nein | Nein | Nein | Nein |
| LEGAL | ✓ | Meta only | Verschlüsselt | Opt-in | EU-Provider only | Nein |
| HR | Minimiert | Meta only | Verschlüsselt | Nein | Nein | Nein |
| CRITICAL | ✓ | Meta only | Verschlüsselt | Nein | Nein | Nein |

---

## Stufe 3 — Policy-Gateway

### Entscheidungen

| Entscheidung | Bedeutung |
|---|---|
| `ALLOW` | Verarbeitung ohne Einschränkung |
| `ALLOW_WITH_NOTICE` | Verarbeitung + Hinweis an Nutzer |
| `ANONYMIZE` | Redaction ausführen, dann verarbeiten |
| `APPROVAL_REQUIRED` | Nutzer-Freigabe nötig, danach weiter |
| `BLOCK` | Keine Verarbeitung, klare Begründung |

### Entscheidungsgrundlagen

- Datenklasse (aus DGL)
- Zweck (aus Request-Kontext)
- ProviderProfile (aktiv? EU? Zertifiziert? AVV vorhanden?)
- Nutzerrolle (User / Manager / Admin / DSB)
- Mandant (aktiv? Override-Policy?)
- Tool/Capability (welches Tool wird gerufen?)
- Redaction-Status (wurde bereits anonymisiert?)
- Freigabe-Status (liegt gültige Nutzerfreigabe vor?)
- Kostenlimit (Budget überschritten?)
- Policy-Version (aktuell? Änderung dokumentiert?)

### Rot-Klasse-Regel

SECRET und SENSITIVE_PERSONAL sind niemals über den normalen Chat-Flow freizugeben.
Ausnahmen laufen ausschließlich über einen dokumentierten Ausnahmeprozess mit Admin-Bestätigung, Audit-Eintrag und Begründung.

---

## Stufe 4 — Routing & Performance

### Routen-Tabelle

| Route | Modell | Verarbeitung | Ziel-Latenz |
|---|---|---|---|
| SIMPLE | Lokal / Fast-Path | Synchron, kein LLM | < 200 ms |
| STANDARD | Llama 8B / kleines Modell | Streaming | < 3 s |
| KOMPLEX | Llama 70B | Satz-Pufferung | < 10 s |
| DOKUMENT | Kleines Modell + Chunking | Async + Fortschritt 0–100 % | < 30 s |
| RISKANT | Llama 70B + Output-Guardrail | Gepuffert + Freigabe | Variabel, sicher |

Fast-Path-Beispiele (SIMPLE): Datum/Uhrzeit, Begrüßung, einfache Rechnung, Hilfe-Texte, interne FAQ-Treffer.

### Performance-Maßnahmen

| Maßnahme | Begründung |
|---|---|
| Fast-Path-Router (Regex/Dictionary, 0 Token) | Einfache Anfragen lokal ohne LLM |
| Token-Budget-Gateway (schätzt vor Routing) | Verhindert unnötige 70B-Aufrufe |
| Routeabhängige Modellwahl | Kleinstes sicheres Modell je Aufgabe |
| Streaming via fetch() ReadableStream | Gefühlte Latenz sinkt deutlich |
| Satz-/Absatzpufferung bei Riskant | Kein Partial-Output bei sensiblen Daten |
| asyncio.gather() für parallele Tools | Multi-Tool-Latenz −40–60 % (Messhypothese) |
| Async Dokumentenverarbeitung + Fortschritt | Kein Frontend-Freeze |
| Compliance-Kontext Lazy-Load | Nur bei KOMPLEX/CRITICAL geladen |
| Connection Pooling (SQLite + httpx.AsyncClient) | Reduziert Overhead bei Last |
| Hard Timeout: 90 s, dann deutsche Fehlermeldung | Keine hängenden Requests |
| Retry nur bei HTTP 408/429/503 | Exponential Backoff 100 ms → max 32 s ± Jitter |
| Preloading häufiger Compliance-Muster beim Start | Kein Kalt-Start bei erster Compliance-Anfrage |

**Hinweis:** Prozentuale Einsparungswerte (30 % weniger Anfragen, 40 % Kostenersparnis) sind Hypothesen bis echte Messdaten aus dem Produktivbetrieb vorliegen.

### Performance-Monitoring

- P50 / P95 / P99 je Route
- Slow-Query-Log bei > 5 s
- Provider-Availability-Check beim Start
- Dashboard: Latenz / Fehlerquote / Kosten / Provider-Status
- Storage: data/metrics.db (SQLite) — kein externer Dienst für MVP

---

## Stufe 5 — Provider-Orchestrator

Keine Businesslogik ruft einen LLM-Provider direkt auf. Alle Aufrufe laufen über den Orchestrator.

### Provider-Interface

```python
class LLMProvider:
    def generate(prompt, params) -> str
    def stream(prompt, params) -> AsyncIterator[str]
    def count_tokens(text) -> int
    def estimate_cost(tokens, model) -> float
    def supports_streaming() -> bool
    def supports_json_mode() -> bool
    def max_context_tokens() -> int
    def provider_region() -> str          # z.B. "EU", "US"
    def provider_profile_version() -> str
```

### Ablauf vor jedem Provider-Call

1. Policy-Gateway hat `ALLOW` oder `ALLOW_WITH_NOTICE` entschieden.
2. ProviderProfile ist aktiv und AVV liegt vor.
3. Daten wurden minimiert / redacted.
4. Kostenbudget reicht für diese Anfrage.
5. Provider wird ausgewählt (Failover-Reihenfolge konfigurierbar).
6. Antwort wird erzeugt und zurückgegeben.

### Provider-Erweiterbarkeit

Groq ist Adapter Nr. 1. Die Architektur ist provider-agnostisch.
Geplante Adapter: OpenAI, lokale Modelle (llama.cpp), EU-zertifizierte Provider.

### ProviderProfile-Felder

```
provider_id, name, region, eu_certified, avv_signed, avv_date,
allowed_data_classes[], max_tokens, cost_per_1k_tokens,
supports_streaming, supports_json_mode, active, profile_version
```

---

## Stufe 6 — Redaction & Prompt-Building

Vor jedem externen LLM-Call:

| Schritt | Aktion |
|---|---|
| Secret-Block | API-Keys, Tokens, Passwörter → `[SECRET_REMOVED]` |
| PII-Ersatz | Name → `[NAME]`, E-Mail → `[EMAIL]`, IBAN → `[IBAN]` |
| Inhalts-Minimierung | Nur relevante Chunks, keine Vollhistorie |
| Chunk-Auswahl | Nur Abschnitte mit hoher Relevanzbewertung |
| Memory-Retrieval | Nur wenn alle 7 Bedingungen erfüllt (siehe Stufe 10) |
| Quellen-Trennung | System-Kontext / Compliance-Kontext / Nutzer-Input klar getrennt |
| Prompt-Finalisierung | Token-Zählung vor Absenden, Budget-Check |

**Memory-Fakten sind abgeleitete Daten** mit eigener Klasse, Retention, Quelle und Löschlogik — nicht gleich behandeln wie Rohdaten.

---

## Stufe 7 — Antwort-Erzeugung

### Ausgabemodi je Route

| Route | Ausgabe |
|---|---|
| SIMPLE | Direkte Antwort, synchron |
| STANDARD | Streaming, Token für Token |
| KOMPLEX | Satz-Pufferung, dann Ausgabe |
| DOKUMENT | Fortschrittsanzeige 0–100 %, dann Ergebnis |
| RISKANT | Output-Guardrail, dann gepufferte Ausgabe |
| BLOCKIERT | Klare Begründung auf Deutsch + sichere Alternative |

### Nutzeranzeige — Pflichtfelder je Antwort

- Verarbeitungsort: lokal / extern (Provider-Name)
- Speicherstatus: gespeichert / nicht gespeichert
- Freigabestatus: aktiv / nicht aktiv
- Risikoampel: Grün / Gelb / Orange / Rot + Textlabel
- Quellenangabe: bei Compliance-Aussagen immer mit Stand/Version

---

## Stufe 8 — Freigabe-UI

Wird ausgelöst, wenn Policy-Gateway `APPROVAL_REQUIRED` entscheidet.

### Anzeigepflichten

- Was wird verarbeitet? (Datenklasse, Kurzbeschreibung)
- Wohin geht es? (Provider, Region)
- Warum ist Freigabe nötig? (Policy-Regel + Erklärung)
- Wie lange gilt die Freigabe? (TTL, Standard: Session)
- Welche Alternative gibt es? (Lokal bearbeiten / Anonymisieren)

### Buttons

| Button | Aktion |
|---|---|
| Abbrechen | Anfrage verwerfen, keine Verarbeitung |
| Anonymisieren | Redaction ausführen, dann ohne Freigabe weiter |
| Lokal bearbeiten | Route auf SIMPLE/lokal umschalten |
| Freigeben | Nutzerfreigabe erteilen, TTL setzen, Audit-Eintrag |

---

## Stufe 9 — Logging & Nachweis

### Vier getrennte Log-Zwecke

| Log | Inhalt | Nie enthalten |
|---|---|---|
| Audit | Policy-Entscheidung, Regel, Datenklasse, Freigabe, Nutzerrolle, Timestamp | Prompts, Antworten |
| Security | Secret erkannt, Incident, Missbrauch, Blockade-Grund | Secrets, PII |
| Performance | Latenz, Fehlerquote, Route, Provider, Token-Anzahl | Texte, Inhalte |
| Cost | Tokens, Provider, Mandant, Use-Case, Kosten | Inhalte, PII |

### Logging-Regeln

- Logs sind getrennte SQLite-Tabellen (kein gemeinsames Log-File)
- Zugriff: nur Admin und DSB
- Retention je Log-Typ konfigurierbar (Standard Audit: 3 Jahre, Security: 5 Jahre, Performance/Cost: 90 Tage)
- Lösch-Protokolle selbst sind personenbezogen möglich → minimal, zugriffsbeschränkt, eigene Retention

### Audit-Log Pflichtfelder

```
id, company_id, user_id_hash, timestamp, route, data_class[],
policy_decision, policy_rule_id, policy_version,
provider (wenn extern), approval_given (bool), approval_ttl,
tool_used, redaction_applied (bool), cost_estimate
```

---

## Stufe 10 — Memory & Reflection (Reflection Skill)

### Was darf gespeichert werden

| Erlaubt | Nicht erlaubt |
|---|---|
| Firmenvokabular | Credentials, API-Keys |
| Formale Präferenzen (Anrede, Format) | Besondere Kategorien (Art. 9 DSGVO) |
| Wiederkehrende FAQ-Muster (kein PII) | HR-Daten, Gehälter, Personalakten |
| Projektkontext (wenn freigegeben) | Rechtsstreitigkeiten |
| Mandantenspezifische Abkürzungen | Sicherheitskonzepte, Notfallpläne |
| | Sensible Finanzdaten |
| | Ungeprüfte personenbezogene Daten |

### SQLite-Schema (reflection_facts)

```sql
CREATE TABLE reflection_facts (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    user_id TEXT,
    data_class TEXT NOT NULL,
    content TEXT NOT NULL,
    quality_score REAL DEFAULT 1.0,  -- min 0.0, max 2.0
    opt_in_confirmed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,        -- Standard: 90 Tage
    source TEXT,
    pii_cleared INTEGER DEFAULT 0
);
```

### Retrieval-Policy — alle 7 Bedingungen müssen erfüllt sein

1. Mandant passt (`company_id`)
2. Nutzer/Zweck passt (Rolle + Use-Case erlaubt)
3. `opt_in_confirmed = 1`
4. Datenklasse für diesen Provider freigegeben
5. Provider erlaubt (ProviderProfile)
6. `expires_at` in der Zukunft
7. PII-Check bestanden (`pii_cleared = 1`)

Nur wenn alle 7 erfüllt → Top-K Fakten in Prompt aufnehmen.

### Feedback-Loop und quality_score

```
Antwort → Nutzer bewertet ✓ oder ✗ (+ optionaler Freitext)

✓ hilfreich     → quality_score + 0.1  (max 2.0)
✗ nicht hilfreich → quality_score − 0.2  (min 0.0)

quality_score < 0.3 → Fakt nicht mehr abgerufen (inaktiv)
≥ 3 negative Bewertungen desselben Fragetyps → Routing-Anpassungsvorschlag im Admin-Dashboard
Admin bestätigt manuell → Änderung aktiviert + versioniert
```

### Adaptives Routing

Nur Vorschläge, niemals automatisch. Jede Änderung erzeugt:
```
policy_version, changed_by, reason, previous_route, new_route, timestamp
```

### Was AILIZA nicht lernt

- Kein Training mit PII
- Kein mandantenübergreifendes Lernen
- Kein unsichtbares Lernen (alle Facts im Dashboard sichtbar)
- Kein Lernen von Credentials
- Kein automatisches Finetuning — weder intern noch über externe Provider

### DSGVO-Compliance des Lernens

| Anforderung | Umsetzung |
|---|---|
| Opt-in | `opt_in_confirmed = 0` als Safe Default |
| Transparenz | Memory-Ansicht im Admin-Dashboard: alle Facts sichtbar |
| Löschung Einzelfakt | `DELETE /memory/{fact_id}` |
| Löschung gesamt | `DELETE /memory?company_id=X` (Art. 17 DSGVO) |
| VVT-Eintrag | Memory als eigener Verarbeitungsvorgang |
| Retention | `expires_at` je Fakt (Standard: 90 Tage) |
| Rechtsgrundlage | Je Mandant und Use-Case prüfen — Produkt-Opt-in ≠ DSGVO-Einwilligung |

---

## Stufe 11 — Feedback & Weiterentwicklung

- Nutzer bewertet Antwort (✓/✗ + Freitext optional)
- quality_score wird angepasst (siehe Stufe 10)
- Schlechte Muster werden **nicht** automatisch produktiv geändert
- Admin sieht alle Vorschläge im Dashboard
- Admin bestätigt Änderungen manuell
- Jede bestätigte Änderung wird versioniert (policy_version, changed_by, reason, timestamp)
- Erfolgreiche Antworten: Admin kann per Klick zum internen Goldenset hinzufügen

---

## Stufe 12 — Dokumenten-Workflow

Dateien sind oft riskanter als Chat-Texte. Dokumenten-Governance muss vor Gate 2 (Pilot mit echten Daten) vollständig stehen.

### 11-Schritte-Ablauf

1. **Upload** — Datei empfangen, Metadaten erfassen
2. **Dateityp-Prüfung** — Erlaubte Typen: PDF, DOCX, XLSX, TXT, CSV (konfigurierbar)
3. **Malware-Scan** — soweit im Deployment möglich (ClamAV oder Virustotal-API optional)
4. **Dokument-Klassifikation** — Data Governance Layer auf Dokument anwenden
5. **PII-/Secret-Scan** — vollständiger Scan vor Chunking
6. **Vorschau sensibler Stellen** — Nutzer sieht markierte Abschnitte (kein Volltext)
7. **Entscheidung** — lokal / anonymisieren / Freigabe / blockieren
8. **Chunking** — nach Entscheidung, nur freigegebene/anonymisierte Chunks
9. **Verarbeitung** — async, mit Fortschrittsanzeige 0–100 %
10. **Ergebnis** — mit Quellenangabe, Unsicherheitshinweis bei Extraktion
11. **Retention und Löschung** — Datei nach konfigurierbarer Frist löschen, Audit-Eintrag

---

## Stufe 13 — Kostenkontrolle

### 3-Stufen-Bremse (automatisch, keine manuelle Bestätigung nötig)

| Stufe | Schwellwert | Aktion |
|---|---|---|
| Warnung | 80 % des Budgets | Hinweis an Nutzer + Admin-Benachrichtigung |
| Downgrade | 95 % des Budgets | Automatisch auf kleinstes verfügbares Modell umschalten |
| Hard Stop | 100 % des Budgets | Keine weiteren externen Calls, nur noch lokal/Fast-Path |

### Vor jeder Ausführung

- Token schätzen (count_tokens vor Route-Entscheidung)
- Modellklasse wählen (kleinstes sicheres Modell)
- Budget prüfen (Mandant + User + globales Limit)
- Nutzer warnen bei teurer Aufgabe (> X Token = Y € — konfigurierbar)
- Hard Limit durchsetzen (kein Soft-Limit das überschritten werden kann)

### Admin-Dashboard Kosten-Sicht

- Kosten pro Mandant (Tages-/Wochen-/Monatsansicht)
- Kosten pro Provider
- Kosten pro Use-Case / Route
- Prognose bis Monatsende (linear extrapoliert)
- Top-10 teuerste Anfragen (anonymisiert)
- Vergleich Budget vs. Verbrauch

---

## Stufe 14 — EU AI Act Compliance

### Use-Case-Einstufung (Pflicht vor Gate 3)

| Kriterium | Prüfung |
|---|---|
| Risikokategorie | Minimal / Begrenzt / Hoch / Inakzeptabel |
| Betroffene Personen | Beschäftigte / Kunden / Dritte |
| Entscheidungsrelevanz | Empfehlung vs. bindende Entscheidung |
| Human Oversight | Ist ein Mensch immer final verantwortlich? |
| Transparenzpflicht | Muss erkennbar sein, dass KI im Spiel ist? |

### Anforderungen je nach Einstufung

**Minimal-Risiko (erwartet für AILIZA MVP):**
- Transparenz gegenüber Nutzern (KI erkennbar)
- Keine Weiterführung verbotener Praktiken (Art. 5 EU AI Act)
- Logging und Audit bereits erfüllt durch DSGVO-Architektur

**Begrenzt-Risiko (wenn Nutzer-Interaktion):**
- Zusätzlich: Offenlegung als KI-System in der UI
- Opt-out-Möglichkeit für Nutzer

**Hoch-Risiko (wenn HR, Kreditwürdigkeitsprüfung, o.ä.):**
- Konformitätsbewertung, CE-Kennzeichnung, Registrierung in EU-Datenbank
- (Nicht für AILIZA MVP geplant — Use Case klar abgrenzen)

---

## Stufe 15 — Betrieb & Go-live Gates

### Gate 1 — Testbetrieb (nur synthetische Daten)

Pflichtkomponenten vor Start:

- [ ] Kill-Switch implementiert und getestet
- [ ] Data Governance Layer MVP (Klassifikation + Secret-Block)
- [ ] Policy-Gateway mit Safe Defaults
- [ ] LLM-Orchestrator (kein Direktaufruf in Businesslogik)
- [ ] Metadaten-Logging (kein Inhalt)
- [ ] Datenflussinventar erstellt
- [ ] ProviderProfile-Schema
- [ ] Rate-Limit-Middleware
- [ ] Mandanten-Isolation geprüft

### Gate 2 — Pilot mit echten Daten (ein Mandant)

Zusätzlich vor Start:

- [ ] AVV/DPA mit Groq (und weiteren Providern) geprüft und unterzeichnet
- [ ] Rechtsgrundlagen-Matrix je Datenklasse und Use-Case
- [ ] Datenschutzhinweise für Nutzer (Art. 13/14 DSGVO)
- [ ] VVT-Entwurf (Verarbeitungsverzeichnis)
- [ ] DSFA-Screening (Datenschutz-Folgenabschätzung, Art. 35 DSGVO)
- [ ] Redaction implementiert und getestet
- [ ] Admin-Freigabe-Workflow vollständig
- [ ] Lösch-/Exporttest bestanden (Art. 17/20 DSGVO)
- [ ] Kostenlimits konfiguriert und getestet
- [ ] Mandantenfilter-Test (Cross-Tenant-Isolation verifiziert)
- [ ] Dokumenten-Governance vollständig

**Nachweis-Paket Gate 2:**
- AVV-Kopien
- Rechtsgrundlagen-Matrix (unterschrieben)
- VVT-Entwurf
- DSFA-Screening-Ergebnis
- Testprotokolle (Redaction, Löschung, Export, Cross-Tenant)

### Gate 3 — Produktivbetrieb (alle Mandanten)

Zusätzlich:

- [ ] RBAC vollständig (User / Manager / Admin / DSB-Rolle)
- [ ] 2FA für Admin-Zugang
- [ ] Incident-Response-Prozess geübt (Tabletop)
- [ ] Backup/Restore getestet (RTO/RPO definiert)
- [ ] AI-Literacy-Schulung für alle Nutzer abgeschlossen
- [ ] EU AI Act Use-Case-Einstufung dokumentiert
- [ ] Cross-Tenant-Test mit Penetrationstest-Qualität
- [ ] Prompt-Injection-Test (Angriffe dokumentiert und mitigiert)
- [ ] Keine kritischen Security-Findings offen
- [ ] Datenschutzhinweise live und erreichbar
- [ ] VVT finalisiert und signiert

---

## Stufe 16 — Implementierungsreihenfolge (20 Schritte)

Reihenfolge nach Sicherheitspriorität — Governance vor Features.

| # | Schritt | Phase | Gate |
|---|---|---|---|
| 1 | Datenflussinventar | P0 | vor Gate 1 |
| 2 | Data Governance Layer MVP | P0 | vor Gate 1 |
| 3 | Kill-Switch | P0 | vor Gate 1 |
| 4 | Secret-Blocker | P0 | vor Gate 1 |
| 5 | LLM-Orchestrator + Provider-Interface | P0 | vor Gate 1 |
| 6 | ProviderProfile-Schema | P0 | vor Gate 1 |
| 7 | Policy-Gateway mit Safe Defaults | P0 | vor Gate 1 |
| 8 | Redaction-Modul | P1 | vor Gate 2 |
| 9 | Metadaten-Logs (4 getrennte) | P0 | vor Gate 1 |
| 10 | Fast-Path-Router | P1 | vor Gate 2 |
| 11 | Token-Budget-Gateway | P1 | vor Gate 2 |
| 12 | Onboarding / Mandanten-Setup | P1 | vor Gate 2 |
| 13 | Freigabe-UI | P1 | vor Gate 2 |
| 14 | Dokumenten-Governance | P1 | vor Gate 2 |
| 15 | Memory-Governance (reflection_skill.py) | P1 | vor Gate 2 |
| 16 | Kosten-Dashboard | P2 | vor Gate 3 |
| 17 | Feedback-Loop UI + quality_score | P2 | vor Gate 3 |
| 18 | Streaming (erst nach Output-Guardrail stabil) | P2 | vor Gate 3 |
| 19 | Admin-Dashboard vollständig | P2 | vor Gate 3 |
| 20 | Pilot-Gate (Gate 2 abnahme) | P2 | Gate 2 → Gate 3 |

**Warum Streaming so spät?** Streaming ist UX-stark, aber erst sinnvoll wenn Output-Guardrail, Redaction und Freigabe-Logik stabil sind. Vorher ist es nur eine schnellere Möglichkeit, Fehler sichtbar zu machen.

---

## Stufe 17 — RACI-Matrix

| Aufgabe | Entwicklung | Admin | DSB | Nutzer |
|---|---|---|---|---|
| Policy-Regeln definieren | Berät | Verantwortlich | Kontrolliert | — |
| Freigaben erteilen | — | Verantwortlich | Informiert | Bestätigt |
| Memory-Fakten löschen | — | Verantwortlich | Kontrolliert | Beantragt |
| Incident melden | Verantwortlich | Informiert | Verantwortlich | Informiert |
| Rechtsgrundlage prüfen | — | Beteiligt | Verantwortlich | — |
| Gate-Freigabe | Beteiligt | Verantwortlich | Muss zustimmen | — |
| Kostenlimits setzen | — | Verantwortlich | Informiert | — |
| Audit-Logs einsehen | — | Lesen | Vollzugriff | — |

**DSB-Rolle:** Kontrollinstanz und Zustimmungspflichtig bei Gates, kein operativer Betrieb.

---

## Kurzfazit

Der vollständige AILIZA-Workflow folgt diesem Prinzip:

> **Erst Daten verstehen → klassifizieren → Zweck und Ziel prüfen →
> minimieren → Modell/Tool wählen → ausführen →
> datensparsam protokollieren → verständlich anzeigen →
> Feedback kontrolliert nutzen.**

Sicherheit, DSGVO und EU AI Act sind keine nachträglichen Anforderungen,
sondern die Architektur selbst.
