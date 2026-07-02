# Compliance-Review — Beta-Readiness Assessment

**Stand:** 25.06.2026  
**Quelle:** Externes Review (nicht verbindliche Rechtsfreigabe)

---

## Kurzurteil

**Für interne Staging-/Pilot-Beta:** ja, wenn offene Punkte erfüllt.  
**Für "alle können es nutzen ohne DSGVO-/EU-AI-Act-Wissen":** noch nicht — Laienmodus fehlt.

---

## Was bereits stark ist

| Baustein | Status |
|----------|--------|
| Kill Switch / Local Mode | ✅ |
| Capability Registry / Policy Gateway | ✅ |
| Human Oversight / Approval Requests | ✅ |
| Audit Vault / Hash Chain | ✅ |
| Redaction / Data Governance | ✅ |
| CORS/TLS-Plan | ✅ Code bereit |
| Secret-Incident-Prozess (Groq Key) | ✅ (sofern alter Key widerrufen) |

---

## Offene Blocker vor Beta

### C1 — TLS
- `AILIZA_FORCE_HTTPS=true` mit HTTPS Redirect + HSTS korrekt umgesetzt
- Standard `false` für Render ok (TLS extern terminiert)
- **Bedingung:** Nach erstem Render-Deploy `AILIZA_FORCE_HTTPS=true` setzen und Redirect-Verhalten testen

### C2 — CORS
- Keine Wildcard als Normalfall ✅
- `AILIZA_CORS_ORIGINS` als Render-ENV korrekt
- Startup-Warnung + Audit-Event bei `CORS=*` + `AILIZA_DEBUG=false` ist gute Governance
- **Bedingung:** Render-Frontend-URL konkret eintragen (`https://dein-frontend.onrender.com`)

### Groq Key
- Alter Key muss widerrufen sein — kein Code kann das ersetzen

---

## Agent-Flow — kritische Lücken

`classify()` und `redact()` müssen **vor** jedem LLM- oder Tool-Aufruf stehen, nicht danach.

**Richtige Reihenfolge:**
```
/agent/run
  → classify(input)
  → evaluate_policy()
  → redact()
  → decide: local | external | approval_required | block
```

**Nicht:** `/agent/run` pauschal auf Login beschränken.  
**Richtig:** Normale Nutzung ohne Login möglich — aber riskante Anfragen stoppen und Approval erzeugen.

---

## Zugriffsmodell (korrigiert)

| Endpunkt | Zugriff |
|----------|---------|
| `/agent/run` | Guest + User, Rate Limit, Pre-Check, Redaction |
| `/feedback` | anonym, Rate Limit, keine sensiblen Logs |
| `/audit-logs GET` | nur Admin/Operator |
| `/audit-logs POST` | nur intern vom Backend |
| `/approvals/*` | nur eingeloggte Admins/Operatoren |
| `/admin/*` | nur Admin |

---

## Priorisierte nächste Schritte

| Priorität | Aufgabe |
|-----------|---------|
| 1 | C8 Freigabe-UI — offene Approvals für Admins sichtbar, approve/reject mit Audit-Eintrag |
| 2 | Agent-Flow: classify → evaluate_policy → redact → decide (vor LLM-Call) |
| 3 | Laienmodus / Compliance-Ampel: `OK`, `Vorsicht`, `Freigabe nötig`, `Nicht erlaubt` |
| 4 | Pflicht-Hinweise bei externem Modellaufruf, personenbezogenen Daten, HR/Recht/Finanzen |
| 5 | Use-Case-Risikoklassen: normal, sensibel, freigabepflichtig, verboten |
| 6 | DSGVO-Minimum: Rechtsgrundlage, Datenschutzhinweis, Speicher-/Löschkonzept |

---

## Beta-Ready-Checkliste (aktualisiert)

| Kriterium | Status |
|-----------|--------|
| Alter Groq-Key widerrufen | ⚠️ zu bestätigen |
| Neuer Key nur in ENV | ⚠️ zu bestätigen |
| `AILIZA_FORCE_HTTPS=true` nach Deploy getestet | ⏳ |
| `AILIZA_CORS_ORIGINS` konkret gesetzt | ⏳ |
| Admin-Routen rollenbasiert geschützt | ✅ Phase 03 |
| C8 Freigabe-UI minimal vorhanden | ⏳ nächster Schritt |
| classify/redact vor LLM-Call | ⏳ |
| Datenschutzhinweise in einfacher Sprache | ⏳ |

---

## EU AI Act / DSGVO Referenz

- EU AI Act in Kraft seit 01.08.2024, Pflichten ab 02.08.2026
- Transparenz und Risikoklassifikation bereits jetzt relevant
- DSGVO Art. 5: Rechtmäßigkeit, Transparenz, Zweckbindung, Datenminimierung, Speicherbegrenzung, Sicherheit
