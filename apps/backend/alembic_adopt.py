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
import sys
from dataclasses import dataclass, field

from sqlalchemy import inspect

try:
    from apps.backend.database import DATABASE_URL, engine, metadata_obj
except ImportError:  # pragma: no cover - Fallback bei Ausfuehrung aus apps/backend/
    from database import DATABASE_URL, engine, metadata_obj  # type: ignore

BASELINE_REVISION = "6165ff33e9ee"


class SchemaMismatchError(Exception):
    """Bestehende Datenbank weicht vom erwarteten Baseline-Schema ab."""


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
    expected_tables = set(metadata_obj.tables.keys())

    missing = expected_tables - actual_tables
    unexpected = actual_tables - expected_tables - {"alembic_version"}
    if missing:
        result.errors.append(f"Fehlende Tabellen: {sorted(missing)}")
    if unexpected:
        result.errors.append(f"Unerwartete zusaetzliche Tabellen: {sorted(unexpected)}")

    for table_name in sorted(expected_tables & actual_tables):
        expected_table = metadata_obj.tables[table_name]
        expected_cols = {c.name: c.nullable for c in expected_table.columns}
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
            ix.name: {
                "columns": tuple(c.name for c in ix.columns),
                "unique": bool(ix.unique),
            }
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
        # eigenes Index-Objekt auftaucht (SQLAlchemy fuehrt ihn intern als
        # Column-Constraint, nicht als Table.indexes-Eintrag). Ein solcher
        # tatsaechlicher Index gilt als abgedeckt, wenn seine Spalten exakt
        # einer erwarteten einspaltigen unique=True-Spalte entsprechen.
        implicit_unique_columns = {
            (col.name,) for col in expected_table.columns if col.unique
        }
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
    args = parser.parse_args(argv)

    print(f"Datenbank: {DATABASE_URL}")
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
