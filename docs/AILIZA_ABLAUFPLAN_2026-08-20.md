# AILIZA – Ablaufplan und technische Abnahme

Stand: 20.08.2026
Basis-Commit: `e07f09cf5b3e72417d6ac05d755a4d495a0b68d6`

> **Status: Lokal lauffaehig und technisch abgenommen; Produktionsfreigabe
> bleibt bis zum Abschluss der externen Betriebs- und Compliance-Punkte gesperrt.**

Der Bericht `AILIZA_GESAMTSTAND_ZUSAMMENGEFUEHRT.md` wurde als Referenz
behandelt. Massgeblich fuer Umsetzung und Abnahme sind der lokale Code, die
Migrationen, Tests und praktischen Betriebsproben.

## Definition „lokal lauffaehig“

1. Eine reproduzierbare Python-3.12-Umgebung kann installiert werden.
2. Eine persistente Datenbank wird beim App-Start ausschliesslich per Alembic
   bis `head` migriert; ein konfliktbehaftetes unversioniertes Schema scheitert
   geschlossen.
3. Die konsolidierte Backend-Suite hat keine Fehler.
4. Das Backend startet mit deaktiviertem externem LLM-Zugriff und intakter
   Governance-Konfiguration.
5. Health, Login, Prüfbeleg und lokaler Chat-Kernablauf funktionieren;
   externe Aufgaben bleiben bei aktivem Kill-Switch geschlossen.
6. Der Frontend-Produktionsbuild ist reproduzierbar.
7. Verschluesseltes Backup, Verify, Restore und Start gegen die
   wiederhergestellte Datenbank funktionieren praktisch.
8. Start, Stop, Update, Test und Restore sind dokumentiert.

## Abgearbeiteter Ablaufplan

| Nr. | Arbeitspaket | Abnahmekriterium | Ergebnis |
|---:|---|---|---|
| 1 | Wahrheitsquellen und Ist-Stand | Bericht gegen Repository, Status, Migrationen und Tests abgeglichen | erledigt |
| 2 | Lokale Runtime | Python 3.12, `pip check`, vollständiger Lockstand | erledigt |
| 3 | Migrationen | Persistenter Lifespan nutzt `alembic upgrade head`; Konfliktschema fail-closed | erledigt |
| 4 | Windows-Lauffaehigkeit | relatives Startskript, ASCII-CLI, Backup ohne POSIX-only-Aufruf, capability-basierte Tests | erledigt |
| 5 | Backend-Smoke | frische SQLite-DB, Alembic-Head, `/health` HTTP 200 | erledigt |
| 6 | Gesamtsuite | keine Fehler in `tests/` und `apps/backend/tests/` | erledigt |
| 7 | Frontend | Vite-Produktionsbuild erzeugt `dist/index.html` | erledigt |
| 8 | Login/Chat | Admin-Seed, Login, Prüfbeleg und lokaler DSGVO-Chat; externer Call fail-closed | erledigt |
| 9 | Backup/Restore | AES-GCM-Backup, Verify, Restore, Integrität, Health und Login gegen Restore | erledigt |
| 10 | Betriebsuebergabe | verifizierte Installations- und Betriebsanleitung, Sperren dokumentiert | lokal erledigt |

## Wesentliche technische Korrekturen

- Der FastAPI-Lifespan verwendet fuer persistente SQLite-/PostgreSQL-
  Datenbanken Alembic als einzige Schema-Autoritaet. `create_all` und direkte
  SQLite-ALTERs bleiben nur Legacy-/In-Memory-Testhelfer.
- Der Governance-Hash normalisiert CRLF nach LF. Damit ist das Manifest unter
  Windows und Linux stabil, erkennt aber weiterhin echte Inhaltsaenderungen.
- Windows-Tests ueberspringen Symlinks nur bei dem konkret nachgewiesenen
  WinError 1314. POSIX-Modus `0600` wird nur auf POSIX geprueft; Verschluesselung
  und Restore bleiben plattformuebergreifend getestet.
- Sandbox-Pfade werden separator- und gross-/kleinschreibungsneutral bewertet.
  Ein bewusst unter `AppData` liegendes Workspace macht nicht automatisch alle
  eigenen Dateien sensitiv; Symlink-Ziele ausserhalb bleiben gesperrt.
- PDF ist Teil des aktuellen Wissensimports; der veraltete Ablehnungstest wurde
  an den implementierten Funktionsumfang angepasst.
- Automatisierte Score-Zeilen werden zusammen mit automatisierten Empfehlungen
  geschwaerzt.
- Redigierte personenbezogene LLM-Anfragen werden an einen bereits Registry-
  und Provider-Policy-geprueften Kandidaten gebunden. Der End-to-End-Beleg nutzt
  fuer PII den lokalen Provider statt einer AVV-losen externen Ausnahme.
- Paketimporte wurden gegen doppelte Top-Level-Datenbankmodule gehaertet; die
  Komponentensuite ist dadurch reihenfolgeunabhaengig.
- Der vollstaendige, getestete Python-3.12-Stand ist in
  `requirements-lock-py312.txt` gebunden. Das Frontend bleibt durch
  `package-lock.json` gebunden.

## Abnahmenachweis vom 20.08.2026

### Backend und Tests

- `pip check`: keine defekten Abhaengigkeiten.
- Governance-Manifest: `ok`, inklusive LF/CRLF-Regressionstest.
- Release-Suite:
  `2131 passed, 18 skipped, 1 xfailed, 0 failed` in 380,89 Sekunden.
- Die Skips sind explizite Host-/Optionalitaetsfaelle, insbesondere fehlendes
  Windows-Symlink-Privileg, POSIX-Modusbits und nicht bereitgestellte optionale
  PostgreSQL-/Integrationsumgebungen; keine fachliche Abweichung wird pauschal
  uebersprungen.
- Sechs Warnungen bleiben ohne Abnahmefehler: absichtlicher Short-Secret-Test,
  Python-3.12-SQLite-Datetime-Deprecation, `utcnow()`-Deprecation und ein alter
  Demo-Test, der einen Wert zurueckgibt.

### Praktischer Kernablauf

- Frische persistente SQLite-Datenbank beim Start bis Revision
  `f9a3c61e07b2` migriert.
- `GET /health`: HTTP 200, Status `ok`.
- Admin-Seed und Login: HTTP 200.
- `/api/policy-redact`: Prüfbeleg ausgestellt.
- Lokale Frage „Was ist die DSGVO?“: Status `completed`.
- Externe Schreibaufgabe bei `AILIZA_EXTERNAL_LLM_ENABLED=false`: kontrolliert
  mit `kill_switch_active` beendet, kein externer Fallback.

### Frontend

- Vite 8.2.1: Produktionsbuild erfolgreich.
- Ergebnis: `dist/index.html`, 162,52 kB (gzip 44,18 kB).

### Backup und Restore

- Verschluesseltes Paket erstellt und entschluesselt.
- `integrity_check=ok`, `foreign_key_check=ok`.
- 35 Tabellen und 34 Zeilen im Abnahmepaket verifiziert.
- Restore enthaelt den Admin-Datensatz und Alembic-Head `f9a3c61e07b2`.
- Anwendung gegen Restore gestartet: Health HTTP 200, Login HTTP 200.

## Kandidatenbindung

Kandidaten-Hash (29 Dateien):
`57e0f6981367876ce49038a1e4365df670834be8cabcaf99418cf8a7ceaeb8f6`

Der Hash ist SHA-256 ueber den Basis-Commit und anschliessend fuer jede
geaenderte oder unversionierte Kandidatendatei (sortierter Repository-Pfad,
NUL-Trenner, SHA-256 des Inhalts). Diese Berichtsdatei selbst ist ausgeschlossen,
damit die Prüfsumme nicht selbstreferenziell ist. Build- und Test-Tempdateien
werden durch Git-Ignorierregeln nicht Teil des Kandidaten.

## Fachliche Ausbaureihenfolge nach der lokalen Abnahme

1. Tenant-/Owner-/Scope-Isolation fuer alle produktiven Datenpfade und den
   Produktions-Memory-Audit abschliessen.
2. Minimalen Wissenslebenszyklus bauen: unveraenderliche Versionen, Herkunft,
   Claims, Konflikte und Answer Receipts.
3. Erst danach Artikelstamm fachlich spezifizieren und tenant-isoliert
   migrieren/API-seitig anbinden.
4. Rechnungen, Positionen, Nummernkreis, PDF und Freigabe-/Auditfluss ergaenzen.

Der externe Prototyp `real_cognitive_agent_memory_engine.py` wird nicht in den
Produktivpfad uebernommen, solange Herkunft, Zweck, Datenmodell und
Mandantenisolation nicht explizit entschieden und getestet sind.

## Noch offene Produktionsfreigabe

Technisch/betrieblich extern zu pruefen:

- deployter Commit/Branch, Runtime, Datenbanktyp und Alembic-Head auf Render;
- Produktions-Memory-Audit gegen den echten Bestand;
- TLS/HSTS, konkrete CORS-Origins, Secret- und Schluesselverwaltung;
- externes Backupziel, Zeitplan, Alarmierung, Aufbewahrung und regelmaessige
  Restore-Probe mit benannter Verantwortung;
- Monitoring, Incident-Prozess und Rollback-Probe.

Organisatorisch/rechtlich zu entscheiden:

- AVV/DPA, Drittlandtransfer und Freigabestatus jedes externen Providers;
- Verantwortliche fuer Betrieb, Datenschutz, Restore und Freigaben;
- dokumentierte Produktionsabnahme und Freigabeentscheidung.

Bis diese Punkte belegt sind, bleibt die Produktionsfreigabe gesperrt und der
externe LLM-Kill-Switch standardmaessig deaktiviert.
