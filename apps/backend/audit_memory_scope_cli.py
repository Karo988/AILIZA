"""
CLI-Entrypoint: Bestandsbericht der Memory-Scope-/Owner-/Tenant-Invarianten.
=============================================================================
Rein lesend (ruft ausschliesslich database.audit_memory_scope_invariants()
auf -- siehe dort fuer die Read-Only-Garantie und die genaue Definition der
geprueften Invarianten). Veraendert NIEMALS Daten. Gedacht, um den in PR M1
(Scope-/Owner-/Tenant-Invarianten im fachlichen Memory-Kern) angekuendigten
Produktions-Audit gegen die echte Datenbank (Render/Neon) auszufuehren --
diese Sandbox hat dazu keinen Netzwerkzugriff, daher konnte der Audit
bislang nur als Trockenlauf gegen eine leere lokale Dev-Datei nachgewiesen
werden.

Verwendung (aus einer Umgebung mit Zugriff auf die produktive
AILIZA_DATABASE_URL, z.B. Render Shell oder ein manueller GitHub-Actions-
Workflow):

    python apps/backend/audit_memory_scope_cli.py
    python apps/backend/audit_memory_scope_cli.py --json
    python apps/backend/audit_memory_scope_cli.py --json > audit_report.json
    python apps/backend/audit_memory_scope_cli.py --summary-only --json

--summary-only: unterdrueckt ALLE internen ID-Listen (Verletzungen und
Info-Werte) -- nur Zaehlwerte + has_violations bleiben erhalten. Gedacht
fuer Ausfuehrungen, deren Log oeffentlich einsehbar ist (z.B. Logs eines
Workflow-Laufs in einem oeffentlichen GitHub-Repository) -- interne
Datensatz-IDs sollen dort nicht auftauchen, auch wenn sie fuer sich
genommen keine Rohinhalte sind.

Exit-Codes (fuer Skripting/CI-Gates geeignet):
    0 -- keine Verletzungen gefunden (has_violations == False)
    1 -- mindestens eine Invarianten-Verletzung gefunden
    2 -- Fehler beim Ausfuehren des Audits (z.B. DB nicht erreichbar)

Sicherheitshinweise:
    - Dieses Script fuehrt KEINE Reparatur/Migration durch -- es liefert
      ausschliesslich einen Bericht. Eine etwaige Reparatur ist bewusst
      ein separater, spaeterer Schritt mit eigener Prüfung.
    - Es werden NUR interne ID-Listen und Zaehlwerte ausgegeben -- keine
      Memory-Rohinhalte (title/content/purpose), keine Nutzernamen im
      Klartext ausser den bereits in memory_items gespeicherten
      owner_user_id/tenant_id-Werten, die fuer die Diagnose zwingend
      benoetigt werden (kein zusaetzliches Leck ueber das Bestehende
      hinaus).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo-Root explizit auf sys.path bringen, BEVOR irgendein AILIZA-Modul
# importiert wird. Grund (Produktions-Audit-Run #1, Exit 2, Workflow-Run
# 30626472529): database.py importiert transitiv `cryptography`
# (governance/field_crypto.py). Fehlt dieses Paket (z.B. bei einer
# schlanken Minimal-Installation), wirft `from database import ...` ein
# ImportError -- der bisherige Fallback `from apps.backend.database import
# ...` schlug dann ZUSAETZLICH fehl, weil das Repo-Root beim direkten
# Skriptaufruf (`python apps/backend/audit_memory_scope_cli.py`) nicht in
# sys.path liegt (nur das Skript-Verzeichnis selbst wird automatisch
# hinzugefuegt). Das erzeugte die irrefuehrende Meldung
# "ModuleNotFoundError: No module named 'apps'", die den eigentlichen
# Fehler (fehlendes cryptography-Paket) verdeckte. Mit dem Repo-Root fest
# in sys.path funktioniert der Import unabhaengig vom Aufrufverzeichnis
# und unabhaengig davon, welches Paket im Einzelfall fehlt -- der echte
# Fehler wird dann klar sichtbar statt durch einen zweiten, irrefuehrenden
# ImportError ueberdeckt.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


_SQLITE_FILE_PREFIX = "sqlite:///"


def _sqlite_file_path(database_url: str) -> str | None:
    """Absoluter Dateipfad, wenn `database_url` eine dateibasierte
    SQLite-URL ist -- sonst None (":memory:" oder anderer Dialekt wie
    PostgreSQL)."""
    if not database_url.startswith(_SQLITE_FILE_PREFIX):
        return None
    tail = database_url[len(_SQLITE_FILE_PREFIX):]
    if tail.startswith(":"):
        return None  # sqlite:///:memory:
    return tail


def _open_readonly_sqlite_engine(db_path: str):
    """Oeffnet eine EIGENE, rein lesende Verbindung zur SQLite-Datei --
    getrennt von der schreibfaehigen, anwendungsweiten `engine` aus
    database.py. Zwei unabhaengige technische Schranken statt nur einer:

    1. URI-Modus `mode=ro`: SQLite oeffnet die Datei betriebssystemseitig
       nur lesend. Anders als eine gewoehnliche `sqlite:///pfad`-Verbindung
       legt das die Datei NICHT an, wenn sie fehlt (die schreibfaehige
       Standardverbindung wuerde das tun -- siehe Docstring von main()).
    2. `PRAGMA query_only = ON`: zusaetzliche SQLite-interne Sperre. Selbst
       wenn `mode=ro` durch einen zukuenftigen Code-/Config-Fehler entfaellt,
       weist SQLite jede schreibende Anweisung auf dieser Verbindung mit
       "attempt to write a readonly database" zurueck (siehe
       tests/test_memory_audit_cli.py::test_readonly_connection_rejects_a_deliberate_write).

    Kein Effekt auf die globale `engine` aus database.py -- diese Funktion
    erzeugt eine vollstaendig unabhaengige zweite Engine, nur fuer die
    Dauer dieses Audit-Laufs."""
    from sqlalchemy import create_engine, event

    ro_engine = create_engine(f"sqlite:///file:{db_path}?mode=ro&uri=true")

    @event.listens_for(ro_engine, "connect")
    def _enforce_query_only(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA query_only = ON")
        finally:
            cursor.close()

    return ro_engine


def _open_readonly_postgres_engine(database_url: str):
    """Oeffnet fuer PostgreSQL (Render/Neon-Dialekt: postgresql+psycopg://)
    eine EIGENE Engine, deren Verbindungen ALLE Anweisungen in einer
    READ ONLY-Transaktion ausfuehren -- serverseitig durchgesetzt (nicht
    nur clientseitiger Code-Verzicht auf Schreib-SQL).

    Technik: `execution_options(postgresql_readonly=True)` laesst
    SQLAlchemys PostgreSQL-Dialekt bei Verbindungsaufbau
    `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` (psycopg2/
    psycopg) setzen. Ein INSERT/UPDATE/DELETE auf einer so geoeffneten
    Verbindung wird vom PostgreSQL-Server selbst mit
    `psycopg.errors.ReadOnlySqlTransaction` ("cannot execute ... in a
    read-only transaction") abgewiesen -- lokal gegen eine isolierte
    Testinstanz nachgewiesen, siehe
    tests/test_memory_audit_cli.py::test_postgres_readonly_connection_rejects_a_deliberate_write.

    Getrennt von der schreibfaehigen, anwendungsweiten `engine` aus
    database.py -- eine vollstaendig unabhaengige zweite Engine, nur fuer
    die Dauer dieses Audit-Laufs. SQLite-Verhalten (siehe
    _open_readonly_sqlite_engine oben) bleibt davon unberuehrt."""
    from sqlalchemy import create_engine

    ro_engine = create_engine(database_url).execution_options(postgresql_readonly=True)
    return ro_engine


def _is_postgres_url(database_url: str) -> bool:
    return database_url.startswith("postgresql")


def _summarize(report: dict) -> dict:
    """Reduziert einen Bericht auf reine Zaehlwerte -- keine internen
    ID-Listen. Fuer Ausgaben in oeffentlich einsehbare Logs (siehe
    --summary-only)."""
    return {
        "total_memory_items": report["total_memory_items"],
        "has_violations": report["has_violations"],
        "violations": {k: len(v) for k, v in report["violations"].items()},
        "info_only": {k: len(v) for k, v in report["info_only"].items()},
        "checked_at": report["checked_at"],
    }


def _print_human_report(report: dict, *, summary_only: bool) -> None:
    """report: bei summary_only=True bereits ueber _summarize() reduziert
    (violations/info_only-Werte sind dann int Zaehlwerte statt ID-Listen)."""
    print(f"Memory-Scope-Audit ({report['checked_at']})")
    print(f"Gesamtzahl memory_items: {report['total_memory_items']}")
    print()
    if report["has_violations"]:
        print("[FEHLER] INVARIANTEN VERLETZT:")
    else:
        print("[OK] Keine Invarianten-Verletzungen gefunden.")
    for key, val in report["violations"].items():
        count = val if summary_only else len(val)
        marker = "[FEHLER]" if count else "       "
        detail = "" if summary_only or not val else f" -- {val}"
        print(f"  {marker} {key}: {count} Treffer{detail}")
    print()
    print("Info (kein harter Fehler, siehe Dokumentation):")
    for key, val in report["info_only"].items():
        count = val if summary_only else len(val)
        detail = "" if summary_only or not val else f" -- {val}"
        print(f"     {key}: {count} Treffer{detail}")
    print()
    if report["has_violations"]:
        print("Naechster Schritt: Verletzte Datensaetze pruefen (KEINE automatische")
        print("Reparatur durch dieses Script) und bewusste Korrektur-Migration planen.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rein lesender Bestandsbericht der Memory-Scope-/Owner-/Tenant-Invarianten.",
    )
    parser.add_argument("--json", action="store_true", help="Bericht als JSON statt Klartext ausgeben.")
    parser.add_argument(
        "--summary-only", action="store_true",
        help="Unterdrueckt interne ID-Listen -- nur Zaehlwerte. Fuer oeffentlich einsehbare Logs.",
    )
    args = parser.parse_args()

    ro_engine = None
    try:
        from sqlalchemy import inspect
        from apps.backend.database import audit_memory_scope_invariants, DATABASE_URL, engine

        db_path = _sqlite_file_path(DATABASE_URL)
        if db_path is not None:
            # Existenzpruefung VOR jeder Verbindung: eine gewoehnliche
            # SQLite-Verbindung (auch eine rein lesende `inspect()`-Anfrage
            # ueber die schreibfaehige Standard-Engine) legt eine fehlende
            # Datei beim Verbindungsaufbau selbst an. Ein Audit darf aber
            # niemals eine Datenbankdatei erzeugen -- deshalb hier ein
            # reiner Dateisystem-Check, bevor SQLAlchemy/SQLite ueberhaupt
            # ins Spiel kommt.
            if not Path(db_path).exists():
                print(
                    f"❌ Audit fehlgeschlagen: Datenbankdatei nicht gefunden: {db_path} "
                    "-- wird von diesem Audit nicht angelegt.",
                    file=sys.stderr,
                )
                return 2
            # Ab hier ausschliesslich ueber eine dedizierte Read-only-
            # Verbindung (mode=ro + PRAGMA query_only) -- siehe
            # _open_readonly_sqlite_engine(). Die schreibfaehige,
            # anwendungsweite `engine` wird fuer diesen Audit-Lauf gar
            # nicht mehr angefasst.
            ro_engine = _open_readonly_sqlite_engine(db_path)
            target_engine = ro_engine
        elif _is_postgres_url(DATABASE_URL):
            # PostgreSQL (Render/Neon): serverseitig durchgesetzte
            # READ ONLY-Transaktion statt des SQLite-spezifischen
            # mode=ro-URI-Tricks -- siehe _open_readonly_postgres_engine().
            # Auch hier ausschliesslich ueber eine dedizierte, von der
            # schreibfaehigen App-Engine getrennte Verbindung.
            ro_engine = _open_readonly_postgres_engine(DATABASE_URL)
            target_engine = ro_engine
        else:
            # ":memory:"-SQLite-Datenbanken (nur in Tests relevant) oder
            # ein anderer, nicht gesondert behandelter Dialekt: Fallback
            # auf die bestehende, code-seitige Read-only-Garantie (nur
            # SELECTs, siehe audit_memory_scope_invariants()) -- keine
            # zusaetzliche Verbindungs-Ebene-Schranke fuer diese Faelle.
            target_engine = engine

        # Rein lesende Existenzpruefung -- kein init_db()/create_all() mehr:
        # Dieses CLI bezeichnet sich als read-only und darf auch technisch
        # niemals Schema anlegen oder aendern (auch nicht "nur" additiv per
        # ensure_sqlite_schema()). Fehlt eine Tabelle, bricht der Audit hier
        # verstaendlich ab, statt sie stillschweigend zu erzeugen.
        insp = inspect(target_engine)
        missing = [t for t in ("memory_items", "memory_visibility") if not insp.has_table(t)]
        if missing:
            print(
                f"❌ Audit fehlgeschlagen: Tabelle(n) fehlen: {', '.join(missing)} "
                "-- Schema muss bereits migriert sein, wird von diesem Audit nicht angelegt.",
                file=sys.stderr,
            )
            return 2

        if ro_engine is not None:
            with ro_engine.connect() as conn:
                report = audit_memory_scope_invariants(conn=conn)
        else:
            report = audit_memory_scope_invariants()
    except Exception as exc:
        print(f"❌ Audit fehlgeschlagen: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        if ro_engine is not None:
            ro_engine.dispose()

    has_violations = report["has_violations"]
    output_report = _summarize(report) if args.summary_only else report

    if args.json:
        print(json.dumps(output_report, indent=2, default=str))
    else:
        _print_human_report(output_report, summary_only=args.summary_only)

    return 1 if has_violations else 0


if __name__ == "__main__":
    sys.exit(main())
