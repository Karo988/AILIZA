# AILIZA — Architektur-Review + Reparaturplan (Prompt für Fable)

> Status dieses Dokuments: Arbeitsauftrag für eine Analyse- und Reparatur-Session,
> kein Freigabe-Nachweis. Ergebnisse aus dieser Session ersetzen keine juristische
> Prüfung.

---

## Rolle

Du bist Senior AI Architect, Security Reviewer und DSGVO-/EU-AI-Act-orientierter
Compliance-Prüfer.

## Ziel

Prüfe AILIZA fachlich, technisch und compliance-orientiert. **AILIZA ist nicht das
Modell selbst, sondern die Anwendungsschicht um externe Modelle herum.** AILIZA soll
für KMU in Europa nutzbar sein und Datenminimierung, Transparenz, menschliche
Kontrolle und nachvollziehbare Modellnutzung sicherstellen.

### Wichtige Trennung (nicht verhandelbar)

- **AILIZA** = Anwendung, Policy Engine, Redaction, Audit, Human Review, UI/Workflow.
- **Externes Modell** (Fable / Claude / Groq / etc.) = austauschbarer Modellanbieter
  hinter einer Abstraktionsschicht.
- Der System-Prompt des Modells darf **nicht behaupten, das Modell sei AILIZA**. Der
  korrekte Rahmen lautet: *"Du bist das Antwortmodell innerhalb von AILIZA"* — nicht
  *"Du bist AILIZA"*. AILIZA ist die Governance-Schicht, die vor und nach dem
  Modellaufruf greift; das Modell ist austauschbar.

---

## Auftrag

### 1. Bestandsaufnahme (zuerst lesen, nicht ändern)

Lies die vorhandene Architektur, Prompts, API-Aufrufe, Redaction-Logik,
Policy-Entscheidungen, Logging, Memory, Tool-Nutzung und Modellrouten. Erstelle eine
Bestandsaufnahme:

- Welche Daten gehen wohin? (Request → Redaction → Policy → Modell → Response →
  Reinsertion → Storage)
- Welche personenbezogenen oder sensiblen Daten können verarbeitet werden?
- Welche externen Anbieter werden genutzt (Modell-APIs, Suchdienste, etc.)?
- Was wird gespeichert — wo, wie lange, geschwärzt oder im Klartext?
- Wo gibt es menschliche Freigaben (Human Review / Approval Gates), und wo fehlen sie?
- Wo laufen aktuell **zwei parallele Redaction-Pfade** (Altsystem vs. neues System) —
  bekanntes Risiko: ein Pfad kann den anderen überschreiben, ohne dass es auffällt.

### 2. Prüfung gegen Leitplanken

**DSGVO:**
- Datenminimierung, Zweckbindung, Rechtsgrundlage (Art. 6)
- Art. 9-Daten (besondere Kategorien) — siehe Korrektur unten, **nicht pauschal
  "absolut blockieren"** formulieren
- Art. 22-Entscheidungen (automatisierte Einzelfallentscheidungen)
- Auftragsverarbeitung (Art. 28 — DPA mit Modellanbieter vorhanden/geprüft?)
- Löschkonzept / Speicherbegrenzung (Art. 5 Abs. 1 lit. e)
- Transparenz- und Informationspflichten (Art. 13/14)

**EU AI Act:**
- Einordnung **pro Use Case**, nicht pauschal über einen einzigen Artikel definiert.
  Hochrisiko hängt vom konkreten Anwendungsfall ab: HR/Beschäftigung, Kreditwürdigkeit,
  Versicherung, Bildung, Gesundheit, kritische Infrastruktur, Strafverfolgung,
  Migration/Asyl, Rechtspflege.
- Menschliche Aufsicht (Human Oversight, Art. 14) ist notwendig, **ersetzt aber nicht
  automatisch alle weiteren Pflichten** (Risikomanagement, Dokumentation,
  Transparenzpflichten Art. 52/50, Logging-Pflichten für Hochrisiko-Systeme).

**Security:**
- Secrets, Tokens, API-Keys in Logs/Prompts/Audit-Trails
- Externe Datenabflüsse (welche Felder verlassen die Infrastruktur wirklich?)
- Prompt Injection (Erkennung, Umgang, Eskalation)
- Tool-Missbrauch (z. B. Such-Tools, die ungefilterte Anfragen weiterreichen)
- Unsichere Defaults (fail-open statt fail-closed bei Klassifizierungsfehlern?)

### 3. Klare Kennzeichnung der Befunde

Markiere durchgängig, woher eine Aussage kommt:

- **Beleg aus dem Code** (mit Datei:Zeile)
- **Annahme** (nicht im Code verifiziert — explizit als Annahme kennzeichnen)
- **Compliance-Risiko**
- **Technisches Risiko**
- **Offene Frage** (braucht menschliche/juristische Entscheidung)

### 4. Priorisierter Reparaturplan vor Umsetzung

**Nicht blind reparieren.** Erst einen priorisierten Plan vorschlagen (Kritisch /
Hoch / Mittel / Niedrig), mit Begründung, bevor Code geändert wird.

### 5. Wenn Code geändert wird

- Nur kleine, nachvollziehbare Patches.
- Keine unnötigen Refactorings.
- Keine neuen externen Datenflüsse ohne Begründung.
- Keine Speicherung ungeschwärzter personenbezogener Daten.
- Keine Secrets in Logs, Prompts oder Audit-Trails.
- Jede Änderung muss einem konkreten Punkt aus dem Reparaturplan zuordenbar sein.

### 6. Mindestens bauen/verbessern

- Redaction **vor** jedem Modellaufruf (ein einziger, konsistenter Pfad — kein
  Altsystem parallel, das die neue Schwärzung überschreibt)
- Policy Engine vor Modellaufruf
- Human Review bei riskanten Entscheidungen (use-case-abhängig, nicht nur bei Art. 22)
- Transparenzhinweis bei externer KI-Nutzung (Nutzer sieht: "Antwort wurde von
  [Anbieter] als Modell hinter AILIZA erzeugt")
- Auditierbare, aber datensparsame Protokollierung (keine Klartext-PII im Log)
- Modellanbieter-Abstraktion (Modell austauschbar, ohne dass Governance-Schicht
  angefasst werden muss)
- Tests für: Redaction, Blocking, Human Review, sichere Modellaufrufe,
  Art. 9-Handling, Konsistenz zwischen allen Redaction-Pfaden

---

## Korrekturen gegenüber einer naiven Erstfassung

1. **AILIZA/Modell sauber trennen.** Modellprompt: *"Du bist das Antwortmodell
   innerhalb von AILIZA"*, nicht *"Du bist AILIZA"*.

2. **Art. 9 nicht pauschal "absolut blockieren".** Praktisch ist ein konservativer
   Default richtig (blockieren/schwärzen), aber rechtlich existieren Ausnahmen
   (Art. 9 Abs. 2 DSGVO — z. B. ausdrückliche Einwilligung, Arbeitsrecht in bestimmten
   Fällen). Für AILIZA als KMU-Assistent: **Default = blockieren/schwärzen; Verarbeitung
   nur nach expliziter Policy-Freigabe in stark minimierter Form, nachvollziehbar
   dokumentiert.**

3. **High-Risk nicht nur über Art. 22 definieren.** EU-AI-Act-Hochrisiko hängt vom
   konkreten Use Case ab (siehe Liste oben). Menschliche Prüfung ist notwendig,
   ersetzt aber nicht automatisch alle weiteren Pflichten (Risikomanagement,
   Dokumentation, Logging, Transparenz).

---

## Ergebnisformat (verbindlich)

1. **Kurzfazit**
2. **Architekturdiagnose**
3. **Kritische Risiken**
4. **DSGVO-/AI-Act-Bewertung**
5. **Konkrete Reparaturmaßnahmen** (priorisiert: Kritisch/Hoch/Mittel/Niedrig)
6. **Patch-Vorschläge oder geänderte Dateien**
7. **Tests und Akzeptanzkriterien**
8. **Offene Fragen**, die vor Produktivbetrieb geklärt werden müssen

---

## Sprachregel (verbindlich für alle Aussagen zu Compliance-Status)

Erfinde keine rechtliche Freigabe. Stelle **nicht** fest, dass AILIZA
"DSGVO-konform" oder "AI-Act-konform" ist, wenn dafür keine vollständige juristische
Prüfung vorliegt. Verwende stattdessen:

- "DSGVO-orientiert"
- "AI-Act-orientiert"
- "prüfungsfähig vorbereitet"

---

## Kontext für diese Session (Stand aus laufender Entwicklung)

- Branch: `claude/adoring-lamport-c1zs8h` (divergiert von `main` — Render deployt
  vermutlich `main`, das ist ein offener technischer Punkt, unabhängig von diesem
  Review zu klären).
- Bekanntes, bereits identifiziertes Risiko: `_governance_pre_check()` in
  `apps/backend/main.py` rief ursprünglich die alte `governance/redaction.py` auf und
  überschrieb damit die Ausgabe der neuen `governance/redaction_v2.py`
  (`RedactionEngineV2`). Das wurde in einem separaten Commit bereits behoben — bei der
  Bestandsaufnahme bitte verifizieren, dass es **keinen weiteren** solchen doppelten
  Pfad gibt (z. B. im Frontend, in `/api/policy-check` vs. `/api/policy-redact`, oder
  in `/agent/run` an anderer Stelle).
- Zwei sichtbare, bewusst beizubehaltende UI-Elemente: die doppelte Leiste
  (Eingabe + sichtbare LLM-Vorschau) und die rechtsseitigen PII-Blasen
  (Privacy-Memory-Panel). Diese UI-Bausteine sollen erhalten bleiben; der Auftrag
  betrifft die Governance-/Redaction-/Policy-Logik dahinter, nicht deren Ersatz.
