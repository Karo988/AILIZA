# Spec: Audit-Vault Stufe 2 — SHA-256 Hash-Chain

**Status:** Umgesetzt  
**Version:** 1.0  
**Dateien:** `apps/backend/database.py`, `apps/backend/audit/vault.py`, `apps/backend/main.py`

---

## Ziel

Manipulationsschutz für Audit-Logs durch append-only SHA-256 Hash-Chain.
Jeder Eintrag enthält den Hash seines Vorgängers. Änderung eines Eintrags
bricht die Kette an genau dieser Stelle.

---

## Datenmodell

```sql
audit_logs (
  id            INTEGER PRIMARY KEY,
  timestamp     DATETIME NOT NULL,
  action        VARCHAR(128) NOT NULL,
  tenant_id     VARCHAR(64) NOT NULL,
  metadata      JSON,
  previous_hash VARCHAR(64) NOT NULL DEFAULT '0000...0000',  -- 64 Nullen = Genesis
  entry_hash    VARCHAR(64) NOT NULL DEFAULT ''
)
```

---

## Hash-Formel

```
SHA-256( "{id}|{timestamp_iso}|{action}|{tenant_id}|{previous_hash}" )
```

Beispiel für Eintrag #1 (Genesis):
```
previous_hash = "0000000000000000000000000000000000000000000000000000000000000000"
entry_hash    = SHA-256("1|2026-06-23T10:00:00+00:00|startup.init|default|0000...0000")
```

---

## Zwei-Phasen-Insert

Da die `id` erst nach dem INSERT bekannt ist, läuft der Write in zwei Phasen:

1. INSERT mit `entry_hash = "pending"` → erhält `entry_id`
2. UPDATE mit berechnetem Hash: `_compute_audit_hash(entry_id, ts_str, action, tenant_id, previous_hash)`

Beide Schritte laufen in einer `engine.begin()` Transaktion.

---

## Verifikation

`verify_audit_chain(tenant_id=None, limit=5000)` in `audit/vault.py`:

1. Liest alle Einträge chronologisch (ORDER BY id ASC)
2. Berechnet jeden Hash neu
3. Prüft: `previous_hash == expected_previous` UND `stored_hash == computed`
4. Gibt `first_invalid_id` zurück bei erstem Fehler

Endpunkt: `GET /admin/audit/verify` (Admin-only)
- Bei Befund: schreibt Audit-Event `audit.chain.manipulation_detected`
- Gibt keinerlei Audit-Inhalt zurück, nur Prüfergebnis

---

## Einschränkungen

- Bestehende DB-Einträge (vor der Migration) haben `entry_hash = ""` — Genesis-Hash wird dort als `"0"*64` behandelt
- WORM-Option (Write Once Read Many via Filesystem-Flag) ist als nächste Stufe geplant, aber noch nicht umgesetzt
- Max. 10.000 Einträge pro Verifikationslauf (Schutz vor Timeout)
