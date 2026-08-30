# Secret-Scan lokal ausführen

Kurzanleitung für den schnellen Scan während der Arbeit.

**Das hier ist eine Anleitung, kein Zwang.** Es gibt bewusst keinen
Pre-Commit-Hook, der Commits blockiert. Verbindlich ist der CI-Job
`secret-scan` in `.github/workflows/ci.yml`.

Wichtig zum Verständnis, was der lokale Scan leistet: Er ist die einzige
Schicht, die einen Fund **vor** dem Push bemerkt. Die CI läuft erst
**nach** dem Push — sie erkennt also, verhindert aber nicht. Welche
Schicht was leistet, steht in `docs/AILIZA_PUSH_SICHERHEITSREGEL.md`,
Abschnitt 2.

Verwandte Dokumente:
- `docs/AILIZA_PUSH_SICHERHEITSREGEL.md` — die verbindliche Regel
- `.gitleaks.toml` — die Konfiguration, die lokal und in der CI gilt

## 1. Einmalig installieren

Die CI verwendet fest **8.28.0**. Eine andere lokale Version kann andere
Ergebnisse liefern als die CI — deshalb dieselbe Version installieren.

Windows (PowerShell):

```powershell
winget install --id gitleaks.gitleaks --version 8.28.0
```

> `winget install gitleaks` ohne Versionsangabe installiert die jeweils
> neueste Version. Das ist nicht falsch, weicht aber von der CI ab.

Alternativ (alle Systeme): das passende Archiv der Version **8.28.0** von
<https://github.com/gitleaks/gitleaks/releases/tag/v8.28.0> herunterladen,
entpacken und die Datei `gitleaks` in einen Ordner legen, der im `PATH`
liegt.

Version verbindlich prüfen — nicht nur anzeigen:

```powershell
$erwartet = "8.28.0"
$ist = (gitleaks version)
if ($ist -ne $erwartet) { Write-Error "gitleaks $ist installiert, erwartet $erwartet" }
else { Write-Host "gitleaks $ist — passt zur CI" }
```

## 2. Vor dem Push: den neuen Commit-Bereich prüfen

Das ist der Scan, der dem verbindlichen Prüfschritt 3 entspricht. Er prüft
**die neuen Commits**, nicht nur den aktuellen Dateistand — ein Secret, das
in einem Zwischencommit hinzugefügt und später wieder gelöscht wurde,
steht trotzdem dauerhaft in der Historie.

Im Repository-Ordner (`C:\AILIZA`):

```powershell
# Ziel-Remote und Ziel-Branch bestimmen, statt origin/main anzunehmen.
# Wer auf einen anderen Branch pusht, prüft sonst den falschen Bereich.
$remote = "origin"
$zielBranch = "main"          # bei Bedarf anpassen

git fetch $remote $zielBranch
$basis = (git merge-base "$remote/$zielBranch" HEAD)

gitleaks git --config .gitleaks.toml `
  --log-opts "$basis..HEAD" `
  --redact --no-banner --exit-code 1 .
```

Ergebnis lesen:

- `no leaks found` → in Ordnung.
- `leaks found: N` → **nicht pushen.** Weiter bei Abschnitt 4.

> `git merge-base` statt `origin/main..HEAD`: Ist der Zielbranch
> zwischenzeitlich weitergelaufen, würden sonst fremde Commits mitgeprüft
> oder eigene übersehen. Die CI ermittelt den Bereich genauso.

## 3. Zwischendurch: nur die geänderten Dateien

Schneller, für die laufende Arbeit — prüft die **bereits gestagten**
Änderungen:

```powershell
gitleaks git --config .gitleaks.toml --staged --redact --no-banner --exit-code 1 .
```

> Bewusst **ohne** ein vorangestelltes `git add .`: Ein Scan-Befehl darf
> nicht nebenbei den Staging-Bereich verändern und alles einsammeln, was
> gerade im Arbeitsverzeichnis liegt. Dateien bewusst und einzeln stagen,
> dann prüfen.

Das ersetzt den Scan aus Abschnitt 2 **nicht**, weil es frühere Commits
des Branches nicht ansieht.

## 4. Wenn etwas gefunden wird

1. **Den gefundenen Wert nirgends hinkopieren** — nicht in einen Chat,
   nicht in ein Ticket, nicht in eine Notiz. `--redact` sorgt dafür, dass
   gitleaks ihn gar nicht erst ausgibt. Das ist Absicht.
2. Gemeldet werden nur **Regel, Datei, Zeile und Commit**. Mehr wird auch
   beim Weitergeben nicht genannt.
3. Ist es ein **echtes** Geheimnis: den Schlüssel beim Anbieter
   **zurückziehen und neu ausstellen**. Ihn nur aus dem Code zu löschen
   genügt nicht — er steht weiter in der Git-Historie.
4. Ist es ein **Fehlalarm**: siehe Abschnitt 5.

Zum Umgang mit bereits veröffentlichten Geheimnissen gilt Abschnitt 6 der
Push-Sicherheitsregel.

## 5. Fehlalarme

Die Regel `generic-api-key` ist eine Entropie-Heuristik: sie erkennt
„sieht aus wie ein Schlüssel", nicht „ist ein Schlüssel". In Testdateien
ist sie deshalb bereits abgeschaltet — siehe die Begründung in
`.gitleaks.toml`.

Für einen einzelnen, begründeten Fehlalarm außerhalb dieser Pfade:

```python
API_KEY = "..."  # gitleaks:allow
```

Der Kommentar gehört nur dorthin, wo nachweislich kein echtes Geheimnis
steht. Im Zweifel nachfragen statt unterdrücken.

**Nicht** die Regel global abschalten und **nicht** ganze Pfade
freistellen, um Ruhe zu haben. Anbieterspezifische Funde sind präzise und
praktisch nie Fehlalarme — sie gelten überall, auch in Testdateien.

## 6. Welche Anbieter erkannt werden

gitleaks bringt Regeln für OpenAI, Anthropic, GitHub, AWS und viele
weitere mit. Für **Groq** und **OpenRouter** gibt es **keine**
mitgelieferte Regel — beide sind deshalb in `.gitleaks.toml` als eigene
Regeln definiert (`ailiza-groq-api-key`, `ailiza-openrouter-api-key`).

Wird ein weiterer Anbieter aufgenommen, ist zuerst zu prüfen, ob gitleaks
eine Regel dafür mitbringt. Falls nicht, gehört eine eigene Regel in
`.gitleaks.toml`. `tests/test_secret_scan_rules.py` schlägt fehl, sobald
ein Anbieter in der Registry auftaucht, dessen Abdeckung nicht geklärt
ist.
