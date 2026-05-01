"""Pytest configuration and fixtures."""
import sys
import os
from pathlib import Path
import pytest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Set dummy environment variables for testing
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['OLLAMA_URL'] = 'http://localhost:11434'
os.environ['SECRET_KEY'] = 'test-secret-key-for-testing-only'

# Add backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.session import Base

# Load workflow fixtures
pytest_plugins = [
    "tests.fixtures.workflow_fixtures",
]


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    # Use in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    yield session

    session.close()
