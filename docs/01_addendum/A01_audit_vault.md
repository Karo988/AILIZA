# A01 — Audit Vault Korrekturen

**Datum:** 24.06.2026

## Bugfix: verify_chain() unvollständig

**Problem:** `verify_chain()` prüfte nur den `entry_hash`, nicht das gespeicherte `previous_hash`-Feld. Eine gezielte Manipulation des `previous_hash`-Felds in der DB blieb unentdeckt.

**Fix:** Zwei unabhängige Prüfungen pro Eintrag:
1. `row["previous_hash"]` muss mit dem laufenden Hash der Kette übereinstimmen
2. Reberechneter `entry_hash` muss mit dem gespeicherten `entry_hash` übereinstimmen

**Datei:** `apps/backend/audit/vault.py`

## Aktuelle Vault-Garantien

- Write-once: keine UPDATE/DELETE-Pfade in der Schnittstelle
- Kein Inhalt: nur `event_type`, `actor_id`, `timestamp_iso`, `previous_hash`, `entry_hash`
- Manipulationsprüfung: `verify_chain()` erkennt Änderungen an allen Feldern
- Export: `export()` liefert alle Einträge im JSON-fähigen Format

## Offene Punkte

- Exportformat noch nicht standardisiert (→ G-02)
- Vault lebt nur im Prozess — kein persistentes DB-Backend außerhalb SQLite in-memory (→ G-01)
