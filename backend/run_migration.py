#!/usr/bin/env python3
"""Run database migration to add require_tool_approval column."""
import sys
from sqlalchemy import create_engine, text
from app.config.settings import settings

def run_migration():
    """Apply the migration SQL."""
    print(f"Connecting to database: {settings.database_url.split('@')[-1]}")  # Hide credentials

    engine = create_engine(settings.database_url)

    migration_sql = """
    -- Add require_tool_approval column (defaults to False for MVP)
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS require_tool_approval BOOLEAN NOT NULL DEFAULT FALSE;

    -- Add index for filtering users by approval requirement
    CREATE INDEX IF NOT EXISTS idx_users_require_tool_approval ON users(require_tool_approval);
    """

    try:
        with engine.connect() as conn:
            print("Running migration...")
            conn.execute(text(migration_sql))
            conn.commit()
            print("✓ Migration completed successfully!")
            print("  - Added require_tool_approval column to users table")
            print("  - Created index on require_tool_approval")
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
