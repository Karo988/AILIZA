/**
 * Migration: Sanitize audit_logs by removing raw task/response data
 *
 * Purpose: DSGVO compliance - audit logs shall not store full PII/payloads
 * Instead: Store only metadata (request_id, pii_count, pii_categories, error_code)
 *
 * Status: Bereit für kontrollierte Testumgebung und Governance-Review.
 * Nicht produktionsreif. Nicht zertifiziert.
 */

BEGIN;

-- Add new audit-safe columns if not exist
ALTER TABLE audit_logs
ADD COLUMN IF NOT EXISTS pii_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS pii_categories JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS error_code VARCHAR(100),
ADD COLUMN IF NOT EXISTS highest_data_class VARCHAR(50),
ADD COLUMN IF NOT EXISTS legal_hold BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS legal_hold_reason_code VARCHAR(100),
ADD COLUMN IF NOT EXISTS legal_hold_until TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS held_by_user_id VARCHAR(255);

-- Migrate old task/response data: set to NULL
UPDATE audit_logs
SET task = NULL,
    response = NULL
WHERE task IS NOT NULL OR response IS NOT NULL;

-- Add constraint preventing new writes to task/response
ALTER TABLE audit_logs
ADD CONSTRAINT no_raw_task_or_response
CHECK (task IS NULL AND response IS NULL);

-- Create legal_holds table if not exist
CREATE TABLE IF NOT EXISTS legal_holds (
    id SERIAL PRIMARY KEY,
    log_id VARCHAR(255) NOT NULL REFERENCES audit_logs(id) ON DELETE CASCADE,
    reason_code VARCHAR(100) NOT NULL,
    hold_until TIMESTAMP WITH TIME ZONE NOT NULL,
    held_by_user_id VARCHAR(255) NOT NULL,
    technical_details JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(log_id)
);

CREATE INDEX IF NOT EXISTS idx_legal_holds_log_id ON legal_holds(log_id);
CREATE INDEX IF NOT EXISTS idx_legal_holds_hold_until ON legal_holds(hold_until);

-- Create approval_logs table if not exist
CREATE TABLE IF NOT EXISTS approval_logs (
    id VARCHAR(36) PRIMARY KEY,
    request_id VARCHAR(255) NOT NULL UNIQUE,
    pii_categories TEXT[] NOT NULL,
    data_class VARCHAR(50) NOT NULL,
    highest_risk_level VARCHAR(50) NOT NULL,
    redacted_preview TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    decision VARCHAR(50),
    decision_reason_code VARCHAR(100),
    decided_by_user_id VARCHAR(255),
    decided_at TIMESTAMP WITH TIME ZONE,
    legal_hold BOOLEAN DEFAULT FALSE,
    legal_hold_reason_code VARCHAR(100),
    legal_hold_until TIMESTAMP WITH TIME ZONE,
    held_by_user_id VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_approval_logs_request_id ON approval_logs(request_id);
CREATE INDEX IF NOT EXISTS idx_approval_logs_expires_at ON approval_logs(expires_at);
CREATE INDEX IF NOT EXISTS idx_approval_logs_legal_hold ON approval_logs(legal_hold);

COMMIT;
