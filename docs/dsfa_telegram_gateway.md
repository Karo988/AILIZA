# Datenschutz-Folgenabschätzung (DSFA) — Entwurf
## AILIZA Telegram-Gateway
**Gemäß DSGVO Art. 35 | Stand: 2026-06-20 | Version: 0.2 (Entwurf — noch nicht fachlich geprüft)**

> ⚠️ **Hinweis:** Dieses Dokument ist ein technisch erstellter DSFA-Entwurf.
> Eine belastbare DSFA erfordert zusätzlich die fachliche Prüfung durch den/die
> Datenschutzbeauftragte(n) und ggf. Konsultation der Aufsichtsbehörde (Art. 36 DSGVO).
> Dieses Dokument ersetzt keine rechtliche Beratung.

---

## 1. Beschreibung der Verarbeitung

### 1.1 Zweck
Empfang von Nutzeranfragen über Telegram, Verarbeitung durch den AILIZA-KI-Agenten
und Rücksendung einer Antwort. Rechtsgrundlage: **Art. 6 Abs. 1 lit. a DSGVO**
(informierte, freiwillige, widerrufbare Einwilligung).

### 1.2 Datenfluss

```
Nutzer (Telegram-App)
  │
  │  HTTPS (TLS 1.3)
  ▼
Telegram-Server (EU / USA — Datenübertragung Art. 46)
  │
  │  Webhook HTTPS + HMAC-SHA256-Signaturprüfung
  ▼
AILIZA Backend (selbst-gehostet)
  │
  ├─► Rate-Limit-Check (in-memory, keine Speicherung)
  ├─► Opt-in-Check (messenger_bindings-Tabelle)
  ├─► Capability-Check (keine externe Kommunikation)
  ├─► Datenschutz-Klassifikation + Redaktion (lokal)
  │
  ├─► Fast-Path: lokale Antwort (kein externer Call)
  │
  └─► [nur wenn AILIZA_EXTERNAL_LLM_ENABLED=true]
        Kill-Switch → Data Governance → Policy-Gateway
        → Redaktion → Provider-Orchestrator
              │
              ▼
        Externer LLM-Anbieter (Groq/Anthropic)
              │
              ▼
        Antwort zurück an Nutzer über Telegram
```

### 1.3 Verarbeitete Daten

| Datenkategorie | Speicherort | Aufbewahrung | Rechtsgrundlage |
|---|---|---|---|
| Telegram chat_id (pseudonymisiert via HMAC-SHA256+Pepper — keine Anonymisierung, Zuordnung mit Secret möglich) | SQLite messenger_bindings | bis Widerruf/Löschung | Art. 6 Abs. 1 lit. a |
| Telegram username (optional) | SQLite messenger_bindings | bis Widerruf/Löschung | Art. 6 Abs. 1 lit. a |
| Opt-in-Zeitstempel | SQLite messenger_bindings | bis Widerruf/Löschung | Art. 7 Abs. 1 |
| Nachrichteninhalt | **nicht** persistent gespeichert | RAM, Verarbeitungsdauer | — |
| Audit-Log (Aktion + HMAC-Pseudonym) | SQLite audit_log | 365 Tage | Art. 5 Abs. 2 (Rechenschaftspflicht) |

### 1.4 Drittanbieter

| Anbieter | Rolle | Rechtsgrundlage Drittlandtransfer | AVV |
|---|---|---|---|
| Telegram Messenger Inc. | Übertragungskanal / Verarbeiter | Art. 46 DSGVO (SCC) | Telegram AGB / DPA |
| Anthropic (optional) | LLM-Verarbeiter | Art. 46 DSGVO (SCC, US) | Anthropic Commercial API Terms |
| Groq Inc. (optional) | LLM-Verarbeiter | Art. 46 DSGVO (SCC, US) | Groq Privacy Policy / DPA |

**Hinweis:** Externe LLM-Calls nur wenn `AILIZA_EXTERNAL_LLM_ENABLED=true`. Default: `false`.

---

## 2. Notwendigkeit und Verhältnismäßigkeit

### 2.1 Zweckbindung (Art. 5 Abs. 1 lit. b)
- Nachrichteninhalt: Verarbeitung nur zur Beantwortung der konkreten Anfrage.
- Kein Training externer Modelle mit Nutzerdaten (Anthropic/Groq API-Nutzungsbedingungen bestätigen dies; **muss bei jedem Anbieterwechsel geprüft werden**).
- Keine Weitergabe an Dritte außer den oben genannten Verarbeitern.

### 2.2 Datenminimierung (Art. 5 Abs. 1 lit. c)
- Nachrichteninhalt wird **nicht** persistent gespeichert.
- Audit-Log enthält **kein** Nachrichteninhalt — nur Aktion und HMAC-Pseudonym der chat_id.
- Telegram username ist optional und nur in messenger_bindings.
- Klassifikation und Redaktion vor jedem LLM-Call (PII wird entfernt).

### 2.3 Speicherbegrenzung (Art. 5 Abs. 1 lit. e)
- Audit-Log: automatische Retention-Cleanup nach 365 Tagen.
- messenger_bindings: kein automatischer Ablauf — Nutzer muss `/loeschen` verwenden.
- **Offener Punkt:** Retention-Policy für inaktive Bindings ohne Nutzerinteraktion fehlt. **Empfehlung:** Automatische Löschung nach 12 Monaten Inaktivität implementieren.

---

## 3. Risikobewertung

| Risiko | Eintrittswahrscheinlichkeit | Schwere | Restrisiko | Maßnahme |
|---|---|---|---|---|
| Unautorisierter Webhook-Zugriff (Spoofing) | Mittel | Hoch | Niedrig | HMAC-SHA256 Webhook-Secret (in Prod Pflicht) |
| PII in LLM-Prompt | Mittel | Hoch | Niedrig | Klassifikation + Redaktion vor LLM-Call |
| Datenweitergabe an unbekannte LLM-Anbieter | Niedrig | Hoch | Niedrig | Kill-Switch, Provider-Orchestrator, AILIZA_EXTERNAL_LLM_ENABLED |
| Drittlandtransfer ohne Rechtsgrundlage | Niedrig | Hoch | Niedrig | AVV + SCC mit Anthropic/Groq prüfen |
| Brute-Force / Replay der chat_id | Niedrig | Mittel | Sehr niedrig | HMAC-SHA256 mit serverseitigem Pepper (AILIZA_SECRET_KEY) |
| Rate-Limit-Umgehung durch wechselnde IPs | Mittel | Niedrig | Niedrig | Rate-Limit per chat_id (nicht IP) |
| Datenverlust bei DB-Ausfall | Niedrig | Mittel | Niedrig | Backup-Empfehlung (siehe offene Punkte) |

---

## 4. Betroffenenrechte

| Recht | Umsetzung | Befehle |
|---|---|---|
| Auskunft (Art. 15) | Auf Anfrage über Admin-Kontakt | — |
| Berichtigung (Art. 16) | Username über Admin | — |
| Löschung (Art. 17) | Vollständige Löschung der Bindung | `/loeschen` |
| Widerruf der Einwilligung (Art. 7 Abs. 3) | Sofortige Deaktivierung, Daten bleiben | `/widerrufen` |
| Einschränkung (Art. 18) | Technisch äquivalent zum Widerruf | `/widerrufen` |
| Datenübertragbarkeit (Art. 20) | Auf Anfrage; binding-Daten sind minimal | — |
| Widerspruch (Art. 21) | Äquivalent Widerruf bei Einwilligungsverarbeitung | `/widerrufen` |

---

## 5. EU AI Act Compliance (Regulation (EU) 2024/1689)

| Anforderung | Artikel | Umsetzung |
|---|---|---|
| KI-System-Kennzeichnung | Art. 50 | Hinweis in `/start`-Nachricht + Suffix jeder Antwort |
| Transparenz über Interaktion mit KI | Art. 50 | Datenschutzhinweis beim ersten Kontakt |
| Menschliche Aufsicht | Art. 14 | Admin-Genehmigung für Skills; Kill-Switch; Opt-in-Pflicht |
| Risikomanagement | Art. 9 | Capability-Registry; mehrstufige Governance-Pipeline |
| Aufzeichnungspflicht | Art. 12 | Audit-Log (ohne Inhalt, mit Pseudonym) |

**Klassifikation des Systems:** AILIZA als Allzweck-Assistent fällt voraussichtlich in die
Kategorie **Allgemein verfügbare KI-Modelle** (Art. 51 ff.) bzw. **Minimales Risiko**,
sofern keine Hochrisiko-Anwendungsfälle (Anhang III) vorliegen. Bei Einsatz in
HR, Strafverfolgung, Bildung oder Kreditvergabe neu bewerten.

---

## 6. Technische und Organisatorische Maßnahmen (TOMs)

| Maßnahme | Status |
|---|---|
| Verschlüsselung in Transit (TLS 1.3 via Telegram) | ✅ |
| Webhook-Authentifizierung (Telegram Secret-Token oder Gateway-HMAC) | ✅ Dev: optional; Prod: hard fail wenn kein Secret gesetzt |
| HMAC-SHA256-Pseudonymisierung der chat_id (nicht Anonymisierung) | ✅ |
| Datenschutz-Klassifikation vor Verarbeitung | ✅ |
| Redaktion vor LLM-Call | ✅ |
| Kill-Switch für externe LLM-Calls | ✅ |
| Rate-Limiting pro Nutzer | ✅ |
| Fail-Closed Default (externe KI deaktiviert) | ✅ |
| Audit-Log ohne PII/Inhalt | ✅ |
| Opt-in mit Datenschutzhinweis | ✅ |
| Widerrufsrecht technisch implementiert | ✅ |
| Löschrecht technisch implementiert | ✅ |
| Mandantentrennung (tenant_id) | ✅ |
| Backup / Restore | ❌ Noch nicht implementiert |
| Retention für inaktive Bindings | ❌ Noch nicht implementiert |
| 2FA für Admin-Accounts | ❌ Noch nicht implementiert |
| AVV mit Telegram schriftlich abgeschlossen | ⚠️ Prüfen (Telegram Business) |
| AVV mit Anthropic abgeschlossen | ⚠️ Prüfen |
| AVV mit Groq abgeschlossen | ⚠️ Prüfen |

---

## 7. Offene Aktionspunkte

| # | Maßnahme | Priorität | Fälligkeit |
|---|---|---|---|
| 1 | AVV mit Telegram, Anthropic, Groq prüfen und abschließen | Hoch | Vor Produktivbetrieb |
| 2 | Retention-Policy für inaktive messenger_bindings (12 Monate) | Mittel | Sprint 2 |
| 3 | Backup/Restore-Prozess für SQLite | Hoch | Sprint 2 |
| 4 | 2FA/TOTP für ADMIN und DSB Rollen | Mittel | Sprint 3 |
| 5 | Datenschutzerklärung (Website) mit Telegram-Abschnitt ergänzen | Hoch | Vor Beta-Launch |
| 6 | Verarbeitungsverzeichnis (VVT, Art. 30) aktualisieren | Mittel | Sprint 2 |
| 7 | AILIZA_ENV=production/staging: Webhook-Secret bereits hard fail — ✅ implementiert | — | Erledigt |

---

## 8. Ergebnis

**Die Verarbeitung ist zulässig** unter den beschriebenen Bedingungen, sofern:
1. Aktionspunkte #1 (AVV) und #5 (Datenschutzerklärung) vor Produktivbetrieb abgeschlossen sind.
2. `AILIZA_TELEGRAM_WEBHOOK_SECRET` in Produktionsumgebungen gesetzt ist.
3. Externe LLM-Calls (`AILIZA_EXTERNAL_LLM_ENABLED=true`) nur nach Prüfung der AVV aktiviert werden.

**Erstellt:** 2026-06-20
**Nächste Überprüfung:** 2026-12-20 oder bei wesentlicher Änderung der Verarbeitung.
