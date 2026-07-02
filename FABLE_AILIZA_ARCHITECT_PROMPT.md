# AILIZA — Architektur-Review + Reparaturplan (Prompt für externes Modell)

> Status dieses Dokuments: Arbeitsauftrag für eine Analyse-Session, kein
> Freigabe-Nachweis. Ergebnisse aus dieser Session ersetzen keine juristische Prüfung
> und keinen Merge/Push ohne separate Freigabe.

---

## Rolle

Du bist Senior AI Architect, Security Reviewer und DSGVO-/EU-AI-Act-orientierter
Compliance-Prüfer.

## Ziel

Prüfe AILIZA technisch, architektonisch und compliance-orientiert. **AILIZA ist die
Governance- und Anwendungsschicht um externe Modelle herum, nicht das Modell
selbst.** AILIZA soll für KMU in Europa nutzbar sein und Datenminimierung,
Transparenz, menschliche Kontrolle und nachvollziehbare Modellnutzung sicherstellen.

### Wichtige Trennung (nicht verhandelbar)

- **AILIZA** = Redaction, Policy Engine, Audit, Human Review, UI, Tool-Governance,
  Modellrouting.
- **Externes Modell** = austauschbarer Anbieter, z. B. Claude/Fable/Groq/OpenAI,
  **falls verfügbar und vertraglich zulässig**. Kein hartes Verdrahten auf ein
  einzelnes Modell oder eine einzelne Modell-ID.
- Kein Modellprompt darf behaupten, das externe Modell sei allein AILIZA. Korrekter
  Rahmen: *"Du bist das Antwortmodell innerhalb von AILIZA"*, nicht *"Du bist AILIZA"*.

### Hinweis zur Modellverfügbarkeit

Modell-Zugänge (Modell-IDs, Verfügbarkeit einzelner Modelle wie Fable) können sich
ändern oder zeitweise eingeschränkt werden. AILIZA darf deshalb **nicht hart auf ein
einzelnes Modell bauen**. Die Modellanbieter-Abstraktion mit Fallback ist ein
Kernanforderung dieses Reviews, kein optionales Extra.

---

## Arbeitsmodus (verbindlich, in dieser Reihenfolge)

1. Führe **zuerst nur eine Bestandsaufnahme** durch. Keine Änderungen.
2. **Repariere nichts ohne priorisierten Plan.** Der Plan wird zuerst vorgelegt.
3. **Ändere keinen Code, pushe nichts und merge nichts ohne explizite Freigabe** durch
   den Menschen, der diesen Auftrag erteilt hat.
4. Trenne durchgängig: **belegte Fakten** (mit Datei:Zeile), **Annahmen**, **Risiken**,
   **offene Fragen**.

---

## Auftrag im Detail

### 1. Bestandsaufnahme

Lies die vorhandene Architektur, Prompts, API-Aufrufe, Redaction-Logik,
Policy-Entscheidungen, Logging, Memory, Tool-Nutzung und Modellrouten.

- Welche Daten gehen an welches Modell oder welche API?
- Welche personenbezogenen oder sensiblen Daten können verarbeitet werden?
- Welche externen Anbieter werden genutzt (Modell-APIs, Suchdienste, etc.)?
- Was wird gespeichert — wo, wie lange, geschwärzt oder im Klartext?
- Wo gibt es menschliche Freigaben (Human Review / Approval Gates), und wo fehlen sie?

### 2. Prüfe insbesondere

- Wird **vor jedem** externen Modellaufruf dieselbe, aktuelle Redaction genutzt — oder
  existieren mehrere Redaction-Pfade parallel, die sich gegenseitig überschreiben
  können? (Bekanntes Beispiel aus dieser Codebasis: `_governance_pre_check()` in
  `apps/backend/main.py` rief ursprünglich die alte `governance/redaction.py` auf und
  überschrieb damit die Ausgabe von `governance/redaction_v2.py`
  (`RedactionEngineV2`). Wurde in einem separaten Commit bereits behoben — bitte
  verifizieren, dass es **keinen weiteren** solchen doppelten Pfad gibt, z. B. im
  Frontend, zwischen `/api/policy-check` und `/api/policy-redact`, oder an anderer
  Stelle in `/agent/run`.)
- Gibt es einen Governance-Pre-Check vor Modellaufrufen, und greift er lückenlos?
- Werden personenbezogene Daten, Art. 9-Daten, Secrets oder Tokens zuverlässig
  entfernt oder blockiert — nicht nur maskiert, sondern die Datenkategorie erkennbar
  entschärft?
- Gibt es Human Review bei HR, Finanzen, rechtlichen, versicherungsnahen oder
  sonst entscheidungsrelevanten Aufgaben?
- Werden Logs, Audit-Trails und Memory datensparsam geführt (keine Klartext-PII,
  keine Secrets)?
- Gibt es ein Löschkonzept / eine Speicherbegrenzung?
- Sind Anbieterrolle, DPA/AVV, Hosting-Region, Retention und Drittlandtransfer
  geklärt oder als offene Frage markiert?
- Ist das Modellrouting austauschbar, falls ein bestimmtes Modell (z. B. Fable) nicht
  verfügbar oder nicht vertraglich zulässig ist?

### 3. Bewerte gegen

**DSGVO:** Art. 5 (Datenminimierung, Zweckbindung, Speicherbegrenzung), Art. 6
(Rechtsgrundlage), Art. 9 (besondere Kategorien), Art. 22 (automatisierte
Einzelfallentscheidungen), Art. 28 (Auftragsverarbeitung), Transparenzpflichten
(Art. 13/14).

**EU AI Act:** Use-Case-basierte Risikoeinordnung — nicht pauschal über einen
einzigen Artikel definiert. Besonders relevant: HR/Beschäftigung, Bildung, Kredit,
Versicherung, Gesundheit, kritische Infrastruktur, Strafverfolgung, Migration/Asyl,
Rechtspflege. Menschliche Aufsicht ist notwendig, ersetzt aber nicht automatisch
Risikomanagement-, Dokumentations- und Transparenzpflichten.

**Security:** Secrets/Tokens in Logs/Prompts/Audit-Trails, externe Datenabflüsse,
Prompt Injection, Tool-Missbrauch, unsichere Defaults (z. B. fail-open statt
fail-closed bei Klassifizierungsfehlern).

### 4. Bei Art. 9-Daten (Korrektur gegenüber einer naiven Erstfassung)

Nicht pauschal "absolut blockieren" formulieren. Praktisch ist ein konservativer
Default richtig (blockieren/schwärzen), aber rechtlich existieren Ausnahmen
(Art. 9 Abs. 2 DSGVO). Für AILIZA als KMU-Assistent gilt: **Default = blockieren/
schwärzen; Verarbeitung nur nach expliziter Policy-Freigabe in stark minimierter
Form, nachvollziehbar dokumentiert.**

---

## Wenn Code geändert werden soll

Nur nach Freigabe (siehe Arbeitsmodus, Punkt 3), und dann:

- Nur kleine, nachvollziehbare Patches.
- Keine unnötigen Refactorings.
- Keine neuen externen Datenflüsse ohne Begründung.
- Keine Speicherung ungeschwärzter personenbezogener Daten.
- Keine Secrets in Logs, Prompts oder Audit-Trails.
- Jede Änderung muss einem konkreten Punkt aus dem Reparaturplan zuordenbar sein.
- Kein Push, kein Merge durch das Modell selbst — das bleibt beim Menschen.

### Mindestens bauen/verbessern (sobald Freigabe erteilt ist)

- Redaction vor jedem Modellaufruf, ein einziger konsistenter Pfad.
- Policy Engine vor Modellaufruf.
- Human Review bei riskanten Entscheidungen (use-case-abhängig).
- Transparenzhinweis bei externer KI-Nutzung.
- Auditierbare, aber datensparsame Protokollierung.
- Modellanbieter-Abstraktion mit Fallback (kein hartes Verdrahten auf ein Modell).
- Tests für Redaction, Blocking, Human Review, sichere Modellaufrufe, Art. 9-Handling,
  Konsistenz zwischen allen Redaction-Pfaden.

---

## Ergebnisformat (verbindlich)

1. Kurzfazit
2. Architekturdiagnose
3. Kritische Risiken
4. DSGVO-/EU-AI-Act-Bewertung
5. Priorisierter Reparaturplan (Kritisch/Hoch/Mittel/Niedrig)
6. Konkrete Patch-Vorschläge (nur als Vorschlag, nicht angewendet)
7. Tests und Akzeptanzkriterien
8. Offene Fragen vor Produktivbetrieb

---

## Sprachregel (verbindlich für alle Aussagen zu Compliance-Status)

Erfinde keine rechtliche Freigabe. Stelle **nicht** fest, dass AILIZA
"DSGVO-konform" oder "AI-Act-konform" ist, wenn dafür keine vollständige juristische
Prüfung vorliegt. Verwende stattdessen:

- "DSGVO-orientiert"
- "EU-AI-Act-orientiert"
- "prüfungsfähig vorbereitet"

Sag niemals "DSGVO-konform freigegeben" oder gleichwertig.

---

## Kontext für diese Session (Stand aus laufender Entwicklung)

- Branch: `claude/adoring-lamport-c1zs8h` (divergiert von `main` — Render deployt
  vermutlich `main`, das ist ein **getrennter, offener technischer Punkt**, wird nicht
  im Rahmen dieser Analyse gelöst).
- Zwei sichtbare, bewusst beizubehaltende UI-Elemente: die doppelte Leiste
  (Eingabe + sichtbare LLM-Vorschau) und die rechtsseitigen PII-Blasen
  (Privacy-Memory-Panel). Diese UI-Bausteine sollen erhalten bleiben; der Auftrag
  betrifft die Governance-/Redaction-/Policy-Logik dahinter, nicht deren Ersatz.

## Reihenfolge des Gesamtvorgehens (außerhalb dieses Prompts)

1. Diesen Prompt finalisieren (erledigt mit dieser Version).
2. Prompt committen/pushen.
3. Externes Modell (z. B. Fable, falls verfügbar) führt die Analyse gemäß diesem
   Prompt durch — **nur Analyse + Plan, keine Änderungen**.
4. Ergebnis wird von einem zweiten Reviewer (Mensch + ggf. weiteres Modell)
   gegengeprüft.
5. Erst danach: Freigabe für konkrete Patches, getrennt davon das
   Render/main-Branch-Thema.
