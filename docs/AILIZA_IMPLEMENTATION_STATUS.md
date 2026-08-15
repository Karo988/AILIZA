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
| **P0 — Chat-Schutzgate: Backend + Frontend** | ✅ **verpflichtend, für `/agent/run` wirksam, Consent+Preview beide Pflicht, echte anonyme Sitzungsbindung** | Commits `937f4ce`, `98149be`, `0457e71`, `6d63f63`, `51de03f`, `365cd80`. Ohne gültigen Beleg: `status="preview_invalid"`, kein Provider-Call (am Mock belegt). `consent_approval_id`-Pfad (Fall 3) braucht jetzt **zusätzlich** einen Beleg. `/documents/agent-run` stellt sich selbst einen Beleg für den serverseitig komponierten Text aus. Frontend holt den Beleg automatisch vor jedem Senden. **Anonyme Nutzer** bekommen jetzt ein eigenes HttpOnly-Sitzungs-Cookie (`ailiza_anon_session`) statt des früheren gemeinsamen `"__anonymous__"`-Werts — ein Beleg aus Browser A ist in Browser B nachweislich nicht nutzbar (Kernbeweis in `test_anon_session_binding.py`). Volle Suite 1498 passed/0 failed. Reviews: auth-security-reviewer (mehrere Funde behoben, danach jeweils Go), pr-diff-reviewer Go | Doppel-Hash-Bindung (`source_hash`/`outbound_hash`), sichtbare/bearbeitbare Lupen-UI, Output-Governance |
| `/agent/run/stream`, `/agent/approvals/{id}/continue` | ✅ **teilweise behoben** | `AgentRuntime.stream()` rief bisher `plan_tool_calls()` mit ROHEM Text auf, ganz ohne `classify()`/`redact()` — realer, von P0 unabhängiger Fund. Commit `0e9ed5e`: `stream()` nutzt jetzt denselben Precheck wie `run()`. **Weiterhin nicht** durch den Preview-Beleg-Gate abgedeckt (nur durch classify/redact, keine Vorschau-Bindung) — `continue_after_approval`/`stream_after_approval` führen nur bereits genehmigte Tool-Calls aus, kein neuer Nutzertext | Beleg-Gate auch für Streaming-Endpunkte, falls gewollt |
| **P0 — Output-Governance (Paket D, Teil 1)** | ✅ **für die drei normalen Antwortpfade wirksam** | Commit `42f2fba`. Neue zentrale Funktion `_governance_post_check` in `main.py` ist die einzige Stelle, an der eine Providerantwort freigegeben wird: erst prüfen (Secrets strippen, `classify`, blocken bei `CREDENTIALS`/`SPECIAL_CATEGORY`), **danach** wiedereinsetzen — und nur Werte, die selbst kein Secret enthalten. `reinsert()` wird jetzt an genau einer Stelle aufgerufen; Audit-Einträge enthalten nur Metadaten. 23 Tests in `tests/test_output_governance.py`, volle Suite 1535 passed / 0 failed, `pr-diff-reviewer` GO. Zwei Befunde aus dem Sicherheitsreview vor dem Commit behoben: (a) die Prüfung an der dritten Aufrufstelle stand in `if reinsertion_map:` und fiel damit ausgerechnet ohne PII in der Eingabe aus; (b) die zugehörigen Tests nahmen wegen ihrer Formulierung den Schreibaufgaben-Kurzpfad und hätten den Fehler nicht gefangen — jetzt wird der Pfad erzwungen und die Tests sind gegen den alten fehlerhaften Zustand rot verifiziert. | **Offen (Teil 2): Streaming und `_ask_llm_directly`** |
| PII in Audit-Logs der Tool-Endpunkte | ✅ | Commit `8496aaa`: `/tools/search` und `/tools/fetch` schrieben rohe Suchanfrage bzw. vollständige URL (inkl. Tokens im Query-String) ins Audit. Jetzt nur Länge/Host + HMAC-Fingerprint über `AILIZA_LOG_HMAC_KEY`; ohne Schlüssel gar kein Fingerprint. 5 Tests, volle Suite 1449 passed/0 failed | erledigt |
| `_ask_llm_directly()` ohne Provider-Kontext | ✅ **behoben** | Der Aufruf übergab dem Orchestrator kein `context`, das Capability-Gate arbeitete deshalb mit `PUBLIC`/`redaction_applied=False` — also blind. Jetzt wird ein `_LLMGovernanceKontext` mit echter Klassifikation, Mandant, Nutzerin und Redaction-Status durchgereicht. Fehlt er, wird er aus dem Text abgeleitet statt auf `PUBLIC` zu raten; scheitert die Klassifikation, gilt die strengste Klasse (unbekannt = schlimmster Fall). Wichtig: die Klassifikation nutzt den **Rohtext**, nicht den geschwärzten — sonst wäre die Schwärzung selbst der Gateway-Bypass. |
| `safe_stream.py` / `output_guardrail` | ✅ **entfernt (begründet)** | Das Modul war token-basiert (Satz-/Absatzpufferung), der reale Streaming-Pfad liefert aber vollständige `stream_event`-Strukturen — es hätte nie gepasst. Sein `output_guardrail` war zudem ein Ja/Nein-Abbruch des gesamten Stroms; die Governance arbeitet feldweise. 0 Aufrufer, 0 Tests. Ein totes Modul, das Schutz suggeriert, ist schlechter als keines, deshalb entfernt statt künstlich verdrahtet; die Schutzlogik liegt jetzt in `_gepruefter_ereignisstrom`. |
| Telegram-Ausgang | ✅ **fail-closed geschlossen** | Der externe Anbieter-Aufruf ist aus `telegram_gateway._run_agent()` entfernt. Telegram kann die Prüf-/Freigabeansicht der Weboberfläche nicht gleichwertig abbilden (kein sichtbarer bereinigter Versandtext, keine Bearbeitung, keine Freigabe) — und die Antwort ging zusätzlich ohne Ausgangsprüfung an die Telegram-Server. Statt eines schwächeren Sondergates bleibt der Weg zu, mit konkretem Alternativweg für die Nutzerin. Lokale Antworten und alle Kommandos bleiben. Gegenprobe: beim testweisen Zurückbauen schlagen 3 Tests fehl | Wiederöffnen erst, wenn eine gleichwertige Prüf-/Freigabeansicht existiert |
| **Egress-Wachhund** | ✅ neu | `tests/test_outbound_egress_allowlist.py`: findet per AST alle Netzwerkausgänge in `apps/backend` und prüft sie gegen eine begründete Allowlist (9 Module). Fand bei der eigenen Entwicklung drei reale Blindstellen: nicht aufgelöste Import-Aliasse (`import requests as http_requests` → Telegram-Ausgang unsichtbar), fehlende SDK-Erkennung (`client.messages.create` → alle Anthropic-Ausgänge unsichtbar), und stilles Überspringen unlesbarer Dateien (UTF-8-BOM in `agent/api_client.py` → Datei mit echtem Anbieter-Aufruf unsichtbar; jetzt fail-closed). Bekannte Grenze im Modul dokumentiert: dynamisch gebaute Aufrufe rutschen durch | — |
| **Streaming-Governance (Paket D, Teil 2)** | ✅ **Gate + Ausgangsprüfung wirksam** | `/agent/run/stream` verlangt jetzt serverseitig einen gültigen Prüfbeleg (derselbe `send_preview_store`, kein zweiter Belegweg). Die **GET-Variante ist entfernt** — sie transportierte den Aufgabentext als `?task=...` und damit in Zugriffsprotokolle, Browser-Verlauf und Referrer; das ist durch kein Backend-Gate reparierbar. Jedes Streaming-Ereignis läuft vor dem Senden durch `_gepruefter_ereignisstrom`; `tenant_id` ist an `sse_response()` ein Pflichtargument, damit eine künftige neue Route die Prüfung nicht vergessen kann. Die drei Fortsetzungs-Routen nach Freigabe sind ebenfalls angeschlossen (Freigabe einer Aktion ist keine Freigabe späterer Inhalte). Zusätzlich prüft `/agent/run` jetzt auch `steps` und `results` — Tool-Ergebnisse und abgerufene Webinhalte gingen bisher ungeprüft an die Anzeige. Belege: `tests/test_streaming_governance.py` (27 Tests), Gegenprobe gegen den alten Zustand = 8 rote Tests. |
| **Vollständige Egress-Inventur** | ✅ erstellt | 9 Module mit Netzwerkausgang, alle gelistet. **Ohne Prüfbeleg laufen weiterhin:** `/agent/run/stream` (GET+POST, → Tavily + URL-Abruf + LLM, größte Lücke), `/agent/approvals/{id}/continue(/stream)`, `/tools/search`, `/tools/fetch`. Zusätzlich: Provider-Failover und der Prüfer-Zweitcall (`gated_client.py:310`) senden denselben Text an **weitere** Anbieter, der Beleg wird aber nur einmal am Eingang verbraucht. `/api/debug/groq-diagnosis` ist in **jeder** Umgebung registriert (fester Testprompt, kein Nutzinhalt) — anders als `/api/debug/provider-test`, das nur außerhalb Produktion registriert wird | Diese Ausgänge an den zentralen Vertrag anbinden (Rest von Paket C) |
| Output-Governance (neu erzeugte PII) | ✅ für `/agent/run` | Commit `42f2fba`: die Modellantwort wird vor der Wiedereinsetzung erneut klassifiziert, vom Modell **neu erzeugte** Zugangsdaten und besondere Kategorien werden blockiert. **Noch nicht abgedeckt:** der Streaming-Pfad (`/agent/run/stream`) und die Härtung von `_ask_llm_directly` | Paket D, Teil 2 |
| Rohe Tool-Parameter in `approval_requests` | ⚠️ offen | `gateway.py:65-70` speichert `input_params` roh in der Datenbank (nicht im Log) — bei PII-haltigen Suchanfragen/URLs liegt das dort im Klartext | Produktentscheidung: Redaction vor Speicherung oder bewusst akzeptieren |
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

### 2026-08-14 — P0-Vorarbeiten: Audit-Fund + Prüfbeleg-Baustein

**Ist-Audit (3 Subagenten parallel, read-only).** Wichtigste Korrektur an der
ursprünglichen Annahme: Im heutigen Chat-Pfad laufen Prüfung und Versand
**synchron im selben Request** (`main.py:1872 → 1886`) — es gibt gar kein
Zeitfenster zwischen „geprüft" und „gesendet". Mehrere der befürchteten
Lücken (Invarianten 4, 8, 9, 10, 12) sind deshalb heute bereits erfüllt. Der
Prüfbeleg wird erst durch die **neue** Bedienung nötig, bei der die Nutzerin
den bereinigten Text bearbeitet und diesen sendet. Er sichert also die
künftige Bedienung ab und schließt keine heute offene Lücke — das ist bewusst
so benannt und nicht als „Sicherheitslücke geschlossen" dargestellt.

**Ungeplanter, aber realer Fund (behoben, `8496aaa`).** `/tools/search` und
`/tools/fetch` schrieben die rohe Nutzereingabe ins Audit-Log. Erste Fassung
nutzte einen einfachen SHA-256-Fingerprint; der Sicherheitsreview wies zu
Recht darauf hin, dass der per Wörterbuchangriff umkehrbar ist. Nachgehärtet
auf HMAC mit dem bestehenden Logging-Schlüssel, gleiches Muster wie
`_mask_user_id_for_log()`.

**Baustein 1 (`937f4ce`).** `governance/send_preview.py` mit 26 Tests:
Bindung an Nutzer/Mandant/Zweck/Text-Hash, Einmalnutzung, TTL, echter
Nebenläufigkeitstest (8 gleichzeitige Threads, genau einer kommt durch),
Unicode-NFC- und Zeilenenden-Normalisierung ohne echte Änderungen zu
verschlucken, Speicherobergrenze. **Noch nicht verdrahtet.**

**Betriebsgrenze, offen dokumentiert:** Der Prüfbeleg liegt prozesslokal im
Arbeitsspeicher. Bei mehreren Workern bricht der Versand sicher ab statt
falsch durchzugehen — keine Lücke, aber eine Fehlbedienung. Passt zur
bestehenden Ein-Worker-Vorgabe in `render.yaml`. Eine mehrprozessfähige
Variante bräuchte gemeinsamen Speicher und damit neue Infrastruktur; das ist
bewusst nicht Teil dieses Pakets.

**Noch offen für P0** (siehe Statustabelle): Verdrahtung in den Versandpfad,
Frontend-Zustandsautomat, Output-Governance, `_ask_llm_directly`-Kontext,
Entscheidung zu `safe_stream`. Die Folgepakete P1A (Navigation), P1B
(Einstellungen) und P2 (Gate-1B-Vorlage) sind **nicht begonnen**.
