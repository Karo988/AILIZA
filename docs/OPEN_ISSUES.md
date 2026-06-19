# Offene Punkte (AILIZA) — Stand 2026-06-19

## Erledigt in dieser Session
- [x] Legacy-Gateway-Tests (test_gateway.py) gefixt — 42 bestanden
- [x] CORS konfigurierbar via AILIZA_CORS_ORIGINS
- [x] ProviderProfile-Register (provider_profiles.py) mit statischem MVP-Register
- [x] Retention-Cleanup-Job (maintenance/retention_cleanup.py) — laeuft bei Start + manuell via POST /admin/cleanup
- [x] Dokumenten-Textextraktion: PDF (pdfplumber), DOCX (python-docx), XLSX (openpyxl) — mit graceful Fallback
- [x] Admin-Endpoints: POST /admin/cleanup, GET /admin/provider-profiles
- [x] .env.example: CORS, Tavily, alle Retention-Keys dokumentiert
- [x] Alle Tests: 95 passed (53 neue + 42 Legacy)

## Noch offen

### Sicherheit & Zugriff
- RBAC / Rollen- und Rechtemodell (Admin vs. Nutzer vs. DSB) fehlt komplett
- 2FA / starke Authentifizierung nicht implementiert
- JWT-Auth vorbereitet, aber nicht erzwungen — alle Endpunkte sind oeffentlich
- Admin-Endpunkte (/admin/*) muessen durch Auth geschuetzt werden (vor Produktion)
- CORS: Standard "*" bleibt fuer lokale Entwicklung — AILIZA_CORS_ORIGINS in .env setzen fuer Pilot

### Mandanten
- tenant_id-Basis vorhanden, aber keine echte Mandanten-UI
- Tenant-Aufloesung pro Request (z.B. aus JWT-Token) noch nicht verdrahtet
- Alle Requests laufen mit DEFAULT_TENANT_ID="default"

### Provider & Compliance
- AVV mit Groq und Anthropic pruefen und unterzeichnen
  (Bis dahin nur PUBLIC/INTERNAL extern — bereits in ProviderProfile hinterlegt)
- ProviderProfile statisch in provider_profiles.py — fuer Produktion: DB-Tabelle + Admin-UI
- eu_certified=False fuer Groq + Anthropic (US-Provider) — DSFA erforderlich vor Pilot

### DSGVO / Compliance
- DSFA (Datenschutz-Folgenabschaetzung) je Use Case noch ausstehend
- Rechtsgrundlagen-Matrix je Mandant und Use Case pruefen
- Datenschutzhinweise (Art. 13/14 DSGVO) noch nicht erstellt
- VVT (Verzeichnis von Verarbeitungstaetigkeiten) noch nicht finalisiert

### Technik
- Groq-Adapter nutzt urllib statt httpx AsyncClient (kein echtes Token-Streaming)
- Retention-Cleanup laeuft nur beim Start — APScheduler fuer staendigen Betrieb
- Memory/Reflection: opt_in=False als Safe Default — noch kein UI fuer Opt-in
- Feedback-Loop: Admin-Vorschlaege (routing_proposals) ohne Admin-UI
- Output-Guardrail in safe_stream.py: nur mit Mock getestet

### Tests
- Provider-Adapter nur mit Mocks (kein echter API-Call)
- Integration-Test (echter Server, echter HTTP-Call) fehlt

## Go-live Gates

Gate 1 (Testbetrieb, synthetische Daten): ERREICHT — alle [x] oben + 95 Tests bestanden
Gate 2 (Pilot, echte Daten): AVV + Rechtsgrundlagen + RBAC + Datenschutzhinweise + DSFA
Gate 3 (Produktion): RBAC/2FA + Incident-Prozess + Backup/Restore + AI-Literacy + Cross-Tenant-Test
