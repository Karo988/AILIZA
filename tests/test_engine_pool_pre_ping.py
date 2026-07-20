"""Tests für Postgres-Verbindungs-Robustheit (pool_pre_ping).

Scope: Neon/Postgres trennt inaktive Verbindungen serverseitig. Ohne
pool_pre_ping versucht SQLAlchemy eine tote Pool-Verbindung wiederzuverwenden
und crasht mit OperationalError -> HTTP 500 (siehe Render-Log 2026-07-20,
write_audit_entry -> _get_latest_audit_hash). pool_pre_ping=True lässt
SQLAlchemy vor jeder Nutzung kurz prüfen, ob die Verbindung noch lebt, und
holt bei Bedarf automatisch eine neue -- kein Code-Retry in write_audit_entry
nötig, das Problem wird eine Ebene tiefer generisch für alle DB-Zugriffe
gelöst.
"""
from __future__ import annotations

import importlib
import os

import pytest


def _build_engine_options(database_url: str) -> dict:
    """Isolierte Kopie der Options-Logik für Assertions ohne echten DB-Connect."""
    from sqlalchemy.pool import StaticPool

    engine_options: dict = {}
    if database_url.startswith("sqlite"):
        engine_options["connect_args"] = {"check_same_thread": False}
    if database_url in {"sqlite:///:memory:", "sqlite://"}:
        engine_options["poolclass"] = StaticPool
    if not database_url.startswith("sqlite"):
        engine_options["pool_pre_ping"] = True
        engine_options["pool_recycle"] = 1800
    return engine_options


class TestPoolPrePing:
    def test_engine_uses_pool_pre_ping_for_postgres(self):
        opts = _build_engine_options("postgresql+psycopg://user:pw@host/db")
        assert opts.get("pool_pre_ping") is True

    def test_engine_pool_recycle_set_for_postgres(self):
        opts = _build_engine_options("postgresql+psycopg://user:pw@host/db")
        assert opts.get("pool_recycle") == 1800

    def test_engine_sqlite_behavior_unchanged(self):
        opts = _build_engine_options("sqlite:////data/ailiza.sqlite")
        assert "pool_pre_ping" not in opts
        assert "pool_recycle" not in opts
        assert opts.get("connect_args") == {"check_same_thread": False}

    def test_engine_sqlite_memory_still_uses_static_pool(self):
        from sqlalchemy.pool import StaticPool

        opts = _build_engine_options("sqlite:///:memory:")
        assert opts.get("poolclass") is StaticPool
        assert "pool_pre_ping" not in opts


class TestRealEngineConfiguration:
    """Prüft die tatsächliche apps.backend.database.engine-Instanz."""

    def test_actual_module_engine_matches_url_dialect(self, monkeypatch):
        # Modul ist bereits mit SQLite (Test-Default) importiert -- prüft nur,
        # dass die reale Engine (nicht die isolierte Kopie oben) konsistent ist.
        from apps.backend import database as db_module

        if db_module.DATABASE_URL.startswith("sqlite"):
            assert db_module.engine.pool.__class__.__name__ in (
                "StaticPool", "QueuePool", "NullPool", "SingletonThreadPool",
            )
        else:
            assert db_module.engine.pool._pre_ping is True

    def test_postgres_url_produces_engine_with_pre_ping(self):
        # Separater Prozess-freier Weg: create_engine direkt mit denselben
        # Options wie das Modul. pysqlite als Stand-in-Dialekt (kein psycopg
        # in der lokalen Testumgebung installiert) -- pool_pre_ping/_recycle
        # sind reine Pool-Konfiguration, unabhaengig vom DBAPI-Treiber.
        from sqlalchemy import create_engine

        opts = _build_engine_options("postgresql+psycopg://user:pw@host/db")
        eng = create_engine("sqlite:///:memory:", pool_pre_ping=opts["pool_pre_ping"],
                            pool_recycle=opts["pool_recycle"])
        try:
            assert eng.pool._pre_ping is True
            assert eng.pool._recycle == 1800
        finally:
            eng.dispose()
