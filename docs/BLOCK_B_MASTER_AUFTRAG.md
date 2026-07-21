# AILIZA Block B — Master-Auftrag für den ausführenden Agenten

## Kontext (kurz)

AILIZA hat ein fertiges Datenbank-Fundament: `users`, `user_settings`, `memory_items`,
`memory_sources`, `memory_visibility`, `memory_suggestions` (Mini-PR 1-3, alle in
`main` gemergt). `decide_memory_storage()` und `confirm_memory_suggestion()` existieren
bereits in `apps/backend/database.py`, werden aber **nirgends im echten Betrieb
aufgerufen**. Ziel dieser Woche: Architektur *fertig und stabil* machen — nicht UI.

Referenzen zum Lesen vor Start:
- `docs/DATABASE_MEMORY_GOVERNANCE_V1.md` (Gesamtkonzept)
- `docs/ROADMAP_ENTSCHEIDUNG_AUTARK_ZUERST.md` (autark first, Cloud optional)
- `apps/backend/database.py` (Suche nach `decide_memory_storage`, `confirm_memory_suggestion`,
  `create_memory_suggestion`, `get_user_settings`)
- `tests/test_memory_suggestions.py`, `tests/test_memory_core_schema.py`, `tests/test_user_settings.py`

## Zeitrahmen

Karo hat noch ~1 Woche auf diesem PC, überträgt danach alles per Git auf einen neuen PC.
Kein Blocker, aber: **Architektur muss diese Woche fertig UND stabil sein** — Priorität
liegt klar auf Backend-Vollständigkeit, nicht auf UI.

## Modell-Empfehlung

Sonnet 5 für beide Schritte (kleine, testgetriebene Code-Arbeit, keine großen
Architektur-Entscheidungen mehr nötig).

## Muss-Regeln (gelten für beide Schritte)

- Tests zuerst schreiben (TDD), bestehende Teststruktur nutzen.
- Kleine, reviewbare PRs — Schritt 1 und Schritt 2 als **zwei getrennte PRs**.
- Vor Code-Änderungen kurz bestätigen, welche Dateien angepasst werden (Karo will das,
  auch wenn dieser Auftrag schon Freigabe für den Umfang ist — bei Unklarheiten fragen,
  nicht raten).
- Bestehende Projektmuster verwenden (siehe `/api/user-settings`, `/api/user-projects`
  als Vorbild für neue Endpunkte).
- Keine sensiblen Inhalte in Logs/Commits.
- Baseline (alle bestehenden Tests) muss nach jedem Schritt grün bleiben.
- Governance-Pipeline (Kill-Switch → Data Governance → Policy-Gateway → Redaction →
  Provider-Orchestrator) bleibt unangetastet — Block B baut zusätzlich, ersetzt nichts.

## Nicht im Scope (bewusst zurückgestellt)

- UI "Mein AILIZA-Gedächtnis" (kommt später, separater Auftrag)
- pgvector, Wissensgraph, RAG (Block C, viel später)
- Freie LLM-Extraktion — `info_kind`-Klassifikation für `decide_memory_storage()`
  muss regelbasiert/deterministisch bleiben, kein LLM-Call zur Klassifikation selbst
- Desktop-Distribution ohne Docker (Block D, eigener späterer Auftrag)

---

## SCHRITT 1: Chat-Anbindung der Speicher-Entscheidungslogik

### Ziel

`decide_memory_storage()` wird im echten `/agent/run`-Flow aufgerufen, nicht nur
isoliert getestet. Ergebnis `create_user_memory_suggestion` / `create_company_memory_suggestion`
führt zu einer **bestätigbaren Aktion** für den Nutzer (bestehendes `appendActionRow`-
Muster im Frontend, siehe `gatedTask`/`consentResend` in `apps/frontend/index.html`
als Vorbild für die Callback-Struktur).

### Branch

```text
claude/memory-chat-integration
```
Von aktuellem `main`.

### Wichtige Design-Entscheidung, die zu klären ist (Stop-Regel!)

`info_kind` (sensitive/technical/setting/user_knowledge) darf **nicht** per freiem
LLM-Call bestimmt werden. Prüfen: Kann die bestehende Redaction-/Klassifikations-Schicht
(`apps/backend/governance/data_governance.py`, `classify()`) als Signal genutzt werden,
um `info_kind` regelbasiert abzuleiten (z. B. DataClass.SENSITIVE → "sensitive",
erkannte Präferenz-Phrasen → "setting")? Falls das nicht sauber möglich ist: **stoppen
und Karo fragen**, wie `info_kind` bestimmt werden soll — nicht selbst eine neue
Heuristik erfinden, die über den bestehenden Governance-Rahmen hinausgeht.

### Umsetzungsschritte

1. Lesen: `apps/backend/main.py` — `run_agent()`, `_compliance_pre_check()`,
   bestehender `/agent/run`-Response-Aufbau (Status `login_required`/`consent_required`
   als Vorbild für einen neuen Status, z. B. `memory_suggestion_pending`).
2. Tests zuerst: Anfrage mit erkanntem, wiederverwendbarem Nutzerwissen führt zu
   `memory_suggestion` (nicht direktem `memory_item`); sensible Inhalte werden
   nie vorgeschlagen; `speichermodus=nie_automatisch` erzeugt keine automatische
   Suggestion.
3. Minimalen Hook in `run_agent()` (oder dediziertem Helper) ergänzen: nach der
   normalen Antwort `decide_memory_storage()` aufrufen (best effort, Fehler dürfen
   die eigentliche Antwort nie blockieren — Governance-Grundsatz: AILIZA antwortet
   immer, siehe frühere Karo-Vorgabe im Chat-Verlauf).
4. Frontend: minimale Anzeige "AILIZA schlägt vor, sich das zu merken" mit
   Bestätigen/Ablehnen (nutzt bestehende `appendActionRow`-Funktion, ruft
   `POST /api/memory-suggestions/{id}/confirm` bzw. `/reject` auf — neue,
   kleine Endpunkte nach `/api/user-settings`-Muster).
5. Tests laufen lassen, Baseline prüfen, committen, PR erstellen, **stoppen**.

### Akzeptanzkriterien

- Tests zuerst geschrieben.
- Sensible Inhalte erzeugen nie eine Suggestion (End-to-End, nicht nur isolierte
  Funktion).
- `speichermodus` aus `user_settings` wird im echten Flow respektiert.
- Bestehende `/agent/run`-Tests bleiben grün (keine Verhaltensänderung für
  Nutzer, die kein Gedächtnis nutzen).
- Kein LLM-Call zur `info_kind`-Klassifikation (regelbasiert/Governance-Signale).

---

## SCHRITT 2: Export & Löschung (Art. 20 / Art. 17 DSGVO)

### Ziel

`GET /api/me/export` und `DELETE /api/me` — vollständig, inklusive aller
Gedächtnis-Tabellen.

### Branch

```text
claude/user-export-deletion
```
Von `main` **nach** Merge von Schritt 1 (oder parallel von main, falls Schritt 1
noch offen ist — dann bei PR-Erstellung vermerken, dass Rebase nach Schritt-1-Merge
nötig ist, analog zur gestapelten PR-Vorgehensweise aus Mini-PR 3).

### Umfang

`GET /api/me/export` liefert (als JSON-Download, nach bestehendem Muster wie
`/admin/audit/export`):
- `users`-Stammdaten (ohne `hashed_password`)
- `user_settings`
- `user_projects`, `user_chats` (bereits vorhanden, `list_user_projects`/`list_user_chats`)
- `memory_items` (nur `scope=user_memory`, `owner_user_id=eigener User`)
- `memory_suggestions` (eigene, alle Status)

`DELETE /api/me`:
- Löscht in einer Transaktion: eigene `user_settings`, `user_projects`, `user_chats`,
  `memory_items` (soft-delete via `mark_memory_item_deleted` reicht — Governance-Kette
  prüfen, ob Hard-Delete nötig ist oder Soft-Delete + Anonymisierung genügt),
  `memory_suggestions`, TOTP-Daten.
- **Stop-Regel:** Es gibt aktuell keine physische `delete_user()`-Funktion im Projekt
  (dokumentiert in `tests/test_user_settings.py::test_no_physical_user_deletion_documented_as_noop`).
  Vor Umsetzung prüfen: Soll `DELETE /api/me` den `users`-Datensatz selbst auch löschen
  (neue Funktionalität, größerer Eingriff) oder nur alle *abhängigen* Daten löschen und
  den Account nur deaktivieren (`active=0`, bestehendes Feld)? **Bei Unklarheit: Karo
  fragen, nicht selbst entscheiden** — das ist eine Governance-Entscheidung, keine
  rein technische.
- Audit-Eintrag: nur Codes (`action="user.self_deletion_requested"`, `user_id`), nie
  Inhalte.

### Akzeptanzkriterien

- Export enthält keine `hashed_password`, keine fremden Daten.
- Löschung ist transaktional (alles oder nichts).
- Bestehende Tests bleiben grün.
- Klare Dokumentation im PR, welche Löschstrategie gewählt wurde und warum.

---

## Abschluss

Nach beiden Schritten: `docs/HANDOFF_DATENBANK_GEDAECHTNIS.md` aktualisieren
(neuer Stand für den PC-Wechsel), volle Test-Suite laufen lassen, kurze
Zusammenfassung an Karo (was fertig ist, was noch offen, was für den neuen
PC zu beachten ist — v. a. `AILIZA_DATABASE_URL` erneut setzen).
