-- Migration: Add timeout_seconds field to tenant_skills table
-- Bug #11: Allow per-skill timeout configuration
-- Date: 2026-06-09

-- Add timeout_seconds column (nullable, defaults to NULL meaning use global timeout)
ALTER TABLE tenant_skills
ADD COLUMN timeout_seconds INTEGER DEFAULT NULL;

-- Add comment explaining the field
COMMENT ON COLUMN tenant_skills.timeout_seconds IS
  'Optional per-skill timeout override in seconds. NULL means use global timeout (180s default). Bug #11 fix.';
