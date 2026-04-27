"""Create default admin user for initial setup."""
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.models import User, UserRole, ApprovalStatus
from app.services.auth import get_password_hash


def create_admin_user():
    """Create default admin user if it doesn't exist."""
    db: Session = SessionLocal()
    try:
        # Check if admin already exists
        admin = db.query(User).filter(User.email == "admin@example.com").first()
        if admin:
            print("Admin user already exists")
            return

        # Create admin user
        admin = User(
            email="admin@example.com",
            name="Admin User",
            password_hash=get_password_hash("admin123"),  # Change this in production!
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED,
        )
        db.add(admin)
        db.commit()
        print("✅ Created default admin user:")
        print("   Email: admin@example.com")
        print("   Password: admin123")
        print("   ⚠️  CHANGE THIS PASSWORD IN PRODUCTION!")

    finally:
        db.close()


if __name__ == "__main__":
    from app.db.init_db import init_db
    print("Initializing database...")
    init_db()
    print("\nCreating admin user...")
    create_admin_user()
