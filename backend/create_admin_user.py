"""Create an admin user for the system."""

import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.models import User, UserRole, ApprovalStatus
from app.services.auth import get_password_hash


def create_admin_user(email: str, name: str, password: str):
    """Create an admin user with full privileges."""
    db = SessionLocal()
    
    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            print(f"❌ User with email {email} already exists!")
            if existing_user.role == UserRole.ADMIN:
                print(f"✅ User is already an admin.")
            else:
                print(f"   Current role: {existing_user.role.value}")
                print(f"   To make this user an admin, run:")
                print(f"   UPDATE users SET role='admin', approval_status='approved' WHERE email='{email}';")
            return
        
        # Create admin user
        user = User(
            email=email,
            name=name,
            password_hash=get_password_hash(password),
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED,
            approved_at=datetime.utcnow(),
            approved_by=None,  # Self-approved (bootstrap)
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        print("✅ Admin user created successfully!")
        print(f"\n📧 Email: {user.email}")
        print(f"👤 Name: {user.name}")
        print(f"🔑 Role: {user.role.value}")
        print(f"✓ Approval Status: {user.approval_status.value}")
        print(f"🆔 User ID: {user.id}")
        print(f"\nYou can now login with:")
        print(f"  Email: {email}")
        print(f"  Password: [the password you provided]")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating admin user: {e}")
        raise
    finally:
        db.close()


def main():
    """Main entry point."""
    print("=" * 60)
    print("Create Admin User")
    print("=" * 60)
    
    # Get user input
    print("\nEnter admin user details:")
    email = input("Email: ").strip()
    name = input("Name: ").strip()
    password = input("Password: ").strip()
    
    if not email or not name or not password:
        print("❌ All fields are required!")
        return
    
    # Confirm
    print(f"\nYou are about to create an admin user:")
    print(f"  Email: {email}")
    print(f"  Name: {name}")
    confirm = input("\nContinue? (yes/no): ").strip().lower()
    
    if confirm not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    create_admin_user(email, name, password)


if __name__ == "__main__":
    main()
