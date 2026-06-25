# AILIZA v1.0 Beta Ready — Workphase 01 v1.2

**Version:** 1.2  
**Status:** Aktiver Arbeitsstand  
**Vorgänger:** v1.1 (im Chat, noch nicht als Datei abgelegt)  
**Branch:** `claude/admiring-curie-9my9rf`

---

## Ziel dieser Phase

Alle kritischen Lücken aus der v1.0-Blaupause schließen, die AILIZA von "v0.9 Beta" zu "v1.0 Beta Ready" bringen.

---

## Was in dieser Phase umgesetzt wurde

### Woche 1–2 (abgeschlossen)

| # | Aufgabe | Datei | Status |
|---|---|---|---|
| 1.1 | `audit_viewer`-Rolle hinzufügen | `apps/backend/auth/rbac.py` | ✅ |
| 1.2 | Audit-Endpunkte auf AUDIT_VIEWER senken | `apps/backend/main.py` | ✅ |
| 1.3 | Startup Secret-Key-Check | `apps/backend/main.py` | ✅ |
| 2.1 | `previous_hash` + `entry_hash` Spalten | `apps/backend/database.py` | ✅ |
| 2.2 | `_compute_audit_hash()` + `_get_latest_audit_hash()` | `apps/backend/database.py` | ✅ |
| 2.3 | `write_audit_entry()` mit Hash-Chain | `apps/backend/database.py` | ✅ |
| 2.4 | `verify_audit_chain()` | `apps/backend/audit/vault.py` | ✅ |
| 2.5 | `GET /admin/audit/verify` Endpunkt | `apps/backend/main.py` | ✅ |
| 2.6 | v1.0-Blaupause (10 Artefakte) | `docs/ailiza-v1.0-blueprint.md` | ✅ |

---

## Was noch offen ist (Woche 3–5)

### Woche 3 — Memory-Governance UI

- `GET /memory/facts` — Liste gespeicherter Facts
- `DELETE /memory/facts/{id}` — DSGVO-Löschung mit Audit-Event
- Frontend: Einstellungen-Seite

### Woche 4 — Freigabe-UI (Human Oversight)

- `GET /admin/approvals` — Frontend für offene Freigaben
- Genehmigen / Ablehnen mit Audit-Event (`approval.granted`, `approval.rejected`)

### Woche 5 — Fehlende Audit-Events + CORS + Backup

- `provider.blocked`, `capability.blocked`, `memory.stored`, `memory.deleted`, `incident.detected`
- CORS Wildcard → explizite Origins
- SQLite Backup-Strategie (Cron)

---

## Permanente Sperren (unveränderlich)

Kein Schritt dieser Phase und keine Folgeversion darf diese Sperren aufheben
ohne explizite schriftliche Freigabe durch den Admin mit DSGVO-Dokumentation:

- Autonome HR-Entscheidungen
- Autonome Buchhaltungsentscheidungen
- Automatische Vertragsfreigaben
- Gesundheitsdaten
- Tools ohne AVV/DPA
- Tools mit Training auf Kundendaten
- Unkontrollierte Websuche
- Alle Provider (Groq, Anthropic, Tavily) — kein AVV vorliegend

---

## Arbeitsregel

```
Chat    = Arbeitsraum
GitHub  = freigegebener Stand

Alles, was fertig ist, kommt nach GitHub.
Alles, was noch diskutiert wird, bleibt im Chat.
Jeder fertige Prompt bekommt: Dateiname · GitHub-Pfad · Version · Commit-Text
```

---

## Nächste Datei

`02_workphases/AILIZA_v1_Beta_Ready_Workphase_01_v1.3.md`  
Commit-Text: `Add Workphase 01 v1.3 with Memory-Governance UI implementation`
