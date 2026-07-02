# AILIZA Alignment mit GDD-Musterrichtlinie für KI

**Referenz:** GDD (Gesellschaft für Datenschutz e.V.) Musterrichtlinie für KI  
https://www.gdd.de/wp-content/uploads/2025/06/GDD-Musterrichtlinie-KI.pdf

**Datum:** 2026-07-01  
**Ziel:** Zeigt, wie AILIZA Phase 1.2 und Phase 2 GDD-Anforderungen erfüllen

---

## 🎯 GDD Governance-Anforderungen vs. AILIZA

### 1. Risikomanagement für KI-Systeme

**GDD Anforderung:** Klassifizierung von KI-Systemen nach Risiko (niedrig / mittel / hoch / kritisch)

| Risiko-Stufe | GDD Definition | AILIZA Implementierung |
|-------------|----------------|----------------------|
| 🟢 **NIEDRIG** | Keine PII, keine kritischen Entscheidungen | GREEN: Normale Fragen |
| 🟡 **MITTEL** | PII mit Redaktion möglich | YELLOW: Normal PII redacted |
| 🟠 **HOCH** | Art. 9-Kategorien, Genehmigung nötig | ORANGE: Approval required |
| 🔴 **KRITISCH** | Hochrisiko-KI, automatisierte Entscheidungen, Diskriminierung | RED: Blockade, kein LLM-Zugriff |

**GDD Status:** ✅ KONFORM – Phase 1.2 implementiert 4-stufiges Risiko-System

---

### 2. Datenschutz-Folgenabschätzung (DPIA)

**GDD Anforderung (Art. 35 DSGVO):** DPIA für hochrisiko KI-Systeme

**Phase 1.2 Status:**
- ❌ Noch nicht durchgeführt
- ⚠️ Erforderlich vor Production

**Phase 2 Aktion:**
```
DPIA Durchführung:
├─ Feststellung: AILIZA ist "HIGH RISK" KI
│  (automatisierte Entscheidungen, Art. 22, Art. 9-Kategorien)
├─ Impact Assessment
│  ├─ Datenvolumen: [TBD]
│  ├─ Datenkategorien: PII, Health, Biometric, Financial
│  ├─ Betroffene: [Employees / Customers / Public]
│  └─ Risiken: Diskriminierung, Verstöße gegen Art. 6/9/22
├─ Mitigationen
│  ├─ Blockade von Hochrisiko-Kontexten ✅
│  ├─ Approval-Workflow mit Audit ✅
│  ├─ Rechtsgrundlagen-Prüfung [Phase 2]
│  └─ Transparenzmitteilung [Phase 2]
└─ Ergebnis: DPIA-Report (veröffentlichbar für Audits)
```

**GDD Status:** ⚠️ TEILWEISE – Phase 2 erforderlich

---

### 3. Governance-Struktur

**GDD Anforderung:** Klar definierte Rollen und Verantwortlichkeiten

| Rolle | GDD Anforderung | AILIZA Phase 1.2 | AILIZA Phase 2 |
|-------|-----------------|------------------|----------------|
| **KI-Verantwortlicher** | Gesamtverantwortung für KI-System | ⚠️ Geplant | ✅ Definiert |
| **Datenschutzbeauftragter (DPO)** | DPIA, Beschwerde, Audit | ❌ Nicht definiert | ✅ Erforderlich |
| **Sicherheitsverantwortlicher** | Encryption, Access Control | ⚠️ Teilweise | ✅ Full |
| **Legal Review** | Rechtsgrundlagen, DPA | ❌ Nicht durchgeführt | ✅ Phase 2 |
| **Admin** | Genehmigung von ORANGE-Fällen | ✅ Implementiert | ✅ Extended |
| **Audit** | Compliance-Überprüfung | ⚠️ Logs vorhanden | ✅ Regelmäßig |

**GDD Status:** ⚠️ TEILWEISE – Governance-Struktur in Phase 2 zu definieren

---

### 4. Transparenz und Betroffenenrechte

**GDD Anforderung:** Nutzer müssen wissen, dass KI verarbeitet + welche Rechte sie haben

**Phase 1.2 Status:**
- ❌ Keine Transparenzmitteilung
- ❌ Keine Nutzer-UI für Rechte

**Phase 2 Implementierung:**

```
Transparenzmitteilung (Art. 13-14 DSGVO):
┌──────────────────────────────────────────────────┐
│ Ihre Daten wurden verarbeitet                    │
├──────────────────────────────────────────────────┤
│ Erkannte Kategorien: [Gesundheit]                │
│ Aktion genommen: [REDACTED zur Verarbeitung]     │
│ Rechtsgrundlage: [Benötigt Einwilligung]         │
│ Speicherfrist: [90 Tage]                         │
├──────────────────────────────────────────────────┤
│ Ihre Rechte:                                     │
│ ☐ Zugriff (Art. 15)       [Anfrage stellen]     │
│ ☐ Korrektur (Art. 16)     [Anfrage stellen]     │
│ ☐ Löschung (Art. 17)      [Anfrage stellen]     │
│ ☐ Beschwerde (Art. 77)    [Bei BfDI]            │
└──────────────────────────────────────────────────┘
```

**GDD Status:** ❌ NICHT KONFORM – Phase 2 erforderlich

---

### 5. Audit und Compliance-Kontrollen

**GDD Anforderung:** Regelmäßige interne und externe Audits

**Phase 1.2 Status:**
- ✅ Audit-Logs strukturiert (normalized reason_codes)
- ✅ 52 Tests (funktionale Validierung)
- ⚠️ Kein externer Compliance-Audit durchgeführt

**Phase 2 Aktion:**
```
Audit-Plan:
├─ Interne Audits (monatlich)
│  ├─ Audit-Log Review (Was wurde blockiert?)
│  ├─ False-Positive Check (Wurden Nutzer zu Unrecht blockiert?)
│  └─ Performance Monitoring (Overhead akzeptabel?)
├─ Externe Compliance-Audit (jährlich)
│  ├─ Zertifizierter Auditor
│  ├─ DPIA-Validierung
│  ├─ DPA-Prüfung
│  └─ Bericht für Regulators
└─ Incident Response
   ├─ Dokumentation (Art. 33-34 DSGVO)
   └─ Notification (72h bei Behörden)
```

**GDD Status:** ⚠️ TEILWEISE – Audit-Struktur geplant, nicht durchgeführt

---

## 📋 GDD Compliance-Matrix: AILIZA Phase 1.2

| GDD-Anforderung | Phase 1.2 | Phase 2 | Status |
|-----------------|-----------|---------|--------|
| **Risiko-Klassifizierung** | ✅ 4-Tier | ✅ Extended | ✅ KONFORM |
| **DPIA durchführen** | ❌ | ✅ Planned | ⚠️ PENDING |
| **Governance-Struktur** | ⚠️ Partial | ✅ Full | ⚠️ PENDING |
| **Transparenz (Art. 13-14)** | ❌ | ✅ Planned | ❌ NICHT KONFORM |
| **Betroffenenrechte** | ❌ | ✅ Planned | ❌ NICHT KONFORM |
| **Audit-Struktur** | ⚠️ Logs | ✅ Planned | ⚠️ PENDING |
| **DPA mit Providern** | ❌ | ✅ Planned | ❌ NICHT KONFORM |
| **Legal Review** | ❌ | ✅ Planned | ❌ NICHT KONFORM |
| **Incident Response** | ⚠️ Partial | ✅ Full | ⚠️ PENDING |
| **Training & Awareness** | ❌ | ✅ Planned | ❌ NICHT KONFORM |

**Gesamtstatus:** ⚠️ **TEILWEISE KONFORM (Phase 1.2)**

---

## 🔴 Kritische GDD-Anforderungen nicht erfüllt (Phase 1.2)

### 1. Transparenzmitteilung fehlt

**GDD Anforderung:** Nutzer muss WISSEN, dass KI verarbeitet

```
PHASE 1.2 (aktuell):
User Input: "Ich habe Migräne"
↓ PolicyEngine blockiert (ORANGE)
↓ Nutzer sieht: "Die Anfrage enthält geschützte Daten"
❌ Nutzer erfährt NICHT:
   - Dass Gesundheitsdaten erkannt wurden
   - Dass KI-System verarbeitet hat
   - Welche Rechte er hat
```

**GDD Lösung (Phase 2):**
```
PHASE 2 (geplant):
User Input: "Ich habe Migräne"
↓ PolicyEngine blockiert (ORANGE)
↓ Transparenzmitteilung:
  "Ihre Anfrage enthält Gesundheitsdaten (Migräne).
   Diese wurden erkannt und nicht verarbeitet.
   Sie haben das Recht auf Zugriff, Korrektur, Löschung.
   Kontakt: dpo@ailiza.de oder BfDI"
✅ Nutzer weiß Bescheid
```

---

### 2. Rechtsgrundlage nicht geprüft

**GDD Anforderung:** Verarbeitung muss auf Rechtsgrundlage beruhen (Art. 6)

```
PHASE 1.2 (aktuell):
- Erkennt: ✅ Gesundheitsdaten
- Prüft aber: ❌ "Haben Sie Einwilligung?"
- Resultat: ❌ Könnte ohne Basis verarbeitet werden (Verstoß!)
```

**GDD Lösung (Phase 2):**
```
- Prüft: "Haben Sie Einwilligung, Vertrag oder Rechtsobligation?"
- Falls JA: Verarbeite mit Grund
- Falls NEIN: Blockade (Art. 6-Verstoß verhindert)
```

---

### 3. Keine Datenschutzerklärung

**GDD Anforderung:** Klare Datenschutzerklärung veröffentlichen

```
Phase 1.2: ❌ Nicht vorhanden
Phase 2: ✅ Erforderlich
  Inhalt:
  ├─ Wer verarbeitet (verantwortliche Stelle)
  ├─ Welche Daten (Art und Kategorien)
  ├─ Warum (Zweck und Rechtsgrundlage)
  ├─ Wie lange (Speicherdauer)
  ├─ An wen (Empfänger, z.B. LLM-Provider)
  ├─ Welche Rechte (Zugriff, Löschung, Beschwerde)
  └─ Kontakt DPO (Beschwerdeverfahren)
```

---

### 4. DPA mit LLM-Providern fehlt

**GDD Anforderung (Art. 28 DSGVO):** Data Processing Agreement mit externen Verarbeitern

```
Phase 1.2: ❌ Nicht geprüft
Phase 2: ✅ Erforderlich
  Für jeden LLM-Provider:
  ├─ DPA signiert?
  ├─ Compliance mit DSGVO?
  ├─ Standard Contractual Clauses (SCC) für USA?
  ├─ Zugangsrechte für Audits?
  └─ Datenlöschungs-Garantie?
```

---

## ✅ GDD-konform in Phase 1.2

### 1. Risiko-Erkennung

**GDD Anforderung:** KI-Systeme nach Risiko klassifizieren

```
✅ Phase 1.2 leistet:
- GREEN: No risk
- YELLOW: Medium (PII mit Redaktion)
- ORANGE: High (Art. 9, Genehmigung)
- RED: Critical (Secrets, Hochrisiko-Kontexte)

Besonders gut: Automatisierte Entscheidungen (Art. 22)
werden BLOCKIERT (RED), nicht redacted
```

---

### 2. Datenminimierung

**GDD Anforderung:** Nur notwendige Daten verarbeiten

```
✅ Phase 1.2 leistet:
- Originaldaten NICHT an LLM
- Nur [PLACEHOLDER] an LLM
- Approval-Logs speichern KEINE PII
- assert_no_pii() validiert vor Speicherung
```

---

### 3. Audit-Trail

**GDD Anforderung:** Nachvollziehbar dokumentieren, was passiert

```
✅ Phase 1.2 leistet:
- Jede Entscheidung geloggt
- reason_code (normalisiert, keine freetext)
- detected_categories (welche Daten erkannt)
- high_risk_contexts (warum blockiert)
- Keine PII in Logs (data protection by design)
```

---

## 🚀 Phase 2: GDD-Erfüllung im Detail

### Sprintplan für GDD-Konformität

**Sprint 1 (Woche 1-2): Transparenz**
```
Task: Implementiere Transparenzmitteilung
├─ Data Categories Liste
├─ User Rights Erklärung
├─ DPO Kontaktinformation
└─ Test: Nutzer erhält alle Infos
```

**Sprint 2 (Woche 2-3): Rechtsgrundlagen**
```
Task: Implementiere Art. 6 + Art. 9 Basis-Prüfung
├─ Legal Basis Matrix
├─ Approval + Basis Validation
├─ Rejection bei fehlender Basis
└─ Test: Keine Verarbeitung ohne Basis
```

**Sprint 3 (Woche 3-4): Provider Governance**
```
Task: Implementiere DPA-Validierung
├─ LLM Provider DPA-Status
├─ SCC für USA-Transfer
├─ Audit-Rechte Dokumentation
└─ Test: DPA-Block bei fehlendem Agreement
```

**Sprint 4 (Woche 4-5): Betroffenenrechte**
```
Task: Implementiere Art. 15/17/20
├─ Data Subject Access Request (DSAR)
├─ Deletion Request Processing
├─ Portability Export
└─ Test: Nutzer kann Rechte ausüben
```

**Sprint 5 (Woche 5-6): Dokumentation**
```
Task: Erstelle GDD-Konformitäts-Dossier
├─ DPIA-Report
├─ Datenschutzerklärung
├─ DPA-Verträge
├─ Governance-Manual
└─ External Legal Review
```

---

## 📊 GDD Checklist für Production

Vor Production MUSS erfüllt sein:

- [ ] **Risiko-Klassifizierung:** AILIZA = "HIGH RISK" (documented in DPIA)
- [ ] **DPIA:** Durchgeführt und genehmigt
- [ ] **Governance:** Rollen definiert (DPO, KI-Verantwortlicher, etc.)
- [ ] **Transparenz:** Datenschutzerklärung veröffentlicht
- [ ] **Rechtsgrundlagen:** Art. 6 + Art. 9 Prüfung aktiv
- [ ] **DPA:** Mit allen LLM-Providern signiert
- [ ] **Betroffenenrechte:** Art. 15/17/20 implementiert
- [ ] **Audit:** Audit-Plan und erste Audits durchgeführt
- [ ] **Incident Response:** Prozess dokumentiert
- [ ] **Training:** Team geschult auf GDD-Anforderungen
- [ ] **External Review:** Rechtanwalt hat reviewed und approved

---

## 📞 GDD-Beschwerdeverfahren

**Falls AILIZA nicht GDD-konform läuft:**

1. **Intern:** Kontaktieren Sie den DPO
   - E-Mail: dpo@ailiza.de
   - Antwort: Innerhalb 30 Tage

2. **Regulatorisch:** Beschwerde bei BfDI (Bundesbeauftragter)
   - https://www.bfdi.bund.de
   - Beschwerdeverfahren kostenlos
   - Antwort: Innerhalb 90 Tage

3. **Gerichtlich:** Klage bei Verwaltungsgericht
   - Falls regulatorisches Verfahren keinen Erfolg

---

## 📄 GDD Referenzen in AILIZA

Alle Dokumente zur GDD-Richtlinie:

1. **AILIZA_RISK_HANDLING_RULE.md**
   - Implementiert GDD 4-Tier Risk Classification

2. **DSGVO_COMPLIANCE_ASSESSMENT.md**
   - Detaillierte GDD-Anforderungen Mapping

3. **COMPLIANCE_SUMMARY.md**
   - Stakeholder-Übersicht zur GDD-Konformität

4. **Diese Datei (GDD_RICHTLINIE_ALIGNMENT.md)**
   - Konkrete Alignment-Matrix

---

**Dokument Version:** 1.0  
**Gültig ab:** 2026-07-01  
**Basiert auf:** GDD Musterrichtlinie für KI (2025-06)  
**Nächste Review:** 2026-10-01 oder bei GDD-Updates

