# AILIZA — Autarker Betrieb (ohne Render/Neon)

Stand: 20.07.2026

Ziel: AILIZA auf eigenem Server, Mini-PC, NAS oder VPS betreiben — ohne
Abhängigkeit von einem Cloud-Anbieter. Nutzer, Chats, Projekte, Policies
und Logs bleiben dauerhaft im eigenen `/data`-Volume erhalten.

## Start

```bash
docker compose up -d
```

Das startet AILIZA mit:
- `AILIZA_DATABASE_URL=sqlite:////data/ailiza.sqlite`
- Daten im benannten Docker-Volume `ailiza_data` (überlebt Neustarts,
  Rebuilds und `docker compose down` — nur `docker compose down -v`
  löscht es).

Secrets (`AILIZA_SECRET_KEY`, `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, ...)
gehören **nicht** in `docker-compose.yml` eingecheckt. Eigene `.env`-Datei
anlegen (siehe `apps/backend/.env.example` falls vorhanden) und in
`docker-compose.yml` per `env_file: .env` einbinden.

## Backup

`scripts/ailiza_backup.py` sichert die SQLite-Datenbank konsistent über
die SQLite-Backup-API (nicht per Dateikopie — sonst fehlen Daten, die noch
in der `-wal`-Datei liegen) und verschlüsselt die Sicherung anschließend
(AES-256-GCM, Schlüssel per scrypt aus einem Passwort abgeleitet, das nur
über stdin/maskierte Eingabe entgegengenommen wird — nie als Argument).

**Achtung:** `sqlite3` ist im Container NICHT installiert (Dockerfile
installiert nur `libsqlite3-dev`). Das Skript läuft daher gegen das
gemountete Docker-Volume, ohne den Container selbst zu benutzen:

```bash
python3 scripts/ailiza_backup.py backup \
  --datenbank /var/lib/docker/volumes/ailiza_ailiza_data/_data/ailiza.sqlite \
  --ausgabe ./backups/ailiza_$(date +%Y%m%d_%H%M%S).bak
# Passwort wird interaktiv abgefragt (zweimal zur Bestätigung).
```

Danach immer prüfen, dass die Sicherung tatsächlich lesbar und inhaltlich
nicht leer ist:

```bash
python3 scripts/ailiza_backup.py verify --paket ./backups/ailiza_<datum>.bak
```

Backups regelmäßig (z. B. täglich per Cron) an einen zweiten Ort kopieren
(externe Platte, verschlüsselter Cloud-Speicher außerhalb der EU-Grenzen
nur nach Prüfung). Kein automatischer Backup-Job ist in AILIZA selbst
eingebaut — das ist bewusst Betreiber-Verantwortung.

## Restore

```bash
docker compose stop ailiza
python3 scripts/ailiza_backup.py restore \
  --paket ./backups/ailiza_<datum>.bak \
  --ziel /var/lib/docker/volumes/ailiza_ailiza_data/_data/ailiza.sqlite \
  --force
docker compose start ailiza
```

`--force` erst setzen, nachdem die aktuelle (womöglich beschädigte)
Datenbank selbst gesichert wurde — das Skript überschreibt ohne
`--force` keine vorhandene Zieldatei.

## DSGVO-Hinweise

- **Löschung (Art. 17):** Nutzerlöschung läuft über die bestehenden
  Admin-/Auth-Endpoints der App, nicht über direktes Datei-Editieren.
  Nach Löschung ältere Backups mit einbeziehen — Backups, die gelöschte
  Nutzerdaten noch enthalten, unterliegen derselben Löschpflicht nach
  Ablauf der Aufbewahrungsfrist.
- **Aufbewahrung:** Backup-Rotationsfrist selbst festlegen und
  dokumentieren (z. B. 30 Tage rollierend). Kürzere Frist = weniger
  Risiko bei Löschanfragen.
- **Zugriff:** `/data`-Volume liegt auf dem eigenen Server — Zugriff
  entsprechend betriebssystemseitig absichern (Dateiberechtigungen,
  Festplattenverschlüsselung empfohlen).

## Production ohne AILIZA_DATABASE_URL

Wenn `AILIZA_ENV=production` gesetzt ist, aber `AILIZA_DATABASE_URL`
fehlt, startet AILIZA trotzdem (kein Hard-Block) — aber mit einer
deutlichen Warnung im Log, da Daten sonst bei jedem Neustart verloren
gehen. Für autarken Betrieb immer explizit setzen:

```
AILIZA_DATABASE_URL=sqlite:////data/ailiza.sqlite
```

## Render/Neon bleibt kompatibel

Diese Änderungen ändern nichts an der bestehenden Render+Neon-Route.
Dieselbe Env-Var (`AILIZA_DATABASE_URL`) steuert beide Betriebsarten:
Postgres-Connection-String → Neon/Cloud, `sqlite:////data/...` →
autarker Betrieb.

## Optional: Postgres

Für mehrere gleichzeitige Nutzer/höhere Last kann später ein lokaler
Postgres-Container ergänzt werden (eigener `db`-Service in
`docker-compose.yml`, `AILIZA_DATABASE_URL=postgresql+psycopg://...`).
Nicht Teil dieses Auftrags — SQLite genügt für den Einstieg.

## Start unter Windows (Docker Desktop)

Docker Desktop muss laufen. In PowerShell im Projektordner:

```powershell
# 1. Secret-Datei aus der Vorlage anlegen (einmalig)
Copy-Item .env.example .env

# 2. Ein starkes Secret erzeugen und in .env eintragen
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Ausgabe kopieren und in .env bei AILIZA_SECRET_KEY einsetzen.

# 3. Starten
docker compose up -d --build

# 4. Oberflaeche oeffnen
Start-Process "http://localhost:8000"
```

Die Datei `.env` wird nie committet (steht in `.gitignore`).

**Ohne gueltiges Secret startet der Container bewusst nicht.** Ist
`AILIZA_SECRET_KEY` nicht gesetzt oder kuerzer als 32 Zeichen, bricht der
Start mit einer verstaendlichen Meldung ab, statt mit stillschweigend
deaktivierter Authentifizierung weiterzulaufen. Der Secret-Wert selbst wird
dabei nie ausgegeben.

Logs ansehen bzw. stoppen:

```powershell
docker compose logs -f
docker compose down          # Daten im Volume ailiza_data bleiben erhalten
```

