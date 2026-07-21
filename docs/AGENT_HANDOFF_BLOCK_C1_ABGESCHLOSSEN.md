# AILIZA Agent-Handoff: Block C — Stand nach C1 + C2 + C3 + C4

**Status:** PR #48 (Schema), PR #49 (TXT/Markdown-Ingestion) und PR #50 (lokale Suche) sind **gemergt**. Block C4 (interne Wissensquellen im Chat mit Quellenanzeige) ist implementiert, 1034/1034 Tests grün, PR wird als nächstes erstellt.

**Zielgruppe:** Karo selbst (Priorisierung) und/oder nächster Agent (für Block C5/Websuche, jeweils erst nach expliziter Freigabe).

---

## 1. Wo wir stehen

```
Block A (Autarker Betrieb, Memory-Kernschema)        ✅ gemergt
Block B (Chat-Anbindung, Export/Löschung DSGVO)       ✅ gemergt
Block C1 (Wissensquellen-Schema)                      ✅ gemergt (PR #48)
Block C2 (TXT/Markdown-Ingestion)                     ✅ gemergt (PR #49)
Block C3 (Lokale Suche)                               ✅ gemergt (PR #50)
Block C4 (RAG mit Quellen)                            ✅ implementiert, PR folgt (Branch claude/knowledge-rag-with-sources)
Block C5 (Optionale Vektorsuche)                      ⏳ nur nach expliziter Freigabe
Block D (Desktop-Distribution ohne Docker)            ⏳ separater, späterer Auftrag
Websuche/Internetrecherche                            ⏳ spätere, eigene Capability (siehe Abschnitt 4, Leitplanken)
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

**Docker-Test:** nicht möglich (Daemon in der Sandbox nicht erreichbar) — auf echtem PC mit `docker compose up -d` verifizieren.

**Noch offen:** PR für C4 muss von dir gemerged werden. Nicht mergen ohne Karo-Freigabe.

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

## 5. Governance-Erinnerung (bleibt für jede Phase bindend)

- Erst fragen, dann programmieren — bei Unklarheiten NICHT raten, Karo fragen
- Keine Dokumente/Chunks an externe LLM-Dienste ohne ausdrückliche Freigabe (Kill-Switch-Pipeline gilt auch hier)
- Jede Antwort aus Dokumentwissen braucht Quellen (ab C4 umzusetzen — Architektur seit C1 darauf ausgelegt)
- Gelöschte/blockierte Quellen dürfen nie genutzt werden (durchgesetzt über `list_active_chunks_for_source` und jetzt auch direkt in `search_knowledge_chunks`)

## 6. Modell-Empfehlung

**Sonnet 5** für C3 war korrekt (iterative Such-Logik, Tests, TDD) — hat gereicht, keine Architektur-Rückfrage nötig.
**Für C4: Sonnet 5** — alle Architekturfragen sind durch Karo bereits final entschieden (Abschnitt 4), C4 ist jetzt iterative Integration bestehender Bausteine (`search_knowledge_chunks`, Governance-Pipeline), kein offener Architektur-Entwurf mehr. Opus 4.8 wäre nur nötig gewesen, um die jetzt getroffenen Entscheidungen zu erarbeiten — das ist bereits erledigt.

---

*Diese Datei ist der Fahrplan für Block C. Nach jedem gemergten PR bitte kurz aktualisieren (Status-Tabelle oben).*
