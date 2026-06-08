#!/usr/bin/env python3
"""
Seed script to create the REINSTATE_USER skill in the database.

This script connects to the SQLite database and inserts the REINSTATE_USER skill
with intent patterns for semantic matching.
"""
import sys
import os
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select
from app.models.models import TenantSkill, Tenant, User
from app.db.session import SessionLocal, engine
from app.core.config import settings
import json


def seed_reinstate_skill():
    """Create and seed the REINSTATE_USER skill."""
    # Get database URL from settings
    print(f"Connecting to database: {settings.database_url}")

    # Create session using existing engine
    db = SessionLocal()

    try:
        # Get tenant_id (assume tenant 1 exists)
        tenant = db.execute(select(Tenant)).scalars().first()
        if not tenant:
            print("ERROR: No tenant found in database. Please create a tenant first.")
            return False

        print(f"Found tenant: {tenant.name} (id={tenant.id})")

        # Get first user for created_by field
        user = db.execute(select(User)).scalars().first()
        created_by = user.id if user else None
        if user:
            print(f"Using user: {user.email} (id={user.id}) as creator")

        # Check if skill already exists
        existing_skill = db.execute(
            select(TenantSkill).where(
                TenantSkill.tenant_id == tenant.id,
                TenantSkill.skill_name == "Reinstate User"
            )
        ).scalars().first()

        if existing_skill:
            print(f"Skill 'Reinstate User' already exists (id={existing_skill.id}, active={existing_skill.is_active})")
            print("Updating existing skill...")

            # Update existing skill
            existing_skill.description = "Restore a deleted user account by finding the _deleted version and creating a new user with original credentials"
            existing_skill.intent_patterns = [
                "reinstate.*user",
                "restore.*user.*account",
                "reactivate.*member",
                "recover.*deleted.*user",
                "undelete.*user",
                "bring.*back.*user"
            ]
            existing_skill.is_active = True
            existing_skill.skill_data = {
                "workflow_type": "user_management",
                "requires_approval": False,
                "steps": [
                    "Identify deleted user by ID",
                    "Locate _deleted user record in database",
                    "Extract original user credentials",
                    "Create new user with original data",
                    "Verify reinstatement"
                ]
            }
            db.commit()
            print(f"✓ Updated skill 'Reinstate User' (id={existing_skill.id})")
            skill_id = existing_skill.id
        else:
            # Create new skill
            skill = TenantSkill(
                tenant_id=tenant.id,
                skill_name="Reinstate User",
                description="Restore a deleted user account by finding the _deleted version and creating a new user with original credentials",
                skill_data={
                    "workflow_type": "user_management",
                    "requires_approval": False,
                    "steps": [
                        "Identify deleted user by ID",
                        "Locate _deleted user record in database",
                        "Extract original user credentials",
                        "Create new user with original data",
                        "Verify reinstatement"
                    ]
                },
                intent_patterns=[
                    "reinstate.*user",
                    "restore.*user.*account",
                    "reactivate.*member",
                    "recover.*deleted.*user",
                    "undelete.*user",
                    "bring.*back.*user"
                ],
                is_active=True,
                version=1,
                created_by=created_by
            )

            db.add(skill)
            db.commit()
            db.refresh(skill)

            print(f"✓ Created skill 'Reinstate User' (id={skill.id})")
            skill_id = skill.id

        # Verify creation
        print("\nVerifying skill in database...")
        verification_skill = db.execute(
            select(TenantSkill).where(TenantSkill.id == skill_id)
        ).scalars().first()

        if verification_skill:
            print(f"✓ Skill verified:")
            print(f"  - ID: {verification_skill.id}")
            print(f"  - Name: {verification_skill.skill_name}")
            print(f"  - Active: {verification_skill.is_active}")
            print(f"  - Tenant ID: {verification_skill.tenant_id}")
            print(f"  - Version: {verification_skill.version}")
            print(f"  - Intent Patterns: {json.dumps(verification_skill.intent_patterns, indent=4)}")
            return True
        else:
            print("ERROR: Failed to verify skill creation")
            return False

    except Exception as e:
        print(f"ERROR: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("REINSTATE_USER Skill Seeding Script")
    print("=" * 60)

    success = seed_reinstate_skill()

    if success:
        print("\n✓ SUCCESS: REINSTATE_USER skill seeded successfully")
        sys.exit(0)
    else:
        print("\n✗ FAILED: Could not seed REINSTATE_USER skill")
        sys.exit(1)
