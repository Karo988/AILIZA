"""Sichere Uebernahme (Stempeln) bestehender Datenbanken in das formale
Alembic-Migrationssystem -- Arbeitspaket 3 (feat/formal-database-migrations).

Hintergrund: Migration 0001 (0001_baseline_existing_schema.py) legt das
27-Tabellen-Schema mit expliziten `op.create_table()`-Aufrufen an. Fuer eine
NEUE, leere Datenbank funktioniert `alembic upgrade head` direkt. Fuer eine
BESTEHENDE Datenbank (Tabellen existieren bereits) wuerde derselbe Befehl mit
"table already exists" fehlschlagen -- das ist beabsichtigt: es darf NIE
automatisch angenommen werden, dass eine bestehende Datenbank exakt dem
erwarteten Schema entspricht.

Dieses Skript prueft stattdessen explizit, ob die tatsaechliche Datenbank
exakt dem erwarteten Schema (Migration 0001) entspricht, und stempelt sie
NUR bei exakter Uebereinstimmung als "bereits auf Stand 0001" (ohne die
Tabellen neu anzulegen). Fail-closed: bei JEDER Abweichung wird abgebrochen,
nichts wird automatisch repariert oder angepasst.

Geprueft wird (bewusst NICHT exakte Typgleichheit -- SQLite hat keine
strikte Typaffinitaet, ein Typvergleich wuerde falsch-positive Fehler
erzeugen):
  - Tabellenmenge: exakt die 27 erwarteten Tabellennamen, nicht mehr,
    nicht weniger.
  - Je Tabelle: Spaltenmenge (Name) und NULL-Zulaessigkeit.
  - Indizes: Name, Spalten, unique-Flag. SQLite-Autoindizes
    (sqlite_autoindex_*, automatisch fuer UNIQUE-Constraints) werden
    herausgefiltert, da sie kein Gegenstueck in der Metadata-Definition
    haben.
  - Constraint-NAMEN werden NICHT als Fehler gewertet, solange die
    fachliche Regel (betroffene Spalten, unique-Flag) identisch ist
    (Karo-Entscheidung 2026-08-02, Punkt 7) -- z.B. automatisch vergebene
    Fremdschluessel-Namen unterscheiden sich zwischen SQLite und PostgreSQL
    und je nach SQLAlchemy-Version, ohne dass das ein Schema-Defekt waere.

Aufruf (aus dem Repository-Root):
    python -m apps.backend.alembic_adopt --dry-run
    python -m apps.backend.alembic_adopt --revision 0001

Nur bei `--revision 0001` und exakter Uebereinstimmung wird tatsaechlich
gestempelt (alembic_version-Tabelle auf "6165ff33e9ee" gesetzt). Kein
automatischer Aufruf beim Programmstart -- ausschliesslich manuell/CLI.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, inspect

try:
    from apps.backend.database import DATABASE_URL, engine
except ImportError:  # pragma: no cover - Fallback bei Ausfuehrung aus apps/backend/
    from database import DATABASE_URL, engine  # type: ignore

BASELINE_REVISION = "6165ff33e9ee"


class SchemaMismatchError(Exception):
    """Bestehende Datenbank weicht vom erwarteten Baseline-Schema ab."""


@dataclass(frozen=True)
class _BaselineIndex:
    name: str
    columns: tuple[str, ...]
    unique: bool


@dataclass(frozen=True)
class _BaselineTable:
    columns: dict[str, bool]  # Spaltenname -> nullable
    indexes: tuple[_BaselineIndex, ...]
    unique_columns: frozenset[str]  # Spalten mit Column(unique=True) (impliziter Index)


@lru_cache(maxsize=1)
def _baseline_reference_schema() -> dict[str, _BaselineTable]:
    """Eingefrorene Referenz fuer Revision 0001 -- Tabellen, Spalten UND
    Indizes, nicht nur Tabellennamen.

    Bewusst NICHT von metadata_obj abgeleitet: metadata_obj waechst mit
    jeder neuen Tabelle/Spalte/Index im laufenden Code (z.B. "customers"
    aus Phase 1, oder die Indizes aus Migration 0004) -- Revision 0001 ist
    aber ein historischer, unveraenderlicher Zeitpunkt. Eine echte, nie
    migrierte Alt-Datenbank aus jener Zeit hat und wird immer GENAU das
    Schema haben, das Migration 0001 tatsaechlich anlegt -- unabhaengig
    davon, was der heutige Code inzwischen kennt. Ein Vergleich gegen das
    lebende metadata_obj wuerde die Adoption jeder echten 0001-Alt-
    Datenbank verweigern, sobald irgendeine neue Tabelle/Spalte/Index zum
    Code hinzukommt -- das waere kein Sicherheitsgewinn, sondern ein
    Funktionsverlust des Adoptionswegs (siehe Vorfall Phase 1: die
    "customers"-Tabelle allein haette dies bereits ausgeloest; eine
    genauere Pruefung zeigte zusaetzlich laenger bestehende Luecken bei
    Migration-0004-Indizes).

    Um Abtippfehler bei 27 Tabellen auszuschliessen, wird hier NICHT von
    Hand dupliziert, sondern die echte Migration 0001 gegen eine
    Wegwerf-SQLite-Datei ausgefuehrt und deren tatsaechliches Schema
    eingelesen -- das bleibt automatisch korrekt, auch wenn sich 0001
    (was es nicht mehr sollte, siehe deren Docstring) oder das
    Lese-Verfahren selbst nie wieder angefasst wird. Ergebnis wird pro
    Prozess einmalig berechnet (Migrationslauf ist nicht kostenlos).
    """
    import subprocess

    backend_dir = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="ailiza-baseline-ref-") as tmpdir:
        db_path = Path(tmpdir) / "baseline_reference.sqlite"
        env = os.environ.copy()
        env["AILIZA_DATABASE_URL"] = f"sqlite:///{db_path}"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini",
             "upgrade", BASELINE_REVISION],
            cwd=backend_dir, env=env, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Konnte Referenzschema fuer Revision 0001 nicht aufbauen "
                f"(alembic upgrade {BASELINE_REVISION} fehlgeschlagen):\n{result.stderr}"
            )

        ref_engine = create_engine(f"sqlite:///{db_path}")
        try:
            inspector = inspect(ref_engine)
            schema: dict[str, _BaselineTable] = {}
            for table_name in inspector.get_table_names():
                if table_name == "alembic_version":
                    continue
                cols = {c["name"]: bool(c["nullable"]) for c in inspector.get_columns(table_name)}
                idxs = tuple(
                    _BaselineIndex(
                        name=ix["name"],
                        columns=tuple(ix["column_names"]),
                        unique=bool(ix["unique"]),
                    )
                    for ix in inspector.get_indexes(table_name)
                    if ix["name"] and not ix["name"].startswith("sqlite_autoindex_")
                )
                unique_cols = frozenset(
                    uc["column_names"][0]
                    for uc in inspector.get_unique_constraints(table_name)
                    if len(uc["column_names"]) == 1
                )
                schema[table_name] = _BaselineTable(columns=cols, indexes=idxs, unique_columns=unique_cols)
        finally:
            ref_engine.dispose()

    return schema


@dataclass
class _ComparisonResult:
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _compare_schema(bind) -> _ComparisonResult:
    result = _ComparisonResult()
    inspector = inspect(bind)

    actual_tables = set(inspector.get_table_names())
    baseline = _baseline_reference_schema()
    # Eingefrorene 0001-Baseline (Tabellen UND Spalten UND Indizes je
    # Tabelle), nicht das lebende metadata_obj -- siehe Docstring von
    # _baseline_reference_schema().
    expected_tables = set(baseline.keys())

    missing = expected_tables - actual_tables
    unexpected = actual_tables - expected_tables - {"alembic_version"}
    if missing:
        result.errors.append(f"Fehlende Tabellen: {sorted(missing)}")
    if unexpected:
        result.errors.append(f"Unerwartete zusaetzliche Tabellen: {sorted(unexpected)}")

    for table_name in sorted(expected_tables & actual_tables):
        expected_table = baseline[table_name]
        expected_cols = expected_table.columns
        actual_cols_raw = inspector.get_columns(table_name)
        actual_cols = {c["name"]: c["nullable"] for c in actual_cols_raw}

        missing_cols = set(expected_cols) - set(actual_cols)
        extra_cols = set(actual_cols) - set(expected_cols)
        if missing_cols:
            result.errors.append(f"{table_name}: fehlende Spalten {sorted(missing_cols)}")
        if extra_cols:
            result.errors.append(f"{table_name}: unerwartete Spalten {sorted(extra_cols)}")

        for col_name in sorted(set(expected_cols) & set(actual_cols)):
            if bool(expected_cols[col_name]) != bool(actual_cols[col_name]):
                result.errors.append(
                    f"{table_name}.{col_name}: nullable weicht ab "
                    f"(erwartet={expected_cols[col_name]}, "
                    f"tatsaechlich={actual_cols[col_name]})"
                )

        expected_indexes = {
            ix.name: {"columns": ix.columns, "unique": ix.unique}
            for ix in expected_table.indexes
        }
        actual_indexes_raw = inspector.get_indexes(table_name)
        actual_indexes = {
            ix["name"]: {
                "columns": tuple(ix["column_names"]),
                "unique": bool(ix["unique"]),
            }
            for ix in actual_indexes_raw
            if ix["name"] and not ix["name"].startswith("sqlite_autoindex_")
        }

        # Spalten-Constraint-Namen sind KEIN Fehler, solange die fachliche
        # Regel identisch ist (Karo-Entscheidung 2026-08-02, Punkt 7): eine
        # Column(unique=True) erzeugt je nach Dialekt einen automatisch
        # benannten Unique-Index/-Constraint (z.B. Postgres:
        # "<table>_<column>_key"), der in expected_table.indexes NICHT als
        # eigenes Index-Objekt auftaucht. Ein solcher tatsaechlicher Index
        # gilt als abgedeckt, wenn seine Spalten exakt einer erwarteten
        # einspaltigen unique=True-Spalte entsprechen.
        implicit_unique_columns = {(col,) for col in expected_table.unique_columns}
        for idx_name, idx_info in list(actual_indexes.items()):
            if (
                idx_name not in expected_indexes
                and idx_info["unique"]
                and idx_info["columns"] in implicit_unique_columns
            ):
                del actual_indexes[idx_name]

        missing_idx = set(expected_indexes) - set(actual_indexes)
        extra_idx = set(actual_indexes) - set(expected_indexes)
        if missing_idx:
            result.errors.append(f"{table_name}: fehlende Indizes {sorted(missing_idx)}")
        if extra_idx:
            result.errors.append(f"{table_name}: unerwartete Indizes {sorted(extra_idx)}")

        for idx_name in sorted(set(expected_indexes) & set(actual_indexes)):
            if expected_indexes[idx_name] != actual_indexes[idx_name]:
                result.errors.append(
                    f"{table_name}.{idx_name}: Index weicht ab "
                    f"(erwartet={expected_indexes[idx_name]}, "
                    f"tatsaechlich={actual_indexes[idx_name]})"
                )

    return result


def check_schema_matches_baseline(bind=None) -> _ComparisonResult:
    """Reine Pruefung, kein Stempeln. Wirft nichts, gibt Ergebnis zurueck."""
    bind = bind if bind is not None else engine
    return _compare_schema(bind)


# ---------------------------------------------------------------------------
# Schema-Drift-Schutz (Issue #79): Vergleich gegen das LEBENDE metadata_obj
#
# Abgrenzung zu _compare_schema() weiter oben: jener Vergleich prueft eine
# BESTEHENDE Alt-Datenbank gegen die eingefrorene Baseline 0001 und beantwortet
# die Frage "darf ich diese Datenbank adoptieren?". Er darf deshalb bewusst
# nicht mitwachsen.
#
# Der Vergleich hier beantwortet die umgekehrte Frage: "beschreibt db_schema.py
# noch das, was `alembic upgrade head` tatsaechlich anlegt?". Er MUSS
# mitwachsen und laeuft nur gegen eine frische, vollstaendig hochmigrierte
# Datenbank -- nie gegen eine Alt-Datenbank. Beide Pruefungen sind daher
# getrennt und teilen nur die Hilfsstrukturen (_ComparisonResult, das
# Ausfiltern von sqlite_autoindex_*, die Behandlung impliziter Unique-Indizes
# aus Column(unique=True) -- Karo-Entscheidung 2026-08-02, Punkt 7).
# ---------------------------------------------------------------------------

_TYPE_FAMILIES = {
    # Ganzzahlen: SQLite meldet INTEGER, PostgreSQL je nach Migration
    # INTEGER/BIGINT/SMALLINT bzw. SERIAL fuer Autoincrement-Primaerschluessel.
    "INTEGER": "INTEGER", "BIGINT": "INTEGER", "SMALLINT": "INTEGER",
    "SERIAL": "INTEGER", "BIGSERIAL": "INTEGER",
    # Zeitstempel: SQLite meldet fuer DateTime(timezone=True) immer DATETIME
    # -- SQLite kennt ueberhaupt keine Zeitzonen-Information im Typ.
    # PostgreSQL meldet je nach Migration TIMESTAMP WITH/WITHOUT TIME ZONE.
    # Die Zeitzonen-Angabe wird deshalb bewusst eingeebnet: sie ist in einem
    # dialektuebergreifenden Vergleich nicht darstellbar. Ein reiner
    # timezone-Unterschied faellt hier also NICHT auf.
    "DATETIME": "TIMESTAMP", "TIMESTAMP": "TIMESTAMP",
    "TIMESTAMP WITHOUT TIME ZONE": "TIMESTAMP",
    "TIMESTAMP WITH TIME ZONE": "TIMESTAMP", "TIMESTAMPTZ": "TIMESTAMP",
    # Fliesskomma: SQLite FLOAT, PostgreSQL DOUBLE PRECISION/REAL.
    "FLOAT": "FLOAT", "REAL": "FLOAT", "DOUBLE PRECISION": "FLOAT",
    # JSON: PostgreSQL kann JSONB melden.
    "JSON": "JSON", "JSONB": "JSON",
    "BOOLEAN": "BOOLEAN", "BOOL": "BOOLEAN",
    "TEXT": "TEXT",
}


def _normalise_type(raw_type) -> str:
    """Reduziert einen Spaltentyp auf eine dialektunabhaengige Normalform.

    Bewusst nicht exakt: SQLite und PostgreSQL melden fuer denselben
    SQLAlchemy-Typ unterschiedliche Namen (DATETIME vs. TIMESTAMP, FLOAT vs.
    DOUBLE PRECISION). Ein wortwoertlicher Vergleich wuerde in jedem
    PostgreSQL-Lauf falsch-positive Fehler erzeugen und die Pruefung damit
    wertlos machen.

    Erhalten bleibt dagegen die fachlich bedeutsame Unterscheidung
    VARCHAR(n) vs. TEXT sowie die Laengenangabe -- beide Dialekte melden
    diese identisch, solange jede String-Spalte eine explizite Laenge hat
    (in db_schema.py durchgehend der Fall).
    """
    text = str(raw_type).upper().strip()
    # Sammel-/Array-Suffixe und Anfuehrungszeichen entfernen.
    text = text.replace('"', "")
    base, _, length = text.partition("(")
    base = base.strip()
    suffix = f"({length.strip()}" if length else ""
    family = _TYPE_FAMILIES.get(base)
    if family is not None:
        # Familien mit fester Semantik ignorieren eine etwaige Praezision
        # (z.B. TIMESTAMP(6)) -- sie ist dialektabhaengig, nicht fachlich.
        return family
    if base in {"VARCHAR", "CHARACTER VARYING", "NVARCHAR"}:
        return f"VARCHAR{suffix}"
    if base in {"CHAR", "CHARACTER", "NCHAR", "BPCHAR"}:
        return f"CHAR{suffix}"
    return f"{base}{suffix}"


def _normalise_server_default(raw) -> str | None:
    """Normalisiert einen reflektierten Server-Default auf einen Literalwert.

    SQLite meldet `'normal'` bzw. `'0'`, PostgreSQL fuer dieselbe Migration
    `'normal'::character varying` bzw. `0`. Verglichen wird deshalb nur der
    nackte Literalwert ohne Typumwandlung, Anfuehrungszeichen und Klammern.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if hasattr(raw, "arg"):  # SQLAlchemy DefaultClause aus metadata_obj
        text = str(getattr(raw, "arg")).strip()
    # Typumwandlung abschneiden: 'normal'::character varying -> 'normal'
    if "::" in text:
        text = text.split("::", 1)[0].strip()
    # Umschliessende Klammern entfernen: (0) -> 0
    while len(text) > 1 and text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    # Umschliessende Anfuehrungszeichen entfernen: 'normal' -> normal
    for quote in ("'", '"'):
        if len(text) > 1 and text.startswith(quote) and text.endswith(quote):
            text = text[1:-1]
            break
    return text


@dataclass(frozen=True)
class _MetadataColumn:
    nullable: bool
    type_name: str
    server_default: str | None


@dataclass(frozen=True)
class _MetadataTable:
    columns: dict[str, _MetadataColumn]
    indexes: tuple[_BaselineIndex, ...]
    unique_columns: frozenset[str]
    primary_key: tuple[str, ...]


def _metadata_reference_schema() -> dict[str, _MetadataTable]:
    """Erwartungsbild aus dem lebenden metadata_obj (db_schema.py)."""
    try:
        from apps.backend.db_schema import metadata_obj
    except ImportError:  # pragma: no cover - Ausfuehrung aus apps/backend/
        from db_schema import metadata_obj  # type: ignore

    schema: dict[str, _MetadataTable] = {}
    for table in metadata_obj.tables.values():
        schema[table.name] = _MetadataTable(
            columns={
                col.name: _MetadataColumn(
                    nullable=bool(col.nullable),
                    type_name=_normalise_type(col.type),
                    server_default=_normalise_server_default(col.server_default),
                )
                for col in table.columns
            },
            indexes=tuple(
                _BaselineIndex(
                    name=ix.name,
                    columns=tuple(c.name for c in ix.columns),
                    unique=bool(ix.unique),
                )
                for ix in table.indexes
                if ix.name
            ),
            unique_columns=frozenset(col.name for col in table.columns if col.unique),
            primary_key=tuple(c.name for c in table.primary_key.columns),
        )
    return schema


def _compare_schema_against_metadata(bind) -> _ComparisonResult:
    result = _ComparisonResult()
    inspector = inspect(bind)

    expected = _metadata_reference_schema()
    actual_tables = set(inspector.get_table_names())
    expected_tables = set(expected)

    missing = expected_tables - actual_tables
    unexpected = actual_tables - expected_tables - {"alembic_version"}
    if missing:
        result.errors.append(
            f"In db_schema.py definiert, aber von keiner Migration angelegt: {sorted(missing)}"
        )
    if unexpected:
        result.errors.append(
            f"Von Migrationen angelegt, aber in db_schema.py unbekannt: {sorted(unexpected)}"
        )

    for table_name in sorted(expected_tables & actual_tables):
        expected_table = expected[table_name]
        expected_cols = expected_table.columns
        actual_cols = {
            c["name"]: c for c in inspector.get_columns(table_name)
        }

        missing_cols = set(expected_cols) - set(actual_cols)
        extra_cols = set(actual_cols) - set(expected_cols)
        if missing_cols:
            result.errors.append(
                f"{table_name}: in db_schema.py definiert, in der Datenbank nicht vorhanden "
                f"{sorted(missing_cols)}"
            )
        if extra_cols:
            result.errors.append(
                f"{table_name}: in der Datenbank vorhanden, in db_schema.py nicht definiert "
                f"{sorted(extra_cols)}"
            )

        for col_name in sorted(set(expected_cols) & set(actual_cols)):
            exp = expected_cols[col_name]
            act = actual_cols[col_name]

            if exp.nullable != bool(act["nullable"]):
                result.errors.append(
                    f"{table_name}.{col_name}: nullable weicht ab "
                    f"(db_schema.py={exp.nullable}, Datenbank={act['nullable']})"
                )

            act_type = _normalise_type(act["type"])
            if exp.type_name != act_type:
                result.errors.append(
                    f"{table_name}.{col_name}: Typ weicht ab "
                    f"(db_schema.py={exp.type_name}, Datenbank={act_type})"
                )

            act_default = _normalise_server_default(act.get("default"))
            # Autoincrement-Primaerschluessel: PostgreSQL legt fuer
            # Integer+autoincrement eine SERIAL-Spalte mit
            # nextval('<tabelle>_<spalte>_seq'::regclass) als Server-Default
            # an, SQLite dagegen INTEGER PRIMARY KEY ganz ohne Default.
            # metadata_obj kennt in beiden Faellen keinen server_default --
            # das ist kein Drift, sondern normale Dialekt-Umsetzung.
            is_autoincrement_default = (
                col_name in expected_table.primary_key
                and exp.server_default is None
                and act_default is not None
                and act_default.lower().startswith("nextval(")
            )
            if exp.server_default != act_default and not is_autoincrement_default:
                result.errors.append(
                    f"{table_name}.{col_name}: Server-Default weicht ab "
                    f"(db_schema.py={exp.server_default!r}, Datenbank={act_default!r})"
                )

        expected_pk = expected_table.primary_key
        actual_pk = tuple(inspector.get_pk_constraint(table_name)["constrained_columns"])
        if expected_pk != actual_pk:
            result.errors.append(
                f"{table_name}: Primaerschluessel weicht ab "
                f"(db_schema.py={list(expected_pk)}, Datenbank={list(actual_pk)})"
            )

        expected_indexes = {
            ix.name: {"columns": ix.columns, "unique": ix.unique}
            for ix in expected_table.indexes
        }
        actual_indexes = {
            ix["name"]: {
                "columns": tuple(ix["column_names"]),
                "unique": bool(ix["unique"]),
            }
            for ix in inspector.get_indexes(table_name)
            if ix["name"] and not ix["name"].startswith("sqlite_autoindex_")
        }

        # Implizite Unique-Indizes aus Column(unique=True) haben je nach
        # Dialekt einen automatisch vergebenen Namen (PostgreSQL:
        # "<tabelle>_<spalte>_key") und tauchen in metadata_obj nicht als
        # eigenes Index-Objekt auf. Sie gelten als abgedeckt, wenn ihre
        # Spalten exakt einer einspaltigen unique=True-Spalte entsprechen
        # (Karo-Entscheidung 2026-08-02, Punkt 7).
        implicit_unique_columns = {(col,) for col in expected_table.unique_columns}
        for idx_name, idx_info in list(actual_indexes.items()):
            if (
                idx_name not in expected_indexes
                and idx_info["unique"]
                and idx_info["columns"] in implicit_unique_columns
            ):
                del actual_indexes[idx_name]

        missing_idx = set(expected_indexes) - set(actual_indexes)
        extra_idx = set(actual_indexes) - set(expected_indexes)
        if missing_idx:
            result.errors.append(
                f"{table_name}: in db_schema.py definiert, in der Datenbank nicht vorhanden "
                f"-- Indizes {sorted(missing_idx)}"
            )
        if extra_idx:
            result.errors.append(
                f"{table_name}: in der Datenbank vorhanden, in db_schema.py nicht definiert "
                f"-- Indizes {sorted(extra_idx)}"
            )

        for idx_name in sorted(set(expected_indexes) & set(actual_indexes)):
            if expected_indexes[idx_name] != actual_indexes[idx_name]:
                result.errors.append(
                    f"{table_name}.{idx_name}: Index weicht ab "
                    f"(db_schema.py={expected_indexes[idx_name]}, "
                    f"Datenbank={actual_indexes[idx_name]})"
                )

    return result


def check_schema_matches_metadata(bind=None) -> _ComparisonResult:
    """Schema-Drift-Schutz (Issue #79): prueft, ob eine vollstaendig auf
    `head` migrierte Datenbank exakt dem entspricht, was db_schema.py
    beschreibt.

    NUR gegen eine frisch hochmigrierte Datenbank aufrufen. Gegen eine noch
    nicht migrierte Alt-Datenbank ist stattdessen
    check_schema_matches_baseline() zustaendig.
    """
    bind = bind if bind is not None else engine
    return _compare_schema_against_metadata(bind)


def stamp_baseline_if_matching(revision: str = BASELINE_REVISION) -> None:
    """Stempelt die bestehende Datenbank auf `revision`, NUR wenn das Schema
    exakt dem erwarteten Baseline-Schema entspricht. Fail-closed: wirft
    SchemaMismatchError bei jeder Abweichung, stempelt dann nichts."""
    result = check_schema_matches_baseline()
    if not result.ok:
        raise SchemaMismatchError(
            "Schema der bestehenden Datenbank weicht vom erwarteten "
            f"Baseline-Schema (Revision {revision}) ab -- kein Stempeln "
            "durchgefuehrt (fail-closed):\n  - " + "\n  - ".join(result.errors)
        )

    from alembic.config import Config
    from alembic import command
    import pathlib

    backend_dir = pathlib.Path(__file__).resolve().parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.attributes["connection"] = engine.connect()
    try:
        command.stamp(cfg, revision)
    finally:
        cfg.attributes["connection"].close()


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Nur pruefen und Ergebnis ausgeben, keine Aenderung an der Datenbank.",
    )
    parser.add_argument(
        "--revision", choices=["0001"], default=None,
        help="Bei exakter Uebereinstimmung auf diese Revision stempeln.",
    )
    parser.add_argument(
        "--against-metadata", action="store_true",
        help="Schema-Drift-Schutz: vergleicht eine auf 'head' migrierte "
             "Datenbank gegen metadata_obj aus db_schema.py statt gegen die "
             "eingefrorene Baseline 0001. Aendert nie etwas.",
    )
    args = parser.parse_args(argv)

    print(f"Datenbank: {DATABASE_URL}")
    if args.against_metadata:
        result = check_schema_matches_metadata()
        if result.ok:
            print("Schema entspricht exakt metadata_obj (db_schema.py) -- kein Drift.")
        else:
            print("Schema-Drift gegenueber db_schema.py:")
            for err in result.errors:
                print(f"  - {err}")
        return 0 if result.ok else 1

    result = check_schema_matches_baseline()
    if result.ok:
        print("Schema entspricht exakt der erwarteten Baseline (Revision 0001).")
    else:
        print("Schema weicht ab:")
        for err in result.errors:
            print(f"  - {err}")

    if args.dry_run:
        return 0 if result.ok else 1

    if args.revision == "0001":
        if not result.ok:
            print("Abbruch (fail-closed): kein Stempeln bei abweichendem Schema.", file=sys.stderr)
            return 1
        stamp_baseline_if_matching(BASELINE_REVISION)
        print(f"Datenbank auf Revision {BASELINE_REVISION} (0001) gestempelt.")
        return 0

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
