# AILIZA — Technische und Organisatorische Maßnahmen (TOM-Katalog)

**Version:** 1.0  
**Stand:** 2026-06-23  
**Nächste Überprüfung:** 2026-12-23  
**Rechtsgrundlage:** DSGVO Art. 25, Art. 32; EU AI Act Art. 9, Art. 12, Art. 17  
**Verantwortlich:** AILIZA-Betreiber (technisch: System Owner)  
**Hinweis:** Dieser Katalog beschreibt den aktuellen Implementierungsstand. Er ersetzt keine Rechtsberatung. Fehlende Nachweise sind als offen markiert.

---

## Geltungsbereich

Dieser TOM-Katalog gilt für:
- AILIZA Core (Backend FastAPI, Frontend React/Vite)
- Alle Daten, die im System verarbeitet werden
- Alle externen Anbieter, die AILIZA nutzt oder künftig nutzen könnte
- Alle Nutzerinnen und Nutzer sowie Rollen im System

Er gilt **nicht** für:
- Extern betriebene Provider-Infrastruktur (separates Provider-DPA-Verfahren erforderlich)
- Daten auf Endgeräten der Nutzenden (Outside-Scope)

---

## Rollen und Verantwortlichkeiten

| Rolle | Kürzel | Aufgabe |
|---|---|---|
| System Owner | SO | Technische Gesamtverantwortung, Freigaben |
| AILIZA-Admin | ADM | Audit-Zugriff, User-Management, Retention |
| Datenschutzverantwortliche/r | DSV | DSGVO-Prüfungen, Löschaufträge, Meldepflicht |
| Entwicklung | DEV | Code, Tests, Sicherheitsmaßnahmen |
| Nutzer/in | USR | Normale Nutzung, kein Admin-Zugriff |

---

## TOM-Übersicht

| Nr. | Bereich | Maßnahme | Status |
|---|---|---|---|
| T01 | Zugriffskontrolle | Rollenbasierte Authentifizierung (RBAC) | ✅ umgesetzt |
| T02 | Zugriffskontrolle | JWT + HttpOnly Cookie | ✅ umgesetzt |
| T03 | Zugriffskontrolle | TOTP-Zweifaktor-Auth | ✅ umgesetzt |
| T04 | Zugriffskontrolle | Backup-Codes für 2FA | ✅ umgesetzt |
| T05 | Berechtigungen | Admin-Only für Audit-Vault | ✅ umgesetzt |
| T06 | Berechtigungen | Tenant-Filterung aller Daten | ✅ umgesetzt |
| T07 | Verschlüsselung | TLS für alle HTTP-Verbindungen | ⚠️ geplant |
| T08 | Verschlüsselung | Passwort-Hashing (bcrypt) | ✅ umgesetzt |
| T09 | Verschlüsselung | TOTP-Secret verschlüsselt gespeichert | ⚠️ prüfen |
| T10 | Datenminimierung | Nur Rolle und user_id im sessionStorage | ✅ umgesetzt |
| T11 | Datenminimierung | Keine Prompts/Inhalte im Audit | ✅ umgesetzt |
| T12 | Pseudonymisierung | user_id als Bezeichner, kein Klarname | ⚠️ teilweise |
| T13 | Protokollierung | Append-only Audit-Log | ✅ umgesetzt |
| T14 | Protokollierung | Sanitized Metadata (keine Secrets) | ✅ umgesetzt |
| T15 | Audit-Vault | Stufe 1 implementiert | ✅ umgesetzt |
| T16 | Audit-Vault | Stufe 2 (Retention-Cleanup-Prozess) | 🔲 offen |
| T17 | Prompt-Injection | Gate 6 Prompt-Injection-Erkennung | ✅ umgesetzt |
| T18 | Prompt-Injection | Dokument-Scan vor Verarbeitung | ✅ umgesetzt |
| T19 | Provider-Governance | Kill-Switch für externe Calls | ✅ umgesetzt |
| T20 | Provider-Governance | Provider-Orchestrator (kein Direktaufruf) | ✅ umgesetzt |
| T21 | Provider-Governance | AVV/DPA-Prüfung vor Provider-Aktivierung | 🔲 offen |
| T22 | Backup | Regelmäßige DB-Sicherung | 🔲 offen |
| T23 | Incident | Incident-Response-Prozess dokumentiert | ✅ umgesetzt |
| T24 | Tests | Automatisierte Regressionstests | ✅ umgesetzt |
| T25 | Tests | Regelmäßiger Security-Review | 🔲 offen |
| T26 | Rate Limiting | API Rate Limiting (slowapi) | ✅ umgesetzt |
| T27 | CORS | CORS-Konfiguration | ⚠️ prüfen |

---

## Detailbeschreibung je TOM

---

### T01 — Rollenbasierte Authentifizierung (RBAC)

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Jede API-Route erfordert eine geprüfte Rolle (USER, ADMIN) |
| **Ziel** | Nur autorisierte Personen können auf Daten und Funktionen zugreifen |
| **Umsetzung** | `require_role(Role.ADMIN / Role.USER)` in FastAPI Dependencies |
| **Verantwortlich** | DEV, SO |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/auth/__init__.py`, `main.py` Route-Dependencies |
| **Offene Punkte** | Feinere Berechtigungen (z.B. Read-only-Rolle) noch nicht implementiert |

---

### T02 — JWT + HttpOnly Cookie

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Session-Token als HttpOnly-Cookie, kein Token im JS-Zugriff |
| **Ziel** | Schutz vor XSS-Token-Diebstahl |
| **Umsetzung** | `ailiza_session`-Cookie, `SameSite=Strict`, kein Bearer-Token im Frontend |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/auth/jwt_handler.py`, `apps/frontend/src/api.js` |
| **Offene Punkte** | AILIZA_SECRET_KEY muss in Produktion gesetzt werden (Warnung im Log aktiv) |

---

### T03 — TOTP-Zweifaktor-Authentifizierung

| Feld | Inhalt |
|---|---|
| **Maßnahme** | TOTP (RFC 6238) als zweiter Faktor für Login |
| **Ziel** | Schutz vor Passwort-Kompromittierung |
| **Umsetzung** | `apps/backend/auth/totp.py`, Endpunkte `/auth/totp/*` |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/database.py` TOTP-Tabellen, `auth/totp.py` |
| **Offene Punkte** | TOTP-Pflicht für Admin-Accounts noch nicht erzwungen |

---

### T04 — Backup-Codes für 2FA

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Einmalige Backup-Codes als 2FA-Notfalloption |
| **Ziel** | Kontowiederherstellung ohne TOTP-Gerät |
| **Umsetzung** | Hashed Backup-Codes in DB, einmaliger Verbrauch (`consume_backup_code`) |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/database.py`, `auth/totp.py` |
| **Offene Punkte** | Keine — korrekt implementiert |

---

### T05 — Admin-Only Audit-Vault

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Audit-Export-Endpunkte nur für `Role.ADMIN` |
| **Ziel** | Normale Nutzer können Audit-Logs nicht einsehen oder exportieren |
| **Umsetzung** | `require_role(Role.ADMIN)` auf allen `/admin/audit/*` Routen |
| **Verantwortlich** | DEV, ADM |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/main.py`, `apps/backend/audit/vault.py` |
| **Offene Punkte** | Kein DELETE/UPDATE auf Audit-Daten implementiert (by design) |

---

### T06 — Tenant-Filterung

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Alle Datenbankabfragen filtern nach `tenant_id` |
| **Ziel** | Mandantentrennung: Nutzer sehen nur eigene Daten |
| **Umsetzung** | `DEFAULT_TENANT_ID`, alle Queries mit `tenant_id`-Filter |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/database.py` |
| **Offene Punkte** | Echte Multi-Tenant-Trennung auf DB-Ebene noch nicht vollständig geprüft |

---

### T07 — TLS-Verschlüsselung

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Alle HTTP-Verbindungen über TLS (HTTPS) |
| **Ziel** | Schutz der Daten im Transport |
| **Umsetzung** | In Entwicklung: HTTP. In Produktion: TLS über Reverse Proxy (nginx/caddy) erforderlich |
| **Verantwortlich** | SO, DEV |
| **Status** | ⚠️ geplant — nicht für lokale Entwicklung, Pflicht in Produktion |
| **Nachweis** | Noch kein Produktions-Deployment vorhanden |
| **Offene Punkte** | TLS-Konfiguration und Zertifikat für Produktionsbetrieb ausstehend |

---

### T08 — Passwort-Hashing

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Passwörter werden mit bcrypt gehasht gespeichert |
| **Ziel** | Passwörter nicht im Klartext, Brute-Force-Schutz |
| **Umsetzung** | `passlib[bcrypt]` in `authenticate_user` / `create_user` |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/database.py` |
| **Offene Punkte** | Keine |

---

### T09 — TOTP-Secret-Speicherung

| Feld | Inhalt |
|---|---|
| **Maßnahme** | TOTP-Secrets verschlüsselt in der Datenbank |
| **Ziel** | TOTP-Secret bei DB-Leak nicht im Klartext |
| **Umsetzung** | Aktuell: Base32-kodiert in SQLite. Verschlüsselung auf Feld-Ebene noch nicht implementiert |
| **Verantwortlich** | DEV, DSV |
| **Status** | ⚠️ prüfen — Feld-Ebenen-Verschlüsselung ausstehend |
| **Nachweis** | `apps/backend/database.py` Spalte `totp_secret` |
| **Offene Punkte** | Feld-Ebenen-Verschlüsselung für `totp_secret` vor Produktionsstart einplanen |

---

### T10 — Datenminimierung im Frontend

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Nur `role` im sessionStorage — kein Token, kein PII |
| **Ziel** | Minimale Datenspeicherung im Browser |
| **Umsetzung** | `sessionStorage.setItem("ailiza_role", data.role)` — kein user_id, kein Token |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/frontend/src/api.js` |
| **Offene Punkte** | Keine |

---

### T11 — Keine Prompts im Audit

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Audit-Einträge enthalten keine Prompts, Anfragetexte oder Nutzerinhalte |
| **Ziel** | Datensparsamkeit, kein Inhalt im Protokoll |
| **Umsetzung** | `_METADATA_BLOCKED_KEYS` in `audit/vault.py`, `audit_writer` schreibt nur Metadaten |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/audit/vault.py`, `tests/test_audit_vault.py` |
| **Offene Punkte** | Keine |

---

### T12 — Pseudonymisierung

| Feld | Inhalt |
|---|---|
| **Maßnahme** | `user_id` als Bezeichner statt Klarname oder E-Mail |
| **Ziel** | Personenbeziehbarkeit reduzieren |
| **Umsetzung** | Login und Audit-Logs verwenden `user_id`, kein Klarname im System |
| **Verantwortlich** | DEV, DSV |
| **Status** | ⚠️ teilweise — user_id kann personenbeziehbar sein je nach Vergabe |
| **Nachweis** | `apps/backend/database.py` |
| **Offene Punkte** | Prüfen ob user_id-Vergabe personenbeziehbar ist. Ggf. interne UUID nutzen |

---

### T13 — Append-only Audit-Log

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Audit-Logs werden nur geschrieben, niemals geändert oder gelöscht |
| **Ziel** | Manipulationsschutz, Nachvollziehbarkeit |
| **Umsetzung** | Kein DELETE/UPDATE auf `audit_logs`-Tabelle im Code. Vault-API hat keinen Löschendpunkt |
| **Verantwortlich** | DEV, ADM |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/audit/vault.py`, `tests/test_audit_vault.py` TestAppendOnly |
| **Offene Punkte** | Vier-Augen-Prozess für DSGVO-Art.-17-Löschung noch nicht formalisiert |

---

### T14 — Sanitized Audit Metadata

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Audit-Exports filtern sensible Schlüssel aus Metadaten |
| **Ziel** | Keine Secrets, Tokens, Passwörter oder Prompts in Exporten |
| **Umsetzung** | `_METADATA_BLOCKED_KEYS = frozenset({"task_content", "prompt", "secret", "password", "token", ...})` |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/audit/vault.py`, `tests/test_audit_vault.py` TestVaultSanitization |
| **Offene Punkte** | Keine |

---

### T15 — Audit-Vault Stufe 1

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Lesender, append-only Audit-Export-Service |
| **Ziel** | Prüfbarkeit aller Systemereignisse durch Admin |
| **Umsetzung** | `GET /admin/audit/events`, `GET /admin/audit/export`, `GET /admin/audit/retention-report` |
| **Verantwortlich** | ADM, DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/audit/vault.py`, `tests/test_audit_vault.py` (21 Tests) |
| **Offene Punkte** | Stufe 2 (gesteuerter Retention-Cleanup) noch nicht implementiert |

---

### T16 — Audit-Vault Stufe 2

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Kontrollierter Retention-Cleanup-Prozess mit Dokumentation |
| **Ziel** | DSGVO Art. 5(1)(e): Speicherbegrenzung mit Nachweis |
| **Umsetzung** | Noch nicht implementiert |
| **Verantwortlich** | ADM, DSV, SO |
| **Status** | 🔲 offen — erst nach expliziter Freigabe durch Nutzer/DSV implementieren |
| **Nachweis** | Keiner |
| **Offene Punkte** | Vier-Augen-Prozess, DSGVO-Dokumentation und Nutzerfreigabe erforderlich |

---

### T17 — Prompt-Injection-Erkennung (Gate 6)

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Automatische Erkennung von Prompt-Injection-Mustern vor Verarbeitung |
| **Ziel** | Schutz vor manipulierten Prompts in Dokumenten oder Nutzereingaben |
| **Umsetzung** | `apps/backend/documents/document_handler.py`, Pattern-Matching, Score-basiert |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/documents/document_handler.py`, Audit-Event `documents.scan` |
| **Offene Punkte** | Regelmäßige Überprüfung der Erkennungsmuster empfohlen |

---

### T18 — Dokument-Scan

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Jede hochgeladene Datei wird vor Nutzung gescannt |
| **Ziel** | Verhinderung unzulässiger Dateitypen und injection-behafteter Dokumente |
| **Umsetzung** | `POST /documents/scan` mit Typ-, Größen-, Injection- und Risikoklassen-Check |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/documents/document_handler.py`, Frontend `AgentChat.jsx` Upload-Section |
| **Offene Punkte** | Keine |

---

### T19 — Kill-Switch für externe Calls

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Globaler Notausschalter für alle externen LLM-Calls |
| **Ziel** | Fail-closed: Bei Unsicherheit wird kein externer Call ausgeführt |
| **Umsetzung** | `AILIZA_EXTERNAL_LLM_ENABLED=false` (Standard), `kill_switch.py` |
| **Verantwortlich** | SO |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/kill_switch.py` |
| **Offene Punkte** | Keine |

---

### T20 — Provider-Orchestrator

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Alle externen LLM-Calls laufen durch eine Governance-Pipeline |
| **Ziel** | Kein Direktaufruf aus `main.py`, immer mit Gate 1–10 |
| **Umsetzung** | Kill-Switch → Data Governance → Policy-Gateway → Redaction → Provider-Orchestrator |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/providers/orchestrator.py`, `CLAUDE.md` Pipeline-Dokumentation |
| **Offene Punkte** | Keine |

---

### T21 — AVV/DPA-Prüfung vor Provider-Aktivierung

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Kein Provider wird aktiviert ohne geprüften Auftragsverarbeitungsvertrag |
| **Ziel** | DSGVO Art. 28: Auftragsverarbeitung nur mit AVV |
| **Umsetzung** | `provider-dpa-checklist.md` (dieses Governance Pack), Kill-Switch aktiv |
| **Verantwortlich** | DSV, SO |
| **Status** | 🔲 offen — kein Provider aktuell aktiviert, Checkliste erstellt |
| **Nachweis** | `policies/governance/provider-dpa-checklist.md` |
| **Offene Punkte** | AVV für alle geplanten Provider muss vor Aktivierung vorliegen |

---

### T22 — Backup

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Regelmäßige Sicherung der SQLite-Datenbank |
| **Ziel** | Wiederherstellbarkeit bei Datenverlust |
| **Umsetzung** | Noch nicht implementiert |
| **Verantwortlich** | SO |
| **Status** | 🔲 offen |
| **Nachweis** | Keiner |
| **Offene Punkte** | Backup-Strategie und Wiederherstellungstest vor Produktionsstart einplanen |

---

### T23 — Incident-Response-Prozess

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Dokumentierter Prozess für Sicherheitsvorfälle |
| **Ziel** | Geordnete Reaktion, 72h-Prüfung bei möglichem Datenschutzvorfall |
| **Umsetzung** | `policies/governance/incident-response-process.md` |
| **Verantwortlich** | DSV, SO |
| **Status** | ✅ umgesetzt (Dokumentation), Prozess noch nicht geübt |
| **Nachweis** | `policies/governance/incident-response-process.md` |
| **Offene Punkte** | Tabletop-Übung empfohlen vor Produktionsstart |

---

### T24 — Automatisierte Regressionstests

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Automatisierte Tests für alle sicherheitsrelevanten Funktionen |
| **Ziel** | Regressionsschutz, Nachweis der Governance-Funktionen |
| **Umsetzung** | pytest, 635 Tests, davon Audit-Vault (21), Local-Mode (21), Debug-Guard (16) |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `tests/`, `apps/backend/tests/`, 635/635 grün (Stand: 2026-06-23) |
| **Offene Punkte** | CI/CD-Integration ausstehend |

---

### T25 — Security-Review

| Feld | Inhalt |
|---|---|
| **Maßnahme** | Regelmäßiger Security-Review durch SO und DEV |
| **Ziel** | Neue Schwachstellen frühzeitig erkennen |
| **Umsetzung** | Noch nicht etabliert als regelmäßiger Prozess |
| **Verantwortlich** | SO, DEV |
| **Status** | 🔲 offen |
| **Nachweis** | Keiner |
| **Offene Punkte** | Quartalsmäßigen Review-Prozess einplanen |

---

### T26 — Rate Limiting

| Feld | Inhalt |
|---|---|
| **Maßnahme** | API-Endpunkte sind rate-limitiert |
| **Ziel** | Schutz vor Brute-Force und übermäßiger Nutzung |
| **Umsetzung** | `slowapi`-Middleware, z.B. `30/minute` auf `/agent/run` |
| **Verantwortlich** | DEV |
| **Status** | ✅ umgesetzt |
| **Nachweis** | `apps/backend/main.py` `@_limiter.limit(...)` Dekoratoren |
| **Offene Punkte** | Limits für Produktion noch nicht abgestimmt |

---

### T27 — CORS-Konfiguration

| Feld | Inhalt |
|---|---|
| **Maßnahme** | CORS auf erlaubte Origins beschränken |
| **Ziel** | Schutz vor Cross-Origin-Anfragen unbekannter Quellen |
| **Umsetzung** | Aktuell `allow_origins=["*"]` (Entwicklung). In Produktion: explizite Origin-Liste |
| **Verantwortlich** | DEV, SO |
| **Status** | ⚠️ prüfen — Wildcard nur für Entwicklung akzeptabel |
| **Nachweis** | `apps/backend/main.py` CORS-Middleware |
| **Offene Punkte** | Vor Produktionsstart: Erlaubte Origins explizit konfigurieren |

---

## Offene Punkte (Zusammenfassung)

| Nr. | Thema | Priorität | Verantwortlich |
|---|---|---|---|
| 1 | AILIZA_SECRET_KEY in Produktion setzen | Hoch | SO |
| 2 | TLS/HTTPS in Produktion | Hoch | SO |
| 3 | CORS-Wildcard → explizite Origins | Hoch | DEV |
| 4 | TOTP-Secret-Feld-Verschlüsselung | Mittel | DEV |
| 5 | TOTP-Pflicht für Admin-Accounts | Mittel | DEV |
| 6 | Pseudonymisierung user_id prüfen | Mittel | DSV |
| 7 | Backup-Strategie | Mittel | SO |
| 8 | AVV für alle Provider vor Aktivierung | Hoch | DSV |
| 9 | Audit-Vault Stufe 2 (Retention-Cleanup) | Nach Freigabe | ADM, DSV |
| 10 | CI/CD-Integration Tests | Niedrig | DEV |
| 11 | Security-Review-Prozess etablieren | Mittel | SO |
| 12 | Tabletop-Übung Incident-Response | Mittel | DSV, SO |

---

*Letzte Änderung: 2026-06-23 — Keine Rechtsberatung. Keine Behauptung vollständiger DSGVO- oder AI-Act-Konformität.*
