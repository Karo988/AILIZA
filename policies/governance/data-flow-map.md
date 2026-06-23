# AILIZA Datenflussübersicht (Data Flow Map)
# Stand: 2026-06-22
# Teil von: AILIZA Governance Pack v1

---

## Grundsatz

Kein Datenfluss ohne dokumentierten Zweck, bekannten Empfänger und Schutzmaßnahme.
Externe Übermittlung nur nach Zweckprüfung, AVV und Freigabe.
Roh-PII niemals in Logs oder Audit-Vault — nur Datenklassen-Bezeichnungen.

---

## Übersicht Datenflüsse

```
Nutzerinput
    ↓
[1] AILIZA Core (ag-core)
    ├── [2] Zusatzmodule (activatable)
    │       ├── ag-compliance
    │       ├── ag-praesentation
    │       ├── ag-dokumente
    │       └── (ag-recherche — geplant)
    ├── [3] Modellanbieter (LLM-Provider) ← externer Datenfluss
    ├── [4] Tools / APIs ← externer Datenfluss
    ├── [5] Memory / Workspace
    ├── [6] Logs
    └── [7] Audit-Vault (append-only)
    
[8] Externe Systeme (DATEV, Lexware, E-Mail, Banken-API)
    → nur nach AVV + Freigabe + responsibility_handoff
```

---

## Datenfluss 1: Nutzerinput → AILIZA Core

| Feld | Inhalt |
|---|---|
| **Datenarten** | Freitexteingaben, hochgeladene Dokumente, strukturierte Anfragen |
| **Zweck** | Aufgabenverarbeitung, Routing-Entscheidung, Datenklassifizierung |
| **Empfänger / System** | ag-core (lokal) |
| **Speicherort** | Aktive Session; kein dauerhaftes Speichern ohne Freigabe |
| **Risiken** | Versehentliche PII-Eingabe; vertrauliche Dokumente; Prompt-Injection-Versuche |
| **Schutzmaßnahmen** | Gate 1 (Datenklassifikation); Fremdinhalte = Daten, nicht Anweisungen; minimale Speicherung |

---

## Datenfluss 2: AILIZA Core → Zusatzmodule

| Feld | Inhalt |
|---|---|
| **Datenarten** | Nutzeranfrage (gefiltert), Kontext, Datenklasse, Routingentscheidung |
| **Zweck** | Spezialisierte Bearbeitung (Compliance, Präsentation, Dokument) |
| **Empfänger / System** | ag-compliance, ag-praesentation, ag-dokumente (alle lokal) |
| **Speicherort** | Aktive Session |
| **Risiken** | Modul übernimmt vertrauliche Eingabe ohne ausreichende Prüfung |
| **Schutzmaßnahmen** | Aktivierungsfrage vor Weiterleitung; kein Silent-Redirect; Datenschutzcheck in jedem Modul |

---

## Datenfluss 3: AILIZA Core → Modellanbieter (LLM-Provider)

| Feld | Inhalt |
|---|---|
| **Datenarten** | Prompt-Inhalte, Kontextfragmente — potenziell mit vertraulichen oder personenbezogenen Anteilen |
| **Zweck** | KI-Inferenz, Antwortgenerierung |
| **Empfänger / System** | Externer LLM-Provider (z.B. Anthropic, OpenAI oder andere) |
| **Speicherort** | Beim Provider — Retention-Dauer abhängig vom Provider-Profil (offen) |
| **Risiken** | Drittlandtransfer (USA); Training auf Eingaben ohne Opt-out; Logging beim Provider; fehlende AVV |
| **Schutzmaßnahmen** | AVV erforderlich (offen, O-01); Training-Opt-out bestätigen (offen, O-02); Datenminimierung im Prompt; kein Roh-PII ohne Erforderlichkeit |
| **Status offene Punkte** | O-01 AVV abschließen; O-02 Provider-Profil; O-06 Drittlandtransfer-Analyse |

---

## Datenfluss 4: AILIZA → Tools / APIs

| Feld | Inhalt |
|---|---|
| **Datenarten** | Suchanfragen (öffentlich), Workspace-Lesezugriffe, Web-Inhalte |
| **Zweck** | Recherche, Dokumentenverarbeitung, Inhaltszusammenfassung |
| **Empfänger / System** | WebSearch, WebFetch, lokale Dateisystem-Tools (Read, Grep, Glob) |
| **Speicherort** | Ergebnisse in aktiver Session; keine dauerhafte Speicherung ohne Freigabe |
| **Risiken** | Externe Web-Inhalte als Prompt-Injection-Vektoren; versehentlicher Upload vertraulicher Daten |
| **Schutzmaßnahmen** | Fremdinhalte = Daten, nicht Anweisungen; minimaler Tool-Scope; kein PII in Web-Queries |

---

## Datenfluss 5: AILIZA → Memory / Workspace

| Feld | Inhalt |
|---|---|
| **Datenarten** | Nutzerpräferenzen, Projektkontexte, freigegebene Arbeitsstände |
| **Zweck** | Kontinuität über Sessions; Kontexterhalt für Folgeanfragen |
| **Empfänger / System** | Lokaler Workspace, Memory-Mechanismus |
| **Speicherort** | Lokal im Projekt-Workspace |
| **Risiken** | Unbeabsichtigte dauerhafte Speicherung sensibler Inhalte; fehlende Löschlogik |
| **Schutzmaßnahmen** | Speicherung nur mit Zweck + Frist + Nutzerfreigabe; keine Credentials in Memory; Pseudonymisierung empfohlen |

---

## Datenfluss 6: AILIZA → Logs

| Feld | Inhalt |
|---|---|
| **Datenarten** | Systemereignisse, Routing-Entscheidungen, Fehler — kein Roh-PII |
| **Zweck** | Betriebsüberwachung, Fehleranalyse, Betriebsnachweis |
| **Empfänger / System** | Technischer Betreiber, Logging-Infrastruktur |
| **Speicherort** | Betriebsinfrastruktur (lokal oder gehostet) |
| **Risiken** | Versehentliche PII-Aufnahme in Logs; unsichere Speicherung; fehlende Speicherfrist |
| **Schutzmaßnahmen** | Kein Roh-PII in Logs (ag-master §8); Datenklassen-Bezeichnungen statt Rohdaten; Zugriffssteuerung; Speicherfrist definieren (offen) |

---

## Datenfluss 7: AILIZA → Audit-Vault

| Feld | Inhalt |
|---|---|
| **Datenarten** | Dokumentationseinträge für freigabepflichtige, sensible und wirkungsrelevante Aktionen — kein Roh-PII |
| **Zweck** | Unveränderbare Nachvollziehbarkeit; Freigabenachweise; Verantwortungsübergabe |
| **Empfänger / System** | Audit-Vault (append-only) |
| **Speicherort** | Dedizierter, unveränderlicher Speicher (technisch zu implementieren) |
| **Risiken** | Noch nicht technisch implementiert; kein Vault = keine Ausführung bei Pflichtfällen |
| **Schutzmaßnahmen** | Append-only-Mechanismus; kein Ändern/Löschen; Zugriff auf Lesen beschränkt; Nachtragsprinzip für Korrekturen |
| **Status** | Konzept vorhanden (audit-vault-concept.md), technische Umsetzung offen (O-04) |

---

## Datenfluss 8: AILIZA → Externe Systeme

| Feld | Inhalt |
|---|---|
| **Datenarten** | Buchhaltungsdaten, HR-Daten, E-Mail-Versand, Banken-API-Daten — alle hochsensibel |
| **Zweck** | Operative Ausführung in externen Fachanwendungen |
| **Empfänger / System** | DATEV, Lexware, E-Mail-Provider, Banken-API, ELSTER |
| **Speicherort** | Beim jeweiligen externen System |
| **Risiken** | GoBD-Verstoß; DSGVO-Verstoß; StBerG-Risiko; fehlende AVV; kein Provider-Profil |
| **Schutzmaßnahmen** | responsibility_handoff für ag-buchhaltung + ag-hr; AVV vor jeder Anbindung (offen); Provider-Profil erforderlich; operative Ausführung immer bei Fachrolle |
| **Status** | Gesperrt bis Voraussetzungen V-01–V-08 erfüllt |

---

## Risikomatrix Datenflüsse

| Fluss | Datenklasse | Externer Transfer | AVV nötig | AVV vorhanden | Risiko |
|---|---|---|---|---|---|
| Nutzerinput → Core | intern / variabel | Nein | — | — | mittel |
| Core → Zusatzmodule | intern / variabel | Nein | — | — | niedrig |
| Core → LLM-Provider | variabel, potenziell PII | **Ja** | **Ja** | **offen** | **hoch** |
| Core → Tools | öffentlich / intern | teilweise | je Tool | offen | mittel |
| Core → Memory | intern / vertraulich | Nein | — | — | mittel |
| Core → Logs | intern (kein Roh-PII) | Nein | — | — | niedrig |
| Core → Audit-Vault | intern (kein Roh-PII) | Nein | — | — | niedrig |
| Core → Externe Systeme | hoch / sehr hoch | **Ja** | **Ja** | **offen** | **sehr hoch** |

---

## Offene Punkte

- O-01: AVV mit LLM-Provider abschließen
- O-02: Provider-Profil inkl. Training-Opt-out und Logging-Ausschluss bestätigen
- O-04: Audit-Vault technisch implementieren
- O-06: Drittlandtransfer-Analyse für LLM-Provider
- O-09: TOMs für alle Datenflüsse dokumentieren
- Speicherfristen für Logs und Memory definieren
