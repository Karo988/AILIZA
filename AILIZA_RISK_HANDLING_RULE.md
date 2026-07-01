# AILIZA Permanente Risk Handling Regel
## Konform mit DSGVO, IHK-Richtlinie und EU AI Act

**Version:** 1.2 (Aktualisiert basierend auf Compliance-Audit)  
**Gültig ab:** 2026-07-01  
**Status:** Orientierungsleitlinie (keine juristische Beratung)  

---

## ⚠️ FUNDAMENTALES PRINZIP

> **"Durchgehen lassen" bedeutet NIE: ungeprüft weiterverarbeiten**

"Durchgehen lassen" heißt NUR:
- ✅ Einen sicheren, minimierten, redigierten oder geschwärzten Output bereitstellen
- ✅ Wenn das ohne Offenlegung personenbezogener oder sensibler Inhalte möglich ist
- ✅ Wenn Zweck, Datenminimierung und Rechtsgrundlage plausibel sind
- ✅ Mit vollständiger Auditierbarkeit und Nachweisbarkeit

**NICHT:**
- ❌ Originaldaten an LLM weitergeben
- ❌ Ohne Prüfung der Rechtsgrundlage (Art. 6 DSGVO)
- ❌ Ohne Art. 9-Validierung für Spezialkat

erorien
- ❌ Ohne DPA-Prüfung für externe Provider
- ❌ Ohne Transparenzmitteilung an Nutzer
- ❌ Ohne Audit-Trail für Betroffenenrechte

---

## 🎨 4-Stufen-Klassifikation

### 🟢 GRÜN – Sicher (Allow)
**Keine sensiblen Daten erkannt**

**Charakteristiken:**
- Keine Geheimnisse
- Keine Art. 9-Kategorien
- Keine Hochrisiko-Kontexte
- Normale Fragen (z.B. "Top 5 Programmiersprachen?")

**Aktion:**
- ✅ Normale LLM-Verarbeitung
- ✅ Logs: action="policy.allowed", reason="SAFE"
- ✅ Keine Redaktion nötig

**Beispiel:**
```
Input: "What are the top 5 programming languages?"
→ Risk Level: GREEN
→ Action: ALLOW
→ LLM erhält: Original-Text
→ Log: {"action": "policy.allowed", "reason_code": "SAFE"}
```

---

### 🟡 GELB – Mit Redaktion (Redact)

**Charakteristiken:**
- Normale PII erkannt (Name, E-Mail, Telefon, Adresse)
- ODER: Sensitive Data erkannt (Gehalt, IBAN, Kreditkarte)
- Keine Art. 9-Kategorien
- Keine Hochrisiko-Kontexte
- Redaktion ist sicher möglich

**Aktion:**
- ✅ **Originaldaten NICHT an LLM**
- ✅ Redacted Text an LLM ("Name: [PERSON]", "E-Mail: [EMAIL]")
- ✅ In Logs: nur reason_code, keine Original-PII
- ⚠️ **Prüfung erforderlich:** Ist Zweck/Rechtsgrundlage plausibel?

**Beispiel:**
```
Input: "Ich bin Anna Mueller, anna@example.de, Tel 0176 123456"
→ Detected: [name, email, phone]
→ Risk Level: YELLOW
→ Action: REDACT
→ LLM erhält: "Ich bin [PERSON], [EMAIL], Tel [PHONE]"
→ Log: {"action": "policy.redacted", "detected_categories": ["name", "email", "phone"]}
→ Audit: Redacted-Text validiert, keine Original-PII in Logs
```

**KRITISCH:** Auch GELB braucht:
- ✅ Rechtsgrundlage (Art. 6 DSGVO)
- ✅ Klarer Zweck
- ✅ Datenminimierung (nur Platzhalter an LLM)
- ✅ Transparenzmitteilung an Nutzer (optional)

---

### 🟠 ORANGE – Genehmigung erforderlich (Approval Required)

**Charakteristiken:**
- Art. 9-Kategorien erkannt (Gesundheit, Religion, politische Meinung, etc.)
- ABER: NICHT in Hochrisiko-Kontext (z.B. nicht HR+Health)
- Redaktion technisch möglich, aber Rechtsgrundlage unklar

**Aktion:**
- ⛔ **BLOCKADE bis Genehmigung**
- ✅ Approval-Request an Admin generiert
- ✅ Redacted Preview (maximal 500 Zeichen, KEINE Originaldaten)
- ✅ Admin prüft Rechtsgrundlage und genehmigt/lehnt ab
- ✅ Nur NACH Genehmigung: Nutzer muss neu-submitten (Validation re-runs)

**Beispiel:**
```
Input: "Mir wurde eine Migräne diagnostiziert und ich brauche Hilfe"
→ Detected: [health]
→ Risk Level: ORANGE
→ Action: APPROVAL_REQUIRED

Approval Request:
{
  "request_id": "req_12345",
  "pii_categories": ["health"],
  "redacted_preview": "Mir wurde eine medizinische Diagnose gestellt...",
  "status": "pending",
  "needs_legal_basis": True  // Critical!
}

Admin Review:
- Rechtgrundlage vorhanden? (Einwilligung / medizinischer Zweck / etc.)
- Ist Redaction ausreichend?
- → GENEHMIGEN oder ABLEHNEN

Nach Genehmigung:
- Nutzer erhält: "Genehmigt. Bitte erneut einreichen."
- Policy re-checks: (validation läuft erneut)
- Falls alle Prüfungen grün: Verarbeitung
```

**ORANGE Regeln:**
- ✅ Redacted Preview speichern (für Audit)
- ✅ **Niemals Original-Text in Approval-Logs**
- ✅ Nutzer muss Einwilligung bestätigen (Art. 4 DSGVO)
- ✅ Rechtsgrundlage dokumentieren

---

### 🔴 ROT – BLOCKADE (Block)

**Charakteristiken:**
- Geheimnisse erkannt (sk-*, gsk_*, JWT, Bearer, Passwörter, etc.)
- ODER: Hochrisiko-Kontexte erkannt:
  - HR + Gesundheit (Bewerbung + Migräne)
  - HR + Biometrie (Bewerbung + Gesichtserknung)
  - HR + Art. 9-Kategorie (Bewerbung + Religion)
  - Automatisierte Entscheidung mit Personenwirkung (Scoring → Ablehnung)
  - Kreditscoring (Bonitätsbewertung)
  - Strafrechtliche Daten
  - Gewerkschaftsbezug

**Aktion:**
- 🚫 **SOFORTIGE BLOCKADE – KEINE VERARBEITUNG**
- ✅ Audit-Entry: action="policy.blocked", reason_code="[HIGH_RISK_TYPE]"
- ✅ Nutzer erhält: Generische Nachricht (keine Preisgabe, was erkannt wurde)
- ✅ Admin erhält: Vollständige Audit-Details mit Kategorien

**Beispiel ROT – Geheimnisse:**
```
Input: "My API key is sk-proj-abc123def456ghi789"
→ Detected: [api_key_openai]
→ Risk Level: RED
→ Action: BLOCK
→ LLM erhält: (Nichts)
→ Nutzer sieht: "Die Anfrage enthält geschützte Daten und kann nicht verarbeitet werden."
→ Admin sieht: {"action": "policy.blocked", "reason_code": "SECRET_DETECTED", "secret_type": "api_key_openai"}
```

**Beispiel ROT – Hochrisiko (HR+Health):**
```
Input: "Bewerbung Paula Ronder. Gesundheitsdaten: Migräne, früherer Herzinfarkt. Automatische Bewertung"
→ Detected: [hr_context, health, automated_decision]
→ Risk Level: RED (multiple)
→ Action: BLOCK (no LLM, no Approval)
→ Nutzer sieht: "Die Anfrage enthält geschützte Daten und kann nicht verarbeitet werden."
→ Admin sieht: {
    "action": "policy.blocked",
    "reason_code": "HIGH_RISK_HR_SPECIAL_CATEGORY",
    "high_risk_contexts": ["HIGH_RISK_HR_HEALTH", "HIGH_RISK_AUTOMATED_DECISION"],
    "detected_categories": ["health"]
  }
```

**ROT Regeln (NICHT verhandelbar):**
- ✅ **Niemals** an LLM weitergeben
- ✅ **Niemals** in Approval-Logs speichern
- ✅ **Niemals** im Audit-Trail Original-Text
- ✅ **Niemals** normalen Nutzer-Error-Message geben
- ✅ **Immer** Admin-Audit dokumentieren mit reason_code

---

### ⚫ SCHWARZ – Verbotene/Sehr riskante automatisierte Entscheidung

**Charakteristiken** (zukünftig in Phase 2+):
- Automatisierte Entscheidung OHNE menschliche Überprüfung
- ODER: Vollständig automatisches Scoring mit Personenwirkung
- ODER: Biometrische Identifizierung ohne Einwilligung
- ODER: Diskriminierungsrisiko erkannt

**Aktion:**
- 🚫 **BLOCKADE ohne Exceptions**
- ✅ Mandatory Audit mit "SCHWARZ" Flag
- ✅ Mandatory Human Review vorgeschrieben
- ✅ Nutzerpflicht: Einwilligung einholen UND Transparenzmitteilung

**SCHWARZ Regeln:**
- ✅ Art. 22 DSGVO compliance check
- ✅ Nutzer muss explizit einwilligen
- ✅ Nutzer muss Recht auf menschliche Überprüfung verstehen
- ✅ Mindestens 30 Tage Beschwerde-Frist

---

## 📋 Entscheidungs-Matrix

```
┌─────────────────────────────────────────────────────────────────┐
│           AILIZA Policy Decision Matrix (Phase 1.2)             │
├──────────────────────┬──────────────┬──────────────┬────────────┤
│ Detected Risk        │ Risk Level   │ Action       │ LLM Input  │
├──────────────────────┼──────────────┼──────────────┼────────────┤
│ Keine               │ GREEN        │ ALLOW        │ Original   │
│ Name, Email         │ YELLOW       │ REDACT       │ [PERSON]   │
│ Gehalt, IBAN        │ YELLOW       │ REDACT       │ [PAYMENT]  │
├──────────────────────┼──────────────┼──────────────┼────────────┤
│ Gesundheit (allein) │ ORANGE       │ APPROVAL     │ Blocked    │
│ Religion (allein)   │ ORANGE       │ APPROVAL     │ Blocked    │
├──────────────────────┼──────────────┼──────────────┼────────────┤
│ API Key (sk-*)      │ RED          │ BLOCK        │ Blocked    │
│ HR + Gesundheit     │ RED          │ BLOCK        │ Blocked    │
│ Automatisiert+Score │ RED          │ BLOCK        │ Blocked    │
│ Kreditscoring       │ RED          │ BLOCK        │ Blocked    │
│ Strafrechtlich      │ RED          │ BLOCK        │ Blocked    │
└──────────────────────┴──────────────┴──────────────┴────────────┘
```

---

## ✅ DSGVO-Anforderungen pro Stufe

### GELB (REDACT) – DSGVO-Prüfung

Vor "Durchgehen lassen" MUSS geprüft sein:

| Anforderung | Prüfung | Status |
|------------|---------|---------|
| Art. 6 Rechtsgrundlage | "Ist Zweck legitim?" | ⚠️ Manuell (Phase 2) |
| Art. 5(c) Datenminimierung | "Nur Platzhalter?" | ✅ Automatisch |
| Art. 5(e) Speicherbegrenzung | "Retention konfiguriert?" | ✅ Automatisch |
| Art. 5(f) Sicherheit | "Audit-Trail vorhanden?" | ✅ Automatisch |
| Zweckbindung | "Zweck dokumentiert?" | ⚠️ Manuell (Phase 2) |

**Fazit:** GELB ist OK, wenn:
1. ✅ Nur Platzhalter an LLM
2. ✅ Vollständiger Audit-Trail
3. ⚠️ Rechtsgrundlage dokumentiert (Admin-Prüfung)

---

### ORANGE (APPROVAL) – DSGVO-Prüfung

Vor Genehmigung MUSS geprüft sein:

| Anforderung | Prüfung | Status |
|------------|---------|---------|
| Art. 6 Rechtsgrundlage | "Explicit legal basis?" | ✅ Admin-Prüfung |
| Art. 9 Basis (falls Art. 9) | "Explicit consent or exception?" | ✅ Admin-Prüfung |
| Art. 5(c) Minimierung | "Redacted preview ok?" | ✅ Automatisch |
| Art. 5(a) Rechtmäßigkeit | "Lawful purpose?" | ✅ Admin-Prüfung |

**Approval-Prüfliste:**
```
□ Rechtsgrundlage: _________________
□ Zweck: __________________________
□ Datenminimierung ok? (nur [REDACTION])
□ Retention Policy akzeptabel?
□ User consent obtained? (Art. 9 falls nötig)
□ Admin signature: __________ (Name, Datum)
```

---

### ROT (BLOCK) – Keine DSGVO-Prüfung möglich

Grund der Blockade ist DSGVO-Konformität selbst.

| Grund | DSGVO-Artikel | Begründung |
|-------|---------------|-----------|
| Geheimnisse | Art. 32 (Sicherheit) | Würde Sicherheit kompromittieren |
| HR+Health | Art. 9(1) + Art. 22 | Spezielle Kategorie + Diskriminierungsrisiko |
| Automation+Score | Art. 22(1) | Automatisierte Entscheidung mit Personenwirkung |
| Kreditscoring | Art. 22(1) + HR-Risiko | Automatisierte Entscheidung mit Personenwirkung |
| Strafrechtlich | Art. 9(1) | Spezielle Kategorie, höchstes Risiko |

**Keine Genehmigung möglich** – nur Blockade

---

## 🔏 Logging & Audit Requirements

### Was MUSS geloggt werden (DSGVO-konform)

✅ **ERLAUBT im Audit-Log:**
```python
{
    "timestamp": "2026-07-01T10:30:00Z",
    "request_id": "req_12345",
    "user_id": "user@company.de",  # hashed OK
    "action": "policy.blocked",
    "risk_level": "red",
    "reason_code": "HIGH_RISK_HR_HEALTH",  # Normalized, no free text
    "detected_categories": ["health"],  # Categories only
    "high_risk_contexts": ["HIGH_RISK_HR_HEALTH"],
    "data_class": "personal",
    "tenant_id": "tenant_abc",
    # NOTHING ELSE – no original text, no content preview
}
```

❌ **VERBOTEN im Log:**
- Original input text
- "Bewerbung Paula Ronder. Gesundheit: Migräne..."
- Free-text explanations
- Stacktraces with data
- PII in error messages

---

## 🚨 Phase 2 – Kritische Ergänzungen

Diese Regel deckt Phase 1.2 ab. Für echte DSGVO-Konformität braucht es:

### 1. Rechtsgrundlagen-System
```python
LEGAL_BASIS_MATRIX = {
    "public_data": ["user_consent", "legitimate_interest"],
    "normal_pii": ["contract", "legal_obligation", "user_consent", "legitimate_interest"],
    "sensitive_pii": ["contract", "legal_obligation"],
    "health": ["explicit_consent", "medical_purpose"],  # Art. 9(2)(h)
    "biometric": ["explicit_consent"],  # Art. 9(2)(a)
    "automated_decision": ["user_opt_in", "human_review"],  # Art. 22(3)
}

# BEFORE processing: Check
legal_basis = get_user_legal_basis(user_id, data_category)
if legal_basis not in LEGAL_BASIS_MATRIX[data_category]:
    return PolicyDecision(decision="block", reason_code="NO_LEGAL_BASIS")
```

### 2. Provider Governance
```python
LLM_PROVIDER_DPA_CHECKLIST = {
    "openai": {
        "dpa_signed": True,
        "date_signed": "2024-01-15",
        "data_location": "EU_with_SCC",  # Standard Contractual Clauses
        "compliance_level": "GDPR_compliant",
    },
    "anthropic": {
        "dpa_signed": True,
        "date_signed": "2024-02-01",
        "data_location": "EU_primary",
        "compliance_level": "GDPR_compliant",
    },
}

# BEFORE LLM call: Verify
if not LLM_PROVIDER_DPA_CHECKLIST[provider]["dpa_signed"]:
    return PolicyDecision(decision="block", reason_code="NO_DPA")
```

### 3. Nutzer-Transparenzmitteilung
```python
user_notification = {
    "title": "Ihre Anfrage wurde verarbeitet",
    "message": "Ihre Anfrage enthielt personenbezogene Daten, die wie folgt behandelt wurden:",
    "processing_details": {
        "data_categories": ["name", "email"],  # was recognized
        "action_taken": "redacted",  # what was done
        "reason": "Datenminimierung gemäß Art. 5(1)(c) DSGVO",
        "retention_period": "90 Tage",
        "your_rights": {
            "access": "Art. 15 DSGVO",
            "rectification": "Art. 16 DSGVO",
            "erasure": "Art. 17 DSGVO",
            "restriction": "Art. 18 DSGVO",
            "portability": "Art. 20 DSGVO",
            "object": "Art. 21 DSGVO",
        },
        "complaint": "datenschutz@ailiza.de oder https://www.bfdi.bund.de",
    }
}
```

### 4. Betroffenenrechte-System
- Art. 15: Access Request
- Art. 16: Correction Request
- Art. 17: Deletion Request
- Art. 20: Portability Request
- Art. 21: Objection

---

## 📞 Verantwortlichkeit

**Wer ist Verantwortlicher?** (Art. 4(7) DSGVO)
- Die Organisation, die AILIZA betreibt
- Nicht: Nutzer
- Nicht: LLM-Provider (Auftragsverarbeiter)

**Datenschutzbeauftragter erforderlich?**
- Öffentliche Behörde: JA
- Unternehmen mit 250+ Mitarbeitern: JA
- Unternehmen <250 Mitarbeitern: Empfohlen

**Kontakt:**
- E-Mail: datenschutz@ailiza.de
- Telefon: +49 30 XXXXXXXX
- Beschwerde: https://www.bfdi.bund.de

---

## ⚠️ Ausnahme-Szenarien

### Scenario 1: Notfall (z.B. Sicherheitsbreach)

**Regel:** Sofortige Blockade + Incident Response

```python
if security_incident_detected():
    # SOFORT blockieren
    return PolicyDecision(decision="block", reason_code="INCIDENT_RESPONSE")
    
    # Benachrichtigen: 
    # Art. 33 DSGVO: Notifizierung an Aufsichtsbehörde (72h)
    # Art. 34 DSGVO: Notifizierung an betroffene Personen
```

### Scenario 2: Legal Hold (Litigation)

**Regel:** Nicht löschen, solange Hold aktiv

```python
if legal_hold_active(log_id):
    # Überspring Deletion
    retention_engine.skip_deletion(log_id)
    
    # Aber: Keep sanitization (no original PII in hold)
    hold_record = {
        "incident_id": "INC-123",
        "policy_version": "1.2",
        "severity": "high",
        # NO original data
    }
```

### Scenario 3: Third Country Transfer (Drittland)

**Regel:** Data-class dependent

```
PUBLIC data + USA transfer → YELLOW (mit Hinweis)
INTERNAL data + USA transfer → ORANGE (Approval erforderlich)
CONFIDENTIAL/PERSONAL + USA transfer → RED (Blockade)

Exception: Falls Standard Contractual Clauses (SCC) oder 
          Adequacy Decision (UK, Japan) vorhanden → GREEN
```

---

## 🔍 Compliance Checklist

Vor Production Deployment:

- [ ] Alle GELB-Fälle: Nur [REDACTION] an LLM, nie Originaldaten
- [ ] Alle ORANGE-Fälle: Admin muss Rechtsgrundlage dokumentieren
- [ ] Alle ROT-Fälle: Keine LLM-Verarbeitung, keine Exceptions
- [ ] Alle Logs: Nur reason_codes und categories, keine PII
- [ ] DPA: Mit allen LLM-Providern signiert
- [ ] Datenschutzerklärung: Published und aktuell
- [ ] Betroffenenrechte: Prozess dokumentiert
- [ ] Legal Hold: Funktioniert und getestet
- [ ] Retention: Konfiguriert und läuft
- [ ] Audit Trails: Regelmäßig überprüft (weekly)

---

## 📚 Referenzen

- **DSGVO:** https://eur-lex.europa.eu/eli/reg/2016/679/oj
- **EU AI Act:** https://eur-lex.europa.eu/eli/reg/2024/1689/oj
- **EDPB Art. 22 Guidelines:** https://edpb.ec.europa.eu/sites/default/files/files/file1/edpb_guidelines_201_automated_decision_making_en.pdf
- **IHK-Richtlinie:** https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
- **Schrems II Decision:** https://curia.europa.eu/jcms/upload/docs/application/pdf/2020-07/cp200091en.pdf

---

**Version 1.2 bestätigt durch:** Compliance-Audit 2026-07-01  
**Nächste Review:** 2026-10-01 oder nach regulatorischen Änderungen

