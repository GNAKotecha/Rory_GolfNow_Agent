-- Migration: Add require_tool_approval to users table
-- Date: 2026-04-28
-- Purpose: Implement fail-safe approval workflow system

-- Add require_tool_approval column (defaults to False for MVP)
ALTER TABLE users
ADD COLUMN require_tool_approval BOOLEAN NOT NULL DEFAULT FALSE;

-- Add index for filtering users by approval requirement
CREATE INDEX idx_users_require_tool_approval ON users(require_tool_approval);

-- To enable approvals for all admins:
-- UPDATE users SET require_tool_approval = TRUE WHERE role = 'admin';
