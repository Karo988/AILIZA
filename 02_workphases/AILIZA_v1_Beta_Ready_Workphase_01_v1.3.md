# AILIZA v1.0 Beta Ready — Workphase 01 v1.3

**Version:** 1.3
**Status:** Aktiver Arbeitsstand — erstellt nach erfolgreicher Umsetzung und Prüfung
**Vorgänger:** v1.2 (`02_workphases/AILIZA_v1_Beta_Ready_Workphase_01_v1.2.md`)
**Branch:** `feature/memory-governance-ui-v1.3`
**Arbeitspaket:** AP-MEMGOV-UI-001 — Memory-Governance UI und Lösch-Audit

---

## Was in dieser Phase umgesetzt wurde (Woche 3 abgeschlossen)

### Backend (bereits vorher grün, unverändert in dieser Runde)

| # | Aufgabe | Datei | Status |
|---|---|---|---|
| 3.1 | `GET /memory/facts` — eigene Memory-Facts, Tenant-/Owner-gefiltert, `scope=="user_memory"` | `apps/backend/routers/approvals.py` | ✅ |
| 3.2 | `DELETE /memory/facts/{id}` — Soft-Delete, generisches 404, `memory_visibility`-Bereinigung | `apps/backend/routers/approvals.py` | ✅ |
| 3.3 | Audit-Event `memory.deleted` in derselben Transaktion wie die Löschung (Hash-Chain, kein Rohinhalt) | `apps/backend/routers/approvals.py` | ✅ |
| 3.4 | Backend-Tests (Auth-Pflicht, Tenant-/User-Trennung, generisches 404, Audit-Inhalt, Rollback bei Audit-Fehler) | `tests/test_memory_self_service.py` | ✅ |

### Frontend — Korrektur in dieser Runde

**Befund vor dieser Runde:** Die ursprüngliche Umsetzung band die Oberfläche
ausschließlich in `apps/frontend/src/components/MemorySettings.jsx`
(React/Vite) ein. `apps/backend/main.py` liefert für alle Routen jedoch
`FileResponse(FRONTEND_DIR / "index.html")` aus — die statische Vanilla-JS-Datei
`apps/frontend/index.html`. Es existiert kein Build-Schritt, der
`apps/frontend/src/` in das ausgelieferte Frontend übersetzt. Die React-Komponente
war damit für keinen echten Nutzer sichtbar oder bedienbar.

**Korrektur:** Die Memory-Governance-Oberfläche wurde zusätzlich direkt in
`apps/frontend/index.html` (das tatsächlich ausgelieferte Frontend) portiert —
im bestehenden Bereich „Compliance & Status“, direkt neben dem vorhandenen
DSGVO-Art.-17-Löschbereich.

| # | Aufgabe | Datei | Status |
|---|---|---|---|
| 3.5 | Karte „Mein persönliches Gedächtnis“ mit den Zuständen Laden / Liste / leer / Ladefehler | `apps/frontend/index.html` | ✅ |
| 3.6 | Gestalteter In-App-Bestätigungsdialog statt `window.confirm()` (erklärt: welche Erinnerung, dass Unternehmenswissen nicht betroffen ist, Abbrechen/Bestätigen) | `apps/frontend/index.html` | ✅ |
| 3.7 | Löschfluss mit Lade-/Erfolgs-/Fehlerzustand, keine internen IDs/Stacktraces sichtbar | `apps/frontend/index.html` | ✅ |
| 3.8 | Test gegen das **tatsächlich ausgelieferte** Frontend (TestClient GET `/`, prüft Markup, `/memory/facts`-Aufruf, erreichbare Löschfunktion) | `tests/test_frontend_memory_governance_delivered.py` | ✅ |
| 3.9 | Fehlerhafter Breakpoint-Test korrigiert (CSS nutzt `760px`, Test erwartete `640px`) | `tests/test_frontend_memory_settings_static.py` | ✅ |

**Hinweis:** `apps/frontend/src/components/MemorySettings.jsx` und die
React-Anbindung in `apps/frontend/src/App.jsx` wurden nicht gelöscht (nicht
Teil dieses Arbeitsauftrags) — sie sind weiterhin unbenutzter, unerreichter
Code. Empfehlung für eine spätere, separat freizugebende Aufräumrunde: diese
Dateien entweder entfernen oder das Projekt auf einen echten Vite-Build
umstellen, damit nicht erneut Funktionen "implementiert" werden, ohne je
ausgeliefert zu werden.

---

## Testergebnis

```
python -m pytest tests/ -q
1064 passed, 2 warnings
```

Keine Regressionen. Diff-Scope: `apps/frontend/index.html`,
`tests/test_frontend_memory_governance_delivered.py` (neu),
`tests/test_frontend_memory_settings_static.py` (Breakpoint-Fix).
Kein Backend-Code verändert — Mandantentrennung, `scope=="user_memory"`,
Audit-Transaktion und generisches 404-Verhalten sind unangetastet.

**Nicht in dieser Runde geprüft:** Bedienung im echten Browser (Sandbox
erlaubt keinen lokal gebundenen Server-Prozess für einen manuellen
Klick-Test). Stattdessen wurde die Erreichbarkeit über `TestClient` gegen
die echte FastAPI-Route `GET /` nachgewiesen — das ist derselbe Pfad, den
ein Browser nimmt, aber kein Ersatz für einen visuellen Test. Vor
Produktionsfreigabe empfiehlt sich ein kurzer manueller Check.

---

## Was noch offen ist (Woche 4–5, unverändert aus v1.2)

### Woche 4 — Freigabe-UI (Human Oversight)

- `GET /admin/approvals` — Frontend für offene Freigaben
- Genehmigen / Ablehnen mit Audit-Event (`approval.granted`, `approval.rejected`)

### Woche 5 — Fehlende Audit-Events + CORS + Backup

- `provider.blocked`, `capability.blocked`, `memory.stored`, `incident.detected`
- CORS Wildcard → explizite Origins
- SQLite Backup-Strategie (Cron)

---

## Permanente Sperren (unverändert aus v1.2)

Kein Schritt dieser Phase und keine Folgeversion darf diese Sperren aufheben
ohne explizite schriftliche Freigabe durch den Admin mit DSGVO-Dokumentation:

- Autonome HR-Entscheidungen
- Autonome Buchhaltungsentscheidungen
- Automatische Vertragsfreigabe ohne Mensch
- Verarbeitung von Gesundheitsdaten
- Unkontrollierte Websuche
- Provider-Training auf Kundendaten
- Provider ohne AVV bei personenbezogenen Daten
- Provider ohne Löschkonzept

---

*Kein Merge nach `main` ohne ausdrückliche Freigabe.*
