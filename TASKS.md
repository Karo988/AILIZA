# AILIZA — Aufgaben-Board

## Fertig

- [x] Block B (B0–B8b): Requirements, Testmodus-Banner, Static-Whitelist,
      config.js-Fix, Beta-Zugangsschutz, Hochrisiko-Abschaltung
- [x] Incident-Revert (passlib-Login, Art.-52-Regression) — PR #8/#9/#10
- [x] Branch-Schutz auf `main` aktiv
- [x] Debug-Endpoint Kill-Switch-Fix (`11779cb`) — verifiziert, Tests grün
- [x] VISION.md / TASKS.md angelegt
- [x] Compliance-Auditor-Bug: blockierte 100% aller Nachrichten (Art.-6-Regel)
- [x] B1: Login-Pflicht für /approvals/{id}/approve und /reject
- [x] B2a: Drei-Stufen-Modell statt Hartblock (Schwärzung zuerst, dann
      Compliance; Fall 1 frei / Fall 2 Login+Doku / Fall 3 Login+Einwilligung)
- [x] B2b: Frontend-Gates (login_required/consent_required) + Login-Modal

## In Arbeit

- [ ] Docker-Staging (`AILIZA-stagin`) Funktionscheckliste — Claude Code
      (Health ✓, Beta-Gate ✓, Golden-Brief ✓ — Rest nach B2-Deploy erneut)

## Review nötig

- [ ] B2 auf Staging live testen (Betreiberin, Browser): Fall 1/2/3 + Login

## Backlog

- [ ] **Feature „Projekt-Freigabe / Kollaboration"** (nach TS3b): Projekte für
      Kollegen freigeben — NICHT per geteiltem Projekt-Passwort (keine
      Nachvollziehbarkeit, nicht einzeln entziehbar → DSGVO-Lücke), sondern per
      Einladung: Kollege mit eigenem (kostenlosem) Login, Zugriff per
      E-Mail/Einladungslink-mit-Passwort. Rolle „nur lesen" / „lesen &
      schreiben", jederzeit einzeln entziehbar, jede Änderung im Audit-Log mit
      Namen. Neue Tabelle `project_shares` (owner/grantee/role/
      invite_password_hash, bcrypt) — TS2-Isolation bleibt, Zugriff wird
      kontrolliert erweitert. Passwörter nur gehasht, nie im Klartext/Log.
- [ ] Block D: Merge-Konfliktcheck + PR Feature-Branch → main
- [ ] AVV Anthropic formal abschließen (Betreiberin, Self-Service)
- [ ] Bezahlter Render-Plan + persistente Disk entscheiden
- [ ] ENV=production + TEST_MODE entfernen (erst nach AVV)
- [ ] Alten Python-Service `AILIZA-1` pausieren (nach Staging-Verifikation)
- [ ] 58 bekannte fehlschlagende Tests sichten/erklären (nicht blockierend)
