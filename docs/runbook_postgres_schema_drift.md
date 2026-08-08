# Runbook: Reparatur der Postgres-Schema-Drift

**Status: NICHT ausgefuehrt.** An der produktiven Datenbank wurde bisher
nichts veraendert. Dieses Dokument beschreibt den freizugebenden Ablauf.

---

## 1. Ausgangslage

Auf der produktiven PostgreSQL-Datenbank fehlen Spalten, die im Python-Schema
(`apps/backend/db_schema.py`) definiert sind. Symptom war ein harter HTTP-500:

```
psycopg.errors.UndefinedColumn: column "owner_user_id" of relation "agent_runs" does not exist
```

**Ursache:** `ensure_sqlite_schema()` in `apps/backend/database.py` beginnt mit

```python
if not DATABASE_URL.startswith("sqlite"):
    return
```

Der Mechanismus, der fehlende Spalten nachtraeglich ergaenzt, lief also
ausschliesslich fuer SQLite. Fuer PostgreSQL existierte kein Aequivalent.
`metadata_obj.create_all()` legt nur fehlende **Tabellen** an, niemals
fehlende **Spalten** -- in keinem Dialekt. Jede Spalte, die nach der
Ersteinrichtung der Postgres-Datenbank im Code ergaenzt wurde, fehlt dort
daher dauerhaft.

### Betroffene Spalten (11)

| Tabelle | Spalte | Typ | Nullable |
|---|---|---|---|
| `audit_logs` | `tenant_id` | String(64) | nein |
| `approval_requests` | `tenant_id` | String(64) | nein |
| `approval_requests` | `owner_user_id` | String(64) | ja |
| `agent_runs` | `tenant_id` | String(64) | nein |
| `agent_runs` | `owner_user_id` | String(64) | ja |
| `users` | `failed_login_attempts` | Integer | nein |
| `users` | `locked_until` | DateTime(tz) | ja |
| `user_projects` | `version` | Integer | nein |
| `user_chats` | `version` | Integer | nein |
| `user_chats` | `keep_uploaded_documents` | Integer | ja |
| `user_chats` | `document_retention_days` | Integer | ja |

Die letzten beiden sind seit dem Baseline-Fix bereits Teil von Migration 0001
und werden hier nur defensiv mitgefuehrt (Normalfall: No-Op).

---

## 2. Reparatur-Bausteine

| Datei | Zweck |
|---|---|
| `apps/backend/alembic/versions/0003_add_missing_columns_postgres_drift.py` | Additive, idempotente `add_column`-Operationen fuer die 11 Spalten |
| `apps/backend/alembic_adopt.py` | `KNOWN_ADDITIVE_GAPS`, `stamp_baseline_with_tolerance()`, CLI-Flag `--allow-additive-gap` |
| `tests/test_postgres_drift_repair.py` | 11 Tests, die den gesamten Ablauf dauerhaft absichern |

### Warum ein Toleranz-Mechanismus noetig ist

`alembic_adopt.py` ist bewusst fail-closed: es stempelt eine Bestands-Datenbank
nur, wenn sie **exakt** der Baseline entspricht. Die Produktionsdatenbank kann
deshalb nicht gestempelt werden -- ihr fehlen ja Spalten. Diese Spalten kann
aber nur Migration 0003 ergaenzen, und die laeuft erst nach dem Stempeln.

Aufgeloest wird das durch eine **eng begrenzte, hart kodierte Allowlist**:
toleriert werden ausschliesslich Spalten, die
1. in `KNOWN_ADDITIVE_GAPS` stehen (= genau die von 0003 reparierten), **und**
2. von der aufrufenden Person ausdruecklich per Flag bestaetigt werden.

Jede andere Abweichung -- fehlende Tabelle, unerwartete Spalte, abweichende
Nullability, nicht gelistete fehlende Spalte -- fuehrt weiterhin zum Abbruch.
Es gibt bewusst **keine** generische "alles ignorieren"-Option.

### Hinweis zu `server_default`

Migration 0003 setzt bei `NOT NULL`-Spalten ein `server_default`, weil
PostgreSQL sonst `ADD COLUMN ... NOT NULL` auf einer Tabelle mit vorhandenen
Zeilen ablehnt. Direkt danach wird die DEFAULT-Klausel wieder entfernt
(`_drop_server_defaults()`), damit eine **reparierte** Datenbank strukturell
identisch zu einer **frisch angelegten** ist. Ohne diesen Schritt bliebe eine
stille Abweichung zurueck, die `alembic_adopt.py` nicht erkennt (dort werden
nur Spaltennamen und Nullability verglichen, keine Defaults).

Auf SQLite wird dieser Schritt uebersprungen: SQLite kann DEFAULT-Klauseln
nicht per `ALTER COLUMN` entfernen, Alembic muesste die Tabelle vollstaendig
neu aufbauen -- ein unnoetiges Datenrisiko. Produktiv laeuft AILIZA auf
PostgreSQL, dort greift der Schritt.

---

## 3. Freizugebender Ablauf

> Jeder Schritt einzeln durchfuehren und das Ergebnis pruefen, bevor der
> naechste beginnt. Bei jeder Unklarheit: abbrechen, nicht weitermachen.

### Schritt 1 -- Backup und verifizierte Wiederherstellung

```bash
pg_dump "$PRODUCTION_DATABASE_URL" -Fc -f ailiza_prod_$(date +%Y%m%d_%H%M%S).dump
```

Das Backup auf einem von der Produktionsinstanz **getrennten** Speicherort
ablegen. Anschliessend in eine **isolierte Testdatenbank** zurueckspielen:

```bash
createdb ailiza_restore_test
pg_restore -d ailiza_restore_test ailiza_prod_<zeitstempel>.dump
```

Ein Backup, das nicht testweise wiederhergestellt wurde, gilt als kein Backup.
Alle folgenden Schritte werden **zuerst gegen diese Kopie** durchgespielt.

### Schritt 2 -- Dry-Run mit vollstaendigem Schema-Diff

```bash
AILIZA_DATABASE_URL="postgresql://.../ailiza_restore_test" \
  python3 -m apps.backend.alembic_adopt --dry-run
```

Erwartet: Exit-Code 1 und eine Auflistung der fehlenden Spalten.

**Abbruchbedingung:** Meldet der Dry-Run *irgendeine* Abweichung, die nicht in
der Tabelle unter Abschnitt 1 steht -- fehlende Tabelle, unerwartete Spalte,
abweichende Nullability -- wird der Vorgang gestoppt und neu bewertet. Die
Toleranz deckt ausschliesslich die 11 gelisteten Spalten ab.

Die vollstaendige Ausgabe wird archiviert (Nachweis fuer die Zertifizierung).

### Schritt 3 -- Allowlist gegen die Migration pruefen

```bash
python3 -m pytest tests/test_postgres_drift_repair.py::test_known_additive_gaps_matches_migration_0003_exactly -v
```

Dieser Test schlaegt fehl, sobald `KNOWN_ADDITIVE_GAPS` und die von 0003
tatsaechlich behandelten Spalten auseinanderlaufen. Zusaetzlich wird die im
Dry-Run gemeldete Spaltenliste manuell gegen Abschnitt 1 abgeglichen -- die
Mengen muessen deckungsgleich sein.

Danach Vorschau mit Toleranz (veraendert nichts):

```bash
python3 -m apps.backend.alembic_adopt --dry-run \
  --allow-additive-gap "audit_logs.tenant_id,approval_requests.tenant_id,approval_requests.owner_user_id,agent_runs.tenant_id,agent_runs.owner_user_id,users.failed_login_attempts,users.locked_until,user_projects.version,user_chats.version,user_chats.keep_uploaded_documents,user_chats.document_retention_days"
```

Erwartet: Exit-Code 0 und die Auflistung der tolerierten Spalten.

### Schritt 4 -- Stempeln, `upgrade head`, Verifikation

```bash
# 4a. Stempeln mit ausdruecklicher Toleranz
python3 -m apps.backend.alembic_adopt --revision 0001 --allow-additive-gap "<siehe oben>"

# 4b. UNMITTELBAR danach: Luecken tatsaechlich schliessen
alembic -c alembic.ini upgrade head

# 4c. Verifikation OHNE Toleranz-Flag
python3 -m apps.backend.alembic_adopt --dry-run
```

**Abnahmebedingung fuer 4c:** Ausgabe `Schema entspricht exakt der erwarteten
Baseline (Revision 0001).` und Exit-Code 0.

Schritt 4a und 4b gehoeren zwingend zusammen. Bleibt es bei 4a stehen, ist die
Datenbank gestempelt, obwohl die Spalten weiterhin fehlen -- ein schlechterer
Zustand als vorher, weil die Luecke dann nicht mehr auffaellt.

**Anwendungstest nach 4b:**
- `/documents/agent-run` aufrufen (die Route, die den urspruenglichen 500er ausloeste)
- Login (`users.failed_login_attempts`, `locked_until`)
- Chat anlegen und Dokument hochladen (`user_chats.version`, Retention-Spalten)
- Audit-Log-Eintrag erzeugen (`audit_logs.tenant_id`)

**Wartungsfenster:** `ALTER TABLE ... ADD COLUMN` nimmt kurzzeitig einen
Lock. Bei `nullable=True` bzw. mit `server_default` ist das in aktuellen
PostgreSQL-Versionen sehr kurz, sollte aber dennoch ausserhalb der Spitzenlast
erfolgen.

### Rueckfallplan

| Fehlerzeitpunkt | Massnahme |
|---|---|
| Schritt 2/3 (Dry-Run) | Kein Eingriff erfolgt -- Vorgang einfach abbrechen |
| Schritt 4a (Stempeln) | `DELETE FROM alembic_version;` setzt den Stempel zurueck, Schema unveraendert |
| Schritt 4b (`upgrade head`) | Migration ist idempotent und rein additiv, kein Datenverlust. Erneut ausfuehrbar. Im Zweifel: Backup aus Schritt 1 zurueckspielen |
| Anwendungstest schlaegt fehl | Backup aus Schritt 1 zurueckspielen. `downgrade()` von 0003 ist bewusst ein No-Op -- es wird **nie** automatisch eine Spalte geloescht |

Die hinzugefuegten Spalten sind additiv: aelterer Anwendungscode, der sie nicht
kennt, funktioniert unveraendert weiter. Ein Rollback der Anwendung erfordert
daher kein Schema-Rollback.

### Schritt 5 -- Separate Freigabe fuer die Produktionsdatenbank

Die Schritte 1-4 werden vollstaendig gegen die **wiederhergestellte Kopie**
durchgefuehrt. Erst wenn dort alle Abnahmebedingungen erfuellt sind, wird eine
**gesonderte, ausdrueckliche Freigabe** fuer denselben Ablauf gegen die echte
Produktionsdatenbank eingeholt. Es gibt keinen automatischen Uebergang von
Schritt 4 auf die Produktion.

---

## 4. Offener Punkt: die Ursache besteht fort

`ensure_sqlite_schema()` ist weiterhin SQLite-only. Die naechste im Code
ergaenzte Spalte erzeugt exakt denselben Fehler erneut, sofern nicht
gleichzeitig eine Alembic-Migration angelegt wird.

Empfohlene Folgemassnahme (noch nicht umgesetzt, eigener Vorgang): ein Test,
der fehlschlaegt, sobald `db_schema.py` eine Spalte enthaelt, die von keiner
Migration erzeugt wird. `tests/test_database_migrations.py` enthaelt bereits
einen Vergleich einer frisch migrierten Datenbank gegen `metadata_obj` -- die
Erweiterung koennte dort ansetzen.

---

## 5. Stand der Testabdeckung

`tests/test_postgres_drift_repair.py` enthaelt 13 Tests: 11 laufen gegen
temporaere SQLite-Datenbanken, 2 gegen eine echte PostgreSQL-Instanz. Die
beiden PostgreSQL-Tests werden uebersprungen, solange
`AILIZA_TEST_POSTGRES_URL` nicht gesetzt ist.

### PostgreSQL-Nachweis (erbracht am 2026-08-03, PostgreSQL 16.13)

Der Ablauf wurde vollstaendig gegen eine lokale PostgreSQL-16-Instanz
durchgespielt: Baseline aufbauen, die betroffenen Spalten entfernen, eine
Bestandszeile einfuegen, dann Dry-Run -> Stempeln mit Toleranz ->
`upgrade head` -> Verifikation ohne Toleranz.

| Nachweis | Ergebnis |
|---|---|
| Strukturvergleich repariert vs. frisch (286 Spalten, inkl. `column_default`, `data_type`, `is_nullable`) | identisch, keine Abweichung |
| `column_default` der sechs mit Backfill ergaenzten `NOT NULL`-Spalten | leer -- `_drop_server_defaults()` greift auf PostgreSQL |
| Bestandszeile nach Reparatur | erhalten; `tenant_id` auf `default` vorbefuellt, `owner_user_id` korrekt `NULL` |
| Verifikation ohne Toleranz-Flag | `Schema entspricht exakt der erwarteten Baseline (Revision 0001).` |

Beide PostgreSQL-Tests wurden gegenprobiert: bei testweise deaktiviertem
`_drop_server_defaults()` schlagen sie fehl
(`audit_logs.tenant_id hat nach der Reparatur noch eine DEFAULT-Klausel
("'default'::character varying")`). Sie erkennen die Regression also
tatsaechlich und sind keine Schoenwetter-Tests.

Lokale PostgreSQL-Instanz fuer diese Tests:

```bash
initdb -D <datadir> -U postgres --auth=trust
pg_ctl -D <datadir> -o '-p 55432' start
export AILIZA_TEST_POSTGRES_URL="postgresql+psycopg://postgres@127.0.0.1:55432/postgres"
python3 -m pytest tests/test_postgres_drift_repair.py -v
```

### Weiterhin offen

Der Nachweis erfolgte gegen ein **leeres, frisch aufgebautes** PostgreSQL-Schema
mit einer einzelnen Testzeile -- nicht gegen eine Kopie der echten
Produktionsdatenbank mit ihrem realen Datenbestand und Datenvolumen. Schritt 1
des Ablaufs (Backup-Restore in eine isolierte Testdatenbank) bleibt daher
zwingend erforderlich und ist durch diesen Nachweis nicht ersetzt.
