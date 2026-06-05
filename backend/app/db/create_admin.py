"""Create default admin user for initial setup."""
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models.models import User, UserRole, ApprovalStatus, Tenant
from app.services.auth import get_password_hash


def create_admin_user():
    """Create default admin user if it doesn't exist."""
    db: Session = SessionLocal()
    try:
        # Create default tenant if it doesn't exist
        tenant = db.query(Tenant).filter(Tenant.slug == "default").first()
        if not tenant:
            tenant = Tenant(
                name="Default Organization",
                slug="default"
            )
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print("✅ Created default tenant")

        # Check if admin already exists
        admin = db.query(User).filter(User.email == "admin@example.com").first()
        if admin:
            print("Admin user already exists")
            return

        # Create admin user
        admin = User(
            tenant_id=tenant.id,
            email="admin@example.com",
            name="Admin User",
            password_hash=get_password_hash("admin123"),  # Change this in production!
            role=UserRole.ADMIN,
            approval_status=ApprovalStatus.APPROVED,
        )
        db.add(admin)

        try:
            db.commit()
            print("✅ Created default admin user:")
            print("   Email: admin@example.com")
            print("   Password: admin123")
            print("   ⚠️  CHANGE THIS PASSWORD IN PRODUCTION!")
        except IntegrityError:
            # Handle race condition: another process created the user between check and commit
            db.rollback()
            print("Admin user already exists (created by concurrent process)")

    finally:
        db.close()


if __name__ == "__main__":
    from app.db.init_db import init_db
    print("Initializing database...")
    init_db()
    print("\nCreating admin user...")
    create_admin_user()
