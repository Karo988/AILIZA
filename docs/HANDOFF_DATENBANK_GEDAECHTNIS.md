# AILIZA — Übergabe-Dokument: Datenbank & Gedächtnis

> **Historischer Detailstand.** Nicht als Einstieg für neue Tasks verwenden.
> Aktueller Einstieg: `docs/AILIZA_HANDOFF_ENTWICKLUNG.md`. Für persönliches
> Lernen zusätzlich `docs/AILIZA_HANDOFF_ANWENDER.md` lesen.

Stand: 30.07.2026 · Für den nächsten Agenten oder PC-Wechsel.

---

## 0. Memory-Kern-Härtung (M0–M2), Stand main @ `133c07a4ff99fc6120450ecd3c22a8d41685e005`

Nach diesem Dokument begann ein mehrteiliger Härtungs-Auftrag für den
fachlichen Memory-Kern (`memory_items`/`memory_sources`/`memory_visibility`/
`memory_suggestions` in `apps/backend/database.py`). Ausführliche fachliche
Erklärung: Skill `ailiza-wissen`.

| PR | Inhalt | Status |
|---|---|---|
| **#64** (M0) | Technischer Memory-Prototyp-Router (`apps/backend/routers/memory.py`, eigenständiges `MemoryEntry`-Modell in `apps/backend/memory/*`) fail-closed quarantänisiert — war nie in `main` registriert, hatte einen fehlerhaften `require_admin`-Import. **Kein** Bezug zu `user_memory`/`company_memory`. | ✅ gemergt |
| **#65** (M1) | Scope-/Owner-/Tenant-Invarianten im fachlichen Memory-Kern korrigiert: `company_memory` mit `owner_user_id` wird abgelehnt, `list_active_memory_items_for_user()` filtert jetzt explizit auf `scope="user_memory"`, Legacy-`user_memory` mit `tenant_id=NULL` bleibt für den Owner sichtbar/exportierbar/löschbar. Neue read-only Funktion `audit_memory_scope_invariants()`. | ✅ gemergt |
| **#66** | CLI-Entrypoint `apps/backend/audit_memory_scope_cli.py` für den Bestands-Audit (`--json`, Exit-Codes 0/1/2). | ✅ gemergt |
| **#67** | Manueller GitHub-Actions-Workflow (`workflow_dispatch`) für den Produktions-Audit gegen die echte Render/Neon-DB, mit `--summary-only`-Flag (keine internen IDs im öffentlichen Log). | ✅ gemergt |

**Aktueller Blocker vor "M2" (Anbindung des Memory-Kerns an den zentralen
Permission-Evaluator `apps/backend/permissions.py` + Sichtbarkeitsdurchsetzung):**
Der Produktions-Audit gegen die echte Datenbank wurde **noch nicht
ausgeführt**. Nötig, bevor M2 beginnt:
1. GitHub-Secret `AILIZA_DATABASE_URL_AUDIT` anlegen (idealerweise ein
   separater, read-only Neon-DB-Nutzer).
2. Workflow „Memory-Scope-Audit (manuell, Produktions-Datenbank)" manuell
   auslösen (Actions-Tab → workflow_dispatch).
3. Exit-Code auswerten: `0` → M2 vorbereiten; `1` → keine M2-Arbeit, erst
   Report/Verletzungen auswerten; `2` → Zugriff/Konfiguration reparieren,
   erneut ausführen.

**Wichtig, falls diese Datei mit älterem Kontext gelesen wird:** Frühere
Beschreibungen von `apps/backend/memory/models.py`/`store.py`/
`sqlite_store.py` (eigenständiges `MemoryEntry`-Modell mit `content_hash`,
`MemoryPurpose`, `VisibilityLevel`) als Referenz für die
`user_memory`/`company_memory`-Architektur sind **falsch** — das ist ein
separates, kleineres, nie produktiv eingebundenes System (siehe PR #64).
Ebenso ist `temporary_only` (in `decide_memory_storage()`) nur ein
Rückgabewert, keine eigene Tabelle, kein Konsolidierungsmechanismus — ein
literaler „Konsolidierung"-Mechanismus ist im aktuellen Code nicht belegt.

---

## 1. Roadmap-Entscheidung (gilt, bis Karo sie ändert)

Siehe `docs/ROADMAP_ENTSCHEIDUNG_AUTARK_ZUERST.md`: AILIZA wird primär **autark**
gebaut (SQLite in `/data`-Docker-Volume), nicht als Cloud-Produkt. Neon/Postgres ist
nur Übergangslösung für Render-Staging. Zukunftsziel (separater, noch nicht
begonnener Auftrag): Desktop-Distribution ohne Docker-Pflicht (Block D).

## 2. Gemergt in `main` (Block A, fertig)

- Postgres-Verbindungs-Fix (`pool_pre_ping`)
- Autarker Betrieb (SQLite `/data`-Volume, `docker-compose.yml`, PR #42)
- Memory-Kernschema: `memory_items`, `memory_sources`, `memory_visibility` (PR #44)
- Kontrolliertes Lernen: `memory_suggestions`, `decide_memory_storage()`,
  `confirm_memory_suggestion()` (PR #45)
- `user_settings` getrennt von `users` (PR #43)
- Vollständig verifiziert: alle Tabellen entstehen automatisch, Daten überleben
  Neustart (lokal ohne Docker-Daemon getestet, da hier keiner verfügbar war —
  auf echtem PC mit `docker compose up -d` verifizieren).

## 3. Block B — Chat nutzbar machen (✅ komplett gemergt in `main`)

| PR | Status |
|---|---|
| **#46** Chat-Anbindung der Speicher-Entscheidungslogik | ✅ gemergt |
| **#47** Export & Löschung (Art. 20/17 DSGVO) | ✅ gemergt |
| CI-Fix (verwaister `apps/backend/tests/`-Schritt deaktiviert) | ✅ gemergt |

Baseline nach beiden Merges: **936/936 Tests grün**, CI (GitHub Actions,
Schritt "Tests (Root)") ebenfalls grün.

### PR #46 — Chat-Anbindung der Speicher-Entscheidungslogik
- `decide_memory_storage()` läuft jetzt im echten `/agent/run`-Flow (dünner
  Wrapper `run_agent()` um umbenanntes `_run_agent_core()`, best effort,
  kann die Antwort strukturell nie blockieren).
- `info_kind`-Klassifikation: **kein LLM**, nutzt bestehende `classify()`
  (Governance) + feste Regel für Einstellungs-Phrasen.
- Neue Endpunkte: `GET /api/memory-suggestions`, `POST .../confirm`, `.../reject`.
- Minimale Frontend-Anzeige (bestehendes `appendActionRow`-Muster).
- 16 neue Tests, Baseline 926/926 grün.

### PR #47 — Export & Löschung (Art. 20 / Art. 17 DSGVO)
- `GET /api/me/export`, `DELETE /api/me`.
- **Karo-Entscheidung:** Löschung deaktiviert Account (`active=0`) + löscht
  abhängige Daten. **Kein** hartes Löschen von `users` in dieser PR.
- `delete_own_account_data()` ist eine **echte Transaktion** (eine `engine.begin()`),
  nicht mehrere unabhängige Aufrufe — alles-oder-nichts getestet.
- 10 neue Tests, Baseline 936/936 grün.

## 4. Offene Governance-Entscheidungen (keine Blocker, nur zur Info)

- Physische `users`-Löschung ist weiterhin **nicht** implementiert (bewusst,
  Karo-Entscheidung für PR #47). Falls später gewünscht: eigener, neuer Auftrag.
- Firmenwissen-Suggestions (`create_company_memory_suggestion`) sind in der
  Entscheidungslogik vorhanden, aber die Chat-Anbindung (PR #46) erzeugt aktuell
  nur `user_memory`-Vorschläge — Firmenwissen-Erkennung im Chat ist noch nicht
  angebunden (bewusst kleiner Schnitt, siehe PR-#46-Beschreibung).

## 4b. Block C — Wissensdatenbank (Details siehe `docs/AGENT_HANDOFF_BLOCK_C1_ABGESCHLOSSEN.md`)

| Phase | Status |
|---|---|
| C1 Wissensquellen-Schema (`knowledge_sources`, `knowledge_chunks`, `knowledge_source_permissions`) | ✅ gemergt (PR #48) |
| C2 Sichere TXT/Markdown-Ingestion (`apps/backend/knowledge/ingestion.py`) | ✅ gemergt (PR #49) |
| C3 Lokale Suche (`apps/backend/knowledge/search.py`, `search_knowledge_chunks()`) | ✅ gemergt (PR #50) |
| C4 Interne Wissensquellen im Chat mit Quellenanzeige (`apps/backend/knowledge/rag_context.py` + Anbindung in `main.py`) | ✅ implementiert, PR folgt (Branch `claude/knowledge-rag-with-sources`) |

**C4 kurz:** `run_agent()` baut best-effort Chat-Kontext aus freigegebenen Wissensquellen
(`_maybe_build_knowledge_context()`), injiziert ihn (max. 3 Snippets, max. 800 Zeichen,
je Snippet erneut gegen `EXTERNAL_LLM` klassifiziert) in `effective_task` innerhalb
`_run_agent_core()`, und hängt nach der Antwort Quellenliste/`answer_mode` an
(`_attach_knowledge_result()`). Fehler an jeder Stelle → normaler Chat läuft unverändert
weiter. Keine Websuche, kein pgvector, keine Embeddings, kein Wissensgraph, keine UI.

## 5. Zurückgestellt (separate spätere Aufträge)

- UI-Panel "Mein AILIZA-Gedächtnis" (reine Sichtbarkeit, ändert nichts an der
  Architektur — kann jederzeit nachgezogen werden)
- Block C5: Optionale Vektorsuche (pgvector) — nur nach expliziter Freigabe
- Websuche/Internetrecherche als eigene, spätere Capability (eigene Leitplanken,
  siehe `docs/AGENT_HANDOFF_BLOCK_C1_ABGESCHLOSSEN.md` Abschnitt 4) — bewusst
  nicht Teil von Block C
- Block D: Desktop-Distribution ohne Docker (gepackte ausführbare Datei)
- **`apps/backend/tests/` aufräumen:** Verwaister Ordner, kaputte Imports auf
  nicht mehr existierende Module (`compliance_auditor`, `KillSwitch`,
  `policy_engine`, `policies.pii_taxonomy`, `governance`, `main`,
  `require_operator`). Wird aktuell **nicht** als Pflicht-CI ausgeführt
  (Schritt in `.github/workflows/ci.yml` bewusst auskommentiert, nicht
  gelöscht). Ordner selbst existiert weiterhin unverändert im Repo. Später
  in einem eigenen, kleinen Auftrag entscheiden: löschen oder reparieren.

## 6. Wichtiger Hinweis für PC-Wechsel

Nach Übertragung auf den neuen PC: **`AILIZA_DATABASE_URL` erneut setzen**
(z. B. `sqlite:////data/ailiza.sqlite` für autarken Betrieb per Docker, oder
lokaler Pfad für direkten Python-Start). Ohne diese Variable warnt AILIZA und
fällt auf einen relativen Dev-Pfad zurück (kein Datenverlust-Risiko in
Production ohne explizite Warnung, siehe `_resolve_database_url()` in
`apps/backend/database.py`).

## 7. Arbeitsregeln (aus CLAUDE.md, unbedingt einhalten)

- Erst fragen, dann programmieren — bei Unklarheit Karo fragen, nicht raten.
- TDD: Tests zuerst, dann Code.
- Jede Antwort nennt die Modell-Empfehlung explizit (Sonnet 5 = Standard).
- Kleine, einzeln bestätigte PRs statt große Umbauten.
- Keine Secrets/PII in Logs oder Commits.

---

*Für den nächsten Agenten: Diese Datei ist der schnellste Weg, ohne Kontextverlust
weiterzumachen. Bei Unklarheiten: Karo fragen.*
