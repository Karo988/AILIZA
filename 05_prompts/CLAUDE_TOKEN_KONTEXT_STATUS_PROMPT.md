# Claude Code — Modell-, Kontext- und Nutzungsstatus

Ergaenzt `CLAUDE.md`, Abschnitt "Model-Strategie fuer Claude Code Sessions".
Gilt fuer alle Claude-Code-Sitzungen an AILIZA. Inhalte hier sind gegen die
tatsaechliche Claude-Code-CLI geprueft, nicht angenommen.

## Modellwahl

- Nenne in jeder Antwort kurz das empfohlene Modell, auch ohne Wechsel
  (Standard: Sonnet 5; Opus 5 fuer grosse Architektur-, Compliance- oder
  Sicherheitsentscheidungen; Haiku nur fuer triviale Aufgaben — siehe
  `CLAUDE.md`).
- Das Modell wird von der Nutzerin manuell umgestellt (`/model`). Claude
  behauptet keinen selbst ausgeloesten Wechsel.

## Token- und Kontextangaben — verifizierte Faehigkeiten

- `/context` zeigt die aktuelle Kontextfenster-Auslastung dieser Sitzung.
- `/usage` zeigt Kosten- und Token-Verbrauch inklusive Prompt-Cache-Anteil.
- Beide muessen von der Nutzerin manuell aufgerufen werden. Es gibt **keine**
  dauerhafte, automatisch sichtbare Anzeige dafuer in Claude Code.
- Rate-Limit-Reset-Zeiten (5-Stunden-Fenster, woechentliches Limit) sind
  **nicht** ueber die Claude-Code-CLI abrufbar. Diese Information kommt
  ausschliesslich aus der claude.ai-Kontooberflaeche, nicht aus einem Prompt
  oder einer CLI-Ausgabe.
- Claude gibt keine erfundenen oder geschaetzten Token-/Reset-Werte aus. Ist
  ein Wert nicht ueber `/context` oder `/usage` tatsaechlich sichtbar, gilt
  exakt `nicht verfuegbar`.

## Wann ein Nutzungsstatus erwaehnt wird

- Auf ausdrueckliche Aufforderung.
- Am Ende eines laengeren Arbeitspakets, zusammen mit der
  `AILIZA-STATUSKAPSEL`.
- Nicht nach jeder kurzen Chat-Nachricht.

## Ausdruecklich nicht versprochen

Keine Zusage einer persistenten Status-/Kontextanzeige ausserhalb von
`/context` und `/usage`, solange das nicht tatsaechlich technisch bestaetigt
wurde (z. B. ueber eine gepruefte Statuszeilen-Konfiguration).
