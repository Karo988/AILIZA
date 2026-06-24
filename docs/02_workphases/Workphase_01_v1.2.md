# Workphase 01 — v1.2 (aktiv)

**Ziel:** Von Spec-ready zu Tech-ready

## Abgeschlossen

| Aufgabe | Tests |
|---------|-------|
| MemoryEntry + Enums (purpose, visibility, data_class) | 26 ✅ |
| MemoryStore In-Memory (add, get, list_active, deactivate, purge_expired) | — |
| SqliteMemoryStore — persistentes Backend | 19 ✅ |
| BS-14–18 auf SQLite-Backend geschlossen | ✅ |
| Audit Vault (Hash-Kette, write-once, verify_chain, export) | 22 ✅ |
| Kill Switch (4 Ebenen, YAML-Config, load_from_config) | 16 ✅ |
| Kill Switch in gateway.py eingebunden | — |
| verify_chain()-Bugfix | — |
| retention_until-Validierung in Store verschoben (Bugfix) | — |
| DataClass Sicherheitsklassifizierung | 6 ✅ |

**Gesamtstand:** 106/106 Tests grün

## Offen

| Aufgabe | Blocker |
|---------|---------|
| Readiness-Gate Tech-ready formal setzen | alle Punkte geschlossen ✅ |

## Readiness

| Ebene | Status |
|-------|--------|
| Prompt-ready | ✅ |
| Spec-ready | ✅ |
| Tech-ready | ❌ — erst nach persistentem Backend + Tests |
