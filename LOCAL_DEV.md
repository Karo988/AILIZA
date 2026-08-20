# AILIZA lokal betreiben (verifizierter Windows-Pfad)

Stand: 20.08.2026. Der hier beschriebene Kandidat ist fuer Python 3.12 und
Node.js 22 oder neuer abgenommen. Externe KI bleibt standardmaessig gesperrt.

## 1. Einmalig installieren

Im Repository-Root `C:\AILIZA\current`:

```powershell
.\install.bat verified
Copy-Item .env.example apps\backend\.env
New-Item -ItemType Directory -Force C:\AILIZA\data, C:\AILIZA\backups
```

In `apps\backend\.env` mindestens diese lokalen Werte setzen:

```dotenv
AILIZA_EXTERNAL_LLM_ENABLED=false
AILIZA_DATABASE_URL=sqlite:///C:/AILIZA/data/ailiza.db
AILIZA_SECRET_KEY=<zufaelliges Secret mit mindestens 32 Zeichen>
AILIZA_ADMIN_USER=admin
AILIZA_ADMIN_PASSWORD=<einmaliges starkes Startpasswort>
```

Ein Secret kann lokal so erzeugt werden:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

`apps\backend\.env` darf nie eingecheckt oder in ein Backup des Repositories
kopiert werden. Nach dem ersten erfolgreichen Login das Startpasswort wechseln
und `AILIZA_ADMIN_PASSWORD` aus der Datei entfernen.

## 2. Start und Stop

```powershell
.\start_ailiza.bat
```

Das Backend ist unter `http://127.0.0.1:8001` erreichbar. Der Start fuehrt fuer
jede persistente Datenbank automatisch `alembic upgrade head` aus. Ein
unversioniertes Altschema wird nicht still veraendert; dessen Uebernahme muss
vorher bewusst geprueft werden:

```powershell
.\.venv\Scripts\python.exe -m apps.backend.alembic_adopt --help
```

Stop: Im Serverfenster `Strg+C` druecken.

## 3. Lokale Funktionspruefung

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
```

Die Browser-Oberflaeche wird separat gebaut:

```powershell
Set-Location apps\frontend
npm ci
npm run build
```

Der Node-Paketstand ist durch `apps/frontend/package-lock.json` gebunden.

## 4. Tests

```powershell
Set-Location C:\AILIZA\current
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest tests apps/backend/tests -q
```

Windows darf nur Tests ueberspringen, deren benoetigte Betriebssystemfaehigkeit
auf dem konkreten Host fehlt (Symlink-Privileg, POSIX-Dateimodus oder optionaler
PostgreSQL-Testserver). Inhaltliche Fehler sind keine zulaessigen Skips.

## 5. Verschluesseltes Backup und Restore

AILIZA vor einem geplanten Restore stoppen. Das Passwort wird interaktiv und
maskiert abgefragt; es darf nicht als Argument oder Umgebungsvariable erscheinen.

```powershell
# Backup
.\.venv\Scripts\python.exe scripts\ailiza_backup.py backup `
  --datenbank C:\AILIZA\data\ailiza.db `
  --ausgabe C:\AILIZA\backups\ailiza_20260820.bak

# Paket pruefen
.\.venv\Scripts\python.exe scripts\ailiza_backup.py verify `
  --paket C:\AILIZA\backups\ailiza_20260820.bak

# Bewusster Restore in eine neue Datei
.\.venv\Scripts\python.exe scripts\ailiza_backup.py restore `
  --paket C:\AILIZA\backups\ailiza_20260820.bak `
  --ziel C:\AILIZA\data\ailiza_restore_test.db
```

Nach jedem Backup `verify` ausfuehren. Mindestens quartalsweise einen Restore
in eine neue Datei proben und `/health`, Login und einen lokalen Chat gegen die
wiederhergestellte Datenbank testen. Backup-Passwort und Pakete getrennt
verwahren.

## 6. Update und Rueckfall

Vor einem Update: Datenbank-Backup erzeugen und pruefen. Danach:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\AILIZA\update_ailiza.ps1
.\install.bat verified
.\.venv\Scripts\python.exe -m pytest tests apps/backend/tests -q
```

Das Update-Skript erstellt zusaetzlich ein Quellcode-ZIP und akzeptiert nur
Fast-Forward-Git-Updates. Ein Quellcode-ZIP ersetzt kein Datenbank-Backup.

## 7. Bekannte Produktionssperren

Der lokale fail-closed Betrieb ist nicht automatisch eine Produktionsfreigabe.
Vor externem Betrieb muessen mindestens TLS/HSTS, konkrete CORS-Origins,
Provider-AVV/DPA, Geheimnisverwaltung, Produktions-Memory-Audit, externes
Backupziel, Alarmierung und eine dokumentierte Restore-Verantwortung abgenommen
sein. Bis dahin bleibt `AILIZA_EXTERNAL_LLM_ENABLED=false`.
