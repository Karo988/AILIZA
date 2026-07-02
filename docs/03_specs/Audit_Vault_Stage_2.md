# Audit Vault — Spezifikation Stage 2

**Status:** Implementiert | **Datei:** `apps/backend/audit/vault.py`

## Hash-Ketten-Schema

Jeder Eintrag bindet vier unveränderliche Felder:

```
entry_hash = SHA-256(previous_hash | event_type | timestamp_iso | actor_id)
```

Startwert: `previous_hash = "0" * 64` (Genesis-Hash)

## Felder pro Eintrag

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| sequence | int | Monoton steigend, PRIMARY KEY |
| event_type | str | z.B. `CONSENT_GRANTED`, `APPROVAL_GIVEN` |
| timestamp_iso | str | UTC ISO-8601 |
| actor_id | str | Anonymisierte ID |
| previous_hash | str | SHA-256 des Vorgängers |
| entry_hash | str | SHA-256 dieses Eintrags |

**Kein `content`-Feld.** Nur Entscheidungsmetadaten.

## Manipulationsprüfung

`verify_chain()` traversiert alle Einträge aufsteigend und prüft:
1. `row["previous_hash"] == laufender Hash`
2. `SHA-256(laufender_hash | event_type | timestamp_iso | actor_id) == row["entry_hash"]`

Gibt `(True, None)` oder `(False, defekte_sequence)` zurück.

## Bekannte Grenzen

- SQLite als Storage — geeignet für Minimum, nicht für Hochlast
- Kein Exportformat-Standard (→ G-02)
