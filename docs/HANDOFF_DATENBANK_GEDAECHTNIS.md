# AILIZA — Übergabe-Dokument: Datenbank & Gedächtnis

Stand: 21.07.2026 · Für den nächsten Agenten oder PC-Wechsel.
**Bitte diese Datei zuerst lesen.**

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

## 3. Offen — Block B (Chat nutzbar machen), zwei gestapelte PRs

| PR | Branch | Basis | Status |
|---|---|---|---|
| **#46** | `claude/memory-chat-integration` | `main` | Offen, **kann direkt gemergt werden** |
| **#47** | `claude/user-export-deletion` | PR #46 (gestapelt!) | Offen, **Merge-Sperre: erst nach #46** |

**Reihenfolge beim Mergen:** #46 zuerst. Danach #47: Base auf `main` umstellen
(GitHub-PR-Settings oder `gh pr edit`), Tests erneut laufen lassen, dann mergen.

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

## 5. Zurückgestellt (nicht Block B, separate spätere Aufträge)

- UI-Panel "Mein AILIZA-Gedächtnis" (reine Sichtbarkeit, ändert nichts an der
  Architektur — kann jederzeit nachgezogen werden)
- Block C: Wissensdatenbank + Vektorsuche (pgvector)
- Block D: Desktop-Distribution ohne Docker (gepackte ausführbare Datei)

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
