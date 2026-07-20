"""Tests für Database URL Normalisierung (Postgres-Dialect-Standardisierung).

Scope: _resolve_database_url() konvertiert postgres:// und postgresql://
zu postgresql+psycopg:// für SQLAlchemy 2.0 + psycopg3 Kompatibilität.
SQLite-URLs bleiben unverändert (lokale Entwicklung).
"""
import os
from pathlib import Path

import pytest

# Isoliere _resolve_database_url() um DB-Connection zu vermeiden
from apps.backend.database import _resolve_database_url


class TestDatabaseUrlNormalization:
    """Postgres URL dialect normalization for psycopg3 compatibility."""

    def test_normalizes_postgres_scheme_to_psycopg(self):
        """postgres:// wird zu postgresql+psycopg:// konvertiert."""
        raw = "postgres://user:pass@localhost/dbname"
        result = _resolve_database_url(raw)
        assert result.startswith("postgresql+psycopg://")
        assert "user:pass@localhost/dbname" in result

    def test_normalizes_postgresql_scheme_to_psycopg(self):
        """postgresql:// wird zu postgresql+psycopg:// konvertiert."""
        raw = "postgresql://user:pass@localhost/dbname"
        result = _resolve_database_url(raw)
        assert result.startswith("postgresql+psycopg://")

    def test_preserves_query_string_in_normalization(self):
        """Query-Parameter (z.B. ?sslmode=require) bleiben erhalten."""
        raw = "postgres://user:pass@host/db?sslmode=require"
        result = _resolve_database_url(raw)
        assert "sslmode=require" in result

    def test_leaves_postgresql_psycopg_untouched(self):
        """postgresql+psycopg:// wird nicht nochmal verändert."""
        raw = "postgresql+psycopg://user:pass@localhost/dbname"
        result = _resolve_database_url(raw)
        assert result == raw

    def test_leaves_sqlite_untouched(self):
        """SQLite-URLs werden nicht angerührt (lokale Entwicklung)."""
        # Absolute SQLite-Path
        raw = "sqlite:////tmp/test.db"
        result = _resolve_database_url(raw)
        assert result.startswith("sqlite:///")
        assert "test.db" in result

    def test_sqlite_memory_untouched(self):
        """SQLite :memory: wird nicht verändert."""
        raw = "sqlite:///:memory:"
        result = _resolve_database_url(raw)
        assert result == raw

    def test_empty_url_uses_dev_fallback_sqlite(self):
        """Leere URL → Dev-Fallback mit SQLite (warnt, aber funktioniert)."""
        raw = ""
        with pytest.warns(UserWarning, match="AILIZA_DATABASE_URL nicht gesetzt"):
            result = _resolve_database_url(raw)
        assert result.startswith("sqlite:///")
        assert "ailiza_dev.db" in result

    def test_neon_real_world_url(self):
        """Real-world Neon connection string wird korrekt normalisiert."""
        # Neon gibt postgres:// oder postgresql:// aus
        raw = "postgresql://neondb_owner:secret@ep-red-snow.c-4.eu-central-1.aws.neon.tech/neondb?sslmode=require"
        result = _resolve_database_url(raw)
        assert result.startswith("postgresql+psycopg://")
        assert "neondb_owner" in result
        assert "sslmode=require" in result
