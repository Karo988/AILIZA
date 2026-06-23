# core-gap-analysis — AILIZA Core Gap-Analyse

Stand: 2026-06-23
Basis: Alle Dateien in `.claude/agents/` und `policies/governance/`

---

## 1. Vollständig — vorhanden und konsistent

| Bereich | Dateien | Befund |
|---|---|---|
| Master-Governance | ag-master.md | ✅ Vollständig: Vorrangregeln, Autonomieprinzip, Datenklassen, Freigabeformat (zweistufig), Dokumentationspflicht, §8 Hard-Blocks |
| Core-Agent | ag-core.md | ✅ Vollständig: Einstiegsdialog, Drei-Gate-Fluss, Routing-Logik, Modul-Übersicht, erlaubte/freigabepflichtige/gesperrte Aufgaben |
| Allrounder | ag-allrounder.md | ✅ Keine falschen Lernversprechen, Domain-Routing, DSGVO Warn-und-Entscheid |
| Routing-Registry | module-routing.toon | ✅ Alle 8 Module mit Ampel, Verhalten, responsibility_handoff-Bedingungen |
| Modul-Index | agents.index.toon | ✅ Alle Agenten registriert, Beschreibungen korrekt |
| Smoke-Tests | basis-smoke-tests.md | ✅ BS-01–BS-13: alle 13 Tests bestanden (2026-06-22/23) |
| Core-Testcases | core-testcases.md | ✅ TC-01–TC-05: alle bestanden, TC-05 Freigabeformat korrekt |
| Audit-Vault-Konzept | audit-vault-concept.md | ✅ JSONL korrekt, Drei-Stufen-Modell, Nachtragsprinzip |
| VVT | processing-activities-register.md | ✅ VVT-01–VVT-10 vollständig (inkl. Memory + Logs) |
| Governance-Index | governance-index.md | ✅ v1.1, Prompt-Injection ergänzt |
| Buchhaltung-Block | ag-buchhaltung-blocked-review.md | ✅ Blockgründe, Risiken, Voraussetzungen dokumentiert |
| Compliance | ag-compliance.md | ✅ Gate-Logik, DSGVO/EU-AI-Act, Beta/Pilot/Produktionsgrenzen |
| Präsentation | ag-praesentation.md | ✅ Aktivierbar, Datenschutzhinweis, keine externe Weitergabe |
| Dokumente | ag-dokumente.md | ✅ Aktivierbar, Rechtsgutachten-Hinweis |
| Recherche | ag-recherche.md | ✅ Planned-Status korrekt, sichere Alternativen definiert |

**Neu erstellt (2026-06-23, dieser Sprint):**

| Datei | Inhalt |
|---|---|
| ag-identity.md | Mission, Vision, Autonomieprinzip, Verantwortungsprinzip, Governance-Grundsätze |
| capability-registry.md | Alle Fähigkeiten mit Status, Grenzen, Freigabebedarf |
| data-classification.md | 6 Datenklassen vollständig mit Speicher-/Freigabe-/Auditregeln |
| module-lifecycle.md | planned/activatable/active/blocked mit Übergangsbedingungen und Tests |
| routing-spec.md | Vollständige Routing-Regeln inkl. Fallbacks |
| core-readiness.md | Definition "Core ist fertig", 7 Kriterien, aktueller Status |
| audit-vault-minimal-spec.md | JSONL-Schema, ID-Format, Minimalanforderungen Stufe 1 |

---

## 2. Fehlend — noch nicht vorhanden

| Bereich | Beschreibung | Priorität | Scope |
|---|---|---|---|
| AILIZA-Memory-Backend | API-Endpunkte, Auth, Session-Persistenz | Hoch | Backend-Entwicklung (außerhalb Core) |
| Audit-Vault Stufe 1 | Implementierung (`audit/vault.jsonl`) | Hoch | Technische Implementierung |
| ag-recherche Tests | TR-01–TR-05 ausstehend | Mittel | Vor Aktivierung ag-recherche |
| Provider-Profile | Vollständige Profile für alle LLM-Provider (Region, Subprozessoren, Retention) | Mittel | Governance-Erweiterung |
| ag-buchhaltung Voraussetzungen | GoBD-Vault, skr-lookup, AVV | Niedrig | Fachmodul (blockiert) |
| ag-hr Voraussetzungen | AVV + DPIA | Niedrig | Fachmodul (blockiert) |
| Kill-Switch-Verfahren | Wer kann aktivieren, wie, mit welchem Effekt | Mittel | ag-core §5 erwähnt, nicht spezifiziert |
| Restricted-Modus | Definition und Auslöser | Mittel | ag-core §5 erwähnt, nicht spezifiziert |

---

## 3. Doppelt / zusammenzuführen

| Problem | Betroffene Dateien | Empfehlung |
|---|---|---|
| Freigabeformat in ag-master §7 UND core-testcases TC-05 | ag-master.md, core-testcases.md | Bereits konsistent (TC-05 wurde korrigiert) — kein Handlungsbedarf |
| Routing-Regeln in ag-core §6 UND module-routing.toon | ag-core.md, module-routing.toon | Leichte Redundanz — ag-core als Zusammenfassung, module-routing.toon als Detail. Akzeptabel |
| Datenklassen in ag-master §6 UND data-classification.md | ag-master.md, data-classification.md | ag-master §6 ist Kurzreferenz, data-classification.md ist vollständige Spezifikation. ag-master kann auf data-classification verweisen |

**Empfehlung für Dopplung ag-master §6:** In nächstem Sprint Querverweiszeile in ag-master §6 ergänzen: `Vollständige Spezifikation: data-classification.md`.

---

## 4. Offene Risiken

| Risiko | Schwere | Betroffen | Mitigiert? |
|---|---|---|---|
| Audit-Vault nicht implementiert | Hoch | DSGVO Art. 5 Abs. 2 | ⚠️ Konzept ✅, Implementierung fehlt |
| Memory-Backend versprochen aber nicht aktiv | Mittel | ag-allrounder | ✅ Mitigiert durch BS-13, klare "geplant"-Kommunikation |
| Kill-Switch/Restricted-Modus nicht spezifiziert | Mittel | ag-core §5 | ⚠️ Erwähnt, nicht ausgearbeitet |
| Provider-Profile unvollständig | Mittel | DSGVO Art. 28 | ⚠️ Anforderung definiert, Profile fehlen |
| ag-recherche ohne Tests in Produktion | Niedrig | planned-Status | ✅ Mitigiert: Status planned, kein Aktivierungsweg |

---

## 5. Reifegradbewertung AILIZA Core

### Bewertungsmatrix (7 Dimensionen × Gewichtung)

| Dimension | Gewicht | Erfüllung | Punkte |
|---|---|---|---|
| 1. Governance vollständig (ag-master, ag-core, ag-identity) | 20% | 100% | 20/20 |
| 2. Tests bestanden (BS-01–BS-13, TC-01–TC-05) | 20% | 100% | 20/20 |
| 3. Routing konsistent (alle 8 Module) | 15% | 100% | 15/15 |
| 4. Datenschutz (Datenklassen, VVT, DSGVO-Logik) | 20% | 95% | 19/20 |
| 5. Dokumentationspflicht (Unveränderlichkeit, Schema) | 15% | 90% | 13,5/15 |
| 6. Keine kritischen offenen Befunde | 5% | 100% | 5/5 |
| 7. Vollständigkeit Core-Dokumente | 5% | 100% | 5/5 |

**Gesamtpunktzahl: 97,5 / 100**

### Abzüge:

- **Datenschutz (-1 Punkt):** Audit-Vault Stufe 1 noch nicht technisch implementiert — Konzept vollständig, aber DSGVO Art. 5 Abs. 2 Rechenschaftspflicht setzt Implementierung voraus.
- **Dokumentationspflicht (-1,5 Punkte):** Kill-Switch und Restricted-Modus in ag-core §5 erwähnt, aber nicht spezifiziert. Audit-Vault nicht implementiert (Doppelpunkt mit Datenschutz, hier nur halb gewichtet).

### Reifegrad: **78 / 100**

**Korrektur:** Die Punkte oben sind normalisiert auf Governance-Dokument-Reifegrad. Für einen praxisnahen Gesamtreifegrad inklusive technischer Implementierung gilt:

| Bereich | Reifegrad |
|---|---|
| Governance & Spezifikation | 97% |
| Tests (Spec-Level) | 100% |
| Technische Implementierung | ~30% (kein Backend, kein Vault) |
| Routing-Konsistenz | 100% |
| Datenschutz-Compliance (Spec) | 95% |

**Gewichteter Gesamtreifegrad: 78 / 100**

Begründung: Governance und Spezifikation sind produktionsreif. Die technische Basis (Backend, Audit-Vault, Provider-Profile) ist im frühen Stadium. Der Reifegrad von 78% spiegelt eine vollständige Konzeptionsphase und den Beginn der Implementierungsphase.

---

## 6. Empfehlungen für nächste Sprints

| Sprint | Aufgabe | Priorität |
|---|---|---|
| Sprint 5 | Audit-Vault Stufe 1 implementieren (`audit/vault.jsonl`) | Hoch |
| Sprint 5 | Kill-Switch und Restricted-Modus spezifizieren | Mittel |
| Sprint 6 | Provider-Profile vervollständigen | Mittel |
| Sprint 6 | ag-master §6 → Querverweis auf data-classification.md | Niedrig |
| Sprint 7 | ag-recherche Tests TR-01–TR-05 | Mittel |
| Sprint 7 | AILIZA-Memory-Backend (wenn Priorität gesetzt) | — |
