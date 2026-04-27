#!/usr/bin/env python3
"""
Create an admin user directly in the database.

Usage:
    # Interactive mode:
    export DATABASE_URL="postgresql://..."
    python scripts/create-admin-user.py

    # Command-line args:
    python scripts/create-admin-user.py --username admin --email admin@test.com --password MyPass123
"""

import os
import sys
import argparse
from datetime import datetime
from getpass import getpass

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from passlib.context import CryptContext
from sqlalchemy import create_engine, text

# Password hashing (same as in backend)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    return pwd_context.hash(password)


def create_admin_user(database_url: str, username: str, email: str, password: str):
    """Create an admin user in the database."""

    # Create database engine
    engine = create_engine(database_url)

    # Hash the password
    hashed_password = hash_password(password)

    # SQL to insert admin user
    insert_sql = text("""
        INSERT INTO users (username, email, hashed_password, role, status, created_at)
        VALUES (:username, :email, :hashed_password, 'ADMIN', 'APPROVED', :created_at)
        RETURNING id, username, email, role, status;
    """)

    try:
        with engine.connect() as conn:
            # Check if user already exists
            check_sql = text("SELECT id FROM users WHERE username = :username OR email = :email")
            result = conn.execute(check_sql, {"username": username, "email": email})
            if result.fetchone():
                print(f"❌ Error: User with username '{username}' or email '{email}' already exists")
                return False

            # Insert admin user
            result = conn.execute(insert_sql, {
                "username": username,
                "email": email,
                "hashed_password": hashed_password,
                "created_at": datetime.utcnow()
            })
            conn.commit()

            user = result.fetchone()
            print("\n✅ Admin user created successfully!")
            print(f"   ID: {user[0]}")
            print(f"   Username: {user[1]}")
            print(f"   Email: {user[2]}")
            print(f"   Role: {user[3]}")
            print(f"   Status: {user[4]}")
            print("\n🔐 You can now login with:")
            print(f"   Username: {username}")
            print(f"   Password: [the password you entered]")
            return True

    except Exception as e:
        print(f"❌ Error creating admin user: {e}")
        return False
    finally:
        engine.dispose()


def main():
    """Main function."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Create an admin user in the database")
    parser.add_argument("--username", "-u", help="Admin username")
    parser.add_argument("--email", "-e", help="Admin email")
    parser.add_argument("--password", "-p", help="Admin password")
    args = parser.parse_args()

    print("=" * 60)
    print("Create Admin User")
    print("=" * 60)
    print()

    # Get database URL from environment
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("❌ Error: DATABASE_URL environment variable not set")
        print()
        print("Set it with:")
        print('  export DATABASE_URL="postgresql://..."')
        print()
        return 1

    # Get user details (from args or prompt)
    if args.username:
        username = args.username
    else:
        print("Enter admin user details:")
        print()
        username = input("Username: ").strip()

    if not username:
        print("❌ Error: Username cannot be empty")
        return 1

    if args.email:
        email = args.email
    else:
        email = input("Email: ").strip()

    if not email:
        print("❌ Error: Email cannot be empty")
        return 1

    if args.password:
        password = args.password
    else:
        password = getpass("Password: ")
        if not password:
            print("❌ Error: Password cannot be empty")
            return 1

        password_confirm = getpass("Confirm password: ")
        if password != password_confirm:
            print("❌ Error: Passwords do not match")
            return 1

    print()
    print(f"Creating admin user '{username}'...")
    print()

    # Create admin user
    success = create_admin_user(database_url, username, email, password)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
