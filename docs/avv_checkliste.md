# AVV-Checkliste — Groq & Anthropic
**AILIZA | Stand: 2026-06-19 | DSGVO Art. 28**

---

## Was ist ein AVV?
Ein Auftragsverarbeitungsvertrag (AVV) ist nach DSGVO Art. 28 Pflicht, wenn ein
Dienstleister personenbezogene Daten im Auftrag des Verantwortlichen verarbeitet.
Jeder externe LLM-Call bei AILIZA ist potenziell Auftragsverarbeitung — sofern der
Prompt personenbezogene Daten enthält.

---

## 1. Anthropic (claude-sonnet-4-6 / API)

| Punkt | Status | Hinweis |
|---|---|---|
| AVV / DPA verfügbar? | ✅ | Anthropic bietet ein Data Processing Addendum (DPA) an |
| Wo abschließen? | → | https://www.anthropic.com/legal/privacy / Account-Einstellungen → „Data Processing" |
| EU-Standardvertragsklauseln (SCC)? | ✅ | In Anthropic-DPA enthalten (SCCs 2021) |
| Serverstandort EU? | ⚠️ | Anthropic = US-Unternehmen. Daten werden in USA verarbeitet. SCC erforderlich |
| Zero-Data-Retention-Option? | ✅ | Anthropic bietet „Zero Retention" per API-Flag an (Prompt-Daten nicht gespeichert) |
| Subauftragnehmer transparent? | ✅ | Liste in Anthropic-Datenschutzerklärung |
| Löschfristen vereinbart? | ✅ | Per DPA / Zero Retention |
| **Aktion für AILIZA** | 🔴 | DPA auf https://console.anthropic.com abschließen, Zero-Retention aktivieren |

### AILIZA-Maßnahmen für Anthropic:
- Redaktion (PII entfernen) **vor** jedem API-Call (bereits implementiert)
- Kill-Switch auf `false` bis DPA unterschrieben
- `ANTHROPIC_API_KEY` nur in `.env`, niemals in Code/Logs

---

## 2. Groq (Groq API / LPU-Inference)

| Punkt | Status | Hinweis |
|---|---|---|
| AVV / DPA verfügbar? | ✅ | Groq bietet ein DPA an |
| Wo abschließen? | → | https://groq.com/legal → „Data Processing Agreement" oder per E-Mail an privacy@groq.com |
| EU-SCC enthalten? | ✅ | In Groq-DPA enthalten |
| Serverstandort EU? | ⚠️ | Groq betreibt LPUs in USA. SCC erforderlich |
| Zero-Data-Retention-Option? | ✅ | Groq speichert Prompts laut Policy nicht für Training (kein opt-in erforderlich) |
| Subauftragnehmer transparent? | ✅ | In Groq-Datenschutzerklärung aufgelistet |
| Löschfristen vereinbart? | ✅ | Per DPA |
| **Aktion für AILIZA** | 🔴 | DPA bei Groq anfordern und unterzeichnen |

### AILIZA-Maßnahmen für Groq:
- Redaktion vor jedem Groq-Call (bereits implementiert)
- Kill-Switch schützt vor unbeabsichtigten Calls
- `GROQ_API_KEY` nur in `.env`

---

## 3. Checkliste vor Produktivbetrieb (beide Provider)

- [ ] **DPA Anthropic** unterzeichnet und gespeichert (Kanzlei oder Geschäftsführung)
- [ ] **DPA Groq** unterzeichnet und gespeichert
- [ ] **Verarbeitungsverzeichnis** (Art. 30 DSGVO): AILIZA-Eintrag mit Zweck „KI-Assistent", Kategorien „Anfragen von Mitarbeitern/Kunden", Empfänger „Anthropic/Groq (AV)", Drittlandtransfer „USA/SCC"
- [ ] **Datenschutz-Folgenabschätzung (DSFA)** prüfen: Bei Verarbeitung besonderer Kategorien (Art. 9) oder Profiling Pflicht; für normalen KMU-Einsatz ggf. nicht erforderlich
- [ ] **Technische Maßnahmen** dokumentiert: Redaktion, Kill-Switch, Retention, Pseudonymisierung (`AILIZA_PSEUDONYMIZE_USERS=true`)
- [ ] **Datenschutzbeauftragter (DSB)** informiert (falls vorhanden) — DSB-Rolle in RBAC bereits vorhanden
- [ ] **Nutzungsbedingungen / Einwilligung** für Endnutzer: Hinweis, dass Anfragen extern verarbeitet werden können
- [ ] **Löschkonzept**: `AILIZA_DATA_RETENTION_DAYS` entspricht gesetzlichem Rahmen

---

## 4. Technische DSGVO-Umsetzung in AILIZA

| Maßnahme | Implementiert | Konfiguration |
|---|---|---|
| Kill-Switch (kein externer Call ohne Erlaubnis) | ✅ | `AILIZA_EXTERNAL_LLM_ENABLED=false` |
| Redaktion vor externem Call | ✅ | `governance/redaction.py` |
| Datenklassifikation | ✅ | `governance/data_governance.py` |
| Policy-Gateway (BLOCK bei CREDENTIALS) | ✅ | `governance/data_matrix.py` |
| Pseudonymisierung | ✅ | `AILIZA_PSEUDONYMIZE_USERS=true` |
| Retention / Löschung | ✅ | `maintenance/retention_cleanup.py` |
| Audit-Log (ohne Inhalte) | ✅ | `audit/` — kein Prompt, kein PII |
| Mandantentrennung | ✅ | `tenant_id` auf allen Tabellen |
| Passwort-Hashing (bcrypt) | ✅ | `auth/models.py` |
| JWT (kein Secret in Code) | ✅ | `AILIZA_SECRET_KEY` in `.env` |

---

## 5. Offene Punkte / Empfehlungen

1. **Drittlandtransfer-Hinweis**: In der Datenschutzerklärung des AILIZA-Mandanten
   explizit auf USA-Transfer + SCC hinweisen.
2. **Aufzeichnung der AVVs**: PDFs der unterzeichneten DPAs in einem sicheren
   Dokumentenmanagementsystem ablegen (nicht im Repo).
3. **Regelmäßige Überprüfung**: Provider-DPAs ändern sich. Jährliche Prüfung empfohlen.
4. **OpenRouter**: Falls als Provider aktiviert, eigenes DPA prüfen (Subprozessor-Kette).

---

*Dieses Dokument ist eine Arbeitshilfe, kein Rechtsrat. Im Zweifel Datenschutzanwalt hinzuziehen.*
