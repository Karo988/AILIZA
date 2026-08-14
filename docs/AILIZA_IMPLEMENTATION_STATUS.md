# AILIZA Implementation Status

Zentrale Wahrheitsquelle für den tatsächlichen Umsetzungsstand — verbindlich für
Codex, Claude Code und jede weitere Session. Das Claude-Artifact (interaktive
Aufgaben-/Freigabeoberfläche) bleibt als Erklärung/Verlaufsprotokoll bestehen,
ist aber **nicht** mehr die Wahrheitsquelle.

**Regel:** ✅ nur mit konkretem Nachweis (Commit, Testlauf, Befehlsausgabe).
Ohne Nachweis: ⚠️ (offen/unklar) oder ⏸️ (Entscheidung fehlt).

## Sitzungsregel

Jede Code-Sitzung:
1. Liest zu Beginn diese Datei.
2. Aktualisiert sie am Ende mit ausgeführten Arbeiten, Tests, Commit-ID und
   offenen Punkten.
3. Markiert nichts als ✅ ohne konkreten Nachweis.

## Status

| Aufgabe | Status | Nachweis | Nächster Schritt |
|---|---|---|---|
| SQLite-Fremdschlüssel (PRAGMA foreign_keys=ON) | ✅ | Commit `5ba59b1`, CI grün (Run 31790449908/31790447006) | erledigt |
| Fixture-Fix (Windows-Cleanup) | ✅ | Commit `73c46a8`, `store.close()` in Fixture, CI grün (Teil von Run für `695b02d`) | erledigt |
| Statusdatei angelegt | ✅ | Commit `695b02d`, CI grün (Run 31798105509/31798102160) | erledigt |
| Gate 1A — Memory-Audit strikt read-only | ✅ | Commit `1e6bda7`, `init_db()` aus `audit_memory_scope_cli.py` entfernt, ersetzt durch `inspect(engine).has_table()`; 14/14 Zieltests + volle Suite 1444 passed/0 failed; CI grün (Run [31806555098](https://github.com/Karo988/AILIZA/actions/runs/31806555098), `completed`/`success`); 4 Subagenten-Reviews grün (memory-invariant-reviewer ×2, pg-sqlite-migration-checker ×2, pr-diff-reviewer: GO) | **P0-Chat-Schutzgate (siehe unten) — höhere Priorität als Gate 1B, das folgt erst danach** |
| **P0 — Chat-Schutzgate (Lupe/Redaction verbindlich vor externem Versand)** | 🔄 in Arbeit | Auftrag erteilt 2026-08-14; Phase 1 (paralleler Ist-Audit) läuft | Ist-Audit abwarten, dann Sicherheitsvertrag (Phase 2) mit Karo abstimmen |
| PC synchronisieren | ⚠️ | PC zuletzt bekannt auf Commit `ea2cbd6`, veraltet gegenüber `1e6bda7`; PC-Synchronisierung ist aus dieser Cloud-Sitzung nicht prüfbar (kein Zugriff auf C:\AILIZA) | Auf dem PC: lokale Änderungen sichern, dann per Fast-forward auf `1e6bda7` synchronisieren |
| Render-Deployment | ⚠️ | ✅ Staging erreichbar: `https://ailiza-stagin.onrender.com/`, Oberfläche meldet „System aktiv". ⚠️ deployter Commit unbekannt, ⚠️ Render-Branch unbekannt, ⚠️ Datenbanktyp unbekannt, ⚠️ Alembic-Revision der Staging-Datenbank unbekannt. Render läuft laut letztem Stand auf `main`/`058fea1` — nicht auf diesem Feature-Branch | Render-Dashboard prüfen: deployter Commit, Branch, DB-Typ, Alembic-Revision |
| Migration 0007 | ⏸️ | Kein bestätigter fachlicher Bedarf, keine Tabellen `knowledge_approvals`/`claim_evidence` im Schema | Produktentscheidung: werden diese Tabellen wirklich gebraucht? |
| Scope-Berechtigungen (Memory-Scopes: session/personal/project/company) | ⏸️ | Fachliche Regeln für Scope-Übertragung fehlen | Regeln festlegen (HANDOFF, keine stillschweigende Implementierung) |
| `memory_items.tenant_id` NOT NULL | ⏸️ | Weiterhin nullable, bewusst wegen alter `user_memory`-Datensätze (`legacy_user_memory_null_tenant`). Empfehlung dieser Session: Ja, langfristig NOT NULL — aber Migration muss bei nicht eindeutig zuordenbaren Altdaten abbrechen und darf niemals automatisch `default` setzen | Backfill-Strategie ausarbeiten (owner_user_id + source_id müssen übereinstimmen), dann eigene Migration |
| CRLF / Gate 10 | ⚠️ | Ursache (CRLF vs. echte Änderung) bisher nicht am identischen Commit auf Windows bewiesen; `.gitattributes` existiert nicht im Repo | Nur bei tatsächlich rotem Gate 10 erneut untersuchen |
| Obsidian-Integration | ⛔ kein Ist-Zustand | Kein Vault, kein Connector, keine `.obsidian`/`.base`-Datei, kein `knowledge_proposal` im Repo — reines externes Konzept, keine Codebasis | Nur falls explizit als neuer Auftrag gewünscht |

## Hinweis zur Präzisierung (GitHub-CI)

Ein früherer Eintrag dieser Datei hatte GitHub-CI pauschal als ✅ markiert,
gestützt auf einen Workflow-Lauf, der vor dem PRAGMA-Commit `5ba59b1`
stattfand. Das war ein Nachweis für den Branch zu einem früheren Stand, nicht
für `5ba59b1` selbst. Präzisiert: Für `5ba59b1` liegt aktuell kein bestätigter
GitHub-Actions-Lauf vor — Status entsprechend auf ⚠️ korrigiert.

**Grundsatz:** Lokale Tests sind kein GitHub-CI- und kein
Render-Deployment-Nachweis. Ein lokal grüner Testlauf beweist nur, dass der
Code in der jeweiligen lokalen Umgebung funktioniert — nicht, dass CI ihn
bestätigt hat oder dass er irgendwo deployt ist.

## Änderungsprotokoll

### 2026-08-14 — PRAGMA-Fix + Statusdatei angelegt
- **Ausgeführt:** `PRAGMA foreign_keys=ON` auf SQLAlchemy-Engine-Connect-Hook
  (`apps/backend/database.py`) und auf direkter `sqlite3.connect()`-Verbindung
  (`apps/backend/memory/sqlite_store.py`) ergänzt; `busy_timeout=5000` auch für
  Letztere ergänzt.
- **Tests:** `tests/test_database_pragma_foreign_keys.py` neu (6 Tests: PRAGMA-
  Werte, echte abgelehnte Fremdschlüsselverletzung). Volle Suite `pytest tests/`:
  1441 passed, 3 skipped, 1 xfailed, 0 failed.
- **Commit:** `5ba59b1` auf `integration/pr86-phase1-alembic-merge`, gepusht
  (`b1c0b83..5ba59b1`). CI grün bestätigt (nachträglich).

### 2026-08-14 — Fixture-Fix + Statusdatei-Commit
- **Ausgeführt:** `TestSqliteMemoryStorePragmas.store`-Fixture ruft jetzt
  `store.close()` nach dem `yield` (vorher: SQLite-Verbindung blieb offen,
  auf Windows verhinderte das den `TemporaryDirectory`-Cleanup — reales,
  plattformspezifisches Problem, auf Linux hier nicht sichtbar).
- **Tests:** volle Suite 1444 passed, 0 failed.
- **Commits:** `73c46a8` (Fixture-Fix, isoliert), `695b02d` (Statusdatei,
  isoliert), beide gepusht, beide CI grün.

### 2026-08-14 — Gate 1A: Memory-Audit strikt read-only
- **Problem:** `apps/backend/audit_memory_scope_cli.py` bezeichnete sich als
  "rein lesend", rief aber `init_db()` auf (`database.py:193-195`), das
  `metadata_obj.create_all(engine)` und `ensure_sqlite_schema()` ausführt —
  beide können Schema anlegen/ändern (CREATE TABLE, ALTER TABLE ADD COLUMN).
  Realer Widerspruch zwischen Docstring-Versprechen und Verhalten.
- **Ausgeführt:** `init_db()`-Aufruf entfernt, ersetzt durch
  `sqlalchemy.inspect(engine).has_table("memory_items")` /
  `has_table("memory_visibility")` als reinen Lese-Check vor
  `audit_memory_scope_invariants()`. Bei fehlender Tabelle: Exit-Code 2 mit
  klarer Meldung statt stillschweigender Schema-Reparatur.
- **Subagenten-Orchestrierung (vor und nach Implementierung):**
  `memory-invariant-reviewer` (2×, vorher+Diff-Review) — grün, geprüfte
  Invarianten (`audit_memory_scope_invariants()`) unverändert, keine
  Owner/Tenant/Scope-Verschiebung. `pg-sqlite-migration-checker` (2×) — grün,
  `has_table()` dialektunabhängig (SQLite `sqlite_master` / Postgres
  `information_schema`), keine versteckte DDL-Aktion. `pr-diff-reviewer`
  (final) — **GO**, Scope exakt eingehalten (nur die 2 erlaubten Dateien),
  geschützte Dateien (`.claude/settings.json`,
  `.claude/agents/strukturplan.md`) unangetastet, `git diff --check` sauber.
  `auth-security-reviewer` nicht eingesetzt (Diff berührt keine
  Auth/Secrets/Rollen).
- **Tests:** `tests/test_memory_audit_cli.py` erweitert — neue Tests
  `test_missing_schema_exits_two_without_creating_it` (Exit-2-Beweis per
  Endzustand + erneuter frischer Verbindung), `test_audit_run_issues_no_write_sql_statements`
  (SQL-Anweisungsbeweis per `before_cursor_execute`-Event: kein
  CREATE/ALTER/DROP/INSERT/UPDATE/DELETE), `test_script_never_calls_init_db_or_creates_schema`
  (statischer Regressionsschutz). Bestehende Tests angepasst, die bisher
  implizit auf das entfernte `init_db()` im CLI angewiesen waren
  (`_init_schema_only()`-Hilfsfunktion im Testsetup ergänzt).
- **Selbstkorrektur während der Umsetzung:** Erster Entwurf des SQL-Beweistests
  nutzte `importlib.reload(apps.backend.database)` im Testprozess — das
  verseuchte die globale Engine und riss beim ersten vollen Suite-Lauf 63
  fremde Tests mit (`UNIQUE constraint failed`, Test-Isolationsbruch). Vor
  jedem Commit erkannt und behoben: Test läuft jetzt per Subprocess wie der
  Rest der Datei. Zweiter voller Lauf: 1444 passed, 0 failed.
- **Commit:** `1e6bda7` auf `integration/pr86-phase1-alembic-merge`, gepusht
  (`695b02d..1e6bda7`). CI grün: [Run 31806555098](https://github.com/Karo988/AILIZA/actions/runs/31806555098).
- **Offen für Gate 1B:** erweiterter, weiterhin rein lesender Zählbericht.
  Lauf gegen echte Docker-/Render-Daten wird erst danach separat
  vorbereitet — noch nicht begonnen.
- **PC-Stand:** unbekannt/veraltet (zuletzt `ea2cbd6` gemeldet, weit hinter
  `1e6bda7`). Ein separater Auftrag an eine Sitzung mit `C:\AILIZA`-Zugriff
  wurde vorbereitet, aber nicht von dieser Sitzung ausgeführt (kein
  Dateisystemzugriff auf den PC von hier aus).
