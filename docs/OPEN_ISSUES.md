# Offene Punkte (AILIZA)

## Sicherheit & Zugriff
- RBAC / Rollen- und Rechtemodell fehlt (Admin vs. Nutzer).
- 2FA / starke Authentifizierung nicht implementiert.
- API-Authentifizierung (JWT vorbereitet, nicht erzwungen).
- CORS aktuell offen (`allow_origins=["*"]`) — fuer Produktion einschraenken.

## Mandanten
- `tenant_id` ist Basis vorhanden, aber keine echte Mandanten-UI / Mandanten-Provisionierung.
- Tenant-Aufloesung pro Request (z. B. aus Auth-Token) noch nicht verdrahtet.

## Compliance
- DSFA (Datenschutz-Folgenabschaetzung) je Use Case ausstehend.
- AVV (Auftragsverarbeitungsvertraege) mit Providern (Groq US, Anthropic US) pruefen.
- ProviderProfile aktuell nur ueber `provider_profile_id` modelliert; echtes Profil-Register fehlt.
- Rechtsgrundlage je Mandant/Use-Case fuer Reflection-Facts pruefen (Opt-in != Einwilligung).

## Technik
- Dokumenten-Textextraktion fuer PDF/DOCX/XLSX ist im MVP Platzhalter.
- Streaming ueber Provider teils gechunkt statt echtem Token-Stream (Groq via urllib).
- Retention-Cleanup-Job (`expires_at`) noch nicht als Scheduler umgesetzt.
- Zwei gateway-Module (`gateway.py` + `gateway/`-Paket) — Konsolidierung empfohlen
  (Bestands-Tests `test_gateway.py` scheitern an dieser Altlast).

## Tests
- Provider-Adapter nur mit Mocks getestet (kein echter API-Call).
- Streaming-Guardrail nur Logik-getestet.
