# AILIZA — Produktionsfreigabe Phasen 5–6

Stand: 31.08.2026

Status: Vorlage. Kein ausgefülltes Feld darf ohne Beleg als erledigt markiert
werden. Secrets, Zugangsdaten und Vertragsdokumente gehören nicht ins Repo.

## Phase 5 — Produktionsinfrastruktur

| Nachweis | Status | Einzutragender Beleg |
|---|---|---|
| Öffentliche Domain festgelegt | live erreichbar | `https://ailiza-1.onrender.com/health`, HTTP 200 am 31.08.2026 |
| TLS-Zertifikat gültig | teilweise belegt | TLS-Verifikation durch `curl` und HTTP 200 am 31.08.2026; Aussteller noch protokollieren |
| HTTP→HTTPS am Render-Edge und HSTS geprüft | blockiert | Redirect 301 bestanden; HSTS-Header am 31.08.2026 noch nicht vorhanden |
| CORS ohne Wildcard | blockiert | Vorlage ist restriktiv; Live-System antwortete am 31.08.2026 noch mit `access-control-allow-origin: *` |
| Produktionsmodus aktiv | vorbereitet | `AILIZA_ENV=production` in `render.yaml` |
| Externe LLMs bewusst freigegeben | offen | Providerliste; sonst `false` belassen |
| Externes verschlüsseltes Backupziel | offen | System/Region, keine Zugangsdaten |
| Backupplan und Aufbewahrung | offen | Häufigkeit und Frist |
| Alarmierung bei Backupfehler | offen | Kanal und verantwortliche Rolle |
| Wiederherstellungstest | offen | Datum, Ergebnis, RPO und RTO |
| Monitoring | offen | Verfügbarkeit, Fehler, Audit-Integrität |
| Notfallübung | offen | Datum und Protokollverweis |

Empfohlener Mindestplan: tägliches verschlüsseltes Backup, getrenntes externes
Ziel, automatische Fehleralarmierung und vierteljährlicher Restore-Test. RPO
und RTO bleiben Owner-Entscheidungen und müssen vor Produktion eingetragen
werden.

### Live-Pruefung vom 31.08.2026

Oeffentliche, nicht authentifizierte Pruefung gegen die oben genannte Domain:

- `http://.../health` leitete mit HTTP 301 exakt auf die HTTPS-URL um;
- `https://.../health` antwortete mit HTTP 200 und dem erwarteten
  Service-Status;
- der HTTPS-Response enthielt noch keinen `Strict-Transport-Security`-Header;
- erlaubte und absichtlich falsche Praefix-Origin erhielten beide noch
  `access-control-allow-origin: *`.

Ergebnis: Der aktuell deployte Stand ist **nicht produktionsfreigegeben**.
Nach Deployment des geprueften Kandidaten muessen HSTS und beide
CORS-Gegenproben wiederholt werden; erst die restriktive Antwort darf das Gate
schliessen.

## Phase 6 — Geschäftliche Abnahme

| Nachweis | Status | Einzutragender Beleg |
|---|---|---|
| AVV/DPA Groq geprüft und abgeschlossen | offen | Ablageort, Prüfer, Datum |
| AVV/DPA jedes weiteren aktiven Providers | offen | Provider, Ablageort, Datum |
| Drittlandtransfer/SCC geprüft | offen | Datenschutzprüfung |
| System Owner benannt | offen | Name/Rolle außerhalb sensibler Repo-Daten |
| Datenschutzverantwortung benannt | offen | Name/Rolle |
| Restore-Verantwortung benannt | offen | Name/Rolle |
| Incident-Kanal eingerichtet | offen | Kanalbezeichnung |
| Produktions-Memory-Audit Exit 0 | offen | Zeitpunkt, DB-Kennung, Report-Hash |
| Formale Produktionsabnahme | offen | Commit, Migration, Datum, Freigebende |

## Formale Freigabe

```text
Deployter Commit:
Migrationsstand:
Produktionsadresse:
Memory-Audit (Zeitpunkt/Exit/Report-Hash):
Backup-Restore-Test (Datum/RPO/RTO):
Aktive Provider mit AVV/DPA-Nachweis:
System Owner:
Datenschutzverantwortung:
Restore-Verantwortung:
Freigabeentscheidung: FREIGEGEBEN / NICHT FREIGEGEBEN
Datum und Freigebende:
```

Bis alle Pflichtfelder belegt sind, lautet der Produktionsstatus
`NICHT FREIGEGEBEN`.

Technische Vorprüfung auf Render, ohne Ausgabe von Secret-Werten:

```bash
python scripts/production_preflight.py
```

Nur Exit 0 erlaubt die weitere Abnahme; Exit 0 ersetzt keinen Backup-,
Restore-, Vertrags- oder Memory-Audit-Nachweis.
