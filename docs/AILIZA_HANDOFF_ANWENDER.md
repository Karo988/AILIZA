# AILIZA — Anwender-Handoff fuer kontrolliertes Lernen

Stand: 30.08.2026

**Status:** Aktueller fachlicher Einstieg fuer persoenliches Lernen und
`user_memory`, fuer Codex und Claude Code gleichermassen.

Dieses lebende Handoff beschreibt, wie AILIZA sich fuer einen angemeldeten
Menschen weiterentwickeln soll. "Selbstlernend" bedeutet hier niemals
unkontrolliertes Beobachten oder eigenmaechtiges Training. Es bedeutet einen
sichtbaren, widerrufbaren Vorschlag-Freigabe-Lernkreislauf.

## 0. Kommunikationsregel

- Antworte im Chat kurz und leicht verstaendlich.
- Beantworte alle Fragen und pruefe die Antwort vorher anhand des belegten
  Produktstands.
- Beschreibe ein Problem knapp und biete mindestens eine konkrete Loesung an.
- Trenne deutlich: `vorhanden`, `in offenem PR`, `geplant`, `offen` und
  `gesperrt`.
- Erklaere dem Nutzer bei Memory-Aktionen kurz, was gespeichert oder verwendet
  wird und wie er es korrigieren, ablehnen oder loeschen kann.

## 1. Anwenderziel

Ein Nutzer soll AILIZA nicht in jedem Gespraech erneut erklaeren muessen:

- wer er ist und in welchem Tenant er arbeitet;
- welchen Antwortstil, welche Sprache und welches Format er bevorzugt;
- welche bestaetigten persoenlichen Fakten und Arbeitsweisen relevant sind;
- welches Projekt oder welcher Vorgang gerade fortgesetzt wird.

Der Nutzer behaelt jederzeit Kontrolle darueber, was vorgeschlagen,
gespeichert, verwendet, korrigiert, exportiert oder geloescht wird.

## 2. Verifizierter Ist-Zustand auf dem aktuellen Entwicklungsstand

Vorhanden sind:

- `user_settings` fuer Antwortlaenge, Ton, Sprache, Ausgabeformat und
  Speichermodus;
- `memory_items` mit den getrennten Scopes `user_memory` und
  `company_memory`;
- `memory_suggestions` als sichtbare Vorstufe vor dauerhaftem Lernen;
- `decide_memory_storage()` fuer blockieren, temporaer behandeln oder einen
  Memory-Vorschlag erzeugen;
- bestaetigen und ablehnen von eigenen Memory-Vorschlaegen;
- Owner- und Tenant-Filter sowie Memory-Invarianten;
- Export und Loeschung eigener Benutzerdaten;
- Chat-Anbindung, die geeignete Nutzeraussagen als Vorschlag erfassen kann.

Noch nicht als Bestandteil von `main` abgenommen:

- die persoenliche Memory-Uebersicht aus PR #114 zum Ansehen, Korrigieren und
  Loeschen einzelner Eintraege;
- eine automatische Nutzung bestaetigter `user_memory`-Eintraege in spaeteren
  Gespraechen;
- die Anbindung aller Memory-Zugriffe an den zentralen Permission-Evaluator;
- langfristige, erklaerbare Mustererkennung ueber mehrere Sitzungen.

## 3. Wichtigste aktuelle Funktionsluecke

Bestaetigte persoenliche Erinnerungen koennen gespeichert werden, werden aber
noch nicht als vollstaendig governance-gepruefter Kontext in jedes neue
Gespraech geladen. Damit ist der Lernkreislauf derzeit nur bis zum Speichern,
nicht bis zum kontrollierten Wiederverwenden geschlossen.

Diese Luecke darf erst nach dem Produktions-Memory-Audit und der zentralen
Permission-Anbindung geschlossen werden. Es darf kein eigener Nebenpfad am
Permission-Evaluator vorbei entstehen.

## 4. Zielbild des Lernkreislaufs

Die vorhandenen und fehlenden Teile dieses Zielbilds muessen weiterhin mit den
Statusangaben aus Abschnitt 2 gekennzeichnet werden:

1. AILIZA erkennt eine moeglicherweise wiederverwendbare Information.
2. Governance klassifiziert den Inhalt vor jeder Speicherung.
3. Der Speichermodus des Nutzers entscheidet, ob nichts geschieht, nachgefragt
   oder ein sichtbarer Vorschlag angelegt wird.
4. Der Nutzer bestaetigt, korrigiert oder verwirft den Vorschlag.
5. Nur eine gueltige Bestaetigung erzeugt dauerhaftes `user_memory`.
6. Bei spaeteren Gespraechen werden nur eigene, aktive, nicht abgelaufene und
   fuer den Zweck relevante Eintraege ueber den Permission-Evaluator geladen.
7. Vor externer Modellnutzung durchlaufen geladene Erinnerungen erneut Kill-
   Switch, Data Governance, Policy, Redaction und Providerfreigabe.
8. Die Oberflaeche zeigt, welche Erinnerungen fuer die Antwort verwendet
   wurden und erlaubt Korrektur oder Loeschung.
9. Jede Speicherung, Nutzung, Korrektur und Loeschung erzeugt minimierte
   Audit-Metadaten ohne den Memory-Inhalt.

## 5. Unveraenderliche Governance-Grenzen

- Kein stilles oder verdecktes Lernen.
- Kein Training eines Modells mit Nutzerdaten durch diesen Lernkreislauf.
- Kein fremdes `user_memory`, auch nicht fuer Manager oder Administratoren.
- Kein `company_memory` im persoenlichen Nutzerkreislauf.
- Kein neuer Memory-Eintrag ohne Tenant, Zweck, Quelle, Status und
  Aufbewahrungsregel.
- Secrets, Zugangsdaten und verbotene Datenklassen werden nicht automatisch
  gespeichert oder geladen.
- Nutzerkorrekturen ersetzen keine Historie heimlich; Aenderung und Quelle
  bleiben nachvollziehbar.
- Loeschung oder Widerruf stoppt kuenftige Verwendung.
- Externe Anbieter sehen nur Inhalte, die nach Klassifikation, Freigabe und
  Redaction uebertragen werden duerfen.

## 6. Reifestufen der Weiterentwicklung

### Stufe A — Sichtbarkeit

- PR #114 pruefen und genau eine Memory-Uebersicht mergen.
- Eigene Eintraege anzeigen, korrigieren und loeschen.
- Quelle, Zweck, Ablaufdatum und Status verstaendlich anzeigen.

### Stufe B — zentrale Berechtigung

- Produktions-Memory-Audit mit Exit 0 abschliessen.
- Lesen, Speichern, Aendern und Loeschen an den Permission-Evaluator anbinden.
- Cross-Tenant-, Owner-, Rollen-, Race- und Rollback-Tests bestehen.

### Stufe C — kontrolliertes Erinnern

- Nur relevante eigene Erinnerungen fuer ein Gespraech auswaehlen.
- Verwendung in der Oberflaeche sichtbar machen.
- Governance vor jeder Modelluebertragung erneut anwenden.
- Nutzer kann eine Erinnerung fuer den aktuellen Turn ausblenden.

### Stufe D — erklaerbares Lernen aus Wiederholungen

- Wiederkehrende Muster erzeugen nur einen neuen Vorschlag, nie direkt Memory.
- Vorschlag nennt Belege, Zweck, erwarteten Nutzen und Aufbewahrungsdauer.
- Widerspruechliche Beobachtungen fuehren zu Rueckfrage statt Ueberschreiben.
- Nutzer kann Muster bestaetigen, korrigieren, pausieren oder dauerhaft
  ablehnen.

### Stufe E — persoenlicher Arbeitsassistent

- Projektkontext und bestaetigte Praeferenzen werden zweckgebunden kombiniert.
- AILIZA erklaert, welche Erinnerung eine Empfehlung beeinflusst hat.
- Qualitaet wird mit Nutzerfeedback bewertet, ohne verdeckte Profilbildung.
- Neue Automatisierung bleibt bis zu separater Freigabe im Vorschlagsmodus.

## 7. Erfolgskriterien aus Anwendersicht

Der Lernkreislauf ist erst fertig, wenn ein Nutzer:

- sehen kann, was AILIZA ueber ihn weiss;
- versteht, warum etwas vorgeschlagen oder verwendet wurde;
- einen Vorschlag vor Speicherung korrigieren kann;
- eine Erinnerung fuer eine einzelne Antwort oder dauerhaft deaktivieren kann;
- seine Daten exportieren und loeschen kann;
- nach einer Loeschung nachweislich keine weitere Verwendung erlebt;
- niemals Daten eines anderen Nutzers oder Tenants sieht.

## 8. Naechster erlaubter Schritt

Zuerst PR #114 gegen konkurrierende Memory-Uebersichten und die aktuellen
Owner-/Tenant-Regeln pruefen. Danach Produktions-Memory-Audit ausfuehren. Erst
nach dokumentiertem Exit 0 darf Stufe B umgesetzt werden. Stufe C beginnt erst,
wenn Stufe B einschliesslich negativer Sicherheitstests abgenommen ist.

## 9. Offene Produktentscheidungen

Vor Stufe C muessen mindestens diese Fragen ausdruecklich entschieden werden:

- Wie viele Erinnerungen duerfen pro Antwort geladen werden?
- Nach welchen belegbaren Kriterien wird Relevanz bestimmt?
- Wie sieht der Nutzer, welche Erinnerung verwendet wurde?
- Welche Standard-Aufbewahrungsdauer gilt je Memory-Art?
- Was geschieht bei widerspruechlichen oder veralteten Erinnerungen?
- Darf eine Erinnerung nur lokal oder nach erneuter Governance auch bei einem
  freigegebenen externen Anbieter verwendet werden?
- Wie kann ein Nutzer Lernen insgesamt pausieren und vorhandene Erinnerungen
  fuer einen einzelnen Turn ausblenden?

Bis zur Entscheidung gilt jeweils fail-closed: keine neue automatische
Verwendung und keine stillschweigende Standardannahme.

## 10. Nicht-Ziele

- Kein eigenstaendiges Modelltraining mit Nutzerinhalten.
- Keine verdeckte Persoenlichkeits- oder Leistungsbewertung.
- Keine automatische Ausweitung von `user_memory` zu `company_memory`.
- Keine autonomen Entscheidungen mit rechtlicher, personeller oder
  finanzieller Wirkung.
- Keine Behauptung, AILIZA habe etwas gelernt, solange es nur vorgeschlagen
  oder noch nicht fuer spaetere Gespraeche nutzbar ist.

## 11. Abnahmekriterien je Reifestufe

- Nutzerkontrolle ist in der Oberflaeche sichtbar und verstaendlich.
- Owner- und Tenant-Isolation besitzen negative Tests.
- Speicherung und Verwendung sind zweckgebunden und widerrufbar.
- Audit enthaelt nur notwendige Metadaten, niemals den Memory-Inhalt.
- Loeschung verhindert nachweislich die kuenftige Verwendung.
- Fehler fallen sicher aus und erzeugen keine stille Speicherung.
- Ist-Zustand, offener PR und Zukunftsvorschlag sind im Handoff getrennt.

## 12. Pflege dieses Handoffs

Jede Aktualisierung nennt den belegenden PR/Commit oder die ausdrueckliche
Owner-Entscheidung. Ein offener PR wird nie als Bestandteil von `main`
beschrieben. Entfernte oder ersetzte Funktionen werden nicht still aus dem
Dokument geloescht, sondern im zugehoerigen PR begruendet.

## 13. Statuskapsel fuer jede Memory-Weiterentwicklung

```text
ANWENDER-MEMORY-STATUS
Reifestufe:
Verifizierter Ist-Zustand:
Neu umgesetzt:
Sichtbare Nutzerkontrolle:
Permission-/Tenant-Nachweis:
Governance-/Audit-Nachweis:
Tests:
Offene Risiken:
Naechster erlaubter Schritt:
```

Dieses Dokument wird nur aktualisiert, wenn Code, Tests oder eine ausdruecklich
dokumentierte Produktentscheidung den Stand tatsaechlich veraendern.
