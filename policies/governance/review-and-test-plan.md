# AILIZA — Review- und Testplan

**Version:** 1.0  
**Stand:** 2026-06-23  
**Nächste Überprüfung:** 2026-09-23 (quartalsweise)  
**Rechtsgrundlage:** DSGVO Art. 32 Abs. 1 lit. d, EU AI Act Art. 9, Art. 17  
**Verantwortlich:** System Owner (SO), Datenschutzverantwortliche/r (DSV), Entwicklung (DEV)  
**Hinweis:** Dieser Plan beschreibt Mindestanforderungen. Zusätzliche Reviews bei Incidents oder größeren Änderungen sind jederzeit möglich und empfohlen.

---

## Zweck

Regelmäßige Reviews und Tests stellen sicher, dass:
- Sicherheitsmaßnahmen funktionieren und nicht durch Änderungen unterlaufen wurden
- Governance-Regeln tatsächlich eingehalten werden (nicht nur dokumentiert)
- Neue Schwachstellen frühzeitig erkannt werden
- Nachweise für Prüfungen und Zertifizierungen vorliegen

---

## Übersicht: Review-Frequenz

| Review-Typ | Frequenz | Verantwortlich | Nächster Termin |
|---|---|---|---|
| Smoke Tests (manuell) | Wöchentlich | DEV | Laufend |
| Regressionstests (automatisiert) | Bei jedem Commit | DEV | Laufend (CI geplant) |
| Prompt-Review | Monatlich | SO, DEV | 2026-07-23 |
| Provider-Review | Quartalsweise | DSV, SO | 2026-09-23 |
| Modulstatus-Review | Quartalsweise | SO | 2026-09-23 |
| Security-Review | Quartalsweise | SO, DEV | 2026-09-23 |
| Audit-Vault-Review | Monatlich | ADM, DSV | 2026-07-23 |
| Rollen-/Berechtigungsprüfung | Quartalsweise | ADM, SO | 2026-09-23 |
| TOM-Katalog-Review | Halbjährlich | DSV, SO | 2026-12-23 |
| AI-Act-Klassifikation-Review | Halbjährlich | DSV, SO | 2026-12-23 |
| Incident-Response-Übung | Halbjährlich | DSV, SO | 2026-12-23 |

---

## 1. Smoke Tests (wöchentlich)

**Ziel:** Kernfunktionen arbeiten nach Änderungen weiterhin korrekt.

**Checkliste:**

- [ ] Login als Testnutzer möglich
- [ ] Login-Fehler bei falschem Passwort korrekt
- [ ] `/health`-Endpunkt antwortet
- [ ] Agent-Chat antwortet (local_only-Modus)
- [ ] Dokument-Upload und Scan funktioniert
- [ ] Audit-Tab zeigt Einträge (nach Login und Agent-Run)
- [ ] Abmelden funktioniert, Session wird ungültig
- [ ] Kill-Switch aktiv (keine externen Calls ohne explizite Freigabe)

**Nachweis:** Manuelle Durchführung dokumentieren (Datum, Ergebnis, Durchführende/r).

**Freigabekriterium:** Alle Punkte bestanden. Bei Fehler → Incident-Prozess.

---

## 2. Regressionstests (automatisiert, bei jedem Commit)

**Ziel:** Keine sicherheitsrelevante Funktion bricht durch Codeänderungen.

**Aktueller Stand:** 635 Tests, alle grün (Stand: 2026-06-23)

**Testkategorien:**

| Kategorie | Tests | Nachweis |
|---|---|---|
| Audit-Vault (Append-Only, Sanitization) | 21 | `tests/test_audit_vault.py` |
| Agent Local-Mode (kein HTTP 500, Audit-Event) | 21 | `tests/test_agent_local_mode.py` |
| Frontend Debug-Guard (DiagBlock-Absicherung) | 16 | `tests/test_frontend_debug_mode.py` |
| Backend-Core (Auth, Agent, Governance) | ~577 | `apps/backend/tests/` |

**Nachweis:** `pytest --tb=short` Ausgabe mit Zeitstempel. CI-Integration geplant.

**Freigabekriterium:** 100 % grün. Kein Merge bei Testfehler.

**Offene Punkte:** CI/CD-Pipeline (z.B. GitHub Actions) noch nicht eingerichtet.

---

## 3. Prompt-Review (monatlich)

**Ziel:** System-Prompts und Antwortmuster enthalten keine unerwünschten Inhalte, keine PII, keine technischen Details für Nutzer.

**Prüfpunkte:**

- [ ] System-Prompt aktuell und genehmigt
- [ ] Keine API-Keys oder Secrets im Prompt
- [ ] Keine PII oder Nutzerdaten im System-Prompt
- [ ] Antworten im local_only-Modus nutzerfreundlich und technisch korrekt
- [ ] KI-Kennzeichnung vorhanden (Art. 50 EU AI Act)
- [ ] Fehlermeldungen ohne technische Details für Endnutzer (VITE_DEBUG_ERRORS=false)

**Nachweis:** Protokoll mit Datum, Prüfperson, Ergebnis.

**Freigabekriterium:** Keine offenen Punkte. Abweichungen → Sofortbehebung oder dokumentierte Ausnahme.

---

## 4. Provider-Review (quartalsweise)

**Ziel:** Kein Provider wird eingesetzt ohne aktuelle Freigabe und geprüften AVV.

**Prüfpunkte:**

- [ ] Kill-Switch Status: `AILIZA_EXTERNAL_LLM_ENABLED` prüfen
- [ ] `provider-dpa-checklist.md` aktuell und vollständig
- [ ] Alle aktiven Provider haben gültigen AVV
- [ ] AVV-Laufzeiten prüfen (Ablaufdaten)
- [ ] Neue Provider seit letztem Review? → Checkliste ergänzen
- [ ] Trainingsnutzung vertraglich ausgeschlossen bei allen aktiven Providern
- [ ] Subprozessoren dokumentiert

**Nachweis:** Signiertes Review-Protokoll (DSV + SO).

**Freigabekriterium:** Alle aktiven Provider freigegeben, AVV vorhanden.

---

## 5. Modulstatus-Review (quartalsweise)

**Ziel:** Kein Modul ist versehentlich aktiviert oder deaktiviert.

**Prüfpunkte:**

| Modul | Soll-Status | Prüfung |
|---|---|---|
| Core Chat (local_only) | Aktiv | ✅ Standard |
| Dokument-Scan | Aktiv | ✅ Standard |
| Audit-Vault Stufe 1 | Aktiv | ✅ Standard |
| Audit-Vault Stufe 2 | Inaktiv | 🔲 Nur nach Freigabe |
| Externe Provider (LLM) | Inaktiv | Kill-Switch prüfen |
| Websuche (Tavily) | Inaktiv | API-Key nicht gesetzt |
| Buchhaltung | Inaktiv | Nur nach Freigabe + Rechtsprüfung |
| HR/Personal | Inaktiv | Nur nach Hochrisiko-Konformitätsprüfung |

**Nachweis:** Protokoll mit Datum und Modulstatus.

**Freigabekriterium:** Alle Soll-Status stimmen. Abweichungen → Sofort melden.

---

## 6. Security-Review (quartalsweise)

**Ziel:** Neue Schwachstellen erkennen bevor sie ausgenutzt werden.

**Prüfpunkte:**

- [ ] Abhängigkeiten (Python, npm) auf bekannte CVEs prüfen (`pip-audit`, `npm audit`)
- [ ] CORS-Konfiguration: Keine Wildcard-Origins in Produktion
- [ ] Secret-Management: `AILIZA_SECRET_KEY` gesetzt und ausreichend lang
- [ ] TLS-Konfiguration in Produktion aktiv
- [ ] Rate-Limiting-Grenzen für Produktion geprüft
- [ ] TOTP-Pflicht für Admin-Accounts prüfen
- [ ] `governance_integrity.json` aktuell
- [ ] Keine Secrets in Logs oder Audit-Einträgen
- [ ] DiagBlock nur bei `VITE_DEBUG_ERRORS=true` aktiv

**Nachweis:** Security-Review-Protokoll mit Findings und Status.

**Freigabekriterium:** Alle kritischen Findings behoben oder mit Zeitplan dokumentiert.

---

## 7. Audit-Vault-Review (monatlich)

**Ziel:** Audit-Vault enthält keine unzulässigen Daten und funktioniert korrekt.

**Prüfpunkte:**

- [ ] Stichproben aus `GET /admin/audit/events` — keine sensiblen Felder sichtbar
- [ ] `agent.degraded_missing_provider` erscheint korrekt nach local_only-Run
- [ ] Keine `task_content`, `prompt`, `password`, `token` in Metadaten
- [ ] Export-Format (JSON/JSONL) korrekt und vollständig
- [ ] Retention-Report zeigt plausible Zahlen
- [ ] Kein DELETE-Endpunkt vorhanden (prüfen mit `GET /admin/audit/events` → nur GET zulässig)

**Nachweis:** Protokoll mit Stichproben-Ergebnis und Datum.

**Freigabekriterium:** Keine sensiblen Daten im Vault, alle Einträge korrekt.

---

## 8. Rollen- und Berechtigungsprüfung (quartalsweise)

**Ziel:** Nur berechtigte Personen haben Zugriff auf Admin-Funktionen.

**Prüfpunkte:**

- [ ] Alle Admin-Accounts bekannt und begründet
- [ ] Keine ehemaligen Nutzenden haben noch aktive Accounts
- [ ] Passwörter für Test-Accounts im Produktionssystem — falls vorhanden: sofort löschen
- [ ] TOTP-Status aller Admin-Accounts prüfen
- [ ] Session-Token-Ablaufzeit konfiguriert und angemessen

**Nachweis:** Nutzerliste mit Rollen und Review-Datum.

**Freigabekriterium:** Alle Accounts berechtigt, keine verwaisten Accounts.

---

## Nachweise und Dokumentation

| Nachweis | Format | Aufbewahrung |
|---|---|---|
| Testergebnisse (pytest) | Text/Log | Git-Repository, 1 Jahr |
| Smoke-Test-Protokoll | Markdown | `docs/` oder internes Wiki |
| Provider-Review-Protokoll | Markdown + Signatur | `policies/governance/` |
| Security-Review-Protokoll | Markdown | `policies/governance/` |
| Audit-Vault-Review | Markdown | `policies/governance/` |
| Incident-Protokolle | Markdown + Nachtrag | Extern, nicht im Vault |
| DSGVO-Meldungen | PDF | Extern, DSV |

---

## Freigabekriterien für v1.0 Beta Ready

AILIZA gilt als v1.0 Beta Ready wenn:

- [ ] Alle automatisierten Tests grün (aktuell: 635/635 ✅)
- [ ] TLS in Produktionsumgebung aktiv
- [ ] CORS auf explizite Origins eingeschränkt
- [ ] AILIZA_SECRET_KEY gesetzt (>= 32 Zeichen)
- [ ] Backup-Strategie dokumentiert und getestet
- [ ] Erster Smoke-Test-Zyklus abgeschlossen
- [ ] TOM-Katalog vollständig ausgefüllt (offene Punkte bekannt)
- [ ] Provider-DPA-Checkliste vollständig (kein Provider mit PII ohne AVV)
- [ ] Incident-Response-Prozess einmal geübt (Tabletop)
- [ ] Rollenprüfung erstmalig durchgeführt

**Aktueller v1.0-Status:** In Vorbereitung. Checkliste teilweise offen (TLS, Backup, Tabletop, CORS-Prod).

---

## Offene Punkte

| Nr. | Thema | Priorität | Verantwortlich |
|---|---|---|---|
| 1 | CI/CD-Integration für Regressionstests | Mittel | DEV |
| 2 | TLS in Produktion konfigurieren | Hoch | SO |
| 3 | CORS-Wildcard vor Produktionsstart einschränken | Hoch | DEV |
| 4 | Backup-Strategie dokumentieren und testen | Mittel | SO |
| 5 | Erste Tabletop-Übung Incident-Response | Mittel | DSV, SO |
| 6 | Erste Rollen-Berechtigungsprüfung durchführen | Mittel | ADM, SO |
| 7 | Erste Provider-Prüfung abschließen (wenn Provider geplant) | Nach Bedarf | DSV |
| 8 | Security-Review-Prozess formalisieren (Termin + Protokoll) | Mittel | SO |

---

*Stand: 2026-06-23 — Kein Anspruch auf vollständige DSGVO- oder EU-AI-Act-Konformität. Fehlende Prüfungen sind offen markiert.*
