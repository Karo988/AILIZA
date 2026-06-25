# AMUN KI-Gästeberater — Start mit Claude Code

Dieses Kit verwandelt das Konzept aus der KI-Roadmap in einen echten, laufenden
Chatbot. **Du musst nicht programmieren** — Claude Code schreibt den Code, du gibst
die Anweisungen. Diese Anleitung ist für Einsteiger.

---

## 1. Was ist Claude Code?
Ein Werkzeug von Anthropic, mit dem du Programmier-Aufgaben an Claude übergibst —
direkt im Terminal oder in der Claude-Desktop-App. Du beschreibst auf Deutsch, was
du willst, und Claude Code baut, ändert und erklärt den Code für dich.

Offizielle Doku (immer aktuell): https://docs.claude.com/en/docs/claude-code/overview

## 2. Was du einmalig brauchst
1. **Node.js** (das Programm, auf dem Claude Code läuft) — von https://nodejs.org
   die empfohlene Version installieren.
2. **Claude Code** installieren. Die genaue, aktuelle Anleitung steht in der Doku
   oben unter "Setup / Installation". Üblicherweise über die Kommandozeile mit dem
   npm-Paket `@anthropic-ai/claude-code`.
3. Einen **Anthropic-Account** mit API-Zugang (für den API-Key, der den Chatbot
   antworten lässt). Siehe https://docs.claude.com/en/api/overview

> Tipp: Falls dich das Terminal abschreckt — Claude Code gibt es auch in der
> Claude-Desktop-App mit einer freundlicheren Oberfläche. Frag mich, dann zeige
> ich dir den Weg.

## 3. So startest du (3 Schritte)
1. Lege diesen Ordner (`amun-ki-berater`) an einem festen Ort auf deinem Rechner ab.
2. Öffne Claude Code **in diesem Ordner**. Claude Code liest dann automatisch die
   Datei `CLAUDE.md` — das ist die komplette Projektanleitung.
3. Tippe als erste Nachricht den **Start-Prompt** aus Abschnitt 4. Fertig — ab da
   führt dich Claude Code Schritt für Schritt.

## 4. Dein erster Prompt (zum Kopieren)
> "Lies die Datei CLAUDE.md und die Dateien im Ordner kontext/. Erkläre mir zuerst
> in einfachen Worten deinen Plan für den AMUN KI-Gästeberater. Baue dann Schritt 1
> (Projekt aufsetzen + API-Key sicher hinterlegen) und erkläre mir jeden Schritt.
> Ich bin Anfängerin, also bitte langsam und ohne Fachjargon."

## 5. Hinweise zur Sicherheit
- Den **API-Key** niemals in den Code schreiben oder ins Internet hochladen.
  Claude Code legt ihn sicher in einer `.env`-Datei ab — das ist so gewollt.
- Im MVPoc werden **keine echten Kundendaten** verarbeitet.

## 6. Was im Ordner liegt
- `CLAUDE.md` — die Projektanleitung, die Claude Code automatisch liest.
- `agent/system_prompt.md` — die "Persönlichkeit" und die Regeln des Beraters.
- `kontext/produktwissen.md` — das Produktwissen (zum Ausfüllen/Erweitern).
- `kontext/speisekarte_allergene.md` — Menü + Allergene + HITL-Regel.
- `golden_dataset/beispiel_gespraeche.md` — Testgespräche, um die Qualität zu prüfen.

---

### Falls du selbst programmieren lernen möchtest
Für diesen Agenten ist das nicht nötig. Wenn dich das Thema aber reizt: **Python**
ist eine sehr vielseitige, einsteigerfreundliche Sprache (gut für Web, Daten, KI,
Automatisierung). Du kannst Claude Code jederzeit bitten, dir den erzeugten Code
zu erklären — das ist eine der besten Arten zu lernen.
