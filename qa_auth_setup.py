#!/usr/bin/env python3
"""Setup auth tokens for QA execution."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.db.session import SessionLocal
from app.models.models import User, UserRole, Tenant
from app.services.auth import create_access_token, get_password_hash

def setup_qa_auth():
    """Create QA user and get auth token."""
    db = SessionLocal()

    try:
        # Get or create tenant
        tenant = db.query(Tenant).first()
        if not tenant:
            print("ERROR: No tenant found")
            return None

        # Get or create QA user
        qa_email = "qa@executor.local"
        qa_user = db.query(User).filter(User.email == qa_email).first()
        if not qa_user:
            qa_user = User(
                name="QA Executor",
                email=qa_email,
                tenant_id=tenant.id,
                role=UserRole.ADMIN,
                approval_status="APPROVED",
                password_hash=get_password_hash("qa_password_123")
            )
            db.add(qa_user)
            db.commit()
            print(f"✅ Created QA user: {qa_email}")
        else:
            print(f"✅ Using existing QA user: {qa_email}")

        # Generate token
        token = create_access_token(
            data={"sub": str(qa_user.id), "tenant_id": str(tenant.id)}
        )

        print(f"\n📋 QA Auth Setup Complete")
        print(f"User ID: {qa_user.id}")
        print(f"Tenant ID: {tenant.id}")
        print(f"\nAuth Token (add to requests):")
        print(f"Authorization: Bearer {token}")

        return {
            "user_id": str(qa_user.id),
            "tenant_id": str(tenant.id),
            "token": token
        }
    finally:
        db.close()

if __name__ == "__main__":
    setup_qa_auth()
