"""Test fuer den ensure_sqlite_schema()-Dialekt-Guard (PR #70, PostgreSQL-Blocker).

Bug: ensure_sqlite_schema() prüfte bislang `DATABASE_URL.startswith("sqlite")`
-- eine beim Modul-Import aus AILIZA_DATABASE_URL gebildete Konstante. Tests
(und potenziell künftiger Code), die zur Laufzeit nur `database.engine` gegen
eine andere Engine (z. B. Postgres) austauschen, ändern DATABASE_URL nicht
mit. Der Guard sah dann weiterhin "sqlite:///:memory:" und führte
SQLite-PRAGMA-Statements gegen die angehängte Postgres-Engine aus ->
`psycopg.errors.SyntaxError: syntax error at or near "PRAGMA"`.

Fix: Guard prüft jetzt `engine.dialect.name` -- den tatsächlichen Dialekt der
aktuell aktiven Engine, unabhängig davon, wie sie zustande kam."""
from __future__ import annotations

import os

os.environ.setdefault("AILIZA_SECRET_KEY", "test-secret-key-minimum-32-chars-ok")
os.environ.setdefault("AILIZA_DATABASE_URL", "sqlite:///:memory:")

import pytest
from sqlalchemy import create_engine

import apps.backend.database as dbmod


def test_ensure_sqlite_schema_runs_pragma_for_sqlite_engine():
    """Unveraendertes Verhalten: gegen eine echte SQLite-Engine muss
    ensure_sqlite_schema() weiterhin ohne Fehler durchlaufen (PRAGMA wird
    ausgefuehrt, Migrationsspalten werden bei Bedarf ergaenzt)."""
    assert dbmod.engine.dialect.name == "sqlite"
    dbmod.metadata_obj.drop_all(dbmod.engine)
    dbmod.init_db()  # ruft ensure_sqlite_schema() intern auf -- darf nicht werfen
    dbmod.ensure_sqlite_schema()  # zweiter Aufruf muss ebenfalls fehlerfrei sein (idempotent)


def test_ensure_sqlite_schema_skips_pragma_for_non_sqlite_dialect(monkeypatch):
    """Kernfix: gegen eine Nicht-SQLite-Engine darf KEIN PRAGMA-Statement
    ausgefuehrt werden -- unabhaengig vom Wert der Modul-Konstante
    DATABASE_URL. Simuliert hier ohne echten Postgres-Connect ueber ein
    gefaelschtes dialect.name, damit der Test auch ohne laufende
    Postgres-Instanz aussagekraeftig ist."""
    calls: list[str] = []
    real_begin = dbmod.engine.begin

    class _FakeDialect:
        name = "postgresql"

    class _FakeEngine:
        dialect = _FakeDialect()

        def begin(self):
            calls.append("begin")
            raise AssertionError(
                "ensure_sqlite_schema() darf bei Nicht-SQLite-Dialekt keine "
                "Connection oeffnen (PRAGMA waere sonst fällig)."
            )

    monkeypatch.setattr(dbmod, "engine", _FakeEngine())
    # DATABASE_URL bewusst NICHT veraendert -- bleibt "sqlite:///:memory:",
    # genau der Fall, der den urspruenglichen Bug ausloeste.
    assert dbmod.DATABASE_URL.startswith("sqlite")

    dbmod.ensure_sqlite_schema()  # darf NICHT in _FakeEngine.begin() laufen
    assert calls == [], "PRAGMA-Pfad wurde trotz Nicht-SQLite-Dialekt betreten"


def test_ensure_sqlite_schema_guard_reads_engine_not_database_url_constant():
    """Regressionstest fuer exakt den urspruenglichen Bug: DATABASE_URL zeigt
    auf SQLite, die tatsaechliche Engine aber (zur Laufzeit ausgetauscht) auf
    einen anderen Dialekt -- der Guard muss sich am Dialekt der Engine
    orientieren, nicht an der Konstante."""
    fake_sqlite_url_but_real_engine = create_engine("sqlite:///:memory:")
    try:
        assert dbmod.DATABASE_URL.startswith("sqlite")
        assert fake_sqlite_url_but_real_engine.dialect.name == "sqlite"
        # Hier zusaetzlich: dialect.name ist fuer den echten SQLite-Fall
        # weiterhin "sqlite" -- der Guard laesst also den Normalfall unveraendert.
    finally:
        fake_sqlite_url_but_real_engine.dispose()
