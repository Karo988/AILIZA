# Audit-Vault — Konzept und Richtlinien

**Stand:** 2026-06-23  
**Status:** Implementiert (Stufe 1)  
**Rechtsgrundlage:** DSGVO Art. 5(1)(f), Art. 30, Art. 32; EU AI Act Art. 12, Art. 19

---

## Prinzipien

### Append-only
Audit-Einträge werden ausschließlich geschrieben — niemals geändert oder gelöscht
(außer expliziter DSGVO-Art.-17-Aufträge mit Dokumentation und Vier-Augen-Prinzip).

### Keine Rohdaten
Folgende Felder werden aus Audit-Exports herausgefiltert:
`task_content`, `prompt`, `input_summary`, `credentials`, `secret`, `totp`, `backup_code`, `password`, `token`

Erlaubt: `id`, `timestamp`, `action`, `tenant_id`, `metadata` (gefiltert).

### Admin-only
`GET /admin/audit/events`, `GET /admin/audit/export`, `GET /admin/audit/retention-report`
erfordern `Role.ADMIN`. Kein Zugriff für reguläre Nutzer.

### Retention-Report ≠ Retention-Cleanup
Der Report-Endpunkt zeigt nur, wie viele Einträge älter als N Tage sind.
**Kein automatisches Löschen.** Jede Löschung erfordert:
1. Expliziten schriftlichen Admin-Auftrag
2. DSGVO-Dokumentation (Art. 17 oder Art. 5(1)(e))
3. Vier-Augen-Prinzip in Produktion

---

## API-Endpunkte (Stufe 1)

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| `GET` | `/admin/audit/events` | Paginierte Events, max. 1000 |
| `GET` | `/admin/audit/export` | Export als JSON oder JSONL, max. 1000 |
| `GET` | `/admin/audit/retention-report` | Zählung älterer Einträge, kein DELETE |

### Query-Parameter (gemeinsam)

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `action` | string | Filter auf Aktionstyp (z. B. `auth.login.success`) |
| `tenant_id` | string | Filter auf Mandant |
| `timestamp_from` | ISO 8601 | Untere Zeitgrenze |
| `timestamp_to` | ISO 8601 | Obere Zeitgrenze |
| `limit` | int (1–1000) | Seitengröße |
| `offset` | int (≥0) | Seitenoffset |
| `fmt` | `json`\|`jsonl` | Nur für `/export` |

---

## Erlaubte Audit-Felder (Metadaten)

Folgende Felder dürfen im `metadata`-Objekt eines Audit-Eintrags stehen:

| Feld | Beispielwert |
|------|-------------|
| `capability` | `"analyze_document"` |
| `decision` | `"allow"` / `"block"` |
| `risk_level` | `"LOW"` / `"HIGH"` |
| `data_class` | `"public"` / `"personal_data"` |
| `provider_id` | `"groq-llama3"` |
| `status` | `"completed"` |
| `rule_id` | `"gate6.injection"` |
| `file_type` | `".txt"` |
| `size_bytes` | `1024` |
| `user_id` | pseudonymisierte ID |
| `role` | `"admin"` |
| `injection_detected` | `true` |
| `pattern_count` | `2` |

---

## Explizit verboten im Audit

- `task_content` — Aufgabeninhalte
- `prompt` — vollständige Prompts
- `input_summary` — Zusammenfassungen von Eingaben
- `credentials`, `secret`, `totp`, `backup_code`, `password`, `token` — Authentifizierungsdaten
- Telegram-Nachrichteninhalte
- Vollständige Fehlermeldungen mit Stack-Trace

---

## Geplant: Stufe 2

- Audit-Vault-Signierung (HMAC oder Merkle-Tree) zur Manipulationserkennung
- Separate verschlüsselte Vault-Datenbank (AES-256-GCM)
- Automatische DSGVO-Art.-17-Dokumentations-Pipeline
- Rate-Limiting auf Audit-Export-Endpunkte
