# AILIZA Agent-Handoff: Block C — Stand nach C1 + C2

**Status:** PR #48 (Block C1: Schema) ist **gemergt**. Block C2 (sichere TXT/Markdown-Ingestion) ist implementiert, 979/979 Tests grün, PR wird als nächstes erstellt.

**Zielgruppe:** Karo selbst (Priorisierung) und/oder nächster Agent (für Block C3, erst nach Merge von C2).

---

## 1. Wo wir stehen

```
Block A (Autarker Betrieb, Memory-Kernschema)        ✅ gemergt
Block B (Chat-Anbindung, Export/Löschung DSGVO)       ✅ gemergt
Block C1 (Wissensquellen-Schema)                      ✅ gemergt (PR #48)
Block C2 (TXT/Markdown-Ingestion)                     ✅ implementiert, PR folgt (Branch claude/knowledge-txt-md-ingestion)
Block C3 (Lokale Suche)                               ⏳ erst nach Merge von C2 starten
Block C4 (RAG mit Quellen)                            ⏳ noch nicht begonnen
Block C5 (Optionale Vektorsuche)                      ⏳ nur nach expliziter Freigabe
Block D (Desktop-Distribution ohne Docker)            ⏳ separater, späterer Auftrag
```

## 2. Block C2 — was gebaut wurde

**Branch:** `claude/knowledge-txt-md-ingestion` · **Modul:** `apps/backend/knowledge/ingestion.py` · **Tests:** `tests/test_knowledge_txt_md_ingestion.py` (23 neu) · **Baseline:** 979/979 Tests grün.

- `ingest_txt_or_markdown_source()` — einziger Einstiegspunkt, nur `.txt`/`.md`
- `ALLOWED_KNOWLEDGE_EXTENSIONS = {".txt", ".md"}` und `MAX_KNOWLEDGE_FILE_BYTES = 2_000_000` als eigene, klar erkennbare Konstanten
- Originaldatei landet unter `/data/uploads` (per `AILIZA_KNOWLEDGE_UPLOAD_DIR` konfigurierbar, Dev-Fallback analog zu `_resolve_database_url`), DB speichert nur Metadaten
- Speicherpfad wird **nie** aus dem Nutzer-Dateinamen gebaut (nur `tenant_id` + zufällige ID + validierte Extension) → Pfad-Traversal strukturell ausgeschlossen
- Klassifikation über bestehende Governance (`classify()` + `check_data_target(target=FILE_STORAGE)`), zusätzlich `classification.needs_review` beachtet, da `FILE_STORAGE` als Ziel in der Datenziel-Matrix für `SPECIAL_CATEGORY` alleine nicht streng genug ist
- Fail-closed: `BLOCK` → Status `blocked`; `APPROVAL_REQUIRED`/`REDACT_REQUIRED`/`needs_review` → Status `pending_review`; sonst `approved`. Nur bei `approved` werden `knowledge_chunks` angelegt
- Verständliche deutsche Nutzermeldungen ohne technische Details, Audit-Eintrag ohne Rohinhalte
- **Docker-Test:** nicht möglich (Daemon in der Sandbox nicht erreichbar) — auf echtem PC mit `docker compose up -d` verifizieren

**Noch offen:** PR für C2 muss von dir gemerged werden, bevor C3 beauftragt wird.

## 3. Nächster großer Schritt: Block C Phase C3 (Lokale Suche)

**Nur starten, wenn die C2-PR gemergt ist.**

Kopiere diesen Block 1:1, sobald das der Fall ist:

```text
Lies zuerst docs/AGENT_HANDOFF_BLOCK_C1_ABGESCHLOSSEN.md im Repo
Karo988/AILIZA (Abschnitt "Block C2 -- was gebaut wurde" fuer den
aktuellen Stand von apps/backend/knowledge/ingestion.py).

Aktueller Stand: Block C1 (Schema: knowledge_sources, knowledge_chunks,
knowledge_source_permissions) und Block C2 (sichere TXT/Markdown-
Ingestion, apps/backend/knowledge/ingestion.py) sind in main gemergt.
Pruefe beide, bevor du etwas Neues baust.

Setze nur Block C Phase C3 um: einfache lokale Suche ueber freigegebene
knowledge_chunks.

Ziel:
- AILIZA kann lokal ueber freigegebene knowledge_chunks suchen.
- Nur berechtigte, aktive und freigegebene Quellen duerfen gefunden werden
  (status="approved", nicht blocked/deleted/expired/pending_review,
  Berechtigung ueber knowledge_source_permissions/tenant_id pruefen).

Suchstrategie:
- Einfach und autark: lokale Keyword-Suche (z.B. LIKE/Substring-Matching
  oder SQLite FTS, falls ohne zusaetzliche Abhaengigkeit moeglich).
- Kein pgvector, keine Embeddings, kein externer Dienst.
- SQLite-kompatibel (kein Postgres-Zwang, autarker Betrieb bleibt primaer).

TDD: Tests zuerst schreiben.

Tests fuer C3:
- Nutzer findet eigene/freigegebene Chunks.
- Nutzer findet fremde/private Chunks nicht.
- blocked/deleted/pending_review Sources werden nicht gefunden.
- Suche liefert Quelle, Titel, Chunk-ID und kurzen Ausschnitt.
- Suche respektiert tenant_id/Berechtigungen.
- Suche funktioniert ohne externe Dienste.
- kein RAG in dieser PR.
- bestehende Tests bleiben gruen.

Ergebnisformat je Treffer:
- source_id, chunk_id, title, snippet, score/einfache Relevanz,
  source_type, visibility_scope, status

Nutzerfreundlichkeit:
- Nichts gefunden: "Ich habe in freigegebenen Quellen nichts Passendes
  gefunden."
- Nicht freigegebene Quelle: nicht anzeigen, nicht andeuten, nicht
  zitieren.

Nicht im Scope C3:
- kein RAG, keine Antwortgenerierung mit Quellen, keine UI-Neugestaltung,
  kein pgvector, keine Embeddings, kein Wissensgraph, kein PDF/DOCX,
  keine automatische Speicherung als memory_item.

Autarker Betrieb bleibt primaer (SQLite, kein Postgres-Zwang).
Aktive Testsuite: pytest tests/ -v --tb=short
Branch: claude/knowledge-local-search
Kleine, klare Commits. Kein Force-Push ohne Rueckfrage. Keine Branches
loeschen. Keine Secrets/PII in Logs oder Commits.
Wenn Docker moeglich ist: docker compose up -d kurz pruefen, sonst klar
melden.

Nach PR-Erstellung stoppen.
```

## 4. Governance-Erinnerung (bleibt für jede Phase bindend)

- Erst fragen, dann programmieren — bei Unklarheiten NICHT raten, Karo fragen
- Keine Dokumente/Chunks an externe LLM-Dienste ohne ausdrückliche Freigabe (Kill-Switch-Pipeline gilt auch hier)
- Jede Antwort aus Dokumentwissen braucht später Quellen (erst ab C4 relevant, aber Architektur muss es von Anfang an ermöglichen)
- Gelöschte/blockierte Quellen dürfen nie genutzt werden (durchgesetzt über `list_active_chunks_for_source`)

## 5. Modell-Empfehlung

**Sonnet 5** für C3 (iterative Such-Logik, Tests, TDD).
**Opus 4.8 nur** falls eine echte Architekturentscheidung zur Suchstrategie (z.B. FTS5 vs. einfaches LIKE) nötig wird und du das explizit anstoßen willst.

---

*Diese Datei ist der Fahrplan für Block C. Nach jedem gemergten PR bitte kurz aktualisieren (Status-Tabelle oben).*
