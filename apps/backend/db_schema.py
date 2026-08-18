"""AILIZA — nebenwirkungsfreie Schema-Definition (27 Kerntabellen).

WICHTIG: Dieses Modul darf beim Import NIEMALS eine Datenbankverbindung
herstellen, kein Verzeichnis anlegen und keine Tabelle erzeugen. Es
enthaelt ausschliesslich die SQLAlchemy-Core-Definition (MetaData +
Table-Objekte) -- reine Beschreibung, kein Datenbankstart.

Hintergrund (Karo-Entscheidung 2026-08-02, Arbeitspaket "Formales
Migrationssystem"): apps.backend.database.py rief bisher beim reinen
Modulimport unbedingt init_db() (= metadata_obj.create_all(engine)) auf.
Das kollidierte mit einer festen, unveraenderlichen Alembic-Baseline
(0001_baseline_existing_schema.py mit expliziten op.create_table()-
Aufrufen): jeder Import von database.py -- auch durch alembic/env.py oder
apps/backend/alembic_adopt.py, die nur metadata_obj/DATABASE_URL lesen
wollen -- legte die Tabellen sofort real an, sodass die Migration danach
mit "table already exists" scheiterte.

Loesung: Schema-Beschreibung (dieses Modul) und Datenbankstart
(apps.backend.database.init_db(), ausdruecklich bei Anwendungsstart in
main.py aufgerufen, siehe dortigen FastAPI-Lifespan) sind jetzt getrennt.
database.py importiert metadata_obj und alle Tabellen von hier und
exportiert sie unveraendert weiter -- bestehende Importe
(`from apps.backend.database import users, memory_items, ...`) funktionieren
unveraendert.
"""
from __future__ import annotations

import os

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Index, Integer, JSON, MetaData, String, Table, Text,
    CheckConstraint, UniqueConstraint, text,
)

DEFAULT_TENANT_ID = os.getenv("AILIZA_DEFAULT_TENANT_ID", "default")

metadata_obj = MetaData()

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
    # list_audit_entries()/query_audit_events() filtern nach tenant_id und
    # sortieren nach timestamp DESC -- ohne Index ein Volltabellen-Scan, der
    # mit wachsendem (append-only) Audit-Log immer teurer wird.
    Index("ix_audit_logs_tenant_timestamp", "tenant_id", "timestamp"),
    Index("ix_audit_logs_action", "action"),
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
    # PR 1 (Identitaets-/RBAC-Grundlage): Besitzer des zugrundeliegenden Runs.
    # NULL fuer historische Datensaetze -- niemals rueckwirkend geraten/befuellt.
    Column("owner_user_id", String(64), nullable=True),
    # list_approval_requests() filtert nach status, sortiert nach created_at
    # DESC. Beides ungenutzt (Volltabellen-Scan + Sortierung im Speicher).
    Index("ix_approval_requests_status", "status"),
    Index("ix_approval_requests_tenant_created", "tenant_id", "created_at"),
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
    # PR 1: NULL fuer anonyme Runs UND fuer historische Datensaetze ohne Owner.
    # Kein Backfill, keine Vermutung.
    Column("owner_user_id", String(64), nullable=True),
    # list_agent_runs() filtert nach status/tenant_id, sortiert nach
    # updated_at DESC.
    Index("ix_agent_runs_status", "status"),
    Index("ix_agent_runs_tenant_updated", "tenant_id", "updated_at"),
)

# ── PR 1 (Identitaets-/RBAC-Grundlage): Fachzustaendigkeiten und gezielte
# Vorgangszuteilung. Reines Schema -- noch keine Permission-Evaluator-Logik,
# noch keine Endpunkt-Anbindung (folgt in spaeteren PRs). ────────────────────
user_specialist_roles = Table(
    "user_specialist_roles",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String(64), nullable=False),
    Column("tenant_id", String(64), nullable=False),
    Column("specialist_role", String(64), nullable=False),
    Column("assigned_by_user_id", String(64), nullable=False),
    Column("assignment_reason", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=False),
    Column("valid_until", DateTime(timezone=True), nullable=True),
    Column("review_required_at", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("revoked_by_user_id", String(64), nullable=True),
    Column("is_active", Integer, nullable=False, default=1),
    Index(
        "ux_active_specialist_role", "user_id", "tenant_id", "specialist_role",
        unique=True, sqlite_where=text("is_active = 1 AND revoked_at IS NULL"),
    ),
)

case_assignments = Table(
    "case_assignments",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("case_type", String(32), nullable=False),
    Column("case_id", String(64), nullable=False),
    Column("tenant_id", String(64), nullable=False),
    Column("assigned_to_user_id", String(64), nullable=False),
    Column("assigned_by_user_id", String(64), nullable=False),
    Column("assignment_reason", Text, nullable=False),
    Column("assigned_at", DateTime(timezone=True), nullable=False),
    Column("valid_until", DateTime(timezone=True), nullable=True),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("revoked_by_user_id", String(64), nullable=True),
    Index(
        "ux_active_case_assignment", "tenant_id", "case_type", "case_id", "assigned_to_user_id",
        unique=True, sqlite_where=text("revoked_at IS NULL"),
    ),
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
    # Knowledge Phase 1 (Memory Tenant Integrity): NOT NULL fuer ALLE Scopes,
    # auch user_memory. Migration c8ff9bb332ba erzwingt das per fail-closed
    # Guard (bricht bei bestehenden NULL-Zeilen kontrolliert ab, kein
    # automatischer Default-Tenant, kein Backfill in dieser Migration).
    Column("tenant_id", String(64), nullable=False),
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
    # Minimale Aufbewahrungs-Einstellung fuer hochgeladene Dokumente dieses
    # Chats (Karo-Entscheidung 2026-08-03, Grundlage fuer das spaeter
    # geplante vollstaendige Eigenschaftsfenster mit allen drei Kategorien
    # Dokumente/Zusammenfassung/Original-Chat). NULL = Systemstandard
    # (behalten, DEFAULT_DOCUMENT_RETENTION_DAYS Tage) -- siehe
    # database.get_chat_document_retention().
    Column("keep_uploaded_documents", Integer, nullable=True),
    Column("document_retention_days", Integer, nullable=True),
    Index("ix_user_chats_tenant_user", "tenant_id", "user_id"),
)

# ── Model Intelligence (Paket A): reine Empfehlungsschicht ──────────────────
# Waehlt NUR aus bereits im Provider-Orchestrator/der Registry freigegebenen
# Providern/Modellen. Kein eigenes Freigaberecht -- ein Modell mit
# status="candidate" wird vom Router (apps/backend/intelligence/model_router.py)
# nie ausgewaehlt, unabhaengig von seinen Scores. Plattformweite Konfiguration
# (wie provider_registry.yaml), daher KEIN tenant_id/owner_user_id -- die
# Entscheidung, welche Modelle ueberhaupt existieren duerfen, ist keine
# Mandantenentscheidung.
model_candidates = Table(
    "model_candidates",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("provider", String(64), nullable=False),
    Column("model_id", String(128), nullable=False),
    Column("modalities", JSON, nullable=False, default=list),
    Column("capabilities", JSON, nullable=False, default=list),
    Column("context_window", Integer, nullable=False, default=0),
    Column("regions", JSON, nullable=False, default=list),
    # candidate | approved | blocked | retired -- nur "approved" ist waehlbar.
    Column("status", String(32), nullable=False, default="candidate"),
    Column("quality_score", Float, nullable=True),
    Column("latency_score", Float, nullable=True),
    Column("cost_score", Float, nullable=True),
    Column("privacy_score", Float, nullable=True),
    Column("benchmark_version", String(64), nullable=False, default="unbenchmarked"),
    Column("evidence_urls", JSON, nullable=False, default=list),
    Column("approved_by", String(64), nullable=True),
    Column("approved_at", DateTime(timezone=True), nullable=True),
    # B4: Wer den Kandidaten eingebracht hat -- Grundlage der
    # Selbstfreigabe-Pruefung (Vier-Augen-Prinzip) in approve_model_candidate().
    Column("created_by", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_model_candidates_provider_model", "provider", "model_id", unique=True),
    Index("ix_model_candidates_status", "status"),
)

# Append-only Protokoll jeder Routing-Empfehlung -- fuer Nachvollziehbarkeit,
# nicht fuer Freigabeentscheidungen. Enthaelt bewusst KEINEN Prompt-/
# Antwortinhalt (nur die Anfrage-Metadaten, wie im Audit-Vault ueblich).
routing_decisions = Table(
    "routing_decisions",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=False, default=DEFAULT_TENANT_ID),
    Column("modality", String(32), nullable=False),
    Column("task", String(64), nullable=False),
    Column("data_risk", String(16), nullable=False),
    Column("selected", String(192), nullable=True),
    Column("fallback", String(192), nullable=True),
    Column("score", Float, nullable=True),
    Column("reason", Text, nullable=False),
    Column("considered", JSON, nullable=False, default=list),
    Column("benchmark_version", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_routing_decisions_tenant_created", "tenant_id", "created_at"),
)

# ── Phase 1 (Ladengeschaeft-Produktlauf): Kundenstammdaten ──────────────────
# Kleinster abgeschlossener Baustein von Kunde -> Artikel -> Rechnung.
# Artikel und Rechnung sind bewusst NICHT Teil dieses Schritts.
# owner_user_id NUR hier (Anlegerin/Zustaendige der Kundenakte) -- kein
# pauschales Feld auf allen Tabellen, wie in den Arbeitsregeln gefordert.
customers = Table(
    "customers",
    metadata_obj,
    # Zusammengesetzter Primary Key wie bei user_projects/user_chats:
    # (tenant_id, id) isoliert vollstaendig, kein Hijack ueber kollidierende id.
    Column("id", String(64), primary_key=True),
    Column("tenant_id", String(64), primary_key=True, nullable=False, default=DEFAULT_TENANT_ID),
    Column("owner_user_id", String(64), nullable=True),
    Column("name", Text, nullable=False),
    Column("email", Text, nullable=True),
    Column("phone", Text, nullable=True),
    Column("address", Text, nullable=True),
    Column("note", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Index("ix_customers_tenant_owner", "tenant_id", "owner_user_id"),
)

# ── Bereichsfreischaltung und Rechteverwaltung V1 ───────────────────────────
# Fachliche Unternehmensbereiche (Buchhaltung, Vertrieb, ...) sind STRIKT
# getrennt von den Governance-Zustaendigkeiten in user_specialist_roles:
# "darf freigeben" (Fachrolle) und "darf sehen" (Bereichsmitgliedschaft) sind
# unterschiedliche Dimensionen und duerfen nicht vermischt werden.

# Globales, festes Vokabular -- KEINE Mandantendaten. Codes sind nach
# Inbetriebnahme unveraenderlich; Bereiche werden deaktiviert, nie geloescht.
business_domains = Table(
    "business_domains",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("code", String(64), nullable=False, unique=True),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("category", String(64), nullable=True),
    # normal | high | confidential -- schraenkt zusaetzlich ein, erweitert nie.
    Column("sensitivity_level", String(32), nullable=False, default="normal"),
    Column("is_system_domain", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("sensitivity_level IN ('normal','high','confidential')",
                    name="ck_bd_sensitivity"),
    CheckConstraint("is_system_domain IN (0,1)", name="ck_bd_system_flag"),
)

# Aktivierung je Mandant. Kein Eintrag ODER is_enabled=0 bedeutet: Bereich im
# Mandanten nicht nutzbar (fail-closed, kein impliziter Zugriff).
tenant_business_domains = Table(
    "tenant_business_domains",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=False),
    Column("domain_id", Integer, ForeignKey("business_domains.id"), nullable=False),
    Column("is_enabled", Integer, nullable=False, default=0),
    Column("enabled_by", String(64), nullable=True),
    Column("enabled_at", DateTime(timezone=True), nullable=True),
    Column("disabled_by", String(64), nullable=True),
    Column("disabled_at", DateTime(timezone=True), nullable=True),
    # Begruendungspflicht: NOT NULL allein genuegt nicht -- eine leere oder
    # nur aus Leerraum bestehende Angabe waere keine Begruendung.
    Column("reason", Text, nullable=False),
    Column("version", Integer, nullable=False, default=1),
    UniqueConstraint("tenant_id", "domain_id", name="uq_tenant_domain"),
    CheckConstraint("is_enabled IN (0,1)", name="ck_tbd_enabled"),
    CheckConstraint("LENGTH(TRIM(reason)) >= 3", name="ck_tbd_reason_not_blank"),
    Index("ix_tenant_business_domains_tenant", "tenant_id", "is_enabled"),
)

# Mitgliedschaft eines Nutzers in einem Fachbereich. Befristbar, pruefbar und
# sofort widerrufbar; abgelaufene Zuweisungen gelten sofort als inaktiv.
user_domain_memberships = Table(
    "user_domain_memberships",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=False),
    Column("domain_id", Integer, ForeignKey("business_domains.id"), nullable=False),
    Column("user_id", String(64), nullable=False),
    # viewer | contributor | reviewer | domain_manager
    Column("role_in_domain", String(32), nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=False),
    Column("valid_until", DateTime(timezone=True), nullable=True),
    Column("review_required_at", DateTime(timezone=True), nullable=True),
    Column("assigned_by", String(64), nullable=False),
    Column("assignment_reason", Text, nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("revoked_by", String(64), nullable=True),
    Column("revocation_reason", Text, nullable=True),
    Column("is_active", Integer, nullable=False, default=1),
    Column("version", Integer, nullable=False, default=1),
    CheckConstraint(
        "role_in_domain IN ('viewer','contributor','reviewer','domain_manager')",
        name="ck_udm_role"),
    CheckConstraint("is_active IN (0,1)", name="ck_udm_active_flag"),
    # Aktiv und widerrufen schliessen einander aus -- sonst gaelte ein
    # widerrufener Zugriff weiter und der Widerruf waere wirkungslos.
    CheckConstraint(
        "(is_active = 1 AND revoked_at IS NULL) OR "
        "(is_active = 0 AND revoked_at IS NOT NULL) OR "
        "(is_active = 0 AND revoked_at IS NULL)",
        name="ck_udm_revoked"),
    CheckConstraint("valid_until IS NULL OR valid_until > valid_from",
                    name="ck_udm_validity"),
    CheckConstraint("LENGTH(TRIM(assignment_reason)) >= 3", name="ck_udm_reason_not_blank"),
    CheckConstraint(
        "revoked_at IS NULL OR LENGTH(TRIM(COALESCE(revocation_reason,''))) >= 3",
        name="ck_udm_revocation_reason"),
    Index("ix_user_domain_memberships_lookup", "tenant_id", "user_id", "is_active"),
    Index("ix_user_domain_memberships_domain", "tenant_id", "domain_id", "is_active"),
    Index("uq_udm_active_member", "tenant_id", "domain_id", "user_id",
          unique=True, sqlite_where=text("is_active = 1"),
          postgresql_where=text("is_active = 1")),
)

# Welche Aktion darf eine Bereichsrolle in einem Bereich ausfuehren.
# Default ist KEIN Zugriff: fehlt eine Zeile, gilt sie als verweigert.
domain_role_permissions = Table(
    "domain_role_permissions",
    metadata_obj,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tenant_id", String(64), nullable=False),
    Column("domain_id", Integer, ForeignKey("business_domains.id"), nullable=False),
    Column("role_in_domain", String(32), nullable=False),
    # domain.view | content.read | content.create | content.update |
    # content.approve | content.export | action.execute | membership.manage
    Column("action", String(64), nullable=False),
    Column("allowed", Integer, nullable=False, default=0),
    Column("granted_by", String(64), nullable=True),
    Column("granted_at", DateTime(timezone=True), nullable=True),
    Column("reason", Text, nullable=False),
    Column("version", Integer, nullable=False, default=1),
    UniqueConstraint("tenant_id", "domain_id", "role_in_domain", "action",
                     name="uq_domain_role_action"),
    CheckConstraint(
        "role_in_domain IN ('viewer','contributor','reviewer','domain_manager')",
        name="ck_drp_role"),
    CheckConstraint(
        "action IN ('domain.view','content.read','content.create','content.update',"
        "'content.approve','content.export','action.execute','membership.manage')",
        name="ck_drp_action"),
    CheckConstraint("allowed IN (0,1)", name="ck_drp_allowed"),
    CheckConstraint("LENGTH(TRIM(reason)) >= 3", name="ck_drp_reason_not_blank"),
    Index("ix_domain_role_permissions_lookup", "tenant_id", "domain_id", "role_in_domain"),
)
