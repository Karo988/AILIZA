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

**Bekannte Lücken**

- **B-MEM-1: Sperrliste greift nicht im Memory-Kern.** `classify()` und
  damit `_BLOCKED_CLASSES` werden nur in `store_fact()`
  (`reflection_facts`) angewendet, nicht in `create_memory_item()` oder
  `confirm_memory_suggestion()`. Ein Inhalt der Klassen `CREDENTIALS`,
  `SPECIAL_CATEGORY`, `HR` oder `LEGAL` würde beim direkten Schreiben in
  `memory_items` nicht automatisch abgewiesen.
  Belegstelle: `apps/backend/database.py` (`create_memory_item`,
  `confirm_memory_suggestion`) gegen
  `apps/backend/reflection/reflection_skill.py:50`.
- **B-MEM-2: Mandantenfilterung nicht durchgängig.**
  `get_memory_item(item_id)` filtert ausschließlich nach `id`, ohne
  `tenant_id`. Zusätzlich hat `memory_visibility` gar keine
  `tenant_id`-Spalte, und in `memory_items` ist `tenant_id`
  `nullable=True`.
  Belegstelle: `apps/backend/database.py:1595`,
  `apps/backend/db_schema.py:306` und `:327`.
- **B-MEM-3: Permission-Evaluator noch nicht angebunden.** Die Anbindung
  des Memory-Kerns an `apps/backend/permissions.py` hat laut `README.md`
  (Zeile 53) noch nicht begonnen; Voraussetzung ist eine
  Produktions-Bestandsprüfung der Memory-Invarianten.

Diese drei Punkte sind **Befunde, keine Behauptungen über geplante
Arbeit**. Sie sind hier dokumentiert, nicht behoben — eine technische
Behebung wäre eine eigene Aufgabe mit eigener Freigabe.

**Referenzdateien:** `apps/backend/db_schema.py` (Zeilen 288–366),
`apps/backend/database.py` (`confirm_memory_suggestion`,
`create_memory_item`), `apps/backend/reflection/reflection_skill.py`,
`apps/backend/routers/memory.py` (siehe Abschnitt 3)

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

## Prüfstatus dieses Dokuments

| Abschnitt | Belegt durch | Zuletzt geprüft | Bekannte Lücken |
|---|---|---|---|
| 1 — `intelligence/` | Quelltext, Tests, Migration | 2026-08-11 | 2 (keine Orchestrator-Anbindung, kein Freigabe-Endpunkt) |
| 2 — Memory-Kern | Quelltext `db_schema.py`, `database.py` | 2026-08-11 | 3 (B-MEM-1, B-MEM-2, B-MEM-3) |
| 3 — `memory/` Prototyp | Quelltext, `grep` auf `include_router` | 2026-08-11 | 3 (kein RBAC, kein `tenant_id`, kein Audit) — Grund der Quarantäne |

Jede Aussage dieses Dokuments wurde gegen den Quelltext geprüft und
zusätzlich unabhängig gegengeprüft. Dabei wurden vier Falschaussagen im
ersten Entwurf gefunden und korrigiert — insbesondere die zunächst
fälschlich behauptete durchgängige Mandantenfilterung und die
Reichweite der Datenklassen-Sperre (jetzt B-MEM-1 und B-MEM-2).

**Nicht geprüft:** ob eine Modul-Registry oder ein automatischer
Doku-Drift-Test eingeführt werden soll. Beides existiert im Repository
derzeit nicht; dieses Dokument wird daher von Hand gepflegt.
