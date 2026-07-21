# AILIZA — Roadmap-Entscheidung: Autark zuerst, Cloud optional

Stand: 20.07.2026 · Karo-Entscheidung, damit sie nicht verloren geht.

---

## Entscheidung

**AILIZA wird primär als autarke, eigene Datenbank/Anwendung gebaut — nicht als Cloud-Produkt.**

- **Neon/Postgres** war und bleibt nur die **Übergangslösung** für die aktuelle Render-Staging-Umgebung (weil Render Free keinen dauerhaften Speicher hat). Kein Zielzustand.
- **Autarker Betrieb** (SQLite in `/data`-Volume, `docker-compose.yml`, siehe PR #42 / `docs/AUTARKER_BETRIEB.md`) ist die **primäre Zielumgebung** ab sofort.
- **Zukunftsziel (separater, späterer Auftrag):** AILIZA soll als **herunterladbare Anwendung ohne Docker-Pflicht** auf jedem PC laufen können (Windows/Mac/Linux) — z. B. per gepackter ausführbarer Datei (PyInstaller o. ä.), Doppelklick startet einen lokalen Server, Browser öffnet automatisch.

## Warum (Vor-/Nachteile-Vergleich, Kurzfassung)

| | Docker Compose (jetzt) | Gepackte Datei (später) | Cloud/Neon (Nebenlinie) |
|---|---|---|---|
| Für wen | Eigener PC/Server zum Testen/Betreiben | Endnutzer, einfacher Download | Übergangslösung Render-Staging |
| Vorteil | Schon fertig (PR #42) | Kein Docker nötig, wirkt wie normales Programm | Kein eigener PC muss laufen |
| Nachteil | Braucht Docker Desktop | Packaging-Aufwand pro OS, noch nicht begonnen | Cloud-Abhängigkeit — genau das, was vermieden werden soll |
| Passt zum Ziel „autark" | ✅ | ✅✅ (bestes Ziel) | ❌ |

## Konsequenz für die Roadmap

1. **Block A (jetzt):** PR #42 (autarker Betrieb), PR #44 (Memory-Kernschema), PR #45 (Memory-Suggestions) mergen. Verifikation lokal via `docker compose up -d` — **nicht** gegen Neon.
2. **Block B:** Gedächtnis nutzbar machen (UI, Export/Löschung, Chat-Anbindung) — läuft unabhängig davon, welche DB dahinter steckt (SQLite oder Postgres), Code ist bereits DB-agnostisch.
3. **Block C:** Wissensdatenbank + Vektorsuche.
4. **Block D (neu, eigener späterer Auftrag, noch nicht begonnen):** Desktop-Distribution ohne Docker (PyInstaller-Packaging). Explizit **nicht** vor Block A/B/C einschieben, um die laufende Datenbank-Arbeit nicht zu verzögern.

**Wichtig:** Der Datenbank-Code selbst unterscheidet nicht zwischen "Docker" und "gepackte Datei" — beide nutzen dieselbe SQLite-Datei über `AILIZA_DATABASE_URL=sqlite:////data/ailiza.sqlite` (oder gleichwertigen lokalen Pfad). Block D ändert nur, *wie* AILIZA gestartet wird, nicht die Datenbank-Architektur selbst.

---

*Für den nächsten Agenten: Diese Entscheidung gilt, bis Karo sie ausdrücklich ändert. Bei Unsicherheit über Zielumgebung: hier nachlesen, nicht neu interpretieren.*
