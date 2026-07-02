# AILIZA – Konsolidierter Reparaturplan (freigabefähig)

**Basis:** Spec-Review (Bestandsaufnahme v1) × Code-Verifikationsbericht (F1–F21).
**Regel:** Ein Patch = ein Branch/Commit. Kein Patch ohne explizite Freigabe.
Nach jedem Patch: zugehöriges Akzeptanzkriterium grün, dann erst der nächste.

---

## A. Abgleich: Was der Code-Report an der Bestandsaufnahme ändert

| Spec-Risiko (v1) | Status nach Code-Prüfung |
|---|---|
| R1 Modell als Compliance-Instanz | **ENTWARNT** — deterministisch belegt (F1, F21) |
| R2 Prompt Injection / Output-Schema | **NICHT GEPRÜFT** — Prüfauftrag Punkt 6 fehlt im Report → V-1 unten |
| R3 Platzhalter-Mapping-Store | **VERSCHOBEN** — Server persistiert nicht (gut), aber Klartext-Map geht per HTTP-Response an den Browser (F19) → neues Risiko-Profil, P-J |
| R5 API-Struktur | Nicht berichtet → V-2 |
| R6 Human-Review-Ausgestaltung | Nicht berichtet → V-3 |
| R7 Risk-Taxonomie undefiniert | **BESTÄTIGT, schlimmer**: drei parallele Taxonomien, zwei aktive Governance-Pfade in /agent/run (F2/F3) |
| NEU | `avv_signed` totes Feld (F8) — kritisch |
| NEU | Selbstauskunft „Nicht produktionsreif" in 3 Kernmodulen (F4–F6) |
| NEU | Retention deckt Nutzdaten/Memory nicht ab (F18) |

---

## B. Vorab zu klärende Policy-Entscheidungen (nur du / die GmbH)

Diese vier Entscheidungen blockieren Patches — bitte je eine Zeile Antwort:

**E1 — Führender Governance-Pfad:** In `/agent/run` laufen zwei Systeme nacheinander
(`_governance_pre_check` mit `data_matrix.PolicyDecision` vs. `PolicyEngine.process_with_policy`).
Empfehlung: `data_matrix`-Pfad als führend (Enum, sauberer), `policy_engine.py` wird
Vorstufe oder entfällt. → Freigabe: ja/nein/anders?

**E2 — `avv_signed` blockierend machen:** Empfehlung: JA. Konsequenz, ehrlich benannt:
Da aktuell ALLE externen Provider `avv_signed=False` haben, darf nach dem Patch kein
externer Provider personenbezogene Daten verarbeiten, bis AVVs unterschrieben sind.
Für eure Phase („noch am Anfang", nicht in Betrieb) ist genau das der richtige Zustand —
Entwicklung läuft mit synthetischen Testdaten oder `local` weiter. → Freigabe: ja/nein?

**E3 — Fallback-Politik (deine offene Frage 4):** Empfehlung: Fallback nur innerhalb
freigegebener Provider (Profil-Check inkl. avv_signed); ist keiner verfügbar → blockieren
mit klarer Fehlermeldung, kein stiller Wechsel. → Freigabe: ja/nein?

**E4 — „Nicht produktionsreif"-Selbstauskunft (F4–F6):** Sind die Docstrings in
`policy_engine.py`, `retention.py`, `legal_hold.py` noch aktueller Stand oder veraltet?
Falls aktuell: Runtime-Warnung beim Start + Blocker-Liste. Falls veraltet: Status
aktualisieren mit Datum und Prüfer. → Deine Einschätzung?

---

## C. Patch-Reihenfolge (nach Freigabe, ein Commit pro Patch)

**Stufe 1 — klein, kritisch, ohne Abhängigkeiten**

| # | Patch | Akzeptanzkriterium |
|---|---|---|
| P-A | `check_provider_policy()`: `avv_signed` blockierend für alle Datenklassen außer explizit als unkritisch definierten (z. B. PUBLIC/SYNTHETIC) | Test: Provider mit `avv_signed=False` + Datenklasse PERSONAL/HR/FINANCE → Routing verweigert, Audit-Eintrag „provider_rejected: no_avv" |
| P-E | `telegram_gateway.py:394` auf `kill_switch.is_external_llm_enabled()` umstellen | Grep: kein direkter `os.getenv("AILIZA_EXTERNAL_LLM_ENABLED")` außerhalb des Kill-Switch-Moduls |
| P-G | `main.py:2812` u. ä.: Exception-Logging auf Typ + Hash statt `str(e)` im Request-Pfad | Test: Exception mit PII im Message-Text → Log enthält keinen Klartext |

**Stufe 2 — strukturell (braucht E1)**

| # | Patch | Akzeptanzkriterium |
|---|---|---|
| P-B | PolicyDecision-Konsolidierung: ein Enum, ein Governance-Pfad in `/agent/run`; RedactionLevel (7 Stufen) auf das Enum gemappt und Mapping dokumentiert | Grep: genau eine `PolicyDecision`-Definition; E2E-Test /agent/run durchläuft nur noch einen Pfad; alle bestehenden Tests grün |
| P-C | Status-Bereinigung F4–F6 gemäß E4 | Docstrings tragen Datum + Status; falls „nicht produktionsreif" bestätigt: Start-Warnung aktiv |

**Stufe 3 — Datenlebenszyklus**

| # | Patch | Akzeptanzkriterium |
|---|---|---|
| P-D | Retention auf Nutzdaten ausweiten: erst Prüfschritt `memory/sqlite_store.py` (welche Tabellen, welche Felder), dann `RETENTION_CONFIG` + Löschlauf für Chat/Memory | Test: Eintrag älter als Frist → Löschlauf entfernt ihn; Legal-Hold-Kollision hat definiertes, dokumentiertes Verhalten |
| P-J | Client-Map härten (F19): HTTPS erzwungen (HSTS), `reinsertion_map` nie in localStorage/sessionStorage, Speicher nach Reinsertion aktiv geleert, Response mit Map nie serverseitig geloggt (Middleware-Check) | Frontend-Review: kein Storage-API-Zugriff auf die Map; Log-Assertion: Response-Bodies des Redact-Endpoints erscheinen nicht in Logs |
| P-F | Testfälle kontextuelle Art.-9-Erkennung („Reha", „Kirchensteuer", „Betriebsrat", „Schwangerschaft", „Schwerbehinderung") | Testsuite enthält die Fälle; erwartetes Verhalten pro Fall dokumentiert (Block vs. Flag) |

---

## D. Offene Verifikationen (Lesen, kein Patch — vor Stufe 3 erledigen)

- **V-1 (aus Prüfauftrag Punkt 6, ungeprüft):** Wird Modell-Output gegen ein striktes
  Schema validiert? Kann Output irgendeine Aktion/ein Gate auslösen? Injection-Testkorpus
  vorhanden? → Falls nein: neuer Patch P-H (Schema-Validierung + „Output steuert nie Gates").
- **V-2:** Tatsächliche Request-Struktur der Provider-Adapter gegen die jeweilige API-Doku
  (der Spec-Fehler mit system-Message-Objekt — ist der im Code oder nur in der Spec?).
- **V-3:** Human-Review-Gate im Code: Was sieht der Prüfer, wie wird Zustimmung
  erfasst (Nutzer-ID + Zeitstempel im Audit?), gibt es einen Pfad, der HIGH-RISK ohne
  Gate abschließt?
- **V-4 (F13):** Was ist der `local`-Provider wirklich — Modell, Dummy, Echo? Wenn Dummy:
  in den Notes kennzeichnen, sonst suggeriert das Profil eine Sicherheit, die nicht existiert.
- **V-5 (F16, operativ):** Render-Deploy-Prozess dokumentieren: `autoDeploy: false`
  beibehalten (bewusster Release-Schritt) → dann Checkliste „Deploy im Dashboard triggern"
  ins README, damit das „Endpoint nicht live"-Problem nicht wieder als Bug erscheint.

---

## E. Nicht-Code-Spur (parallel, GmbH-Aufgaben)

1. AVV/DPA-Abschlüsse je Provider (Anthropic API zuerst, da geplanter Kern);
   bis dahin gilt durch P-A automatisch: keine personenbezogenen Daten extern.
2. Verzeichnis von Verarbeitungstätigkeiten (Art. 30) anlegen; DSFA-Bedarf prüfen,
   sobald reale Use-Cases (HR?) feststehen.
3. „Jurist-Agent": als wöchentliches Monitoring mit Ticket-Output ok — Freigabe von
   Änderungen bleibt bei einem Menschen; Abnahme im Audit-Trail dokumentieren.
4. Spec-Dokument korrigieren: „90 Tage DSGVO-Frist" streichen (zweckgebundene Fristen
   aus P-D übernehmen), Rollentrennung AILIZA/Modell im Prompt-Text nachziehen.

---

*Hinweis: DSGVO-/EU-AI-Act-orientierte Vorbereitung; ersetzt keine juristische Endprüfung. Ich bin eine KI, kein Anwalt.*
