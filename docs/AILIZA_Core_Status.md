# AILIZA Core — Status & Readiness

**Stand:** 24.06.2026
**Branch:** claude/adoring-lamport-c1zs8h

---

## Präzise Formulierung des aktuellen Stands

```
AILIZA Core ist prompt- und governance-seitig final spezifiziert.

Technisch final ist AILIZA Core erst nach Umsetzung und Test des
Memory-Backends sowie des Audit-Vault-Minimums.
```

> **Nicht** „AILIZA Core ist final bereit" — das wäre technisch ungenau.
> Die Spezifikation ist bereit. Die Implementierung ist noch offen.

---

## Fachlich / Konzeptionell: Was geregelt ist

Die folgenden Core-Regeln sind vollständig definiert und in der Basis verankert:

| Regel | Beschreibung |
|-------|-------------|
| Kontrollierte Autonomie | Agent handelt nur im definierten Rahmen |
| Nutzeranpassung | Anpassung erlaubt, aber mit klaren Grenzen |
| Kurzzeit-Kontext | Kein dauerhaftes Speichern ohne Zustimmung |
| Dauerhafte Speicherung nur mit Zustimmung | Explizites Opt-in erforderlich |
| Keine sensiblen Daten ins Memory | PII, Gesundheitsdaten, Finanzdaten ausgeschlossen |
| Nutzerkontrolle über Memory | Nutzer kann jederzeit löschen, exportieren, einsehen |
| Keine falschen Lernversprechen | ag-allrounder darf kein dauerhaftes Lernen versprechen |
| Audit-Vault unveränderbar | Einträge sind write-once, nicht editierbar |
| responsibility_handoff geschützt | Übergabe-Protokoll bleibt integer |

Das ist die richtige Balance: **intelligent, aber nicht heimlich speichernd.**

---

## Readiness-Übersicht

| Bereich | Status | Hinweis |
|---------|--------|---------|
| AILIZA Core Prompt | ✅ final spezifiziert | |
| Nutzeranpassung | ✅ geregelt | |
| Memory-Regeln | ✅ geregelt | |
| Sensible Daten | ✅ ausgeschlossen | |
| Nutzerkontrolle | ✅ geregelt | |
| ag-allrounder Lernversprechen | ✅ bereinigt | |
| BS-14 bis BS-18 | 🟡 definiert, technisch offen | Memory-Backend fehlt noch |
| Memory-Backend | 🔵 später | nächste Entwicklungsphase |
| Audit-Vault technisch | 🔵 später | Minimal-Spec noch zu erstellen |
| Kill-Switch / Restricted-Modus | ⚠️ prüfen | Spezifikation aus Gate 3 vorhanden — prüfen ob vollständig in Basis dokumentiert |

---

## Hinweis: Kill-Switch / Restricted-Modus

Kill-Switch und Betriebsmodi wurden in **Gate 3** bereits beschrieben.

Der Eintrag ist daher **keine offene Spezifikation**, sondern eine **Konsistenzprüfung**:

```
Prüfen, ob die aktuelle Spezifikation aus Gate 3 vollständig
in der aktuellen Basis (docs, policies, agent_core) dokumentiert ist.
```

Falls Gate-3-Inhalte fehlen oder veraltet sind → als Lücke markieren und nachziehen.

---

## BS-14 bis BS-18 — Technisch offen

Diese Behavioral Specifications sind definiert, aber noch nicht ausgeführt:

- Abhängigkeit: Memory-Backend existiert noch nicht
- Konsequenz: keine technische Lücke, sondern eine **planmäßige Reihenfolge**
- Status bleibt 🟡 bis Memory-Backend implementiert und getestet ist

---

## Core Readiness — Drei Ebenen

| Ebene | Status | Bedeutung |
|-------|--------|-----------|
| **Prompt-ready** | ✅ | Core-Prompt ist vollständig und einsatzbereit |
| **Spec-ready** | ✅ | Alle Regeln und Governance-Anforderungen sind spezifiziert |
| **Tech-ready** | 🟡 | Offen bis Memory-Backend + Audit-Vault-Minimum umgesetzt und getestet sind |

**Offiziell markierbar als: Basis v1.0 Spec-ready**
Tech-ready folgt nach Implementierung.

---

## Nächste Schritte (priorisiert)

1. **Kill-Switch / Restricted-Modus gegen Basis prüfen**
   - Gate-3-Spezifikation mit aktuellem Stand abgleichen
   - Fehlende Teile in `docs/` und `policies/` nachtragen

2. **Audit-Vault Minimal-Spec erstellen**
   - Was muss der Vault mindestens speichern?
   - Write-once-Mechanismus definieren
   - Format und Aufbewahrungsdauer festlegen

3. **Core-Readiness Trennung finalisieren**
   - Prompt-ready ✅
   - Spec-ready ✅
   - Tech-ready 🟡 (offen)

---

*AILIZA Core — Basis v1.0 Spec-ready | Tech-ready ausstehend*
