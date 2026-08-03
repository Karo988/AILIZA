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

# Exakte (tabelle, spalte)-Paare, die in
# apps/backend/alembic/versions/0003_add_missing_columns_postgres_drift.py
# additiv per op.add_column() nachgeruestet werden. Diese Liste ist die
# EINZIGE erlaubte Toleranz-Allowlist fuer stamp_baseline_with_tolerance() --
# sie wurde bewusst 1:1 aus 0003 uebernommen (nicht neu erfunden), damit
# Toleranz und Migration nie auseinanderlaufen. Jede andere fehlende Spalte
# oder Tabelle bleibt hart fail-closed abgelehnt.
KNOWN_ADDITIVE_GAPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("audit_logs", "tenant_id"),
        ("approval_requests", "tenant_id"),
        ("approval_requests", "owner_user_id"),
        ("agent_runs", "tenant_id"),
        ("agent_runs", "owner_user_id"),
        ("users", "failed_login_attempts"),
        ("users", "locked_until"),
        ("user_projects", "version"),
        ("user_chats", "version"),
        ("user_chats", "keep_uploaded_documents"),
        ("user_chats", "document_retention_days"),
    }
)


class SchemaMismatchError(Exception):
    """Bestehende Datenbank weicht vom erwarteten Baseline-Schema ab."""


class UnknownAdditiveGapError(Exception):
    """CLI/Aufrufer hat eine Spalte als Toleranz angefragt, die NICHT in
    KNOWN_ADDITIVE_GAPS gelistet ist -- wird immer abgelehnt."""


@dataclass
class _ComparisonResult:
    errors: list[str] = field(default_factory=list)
    tolerated: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _compare_schema(bind, allow_gaps: frozenset[tuple[str, str]] | None = None) -> _ComparisonResult:
    result = _ComparisonResult()
    inspector = inspect(bind)
    allow_gaps = allow_gaps or frozenset()

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
        # Nur Spalten tolerieren, die (a) in dieser Pruefung explizit per
        # allow_gaps angefragt UND (b) in KNOWN_ADDITIVE_GAPS gelistet sind.
        tolerated_cols = {
            c for c in missing_cols
            if (table_name, c) in allow_gaps and (table_name, c) in KNOWN_ADDITIVE_GAPS
        }
        hard_missing_cols = missing_cols - tolerated_cols
        extra_cols = set(actual_cols) - set(expected_cols)
        if hard_missing_cols:
            result.errors.append(f"{table_name}: fehlende Spalten {sorted(hard_missing_cols)}")
        if tolerated_cols:
            for c in sorted(tolerated_cols):
                result.tolerated.append(f"{table_name}.{c}")
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

    _do_stamp(revision)


def _do_stamp(revision: str) -> None:
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


def stamp_baseline_with_tolerance(
    allow_gaps: set[tuple[str, str]] | None = None,
    revision: str = BASELINE_REVISION,
) -> None:
    """Stempelt die bestehende Datenbank auf `revision` -- toleriert dabei
    NUR fehlende Spalten, die explizit per `allow_gaps` bestaetigt UND
    gleichzeitig in KNOWN_ADDITIVE_GAPS gelistet sind (die Menge, die
    0003_add_missing_columns_postgres_drift.py additiv nachruestet).

    Keine automatische/pauschale Toleranz: ohne `allow_gaps` verhaelt sich
    diese Funktion identisch zu stamp_baseline_if_matching() (streng
    fail-closed). Fehlt irgendeine ANDERE Spalte (nicht in der Allowlist),
    fehlt eine ganze Tabelle, oder gibt es sonstige Abweichungen (Indizes,
    nullable, unerwartete Spalten/Tabellen) -- wird weiterhin hart
    abgelehnt, ohne Ausnahme.

    Dies ist eine bewusste, protokollierte Ausnahme (Audit-Nachvollziehbarkeit):
    jede tolerierte Spalte wird explizit geloggt.
    """
    allow_gaps = allow_gaps or set()
    unknown = allow_gaps - KNOWN_ADDITIVE_GAPS
    if unknown:
        raise UnknownAdditiveGapError(
            "Abbruch (fail-closed): folgende angefragte Toleranzen sind NICHT "
            f"in KNOWN_ADDITIVE_GAPS (0003-Migration) gelistet und werden "
            f"daher abgelehnt: {sorted(unknown)}"
        )

    result = _compare_schema(engine, allow_gaps=frozenset(allow_gaps))
    if not result.ok:
        raise SchemaMismatchError(
            "Schema der bestehenden Datenbank weicht vom erwarteten "
            f"Baseline-Schema (Revision {revision}) ab -- kein Stempeln "
            "durchgefuehrt (fail-closed), auch mit Toleranz-Mechanismus:\n  - "
            + "\n  - ".join(result.errors)
        )

    if result.tolerated:
        print(
            "Bewusste, protokollierte Ausnahme (Audit): folgende fehlende "
            "Spalten wurden explizit toleriert, weil sie in "
            "0003_add_missing_columns_postgres_drift.py additiv nachgerüstet "
            f"werden: {result.tolerated}"
        )
    else:
        print("Keine Toleranz-Spalten benoetigt -- Schema entspricht exakt der Baseline.")

    _do_stamp(revision)
    print(
        f"Datenbank mit Toleranz-Mechanismus auf Revision {revision} gestempelt "
        f"(tolerierte Spalten: {result.tolerated if result.tolerated else 'keine'})."
    )


def _parse_allow_additive_gap(raw: str) -> set[tuple[str, str]]:
    """Parst `--allow-additive-gap tabelle.spalte,tabelle2.spalte2` und
    validiert jeden Eintrag gegen KNOWN_ADDITIVE_GAPS. Wirft bei jedem
    unbekannten Eintrag ab (fail-closed, keine stille Ignorierung)."""
    gaps: set[tuple[str, str]] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "." not in item:
            raise UnknownAdditiveGapError(
                f"Ungueltiges Format fuer --allow-additive-gap: '{item}' "
                "(erwartet: tabelle.spalte)"
            )
        table_name, column_name = item.split(".", 1)
        pair = (table_name, column_name)
        if pair not in KNOWN_ADDITIVE_GAPS:
            raise UnknownAdditiveGapError(
                f"'{item}' ist NICHT in KNOWN_ADDITIVE_GAPS gelistet (nur "
                "Spalten aus 0003_add_missing_columns_postgres_drift.py "
                "duerfen toleriert werden) -- Abbruch (fail-closed)."
            )
        gaps.add(pair)
    return gaps


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
        "--allow-additive-gap", default=None, metavar="tabelle.spalte[,tabelle2.spalte2,...]",
        help=(
            "Explizite, protokollierte Ausnahme: toleriert genau diese fehlenden "
            "Spalten beim Stempeln (nur zusammen mit --revision 0001), sofern sie "
            "in KNOWN_ADDITIVE_GAPS (0003_add_missing_columns_postgres_drift.py) "
            "gelistet sind. Jeder nicht gelistete Wert fuehrt zum Abbruch."
        ),
    )
    args = parser.parse_args(argv)

    allow_gaps: set[tuple[str, str]] | None = None
    if args.allow_additive_gap:
        try:
            allow_gaps = _parse_allow_additive_gap(args.allow_additive_gap)
        except UnknownAdditiveGapError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    print(f"Datenbank: {DATABASE_URL}")
    result = check_schema_matches_baseline() if not allow_gaps else _compare_schema(
        engine, allow_gaps=frozenset(allow_gaps)
    )
    if result.ok:
        if result.tolerated:
            print(
                "Schema entspricht der Baseline (Revision 0001) unter Toleranz "
                f"folgender explizit bestaetigter Spalten: {result.tolerated}"
            )
        else:
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
        if allow_gaps:
            stamp_baseline_with_tolerance(allow_gaps=allow_gaps, revision=BASELINE_REVISION)
        else:
            stamp_baseline_if_matching(BASELINE_REVISION)
            print(f"Datenbank auf Revision {BASELINE_REVISION} (0001) gestempelt.")
        return 0

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
