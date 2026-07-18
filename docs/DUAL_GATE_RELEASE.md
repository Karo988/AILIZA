# AILIZA — Dual-Gate v3: Release-/Betriebsprotokoll

Stand: 18.07.2026 · Repo: `Karo988/AILIZA` · Branch: `main`

---

## 1. Stand nach Dual-Gate-Roadmap

| PR/Issue | Titel | Status |
|---|---|---|
| #32 | Dual-Gate PR-1: Refusal-/Invalid-Netz am Provider-Chokepoint | ✅ gemergt |
| #33 | Dual-Gate PR-2: Stufe-1-PII-Integrität + Pfad-B-Härtung | ✅ gemergt |
| #34 | Dual-Gate PR-3: Spiegel-Linting + asymmetrische Schwellen + Freigabe-Cockpit | ✅ gemergt |
| #35 | Dual-Gate PR-3b: Verdrahtung Spiegel-Linting in echten main.py-Flow | ✅ gemergt |
| #37 | Dual-Gate PR-4: Stufe-3-Prüfer (flag-only) + Budget-Feinschliff + Statusphasen-Hook + Replay-Korpus | ✅ gemergt |
| #38 | Dual-Gate PR-5: Groq/OpenAI response_format-Live-Verdrahtung | ✅ gemergt |
| #36 | Issue: bekannter Baseline-Testfehler `test_propose_endpoint_requires_auth` | ✅ geschlossen (Fix in PR #39) |
| #39 | Fix: `/skills/propose` crasht ohne Auth statt 401 (schließt #36) | ✅ gemergt |
| #40 | Audit: `TokenData \| None`-Endpunkte auf versehentliche Pflicht-Auth-Bugs | ✅ auditiert, keine weitere Fundstelle, geschlossen |

---

## 2. Architekturüberblick

**Vorher:** Jeder Provider-Adapter gab nur rohen Text zurück. Eine Provider-Ablehnung ("Textwand") oder ein kaputtes Antwortformat konnte unverändert bis zum Nutzer durchschlagen. Es gab keine zweite, deterministische Instanz, die die Egress-Seite (die Antwort) genauso prüft wie die Ingress-Seite (die Anfrage).

**Jetzt:** Ein einziger Chokepoint (`orchestrator.py:346`, `provider.generate_with_meta()`) läuft für jeden Provider — auch künftige — durch `GatedLLMClient`. Kernprinzip bleibt durchgehend gewahrt: **Ablehnung ist deterministisch (Policy-Code), Generierung ist probabilistisch (LLM).** Der LLM ist nirgends alleiniger Richter über eine Sicherheitsentscheidung.

```
Nutzeranfrage
     │
     ▼
Ingress-Redaction (bestehend, unverändert)
     │
     ▼
GatedLLMClient.generate()
     │
     ├─ Pfad-Klassifikation: A (natives Schema, Anthropic) / B (alle anderen,
     │  auch unbekannte künftige Provider → fail-safe immer B)
     │
     ├─ Generate-Versuch (Slot 1)
     │     │
     │     ├─ Refusal/leer? → Repair-Versuch (Slot 2, ohne Rohtext im Fehler)
     │     ├─ JSON-Modus (Pfad B, falls Provider-Capability): response_format
     │     │  nur beim 1. Versuch, nie erneut nach Fehlschlag
     │     └─ Format kaputt? → recover_json → Few-Shot-Retry → Klartext-
     │        Vertrag (Degradations-Leiter, NIE Block wegen Format)
     │
     ├─ Egress-Enforcement (nur NUTZER_AUSGABE + ingress_source vorhanden):
     │     Spiegel-Linting: dieselben Redaction-Muster laufen getrennt auf
     │     Ingress UND Egress. Generator-eigene risk_flags sind nur tertiär.
     │     └─ RED/BLACK-Signal-Uneinigkeit? → optionaler Stufe-3-Prüfer
     │        (Slot 3, flag-only, überschreibt NIE die Policy-Entscheidung)
     │
     └─ Ergebnis: DELIVER / DELIVER_AFTER_CONFIRM / BLOCK_WITH_ALTERNATIVE
        (genau 3 Endzustände — eine rohe Ablehnung beim Nutzer ist per
        Definition ein Bug, kein 4. Zustand)
```

---

## 3. Enforce-/Shadow-Status je Komponente

Quelle: `apps/backend/governance/mirror_lint.py`, `_RULE_MODE`.

| Modus | Kategorien | Bedeutung |
|---|---|---|
| **enforce** (blockt aktiv) | `iban`, `bic`, `card`, `card_cvv`, `card_expiry`, `credential`, `secret_openai`, `secret_groq`, `secret_jwt`, `secret_bearer`, `official_id`, `child_field`, `reference` | Zertifizierungskritisch — blockt bereits bei einem einzelnen Signal (Ingress ODER Egress). Rollout: sofort scharf, da die PR-1-Degradations-Leiter (Klartext-Vertrag statt Hartblock bei Formatfehlern) das Worst-Case-Risiko begrenzt. |
| **shadow** (erkennt, blockt nie) | `name*` (7 Varianten), `email`, `birthdate`, `server_path`, `ip_address`, `gps_coords`, `device_id`, `financial_detail`, `financial_balance`, `financial_keyword`, `address*` (3 Varianten), `phone` | Komfort-/Wording-Kategorien — brauchen laut Spec beide Signale UND mindestens 1 Woche Beobachtung, bevor sie auf `enforce` gehoben werden. **Aktuell: noch keine dieser Kategorien wurde auf `enforce` umgestellt.** |
| **unbekannt/neu** | alles nicht Gelistete | Fail-closed-Default: automatisch `shadow`, nie `enforce`. Ein neues Redaction-Muster kann also nie ungeprüft live blocken. |

---

## 4. Tests und Baseline

- **Dual-Gate-Tests gesamt:** 49 (PR-1: 14, PR-2: 7, PR-3: 7, PR-3b: 8, PR-4: 7, PR-5: 6), alle grün.
- **Gesamte Backend-Suite (`tests/`):** 832/832 grün, **0 bekannte Fehler** (vor Issue-#36-Fix: 1 bekannter Fehler über mehrere PRs stabil).
- **Kein neuer Dependency** über alle 5 Dual-Gate-PRs hinweg (geprüft gegen `requirements-core.txt`-Baseline, T7 in PR-2).
- **Keine echten API-Calls in Tests** — durchgehend Fake-Provider.
- **Kein Frontend geändert** in der gesamten Dual-Gate-Serie.

---

## 5. Datenschutz-/Audit-Grundsätze

- Governance-Kette unverändert intakt: Kill-Switch → Data Governance → Policy-Gateway → Redaction → Provider-Orchestrator. Dual-Gate sitzt zusätzlich *innerhalb* des Provider-Orchestrator-Schritts, ersetzt keine bestehende Stufe.
- **Gate-Diagnosekapsel** (`GateDiagnostic`) enthält ausschließlich Status-Codes (`outcome`, `zweck`, `attempts`, `grund`, `pruefer_flag` etc.) — nie Prompt-Inhalte, Antworten oder Nutzerdaten. Strukturell durch Tests abgesichert (`test_gate_diagnostic_contains_only_codes_no_prompt_or_content` u.a.).
- **Statusphasen-Events** (`on_phase`-Hook, PR-4) sind reine Codes (`GENERATE`/`REPAIR`/`PRUEFER`/`DELIVER`/`BLOCK`), nie Inhalte.
- **Stufe-3-Prüfer** ist strukturell an das Prinzip "Ablehnung deterministisch, Generierung probabilistisch" gebunden: er liefert nur ein Flag (`CONFIRMED`/`UNCLEAR`/`PRUEFER_ERROR`), das nie in die Blocking-Entscheidung selbst einfließt.

---

## 6. Offene Betreiberentscheidungen

### 6.1 Shadow-Auswertung — ⚠️ NOCH UNGELÖST, keine bestehende Funktion

Die Shadow-Kategorien für personenbezogene Standarddaten wie Name, Adresse, E-Mail und Telefonnummer sind technisch als beobachtende Regeln vorhanden (`rule_mode() == "shadow"`, `mirror_lint.py`). Das ist **kein** Logging- oder Auswertungsmechanismus — Findings werden zur Laufzeit erzeugt und zurückgegeben, aber nirgends gesammelt oder persistiert. Es fehlt ein auswertbarer, datensparsamer Shadow-Logging-Mechanismus, der Trefferzahlen, mögliche False Positives/False Negatives und spätere Enforce-Freigaben nachvollziehbar dokumentiert.

Ohne diesen Mechanismus gibt es keine belastbare Datengrundlage für den Übergang von `shadow` zu `enforce`. Karo muss explizit entscheiden:

1. **Shadow-Logging bauen:** datensparsame Auswertung mit Regel-ID, Modus, Endzustand, Hash/Codes und Trefferzählung, aber ohne Rohinhalte.
2. **Shadow-Regeln dauerhaft beobachtend lassen:** kein Enforce-Übergang für diese Kategorien.
3. **Enforce ohne eigene Shadow-Datengrundlage freigeben:** fachlich möglich, aber governance-schwächer und dokumentationspflichtig.

Empfehlung: Option 1, als separater Mini-PR. Sonst bleibt das Freigabe-Cockpit aus PR-3 strukturell vorbereitet, aber nicht wirklich entscheidungsfähig.

### 6.2 Weitere kleinere Restrisiken (informativ, keine akute Entscheidung nötig)

| Risiko | Einordnung |
|---|---|
| Pfad-B-JSON-Härtung nur für Groq/OpenAI verdrahtet, nicht OpenRouter | Klein — OpenRouter ist Passthrough, Degradations-Leiter greift trotzdem (kein Block) |
| Stufe-3-Prüfer nutzt einfaches Ja/Nein-Textmuster, kein ausgebautes Prompt-Design | Bewusst klein gehalten (PR-4-Scope-Grenze), funktioniert als flag-only-Signal |
| `on_phase`-Hook existiert, aber kein Frontend nutzt ihn | Bewusst (PR-4-Scope-Grenze: Infrastruktur ohne UI-Aufblähung) |
| Debug-Provider-Test (`/api/debug/provider-test`) ruft `provider.generate()` direkt am Gate vorbei | Akzeptiert — Route existiert nachweislich nicht in Produktion (Test: `test_provider_debug_endpoint_not_registered_in_production`) |

---

## 7. Empfohlene nächste Maßnahmen

1. **Entscheidung zu 6.1 treffen** (Shadow-Logging ja/nein/wann).
2. Falls ja: kleiner, eng geschnittener Mini-PR für datensparsames Shadow-Logging (Regel-ID + Modus + Endzustand + Zähler, keine Rohinhalte) — analog zum bisherigen PR-Zuschnitt dieser Serie.
3. Kein weiterer Dual-Gate-Umbau ohne neuen Anlass — der Kern ist fertig und getestet.

---

*Erstellt von Claude Code. Modell-Empfehlung: Sonnet 5 (Dokumentation/Betriebsabschluss).*
