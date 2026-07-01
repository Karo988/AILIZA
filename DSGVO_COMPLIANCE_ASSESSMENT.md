# DSGVO-Konformitätsaudit: AILIZA Phase 1.2

**Datum:** 2026-07-01  
**Basis:** DSGVO (Datenschutz-Grundverordnung), EU AI Act, RecitalEs zur Transparenz  
**Status:** Teilweise konform unter Bedingungen – Nicht produktionsreif ohne weitere Massnahmen

---

## 🔍 DSGVO-Anforderungen vs. Implementierung

### 1. Art. 4 DSGVO – Definition "Verarbeitung"

**Anforderung:** Personenbezogene Daten (PbD) = Informationen, die sich auf eine identifizierte oder identifizierbare natürliche Person beziehen.

| Kategorie | PII-Status | Phase 1.2 Handling | DSGVO-Konform? |
|-----------|-----------|-------------------|-----------------|
| Name, E-Mail, Telefon | Normal | REDACT (YELLOW) | ✅ |
| Kreditkarte, IBAN, Gehalt | Sensitive | REDACT (YELLOW) | ✅ |
| Geheimschlüssel (sk-*, JWT) | Secrets | BLOCK (RED) | ✅ |
| Art. 9 Daten (Gesundheit, Religion) | Special | BLOCK or APPROVAL (ORANGE) | ⚠️ |
| Hochrisiko-Kontexte (HR+Health) | High-Risk | BLOCK (RED) | ✅ |

**Befund:** ✅ Secrets und normale PII-Daten werden korrekt behandelt.

---

### 2. Art. 9 DSGVO – Verbot der Verarbeitung besonderer Kategorien

**Anforderung:** 
> "Die Verarbeitung personenbezogener Daten, aus denen die rassische und ethnische Herkunft, politische Meinungen, religiöse oder weltanschauliche Überzeugungen oder die Gewerkschaftszugehörigkeit hervorgehen, sowie die Verarbeitung von genetischen Daten, Gesundheitsdaten oder Daten zum Sexualleben oder der Geschlechtsidentität einer Person ist untersagt."

**Ausnahmen:** 
- Art. 9(2)(a) – Ausdrückliche Einwilligung
- Art. 9(2)(h) – Medizinische Zwecke
- Art. 9(2)(i) – Beschäftigungszwecke (unter Bedingungen)
- Andere begrenzte Ausnahmen

**Phase 1.2 Implementierung:**

| Szenario | Phase 1.2 Handling | Rechtsgrundlage Vorhanden? | DSGVO-Konform? |
|----------|-------------------|---------------------------|-----------------|
| Nutzer gibt Gesundheitsdaten | ORANGE (Approval Required) | ⚠️ Nein geprüft | ⚠️ Bedingt |
| HR+Gesundheit (Bewerbung) | RED (Block) | N/A | ✅ |
| Religion in Profil | ORANGE (Approval Required) | ⚠️ Nein geprüft | ⚠️ Bedingt |
| Biometrische Daten | RED/ORANGE | ⚠️ Nein geprüft | ⚠️ Bedingt |

**Befund:** ⚠️ **KRITISCH:** Phase 1.2 erkennt Art. 9-Daten korrekt, aber:
- ✅ HIGH_RISK_HR_SPECIAL_CATEGORY wird BLOCKIERT (gut)
- ⚠️ Einzelne Art. 9-Daten (z.B. nur "Gesundheit") gehen zu ORANGE ohne Rechtsgrundlage-Check
- ❌ **Keine Mechanismus zur Validierung der Rechtsgrundlage** (Art. 9(2))
- ❌ **Keine automatische Einwilligungsprüfung**

**Empfehlung:** 
```python
# Phase 2: Add legal basis validation
if decision == "approval_required" and "health" in detected_special_categories:
    legal_basis = check_legal_basis(user_id, "health")
    if legal_basis not in ["explicit_consent", "medical_purpose"]:
        return PolicyDecision(decision="block", reason_code="NO_LEGAL_BASIS_ART9")
```

---

### 3. Art. 22 DSGVO – Automatisierte Einzelentscheidungen

**Anforderung:** 
> "Die betroffene Person hat das Recht, nicht einer ausschließlich auf einer Automatisierten Verarbeitung […] beruhenden Entscheidung unterworfen zu werden, die ihr gegenüber rechtliche Wirkung entfaltet oder sie in ähnlicher Weise erheblich beeinträchtigt."

**Phase 1.2 Implementierung:**

```
HIGH_RISK_AUTOMATED_DECISION: Block (RED)
Trigger: "automatisierte entscheidung" + impact ("ablehnen", "kündigen", etc.)
```

**Analyse:**

| Anforderung | Status | Befund |
|------------|--------|---------|
| Automatisierte Entscheidung erkannt? | ✅ | Ja, HIGH_RISK_AUTOMATED_DECISION |
| Wird blockiert? | ✅ | Ja, RED (keine LLM-Verarbeitung) |
| Nutzer erhält Hinweis? | ⚠️ | Nur generische Nachricht |
| Nutzererklärung möglich? | ❌ | Nicht implementiert |
| Mensch kann eingreifen? | ❌ | Nur System-Admin, nicht Nutzer |

**Befund:** ⚠️ **TEILWEISE KONFORM:**
- ✅ Automatisierte Entscheidungen werden erkannt und blockiert
- ⚠️ Art. 22(3) DSGVO verlangt, dass Nutzer eine Erklärung erhalten UND eingreifen kann
- ❌ **Keine Transparenzmitteilung an Nutzer** (Recital 71)
- ❌ **Keine Nutzer-Opt-Out-Möglichkeit**

**Empfehlung für Phase 2:**
```python
# Before blocking: Notify user about Art. 22 right
notification = {
    "type": "automated_decision_blocked",
    "message": "Ihre Anfrage enthält eine automatisierte Entscheidung mit Personenwirkung. "
               "Gemäß Art. 22 DSGVO haben Sie das Recht auf menschliche Überprüfung.",
    "user_rights": {
        "request_human_review": True,
        "appeal_decision": True,
        "opt_out_automated": True
    }
}
```

---

### 4. Art. 5 DSGVO – Verarbeitungsgrundsätze

#### 4.1 Rechtmäßigkeit (Art. 5(1)(a))

**Anforderung:** Verarbeitung muss auf einer rechtlichen Grundlage beruhen (Art. 6 oder 9).

| Grundlage | Phase 1.2 Prüfung | Befund |
|-----------|-------------------|--------|
| Einwilligung (Art. 6(1)(a)) | ❌ Nein | Nicht geprüft |
| Vertrag (Art. 6(1)(b)) | ❌ Nein | Nicht geprüft |
| Rechtliche Verpflichtung (Art. 6(1)(c)) | ❌ Nein | Nicht geprüft |
| Berechtigte Interessen (Art. 6(1)(f)) | ❌ Nein | Nicht geprüft |

**Befund:** ❌ **NICHT KONFORM** – Phase 1.2 prüft KEINE Rechtsgrundlage für Datenverarbeitung.

**Empfehlung für Phase 2:**
- Add `legal_basis` field to approval workflow
- Implement basis check: `if legal_basis not in valid_bases: return BLOCK`

#### 4.2 Zweckbindung (Art. 5(1)(b))

**Anforderung:** Daten dürfen nur für ursprünglichen Zweck verarbeitet werden.

**Phase 1.2 Status:** ⚠️ Begrenzt geprüft
- ✅ Audit logs tracken `reason_code` (zweckbezogen)
- ❌ Keine Prüfung, ob LLM-Verarbeitung dem ursprünglichen Zweck entspricht
- ❌ Keine Zweckbegrenzungs-Erklärung an Nutzer

#### 4.3 Datenminimierung (Art. 5(1)(c))

**Anforderung:** Nur erforderliche Daten verarbeiten.

**Phase 1.2 Status:** ✅ Gut
- ✅ Secrets werden BLOCKIERT (nicht minimiert, sondern gelöscht)
- ✅ Sensitive Data werden REDACTED
- ✅ Approval-Logs speichern NUR Metadaten, keine Originaldaten
- ✅ `assert_no_pii()` prüft vor Speicherung

**Befund:** ✅ **KONFORM** für Datenminimierung

#### 4.4 Richtigkeit (Art. 5(1)(d))

**Anforderung:** Daten müssen sachlich richtig sein.

**Phase 1.2 Status:** ⚠️ Begrenzt
- ✅ Audit logs dokumentieren, WELCHE Kategorien erkannt wurden
- ❌ Keine Prüfung auf Falsch-Positive (z.B. "Migräne" könnte auch Teil eines Romannamens sein)
- ❌ Keine Möglichkeit für Nutzer, fehlerhafte Klassifikation zu korrigieren

#### 4.5 Speicherbegrenzung (Art. 5(1)(e))

**Anforderung:** Daten nicht länger als nötig speichern.

**Phase 1.2 Status:** ✅ Gut
- ✅ Retention Engine mit konfigurierten Löschfristen
  - audit_logs: 90 Tage
  - approval_logs: 365 Tage
  - security_logs: 180 Tage
- ✅ Legal Hold respektiert (blockiert Löschung bei Bedarf)
- ✅ pg_advisory_lock verhindert Race Conditions

**Befund:** ✅ **KONFORM** für Speicherbegrenzung

#### 4.6 Integrität & Vertraulichkeit (Art. 5(1)(f))

**Anforderung:** Angemessene Sicherheit gewährleisten.

**Phase 1.2 Status:** ⚠️ Begrenzt
- ✅ Audit logs werden in Datenbank gespeichert (strukturiert)
- ✅ Normalized reason_codes (keine freetext PII in Logs)
- ⚠️ Keine Verschlüsselung erwähnt (Infrastruktur-Layer)
- ⚠️ Keine TLS in Transit erwähnt (Infrastruktur-Layer)
- ⚠️ Keine End-to-End-Encryption für sensitive Data

**Empfehlung:** Infrastruktur-Review notwendig (Phase 2+)

---

### 5. Art. 6 DSGVO – Rechtmäßigkeit der Verarbeitung

**Anforderung:** Verarbeitung muss auf EINER Rechtsgrundlage beruhen:
- (a) Einwilligung
- (b) Vertrag
- (c) Rechtliche Verpflichtung
- (d) Lebensinteressen
- (e) Aufgabe im öffentlichen Interesse
- (f) Berechtigte Interessen

**Phase 1.2 Implementierung:**

```python
# PolicyEngine.process_with_policy() hat NO Rechtsgrundlage-Prüfung!
# Decision ist nur basierend auf Risiko-Level, nicht auf Rechtsgrundlage
```

**Befund:** ❌ **NICHT KONFORM** – Kritisches Defizit

**Empfehlung für Phase 2:**
```python
legal_basis_check = {
    "secret": "none",  # Always block, no basis needed
    "health": "must_have_consent_or_medical",
    "religion": "must_have_consent",
    "automated_decision": "must_have_transparency_right",
}

if data_class in ["confidential", "personal", "sensitive"]:
    basis = get_legal_basis(user_id, data_class)
    if basis not in VALID_BASES[data_class]:
        return PolicyDecision(decision="block", reason_code="NO_LEGAL_BASIS")
```

---

### 6. Art. 13-14 DSGVO – Informationspflicht

**Anforderung:** Nutzer muss informiert werden über:
- Wer verarbeitet (verantwortliche Stelle)
- Welche Daten (Art und Kategorien)
- Warum (Zweck und Rechtsgrundlage)
- Wie lange (Speicherfrist)
- Welche Rechte (Zugang, Löschung, Beschwerde, etc.)

**Phase 1.2 Status:** ❌ Nicht implementiert
- ❌ Keine Transparenzmitteilung an Nutzer
- ❌ Keine Angabe der Rechtsgrundlage in der Mitteilung
- ❌ Keine Kontaktdaten des Datenschutzbeauftragten
- ❌ Keine Beschwerdewege

**Empfehlung für Phase 2:**
```python
transparency_notice = {
    "controller": "AILIZA Data Controller",
    "data_categories": detected_special_categories,
    "legal_basis": legal_basis,
    "retention_period": "90 days (audit_logs)",
    "user_rights": [
        "Access (Art. 15)",
        "Rectification (Art. 16)",
        "Erasure (Art. 17)",
        "Restriction (Art. 18)",
        "Portability (Art. 20)",
        "Object (Art. 21)"
    ],
    "complaint_address": "dpo@ailiza.example.com",
    "supervisory_authority": "Bundesdatenschutzbeauftragter (BfDI)"
}
```

---

### 7. EU AI Act – Hochrisiko-Kategorisierung

**Anforderung (Art. 6 EU AI Act):** Hochrisiko-KI-Systeme müssen:
- Risikoanalyse durchführen
- Transparente Dokumentation
- Menschliche Aufsicht gewährleisten
- Kontinuierliche Überwachung

**AILIZA Risiko-Einordnung:**

| Risiko-Typ | Phase 1.2 Hanling | HR-Kategorie? |
|-----------|------------------|---------------|
| Recruitment/Employment (HR+Health) | BLOCK (RED) | ✅ Ja (Anhang III, Punkt 1) |
| Automated Decision making | BLOCK (RED) | ✅ Ja (Anhang III, Punkt 6) |
| Credit Scoring | BLOCK (RED) | ✅ Ja (Anhang III, Punkt 5) |
| Criminal Data | BLOCK (RED) | ✅ Ja (Anhang III, Punkt 3) |

**Befund:** ✅ Phase 1.2 blockiert alle erkannten Hochrisiko-Kategorien

**Defizit:** ❌ Aber keine strukturierte Risk Impact Assessment dokumentiert

**Empfehlung für Phase 2:**
- Risk Register mit DPIA (Data Protection Impact Assessment)
- Nachweise für human oversight
- Audit trail für alle HIGH_RISK blockades

---

### 8. Art. 24 DSGVO – Verantwortung des Verantwortlichen

**Anforderung:** Dokumentieren, dass Compliance-Maßnahmen getroffen wurden.

**Phase 1.2 Status:** ⚠️ Teilweise
- ✅ Audit logs (dokumentiert WELCHE Entscheidungen getroffen)
- ✅ Test suite (52 Tests zeigen Funktionalität)
- ⚠️ Keine formale DSGVO-Compliance-Erklärung
- ❌ Keine Datenschutzerklärung an Nutzern
- ❌ Keine Data Processing Agreement (DPA) mit LLM-Providern

**Empfehlung:** Privacy Policy + DPA Templates für Phase 2

---

### 9. Art. 28 DSGVO – Auftragsverarbeiter-Vereinbarung

**Anforderung:** Falls LLM (OpenAI, Anthropic, etc.) als Auftragsverarbeiter genutzt, MUSS:
- Signed Data Processing Agreement (DPA) vorhanden sein
- Garantien: Datensicherheit, Unterstützung bei Betroffenenrechten
- Unterbindung von Datentransfers ohne Zustimmung

**AILIZA Status:** ⚠️ Kritisch
- ❌ Keine DPA-Prüfung in Phase 1.2
- ❌ Keine Automatische Prüfung, ob LLM-Provider zertifiziert ist
- ⚠️ USA-Transfer ohne adequacy decision?

**Empfehlung für Phase 2:**
```python
# Provider Governance (Phase 2)
LLM_PROVIDER_COMPLIANCE = {
    "openai": {
        "dpa_signed": True,
        "adequacy_decision": "schrems_ii_standard_contractual_clauses",
        "data_location": "EU_only",  # or "USA_with_safeguards"
    },
    "anthropic": {
        "dpa_signed": True,
        "adequacy_decision": "standard_contractual_clauses",
        "data_location": "EU",
    }
}
```

---

## 📊 Zusammenfassung: DSGVO-Konformität

| Artikel | Thema | Status | Schweregrad |
|---------|-------|--------|-------------|
| Art. 4 | Definition | ✅ | — |
| Art. 5 (a) | Rechtmäßigkeit | ❌ | 🔴 KRITISCH |
| Art. 5 (b) | Zweckbindung | ⚠️ | 🟡 MEDIUM |
| Art. 5 (c) | Datenminimierung | ✅ | — |
| Art. 5 (d) | Richtigkeit | ⚠️ | 🟡 MEDIUM |
| Art. 5 (e) | Speicherbegrenzung | ✅ | — |
| Art. 5 (f) | Sicherheit | ⚠️ | 🟡 MEDIUM |
| Art. 6 | Rechtsgrundlage-Prüfung | ❌ | 🔴 KRITISCH |
| Art. 9 | Besondere Kategorien | ⚠️ | 🔴 KRITISCH |
| Art. 13-14 | Informationspflicht | ❌ | 🔴 KRITISCH |
| Art. 22 | Automatisierte Entscheidungen | ⚠️ | 🟡 MEDIUM |
| Art. 24 | Verantwortung | ⚠️ | 🟡 MEDIUM |
| Art. 28 | Auftragsverarbeiter | ❌ | 🔴 KRITISCH |

---

## ✅ Was Phase 1.2 BEREITS KONFORM ist

1. ✅ **Secrets werden BLOCKIERT** (nie an LLM)
2. ✅ **Datenminimierung** (nur Metadaten in Approval-Logs)
3. ✅ **Speicherbegrenzung** (Retention mit konfigurierten Fristen)
4. ✅ **Hochrisiko-Blockade** (HR+Health, Automation, Criminal)
5. ✅ **Audit-Trail** (normalisierte Reason-Codes, keine PII in Logs)
6. ✅ **Legal Hold** (Preservation bei Bedarf)
7. ✅ **Transparenz für Admins** (detaillierte Logs)

---

## ❌ Was Phase 1.2 NICHT KONFORM ist

1. ❌ **Keine Rechtsgrundlage-Prüfung** (Art. 6 DSGVO)
2. ❌ **Keine Art. 9-Rechtsgrundlage-Validierung** (nur Erkennung, keine Basis-Check)
3. ❌ **Keine Nutzertransparenz** (Nutzer weiß nicht, welche Daten verarbeitet wurden)
4. ❌ **Keine Art. 22-Nutzerrechte-Umsetzung** (Nutzer kann nicht eingreifen)
5. ❌ **Keine DPA-Prüfung für LLM-Provider** (USA-Transfer unklar)
6. ❌ **Keine Datenschutzerklärung an Nutzer**

---

## 🛠️ Empfehlungen für Phase 2

### Priorität 🔴 KRITISCH (Muss vor Production)

1. **Rechtsgrundlage-System implementieren**
   ```python
   # Check Art. 6 legal basis BEFORE processing
   legal_basis = get_legal_basis(user_id)
   if legal_basis not in VALID_BASES:
       return PolicyDecision(decision="block", reason_code="NO_LEGAL_BASIS_ART6")
   ```

2. **Art. 9 Rechtsgrundlage-Validierung**
   ```python
   if "health" in detected_special_categories:
       if legal_basis not in ["explicit_consent", "medical_purpose"]:
           return PolicyDecision(decision="block", reason_code="NO_LEGAL_BASIS_ART9")
   ```

3. **LLM-Provider Governance**
   - DPA-Prüfung für alle verwendeten Provider
   - Standard Contractual Clauses (SCC) für USA-Transfer
   - Schrems II Compliance

4. **Nutzertransparenz-Mitteilung**
   - Was wurde erkannt (kategorien)
   - Warum wurde blockiert/redacted (reason_code)
   - Welche Rechte hat der Nutzer

### Priorität 🟡 MEDIUM (Vor oder kurz nach Production)

5. **Art. 22 Nutzerrechte-Umsetzung**
   - Explizite Mitteilung an Nutzer
   - Option für manuelle Überprüfung
   - Opt-Out-Möglichkeit

6. **Datenschutzerklärung**
   - Veröffentlichung unter datenschutz.ailiza.de
   - Übersetzungen (DE, EN, etc.)
   - Regular Updates bei Änderungen

7. **Betroffenenrechte-System**
   - Art. 15: Zugriff auf Daten
   - Art. 17: Recht auf Vergessenwerden
   - Art. 20: Datenportabilität

8. **DPIA (Data Protection Impact Assessment)**
   - Dokumentieren für Hochrisiko-Verarbeitung
   - Risikoanalyse
   - Mitigations-Maßnahmen

### Priorität 🟢 SHOULD (Empfohlen)

9. **Datenschutzbeauftragter (DPO)**
   - Kontakt: dpo@ailiza.example.com
   - Erreichbarkeit dokumentieren
   - Beschwerdeverfahren

10. **Regelmäßige Audits**
    - Compliance-Prüfungen quarterly
    - Penetration Testing
    - Automatisierte Checks

---

## 📝 Compliance-Dokumentation

### Zu erstellende Dokumente für Phase 2

1. **Datenschutzerklärung (Art. 13-14)**
2. **Data Processing Agreement (DPA) mit LLM-Providern**
3. **Risiko-Register und DPIA**
4. **Compliance-Matrix** (wie jedes Artikel erfüllt wird)
5. **Incident Response Plan**
6. **Audit Trail Reports** (regelmäßig exportieren)

---

## ⚠️ KRITISCHE WARNUNG

> **Phase 1.2 ist NICHT PRODUKTIONSREIF für die DSGVO-Konformität.**
> 
> Folgende Lücken MÜSSEN vor Production geschlossen werden:
> 1. Rechtsgrundlage-Prüfung (Art. 6)
> 2. Art. 9 Basis-Validierung
> 3. LLM-Provider DPA
> 4. Nutzertransparenz
> 5. Art. 22-Nutzerrechte

**Empfohlenes Vorgehen:**
1. Phase 1.2 in Staging/Test-Umgebung nutzbar ✅
2. Phase 2: Rechtliche Lücken schließen (4-8 Wochen)
3. Legal Review durch externen Datenschutzanwalt (2-4 Wochen)
4. Production-Deployment nach Zertifizierung

---

## 📚 Referenzen

- DSGVO: https://eur-lex.europa.eu/eli/reg/2016/679/oj
- EU AI Act: https://eur-lex.europa.eu/eli/reg/2024/1689/oj
- EDPB Guidelines on Article 22: https://edpb.ec.europa.eu/sites/default/files/files/file1/edpb_guidelines_201_automated_decision_making_en.pdf
- Schrems II Decision: https://curia.europa.eu/jcms/upload/docs/application/pdf/2020-07/cp200091en.pdf
- ISPC Standard Contractual Clauses: https://commission.europa.eu/publications/standard-contractual-clauses-scc_en

