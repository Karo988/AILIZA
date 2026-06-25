# AILIZA Beta-Betriebsprofil

**Stand:** 2026-06-20  
**Version:** 1.0  
**Gültig für:** Beta-Phase (vor Produktiv-Freigabe)  
**Freigabe durch:** DSB / technische Leitung erforderlich

> Dieses Dokument definiert die verbindlichen Betriebsauflagen für die Beta-Phase.
> Jede Auflage ist als Checkbox formuliert – Freigabe für Produktivbetrieb erst nach
> Abhaken aller Punkte mit Datum und Unterschrift.

---

## 1. Infrastruktur-Auflagen

| # | Auflage | Status | Nachweis |
|---|---|---|---|
| I-1 | Datenbankdatei liegt auf verschlüsseltem Volume (dm-crypt, SQLCipher oder gleichwertig) | ☐ Offen | Infrastruktur-Protokoll |
| I-2 | DB-Nutzer hat minimale Rechte (kein DROP/ALTER in Produktiv) | ☐ Offen | DB-Konfiguration |
| I-3 | Backup-Verschlüsselung aktiv (Backups nicht im Klartext) | ☐ Offen | Backup-Konfiguration |
| I-4 | TLS 1.2+ für alle externen Endpunkte | ☐ Offen | TLS-Zertifikat |
| I-5 | `AILIZA_SECRET_KEY` ≥ 32 Zeichen, zufällig, nicht im Code/Repository | ☐ Offen | Secret-Management-Nachweis |
| I-6 | API-Keys (Groq, Anthropic) ausschließlich in Umgebungsvariablen, nicht im Code | ☐ Offen | Code-Review / Secret-Scan |

---

## 2. Datenschutz-Auflagen (DSGVO)

| # | Auflage | Status | Nachweis |
|---|---|---|---|
| D-1 | VVT nach Art. 30 liegt vor und ist durch DSB geprüft | ☐ Offen | `docs/vvt_art30.md` + DSB-Freigabe |
| D-2 | AVV mit Groq Cloud abgeschlossen | ☐ Offen | Vertragsdokument |
| D-3 | AVV mit Anthropic abgeschlossen | ☐ Offen | Vertragsdokument |
| D-4 | AVV mit Telegram (falls Telegram-Kanal aktiv) abgeschlossen | ☐ Offen | Vertragsdokument |
| D-5 | Datenschutzerklärung veröffentlicht (inkl. LLM-Provider, Telegram, Opt-in-Text) | ☐ Offen | URL der DSE |
| D-6 | Retention-Cleanup ist scheduled (APScheduler oder Cron) und läuft nachweislich | ☐ Offen | Scheduler-Logs |
| D-7 | Betroffenenanfragen (Art. 15-21) sind prozessual geregelt (auch wenn kein Self-Service) | ☐ Offen | Prozessdokument |

---

## 3. Sicherheits-Auflagen

| # | Auflage | Status | Nachweis |
|---|---|---|---|
| S-1 | TOTP-2FA ist für alle ADMIN/DSB-Konten aktiviert und bestätigt | ☐ Offen | Audit-Log |
| S-2 | Standard-Passwörter sind geändert; keine Default-Credentials in Produktiv | ☐ Offen | Penetrationstest / manueller Check |
| S-3 | Kill-Switch (`AILIZA_EXTERNAL_LLM_ENABLED=false`) ist getestet und funktionsfähig | ☐ Offen | Testprotokoll |
| S-4 | Rate-Limiting aktiv (Login 10/min, TOTP-Verify 5/min, Register 5/min) | ☐ Offen | Konfigurationscheck |
| S-5 | Security-Scan (Bandit o.ä.) ohne kritische Findings (CVSS ≥ 7.0) | ☐ Offen | Scan-Report |
| S-6 | Keine Secrets in Git-History (Secret-Scan bestanden) | ☐ Offen | Secret-Scan-Report |

---

## 4. Test-Auflagen

| # | Auflage | Status | Nachweis |
|---|---|---|---|
| T-1 | Alle Unit-Tests grün (`pytest tests/`) | ☐ Offen | CI-Run |
| T-2 | E2E-Governance-Tests grün (Kill-Switch, Classify, Redact, Policy, Fail-Closed) | ☐ Offen | `tests/test_e2e_governance.py` |
| T-3 | TOTP-Tests grün (39 Tests: Algorithmus, Backup-Codes, Flow, Audit-Cleanliness) | ☐ Offen | `tests/test_totp.py` |
| T-4 | Kein Test bestätigt selbstgebaute Kryptografie (`test_no_self_built_crypto_*`) | ✅ Erfüllt | `tests/test_totp.py::TestTotpAlgorithm::test_no_self_built_crypto_functions_in_totp_module` |

---

## 5. Betriebliche Grenzen (Beta-Einschränkungen)

Diese Einschränkungen gelten **bis zur Produktiv-Freigabe** und müssen aktiv kommuniziert werden:

| Einschränkung | Begründung | Production-Gate |
|---|---|---|
| TOTP-Secrets im Klartext in DB | `cryptography`-Paket nicht produktiv einsetzbar ohne cf-fi-Backend; Beta-Auflage: Volume-Verschlüsselung | AES-256-GCM via `cryptography` oder KMS/Vault |
| Nur PUBLIC/INTERNAL-Daten an LLM-Provider | AVV mit Groq und Anthropic noch nicht abgeschlossen | AVV abschließen → dann CONFIDENTIAL möglich (nach Policy-Prüfung) |
| OpenRouter deaktiviert | Subverarbeiter-Kette ungeklärt; kein AVV verfügbar | AVV + Subverarbeiter-Review |
| Kein Self-Service für Betroffenenrechte Art. 15, 18, 20 | Noch nicht implementiert | Implementierung vor Breit-Roll-out |
| Refresh-Token-Revokation fehlt | JWT-Blacklist noch nicht implementiert | Implementierung vor Produktiv-Einsatz mit langen Sessions |

---

## 6. Freigabe-Checkliste (zu unterschreiben vor Produktiv-Betrieb)

```
Alle Punkte in Abschnitt 1–4 sind erfüllt: ☐

Betriebliche Grenzen aus Abschnitt 5 sind dokumentiert und kommuniziert: ☐

VVT ist durch DSB geprüft und freigegeben: ☐

Datenschutzerklärung ist veröffentlicht: ☐

Datum: _______________

Technische Leitung: _______________

DSB: _______________
```

---

## 7. Versionsverlauf

| Version | Datum | Änderung |
|---|---|---|
| 1.0 | 2026-06-20 | Erstversion – Beta-Betriebsprofil |
