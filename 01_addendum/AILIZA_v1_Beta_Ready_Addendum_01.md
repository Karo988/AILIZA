# AILIZA v1.0 Beta Ready — Addendum 01

Korrekturen und Ergänzungen zur eingefrorenen Basis (`00_masterplan/`).

---

## A01 — AUDIT_VIEWER-Rolle (umgesetzt)

**Problem:** Externe Prüferinnen und DSB hatten keine Möglichkeit, Audit-Logs zu lesen ohne vollständige Admin-Rechte.

**Lösung:** Neue Rolle `AUDIT_VIEWER = 1` in `apps/backend/auth/rbac.py`.

Rollenhierarchie nach Korrektur:
```
USER(0) < AUDIT_VIEWER(1) < MANAGER(2) < ADMIN(3) < DSB(4)
```

Audit-Endpunkte auf `require_role(Role.AUDIT_VIEWER)` gesenkt:
- `GET /admin/audit/events`
- `GET /admin/audit/export`
- `GET /admin/audit/retention-report`

---

## A02 — Audit-Vault Stufe 2: SHA-256 Hash-Chain (umgesetzt)

**Problem:** Audit-Logs waren append-only, aber ohne Manipulationsschutz.

**Lösung:**
- `apps/backend/database.py`: Spalten `previous_hash` + `entry_hash`
- `_compute_audit_hash(entry_id, timestamp, action, tenant_id, previous_hash)` → SHA-256
- Genesis-Hash: `"0" * 64` (kein Vorgänger)
- `write_audit_entry()`: zwei Phasen (INSERT ohne ID → UPDATE mit echtem Hash)
- `apps/backend/audit/vault.py`: `verify_audit_chain()` prüft alle Einträge chronologisch
- `apps/backend/main.py`: `GET /admin/audit/verify` (Admin-only), schreibt `audit.chain.manipulation_detected` bei Befund

---

## A03 — Startup Secret-Key-Check (umgesetzt)

**Problem:** `AILIZA_SECRET_KEY` < 32 Zeichen wurde nur als Warning geloggt, nicht als Hard-Block.

**Lösung:** `apps/backend/main.py` nach `init_db()`:
- Wenn Key < 32 Zeichen → CRITICAL-Log + `AILIZA_EXTERNAL_LLM_ENABLED=false` + Audit-Event `startup.secret_key_missing`
- Service bleibt erreichbar (Health-Endpunkte antworten), aber kein externer LLM-Call möglich

---

## A04 — Freigabe-UI (offen — Woche 4)

Benötigt:
- `GET /admin/approvals` — Frontend-Seite für Admin
- Liste offener Freigabe-Anfragen mit Kontext (Aktion, Antragsteller, Risiko)
- Genehmigen / Ablehnen mit Audit-Event

---

## A05 — Memory-Governance UI (offen — Woche 3)

Benötigt:
- `GET /memory/facts` — Liste gespeicherter Facts (tenant-gefiltert, sanitized)
- `DELETE /memory/facts/{id}` — DSGVO-konforme Löschung (mit Audit-Event `memory.deleted`)
- Frontend: Einstellungen-Seite mit Übersicht und Lösch-Button

---

## Dauerhafte Sperren (unveränderlich)

Folgende Funktionen bleiben **permanent blocked** bis zur expliziten schriftlichen Freigabe durch den Admin mit DSGVO-Dokumentation:

- Autonome HR-Entscheidungen
- Autonome Buchhaltungsentscheidungen
- Automatische Vertragsfreigaben
- Verarbeitung von Gesundheitsdaten
- Tools ohne unterzeichneten AVV/DPA
- Tools mit Training auf Kundendaten
- Tools ohne Löschkonzept
- Unkontrollierte Websuche ohne Policy-Gateway
- Alle LLM-Provider (Groq, Anthropic, Tavily) — solange kein AVV vorliegt
