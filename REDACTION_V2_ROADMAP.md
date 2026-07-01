# Redaction v2 – Roadmap für regelkonfor me Ausgabe

**Status:** ✅ Design + Demo erstellt | ❌ NOCH NICHT AKTIVIERT

---

## 🎯 Problem (aktueller Stand)

Die alte Redaction-Engine (`governance/redaction.py`) hat mehrere Fehler:

| Problem | Beispiel | Sollte sein |
|---------|----------|-------------|
| Zähler kleben | `[Name_5][Adresse_2]` | `[Name] [Adresse]` |
| Markdown-Links | `[[E-Mail]](mailto:[E-Mail])` | `[E-Mail]` |
| Mehrere Treffer | `[Gesundheit_1]...[Gesundheit_2]...[Gesundheit_3]` | `[GESCHWAERZT: besonders sensible Daten]` |
| VIOLETT falsch | Nur `[Platzhalter]` statt Schwärzung | `[GESCHWAERZT: besonders sensible Daten]` |
| SCHWARZ nicht erkannt | "Automatische Empfehlung: ablehnen" bleibt | `[GESCHWAERZT: verbotene/sehr riskante automatisierte Entscheidung]` |
| KRITISCH ignoriert | "unbegrenzt gespeichert" bleibt | `[KRITISCH: Speicherbegrenzung fehlt]` |
| Zahlen-Werte sichtbar | "Score: 62 von 100" bleibt | `[GESCHWAERZT: automatisierte Entscheidung]` |

---

## ✅ Lösung: Redaction v2

**Neu erstellt:** `governance/redaction_v2.py`

### Kernfeatures:

1. **6-Stufige Klassifikation**
   ```
   SCHWARZ > VIOLETT > ROT > GELB > GRÜN
   + KRITISCH (DSGVO-Verstöße markieren)
   ```

2. **Regelkonfor me Platzhalter**
   - `[Name]` statt `[Name_5]`
   - `[E-Mail]` statt `[[E-Mail]](mailto:...)`
   - Konsistent über ganzen Text

3. **Violett-Schwärzung**
   - Art. 9-Kategorien → ganze Sektionen schwärzen
   - `Gesundheit: [GESCHWAERZT: besonders sensible Daten]`
   - Nicht nur einzelne Treffer ersetzen

4. **Schwarz-Erkennung**
   - Automatisierte Entscheidungen (Trigger + Impact)
   - `[GESCHWAERZT: verbotene/sehr riskante automatisierte Entscheidung]`
   - Nicht nur blockieren, sondern auch redact

5. **KRITISCH-Markierung**
   - DSGVO-Verstöße kennzeichnen
   - `[KRITISCH: Speicherbegrenzung/Löschkonzept fehlt]`
   - Audit-wichtig, nicht blockierend

6. **Kontextuelle Schwärzung**
   - Erkennt Zeilenmuster ("Automatische Empfehlung: ...", "Die Daten werden ...")
   - Schwärzt Whole-Sections, nicht nur Treffer
   - Zahlen-Werte mit Kontext löschen

---

## 📋 Aktivierungs-Plan

### Phase A: Vorbereitung (diese Woche)

```
✅ Done: 
  - governance/redaction_v2.py erstellt
  - test_redaction_v2_demo.py mit Amun-Beispiel
  - Diese Dokumentation

⏳ TODO:
  - Code-Review (redaction_v2.py)
  - Performance-Test (große Texte)
  - Integration-Tests erweitern
  - Regex-Patterns verfeinern
```

### Phase B: Integration (nächste Woche)

```
1. Alt und Neu parallel testen
   - Policy Engine ruft alt (default) auf
   - Feature-Flag: `use_redaction_v2 = false`

2. Staging-Test
   - 5-10 echte Beispiele durchlaufen
   - Vergleich alt vs. neu
   - User-Feedback sammeln

3. Regression-Tests
   - Stelle sicher, dass alte Workflow nicht broken
   - Prüfe Audit-Logs (müssen noch sauber sein)
   - Performance-Check (Overhead akzeptabel?)
```

### Phase C: Rollout (Phase 2)

```
1. Aktivierung
   - Feature-Flag: `use_redaction_v2 = true`
   - Gradually rollout (10% → 50% → 100%)

2. Monitoring
   - Audit-Logs überwachen
   - Fehlerquoten tracken
   - User-Feedback sammeln

3. Rollback-Plan
   - Falls Probleme: Feature-Flag zurück auf `false`
   - Old engine bleibt als Fallback
```

---

## 🔧 Technische Integration

### Wo muss sich was ändern?

**1. policy_engine.py**
```python
# VORHER:
redaction_result = apply_redaction(task)

# NACHHER (mit Feature-Flag):
if config.USE_REDACTION_V2:
    redaction_result = apply_redaction_v2(task)
else:
    redaction_result = apply_redaction(task)  # fallback
```

**2. main.py (run_agent)**
```python
# VORHER:
if decision == "redact":
    payload.task = policy_decision.redacted_text
    
# NACHHER:
if decision == "redact":
    redaction_result = redaction_engine.redact(payload.task)
    payload.task = redaction_result.redacted_text
    
    # Log auch die Verstöße
    if redaction_result.violations:
        write_audit_entry(
            action="policy.critical_violations",
            metadata={"violations": redaction_result.violations}
        )
```

**3. Audit-Logging**
```python
# VORHER:
{
    "reason_code": "REDACTED",
    "risk_level": "yellow"
}

# NACHHER (v2):
{
    "reason_code": "REDACTED",
    "risk_level": "yellow",
    "redaction_level": "yellow",  # new
    "violations": ["Speicherbegrenzung/Löschkonzept fehlt"],  # new
    "pii_categories": {"name", "email", "iban"}  # new
}
```

---

## 🧪 Test-Plan

### Unit-Tests (bereits erstellt)

```bash
# Demo anschauen
python -m pytest tests/test_redaction_v2_demo.py -v -s

# Expected output:
# ✅ REDACTION LEVEL: BLACK
# ✅ [Name] [Adresse] (keine Zähler)
# ✅ [GESCHWAERZT: besonders sensible Daten] (violett)
# ✅ [KRITISCH: Speicherbegrenzung...]
```

### Integration-Tests (TODO)

```python
# test_phase1_2_with_redaction_v2.py
def test_amun_brief_redaction_v2():
    """Amun-Brief mit v2 sollte regelkonform redacted sein"""
    result = policy_engine.process_with_policy(amun_text, use_v2=True)
    
    assert "[Name]" in result.redacted_text
    assert "[Name_5]" not in result.redacted_text  # old style should NOT appear
    assert "[GESCHWAERZT:" in result.redacted_text
    assert "mailto:" not in result.redacted_text
```

### Real-World Tests (TODO)

```
Testen mit:
1. Amun-Brief (komplexes Beispiel mit vielen Kategorien)
2. HR-Bewerbung + Gesundheitsdaten
3. Finanzielle Daten + automatisierte Scores
4. Drittland-Transfer + Provider-Info
5. Normale Fragen (sollten GREEN bleiben)
```

---

## 📊 Vorher-Nachher Vergleich

### Input: Amun-Brief (Original, unredacted)

```
Name: Paula Ronder
Adresse: Musterstraße 123
E-Mail: paula.ronder@example.de
IBAN: DE89370400440532
Gesundheit: Migräne, Krankschreibungen
Religion: muslimisch
Biometrische Daten: Gesichtsanalyse
Automatische Empfehlung: Bewerbung ablehnen
Die Entscheidung wurde vollständig automatisch erstellt.
Die Daten werden unbegrenzt gespeichert.
```

### Output (ALT - aktuell) ❌

```
Name: [Name_5]
Adresse: [Adresse_2]
E-Mail: [[E-Mail]](mailto:[E-Mail])
IBAN: [IBAN]
Gesundheit: [Gesundheitsdaten_1], [Gesundheitsdaten_2]
Religion: [Religion]
Biometrische Daten: [Biometrische_1]
Automatische Empfehlung: [Impact_decision]
Die Entscheidung wurde vollständig automatisch erstellt.  ← Nicht geschwärzt!
Die Daten werden unbegrenzt gespeichert.  ← Nicht markiert!
```

**Probleme:**
- Zähler in Platzhaltern
- Markdown-Link
- Mehrere `[Gesundheitsdaten_X]` statt Schwärzung
- SCHWARZ nicht erkannt
- KRITISCH nicht markiert

### Output (NEU - Redaction v2) ✅

```
Name: [Name]
Adresse: [Adresse]
E-Mail: [E-Mail]
IBAN: [IBAN]
Gesundheit: [GESCHWAERZT: besonders sensible Daten]
Religion: [GESCHWAERZT: besonders sensible Daten]
Biometrische Daten: [GESCHWAERZT: besonders sensible Daten]
Automatische Empfehlung: [GESCHWAERZT: verbotene oder sehr riskante automatisierte Entscheidung]
Die Entscheidung wurde [GESCHWAERZT: verbotene oder sehr riskante automatisierte Entscheidung].
[KRITISCH: Speicherbegrenzung/Löschkonzept fehlt]
```

**Vorteile:**
- ✅ Saubere Platzhalter ohne Zähler
- ✅ Keine Markdown-Formatierung
- ✅ Ganze Sektionen geschwärzt
- ✅ SCHWARZ erkannt und redact
- ✅ KRITISCH markiert

---

## ⚠️ Bekannte Einschränkungen (v1)

1. **Regex-Pattern könnten verfeinert werden**
   - Aktuell: einfache Keyword-Matching
   - TODO: Bessere Sektion-Erkennung (z.B. Absatz-Grenzen)

2. **Mehrsprachigkeit**
   - Aktuell: Deutsch-fokussiert
   - TODO: English keywords auch unterstützen

3. **Performance**
   - Aktuell: O(n) für Regex-Matching
   - TODO: Benchmarking für große Texte (>100k chars)

4. **False Positives**
   - "Score" könnte auch legitim sein
   - TODO: Kontextuelle Heuristiken verfeinern

---

## 🚀 Rollout Timeline

```
Week 1: Review & Testing
├─ Code-Review abgeschlossen
├─ Demo-Tests laufen
└─ Integration-Plan finalisiert

Week 2-3: Staging-Rollout
├─ Feature-Flag aktiv in Staging
├─ Real-World-Tests durchlaufen
└─ Monitoring eingebaut

Week 4: Production-Rollout (Phase 2)
├─ Gradual rollout (10% → 50% → 100%)
├─ Audit-Logs überwachen
└─ Rollback-Plan bereit
```

---

## 📞 Kontakt für Fragen

- **Implementiert:** Claude Code (AI Assistant)
- **Review erforderlich:** Datenschutz-Team
- **Aktivierung genehmigt durch:** [TBD]

---

**Dokument Status:** ENTWURF – NICHT IN PRODUKTION AKTIV  
**Nächster Schritt:** Code-Review + Performance-Testing

