# Nächster Arbeits-Prompt — Workphase 01 v1.3

**Ziel:** Memory-Governance UI (Woche 3)

---

## Kontext

Repository: `karo988/ailiza`  
Branch: `claude/admiring-curie-9my9rf`  
Aktueller Stand: `02_workphases/AILIZA_v1_Beta_Ready_Workphase_01_v1.2.md`

Alle v1.2-Aufgaben sind abgeschlossen (635 Tests grün, committed, gepusht).

---

## Aufgabe

Implementiere die Memory-Governance UI für AILIZA v1.0:

### Backend

1. `GET /memory/facts` — Liste aller gespeicherter Facts für den aktuellen Tenant
   - Gefiltert nach `tenant_id` aus JWT
   - Sanitized (keine `CREDENTIALS`, `SPECIAL_CATEGORY`, `HR`, `LEGAL` Inhalte)
   - Paginiert (`limit`, `offset`)
   - Mindestrolle: USER (eigene Facts) / ADMIN (alle Facts)

2. `DELETE /memory/facts/{fact_id}` — DSGVO-konforme Löschung
   - Prüft Eigentümerschaft oder ADMIN-Rolle
   - Schreibt Audit-Event `memory.deleted` mit `fact_id` und `tenant_id`
   - Kein Inhalt im Audit-Event (nur ID)

### Frontend

3. Einstellungen-Seite (oder Tab in bestehendem Dashboard)
   - Übersicht gespeicherter Facts (Zeitstempel, Typ, kein Inhalt wenn BLOCKED)
   - Lösch-Button pro Eintrag mit Bestätigungs-Dialog
   - Deutsche Fehlermeldungen
   - Kein Stack-Trace für normale Nutzer

---

## Sicherheitsregeln (unveränderlich)

- Keine echten Kundendaten in Tests
- Keine API-Keys in Code oder Logs
- Keine PII in Audit-Events
- Fail-closed: bei Unklarheit nicht löschen, sondern Fehler zurückgeben
- Nur eigene Facts löschbar (außer ADMIN)

---

## Output

1. Code-Änderungen committed und gepusht
2. Tests grün
3. `02_workphases/AILIZA_v1_Beta_Ready_Workphase_01_v1.3.md` erstellt

Commit-Text:
```
feat(v1.0): Memory-Governance UI – GET /memory/facts, DELETE /memory/facts/{id}
```
