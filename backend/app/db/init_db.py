"""Database initialization utilities."""
from app.db.session import engine, Base
from app.models.models import (
    User,
    Session,
    Message,
    WorkflowEvent,
    ToolCall,
    Approval,
    WorkflowClassification,
    UserPreference,
    WorkflowMemory,
    DomainKnowledge,
)


def init_db():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")


def drop_all():
    """Drop all database tables. Use with caution!"""
    Base.metadata.drop_all(bind=engine)
    print("All database tables dropped")


if __name__ == "__main__":
    print("Initializing database...")
    init_db()
