# Secret-Scan lokal ausführen

Kurzanleitung für den schnellen Scan während der Arbeit.

**Das hier ist eine Anleitung, kein Zwang.** Es gibt bewusst keinen
Pre-Commit-Hook, der Commits blockiert. Verbindlich ist der CI-Job
`secret-scan` in `.github/workflows/ci.yml` — der läuft bei jedem Push
und schlägt bei einem Fund fehl.

Verwandte Dokumente:
- `docs/AILIZA_PUSH_SICHERHEITSREGEL.md` — die verbindliche Regel
- `.gitleaks.toml` — die Konfiguration, die lokal und in der CI gilt

## 1. Einmalig installieren

Windows (PowerShell, mit winget):

```powershell
winget install gitleaks
```

Alternativ (alle Systeme): das passende Archiv der Version **8.28.0** von
<https://github.com/gitleaks/gitleaks/releases/tag/v8.28.0> herunterladen,
entpacken und die Datei `gitleaks` in einen Ordner legen, der im `PATH`
liegt.

Prüfen, ob es funktioniert:

```powershell
gitleaks version
```

> Die CI verwendet fest die Version 8.28.0. Eine deutlich neuere Version
> kann lokal andere Ergebnisse liefern als die CI — das ist kein Fehler,
> aber gut zu wissen, wenn die Zahlen auseinandergehen.

## 2. Vor dem Push: den neuen Commit-Bereich prüfen

Das ist der Scan, der dem verbindlichen Prüfschritt 3 entspricht. Er prüft
**die neuen Commits**, nicht nur den aktuellen Dateistand — ein Secret, das
in einem Zwischencommit hinzugefügt und später wieder gelöscht wurde,
steht trotzdem dauerhaft in der Historie.

Im Repository-Ordner `C:\AILIZA\current`:

```powershell
git fetch origin
gitleaks git --config .gitleaks.toml --log-opts "--no-merges origin/main..HEAD" --redact --no-banner --exit-code 1 .
```

Ergebnis lesen:

- `no leaks found` → in Ordnung.
- `leaks found: N` → **nicht pushen.** Weiter bei Abschnitt 4.

## 3. Zwischendurch: nur die geänderten Dateien

Schneller, für die laufende Arbeit — prüft die gestagten Änderungen:

```powershell
git add .
gitleaks git --config .gitleaks.toml --staged --redact --no-banner --exit-code 1 .
```

Das ersetzt den Scan aus Abschnitt 2 **nicht**, weil es frühere Commits
des Branches nicht ansieht.

## 4. Wenn etwas gefunden wird

1. **Den gefundenen Wert nirgends hinkopieren** — nicht in einen Chat,
   nicht in ein Ticket, nicht in eine Notiz. `--redact` sorgt dafür, dass
   gitleaks ihn gar nicht erst ausgibt. Das ist Absicht.
2. Gemeldet werden nur **Kategorie, Datei und Zeile**. Mehr wird auch
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
freistellen, um Ruhe zu haben. Anbieterspezifische Funde (AWS, GitHub,
OpenAI, Anthropic, Groq, private Schlüssel) sind präzise und praktisch nie
Fehlalarme — die gelten überall, auch in Testdateien.
