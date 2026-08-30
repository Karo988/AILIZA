# AILIZA — verbindliche Codex-Anweisungen

Diese Regeln gelten fuer alle Codex-Arbeiten in diesem Repository. Fuer
Claude-Code-Sitzungen gilt `CLAUDE.md` mit denselben Handoffs als Basis.

## Kommunikation im Chat

- Antworte kurz und leicht verstaendlich.
- Beantworte alle Fragen und kontrolliere die Antwort vor dem Senden.
- Beschreibe Probleme knapp und biete mindestens eine konkrete Loesung an.
- Markiere fehlende Fakten als `nicht verfuegbar` und offene Entscheidungen als
  `offen`; erfinde nichts.
- Bewahre trotz Kuerze notwendige Belege, Risiken und Abnahmekriterien.

## Pflichtstart

1. Lies zuerst `docs/AILIZA_HANDOFF_ENTWICKLUNG.md`.
2. Bestimme danach nur den betroffenen Diff, maximal fuenf primaere Dateien
   und die zugehoerigen Zieltests.
3. Lade historische Chats, `docs/archiv/` und alte Handovers nur bei einem
   konkreten, belegten Informationsbedarf.

## Modell und Kontext

Wende die Auswahl-, Eskalations-, Kontext- und Statusregeln aus
`05_prompts/CODEX_TOKEN_KONTEXT_STATUS_PROMPT.md` an.

- Empfehle das kleinste geeignete Modell und die niedrigste sichere
  Reasoning-Stufe.
- Behaupte keinen Modellwechsel, wenn die laufende Codex-Umgebung ihn nicht
  technisch bestaetigt.
- Gib Token-, Kontext-, Konto- und Resetwerte nur aus, wenn sie tatsaechlich
  messbar sind; sonst exakt `nicht verfuegbar`.
- Fuehre ohne ausdruecklichen Auftrag niemals einen Usage-Reset aus.
- Erstelle den Nutzungsstatus auf Aufforderung sowie am Ende eines langen
  Tasks, nicht nach jeder kurzen Nachricht.

## Arbeitsgrenzen

- Ein Task bearbeitet genau ein klar abgegrenztes Arbeitspaket.
- Fuer Analyse-, Review- und Planungsauftraege nur pruefen und berichten.
- Fuer Aenderungsauftraege den kleinsten sicheren Schnitt implementieren und
  angemessen testen.
- Keine Secrets, Roh-Prompts, Memory-Inhalte oder personenbezogenen Daten in
  Logs, Commits, Testausgaben oder Handovers schreiben.
- Externe, destruktive, kostenpflichtige oder wesentlich
  umfangserweiternde Aktionen benoetigen eine ausdrueckliche Freigabe.

## Pflichtabschluss

Beende groessere Arbeitspakete mit der maximal zwoelfzeiligen
`AILIZA-STATUSKAPSEL` aus `docs/AILIZA_HANDOFF_ENTWICKLUNG.md`.

Bei Arbeiten am persoenlichen Lernen, an `user_memory`, Memory-Vorschlaegen
oder deren Oberflaeche lies zusaetzlich `docs/AILIZA_HANDOFF_ANWENDER.md` und
halte dessen Reifestufen und Governance-Sperren ein.
