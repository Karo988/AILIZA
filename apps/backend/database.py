from __future__ import annotations

import logging
import os
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, MetaData, String, Table, Text, create_engine, delete, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

try:
    from .governance.field_crypto import encrypt_field, decrypt_field, encrypt_json, decrypt_json
except ImportError:
    from governance.field_crypto import encrypt_field, decrypt_field, encrypt_json, decrypt_json  # type: ignore

logger = logging.getLogger(__name__)

_RAW_DB_URL = os.getenv("AILIZA_DATABASE_URL", "")

def _resolve_database_url(raw: str) -> str:
    """
    Wandelt den konfigurierten DB-URL in einen stabilen absoluten Pfad um.

    Regeln:
    - Kein AILIZA_DATABASE_URL gesetzt → relativer Fallback mit Warnung (Dev-Modus)
    - Relativer sqlite-Pfad → zu absolutem Pfad aufgelöst, Warnung ausgegeben
    - Absoluter Pfad → unverändert übernommen
    - postgres:// oder postgresql:// → postgresql+psycopg:// (psycopg3-Kompatibilität)
    - postgresql+psycopg:// → unverändert
    - Andere DB-Typen → unverändert
    - Verzeichnis wird ggf. angelegt (nur bei sqlite)
    """
    if not raw:
        # Dev-Fallback: relativ zum Repo-Root (apps/backend/../..)
        repo_root = Path(__file__).resolve().parent.parent.parent
        fallback = repo_root / "data" / "ailiza_dev.db"
        if os.getenv("AILIZA_ENV", "development").strip().lower() == "production":
            # Fail-soft (kein Hard-Block): App bleibt erreichbar, aber ohne
            # persistenten Speicher droht Datenverlust bei jedem Neustart.
            warnings.warn(
                "PRODUCTION-WARNUNG: AILIZA_ENV=production, aber AILIZA_DATABASE_URL "
                "ist nicht gesetzt. Daten gehen bei jedem Neustart/Deploy verloren. "
                "Fuer autarken Betrieb: AILIZA_DATABASE_URL=sqlite:////data/ailiza.sqlite "
                "mit persistentem Volume setzen (siehe docs/AUTARKER_BETRIEB.md).",
                stacklevel=2,
            )
        else:
            warnings.warn(
                f"AILIZA_DATABASE_URL nicht gesetzt. Dev-Fallback: {fallback}. "
                "In Produktion AILIZA_DATABASE_URL mit absolutem Pfad setzen.",
                stacklevel=2,
            )
        raw = f"sqlite:///{fallback}"

    # Postgres-Dialekt-Normalisierung: postgres:// oder postgresql:// → postgresql+psycopg://
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql+psycopg://", 1)
    elif raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+psycopg://", 1)

    if not raw.startswith("sqlite"):
        return raw  # Normalisiert oder andere DB-Typen

    # sqlite:///./pfad  oder  sqlite:///relativer/pfad
    prefix = "sqlite:///"
    path_str = raw[len(prefix):]

    if path_str.startswith(":"):
        return raw  # sqlite:///:memory:

    p = Path(path_str)
    if not p.is_absolute():
        # Relativen Pfad zu absolutem Pfad auflösen (Repo-Root als Basis)
        repo_root = Path(__file__).resolve().parent.parent.parent
        p = (repo_root / p).resolve()
        warnings.warn(
            f"AILIZA_DATABASE_URL enthält relativen Pfad — aufgelöst zu: {p}. "
            "Empfehlung: absoluten Pfad setzen (4 Slashes: sqlite:////absolut/pfad.db).",
            stacklevel=2,
        )
    else:
        p = p.resolve()

    # Verzeichnis anlegen falls nicht vorhanden
    p.parent.mkdir(parents=True, exist_ok=True)

    return f"sqlite:///{p}"


DATABASE_URL = _resolve_database_url(_RAW_DB_URL)
DEFAULT_TENANT_ID = os.getenv("AILIZA_DEFAULT_TENANT_ID", "default")

engine_options: dict[str, Any] = {}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
if DATABASE_URL in {"sqlite:///:memory:", "sqlite://"}:
    engine_options["poolclass"] = StaticPool
if not DATABASE_URL.startswith("sqlite"):
    # Neon/Postgres trennt inaktive Verbindungen serverseitig. Ohne
    # pool_pre_ping wuerde SQLAlchemy eine tote Pool-Verbindung wiederverwenden
    # und mit OperationalError abstuerzen (HTTP 500) -- pool_pre_ping prueft
    # vor jeder Nutzung kurz, ob die Verbindung noch lebt, und holt bei Bedarf
    # automatisch eine neue. pool_recycle erneuert Verbindungen zusaetzlich
    # praeventiv, bevor Neon sie von sich aus killt.
    engine_options["pool_pre_ping"] = True
    engine_options["pool_recycle"] = 1800

engine: Engine = create_engine(DATABASE_URL, **engine_options)

metadata_obj = MetaData()
_UNSET = object()

audit_logs = Table(
    "audit_logs",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("action", String(255), nullable=False),
    Column("metadata", JSON, nullable=False, default=dict),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    # Audit-Vault Stufe 2: Hash-Chain (append-only Integritätssicherung)
    Column("previous_hash", String(64), nullable=False, default="0" * 64),
    Column("entry_hash", String(64), nullable=False, default=""),
)

approval_requests = Table(
    "approval_requests",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("run_id", String(36), nullable=True),
    Column("tool", String(64), nullable=False),
    Column("input_params", JSON, nullable=False),
    Column("risk_level", String(32), nullable=False),
    Column("risk_reason", Text, nullable=False),
    Column("required_approver_roles", JSON, nullable=True),
    Column("status", String(32), nullable=False, default="pending"),
    Column("resolved_at", DateTime(timezone=True), nullable=True),
    Column("note", Text, nullable=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)

agent_runs = Table(
    "agent_runs",
    metadata_obj,
    Column("id", String(36), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("task", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("pending_approval_id", Integer, nullable=True),
    Column("result", JSON, nullable=True),
    Column("run_metadata", JSON, nullable=False, default=dict),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
)

# ── Getrennte Logs (KEINE Inhalte, keine Prompts, keine Secrets) ─────────────
security_logs = Table(
    "security_logs",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("incident_type", String(64), nullable=False),
    Column("severity", String(32), nullable=False),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)

performance_logs = Table(
    "performance_logs",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("latency_ms", Integer, nullable=False),
    Column("route", String(32), nullable=True),
    Column("provider", String(64), nullable=True),
    Column("error_type", String(64), nullable=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)

cost_logs = Table(
    "cost_logs",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("tokens_in", Integer, nullable=False, default=0),
    Column("tokens_out", Integer, nullable=False, default=0),
    Column("provider", String(64), nullable=True),
    Column("model", String(128), nullable=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("use_case", String(128), nullable=True),
    Column("cost_estimate", Float, nullable=False, default=0.0),
    Column("expires_at", DateTime(timezone=True), nullable=True),
)

reflection_facts = Table(
    "reflection_facts",
    metadata_obj,
    Column("id", String(36), primary_key=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("user_id", String(64), nullable=True),
    Column("data_classes", JSON, nullable=True),
    Column("content", Text, nullable=False),
    Column("quality_score", Float, nullable=False, default=1.0),
    Column("opt_in_confirmed", Integer, nullable=False, default=0),
    Column("created_at", String(40), nullable=False),
    Column("expires_at", String(40), nullable=False),
    Column("source", String(64), nullable=True),
    Column("purpose", String(128), nullable=True),
    Column("pii_cleared", Integer, nullable=False, default=0),
)

feedback = Table(
    "feedback",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("run_id", String(36), nullable=True),
    Column("rating", String(32), nullable=False),
    Column("reason", Text, nullable=True),
    Column("quality_score_delta", Float, nullable=False, default=0.0),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

routing_proposals = Table(
    "routing_proposals",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("trigger_type", String(64), nullable=False),
    Column("description", Text, nullable=True),
    Column("previous_route", String(32), nullable=True),
    Column("proposed_route", String(32), nullable=True),
    Column("status", String(32), nullable=False, default="pending"),
    Column("changed_by", String(64), nullable=True),
    Column("reason", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("confirmed_at", DateTime(timezone=True), nullable=True),
    Column("policy_version", String(32), nullable=True),
)

kill_switch_state = Table(
    "kill_switch_state",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("enabled", Integer, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

users = Table(
    "users",
    metadata_obj,
    Column("user_id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("role", String(32), nullable=False, default="user"),
    Column("hashed_password", String(256), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("active", Integer, nullable=False, default=1),
    Column("failed_login_attempts", Integer, nullable=False, default=0),
    Column("locked_until", DateTime(timezone=True), nullable=True),
)

# ── Mini-PR 1 (Gedaechtnis-Governance v1): Profil bleibt technisch/klein,
# aenderbare Arbeits-/Bedienpraeferenzen kommen in eine eigene Tabelle.
# Kein Gedaechtnis (memory_items) -- das ist bewusst NICHT Teil dieser PR,
# siehe docs/DATABASE_MEMORY_GOVERNANCE_V1.md.
user_settings = Table(
    "user_settings",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("antwortlaenge", String(32), nullable=False, default="normal"),
    Column("ton", String(32), nullable=False, default="freundlich"),
    Column("sprache", String(8), nullable=True),
    Column("ausgabeformat", String(32), nullable=True),
    Column("ui_prefs", JSON, nullable=False, default=dict),
    Column("benachrichtigungen", JSON, nullable=False, default=dict),
    # Datensparsamer Default: kein automatisches Merken, keine sichtbaren
    # Zusammenfassungen, ohne dass der Nutzer aktiv zustimmt (Karo-Leitbild
    # "kein heimliches Profiling"). Vorschlaege sind erlaubt (an/aus je
    # Vorschlag pruefbar), Speichermodus fragt standardmaessig nach.
    Column("aktives_merken", Integer, nullable=False, default=0),
    Column("sichtbare_zusammenfassungen_erlaubt", Integer, nullable=False, default=0),
    Column("erinnerungs_vorschlaege_erlaubt", Integer, nullable=False, default=1),
    Column("speichermodus", String(32), nullable=False, default="immer_fragen"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_user_settings_user_tenant", "user_id", "tenant_id", unique=True),
)


messenger_bindings = Table(
    "messenger_bindings",
    metadata_obj,
    Column("chat_id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("telegram_username", String(128), nullable=True),
    Column("opt_in_confirmed", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("opt_in_at", DateTime(timezone=True), nullable=True),
)

totp_secrets = Table(
    "totp_secrets",
    metadata_obj,
    Column("user_id", String(64), primary_key=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("secret_b32", String(64), nullable=False),
    Column("confirmed", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("confirmed_at", DateTime(timezone=True), nullable=True),
)

totp_backup_codes = Table(
    "totp_backup_codes",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("code_hash", String(64), nullable=False),
    Column("used", Integer, nullable=False, default=0),
    Column("used_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

skills = Table(
    "skills",
    metadata_obj,
    Column("skill_id", String(36), primary_key=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("name", String(128), nullable=False),
    Column("description", String(512), nullable=True),
    Column("steps_summary", Text, nullable=False),
    Column("data_classes", JSON, nullable=True),
    Column("risk_level", String(32), nullable=False, default="medium"),
    Column("gdpr_purpose", String(256), nullable=True),
    Column("source_run_id", String(36), nullable=True),
    Column("proposed_by", String(64), nullable=True),
    Column("status", String(32), nullable=False, default="pending"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("approved_at", DateTime(timezone=True), nullable=True),
    Column("approved_by", String(64), nullable=True),
    Column("rejection_reason", String(512), nullable=True),
)


# ── Serverseitige Speicherung: Projekte + Chats (Teilschritt 1) ──────────────
# Karo-Wunsch 2026-07-16: Projekte/Chats sollen an das Nutzerkonto gebunden
# und geraeteuebergreifend (Handy <-> Laptop) verfuegbar sein, statt nur im
# Browser-localStorage. Strikte Mandanten- UND Nutzertrennung: jede Query
# filtert IMMER nach tenant_id UND user_id. Keine Secrets/Rohdaten hier -
# Chatnachrichten werden bereits geschwaerzt/pseudonymisiert gespeichert.
# retention_until ist vorbereitet, aber es gibt (bewusst) noch KEINE
# automatische Loeschung (Betreiber-Entscheidung 2026-07-16).
user_projects = Table(
    "user_projects",
    metadata_obj,
    # Zusammengesetzter Primary Key: jeder (tenant_id, user_id) hat seinen
    # eigenen id-Namensraum -> vollstaendige Isolation, kein Hijack ueber
    # eine kollidierende id (Karo-Fund im Teilschritt-1-Test).
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), primary_key=True, nullable=False, default=DEFAULT_TENANT_ID),
    Column("user_id", String(64), primary_key=True, nullable=False),
    # Text statt String(256): verschlüsselte Werte (Base64 + AES-GCM-Overhead)
    # sind laenger als der Klartext -> muss auch unter Postgres nicht abschneiden.
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("priority", String(32), nullable=True),
    Column("chat_id", String(64), nullable=True),
    Column("files", JSON, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("retention_until", DateTime(timezone=True), nullable=True),
    Column("version", Integer, nullable=False, default=1),
    Index("ix_user_projects_tenant_user", "tenant_id", "user_id"),
)

user_chats = Table(
    "user_chats",
    metadata_obj,
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), primary_key=True, nullable=False, default=DEFAULT_TENANT_ID),
    Column("user_id", String(64), primary_key=True, nullable=False),
    Column("project_id", String(64), nullable=True),  # None = projektloser Chat
    # Text statt String(256): verschluesselter Titel ist laenger als Klartext.
    Column("title", Text, nullable=True),
    Column("messages", JSON, nullable=False, default=list),
    Column("message_count", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("retention_until", DateTime(timezone=True), nullable=True),
    Column("version", Integer, nullable=False, default=1),
    Index("ix_user_chats_tenant_user", "tenant_id", "user_id"),
)


def init_db() -> None:
    metadata_obj.create_all(engine)
    ensure_sqlite_schema()


def _add_column_if_missing(connection, table: str, column: str, ddl_type: str) -> None:
    cols = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})").all()}
    if cols and column not in cols:
        connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def ensure_sqlite_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    with engine.begin() as connection:
        approval_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(approval_requests)").all()
        }
        if approval_columns and "run_id" not in approval_columns:
            connection.exec_driver_sql("ALTER TABLE approval_requests ADD COLUMN run_id VARCHAR(36)")
        # tenant_id Migration fuer Bestandstabellen
        tenant_ddl = f"VARCHAR(64) DEFAULT '{DEFAULT_TENANT_ID}'"
        for table in ("audit_logs", "approval_requests", "agent_runs"):
            _add_column_if_missing(connection, table, "tenant_id", tenant_ddl)
        # Account-Lockout-Felder fuer bestehende users-Tabellen
        _add_column_if_missing(connection, "users", "failed_login_attempts", "INTEGER DEFAULT 0")
        _add_column_if_missing(connection, "users", "locked_until", "DATETIME")
        # Version-Spalte fuer serverseitige Speicherung (Optimistic Locking)
        _add_column_if_missing(connection, "user_projects", "version", "INTEGER DEFAULT 1")
        _add_column_if_missing(connection, "user_chats", "version", "INTEGER DEFAULT 1")
        # TOTP-Felder (Tabellen werden durch metadata_obj.create_all angelegt)


def get_kill_switch_flag() -> bool | None:
    """Liest optionales DB-Flag fuer den Kill-Switch. None = nicht gesetzt."""
    try:
        with engine.begin() as connection:
            row = connection.execute(
                select(kill_switch_state.c.enabled).order_by(kill_switch_state.c.id.desc()).limit(1)
            ).first()
    except Exception:
        return None
    if not row or row[0] is None:
        return None
    return bool(row[0])


# ── Getrennte Log-Writer ─────────────────────────────────────────────────────
def write_security_log(incident_type: str, severity: str, tenant_id: str = DEFAULT_TENANT_ID,
                       expires_at: datetime | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(insert(security_logs).values(
            timestamp=datetime.now(timezone.utc), incident_type=incident_type,
            severity=severity, tenant_id=tenant_id, expires_at=expires_at))


def write_performance_log(latency_ms: int, route: str | None, provider: str | None,
                          error_type: str | None, tenant_id: str = DEFAULT_TENANT_ID,
                          expires_at: datetime | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(insert(performance_logs).values(
            timestamp=datetime.now(timezone.utc), latency_ms=latency_ms, route=route,
            provider=provider, error_type=error_type, tenant_id=tenant_id, expires_at=expires_at))


def write_cost_log(tokens_in: int, tokens_out: int, provider: str | None, model: str | None,
                   tenant_id: str = DEFAULT_TENANT_ID, use_case: str | None = None,
                   cost_estimate: float = 0.0, expires_at: datetime | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(insert(cost_logs).values(
            timestamp=datetime.now(timezone.utc), tokens_in=tokens_in, tokens_out=tokens_out,
            provider=provider, model=model, tenant_id=tenant_id, use_case=use_case,
            cost_estimate=cost_estimate, expires_at=expires_at))


def list_performance_logs(tenant_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    query = select(performance_logs).order_by(performance_logs.c.timestamp.desc()).limit(limit)
    if tenant_id is not None:
        query = query.where(performance_logs.c.tenant_id == tenant_id)
    with engine.begin() as connection:
        return [dict(r) for r in connection.execute(query).mappings().all()]


def _compute_audit_hash(entry_id: int, timestamp: str, action: str,
                        tenant_id: str, previous_hash: str) -> str:
    """SHA-256 Hash-Chain für Audit-Vault Stufe 2."""
    import hashlib
    raw = f"{entry_id}|{timestamp}|{action}|{tenant_id}|{previous_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_latest_audit_hash(connection: Any) -> str:
    """Liest den entry_hash des letzten Audit-Eintrags (für Hash-Chain)."""
    row = connection.execute(
        select(audit_logs.c.entry_hash)
        .order_by(audit_logs.c.id.desc())
        .limit(1)
    ).fetchone()
    if row is None or not row[0]:
        return "0" * 64  # Genesis-Hash
    return row[0]


def write_audit_entry(action: str, metadata: dict[str, Any] | None = None,
                      tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    ts = datetime.now(timezone.utc)
    entry: dict[str, Any] = {
        "timestamp": ts,
        "action": action,
        "metadata": metadata or {},
        "tenant_id": tenant_id,
    }

    with engine.begin() as connection:
        previous_hash = _get_latest_audit_hash(connection)
        entry["previous_hash"] = previous_hash
        # Temporärer Hash ohne ID — wird nach Insert mit echter ID berechnet
        result = connection.execute(
            insert(audit_logs).values(**entry, entry_hash="pending")
        )
        entry_id = result.inserted_primary_key[0]
        entry["id"] = entry_id
        # Hash mit echter ID berechnen und zurückschreiben
        ts_str = ts.isoformat()
        entry_hash = _compute_audit_hash(entry_id, ts_str, action, tenant_id, previous_hash)
        entry["entry_hash"] = entry_hash
        from sqlalchemy import update as _update
        connection.execute(
            _update(audit_logs)
            .where(audit_logs.c.id == entry_id)
            .values(entry_hash=entry_hash)
        )

    return entry


def list_audit_entries(limit: int = 100, tenant_id: str | None = None) -> list[dict[str, Any]]:
    query = select(audit_logs).order_by(audit_logs.c.timestamp.desc()).limit(limit)
    if tenant_id is not None:
        query = query.where(audit_logs.c.tenant_id == tenant_id)

    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()

    return [dict(row) for row in rows]


def query_audit_events(
    *,
    action: str | None = None,
    tenant_id: str | None = None,
    timestamp_from: datetime | None = None,
    timestamp_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Paginierte, gefilterte Audit-Abfrage für den Audit-Vault (read-only)."""
    limit = min(max(1, limit), 1000)
    offset = max(0, offset)

    query = select(audit_logs).order_by(audit_logs.c.timestamp.desc())

    if action:
        query = query.where(audit_logs.c.action == action)
    if tenant_id:
        query = query.where(audit_logs.c.tenant_id == tenant_id)
    if timestamp_from:
        query = query.where(audit_logs.c.timestamp >= timestamp_from)
    if timestamp_to:
        query = query.where(audit_logs.c.timestamp <= timestamp_to)

    query = query.offset(offset).limit(limit)

    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()

    return [dict(row) for row in rows]


def count_audit_events(
    *,
    action: str | None = None,
    tenant_id: str | None = None,
    timestamp_from: datetime | None = None,
    timestamp_to: datetime | None = None,
) -> int:
    """Zählt Audit-Einträge für Retention-Reports (kein DELETE)."""
    from sqlalchemy import func

    query = select(func.count()).select_from(audit_logs)

    if action:
        query = query.where(audit_logs.c.action == action)
    if tenant_id:
        query = query.where(audit_logs.c.tenant_id == tenant_id)
    if timestamp_from:
        query = query.where(audit_logs.c.timestamp >= timestamp_from)
    if timestamp_to:
        query = query.where(audit_logs.c.timestamp <= timestamp_to)

    with engine.begin() as connection:
        return connection.execute(query).scalar() or 0


def create_approval_request(
    tool: str,
    input_params: dict[str, Any],
    risk_level: str,
    risk_reason: str,
    run_id: str | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
    required_approver_roles: list[str] | None = None,
) -> dict[str, Any]:
    from .approval import APPROVAL_TIMEOUT_SECONDS, APPROVAL_ROLES  # type: ignore[attr-defined]
    now = datetime.now(timezone.utc)
    timeout_s = APPROVAL_TIMEOUT_SECONDS.get(risk_level, 1800)
    expires = (now + timedelta(seconds=timeout_s)) if timeout_s > 0 else None
    roles = required_approver_roles or APPROVAL_ROLES.get(risk_level, ["admin", "owner"])
    entry = {
        "created_at": now,
        "run_id": run_id,
        "tool": tool,
        "input_params": input_params,
        "risk_level": risk_level,
        "risk_reason": risk_reason,
        "required_approver_roles": roles,
        "status": "pending",
        "resolved_at": None,
        "note": None,
        "tenant_id": tenant_id,
        "expires_at": expires,
    }

    with engine.begin() as connection:
        result = connection.execute(insert(approval_requests).values(**entry))
        entry["id"] = result.inserted_primary_key[0]

    return entry


def create_agent_run(
    run_id: str,
    task: str,
    status: str = "running",
    run_metadata: dict[str, Any] | None = None,
    tenant_id: str = DEFAULT_TENANT_ID,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    entry = {
        "id": run_id,
        "created_at": now,
        "updated_at": now,
        "task": task,
        "status": status,
        "pending_approval_id": None,
        "result": None,
        "run_metadata": run_metadata or {},
        "tenant_id": tenant_id,
    }

    with engine.begin() as connection:
        connection.execute(insert(agent_runs).values(**entry))

    return entry


def get_agent_run(run_id: str) -> dict[str, Any] | None:
    query = select(agent_runs).where(agent_runs.c.id == run_id)

    with engine.begin() as connection:
        row = connection.execute(query).mappings().first()

    return dict(row) if row else None


def list_agent_runs(status: str | None = None, limit: int = 100,
                    tenant_id: str | None = None) -> list[dict[str, Any]]:
    query = select(agent_runs).order_by(agent_runs.c.updated_at.desc()).limit(limit)
    if status:
        query = query.where(agent_runs.c.status == status)
    if tenant_id is not None:
        query = query.where(agent_runs.c.tenant_id == tenant_id)

    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()

    return [dict(row) for row in rows]


def update_agent_run(
    run_id: str,
    *,
    status: str | None = None,
    pending_approval_id: int | None | object = _UNSET,
    result: dict[str, Any] | None | object = _UNSET,
    run_metadata: dict[str, Any] | None | object = _UNSET,
) -> dict[str, Any] | None:
    values: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if status is not None:
        values["status"] = status
    if pending_approval_id is not _UNSET:
        values["pending_approval_id"] = pending_approval_id
    if result is not _UNSET:
        values["result"] = result
    if run_metadata is not _UNSET:
        values["run_metadata"] = run_metadata or {}

    query = update(agent_runs).where(agent_runs.c.id == run_id).values(**values)
    with engine.begin() as connection:
        result_row = connection.execute(query)

    if result_row.rowcount == 0:
        return None

    return get_agent_run(run_id)


def link_approval_to_run(approval_id: int, run_id: str) -> dict[str, Any] | None:
    query = update(approval_requests).where(approval_requests.c.id == approval_id).values(run_id=run_id)
    with engine.begin() as connection:
        result = connection.execute(query)

    if result.rowcount == 0:
        return None

    return get_approval_request(approval_id)


def list_approval_requests(status: str | None = None) -> list[dict[str, Any]]:
    query = select(approval_requests).order_by(approval_requests.c.created_at.desc())
    if status:
        query = query.where(approval_requests.c.status == status)

    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()

    return [dict(row) for row in rows]


def get_approval_request(approval_id: int) -> dict[str, Any] | None:
    query = select(approval_requests).where(approval_requests.c.id == approval_id)

    with engine.begin() as connection:
        row = connection.execute(query).mappings().first()

    return dict(row) if row else None


def resolve_approval_request(approval_id: int, status: str, note: str = "") -> dict[str, Any] | None:
    resolved_at = datetime.now(timezone.utc)
    query = (
        update(approval_requests)
        .where(approval_requests.c.id == approval_id)
        .where(approval_requests.c.status == "pending")
        .values(status=status, resolved_at=resolved_at, note=note)
    )

    with engine.begin() as connection:
        result = connection.execute(query)

    if result.rowcount == 0:
        return get_approval_request(approval_id)

    return get_approval_request(approval_id)


# ── Reflection Facts ─────────────────────────────────────────────────────────
def insert_reflection_fact(values: dict[str, Any]) -> None:
    with engine.begin() as connection:
        connection.execute(insert(reflection_facts).values(**values))


def query_reflection_facts(tenant_id: str, purpose: str | None = None,
                           limit: int = 5) -> list[dict[str, Any]]:
    query = select(reflection_facts).where(reflection_facts.c.tenant_id == tenant_id)
    if purpose:
        query = query.where(reflection_facts.c.purpose == purpose)
    query = query.order_by(reflection_facts.c.quality_score.desc()).limit(limit)
    with engine.begin() as connection:
        return [dict(r) for r in connection.execute(query).mappings().all()]


def delete_reflection_fact(fact_id: str) -> int:
    with engine.begin() as connection:
        result = connection.execute(delete(reflection_facts).where(reflection_facts.c.id == fact_id))
    return result.rowcount


def delete_reflection_facts_for_tenant(tenant_id: str) -> int:
    with engine.begin() as connection:
        result = connection.execute(delete(reflection_facts).where(reflection_facts.c.tenant_id == tenant_id))
    return result.rowcount


def adjust_fact_quality_for_run(run_id: str, delta: float, tenant_id: str = DEFAULT_TENANT_ID) -> None:
    # MVP: passt quality_score aller Facts des Tenants mit passender source an.
    with engine.begin() as connection:
        connection.execute(
            update(reflection_facts)
            .where(reflection_facts.c.tenant_id == tenant_id)
            .where(reflection_facts.c.source == run_id)
            .values(quality_score=reflection_facts.c.quality_score + delta)
        )


# ── Feedback ─────────────────────────────────────────────────────────────────
def insert_feedback(tenant_id: str, run_id: str | None, rating: str,
                    reason: str | None, quality_score_delta: float) -> dict[str, Any]:
    entry = {
        "tenant_id": tenant_id, "run_id": run_id, "rating": rating,
        "reason": reason, "quality_score_delta": quality_score_delta,
        "created_at": datetime.now(timezone.utc),
    }
    with engine.begin() as connection:
        result = connection.execute(insert(feedback).values(**entry))
        entry["id"] = result.inserted_primary_key[0]
    return entry


def count_negative_feedback(tenant_id: str, run_id: str | None) -> int:
    query = select(feedback).where(feedback.c.tenant_id == tenant_id).where(
        feedback.c.rating == "not_helpful")
    if run_id is not None:
        query = query.where(feedback.c.run_id == run_id)
    with engine.begin() as connection:
        return len(connection.execute(query).all())


# ── Routing Proposals ────────────────────────────────────────────────────────
def insert_routing_proposal(tenant_id: str, trigger_type: str, description: str,
                            previous_route: str | None = None, proposed_route: str | None = None,
                            reason: str | None = None) -> dict[str, Any]:
    entry = {
        "tenant_id": tenant_id, "trigger_type": trigger_type, "description": description,
        "previous_route": previous_route, "proposed_route": proposed_route,
        "status": "pending", "changed_by": None, "reason": reason,
        "created_at": datetime.now(timezone.utc), "confirmed_at": None, "policy_version": None,
    }
    with engine.begin() as connection:
        result = connection.execute(insert(routing_proposals).values(**entry))
        entry["id"] = result.inserted_primary_key[0]
    return entry


def list_routing_proposals(tenant_id: str | None = None) -> list[dict[str, Any]]:
    query = select(routing_proposals).order_by(routing_proposals.c.created_at.desc())
    if tenant_id is not None:
        query = query.where(routing_proposals.c.tenant_id == tenant_id)
    with engine.begin() as connection:
        return [dict(r) for r in connection.execute(query).mappings().all()]


# ── Nutzer / Auth ─────────────────────────────────────────────────────────────
def create_user(user_id: str, tenant_id: str, role: str, hashed_password: str) -> dict[str, Any]:
    entry = {
        "user_id": user_id, "tenant_id": tenant_id, "role": role,
        "hashed_password": hashed_password,
        "created_at": datetime.now(timezone.utc), "active": 1,
    }
    with engine.begin() as connection:
        connection.execute(insert(users).values(**entry))
    return {k: v for k, v in entry.items() if k != "hashed_password"}


def get_user(user_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    query = select(users).where(users.c.user_id == user_id)
    if tenant_id is not None:
        query = query.where(users.c.tenant_id == tenant_id)
    with engine.begin() as connection:
        row = connection.execute(query).mappings().first()
    return dict(row) if row else None


_USER_SETTINGS_BOOL_FIELDS = (
    "aktives_merken", "sichtbare_zusammenfassungen_erlaubt", "erinnerungs_vorschlaege_erlaubt",
)


def _decode_user_settings_row(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    for field in _USER_SETTINGS_BOOL_FIELDS:
        row[field] = bool(row[field])
    return row


def get_user_settings(user_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any] | None:
    """Kein Auto-Anlegen: ohne expliziten upsert_user_settings()-Aufruf existiert
    kein Datensatz -- kein heimliches Anlegen von Einstellungen."""
    with engine.begin() as conn:
        row = conn.execute(
            select(user_settings)
            .where(user_settings.c.user_id == user_id)
            .where(user_settings.c.tenant_id == tenant_id)
        ).mappings().first()
    return _decode_user_settings_row(dict(row)) if row else None


def upsert_user_settings(user_id: str, tenant_id: str = DEFAULT_TENANT_ID, **fields: Any) -> dict[str, Any]:
    """Legt Settings mit Defaults an oder aktualisiert nur die uebergebenen Felder.
    Maximal ein Datensatz pro (user_id, tenant_id) -- durchgesetzt per Unique-Index."""
    now = datetime.now(timezone.utc)
    defaults = {
        "antwortlaenge": "normal", "ton": "freundlich", "sprache": None,
        "ausgabeformat": None, "ui_prefs": {}, "benachrichtigungen": {},
        "aktives_merken": 0, "sichtbare_zusammenfassungen_erlaubt": 0,
        "erinnerungs_vorschlaege_erlaubt": 1, "speichermodus": "immer_fragen",
    }
    with engine.begin() as conn:
        existing = conn.execute(
            select(user_settings.c.id, user_settings.c.created_at)
            .where(user_settings.c.user_id == user_id)
            .where(user_settings.c.tenant_id == tenant_id)
        ).first()
        if existing:
            update_values = {k: v for k, v in fields.items() if k in defaults}
            for b in _USER_SETTINGS_BOOL_FIELDS:
                if b in update_values:
                    update_values[b] = int(bool(update_values[b]))
            update_values["updated_at"] = now
            if update_values:
                conn.execute(
                    update(user_settings)
                    .where(user_settings.c.id == existing[0])
                    .values(**update_values)
                )
        else:
            values = {**defaults, **{k: v for k, v in fields.items() if k in defaults}}
            for b in _USER_SETTINGS_BOOL_FIELDS:
                values[b] = int(bool(values[b]))
            conn.execute(insert(user_settings).values(
                user_id=user_id, tenant_id=tenant_id, created_at=now, updated_at=now, **values,
            ))
    return get_user_settings(user_id, tenant_id)


def _max_attempts() -> int:
    return int(os.getenv("AILIZA_MAX_LOGIN_ATTEMPTS", "5"))

def _lockout_minutes() -> int:
    return int(os.getenv("AILIZA_LOCKOUT_MINUTES", "15"))


def authenticate_user(user_id: str, plain_password: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    """
    Prueft Credentials. Sperrt Account nach _MAX_FAILED_ATTEMPTS Fehlversuchen
    fuer _LOCKOUT_MINUTES Minuten. Gibt None zurueck bei Fehler (kein Hinweis auf Grund).
    """
    row = get_user(user_id, tenant_id)
    if not row or not row.get("active"):
        return None

    # Lockout pruefen
    locked_until = row.get("locked_until")
    if locked_until is not None:
        if isinstance(locked_until, str):
            locked_until = datetime.fromisoformat(locked_until)
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < locked_until:
            return None  # gesperrt — kein Unterschied zu falschen Credentials

    try:
        import bcrypt
        pw_ok = bcrypt.checkpw(plain_password.encode(), row["hashed_password"].encode())
    except ImportError:
        return None

    if not pw_ok:
        _record_failed_login(user_id, tenant_id or row["tenant_id"])
        return None

    # Erfolg: Zähler zurücksetzen
    _reset_failed_login(user_id, tenant_id or row["tenant_id"])
    return {k: v for k, v in row.items() if k not in ("hashed_password",)}


def _record_failed_login(user_id: str, tenant_id: str) -> None:
    from datetime import timedelta
    with engine.begin() as conn:
        row = conn.execute(
            select(users.c.failed_login_attempts)
            .where(users.c.user_id == user_id)
            .where(users.c.tenant_id == tenant_id)
        ).first()
        attempts = (row[0] if row else 0) + 1
        locked_until = None
        if attempts >= _max_attempts():
            locked_until = datetime.now(timezone.utc) + timedelta(minutes=_lockout_minutes())
        conn.execute(
            update(users)
            .where(users.c.user_id == user_id)
            .where(users.c.tenant_id == tenant_id)
            .values(failed_login_attempts=attempts, locked_until=locked_until)
        )


def _reset_failed_login(user_id: str, tenant_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(users)
            .where(users.c.user_id == user_id)
            .where(users.c.tenant_id == tenant_id)
            .values(failed_login_attempts=0, locked_until=None)
        )


# ── TOTP ──────────────────────────────────────────────────────────────────────
def upsert_totp_secret(user_id: str, tenant_id: str, secret_b32: str) -> None:
    """
    Speichert (oder ersetzt) ein TOTP-Secret; confirmed=0 bis Erstbestätigung.

    Beta-Betriebsauflage: Secret liegt im Klartext in der DB.
    Schutz erfolgt durch DB-/Volume-Verschlüsselung und minimale DB-Rechte.
    Production-Gate: AES-256-GCM oder KMS/Vault vor Produktiv-Einsatz erforderlich.
    Keine selbstgebaute Kryptografie (XOR o.ä.) als Ersatz zulässig.
    """
    with engine.begin() as conn:
        existing = conn.execute(
            select(totp_secrets).where(totp_secrets.c.user_id == user_id)
        ).first()
        if existing:
            conn.execute(
                update(totp_secrets)
                .where(totp_secrets.c.user_id == user_id)
                .values(secret_b32=secret_b32, confirmed=0, confirmed_at=None,
                        created_at=datetime.now(timezone.utc))
            )
        else:
            conn.execute(insert(totp_secrets).values(
                user_id=user_id, tenant_id=tenant_id, secret_b32=secret_b32,
                confirmed=0, created_at=datetime.now(timezone.utc), confirmed_at=None,
            ))


def confirm_totp_secret(user_id: str) -> bool:
    """Markiert TOTP-Secret als bestätigt. Gibt False zurück wenn kein Secret vorhanden."""
    with engine.begin() as conn:
        result = conn.execute(
            update(totp_secrets)
            .where(totp_secrets.c.user_id == user_id)
            .where(totp_secrets.c.confirmed == 0)
            .values(confirmed=1, confirmed_at=datetime.now(timezone.utc))
        )
    return result.rowcount > 0


def get_totp_record(user_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(totp_secrets).where(totp_secrets.c.user_id == user_id)
        ).mappings().first()
    return dict(row) if row else None


def delete_totp_secret(user_id: str) -> int:
    with engine.begin() as conn:
        r1 = conn.execute(delete(totp_secrets).where(totp_secrets.c.user_id == user_id))
        conn.execute(delete(totp_backup_codes).where(totp_backup_codes.c.user_id == user_id))
    return r1.rowcount


def store_backup_codes(user_id: str, tenant_id: str, code_hashes: list[str]) -> None:
    """Speichert gehashte Backup-Codes. Vorherige Codes werden gelöscht."""
    with engine.begin() as conn:
        conn.execute(delete(totp_backup_codes).where(totp_backup_codes.c.user_id == user_id))
        now = datetime.now(timezone.utc)
        for h in code_hashes:
            conn.execute(insert(totp_backup_codes).values(
                user_id=user_id, tenant_id=tenant_id, code_hash=h, used=0, created_at=now,
            ))


def consume_backup_code(user_id: str, plain_code: str) -> bool:
    """
    Prüft und verbraucht einen Backup-Code (HMAC+Pepper, constant-time).
    Einmalig — nach Verwendung wird used=1 gesetzt.
    """
    from .auth.totp import verify_backup_code
    with engine.begin() as conn:
        rows = conn.execute(
            select(totp_backup_codes)
            .where(totp_backup_codes.c.user_id == user_id)
            .where(totp_backup_codes.c.used == 0)
        ).mappings().all()
        for row in rows:
            if verify_backup_code(plain_code, row["code_hash"]):
                conn.execute(
                    update(totp_backup_codes)
                    .where(totp_backup_codes.c.id == row["id"])
                    .values(used=1, used_at=datetime.now(timezone.utc))
                )
                return True
    return False


try:
    init_db()
except Exception:
    logger.exception("Database initialization failed")
    raise


# ── Helper: Serverseitige Projekt-/Chat-Speicherung (Teilschritt 1) ──────────
# GRUNDREGEL: Jede Funktion filtert IMMER nach tenant_id UND user_id. Es gibt
# keinen Weg, ueber diese Helper an fremde Datensaetze zu gelangen.

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def save_user_project(project_id: str, tenant_id: str, user_id: str, *,
                      name: str, description: str | None = None,
                      priority: str | None = None, chat_id: str | None = None,
                      files: list | None = None,
                      expected_version: int | None = None) -> dict[str, Any]:
    """Upsert eines Projekts. Ueberschreibt NUR den eigenen Datensatz
    (gleiche id + tenant_id + user_id)."""
    now = _now_utc()
    with engine.begin() as conn:
        existing = conn.execute(
            select(user_projects.c.id, user_projects.c.created_at)
            .where(user_projects.c.id == project_id)
            .where(user_projects.c.tenant_id == tenant_id)
            .where(user_projects.c.user_id == user_id)
        ).first()
        values = dict(name=encrypt_field(name), description=encrypt_field(description),
                      priority=priority, chat_id=chat_id, files=files, updated_at=now,
                      tenant_id=tenant_id, user_id=user_id)
        if existing:
            current_version = conn.execute(
                select(user_projects.c.version)
                .where(user_projects.c.id == project_id)
                .where(user_projects.c.tenant_id == tenant_id)
                .where(user_projects.c.user_id == user_id)
            ).scalar() or 1
            if expected_version is not None and expected_version != current_version:
                return {"conflict": True, "current_version": current_version}
            new_version = current_version + 1
            conn.execute(
                update(user_projects)
                .where(user_projects.c.id == project_id)
                .where(user_projects.c.tenant_id == tenant_id)
                .where(user_projects.c.user_id == user_id)
                .values(version=new_version, **values)
            )
            created_at = existing[1]
        else:
            created_at = now
            new_version = 1
            conn.execute(insert(user_projects).values(
                id=project_id, created_at=created_at, retention_until=None,
                version=new_version, **values))
    return {"id": project_id, "created_at": created_at, "updated_at": now,
            "version": new_version}


def migrate_encrypt_existing_records() -> dict[str, int]:
    """Verschluesselt bestehende Klartext-Datensaetze nachtraeglich (Teilschritt
    2, Migration). Idempotent: encrypt_field/-json erkennen bereits
    verschluesselte Werte (enc:v1:-Praefix) und lassen sie unveraendert, daher
    kann diese Funktion gefahrlos mehrfach laufen (z. B. bei jedem Start).
    Kein Datensatz wird geloescht oder inhaltlich veraendert."""
    migrated = {"projects": 0, "chats": 0}
    with engine.begin() as conn:
        for row in conn.execute(select(user_projects)).mappings().all():
            new_name = encrypt_field(row["name"])
            new_desc = encrypt_field(row["description"])
            if new_name != row["name"] or new_desc != row["description"]:
                conn.execute(
                    update(user_projects)
                    .where(user_projects.c.id == row["id"])
                    .where(user_projects.c.tenant_id == row["tenant_id"])
                    .where(user_projects.c.user_id == row["user_id"])
                    .values(name=new_name, description=new_desc)
                )
                migrated["projects"] += 1
        for row in conn.execute(select(user_chats)).mappings().all():
            new_title = encrypt_field(row["title"])
            new_messages = encrypt_json(row["messages"])
            if new_title != row["title"] or new_messages != row["messages"]:
                conn.execute(
                    update(user_chats)
                    .where(user_chats.c.id == row["id"])
                    .where(user_chats.c.tenant_id == row["tenant_id"])
                    .where(user_chats.c.user_id == row["user_id"])
                    .values(title=new_title, messages=new_messages)
                )
                migrated["chats"] += 1
    return migrated


def _decrypt_project_row(row: dict[str, Any]) -> dict[str, Any]:
    row["name"] = decrypt_field(row.get("name"))
    row["description"] = decrypt_field(row.get("description"))
    return row


def list_user_projects(tenant_id: str, user_id: str) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            select(user_projects)
            .where(user_projects.c.tenant_id == tenant_id)
            .where(user_projects.c.user_id == user_id)
            .order_by(user_projects.c.updated_at.desc())
        ).mappings().all()
    return [_decrypt_project_row(dict(r)) for r in rows]


def delete_user_project(project_id: str, tenant_id: str, user_id: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            delete(user_projects)
            .where(user_projects.c.id == project_id)
            .where(user_projects.c.tenant_id == tenant_id)
            .where(user_projects.c.user_id == user_id)
        )
    return result.rowcount


def save_user_chat(chat_id: str, tenant_id: str, user_id: str, *,
                   messages: list, project_id: str | None = None,
                   title: str | None = None,
                   expected_version: int | None = None) -> dict[str, Any]:
    """Upsert eines Chats. Ueberschreibt NUR den eigenen Datensatz."""
    now = _now_utc()
    msgs = messages if isinstance(messages, list) else []
    with engine.begin() as conn:
        existing = conn.execute(
            select(user_chats.c.id, user_chats.c.created_at)
            .where(user_chats.c.id == chat_id)
            .where(user_chats.c.tenant_id == tenant_id)
            .where(user_chats.c.user_id == user_id)
        ).first()
        values = dict(project_id=project_id, title=encrypt_field(title),
                      messages=encrypt_json(msgs),
                      message_count=len(msgs), updated_at=now,
                      tenant_id=tenant_id, user_id=user_id)
        if existing:
            current_version = conn.execute(
                select(user_chats.c.version)
                .where(user_chats.c.id == chat_id)
                .where(user_chats.c.tenant_id == tenant_id)
                .where(user_chats.c.user_id == user_id)
            ).scalar() or 1
            if expected_version is not None and expected_version != current_version:
                return {"conflict": True, "current_version": current_version}
            new_version = current_version + 1
            conn.execute(
                update(user_chats)
                .where(user_chats.c.id == chat_id)
                .where(user_chats.c.tenant_id == tenant_id)
                .where(user_chats.c.user_id == user_id)
                .values(version=new_version, **values)
            )
            created_at = existing[1]
            was_created = False
        else:
            created_at = now
            new_version = 1
            conn.execute(insert(user_chats).values(
                id=chat_id, created_at=created_at, retention_until=None,
                version=new_version, **values))
            was_created = True
    return {"id": chat_id, "created_at": created_at, "updated_at": now,
            "message_count": len(msgs), "version": new_version,
            "created": was_created}


def _decrypt_chat_row(row: dict[str, Any]) -> dict[str, Any]:
    row["title"] = decrypt_field(row.get("title"))
    row["messages"] = decrypt_json(row.get("messages"))
    return row


def list_user_chats(tenant_id: str, user_id: str,
                    project_id: str | None = None) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        query = (
            select(user_chats)
            .where(user_chats.c.tenant_id == tenant_id)
            .where(user_chats.c.user_id == user_id)
        )
        if project_id is not None:
            query = query.where(user_chats.c.project_id == project_id)
        rows = conn.execute(query.order_by(user_chats.c.updated_at.desc())).mappings().all()
    return [_decrypt_chat_row(dict(r)) for r in rows]


def get_user_chat(chat_id: str, tenant_id: str, user_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(user_chats)
            .where(user_chats.c.id == chat_id)
            .where(user_chats.c.tenant_id == tenant_id)
            .where(user_chats.c.user_id == user_id)
        ).mappings().first()
    return _decrypt_chat_row(dict(row)) if row else None


def delete_user_chat(chat_id: str, tenant_id: str, user_id: str) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            delete(user_chats)
            .where(user_chats.c.id == chat_id)
            .where(user_chats.c.tenant_id == tenant_id)
            .where(user_chats.c.user_id == user_id)
        )
    return result.rowcount
