# AILIZA Agent-Handoff: Block C (C1–C4, alle gemergt) + Block D0 (Demo-UI)

**Status:** PR #48 (Schema), PR #49 (TXT/Markdown-Ingestion), PR #50 (lokale Suche) und PR #51 (interne Wissensquellen im Chat mit Quellenanzeige) sind **alle gemergt**. Block D0 (kleine Demo-/UI-Schicht "Firmendatenbank") ist implementiert, 1077/1077 Tests grün, PR wird als nächstes erstellt (siehe Abschnitt 8).

**Zielgruppe:** Karo selbst (Priorisierung) und/oder nächster Agent.

---

## 1. Wo wir stehen

```
Block A (Autarker Betrieb, Memory-Kernschema)        ✅ gemergt
Block B (Chat-Anbindung, Export/Löschung DSGVO)       ✅ gemergt
Block C1 (Wissensquellen-Schema)                      ✅ gemergt (PR #48)
Block C2 (TXT/Markdown-Ingestion)                     ✅ gemergt (PR #49)
Block C3 (Lokale Suche)                               ✅ gemergt (PR #50)
Block C4 (RAG mit Quellen)                            ✅ gemergt (PR #51)
Block C5 (Optionale Vektorsuche)                      ⏳ nur nach expliziter Freigabe
Block D (Desktop-Distribution ohne Docker)            ⏳ separater, späterer Auftrag
Websuche/Internetrecherche                            ⏳ spätere, eigene Capability (siehe Abschnitt 4, Leitplanken)
Empfohlener Folgeschritt: kleine UI-/Demo-Schicht      ⏳ noch nicht beauftragt (siehe Abschnitt 5)
```

## 2. Block C2 — was gebaut wurde (zur Erinnerung, bereits gemergt)

**Modul:** `apps/backend/knowledge/ingestion.py` · **Tests:** `tests/test_knowledge_txt_md_ingestion.py` (23)

- `ingest_txt_or_markdown_source()` — einziger Einstiegspunkt, nur `.txt`/`.md`
- `ALLOWED_KNOWLEDGE_EXTENSIONS = {".txt", ".md"}`, `MAX_KNOWLEDGE_FILE_BYTES = 2_000_000`
- Originaldatei unter `/data/uploads`, DB speichert nur Metadaten
- Speicherpfad nie aus Nutzer-Dateinamen gebaut → Pfad-Traversal strukturell ausgeschlossen
- Fail-closed über bestehende Governance (`classify()` + `check_data_target` + `needs_review`): blocked/pending_review/approved

## 3. Block C3 — was gebaut wurde

**Branch:** `claude/knowledge-local-search` · **Modul:** `apps/backend/knowledge/search.py` · **Tests:** `tests/test_knowledge_local_search.py` (20 neu) · **Baseline:** 999/999 Tests grün.

- `search_knowledge_chunks(*, tenant_id, requester_user_id, query, requester_roles=None, project_id=None, limit=10)` — einziger Einstiegspunkt
- Reine lokale Substring-Relevanz (Vorkommenszählung der Suchbegriffe je Chunk), keine Bibliothek, keine Embeddings, keine externen Aufrufe
- Nur Quellen mit `status="approved"` werden überhaupt betrachtet — blocked/deleted/expired/pending_review sind strukturell ausgeschlossen (Filter direkt in der DB-Abfrage, nicht nachträglich)
- Sichtbarkeit über `knowledge_source_permissions`:
  - `private` → nur Uploader/`created_by`
  - `project` → nur bei übereinstimmender `project_id`
  - `team`/`organization` → alle im selben Tenant (Mandantengrenze ist bereits vorher hart durchgesetzt)
  - `external_limited` → nur `allowed_user_ids`/`allowed_roles`
  - **Kein Permission-Eintrag vorhanden → fail-closed: nur der Uploader sieht die Quelle**
- Ergebnis je Treffer: `source_id`, `chunk_id`, `title`, `snippet`, `score`, `source_type`, `visibility_scope`, `status`
- Kein Treffer → `message = "Ich habe in freigegebenen Quellen nichts Passendes gefunden."`
- Nicht freigegebene Quellen werden nie angezeigt, angedeutet oder zitiert (vollständig aus der Ergebnismenge ausgeschlossen, nicht nur redigiert)
- Kein RAG, keine Antwortgenerierung, keine UI, kein pgvector, keine Embeddings, kein Wissensgraph
- **Docker-Test:** nicht möglich (Daemon in der Sandbox nicht erreichbar) — auf echtem PC mit `docker compose up -d` verifizieren

**PR-Status:** #48, #49, #50 alle gemergt.

## 4. Block C4 — was gebaut wurde

**Branch:** `claude/knowledge-rag-with-sources` · **Module:** `apps/backend/knowledge/rag_context.py` (neu) + Anbindung in `apps/backend/main.py` · **Tests:** `tests/test_knowledge_rag_context.py` (24 neu) + `tests/test_knowledge_chat_rag_integration.py` (11 neu) · **Baseline:** 1034/1034 Tests grün.

**`apps/backend/knowledge/rag_context.py` (reine, isolierte Logik):**
- `build_knowledge_context()` — ruft `search_knowledge_chunks()` best-effort auf, re-klassifiziert jedes Snippet gegen `DataTarget.EXTERNAL_LLM` (zusätzlich zur Ingestion-Prüfung gegen `FILE_STORAGE`), wendet Budget an (max. 3 Snippets, max. 800 Zeichen gesamt — bereits vorhandenes 160-Zeichen-Einzel-Snippet-Limit aus C3 bleibt unverändert), baut den Kontextblock mit `[Quelle N]`-Tags
- `answer_mode` ∈ `internal_knowledge` / `general_ai` / `no_internal_source` / `blocked_sensitive` (`internal_plus_general` ist im Mapping vorgesehen, aber nicht automatisch erkennbar — Follow-up, siehe unten)
- Explizite Dokumentenfrage per einfacher Keyword-Erkennung (`dokument`, `quelle`, `wissensdatenbank`, `interne(s) wissen`, `gespeicherte unterlage`) — **kein LLM-Klassifikator**, nur bei Nulltreffern relevant für den Hinweistext
- `sanitize_answer_citations()` — entfernt `[Quelle N]`-Tags aus dem sichtbaren Antworttext, die nicht im Backend-`tag_map` vorkommen (gegen erfundene Zitate)
- `build_sources_list()` — Quellenliste **ausschließlich** aus dem Backend-`tag_map`, nie aus Modelltext geparst — Modell kann strukturell keine zusätzlichen Quellen erzeugen
- Wirft **nie** eine Exception (mehrschichtiges Fail-safe: Suche, Re-Klassifikation, Gesamtfunktion je einzeln abgesichert)

**Anbindung in `main.py` (minimaler Footprint, analog `_maybe_suggest_memory()`):**
- `_maybe_build_knowledge_context()` — best-effort Wrapper, ohne Login (kein `token`) kein Kontext (keine Zuordnung möglich, exakt wie beim Memory-Muster)
- Einziger Injektionspunkt in `_run_agent_core()`: direkt nach `effective_task = pre_check.get("task", payload.task)` wird der geprüfte Kontextblock angehängt — dadurch automatisch wirksam für **alle** LLM-Aufrufpfade (Schreibaufgabe, AgentRuntime, Zusammenfassung), da sie alle `effective_task` verwenden. Durchläuft dadurch dieselbe Governance-Pipeline (Kill-Switch/Klassifikation/Redaction) wie jede andere Aufgabe.
- `_attach_knowledge_result()` — hängt nach der Antwort `answer_mode`, optional `confidence`/`sources`/`knowledge_notice` an, bereinigt `message`/`ai_response` von halluzinierten Zitaten, hängt bei expliziter Dokumentenfrage ohne Treffer den wörtlichen Hinweistext an die sichtbare Antwort an, schreibt Audit-light-Eintrag (`knowledge.context_used`, nur Metadaten: `answer_mode`, `found_count`, `filtered_count`, `source_ids`, `chunk_ids` — nie Snippet-Inhalte/Rohtexte/`storage_path`)
- Beide Wrapper vollständig fehlertolerant (try/except, `logger.exception`, nie Chat-blockierend)

**Bewusst nicht umgesetzt (siehe Karo-Vorgabe unten):**
- Keine Websuche, keine öffentlichen Quellen
- Keine neuen Nutzereinstellungen, keine UI-Buttons
- Kein pgvector, keine Embeddings, kein Wissensgraph
- Kein Admin-Cockpit, kein großes RAG-Redesign
- `internal_plus_general` (answer_mode) ist im Mapping vorbereitet, aber nicht automatisch von `internal_knowledge` unterschieden — würde erfordern zu erkennen, "wie" das Modell den Kontext genutzt hat; als Follow-up dokumentiert, nicht geraten

**PR #51: gemergt (2026-07-21).** CI grün, `mergeable_state: clean`, 1034/1034 Tests grün — vor dem Merge nochmal lokal gegen die C4-Checkliste geprüft (interne Quellen genutzt, Snippet-/Zeichen-Limit, Re-Klassifikation, keine erfundenen Quellen, kein Standardhinweis bei Nulltreffern, best-effort Fehlerfestigkeit, keine Websuche/pgvector/Embeddings/Wissensgraph/UI/automatische Memory-Erzeugung — alles bestätigt).

**Docker-Test:** In dieser Sandbox nicht möglich (Docker-Daemon nicht erreichbar, `/var/run/docker.sock` fehlt; auch ein direkter `uvicorn`-Start ohne Docker scheitert am Package-Importkontext dieser Sandbox). **Bitte auf echtem PC mit `docker compose up -d` prüfen.**

**Manuelle Demo:** In dieser Sandbox **nicht durchgeführt** (App/Docker nicht lauffähig, keine echten LLM-Provider-Keys verfügbar). Stattdessen Checkliste vorbereitet, siehe unten — bitte auf einem PC mit laufendem Docker und konfiguriertem Provider durchführen.

### C4-Demo-Checkliste (auf echtem PC durchführen)

1. TXT- oder Markdown-Dokument hochladen (über `ingest_txt_or_markdown_source()` bzw. eine spätere Upload-Anbindung — aktuell noch keine UI dafür, siehe Abschnitt 5).
2. Prüfen: Quelle hat Status `approved` (nicht `pending_review`/`blocked`).
3. Im Chat nach einem Inhalt aus dem Dokument fragen.
4. Prüfen:
   - Antwort nutzt internes Wissen (`answer_mode: "internal_knowledge"` im Response-Body).
   - `sources`-Liste wird im Response-Body angezeigt.
   - Jede Quelle enthält `title`, `source_id`, `chunk_id`.
5. Eine Frage stellen, zu der es keinen Treffer gibt.
6. Prüfen:
   - Chat antwortet normal weiter.
   - Kein Standardhinweis in der Antwort, `answer_mode: "general_ai"`.
7. Explizit fragen: "Was steht dazu in unseren Dokumenten?"
8. Wenn kein Treffer:
   - Antwort enthält wörtlich: "Ich habe in freigegebenen Quellen nichts Passendes gefunden."
   - `answer_mode: "no_internal_source"`.
9. Prüfen:
   - Keine Websuche ausgelöst.
   - Keine externen Quellen in der Antwort.
   - Keine automatische Memory-Erzeugung durch diesen Schritt (Memory-Suggestion-Logik aus Block B bleibt unverändert/unabhängig).
   - Im Server-Log/Request an den LLM-Provider (falls einsehbar) stehen nur Snippets, nie ganze Dokumente oder `storage_path`.

## 4a. Ursprünglicher C4-Auftrag (bereits umgesetzt, zur Nachvollziehbarkeit archiviert)

Karo hat alle offenen Punkte final entschieden (2026-07-21). Der folgende Block war der ausführbare Auftrag, ist jetzt umgesetzt:

```text
Lies zuerst docs/AGENT_HANDOFF_BLOCK_C1_ABGESCHLOSSEN.md im Repo
Karo988/AILIZA (Abschnitt 4 fuer den vollstaendigen, final entschiedenen
C4-Auftrag -- diese Entscheidungen sind bindend, NICHT erneut fragen).

Aktueller Stand: Block C1 (Schema), C2 (TXT/Markdown-Ingestion,
apps/backend/knowledge/ingestion.py) und C3 (lokale Suche,
apps/backend/knowledge/search.py, Funktion search_knowledge_chunks())
sind in main gemergt. Pruefe alle drei, bevor du etwas Neues baust.

Ziel: Agent kann bei einer Chat-Anfrage passende, freigegebene Quellen
ueber search_knowledge_chunks() abrufen, als begrenzten Kontext an das
LLM geben und in der Antwort korrekt zitieren.

Karo-Entscheidungen (final, bindend):

1. Kein Treffer / allgemeine Antwort:
   - Findet search_knowledge_chunks() nichts Passendes, antwortet AILIZA
     GANZ NORMAL weiter, OHNE Standardhinweis (kein "nichts gefunden" bei
     jeder normalen Chat-Anfrage -- das waere nervig).
   - NUR wenn der Nutzer explizit nach Dokumenten/Quellen/interner
     Wissensdatenbank/gespeicherten Unterlagen fragt (einfache
     Keyword-Erkennung reicht, kein LLM-Klassifikator noetig -- z.B.
     "Dokument", "Quelle", "Wissensdatenbank", "gespeicherte Unterlage"
     im Nutzertext), UND nichts gefunden wird, sagt AILIZA woertlich:
     "Ich habe in freigegebenen Quellen nichts Passendes gefunden."
   - Bei einer allgemeinen (nicht dokumentbezogenen) Antwort OHNE
     passende interne Quelle darf AILIZA optional klar markieren:
     "Ich habe keine passende interne Quelle gefunden und antworte
     daher allgemein." (kein Zwang, aber erlaubt/vorgesehen)

2. Kontext-Limit (hart, als eigene Konstanten):
   - Maximal 3 Snippets gleichzeitig im LLM-Kontext.
   - Insgesamt maximal 800 Zeichen aller Snippets zusammen.
   - Bereits vorhandenes Einzel-Snippet-Limit aus C3 (160 Zeichen)
     bleibt unveraendert -- das Kontext-Limit ist zusaetzlich, nicht
     ein Ersatz.

3. Re-Klassifikation vor externem LLM-Versand (immer, ohne Ausnahme):
   - JEDES Snippet, das in den LLM-Kontext soll, wird erneut geprueft:
     classify() + check_data_target(target=DataTarget.EXTERNAL_LLM)
     (siehe apps/backend/governance/data_governance.py und data_matrix.py).
   - Das ist zusaetzlich zur Pruefung bei der Ingestion (C2), die nur
     gegen DataTarget.FILE_STORAGE geklassifiziert hat -- FILE_STORAGE
     und EXTERNAL_LLM sind unterschiedliche Ziele mit unterschiedlichen
     Policy-Entscheidungen (siehe _decide_single() in data_matrix.py).
   - Wenn ein Snippet bei dieser Pruefung NICHT fuer EXTERNAL_LLM erlaubt
     ist (Decision != ALLOW/ALLOW_WITH_NOTICE): Snippet wird einfach NICHT
     in den Kontext gegeben. Kein Fehler, kein Abbruch -- der Chat laeuft
     normal weiter (ggf. mit weniger oder ganz ohne Kontext, siehe Punkt 1).

4. Produkt-Fallback (kein Rueckfrage-Popup):
   - Keine Rueckfrage-Kaskade wie "Darf ich das LLM fragen?".
   - Das LLM ist der normale Antwortweg. Interne Wissensquellen sind
     Zusatzkontext, wenn passende freigegebene Treffer vorhanden sind --
     kein Nutzer-Interaktionsschritt dazwischen.

Konkrete Bausteine (was zu implementieren ist):

- Best-effort-Schritt in main.py (Muster wie _maybe_suggest_memory() aus
  Block B): VOR dem eigentlichen LLM-Call search_knowledge_chunks()
  aufrufen (tenant_id, requester_user_id aus dem aktuellen Request/Chat,
  query = Nutzeranfrage).
- Aus den Treffern: Re-Klassifikation je Snippet (Punkt 3), dann
  Kontext-Limit anwenden (Punkt 2, max. 3 Snippets / max. 800 Zeichen
  gesamt -- bei Ueberschreitung nach Score sortiert abschneiden, nicht
  einfach die ersten N ungeprueft).
- Kontext-Block mit Referenz-Tags aufbauen, z.B. "[Quelle 1]", "[Quelle 2]"
  -- NUR hit["snippet"] verwenden, NIE rohes chunk_text oder storage_path
  oder den Original-Dateiinhalt.
- Tag-zu-Metadaten-Zuordnung (source_id, title) serverseitig merken, damit
  nach der LLM-Antwort eine "Quellen:"-Liste angehaengt werden kann --
  NUR fuer Snippets, die tatsaechlich im Kontext waren.
- Zitat-Validierung: zitiert das Modell ein Tag, das nicht in der
  mitgegebenen Zuordnung existiert, wird das serverseitig entfernt/
  ignoriert (keine erfundenen Quellen).
- Fehler in search_knowledge_chunks() oder der Re-Klassifikation duerfen
  den normalen Chat NIE blockieren (try/except, fail-safe auf "kein
  Kontext", genau wie bei _maybe_suggest_memory()).

Nicht in diesem Auftrag (bewusst spaetere, separate Capability):
- KEINE Websuche / oeffentliche Internetrecherche. Das kommt spaeter als
  eigene Capability und NUR mit eigenen Leitplanken: Admin-Regel oder
  Nutzereinstellung muss es erlauben, keine internen Snippets duerfen an
  eine Websuche gesendet werden, oeffentliche Quellen muessen klar als
  oeffentlich gekennzeichnet werden, echte Links/Quellen muessen
  vorhanden sein, nichts wird automatisch ins Gedaechtnis gespeichert.
  Das ist NICHT Teil von C4 -- nicht anfangen, auch nicht vorbereiten.
- Keine neuen Einstellungen/Admin-Optionen bauen.
- Keine UI-Buttons oder UI-Neugestaltung.
- Kein pgvector, keine Embeddings, kein Wissensgraph.
- Keine automatische Speicherung als memory_item.

TDD: Tests zuerst schreiben. Tests fuer C4 mindestens:
- Treffer werden korrekt in Kontext-Snippets mit Tags uebersetzt.
- Kontext-Limit wird hart durchgesetzt (nie mehr als 3 Snippets, nie
  mehr als 800 Zeichen gesamt).
- Re-Klassifikation blockiert ein Snippet fuer EXTERNAL_LLM korrekt,
  Chat laeuft trotzdem normal weiter (kein Crash, keine Exception nach
  aussen).
- Nur tatsaechlich verwendete Snippets erscheinen in der Quellenliste.
- Erfundene/nicht mitgegebene Zitate werden entfernt.
- Nicht freigegebene Quellen erscheinen nirgendwo (weder Kontext noch
  Quellenliste).
- Allgemeine Antwort ohne explizite Dokumentenfrage zeigt KEINEN
  Standardhinweis.
- Explizite Dokumentenfrage ohne Treffer zeigt den woertlichen Hinweistext.
- Fehler in search_knowledge_chunks() blockieren den Chat nicht.
- Bestehende Tests bleiben gruen.

Autarker Betrieb bleibt primaer (SQLite, kein Postgres-Zwang).
Aktive Testsuite: pytest tests/ -v --tb=short
Branch: claude/knowledge-rag-with-sources
Kleine, klare Commits. Kein Force-Push ohne Rueckfrage. Keine Branches
loeschen. Keine Secrets/PII in Logs oder Commits.
Wenn Docker moeglich ist: docker compose up -d kurz pruefen, sonst klar
melden.
Handoff-Dokument nach Umsetzung aktualisieren.

Nach PR-Erstellung stoppen.
```

## 5. Empfohlener Folgeschritt (umgesetzt als Block D0, siehe Abschnitt 8)

~~Block C (C1–C4) ist jetzt vollständig gemergt, aber es gibt aktuell keine Möglichkeit, das praktisch zu sehen~~ — **erledigt durch Block D0** (Abschnitt 8): kleine Demo-/UI-Schicht "Firmendatenbank" mit Upload, Statusanzeige und Quellenliste im Chat.

## 6. Governance-Erinnerung (bleibt für jede Phase bindend)

- Erst fragen, dann programmieren — bei Unklarheiten NICHT raten, Karo fragen
- Keine Dokumente/Chunks an externe LLM-Dienste ohne ausdrückliche Freigabe (Kill-Switch-Pipeline gilt auch hier)
- Jede Antwort aus Dokumentwissen braucht Quellen (ab C4 umgesetzt — siehe Abschnitt 4)
- Gelöschte/blockierte Quellen dürfen nie genutzt werden (durchgesetzt über `list_active_chunks_for_source` und `search_knowledge_chunks`)

## 7. Modell-Empfehlung

**Sonnet 5** für C4 war korrekt — alle Architekturfragen waren durch Karo bereits final entschieden, reine Integration bestehender Bausteine, kein offener Architektur-Entwurf.
**Für Block D0: ebenfalls Sonnet 5** — kleine, klar abgegrenzte Frontend-/API-Anbindung ohne neue Architekturentscheidung (bestätigt sich im Ergebnis).

## 8. Block D0 — Demo-/UI-Schicht "Firmendatenbank" (was gebaut wurde)

**Branch:** `claude/knowledge-demo-ui` · **Tests:** 43 neu (`test_knowledge_demo_view.py`: 13, `test_knowledge_demo_db.py`: 6, `test_knowledge_txt_md_ingestion.py`: +3 Kategorie-Tests, `test_knowledge_demo_api.py`: 21) · **Baseline:** 1077/1077 Tests grün.

### Backend (additiv, keine bestehende Logik verändert)

- **`category`-Spalte** auf `knowledge_sources` (nullable, additive SQLite-Migration analog bestehendem Muster) — rein manuell, feste Whitelist `ALLOWED_DEMO_CATEGORIES` in `apps/backend/knowledge/ingestion.py` (Allgemein, Richtlinie, Projekt, Kunde, Vorlage, Anleitung, Vertrag/Compliance). **Keine automatische Kategorisierung per LLM.**
- **`list_knowledge_sources_for_tenant()`** (neu in `database.py`) — alle Quellen eines Mandanten inkl. Chunk-Anzahl, ungefiltert nach Status (die UI zeigt bewusst auch blockierte/wartende Quellen, damit der volle Überblick sichtbar ist).
- **`ingest_txt_or_markdown_source()`** um optionalen `category`-Parameter erweitert (validiert, sonst `KnowledgeIngestionError`).
- **Neues Modul `apps/backend/knowledge/demo_view.py`** (reine Anzeigelogik, keine DB-Schreibzugriffe):
  - `usability_label_for_status()` → "Nutzbar im Chat" / "Wartet auf Prüfung" / "Blockiert" / "Nicht aktiv"
  - `status_explanation()` — nutzerfreundliche Erklärung ohne technische Details
  - `sort_sources_for_demo()` — approved zuerst, dann wartend, dann blocked/deleted/expired, je Gruppe neueste zuerst
  - `to_public_source_view()` — Whitelist-Ansicht (`PUBLIC_SOURCE_FIELDS`), **niemals** `storage_path` oder `chunk_text`
- **Neue Endpunkte in `main.py`** (alle mit Login-Pflicht, `_require_user()`):
  - `POST /api/knowledge/upload` — nutzt `ingest_txt_or_markdown_source()` direkt, keine Parallel-Logik
  - `GET /api/knowledge/sources` — sortierte, öffentliche Ansicht aller Quellen des eigenen Mandanten
  - `GET /api/knowledge/sources/{id}` — Detailansicht, 404 bei fremdem Mandanten oder unbekannter ID

### Frontend (`apps/frontend/index.html`, additiv)

- Neuer Sidebar-Eintrag **"Firmendatenbank"** (eigene View `view-wissensdb`, unabhängig von der bestehenden "Wissensbibliothek" für Prompt-Vorlagen)
- Upload-Formular (Datei + optionale Kategorie-Auswahl), Status-/Filter-Leiste (Alle/Nutzbar/Wartet auf Prüfung/Blockiert/Nicht aktiv), Suche (Titel/Dateiname/Kategorie/source_id)
- Karten-Ansicht mit Status-Badge, Klick zeigt Detailbereich (Status-Erklärung, source_id, Kategorie, Sichtbarkeit, Chunk-Anzahl); bei nutzbaren Quellen Button "Frage zu dieser Quelle stellen" (öffnet nur den Chat mit vorbereitetem Text, ändert **nie** direkt einen Datenbankstatus)
- Chat-Antwort zeigt jetzt zusätzlich (rein additiv, nur wenn vom Backend geliefert): `data.knowledge_notice` (z. B. "Antwort basiert auf: internes Wissen.") und `data.sources` als einfache Liste (Titel, `source_id`, `chunk_id`)

### Sicherheit / Statuslogik (durchgesetzt, nicht nur behauptet)

- `approved` = nutzbar, `pending_review`/`uploaded` = sichtbar, nicht nutzbar, `blocked` = sichtbar, nicht nutzbar, `deleted`/`expired` = nicht aktiv — durch `is_usable_in_chat()` hart codiert, nicht im Frontend entscheidbar
- Backend gibt **nie** `storage_path` oder rohes `chunk_text` heraus (durch `to_public_source_view()`-Whitelist strukturell ausgeschlossen, per Test abgesichert)
- Kein neuer externer Dienst, keine Websuche, kein pgvector, keine Embeddings, kein Wissensgraph

### Bewusst nicht gebaut

- Keine Rollenverwaltung, kein Admin-Cockpit
- Keine Export-/Löschfunktion in D0 (bestehende Export/Löschung aus Block B bleibt unverändert und unabhängig)
- Keine Memory-Verwaltung, keine automatische Memory-Erzeugung aus Dokumenten
- Keine PDF/DOCX-Verarbeitung (weiterhin nur `.txt`/`.md`, wie in C2 entschieden)
- Kein neues Designsystem — bestehende CSS-Klassen (`.card`, `.grid`, `.meta-pill`, `.wissen-cat-btn`) wiederverwendet
- Keine produktive Kundenfreigabe — D0 ist explizit ein Demo-/Prüfmodus

### Tests

Kein Frontend-Testsystem im Repo vorhanden. Stattdessen durchgeführt:
- `pytest tests/ -v --tb=short` → **1077/1077 grün**
- `node --check` auf den extrahierten `<script>`-Inhalt von `index.html` → **kein Syntaxfehler**
- Python `html.parser` über die gesamte Datei → **keine Parse-Fehler**

### Docker-Test

Nicht möglich — Docker-Daemon in dieser Sandbox nicht erreichbar (`/var/run/docker.sock` fehlt), wie bei C2/C3/C4. **Bitte auf echtem PC mit `docker compose up -d` verifizieren.**

### Manuelle Demo

In dieser Sandbox nicht als Browser-Klickdurchlauf durchführbar (kein Docker, kein Browser). Die Demo-Schritte sind aber **funktional über die neuen API-Tests abgedeckt** (Upload → Statusanzeige → Chat mit Quelle → Chat ohne Treffer → explizite Dokumentenfrage). Checkliste für die echte Durchführung auf einem PC:

1. Firmendatenbank öffnen (Sidebar → "Firmendatenbank").
2. TXT- oder Markdown-Datei hochladen, optional Kategorie wählen.
3. Prüfen: Status wird als Badge angezeigt ("Nutzbar im Chat" / "Wartet auf Prüfung" / "Blockiert").
4. Bei einer `approved`-Quelle: im Chat eine Frage zum Dokumentinhalt stellen (oder über "Frage zu dieser Quelle stellen").
5. Prüfen: Antwort erscheint, danach ein Hinweis wie "Antwort basiert auf: internes Wissen." und eine Quellenliste mit Titel/`source_id`/`chunk_id`.
6. Eine Frage ohne Treffer stellen — prüfen: Chat antwortet normal, kein Standardhinweis.
7. Explizit fragen: "Was steht dazu in unseren Dokumenten?" — bei keinem Treffer erscheint: "Ich habe in freigegebenen Quellen nichts Passendes gefunden."
8. Prüfen: keine Websuche, keine externen Quellen, keine automatische Memory-Erzeugung, keine ganzen Dokumente im Prompt, kein `storage_path` irgendwo sichtbar.

### Offene Folgepunkte

- Kein automatisiertes Frontend-Testsystem im Repo — falls gewünscht, separater kleiner Auftrag (z. B. Playwright)
- Manuelle Kategorie kann aktuell nur beim Upload gesetzt werden, kein nachträgliches Bearbeiten (bewusst kleinster Schnitt)
- Echte Browser-Demo auf einem PC mit Docker steht noch aus

---

*Diese Datei ist der Fahrplan für Block C. Nach jedem gemergten PR bitte kurz aktualisieren (Status-Tabelle oben).*
