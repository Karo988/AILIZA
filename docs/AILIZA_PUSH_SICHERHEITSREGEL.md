# AILIZA Push-Sicherheitsregel

Verbindlich ab sofort. Gilt für alle Pushes zu jedem Remote, unabhängig
davon, ob anschließend gemergt oder deployt wird.

**Lesehinweis:** Dieses Dokument trennt drei Dinge strikt.
Abschnitte 1–10 sind **verbindliche Regel**. Abschnitt 11 listet auf, was
im Repository **tatsächlich belegt** ist. Abschnitt 12 listet auf, was
**empfohlen, aber nicht nachgewiesen** ist. Was in Abschnitt 12 steht,
darf nirgends als vorhanden bezeichnet werden.

---

## 1. Grundsatz

Vor jedem Push muss der tatsächlich neu zu übertragende Commit-Bereich
gegen Secrets, Zugangsdaten und unzulässige sensible Inhalte geprüft
werden. Ein einfacher Vergleich des aktuellen Dateistands genügt nicht,
weil ein Secret in einem früheren Commit enthalten und später wieder
gelöscht worden sein kann.

Der Prüfbereich wird aus dem Ziel-Remote, dem Ziel-Branch und dem
Merge-Base ermittelt. Es darf nicht pauschal von einer festen Anzahl von
Branches ausgegangen werden.

Ein Push ist bereits eine externe Speicherung — auch ohne Merge und ohne
Deployment.

## 2. Verbindliche Prüfungen

1. Ziel-Remote und Ziel-Branch eindeutig feststellen.
2. Neu zu übertragenden Commit-Bereich bestimmen.
3. Diesen Bereich **werkzeuggestützt** auf Secrets prüfen (gitleaks,
   siehe Abschnitt „Durchführung von Prüfschritt 3").
4. Geänderte Inhalte ergänzend auf personenbezogene Daten, besondere
   Kategorien personenbezogener Daten und vertrauliche Unternehmensdaten
   prüfen.
5. Prüfergebnis mit Status, Zeitpunkt, Prüfbereich und Werkzeug
   dokumentieren.
6. Nur bei einem gültigen Ergebnis darf gepusht werden.

Zulässige Ergebnisse:

- **GÜLTIG** — Prüfung erfolgreich, kein blockierender Fund.
- **UNGÜLTIG** — Sicherheitsfund, unvollständiger Prüfbereich oder nicht
  zuverlässig ausführbare Prüfung.
- **NICHT ANWENDBAR** — nur mit kurzer, dokumentierter Begründung.

Bei jedem Fund werden ausschließlich Kategorie, Datei und Zeile
beziehungsweise Commit genannt. **Der gefundene Wert wird niemals
ausgegeben**, auch nicht gekürzt oder maskiert.

### Durchführung von Prüfschritt 3

Eingeführtes Werkzeug ist **gitleaks**, Version 8.28.0, mit der
Konfiguration `.gitleaks.toml` (Beleg: Abschnitt 11). Die frühere
Übergangsregel mit Sichtprüfung ist damit entfallen. Eine reine
Sichtprüfung ist als alleiniger Nachweis **nicht mehr zulässig**.

Der Prüfschritt wird an zwei Stellen ausgeführt:

| Ort | Verbindlichkeit | Bemerkung |
|---|---|---|
| Lokal vor dem Push | **empfohlen** | Anleitung: `docs/SECRET_SCAN_LOKAL.md`. Findet das Problem, bevor es das Repository erreicht. |
| CI-Job `secret-scan` | **verbindlich** | Läuft bei jedem Push und jedem Pull Request. Ein Fund macht den Job rot. |

Der verbindliche Nachweis ist das Ergebnis des CI-Jobs. Ist gitleaks
lokal nicht installiert, darf gepusht werden — der CI-Scan holt den
Prüfschritt nach. Das ist bewusst so: eine fehlende lokale Installation
soll die Arbeit nicht blockieren, und der Scan wird dadurch nicht
übersprungen, sondern nur später ausgeführt.

**Abgrenzung zu Abschnitt 10:** Schlägt der CI-Job `secret-scan` wegen
eines **Funds** fehl, gilt die Prüfung als UNGÜLTIG; weiteres Vorgehen
nach Abschnitt 6. Fällt er aus einem **technischen Grund** aus
(Download nicht erreichbar, Runner-Fehler), gilt Abschnitt 5: der Lauf
darf einmal wiederholt werden. Ein dauerhaft ausgefallenes Werkzeug
sperrt den Push.

## 3. Technische Schutzschichten

Angestrebter Ablauf, in dieser Reihenfolge:

1. Schneller Secret-Scan der geänderten beziehungsweise gestagten Dateien
   während der lokalen Arbeit.
2. Vollständiger Scan des neu zu pushenden Commit-Bereichs unmittelbar
   vor dem Push.
3. Secret-Scan in der CI.
4. Serverseitige Push Protection, soweit für Repository und Organisation
   verfügbar.
5. Geschützte Hauptbranches.

Push Protection ist eine **zusätzliche** serverseitige Schutzschicht. Sie
ersetzt weder die lokale Prüfung noch die CI und erkennt nicht
zwangsläufig jedes Secret-Format.

Welche dieser Schichten heute tatsächlich aktiv sind, steht in
Abschnitt 11. Nicht belegte Schichten dürfen nicht als umgesetzt
bezeichnet werden.

## 4. Testdaten

Inhalte unter `tests/`, `fixtures/` oder in eindeutig bezeichneten
Testdateien dürfen als synthetisch behandelt werden, wenn sie erkennbar
als Testdaten erzeugt wurden und keine konkreten Hinweise auf reale
Personen enthalten.

Für Testdaten sind nach Möglichkeit reservierte oder kontrollierte Werte
zu verwenden, etwa `example.com`-Adressen und ausdrücklich gekennzeichnete
Testidentitäten.

Ein gewöhnlicher Name allein löst keinen Stopp aus. Eine gültige
Prüfsumme, eine reale Domain oder eine formal gültige Telefonnummer
beweist weder Echtheit noch Unbedenklichkeit. Entscheidend sind Herkunft,
Kontext und Kombination der Merkmale.

Bei konkreten Hinweisen auf reale personenbezogene Daten gilt die Prüfung
als UNGÜLTIG, bis der Inhalt entfernt, anonymisiert oder ausdrücklich
freigegeben wurde.

## 5. Werkzeugfehler

Bei einem mutmaßlich vorübergehenden Werkzeugfehler darf derselbe
Prüfschritt **einmal** wiederholt werden.

Bleibt der Fehler bestehen, ist das Ergebnis UNGÜLTIG. Es darf nicht
gepusht werden. Als sichere Weiterarbeit sind lokale Änderungen, lokale
Commits oder ein dokumentierter `responsibility_handoff` erlaubt.

Ein Sicherheitsfund ist **kein** Werkzeugfehler und darf nicht durch
Wiederholen oder Wechseln des Werkzeugs umgangen werden.

Eine leere Trefferliste nach einem fehlgeschlagenen Befehl ist kein
bestandenes Ergebnis. Exitcode und erwartete Ausgabe sind bei jedem
Prüfschritt auszuwerten.

## 6. Bereits vorhandene Geheimnisse

„Bereits vorhanden" oder „bereits öffentlich" bedeutet **nicht** „sicher".

Wird ein echtes Secret in einem lokalen oder veröffentlichten Commit
gefunden, darf es nicht weiterverbreitet werden. Wurde es bereits an ein
Remote-System übertragen, gilt es als potenziell kompromittiert.

Das Entfernen aus dem aktuellen Dateistand, das Löschen eines Branches
oder das Umschreiben der Historie **ersetzt keine Rotation**. Rotation und
Widerruf erfolgen ausschließlich durch die zuständige berechtigte Person.
AILIZA dokumentiert Fund, Zuständigkeit und Übergabe, führt aber keine
eigenmächtige Rotation durch.

## 7. Backup und Datenverlust

**Ein Push ist keine Sicherungsmethode.**

Vor risikoreichen lokalen Operationen ist eine geeignete lokale oder
verschlüsselte Sicherung zu verwenden.

Solange Ziel, Verschlüsselung, Schlüsselverwahrung, Restore-Verfahren und
Verantwortlichkeit für AILIZA nicht nachgewiesen sind, darf ein
produktionsfähiges Backup-/Restore-Verfahren nicht als vorhanden
bezeichnet werden. Zum belegten Stand siehe Abschnitt 11.

## 8. Datenschutz und Memory Scopes

Wissen und Daten dürfen nicht ohne Berechtigung zwischen `session`,
`personal`, `project` und `company` übertragen werden.

`help_glossary` und `learning_content` sind Inhaltsbereiche und **keine**
persönlichen Memory Scopes.

Ein Push darf keine Scope-Grenze, Mandantengrenze oder bestehende
Berechtigung umgehen. Bei Unsicherheit ist nur der betroffene Teil zu
blockieren; sichere lokale Weiterarbeit oder `responsibility_handoff`
bleiben möglich.

## 9. Nachweis

Für jeden geprüften Push sind mindestens festzuhalten:

- Repository
- Ziel-Remote und Ziel-Branch
- geprüfter Commit-Bereich
- Prüfmethode (lokaler Scan oder CI-Job `secret-scan`) sowie Name und
  Version des eingesetzten Werkzeugs
- Ergebnis
- erkannte Ausnahmen
- verantwortliche Freigabe, falls erforderlich
- Zeitpunkt

Die Regel und ihre Prüfbelege können die technischen und organisatorischen
Maßnahmen von AILIZA unterstützen. Sie stellen **für sich allein keinen
vollständigen Nachweis** der Einhaltung von Art. 32 DSGVO dar.

### Ergebnisformat

```
Prüfbereich/Commits:       GÜLTIG / UNGÜLTIG
Prüfung Secrets:           GÜLTIG / UNGÜLTIG / MANUELLE PRÜFUNG
Methode Secret-Prüfung:    lokaler Scan / CI-Job secret-scan (gitleaks 8.28.0)
Prüfung personenbezogen:   GÜLTIG / UNGÜLTIG / MANUELLE PRÜFUNG
Prüfung Art.-9-Daten:      GÜLTIG / UNGÜLTIG / MANUELLE PRÜFUNG
Prüfung interne Angaben:   GÜLTIG / UNGÜLTIG / MANUELLE PRÜFUNG
Warnungen ohne Sperre:     <Liste oder "keine">
Werkzeugstatus:            GÜLTIG / UNGÜLTIG / NICHT ANWENDBAR
Pushfreigabe:              JA / NEIN
```

Seit der Einführung von gitleaks ist bei jedem Push ein Werkzeug im
Einsatz. `Werkzeugstatus` ist daher auf `GÜLTIG` oder `UNGÜLTIG` zu
setzen — `NICHT ANWENDBAR` darf ein fehlgeschlagenes Werkzeug nicht
verdecken und ist für die Secret-Prüfung nicht mehr vorgesehen.

## 10. Harte Sperre

Kein Push bei:

- erkanntem oder ungeklärtem Secret
- realen Zugangsdaten
- unberechtigten personenbezogenen oder vertraulichen Daten
- besonderer Kategorie personenbezogener Daten ohne belegte Berechtigung
- unklarem Ziel-Remote
- unvollständigem Commit-Prüfbereich
- dauerhaft ausgefallenem Sicherheitswerkzeug — gemeint ist ein
  **eingeführtes** Werkzeug, das nicht mehr zuverlässig läuft. Ein
  einmaliger technischer Fehlschlag des CI-Jobs `secret-scan` fällt
  dagegen unter Abschnitt 5 (einmalige Wiederholung zulässig). Eine
  fehlende **lokale** gitleaks-Installation ist kein Ausfall — dafür
  gilt die Aufteilung in Abschnitt 2.
- unbelegter erforderlicher Freigabe

Die Sperre ist fail-closed, aber auf den betroffenen Push beziehungsweise
Inhalt begrenzt. Andere, nicht betroffene Arbeit wird dadurch nicht
angehalten.

---

## 11. Technisch belegte Absicherung

Stand der Prüfung: **26. August 2026**, gegen `main`.
Diese Liste ist im Repository überprüfbar.

| Schutzmaßnahme | Status | Beleg |
|---|---|---|
| Secret-Scanner (gitleaks) | **vorhanden** | `.github/workflows/ci.yml`, Job **`secret-scan`**; Konfiguration `.gitleaks.toml`; Version fest auf 8.28.0 gepinnt |
| Secret-Scan in der CI | **vorhanden** | Job `secret-scan`, läuft bei jedem Push und bei jedem Pull Request (`--exit-code 1`, kein `continue-on-error`) |
| Scan des Commit-Bereichs statt nur des Dateistands | **vorhanden** | Schritt „Prüfbereich bestimmen" im Job `secret-scan`: Push `before..sha`, Pull Request `base..head`; bei nicht eindeutig bestimmbarem Bereich fail-closed auf die vollständige Historie |
| Fundausgabe ohne Klartextwert | **vorhanden** | `--redact` im Job `secret-scan`; kein Upload eines Fundberichts als Artefakt |
| Anleitung für den lokalen Scan | **vorhanden** | `docs/SECRET_SCAN_LOKAL.md` |
| Verschlüsseltes lokales Backup | **vorhanden** | `scripts/ailiza_backup.py`, AES-256-GCM; Tests in `tests/test_ailiza_backup.py` |
| Restore-Funktion | **vorhanden** | Restore-Pfad in `scripts/ailiza_backup.py`, getestet |
| CI bei jedem Push | **vorhanden** | `.github/workflows/ci.yml` — Jobs: `test`, `secret-scan`, `frontend-quality`, `sandbox-platform`, `postgres-audit`, `frontend-e2e` |
| PostgreSQL-Migrationsprüfung in CI | **vorhanden** | Job `postgres-audit` |
| Frontend-Prüfung in CI | **vorhanden** | Job `frontend-e2e` |
| `.env` von der Versionierung ausgeschlossen | **vorhanden, mit benannten Ausnahmen** | `.gitignore` blockiert `.env`. Getrackt und ausdrücklich freigegeben sind die zwei öffentlichen Vorlagen `.env.example` und `apps/frontend/.env.example` — beide ohne Schlüsselwerte. Eine dritte `.env`-Variante gibt es nicht. |
| Governance-Integritätsprüfung (Gate 10) | **vorhanden** | `apps/backend/config_integrity.py`, `governance_integrity.json` |

**Zum Prüfumfang des Jobs `test`:** Er führt ausschließlich `pytest tests/`
aus. Die zweite Suite unter `apps/backend/tests/` ist in `ci.yml`
auskommentiert und läuft **nicht** mit. Wer sich auf „CI ist grün" beruft,
bezieht sich damit auf `tests/`, nicht auf den gesamten Testbestand.

**Nicht belegt und daher nicht als vorhanden zu bezeichnen:**

| Schutzmaßnahme | Status |
|---|---|
| Pre-Commit-Hooks | **nicht vorhanden** — kein `.pre-commit-config.yaml`, kein `.husky/`. Bewusste Entscheidung: der lokale Scan ist eine Anleitung (`docs/SECRET_SCAN_LOKAL.md`), kein erzwungener Hook. Verbindlich ist die CI. |
| Serverseitige Push Protection | **nicht nachgewiesen** — nur in den GitHub-Einstellungen prüfbar, nicht im Repository |
| Branch-Schutz auf `main` | **nicht nachgewiesen** — nur in den GitHub-Einstellungen prüfbar |
| Betriebsfähiges Backup-Verfahren | **nicht nachgewiesen** — Skript und Tests existieren; Ziel, Zeitplan, Schlüsselverwahrung, Verantwortlichkeit und regelmäßige Restore-Probe sind nicht dokumentiert |

## 12. Empfohlen, noch nicht umgesetzt

Diese Punkte sind Empfehlungen. Sie sind **nicht** Bestandteil der
verbindlichen Regel, solange sie nicht umgesetzt und in Abschnitt 11
belegt sind.

1. ~~**Secret-Scanner einführen** (`gitleaks` oder gleichwertig) und in die
   CI aufnehmen.~~ — **erledigt am 26. August 2026.** Umgesetzt als Job
   `secret-scan` in `.github/workflows/ci.yml` mit `.gitleaks.toml`;
   lokale Anleitung in `docs/SECRET_SCAN_LOKAL.md`. Belegt in
   Abschnitt 11.
2. **Serverseitige Push Protection aktivieren.** Sie ist die einzige
   Schutzschicht, die nicht davon abhängt, ob eine Regel befolgt wurde.
3. **Branch-Schutz auf `main`** einrichten und den Status dokumentieren.
4. **Backup-Betriebskonzept** festlegen: Ziel, Zeitplan, Aufbewahrung,
   Schlüsselverwahrung, benannte Verantwortliche, regelmäßige
   Restore-Probe mit Protokoll.
5. **Prüfbelege ablegen** — die Angaben aus Abschnitt 9 an einer festen
   Stelle sammeln, damit die Regel auditierbar wird und nicht nur
   beschrieben ist.

Die frühere Übergangsregel zu Prüfschritt 3 ist mit der Umsetzung von
Punkt 1 **entfallen**. Es gilt ausschließlich der Wortlaut in Abschnitt 2.
