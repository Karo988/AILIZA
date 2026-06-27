---
name: core-readiness
description: AILIZA Core-Readiness-Definition. Drei Ebenen — Prompt-ready, Spec-ready, Tech-ready. Aktueller Status: Basis v1.0 Spec-ready (Stand 2026-06-23).
status: active
updated: 2026-06-23
version: 1.1
---

# core-readiness — AILIZA Core-Readiness

Stand: 2026-06-23

---

## Drei-Ebenen-Modell

AILIZA Core-Readiness ist in drei unabhängig bewertbaren Ebenen definiert.
Ein höheres Level setzt das vorherige voraus.

| Ebene | Bedeutung | Aktueller Status |
|---|---|---|
| **Prompt-ready** | Alle Prompts, Regeln und Agenten-Definitionen vollständig und konsistent | ✅ erreicht |
| **Spec-ready** | Alle Spezifikationsdokumente, Tests (definiert), Gap-Analyse, Lifecycle-Dokumente vollständig | ✅ erreicht |
| **Tech-ready** | Technische Implementierung (Backend, Vault, Provider) live und Tests bestanden | ⏳ ausstehend |

**Aktueller Gesamtstatus: Basis v1.0 Spec-ready (Stand: 2026-06-23)**

---

## Ebene 1: Prompt-ready

AILIZA Core ist Prompt-ready wenn alle Agenten-Definitionen vollständig, konsistent und widerspruchsfrei sind.

| Anforderung | Datei | Status |
|---|---|---|
| Master-Governance vollständig (Vorrangregeln, Autonomie, Freigabe, Memory, Datenschutz) | ag-master.md v1.1 | ✅ |
| Core-Agent vollständig (Einstieg, Basisfluss, Routing, Gate 1–3, Datenschutzregeln) | ag-core.md v1.1 | ✅ |
| Gate 3 Betriebsmodi vollständig (5 Modi inkl. kill_switch_active) | ag-core.md §5, ag-compliance.md Gate 3 | ✅ |
| Allrounder ohne falsche Lernversprechen (keine API-Calls) | ag-allrounder.md v1.1 | ✅ |
| Nutzeranpassung und Memory-Regeln definiert (Kurzzeit + dauerhaft + Nutzerkontrolle) | ag-master.md §13 | ✅ |
| Identität und Leitprinzipien dokumentiert | ag-identity.md | ✅ |
| Routing-Logik vollständig (alle 8 Module, Fallbacks) | ag-core.md §6, routing-spec.md | ✅ |
| Freigabeformat zweistufig (Kurzfreigabe + Vollfreigabe) | ag-master.md §7 | ✅ |
| Unveränderlichkeitsregel + Nachtragsprinzip | ag-master.md §10 | ✅ |
| Blocked-Module im Verantwortungs- und Übergabemodus | ag-buchhaltung-blocked-review.md | ✅ |
| Keine kritischen Widersprüche (Governance-Konsistenz-Check v1.1) | governance-index.md | ✅ |

**Prompt-ready: ✅ vollständig**

---

## Ebene 2: Spec-ready

AILIZA Core ist Spec-ready wenn alle Spezifikationsdokumente, Test-Specs und Lifecycle-Regeln vollständig sind.

| Anforderung | Datei | Status |
|---|---|---|
| Capability-Register vollständig | capability-registry.md | ✅ |
| Datenklassifizierung vollständig (6 Klassen) | data-classification.md | ✅ |
| Module-Lifecycle vollständig | module-lifecycle.md | ✅ |
| Routing-Spezifikation vollständig | routing-spec.md | ✅ |
| Audit-Vault-Mindestspezifikation (JSONL-Schema, IDs, Append-only) | audit-vault-minimal-spec.md | ✅ |
| VVT vollständig (VVT-01 bis VVT-10, inkl. Memory + Logs) | processing-activities-register.md | ✅ |
| Smoke-Tests BS-01–BS-13 bestanden | basis-smoke-tests.md | ✅ |
| Smoke-Tests BS-14–BS-18 vollständig spezifiziert (Memory/Nutzerkontrolle) | basis-smoke-tests.md | ✅ spezifiziert |
| Core-Testcases TC-01–TC-05 bestanden | core-testcases.md | ✅ |
| Gap-Analyse vollständig | core-gap-analysis.md | ✅ |
| Kill-Switch-Querverweis konsistent (ag-core §5 ↔ ag-compliance Gate 3) | ag-core.md §5 | ✅ |
| Keine kritischen offenen Befunde | core-gap-analysis.md | ✅ |

**Spec-ready: ✅ vollständig**

---

## Ebene 3: Tech-ready

AILIZA Core ist Tech-ready wenn die technische Implementierung live ist und Tests gegen echte Systeme bestanden haben.

| Anforderung | Status | Abhängigkeit |
|---|---|---|
| Audit-Vault Stufe 1 implementiert (`audit/vault.jsonl`, append-only) | ⏳ offen | Backend-Entwicklung |
| BS-14–BS-18 gegen echtes Memory-Backend ausgeführt und bestanden | ⏳ offen | Memory-Backend aktiv |
| Memory-Backend aktiviert (Session-übergreifende Präferenzen) | ⏳ offen | Backend-Entwicklung |
| Provider-Profile vollständig (Region, AVV, Trainingsnutzung, Retention) | ⏳ offen | Provider-Entscheidung |
| Kill-Switch-Aktivierungsprozedur definiert (wer darf aktivieren) | ⏳ offen | Organisationsentscheidung |

**Tech-ready: ⏳ ausstehend**

---

## Nicht-Ziele des Core (Scope-Ausschlüsse)

Core gilt als Spec-ready, auch wenn folgendes noch offen ist:

- AILIZA-Memory-Backend (geplant → Tech-ready)
- ag-recherche Tests TR-01–TR-05 (geplant, Modul-Scope)
- ag-buchhaltung Voraussetzungen (blocked, Fachmodul-Scope)
- ag-hr Voraussetzungen (blocked, Fachmodul-Scope)
- CRM, Marketing, Schulung (nicht im Core-Scope)
- Modul-spezifische Vertiefungstests (nach Core-Freigabe, Modul-Scope)

---

## Gesamtstatus

```
AILIZA Core — Basis v1.0
Stand:         2026-06-23
Prompt-ready:  ✅ vollständig
Spec-ready:    ✅ vollständig
Tech-ready:    ⏳ ausstehend (Memory-Backend, Audit-Vault Stufe 1, Provider-Profile)

Offizielle Bezeichnung: Basis v1.0 Spec-ready
```

---

## Freigabe-Kriterien je Ebene

| Ebene | Freigabe durch |
|---|---|
| Prompt-ready | Governance-Review + Konsistenz-Check bestanden |
| Spec-ready | Prompt-ready + alle Spezifikationsdokumente + Test-Specs vollständig + Gap-Analyse |
| Tech-ready | Spec-ready + alle Tech-Tests bestanden + kein offener kritischer Befund |
