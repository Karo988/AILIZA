# CLAUDE.md — Projektanweisungen für den AMUN KI-Gästeberater

> Diese Datei liest Claude Code automatisch, sobald der Ordner geöffnet wird.
> Sie ist das "Gehirn" des Projekts: Ziel, Regeln und Arbeitsweise.

## Wer bist du (Claude Code) in diesem Projekt
Du hilfst beim Bau eines **KI-Gästeberaters** für AMUN — ein orientalisches
Fachgeschäft mit Café (Düfte, Tees, Leuchten, Schmuck + Sandwiches/Kuchen/Getränke).
Die Nutzerin ist **Anfängerin ohne Programmiererfahrung**.

### Wichtige Arbeitsregeln
- Erkläre jeden Schritt in einfacher Sprache, bevor du Code schreibst.
- Arbeite in **kleinen Schritten**. Nach jedem Schritt kurz zeigen, was passiert ist.
- Wähle die **einfachste mögliche Lösung**, die funktioniert. Kein Over-Engineering.
- Kommentiere den Code auf Deutsch, damit die Nutzerin ihn versteht.
- Frage nach, wenn etwas unklar ist, statt etwas anzunehmen.
- Niemals echte Kundendaten verarbeiten (siehe Datenschutz unten).

## Was gebaut werden soll (MVPoc — Schritt 4 der Roadmap)
Ein **einfacher Web-Chatbot**, der über die **Claude API** Gäste berät:
- Eingabefeld + Chatverlauf im Browser (eine einzelne Seite genügt).
- Empfehlungen zu Duft, Tee, Menü auf Basis von Stimmung, Anlass, Budget.
- Antwortzeit unter ca. 3 Sekunden.
- Läuft lokal auf dem Rechner der Nutzerin (für die Pitch-Demo reicht das).

Empfohlener Tech-Stack (einfachst möglich):
- Variante A (am einfachsten für eine Demo): eine einzelne HTML-Datei mit etwas
  JavaScript, die die Claude API aufruft.
- Variante B (wenn ein kleiner Server nötig ist, um den API-Key zu schützen):
  ein minimaler Node.js- oder Python-Server.
Triff die Wahl pragmatisch und erkläre der Nutzerin kurz das Warum.

## Verhalten des Agenten (das ist die Kernlogik)
Der genaue System-Prompt steht in `agent/system_prompt.md`. Kurzfassung der Regeln:
1. **Guardrail:** Nur über das AMUN-Sortiment und Café-Angebot sprechen. Bei
   themenfremden Fragen freundlich zurück zum Sortiment lenken.
2. **Human-in-the-Loop (HITL) bei Allergenen:** Allergen-Auskünfte nur als
   unverbindlichen Hinweis geben und IMMER ans Personal verweisen
   ("Bitte lassen Sie sich das von unserem Team bestätigen.").
   Die KI gibt NIE die rechtsverbindliche Letztauskunft.
3. **Fallback:** Bei Unsicherheit oder fehlendem Wissen ehrlich sagen, dass ein
   Teammitglied weiterhilft — nicht raten, nicht halluzinieren.
4. **Kein PII:** Nicht nach Namen, Adresse, Telefonnummer o. Ä. fragen.

## Wissensbasis (das "Golden Dataset")
Liegt im Ordner `kontext/`:
- `produktwissen.md` — Produkte mit Tags (Stimmung, Anlass, Budget).
- `speisekarte_allergene.md` — Menü + Allergene + HITL-Hinweis.
Lies diese Dateien und gib ihren Inhalt dem Agenten als Wissen mit
(z. B. im System-Prompt oder per einfacher Datei-Einbindung).

## Erfolgskriterien (KPIs aus dem Pitch)
- Beratungs-Completion-Rate ≥ 70 %
- Antwortgenauigkeit ≥ 85 % gegen das Golden Dataset
- Gäste-Zufriedenheit (NPS) ≥ 7/10
Zum Testen liegen Beispielgespräche in `golden_dataset/beispiel_gespraeche.md`.

## Datenschutz & Sicherheit (nicht verhandelbar)
- Der API-Key kommt in eine `.env`-Datei und wird NIE in den Code geschrieben
  oder hochgeladen. Lege eine `.gitignore` an, die `.env` ausschließt.
- Keine echten personenbezogenen Daten im MVPoc.
- Wenn ein Server gebaut wird: der API-Key bleibt auf dem Server, nie im Browser.

## Reihenfolge der Umsetzung (Vorschlag)
1. Projekt aufsetzen + API-Key sicher hinterlegen.
2. Minimaler Chat ("Hallo Welt": eine Frage rein, eine Antwort von Claude raus).
3. System-Prompt + Wissensbasis einbinden (echtes AMUN-Verhalten).
4. Allergen-/Fallback-Regeln testen mit den Beispielgesprächen.
5. Oberfläche aufhübschen (einfaches, sauberes Chat-Design).
