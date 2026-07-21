from __future__ import annotations

import logging
import os
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, JSON, MetaData, String, Table, Text, create_engine, delete, insert, select, update
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

# ── Mini-PR 2 (Gedaechtnis-Governance v1): Kernschema fuer sichtbares,
# kontrolliertes Gedaechtnis. NUR Datenstruktur -- keine automatische
# Erkennung, keine memory_suggestions, keine UI, kein pgvector, kein
# Wissensgraph (siehe docs/DATABASE_MEMORY_GOVERNANCE_V1.md).
memory_sources = Table(
    "memory_sources",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("source_type", String(32), nullable=False),
    Column("reference", String(255), nullable=True),
    Column("source_title", String(255), nullable=True),
    Column("source_date", DateTime(timezone=True), nullable=True),
    Column("confirmed_by", String(64), nullable=True),
    Column("approved_by", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

memory_items = Table(
    "memory_items",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=True),  # company_memory Pflicht, user_memory optional
    Column("scope", String(32), nullable=False),
    Column("owner_user_id", String(64), nullable=True),  # user_memory Pflicht, company_memory None
    # Text statt String: Inhalt kann laenger sein, keine willkuerliche Kuerzung.
    Column("title", Text, nullable=False),
    Column("content", Text, nullable=False),
    Column("category", String(64), nullable=True),
    Column("purpose", Text, nullable=True),  # aktive Eintraege: Pflicht (siehe create_memory_item)
    Column("source_id", Integer, ForeignKey("memory_sources.id"), nullable=True),
    Column("status", String(32), nullable=False, default="suggested"),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("last_used_at", DateTime(timezone=True), nullable=True),
    Column("created_by", String(64), nullable=True),
    Column("approved_by", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_memory_items_owner", "owner_user_id"),
    Index("ix_memory_items_tenant_status", "tenant_id", "status"),
)

memory_visibility = Table(
    "memory_visibility",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("memory_item_id", Integer, ForeignKey("memory_items.id"), nullable=False, unique=True),
    Column("visibility_scope", String(32), nullable=False, default="private"),
    Column("allowed_roles", JSON, nullable=False, default=list),
    Column("allowed_user_ids", JSON, nullable=False, default=list),
    Column("allowed_org_id", String(64), nullable=True),
    Column("project_id", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# ── Mini-PR 3 (Gedaechtnis-Governance v1): Pruefraum vor memory_items.
# Vorschlaege statt heimliches Lernen -- nur bestaetigte Vorschlaege werden
# zu memory_items ueberfuehrt. Keine freie LLM-Extraktion, keine UI.
memory_suggestions = Table(
    "memory_suggestions",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("suggested_scope", String(32), nullable=False),
    Column("suggested_title", Text, nullable=False),
    Column("suggested_content", Text, nullable=True),  # bei blocked: nie Rohinhalt
    Column("suggested_category", String(64), nullable=True),
    Column("suggested_purpose", Text, nullable=True),
    Column("source_type", String(32), nullable=True),
    Column("source_reference", String(255), nullable=True),
    Column("status", String(32), nullable=False, default="open"),
    Column("risk_level", String(32), nullable=False, default="low"),
    Column("requires_admin_approval", Integer, nullable=False, default=0),
    Column("project_id", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("reviewed_at", DateTime(timezone=True), nullable=True),
    Column("reviewed_by", String(64), nullable=True),
    Index("ix_memory_suggestions_user_tenant", "user_id", "tenant_id"),
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
# -- Block C Phase C1: Wissensdatenbank-Schema (nur Fundament) --------------
# Nur Tabellen fuer Dokumentquellen, Text-Chunks und Berechtigungen.
# KEINE Extraktion, KEINE Suche, KEIN RAG, KEINE Embeddings, KEIN pgvector,
# KEINE UI in dieser Phase (siehe AILIZA_BLOCK_C_PHASE_C1_DOCUMENT_SCHEMA.md).
knowledge_sources = Table(
    "knowledge_sources",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("uploaded_by", String(64), nullable=False),
    Column("source_type", String(32), nullable=False),
    Column("title", Text, nullable=False),
    Column("original_filename", String(255), nullable=True),
    Column("storage_path", String(512), nullable=True),
    Column("content_hash", String(64), nullable=True),
    Column("mime_type", String(128), nullable=True),
    Column("status", String(32), nullable=False, default="uploaded"),
    Column("visibility_scope", String(32), nullable=False, default="private"),
    Column("approved_by", String(64), nullable=True),
    Column("approved_at", DateTime(timezone=True), nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_knowledge_sources_tenant_status", "tenant_id", "status"),
)

knowledge_chunks = Table(
    "knowledge_chunks",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_id", Integer, ForeignKey("knowledge_sources.id"), nullable=False),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("chunk_index", Integer, nullable=False),
    Column("chunk_text", Text, nullable=False),
    Column("chunk_hash", String(64), nullable=True),
    Column("page_number", Integer, nullable=True),
    Column("section_title", String(255), nullable=True),
    Column("token_estimate", Integer, nullable=True),
    Column("status", String(32), nullable=False, default="active"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_knowledge_chunks_source", "source_id"),
)

knowledge_source_permissions = Table(
    "knowledge_source_permissions",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source_id", Integer, ForeignKey("knowledge_sources.id"), nullable=False),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("visibility_scope", String(32), nullable=False, default="private"),
    Column("allowed_roles", JSON, nullable=False, default=list),
    Column("allowed_user_ids", JSON, nullable=False, default=list),
    Column("project_id", String(64), nullable=True),
    Column("created_by", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_knowledge_source_permissions_source", "source_id"),
)


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
    Pflichtregeln (Scope/Zweck/Quelle/Besitzer) werden hier durchgesetzt,
    nicht erst in einer spaeteren Schicht (fail-closed)."""
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
    return get_memory_item(item_id)


def get_memory_item(item_id: int) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(select(memory_items).where(memory_items.c.id == item_id)).mappings().first()
    return dict(row) if row else None


def list_active_memory_items_for_user(user_id: str, tenant_id: str = DEFAULT_TENANT_ID) -> list[dict[str, Any]]:
    """Nur eigene, aktive, nicht abgelaufene Eintraege -- keine fremden user_memory-Eintraege."""
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        rows = conn.execute(
            select(memory_items)
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


def set_memory_visibility(memory_item_id: int, *, visibility_scope: str,
                          allowed_roles: list | None = None, allowed_user_ids: list | None = None,
                          allowed_org_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
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


def mark_memory_item_deleted(item_id: int) -> None:
    """Soft-Delete: status='deleted'. Geloeschte Eintraege werden von den
    list_active_*-Funktionen nie zurueckgegeben (Status-Filter auf 'active')."""
    with engine.begin() as conn:
        conn.execute(
            update(memory_items).where(memory_items.c.id == item_id)
            .values(status="deleted", updated_at=datetime.now(timezone.utc))
        )


# -- Block C Phase C1: Wissensdatenbank -- nur Schema-Fundament ------------
# Keine Extraktion, keine Suche, keine Embeddings (siehe
# AILIZA_BLOCK_C_PHASE_C1_DOCUMENT_SCHEMA.md). Diese Funktionen legen nur
# Quellen/Chunks/Berechtigungen an und lesen sie zurueck.
class KnowledgeValidationError(ValueError):
    """Eine Wissensquelle/-Chunk/-Berechtigung verletzt eine Pflichtregel."""


_VALID_SOURCE_TYPES = {"pdf", "docx", "txt", "md", "csv", "manual", "url_reference"}
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


def _get_memory_suggestion(suggestion_id: int) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(
            select(memory_suggestions).where(memory_suggestions.c.id == suggestion_id)
        ).mappings().first()
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


def reject_memory_suggestion(suggestion_id: int, *, reviewed_by: str) -> None:
    """Abgelehnte Vorschlaege erzeugen NIE ein memory_item."""
    with engine.begin() as conn:
        conn.execute(
            update(memory_suggestions).where(memory_suggestions.c.id == suggestion_id)
            .values(status="rejected", reviewed_at=datetime.now(timezone.utc), reviewed_by=reviewed_by)
        )


def mark_memory_suggestion_blocked(suggestion_id: int, *, reviewed_by: str | None = None) -> None:
    """Blockiert + entfernt den Rohinhalt (Datensparsamkeit)."""
    with engine.begin() as conn:
        conn.execute(
            update(memory_suggestions).where(memory_suggestions.c.id == suggestion_id)
            .values(status="blocked", risk_level="blocked",
                    suggested_content="[BLOCKIERT: sensibler Inhalt nicht gespeichert]",
                    reviewed_at=datetime.now(timezone.utc), reviewed_by=reviewed_by)
        )


def confirm_memory_suggestion(suggestion_id: int, *, confirmed_by: str,
                              reviewer_role: str = "user") -> dict[str, Any]:
    """Ueberfuehrt einen bestaetigten Vorschlag in das Gedaechtnis:
    memory_source + memory_item + memory_visibility (via create_memory_item).
    company_memory verlangt Admin-Rolle (bestehendes Rollenmodell: admin/manager).
    Nur Status open/needs_admin_approval sind bestaetigbar -- rejected/expired/
    blocked erzeugen nie ein memory_item."""
    suggestion = _get_memory_suggestion(suggestion_id)
    if suggestion is None:
        raise MemoryValidationError("Vorschlag nicht gefunden.")
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


def apply_confirmed_memory_suggestion(suggestion_id: int, *, confirmed_by: str,
                                      reviewer_role: str = "user") -> dict[str, Any]:
    """Alias gemaess Spec-Namensvorschlag -- identisch zu confirm_memory_suggestion."""
    return confirm_memory_suggestion(suggestion_id, confirmed_by=confirmed_by, reviewer_role=reviewer_role)


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
    conn.execute(
        update(memory_items)
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
