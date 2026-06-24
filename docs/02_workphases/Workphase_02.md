# Workphase 02 — API-Schicht für Core-Komponenten

**Gestartet:** 24.06.2026  
**Ziel:** Memory Backend, Kill Switch und Audit Vault via REST-API erreichbar machen

## Abgeschlossen

| Aufgabe | Tests | Commit |
|---------|-------|--------|
| Memory Router (`/memory/`) — CRUD + Soft-Delete + Purge | — | `84d9fc8` |
| Memory Router — Pydantic Response-Modelle | — | `76f2005` |
| Kill Switch Router (`/admin/kill-switch/`) — status, halt, resume | — | `927b0b8` |
| Kill Switch Singleton (`kill_switch_state.py`) — prozess-weit geteilt | — | `927b0b8` |
| Gateway-Korrektur: Kill Switch in `gateway/runtime_gateway.py` eingebaut | — | `927b0b8` |
| Vault Router (`/audit/vault/`) — export, stats, verify | 10 ✅ | `ae6d4d7` |

**Gesamtstand:** 117/117 Tests grün

## Wichtige Erkenntnisse

- `gateway.py` war toter Code — Python lud immer `gateway/__init__.py` → `runtime_gateway.py`
- Kill Switch war in Phase 01 in `gateway.py` eingebaut, aber nie aktiv. In Phase 02 korrekt in `runtime_gateway.py` integriert.
- Singleton-Pattern für alle Stores: Lazy-init via `get_store()` / `get_vault()` — verhindert SQLite-Fehler bei unterschiedlichen Working Directories

## Endpunkte

| Endpunkt | Methode | Beschreibung |
|----------|---------|--------------|
| `/memory` | POST | Eintrag anlegen |
| `/memory` | GET | Aktive Einträge auflisten |
| `/memory/{id}` | GET | Eintrag abrufen |
| `/memory/{id}` | DELETE | Soft-Delete (deactivate) |
| `/memory/purge` | POST | Abgelaufene bereinigen |
| `/admin/kill-switch/status` | GET | Aktueller Zustand |
| `/admin/kill-switch/halt` | POST | Stoppen (global/provider/module/capability) |
| `/admin/kill-switch/resume` | POST | Freigeben |
| `/audit/vault/export` | GET | Hash-Kette exportieren |
| `/audit/vault/stats` | GET | Statistiken |
| `/audit/vault/verify` | GET | Kettenintegrität prüfen |

## Readiness

| Ebene | Status |
|-------|--------|
| Tech-ready Phase 01 | ✅ |
| API-Schicht Phase 02 | ✅ |
