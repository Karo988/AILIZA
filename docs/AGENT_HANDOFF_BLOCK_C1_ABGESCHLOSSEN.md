# AILIZA Agent-Handoff: Block C Phase C1 (Schema) fertig — nächste Schritte

**Status:** PR #48 (Block C1: Dokumentquellen-Schema) ist offen, `mergeable_state: clean`, 956/956 Tests grün. Noch nicht gemergt — wartet auf Karos Review/Merge.

**Zielgruppe:** Karo selbst (Priorisierung) und/oder nächster Agent (nach Merge von PR #48).

---

## 1. Wo wir stehen

```
Block A (Autarker Betrieb, Memory-Kernschema)        ✅ gemergt
Block B (Chat-Anbindung, Export/Löschung DSGVO)       ✅ gemergt
Block C1 (Wissensquellen-Schema)                      ⏳ PR #48 offen, bereit zum Merge
Block C2 (Dokument-Ingestion)                         ⏳ noch nicht begonnen
Block C3 (Lokale Suche)                               ⏳ noch nicht begonnen
Block C4 (RAG mit Quellen)                            ⏳ noch nicht begonnen
Block C5 (Optionale Vektorsuche)                      ⏳ nur nach expliziter Freigabe
Block D (Desktop-Distribution ohne Docker)            ⏳ separater, späterer Auftrag
```

## 2. Sofort zu erledigen (von dir, nicht vom Agenten)

1. **PR #48 mergen** (oder Review-Kommentare zuerst klären)
   - Link: https://github.com/Karo988/AILIZA/pull/48
   - Status: clean, 956/956 Tests grün, Unicode-Hinweis bereits bereinigt
2. Danach: nächster Agent arbeitet auf frischem `main` inkl. `knowledge_sources`/`knowledge_chunks`/`knowledge_source_permissions`

## 3. Nächster großer Schritt: Block C Phase C2 (Dokument-Ingestion)

**Nicht sofort automatisch starten** — vorher die 3 offenen Stop-Fragen aus `AILIZA_BLOCK_C_STOP_DECISIONS.md` klären, die C2 direkt betreffen:

| # | Frage | Empfehlung | Deine Entscheidung |
|---|---|---|---|
| 1 | Speicherort Originaldateien? | `/data/uploads` (Docker-Volume) + Metadaten in DB | ⬜ offen |
| 2 | Erlaubte Dateitypen für v1? | TXT + Markdown zuerst, PDF/DOCX später | ✅ **Karo-Entscheidung: Erst sicherer Kern mit nur TXT + Markdown, Erweiterung auf weitere Dateitypen erst als späterer, separater Schritt nach erneuter Freigabe** |
| 3 | Umgang mit sensiblen Dokumenten? | Nicht frei entscheidbar — braucht dein OK (blockieren / redigieren / Admin-Freigabe) | ⬜ offen |

**Noch 2 offene Fragen**, bevor C2 vollständig beauftragt werden kann — der nächste Agent-Prompt unten enthält sie als expliziten Stopp-Punkt, nicht als Freibrief zum Raten.

## 4. Fertiger Prompt für den nächsten Agenten (Block C2, nach PR #48-Merge)

Kopiere diesen Block 1:1, sobald PR #48 gemergt ist und du die 3 Fragen oben beantwortet hast (oder den Agenten explizit fragen lässt):

```text
Lies zuerst docs/AGENT_HANDOFF_BLOCK_B_ABGESCHLOSSEN.md und
docs/AGENT_HANDOFF_BLOCK_C1_ABGESCHLOSSEN.md im Repo Karo988/AILIZA.

Danach (falls noch im Upload-Paket vorhanden, sonst im Repo suchen):
- AILIZA_BLOCK_C_MASTER_AUFTRAG.md
- AILIZA_BLOCK_C_PHASE_C2_INGESTION_PIPELINE.md
- AILIZA_BLOCK_C_STOP_DECISIONS.md

Aktueller Stand: Block C1 (Tabellen knowledge_sources, knowledge_chunks,
knowledge_source_permissions) ist in main gemergt. Prüfe das existierende
Schema in apps/backend/database.py, bevor du etwas Neues baust.

Karo-Entscheidung zu Dateitypen: ERST sicherer Kern, DANN Dateitypen
erweitern. Das heisst konkret fuer diesen Auftrag:

Setze nur Block C Phase C2 Schritt 1 um (sicherer Ingestion-Kern,
NUR TXT + Markdown):
- Dokumente aufnehmen -- ausschliesslich .txt und .md, alles andere
  wird mit klarer, verstaendlicher Fehlermeldung abgelehnt (fail-closed,
  keine Erkennung/Sniffing von "eigentlich doch okay")
- Text extrahieren (fuer TXT/MD ist das reines Einlesen, keine
  Parsing-Bibliothek noetig -- bewusst der einfachste/sicherste Fall zuerst)
- Inhalte chunkweise in knowledge_chunks speichern
- Quellen (knowledge_sources) und Berechtigungen
  (knowledge_source_permissions) beachten - keine Ingestion ohne
  gueltige Source, kein Auto-Approve
- Dateityp-Whitelist als eigene, klar erkennbare Konstante/Funktion
  implementieren (z.B. ALLOWED_INGESTION_TYPES = {"txt", "md"}), NICHT
  hart im Ablauf verstreut -- das ist die Stelle, die spaeter für
  PDF/DOCX erweitert wird, also muss sie einfach erweiterbar UND leicht
  auditierbar sein

Ausdruecklich NICHT in diesem Auftrag (kommt als eigener, spaeterer
Schritt sobald der Kern sicher steht und Karo das freigibt):
- Kein PDF/DOCX/CSV, auch nicht "testweise" oder "vorbereitend"
- Keine Erweiterung der Whitelist ohne Karos ausdrueckliches OK
- Keine Suche
- Kein RAG
- Keine Embeddings
- Kein pgvector
- Keine Upload-UI
- Keine automatische Erinnerung aus Dokumenten in memory_items
- Keine Firmenwissen-Suggestion aus Dokumenten

Stop-Regeln (siehe AILIZA_BLOCK_C_STOP_DECISIONS.md) - bei diesen
Punkten IMMER erst fragen, nicht raten:
- Speicherort Originaldateien (Empfehlung: /data/uploads + Metadaten in DB,
  noch nicht von Karo final bestaetigt -- nachfragen falls nicht laengst geklaert)
- Umgang mit sensiblen Dokumenten (blockieren/redigieren/Admin-Freigabe -
  NICHT frei entscheiden, noch offen)
- Keine Dokumente/Chunks an externe LLM-/Embedding-Dienste ohne
  ausdrueckliche Freigabe

Autarker Betrieb bleibt primaer (SQLite, kein Postgres-Zwang).
Tests zuerst (TDD).
Aktive Testsuite: pytest tests/ -v --tb=short
Kleine, einzeln bestaetigte PR statt grosser Umbau.
Branch: claude/knowledge-document-ingestion

Nach PR-Erstellung stoppen.
```

## 5. Governance-Erinnerung (bleibt für jede Phase bindend)

- Erst fragen, dann programmieren — bei den 3 Stop-Fragen oben NICHT raten
- Keine Dokumente/Chunks an externe LLM-Dienste ohne ausdrückliche Freigabe (Kill-Switch-Pipeline gilt auch hier)
- Jede Antwort aus Dokumentwissen braucht später Quellen (erst ab C4 relevant, aber Architektur muss es von Anfang an ermöglichen)
- Gelöschte/blockierte Quellen dürfen nie genutzt werden (in C1 bereits durchgesetzt über `list_active_chunks_for_source`)

## 6. Modell-Empfehlung

**Sonnet 5** für C2 (iterative Ingestion-Pipeline, Tests, TDD).
**Opus 4.8 nur** falls eine echte Architekturentscheidung zu Chunking-Strategie oder Datei-Handling nötig wird und du das explizit anstoßen willst.

---

*Diese Datei ist der Fahrplan für Block C. Nach jedem gemergten PR bitte kurz aktualisieren (Status-Tabelle oben).*
