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
| SQLite-Fremdschlüssel (PRAGMA foreign_keys=ON) | ✅ | Commit `5ba59b1` existiert auf GitHub (Branch `integration/pr86-phase1-alembic-merge`); 1441 Tests lokal in der Claude-Code-Umgebung bestanden (`tests/test_database_pragma_foreign_keys.py` 6/6, volle Suite 1441 passed / 0 failed). **Lokale Tests sind kein GitHub-CI- und kein Render-Deployment-Nachweis.** | GitHub-Actions-Lauf für `5ba59b1` bestätigen; danach Render-Deployment prüfen |
| PC synchronisieren | ⚠️ | PC auf Commit `ea2cbd6`; PC-Synchronisierung ist nicht in dieser Cloud-Sitzung prüfbar (kein Zugriff auf C:\AILIZA) | Auf dem PC selbst: lokale Änderungen sichern, dann auf `5ba59b1` synchronisieren |
| GitHub-CI | ⚠️ | Für `5ba59b1` ist kein GitHub-Actions-Lauf nachgewiesen. (Ein früherer Lauf auf demselben Branch vor diesem Commit war grün — das ist kein Nachweis für `5ba59b1` selbst.) | GitHub-Actions-Lauf für `5ba59b1` gezielt prüfen |
| Render-Deployment | ⚠️ | ✅ Staging erreichbar: `https://ailiza-stagin.onrender.com/`, Oberfläche meldet „System aktiv". ⚠️ deployter Commit unbekannt, ⚠️ Render-Branch unbekannt, ⚠️ Datenbanktyp unbekannt, ⚠️ Alembic-Revision der Staging-Datenbank unbekannt | Render-Dashboard prüfen: deployter Commit, Branch, DB-Typ, Alembic-Revision |
| Migration 0007 | ⏸️ | Kein bestätigter fachlicher Bedarf, keine Tabellen `knowledge_approvals`/`claim_evidence` im Schema | Produktentscheidung: werden diese Tabellen wirklich gebraucht? |
| Scope-Berechtigungen (Memory-Scopes: session/personal/project/company) | ⏸️ | Fachliche Regeln für Scope-Übertragung fehlen | Regeln festlegen (HANDOFF, keine stillschweigende Implementierung) |
| CRLF / Gate 10 | ⚠️ | Ursache (CRLF vs. echte Änderung) bisher nicht am identischen Commit auf Windows bewiesen; `.gitattributes` existiert nicht im Repo | Nur bei tatsächlich rotem Gate 10 erneut untersuchen |

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
  (`b1c0b83..5ba59b1`).
- **Offen:** CI-Lauf für `5ba59b1` selbst noch nicht bestätigt (nur für den
  Stand davor); Render-Deploy-Status unbekannt; PC-Sync ausstehend.
