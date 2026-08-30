# AILIZA — Entwicklungs-Handoff

Stand: 30.08.2026

**Status:** Aktueller Einstieg fuer neue Entwicklungs-Tasks, fuer Codex
(`AGENTS.md`) und Claude Code (`CLAUDE.md`) gleichermassen.

Dieses Dokument beschreibt den verifizierten Arbeitsstand, die Reihenfolge,
offene Entscheidungen und Sperren. Historische Handovers werden nur bei einem
konkreten Bedarf gelesen.

## 0. Kommunikationsregel

- Antworte im Chat kurz und leicht verstaendlich.
- Beantworte alle gestellten Fragen und pruefe die Antwort vorher anhand der
  verfuegbaren Fakten.
- Beschreibe Probleme knapp und biete mindestens eine konkrete Loesung an.
- Sage klar `nicht verfuegbar` oder `offene Entscheidung`, statt zu raten.
- Kuerze nie notwendige Sicherheitswarnungen, Abnahmekriterien oder
  Begründungen weg.

## 1. Produktstatus

AILIZA ist lokal technisch abgenommen, aber noch nicht fuer den echten
Produktionsbetrieb freigegeben. Der unveraenderte lokale Checkout bestand am
30.08.2026 die vollstaendige Suite mit 2325 bestandenen und 14 uebersprungenen
Tests. Fuer Windows war ein beschreibbarer pytest-Tempordner erforderlich.

Der alte Groq-Key ist widerrufen und wird nicht weiter bearbeitet. Der neue
Key liegt als geschuetzte Render-Umgebungsvariable vor. Keine
History-Neuschreibung und keine Branch-Loeschung allein wegen des alten Keys.

## 2. Verbindlicher Kernpfad

1. PR #109, #110, #111 und #112 nacheinander mergen; nach jedem Merge CI
   abwarten.
2. PR #114 separat pruefen und mergen; konkurrierende Memory-Uebersichten nicht
   doppelt uebernehmen.
3. PR #87 auf Ueberholung durch spaetere Memory-Arbeit pruefen. Fuer PR #106
   und #107 ist noch offen, ob sie zum Produktions-Kernpfad oder zu einer
   spaeteren Ausbaustufe gehoeren.
4. Audit-Ereignisse vereinheitlichen und vervollstaendigen.
5. Admin-Freigabeoberflaeche fuer die vorhandene `/approvals`-API bauen.
6. Dokumentation konsolidieren.
7. Produktions-Memory-Audit gegen die echte Datenbank ausfuehren.
8. Erst nach dokumentiertem Audit-Exit 0 den Memory-Kern an den zentralen
   Permission-Evaluator anbinden.
9. TLS, CORS, externer Backupbetrieb, Monitoring, Wiederherstellungstest und
   geschaeftliche Abnahme abschliessen.

## 3. Verifizierte technische Tatsachen

- Die Freigabe-API liegt unter `/approvals`, nicht unter `/admin/approvals`.
- `user_memory` und `company_memory` bleiben strikt getrennte Scopes.
- Der fachliche Memory-Kern liegt in `memory_items`, `memory_sources`,
  `memory_visibility` und `memory_suggestions`; `apps/backend/memory/` ist ein
  quarantinisierter technischer Prototyp.
- Neue externe Provider oder Tools bleiben bis zu dokumentierter Freigabe
  fail-closed.

## 4. Offene Entscheidungen — nicht eigenmaechtig festlegen

- Audit-Vokabular: Spezifikation nennt `approval.granted`, aktueller Code
  verwendet teilweise `approval.approved`. Der verbindliche Name ist noch zu
  entscheiden.
- PR #106 und #107: Kernpfad oder spaetere Ausbaustufe.
- Dokumentationsautoritaet: welche Datei beziehungsweise Dokumentengruppe die
  verbindliche Regelquelle ist.
- Dokumentationsbaum: Root-Ordner `00_masterplan/` bis `06_release/` oder eine
  konsolidierte Struktur unter `docs/`.

Bis zur Entscheidung werden Vorschlaege als Vorschlaege markiert. Technische
Widersprueche werden mit Datei- oder Testbeleg gemeldet.

## 5. Produktionssperren

Keine Produktionsfreigabe ohne folgende Nachweise:

- echte Domain mit TLS, Redirect und HSTS;
- konkrete CORS-Origins, keine Produktions-Wildcard;
- erfolgreicher Produktions-Memory-Audit;
- externes verschluesseltes Backup mit Zeitplan, Alarmierung und Aufbewahrung;
- dokumentierter Restore-Test mit RPO/RTO;
- Monitoring, Notfallplan und benannte Verantwortliche;
- gepruefte AVV/DPA der aktivierten Anbieter;
- formale Produktionsabnahme mit deploytem Commit und Migrationsstand.

## 6. Kontextarme Arbeitsweise

Ein neuer Task liest zuerst nur:

1. `AGENTS.md` (Codex) beziehungsweise `CLAUDE.md` (Claude Code);
2. dieses Handoff;
3. Ziel und Diff des aktuellen Arbeitspakets;
4. maximal fuenf primaere Dateien und die zugehoerigen Zieltests.

Erst bei einer belegten Informationsluecke duerfen weitere Dokumente geladen
werden. `docs/archiv/`, alte Chats und historische Statusberichte werden nicht
vorsorglich gelesen. Es gilt ein Arbeitspaket pro Task und ein kleiner,
verifizierbarer PR pro Paket.

## 7. Umgang mit widerspruechlichen Quellen

Die verbindliche Regelquelle und der endgueltige Dokumentationsbaum sind noch
offen. Deshalb gilt bis zur Entscheidung:

- Code und gruene Tests belegen den technischen Ist-Zustand, entscheiden aber
  keine offene Produkt- oder Governance-Frage.
- Bei widerspruechlichen fachlichen Regeln nicht selbst auswaehlen, sondern den
  Konflikt kurz mit beiden Fundstellen melden und eine Loesung empfehlen.
- `docs/AGENT_HANDOFF_BLOCK_C1_ABGESCHLOSSEN.md` und
  `docs/HANDOFF_DATENBANK_GEDAECHTNIS.md` sind historische Detailstaende, keine
  aktuellen Startdokumente.

## 8. Abnahmekriterien fuer jeden Entwicklungs-Task

- Ziel und Nicht-Ziele sind klar.
- Betroffene Dateien und Risiken sind genannt.
- Relevante Tests sind gruen oder der Blocker ist belegt.
- Keine unbestaetigte Empfehlung wird als Entscheidung dokumentiert.
- Dokumentation und Code behaupten denselben umgesetzten Stand.
- Der naechste Schritt ist konkret ausfuehrbar.

## 9. Pflichtabschluss eines Entwicklungs-Tasks

```text
AILIZA-STATUSKAPSEL
Ziel:
Ergebnis:
Branch/Commit:
Geaenderte Kerndateien:
Tests mit Ergebnis:
Offene Risiken oder Entscheidungen:
Naechster exakt ausfuehrbarer Schritt:
Nicht bearbeitet:
```

Die Kapsel bleibt maximal zwoelf kurze Zeilen. Ein Folgetask erhaelt diese
Kapsel und den PR-/Commit-Link statt des gesamten alten Chats.

## 10. Pflege und Verantwortlichkeit

Dieses Handoff wird nur geaendert, wenn ein Merge, ein Testnachweis oder eine
ausdrueckliche Owner-Entscheidung den Stand veraendert. Jede Aktualisierung
nennt Datum, Beleg und offene Folgearbeit. Historische Details werden nicht
hier angehaeuft.

## 11. Merge-Checkliste fuer dieses Handoff-Paket

Diese Dateien muessen gemeinsam im selben PR enthalten sein:

- `AGENTS.md`;
- `README.md`;
- `05_prompts/CODEX_TOKEN_KONTEXT_STATUS_PROMPT.md`;
- `05_prompts/CLAUDE_TOKEN_KONTEXT_STATUS_PROMPT.md`;
- `docs/AILIZA_HANDOFF_ENTWICKLUNG.md`;
- `docs/AILIZA_HANDOFF_ANWENDER.md`;
- die historischen Hinweise in
  `docs/AGENT_HANDOFF_BLOCK_C1_ABGESCHLOSSEN.md` und
  `docs/HANDOFF_DATENBANK_GEDAECHTNIS.md`;
- die Ergaenzung in `CLAUDE.md` (Pflichtstart-Verweis auf beide Handoffs).

Vor Merge pruefen:

- alle relativen Dateiverweise existieren im PR;
- `git diff --check` ist sauber;
- keine offene Entscheidung wird als beschlossen bezeichnet;
- ein frischer Checkout kann dem Startprompt ohne lokale Zusatzdatei folgen;
- der PR enthaelt keine Produktcode-Aenderung und keinen Secret-Wert.

## 12. Startprompt fuer Codex

```text
Arbeite am Projekt AILIZA. Lies zuerst `AGENTS.md` und danach ausschliesslich
`docs/AILIZA_HANDOFF_ENTWICKLUNG.md`. Pruefe Branch, origin/main, den betroffenen
Diff und nur die fuer dieses Arbeitspaket notwendigen Dateien und Tests:

ARBEITSPAKET: [genau ein Ziel]

Arbeite kontextsparend, implementiere den kleinsten sicheren Schnitt, gib keine
Secrets aus und ende mit der AILIZA-STATUSKAPSEL.
```

## 13. Startprompt fuer Claude Code

```text
Arbeite am Projekt AILIZA. Lies zuerst `CLAUDE.md` und danach ausschliesslich
`docs/AILIZA_HANDOFF_ENTWICKLUNG.md`. Pruefe Branch, origin/main, den betroffenen
Diff, offene PRs zum selben Thema (Ein-Agent-Regel bei Governance-/Memory-Code)
und nur die fuer dieses Arbeitspaket notwendigen Dateien und Tests. `main.py`,
`index.html` und `database.py` nie vollstaendig lesen -- grep/rg zuerst, dann
gezielt mit Offset/Limit.

ARBEITSPAKET: [genau ein Ziel]

Freigabe-Modell: rein lesend ohne Rueckfrage, Aenderungen mit kurzer
Ankuendigung (WAS/WARUM) und Warten auf OK -- einmal pro Paket, nicht pro
Datei. Keine Entscheidung aus Abschnitt 4 selbst treffen. Kleinsten sicheren
Schnitt umsetzen, angemessen testen (Pflicht-Subagenten je nach Bereich
beachten), keine Secrets ausgeben, mit der AILIZA-STATUSKAPSEL enden.
```
