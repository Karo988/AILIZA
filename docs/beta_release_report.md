# AILIZA — Beta-Freigabebericht

**Stand:** 2026-06-22 (aktualisiert: Gate 6 implementiert)
**Branch:** `claude/admiring-curie-9my9rf`
**Testsuite:** 569/569 grün

---

## Gate-Übersicht

| Gate | Beschreibung | Status | Anmerkung |
|------|-------------|--------|-----------|
| Gate 1 | Klassifikator — Biometrie (Art. 9), HR, tabellarische Personendaten | ✅ Sprint 1 | Pattern-basiert, kein LLM |
| Gate 2 | Person-Decision-Block (DSGVO Art. 22, EU AI Act) | ✅ Sprint 1 | `requires_human_decision`, PERSON_DECISION + SAFETY_CRITICAL |
| Gate 3 | Kill-Switch / 5 Betriebsmodi (fail-closed) | ✅ Sprint 1 | normal/restricted/read_only/offline/kill_switch_active |
| Gate 4 | Rollenbasiertes Approval (security_lead/privacy/legal/owner) | ✅ Sprint 1 | `APPROVAL_ROLES`, `can_approve()` |
| Gate 5 | Retention (approval_requests 90d, agent_runs 30d) + Cleanup-Job | ✅ Sprint 1 | `retention_cleanup.py` |
| Gate 5b | Audit-Sauberkeit in Fehlerpfaden | ✅ Sprint 1 | `_safe_param_summary()`, kein Inhalt in Logs |
| Gate 6 | Prompt-Injection-Erkennung in Dokumenten/PDFs | ✅ Sprint 3 | `_scan_for_injection()`, 14 Pattern, `SECURITY_SENSITIVE`, Audit-Light |
| Gate 7 | TOTP-Secret at rest (AES-256-GCM) | 🔴 Produktions-Gate | Aktuell kein KMS/Vault; Beta: kein TOTP-Geheimnis an externe Provider |
| Gate 8 | Local Device Protection (Sandbox, Symlink, Approval-Reuse) | ✅ Sprint 1 | `sandbox.py`, `SandboxApproval` |
| Gate 9 | Capability Risk Manifest (No-Fallback-No-Go, AVV-Gate) | ✅ Sprint 2 | `capability_manifest.py` |
| Gate 10 | Config Integrity + Runtime-Enforcement (`lifespan()`) | ✅ Sprint 2 | `config_integrity.py`, SHA-256 + fail-closed |

---

## Freigabeformulierung

AILIZA ist für die **interne technische Beta mit synthetischen Daten** freigegeben.

Freigegeben sind nur lokale, workspace-gebundene Capabilities:
`analyze_document`, `classify_data`, `generate_report_workspace` und `compliance_check`.

Nicht freigegeben sind: echte personenbezogene Daten, externe Provider mit echten Daten,
HR-Entscheidungen, Biometrie, Massennachrichten, Shell-Kommandos und Systemeingriffe.

Gate 10 ist aktiv im Backend-Start eingebunden. Bei beschädigter Governance-Konfiguration
startet AILIZA nicht normal und fällt fail-closed in den `kill_switch_active`-Modus.

---

## Capability-Freigabestand

| Capability | Status | Bedingung |
|-----------|--------|-----------|
| `analyze_document` | ✅ Beta freigegeben | Nur Workspace, synthetische Daten |
| `classify_data` | ✅ Beta freigegeben | Intern, offline-fähig |
| `generate_report_workspace` | ✅ Beta freigegeben | Schreiben nur in `AILIZA_WORKSPACE_PATH` |
| `compliance_check` | ✅ Beta freigegeben | DSGVO/EU-AI-Act-Prüfung lokal |
| `summarize_document` | 🟡 Gesperrt bis AVV | AVV-Abschluss + Admin/Owner Approval |
| `send_message_single` | 🟡 Gesperrt bis AVV | AVV + Admin/Owner Approval + Vorschau |
| `send_push_all_visitors` | 🟡 SAFETY_CRITICAL | security_lead/operations_lead/owner + SOP-UC03 + AVV |
| `hr_shift_assignment` | 🔴 Nicht freigegeben | DPIA erforderlich, nur Vorschläge erlaubt |
| `biometric_vip_recognition` | 🔴 Permanent gesperrt | No-Fallback-No-Go, DPIA fehlt, Art. 9 |
| `access_control_camera` | 🔴 Permanent gesperrt | No-Fallback-No-Go, DPIA fehlt |
| `execute_shell_command` | 🔴 Permanent gesperrt | No-Fallback-No-Go, Gate 8 `ALWAYS_BLOCKED` |
| `install_software` | 🔴 Permanent gesperrt | No-Fallback-No-Go, Gate 8 `ALWAYS_BLOCKED` |

---

## Smoke-Test (synthetische Daten, 2026-06-22)

| Aktion | Ergebnis | Gate |
|--------|---------|------|
| Workspace-Verzeichnis eingerichtet (`AILIZA_WORKSPACE_PATH`) | ✅ konfiguriert | Gate 8 |
| Dokument in Workspace lesen (`analyze_document`) | ✅ erlaubt | Gate 8 + Gate 9 |
| Bericht in Workspace schreiben (`generate_report_workspace`) | ✅ erlaubt | Gate 8 + Gate 9 |
| CSV-Header mit Personendaten klassifizieren | ✅ `PERSONAL_DATA` + `needs_review=True` | Gate 1 |
| "Gesichtserkennung" → Biometrie-Erkennung | ✅ `SPECIAL_CATEGORY` + `requires_human_decision=True` | Gate 1 |
| "alle Besucher benachrichtigen" → SAFETY_CRITICAL | ✅ blockiert, 300s-Timeout | Gate 2 |
| Datei außerhalb Workspace löschen | ✅ blockiert, `requires_owner_approval=True` | Gate 8 |
| Shell-Befehl `rm -rf /tmp` | ✅ permanent blockiert | Gate 8 |
| Symlink `workspace/link → /etc` ausbrechen | ✅ blockiert durch `Path.resolve()` | Gate 8 |
| `governance_integrity.json` manipulieren → Start | ✅ `kill_switch_active` gesetzt | Gate 10 |
| Manifest fehlt → Start | ✅ `MISSING_MANIFEST`, kein normaler Start | Gate 10 |
| `AILIZA_OPERATION_MODE=restricted` → kein Write/Send | ✅ geblockt | Gate 3 |
| `install_software` Capability prüfen | ✅ No-Fallback-No-Go, permanent blockiert | Gate 9 |
| `biometric_vip_recognition` Capability prüfen | ✅ No-Fallback-No-Go, permanent blockiert | Gate 9 |

---

## Bekannte Lücken (Beta-Auflagen)

### Gate 6 — Prompt-Injection in Dokumenten ✅ implementiert
`_scan_for_injection()` in `document_handler.py` erkennt 14 Pattern (EN + DE),
setzt `SECURITY_SENSITIVE + needs_review=True`, blockiert externe Verarbeitung.
Audit-Light: nur Metadaten (injection_detected, pattern_count) — kein Treffertext.
Testsuite: 33 Tests (33/33 grün).

### Gate 7 — TOTP at rest (Produktions-Gate)
TOTP-Secrets sind nicht mit AES-256-GCM verschlüsselt.
Beta-Kompensation: TOTP-Secrets werden nicht an externe Provider weitergegeben.
Produktionsanforderung: KMS/Vault oder `cryptography`-Bibliothek mit AES-GCM.

### AVV-Abschluss (Pilot-Blocker)
Keine echten personenbezogenen Daten an externe LLMs bis AVV bestätigt:
- Groq
- Anthropic
- Telegram
- Notion/CRM (falls geplant)

### Branch / Release-Tag
Feature-Branch `claude/admiring-curie-9my9rf`, Tag `v0.1.0-beta` gesetzt (2026-06-22).
Für Pilot: in geschützten Release-Branch mergen.

### Manifest-Signierung
`governance_integrity.json` ist SHA-256-basiert — ausreichend für interne Beta.
Produktionsanforderung: GPG-Signatur oder HSM-basierte Signierung.

---

## Offene Produktionspunkte (priorisiert)

| Punkt | Pilot-Blocker | Produktions-Gate |
|-------|:---:|:---:|
| Gate 6: Prompt-Injection in Dokumenten | ✅ erledigt | ✅ |
| AVV-Abschluss Groq/Anthropic | ✅ | ✅ |
| AVV-Abschluss Telegram/Notion | — | ✅ |
| Gate 7: TOTP AES-256-GCM | — | ✅ |
| GPG-Signatur für Integrity-Manifest | — | ✅ |
| DPIA für HR-Use-Cases | ✅ | ✅ |
| DPIA für Biometrie (Art. 9) | ✅ | ✅ |
| `enforce_integrity()` in CI/CD Pre-Deploy | — | ✅ |
| Release-Branch + `v0.1.0-beta` Tag | ✅ erledigt | ✅ |
| Smoke-Test mit echtem Backend-Start (uvicorn) | ✅ | ✅ |

---

## Testsuite-Übersicht

| Testdatei | Tests | Beschreibung |
|-----------|-------|-------------|
| `test_sprint1_governance.py` | 40 | Gate 1–5b |
| `test_gate6_prompt_injection.py` | 33 | Pattern-Erkennung, Audit-Light, Scan |
| `test_gate8_device_protection.py` | 68 | Sandbox, Symlink, Approval-Reuse |
| `test_gate9_capability_manifest.py` | 42 | Manifest, No-Fallback-No-Go, AVV |
| `test_gate10_config_integrity.py` | 40 | Integrity-Check, Manifest |
| `test_gate10_runtime_enforcement.py` | 38 | Lifespan, Kill-Switch nach Failure, Smoke |
| Bestands-Tests | 308 | E2E, Auth, Approval, Redaktion, VVT, … |
| **Gesamt** | **569** | **569/569 grün** |
