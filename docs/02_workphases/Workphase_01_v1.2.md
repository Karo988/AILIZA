# Workphase 01 — v1.2 (aktiv)

**Ziel:** Von Spec-ready zu Tech-ready

## Abgeschlossen

| Aufgabe | Tests |
|---------|-------|
| MemoryEntry + Enums (purpose, visibility, data_class) | 26 ✅ |
| MemoryStore (add, get, list_active, deactivate, purge_expired) | — |
| Audit Vault (Hash-Kette, write-once, verify_chain, export) | 22 ✅ |
| Kill Switch (4 Ebenen, 2 Modi, Change-Log) | 15 ✅ |
| Kill Switch in gateway.py eingebunden | — |
| verify_chain()-Bugfix | — |
| DataClass Sicherheitsklassifizierung | 6 ✅ |

**Gesamtstand:** 87/87 Tests grün

## Offen

| Aufgabe | Blocker |
|---------|---------|
| Memory-Backend SQLite-Persistenz | — |
| BS-14–18 auf persistentem Backend schließen | Memory-Backend |
| Kill-Switch Persistenz | — |
| Readiness-Gate Tech-ready setzen | obige Punkte |

## Readiness

| Ebene | Status |
|-------|--------|
| Prompt-ready | ✅ |
| Spec-ready | ✅ |
| Tech-ready | ❌ — erst nach persistentem Backend + Tests |
