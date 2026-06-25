# Pre-Staging Abnahme — Checkliste

**Stand:** 25.06.2026  
**Voraussetzung:** Alle Code-Blöcke (Phase 01–03, C8, Agent-Flow) sind abgeschlossen.

---

## Offene Punkte vor Staging-Deploy

### 1. Secret-Incident abschliessen
- [ ] Alten Groq-API-Key widerrufen (in Groq-Konsole)
- [ ] Neuen Key generieren
- [ ] Neuen Key nur als Render-ENV-Variable setzen — nie im Code
- [ ] GitHub Secret-Scanning-Alert als resolved markieren

### 2. Render-ENV setzen
```
AILIZA_FORCE_HTTPS=true
AILIZA_CORS_ORIGINS=https://<dein-frontend>.onrender.com
AILIZA_OPERATOR_KEY=<sicherer-zufallskey>
AILIZA_ADMIN_KEY=<sicherer-zufallskey>
GROQ_API_KEY=<neuer-key>
```

### 3. Staging-Smoke-Tests (manuell)

| Szenario | Erwartetes Ergebnis |
|----------|---------------------|
| Gastfrage (normal) | Antwort direkt |
| PII in Anfrage (z.B. E-Mail) | Antwort nach Redaction, kein PII in Logs |
| HR-Thema (Kündigung) | Status `pending_approval`, kein LLM-Call |
| Manipulation/Blocked | Status `blocked`, sofortiger Stop |
| Admin öffnet Freigaben-UI | Login mit API-Key, offene Approvals sichtbar |
| Admin genehmigt Approval | Audit-Eintrag, Agent führt aus |
| Admin lehnt ab | Audit-Eintrag, Agent bleibt gestoppt |
| Unbekannter API-Key | HTTP 403 auf Admin-Endpunkten |
| HTTPS-Redirect | HTTP → HTTPS redirect (nur wenn FORCE_HTTPS=true) |
| CORS falsche Origin | HTTP 403 auf API-Calls |

### 4. Nach Smoke-Tests
- [ ] Secret-Scanning-Alert schliessen
- [ ] Staging als "intern freigegeben" markieren
- [ ] Workphase_03.md abschliessen

---

## Was bereits erledigt ist

| Block | Status |
|-------|--------|
| classify → redact → decide vor LLM/Tool-Call | ✅ |
| HIGH/BLOCKED nie in plan_tool_calls() | ✅ bewiesen (Tests) |
| Admin-Routen rollenbasiert (operator/admin) | ✅ |
| C8 Freigabe-UI | ✅ |
| Audit Vault Hash-Kette | ✅ |
| Kill Switch API | ✅ |
| Memory Backend API | ✅ |
| 151/151 Tests grün | ✅ |
