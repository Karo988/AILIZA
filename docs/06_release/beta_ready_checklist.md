# Beta-Ready Checkliste

**Letztes Update:** 24.06.2026

## Kriterien

| Kriterium | Status | Notiz |
|-----------|--------|-------|
| Memory Backend — Modelle + Enums | ✅ | `models.py`, 26 Tests |
| Memory Backend — Store-Schnittstelle | ✅ | `store.py`, In-Memory |
| Memory Backend — SQLite-Persistenz | ✅ | `sqlite_store.py`, 19 Tests |
| Audit Vault — Hash-Kette | ✅ | `vault.py`, 22 Tests |
| Audit Vault — verify_chain() | ✅ | Bugfix eingebaut |
| Audit Vault — Export | ✅ | `export()` vorhanden |
| Kill Switch — 4 Ebenen + YAML-Config | ✅ | `kill_switch.py`, 16 Tests |
| Kill Switch — Persistenz | ✅ | accepted for v1.0 — YAML-Initialzustand |
| Policy Engine | ✅ | `policy.py`, Tests vorhanden |
| Approval Flow | ✅ | `routers/approvals.py` |
| BS-14–18 auf persistentem Backend | ✅ | SQLite-Backend + Tests |
| Dokumentationsstruktur | ✅ | `docs/00–06` |
| Alle Tests grün | ✅ | 95/95 |

## Beta-Freigabe möglich wenn

1. SQLite-Memory-Backend implementiert und getestet
2. BS-14–18 auf persistentem Backend grün
3. Kill-Switch-Persistenz oder explizite Entscheidung dagegen
4. Tech-ready offiziell gesetzt

**Aktuell: Basis v1.0 Tech-ready — Beta-Freigabe möglich nach finaler Abnahme.**
