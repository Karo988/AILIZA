# AILIZA Agent-Handoff: Block C — Stand nach C1 + C2 + C3

**Status:** PR #48 (Schema) und PR #49 (TXT/Markdown-Ingestion) sind **gemergt**. Block C3 (lokale Suche) ist implementiert, 999/999 Tests grün, PR wird als nächstes erstellt.

**Zielgruppe:** Karo selbst (Priorisierung) und/oder nächster Agent (für Block C4, erst nach Merge von C3).

---

## 1. Wo wir stehen

```
Block A (Autarker Betrieb, Memory-Kernschema)        ✅ gemergt
Block B (Chat-Anbindung, Export/Löschung DSGVO)       ✅ gemergt
Block C1 (Wissensquellen-Schema)                      ✅ gemergt (PR #48)
Block C2 (TXT/Markdown-Ingestion)                     ✅ gemergt (PR #49)
Block C3 (Lokale Suche)                               ✅ implementiert, PR folgt (Branch claude/knowledge-local-search)
Block C4 (RAG mit Quellen)                            ⏳ erst nach Merge von C3 starten
Block C5 (Optionale Vektorsuche)                      ⏳ nur nach expliziter Freigabe
Block D (Desktop-Distribution ohne Docker)            ⏳ separater, späterer Auftrag
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

**Noch offen:** PR für C3 muss von dir gemerged werden, bevor C4 beauftragt wird.

## 4. Nächster großer Schritt: Block C Phase C4 (RAG mit Quellen)

**Nur starten, wenn die C3-PR gemergt ist.** C4 ist architektonisch bedeutsamer als C1–C3 (erste Stelle, an der Such-Ergebnisse in eine Agent-Antwort einfließen) — vor Beauftragung kurz mit Karo abstimmen, ob Sonnet 5 reicht oder ein Opus-Review vorgeschaltet werden soll (siehe Modell-Empfehlung unten).

Groborientierung für den Prompt (noch nicht final ausformuliert wie bei C2/C3, da C4 von Karo vermutlich nochmal geschärft wird, bevor er beauftragt wird):

```text
Ziel: Agent kann bei einer Chat-Anfrage passende Quellen ueber
search_knowledge_chunks() abrufen und in der Antwort nennen.

Muss-Regeln:
- Keine Antwort auf Basis nicht freigegebener Dokumente.
- Jede Antwort aus Dokumentwissen nennt ihre Quelle(n) (source_id/title).
- Weiterhin nur approved/aktive/berechtigte Quellen (search_knowledge_chunks
  garantiert das bereits -- keine eigene Parallel-Logik bauen).
- Kein automatisches Ueberschreiben der normalen Chat-Antwort, wenn keine
  passende Quelle gefunden wird (message aus search_knowledge_chunks nutzen).
- Kein pgvector, keine Embeddings, keine externen Such-/RAG-Dienste.
- TDD, aktive Testsuite: pytest tests/ -v --tb=short
- Branch: claude/knowledge-rag-with-sources

Nach PR-Erstellung stoppen.
```

## 5. Governance-Erinnerung (bleibt für jede Phase bindend)

- Erst fragen, dann programmieren — bei Unklarheiten NICHT raten, Karo fragen
- Keine Dokumente/Chunks an externe LLM-Dienste ohne ausdrückliche Freigabe (Kill-Switch-Pipeline gilt auch hier)
- Jede Antwort aus Dokumentwissen braucht Quellen (ab C4 umzusetzen — Architektur seit C1 darauf ausgelegt)
- Gelöschte/blockierte Quellen dürfen nie genutzt werden (durchgesetzt über `list_active_chunks_for_source` und jetzt auch direkt in `search_knowledge_chunks`)

## 6. Modell-Empfehlung

**Sonnet 5** für C3 war korrekt (iterative Such-Logik, Tests, TDD) — hat gereicht, keine Architektur-Rückfrage nötig.
**Für C4:** Sonnet 5 als Standard, aber **Opus 4.8 in Erwägung ziehen**, sobald es um die konkrete Ausgestaltung "wie zitiert der Agent Quellen in der Chat-Antwort" geht — das ist näher an einer Architekturentscheidung (User-Erlebnis + Governance-Konsistenz) als reine Ingestion/Suche.

---

*Diese Datei ist der Fahrplan für Block C. Nach jedem gemergten PR bitte kurz aktualisieren (Status-Tabelle oben).*
