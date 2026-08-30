# Codex — Modell-, Kontext- und Nutzungsstatus

Ergaenzt `AGENTS.md`, Abschnitt "Modell und Kontext". Gilt fuer alle
Codex-Sitzungen an AILIZA.

## Modellwahl

- Empfehle das kleinste Modell und die niedrigste Reasoning-Stufe, die fuer
  die Aufgabe ausreicht. Einfache, iterative Aenderungen brauchen kein
  starkes Modell; grosse Architektur-, Compliance- oder
  Sicherheitsentscheidungen rechtfertigen ein staerkeres.
- Nenne die Empfehlung kurz in jeder Antwort, auch wenn sie unveraendert
  bleibt.
- Behaupte niemals einen tatsaechlich erfolgten Modellwechsel, wenn die
  laufende Codex-Umgebung das nicht selbst bestaetigt. Ein Wechsel wird vom
  Menschen ausgeloest, nicht von Codex vorgetaeuscht.

## Token- und Kontextangaben

- Gib Token-, Kontextfenster-, Konto- oder Reset-Werte nur aus, wenn sie aus
  einer tatsaechlich verfuegbaren, messbaren Quelle stammen (z. B. einer
  Oberflaechenanzeige der Codex-Umgebung selbst).
- Ist ein Wert nicht messbar oder unsicher, schreibe exakt `nicht verfuegbar`.
  Keine Schaetzung, keine Naeherung, kein Raten.
- Rate-Limit-Reset-Zeiten sind Konto-/Abrechnungsinformationen des Anbieters.
  Ohne eine echte, in der Umgebung sichtbare Anzeige dafuer gilt ebenfalls
  `nicht verfuegbar` — nicht aus dem Kontextfenster-Verbrauch ableiten oder
  schaetzen.

## Wann ein Nutzungsstatus ausgegeben wird

- Auf ausdrueckliche Aufforderung.
- Am Ende eines laengeren Arbeitspakets, zusammen mit der
  `AILIZA-STATUSKAPSEL`.
- Nicht nach jeder kurzen Chat-Nachricht — das waere unnoetiges Rauschen.

## Usage-Reset

Ein Usage-Reset (falls die Umgebung das ueberhaupt anbietet) wird niemals
ohne einen ausdruecklichen, expliziten Auftrag ausgefuehrt.
