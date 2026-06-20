# Verarbeitungsverzeichnis nach DSGVO Art. 30
## AILIZA – Autonomer KI-Assistent für KMU

**Stand:** 2026-06-20  
**Version:** 0.3 (Entwurf – noch nicht fachlich geprüft)  
**Verantwortlicher:** [Unternehmensname, Anschrift – einzutragen]  
**DSB (falls benannt):** [Name, Kontakt – einzutragen]  
**Erstellt durch:** Technische Implementierung AILIZA  
**Nächste Überprüfung:** 2026-09-20

> **Hinweis:** Dieses Verzeichnis ist ein technischer Entwurf auf Basis der implementierten
> Systemkomponenten. Es ersetzt keine rechtliche Prüfung durch den Datenschutzbeauftragten
> oder Rechtsanwalt. Vor Produktiv-Betrieb ist eine fachliche Prüfung und Freigabe
> durch den DSB erforderlich.

---

## Verarbeitungstätigkeit 1: Nutzerauthentifizierung und Zugriffskontrolle

| Feld | Inhalt |
|---|---|
| **Bezeichnung** | Login, JWT-Sessionverwaltung, RBAC, TOTP-Zwei-Faktor-Authentifizierung |
| **Zweck** | Zugriffskontrolle auf das AILIZA-System; Sicherstellung dass nur autorisierte Nutzer auf Funktionen zugreifen (Art. 5 Abs. 1 lit. f DSGVO, Art. 32 DSGVO) |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. b (Vertragserfüllung) oder Art. 6 Abs. 1 lit. f (berechtigtes Interesse: IT-Sicherheit) |
| **Betroffene Personen** | Mitarbeiter und Administratoren des Unternehmens (B2B-Nutzer) |
| **Verarbeitete Daten** | user_id (pseudonym), gehashtes Passwort (bcrypt), Rolle (user/manager/admin/dsb), tenant_id, Login-Zeitstempel, Fehlversuche, Sperrzeit, TOTP-Secret (Base32, Klartext in DB – Beta-Betriebsauflage), TOTP-Backup-Code-Hashes (HMAC-SHA256+Pepper) |
| **Empfänger** | Keine Weitergabe an Dritte; nur interner DB-Zugriff |
| **Drittlandtransfer** | Keiner |
| **Speicherdauer** | Nutzerkonto: bis zur Löschung durch Admin oder Betroffenen; Login-Fehlversuche: nach erfolgreicher Anmeldung gelöscht; TOTP-Secret: bis zur Deaktivierung durch Nutzer oder Admin-Reset |
| **TOM** | bcrypt-Passwort-Hashing, Account-Lockout nach 5 Fehlversuchen (15 min), HttpOnly+SameSite=Strict Cookie, Bearer-Token-Fallback für API-Clients, CSRF-Origin-Check, TOTP-2FA für ADMIN/DSB-Rollen, Rate-Limiting (login 10/min, totp/verify 5/min) |
| **Offene Punkte** | TOTP-Secret at rest: Production-Gate (AES-256-GCM oder KMS/Vault) noch offen; Refresh-Token-Revokation noch nicht implementiert |

---

## Verarbeitungstätigkeit 2: Telegram-Messenger-Gateway

| Feld | Inhalt |
|---|---|
| **Bezeichnung** | Empfang und Verarbeitung von Telegram-Nachrichten, Opt-in-Verwaltung, Antwort-Versand |
| **Zweck** | Bereitstellung eines konversationellen KI-Assistenten über Telegram für KMU-Mitarbeiter; Verarbeitung von Nutzeranfragen und Rückgabe von KI-generierten Antworten |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. a (Einwilligung – expliziter Opt-in via /start + /accept) |
| **Betroffene Personen** | Telegram-Nutzer die aktiv dem Dienst beigetreten sind (Opt-in) |
| **Verarbeitete Daten** | Pseudonymisierte Chat-ID (HMAC-SHA256 + AILIZA_SECRET_KEY als Pepper; Re-Identifikation mit Pepper möglich → Pseudonymisierung, nicht Anonymisierung), Telegram-Username (optional), Nachrichteninhalt (flüchtig, nur für LLM-Verarbeitung, kein persistentes Speichern), Opt-in-Status, Opt-in-Zeitstempel, Systemnachricht mit EU AI Act Art. 50 Hinweis |
| **Empfänger** | Telegram (Webhook-Eingang und Antwort-Versand); LLM-Provider (siehe VT 3) |
| **Drittlandtransfer** | Telegram: Drittland (US/Dubai), Transferbasis unklar – **AVV mit Telegram noch nicht abgeschlossen (offener Punkt)** |
| **Speicherdauer** | messenger_bindings: bis Widerruf (/widerrufen) oder Löschung (/delete_me); nach Widerruf: opt_in_confirmed=0, Daten bleiben (Art. 7 Abs. 3); nach /delete_me: vollständige Löschung (Art. 17) |
| **TOM** | HMAC-SHA256+Pepper-Pseudonymisierung der Chat-ID, keine Klartextspeicherung, HMAC-SHA256 Webhook-Signaturprüfung, Rate-Limiting, Datenklassen-Check vor LLM-Weiterleitung (CREDENTIALS/SPECIAL_CATEGORY blockiert), Redaction vor LLM-Call, EU AI Act Art. 50 Transparenz-Hinweis in jeder Antwort |
| **Offene Punkte** | AVV mit Telegram (DSGVO Art. 28) ausstehend; Retention-Policy für inaktive Bindings (Empfehlung: 12 Monate) noch nicht umgesetzt; Datenschutzerklärung mit Telegram-Abschnitt noch nicht veröffentlicht |

---

## Verarbeitungstätigkeit 3: LLM-Provider-Verarbeitung (externe KI-Calls)

| Feld | Inhalt |
|---|---|
| **Bezeichnung** | Weiterleitung von Nutzernachrichten an externe LLM-Anbieter (Groq, Anthropic) für KI-Antwortgenerierung |
| **Zweck** | Generierung von KI-Antworten auf Nutzerfragen im Rahmen des KMU-Assistenten |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. b (Vertragserfüllung) oder Art. 6 Abs. 1 lit. a (Einwilligung, bei Telegram-Kanal) |
| **Betroffene Personen** | Nutzer die Anfragen stellen (direkt oder über Telegram-Gateway) |
| **Verarbeitete Daten** | Nachrichteninhalt nach Redaction (PII soweit möglich entfernt), Datenklasse (PUBLIC/INTERNAL – CONFIDENTIAL und höher werden blockiert), kein Klartext-Prompt in Logs |
| **Empfänger** | Groq Cloud (US), Anthropic (US) |
| **Drittlandtransfer** | US-Transfer; Transferbasis: Standardvertragsklauseln (SCC, Art. 46 Abs. 2 lit. c DSGVO) – **AVV/DPA mit Groq und Anthropic noch nicht unterzeichnet (offener Punkt)** |
| **Speicherdauer** | Kein persistentes Speichern von Prompts oder Antworten durch AILIZA; Provider-seitig: laut jeweiliger Datenschutzrichtlinie (Groq: keine Trainingsnutzung lt. API-Policy; Anthropic: keine Trainingsnutzung lt. Commercial Terms) |
| **TOM** | Kill-Switch (AILIZA_EXTERNAL_LLM_ENABLED), Data-Governance-Pipeline vor jedem Call (Klassifikation → Policy-Check → Redaction → Provider-Orchestrator), ProviderProfile-Governance (check_provider_policy vor jedem Call), Fail-Closed (unbekannter Provider → Block), OpenRouter standardmäßig deaktiviert (admin_disabled=True) |
| **Offene Punkte** | AVV/DPA mit Groq ausstehend; AVV/DPA mit Anthropic ausstehend; bis AVV: nur PUBLIC/INTERNAL-Daten erlaubt |

---

## Verarbeitungstätigkeit 4: Audit- und Sicherheits-Logging

| Feld | Inhalt |
|---|---|
| **Bezeichnung** | Protokollierung sicherheitsrelevanter Ereignisse, Performance-Metriken und Kostendaten ohne Inhalte |
| **Zweck** | IT-Sicherheit, Nachvollziehbarkeit von Admin-Aktionen, Performance-Monitoring, Kostenüberwachung (Art. 5 Abs. 2 DSGVO – Rechenschaftspflicht, Art. 32 DSGVO) |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. c (rechtliche Verpflichtung: Nachweispflicht) und Art. 6 Abs. 1 lit. f (berechtigtes Interesse: IT-Sicherheit) |
| **Betroffene Personen** | Nutzer und Administratoren des Systems |
| **Verarbeitete Daten** | Audit-Log: action (Ereignistyp), Metadaten (user_id, role, tenant_id – nie Passwort, TOTP-Secret, Code, Backup-Code oder Prompt-Inhalt), Zeitstempel; Security-Log: incident_type, severity, tenant_id; Performance-Log: latency_ms, provider, error_type – keine personenbezogenen Daten; Cost-Log: tokens_in, tokens_out, provider, model, use_case, cost_estimate – keine personenbezogenen Daten |
| **Empfänger** | Keine Weitergabe; nur interner DB-Zugriff durch Admins und DSB |
| **Drittlandtransfer** | Keiner |
| **Speicherdauer** | Konfigurierbar via Retention-Cleanup (APScheduler); Empfehlung: Audit-Logs 90 Tage, Security-Logs 180 Tage, Performance/Cost-Logs 30 Tage; **Retention-Policy noch nicht produktiv konfiguriert (offener Punkt)** |
| **TOM** | Getrennte Log-Tabellen (Audit, Security, Performance, Cost), kein Prompt-Inhalt, kein Secret, keine Backup-Codes in Logs (durch Tests gesichert), tenant_id-Isolation, nur ADMIN/DSB-Lesezugriff |
| **Offene Punkte** | Retention-Zeiträume noch nicht per Konfiguration festgelegt und dokumentiert |

---

## Verarbeitungstätigkeit 5: Memory und Skill-Learning (Opt-in)

| Feld | Inhalt |
|---|---|
| **Bezeichnung** | Speicherung von Reflexions-Facts aus erfolgreichen Agentenläufen zur Qualitätsverbesserung; Skill-Proposal-System |
| **Zweck** | Verbesserung der KI-Antwortqualität durch Lernen aus vergangenen Interaktionen; Aufbau eines Skill-Registers |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. a (Einwilligung – opt_in_confirmed=1 zwingend) |
| **Betroffene Personen** | Nutzer die Memory-Opt-in erteilt haben |
| **Verarbeitete Daten** | reflection_facts: Inhalt (keine PII nach Redaction), data_classes, quality_score, pii_cleared-Flag, created_at, expires_at, tenant_id, user_id (optional); skills: Name, Beschreibung, steps_summary, status, proposed_by |
| **Empfänger** | Keine Weitergabe; LLM-Provider erhält Kontext-Facts als Teil des Prompts (→ VT 3) |
| **Drittlandtransfer** | Indirekt via LLM-Provider (→ VT 3) |
| **Speicherdauer** | reflection_facts: expires_at-Feld (konfigurierbar, Empfehlung: 90 Tage); bei Widerruf: Löschung aller Facts des Tenants |
| **TOM** | opt_in_confirmed-Pflicht, pii_cleared-Flag, Redaction vor Speicherung, Datenklassen-Klassifikation, tenant_id-Isolation, Quality-Score-System (negative Bewertungen reduzieren Score) |
| **Offene Punkte** | Widerrufsweg für Memory-Opt-in noch nicht über UI erreichbar (nur API); Opt-in-Text noch nicht als Datenschutzhinweis formuliert |

---

## Verarbeitungstätigkeit 6: Nutzerverwaltung und Rollenpflege (Admin)

| Feld | Inhalt |
|---|---|
| **Bezeichnung** | Anlegen, Verwalten und Löschen von Nutzerkonten; Rollenzuweisung; TOTP-Administration |
| **Zweck** | Zugriffsverwaltung; Sicherstellung der Rollenintegrität (RBAC); Wiederherstellung bei verlorenem TOTP-Gerät |
| **Rechtsgrundlage** | Art. 6 Abs. 1 lit. b (Vertragserfüllung) oder Art. 6 Abs. 1 lit. f (berechtigtes Interesse: Zugriffskontrolle) |
| **Betroffene Personen** | Mitarbeiter und Administratoren |
| **Verarbeitete Daten** | user_id, tenant_id, Rolle, created_at, active-Flag; bei TOTP-Admin-Reset: target_user_id, ausführender Admin (user_id), Begründung (Pflichtfeld), Zeitstempel |
| **Empfänger** | Keine Weitergabe |
| **Drittlandtransfer** | Keiner |
| **Speicherdauer** | Nutzerkonto: bis Admin-Löschung oder Betroffenenantrag (Art. 17 DSGVO); Admin-Aktions-Log (Audit): → VT 4 |
| **TOM** | Nur ADMIN-Rolle darf Nutzer anlegen/löschen/TOTP-Reset; TOTP-Reset nur mit Pflichtbegründung; alle Admin-Aktionen im Audit-Log; Rate-Limiting auf Register-Endpoint (5/min) |
| **Offene Punkte** | Vier-Augen-Prinzip für Admin-Reset noch nicht implementiert (Empfehlung für höheres Schutzlevel); Passwort-Reset-Flow noch nicht implementiert |

---

## Auftragsverarbeiter (Art. 28 DSGVO)

| Auftragsverarbeiter | Zweck | Region | Transferbasis | AVV | Status |
|---|---|---|---|---|---|
| Groq Cloud | LLM-Inferenz | US | SCC (Art. 46) | Noch nicht abgeschlossen | ⚠️ Ausstehend – nur PUBLIC/INTERNAL bis AVV |
| Anthropic | LLM-Inferenz | US | SCC (Art. 46) | Noch nicht abgeschlossen | ⚠️ Ausstehend – nur PUBLIC/INTERNAL bis AVV |
| Telegram | Messenger-Infrastruktur | US/AE | Unklar | Noch nicht abgeschlossen | ⚠️ Ausstehend – Kanal nur mit AVV produktiv |
| OpenRouter | LLM-Aggregator (Fallback) | US | SCC (Art. 46) | Nicht verfügbar (Stand 2026-06) | 🔴 Deaktiviert (admin_disabled) – Subverarbeiter-Kette ungeklärt |

---

## Betroffenenrechte (Art. 15–21 DSGVO)

| Recht | Umsetzung | Status |
|---|---|---|
| Auskunft (Art. 15) | Über Admin-Endpoints abrufbar (Audit-Log, Binding) | ⚠️ Kein Self-Service für Endnutzer |
| Berichtigung (Art. 16) | Über Admin möglich | ⚠️ Kein Self-Service |
| Löschung (Art. 17) | Telegram: /delete_me; Nutzer: Admin-Löschung | ✅ Telegram implementiert |
| Einschränkung (Art. 18) | Noch nicht implementiert | 🔴 Offen |
| Datenübertragbarkeit (Art. 20) | Noch nicht implementiert | 🔴 Offen |
| Widerspruch (Art. 21) | Telegram: /widerrufen (Opt-in-Widerruf) | ⚠️ Nur Telegram; allg. Widerspruch fehlt |
| Widerruf Einwilligung (Art. 7 Abs. 3) | Telegram: /widerrufen; Memory: API | ⚠️ Kein UI-Widerruf für Memory |

---

## Offene Punkte (Gesamtübersicht)

| Nr. | Punkt | Priorität | Zuständig |
|---|---|---|---|
| 1 | AVV mit Telegram abschließen | Hoch | Rechtlich |
| 2 | AVV/DPA mit Groq abschließen | Hoch | Rechtlich |
| 3 | AVV/DPA mit Anthropic abschließen | Hoch | Rechtlich |
| 4 | TOTP-Secret at rest: AES-GCM oder KMS/Vault | Hoch | Technisch (Production-Gate) |
| 5 | Retention-Zeiträume konfigurieren und dokumentieren | Mittel | Technisch + DSB |
| 6 | Datenschutzerklärung mit Telegram-Abschnitt veröffentlichen | Hoch | Rechtlich |
| 7 | Betroffenenrechte Art. 18, 20 implementieren | Mittel | Technisch |
| 8 | Memory-Opt-in-Widerruf über UI | Mittel | Technisch |
| 9 | Passwort-Reset-Flow | Mittel | Technisch |
| 10 | Vier-Augen-Prinzip für Admin-TOTP-Reset | Niedrig | Technisch |
| 11 | VVT fachliche Prüfung durch DSB | Hoch | DSB |
| 12 | OpenRouter AVV + Subverarbeiter-Liste | Niedrig (deaktiviert) | Rechtlich (bei Bedarf) |

---

*Dieses Verzeichnis wird bei jeder wesentlichen Änderung der Datenverarbeitung aktualisiert.*  
*Nächste Pflicht-Review: 2026-09-20 oder bei Einführung neuer Verarbeitungstätigkeiten.*
