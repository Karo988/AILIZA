# AILIZA Agent-Handoff: Block B Abgeschlossen

**Status:** Block B (Chat-Integration + DSGVO Export/Deletion) ist vollständig implementiert, getestet und in `main` gemergt.

**Zielgruppe:** Nächster Agent / PC-Wechsel (Deadline: ~1 Woche).

**Lesedauer:** ~15 Minuten.

---

## 1. Executive Summary: Was ist fertig?

| Komponente | PR | Status | Tests |
|---|---|---|---|
| Chat-Anbindung Speicher-Entscheidungslogik | #46 | ✅ Gemergt | 16 neue Tests |
| Export & Löschung (Art. 20/17 DSGVO) | #47 | ✅ Gemergt | 10 neue Tests |
| CI-Fix (verwaiste Tests deaktiviert) | — | ✅ Umgesetzt | 936/936 grün |

**Aktueller Stand:** `main` hat 936/936 Tests grün, alle Governance-Pipelines aktiv, System produktionsreif für Block C.

---

## 2. Architektur-Überblick (UNVERHANDELBAR)

Die folgenden Komponenten sind **stabil und zentral** — keine Änderungen ohne explizite Genehmigung:

### 2.1 Autarker Betrieb (SQLite, nicht Neon/Cloud)
- **Primary:** SQLite in `/data`-Docker-Volume (`sqlite:////data/ailiza.sqlite`)
- **Datenbank:** Automatisch erstellt beim ersten Start
- **Verifikation (lokal):** `docker compose up -d` + Chat-Anfrage + `sqlite3 /data/ailiza.sqlite ".tables"` sollte alle Tabellen zeigen

### 2.2 Memory-Kernschema (3-lagig)
```sql
memory_suggestions    -- Vorschläge aus Chat (status: open|confirmed|rejected|expired|needs_admin_approval|blocked)
memory_items          -- Akzeptierte Speichereinträge (memory_kind: user_memory|company_memory, visibility: private|restricted|internal)
memory_visibility     -- Wer darf was sehen (tenant_id, user_id, access_level)
user_settings         -- Benutzerpräferenzen, getrennt von users-Tabelle
```

### 2.3 Governance-Pipeline (NIEMALS umgehen)
Jeder externe LLM-Call durchläuft diese Reihenfolge:
1. **Kill-Switch** (`enforce_kill_switch`) — `AILIZA_EXTERNAL_LLM_ENABLED=false` => keine externen Calls
2. **Data Governance** (`classify()`) — 5 Klassifikations-Kategorien
3. **Policy-Gateway** (`evaluate_policy()`) — Modell-Routing, Token-Budget
4. **Redaction** — PII/Secrets entfernen vor externem Send
5. **Provider-Orchestrator** — LLM-Call durchführen

**Fail-closed:** Bei Unklarheit nicht extern senden.

### 2.4 Entscheidungslogik (deterministic, kein LLM)
```python
decide_memory_storage(input_text, user_id, tenant_id)
  ├─ classify_info_kind()       # Pattern-basiert, nutzt bestehende classify()
  ├─ memory_kind erzeugen       # user_memory oder company_memory
  ├─ Blockierungsregeln prüfen  # Z.B. secret => blockiert, normal => ok
  └─ memory_suggestion erzeugen # Status: open (wartet auf Bestätigung)
```

**Wichtig:** `decide_memory_storage()` ist deterministic, braucht KEIN LLM, und läuft best-effort im Chat-Response-Flow.

---

## 3. Implementierte Features (Block B)

### 3.1 Chat-Anbindung (PR #46)

**Was passiert jetzt:**
1. Nutzer schreibt eine Chat-Anfrage
2. Agent antwortet normal
3. Danach (best-effort, nie blockierend): `_maybe_suggest_memory()` läuft
4. Wenn `decide_memory_storage()` einen Vorschlag erzeugt → UI zeigt "Merken / Nicht merken" Button
5. Nutzer klickt → `POST /api/memory-suggestions/{id}/confirm` oder `/reject`

**Neue Endpoints:**
- `GET /api/memory-suggestions` — Liste aller offenen Vorschläge für aktuellen Nutzer
- `POST /api/memory-suggestions/{id}/confirm` — Akzeptiert, erstellt `memory_items` Eintrag
- `POST /api/memory-suggestions/{id}/reject` — Lehnt ab, setzt Status `rejected`

**Frontend-Integration:**
- Minimal: Nach `addAiMessage()`, wenn `data.memory_suggestion` existiert, `appendActionRow()` mit zwei Buttons aufrufen
- Bestehende Pattern wurde beibehalten (kein neues UI-Framework)

**Tests:** 16 neue Tests in `tests/test_memory_chat_integration.py`
- Klassifikation funktioniert (kein LLM)
- Blockierungsregeln greifen
- Confirm/Reject-API funktioniert
- Best-effort Fehlerbehandlung (Exception blockiert nie die Chat-Antwort)

### 3.2 Export & Löschung (PR #47)

**Was neu ist:**

#### `GET /api/me/export` — DSGVO Art. 20 (Datenportabilität)
```json
{
  "user": { "id", "email", "created_at", "language" },
  "memory_items": [
    { "id", "content", "memory_kind", "created_at", "visibility" }
  ],
  "chats": [ { "id", "title", "created_at" } ],
  "user_settings": [ { "key", "value" } ]
}
```
- **Ausgeschlossen:** `hashed_password`, fremde Nutzerdaten, nicht-eigene Memory-Einträge
- **Audit-Log:** "export_triggered" (kein Inhalt, nur Code)

#### `DELETE /api/me` — DSGVO Art. 17 (Recht auf Vergessenwerden)
- **Strategie:** Deaktivierung statt Hard-Delete (Karo-Entscheidung)
- **Was passiert:**
  1. `active=0` in `users`-Tabelle (Soft-Delete)
  2. Alle abhängigen Daten werden gelöscht:
     - `user_projects` (komplett)
     - `user_chats` (komplett)
     - `user_settings` (komplett)
     - `memory_suggestions` (nur des Nutzers)
     - `memory_items` (soft-deleted: `deleted_at` gesetzt, nicht komplett gelöscht)
  3. **Transaktion:** Alles-oder-nichts in single `engine.begin()` Block
- **Nach Löschung:** Login unmöglich (active=0 wird gecheckt), aber Datensätze bleiben für Audit
- **Audit-Log:** "account_deactivated" + "data_deleted" (kein Inhalt)

**Tests:** 10 neue Tests in `tests/test_user_export_deletion.py`
- Export-Inhalt/Isolation/Scope korrekt
- Transaktionalität: bei Exception wird nichts gelöscht
- Login nach Löschung unmöglich
- Audit-Einträge vorhanden

### 3.3 CI-Fix (Option B umgesetzt)

**Problem:** Verwaiste `apps/backend/tests/` Ordner mit 7 Collection-Errors
- Kaputte Imports auf nicht existierende Module: `compliance_auditor`, `KillSwitch`, `policy_engine`, `governance`, `main`, `require_operator`

**Lösung:** Legacy-Test-Schritt in `.github/workflows/ci.yml` auskommentiert, Ordner NICHT gelöscht
- Ordner bleibt unangetastet für später (separate Entscheidung: löschen oder reparieren)
- Aktive Test-Suite: `pytest tests/` (936/936 grün)
- CI wird nur noch bei Root-Tests gemessen

**Ergebnis:** CI grün, beide PRs gemergt, Entscheidung über Aufräumen aufgeschoben.

---

## 4. Code-Struktur: Wo ist was?

```
apps/backend/
├── database.py
│   ├── memory_items, memory_suggestions, memory_visibility Tabellen
│   ├── decide_memory_storage()
│   ├── confirm_memory_suggestion(), reject_memory_suggestion()
│   ├── export_user_data()
│   ├── delete_own_account_data()
│   └── Alle Table-Def sind auto-created mit SQLAlchemy
│
├── main.py
│   ├── classify_info_kind_for_memory()      # Pattern-basiert, nutzt existing classify()
│   ├── _maybe_suggest_memory()               # Best-effort Wrapper
│   ├── run_agent() → _run_agent_core()       # Thin Wrapper mit Suggestion
│   ├── POST /agent/run                       # Chat-Endpoint (mit _maybe_suggest_memory)
│   ├── GET /api/memory-suggestions           # Nutzer-Vorschläge auflisten
│   ├── POST /api/memory-suggestions/{}/confirm, /reject
│   ├── GET /api/me/export                    # DSGVO Export
│   └── DELETE /api/me                        # DSGVO Löschung
│
├── governance/                               # Keine Änderungen seit Block A
│   ├── data_governance.py (classify)
│   ├── redaction.py
│   └── ...
│
└── providers/orchestrator.py                 # Provider-Routing
```

**Wichtig für nächste Agent:** Diese Struktur ist STABIL. Keine Umbauten ohne Genehmigung.

---

## 5. Tests: Wie Qualität gesichert wird

### 5.1 Test-Suite Struktur

**Aktiv (in CI):**
```bash
pytest tests/ -v --tb=short
```
- `tests/test_memory_chat_integration.py` (16 Tests)
- `tests/test_user_export_deletion.py` (10 Tests)
- Alle bestehenden Governance/Policy/Routing-Tests
- **Baseline:** 936/936 grün nach PR #47

**Deaktiviert (in CI-Workflow auskommentiert):**
```bash
# pytest apps/backend/tests/ -v --tb=short    [NICHT AUSGEFÜHRT]
```
- Verwaiste Tests, kaputte Imports
- Entscheidung über Aufräumen: später, separater Auftrag

### 5.2 Wichtige Test-Patterns

**Memory-Integration Tests:**
```python
def test_decide_memory_storage_classifies_correctly():
    # Testet, dass Text korrekt klassifiziert wird
    # Nutzt KEIN LLM, pattern-basiert
    assert decide_memory_storage("Meine Diagnose...") → memory_kind="user_memory"

def test_memory_suggestion_survives_confirm():
    # Testet, dass `confirm()` memory_items erzeugt
    suggestion = create_memory_suggestion(...)
    confirm_memory_suggestion(suggestion.id)
    assert get_memory_items(user_id) → [created item]

def test_best_effort_error_doesnt_block_response():
    # Testet, dass Exception in _maybe_suggest_memory Chat nicht blockiert
    with patch("decide_memory_storage", side_effect=Exception("DB down")):
        response = client.post("/agent/run", ...)  # Muss 200 sein, nicht 500
        assert response.status_code == 200
```

**Export/Deletion Tests:**
```python
def test_export_excludes_hashed_password():
    # Testet, dass export nur sichere Felder hat
    export = export_user_data(user_id)
    assert "hashed_password" not in export

def test_delete_is_transactional():
    # Testet, dass bei Exception nichts gelöscht wird
    with patch("delete_projects", side_effect=Exception):
        delete_own_account_data(user_id)  # Sollte rollback() aufrufen
    assert user.active == 1  # Nicht gelöscht, weil Transaction failed

def test_login_after_delete_fails():
    # Testet, dass active=0 Login blockiert
    delete_own_account_data(user_id)
    with pytest.raises(UnauthorizedError):
        authenticate(user.email, password)
```

### 5.3 Lokale Verifikation vor Push

**Vor Commit:**
```bash
cd /home/user/AILIZA
pytest tests/ -v --tb=short                # Muss 936/936 sein
```

**Vor Push:**
```bash
git status                                  # Keine unerwarteten Dateien
git diff --cached                           # Review, keine Secrets
git log --oneline -5                        # Commit-Nachrichten sinnvoll
```

---

## 6. Governance-Constraints (NIEMALS verletzen)

**Aus CLAUDE.md — absolut bindend für alle nächsten Agenten:**

1. **Grundregel: Erst fragen, dann programmieren**
   - Vor jeder Code-Änderung: **ERKLÄREN WAS und WARUM**
   - Dann auf OK-Bestätigung WARTEN
   - Erst DANACH: Implementieren, Committen, Pushen

2. **Keine Secrets/PII in Logs oder Commits**
   - API-Keys, Passwörter, vollständige Prompts gehören NICHT in Log-Output
   - Audit-Logs nur Codes (z.B. "export_triggered"), nie Rohdaten

3. **Externe LLM-Calls NIEMALS direkt**
   - Nie `openai.ChatCompletion.create()` direkt in `main.py`
   - Immer durch `ProviderOrchestrator` + komplette Governance-Pipeline
   - Fail-closed: bei Unklarheit nicht senden

4. **Governance-Pipeline ist Gesetz**
   ```
   Kill-Switch → Data Governance → Policy-Gateway → Redaction → Provider-Orchestrator
   ```
   - Diese Reihenfolge ist nicht optional
   - Kein Shortcut, kein "nur dieses mal"

5. **5 DSGVO-Kategorien müssen korrekt redaktiert werden**
   - secret (⚫) > forbidden (🔴) > confidential (🟠) > high (🟡) > normal (🟢)
   - False Positives/Negatives sind Zertifizierungs-Fehler

6. **Verständliche deutsche Fehlermeldungen**
   - Nie Stack-Trace zum Client
   - Z.B. statt "KeyError: tenant_id": "Nutzer nicht gefunden"

---

## 7. Nächste Aufgaben: Was kommt nach Block B?

### 7.1 NICHT dabei: Diese sind aufgeschoben

| Task | Typ | Grund | Status |
|---|---|---|---|
| **Block C** | Wissensdatenbank + pgvector | Erfordert stabile Memory-Basis | Wartet auf Block B ✅ |
| **Block D** | Desktop-Distribution (PyInstaller) | Größerer Packagings-Auftrag | Später, separater Auftrag |
| **UI-Panel** | "Mein AILIZA-Gedächtnis" | Nur Sichtbarkeit, keine Architektur | Reine Oberfläche, kann später |
| **apps/backend/tests/ aufräumen** | Cleanup | Verwaister Ordner, Entscheidung später | Separate kleine Auftrag |

### 7.2 Wahrscheinliche nächste Priorität: Block C (Wissensdatenbank)

**Block C Outline (nicht implementiert, nur als Referenz für nächste Agent):**
- Dokumenten-Upload-Flow erweitern (PDFs, TXT)
- pgvector-Integration (Falls nicht Postgres, dann z.B. Qdrant oder Milvus)
- Relevance-Retrieval für Chat
- Governance für Dokumenten-Inhalte
- Tests für Chunk-Klassifikation + Retrieval

**Vorbereitungen bereits done:**
- Governance-Pipeline existiert (kann für Dokumente genutzt werden)
- Memory-Schema ist stabil (Dokumente könnten als `company_memory` speichern)

---

## 8. Git-Workflow (BINDEND für alle Commits)

### 8.1 Entwicklungs-Branch
```bash
git fetch origin
git checkout -B claude/adoring-lamport-c1zs8h origin/main
# oder: branch erstellen, falls noch nicht existent
git checkout -b claude/adoring-lamport-c1zs8h
```

### 8.2 Commits schreiben

**Format (mit Trailer):**
```
Kurze, aussagekräftige Nachricht (< 70 Zeichen).

Längere Beschreibung falls nötig (Absätze getrennt).

Co-Authored-By: Claude <nächster Agent> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_... [wenn verfügbar]
```

**Wichtig:**
- Jeder Commit sollte logisch abgeschlossen sein
- Keine "half-finished" Implementierungen
- Tests müssen am Ende grün sein

### 8.3 Push

```bash
git push -u origin claude/adoring-lamport-c1zs8h
```

**Bei Netzwerkfehlern:** Bis zu 4× mit exponentiellem Backoff (2s, 4s, 8s, 16s) wiederholen.

### 8.4 Pull Requests

**Nur mit expliziter Genehmigung von Karo erstellen.**
- Nutze PR-Template (`.github/pull_request_template.md` falls vorhanden)
- Beschreibe WAS geändert wurde und WARUM
- CI muss grün sein

---

## 9. Model-Empfehlung für nächste Agent

**Standard (>90% der Zeit):** Sonnet 5
- Iterative Entwicklung, Bugfixing, Pattern-Implementierung
- Gutes Preis-Leistungs-Verhältnis für längere Sessions
- Für Block C (Vektorsuche, Dokumenten-Governance) ausreichend

**Opus 4.8:** Nur für
- Große Architektur-Entscheidungen (z.B. pgvector vs. Qdrant)
- DSGVO/EU AI Act Compliance-Analysen (Art. 9 Kategorisierung)
- Code-Review vor Meilensteinen

**Haiku:** Nur triviale Tasks (Syntax, Status-Checks)

**PFLICHT:** Jede Antwort muss explizit nennen, welches Modell für die Aufgabe empfohlen wird. Z.B.: "Empfehlung: Sonnet 5 (Block C Dokumenten-Integration)."

---

## 10. PC-Wechsel in ~1 Woche: Was beachten

**Nach Übertragung auf neuen PC:**
```bash
# WICHTIG: AILIZA_DATABASE_URL muss neu gesetzt werden!
export AILIZA_DATABASE_URL="sqlite:////data/ailiza.sqlite"
# oder für lokalen Python-Start ohne Docker:
export AILIZA_DATABASE_URL="sqlite:///./local_ailiza.sqlite"
```

**Warnsystem:** `_resolve_database_url()` in `apps/backend/database.py` warnt, wenn Variable nicht gesetzt → fallback auf relativen Dev-Pfad (kein Datenverlust-Risiko ohne explizite Warnung).

**Verifikation:**
```bash
docker compose up -d
# In neuem Terminal:
curl http://localhost:8001/api/health
# Sollte 200 sein
sqlite3 /data/ailiza.sqlite ".tables"
# Sollte alle Tabellen zeigen (users, memory_items, etc.)
```

---

## 11. Debugging & Häufige Fehler

### 11.1 Fehler: "AttributeError: module 'X' has no attribute 'Y'"

**Ursache:** Verwaiste Imports aus gelöschten Modulen (z.B. `compliance_auditor`)
- Betrifft nur `apps/backend/tests/` (nicht aktiv in CI)
- Root `tests/` sollte immer grün sein

**Lösung:**
```bash
pytest tests/ -v --tb=short  # Nutzt nur Root-Tests
# ✅ Sollte 936/936 sein
```

### 11.2 Fehler: "AILIZA_DATABASE_URL not set"

**Ursache:** Environment-Variable fehlt
**Lösung:**
```bash
export AILIZA_DATABASE_URL="sqlite:////data/ailiza.sqlite"
# oder in .env:
AILIZA_DATABASE_URL=sqlite:////data/ailiza.sqlite
```

### 11.3 Fehler: "TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'"

**Häufig:** PII-Redaction hat `None` statt Safe-String zurückgegeben
**Lösung:** Redaction-Code checken, `or ""` einfügen

### 11.4 Fehler: "TransactionRollbackError"

**Häufig:** Datenbankoperation in falscher Transaction-Scope
**Lösung:** `engine.begin()` nutzen statt Einzelaufrufe (siehe `delete_own_account_data()`)

---

## 12. Handoff-Checkliste für nächste Agent

Wenn ihr diese Datei lest:

- [ ] `docs/HANDOFF_DATENBANK_GEDAECHTNIS.md` gelesen (Status, offene Fragen)
- [ ] `CLAUDE.md` gelesen (Governance-Constraints)
- [ ] `main` branch lokal gechekt: `git checkout main && git pull`
- [ ] Tests lokal grün: `pytest tests/ -v`
- [ ] Docker-Umgebung startet: `docker compose up -d`
- [ ] `/api/health` antwortet: `curl http://localhost:8001/api/health`
- [ ] Entwicklungs-Branch erstellt: `git checkout -b claude/adoring-lamport-c1zs8h`
- [ ] AILIZA_DATABASE_URL für euren PC gesetzt (siehe Punkt 10)

Wenn alle Häkchen gesetzt sind: **Ready for next block!**

---

## 13. Kontakt & Fragen

**Bei Unklarheiten:**
- Erst README/HANDOFF-Docs lesen
- Dann Karo fragen, nicht raten
- **GRUNDREGEL:** Erst fragen, dann programmieren

**Wichtige Kommandos für Quick-Start:**
```bash
cd /home/user/AILIZA

# Develop Branch
git checkout -b claude/adoring-lamport-c1zs8h 2>/dev/null || \
  git checkout claude/adoring-lamport-c1zs8h

# Tests lokal
pytest tests/ -v --tb=short

# Docker starten
docker compose up -d

# Backend Logs
docker logs -f ailiza-backend

# Datenbank inspizieren
sqlite3 /data/ailiza.sqlite ".schema memory_items"
```

---

**Stand:** 21.07.2026 · Block B komplett gemergt · 936/936 Tests grün · Bereit für Block C.

*Viel Erfolg bei der Fortsetzung! 🚀*
