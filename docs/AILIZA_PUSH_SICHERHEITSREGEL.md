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
3. Diesen Bereich auf Secrets prüfen — **werkzeuggestützt, sobald ein
   Scanner eingeführt ist** (siehe Übergangsregel unten).
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

### Übergangsregel zu Prüfschritt 3

Im Repository ist derzeit **kein** Secret-Scanner eingeführt (Stand siehe
Abschnitt 11). Bis das nachgeholt ist, gilt:

- Prüfschritt 3 wird als **Sichtprüfung** des neu zu übertragenden
  Commit-Bereichs durchgeführt.
- Das Ergebnis ist im Nachweis ausdrücklich als `Sichtprüfung` zu
  kennzeichnen — nicht als werkzeuggestützte Prüfung.
- Eine so durchgeführte Prüfung kann GÜLTIG sein. Das Fehlen eines
  Scanners allein sperrt den Push **nicht**.

Diese Übergangsregel endet, sobald ein Scanner eingeführt ist. Ab dann
ist die Sichtprüfung als alleiniger Nachweis nicht mehr zulässig.

**Abgrenzung zu Abschnitt 10:** Ein *ausgefallenes* Werkzeug sperrt den
Push — ein *noch nicht eingeführtes* Werkzeug nicht. Andernfalls wäre
jeder Push bis zur Scanner-Einführung ungültig, was die Regel praktisch
unanwendbar machen würde.

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
- eingesetztes Werkzeug und Version
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
Methode Secret-Prüfung:    Sichtprüfung / <Werkzeug + Version>
Prüfung personenbezogen:   GÜLTIG / UNGÜLTIG / MANUELLE PRÜFUNG
Prüfung Art.-9-Daten:      GÜLTIG / UNGÜLTIG / MANUELLE PRÜFUNG
Prüfung interne Angaben:   GÜLTIG / UNGÜLTIG / MANUELLE PRÜFUNG
Warnungen ohne Sperre:     <Liste oder "keine">
Werkzeugstatus:            GÜLTIG / UNGÜLTIG
Pushfreigabe:              JA / NEIN
```

## 10. Harte Sperre

Kein Push bei:

- erkanntem oder ungeklärtem Secret
- realen Zugangsdaten
- unberechtigten personenbezogenen oder vertraulichen Daten
- besonderer Kategorie personenbezogener Daten ohne belegte Berechtigung
- unklarem Ziel-Remote
- unvollständigem Commit-Prüfbereich
- dauerhaft ausgefallenem Sicherheitswerkzeug — gemeint ist ein
  **eingeführtes** Werkzeug, das nicht mehr zuverlässig läuft. Ein noch
  nicht eingeführtes Werkzeug fällt unter die Übergangsregel in
  Abschnitt 2 und sperrt den Push nicht.
- unbelegter erforderlicher Freigabe

Die Sperre ist fail-closed, aber auf den betroffenen Push beziehungsweise
Inhalt begrenzt. Andere, nicht betroffene Arbeit wird dadurch nicht
angehalten.

---

## 11. Technisch belegte Absicherung

Stand der Prüfung: **21. August 2026**, gegen `main`.
Diese Liste ist im Repository überprüfbar.

| Schutzmaßnahme | Status | Beleg |
|---|---|---|
| Verschlüsseltes lokales Backup | **vorhanden** | `scripts/ailiza_backup.py`, AES-256-GCM; Tests in `tests/test_ailiza_backup.py` |
| Restore-Funktion | **vorhanden** | Restore-Pfad in `scripts/ailiza_backup.py`, getestet |
| CI bei jedem Push | **vorhanden** | `.github/workflows/ci.yml` — drei Jobs: `test`, `postgres-audit`, `frontend-e2e` |
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
| gitleaks oder ein anderer Secret-Scanner | **nicht vorhanden** — kein Treffer in `.github/` |
| Secret-Scan in der CI | **nicht vorhanden** — keiner der drei vorhandenen Jobs führt einen Secret-Scan aus |
| Pre-Commit-Hooks | **nicht vorhanden** — kein `.pre-commit-config.yaml`, kein `.husky/` |
| Serverseitige Push Protection | **nicht nachgewiesen** — nur in den GitHub-Einstellungen prüfbar, nicht im Repository |
| Branch-Schutz auf `main` | **nicht nachgewiesen** — nur in den GitHub-Einstellungen prüfbar |
| Betriebsfähiges Backup-Verfahren | **nicht nachgewiesen** — Skript und Tests existieren; Ziel, Zeitplan, Schlüsselverwahrung, Verantwortlichkeit und regelmäßige Restore-Probe sind nicht dokumentiert |

## 12. Empfohlen, noch nicht umgesetzt

Diese Punkte sind Empfehlungen. Sie sind **nicht** Bestandteil der
verbindlichen Regel, solange sie nicht umgesetzt und in Abschnitt 11
belegt sind.

1. **Secret-Scanner einführen** (`gitleaks` oder gleichwertig) und in die
   CI aufnehmen. Ohne Werkzeug bleibt Prüfschritt 3 eine Sichtprüfung
   über die Commit-Historie — langsam und unzuverlässig.
2. **Serverseitige Push Protection aktivieren.** Sie ist die einzige
   Schutzschicht, die nicht davon abhängt, ob eine Regel befolgt wurde.
3. **Branch-Schutz auf `main`** einrichten und den Status dokumentieren.
4. **Backup-Betriebskonzept** festlegen: Ziel, Zeitplan, Aufbewahrung,
   Schlüsselverwahrung, benannte Verantwortliche, regelmäßige
   Restore-Probe mit Protokoll.
5. **Prüfbelege ablegen** — die Angaben aus Abschnitt 9 an einer festen
   Stelle sammeln, damit die Regel auditierbar wird und nicht nur
   beschrieben ist.

Bis Punkt 1 umgesetzt ist, gilt die **Übergangsregel in Abschnitt 2**:
Prüfschritt 3 wird als Sichtprüfung durchgeführt und im Nachweis
ausdrücklich als solche gekennzeichnet. Das Fehlen eines Scanners sperrt
den Push nicht — ein ausgefallenes eingeführtes Werkzeug dagegen schon.
