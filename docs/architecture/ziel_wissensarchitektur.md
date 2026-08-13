# Zielarchitektur: Intelligente AILIZA-Wissensdatenbank

Status: **Zielbild, noch nicht umgesetzt.** Dieses Dokument fixiert das fachliche
Zielbild für den Ausbau von AILIZA zum "perfekten KMU-Agenten" sowie den
Ist-Vergleich mit dem aktuellen Datenbankstand (`apps/backend/db_schema.py`)
und den geplanten Umsetzungs-Phasenplan. Es beschreibt eine Zielrichtung,
keinen bereits implementierten Zustand.

## Gesamtbild der intelligenten AILIZA-Datenbank

Die AILIZA-Datenbank soll nicht nur Informationen speichern. Sie soll
Unternehmenswissen **verstehen, absichern, prüfen, verbinden, aktuell
halten und mit Quellen belegen**.

```text
Dokumente, E-Mails, Systeme und Gespräche
                    ↓
          Sicherheits- und Rechteprüfung
                    ↓
     Quellen erfassen und Inhalte extrahieren
                    ↓
      einzelne Wissensaussagen erkennen
                    ↓
       prüfen, versionieren und freigeben
                    ↓
     zentrale AILIZA-Wissensdatenbank
          ↙          ↓          ↘
       Suche     Wissensgraph    KI-Kontext
          ↓          ↓          ↓
     Antworten, Vorlagen und Arbeitsprozesse
                    ↓
       Quellenbeleg und Nutzungsnachweis
```

### 1. Die Speicherbereiche

Jeder Inhalt gehört genau zu einem fachlichen Memory Scope:

| Scope      | Bedeutung                                               |
| ---------- | -------------------------------------------------------- |
| `session`  | Nur für die aktuelle Unterhaltung oder Aufgabe            |
| `personal` | Persönliche Arbeitsweisen und Präferenzen eines Nutzers   |
| `project`  | Wissen eines bestimmten Projekts                          |
| `company`  | Berechtigtes und gegebenenfalls geprüftes Firmenwissen    |

`help_glossary` und `learning_content` sind Inhaltsbereiche, keine
zusätzlichen Speicherbereiche. Wissen wird niemals allein aufgrund
inhaltlicher Ähnlichkeit zwischen den Scopes übertragen.

### 2. Die fünf Wissensebenen

**Originalquellen** — Unveränderte Dokumente, PDFs, E-Mails, Protokolle,
Tabellen, Webseiten oder Systemdatensätze. Gespeichert werden Herkunft,
Zeitpunkt, Dateityp und Hash.

**Quellenstellen** — Die genaue Fundstelle einer Information: Seite und
Absatz, Tabelle und Zeile, Zeitmarke, E-Mail oder Datensatz,
Dokumentversion.

**Wissensaussagen** — Kleine, einzeln prüfbare Aussagen, z. B.:
> „Produkt A kostet seit dem 1. August 2026 netto 120 Euro."
Nicht das ganze Dokument wird als Wahrheit behandelt, sondern jede
relevante Aussage mit ihrem Beleg.

**Beziehungen** — Verbindungen zwischen Wissen, Personen, Produkten,
Kunden, Projekten und Regeln:
```text
Produkt A → besitzt Preis → 120 Euro
Produkt A → gehört zu → Produktgruppe B
Mitarbeiterin C → ist verantwortlich für → Produkt A
Regel D → gilt für → Produktgruppe B
```

**Nutzungsnachweise** — AILIZA dokumentiert intern, welche
Wissensaussagen und Quellen eine Antwort, Vorlage oder Entscheidung
beeinflusst haben.

### 3. Zentrale Datenobjekte (Zielmodell)

| Objekt                    | Aufgabe                                   |
| -------------------------- | ------------------------------------------ |
| `source_artifacts`        | Originalquellen und Dateien               |
| `source_passages`         | genaue Fundstellen                        |
| `knowledge_items`         | fachliche Identität eines Wissenseintrags |
| `knowledge_versions`      | unveränderliche Versionen                 |
| `knowledge_claims`        | einzelne prüfbare Aussagen                |
| `claim_evidence`          | Verbindung von Aussage und Quellenstelle  |
| `claim_relations`         | Beziehungen im Wissensgraphen             |
| `conflict_sets`           | widersprüchliche Aussagen                 |
| `permissions`             | Lese-, Schreib- und Aktionsrechte         |
| `approvals`               | Prüfungen und Freigaben                   |
| `review_tasks`            | fällige oder notwendige Prüfaufgaben      |
| `answer_receipts`         | Wissensnachweise erzeugter Antworten      |
| `template_definitions`    | professionelle Arbeitsvorlagen            |
| `template_runs`           | protokollierte Vorlagennutzung            |
| `audit_events`            | manipulationsgeschützte Ereignisse        |
| `index_jobs`              | Aufbau der Such- und Graphindizes         |
| `integration_connections` | kontrollierte externe Anschlüsse          |

Die genauen Tabellen und Felder sind ein Zielmodell. Ihre vollständige
technische Umsetzung ist aus der vorliegenden Memory-Referenz noch nicht
belegt.

### 4. Lebenszyklus des Wissens

```text
importiert
→ Entwurf
→ in Prüfung
→ freigegeben
→ gegebenenfalls veraltet
→ archiviert oder soft-gelöscht
```

Eine freigegebene Version wird niemals still überschrieben. Eine
Änderung erzeugt eine neue Version. Jede Version besitzt: Inhalt und
Kategorie, Scope und Organisationszuordnung, Quelle und genaue
Belegstelle, Autor und Verantwortlichen, Prüfer und Freigabestatus,
fachliche Gültigkeit, Erfassungs- und Änderungshistorie, Zugriffsrechte,
Konfliktstatus, Lösch- und Aufbewahrungsstatus.

### 5. Zwei getrennte Zeitachsen

AILIZA unterscheidet:
1. **Fachliche Gültigkeit:** Wann galt die Information tatsächlich?
2. **Systemhistorie:** Wann wurde sie in AILIZA erfasst, geändert oder
   freigegeben?

Damit kann AILIZA z. B. korrekt beantworten: „Welcher Preis galt am
1. Mai 2026?" Der heutige Preis wird nicht rückwirkend als damalige
Wahrheit dargestellt.

### 6. Dokumentwissen-Pipeline

1. PDF, Markdown oder andere erlaubte Quelle übernehmen.
2. Identität und Berechtigung prüfen.
3. Dateityp, Größe und Sicherheit prüfen.
4. Scope und Zweck festlegen.
5. Text, Tabellen und Struktur extrahieren.
6. sensible Daten klassifizieren.
7. Quelle, Hash, Datum und Dokument-ID speichern.
8. nachvollziehbare Quellenabschnitte bilden.
9. Wissensaussagen und Beziehungen vorschlagen.
10. Konflikte mit vorhandenem Wissen erkennen.
11. menschliche Prüfung und Freigabe durchführen.
12. Such-, Vektor- und Graphindizes aktualisieren.
13. nur erlaubtes Wissen für Antworten abrufen.
14. Antwort mit Quellen und Nutzungsnachweis erzeugen.

### 7. Intelligente Suche

Klassische Volltextsuche, Filter nach Firma/Projekt/Person/Scope, Suche
nach Status und Gültigkeitszeitraum, semantische Ähnlichkeitssuche,
Suche im Wissensgraphen, Suche nach Quellen und Verantwortlichen.
Volltext-, Vektor- und Graphindizes sind nur **erneuerbare Suchhilfen**.
Sie dürfen niemals über Berechtigungen, Freigaben oder Gültigkeit
entscheiden.

### 8. Konfliktmanagement

Findet AILIZA zwei widersprüchliche Aussagen, entscheidet sie nicht
automatisch nach Aktualität oder Ähnlichkeit:
1. beide Aussagen werden erhalten,
2. beide Quellen werden angezeigt,
3. ein Konfliktfall entsteht,
4. die automatische Verwendung wird bei hohem Risiko gesperrt,
5. eine berechtigte Person entscheidet,
6. die Entscheidung bleibt mit Begründung nachvollziehbar.

### 9. Rollen und Berechtigungen

Jede Lese- und Schreiboperation prüft mindestens: Organisation bzw.
Mandant, Nutzeridentität, Rolle, Scope, konkrete Ressource, erlaubte
Aktion, Zweck, Datenklasse, Status und Gültigkeit.

Wichtige Regeln:
- Ein Firmenadministrator darf nicht automatisch persönliche Inhalte
  anderer Nutzer lesen.
- Projekt A sieht kein Wissen aus Projekt B.
- Kundenkontext ist nicht automatisch persönliches Wissen.
- `personal` darf nicht automatisch zu `company` werden.
- Externe Aktionen benötigen eine separate Freigabe.
- Für Solo-Unternehmen muss `solo_compensated` sichtbar vom echten
  Vier-Augen-Prinzip `dual_control` getrennt werden.

### 10. Anbindung an die bestehende Memory Engine

**Nicht belegt im aktuellen Code** (siehe Ist-Vergleich unten):
`episodic_logs`, `graph_nodes`, `graph_edges`, `core_facts`,
`get_context_summary()`, `CognitiveAgent.trigger_sleep_cycle()`. Für die
Zielarchitektur gelten dennoch folgende Grenzen, falls/wenn diese
Komponenten entstehen:
- Chatverläufe erzeugen höchstens Wissensvorschläge.
- Ein etwaiger Fakten-Cache ist nur Cache, keine alleinige Wahrheit.
- Der Graph wird aus erlaubtem und freigegebenem Wissen abgeleitet.
- Ein etwaiger Konsolidierungszyklus darf freigegebenes Firmenwissen
  nicht selbstständig überschreiben oder löschen.
- Ein Kontextaufbau-Mechanismus benötigt Filter für Mandant, Nutzer,
  Rolle, Scope, Zweck, Status und Gültigkeit.

### 11. Wissensgesundheit (Dashboard, Zielbild)

Fällige Überprüfungen, ablaufende Gültigkeiten, Wissen ohne belastbare
Quelle, offene Konflikte, Einträge ohne Verantwortlichen, häufig
verwendete aber schwach belegte Aussagen, verwaiste Dokumente, Antworten
auf inzwischen veraltetem Wissen, fehlgeschlagene Indexaktualisierungen.

### 12. Professionelle Arbeitsvorlagen

Jede Vorlage definiert: benötigte Eingaben, erlaubte Quellen, erlaubte
Scopes, Qualitätsanforderungen, Sicherheitsregeln, Ausgabeformat,
erforderliche Freigabe, erlaubte externe Aktionen. Vorgesehen u. a.:
E-Mail schreiben/beantworten, Angebot, Rechnungstext, Mahnung,
Reklamation, Kundenhistorie, Meeting-Protokoll, Produktbeschreibung,
Pressemitteilung, Kosten-Nutzen-Analyse. Versand, Buchung oder
Veröffentlichung erfolgen niemals automatisch ohne Berechtigung und
Freigabe.

### 13–15. Obsidian-Option und Knowledge Studio

Obsidian ist nicht die zentrale Datenbank, sondern eine optionale
Wissensoberfläche (native AILIZA Wissen / + Obsidian Workspace / Managed
Knowledge Workspace) mit kontrolliertem Rückkreislauf
(AILIZA-Freigabe → Obsidian-Lesekopie → Änderungsvorschlag →
AILIZA-Prüfung → menschliche Freigabe → neue Wissensversion). Offenes
Austauschformat (CommonMark, dokumentierte YAML/JSON-Metadaten, stabile
UUIDs, Hash-Prüfsummen, Exportmanifest) verhindert Obsidian-Abhängigkeit.
Ein späteres "AILIZA Knowledge Studio" kann bewährte Funktionen nativ
anbieten. Beide Punkte sind eigenständige, nachgelagerte Vorhaben und
nicht Teil des unten stehenden Phasenplans.

### 16. Zielbild

- Sie erinnert sich, ohne alles ungeprüft zu glauben.
- Sie verbindet Wissen, ohne Berechtigungsgrenzen zu vermischen.
- Sie erkennt Widersprüche, statt sie zu verstecken.
- Sie kennt Vergangenheit und aktuellen Stand.
- Sie zeigt Quellen statt unbelegte Antworten zu erzeugen.
- Sie lässt Menschen über kritisches Firmenwissen entscheiden.
- Sie bleibt unabhängig von Obsidian, Vektordatenbanken und einzelnen
  KI-Modellen.

---

## Ist-Vergleich (Stand 2026-08-13, `apps/backend/db_schema.py`)

Tatsächlich vorhandene Tabellen: `audit_logs`, `approval_requests`,
`agent_runs`, `user_specialist_roles`, `case_assignments`,
`security_logs`, `performance_logs`, `cost_logs`, `reflection_facts`,
`feedback`, `routing_proposals`, `kill_switch_state`, `users`,
`user_settings`, `memory_sources`, `memory_items`, `memory_visibility`,
`memory_suggestions`, `messenger_bindings`, `totp_secrets`,
`totp_backup_codes`, `skills`, `knowledge_sources`, `knowledge_chunks`,
`knowledge_source_permissions`, `user_projects`, `user_chats`.

| Zielobjekt | Status | Tatsächliche Tabelle |
|---|---|---|
| `source_artifacts` | abgewandelt vorhanden | `knowledge_sources` |
| `source_passages` | abgewandelt vorhanden | `knowledge_chunks` |
| `knowledge_items` | fehlt komplett | — |
| `knowledge_versions` | fehlt komplett | — |
| `knowledge_claims` | fehlt komplett | — |
| `claim_evidence` | fehlt komplett | — |
| `claim_relations` | fehlt komplett | — |
| `conflict_sets` | fehlt komplett | — |
| `permissions` | abgewandelt vorhanden | `knowledge_source_permissions`, `memory_visibility` (getrennt, nicht generisch) |
| `approvals` | abgewandelt vorhanden | `approval_requests`, `memory_suggestions` |
| `review_tasks` | fehlt komplett | — |
| `answer_receipts` | fehlt komplett | — |
| `template_definitions` | fehlt (anderes vorhanden) | `skills` (kein Vorlagenmodell) |
| `template_runs` | fehlt komplett | — |
| `audit_events` | vorhanden | `audit_logs` |
| `index_jobs` | fehlt komplett | — |
| `integration_connections` | abgewandelt vorhanden | `messenger_bindings` (nur Messenger) |

`episodic_logs`, `graph_nodes`, `graph_edges`, `core_facts`,
`get_context_summary()`, `CognitiveAgent.trigger_sleep_cycle()`: **nicht
im aktuellen Code gefunden.** Möglicher Bezug zum Remote-Branch
`real_cognitive_agent_memory_engine.py` (nicht in `main` gemerged) —
noch nicht verifiziert.

---

## Phasenplan

Jede Phase startet erst nach expliziter Freigabe (CLAUDE.md-Grundregel).

**Phase 1 — Wissens-Kern:** `knowledge_items`, `knowledge_versions`,
`knowledge_claims`, `claim_evidence`. Baut auf vorhandenen
`knowledge_sources`/`knowledge_chunks` auf. Offene Grundsatzfrage: Speisen
`memory_items`/`reflection_facts` künftig auch die Claims-Schicht, oder
bleibt sie vorerst dokumentenbasiert? DSGVO-Klassifikation läuft über die
bestehende Governance-Pipeline. Reviewer: `pg-sqlite-migration-checker`,
ggf. `memory-invariant-reviewer`.

**Phase 2 — Graph & Konfliktmanagement:** `claim_relations`,
`conflict_sets`. Setzt Phase 1 voraus. Braucht vorab eine fachlich
festgelegte Konflikt-Erkennungsregel (nicht rein technisch).

**Phase 3 — Prozess & Nachweis:** `review_tasks`, `answer_receipts`,
generisches `permissions`-Modell, Erweiterung `approvals`. Größte
Einzelentscheidung: bestehende `knowledge_source_permissions` und
`memory_visibility` ablösen vs. parallel lassen. Reviewer:
`auth-security-reviewer`, ggf. `memory-invariant-reviewer`.

**Phase 4 — Vorlagen & Integrationen:** `template_definitions`,
`template_runs`, `index_jobs`, `integration_connections`. Kann teilweise
parallel laufen, sollte aber nicht vor Phase 1 beginnen (Vorlagen
brauchen "erlaubte Quellen/Scopes" aus Phase 1). `index_jobs` braucht
vorab eine Entscheidung zur Such-/Vektorinfrastruktur.

**Nicht Teil des Phasenplans:** Obsidian-Anbindung (Abschnitte 13–14),
Knowledge Studio UI (Abschnitt 15) — eigenständige, nachgelagerte
Vorhaben.
