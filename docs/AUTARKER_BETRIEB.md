# AILIZA — Autarker Betrieb (ohne Render/Neon)

Stand: 20.07.2026

Ziel: AILIZA auf eigenem Server, Mini-PC, NAS oder VPS betreiben — ohne
Abhängigkeit von einem Cloud-Anbieter. Nutzer, Chats, Projekte, Policies
und Logs bleiben dauerhaft im eigenen `/data`-Volume erhalten.

## Aufteilung: was liegt wo?

Karo-Entscheidung: **immer ein Stand auf dem eigenen Rechner und einer bei
GitHub** — aber strikt getrennt nach Art des Inhalts.

| | Auf dem Rechner | Bei GitHub |
|---|---|---|
| Programmcode | ✅ (Arbeitskopie) | ✅ (Versionierung, Sicherung) |
| Konfigurationsvorlage `.env.example` | ✅ | ✅ (ohne echte Werte) |
| Eigene `.env` mit Schlüsseln | ✅ | ❌ **nie** |
| Datenbank (`ailiza.sqlite`) | ✅ | ❌ **nie** |
| Chats, Nutzer, Logs | ✅ | ❌ **nie** |

**Warum die Trennung nicht verhandelbar ist:** In der Datenbank stehen
personenbezogene Daten. Ein Repository ist dafür kein zulässiger Speicherort —
Daten in der Git-Historie lassen sich praktisch nicht mehr entfernen, und bei
einem öffentlichen Repository wären sie für jeden abrufbar. Das wäre ein
DSGVO-Verstoß, unabhängig davon, wo AILIZA selbst läuft.

Technisch abgesichert über `.gitignore`: `*.db`, `*.sqlite`, `.env` und
`secrets/` sind blockiert. Einzige bewusste Ausnahme ist
`apps/backend/.env.example` — eine Vorlage ohne echte Werte.

Prüfen lässt sich das jederzeit:

```bash
git check-ignore -v data/ailiza.sqlite    # muss eine Regel ausgeben
git add --dry-run .env                    # muss abgelehnt werden
```

## Erstinstallation auf dem eigenen Rechner

Voraussetzung: Git und Docker Desktop installiert.

```bash
# 1. Code holen
git clone https://github.com/Karo988/AILIZA.git
cd AILIZA

# 2. Konfiguration anlegen
cp apps/backend/.env.example .env

# 3. Schlüssel erzeugen und in .env bei AILIZA_SECRET_KEY eintragen
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

⚠️ **Den Schlüssel einmal setzen und sicher aufbewahren.** Aus ihm wird der
Schlüssel abgeleitet, mit dem Chatinhalte verschlüsselt in der Datenbank
liegen. Wird er später geändert, sind alle bereits gespeicherten Chats
unlesbar — auch wenn die Daten noch vorhanden sind.

An `docker-compose.yml` ist **nichts** zu ändern — die `.env` wird bereits
eingebunden (`env_file`, mit `required: false`). Danach starten (siehe
nächster Abschnitt). Beim ersten Start legt AILIZA die Datenbank selbst an.

Fehlt der Schlüssel, startet AILIZA trotzdem, aber die Anmeldung
funktioniert nicht. Im Protokoll (`docker compose logs ailiza`) steht dann
ein entsprechender Hinweis.

## Aktualisieren

```bash
git pull                      # neuen Stand von GitHub holen
docker compose up -d --build  # neu bauen und starten
```

Die Datenbank liegt im Volume `ailiza_data` und ist davon nicht betroffen —
ein Update löscht keine Daten. Schema-Änderungen werden beim Start
automatisch nachgezogen.

**Vor jedem Update ein Backup anlegen** (siehe Abschnitt „Backup"). Ein
Update ist der einzige Zeitpunkt, an dem sich am Datenbestand etwas ändern
kann.

## Start

```bash
docker compose up -d
```

Das startet AILIZA mit:
- `AILIZA_DATABASE_URL=sqlite:////data/ailiza.sqlite`
- Bindung an `127.0.0.1:8000` — nur auf diesem Rechner erreichbar
- Externe KI ausgeschaltet (`AILIZA_EXTERNAL_LLM_ENABLED=false`)
- Daten im Volume `ailiza_data` (überlebt Neustarts, Rebuilds und
  `docker compose down` — nur `docker compose down -v` löscht es)

Erreichbar unter `http://localhost:8000`.

Secrets (`AILIZA_SECRET_KEY`, `GROQ_API_KEY`, ...) gehören **nicht** in
`docker-compose.yml`, sondern in die `.env` im Projektstamm — sie ist
bereits eingebunden und durch `.gitignore` blockiert.

**Vorrang beachten:** Werte unter `environment:` in `docker-compose.yml`
stechen die `.env`. `AILIZA_ENV`, `AILIZA_DATABASE_URL` und
`AILIZA_EXTERNAL_LLM_ENABLED` lassen sich deshalb **nicht** über die `.env`
ändern. Die externe KI ist bewusst dort festgehalten, damit sie nicht durch
einen versehentlich in die `.env` geratenen Eintrag aktiviert wird — sie
einzuschalten ist eine bewusste Entscheidung mit Datenschutzfolgen (siehe
`apps/backend/.env.example`).

## Backup

**Kurz: `backup-local.cmd` doppelklicken.** Was dabei passiert und warum,
steht hier.

### Warum nicht einfach die Datei kopieren

Zwei Gründe, beide führen zu einer scheinbar vorhandenen, aber wertlosen
Sicherung:

1. **SQLite darf im Betrieb nicht per Dateikopie gesichert werden.** Im
   WAL-Modus liegen noch nicht übertragene Änderungen in einer separaten
   `-wal`-Datei. Eine Kopie allein der Hauptdatei ist unvollständig oder
   beschädigt.
2. **Ohne den Schlüssel ist die Datenbank unlesbar.** Chattitel, Chatinhalte,
   Projektnamen und -beschreibungen liegen mit AES-256-GCM verschlüsselt
   (`apps/backend/governance/field_crypto.py`). Der Schlüssel wird aus
   `AILIZA_SECRET_KEY` abgeleitet und steht in der `.env` — nicht in der
   Datenbank. Datenbank und `.env` gehören deshalb **immer zusammen**.

Eine frühere Fassung dieser Anleitung rief `sqlite3` im Container auf. Dieses
Programm ist dort **nicht installiert** — das Dockerfile installiert nur
`libsqlite3-dev`, also die Bibliothek, nicht das Kommandozeilenwerkzeug. Die
Anleitung konnte also nie funktionieren. `scripts/ailiza_backup.py` nutzt
stattdessen die SQLite-Backup-Schnittstelle der Python-Standardbibliothek.

### Sicherung erstellen

Windows:

```
backup-local.cmd        (Doppelklick)
```

Andere Systeme:

```bash
python3 scripts/ailiza_backup.py backup --out ~/ailiza-backups
```

Das Skript sichert konsistent bei laufendem AILIZA, prüft die Sicherung mit
`PRAGMA integrity_check`, packt Datenbank und `.env` zusammen und
verschlüsselt das Paket mit einem Passwort (scrypt + AES-256-GCM). Daneben
entsteht eine `.sha256`-Prüfsummendatei.

Die Ablage erfolgt bewusst **außerhalb** des Projektordners
(`%LOCALAPPDATA%\AILIZA\backups`), damit das Paket nicht versehentlich per
`git add -f` in ein Repository geraten kann. `.gitignore` allein ist keine
Sperre.

### Abnahme — ohne sie ist es keine Sicherung

```bash
python3 scripts/ailiza_backup.py verify --archive <paket>
```

Geprüft wird in fünf Schritten: Prüfsumme, Entschlüsselung des Pakets,
`integrity_check` der Datenbank, Tabellen- und Chatzählung, und zuletzt der
entscheidende Schritt — **ein verschlüsselter Chattitel wird mit dem
mitgesicherten Schlüssel tatsächlich im Klartext gelesen**.

Erst dieser letzte Schritt beweist, dass Datenbank und Schlüssel
zusammenpassen. Eine Sicherung, die mit der falschen `.env` erstellt wurde,
besteht alle vorherigen Prüfungen: Prüfsumme stimmt, Datenbank ist
unversehrt, Chats sind vorhanden — die Inhalte wären trotzdem für immer
unlesbar. Genau diesen Fall fängt Schritt 5 ab.

### Wiederherstellung

```bash
python3 scripts/ailiza_backup.py restore --archive <paket> --to <zielpfad>
```

Bricht ab, wenn am Zielpfad bereits eine Datenbank liegt (`--force`
überschreibt bewusst). Die mitgesicherte `.env` wird als
`env-aus-sicherung` daneben abgelegt und muss als `.env` übernommen werden,
**bevor** AILIZA startet — sonst sind die wiederhergestellten Chats
unlesbar.

In das Docker-Volume zurückspielen:

```bash
docker compose stop ailiza
docker run --rm -v ailiza_ailiza_data:/data -v "$(pwd)":/quelle alpine \
  cp /quelle/ailiza.sqlite /data/ailiza.sqlite
docker compose start ailiza
```

Der Volume-Name `ailiza_ailiza_data` gilt, weil `docker-compose.yml` den
Projektnamen fest auf `ailiza` setzt. Ohne diese Festlegung leitet Compose
ihn vom Ordnernamen ab — ein umbenannter Ordner hätte dann ein anderes,
leeres Volume zur Folge.

### Zweite Kopie auf externem Datenträger — Pflicht, nicht Kür

`%LOCALAPPDATA%\AILIZA\backups` liegt üblicherweise auf **derselben
Festplatte** wie AILIZA. Das schützt vor versehentlichem Löschen — nicht vor
Festplattendefekt, Diebstahl oder einem Verschlüsselungstrojaner, der alle
erreichbaren Laufwerke befällt.

Das Sicherungspaket ist bereits mit scrypt + AES-256-GCM verschlüsselt und
kann deshalb ohne weitere Vorkehrung kopiert werden:

```
copy "%LOCALAPPDATA%\AILIZA\backups\ailiza_*.ailiza-backup*" E:\AILIZA-Sicherung\
```

Beide Dateien mitnehmen — das Paket **und** die `.sha256`-Prüfsummendatei.
Ohne sie entfällt bei der Abnahme die Manipulationsprüfung.

Den externen Datenträger nach dem Kopieren **abziehen**. Ein dauerhaft
angestecktes Laufwerk wird von Schadsoftware genauso verschlüsselt wie die
interne Platte.

Die Abnahme läuft auch auf der Kopie:

```bash
python3 scripts/ailiza_backup.py verify --archive E:\AILIZA-Sicherung\ailiza_….ailiza-backup
```

### Regelmäßigkeit

AILIZA bringt keinen automatischen Sicherungsauftrag mit — das ist bewusst
Sache der Betreiberin. Mindestens zwei Ablageorte, einer davon getrennt vom
Rechner. Vor jedem Update eine Sicherung.

### Geprüfte Randfälle

Die Sicherung wurde gegen die Fälle geprüft, die eine Dateikopie scheitern
lassen würden:

| Fall | Ergebnis |
|---|---|
| `.db`, `-wal` und `-shm` vorhanden, Verzeichnis schreibgeschützt | vollständig gesichert |
| Schreibvorgang **während** der Sicherung | konsistent, laufende Änderungen enthalten |
| `-shm` fehlt (AILIZA sauber gestoppt) | funktioniert |
| `-wal` vorhanden, `-shm` fehlt (Absturzfall) | funktioniert, **kein stiller Datenverlust** — nur im WAL liegende Änderungen sind enthalten |
| Pfad mit Leerzeichen und Umlauten (`C:\Karo Müller\…`) | funktioniert |
| Falsches Passwort / manipuliertes Paket / falscher Schlüssel | jeweils erkennbar abgelehnt |

Der vierte Fall ist der heikelste: Läge der WAL-Inhalt nicht in der
Sicherung, wären die letzten Änderungen unbemerkt verloren — die Sicherung
sähe trotzdem fehlerfrei aus.

## Zugriff von weiteren eigenen Geräten (Laptop, Handy)

AILIZA ist an `127.0.0.1` gebunden und damit nur auf dem Rechner erreichbar,
auf dem sie läuft. Das ist die sichere Grundeinstellung und sollte so
bleiben — die Bindung aufzubohren würde AILIZA für jedes Gerät im selben
WLAN unverschlüsselt zugänglich machen.

Für den Zugriff von eigenen Geräten stattdessen ein **privates
Mesh-Netzwerk** (z. B. Tailscale, WireGuard-basiert):

1. Auf PC, Laptop und Handy installieren, überall mit demselben Konto anmelden
2. Auf dem AILIZA-Rechner: `tailscale serve --bg 8000`
3. Von den anderen Geräten die angezeigte `https://…ts.net`-Adresse aufrufen

Damit gilt:

- AILIZA bleibt an `127.0.0.1` gebunden; das private Netz reicht sie weiter
- **HTTPS ist enthalten** — nötig, weil die Sitzungscookies bei
  `AILIZA_ENV=production` mit `secure=True` gesetzt werden und über eine
  unverschlüsselte Verbindung gar nicht ankämen
- Kein Port im Router offen, nicht aus dem Internet erreichbar
- Keine Domain, kein Zertifikatskauf
- Ein einziger Datenbestand — kein Abgleich zwischen Geräten nötig

Das Frontend verwendet relative Adressen (`const API = ""`), funktioniert
also unter jedem Hostnamen ohne Anpassung.

**Einschränkungen, die man kennen muss:**

- Der AILIZA-Rechner muss laufen. Ist er aus, kommt kein anderes Gerät heran.
- Tailscale vermittelt die Verbindung über einen Dienst des Anbieters (US-
  Unternehmen). Der Datenverkehr ist Ende-zu-Ende verschlüsselt, Inhalte
  sieht der Anbieter nicht — die Vermittlung findet aber dort statt. Wer das
  vermeiden will, betreibt *Headscale* selbst.
- Am Programmcode arbeitet man von anderen Geräten über GitHub, nicht über
  dieses Netz. Code und Daten bleiben getrennt.

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
