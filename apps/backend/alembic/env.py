"""AILIZA Alembic-Umgebung.

WICHTIG: Diese Datei wird NUR geladen, wenn die Alembic-CLI explizit
aufgerufen wird (`alembic upgrade head`, `alembic revision ...`) -- ein
normaler Python-Import von apps.backend.* fuehrt NIE zu einem Migrationslauf.

Liest dieselbe DATABASE_URL wie die Anwendung selbst (apps.backend.database),
damit Migrations-Tool und Laufzeit-Engine niemals auf unterschiedliche
Datenbanken zeigen koennen. target_metadata ist dieselbe SQLAlchemy-
MetaData-Instanz (metadata_obj), die auch ensure_sqlite_schema()/
init_db() verwenden -- kein zweites, unabhaengig gepflegtes Schema.
"""
from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Repo-Root auf sys.path, damit "apps.backend.database" unabhaengig vom
# Arbeitsverzeichnis importierbar ist (alembic wird sowohl aus dem
# Repo-Root als auch aus apps/backend heraus unterstuetzt).
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from apps.backend.database import DATABASE_URL
    from apps.backend.db_schema import metadata_obj
except ImportError:
    # Fallback fuer den Fall, dass apps/backend selbst als Package-Root
    # importiert wird (gleiches Muster wie im restlichen Backend).
    sys.path.insert(0, str(_THIS_DIR.parent))
    from database import DATABASE_URL  # type: ignore
    from db_schema import metadata_obj  # type: ignore

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata_obj

# DATABASE_URL wird bewusst hier gesetzt statt im .ini-File hinterlegt --
# einzige Quelle der Wahrheit ist apps.backend.database._resolve_database_url().
config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))


def run_migrations_offline() -> None:
    """Erzeugt reines SQL ohne DB-Verbindung (`alembic upgrade head --sql`)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Verbindet sich mit der Ziel-Datenbank und wendet Migrationen an."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite unterstuetzt kein natives ALTER TABLE fuer viele Faelle --
            # render_as_batch erzeugt stattdessen Kopier-Migrationen. Fuer
            # Postgres wirkungslos (dort ohnehin natives ALTER TABLE).
            render_as_batch=connection.engine.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
