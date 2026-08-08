# AILIZA – Freigabe Stufe 1 (verbindlich)

**Freigegeben durch:** Betreiber (Amun Best of Orient GmbH), Datum: 2026-07-02
Umsetzung: ein Patch = ein Branch/Commit, Reihenfolge wie unten.
Kein Merge/Deploy in eine produktive Umgebung ohne neue, separate Freigabe.

---

## Bestätigte Entscheidungen

- **E1: JA** — `governance/data_matrix.PolicyDecision` ist der führende Pfad.
  `policy_engine.py` wird Vorstufe oder entfällt (P-B, Stufe 2).
- **E2: JA, mit Testmodus-Ausnahme** — Spezifikation unten in P-A.
- **E3: JA** — Fallback nur innerhalb freigegebener Provider; bei Wechsel wird
  Anbieter + Modell in der Antwort sichtbar gemacht und im Audit protokolliert;
  kein verfügbarer Provider → Block mit klarer Fehlermeldung.
- **E4: Docstrings sind AKTUELL** („Nicht produktionsreif" stimmt noch) →
  P-C wird: Runtime-Warnung beim Start solange Status besteht + Blocker-Liste
  pro Modul (was fehlt zur Reife), Status mit Datum versehen.

---

## P-A — `avv_signed` blockierend, mit Testmodus-Ausnahme (FREIGEGEBEN)

**Regel:** Provider mit `avv_signed=False` werden blockiert, AUSSER alle drei
Bedingungen gelten gleichzeitig:
1. `test_mode == true` (Definition unten), UND
2. die klassifizierte Datenklasse ist ausschließlich PUBLIC, SYNTHETIC oder DEMO, UND
3. die Klassifikations-Engines (Redaction/PII/Art.-9) haben KEINE personen-
   bezogenen, sensiblen oder vertraulichen Daten erkannt.

**Härtung 1 — test_mode ist serverseitig:**
- `test_mode` kommt ausschließlich aus Server-Konfiguration
  (Env `AILIZA_TEST_MODE` und/oder DB-Flag), NIEMALS aus Request-Parametern,
  Headern oder Client-Payload. Grep-Akzeptanz: kein Request-Feld setzt test_mode.
- Startup-Guard: Ist `AILIZA_TEST_MODE=true` UND die Umgebung als Produktion
  markiert (z. B. `AILIZA_ENV=production` / Render-Prod-Service), verweigert
  die Anwendung den Start mit eindeutiger Fehlermeldung. (Setzt Bedingung
  „Testmodus nie in Produktion" technisch durch.)

**Härtung 2 — Klassifikation schlägt Etikett:**
- Auch im Testmodus laufen Redaction + Art.-9-Erkennung vollständig.
- Erkennt die Engine PERSONAL/HR/FINANCE/HEALTH/LEGAL o. ä. → Block, auch
  wenn der Aufrufer den Inhalt als Test deklariert.

**Transparenz:** Jede Antwort im Testmodus trägt sichtbar Provider + Modell +
Hinweis „Testmodus / nicht produktiv".

**Audit:** Jeder Modellaufruf protokolliert `test_mode`, `provider`, `model`,
bei Nutzung der Ausnahme zusätzlich `no_avv_test_exception=true`.

**Akzeptanztests (alle müssen grün sein):**
| Fall | Erwartung |
|---|---|
| avv_signed=False + PERSONAL | blockiert |
| avv_signed=False + HR | blockiert |
| avv_signed=False + SYNTHETIC + test_mode=true | erlaubt, Antwort trägt Testmodus-Hinweis |
| avv_signed=False + SYNTHETIC + test_mode=false | blockiert |
| avv_signed=False + SYNTHETIC + test_mode=true, aber PII im Text erkannt | blockiert (Härtung 2) |
| test_mode=true per Request-Parameter gesendet | wirkungslos (Härtung 1) |
| AILIZA_TEST_MODE=true + AILIZA_ENV=production | Anwendung startet nicht |
| Audit-Eintrag | enthält test_mode, provider, model, ggf. no_avv_test_exception |

---

## P-E — Kill-Switch zentralisieren (FREIGEGEBEN)

`telegram_gateway.py:394` auf `kill_switch.is_external_llm_enabled()` umstellen.
Akzeptanz: kein direkter `os.getenv("AILIZA_EXTERNAL_LLM_ENABLED")` außerhalb
des Kill-Switch-Moduls (Grep-Check).

## P-G — Exception-Logging PII-frei (FREIGEGEBEN)

`main.py:2812` und vergleichbare Stellen im Request-Pfad: Log nur
Exception-Typ + Korrelations-ID/Hash, nicht `str(e)` ungefiltert.
Akzeptanz: Test mit PII-haltiger Exception-Message → Log enthält keinen Klartext.

## E3-Zusatzpatch (klein, FREIGEGEBEN): Fallback-Transparenz

Bei Provider-Wechsel durch Failover: genutzter Provider + Modell in
Response-Metadaten UND Audit-Eintrag (`failover_from`, `failover_to`).
Akzeptanz: simulierter Ausfall des ersten Providers → Antwort und Audit
zeigen den tatsächlich genutzten Anbieter; kein stiller Wechsel.

---

## Neue Verifikation V-6 — Geolocation-Abfrage im Frontend (NUR LESEN)

Symptom: Beim Öffnen erscheint teils eine Browser-Standortabfrage.
Auftrag: Frontend nach `navigator.geolocation`, `getCurrentPosition`,
`watchPosition` und Permission-Requests durchsuchen (auch eingebundene
Third-Party-Skripte/Widgets prüfen). Bericht: Datei:Zeile, Zweck (falls
erkennbar), ob Standortdaten irgendwohin gesendet werden.
Einordnung: Ohne dokumentierten Zweck + Einwilligung gehört der Aufruf
entfernt — Standortdaten sind personenbezogen und hier ohne erkennbaren Nutzen.
KEIN Fix ohne Freigabe; erst Befund.

## Weiterhin offen (vor Stufe 3)

V-1 Output-Schema/Injection, V-2 Provider-Request-Struktur, V-3 Human-Review-
Gate im Code, V-4 `local`-Provider (Modell/Dummy?), V-5 Deploy-Prozess-Doku.

---

## Reihenfolge für die Code-Session

1. P-A (inkl. Härtung 1+2, alle Akzeptanztests)
2. P-E
3. P-G
4. E3-Zusatzpatch
5. V-6 Befundbericht (kein Fix)
Danach: Ergebnisbericht zurück, dann Freigabe Stufe 2 (P-B, P-C).
