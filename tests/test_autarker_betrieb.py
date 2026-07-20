"""Tests für autarken Betrieb: SQLite in persistentem /data-Volume.

Scope: Production-Warnung ohne AILIZA_DATABASE_URL (kein Hard-Block),
absolute /data-Pfade, Persistenz über Engine-Neustart hinweg.
"""
import os
import warnings

import pytest

from apps.backend.database import _resolve_database_url


class TestAbsoluteDataPath:
    def test_absolute_data_path_accepted(self, tmp_path):
        target = tmp_path / "data" / "ailiza.sqlite"
        raw = f"sqlite:///{target}"
        result = _resolve_database_url(raw)
        assert result == f"sqlite:///{target}"
        assert target.parent.exists()


class TestDevFallback:
    def test_dev_fallback_only_warns_in_development(self, monkeypatch):
        monkeypatch.delenv("AILIZA_ENV", raising=False)
        with pytest.warns(UserWarning, match="AILIZA_DATABASE_URL nicht gesetzt"):
            result = _resolve_database_url("")
        assert result.startswith("sqlite:///")
        assert "ailiza_dev.db" in result


class TestProductionWarning:
    def test_production_without_db_url_logs_warning(self, monkeypatch):
        monkeypatch.setenv("AILIZA_ENV", "production")
        with pytest.warns(UserWarning, match="PRODUCTION"):
            _resolve_database_url("")

    def test_production_without_db_url_does_not_raise(self, monkeypatch):
        monkeypatch.setenv("AILIZA_ENV", "production")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = _resolve_database_url("")
        assert result.startswith("sqlite:///")

    def test_no_secrets_or_pii_in_db_warning(self, monkeypatch):
        monkeypatch.setenv("AILIZA_ENV", "production")
        with pytest.warns(UserWarning) as records:
            _resolve_database_url("")
        for r in records:
            msg = str(r.message)
            assert "password" not in msg.lower()
            assert "@" not in msg  # keine Connection-Strings/E-Mails


class TestTablesAndPersistence:
    def test_tables_created_in_absolute_path_db(self, tmp_path):
        from sqlalchemy import create_engine, MetaData, Table, Column, Integer

        db_path = tmp_path / "data" / "ailiza.sqlite"
        resolved = _resolve_database_url(f"sqlite:///{db_path}")
        engine = create_engine(resolved)
        meta = MetaData()
        Table("probe", meta, Column("id", Integer, primary_key=True))
        meta.create_all(engine)
        assert db_path.exists()
        engine.dispose()

    def test_user_survives_engine_restart(self, tmp_path):
        from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, insert, select

        db_path = tmp_path / "data" / "ailiza.sqlite"
        resolved = _resolve_database_url(f"sqlite:///{db_path}")

        engine1 = create_engine(resolved)
        meta1 = MetaData()
        users = Table("probe_users", meta1, Column("id", Integer, primary_key=True), Column("name", String(64)))
        meta1.create_all(engine1)
        with engine1.begin() as conn:
            conn.execute(insert(users).values(id=1, name="tester01"))
        engine1.dispose()

        # Neue Engine simuliert Neustart derselben Datei
        engine2 = create_engine(resolved)
        meta2 = MetaData()
        users2 = Table("probe_users", meta2, Column("id", Integer, primary_key=True), Column("name", String(64)))
        with engine2.begin() as conn:
            row = conn.execute(select(users2).where(users2.c.id == 1)).fetchone()
        engine2.dispose()

        assert row is not None
        assert row.name == "tester01"
