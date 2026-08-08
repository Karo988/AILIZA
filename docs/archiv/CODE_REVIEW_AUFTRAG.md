# Prüfauftrag: AILIZA Code-Verifikation (Bestandsaufnahme, keine Änderungen)

Rolle: Senior Security/Compliance Code-Reviewer. Nur lesen und berichten.
Kein Code ändern, nichts pushen, nichts mergen, keine Env-Variablen anfassen.
Jede Aussage mit Datei + Zeilennummer belegen. Format pro Punkt:
BEFUND (belegt) / RISIKO / EMPFEHLUNG. Was nicht prüfbar ist, als
"NICHT PRÜFBAR" markieren statt zu raten.

## P0 – Governance-Verifikation (wichtigste Fragen)

1. **Wer erzeugt die Compliance-Entscheidungen?**
   Suche alle Stellen, an denen `policy_decision`, `human_review_required`,
   `risk_level` oder Audit-Einträge gesetzt werden. Beleg: Werden diese
   Werte ausschließlich deterministisch in AILIZA-Code berechnet, oder
   werden sie (auch teilweise) aus der Modell-Antwort übernommen?
   Grep-Startpunkte: `human_review`, `audit`, `compliance_check`,
   `json.loads` auf Provider-Responses.

2. **Greift die Redaction vor JEDEM externen Call?**
   Liste alle Callsites, die einen Provider aufrufen (alles, was
   `providers/orchestrator.py` oder HTTP-Clients nutzt). Für jede Callsite:
   Läuft der Input nachweislich durch `redaction_v2`? Gibt es Bypass-Pfade
   (Debug-Endpoints, Health-Checks mit Echtdaten, Retry-Logik, die
   Rohinput cached)?

3. **Fehlerpfade und Logging:**
   Prüfe alle `except`-Blöcke und Logger-Aufrufe entlang des Request-Pfads:
   Wird irgendwo ungeschwärzter Input, das Platzhalter-Mapping oder ein
   API-Key geloggt (auch in Tracebacks)? Prüfe auch die Render-Logs-Konfig.

4. **Provider-Orchestrator:**
   a) Gibt es pro Provider ein Compliance-Profil (Region, DPA-Status,
      erlaubte Datenklassen), das vor dem Routing geprüft wird – oder
      routet die Kette rein nach Verfügbarkeit?
   b) Was ist `local` konkret – echtes lokales Modell, Dummy, oder Echo?
   c) Greift `AILIZA_EXTERNAL_LLM_ENABLED` wirklich vor jedem externen
      Call (zentrale Stelle) oder nur an einzelnen Stellen?
   d) Wird bei Fallback der Provider-Wechsel im Audit protokolliert?

5. **Platzhalter-Mapping-Store:**
   Wo wird die Zuordnung [Name_1]→Klarname gespeichert (Datei, DB, Memory)?
   Verschlüsselt? Pro Tenant getrennt (`AILIZA_DEFAULT_TENANT_ID`)?
   Welche Löschlogik greift (`retention.py`)? Kollidiert `legal_hold.py`
   mit Löschpflichten, und ist diese Kollision behandelt?

## P1 – Sicherheit

6. **Prompt Injection:** Wird Modell-Output schema-validiert (striktes
   JSON-Schema, Ablehnung bei Abweichung)? Kann Modell-Output irgendeine
   Aktion, ein Gate oder einen Statuswechsel direkt auslösen?
   Wird Nutzerinhalt im Prompt klar als Daten abgegrenzt (Delimiter)?

7. **Secrets:** Wie werden API-Keys geladen (Env, Datei)? Liegen Keys oder
   Beispiel-Secrets im Repo (`git log`/Dateien prüfen: `.env`, `render.yaml`,
   Tests)? Erkennt die Redaction gängige Token-Formate (sk-, ghp_, JWT,
   private Keys) und ENTFERNT sie (nicht maskiert)?

8. **Art.-9-Erkennung:** Extrahiere die Kategorien aus
   `policies/pii_taxonomy.py` und `compliance/dsgvo.py`. Decken sie alle
   Art.-9-Kategorien ab? Gibt es Tests mit kontextuellen Fällen
   ("Reha", "Kirchensteuer", "Betriebsrat")? Blockiert der Treffer den
   API-Call deterministisch (Beleg: Codepfad)?

## P2 – Konsistenz

9. **Enums/Taxonomie:** Ist `PolicyDecision` genau einmal definiert und
   überall importiert? Wie viele Risk-Level gibt es real im Code, und
   sind Kriterien pro Stufe dokumentiert/getestet?

10. **EU-AI-Act-Modul:** Was prüft `compliance/eu_ai_act.py` konkret –
    Use-Case-Klassifikation (HR/Kredit/Versicherung → Hochrisiko-Gate)?
    Wird das Ergebnis mit dem Human-Review-Gate verdrahtet?

11. **Tests:** Welche der obigen Punkte sind durch Tests abgedeckt?
    Liste fehlende Testfälle.

## Ergebnisformat

1. Tabelle: Befund-ID, Datei:Zeile, Status (OK / Risiko / kritisch / nicht prüfbar)
2. Top-5-Risiken priorisiert
3. Vorschlagsliste für Patches – OHNE sie umzusetzen; Umsetzung erst
   nach expliziter Freigabe, ein Patch pro Branch/Commit.
