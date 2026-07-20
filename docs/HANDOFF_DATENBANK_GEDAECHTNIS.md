# AILIZA — Übergabe-Dokument: Datenbank & Gedächtnis

Stand: 20.07.2026 · Für den nächsten Agenten, falls Karo die Tokens ausgehen.
**Bitte diese Datei zuerst lesen, dann mit Karo bestätigen, womit weitergemacht wird.**

---

## 1. Was bereits fertig ist (3 offene Branches, keiner gemergt)

| Branch | Inhalt | Status |
|---|---|---|
| `claude/postgres-pool-pre-ping` | Fix für HTTP-500-Absturz bei toter Neon-Verbindung (`pool_pre_ping`) | ✅ Fertig, 846/846 Tests grün, **wartet auf Merge-OK** |
| `claude/autarker-betrieb` (PR #42 auf GitHub) | SQLite in `/data`-Docker-Volume für Betrieb ohne Render/Neon | ✅ Fertig, wartet auf Merge-OK |
| `claude/memory-architecture-v1` | Konzept-Dokument `docs/MEMORY_ARCHITECTURE_V1.md` (17-Tabellen-Bestandsaufnahme, Datenklassen, Lösch-/Backup-Regeln, 3 Mini-PR-Vorschläge) | ✅ Reines Konzept, kein Code, wartet auf Entscheidung |

**Wichtig: Reihenfolge beim Mergen.** `postgres-pool-pre-ping` und `autarker-betrieb` sind unabhängig voneinander, beide gehen von `main` aus — einzeln mergebar, kein Konflikt zu erwarten.

---

## 2. Was live auf Render passiert ist (Kontext für Debugging)

- Render-Service `AILIZA-staging` läuft mit Neon-Postgres (`AILIZA_DATABASE_URL` gesetzt).
- Zwei echte Bugs wurden auf dem Weg gefunden und bereits gefixt (auf `main` gemergt):
  1. `agent_runtime`/`main.py` Fallback-Imports fehlte `apps.backend.` Präfix → `ModuleNotFoundError` beim Deploy.
  2. Neon-Connection-String im Render-Dashboard hatte zuerst das maskierte Passwort statt des echten (Nutzerfehler beim Kopieren, kein Code-Bug).
- **Noch offen:** `pool_pre_ping`-Fix (siehe oben) ist geschrieben, aber noch nicht gemergt/deployed.

---

## 3. Der noch nicht umgesetzte Gedächtnis-Auftrag (großes Konzept)

Karo hat einen sehr detaillierten Prompt für ein "Profilregel- und Governance-Konzept" vorbereitet (13 Abschnitte: Kurzurteil, Drei-Ebenen-Modell Profil/Einstellungen/Gedächtnis, Datenmodell, Rollen, Entscheidungslogik, RAG-Logik, DSGVO/EU-AI-Act, UI-Konzept, Mini-PR-Roadmap, Risiken, Nicht-im-Scope).

**Kernprinzip des Auftrags:** So wenig festes Profil wie möglich, so viel Nutzerkontrolle wie möglich. Kein heimliches Profiling. Drei getrennte Ebenen:
- **Profil** (`users`) = nur technische Stammdaten, klein halten
- **Einstellungen** (`user_settings`) = Arbeitspräferenzen (Ton, Länge, Sprache), keine Persönlichkeitsanalyse
- **Gedächtnis** (`memory_items`) = inhaltliches Wissen, nur sichtbar/bestätigt/löschbar, getrennt in Firmengedächtnis vs. Nutzergedächtnis

**Status:** Prompt liegt vor (siehe Konversationsverlauf), **noch nicht ausgeführt**. Das ist reine Text-/Konzeptarbeit, kein Code — passt für **Opus** (Architektur/Compliance-Tiefe) oder in Etappen für Sonnet, je nach Budget.

**Empfehlung für den nächsten Agenten:** Diesen Prompt 1:1 übernehmen (Karo hat ihn bereits fertig formuliert, mit einer kleinen Präzisierung: "aktives aber sichtbares Merken statt heimliches Lernen"). Als reines Konzept-Dokument ausarbeiten, wie bei `MEMORY_ARCHITECTURE_V1.md` — neuer eigener Branch, kein Code, PR mit Doku, wartet auf Karo-Freigabe.

---

## 4. Arbeitsregeln, die für Karo gelten (aus CLAUDE.md, unbedingt einhalten)

- **Erst fragen, dann programmieren.** Vor jeder Code-Änderung erklären WAS/WARUM, auf OK warten.
- Testliste vor Implementierung, TDD.
- Jede Antwort muss die Modell-Empfehlung explizit nennen (Sonnet 5 = Standard, Opus nur für große Architektur/Compliance-Entscheidungen).
- Deutsche, einfache Sprache in Erklärungen (Karo-Wunsch aus dieser Session).
- Keine Secrets/PII in Logs oder Commits.
- Kleine, einzeln bestätigte PRs statt große Umbauten.

---

## 5. Nächste sinnvolle Schritte (Prioritätsvorschlag)

1. `postgres-pool-pre-ping` mergen + deployen (kleinster, dringendster Fix — behebt echten Live-Bug).
2. `autarker-betrieb` (PR #42) reviewen + mergen, wenn Karo bereit ist.
3. Gedächtnis-Konzept-Prompt (Abschnitt 3 oben) als eigenständiges Dokument ausarbeiten.
4. Erst danach: erste Mini-PRs aus dem Gedächtnis-Konzept umsetzen (nicht vor Schritt 3, Architektur muss zuerst stehen).

---

*Für den nächsten Agenten: Diese Datei ist der schnellste Weg, um ohne Kontextverlust weiterzumachen. Bei Unklarheiten: Karo fragen, nicht raten — sie legt Wert auf "erst fragen, dann handeln".*
