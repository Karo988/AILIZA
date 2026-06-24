# Beta-Ready Checkliste

**Letztes Update:** 24.06.2026

## Kriterien

| Kriterium | Status | Notiz |
|-----------|--------|-------|
| Memory Backend — Modelle + Enums | ✅ | `models.py`, 26 Tests |
| Memory Backend — Store-Schnittstelle | ✅ | `store.py`, In-Memory |
| Memory Backend — SQLite-Persistenz | ❌ | offen |
| Audit Vault — Hash-Kette | ✅ | `vault.py`, 22 Tests |
| Audit Vault — verify_chain() | ✅ | Bugfix eingebaut |
| Audit Vault — Export | ✅ | `export()` vorhanden |
| Kill Switch — 4 Ebenen | ✅ | `kill_switch.py`, 15 Tests |
| Kill Switch — Persistenz | ❌ | überlebt keinen Neustart |
| Policy Engine | ✅ | `policy.py`, Tests vorhanden |
| Approval Flow | ✅ | `routers/approvals.py` |
| BS-14–18 auf persistentem Backend | ❌ | wartet auf SQLite-Memory |
| Dokumentationsstruktur | ✅ | `docs/00–06` |
| Alle Tests grün | ✅ | 87/87 |

## Beta-Freigabe möglich wenn

1. SQLite-Memory-Backend implementiert und getestet
2. BS-14–18 auf persistentem Backend grün
3. Kill-Switch-Persistenz oder explizite Entscheidung dagegen
4. Tech-ready offiziell gesetzt

**Aktuell: Basis v1.0 Spec-ready — Beta noch nicht freigegeben.**
