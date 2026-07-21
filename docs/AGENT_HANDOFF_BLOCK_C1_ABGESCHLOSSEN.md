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

Alle 3 Stop-Fragen aus `AILIZA_BLOCK_C_STOP_DECISIONS.md` sind entschieden — C2 kann beauftragt werden, sobald PR #48 gemergt ist:

| # | Frage | Karo-Entscheidung |
|---|---|---|
| 1 | Speicherort Originaldateien? | ✅ `/data/uploads` (Docker-Volume). DB speichert nur Pfad, Hash, Status, Besitzer, Sichtbarkeit, Berechtigungen — keine Binärdaten in der Datenbank. |
| 2 | Erlaubte Dateitypen für v1? | ✅ Nur TXT + Markdown (C2a). PDF (C2b) und DOCX (C2c) folgen als eigene, spätere Schritte nach erneuter Freigabe — nicht "vorbereitend" im selben PR. |
| 3 | Umgang mit sensiblen Dokumenten? | ✅ Fail-closed: als sensibel/riskant erkannte Dokumente werden **nicht** als aktive Wissensquelle verarbeitet — Status `blocked` oder `pending_review`, keine Chunks für aktive Nutzung, keine Inhalte an externe LLMs. Immer verständliche Erklärung + Alternative für den Nutzer, nie stillschweigendes Blockieren ohne Feedback. |

Alle 3 Entscheidungen sind bereits in den Agent-Prompt unten eingearbeitet.

## 4. Fertiger Prompt für den nächsten Agenten (Block C2, nach PR #48-Merge)

Kopiere diesen Block 1:1, sobald PR #48 gemergt ist:

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

Karo hat alle 3 Stop-Fragen aus AILIZA_BLOCK_C_STOP_DECISIONS.md bereits
entschieden -- NICHT erneut fragen, diese Entscheidungen sind bindend:

1. Speicherort Originaldateien: /data/uploads (Docker-Volume). Die
   Datenbank speichert NUR Metadaten (Pfad, Hash, Status, Besitzer,
   Sichtbarkeit, Berechtigungen) -- keine Binaerdaten in der DB.
2. Dateitypen: NUR TXT + Markdown in diesem Auftrag (C2a). PDF (C2b)
   und DOCX (C2c) sind spaetere, separate Auftraege nach erneuter
   Freigabe -- nicht "vorbereitend" im selben PR.
3. Umgang mit sensiblen Dokumenten: fail-closed. Als sensibel/riskant
   erkannte Dokumente werden NICHT als aktive Wissensquelle verarbeitet.
   Status auf "blocked" oder "pending_review" setzen. Keine Chunks fuer
   aktive Nutzung/Suche freigeben. Keine Inhalte an externe LLM-/
   Embedding-Dienste senden. Der Nutzer bekommt immer eine
   verstaendliche Erklaerung und wo sinnvoll eine Alternative (z.B.
   "Bitte Admin-Freigabe anfragen") -- kein stillschweigendes Verwerfen
   ohne Feedback.

Setze nur Block C Phase C2 Schritt 1 um (sicherer Ingestion-Kern,
NUR TXT + Markdown):
- Dokumente aufnehmen -- ausschliesslich .txt und .md, alles andere
  wird mit klarer, verstaendlicher Fehlermeldung abgelehnt (fail-closed,
  keine Erkennung/Sniffing von "eigentlich doch okay")
- Originaldatei nach /data/uploads schreiben (Docker-Volume), DB-Zeile
  in knowledge_sources bekommt storage_path + content_hash (nur
  Metadaten, keine Binaerdaten in der DB)
- Text extrahieren (fuer TXT/MD ist das reines Einlesen, keine
  Parsing-Bibliothek noetig -- bewusst der einfachste/sicherste Fall zuerst)
- Vor dem Speichern: bestehende Governance-classify()-Pipeline auf den
  Inhalt anwenden (siehe apps/backend/governance/) -- bei sensiblem
  Befund status=blocked oder pending_review setzen, siehe Stop-Antwort 3
  oben. Keine neue eigene Klassifikation erfinden, bestehende nutzen.
- Inhalte chunkweise in knowledge_chunks speichern (nur wenn Source
  aktiv/freigegeben ist)
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

Weiterhin bindende Stop-Regel (siehe AILIZA_BLOCK_C_STOP_DECISIONS.md) --
bei diesem Punkt IMMER erst fragen, nicht raten, falls er relevant wird:
- Keine Dokumente/Chunks an externe LLM-/Embedding-Dienste ohne
  ausdrueckliche Freigabe (Kill-Switch-Pipeline gilt auch hier)

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
