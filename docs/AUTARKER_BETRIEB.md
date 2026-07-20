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

SQLite ist eine einzelne Datei — Backup heißt: Datei konsistent kopieren.

**Variante A — Container läuft weiter (empfohlen, konsistent via SQLite-Backup-API):**

```bash
docker compose exec ailiza sqlite3 /data/ailiza.sqlite ".backup /data/backup_$(date +%Y%m%d_%H%M%S).sqlite"
docker cp $(docker compose ps -q ailiza):/data/backup_<timestamp>.sqlite ./backups/
```

**Variante B — Container kurz stoppen:**

```bash
docker compose stop ailiza
docker run --rm -v ailiza_ailiza_data:/data -v $(pwd)/backups:/backup alpine \
  cp /data/ailiza.sqlite /backup/ailiza_$(date +%Y%m%d).sqlite
docker compose start ailiza
```

Backups regelmäßig (z. B. täglich per Cron) an einen zweiten Ort kopieren
(externe Platte, verschlüsselter Cloud-Speicher außerhalb der EU-Grenzen
nur nach Prüfung). Kein automatischer Backup-Job ist in AILIZA selbst
eingebaut — das ist bewusst Betreiber-Verantwortung.

## Restore

```bash
docker compose stop ailiza
docker run --rm -v ailiza_ailiza_data:/data -v $(pwd)/backups:/backup alpine \
  cp /backup/ailiza_<datum>.sqlite /data/ailiza.sqlite
docker compose start ailiza
```

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
