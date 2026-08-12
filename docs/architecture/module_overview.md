# Modulübersicht — Governance-relevante Backend-Module

Stand: 2026-08-11. Geprüft gegen Branch `feature/model-intelligence-router`.

Dieses Dokument beschreibt Module, die für DSGVO- und EU-AI-Act-Prüfungen
relevant sind, aber bisher in keiner Strukturübersicht auftauchten. Jede
Aussage nennt ihre Belegstelle im Code.

**Wichtiger Hinweis vorab:** `apps/backend/memory/` ist **nicht** der
fachliche Memory-Kern, sondern ein quarantänisierter Prototyp. Die
Unterscheidung steht in Abschnitt 3.

---

## 1. `apps/backend/intelligence/` — Modell-Empfehlung

**Zweck:** Wählt unter bereits freigegebenen Modellen dasjenige aus, das
die harten Anforderungen einer Anfrage erfüllt (Fähigkeiten, Datenschutz,
Kontextgröße, Region) und nach versionierten Benchmark-Scores am besten
passt.

**Governance-Rolle:** Das Modul hat **kein eigenes Freigaberecht**. Es kann
weder einen Provider noch ein Modell freischalten. Es routet
ausschließlich unter Kandidaten mit `status="approved"`.

**Zentrale Komponenten**

| Datei | Inhalt |
|---|---|
| `models.py` | `ModelCandidate`, `RoutingRequest`, `RoutingDecision` (unveränderliche Datenklassen) |
| `model_router.py` | `ModelRouter.route()` — deterministische Auswahl, keine Zufallskomponente |
| `__init__.py` | Exportiert genau diese vier Symbole |

**Verbindliche Regeln (im Code durchgesetzt)**

1. **Freigabe ist ein menschlicher Schritt.** `approve_model_candidate()`
   in `apps/backend/database.py` verlangt `reviewer_role` aus
   `("admin", "manager")` und wirft sonst `ValueError`. Dasselbe
   Rollenmodell wie `confirm_memory_suggestion()`.
2. **Neue Kandidaten sind nie sofort wählbar.** `create_model_candidate()`
   setzt immer `status="candidate"` — unabhängig von den Übergabewerten.
3. **Harte Datenklassen-Sperre.** `recommend_model()` bricht ab, sobald
   `data_classes` eine der Klassen `credentials`, `special_category`,
   `hr`, `legal` enthält (Konstante `_MODEL_ROUTING_BLOCKED_CLASSES`).
   Kein Score kann diese Sperre aufheben. Dies ist dieselbe Sperrliste
   wie `_BLOCKED_CLASSES` in `apps/backend/reflection/reflection_skill.py`.
4. **Datenschutz-Schwelle.** Bei `data_risk` in `high`/`critical` werden
   Modelle mit `privacy_score < 0.8` ausgeschlossen
   (`ModelRouter._eligible()`).

**Persistenz und Nachweisbarkeit**

| Tabelle | Zweck | Mandantentrennung |
|---|---|---|
| `model_candidates` | Welche Modelle existieren und welchen Freigabestatus sie haben | plattformweit, **kein** `tenant_id` — welche Modelle grundsätzlich existieren dürfen, ist keine Mandantenentscheidung |
| `routing_decisions` | Append-only Protokoll jeder Empfehlung | `tenant_id`-gefiltert |

Jede Empfehlung schreibt zusätzlich einen Eintrag in den zentralen
Audit-Vault über `write_audit_entry(action="model.routing.recommended")`.
Blockierte Anfragen erzeugen `action="model.routing.blocked"`. Beide
enthalten **keine** Prompt- oder Antwortinhalte, nur Metadaten.

Migration: `apps/backend/alembic/versions/0005b_add_model_intelligence_tables.py`
(Revision `b7e4d92c1a63`).

**Abgrenzung**

- **Nicht** im produktiven LLM-Aufrufpfad verdrahtet. `recommend_model()`
  liefert eine Empfehlung und einen Audit-Eintrag — es ruft selbst
  keinen Provider auf. Der produktive Pfad läuft weiterhin über
  `providers/orchestrator.py`.
- **Nicht** zuständig für die Provider-Freigabe. Diese liegt bei
  `providers/provider_profiles.py` (AVV-Prüfung) und
  `registry/provider_registry.yaml`.
- **Nicht** identisch mit `routing/router.py` — jenes entscheidet über
  Token-Budget und Komplexitätsstufe (SIMPLE..RISKY), nicht über die
  Modellauswahl.

**Freigabe und Routing — beides fail-closed (B3/B4)**

| Prüfpunkt | Verhalten |
|---|---|
| Modellfreigabe ohne angemeldete Person | verweigert (`ModelApprovalDenied`) |
| Freigabe per frei übergebenem Rollen-String | nicht mehr möglich — der Parameter existiert nicht |
| Freigabe im fremden Namen | ausgeschlossen; `approved_by` stammt aus dem Actor |
| Selbstfreigabe (Einbringer = Freigebender) | verweigert und auditiert |
| Unbekannte oder unzureichende Rolle | verweigert und auditiert |
| Routing ohne Klassifikation | kein Modell wird ausgewählt |
| Klassifikation als lose Liste oder Dict | abgewiesen — nur `ClassificationResult` der Governance-Komponente |
| Gesperrte Datenklasse | kein Modell, unabhängig von Score, Provider und `local_only` |

**Bekannte Lücken**

- Keine Anbindung an `orchestrator.generate()`. Bewusst offen gelassen;
  eine Verdrahtung ist eine eigene Entscheidung mit eigener Freigabe.
- Kein API-Endpunkt für die Modellfreigabe. Freigaben erfolgen derzeit
  nur über die Datenbankfunktion. Es gibt damit **keinen produktiven
  Aufrufer** — die Härtung ist vorsorglich, nicht reaktiv.
- **B-GOV-2 (offen, HANDOFF):** `ClassificationResult` trägt keine
  Versionsangabe. Eine Bindung an eine bestimmte Klassifiziererversion ist
  deshalb nicht möglich; belegt ist nur die Herkunft (Typ), nicht der
  Stand. Zu ergänzen, bevor Klassifikationsergebnisse revisionssicher
  nachweisbar sein müssen.
- **Freigabepolicy nicht bestätigt (HANDOFF):** Die Schwelle
  (`manager`/`admin`, `dsb` ausgeschlossen) folgt dem bestehenden
  Projektmuster aus `confirm_memory_suggestion()`. Eine fachlich
  bestätigte Freigaberegel für Modelle existiert im Repository nicht und
  wurde hier **nicht** eigenmächtig beschlossen — sie ist zu bestätigen.
- **Vier-Augen-Prinzip nur bei bekanntem Urheber:** Ist `created_by` nicht
  gesetzt (Altbestand oder Anlage ohne Urheber), lässt sich Selbstfreigabe
  nicht prüfen. Dieser Fall wird auditiert
  (`model.approval.creator_unknown`), nicht stillschweigend übergangen.

**Referenzdateien:** `apps/backend/intelligence/__init__.py`,
`model_router.py`, `models.py`, `apps/backend/database.py`
(`create_model_candidate`, `approve_model_candidate`,
`list_model_candidates`, `recommend_model`), `apps/backend/db_schema.py`
(`model_candidates`, `routing_decisions`),
`tests/test_model_intelligence_router.py`

---

## 2. Memory-Kern — Tabellen in `apps/backend/db_schema.py`

**Zweck:** Fachliches Gedächtnis von AILIZA. Speichert freigegebene
Inhalte mit Herkunft, Sichtbarkeit und Aufbewahrungsfrist.

**Governance-Rolle:** Zentral. Hier entscheidet sich, welche Information
über eine Sitzung hinaus erhalten bleibt und wer sie sehen darf.

**Zentrale Komponenten**

| Tabelle | Zeile in `db_schema.py` | Zweck |
|---|---|---|
| `memory_sources` | 288 | Woher stammt ein Inhalt |
| `memory_items` | 303 | Der Inhalt selbst |
| `memory_visibility` | 327 | Wer darf ihn sehen |
| `memory_suggestions` | 344 | Vorschläge, die noch auf Freigabe warten |

**Verbindliche Regeln (im Code durchgesetzt)**

1. **Unternehmensweites Gedächtnis braucht eine Freigabe.**
   `confirm_memory_suggestion()` verlangt bei
   `requires_admin_approval` eine `reviewer_role` aus
   `("admin", "manager")`, sonst `MemoryValidationError`.
2. **Nur bestimmte Zustände sind bestätigbar.** Nur `open` und
   `needs_admin_approval` — `rejected`, `expired` und `blocked` erzeugen
   nie ein `memory_item`.
3. **Vier Datenklassen werden im Reflection-Pfad nie gespeichert.**
   `_BLOCKED_CLASSES` in `reflection/reflection_skill.py`:
   `CREDENTIALS`, `SPECIAL_CATEGORY`, `HR`, `LEGAL`.

   **Wichtige Einschränkung:** Diese Prüfung über `classify()` läuft
   ausschließlich in `store_fact()` (Ziel: Tabelle `reflection_facts`).
   `create_memory_item()` und `confirm_memory_suggestion()` rufen
   `classify()` **nicht** auf — sie prüfen nur Scope, Zweck, Quelle und
   Besitzer über `_validate_memory_item()`. Die Sperrliste greift also
   **nicht** automatisch bei jedem Schreibvorgang in den Memory-Kern.
   Siehe „Bekannte Lücken".

**Fachliche Gedächtnisebenen:** Sitzung, Persönlich, Projekt,
Unternehmen. Technisch abgebildet über `user_memory` / `company_memory`
plus `visibility_scope` — die fachlichen Ebenen sind keine eigenen
Tabellen.

**Abgrenzung**

- **Nicht** identisch mit `apps/backend/memory/` (siehe Abschnitt 3).
  Diese Verwechslung ist der wahrscheinlichste Fehler bei einer Prüfung.

**Behobene Befunde (B-MEM-1 bis B-MEM-3)**

Alle drei wurden praktisch reproduziert und anschließend behoben. Die
Nachweise liegen in `tests/test_memory_security_hardening.py` (32 Tests).

| ID | Befund (vorher) | Behebung |
|---|---|---|
| B-MEM-1 | Die Sperrliste griff nur in `store_fact()` (`reflection_facts`). Über `create_memory_item()` ließen sich Zugangsdaten, Gesundheits-, Personal- und Rechtsdaten unredigiert speichern. | Zentrale Prüfung `_enforce_memory_content_policy()` an **allen** Schreibpfaden. Vorschläge werden datensparsam blockiert (Rohinhalt verworfen) statt abgewiesen. |
| B-MEM-2 | Über die reine ID waren fremde Mandanten les-, änder-, lösch- und bestätigbar. | `tenant_id` ist Pflichtparameter (keyword-only) in `get_memory_item`, `set_memory_visibility`, `mark_memory_item_deleted`, `reject_memory_suggestion`, `mark_memory_suggestion_blocked`, `confirm_memory_suggestion`. Filterung erfolgt in SQL, nicht nachgelagert. |
| B-MEM-3 | Memory-Aktionen liefen nie durch `evaluate_permission()`; es gab nur eine Ad-hoc-Zugehörigkeitsliste und einen Rollen-String. | Neun `MEMORY_*`-Aktionen im **bestehenden** zentralen Evaluator; die drei produktiven Endpunkte rufen ihn über `_require_memory_permission()`. Kein zweites Berechtigungssystem. **Teilweise** — siehe Einschränkung unten. |

**Einschränkung zu B-MEM-3 (wichtig für eine Prüfung):** Produktiv
angebunden sind nur die drei Vorschlags-Aktionen
(`MEMORY_SUGGESTION_LIST/CONFIRM/REJECT`). Die Konstanten auf Item-Ebene
(`MEMORY_ITEM_READ/LIST/CREATE/DELETE`, `MEMORY_VISIBILITY_UPDATE`,
`MEMORY_SCOPE_TRANSFER`) sind definiert und getestet, werden aber von
**keinem** Produktivpfad aufgerufen — es gibt dort heute keine
HTTP-Endpunkte. Der Schutz auf Item-Ebene stammt allein aus den
`tenant_id`-Pflichtparametern der Datenbankfunktionen. Wer die Tests
liest, könnte sonst eine Absicherung annehmen, die im Betrieb nicht
greift.

**Entwurfsentscheidungen dabei**

- **Keine `tenant_id`-Spalte in `memory_visibility`.** Sie wäre eine
  zweite Wahrheit über die Mandantenzugehörigkeit und könnte vom
  zugehörigen `memory_item` abweichen. Der Mandantenbezug wird stattdessen
  über das Item geprüft.
- **`memory_items.tenant_id` bleibt `nullable`.** Altdaten ohne Mandant
  müssen für ihren Besitzer auffindbar, exportierbar und löschbar bleiben
  (Art. 17/20 DSGVO). Eine stillschweigende Zuordnung wäre eine
  Datenfälschung.
- **Kein generischer Zugriff auf mandantenlose Altdaten.** Ein erster
  Entwurf ließ solche Zeilen mit passendem `owner_user_id` über
  `get_memory_item()` zu. Das war falsch: derselbe `user_id` kann in
  mehreren Mandanten existieren, wodurch ein Nutzer aus Mandant B an die
  Altdaten eines gleichnamigen Nutzers aus Mandant A kam. Die Ausnahme
  wurde entfernt; der Selbstbedienungspfad läuft ausschließlich über
  `list_active_memory_items_for_user()` und
  `_soft_delete_owned_memory_items()`, die zusätzlich nach `scope` und
  `owner_user_id` filtern.
- **`tenant_id=None` ist ein Fehler, kein Filter.** `== None` übersetzt
  SQLAlchemy zu `IS NULL` und hätte alle mandantenlosen Zeilen getroffen.
  `_require_tenant()` weist leere Werte fail-closed ab.
- **Scope-Wechsel ist hart verweigert.** Es existiert kein freigegebener
  Transferpfad zwischen Gedächtnisebenen; `MEMORY_SCOPE_TRANSFER` wird für
  **jede** Rolle abgelehnt und der Versuch auditiert.

**Zweite Prüfrunde — acht weitere Lücken in der ersten Behebung**

Eine unabhängige Gegenprüfung fand in der *ersten* Fassung dieser
Behebung acht Lücken, davon drei mit hohem Schweregrad. Alle wurden
behoben und mit Tests belegt:

| Schwere | Lücke | Behebung |
|---|---|---|
| hoch | Beim Blockieren wurde nur der Inhalt verworfen — der Titel enthielt im Chat-Pfad den Rohprompt (`title=task[:100]`) | Titel, Zweck und Kategorie werden ebenfalls verworfen |
| hoch | `tenant_id=None` wirkte als `IS NULL` und öffnete alle Altdaten | `_require_tenant()` an allen Zugriffspfaden |
| hoch | Altdaten-Ausnahme prüfte nur den Besitzernamen, nicht den Ursprungsmandanten | Ausnahme entfernt (siehe oben) |
| mittel | `purpose` und `category` liefen an der Inhaltsprüfung vorbei | beide werden geprüft |
| mittel | `confirm_memory_suggestion()` filterte nicht nach Eigentümer — ein anderer Nutzer desselben Mandanten konnte bestätigen | zusätzlicher `user_id`-Filter, auch im öffentlichen Alias |
| niedrig | `MEMORY_ITEM_CREATE` hatte Listen-Semantik (Blanko-Erlaubnis) | als Eigentümer-Aktion eingestuft |
| niedrig | Die Endpunkte übergaben den Aufrufer als Eigentümer — die Prüfung war dadurch wirkungslos | tatsächlicher Eigentümer aus dem Datensatz |

Eine **zweite** Prüfrunde deckte danach einen weiteren Fehler in genau
dieser Korrektur auf: Die Rollen-Ausnahme für admin/manager hob die
Eigentümerbindung **pauschal** auf, nicht nur für Firmenwissen. Ein
Manager konnte dadurch aus dem persönlichen Vorschlag eines fremden
Nutzers einen Gedächtniseintrag erzeugen. Die Ausnahme greift jetzt nur
noch bei `suggested_scope == "company_memory"`.

**Verbleibende Lücken**

- **B-GOV-1 (neu, offen): `classify()` erkennt nicht jeden Art.-10-Fall.**
  Ein Text über ein Strafverfahren („Mitarbeiter Meier wurde wegen
  Diebstahl strafrechtlich verurteilt") wird als `public` eingestuft, nicht
  als `LEGAL`, und damit gespeichert. Texte mit HR- oder
  Gesundheitsbezug werden dagegen korrekt geblockt. Die Sperre ist also nur
  so gut wie der Klassifizierer.
  `declared_data_classes` ist der verlässliche Weg — **wird aber derzeit
  von keinem produktiven Aufrufer gesetzt**, nur in Tests. Der Parameter
  ist damit heute eine Möglichkeit, keine wirksame Maßnahme.
  Eine Verbesserung von `classify()` selbst wirkt auf die gesamte
  Redaction-/Policy-Pipeline und gehört in eine eigene Aufgabe mit eigener
  Freigabe. **HANDOFF.**
- **B-MEM-4 (neu, offen): Selbstbedienungspfad bleibt mandantenübergreifend
  für Altdaten — nur teilweise behoben.** Gehärtet wurde ausschließlich
  `get_memory_item()`. `list_active_memory_items_for_user()`,
  `export_user_data()` und `_soft_delete_owned_memory_items()` enthalten
  weiterhin `or_(tenant_id == X, tenant_id.is_(None))` und filtern nur nach
  `owner_user_id` und `scope`. Praktisch belegt: Existiert derselbe
  `user_id` in zwei Mandanten, liest **und löscht** jeder von beiden diese
  mandantenlosen Altdaten.
  Das ist bestehendes, dokumentiertes Verhalten (M1-Übergangsregel) und war
  nicht Teil dieser Änderung. Die Auflösung erfordert eine Entscheidung, wem
  die Altdaten zugeordnet werden — eine stillschweigende Zuordnung wäre
  Datenfälschung, ein ersatzloses Sperren würde Auskunft und Löschung nach
  Art. 17/20 DSGVO verhindern. Deshalb ausdrücklich **nicht** eigenmächtig
  entschieden. **HANDOFF — braucht eine menschliche Entscheidung.**
- **Außerhalb des Memory-Bereichs, nur als Hinweis:** `/feedback`
  (`apps/backend/main.py`) übernimmt `tenant_id` aus dem Anfragekörper
  statt aus dem Token. Nicht Teil dieser Aufgabe, nicht geprüft.
- **B-MEM-3 (Rest): Anbindung an `permissions.py` ist auf die drei
  produktiven Memory-Endpunkte begrenzt.** Die Datenbankfunktionen selbst
  setzen Mandant und Eigentümer durch, prüfen aber keine Rolle — ein
  direkter Aufruf aus dem Code umgeht die Rollenprüfung. Für weitere
  Endpunkte muss `_require_memory_permission()` jeweils ergänzt werden.

**Referenzdateien:** `apps/backend/db_schema.py` (Zeilen 288–366),
`apps/backend/database.py` (`_enforce_memory_content_policy`,
`_memory_blocked_classes`, `create_memory_item`, `get_memory_item`,
`set_memory_visibility`, `mark_memory_item_deleted`,
`confirm_memory_suggestion`, `reject_memory_suggestion`),
`apps/backend/permissions.py` (`MEMORY_*`, `evaluate_permission`),
`apps/backend/main.py` (`_require_memory_permission` und die drei
Memory-Endpunkte), `apps/backend/reflection/reflection_skill.py`,
`apps/backend/routers/memory.py` (siehe Abschnitt 3),
`tests/test_memory_security_hardening.py`

---

## 3. `apps/backend/memory/` — technischer Prototyp, quarantänisiert

> **Dieses Modul ist nicht produktiv und nicht der Memory-Kern.**
> Es steht hier ausschließlich, damit es bei einer Prüfung nicht
> fälschlich für ein Governance-Modul gehalten wird.

**Zweck (ursprünglich):** Technischer Hash-Speicher für Merkmale wie
Sitzungs- oder Audit-Kennzeichen. Speichert **nur** `content_hash`, nie
Klartext.

**Tatsächlicher Status: gesperrt.** Belege:

1. **Nicht eingebunden.** `apps/backend/main.py` enthält genau einen
   `include_router()`-Aufruf (Zeile 511, `approvals_router`). Der
   Memory-Prototyp-Router ist dort nicht registriert und damit über
   HTTP nicht erreichbar.
2. **Fail-closed gesperrt.** `routers/memory.py` registriert
   `_quarantine_guard()` als router-weite `dependencies=[...]`. Diese
   Funktion wirft **immer** HTTP 503 — unabhängig von Zugangsdaten,
   Rolle oder Mandant. Auch ein später ergänzter Endpunkt wäre damit
   automatisch gesperrt.
3. **Eigene, getrennte Datenhaltung.** `sqlite_store.py` schreibt in
   eine eigene SQLite-Datei, nicht in die Hauptdatenbank.
4. **Eigene Begriffe.** `MemoryPurpose` (`task`, `session`, `audit`,
   `consent`) und `VisibilityLevel` (`user`, `operator`, `system`) sind
   **nicht** die Scopes des fachlichen Kerns und dürfen nicht mit ihnen
   gleichgesetzt werden.

**Bekannte Lücken**

- Keine Anbindung an RBAC (`auth/`) oder den zentralen
  Permission-Evaluator.
- Keine Mandantentrennung (`tenant_id` wird nicht geführt).
- Keine Anbindung an den Audit-Vault.

Diese Lücken sind der Grund für die Quarantäne, nicht ein zu behebender
Fehler im laufenden Betrieb.

**Offene Entscheidung:** Ob dieses Modul weiterbetrieben, ausgebaut oder
entfernt wird, ist offen. Belegstelle: Moduldocstring in
`apps/backend/routers/memory.py`, der als Voraussetzung für eine
produktive Nutzung ausdrücklich „eine bewusste Entscheidung, ob dieses
Modul ueberhaupt weiterbetrieben oder entfernt wird" nennt. Bis dahin
bleibt es unregistriert und gesperrt.

**Referenzdateien:** `apps/backend/memory/__init__.py`, `models.py`,
`store.py`, `sqlite_store.py`, `apps/backend/routers/memory.py`,
`tests/test_memory_prototype_quarantine.py`

---

## 3a. Migrations-Merge-Gate (bedingt)

**Aktueller Stand:** Der PR-Branch hat **genau einen** Alembic-Head
(`b7e4d92c1a63`). Die Kette ist linear:
`6165ff33e9ee → b4d3a1d0de71 → d8f4c6a91b27 → b7e4d92c1a63`.

**Der Konflikt ist damit nicht aufgelöst, sondern nur nicht ausgelöst.**
Der lokale Branch `feature/phase-1` (nicht auf dem Remote, nicht Teil von
PR #86) enthält `e1a7c3f92b56` mit demselben Vorgänger `d8f4c6a91b27`.

| | |
|---|---|
| Auslöser | Sobald beide Zweige gemeinsam integriert werden |
| Folge ohne Maßnahme | Zwei Heads, `alembic upgrade head` schlägt fehl |
| Maßnahme | Genau **ein** Head herstellen: entweder `down_revision` eines Zweigs auf den anderen umhängen (lineare Reihenfolge) oder eine Alembic-Merge-Revision erzeugen |
| Voraussetzung | Erst wenn beide Zweige tatsächlich integriert werden — eine Merge-Revision auf einen nicht integrierten Branch zu bauen erzeugt eine Abhängigkeit auf Code, den es öffentlich nicht gibt |
| Nachweis danach | `alembic heads` liefert genau einen Head; frische Migration, Upgrade einer bestehenden Datenbank und Downgrade erneut vollständig testen |

**Status: bedingtes Merge-Gate, offen.** Es blockiert PR #86 nicht, muss
aber vor dem gemeinsamen Merge mit `feature/phase-1` erledigt sein.

---

## 4. Zielarchitektur Memory — HANDOFF, noch nicht umgesetzt

> Dieser Abschnitt beschreibt **Absicht, keinen Ist-Zustand**. Keine der
> hier genannten Klassen existiert heute. Er dient als Rahmen für spätere
> Entscheidungen, nicht als Beschreibung des Codes.

**Ziel:** Andere Speicher (PostgreSQL, Graph-, Vektorspeicher) anbinden
können, ohne die Governance-Regeln zu vervielfachen.

**Tragende Regel:** Mandant, Gedächtnisebene, Berechtigung,
Datenklassen-Sperre und Audit werden **oberhalb** des konkreten Speichers
durchgesetzt. Kein Speicheradapter darf diese Regeln selbst
implementieren, ändern oder überspringen — sonst entstehen so viele
Governance-Varianten wie Datenbanken.

**Heutiger Stand als Ausgangspunkt:** Die Durchsetzung liegt bereits in
`apps/backend/database.py` vor den SQL-Aufrufen (`_enforce_memory_content_policy`,
Mandantenfilter, `_validate_memory_item`) und in `permissions.py` vor dem
Datenzugriff. Das ist faktisch schon die geforderte Reihenfolge — was
fehlt, ist die Trennung von SQLAlchemy.

**Schrittfolge (Vorschlag, jeweils eigene Freigabe)**

| Schritt | Inhalt | Risiko |
|---|---|---|
| 1 | Lese-/Schreibzugriffe auf die vier Memory-Tabellen hinter eine schmale Schnittstelle legen (`MemoryRepository`), Regeln bleiben davor | gering, rein struktureller Umbau |
| 2 | Bestehende SQLAlchemy-Implementierung als erste Umsetzung dieser Schnittstelle | gering |
| 3 | Zweite Umsetzung (z. B. PostgreSQL-spezifisch) nur, wenn ein realer Bedarf besteht | mittel |
| 4 | Vektor-/Graphspeicher ausschließlich als **zusätzlicher Index** neben der führenden Tabelle, nie als alleinige Quelle | hoch — eigene Prüfung nötig |

**Ausdrücklich nicht vorgesehen:** eine Neuentwicklung des Memory-Kerns.
Schritt 1 lohnt sich nur, wenn er echte Kopplung entfernt und alle
bestehenden Tests unverändert grün bleiben. Andernfalls bleibt es beim
heutigen Aufbau.

---

## Prüfstatus dieses Dokuments

| Abschnitt | Belegt durch | Zuletzt geprüft | Prüfer | Bekannte Lücken |
|---|---|---|---|---|
| 1 — `intelligence/` | Quelltext, Tests, Migration | 2026-08-11 | Prüfung offen | 2 (keine Orchestrator-Anbindung, kein Freigabe-Endpunkt) |
| 2 — Memory-Kern | Quelltext, 32 Sicherheitstests, praktische Reproduktion | 2026-08-12 | Prüfung offen | 2 offen (B-GOV-1, B-MEM-3-Rest); B-MEM-1/2 behoben |
| 3 — `memory/` Prototyp | Quelltext, `grep` auf `include_router` | 2026-08-11 | Prüfung offen | 3 (kein RBAC, kein `tenant_id`, kein Audit) — Grund der Quarantäne |
| 4 — Zielarchitektur | keine — reine Absicht | 2026-08-12 | Prüfung offen | vollständig HANDOFF |

**Prüfer:** Für keinen Abschnitt liegt bislang eine namentliche
menschliche Abnahme vor. Der Status lautet deshalb durchgehend
**Prüfung offen** — die technische Verifikation (Tests, Reproduktion,
unabhängige Gegenprüfung durch einen zweiten Agenten) ersetzt keine
personelle Freigabe.

Jede Aussage dieses Dokuments wurde gegen den Quelltext geprüft und
zusätzlich unabhängig gegengeprüft. Im ersten Entwurf wurden dabei vier
Falschaussagen gefunden und korrigiert — insbesondere die zunächst
fälschlich behauptete durchgängige Mandantenfilterung und die Reichweite
der Datenklassen-Sperre (daraus wurden B-MEM-1 und B-MEM-2).

**Nicht geprüft:** ob eine Modul-Registry oder ein automatischer
Doku-Drift-Test eingeführt werden soll. Beides existiert im Repository
derzeit nicht; dieses Dokument wird daher von Hand gepflegt.
