from __future__ import annotations

import hashlib
import logging
import os
import threading
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Index, Integer, JSON, MetaData, String, Table, Text,
    and_, create_engine, delete, event, exists, insert, literal, or_, select, text, update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

# Prozessweite Sperre fuer ALLE Schreib-/kritischen Lesevorgaenge, die
# nicht nebenlaeufig gegeneinander laufen duerfen. Grund: die aktuelle
# SQLite-:memory:-Anbindung teilt sich ueber StaticPool EINE rohe
# sqlite3-Verbindung zwischen allen Threads (noetig, damit alle Threads
# dieselben In-Memory-Daten sehen). Nebenlaeufige execute()-Aufrufe auf
# DERSELBEN rohen sqlite3-Verbindung aus mehreren Threads sind NICHT sicher
# serialisiert. Es darf daher NUR EINE einzige Sperre fuer alle
# betroffenen Operationen verwendet werden -- mehrere unabhaengige Sperren
# (z.B. je eine fuer Audit-Schreibzugriffe und eine fuer
# Genehmigungsentscheidungen) verhindern die Kollision zwischen sich
# selbst, aber NICHT gegeneinander, und die Verbindung kann trotzdem
# nebenlaeufig aus zwei Threads angesprochen werden. Siehe
# write_audit_entry() und decide_approval_atomic() weiter unten sowie
# DEPLOY_RENDER.md (Betriebsgrenze: nur ein Uvicorn-Prozess, keine
# --workers > 1, solange keine DB-seitige Sperre existiert).
_sql_write_lock = threading.RLock()

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

try:
    from .db_schema import (
        DEFAULT_TENANT_ID, metadata_obj,
        audit_logs, approval_requests, agent_runs, user_specialist_roles,
        case_assignments, security_logs, performance_logs, cost_logs,
        reflection_facts, feedback, routing_proposals, kill_switch_state,
        users, user_settings, memory_sources, memory_items, memory_visibility,
        memory_suggestions, messenger_bindings, totp_secrets, totp_backup_codes,
        skills, knowledge_sources, knowledge_chunks, knowledge_source_permissions,
        user_projects, user_chats, model_candidates, routing_decisions, customers,
    )
except ImportError:
    from db_schema import (  # type: ignore
        DEFAULT_TENANT_ID, metadata_obj,
        audit_logs, approval_requests, agent_runs, user_specialist_roles,
        case_assignments, security_logs, performance_logs, cost_logs,
        reflection_facts, feedback, routing_proposals, kill_switch_state,
        users, user_settings, memory_sources, memory_items, memory_visibility,
        memory_suggestions, messenger_bindings, totp_secrets, totp_backup_codes,
        skills, knowledge_sources, knowledge_chunks, knowledge_source_permissions,
        user_projects, user_chats, model_candidates, routing_decisions, customers,
    )

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

# SQLite-Performance/Nebenlaeufigkeit: WAL erlaubt gleichzeitige Leser waehrend
# ein Schreiber aktiv ist (statt des Standard-Rollback-Journals, das Leser
# blockiert). busy_timeout laesst SQLite bei einem kurzen Sperrkonflikt bis zu
# 5s auf Freigabe warten, statt sofort mit "database is locked" abzubrechen --
# relevant, weil sonst jeder Konflikt (auch ein kurzer WAL-Checkpoint) eine
# OperationalError auf Anwendungsebene ausloest. Rein additiv: keine
# Schema-/Datenaenderung, betrifft nur das Transaktionsverhalten der
# Verbindung. WAL ist fuer ":memory:"-Datenbanken wirkungslos (SQLite ignoriert
# es dort), busy_timeout bleibt in dem Fall trotzdem sinnvoll (mehrere Threads
# teilen sich ueber StaticPool dieselbe rohe Verbindung, siehe
# _sql_write_lock oben). Bestaetigt kompatibel mit der SQLite-Backup-API aus
# scripts/ailiza_backup.py (test_backup_captures_wal_committed_writes deckt
# WAL-Faelle bereits ab, siehe PR #82).
if DATABASE_URL.startswith("sqlite"):
    _IS_MEMORY_DB = DATABASE_URL in {"sqlite:///:memory:", "sqlite://"}

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas_on_connect(dbapi_connection, connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        try:
            if not _IS_MEMORY_DB:
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            # Fremdschluesselpruefung ist bei SQLite pro Verbindung deaktiviert,
            # sofern nicht explizit aktiviert -- ohne diese Zeile werden ON
            # DELETE CASCADE u.ae. Regeln aus dem Schema stillschweigend
            # ignoriert.
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

_UNSET = object()



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
        # PR 1 (Identitaets-/RBAC-Grundlage): owner_user_id additiv, NULL fuer
        # alle Bestandsdatensaetze -- kein Backfill, keine Vermutung.
        _add_column_if_missing(connection, "agent_runs", "owner_user_id", "VARCHAR(64)")
        _add_column_if_missing(connection, "approval_requests", "owner_user_id", "VARCHAR(64)")
        # Minimale Aufbewahrungs-Einstellung pro Chat (Karo-Entscheidung 2026-08-03)
        _add_column_if_missing(connection, "user_chats", "keep_uploaded_documents", "INTEGER")
        _add_column_if_missing(connection, "user_chats", "document_retention_days", "INTEGER")


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


def _canonicalize_audit_timestamp(ts: datetime) -> str:
    """Kanonische, zeitzonensichere Serialisierung eines Audit-Timestamps
    fuer die Hash-Chain -- einzige Quelle dieser Logik, von Schreib- UND
    Verifikationspfad gemeinsam genutzt (siehe _compute_audit_hash).

    Hintergrund (Bug, live reproduziert): audit_logs.timestamp wird beim
    Schreiben ausnahmslos ueber datetime.now(timezone.utc) gesetzt (belegte
    Bestandsinvariante, per Grep verifiziert -- keine andere Zeitquelle).
    SQLite liefert eine DateTime(timezone=True)-Spalte beim Zurueklesen
    jedoch als NAIVES datetime (tzinfo geht verloren). isoformat() auf dem
    zurueckgelesenen, naiven Objekt erzeugt dadurch einen anderen String
    als beim urspruenglichen Schreiben ("...441014" statt "...441014+00:00"),
    wodurch der neu berechnete Hash nie mit dem gespeicherten entry_hash
    uebereinstimmt -- verify_audit_chain() meldete dadurch bei JEDEM Aufruf
    faelschlich "Manipulation erkannt" (Falsch-Alarm), obwohl nichts
    veraendert wurde.

    Fix ausschliesslich auf der Leseseite: ein naives datetime wird als UTC
    interpretiert (angehaengtes tzinfo=UTC, kein Zeitwert veraendert) --
    das rekonstruiert exakt den beim Schreiben gehashten String, ohne
    bestehende entry_hash-Werte oder Datensaetze zu veraendern. Ein bereits
    aware datetime wird zusaetzlich nach UTC normalisiert (astimezone),
    damit ein kuenftiger, nicht-UTC-aware Zeitstempel keinen abweichenden
    String erzeugt.

    Fail-closed: kein stiller str()-Fallback fuer Nicht-datetime-Werte --
    ein ungueltiger Typ ist ein Programmfehler, kein Fall fuer eine
    geratene Zeichenkette in der Hash-Chain."""
    if not isinstance(ts, datetime):
        raise TypeError(
            f"Audit-Timestamp muss ein datetime-Objekt sein, nicht {type(ts).__name__!r}."
        )
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    return ts.isoformat()


def _compute_audit_hash(entry_id: int, timestamp: datetime, action: str,
                        tenant_id: str, previous_hash: str) -> str:
    """SHA-256 Hash-Chain für Audit-Vault Stufe 2. `timestamp` MUSS ein
    datetime-Objekt sein (nicht vorformatiert) -- die kanonische
    Serialisierung erfolgt intern via _canonicalize_audit_timestamp(),
    damit Schreib- und Verifikationspfad garantiert identisch hashen."""
    import hashlib
    ts_str = _canonicalize_audit_timestamp(timestamp)
    raw = f"{entry_id}|{ts_str}|{action}|{tenant_id}|{previous_hash}"
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


def _insert_audit_entry_on_connection(
    connection: Any, action: str, metadata: dict[str, Any] | None, tenant_id: str,
) -> dict[str, Any]:
    """Fuegt einen Audit-Eintrag inkl. Hash-Chain auf einer BEREITS
    GEOEFFNETEN Connection/Transaktion ein -- kein eigenes engine.begin().
    Wird sowohl von write_audit_entry() (eigene Transaktion) als auch von
    consume_compliance_consent() (gemeinsame Transaktion mit der
    Statusaenderung) verwendet, damit Verbrauch und Audit-Eintrag
    entweder GEMEINSAM committen oder GEMEINSAM zurueckgerollt werden."""
    ts = datetime.now(timezone.utc)
    entry: dict[str, Any] = {
        "timestamp": ts,
        "action": action,
        "metadata": metadata or {},
        "tenant_id": tenant_id,
    }
    previous_hash = _get_latest_audit_hash(connection)
    entry["previous_hash"] = previous_hash
    # Temporärer Hash ohne ID — wird nach Insert mit echter ID berechnet
    result = connection.execute(
        insert(audit_logs).values(**entry, entry_hash="pending")
    )
    entry_id = result.inserted_primary_key[0]
    entry["id"] = entry_id
    # Hash mit echter ID berechnen und zurückschreiben -- ts ist das
    # bereits aware datetime-Objekt aus dieser Funktion (Zeile oben, VOR
    # dem DB-Insert/Round-Trip), nicht das zurückgelesene.
    entry_hash = _compute_audit_hash(entry_id, ts, action, tenant_id, previous_hash)
    entry["entry_hash"] = entry_hash
    from sqlalchemy import update as _update
    connection.execute(
        _update(audit_logs)
        .where(audit_logs.c.id == entry_id)
        .values(entry_hash=entry_hash)
    )
    return entry


def write_audit_entry(action: str, metadata: dict[str, Any] | None = None,
                      tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    """Lesen des vorherigen Hash-Chain-Werts und Insert muessen als EINE
    Einheit ablaufen -- ohne Sperre koennen zwei gleichzeitige Aufrufe
    (z.B. zwei parallele Genehmigungsentscheidungen) denselben previous_hash
    lesen, wodurch ein Audit-Eintrag verloren gehen bzw. die Hash-Chain
    inkonsistent werden kann. Verwendet dieselbe _sql_write_lock wie
    decide_approval_atomic() (siehe deren Docstring) -- ZWEI unabhaengige
    Sperren wuerden sich zwar jeweils selbst korrekt serialisieren, aber
    NICHT gegenseitig, und die geteilte SQLite-Verbindung koennte trotzdem
    von zwei Threads gleichzeitig angesprochen werden."""
    with _sql_write_lock, engine.begin() as connection:
        return _insert_audit_entry_on_connection(connection, action, metadata, tenant_id)


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
    owner_user_id: str | None = None,
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
        # PR 2: Owner wird ausschliesslich serverseitig gesetzt (aus dem
        # geprueften Session-Kontext bzw. dem zugrundeliegenden Agent-Run),
        # niemals aus einem Client-Wert uebernommen.
        "owner_user_id": owner_user_id,
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
    owner_user_id: str | None = None,
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
        # PR 2: NULL fuer anonyme Runs (kein Login) und fuer historische
        # Datensaetze vor diesem PR. Ausschliesslich aus dem geprueften
        # Session-Kontext gesetzt, nie aus dem Client uebernommen.
        "owner_user_id": owner_user_id,
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


def update_agent_run_for_tenant(
    run_id: str,
    tenant_id: str,
    *,
    status: str | None = None,
    pending_approval_id: int | None | object = _UNSET,
    result: dict[str, Any] | None | object = _UNSET,
    run_metadata: dict[str, Any] | None | object = _UNSET,
) -> dict[str, Any] | None:
    """Tenant-gebundene Variante von update_agent_run() -- fuer Aenderungen,
    die aus einer Genehmigungsentscheidung folgen (z.B. Ablehnung). Der
    verknuepfte Run wird NUR veraendert, wenn run_id UND tenant_id
    uebereinstimmen; eine fehlerhafte oder tenant-fremde Verknuepfung darf
    niemals einen Run in einem fremden Tenant veraendern."""
    values: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if status is not None:
        values["status"] = status
    if pending_approval_id is not _UNSET:
        values["pending_approval_id"] = pending_approval_id
    if result is not _UNSET:
        values["result"] = result
    if run_metadata is not _UNSET:
        values["run_metadata"] = run_metadata or {}

    query = (
        update(agent_runs)
        .where(agent_runs.c.id == run_id)
        .where(agent_runs.c.tenant_id == tenant_id)
        .values(**values)
    )
    with engine.begin() as connection:
        result_row = connection.execute(query)

    if result_row.rowcount == 0:
        write_audit_entry(
            action="agent_run.update_blocked_tenant_mismatch",
            tenant_id=tenant_id,
            metadata={"run_id": run_id},
        )
        return None

    with engine.begin() as connection:
        row = connection.execute(
            select(agent_runs).where(agent_runs.c.id == run_id).where(agent_runs.c.tenant_id == tenant_id)
        ).mappings().first()
    return dict(row) if row else None


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


# ── PR 1 (Identitaets-/RBAC-Grundlage): Fachzustaendigkeiten ────────────────
# Reine Datenschicht. Keine Permission-Evaluator-Logik, keine Endpunkte --
# folgt in spaeteren, separaten PRs.

class SpecialistRoleValidationError(ValueError):
    """Eine Fachrollen-Zuweisung verletzt eine Pflichtregel oder ist bereits aktiv vergeben."""


_VALID_SPECIALIST_ROLES = {
    "DATENSCHUTZBEAUFTRAGTER",
    "INFORMATIONSSICHERHEITSBEAUFTRAGTER",
    "RECHTSVERANTWORTLICHER",
    "BETRIEBSVERANTWORTLICHER",
    "KI_GOVERNANCE_VERANTWORTLICHER",
}


def _is_unique_violation(exc: IntegrityError, table: str, columns: tuple[str, ...]) -> bool:
    """Grenzt den erwarteten Unique-Konflikt des aktiven Zuweisungs-Index von
    anderen Integritaetsfehlern ab, die nicht verschluckt werden duerfen.
    SQLite meldet bei UNIQUE-Verletzungen die beteiligten Spalten, nicht den
    Indexnamen (z. B. "UNIQUE constraint failed: t.a, t.b, t.c")."""
    message = str(exc.orig)
    if "UNIQUE constraint failed" not in message:
        return False
    return all(f"{table}.{col}" in message for col in columns)


def create_specialist_role_assignment(
    *, user_id: str, tenant_id: str, specialist_role: str,
    assigned_by_user_id: str, assignment_reason: str,
    valid_until: datetime | None = None, review_required_at: datetime | None = None,
) -> dict[str, Any]:
    if not user_id or not tenant_id:
        raise SpecialistRoleValidationError("user_id und tenant_id sind Pflicht.")
    if specialist_role not in _VALID_SPECIALIST_ROLES:
        raise SpecialistRoleValidationError(
            f"Ungueltige Fachrolle: {specialist_role!r}. Erlaubt: {_VALID_SPECIALIST_ROLES}"
        )
    if not assigned_by_user_id:
        raise SpecialistRoleValidationError("assigned_by_user_id ist Pflicht.")
    if not assignment_reason or not assignment_reason.strip():
        raise SpecialistRoleValidationError("assignment_reason ist Pflicht.")

    if get_user(user_id, tenant_id=tenant_id) is None:
        raise SpecialistRoleValidationError(
            "Zielnutzer gehoert nicht zum angegebenen Tenant."
        )
    if get_user(assigned_by_user_id, tenant_id=tenant_id) is None:
        raise SpecialistRoleValidationError(
            "Zuweisende Person gehoert nicht zum angegebenen Tenant."
        )

    now = datetime.now(timezone.utc)
    entry = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "specialist_role": specialist_role,
        "assigned_by_user_id": assigned_by_user_id,
        "assignment_reason": assignment_reason,
        "created_at": now,
        "valid_from": now,
        "valid_until": valid_until,
        "review_required_at": review_required_at,
        "revoked_at": None,
        "revoked_by_user_id": None,
        "is_active": 1,
    }
    try:
        with engine.begin() as connection:
            result = connection.execute(insert(user_specialist_roles).values(**entry))
            entry["id"] = result.inserted_primary_key[0]
    except IntegrityError as exc:
        if not _is_unique_violation(
            exc, "user_specialist_roles", ("user_id", "tenant_id", "specialist_role")
        ):
            raise
        raise SpecialistRoleValidationError(
            f"{user_id} besitzt die Fachrolle {specialist_role} in diesem Tenant bereits aktiv."
        ) from exc

    return entry


def revoke_specialist_role_assignment(
    assignment_id: int, tenant_id: str, revoked_by_user_id: str,
) -> dict[str, Any] | None:
    if not tenant_id:
        raise SpecialistRoleValidationError("tenant_id ist Pflicht.")
    if not revoked_by_user_id:
        raise SpecialistRoleValidationError("revoked_by_user_id ist Pflicht.")
    now = datetime.now(timezone.utc)
    query = (
        update(user_specialist_roles)
        .where(user_specialist_roles.c.id == assignment_id)
        .where(user_specialist_roles.c.tenant_id == tenant_id)
        .where(user_specialist_roles.c.revoked_at.is_(None))
        .values(revoked_at=now, revoked_by_user_id=revoked_by_user_id, is_active=0)
    )
    with engine.begin() as connection:
        connection.execute(query)
        row = connection.execute(
            select(user_specialist_roles)
            .where(user_specialist_roles.c.id == assignment_id)
            .where(user_specialist_roles.c.tenant_id == tenant_id)
        ).mappings().first()
    return dict(row) if row else None


def list_active_specialist_roles(user_id: str, tenant_id: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    query = (
        select(user_specialist_roles)
        .where(user_specialist_roles.c.user_id == user_id)
        .where(user_specialist_roles.c.tenant_id == tenant_id)
        .where(user_specialist_roles.c.is_active == 1)
        .where(user_specialist_roles.c.revoked_at.is_(None))
    )
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [
        dict(row) for row in rows
        if row["valid_until"] is None or _as_aware_utc(row["valid_until"]) > now
    ]


def _as_aware_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ── PR 1 (Identitaets-/RBAC-Grundlage): Gezielte Vorgangszuteilung ──────────
class CaseAssignmentValidationError(ValueError):
    """Eine Vorgangszuteilung verletzt eine Pflichtregel oder ist bereits aktiv vergeben."""


_VALID_CASE_TYPES = {"AGENT_RUN", "APPROVAL"}


def _case_exists_in_tenant(case_type: str, case_id: str, tenant_id: str) -> bool:
    with engine.begin() as connection:
        if case_type == "AGENT_RUN":
            row = connection.execute(
                select(agent_runs.c.id)
                .where(agent_runs.c.id == case_id)
                .where(agent_runs.c.tenant_id == tenant_id)
            ).first()
        else:  # APPROVAL
            try:
                approval_id = int(case_id)
            except (TypeError, ValueError):
                return False
            row = connection.execute(
                select(approval_requests.c.id)
                .where(approval_requests.c.id == approval_id)
                .where(approval_requests.c.tenant_id == tenant_id)
            ).first()
    return row is not None


def create_case_assignment(
    *, case_type: str, case_id: str, tenant_id: str,
    assigned_to_user_id: str, assigned_by_user_id: str, assignment_reason: str,
    valid_until: datetime | None = None,
) -> dict[str, Any]:
    if case_type not in _VALID_CASE_TYPES:
        raise CaseAssignmentValidationError(
            f"Ungueltiger case_type: {case_type!r}. Erlaubt: {_VALID_CASE_TYPES}"
        )
    if not case_id or not tenant_id:
        raise CaseAssignmentValidationError("case_id und tenant_id sind Pflicht.")
    if not assigned_to_user_id or not assigned_by_user_id:
        raise CaseAssignmentValidationError("assigned_to_user_id und assigned_by_user_id sind Pflicht.")
    if not assignment_reason or not assignment_reason.strip():
        raise CaseAssignmentValidationError("assignment_reason ist Pflicht.")

    assigner = get_user(assigned_by_user_id, tenant_id=tenant_id)
    if assigner is None:
        raise CaseAssignmentValidationError(
            "Zuweisende Person gehoert nicht zum angegebenen Tenant."
        )
    assignee = get_user(assigned_to_user_id, tenant_id=tenant_id)
    if assignee is None:
        raise CaseAssignmentValidationError(
            "Zugewiesene Person gehoert nicht zum angegebenen Tenant."
        )
    if not _case_exists_in_tenant(case_type, case_id, tenant_id):
        raise CaseAssignmentValidationError(
            f"{case_type} {case_id} existiert nicht oder gehoert nicht zum angegebenen Tenant."
        )

    now = datetime.now(timezone.utc)
    entry = {
        "case_type": case_type,
        "case_id": case_id,
        "tenant_id": tenant_id,
        "assigned_to_user_id": assigned_to_user_id,
        "assigned_by_user_id": assigned_by_user_id,
        "assignment_reason": assignment_reason,
        "assigned_at": now,
        "valid_until": valid_until,
        "revoked_at": None,
        "revoked_by_user_id": None,
    }
    try:
        with engine.begin() as connection:
            result = connection.execute(insert(case_assignments).values(**entry))
            entry["id"] = result.inserted_primary_key[0]
    except IntegrityError as exc:
        if not _is_unique_violation(
            exc, "case_assignments", ("tenant_id", "case_type", "case_id", "assigned_to_user_id")
        ):
            raise
        raise CaseAssignmentValidationError(
            f"{assigned_to_user_id} ist fuer {case_type} {case_id} bereits aktiv zugewiesen."
        ) from exc

    return entry


def revoke_case_assignment(
    assignment_id: int, tenant_id: str, revoked_by_user_id: str,
) -> dict[str, Any] | None:
    if not tenant_id:
        raise CaseAssignmentValidationError("tenant_id ist Pflicht.")
    if not revoked_by_user_id:
        raise CaseAssignmentValidationError("revoked_by_user_id ist Pflicht.")
    now = datetime.now(timezone.utc)
    query = (
        update(case_assignments)
        .where(case_assignments.c.id == assignment_id)
        .where(case_assignments.c.tenant_id == tenant_id)
        .where(case_assignments.c.revoked_at.is_(None))
        .values(revoked_at=now, revoked_by_user_id=revoked_by_user_id)
    )
    with engine.begin() as connection:
        connection.execute(query)
        row = connection.execute(
            select(case_assignments)
            .where(case_assignments.c.id == assignment_id)
            .where(case_assignments.c.tenant_id == tenant_id)
        ).mappings().first()
    return dict(row) if row else None


def list_active_case_assignments(assigned_to_user_id: str, tenant_id: str) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    query = (
        select(case_assignments)
        .where(case_assignments.c.assigned_to_user_id == assigned_to_user_id)
        .where(case_assignments.c.tenant_id == tenant_id)
        .where(case_assignments.c.revoked_at.is_(None))
    )
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [
        dict(row) for row in rows
        if row["valid_until"] is None or _as_aware_utc(row["valid_until"]) > now
    ]


def has_active_case_assignment(case_type: str, case_id: str, tenant_id: str, user_id: str) -> bool:
    """PR 2: gezielte Pruefung fuer den Permission-Evaluator -- besteht fuer
    GENAU diesen Vorgang eine gueltige (nicht widerrufene, nicht abgelaufene)
    Zuweisung an user_id?"""
    query = (
        select(case_assignments.c.valid_until)
        .where(case_assignments.c.case_type == case_type)
        .where(case_assignments.c.case_id == case_id)
        .where(case_assignments.c.tenant_id == tenant_id)
        .where(case_assignments.c.assigned_to_user_id == user_id)
        .where(case_assignments.c.revoked_at.is_(None))
    )
    with engine.begin() as connection:
        rows = connection.execute(query).all()
    now = datetime.now(timezone.utc)
    return any(r[0] is None or _as_aware_utc(r[0]) > now for r in rows)


def list_own_or_assigned_agent_runs(
    *, tenant_id: str, user_id: str, status: str | None = None, limit: int = 100,
) -> list[dict[str, Any]]:
    """PR 2: ersetzt die zuvor ungefilterte list_agent_runs() fuer den
    Self-Service-Endpunkt -- nur eigene ODER ausdruecklich zugewiesene Runs,
    niemals tenant-weit ungefiltert."""
    query = (
        select(agent_runs)
        .where(agent_runs.c.tenant_id == tenant_id)
        .where(or_(
            agent_runs.c.owner_user_id == user_id,
            _active_assignment_exists_clause("AGENT_RUN", agent_runs.c.id, tenant_id, user_id),
        ))
        .order_by(agent_runs.c.updated_at.desc())
        .limit(limit)
    )
    if status:
        query = query.where(agent_runs.c.status == status)
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(row) for row in rows]


def list_own_or_assigned_approvals(
    *, tenant_id: str, user_id: str, status: str | None = None,
) -> list[dict[str, Any]]:
    """PR 2: ersetzt die zuvor ungefilterte list_approval_requests() fuer den
    Self-Service-Endpunkt -- nur eigene ODER ausdruecklich zugewiesene
    Genehmigungsanfragen."""
    from sqlalchemy import cast
    query = (
        select(approval_requests)
        .where(approval_requests.c.tenant_id == tenant_id)
        .where(or_(
            approval_requests.c.owner_user_id == user_id,
            _active_assignment_exists_clause(
                "APPROVAL", cast(approval_requests.c.id, String), tenant_id, user_id,
            ),
        ))
        .order_by(approval_requests.c.created_at.desc())
    )
    if status:
        query = query.where(approval_requests.c.status == status)
    with engine.begin() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(row) for row in rows]


def _active_assignment_exists_clause(case_type: str, case_id_expr, tenant_id: str, user_id: str):
    """Korrelierte EXISTS-Bedingung fuer eine aktive (nicht widerrufene, nicht
    abgelaufene) Vorgangszuteilung -- wird DIREKT in die jeweilige
    Ressourcenabfrage bzw. das UPDATE eingebettet, statt Zuweisungs-IDs in
    einer separaten Abfrage vorzuladen. Damit gibt es keinen Zeitraum
    zwischen zwei getrennten Abfragen, in dem ein zwischenzeitlicher
    Widerruf wirkungslos bliebe."""
    now = datetime.now(timezone.utc)
    return exists(
        select(case_assignments.c.id)
        .where(case_assignments.c.case_type == case_type)
        .where(case_assignments.c.case_id == case_id_expr)
        .where(case_assignments.c.tenant_id == tenant_id)
        .where(case_assignments.c.assigned_to_user_id == user_id)
        .where(case_assignments.c.revoked_at.is_(None))
        .where(or_(case_assignments.c.valid_until.is_(None), case_assignments.c.valid_until > now))
    )


def get_accessible_agent_run(run_id: str, tenant_id: str, user_id: str) -> dict[str, Any] | None:
    """PR 2 Nachbesserung: Tenant-/Owner-/Zuweisungsfilter als EINE
    korrelierte Abfrage (EXISTS) -- kein Vorladen von Zuweisungs-IDs in
    einem separaten Schritt, kein Zeitfenster fuer einen wirkungslosen
    zwischenzeitlichen Widerruf."""
    query = (
        select(agent_runs)
        .where(agent_runs.c.id == run_id)
        .where(agent_runs.c.tenant_id == tenant_id)
        .where(or_(
            agent_runs.c.owner_user_id == user_id,
            _active_assignment_exists_clause("AGENT_RUN", agent_runs.c.id, tenant_id, user_id),
        ))
    )
    with engine.begin() as connection:
        row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def get_approval_request_for_tenant(approval_id: int, tenant_id: str) -> dict[str, Any] | None:
    """Tenant-gebundener Lookup -- ein Datensatz eines fremden Tenants wird
    von der Abfrage selbst ausgeschlossen, nicht erst nach dem Laden verworfen."""
    query = (
        select(approval_requests)
        .where(approval_requests.c.id == approval_id)
        .where(approval_requests.c.tenant_id == tenant_id)
    )
    with engine.begin() as connection:
        row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def get_accessible_approval(approval_id: int, tenant_id: str, user_id: str) -> dict[str, Any] | None:
    from sqlalchemy import cast
    query = (
        select(approval_requests)
        .where(approval_requests.c.id == approval_id)
        .where(approval_requests.c.tenant_id == tenant_id)
        .where(or_(
            approval_requests.c.owner_user_id == user_id,
            _active_assignment_exists_clause(
                "APPROVAL", cast(approval_requests.c.id, String), tenant_id, user_id,
            ),
        ))
    )
    with engine.begin() as connection:
        row = connection.execute(query).mappings().first()
    return dict(row) if row else None


def consume_compliance_consent(
    *, approval_id: int, task: str, user_id: str, tenant_id: str,
    audit_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Nutzer- und tenantgebundene, EINMALIGE Verwendung einer erteilten
    compliance_consent (B2 Drei-Stufen-Modell). Ersetzt den fruehren
    main._valid_compliance_consent(), der weder Owner noch Tenant pruefte
    und beliebig oft wiederverwendbar war.

    Autorisierung, Statusaenderung (approved -> consumed) UND der
    zugehoerige Audit-Eintrag (compliance.consent_used) sind EINE
    gemeinsame Transaktion -- kein globaler get_approval_request(
    approval_id)-Lookup, kein separates Lesen vor dem Schreiben, und der
    Audit-Eintrag kann niemals fehlen, ohne dass auch der Verbrauch
    zurueckgerollt wird (und umgekehrt). Die WHERE-Klausel des UPDATE
    prueft in genau diesem Statement:
      - approval_id UND tenant_id (Tenant-Bindung),
      - owner_user_id == user_id (nur die einwilligende Person selbst),
      - tool == 'compliance_consent',
      - status == 'approved' (noch nicht verbraucht/abgelehnt/pending),
      - task_sha256 (im JSON-Feld input_params) entspricht EXAKT der
        aktuellen Anfrage (task_sha256-Bindung, siehe main._consent_task_hash),
      - EXISTS ein aktueller, aktiver, nicht gesperrter users-Datensatz
        (user_id + tenant_id, active=1, locked_until IS NULL ODER
        locked_until <= jetzt) -- das gueltige JWT allein reicht fuer diese
        sicherheitskritische Aktion NICHT aus; ein zwischenzeitlich
        gesperrter/deaktivierter Nutzer kann seine eigene, bereits
        genehmigte Einwilligung nicht mehr verwenden. Fehlt der
        users-Datensatz komplett, gilt ebenfalls Default Deny.

    resolved_at wird NICHT ueberschrieben -- es bleibt der Zeitpunkt der
    urspruenglichen Genehmigung (approved). Der Verbrauchszeitpunkt ergibt
    sich aus dem Zeitstempel des compliance.consent_used-Audit-Eintrags.

    Nur rowcount == 1 gilt als erfolgreiche, einmalige Nutzung -- eine
    zweite Verwendung derselben Einwilligung (status ist dann bereits
    'consumed') schlaegt fehl, ebenso ein fremder Nutzer/Tenant, ein
    abweichender Text oder ein gesperrter/fehlender Nutzer. Gibt den
    aktualisierten Datensatz zurueck oder None bei Ablehnung."""
    import hashlib
    task_sha256 = hashlib.sha256(task.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)

    active_user_exists = exists(
        select(users.c.user_id)
        .where(users.c.user_id == user_id)
        .where(users.c.tenant_id == tenant_id)
        .where(users.c.active == 1)
        .where(or_(users.c.locked_until.is_(None), users.c.locked_until <= now))
    )

    query = (
        update(approval_requests)
        .where(approval_requests.c.id == approval_id)
        .where(approval_requests.c.tenant_id == tenant_id)
        .where(approval_requests.c.owner_user_id == user_id)
        .where(approval_requests.c.tool == "compliance_consent")
        .where(approval_requests.c.status == "approved")
        .where(approval_requests.c.input_params["task_sha256"].as_string() == task_sha256)
        .where(active_user_exists)
        .values(status="consumed")
    )

    with _sql_write_lock, engine.begin() as connection:
        result = connection.execute(query)
        if result.rowcount != 1:
            # Explizit KEIN Audit-Eintrag bei Ablehnung -- die Transaktion
            # wird beim Verlassen des `with engine.begin()`-Blocks ohne
            # Aenderungen committet (nichts wurde geschrieben).
            return None

        # Audit-Eintrag in DERSELBEN Transaktion wie der Verbrauch -- schlaegt
        # der Insert fehl, wirft SQLAlchemy und die gesamte Transaktion
        # (inkl. des bereits ausgefuehrten UPDATE) wird zurueckgerollt, der
        # Status bleibt 'approved'. Minimale Metadaten, keine Rohtexte.
        base_metadata = {
            "approval_id": approval_id,
            "user_id": user_id,
            "tenant_id": tenant_id,
        }
        if audit_metadata:
            base_metadata.update({
                k: v for k, v in audit_metadata.items() if k in ("audit_id",)
            })
        _insert_audit_entry_on_connection(
            connection, "compliance.consent_used", base_metadata, tenant_id,
        )

        row = connection.execute(
            select(approval_requests)
            .where(approval_requests.c.id == approval_id)
            .where(approval_requests.c.tenant_id == tenant_id)
        ).mappings().first()
        return dict(row) if row else None


# Oeffentlicher Alias auf DIESELBE Sperre wie write_audit_entry (siehe
# _sql_write_lock oben im Modul) -- der Aufrufer (permissions.py) haelt
# diese Sperre ueber den GESAMTEN Entscheidungsvorgang, nicht nur das
# abschliessende UPDATE. Bewusst dieselbe Sperreninstanz wie fuer Audit-
# Schreibzugriffe, damit sich eine Genehmigungsentscheidung und ein
# Audit-Schreibzugriff niemals gegenseitig auf der geteilten SQLite-
# Verbindung ueberlappen koennen -- siehe Docstring unten.
decide_approval_lock = _sql_write_lock


def decide_approval_atomic(
    *, approval_id: int, tenant_id: str, actor_user_id: str, new_status: str, note: str,
    allow_consent_owner: bool, literal_roles: set[str], specialist_domains: set[str],
) -> tuple[str, dict[str, Any] | None]:
    """Autorisierung (aktiver, nicht gesperrter Nutzer + Zuweisung + passende
    Rolle/Fachzustaendigkeit + Vier-Augen-Prinzip) UND Statusaenderung als
    EINE atomare SQL-Operation. Die WHERE-Klausel des UPDATE prueft
    Nutzerstatus, Zuweisung, Fachrolle/Rolle, Vier-Augen-Prinzip, Tenant,
    Status und Ablauf alle im selben Statement -- ein Widerruf der Zuweisung,
    eine Sperrung des Nutzers oder der Entzug der Fachrolle genau zwischen
    einer vorgelagerten Pruefung und dem UPDATE kann die Entscheidung damit
    nicht mehr durchrutschen lassen, weil es keine vorgelagerte Pruefung
    mehr gibt: die Bedingung IST das UPDATE.

    KEIN Token-Rollen-Fallback: fehlt ein aktueller users-Datensatz fuer
    actor_user_id/tenant_id, gilt Default Deny -- fuer BEIDE Pfade (siehe
    active_user_exists unten). Die compliance_consent-Ausnahme prueft
    zusaetzlich Owner-Identitaet und Task-Bindung, ist aber vom aktiven,
    nicht gesperrten users-Datensatz NICHT befreit: ein zwischenzeitlich
    deaktivierter/gesperrter Nutzer kann auch seine eigene Einwilligung
    nicht mehr wirksam nutzen. (Diese eigentliche Verwendung der
    compliance_consent zum Versand der zugehoerigen Anfrage laeuft separat
    ueber database.consume_compliance_consent() -- der Consent-Zweig hier
    in decide_approval_atomic betrifft nur das FREIGEBEN/ABLEHNEN der
    Einwilligungs-Anfrage selbst, siehe routers/approvals.py.)

    Rueckgabe (outcome, entry):
      OK               -- Entscheidung gespeichert (rowcount == 1).
      NOT_ZUSTAENDIG   -- Person ist nicht zustaendig (Default-Antwort fuer
                           nicht existent/fremder Tenant/keine Zuweisung o.
                           passende Rolle -- absichtlich nicht unterscheidbar).
      ALREADY_DECIDED  -- zustaendig, aber Status bereits != pending.
      EXPIRED          -- zustaendig, aber abgelaufen.
      CONFLICT         -- zustaendig und (noch) gueltig, aber eine parallele
                           Anfrage war zwischen Pruefung und UPDATE schneller.

    Prozess-Sperre (decide_approval_lock): die aktuelle SQLite-Anbindung fuer
    :memory:-Datenbanken teilt sich ueber StaticPool EINE rohe sqlite3-
    Verbindung zwischen allen Threads (das ist bei In-Memory-SQLite noetig,
    damit alle Threads dieselben Daten sehen). Nebenlaeufige execute()-
    Aufrufe auf DERSELBEN rohen sqlite3-Verbindung aus mehreren Threads sind
    NICHT sicher serialisiert -- das betrifft nicht nur dieses UPDATE,
    sondern JEDE Abfrage waehrend des Entscheidungsvorgangs (auch die
    vorgelagerten Lesezugriffe in permissions.decide_approval()). Der
    Aufrufer haelt decide_approval_lock daher ueber den GESAMTEN
    Entscheidungsvorgang, nicht nur ueber diese Funktion. Fuer eine
    produktive Mehrprozess-/Mehrverbindungs-Datenbank (z.B. Postgres) waere
    stattdessen eine DB-seitige Sperre (SELECT ... FOR UPDATE oder ein
    Advisory Lock) der naechste Schritt -- das bleibt aus SQLite-Sicht
    bewusst ausserhalb dieses PRs.
    """
    now = datetime.now(timezone.utc)
    case_id_str = str(approval_id)

    # Aktueller Nutzerstatus MUSS Teil derselben atomaren Pruefung sein:
    # aktiv und nicht gesperrt, zum Zeitpunkt des UPDATE. Kein Fallback auf
    # die Rolle aus dem Token -- fehlt der Datensatz, ist der Zuweisungs-/
    # Rollen-Pfad grundsaetzlich versperrt (Default Deny).
    active_user_exists = exists(
        select(users.c.user_id)
        .where(users.c.user_id == actor_user_id)
        .where(users.c.tenant_id == tenant_id)
        .where(users.c.active == 1)
        .where(or_(users.c.locked_until.is_(None), users.c.locked_until <= now))
    )

    assignment_exists = _active_assignment_exists_clause(
        "APPROVAL", literal(case_id_str), tenant_id, actor_user_id,
    )

    specialist_exists = (
        exists(
            select(user_specialist_roles.c.id)
            .where(user_specialist_roles.c.user_id == actor_user_id)
            .where(user_specialist_roles.c.tenant_id == tenant_id)
            .where(user_specialist_roles.c.is_active == 1)
            .where(user_specialist_roles.c.revoked_at.is_(None))
            .where(user_specialist_roles.c.valid_from <= now)
            .where(or_(
                user_specialist_roles.c.valid_until.is_(None),
                user_specialist_roles.c.valid_until > now,
            ))
            .where(user_specialist_roles.c.specialist_role.in_(specialist_domains))
        ) if specialist_domains else literal(False)
    )

    literal_role_exists = (
        exists(
            select(users.c.user_id)
            .where(users.c.user_id == actor_user_id)
            .where(users.c.tenant_id == tenant_id)
            .where(users.c.role.in_(literal_roles))
        ) if literal_roles else literal(False)
    )

    role_match = or_(specialist_exists, literal_role_exists)

    # Vier-Augen-Prinzip: eine aktive Zuweisung PLUS passende Rolle darf
    # NIEMALS die eigene Anfrage freigeben -- nur die separat streng
    # geprüfte compliance_consent-Ausnahme darf die eigene Anfrage betreffen.
    not_self_owned = or_(
        approval_requests.c.owner_user_id.is_(None),
        approval_requests.c.owner_user_id != actor_user_id,
    )

    zustaendig = or_(
        and_(active_user_exists, assignment_exists, role_match, not_self_owned),
        and_(literal(bool(allow_consent_owner)), active_user_exists, approval_requests.c.owner_user_id == actor_user_id),
    )

    update_query = (
        update(approval_requests)
        .where(approval_requests.c.id == approval_id)
        .where(approval_requests.c.tenant_id == tenant_id)
        .where(approval_requests.c.status == "pending")
        .where(or_(approval_requests.c.expires_at.is_(None), approval_requests.c.expires_at > now))
        .where(zustaendig)
        .values(status=new_status, resolved_at=now, note=note)
    )

    with decide_approval_lock, engine.begin() as connection:
        result = connection.execute(update_query)
        rowcount = result.rowcount
        entry_row = connection.execute(
            select(approval_requests)
            .where(approval_requests.c.id == approval_id)
            .where(approval_requests.c.tenant_id == tenant_id)
        ).mappings().first()
        entry = dict(entry_row) if entry_row else None

        if rowcount == 1:
            return "OK", entry

        if entry is None:
            return "NOT_ZUSTAENDIG", None

        # Differenzierung NUR fuer die Fehlermeldung, in derselben
        # Transaktion/Verbindung wie das gescheiterte UPDATE -- kein neues
        # Zeitfenster, da hier keine weitere Zustandsaenderung stattfindet.
        zustaendig_row = connection.execute(
            select(literal(True))
            .select_from(approval_requests)
            .where(approval_requests.c.id == approval_id)
            .where(approval_requests.c.tenant_id == tenant_id)
            .where(zustaendig)
        ).first()
        if not zustaendig_row:
            return "NOT_ZUSTAENDIG", None
        if entry["status"] != "pending":
            return "ALREADY_DECIDED", entry
        expires_at = entry.get("expires_at")
        if expires_at is not None and _as_aware_utc(expires_at) < now:
            return "EXPIRED", entry
        return "CONFLICT", entry


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


# ── Mini-PR 2: Memory-Kernschema Helper ──────────────────────────────────────
# Nur Datenstruktur + minimale Validierung. Keine automatische Erkennung,
# keine memory_suggestions-Logik (Mini-PR 3), keine UI, kein pgvector.

class MemoryValidationError(ValueError):
    """Ein Memory-Eintrag verletzt eine Pflichtregel (Scope/Quelle/Zweck/Besitzer)."""


_VALID_MEMORY_SCOPES = {"company_memory", "user_memory"}
_VALID_MEMORY_STATUS = {"suggested", "confirmed", "active", "outdated", "deleted"}
_ACTIVE_STATUS_VALUES = ("active",)


def create_memory_source(tenant_id: str, source_type: str, *,
                         reference: str | None = None, source_title: str | None = None,
                         source_date: datetime | None = None,
                         confirmed_by: str | None = None, approved_by: str | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        result = conn.execute(insert(memory_sources).values(
            tenant_id=tenant_id, source_type=source_type, reference=reference,
            source_title=source_title, source_date=source_date,
            confirmed_by=confirmed_by, approved_by=approved_by,
            created_at=now, updated_at=now,
        ))
        source_id = result.inserted_primary_key[0]
    return {"id": source_id, "tenant_id": tenant_id, "source_type": source_type}


def _require_tenant(tenant_id: str | None, *, funktion: str) -> str:
    """Fail-closed Tenant-Pflichtpruefung (Knowledge Phase 1 -- Memory
    Tenant Integrity). None, "" und reine Whitespace-Werte gelten als
    fehlend. Kein automatischer Default-Tenant, kein Erraten -- der
    Aufrufer muss einen echten, serverseitig ermittelten Tenant liefern."""
    if tenant_id is None or not tenant_id.strip():
        raise MemoryValidationError(
            f"{funktion}: tenant_id fehlt oder ist leer -- Vorgang abgelehnt "
            "(kein automatischer Default-Tenant)."
        )
    return tenant_id


def _validate_memory_item(scope: str, tenant_id: str | None, owner_user_id: str | None,
                          status: str, source_id: int | None, purpose: str | None) -> None:
    if scope not in _VALID_MEMORY_SCOPES:
        raise MemoryValidationError(f"Ungueltiger scope: {scope!r}. Erlaubt: {_VALID_MEMORY_SCOPES}")
    if status not in _VALID_MEMORY_STATUS:
        raise MemoryValidationError(f"Ungueltiger status: {status!r}. Erlaubt: {_VALID_MEMORY_STATUS}")
    if scope == "user_memory" and not owner_user_id:
        raise MemoryValidationError("user_memory braucht owner_user_id.")
    if scope == "company_memory" and not tenant_id:
        raise MemoryValidationError("company_memory braucht tenant_id (Organisationsbezug).")
    if scope == "company_memory" and owner_user_id:
        raise MemoryValidationError(
            "company_memory darf keinen owner_user_id haben (gehoert der Organisation, "
            "nicht einer einzelnen Person)."
        )
    if status in _ACTIVE_STATUS_VALUES:
        if not source_id:
            raise MemoryValidationError("Aktiver Memory-Eintrag braucht source_id.")
        if not purpose:
            raise MemoryValidationError("Aktiver Memory-Eintrag braucht purpose.")


def _default_visibility_for_scope(scope: str, tenant_id: str | None) -> dict[str, Any]:
    if scope == "user_memory":
        return {"visibility_scope": "private", "allowed_org_id": None}
    return {"visibility_scope": "organization", "allowed_org_id": tenant_id}


def create_memory_item(tenant_id: str | None, scope: str, title: str, content: str, *,
                       purpose: str | None = None, source_id: int | None = None,
                       owner_user_id: str | None = None, category: str | None = None,
                       status: str = "suggested", expires_at: datetime | None = None,
                       created_by: str | None = None, approved_by: str | None = None) -> dict[str, Any]:
    """Legt einen Memory-Eintrag an. Kein automatischer Aufrufpfad -- diese
    Funktion wird nur explizit aufgerufen (siehe test_no_automatic_chat_to_memory_path_exists).
    Pflichtregeln (Scope/Zweck/Quelle/Besitzer/Tenant) werden hier
    durchgesetzt, nicht erst in einer spaeteren Schicht (fail-closed).

    Knowledge Phase 1 (Memory Tenant Integrity): tenant_id ist fuer JEDEN
    Scope Pflicht (auch user_memory) -- kein neuer Eintrag darf je ohne
    Tenant entstehen, siehe _require_tenant()."""
    tenant_id = _require_tenant(tenant_id, funktion="create_memory_item")
    _validate_memory_item(scope, tenant_id, owner_user_id, status, source_id, purpose)
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        result = conn.execute(insert(memory_items).values(
            tenant_id=tenant_id, scope=scope, owner_user_id=owner_user_id,
            title=title, content=content, category=category, purpose=purpose,
            source_id=source_id, status=status, expires_at=expires_at,
            created_by=created_by, approved_by=approved_by,
            created_at=now, updated_at=now,
        ))
        item_id = result.inserted_primary_key[0]
        if status in _ACTIVE_STATUS_VALUES:
            vis = _default_visibility_for_scope(scope, tenant_id)
            conn.execute(insert(memory_visibility).values(
                memory_item_id=item_id, visibility_scope=vis["visibility_scope"],
                allowed_roles=[], allowed_user_ids=[], allowed_org_id=vis["allowed_org_id"],
                project_id=None, created_at=now, updated_at=now,
            ))
        # Bewusst NICHT ueber get_memory_item(): dort ist tenant_id ab
        # Phase 1 Pflicht und dient als Zugriffskontrolle -- die Rueckgabe
        # der gerade selbst angelegten Zeile braucht das nicht, sondern
        # liest direkt in derselben Transaktion zurueck.
        row = conn.execute(select(memory_items).where(memory_items.c.id == item_id)).mappings().first()
    return dict(row)


def get_memory_item(item_id: int, *, tenant_id: str) -> dict[str, Any] | None:
    """Liest einen Memory-Eintrag NUR, wenn er zum angegebenen Tenant
    gehoert (Knowledge Phase 1). tenant_id ist Pflicht-Keyword -- ein
    Aufruf ohne serverseitig ermittelten Tenant ist nicht mehr moeglich.
    Fremder Tenant erhaelt None, exakt wie "existiert nicht" (kein
    Unterschied in der Antwort, der die Existenz eines fremden Eintrags
    verraten wuerde)."""
    tenant_id = _require_tenant(tenant_id, funktion="get_memory_item")
    with engine.begin() as conn:
        row = conn.execute(
            select(memory_items)
            .where(memory_items.c.id == item_id)
            .where(memory_items.c.tenant_id == tenant_id)
        ).mappings().first()
    return dict(row) if row else None


def list_active_memory_items_for_user(user_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> list[dict[str, Any]]:
    """Nur eigene, aktive, nicht abgelaufene user_memory-Eintraege -- keine
    fremden Eintraege und kein company_memory (M1: expliziter scope-Filter,
    vorher implizit ueber owner_user_id).

    Knowledge Phase 1: die fruehere Uebergangsregel (Legacy-user_memory mit
    tenant_id=NULL zusaetzlich sichtbar machen) entfaellt. memory_items.tenant_id
    ist jetzt NOT NULL (siehe Migration) -- jede Zeile hat einen Tenant.
    Verbleibende Alt-Datenbanken ohne Migration werden ueber den fail-closed
    Migrations-Guard blockiert, nicht stillschweigend hier kompensiert."""
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        rows = conn.execute(
            select(memory_items)
            .where(memory_items.c.scope == "user_memory")
            .where(memory_items.c.owner_user_id == user_id)
            .where(memory_items.c.tenant_id == tenant_id)
            .where(memory_items.c.status == "active")
        ).mappings().all()
    return [dict(r) for r in rows if r["expires_at"] is None or _as_aware(r["expires_at"]) > now]


def list_active_memory_items_for_org(tenant_id: str) -> list[dict[str, Any]]:
    """Nur company_memory desselben Mandanten, aktiv, nicht abgelaufen."""
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        rows = conn.execute(
            select(memory_items)
            .where(memory_items.c.tenant_id == tenant_id)
            .where(memory_items.c.scope == "company_memory")
            .where(memory_items.c.status == "active")
        ).mappings().all()
    return [dict(r) for r in rows if r["expires_at"] is None or _as_aware(r["expires_at"]) > now]


def _as_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ── M1: Read-only Bestandspruefung der Scope-/Owner-/Tenant-Invarianten ────
# Verbindliche Zielregeln (siehe _validate_memory_item):
#   user_memory:    scope=="user_memory", owner_user_id PFLICHT
#   company_memory: scope=="company_memory", tenant_id PFLICHT, owner_user_id MUSS NULL sein
#
# Diese Funktion VERAENDERT NIEMALS Daten (rein lesend) -- sie liefert nur
# einen Bericht. Seit Knowledge Phase 1 (Migration c8ff9bb332ba) ist
# memory_items.tenant_id NOT NULL -- eine solche Zeile kann in einer
# migrierten Datenbank technisch nicht mehr existieren. legacy_user_memory_null_tenant
# bleibt als Diagnosefeld fuer NICHT migrierte Alt-Datenbanken (z.B. vor
# der NOT-NULL-Migration) bestehen und wird dort weiterhin als Info statt
# harter Verletzung gemeldet -- kein automatischer Abbruch, das entscheidet
# der Aufrufer. Aufrufer
# (z.B. ein Migrations-/Deploy-Skript) entscheiden selbst, ob bei
# gefundenen echten Verletzungen abgebrochen wird -- diese Funktion selbst
# wirft nichts, sie berichtet nur (fail-safe: lieber ein zu ausfuehrlicher
# Bericht als eine stille Fehlklassifikation).
def _collect_memory_scope_invariants(conn) -> dict[str, Any]:
    """Liest die Rohdaten fuer den Invarianten-Bericht ueber EINE gegebene
    Connection -- ausschliesslich SELECTs, kein Transaktions-/
    Verbindungsmanagement hier (das entscheidet der Aufrufer, siehe
    audit_memory_scope_invariants())."""
    from sqlalchemy import func

    total = conn.execute(select(func.count()).select_from(memory_items)).scalar_one()

    user_memory_missing_owner = conn.execute(
        select(memory_items.c.id)
        .where(memory_items.c.scope == "user_memory")
        .where(memory_items.c.owner_user_id.is_(None))
    ).scalars().all()

    company_memory_missing_tenant = conn.execute(
        select(memory_items.c.id)
        .where(memory_items.c.scope == "company_memory")
        .where(memory_items.c.tenant_id.is_(None))
    ).scalars().all()

    company_memory_with_owner = conn.execute(
        select(memory_items.c.id)
        .where(memory_items.c.scope == "company_memory")
        .where(memory_items.c.owner_user_id.isnot(None))
    ).scalars().all()

    unknown_scope = conn.execute(
        select(memory_items.c.id, memory_items.c.scope)
        .where(memory_items.c.scope.notin_(list(_VALID_MEMORY_SCOPES)))
    ).all()

    legacy_user_memory_null_tenant = conn.execute(
        select(memory_items.c.id)
        .where(memory_items.c.scope == "user_memory")
        .where(memory_items.c.tenant_id.is_(None))
        .where(memory_items.c.owner_user_id.isnot(None))
    ).scalars().all()

    active_without_visibility = conn.execute(
        select(memory_items.c.id)
        .select_from(memory_items.outerjoin(
            memory_visibility, memory_visibility.c.memory_item_id == memory_items.c.id,
        ))
        .where(memory_items.c.status == "active")
        .where(memory_visibility.c.id.is_(None))
    ).scalars().all()

    return dict(
        total=total,
        user_memory_missing_owner=user_memory_missing_owner,
        company_memory_missing_tenant=company_memory_missing_tenant,
        company_memory_with_owner=company_memory_with_owner,
        unknown_scope=unknown_scope,
        legacy_user_memory_null_tenant=legacy_user_memory_null_tenant,
        active_without_visibility=active_without_visibility,
    )


def audit_memory_scope_invariants(conn=None) -> dict[str, Any]:
    """Liefert einen Bestandsbericht ueber memory_items, der alle
    Verletzungen der Scope-/Owner-/Tenant-Invarianten auflistet, OHNE
    irgendetwas zu veraendern. Gedacht als Trockenlauf/Repair-Report vor
    einer kuenftigen Migration.

    `conn`: optionale, bereits geoeffnete Connection (z.B. eine dedizierte
    Read-only-Verbindung des CLI-Audits, siehe
    audit_memory_scope_cli.py). Ohne Angabe wird wie bisher die
    anwendungsweite `engine` verwendet -- bestehende Aufrufer (Tests,
    interne Nutzung) sind unveraendert."""
    if conn is not None:
        raw = _collect_memory_scope_invariants(conn)
    else:
        with engine.begin() as conn:
            raw = _collect_memory_scope_invariants(conn)

    total = raw["total"]
    user_memory_missing_owner = raw["user_memory_missing_owner"]
    company_memory_missing_tenant = raw["company_memory_missing_tenant"]
    company_memory_with_owner = raw["company_memory_with_owner"]
    unknown_scope = raw["unknown_scope"]
    legacy_user_memory_null_tenant = raw["legacy_user_memory_null_tenant"]
    active_without_visibility = raw["active_without_visibility"]

    violations = {
        "user_memory_missing_owner": list(user_memory_missing_owner),
        "company_memory_missing_tenant": list(company_memory_missing_tenant),
        "company_memory_with_owner": list(company_memory_with_owner),
        "unknown_scope": [{"id": r[0], "scope": r[1]} for r in unknown_scope],
    }
    info_only = {
        # Kein Fehler -- Diagnosefeld fuer nicht migrierte Alt-DBs, siehe Docstring oben.
        "legacy_user_memory_null_tenant": list(legacy_user_memory_null_tenant),
        # Kein harter Fehler dieser Pruefung, aber relevant fuer M2/M3
        # (Default-Deny beim Lesen einer sichtbarkeits-losen aktiven Zeile).
        "active_without_visibility": list(active_without_visibility),
    }
    has_violations = any(v for v in violations.values())
    return {
        "total_memory_items": total,
        "has_violations": has_violations,
        "violations": violations,
        "info_only": info_only,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def count_unassigned_memory_items(conn=None) -> int:
    """Rein lesende Diagnose (Knowledge Phase 1): Anzahl memory_items ohne
    eindeutigen Tenant (NULL oder reiner Whitespace). Gedacht als
    Vorab-Pruefung vor der NOT-NULL-Migration bzw. als wiederverwendbarer
    Nachweis, dass Altbestand weder automatisch zugeordnet noch geloescht
    wurde -- veraendert nichts."""
    from sqlalchemy import func

    query = select(func.count()).select_from(memory_items).where(
        or_(memory_items.c.tenant_id.is_(None), func.trim(memory_items.c.tenant_id) == "")
    )
    if conn is not None:
        return conn.execute(query).scalar_one()
    with engine.begin() as conn:
        return conn.execute(query).scalar_one()


def set_memory_visibility(memory_item_id: int, *, tenant_id: str, visibility_scope: str,
                          owner_user_id: str | None = None,
                          allowed_roles: list | None = None, allowed_user_ids: list | None = None,
                          allowed_org_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
    """Knowledge Phase 1: memory_visibility hat selbst keine tenant_id-Spalte
    (bewusst -- eine zweite, potenziell abweichende Tenant-Quelle waere ein
    Risiko). Die Tenant-Zugehoerigkeit wird deshalb ZUERST ueber das
    verknuepfte memory_item verifiziert (get_memory_item() ist bereits
    tenant-gefiltert) -- erst danach wird memory_visibility geaendert.
    owner_user_id (falls angegeben): zusaetzliche Eigentuemer-Bindung fuer
    persoenliche Eintraege -- ein anderer Nutzer desselben Tenants darf die
    Sichtbarkeit eines fremden user_memory-Eintrags nicht aendern."""
    tenant_id = _require_tenant(tenant_id, funktion="set_memory_visibility")
    item = get_memory_item(memory_item_id, tenant_id=tenant_id)
    if item is None:
        raise MemoryValidationError("Memory-Eintrag nicht gefunden.")
    if item["scope"] == "user_memory" and owner_user_id is not None and item["owner_user_id"] != owner_user_id:
        raise MemoryValidationError("Memory-Eintrag gehoert einer anderen Person.")

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        existing = conn.execute(
            select(memory_visibility.c.id)
            .where(memory_visibility.c.memory_item_id == memory_item_id)
        ).first()
        values = dict(
            visibility_scope=visibility_scope, allowed_roles=allowed_roles or [],
            allowed_user_ids=allowed_user_ids or [], allowed_org_id=allowed_org_id,
            project_id=project_id, updated_at=now,
        )
        if existing:
            conn.execute(
                update(memory_visibility).where(memory_visibility.c.id == existing[0]).values(**values)
            )
        else:
            conn.execute(insert(memory_visibility).values(
                memory_item_id=memory_item_id, created_at=now, **values,
            ))
        row = conn.execute(
            select(memory_visibility).where(memory_visibility.c.memory_item_id == memory_item_id)
        ).mappings().first()
    return dict(row)


def mark_memory_item_deleted(item_id: int, *, tenant_id: str, owner_user_id: str | None = None) -> None:
    """Soft-Delete: status='deleted'. Geloeschte Eintraege werden von den
    list_active_*-Funktionen nie zurueckgegeben (Status-Filter auf 'active').

    Knowledge Phase 1: tenant_id ist Pflicht -- ein fremder Tenant kann ein
    Item weder hart noch weich loeschen. owner_user_id (falls angegeben):
    zusaetzliche Eigentuemer-Bindung fuer persoenliche Eintraege innerhalb
    desselben Tenants."""
    tenant_id = _require_tenant(tenant_id, funktion="mark_memory_item_deleted")
    item = get_memory_item(item_id, tenant_id=tenant_id)
    if item is None:
        raise MemoryValidationError("Memory-Eintrag nicht gefunden.")
    if item["scope"] == "user_memory" and owner_user_id is not None and item["owner_user_id"] != owner_user_id:
        raise MemoryValidationError("Memory-Eintrag gehoert einer anderen Person.")

    with engine.begin() as conn:
        conn.execute(
            update(memory_items)
            .where(memory_items.c.id == item_id)
            .where(memory_items.c.tenant_id == tenant_id)
            .values(status="deleted", updated_at=datetime.now(timezone.utc))
        )


# -- Block C Phase C1: Wissensdatenbank -- nur Schema-Fundament ------------
# Keine Extraktion, keine Suche, keine Embeddings (siehe
# AILIZA_BLOCK_C_PHASE_C1_DOCUMENT_SCHEMA.md). Diese Funktionen legen nur
# Quellen/Chunks/Berechtigungen an und lesen sie zurueck.
class KnowledgeValidationError(ValueError):
    """Eine Wissensquelle/-Chunk/-Berechtigung verletzt eine Pflichtregel."""


_VALID_SOURCE_TYPES = {"pdf", "docx", "xlsx", "txt", "md", "csv", "image", "manual", "url_reference"}
_VALID_SOURCE_STATUS = {"uploaded", "pending_review", "approved", "blocked", "deleted", "expired"}
_INACTIVE_SOURCE_STATUS = {"blocked", "deleted", "expired"}
_VALID_CHUNK_STATUS = {"active", "deleted", "blocked"}
_VALID_VISIBILITY_SCOPES = {"private", "project", "team", "organization", "external_limited"}


def create_knowledge_source(*, tenant_id: str | None, uploaded_by: str | None,
                            source_type: str, title: str,
                            original_filename: str | None = None,
                            storage_path: str | None = None,
                            content_hash: str | None = None,
                            mime_type: str | None = None,
                            status: str = "uploaded",
                            visibility_scope: str = "private",
                            approved_by: str | None = None,
                            approved_at: datetime | None = None,
                            expires_at: datetime | None = None) -> dict[str, Any]:
    if not tenant_id:
        raise KnowledgeValidationError("knowledge_source braucht tenant_id.")
    if not uploaded_by:
        raise KnowledgeValidationError("knowledge_source braucht uploaded_by.")
    if source_type not in _VALID_SOURCE_TYPES:
        raise KnowledgeValidationError(f"Ungueltiger source_type: {source_type!r}. Erlaubt: {_VALID_SOURCE_TYPES}")
    if status not in _VALID_SOURCE_STATUS:
        raise KnowledgeValidationError(f"Ungueltiger status: {status!r}. Erlaubt: {_VALID_SOURCE_STATUS}")
    if visibility_scope not in _VALID_VISIBILITY_SCOPES:
        raise KnowledgeValidationError(
            f"Ungueltiger visibility_scope: {visibility_scope!r}. Erlaubt: {_VALID_VISIBILITY_SCOPES}")

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        result = conn.execute(insert(knowledge_sources).values(
            tenant_id=tenant_id, uploaded_by=uploaded_by, source_type=source_type,
            title=title, original_filename=original_filename, storage_path=storage_path,
            content_hash=content_hash, mime_type=mime_type, status=status,
            visibility_scope=visibility_scope, approved_by=approved_by,
            approved_at=approved_at, expires_at=expires_at,
            created_at=now, updated_at=now,
        ))
        source_id = result.inserted_primary_key[0]
    return get_knowledge_source(source_id)


def get_knowledge_source(source_id: int) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(knowledge_sources).where(knowledge_sources.c.id == source_id)
        ).mappings().first()
    return dict(row) if row else None


def get_knowledge_source_by_hash(*, tenant_id: str, content_hash: str) -> dict[str, Any] | None:
    """Sucht eine nicht geloeschte/abgelaufene Quelle mit identischem
    content_hash im selben Tenant -- Grundlage fuer den Duplikat-Check beim
    Upload (Karo-Entscheidung 2026-08-03: bestehende Quelle wiederverwenden,
    kein Fehler, kein zweiter Eintrag). "blocked" wird bewusst NICHT
    ausgeschlossen, damit ein frueher geblockter Upload erkennbar bleibt,
    statt endlos erneut hochgeladen und neu geprueft zu werden."""
    if not tenant_id or not content_hash:
        return None
    with engine.begin() as conn:
        row = conn.execute(
            select(knowledge_sources)
            .where(knowledge_sources.c.tenant_id == tenant_id)
            .where(knowledge_sources.c.content_hash == content_hash)
            .where(knowledge_sources.c.status.notin_({"deleted", "expired"}))
            .order_by(knowledge_sources.c.created_at.desc())
        ).mappings().first()
    return dict(row) if row else None


def _knowledge_source_status(conn: Any, source_id: int) -> str | None:
    row = conn.execute(
        select(knowledge_sources.c.status).where(knowledge_sources.c.id == source_id)
    ).first()
    return row[0] if row else None


def create_knowledge_chunk(*, source_id: int, tenant_id: str | None, chunk_index: int,
                           chunk_text: str, chunk_hash: str | None = None,
                           page_number: int | None = None,
                           section_title: str | None = None,
                           token_estimate: int | None = None,
                           status: str = "active") -> dict[str, Any]:
    if status not in _VALID_CHUNK_STATUS:
        raise KnowledgeValidationError(f"Ungueltiger Chunk-Status: {status!r}. Erlaubt: {_VALID_CHUNK_STATUS}")

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        if _knowledge_source_status(conn, source_id) is None:
            raise KnowledgeValidationError(f"knowledge_chunk braucht existierende source_id (id={source_id}).")
        result = conn.execute(insert(knowledge_chunks).values(
            source_id=source_id, tenant_id=tenant_id, chunk_index=chunk_index,
            chunk_text=chunk_text, chunk_hash=chunk_hash, page_number=page_number,
            section_title=section_title, token_estimate=token_estimate, status=status,
            created_at=now, updated_at=now,
        ))
        chunk_id = result.inserted_primary_key[0]
        row = conn.execute(
            select(knowledge_chunks).where(knowledge_chunks.c.id == chunk_id)
        ).mappings().first()
    return dict(row)


def list_active_chunks_for_source(source_id: int) -> list[dict[str, Any]]:
    """Nur aktive Chunks einer nicht geloeschten/blockierten/abgelaufenen Source."""
    with engine.begin() as conn:
        source_status = _knowledge_source_status(conn, source_id)
        if source_status is None or source_status in _INACTIVE_SOURCE_STATUS:
            return []
        rows = conn.execute(
            select(knowledge_chunks)
            .where(knowledge_chunks.c.source_id == source_id)
            .where(knowledge_chunks.c.status == "active")
            .order_by(knowledge_chunks.c.chunk_index)
        ).mappings().all()
    return [dict(r) for r in rows]


def set_knowledge_source_permission(*, source_id: int, tenant_id: str | None,
                                    visibility_scope: str,
                                    allowed_roles: list | None = None,
                                    allowed_user_ids: list | None = None,
                                    project_id: str | None = None,
                                    created_by: str | None = None) -> dict[str, Any]:
    if visibility_scope not in _VALID_VISIBILITY_SCOPES:
        raise KnowledgeValidationError(
            f"Ungueltiger visibility_scope: {visibility_scope!r}. Erlaubt: {_VALID_VISIBILITY_SCOPES}")

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        if _knowledge_source_status(conn, source_id) is None:
            raise KnowledgeValidationError(f"knowledge_source_permission braucht existierende source_id (id={source_id}).")
        existing = conn.execute(
            select(knowledge_source_permissions.c.id)
            .where(knowledge_source_permissions.c.source_id == source_id)
        ).first()
        values = dict(
            tenant_id=tenant_id, visibility_scope=visibility_scope,
            allowed_roles=allowed_roles or [], allowed_user_ids=allowed_user_ids or [],
            project_id=project_id, created_by=created_by, updated_at=now,
        )
        if existing:
            conn.execute(
                update(knowledge_source_permissions)
                .where(knowledge_source_permissions.c.id == existing[0])
                .values(**values)
            )
            perm_id = existing[0]
        else:
            result = conn.execute(insert(knowledge_source_permissions).values(
                source_id=source_id, created_at=now, **values,
            ))
            perm_id = result.inserted_primary_key[0]
        row = conn.execute(
            select(knowledge_source_permissions).where(knowledge_source_permissions.c.id == perm_id)
        ).mappings().first()
    return dict(row)


def get_knowledge_source_permission(source_id: int) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(knowledge_source_permissions)
            .where(knowledge_source_permissions.c.source_id == source_id)
        ).mappings().first()
    return dict(row) if row else None


def mark_knowledge_source_deleted(source_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(knowledge_sources).where(knowledge_sources.c.id == source_id)
            .values(status="deleted", updated_at=datetime.now(timezone.utc))
        )


def mark_knowledge_source_blocked(source_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(knowledge_sources).where(knowledge_sources.c.id == source_id)
            .values(status="blocked", updated_at=datetime.now(timezone.utc))
        )


# ── Mini-PR 3: Speicher-Entscheidungslogik + memory_suggestions Helper ───────
# Vorschlaege statt heimliches Lernen. decide_memory_storage() entscheidet
# deterministisch (kein LLM), was mit einer erkannten Information passiert.
# Keine freie LLM-Extraktion -- der Aufrufer klassifiziert (info_kind), die
# Entscheidung hier folgt festen Regeln.

_VALID_SUGGESTION_STATUS = {"open", "confirmed", "rejected", "expired", "needs_admin_approval", "blocked"}
_VALID_RISK_LEVELS = {"low", "medium", "high", "blocked"}

# Wiederverwendung der bestehenden Secret-Muster-Idee (main.py contains_secret):
# hier bewusst eigene, kleine Kopie auf DB-Ebene, damit database.py nicht
# main.py importieren muss (Zirkularimport). Gleiche Muster-Familie.
import re as _re

_SUGGESTION_SECRET_PATTERNS = [
    _re.compile(r"\bsk-[\w\-]{10,}\b"),
    _re.compile(r"\bgsk_[\w\-]{10,}\b"),
    _re.compile(r"\beyJ[\w\-\.]+\b"),
    _re.compile(r"(?i)\b(passwort|password|api.?key|token|private.?key|recovery.?code|zugangscode)\b[ \t]*:?[ \t]*\S+"),
]


def _contains_secret_content(content: str | None) -> bool:
    if not content:
        return False
    return any(p.search(content) for p in _SUGGESTION_SECRET_PATTERNS)


def decide_memory_storage(*, user_id: str, tenant_id: str,
                          info_kind: str, reusable: bool, has_source: bool,
                          content: str | None = None,
                          project_id: str | None = None,
                          user_initiated: bool = False,
                          org_related: bool = False) -> str:
    """Deterministische Speicherentscheidung (siehe AILIZA_MINI_PR3_DECISION_LOGIC).

    info_kind: "sensitive" | "technical" | "setting" | "user_knowledge"
    Ergebnis: technically_store | store_as_setting |
              create_user_memory_suggestion | create_company_memory_suggestion |
              admin_approval_required | temporary_only | discard | block_sensitive
    """
    # 1. Secrets IMMER blockieren, egal was der Aufrufer klassifiziert hat.
    if _contains_secret_content(content):
        return "block_sensitive"
    # 2. Sensible Kategorien: nie dauerhaft speichern.
    if info_kind == "sensitive":
        return "block_sensitive"
    # 3. Technisch notwendig: bestehende Audit-/Datenpfade, nie Suggestion.
    if info_kind == "technical":
        return "technically_store"
    # 4. Reine Einstellung: nach user_settings, nicht ins Gedaechtnis.
    if info_kind == "setting":
        return "store_as_setting"
    # 5. Inhaltliches Wissen: Wiederverwendbarkeit + Quelle Pflicht.
    if not reusable:
        return "discard"
    if not has_source:
        return "temporary_only"
    # 6. Speichermodus des Nutzers respektieren.
    settings = get_user_settings(user_id, tenant_id) or {}
    modus = settings.get("speichermodus", "immer_fragen")
    if modus == "nie_automatisch" and not user_initiated:
        return "temporary_only"
    if modus == "projektbezogen_fragen" and not project_id:
        return "temporary_only"
    # 7. Ziel-Scope: Firmenwissen braucht Admin-Freigabe (Mini-PR-3-Regel).
    if org_related:
        return "create_company_memory_suggestion"
    return "create_user_memory_suggestion"


def create_memory_suggestion(*, user_id: str, tenant_id: str, suggested_scope: str,
                             suggested_title: str, suggested_content: str | None,
                             suggested_purpose: str | None, source_type: str | None,
                             suggested_category: str | None = None,
                             source_reference: str | None = None,
                             status: str | None = None, risk_level: str = "low",
                             project_id: str | None = None,
                             expires_at: datetime | None = None) -> dict[str, Any]:
    """Legt einen Vorschlag an (noch KEIN Gedaechtnis). company_memory erzwingt
    Admin-Freigabe. Blockierte Vorschlaege speichern NIE den Rohinhalt --
    nur Kategorie/Grund (Datensparsamkeit bei sensiblen Funden)."""
    if suggested_scope not in _VALID_MEMORY_SCOPES:
        raise MemoryValidationError(f"Ungueltiger suggested_scope: {suggested_scope!r}")
    if risk_level not in _VALID_RISK_LEVELS:
        raise MemoryValidationError(f"Ungueltiger risk_level: {risk_level!r}")
    if not suggested_purpose:
        raise MemoryValidationError("Vorschlag braucht suggested_purpose.")
    if not source_type:
        raise MemoryValidationError("Vorschlag braucht source_type.")

    requires_admin = suggested_scope == "company_memory"
    if status is None:
        status = "needs_admin_approval" if requires_admin else "open"
    if status not in _VALID_SUGGESTION_STATUS:
        raise MemoryValidationError(f"Ungueltiger status: {status!r}")

    # Blockierte Vorschlaege: Rohinhalt NIE speichern, nur Kategorie-Hinweis.
    if status == "blocked" or risk_level == "blocked" or _contains_secret_content(suggested_content):
        suggested_content = "[BLOCKIERT: sensibler Inhalt nicht gespeichert]"
        status = "blocked"
        risk_level = "blocked"

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        result = conn.execute(insert(memory_suggestions).values(
            user_id=user_id, tenant_id=tenant_id, suggested_scope=suggested_scope,
            suggested_title=suggested_title, suggested_content=suggested_content,
            suggested_category=suggested_category, suggested_purpose=suggested_purpose,
            source_type=source_type, source_reference=source_reference,
            status=status, risk_level=risk_level,
            requires_admin_approval=int(requires_admin), project_id=project_id,
            created_at=now, expires_at=expires_at,
        ))
        suggestion_id = result.inserted_primary_key[0]
    return _get_memory_suggestion(suggestion_id)


def _get_memory_suggestion(suggestion_id: int, *, tenant_id: str | None = None,
                           user_id: str | None = None) -> dict[str, Any] | None:
    """Knowledge Phase 1: optionale tenant_id/user_id-Filter. memory_suggestions
    hat (anders als memory_visibility) eine eigene tenant_id-Spalte -- die
    wird hier direkt im SQL-WHERE genutzt statt nur nachtraeglich in Python
    zu vergleichen. Ohne Angabe (interner Aufruf direkt nach eigenem
    INSERT) bleibt das Verhalten unveraendert ungefiltert."""
    query = select(memory_suggestions).where(memory_suggestions.c.id == suggestion_id)
    if tenant_id is not None:
        query = query.where(memory_suggestions.c.tenant_id == tenant_id)
    if user_id is not None:
        query = query.where(memory_suggestions.c.user_id == user_id)
    with engine.begin() as conn:
        row = conn.execute(query).mappings().first()
    if not row:
        return None
    result = dict(row)
    result["requires_admin_approval"] = bool(result["requires_admin_approval"])
    return result


def list_memory_suggestions_for_user(user_id: str, tenant_id: str = DEFAULT_TENANT_ID,
                                     status: str | None = "open") -> list[dict[str, Any]]:
    """Nur eigene Vorschlaege. status=None listet alle Status (fuer Review-Ansichten)."""
    query = (
        select(memory_suggestions)
        .where(memory_suggestions.c.user_id == user_id)
        .where(memory_suggestions.c.tenant_id == tenant_id)
    )
    if status is not None:
        query = query.where(memory_suggestions.c.status == status)
    with engine.begin() as conn:
        rows = conn.execute(query.order_by(memory_suggestions.c.created_at.desc())).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["requires_admin_approval"] = bool(d["requires_admin_approval"])
        out.append(d)
    return out


def reject_memory_suggestion(suggestion_id: int, *, reviewed_by: str, tenant_id: str,
                             user_id: str | None = None) -> None:
    """Abgelehnte Vorschlaege erzeugen NIE ein memory_item.

    Knowledge Phase 1: tenant_id ist Pflicht und wird im UPDATE-WHERE
    durchgesetzt (nicht nur vom Aufrufer vorab geprueft -- Verteidigung in
    der Datenschicht selbst, TOCTOU-sicher). user_id (falls angegeben):
    zusaetzliche Eigentuemer-Bindung, damit ein anderer Nutzer desselben
    Tenants einen fremden Vorschlag nicht ablehnen kann. rowcount==0
    bedeutet: kein passender Vorschlag (falscher Tenant/Owner oder nicht
    vorhanden) -- wird einheitlich als "nicht gefunden" gemeldet."""
    tenant_id = _require_tenant(tenant_id, funktion="reject_memory_suggestion")
    query = (
        update(memory_suggestions)
        .where(memory_suggestions.c.id == suggestion_id)
        .where(memory_suggestions.c.tenant_id == tenant_id)
    )
    if user_id is not None:
        query = query.where(memory_suggestions.c.user_id == user_id)
    with engine.begin() as conn:
        result = conn.execute(
            query.values(status="rejected", reviewed_at=datetime.now(timezone.utc), reviewed_by=reviewed_by)
        )
    if result.rowcount == 0:
        raise MemoryValidationError("Vorschlag nicht gefunden.")


def mark_memory_suggestion_blocked(suggestion_id: int, *, tenant_id: str,
                                   reviewed_by: str | None = None, user_id: str | None = None) -> None:
    """Blockiert + entfernt den Rohinhalt (Datensparsamkeit).

    Knowledge Phase 1: tenant_id Pflicht, im UPDATE-WHERE durchgesetzt --
    siehe reject_memory_suggestion() fuer Details."""
    tenant_id = _require_tenant(tenant_id, funktion="mark_memory_suggestion_blocked")
    query = (
        update(memory_suggestions)
        .where(memory_suggestions.c.id == suggestion_id)
        .where(memory_suggestions.c.tenant_id == tenant_id)
    )
    if user_id is not None:
        query = query.where(memory_suggestions.c.user_id == user_id)
    with engine.begin() as conn:
        result = conn.execute(
            query.values(status="blocked", risk_level="blocked",
                        suggested_content="[BLOCKIERT: sensibler Inhalt nicht gespeichert]",
                        reviewed_at=datetime.now(timezone.utc), reviewed_by=reviewed_by)
        )
    if result.rowcount == 0:
        raise MemoryValidationError("Vorschlag nicht gefunden.")


def confirm_memory_suggestion(suggestion_id: int, *, confirmed_by: str, tenant_id: str,
                              reviewer_role: str = "user", user_id: str | None = None) -> dict[str, Any]:
    """Ueberfuehrt einen bestaetigten Vorschlag in das Gedaechtnis:
    memory_source + memory_item + memory_visibility (via create_memory_item).
    company_memory verlangt Admin-Rolle (bestehendes Rollenmodell: admin/manager).
    Nur Status open/needs_admin_approval sind bestaetigbar -- rejected/expired/
    blocked erzeugen nie ein memory_item.

    Knowledge Phase 1: tenant_id ist Pflicht und wird direkt beim Laden des
    Vorschlags gefiltert (_get_memory_suggestion(tenant_id=...)) -- vorher
    wurde der Vorschlag komplett ungefiltert geladen und `suggestion["tenant_id"]`
    blind fuer die Item-Erstellung uebernommen; ein fremder Tenant konnte so
    theoretisch einen fremden Vorschlag bestaetigen. user_id (falls
    angegeben): zusaetzliche Eigentuemer-Bindung fuer user_memory-Vorschlaege
    -- gilt unabhaengig von der Rolle (auch ein Manager darf keinen fremden
    persoenlichen Vorschlag bestaetigen)."""
    tenant_id = _require_tenant(tenant_id, funktion="confirm_memory_suggestion")
    suggestion = _get_memory_suggestion(suggestion_id, tenant_id=tenant_id)
    if suggestion is None:
        raise MemoryValidationError("Vorschlag nicht gefunden.")
    if suggestion["suggested_scope"] == "user_memory" and user_id is not None and suggestion["user_id"] != user_id:
        raise MemoryValidationError("Vorschlag gehoert einer anderen Person.")
    if suggestion["status"] not in ("open", "needs_admin_approval"):
        raise MemoryValidationError(
            f"Vorschlag mit Status {suggestion['status']!r} kann nicht bestaetigt werden."
        )
    if suggestion["requires_admin_approval"] and reviewer_role not in ("admin", "manager"):
        raise MemoryValidationError(
            "company_memory-Vorschlaege brauchen Admin-/Manager-Freigabe."
        )

    source = create_memory_source(
        tenant_id=suggestion["tenant_id"],
        source_type=suggestion["source_type"] or "user_confirmation",
        reference=suggestion["source_reference"],
        source_title=f"Bestaetigter Vorschlag #{suggestion_id}",
        confirmed_by=confirmed_by,
        approved_by=confirmed_by if suggestion["requires_admin_approval"] else None,
    )
    owner = suggestion["user_id"] if suggestion["suggested_scope"] == "user_memory" else None
    item = create_memory_item(
        tenant_id=suggestion["tenant_id"], scope=suggestion["suggested_scope"],
        title=suggestion["suggested_title"], content=suggestion["suggested_content"] or "",
        purpose=suggestion["suggested_purpose"], source_id=source["id"],
        owner_user_id=owner, category=suggestion["suggested_category"],
        status="active", created_by=suggestion["user_id"],
        approved_by=confirmed_by if suggestion["requires_admin_approval"] else None,
    )
    with engine.begin() as conn:
        conn.execute(
            update(memory_suggestions).where(memory_suggestions.c.id == suggestion_id)
            .values(status="confirmed", reviewed_at=datetime.now(timezone.utc), reviewed_by=confirmed_by)
        )
    return {"suggestion_id": suggestion_id, "memory_item_id": item["id"], "source_id": source["id"]}


def apply_confirmed_memory_suggestion(suggestion_id: int, *, confirmed_by: str, tenant_id: str,
                                      reviewer_role: str = "user", user_id: str | None = None) -> dict[str, Any]:
    """Alias gemaess Spec-Namensvorschlag -- identisch zu confirm_memory_suggestion."""
    return confirm_memory_suggestion(
        suggestion_id, confirmed_by=confirmed_by, tenant_id=tenant_id,
        reviewer_role=reviewer_role, user_id=user_id,
    )


# ── Block B Schritt 2: Export & Loeschung (Art. 20 / Art. 17 DSGVO) ──────────
# Karo-Entscheidung zur Stop-Regel: DELETE /api/me deaktiviert den Account
# (active=0) und loescht/anonymisiert abhaengige persoenliche Daten. KEIN
# hartes Loeschen des users-Datensatzes in dieser PR.

def export_user_data(user_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> dict[str, Any]:
    """Alle eigenen Daten fuer den Nutzer-Export (Art. 20 DSGVO). Niemals
    hashed_password, niemals fremde Daten, nur user_memory-Scope (kein
    Firmenwissen -- das gehoert nicht dem einzelnen Nutzer)."""
    user = get_user(user_id, tenant_id)
    user_export = None
    if user:
        user_export = {k: v for k, v in user.items() if k != "hashed_password"}
    return {
        "user": user_export,
        "user_settings": get_user_settings(user_id, tenant_id),
        "user_projects": list_user_projects(tenant_id, user_id),
        "user_chats": list_user_chats(tenant_id, user_id),
        "memory_items": list_active_memory_items_for_user(user_id, tenant_id),
        "memory_suggestions": list_memory_suggestions_for_user(user_id, tenant_id, status=None),
    }


def _soft_delete_owned_memory_items(conn: Any, user_id: str, tenant_id: str, now: datetime) -> None:
    """Loescht (soft) ausschliesslich eigenes user_memory des Nutzers --
    NIEMALS company_memory (M1: expliziter scope-Filter; company_memory
    hat ohnehin owner_user_id=NULL und wuerde durch den owner_user_id-
    Filter allein schon ausgeschlossen, der scope-Filter macht das aber
    unmissverstaendlich explizit statt implizit).

    Knowledge Phase 1: die fruehere Uebergangsregel (Legacy-NULL-Zeilen
    zusaetzlich einschliessen) entfaellt -- memory_items.tenant_id ist NOT
    NULL, siehe list_active_memory_items_for_user()."""
    conn.execute(
        update(memory_items)
        .where(memory_items.c.scope == "user_memory")
        .where(memory_items.c.owner_user_id == user_id)
        .where(memory_items.c.tenant_id == tenant_id)
        .values(status="deleted", updated_at=now)
    )


def delete_own_account_data(user_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> None:
    """Loescht/deaktiviert alle eigenen personenbezogenen Daten in EINER
    Transaktion (alles oder nichts): user_projects, user_chats,
    user_settings, eigene memory_items (soft-delete), eigene
    memory_suggestions. Setzt users.active=0 -- der users-Datensatz selbst
    bleibt bestehen (keine physische Loeschung in dieser PR, siehe
    docs/BLOCK_B_MASTER_AUFTRAG.md)."""
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            delete(user_projects)
            .where(user_projects.c.user_id == user_id)
            .where(user_projects.c.tenant_id == tenant_id)
        )
        conn.execute(
            delete(user_chats)
            .where(user_chats.c.user_id == user_id)
            .where(user_chats.c.tenant_id == tenant_id)
        )
        conn.execute(
            delete(user_settings)
            .where(user_settings.c.user_id == user_id)
            .where(user_settings.c.tenant_id == tenant_id)
        )
        _soft_delete_owned_memory_items(conn, user_id, tenant_id, now)
        conn.execute(
            delete(memory_suggestions)
            .where(memory_suggestions.c.user_id == user_id)
            .where(memory_suggestions.c.tenant_id == tenant_id)
        )
        conn.execute(
            update(users)
            .where(users.c.user_id == user_id)
            .where(users.c.tenant_id == tenant_id)
            .values(active=0)
        )


def _max_attempts() -> int:
    return int(os.getenv("AILIZA_MAX_LOGIN_ATTEMPTS", "5"))

def _lockout_minutes() -> int:
    return int(os.getenv("AILIZA_LOCKOUT_MINUTES", "15"))


# PR A: interne, technische Ursachen-Codes fuer fehlgeschlagene Anmeldungen.
# NIEMALS nach aussen weitergeben (main.py gibt fuer ALLE Faelle dieselbe
# neutrale 401-Antwort zurueck) -- ausschliesslich fuer die interne
# Diagnose/das Audit-Log gedacht (kein User-Enumeration-Leck).
AUTH_REASON_USER_NOT_FOUND = "auth_user_not_found"
AUTH_REASON_TENANT_MISMATCH = "auth_tenant_mismatch"
AUTH_REASON_USER_INACTIVE = "auth_user_inactive"
AUTH_REASON_USER_LOCKED = "auth_user_locked"
AUTH_REASON_PASSWORD_MISMATCH = "auth_password_mismatch"
AUTH_REASON_PASSWORD_HASH_INVALID = "auth_password_hash_invalid"
AUTH_REASON_DATABASE_ERROR = "auth_database_error"
AUTH_REASON_SUCCESS = "auth_success"

# Timing-Schutz: fester, einmalig vorab berechneter bcrypt-Hash. Bei
# unbekannten Nutzernamen wird trotzdem ein bcrypt-Vergleich gegen diesen
# Dummy-Hash durchgefuehrt, damit die Antwortzeit sich nicht messbar von der
# eines "Passwort falsch"-Falls unterscheidet (kein User-Enumeration-Leck
# ueber Timing). Bewusst NICHT pro Request neu erzeugt (bcrypt.gensalt() ist
# teuer und wuerde selbst zur Streuung beitragen).
_DUMMY_BCRYPT_HASH = "$2b$12$C6UzMDM.H6dfI/f/IKcEeO0rAkD7DdyWjSGUmwq8U1qXENJ2QLQVe"


def authenticate_user_with_reason(
    user_id: str, plain_password: str, tenant_id: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Wie authenticate_user(), gibt zusaetzlich einen internen, technischen
    Ursachen-Code zurueck (siehe AUTH_REASON_*-Konstanten). Der Ursachen-Code
    ist AUSSCHLIESSLICH fuer interne Diagnose/Audit-Logs bestimmt -- die
    oeffentliche HTTP-Antwort bleibt in main.py fuer alle Nicht-Erfolgsfaelle
    identisch (keine unterschiedlichen Statuscodes/Texte je Ursache)."""
    row = get_user(user_id, tenant_id)
    if not row:
        # Sekundaerpruefung NUR fuer die interne Klassifikation: existiert der
        # Nutzername in irgendeinem Tenant, aber nicht im angefragten? Das
        # aendert NICHTS an der oeffentlichen Antwort, hilft aber intern,
        # eine falsche Tenant-Zuordnung von einem unbekannten Nutzernamen zu
        # unterscheiden.
        try:
            import bcrypt
            bcrypt.checkpw(plain_password.encode(), _DUMMY_BCRYPT_HASH.encode())
        except ImportError:
            pass
        if tenant_id is not None and get_user(user_id, None) is not None:
            return None, AUTH_REASON_TENANT_MISMATCH
        return None, AUTH_REASON_USER_NOT_FOUND

    if not row.get("active"):
        return None, AUTH_REASON_USER_INACTIVE

    # Lockout pruefen
    locked_until = row.get("locked_until")
    if locked_until is not None:
        if isinstance(locked_until, str):
            locked_until = datetime.fromisoformat(locked_until)
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < locked_until:
            return None, AUTH_REASON_USER_LOCKED

    try:
        import bcrypt
        pw_ok = bcrypt.checkpw(plain_password.encode(), row["hashed_password"].encode())
    except ImportError:
        return None, AUTH_REASON_DATABASE_ERROR
    except (ValueError, TypeError):
        # bcrypt wirft ValueError bei einem strukturell ungueltigen Hash
        # (z.B. Datenkorruption) -- fachlich klar von "Passwort falsch" zu
        # unterscheiden, ohne das nach aussen zu zeigen.
        return None, AUTH_REASON_PASSWORD_HASH_INVALID

    if not pw_ok:
        _record_failed_login(user_id, tenant_id or row["tenant_id"])
        return None, AUTH_REASON_PASSWORD_MISMATCH

    # Erfolg: Zähler zurücksetzen
    _reset_failed_login(user_id, tenant_id or row["tenant_id"])
    return {k: v for k, v in row.items() if k not in ("hashed_password",)}, AUTH_REASON_SUCCESS


def authenticate_user(user_id: str, plain_password: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    """
    Prueft Credentials. Sperrt Account nach _MAX_FAILED_ATTEMPTS Fehlversuchen
    fuer _LOCKOUT_MINUTES Minuten. Gibt None zurueck bei Fehler (kein Hinweis auf Grund).
    Bestehende, unveraenderte oeffentliche Signatur -- reiner Wrapper um
    authenticate_user_with_reason() fuer alle Aufrufer, die den Ursachen-Code
    nicht benoetigen (z.B. bestehende Tests)."""
    user, _reason = authenticate_user_with_reason(user_id, plain_password, tenant_id)
    return user


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


# init_db() wird NICHT mehr automatisch beim Modulimport ausgefuehrt (Karo-
# Entscheidung 2026-08-02, Arbeitspaket "Formales Migrationssystem"): ein
# reiner Import von apps.backend.database (z.B. durch alembic/env.py oder
# apps/backend/alembic_adopt.py) darf keine Tabellen anlegen. Der
# tatsaechliche Datenbankstart erfolgt ausdruecklich beim Start der
# Anwendung -- siehe FastAPI-Lifespan in apps/backend/main.py (`init_db()`
# wird dort explizit aufgerufen). Fuer Tests siehe tests/conftest.py.


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


# ── Model Intelligence (Paket A): reine Empfehlungsschicht ──────────────────
# GRUNDREGEL: kein Aufruf hier setzt jemals status="approved" fuer einen neu
# angelegten Kandidaten. Freigabe ist ausdruecklich ein separater,
# menschlicher Schritt (approve_model_candidate()), niemals Teil des
# Anlegens oder des Routings selbst.

def create_model_candidate(provider: str, model_id: str, *,
                            modalities: list[str], capabilities: list[str],
                            context_window: int, regions: list[str] | None = None,
                            evidence_urls: list[str] | None = None,
                            created_by: str) -> dict[str, Any]:
    """Legt einen neuen Modell-Kandidaten an -- IMMER mit status="candidate".
    Kein Upsert: (provider, model_id) ist unique, ein zweiter Aufruf mit
    derselben Kombination wirft IntegrityError.

    created_by ist PFLICHT: ohne bekannten Urheber laesst sich in
    approve_model_candidate() keine Selbstfreigabe erkennen, das
    Vier-Augen-Prinzip waere damit wirkungslos. Ein optionaler Wert wurde
    von keinem Aufrufer gesetzt und machte die Pruefung praktisch nie
    aktiv (unabhaengig belegt)."""
    if not created_by or not str(created_by).strip():
        raise ValueError(
            "create_model_candidate: created_by ist Pflicht "
            "(Grundlage der Selbstfreigabe-Pruefung)."
        )
    now = _now_utc()
    with engine.begin() as conn:
        conn.execute(insert(model_candidates).values(
            provider=provider, model_id=model_id,
            modalities=list(modalities), capabilities=list(capabilities),
            context_window=context_window, regions=list(regions or []),
            status="candidate", benchmark_version="unbenchmarked",
            evidence_urls=list(evidence_urls or []),
            created_by=created_by,
            created_at=now, updated_at=now,
        ))
    return {
        "provider": provider, "model_id": model_id, "status": "candidate",
        "modalities": modalities, "capabilities": capabilities,
        "context_window": context_window, "regions": regions or [],
        "created_by": created_by,
        "created_at": now, "updated_at": now,
    }


# ── Phase 1 (Ladengeschaeft-Produktlauf): Kunde -> Artikel -> Rechnung ───────
# Kleinster abgeschlossener Baustein: nur Kundenstammdaten (Anlegen + Liste).
# GRUNDREGEL wie oben: jede Funktion filtert IMMER nach tenant_id. Kein Weg,
# ueber diese Helper an Datensaetze fremder Mandanten zu gelangen.

def create_customer(customer_id: str, tenant_id: str, *,
                     name: str, owner_user_id: str | None = None,
                     email: str | None = None, phone: str | None = None,
                     address: str | None = None, note: str | None = None) -> dict[str, Any]:
    """Legt einen neuen Kunden an. Kein Upsert -- eine bestehende id+tenant_id
    fuehrt zu einem IntegrityError (Primary-Key-Verletzung), keine stille
    Ueberschreibung fremder/eigener Datensaetze. Personenbezogene Felder
    werden wie bei user_projects/user_chats feldverschluesselt gespeichert."""
    now = _now_utc()
    with engine.begin() as conn:
        conn.execute(insert(customers).values(
            id=customer_id, tenant_id=tenant_id, owner_user_id=owner_user_id,
            name=encrypt_field(name), email=encrypt_field(email),
            phone=encrypt_field(phone), address=encrypt_field(address),
            note=encrypt_field(note), created_at=now, updated_at=now,
        ))
    return {
        "id": customer_id, "tenant_id": tenant_id, "owner_user_id": owner_user_id,
        "name": name, "email": email, "phone": phone, "address": address, "note": note,
        "created_at": now, "updated_at": now,
    }


class ModelApprovalDenied(RuntimeError):
    """Freigabe verweigert -- eigene Klasse, damit ein Aufrufer sie nicht
    versehentlich mit einem Datenfehler (ValueError) verwechselt."""


def approve_model_candidate(provider: str, model_id: str, *,
                             actor: Any,
                             quality_score: float, latency_score: float,
                             cost_score: float, privacy_score: float,
                             benchmark_version: str) -> dict[str, Any] | None:
    """Setzt status="approved" -- der einzige Weg, wie ein Kandidat waehlbar
    wird. Gibt None zurueck, wenn (provider, model_id) nicht existiert
    (kein stilles Anlegen).

    B4 (korrigiert): Frueher genuegte ein frei uebergebener Rollen-String
    (`reviewer_role="admin"`), der von keiner Sitzung gedeckt war -- jeder
    Aufrufer konnte ihn setzen. Jetzt ist ein authentifizierter Actor
    (TokenData) Pflicht; die Entscheidung faellt im zentralen
    evaluate_permission() unter der Aktion MODEL_CANDIDATE_APPROVE.
    approved_by wird aus dem Actor abgeleitet und NICHT vom Aufrufer
    uebernommen -- eine Freigabe im fremden Namen ist damit ausgeschlossen.

    Selbstfreigabe: Stimmt created_by des Kandidaten mit dem Actor ueberein,
    verweigert der Evaluator. Ist created_by nicht gesetzt (Altbestand oder
    Anlage ohne Urheber), kann das Vier-Augen-Prinzip nicht geprueft werden;
    dieser Fall wird auditiert und ist als HANDOFF dokumentiert.

    HANDOFF: Eine fachlich bestaetigte Freigabepolicy fuer Modelle existiert
    im Repository nicht. Die Schwelle folgt dem bestehenden Projektmuster
    (admin/manager) und ist deny-by-default -- sie ist zu bestaetigen."""
    try:
        from .permissions import evaluate_permission, MODEL_CANDIDATE_APPROVE
    except ImportError:  # pragma: no cover - Ausfuehrung aus apps/backend/
        from permissions import evaluate_permission, MODEL_CANDIDATE_APPROVE  # type: ignore

    if actor is None or not getattr(actor, "user_id", None):
        raise ModelApprovalDenied(
            "Modellfreigabe erfordert eine angemeldete Person."
        )

    with engine.begin() as conn:
        vorhandener = conn.execute(
            select(model_candidates)
            .where(model_candidates.c.provider == provider)
            .where(model_candidates.c.model_id == model_id)
        ).mappings().first()
    if vorhandener is None:
        return None

    urheber = vorhandener["created_by"]
    if not urheber or not str(urheber).strip():
        # Fail-closed statt fail-open: ohne bekannten Urheber laesst sich
        # eine Selbstfreigabe nicht ausschliessen. Vorher wurde der Fall nur
        # auditiert und die Freigabe trotzdem erteilt -- damit war das
        # Vier-Augen-Prinzip fuer Altbestaende wirkungslos.
        write_audit_entry(
            action="model.approval.denied",
            tenant_id=getattr(actor, "tenant_id", None) or DEFAULT_TENANT_ID,
            metadata={"provider": provider, "model_id": model_id,
                      "reason_code": "FOUR_EYES_NOT_VERIFIABLE"},
        )
        raise ModelApprovalDenied(
            "Ohne bekannten Urheber (created_by) kann eine Selbstfreigabe nicht "
            "ausgeschlossen werden -- die Freigabe wird verweigert."
        )

    entscheidung = evaluate_permission(
        action=MODEL_CANDIDATE_APPROVE,
        actor=actor,
        tenant_id=getattr(actor, "tenant_id", None) or DEFAULT_TENANT_ID,
        resource_type="model_candidate",
        resource_id=f"{provider}:{model_id}",
        resource_owner_user_id=urheber,
    )
    if not entscheidung.allowed:
        raise ModelApprovalDenied(entscheidung.reason_de)

    approved_by = actor.user_id
    now = _now_utc()
    with engine.begin() as conn:
        result = conn.execute(
            update(model_candidates)
            .where(model_candidates.c.provider == provider)
            .where(model_candidates.c.model_id == model_id)
            .values(
                status="approved", approved_by=approved_by, approved_at=now,
                quality_score=quality_score, latency_score=latency_score,
                cost_score=cost_score, privacy_score=privacy_score,
                benchmark_version=benchmark_version, updated_at=now,
            )
        )
        if result.rowcount == 0:
            return None
        row = conn.execute(
            select(model_candidates)
            .where(model_candidates.c.provider == provider)
            .where(model_candidates.c.model_id == model_id)
        ).mappings().first()
    return dict(row)


def list_model_candidates(status: str | None = None) -> list[dict[str, Any]]:
    """Plattformweite Liste -- kein tenant_id-Filter (siehe db_schema.py:
    welche Modelle existieren duerfen, ist keine Mandantenentscheidung)."""
    query = select(model_candidates).order_by(model_candidates.c.provider, model_candidates.c.model_id)
    if status is not None:
        query = query.where(model_candidates.c.status == status)
    with engine.begin() as conn:
        rows = conn.execute(query).mappings().all()
    return [dict(row) for row in rows]


_MODEL_ROUTING_BLOCKED_CLASSES = {"credentials", "special_category", "hr", "legal"}

# Feste Aufgabenarten. task war vorher freier Text und wurde woertlich
# persistiert -- damit konnte ein Aufrufer einen Rohprompt in die Datenbank
# und ins Audit schreiben. Nur diese Werte sind zulaessig.
_ROUTING_TASKS = {"chat", "summarize", "extract", "classify", "code", "translate", "table"}
_ROUTING_MODALITIES = {"text", "image", "audio", "video"}
_ROUTING_RISKS = {"low", "medium", "high", "critical"}
# Datenklassen, die unabhaengig von der Angabe des Aufrufers ein hohes
# Risiko bedeuten. data_risk war vorher frei waehlbar -- mit "low" liess
# sich die Datenschutzschwelle (privacy_score >= 0.8) umgehen, obwohl der
# Text personenbezogene Daten enthielt (unabhaengig reproduziert).
_HIGH_RISK_DATA_CLASSES = {
    "personal_data", "financial", "security_sensitive", "intellectual_property",
}


def recommend_model(tenant_id: str, *, modality: str, task: str,
                     required_capabilities: list[str] | None = None,
                     min_context_window: int = 0,
                     allowed_providers: list[str] | None = None,
                     required_region: str | None = None,
                     local_only: bool = False,
                     data_risk: str = "low",
                     prompt_text: str | None = None) -> dict[str, Any]:
    """Liefert NUR eine Empfehlung -- ruft selbst keinen Provider auf und
    veraendert keine Freigabe. Schreibt einen Audit-Eintrag ueber das
    bestehende Audit-Vault (write_audit_entry), keine separate Logdatei.

    B3 (zweifach korrigiert):

    1. Frueher war die Datenklassenliste ein optionaler Parameter --
       Weglassen hob die Sperre auf.
    2. Danach wurde ein ClassificationResult verlangt. Auch das war KEIN
       Herkunftsnachweis: die Dataclass ist offen, ein Aufrufer konnte ein
       harmloses Ergebnis selbst bauen und damit HR-/Gesundheitsdaten
       durchrouten (unabhaengig reproduziert).

    Jetzt klassifiziert diese Funktion SELBST ueber classify(). Nur ein
    hier erzeugtes Ergebnis wird verwendet -- ein Aufrufer kann keine
    Klassifikation mehr vorgeben. Ohne prompt_text ist keine Klassifikation
    moeglich und es wird kein Modell ausgewaehlt (fail-closed).

    prompt_text wird ausschliesslich im Arbeitsspeicher klassifiziert und
    NIEMALS gespeichert oder auditiert -- persistiert wird nur ein
    SHA-256-Praefix als Wiedererkennungsmerkmal.

    HANDOFF (B-GOV-2): ClassificationResult traegt keine Versionsangabe;
    eine Bindung an eine Klassifiziererversion ist daher nicht moeglich."""
    try:
        from .intelligence.model_router import ModelRouter
        from .intelligence.models import ModelCandidate, RoutingRequest
        from .governance.data_governance import classify
    except ImportError:  # pragma: no cover - Fallback bei Ausfuehrung aus apps/backend/
        from intelligence.model_router import ModelRouter  # type: ignore
        from intelligence.models import ModelCandidate, RoutingRequest  # type: ignore
        from governance.data_governance import classify  # type: ignore

    # Aufgabenart gegen eine feste Liste pruefen. Vorher war task freier
    # Text und wurde woertlich in routing_decisions UND ins Audit
    # geschrieben -- ein Aufrufer konnte damit einen ganzen Rohprompt
    # persistieren (unabhaengig reproduziert).
    # Alle drei Felder werden in routing_decisions gespeichert UND auditiert.
    # Ungeprueft waren sie Freitext -- damit liess sich ein Rohprompt
    # persistieren (unabhaengig reproduziert). Nur feste Werte sind zulaessig.
    for feld, wert, erlaubt in (("Aufgabenart", task, _ROUTING_TASKS),
                                ("Modalitaet", modality, _ROUTING_MODALITIES),
                                ("Risikostufe", data_risk, _ROUTING_RISKS)):
        if wert not in erlaubt:
            return {
                "selected": None, "fallback": None, "score": None,
                "reason": f"Unbekannte {feld} {wert!r}. Erlaubt: {sorted(erlaubt)}.",
                "considered": (), "benchmark_version": None,
            }

    prompt_ref = (hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]
                  if prompt_text else None)

    if not prompt_text or not prompt_text.strip():
        write_audit_entry(
            action="model.routing.blocked",
            metadata={"modality": modality, "task": task,
                      "reason_code": "CLASSIFICATION_NOT_POSSIBLE"},
            tenant_id=tenant_id,
        )
        return {
            "selected": None, "fallback": None, "score": None,
            "reason": ("Ohne Text kann nicht klassifiziert werden -- es wird kein "
                       "externes Modell ausgewaehlt."),
            "considered": (), "benchmark_version": None,
        }

    klassifikation = classify(prompt_text)
    data_classes = {getattr(c, "value", str(c)).lower()
                    for c in (klassifikation.data_classes or [])}

    # classify() stuft echte Schluessel (sk-..., gsk_..., AIza...) nicht
    # zuverlaessig als credentials ein -- die vorhandene Secret-Heuristik
    # erkennt sie und wird deshalb zusaetzlich ausgewertet (unabhaengig
    # belegt: ein echter API-Key galt sonst als "public").
    if _contains_secret_content(prompt_text):
        data_classes.add("credentials")

    # Risikostufe: die Angabe des Aufrufers ist nur eine Untergrenze. Eine
    # Klassifikation mit personenbezogenen oder vergleichbar sensiblen Daten
    # hebt sie an -- sonst koennte "low" die Datenschutzschwelle umgehen.
    if data_classes & _HIGH_RISK_DATA_CLASSES and data_risk in ("low", "medium"):
        data_risk = "high"

    blocked = _MODEL_ROUTING_BLOCKED_CLASSES & data_classes
    if blocked:
        write_audit_entry(
            action="model.routing.blocked",
            metadata={
                "modality": modality, "task": task,
                "blocked_classes": sorted(blocked),
                "prompt_ref": prompt_ref,
            },
            tenant_id=tenant_id,
        )
        return {
            "selected": None, "fallback": None, "score": None,
            "reason": "Datenklasse darf nicht extern geroutet werden (CREDENTIALS/SPECIAL_CATEGORY/HR/LEGAL).",
            "considered": (), "benchmark_version": None,
        }

    approved_rows = list_model_candidates(status="approved")
    candidates = [ModelCandidate.from_row(row) for row in approved_rows]

    request = RoutingRequest(
        modality=modality, task=task,
        required_capabilities=frozenset(required_capabilities or []),
        min_context_window=min_context_window,
        allowed_providers=frozenset(allowed_providers) if allowed_providers is not None else None,
        required_region=required_region, local_only=local_only,
        data_risk=data_risk,  # type: ignore[arg-type]
    )
    decision = ModelRouter(candidates).route(request)

    now = _now_utc()
    with engine.begin() as conn:
        conn.execute(insert(routing_decisions).values(
            tenant_id=tenant_id, modality=modality, task=task, data_risk=data_risk,
            selected=decision.selected, fallback=decision.fallback, score=decision.score,
            reason=decision.reason, considered=list(decision.considered),
            benchmark_version=decision.benchmark_version, created_at=now,
        ))

    write_audit_entry(
        action="model.routing.recommended",
        metadata={
            # task ist gegen _ROUTING_TASKS geprueft und damit kein Freitext.
            "modality": modality, "task": task, "data_risk": data_risk,
            "selected": decision.selected, "fallback": decision.fallback,
            "considered_count": len(decision.considered),
            # Wiedererkennung ohne Inhalt: gekuerzter Hash, nie der Text.
            "prompt_ref": prompt_ref,
        },
        tenant_id=tenant_id,
    )

    return {
        "selected": decision.selected, "fallback": decision.fallback,
        "score": decision.score, "reason": decision.reason,
        "considered": decision.considered, "benchmark_version": decision.benchmark_version,
    }


def _decode_customer_row(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row)
    row["name"] = decrypt_field(row["name"])
    row["email"] = decrypt_field(row["email"])
    row["phone"] = decrypt_field(row["phone"])
    row["address"] = decrypt_field(row["address"])
    row["note"] = decrypt_field(row["note"])
    return row


def list_customers(tenant_id: str, owner_user_id: str | None = None) -> list[dict[str, Any]]:
    """Listet Kunden eines Mandanten. owner_user_id ist ein zusaetzlicher
    Filter (nicht Pflicht) -- Sichtbarkeit ueber Rollen/Rechte ist nicht
    Teil dieses kleinsten Bausteins und wird hier bewusst nicht vorweggenommen."""
    query = (
        select(customers)
        .where(customers.c.tenant_id == tenant_id)
        .order_by(customers.c.created_at.desc())
    )
    if owner_user_id is not None:
        query = query.where(customers.c.owner_user_id == owner_user_id)
    with engine.begin() as conn:
        rows = conn.execute(query).mappings().all()
    return [_decode_customer_row(row) for row in rows]


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


# ── Minimale Aufbewahrungs-Einstellung fuer hochgeladene Dokumente pro Chat
# (Karo-Entscheidung 2026-08-03) -- Grundlage fuer das spaeter geplante
# vollstaendige Eigenschaftsfenster (Dokumente/Zusammenfassung/Original-Chat,
# 1 Tag bis 12 Jahre). Hier bewusst nur EINE Kategorie (Dokumente) mit
# Behalten-ja/nein + Tageszahl.
DEFAULT_DOCUMENT_RETENTION_DAYS = 14
MIN_DOCUMENT_RETENTION_DAYS = 1
MAX_DOCUMENT_RETENTION_DAYS = 4380  # 12 Jahre -- Obergrenze aus Karo-Vorgabe


class ChatRetentionValidationError(ValueError):
    """Ungueltiger Wert fuer die Chat-Aufbewahrungs-Einstellung."""


def get_chat_document_retention(*, chat_id: str, tenant_id: str, user_id: str) -> dict[str, Any]:
    """Liest die Aufbewahrungs-Einstellung fuer Dokument-Uploads eines Chats.
    Fehlt der Chat oder ist ein Feld NULL, gelten die Systemstandards
    (behalten=True, DEFAULT_DOCUMENT_RETENTION_DAYS Tage) -- kein heimliches
    Verwerfen von Uploads ohne explizite Nutzer-Entscheidung."""
    chat = get_user_chat(chat_id, tenant_id, user_id) if chat_id else None
    keep = True
    days = DEFAULT_DOCUMENT_RETENTION_DAYS
    if chat is not None:
        if chat.get("keep_uploaded_documents") is not None:
            keep = bool(chat["keep_uploaded_documents"])
        if chat.get("document_retention_days") is not None:
            days = int(chat["document_retention_days"])
    return {"keep_documents": keep, "retention_days": days}


def set_chat_document_retention(*, chat_id: str, tenant_id: str, user_id: str,
                                keep_documents: bool, retention_days: int) -> dict[str, Any]:
    if not (MIN_DOCUMENT_RETENTION_DAYS <= retention_days <= MAX_DOCUMENT_RETENTION_DAYS):
        raise ChatRetentionValidationError(
            f"retention_days muss zwischen {MIN_DOCUMENT_RETENTION_DAYS} und "
            f"{MAX_DOCUMENT_RETENTION_DAYS} liegen (erhalten: {retention_days})."
        )
    with engine.begin() as conn:
        result = conn.execute(
            update(user_chats)
            .where(user_chats.c.id == chat_id)
            .where(user_chats.c.tenant_id == tenant_id)
            .where(user_chats.c.user_id == user_id)
            .values(
                keep_uploaded_documents=1 if keep_documents else 0,
                document_retention_days=retention_days,
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount == 0:
            raise ChatRetentionValidationError(f"Chat nicht gefunden (id={chat_id}).")
    return get_chat_document_retention(chat_id=chat_id, tenant_id=tenant_id, user_id=user_id)
