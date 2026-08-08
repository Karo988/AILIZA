"""baseline: bestehende 27-Tabellen-Schema als Alembic-Ausgangsstand

Revision ID: 6165ff33e9ee
Revises:
Create Date: 2026-08-02

WICHTIG (Adoption eines bereits gewachsenen Schemas, kein Neubau):
Diese Baseline-Migration bildet das Schema, das ueber
apps.backend.database.metadata_obj (SQLAlchemy Core, 27 Tabellen) sowohl bei
neuen Datenbanken (init_db()/metadata_obj.create_all) als auch in der
bestehenden Produktions-/Dev-Datenbank existiert, FUNKTIONAL 1:1 nach --
mit expliziten op.create_table()/op.create_index()-Aufrufen statt eines
Imports von metadata_obj. Grund: diese Migration ist damit unabhaengig von
kuenftigen Aenderungen an database.py -- der historische Ausgangsstand bleibt
stabil, auch wenn sich das ORM-Modell spaeter weiterentwickelt.

Bewusst NICHT Teil dieser Migration (Karo-Entscheidung 2026-08-02):
  - Die zwei partiellen Unique-Indizes (ux_active_specialist_role,
    ux_active_case_assignment) haben in database.py nur sqlite_where, KEIN
    postgresql_where. Unter PostgreSQL werden sie dadurch aktuell als volle
    (nicht-partielle) Unique-Indizes angelegt -- das ist eine bestehende,
    bekannte Abweichung. Diese Migration 0001 bildet genau dieses Verhalten
    1:1 ab (kein postgresql_where hier). Die Korrektur folgt bewusst separat
    in Migration 0002, NACH Pruefung/Uebernahme bestehender Datenbanken.
  - Fremdschluessel ohne explizites `name=` in database.py (memory_items.
    source_id, memory_visibility.memory_item_id, knowledge_chunks.source_id,
    knowledge_source_permissions.source_id) werden hier mit von SQLAlchemy
    automatisch vergebenen Namen angelegt -- keine Umbenennung, kein
    Drop/Recreate nur zur Namensgebung an bestehenden Datenbanken. Ab dieser
    Migration werden fuer NEUE Migrationen feste, eindeutige Namen verwendet
    (siehe 0002).

downgrade() ist ABSICHTLICH nicht implementiert (raise) -- ein Downgrade
dieser Baseline wuerde de facto "alle 27 Tabellen loeschen" bedeuten. Das
widerspricht der Vorgabe "keine Daten loeschen oder veraendern" und wird
deshalb nicht angeboten, bis ein bewusst freigegebener, gesonderter
Rueckbau-Prozess existiert.

Diese Migration ERSETZT NICHT ensure_sqlite_schema() (siehe database.py) --
beide existieren aktuell parallel. Das Ablösen von ensure_sqlite_schema()
ist ausdruecklich NICHT Teil dieses Arbeitspakets.

Bestehende Datenbanken: NICHT direkt mit `alembic upgrade head` gegen diese
Migration laufen lassen (die Tabellen existieren dort bereits -> Fehler
"table already exists"). Stattdessen erst pruefen und stempeln, siehe
apps/backend/alembic_adopt.py ("python -m apps.backend.alembic_adopt").
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6165ff33e9ee"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_TENANT_ID = "default"


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("metadata", sa.JSON, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False),
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("input_params", sa.JSON, nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("risk_reason", sa.Text, nullable=False),
        sa.Column("required_approver_roles", sa.JSON, nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_user_id", sa.String(64), nullable=True),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("pending_approval_id", sa.Integer, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("run_metadata", sa.JSON, nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("owner_user_id", sa.String(64), nullable=True),
    )

    op.create_table(
        "user_specialist_roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("specialist_role", sa.String(64), nullable=False),
        sa.Column("assigned_by_user_id", sa.String(64), nullable=False),
        sa.Column("assignment_reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_required_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Integer, nullable=False),
    )
    op.create_index(
        "ux_active_specialist_role", "user_specialist_roles",
        ["user_id", "tenant_id", "specialist_role"], unique=True,
        sqlite_where=sa.text("is_active = 1 AND revoked_at IS NULL"),
    )

    op.create_table(
        "case_assignments",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("case_type", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("assigned_to_user_id", sa.String(64), nullable=False),
        sa.Column("assigned_by_user_id", sa.String(64), nullable=False),
        sa.Column("assignment_reason", sa.Text, nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ux_active_case_assignment", "case_assignments",
        ["tenant_id", "case_type", "case_id", "assigned_to_user_id"], unique=True,
        sqlite_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "security_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("incident_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "performance_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer, nullable=False),
        sa.Column("route", sa.String(32), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("error_type", sa.String(64), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "cost_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False),
        sa.Column("tokens_out", sa.Integer, nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("use_case", sa.String(128), nullable=True),
        sa.Column("cost_estimate", sa.Float, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "reflection_facts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("data_classes", sa.JSON, nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("quality_score", sa.Float, nullable=False),
        sa.Column("opt_in_confirmed", sa.Integer, nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("expires_at", sa.String(40), nullable=False),
        sa.Column("source", sa.String(64), nullable=True),
        sa.Column("purpose", sa.String(128), nullable=True),
        sa.Column("pii_cleared", sa.Integer, nullable=False),
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("rating", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("quality_score_delta", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "routing_proposals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("trigger_type", sa.String(64), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("previous_route", sa.String(32), nullable=True),
        sa.Column("proposed_route", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("changed_by", sa.String(64), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_version", sa.String(32), nullable=True),
    )

    op.create_table(
        "kill_switch_state",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("enabled", sa.Integer, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Integer, nullable=False),
        sa.Column("failed_login_attempts", sa.Integer, nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "user_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("antwortlaenge", sa.String(32), nullable=False),
        sa.Column("ton", sa.String(32), nullable=False),
        sa.Column("sprache", sa.String(8), nullable=True),
        sa.Column("ausgabeformat", sa.String(32), nullable=True),
        sa.Column("ui_prefs", sa.JSON, nullable=False),
        sa.Column("benachrichtigungen", sa.JSON, nullable=False),
        sa.Column("aktives_merken", sa.Integer, nullable=False),
        sa.Column("sichtbare_zusammenfassungen_erlaubt", sa.Integer, nullable=False),
        sa.Column("erinnerungs_vorschlaege_erlaubt", sa.Integer, nullable=False),
        sa.Column("speichermodus", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_user_settings_user_tenant", "user_settings", ["user_id", "tenant_id"], unique=True,
    )

    op.create_table(
        "memory_sources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column("source_title", sa.String(255), nullable=True),
        sa.Column("source_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by", sa.String(64), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "memory_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("owner_user_id", sa.String(64), nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("purpose", sa.Text, nullable=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("memory_sources.id"), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_items_owner", "memory_items", ["owner_user_id"])
    op.create_index("ix_memory_items_tenant_status", "memory_items", ["tenant_id", "status"])

    op.create_table(
        "memory_visibility",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("memory_item_id", sa.Integer, sa.ForeignKey("memory_items.id"),
                  nullable=False, unique=True),
        sa.Column("visibility_scope", sa.String(32), nullable=False),
        sa.Column("allowed_roles", sa.JSON, nullable=False),
        sa.Column("allowed_user_ids", sa.JSON, nullable=False),
        sa.Column("allowed_org_id", sa.String(64), nullable=True),
        sa.Column("project_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "memory_suggestions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("suggested_scope", sa.String(32), nullable=False),
        sa.Column("suggested_title", sa.Text, nullable=False),
        sa.Column("suggested_content", sa.Text, nullable=True),
        sa.Column("suggested_category", sa.String(64), nullable=True),
        sa.Column("suggested_purpose", sa.Text, nullable=True),
        sa.Column("source_type", sa.String(32), nullable=True),
        sa.Column("source_reference", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("requires_admin_approval", sa.Integer, nullable=False),
        sa.Column("project_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_memory_suggestions_user_tenant", "memory_suggestions", ["user_id", "tenant_id"],
    )

    op.create_table(
        "messenger_bindings",
        sa.Column("chat_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("telegram_username", sa.String(128), nullable=True),
        sa.Column("opt_in_confirmed", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opt_in_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "totp_secrets",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("secret_b32", sa.String(64), nullable=False),
        sa.Column("confirmed", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "totp_backup_codes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used", sa.Integer, nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "skills",
        sa.Column("skill_id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("steps_summary", sa.Text, nullable=False),
        sa.Column("data_classes", sa.JSON, nullable=True),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("gdpr_purpose", sa.String(256), nullable=True),
        sa.Column("source_run_id", sa.String(36), nullable=True),
        sa.Column("proposed_by", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("rejection_reason", sa.String(512), nullable=True),
    )

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("uploaded_by", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("storage_path", sa.String(512), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("visibility_scope", sa.String(32), nullable=False),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_knowledge_sources_tenant_status", "knowledge_sources", ["tenant_id", "status"],
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("knowledge_sources.id"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("chunk_hash", sa.String(64), nullable=True),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("section_title", sa.String(255), nullable=True),
        sa.Column("token_estimate", sa.Integer, nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_chunks_source", "knowledge_chunks", ["source_id"])

    op.create_table(
        "knowledge_source_permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("knowledge_sources.id"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("visibility_scope", sa.String(32), nullable=False),
        sa.Column("allowed_roles", sa.JSON, nullable=False),
        sa.Column("allowed_user_ids", sa.JSON, nullable=False),
        sa.Column("project_id", sa.String(64), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_knowledge_source_permissions_source", "knowledge_source_permissions", ["source_id"],
    )

    op.create_table(
        "user_projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("priority", sa.String(32), nullable=True),
        sa.Column("chat_id", sa.String(64), nullable=True),
        sa.Column("files", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False),
    )
    op.create_index("ix_user_projects_tenant_user", "user_projects", ["tenant_id", "user_id"])

    op.create_table(
        "user_chats",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("user_id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(64), nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("messages", sa.JSON, nullable=False),
        sa.Column("message_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("keep_uploaded_documents", sa.Integer(), nullable=True),
        sa.Column("document_retention_days", sa.Integer(), nullable=True),
    )
    op.create_index("ix_user_chats_tenant_user", "user_chats", ["tenant_id", "user_id"])


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade der Baseline-Migration ist absichtlich nicht "
        "implementiert -- wuerde alle 27 AILIZA-Kerntabellen loeschen. "
        "Kein automatischer Datenverlust ohne gesonderten, bewusst "
        "freigegebenen Rueckbau-Prozess."
    )
