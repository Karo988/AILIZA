---
name: core-readiness
description: AILIZA Core-Readiness-Definition. Was "AILIZA Core ist fertig" bedeutet — Mindestanforderungen für Governance, Tests, Routing, Dokumentation und Audit. Basis für Reifegradbewertung.
status: active
updated: 2026-06-23
---

# core-readiness — AILIZA Core-Readiness

Stand: 2026-06-23

---

## Definition: AILIZA Core ist fertig

AILIZA Core gilt als fertig, wenn alle folgenden Kriterien erfüllt sind.

---

## Kriterium 1: Governance vollständig

| Anforderung | Datei | Status |
|---|---|---|
| Master-Governance definiert (Vorrangregeln, Autonomie, Freigabe, Datenschutz) | ag-master.md | ✅ |
| Core-Agent definiert (Einstieg, erlaubte Aufgaben, Routing, Basisfluss) | ag-core.md | ✅ |
| Identität und Leitprinzipien dokumentiert | ag-identity.md | ✅ |
| Capability-Register vollständig | capability-registry.md | ✅ |
| Datenklassifizierung vollständig (6 Klassen) | data-classification.md | ✅ |
| Module-Lifecycle definiert | module-lifecycle.md | ✅ |
| Routing-Spezifikation vollständig | routing-spec.md | ✅ |
| Audit-Vault-Mindestspezifikation | audit-vault-minimal-spec.md | ✅ |

---

## Kriterium 2: Tests bestanden

| Anforderung | Datei | Status |
|---|---|---|
| Smoke-Tests BS-01–BS-13 alle bestanden | basis-smoke-tests.md | ✅ |
| Core-Testcases TC-01–TC-05 alle bestanden | core-testcases.md | ✅ |
| Routing für alle Ampel-Zustände getestet | basis-smoke-tests.md | ✅ |
| Prompt-Injection-Test bestanden (BS-09) | basis-smoke-tests.md | ✅ |
| Unveränderlichkeits-Test bestanden (BS-11) | basis-smoke-tests.md | ✅ |
| Kurzfreigabe-Test bestanden (BS-12) | basis-smoke-tests.md | ✅ |
| Keine falschen Versprechen (BS-13) | basis-smoke-tests.md | ✅ |

---

## Kriterium 3: Routing konsistent

| Anforderung | Status |
|---|---|
| Alle 8 Module haben definierten Routing-Status | ✅ |
| Kein Modul ohne Routing-Eintrag | ✅ |
| Kein Silent-Redirect für activatable-Module | ✅ |
| Planned-Module haben sichere Alternative | ✅ |
| Blocked-Module haben responsibility_handoff-Output | ✅ |
| Hard-Block für EU AI Act Art. 5 definiert | ✅ |

---

## Kriterium 4: Dokumentationspflicht aktiv

| Anforderung | Status |
|---|---|
| Unveränderlichkeitsregel definiert (ag-master §10) | ✅ |
| 13 Pflichtfelder je Dokumentation definiert | ✅ |
| 6 Pflichtfelder je Nachtrag definiert | ✅ |
| Audit-Vault-Konzept beschrieben | ✅ |
| JSONL-Schema definiert | ✅ |
| Nachtragsprinzip (Append-only) definiert | ✅ |

---

## Kriterium 5: Datenschutz aktiv

| Anforderung | Status |
|---|---|
| 6 Datenklassen vollständig definiert | ✅ |
| Sonderkorridor-Regel definiert (ag-master §7b) | ✅ |
| Zweistufiges Freigabeformat aktiv (Kurz + Voll) | ✅ |
| VVT vollständig (VVT-01 bis VVT-10) | ✅ |
| Kein KI-Call ohne Datenklasse (Regel definiert) | ✅ |
| Credentials-Block definiert | ✅ |

---

## Kriterium 6: Keine kritischen offenen Befunde

| Anforderung | Status |
|---|---|
| Governance-Konsistenz-Check bestanden | ✅ (2026-06-23, v1.1) |
| UX-Check bestanden | ✅ (2026-06-23) |
| Finalisierungscheck bestanden | ✅ (2026-06-23) |
| Keine bekannten kritischen Widersprüche | ✅ |

---

## Kriterium 7: Auditpflicht aktiv

| Anforderung | Status |
|---|---|
| Auditpflichtige Ereignisse definiert | ✅ |
| Verantwortliche Rollen je Event definiert | ✅ |
| Audit-Stufen-Konzept beschrieben (Stufe 1–3) | ✅ |
| Nachtragspflicht definiert | ✅ |

---

## Nicht-Ziele des Core

Core gilt als fertig, auch wenn folgendes noch offen ist:

- AILIZA-Memory-Backend (geplant, nicht implementiert)
- ag-recherche (planned, Tests ausstehend)
- ag-buchhaltung (blocked, Voraussetzungen fehlen)
- ag-hr (blocked, AVV + DPIA fehlen)
- Modul-spezifische Vertiefungstests (nach Core-Freigabe)
- CRM, Marketing, Schulung (nicht im Core-Scope)

---

## Reifegradbewertung

Core-Reifegrad wird berechnet in: **core-gap-analysis** (separate Lieferung).

Basis: Prozentualer Erfüllungsgrad der 7 Kriterien oben × gewichtete Faktormatrix.

---

## Core-Freigabe-Entscheidung

Core gilt als freigegeben wenn:
- Alle 7 Kriterien: ✅
- Keine offenen kritischen Befunde (rot)
- Governance-Review abgeschlossen
- Tests dokumentiert und bestanden

**Aktueller Status: Core-Readiness erreicht (Stand: 2026-06-23)**
